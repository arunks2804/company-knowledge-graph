"""Uses the LLM to extend or refine the seed ontology based on observed schema data."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..llm import get_provider

_ONTOLOGY_PATH = Path(__file__).parent.parent.parent.parent / "ontology" / "core_ontology.yaml"
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


def load_seed_ontology() -> dict:
    with open(_ONTOLOGY_PATH) as f:
        return yaml.safe_load(f)


def save_ontology(ontology: dict) -> None:
    with open(_ONTOLOGY_PATH, "w") as f:
        yaml.dump(ontology, f, default_flow_style=False, allow_unicode=True)


def generate_ontology(schema_data: list[dict]) -> dict:
    """
    Given a list of schema dicts from each connector, ask the LLM to propose
    a merged ontology that maps all source concepts to a shared class hierarchy.
    """
    seed = load_seed_ontology()
    provider = get_provider()

    schema_summary = json.dumps(schema_data, indent=2)[:8000]
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

    merged = {
        "classes": seed.get("classes", []) + [
            c for c in result.get("classes", [])
            if c.get("name") not in {x["name"] for x in seed.get("classes", [])}
        ],
        "relationships": seed.get("relationships", []) + [
            r for r in result.get("relationships", [])
            if r.get("name") not in {x["name"] for x in seed.get("relationships", [])}
        ],
    }
    save_ontology(merged)
    return merged
