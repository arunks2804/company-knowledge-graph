"""Uses the LLM to extend or refine the seed ontology based on observed schema data."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..llm import get_provider
from . import taxonomy
_SKILL = (Path(__file__).parent.parent.parent.parent / "skills" / "ontology_generation.md").read_text()

_SCHEMA = {
    "classes": [
        {
            "name": "string",
            "description": "string",
            "properties": ["string"],
            "source_hints": ["string"],
        }
    ],
    "relationships": [
        {
            "name": "string",
            "from": "string",
            "to": "string",
            "description": "string",
        }
    ],
}


def load_seed_ontology(org_id: str | None = None) -> dict:
    """The org's ontology if it has one yet, otherwise the shared core seed."""
    return taxonomy.load(org_id)


def save_ontology(ontology: dict, org_id: str | None = None) -> None:
    taxonomy.save(ontology, org_id)


def _observed_columns(schema_data: list[dict]) -> set[tuple[str, str]]:
    """{(table, column)} actually extracted from the sources, lowercased."""
    seen = set()
    for src in schema_data:
        schema = src.get("schema")
        if not isinstance(schema, dict):
            continue
        for table, cols in schema.items():
            for c in cols or []:
                name = c.get("column") if isinstance(c, dict) else c
                if name:
                    seen.add((str(table).lower(), str(name).lower()))
    return seen


def _hint_column(hint: str, observed: set[tuple[str, str]]) -> tuple[str, str] | None:
    """Resolve "source.table.column", "table.column" or "column" to an observed (table, column)."""
    parts = str(hint).lower().split(".")
    if len(parts) >= 2:
        key = (parts[-2], parts[-1])
        return key if key in observed else None
    return next((tc for tc in observed if tc[1] == parts[0]), None)


def _evidence_backed(generated: dict, seed: dict, schema_data: list[dict]) -> dict:
    """Keep generated classes only when the schemas support them (skills/ontology_generation.md
    rule 1): at least two source hints that name real extracted columns, none of which is an id
    column an existing class already owns (that would be a synonym, e.g. ProductVariant on
    product_id). Relationships are kept only between known classes not already linked."""
    observed = _observed_columns(schema_data)
    owned = {str(h).split(".")[-1].lower() for c in seed.get("classes", []) for h in c.get("source_hints") or []}
    seed_names = {c["name"] for c in seed.get("classes", [])}

    classes = []
    for c in generated.get("classes", []) or []:
        name = c.get("name")
        if not name or name in seed_names:
            continue
        cols = {tc for tc in (_hint_column(h, observed) for h in c.get("source_hints") or []) if tc}
        if len(cols) >= 2 and not any(col in owned for _, col in cols):
            classes.append({**c, "source_hints": sorted(f"{t}.{col}" for t, col in cols)})

    known = seed_names | {c["name"] for c in classes}
    linked = {frozenset((r.get("from"), r.get("to"))) for r in seed.get("relationships", [])}
    relationships = []
    for r in generated.get("relationships", []) or []:
        pair = frozenset((r.get("from"), r.get("to")))
        if taxonomy.rel_name(r) and r.get("from") in known and r.get("to") in known and pair not in linked:
            relationships.append(r)
            linked.add(pair)
    return {"classes": classes, "relationships": relationships}


def generate_ontology(schema_data: list[dict], org_id: str | None = None) -> dict:
    """
    Given a list of schema dicts from each connector, ask the LLM to propose
    a merged ontology that maps all source concepts to a shared class hierarchy.
    """
    seed = load_seed_ontology(org_id)
    provider = get_provider()

    schema_summary = json.dumps(schema_data, indent=2, default=str)[:8000]
    seed_str = yaml.dump(seed, default_flow_style=False)

    prompt = f"""
You are a knowledge-graph ontology engineer.

## Skill guidance
{_SKILL}

Existing seed ontology (YAML):
{seed_str}

Observed source schemas (JSON — truncated to 8000 chars):
{schema_summary}

Task:
1. Extend the ontology with any new classes or relationships implied by the schemas.
2. For each class, list `source_hints`: which table/column names map to this class.
3. Keep existing classes and relationships — only add, never delete.
4. Return valid JSON matching exactly the schema below.
"""
    result = provider.generate_structured(prompt, _SCHEMA)

    added = _evidence_backed(result, seed, schema_data)
    merged = {
        "classes": seed.get("classes", []) + added["classes"],
        "relationships": seed.get("relationships", []) + added["relationships"],
    }
    save_ontology(merged, org_id)
    return merged
