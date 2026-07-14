"""Generates natural-language descriptions of graph entities using the LLM."""
from __future__ import annotations

from neo4j import GraphDatabase

from ..llm import get_provider


def describe_entity(driver: GraphDatabase.driver, canonical_id: str) -> str:
    """
    Fetch the entity + its connected chunks from Neo4j,
    then ask the LLM to write a concise NL description.
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (e:Entity {canonical_id: $cid})
            OPTIONAL MATCH (e)-[:MENTIONED_IN]->(c:DocumentChunk)
            RETURN e, collect(c.text)[..3] AS chunks
            """,
            cid=canonical_id,
        )
        record = result.single()
        if record is None:
            return f"No entity found with id {canonical_id}"
        entity = dict(record["e"])
        chunks = record["chunks"] or []

    provider = get_provider()
    context = "\n---\n".join(chunks) if chunks else "(no document mentions found)"
    prompt = f"""
Entity from the knowledge graph:
{entity}

Document excerpts mentioning this entity:
{context}

Write a concise 2–3 sentence description of this entity suitable for display in a UI.
Include what it is, its key attributes, and any notable facts from the documents.
"""
    return provider.generate_text(prompt).strip()


def describe_graph_summary(driver: GraphDatabase.driver) -> str:
    """Return an LLM-generated executive summary of the whole knowledge graph."""
    with driver.session() as session:
        stats = session.run(
            """
            MATCH (e:Entity) RETURN labels(e) AS labels, count(e) AS cnt
            """
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
