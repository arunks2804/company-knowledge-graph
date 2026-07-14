"""Syncs resolved entities and relationships to Neo4j."""
from __future__ import annotations

import os

from neo4j import GraphDatabase


def get_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, password))


def ensure_indexes(driver) -> None:
    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT entity_id IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE e.canonical_id IS UNIQUE"
        )
        session.run(
            "CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS "
            "FOR (c:DocumentChunk) ON (c.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}"
        )


def upsert_entity(driver, entity: dict) -> None:
    """Merge entity node and record all source references as properties."""
    with driver.session() as session:
        session.run(
            f"""
            MERGE (e:Entity:{entity['class']} {{canonical_id: $cid}})
            SET e.canonical_label = $label,
                e.confidence = $confidence,
                e.status = $status,
                e.sources = $sources
            """,
            cid=entity["canonical_id"],
            label=entity.get("canonical_label", ""),
            confidence=entity.get("confidence", 0.0),
            status=entity.get("status", "unresolved"),
            sources=str(entity.get("sources", [])),
        )


def sync_entities(driver, entities: list[dict]) -> dict:
    """Upsert all resolved entities. Returns counts by status."""
    counts: dict[str, int] = {"auto_commit": 0, "needs_review": 0, "unresolved": 0}
    for entity in entities:
        upsert_entity(driver, entity)
        counts[entity.get("status", "unresolved")] = counts.get(entity.get("status", "unresolved"), 0) + 1
    return counts


def link_entity_to_chunks(driver, canonical_id: str, doc_path: str) -> None:
    """Create MENTIONED_IN edges from a graph entity to document chunks that reference it."""
    with driver.session() as session:
        session.run(
            """
            MATCH (e:Entity {canonical_id: $cid})
            MATCH (c:DocumentChunk {doc_path: $path})
            WHERE c.text CONTAINS e.canonical_label
            MERGE (e)-[:MENTIONED_IN]->(c)
            """,
            cid=canonical_id,
            path=doc_path,
        )
