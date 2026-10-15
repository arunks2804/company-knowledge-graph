"""FastAPI application — ingestion pipeline + retrieval API."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .auth import router as auth_router, require_read_only, require_read_write
from .auth.models import Principal
from .auth.store import create_user, has_users
from .ontology.generator import load_seed_ontology
from .ontology.taxonomy import describe as describe_ontology, rel_name
from .graph.neo4j_sync import get_driver
from .graph.nl_describe import describe_graph_summary
from .graph.editor import (
    update_entity, remove_entity, approve_entity, reject_entity,
    split_entity, update_relationship as update_graph_rel, remove_relationship as remove_graph_rel,
)
from .ontology.editor import (
    update_class, remove_class, add_class,
    update_relationship as update_onto_rel, remove_relationship as remove_onto_rel, add_relationship as add_onto_rel,
)
from .retrieval.api import router as retrieval_router
from .orgs.api import router as orgs_router
from .orgs.config import get_org_sources
from .orgs.scope import require_org
from .pipeline.ingest_graph import (
    EXTRACTORS as _EXTRACTORS, ingest_status as _ingest_status,
    run_ingest, pending_review, resume_ingest,
)

app = FastAPI(title="Company Knowledge Graph", version="1.0.0")

# ── CORS ──────────────────────────────────────────────────────────────────────
# allow_credentials requires explicit origins — not "*"
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(retrieval_router)
app.include_router(orgs_router)

_FRONTEND = Path(__file__).parent.parent.parent / "frontend" / "dist"
_SCHEMAS_BASE = Path(__file__).parent.parent.parent / "schemas"
_DOCS_BASE = Path(__file__).parent.parent.parent / "data_sources" / "documents"

if _FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND / "assets")), name="assets")


# ── bootstrap admin user ───────────────────────────────────────────────────────

@app.on_event("startup")
def _bootstrap():
    """Create the initial admin user from env vars if no users exist yet."""
    if not has_users():
        username = os.environ.get("ADMIN_USERNAME")
        password = os.environ.get("ADMIN_PASSWORD")
        if username and password:
            create_user(username, password, "read_write")


# ── public endpoints ───────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    index = _FRONTEND / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "message": "Company Knowledge Graph API"}


@app.get("/health")
def health():
    driver = get_driver()
    try:
        driver.verify_connectivity()
        neo4j_ok = True
    except Exception:
        neo4j_ok = False
    finally:
        driver.close()
    return {
        "neo4j": neo4j_ok,
        "langsmith": bool(os.environ.get("LANGCHAIN_API_KEY")),
    }


# ── read-only endpoints ────────────────────────────────────────────────────────

@app.get("/sources")
def list_sources(_: Principal = Depends(require_read_only)):
    schema_files = []
    if _SCHEMAS_BASE.exists():
        for fp in sorted(_SCHEMAS_BASE.rglob("*")):
            if fp.is_file() and fp.suffix.lower() in (".sql", ".json", ".yaml", ".yml") and not fp.name.startswith("."):
                schema_files.append({"name": fp.name, "path": str(fp), "type": "schema_file"})

    doc_files = []
    if _DOCS_BASE.exists():
        for fp in sorted(_DOCS_BASE.rglob("*")):
            if fp.is_file() and fp.suffix.lower() in (".txt", ".md", ".pdf") and not fp.name.startswith("."):
                doc_files.append({"name": fp.name, "path": str(fp), "type": "document"})

    return {
        "live_connectors": ["postgres", "druid", "dynamodb", "iceberg", "timescaledb"],
        "schema_files": schema_files,
        "documents": doc_files,
    }


@app.get("/ontology")
def ontology(_: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    return load_seed_ontology(org_id)


@app.get("/ontology/describe")
def ontology_describe(_: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    return {"description": describe_ontology(org_id)}


@app.get("/ontology/graph")
def ontology_graph(_: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    data = load_seed_ontology(org_id)
    nodes = [
        {
            "data": {
                "id": c["name"],
                "label": c["name"],
                "description": c.get("description", ""),
                "source_hints": c.get("source_hints", []),
            }
        }
        for c in data.get("classes", [])
        if not c.get("abstract")   # the abstract Entity base is not a real kind of thing
    ]
    edges = [
        {
            "data": {
                "id": f"{rel_name(r)}_{i}",
                "source": r.get("from", ""),
                "target": r.get("to", ""),
                "label": rel_name(r),
                "description": r.get("description", ""),
            }
        }
        for i, r in enumerate(data.get("relationships", []))
        if r.get("from") and r.get("to")
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/ingest/status")
def ingest_status(_: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    return _ingest_status.get(org_id, {"state": "idle", "detail": ""})


@app.get("/graph/summary")
def graph_summary(_: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return {"summary": describe_graph_summary(driver, org_id)}
    finally:
        driver.close()


@app.get("/entities")
def list_entities(status: str | None = None, limit: int = 50,
                  _: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        with driver.session() as session:
            if status:
                result = session.run(
                    "MATCH (e:Entity {org_id: $org, status: $s}) RETURN e LIMIT $l",
                    org=org_id, s=status, l=limit,
                )
            else:
                result = session.run("MATCH (e:Entity {org_id: $org}) RETURN e LIMIT $l", org=org_id, l=limit)
            return [dict(r["e"]) for r in result]
    finally:
        driver.close()


# ── ingest (read-write) ────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    sources: list[str] = []
    schema_file_paths: list[str] = []
    doc_file_paths: list[str] = []


def _validate_path(user_path: str, allowed: set[str]) -> Path:
    """Reject any path that is not one of the files configured for this org."""
    p = Path(user_path).resolve()
    if str(p) not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid file path for this organisation: {user_path}")
    return p


def _run_ingest(org_id: str, sources: list[str], schema_file_paths: list[str], doc_file_paths: list[str]) -> None:
    """Runs the LangGraph ingestion pipeline (app/pipeline/ingest_graph.py)."""
    run_ingest(org_id, sources, schema_file_paths, doc_file_paths)


@app.post("/ingest")
def ingest(req: IngestRequest, background_tasks: BackgroundTasks,
           _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    if _ingest_status.get(org_id, {}).get("state") == "running":
        raise HTTPException(status_code=409, detail="Ingest already running")

    # only connectors enabled and files configured for this org may be ingested
    org_sources = get_org_sources(org_id)
    enabled = {c["name"] for c in org_sources.get("connectors", []) if c["enabled"]}
    for name in req.sources:
        if name not in _EXTRACTORS or name not in enabled:
            raise HTTPException(status_code=400, detail=f"Connector '{name}' is not enabled for this organisation")
    allowed_schemas = {str(Path(f["path"]).resolve()) for f in org_sources.get("schema_files", [])}
    allowed_docs = {str(Path(f["path"]).resolve()) for f in org_sources.get("documents", [])}
    schema_paths = [str(_validate_path(fp, allowed_schemas)) for fp in req.schema_file_paths]
    doc_paths = [str(_validate_path(fp, allowed_docs)) for fp in req.doc_file_paths]

    background_tasks.add_task(_run_ingest, org_id, req.sources, schema_paths, doc_paths)
    return {"status": "started"}


class ReviewDecisionsRequest(BaseModel):
    decisions: dict[str, Literal["approve", "reject"]] = {}


@app.get("/ingest/review")
def ingest_review(_: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    """Entities held at the review gate of a paused ingest (only when ingest.review_gate is on)."""
    pending = pending_review(org_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="No ingest awaiting review")
    return {"entities": pending}


@app.post("/ingest/review")
def ingest_review_submit(req: ReviewDecisionsRequest, background_tasks: BackgroundTasks,
                         _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    if _ingest_status.get(org_id, {}).get("state") != "awaiting_review" or pending_review(org_id) is None:
        raise HTTPException(status_code=409, detail="No ingest awaiting review")
    _ingest_status[org_id] = {"state": "running", "detail": "resuming after review"}
    background_tasks.add_task(resume_ingest, org_id, req.decisions)
    return {"status": "resumed"}


# ── entity editing (read-write) ────────────────────────────────────────────────

class UpdateEntityRequest(BaseModel):
    canonical_label: str | None = None
    class_name: str | None = None
    status: str | None = None


class RelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    new_type: str | None = None


class SplitEntityRequest(BaseModel):
    entity_a: dict
    entity_b: dict


@app.patch("/entities/{canonical_id}")
def entity_update(canonical_id: str, req: UpdateEntityRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return update_entity(driver, org_id, canonical_id, req.canonical_label, req.class_name, req.status)
    finally:
        driver.close()


@app.delete("/entities/{canonical_id}")
def entity_remove(canonical_id: str, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return remove_entity(driver, org_id, canonical_id)
    finally:
        driver.close()


@app.post("/entities/{canonical_id}/approve")
def entity_approve(canonical_id: str, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return approve_entity(driver, org_id, canonical_id)
    finally:
        driver.close()


@app.post("/entities/{canonical_id}/reject")
def entity_reject(canonical_id: str, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return reject_entity(driver, org_id, canonical_id)
    finally:
        driver.close()


@app.post("/entities/{canonical_id}/split")
def entity_split(canonical_id: str, req: SplitEntityRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return split_entity(driver, org_id, canonical_id, req.entity_a, req.entity_b)
    finally:
        driver.close()


@app.patch("/graph/relationship")
def graph_rel_update(req: RelationshipRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return update_graph_rel(driver, org_id, req.source_id, req.target_id, req.rel_type, req.new_type or req.rel_type)
    finally:
        driver.close()


@app.delete("/graph/relationship")
def graph_rel_remove(req: RelationshipRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return remove_graph_rel(driver, org_id, req.source_id, req.target_id, req.rel_type)
    finally:
        driver.close()


# ── ontology editing (read-write) ──────────────────────────────────────────────

class UpdateClassRequest(BaseModel):
    new_name: str | None = None
    description: str | None = None
    source_hints: list[str] | None = None


class AddClassRequest(BaseModel):
    name: str
    description: str = ""
    source_hints: list[str] = []


class OntologyRelRequest(BaseModel):
    from_class: str
    to_class: str
    name: str
    new_name: str | None = None
    description: str = ""


@app.patch("/ontology/classes/{name}")
def ontology_class_update(name: str, req: UpdateClassRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    return update_class(org_id, name, req.new_name, req.description, req.source_hints)


@app.delete("/ontology/classes/{name}")
def ontology_class_remove(name: str, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    return remove_class(org_id, name)


@app.post("/ontology/classes")
def ontology_class_add(req: AddClassRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    return add_class(org_id, req.name, req.description, req.source_hints)


@app.patch("/ontology/relationships")
def ontology_rel_update(req: OntologyRelRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    return update_onto_rel(org_id, req.from_class, req.to_class, req.name, req.new_name or req.name)


@app.delete("/ontology/relationships")
def ontology_rel_remove(req: OntologyRelRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    return remove_onto_rel(org_id, req.from_class, req.to_class, req.name)


@app.post("/ontology/relationships")
def ontology_rel_add(req: OntologyRelRequest, _: Principal = Depends(require_read_write), org_id: str = Depends(require_org)):
    return add_onto_rel(org_id, req.from_class, req.to_class, req.name, req.description)
