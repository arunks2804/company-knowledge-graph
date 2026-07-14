"""Translates natural language to Cypher and executes it (read-only)."""
from __future__ import annotations

from neo4j import GraphDatabase

from pathlib import Path

from ..llm import get_provider
from ..ontology.taxonomy import describe as describe_ontology

_SKILL = (Path(__file__).parent.parent.parent.parent / "skills" / "cypher_generation.md").read_text()

_CYPHER_SCHEMA = {
    "cypher": "string",
    "explanation": "string",
}


def nl_to_cypher(question: str) -> dict:
    """Ask the LLM to translate a NL question to a read-only Cypher query."""
    provider = get_provider()
    ontology_desc = describe_ontology()
    prompt = f"""
You are a Neo4j Cypher expert.

## Skill guidance
{_SKILL}

Ontology:
{ontology_desc}

Translate the following question into a read-only Cypher query (no MERGE, CREATE, DELETE).
Return JSON with keys: "cypher" (the query string) and "explanation" (one sentence what it does).

Question: {question}
"""
    return provider.generate_structured(prompt, _CYPHER_SCHEMA)


def run_cypher(driver: GraphDatabase.driver, question: str) -> dict:
    """Translate question to Cypher, run it, return {cypher, explanation, rows}."""
    spec = nl_to_cypher(question)
    cypher = spec.get("cypher", "")

    # Safety: block write keywords
    blocked = ["CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP"]
    upper = cypher.upper()
    for kw in blocked:
        if kw in upper:
            return {
                "cypher": cypher,
                "explanation": spec.get("explanation", ""),
                "rows": [],
                "error": f"Generated query contains disallowed keyword: {kw}",
            }

    try:
        with driver.session() as session:
            result = session.run(cypher)
            rows = [dict(r) for r in result]
    except Exception as exc:
        return {
            "cypher": cypher,
            "explanation": spec.get("explanation", ""),
            "rows": [],
            "error": str(exc),
        }

    return {
        "cypher": cypher,
        "explanation": spec.get("explanation", ""),
        "rows": rows,
    }
