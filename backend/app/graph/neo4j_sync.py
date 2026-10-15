"""Syncs resolved entities and relationships to Neo4j.

Every Entity, Document and DocumentChunk carries an org_id; entities are unique on
(org_id, canonical_id) so two organisations can hold product:LP-4471 independently.
"""
from __future__ import annotations

import json
import os

from neo4j import GraphDatabase

from .relationships import safe_ident


def get_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, password))


def ensure_indexes(driver) -> None:
    with driver.session() as session:
        # the pre-org constraint made canonical_id globally unique, which blocks multi-org graphs
        session.run("DROP CONSTRAINT entity_id IF EXISTS")
        session.run(
            "CREATE CONSTRAINT entity_org_id IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE (e.org_id, e.canonical_id) IS UNIQUE"
        )
        session.run("CREATE INDEX document_org_path IF NOT EXISTS FOR (d:Document) ON (d.org_id, d.path)")
        session.run("CREATE INDEX chunk_org_path IF NOT EXISTS FOR (c:DocumentChunk) ON (c.org_id, c.doc_path)")
        session.run(
            "CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS "
            "FOR (c:DocumentChunk) ON (c.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}"
        )


def _match_terms(entity: dict) -> list[str]:
    """Strings that identify this entity in free text: its label and every source key value."""
    terms = {entity.get("canonical_label") or "", entity["canonical_id"].split(":", 1)[-1]}
    for s in entity.get("sources", []):
        if isinstance(s, dict) and s.get("key_value") is not None:
            terms.add(str(s["key_value"]))
    return sorted(t for t in terms if len(t) >= 3)


def upsert_entity(driver, org_id: str, entity: dict) -> None:
    """Merge entity node and record all source references as properties."""
    label = safe_ident(entity.get("class", ""), "Unclassified")
    with driver.session() as session:
        session.run(
            f"""
            MERGE (e:Entity {{org_id: $org, canonical_id: $cid}})
            SET e:{label},
                e.class = $cls,
                e.canonical_label = $label,
                e.confidence = $confidence,
                e.status = $status,
                e.sources = $sources,
                e.match_terms = $terms
            """,
            org=org_id,
            cid=entity["canonical_id"],
            cls=label,
            label=entity.get("canonical_label", ""),
            confidence=entity.get("confidence", 0.0),
            status=entity.get("status", "unresolved"),
            sources=json.dumps(entity.get("sources", []), default=str),
            terms=_match_terms(entity),
        )


def upsert_relationship(driver, org_id: str, rel: dict) -> None:
    rel_type = safe_ident(rel["type"], "RELATED_TO")
    with driver.session() as session:
        session.run(
            f"""
            MATCH (a:Entity {{org_id: $org, canonical_id: $src}})
            MATCH (b:Entity {{org_id: $org, canonical_id: $tgt}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.confidence = $confidence, r.evidence = $evidence
            """,
            org=org_id,
            src=rel["from_id"],
            tgt=rel["to_id"],
            confidence=rel.get("confidence", 0.0),
            evidence=rel.get("evidence", ""),
        )


def sync_entities(driver, org_id: str, entities: list[dict], relationships: list[dict] | None = None) -> dict:
    """Upsert all resolved entities, then the edges between them. Returns counts by status."""
    counts: dict[str, int] = {"auto_commit": 0, "needs_review": 0, "unresolved": 0}
    for entity in entities:
        if not entity.get("canonical_id"):
            continue
        upsert_entity(driver, org_id, entity)
        counts[entity.get("status", "unresolved")] = counts.get(entity.get("status", "unresolved"), 0) + 1
    for rel in relationships or []:
        upsert_relationship(driver, org_id, rel)
    counts["relationships"] = len(relationships or [])
    return counts


def link_entities_to_chunks(driver, org_id: str, doc_path: str) -> None:
    """Create MENTIONED_IN edges from org entities to the chunks of one document that mention them."""
    with driver.session() as session:
        session.run(
            """
            MATCH (c:DocumentChunk {org_id: $org, doc_path: $path})
            MATCH (e:Entity {org_id: $org})
            WHERE any(t IN coalesce(e.match_terms, [e.canonical_label])
                      WHERE toLower(c.text) CONTAINS toLower(t))
            MERGE (e)-[:MENTIONED_IN]->(c)
            """,
            org=org_id,
            path=doc_path,
        )
