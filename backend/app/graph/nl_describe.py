"""Generates natural-language descriptions of graph entities using the LLM."""
from __future__ import annotations

from neo4j import GraphDatabase

from ..llm import get_provider


def describe_entity(driver: GraphDatabase.driver, org_id: str, canonical_id: str) -> str:
    """
    Fetch the entity + its connected chunks from Neo4j,
    then ask the LLM to write a concise NL description.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (e:Entity {org_id: $org, canonical_id: $cid})
            OPTIONAL MATCH (e)-[:MENTIONED_IN]->(c:DocumentChunk)
            OPTIONAL MATCH (e)-[r]-(other:Entity {org_id: $org})
            RETURN e, collect(DISTINCT c.text)[..3] AS chunks,
                   collect(DISTINCT type(r) + ' ' + other.canonical_label)[..10] AS links
            """,
            cid=canonical_id,
            org=org_id,
        )
        record = result.single()
        if record is None:
            return f"No entity found with id {canonical_id}"
        entity = {k: v for k, v in dict(record["e"]).items() if k != "match_terms"}
        chunks = record["chunks"] or []
        links = [l for l in record["links"] or [] if l]

    provider = get_provider()
    context = "\n---\n".join(chunks) if chunks else "(no document mentions found)"
    prompt = f"""
Entity from the knowledge graph:
{entity}

Graph relationships:
{chr(10).join(links) if links else "(none)"}

Document excerpts mentioning this entity:
{context}

Write a concise 2–3 sentence description of this entity suitable for display in a UI.
Include what it is, its key attributes, and any notable facts from the documents.
"""
    return provider.generate_text(prompt).strip()


def describe_graph_summary(driver: GraphDatabase.driver, org_id: str) -> str:
    """Return an LLM-generated executive summary of the whole knowledge graph."""
    with driver.session() as session:
        stats = session.run(
            """
            MATCH (e:Entity {org_id: $org}) RETURN labels(e) AS labels, count(e) AS cnt
            """,
            org=org_id,
        ).data()

    provider = get_provider()
    stats_str = "\n".join(f"- {r['labels']}: {r['cnt']} nodes" for r in stats)
    prompt = f"""
Knowledge graph node counts:
{stats_str}

Write a 3–4 sentence executive summary of what this graph represents,
who would find it useful, and what kinds of questions it can answer.
"""
    return provider.generate_text(prompt).strip()
