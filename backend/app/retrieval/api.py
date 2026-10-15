"""FastAPI router for retrieval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import Literal

from pydantic import BaseModel

from ..auth import require_read_only
from ..auth.models import Principal
from ..orgs.scope import require_org

from ..graph.neo4j_sync import get_driver
from ..graph.nl_describe import describe_entity, describe_graph_summary
from .investigate import investigate
from .search import entity_search, vector_search
from .cypher_access import run_cypher

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


@router.get("/neighbourhood/{canonical_id}")
def neighbourhood(canonical_id: str, hops: int = 1,
                  _: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    """
    Return nodes and edges for the neighbourhood of an entity.
    hops=1 means direct connections only.
    Returns Cytoscape-compatible {nodes, edges}.
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (e:Entity {org_id: $org, canonical_id: $cid})
                OPTIONAL MATCH (e)-[r]-(other:Entity {org_id: $org})
                RETURN e,
                       collect(DISTINCT {
                           rel: type(r),
                           other_id: other.canonical_id,
                           other_label: other.canonical_label,
                           other_classes: labels(other),
                           other_status: other.status,
                           other_confidence: other.confidence,
                           direction: CASE WHEN startNode(r) = e THEN 'out' ELSE 'in' END
                       }) AS connections
                """,
                cid=canonical_id,
                org=org_id,
            )
            record = result.single()
            if record is None:
                return {"nodes": [], "edges": []}

            centre = dict(record["e"])
            connections = record["connections"] or []

            nodes = [{
                "data": {
                    "id": centre.get("canonical_id"),
                    "label": centre.get("canonical_label", centre.get("canonical_id")),
                    "classes": ["centre"],
                    "status": centre.get("status"),
                    "confidence": centre.get("confidence"),
                }
            }]
            edges = []
            seen_nodes = {centre.get("canonical_id")}

            for conn in connections:
                other_id = conn.get("other_id")
                if not other_id or other_id in seen_nodes:
                    continue
                seen_nodes.add(other_id)
                other_classes = conn.get("other_classes") or []
                nodes.append({
                    "data": {
                        "id": other_id,
                        "label": conn.get("other_label", other_id),
                        "classes": [c for c in other_classes if c != "Entity"],
                        "status": conn.get("other_status"),
                        "confidence": conn.get("other_confidence"),
                    }
                })
                if conn.get("direction") == "out":
                    edges.append({"data": {"source": canonical_id, "target": other_id, "label": conn.get("rel", "")}})
                else:
                    edges.append({"data": {"source": other_id, "target": canonical_id, "label": conn.get("rel", "")}})

        return {"nodes": nodes, "edges": edges, "centre": canonical_id}
    finally:
        driver.close()


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    history: list[Turn] = []


@router.post("/investigate")
def investigate_endpoint(req: QueryRequest, _: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return investigate(driver, org_id, req.question, [t.model_dump() for t in req.history])
    finally:
        driver.close()


@router.post("/search/chunks")
def chunk_search(req: QueryRequest, _: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return vector_search(driver, org_id, req.question, top_k=req.top_k)
    finally:
        driver.close()


@router.post("/search/entities")
def entity_search_endpoint(req: QueryRequest, _: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return entity_search(driver, org_id, req.question, top_k=req.top_k)
    finally:
        driver.close()


@router.post("/cypher")
def cypher_endpoint(req: QueryRequest, _: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return run_cypher(driver, org_id, req.question)
    finally:
        driver.close()


class EntityRequest(BaseModel):
    canonical_id: str


@router.post("/describe/entity")
def describe_entity_endpoint(req: EntityRequest, _: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return {"description": describe_entity(driver, org_id, req.canonical_id)}
    finally:
        driver.close()


@router.get("/describe/graph")
def describe_graph_endpoint(_: Principal = Depends(require_read_only), org_id: str = Depends(require_org)):
    driver = get_driver()
    try:
        return {"summary": describe_graph_summary(driver, org_id)}
    finally:
        driver.close()
