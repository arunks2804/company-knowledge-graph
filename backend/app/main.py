"""FastAPI application — ingestion pipeline + retrieval API."""
from __future__ import annotations

import os
from pathlib import Path

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
from .connectors.postgres_live import extract_all as pg_extract
from .connectors.druid_live import extract_all as druid_extract
from .connectors.dynamo_sample import extract_all as dynamo_extract
from .connectors.iceberg_catalog import extract_all as iceberg_extract
from .connectors.timescale_live import extract_all as timescale_extract
from .connectors.schema_files import extract_all as schema_files_extract
from .documents.chunker import chunk_text
from .documents.doc_extractor import extract_documents, READERS
from .documents.embedder import embed_and_store
from .ontology.generator import generate_ontology, load_seed_ontology
from .ontology.resolver import resolve_entities
from .ontology.taxonomy import describe as describe_ontology
from .graph.neo4j_sync import get_driver, ensure_indexes, sync_entities, link_entity_to_chunks
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
def ontology(_: Principal = Depends(require_read_only)):
    return load_seed_ontology()


@app.get("/ontology/describe")
def ontology_describe(_: Principal = Depends(require_read_only)):
    return {"description": describe_ontology()}


@app.get("/ontology/graph")
def ontology_graph(_: Principal = Depends(require_read_only)):
    data = load_seed_ontology()
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
    ]
    edges = [
        {
            "data": {
                "id": f"{r['name']}_{i}",
                "source": r.get("from", ""),
                "target": r.get("to", ""),
                "label": r["name"],
                "description": r.get("description", ""),
            }
        }
        for i, r in enumerate(data.get("relationships", []))
        if r.get("from") and r.get("to")
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/ingest/status")
def ingest_status(_: Principal = Depends(require_read_only)):
    return _ingest_status


@app.get("/graph/summary")
def graph_summary(_: Principal = Depends(require_read_only)):
    driver = get_driver()
    try:
        return {"summary": describe_graph_summary(driver)}
    finally:
        driver.close()


@app.get("/entities")
def list_entities(status: str | None = None, limit: int = 50, _: Principal = Depends(require_read_only)):
    driver = get_driver()
    try:
        with driver.session() as session:
            if status:
                result = session.run(
                    "MATCH (e:Entity {status: $s}) RETURN e LIMIT $l",
                    s=status, l=limit,
                )
            else:
                result = session.run("MATCH (e:Entity) RETURN e LIMIT $l", l=limit)
            return [dict(r["e"]) for r in result]
    finally:
        driver.close()


# ── ingest (read-write) ────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    sources: list[str] = []
    schema_file_paths: list[str] = []
    doc_file_paths: list[str] = []


_ingest_status: dict = {"state": "idle", "detail": ""}


def _validate_path(user_path: str, base: Path) -> Path:
    """Reject any path that escapes the allowed base directory."""
    p = Path(user_path).resolve()
    if not str(p).startswith(str(base.resolve())):
        raise HTTPException(status_code=400, detail=f"Invalid file path: {user_path}")
    return p


def _run_ingest(sources: list[str], schema_file_paths: list[str], doc_file_paths: list[str]) -> None:
    global _ingest_status
    try:
        _ingest_status = {"state": "running", "detail": "connecting to graph"}
        driver = get_driver()
        ensure_indexes(driver)

        schema_data = []

        if "postgres" in sources:
            _ingest_status["detail"] = "extracting postgres"
            try:
                schema_data.append(pg_extract())
            except Exception as e:
                schema_data.append({"source": "postgres", "error": str(e)})

        if "druid" in sources:
            _ingest_status["detail"] = "extracting druid"
            try:
                schema_data.append(druid_extract())
            except Exception as e:
                schema_data.append({"source": "druid", "error": str(e)})

        if "dynamodb" in sources:
            _ingest_status["detail"] = "extracting dynamodb"
            try:
                schema_data.append(dynamo_extract())
            except Exception as e:
                schema_data.append({"source": "dynamodb", "error": str(e)})

        if "iceberg" in sources:
            _ingest_status["detail"] = "extracting iceberg"
            try:
                schema_data.append(iceberg_extract())
            except Exception as e:
                schema_data.append({"source": "iceberg", "error": str(e)})

        if "timescaledb" in sources:
            _ingest_status["detail"] = "extracting timescaledb"
            try:
                schema_data.append(timescale_extract())
            except Exception as e:
                schema_data.append({"source": "timescaledb", "error": str(e)})

        if schema_file_paths:
            _ingest_status["detail"] = f"reading {len(schema_file_paths)} schema file(s)"
            for fp in schema_file_paths:
                try:
                    results = schema_files_extract(schemas_dir=Path(fp).parent)
                    schema_data.extend([r for r in results if Path(fp).name in r.get("source", "")])
                except Exception as e:
                    schema_data.append({"source": f"schema_file:{fp}", "error": str(e)})

        _ingest_status["detail"] = "generating ontology"
        ontology = generate_ontology(schema_data)

        _ingest_status["detail"] = "resolving entities"
        entities = resolve_entities(schema_data, ontology)
        counts = sync_entities(driver, entities)

        raw_docs = []
        if doc_file_paths:
            _ingest_status["detail"] = f"processing {len(doc_file_paths)} document(s)"
            for fp in doc_file_paths:
                p = Path(fp)
                reader = READERS.get(p.suffix.lower())
                if reader:
                    text = reader(p)
                    if text.strip():
                        doc = {"path": str(p), "name": p.name, "text": text}
                        raw_docs.append(doc)
                        chunks = chunk_text(text)
                        embed_and_store(driver, doc, chunks)
                        for ent in entities:
                            link_entity_to_chunks(driver, ent["canonical_id"], str(p))

        driver.close()
        _ingest_status = {
            "state": "done",
            "detail": "complete",
            "entity_counts": counts,
            "entities": len(entities),
            "documents": len(raw_docs),
        }
    except Exception as exc:
        _ingest_status = {"state": "error", "detail": str(exc)}


@app.post("/ingest")
def ingest(req: IngestRequest, background_tasks: BackgroundTasks, _: Principal = Depends(require_read_write)):
    if _ingest_status.get("state") == "running":
        raise HTTPException(status_code=409, detail="Ingest already running")

    # validate file paths stay within allowed directories
    for fp in req.schema_file_paths:
        _validate_path(fp, _SCHEMAS_BASE)
    for fp in req.doc_file_paths:
        _validate_path(fp, _DOCS_BASE)

    background_tasks.add_task(_run_ingest, req.sources, req.schema_file_paths, req.doc_file_paths)
    return {"status": "started"}


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
def entity_update(canonical_id: str, req: UpdateEntityRequest, _: Principal = Depends(require_read_write)):
    driver = get_driver()
    try:
        return update_entity(driver, canonical_id, req.canonical_label, req.class_name, req.status)
    finally:
        driver.close()


@app.delete("/entities/{canonical_id}")
def entity_remove(canonical_id: str, _: Principal = Depends(require_read_write)):
    driver = get_driver()
    try:
        return remove_entity(driver, canonical_id)
    finally:
        driver.close()


@app.post("/entities/{canonical_id}/approve")
def entity_approve(canonical_id: str, _: Principal = Depends(require_read_write)):
    driver = get_driver()
    try:
        return approve_entity(driver, canonical_id)
    finally:
        driver.close()


@app.post("/entities/{canonical_id}/reject")
def entity_reject(canonical_id: str, _: Principal = Depends(require_read_write)):
    driver = get_driver()
    try:
        return reject_entity(driver, canonical_id)
    finally:
        driver.close()


@app.post("/entities/{canonical_id}/split")
def entity_split(canonical_id: str, req: SplitEntityRequest, _: Principal = Depends(require_read_write)):
    driver = get_driver()
    try:
        return split_entity(driver, canonical_id, req.entity_a, req.entity_b)
    finally:
        driver.close()


@app.patch("/graph/relationship")
def graph_rel_update(req: RelationshipRequest, _: Principal = Depends(require_read_write)):
    driver = get_driver()
    try:
        return update_graph_rel(driver, req.source_id, req.target_id, req.rel_type, req.new_type or req.rel_type)
    finally:
        driver.close()


@app.delete("/graph/relationship")
def graph_rel_remove(req: RelationshipRequest, _: Principal = Depends(require_read_write)):
    driver = get_driver()
    try:
        return remove_graph_rel(driver, req.source_id, req.target_id, req.rel_type)
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
def ontology_class_update(name: str, req: UpdateClassRequest, _: Principal = Depends(require_read_write)):
    return update_class(name, req.new_name, req.description, req.source_hints)


@app.delete("/ontology/classes/{name}")
def ontology_class_remove(name: str, _: Principal = Depends(require_read_write)):
    return remove_class(name)


@app.post("/ontology/classes")
def ontology_class_add(req: AddClassRequest, _: Principal = Depends(require_read_write)):
    return add_class(req.name, req.description, req.source_hints)


@app.patch("/ontology/relationships")
def ontology_rel_update(req: OntologyRelRequest, _: Principal = Depends(require_read_write)):
    return update_onto_rel(req.from_class, req.to_class, req.name, req.new_name or req.name)


@app.delete("/ontology/relationships")
def ontology_rel_remove(req: OntologyRelRequest, _: Principal = Depends(require_read_write)):
    return remove_onto_rel(req.from_class, req.to_class, req.name)


@app.post("/ontology/relationships")
def ontology_rel_add(req: OntologyRelRequest, _: Principal = Depends(require_read_write)):
    return add_onto_rel(req.from_class, req.to_class, req.name, req.description)
