import pytest
from fastapi.testclient import TestClient

from app import main
from app.auth import require_read_only, require_read_write
from app.auth.models import Principal, Role


@pytest.fixture
def client(monkeypatch):
    user = Principal("u1", "tester", Role.read_write, "user")
    main.app.dependency_overrides[require_read_only] = lambda: user
    main.app.dependency_overrides[require_read_write] = lambda: user
    started = []
    monkeypatch.setattr(main, "_run_ingest", lambda *a: started.append(a))
    yield TestClient(main.app), started
    main.app.dependency_overrides.clear()


def test_org_header_required(client):
    c, _ = client
    assert c.get("/ontology").status_code == 422
    assert c.get("/ontology", headers={"X-Org-Id": "nope"}).status_code == 404
    assert c.get("/ontology", headers={"X-Org-Id": "../orgs"}).status_code == 404
    assert c.get("/ontology", headers={"X-Org-Id": "example"}).status_code == 200


def test_ontology_graph_uses_relationship_names(client):
    c, _ = client
    edges = c.get("/ontology/graph", headers={"X-Org-Id": "example"}).json()["edges"]
    assert {"PLACED", "SUPPLIED_BY", "AFFECTS"} <= {e["data"]["label"] for e in edges}


def test_ingest_only_allows_org_enabled_connectors_and_files(client):
    c, started = client
    h = {"X-Org-Id": "example"}
    # druid is disabled in orgs/example/config.yaml
    assert c.post("/ingest", json={"sources": ["druid"]}, headers=h).status_code == 400
    assert c.post("/ingest", json={"doc_file_paths": ["/etc/passwd"]}, headers=h).status_code == 400
    sources = c.get("/orgs/example/sources").json()
    doc = sources["documents"][0]["path"]
    r = c.post("/ingest", json={"sources": ["postgres"], "doc_file_paths": [doc]}, headers=h)
    assert r.status_code == 200
    assert started and started[0][0] == "example"
