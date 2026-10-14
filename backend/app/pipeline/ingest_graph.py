"""Ingestion pipeline as a LangGraph StateGraph.

extract → read_documents → generate_ontology → resolve_entities → build_relationships
    → [review_gate] → sync_graph → embed_and_link_documents

review_gate only runs when `ingest.review_gate` is enabled in llm_config.yaml and at least one
entity resolved as needs_review: the run pauses (interrupt + checkpoint) until a reviewer resumes
it with approve/reject decisions. Otherwise every resolved entity is written as before, with
needs_review entities committed but flagged.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..connectors.postgres_live import extract_all as pg_extract
from ..connectors.druid_live import extract_all as druid_extract
from ..connectors.dynamo_sample import extract_all as dynamo_extract
from ..connectors.iceberg_catalog import extract_all as iceberg_extract
from ..connectors.timescale_live import extract_all as timescale_extract
from ..connectors.schema_files import extract_all as schema_files_extract
from ..documents.chunker import chunk_text
from ..documents.doc_extractor import READERS
from ..documents.embedder import embed_and_store
from ..graph.neo4j_sync import get_driver, ensure_indexes, sync_entities, link_entities_to_chunks
from ..graph.relationships import build_relationships
from ..llm.provider import load_config
from ..ontology.generator import generate_ontology
from ..ontology.resolver import resolve_entities

EXTRACTORS = {
    "postgres": pg_extract,
    "druid": druid_extract,
    "dynamodb": dynamo_extract,
    "iceberg": iceberg_extract,
    "timescaledb": timescale_extract,
}


class IngestState(TypedDict, total=False):
    org_id: str
    sources: list[str]
    schema_file_paths: list[str]
    doc_file_paths: list[str]
    review_gate: bool
    schema_data: list[dict]
    raw_docs: list[dict]
    ontology: dict
    entities: list[dict]
    proposed_relationships: list[dict]
    relationships: list[dict]
    counts: dict


# per-org ingest status: {org_id: {"state": ..., "detail": ...}}
ingest_status: dict[str, dict] = {}
# org_id → thread_id of a run paused at review_gate
_pending_reviews: dict[str, str] = {}


def _detail(state: IngestState, detail: str) -> None:
    ingest_status.setdefault(state["org_id"], {}).update(state="running", detail=detail)


@contextmanager
def _neo4j():
    driver = get_driver()
    try:
        yield driver
    finally:
        driver.close()


def review_gate_enabled() -> bool:
    return bool((load_config().get("ingest") or {}).get("review_gate", False))


def read_documents(doc_file_paths: list[str]) -> list[dict]:
    docs = []
    for fp in doc_file_paths:
        p = Path(fp)
        reader = READERS.get(p.suffix.lower())
        if reader:
            text = reader(p)
            if text.strip():
                docs.append({"path": str(p), "name": p.name, "text": text})
    return docs


# ── nodes ──────────────────────────────────────────────────────────────────────

def extract_node(state: IngestState) -> dict:
    _detail(state, "connecting to graph")
    with _neo4j() as driver:
        ensure_indexes(driver)

    schema_data = []
    for name in state.get("sources", []):
        _detail(state, f"extracting {name}")
        try:
            schema_data.append(EXTRACTORS[name]())
        except Exception as e:
            schema_data.append({"source": name, "error": str(e)})

    schema_file_paths = state.get("schema_file_paths", [])
    if schema_file_paths:
        _detail(state, f"reading {len(schema_file_paths)} schema file(s)")
        for fp in schema_file_paths:
            try:
                results = schema_files_extract(schemas_dir=Path(fp).parent)
                schema_data.extend([r for r in results if r.get("file") == str(Path(fp).resolve())])
            except Exception as e:
                schema_data.append({"source": f"schema_file:{fp}", "error": str(e)})
    return {"schema_data": schema_data}


def read_documents_node(state: IngestState) -> dict:
    # documents are read up front so their mentions take part in entity resolution
    paths = state.get("doc_file_paths", [])
    _detail(state, f"reading {len(paths)} document(s)")
    return {"raw_docs": read_documents(paths)}


def generate_ontology_node(state: IngestState) -> dict:
    _detail(state, "generating ontology")
    return {"ontology": generate_ontology(state["schema_data"], state["org_id"])}


def resolve_entities_node(state: IngestState) -> dict:
    _detail(state, "resolving entities across sources and documents")
    entities, proposed = resolve_entities(state["schema_data"], state["ontology"], state["raw_docs"])
    return {"entities": entities, "proposed_relationships": proposed}


def build_relationships_node(state: IngestState) -> dict:
    _detail(state, "building relationships")
    return {"relationships": build_relationships(
        state["entities"], state["schema_data"], state["ontology"], state["proposed_relationships"],
    )}


def _needs_review(state: IngestState) -> list[dict]:
    return [e for e in state.get("entities", []) if e.get("status") == "needs_review"]


def route_review(state: IngestState) -> str:
    return "review_gate" if state.get("review_gate") and _needs_review(state) else "sync_graph"


def review_gate_node(state: IngestState) -> dict:
    """Pause for human review. Resume value: {canonical_id: "approve" | "reject"}.

    Approved entities are committed as auto_commit; rejected ones are dropped along with
    their edges; undecided ones are committed still flagged needs_review.
    """
    pending = _needs_review(state)
    ingest_status[state["org_id"]] = {
        "state": "awaiting_review",
        "detail": f"{len(pending)} entities need review",
        "pending": len(pending),
    }
    decisions = interrupt({"entities": pending}) or {}
    _detail(state, "applying review decisions")

    rejected = {cid for cid, d in decisions.items() if d == "reject"}
    entities = []
    for e in state["entities"]:
        if e.get("canonical_id") in rejected:
            continue
        if e.get("status") == "needs_review" and decisions.get(e.get("canonical_id")) == "approve":
            e = {**e, "status": "auto_commit"}
        entities.append(e)
    relationships = [r for r in state["relationships"]
                     if r.get("from_id") not in rejected and r.get("to_id") not in rejected]
    return {"entities": entities, "relationships": relationships}


def sync_graph_node(state: IngestState) -> dict:
    _detail(state, "writing entities and relationships")
    with _neo4j() as driver:
        counts = sync_entities(driver, state["org_id"], state["entities"], state["relationships"])
    return {"counts": counts}


def embed_and_link_documents_node(state: IngestState) -> dict:
    raw_docs = state.get("raw_docs", [])
    _detail(state, f"embedding {len(raw_docs)} document(s)")
    with _neo4j() as driver:
        for i, doc in enumerate(raw_docs, 1):
            _detail(state, f"embedding document {i}/{len(raw_docs)}")
            embed_and_store(driver, state["org_id"], doc, chunk_text(doc["text"]))
            link_entities_to_chunks(driver, state["org_id"], doc["path"])
    return {}


def build_ingest_graph(checkpointer=None):
    g = StateGraph(IngestState)
    g.add_node("extract", extract_node)
    g.add_node("read_documents", read_documents_node)
    g.add_node("generate_ontology", generate_ontology_node)
    g.add_node("resolve_entities", resolve_entities_node)
    g.add_node("build_relationships", build_relationships_node)
    g.add_node("review_gate", review_gate_node)
    g.add_node("sync_graph", sync_graph_node)
    g.add_node("embed_and_link_documents", embed_and_link_documents_node)

    g.add_edge(START, "extract")
    g.add_edge("extract", "read_documents")
    g.add_edge("read_documents", "generate_ontology")
    g.add_edge("generate_ontology", "resolve_entities")
    g.add_edge("resolve_entities", "build_relationships")
    g.add_conditional_edges("build_relationships", route_review, ["review_gate", "sync_graph"])
    g.add_edge("review_gate", "sync_graph")
    g.add_edge("sync_graph", "embed_and_link_documents")
    g.add_edge("embed_and_link_documents", END)
    return g.compile(checkpointer=checkpointer)


_checkpointer = InMemorySaver()
_graph = build_ingest_graph(_checkpointer)


# ── running ────────────────────────────────────────────────────────────────────

def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _drive(org_id: str, thread_id: str, graph_input) -> None:
    """Invoke or resume the graph; record the final status, or leave the run parked for review."""
    paused = False
    try:
        _graph.invoke(graph_input, _config(thread_id))
        snapshot = _graph.get_state(_config(thread_id))
        if snapshot.next:  # stopped at review_gate's interrupt
            paused = True
            _pending_reviews[org_id] = thread_id
            return
        values = snapshot.values
        ingest_status[org_id] = {
            "state": "done",
            "detail": "complete",
            "entity_counts": values.get("counts", {}),
            "entities": len(values.get("entities", [])),
            "relationships": len(values.get("relationships", [])),
            "documents": len(values.get("raw_docs", [])),
        }
    except Exception as exc:
        ingest_status[org_id] = {"state": "error", "detail": str(exc)}
    finally:
        if not paused:
            if _pending_reviews.get(org_id) == thread_id:
                del _pending_reviews[org_id]
            _checkpointer.delete_thread(thread_id)


def run_ingest(org_id: str, sources: list[str], schema_file_paths: list[str], doc_file_paths: list[str],
               review_gate: bool | None = None) -> None:
    # a new run supersedes any run still waiting for review
    stale = _pending_reviews.pop(org_id, None)
    if stale:
        _checkpointer.delete_thread(stale)
    ingest_status[org_id] = {"state": "running", "detail": "starting"}
    _drive(org_id, f"{org_id}:{uuid.uuid4().hex}", {
        "org_id": org_id,
        "sources": sources,
        "schema_file_paths": schema_file_paths,
        "doc_file_paths": doc_file_paths,
        "review_gate": review_gate_enabled() if review_gate is None else review_gate,
    })


def pending_review(org_id: str) -> list[dict] | None:
    """Entities awaiting review for the org's paused run, or None if nothing is paused."""
    thread_id = _pending_reviews.get(org_id)
    if not thread_id:
        return None
    for task in _graph.get_state(_config(thread_id)).tasks:
        for intr in task.interrupts:
            return intr.value.get("entities", [])
    return None


def resume_ingest(org_id: str, decisions: dict[str, str]) -> None:
    thread_id = _pending_reviews.get(org_id)
    if not thread_id:
        raise LookupError(f"No ingest awaiting review for {org_id}")
    ingest_status[org_id] = {"state": "running", "detail": "resuming after review"}
    _drive(org_id, thread_id, Command(resume=decisions))
