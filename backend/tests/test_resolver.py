from pathlib import Path

import app.ontology.resolver as resolver
from app.ontology.taxonomy import load


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate_structured(self, prompt, schema):
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else {"entities": [], "relationships": []}


def _run(monkeypatch, provider, schema_data, docs, batch_chars=None):
    monkeypatch.setattr(resolver, "get_provider", lambda: provider)
    if batch_chars:
        monkeypatch.setattr(resolver, "BATCH_CHARS", batch_chars)
    return resolver.resolve_entities(schema_data, load(), docs)


PG = {"source": "postgres", "schema": {"products": [{"column": "product_id"}]},
      "samples": {"products": [{"product_id": "LP-4471", "name": "Laptop Pro 14"}]}}
DRUID = {"source": "druid", "schema": {"inventory_events": [{"column": "sku_code"}]},
         "samples": {"inventory_events": [{"sku_code": "LP4471"}]}}
DOC = {"name": "report_001.txt", "path": "/x/report_001.txt",
       "text": "Incident MNT-2024-001: unit SKU LP-4471 failed at WH-EAST."}


def test_documents_are_part_of_resolution_input(monkeypatch):
    p = FakeProvider([])
    _run(monkeypatch, p, [PG], [DOC])
    assert any("SKU LP-4471 failed at WH-EAST" in prompt for prompt in p.prompts)


def test_input_is_batched_not_truncated(monkeypatch):
    big = {"source": "postgres", "schema": {f"t{i}": [{"column": "c"}] for i in range(30)},
           "samples": {f"t{i}": [{"c": f"VALUE-{i:04d}" + "x" * 200}] for i in range(30)}}
    p = FakeProvider([])
    _run(monkeypatch, p, [big], [DOC], batch_chars=1500)
    assert len(p.prompts) > 1
    joined = "\n".join(p.prompts)
    for i in range(30):
        assert f"VALUE-{i:04d}" in joined          # nothing silently cut off
    assert "SKU LP-4471" in joined


def test_exact_keys_merge_across_sources_and_documents_without_llm(monkeypatch):
    p = FakeProvider([])
    entities, _ = _run(monkeypatch, p, [DRUID, PG], [DOC])
    product = {e["canonical_id"]: e for e in entities}["product:LP-4471"]   # Postgres id form wins
    assert product["canonical_label"] == "Laptop Pro 14"
    assert {(s["source_type"], s["key_value"]) for s in product["sources"]} == {
        ("postgres", "LP-4471"), ("druid", "LP4471"), ("document", "LP-4471")}
    assert product["confidence"] == 0.90 and product["status"] == "auto_commit"   # 2 structured systems
    # tables the exact-key pass understood are not re-sent to the LLM; documents still are
    assert all('"table": "products"' not in prompt for prompt in p.prompts)
    assert any("SKU LP-4471" in prompt for prompt in p.prompts)


def test_single_source_entities_go_to_review(monkeypatch):
    entities, _ = _run(monkeypatch, FakeProvider([]), [PG], [])
    product = entities[0]
    assert product["confidence"] == 0.60 and product["status"] == "needs_review"


def test_llm_entities_must_be_backed_by_the_material(monkeypatch):
    p = FakeProvider([{
        "entities": [
            # real: the incident id is in the report
            {"canonical_id": "maintenanceincident:MNT-2024-001", "canonical_label": "MNT-2024-001",
             "class": "MaintenanceIncident", "confidence": 0.99,
             "sources": [{"source_type": "document", "table_or_datasource": "report_001.txt",
                          "key_column": "mention", "key_value": "MNT-2024-001"}]},
            # invented: WH-WEST appears nowhere in the material
            {"canonical_id": "warehouse:WH-WEST", "class": "Warehouse", "confidence": 0.99,
             "sources": [{"source_type": "postgres", "table_or_datasource": "warehouses", "key_value": "WH-WEST"}]},
            # real id from the report, attached to a table that was never ingested
            {"canonical_id": "maintenanceincident:MNT-2024-001", "class": "MaintenanceIncident", "confidence": 0.99,
             "sources": [{"source_type": "postgres", "table_or_datasource": "maintenanceincidents",
                          "key_column": "incident_id", "key_value": "MNT-2024-001"}]},
            # invented class
            {"canonical_id": "fault:PMIC", "class": "Fault", "confidence": 0.99,
             "sources": [{"source_type": "document", "key_value": "LP-4471"}]},
        ],
        "relationships": [
            {"from_id": "maintenanceincident:MNT-2024-001", "type": "AFFECTS", "to_id": "product:LP4471"},
            # both ends are database records: only rows may link them, never document text
            {"from_id": "order:ORD-20240115", "type": "CONTAINS", "to_id": "product:LP-4471"},
        ],
    }])
    orders = {"source": "postgres", "schema": {"orders": [{"column": "order_id"}]},
              "samples": {"orders": [{"order_id": "ORD-20240115"}]}}
    entities, proposed = _run(monkeypatch, p, [PG, orders], [DOC])
    by_id = {e["canonical_id"]: e for e in entities}
    assert set(by_id) == {"product:LP-4471", "order:ORD-20240115", "maintenanceincident:MNT-2024-001"}
    assert len(proposed) == 1
    incident = by_id["maintenanceincident:MNT-2024-001"]
    assert incident["status"] == "needs_review"          # document-only → never auto-committed
    assert {s["source_type"] for s in incident["sources"]} == {"document"}   # invented postgres table dropped
    assert proposed[0]["to_id"] == "product:LP-4471"      # endpoint matched by normalised id


def test_status_enforced_from_confidence(monkeypatch):
    p = FakeProvider([{"entities": [
        {"canonical_id": "maintenanceincident:MNT-2024-001", "class": "MaintenanceIncident",
         "confidence": "high", "sources": [{"source_type": "document", "key_value": "MNT-2024-001"}]},
    ]}])
    entities, _ = _run(monkeypatch, p, [], [DOC])
    assert entities[0]["status"] == "unresolved" and entities[0]["confidence"] == 0.0


REPORTS = sorted((Path(__file__).parents[2] / "data_sources" / "documents" / "maintenance_reports").glob("*.txt"))


def test_reports_declare_incidents_and_link_without_llm(monkeypatch):
    docs = [{"name": p.name, "text": p.read_text()} for p in REPORTS]
    inventory = {"source": "postgres", "schema": {"inventory": [{"column": "product_id"}]},
                 "samples": {"inventory": [{"product_id": "LP-4471", "warehouse_id": "WH-EAST"},
                                           {"product_id": "MN-5543", "warehouse_id": "WH-SOUTH"}]}}
    entities, proposed = _run(monkeypatch, FakeProvider([]), [inventory], docs)
    by_id = {e["canonical_id"]: e for e in entities}

    # both incident reports declare an incident; the supplier quality review is not one
    assert {"maintenanceincident:MNT-2024-001", "maintenanceincident:MNT-2024-002"} <= set(by_id)
    assert not any(cid.endswith("SQR-2024-001") for cid in by_id)
    assert by_id["maintenanceincident:MNT-2024-001"]["status"] == "needs_review"
    # the quality review mentions the incident, so it is linked as a document source
    assert any(s["table_or_datasource"] == "report_003.txt"
               for s in by_id["maintenanceincident:MNT-2024-001"]["sources"])

    edges = {(r["from_id"], r["type"], r["to_id"]) for r in proposed}
    assert ("maintenanceincident:MNT-2024-002", "AFFECTS", "product:MN-5543") in edges
    assert ("maintenanceincident:MNT-2024-002", "LOCATED_AT", "warehouse:WH-SOUTH") in edges
    assert ("maintenanceincident:MNT-2024-001", "AFFECTS", "product:LP-4471") in edges
