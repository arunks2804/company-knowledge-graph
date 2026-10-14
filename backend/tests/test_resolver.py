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


def test_postgres_first_and_known_ids_passed_forward(monkeypatch):
    p = FakeProvider([
        {"entities": [{"canonical_id": "product:LP-4471", "canonical_label": "Laptop Pro 14", "class": "Product",
                       "confidence": 0.7, "sources": [{"source_type": "postgres", "key_value": "LP-4471"}]}]},
        {"entities": [{"canonical_id": "product:LP4471", "canonical_label": "", "class": "Product",
                       "confidence": 0.9, "sources": [{"source_type": "druid", "key_value": "LP4471"}]}]},
        {"entities": [{"canonical_id": "maintenanceincident:MNT-2024-001", "canonical_label": "MNT-2024-001",
                       "class": "MaintenanceIncident", "confidence": 0.6, "sources": []}],
         "relationships": [{"from_id": "maintenanceincident:MNT-2024-001", "type": "AFFECTS",
                            "to_id": "product:LP4471"}]},
    ])
    # druid listed first on purpose; postgres must still be resolved first
    entities, proposed = _run(monkeypatch, p, [DRUID, PG], [DOC], batch_chars=200)
    assert '"source": "postgres"' in p.prompts[0]
    assert "product:LP-4471" in p.prompts[1]          # later batches see earlier ids

    by_id = {e["canonical_id"]: e for e in entities}
    assert set(by_id) == {"product:LP-4471", "maintenanceincident:MNT-2024-001"}
    product = by_id["product:LP-4471"]
    assert {s["source_type"] for s in product["sources"]} == {"postgres", "druid"}
    assert product["confidence"] == 0.9 and product["status"] == "auto_commit"
    assert product["canonical_label"] == "Laptop Pro 14"
    # the alias id from batch 2 is remapped onto the merged entity
    assert proposed[0]["to_id"] == "product:LP-4471"


def test_status_enforced_from_confidence(monkeypatch):
    p = FakeProvider([{"entities": [
        {"canonical_id": "customer:CUST-001", "class": "Customer", "confidence": "high", "status": "auto_commit"},
    ]}])
    entities, _ = _run(monkeypatch, p, [PG], [])
    assert entities[0]["status"] == "unresolved" and entities[0]["confidence"] == 0.0
