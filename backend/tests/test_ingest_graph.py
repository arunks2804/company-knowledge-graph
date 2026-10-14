"""Drives the LangGraph ingestion pipeline end-to-end with a fake LLM and a mocked Neo4j driver."""
import copy
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.documents.embedder as embedder
import app.ontology.generator as generator
import app.ontology.resolver as resolver
import app.ontology.taxonomy as taxonomy
import app.pipeline.ingest_graph as ig
from app import main
from app.auth import require_read_only, require_read_write
from app.auth.models import Principal, Role

ORG = "example"
HEADERS = {"X-Org-Id": ORG}

PG = {"source": "postgres", "schema": {"orders": [{"column": "order_id"}, {"column": "customer_id"}]},
      "samples": {"orders": [{"order_id": "ORD-20240101", "customer_id": "CUST-001"}]}}


def _ent(cid, cls, key, conf):
    return {"canonical_id": cid, "canonical_label": key, "class": cls, "confidence": conf,
            "sources": [{"source_type": "postgres", "key_value": key}]}


RESOLUTION = {"entities": [
    _ent("customer:CUST-001", "Customer", "CUST-001", 0.95),
    _ent("order:ORD-20240101", "Order", "ORD-20240101", 0.6),   # → needs_review
]}


class FakeProvider:
    def __init__(self):
        self.prompts = []
        self.embedded = []

    def generate_structured(self, prompt, schema):
        self.prompts.append(prompt)
        if "ontology engineer" in prompt:
            return {"classes": [], "relationships": []}
        return copy.deepcopy(RESOLUTION)

    def generate_text(self, prompt):
        return ""

    def embed(self, text):
        self.embedded.append(text)
        return [0.0] * 768


@pytest.fixture
def env(monkeypatch, tmp_path):
    provider = FakeProvider()
    for mod in (generator, resolver, embedder):
        monkeypatch.setattr(mod, "get_provider", lambda: provider)
    monkeypatch.setattr(taxonomy, "org_dir", lambda org_id: tmp_path)   # keep ontology writes out of the repo
    monkeypatch.setitem(ig.EXTRACTORS, "postgres", lambda: PG)

    driver = MagicMock()
    monkeypatch.setattr(ig, "get_driver", lambda: driver)

    doc = tmp_path / "incident.txt"
    doc.write_text("Order ORD-20240101 for customer CUST-001 arrived damaged.")

    user = Principal("u1", "tester", Role.read_write, "user")
    main.app.dependency_overrides[require_read_only] = lambda: user
    main.app.dependency_overrides[require_read_write] = lambda: user
    monkeypatch.setattr(main, "get_org_sources", lambda org_id: {
        "connectors": [{"name": "postgres", "enabled": True}],
        "schema_files": [],
        "documents": [{"path": str(doc)}],
    })
    ig.ingest_status.pop(ORG, None)
    yield TestClient(main.app), provider, driver, str(doc)
    main.app.dependency_overrides.clear()
    ig.ingest_status.pop(ORG, None)


def _cypher(driver):
    session = driver.session.return_value.__enter__.return_value
    return [(c.args[0], c.kwargs) for c in session.run.call_args_list]


def _ingest(client, doc):
    r = client.post("/ingest", headers=HEADERS,
                    json={"sources": ["postgres"], "doc_file_paths": [doc]})
    assert r.status_code == 200
    return client.get("/ingest/status", headers=HEADERS).json()


def test_post_ingest_runs_graph_and_auto_commits(env, monkeypatch):
    client, provider, driver, doc = env
    monkeypatch.setattr(ig, "review_gate_enabled", lambda: False)

    status = _ingest(client, doc)

    assert status["state"] == "done", status
    assert status["entities"] == 2 and status["documents"] == 1
    assert status["entity_counts"]["auto_commit"] == 1 and status["entity_counts"]["needs_review"] == 1
    # the document took part in resolution, then got embedded
    assert any("arrived damaged" in p for p in provider.prompts)
    assert provider.embedded and "arrived damaged" in provider.embedded[0]

    calls = _cypher(driver)
    written = {kw.get("cid"): kw.get("status") for q, kw in calls if "MERGE (e:Entity" in q}
    assert written == {"customer:CUST-001": "auto_commit", "order:ORD-20240101": "needs_review"}
    assert all(kw.get("org") == ORG for q, kw in calls if "$org" in q)
    # FK edge derived from the orders sample row
    assert any("PLACED" in q and kw["src"] == "customer:CUST-001" for q, kw in calls)
    assert any("MENTIONED_IN" in q for q, _ in calls)
    assert ig.pending_review(ORG) is None


def test_review_gate_pauses_then_applies_decisions(env, monkeypatch):
    client, provider, driver, doc = env
    monkeypatch.setattr(ig, "review_gate_enabled", lambda: True)

    status = _ingest(client, doc)

    assert status["state"] == "awaiting_review" and status["pending"] == 1
    assert not any("MERGE (e:Entity" in q for q, _ in _cypher(driver))   # nothing written yet
    pending = client.get("/ingest/review", headers=HEADERS).json()["entities"]
    assert [e["canonical_id"] for e in pending] == ["order:ORD-20240101"]

    r = client.post("/ingest/review", headers=HEADERS, json={"decisions": {"order:ORD-20240101": "reject"}})
    assert r.status_code == 200
    status = client.get("/ingest/status", headers=HEADERS).json()

    assert status["state"] == "done", status
    assert status["entities"] == 1 and status["relationships"] == 0
    calls = _cypher(driver)
    assert {kw.get("cid") for q, kw in calls if "MERGE (e:Entity" in q} == {"customer:CUST-001"}
    assert not any("PLACED" in q for q, _ in calls)
    assert client.get("/ingest/review", headers=HEADERS).status_code == 404


def test_review_gate_approve_commits_entity(env, monkeypatch):
    client, _, driver, doc = env
    monkeypatch.setattr(ig, "review_gate_enabled", lambda: True)
    _ingest(client, doc)

    client.post("/ingest/review", headers=HEADERS, json={"decisions": {"order:ORD-20240101": "approve"}})

    status = client.get("/ingest/status", headers=HEADERS).json()
    assert status["entity_counts"]["auto_commit"] == 2 and status["relationships"] == 1


def test_review_gate_skipped_when_nothing_needs_review(env, monkeypatch):
    client, _, _, doc = env
    monkeypatch.setattr(ig, "review_gate_enabled", lambda: True)
    monkeypatch.setitem(RESOLUTION["entities"][1], "confidence", 0.99)

    assert _ingest(client, doc)["state"] == "done"


def test_node_error_reported_in_status(env, monkeypatch):
    client, _, _, doc = env
    monkeypatch.setattr(ig, "sync_entities", MagicMock(side_effect=RuntimeError("neo4j down")))

    status = _ingest(client, doc)
    assert status == {"state": "error", "detail": "neo4j down"}
