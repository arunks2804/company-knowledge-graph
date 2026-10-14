"""Translates natural language to Cypher and executes it (read-only)."""
from __future__ import annotations

import re

from neo4j import GraphDatabase

from pathlib import Path

from ..llm import get_provider
from ..ontology.taxonomy import describe as describe_ontology

_SKILL = (Path(__file__).parent.parent.parent.parent / "skills" / "cypher_generation.md").read_text()

_CYPHER_SCHEMA = {
    "cypher": "string",
    "explanation": "string",
}


def nl_to_cypher(org_id: str, question: str) -> dict:
    """Ask the LLM to translate a NL question to a read-only Cypher query."""
    provider = get_provider()
    ontology_desc = describe_ontology(org_id)
    prompt = f"""
You are a Neo4j Cypher expert.

## Skill guidance
{_SKILL}

Ontology:
{ontology_desc}

Translate the following question into a read-only Cypher query (no MERGE, CREATE, DELETE).
The graph holds several organisations. Every node pattern MUST be restricted to the current
organisation with the parameter $org_id, e.g. (p:Product {{org_id: $org_id}}) — never hard-code it.
Return JSON with keys: "cypher" (the query string) and "explanation" (one sentence what it does).

Question: {question}
"""
    return provider.generate_structured(prompt, _CYPHER_SCHEMA)


def _unscoped_node_patterns(cypher: str) -> bool:
    """
    True if any node pattern lacks an {org_id: $org_id} restriction. A bare (p) is allowed only
    when p was already bound by a scoped pattern. Function calls like count(p) are not node patterns.
    """
    scoped: set[str] = set()
    for m in re.finditer(r"(?<!\w)\(\s*(\w*)\s*(:[^(){}]*)?(\{[^}]*\})?\s*\)", cypher):
        var, label, props = m.group(1), m.group(2), m.group(3)
        if props and re.search(r"org_id\s*:\s*\$org_id\b", props):
            if var:
                scoped.add(var)
            continue
        if var and not label and not props and var in scoped:
            continue
        return True
    return False


def run_cypher(driver: GraphDatabase.driver, org_id: str, question: str) -> dict:
    """Translate question to Cypher, run it, return {cypher, explanation, rows}."""
    spec = nl_to_cypher(org_id, question)
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

    if _unscoped_node_patterns(cypher):
        return {
            "cypher": cypher,
            "explanation": spec.get("explanation", ""),
            "rows": [],
            "error": "Generated query is not restricted to the current organisation (missing {org_id: $org_id})",
        }

    try:
        with driver.session() as session:
            result = session.run(cypher, org_id=org_id)
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
