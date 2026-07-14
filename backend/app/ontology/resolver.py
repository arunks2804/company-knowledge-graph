"""Entity resolution: maps records from all sources to a single canonical graph node."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..llm import get_provider

_CFG_PATH = Path(__file__).parent.parent.parent / "config" / "llm_config.yaml"
_SKILL = (Path(__file__).parent.parent.parent.parent / "skills" / "entity_resolution.md").read_text()


def _thresholds() -> dict:
    with open(_CFG_PATH) as f:
        return yaml.safe_load(f).get("confidence", {})


_RESOLUTION_SCHEMA = {
    "entities": [
        {
            "canonical_id": "string",
            "canonical_label": "string",
            "class": "string",
            "confidence": 0.0,
            "sources": [
                {
                    "source_type": "string",
                    "table_or_datasource": "string",
                    "key_column": "string",
                    "key_value": "string",
                }
            ],
            "status": "auto_commit | needs_review | unresolved",
        }
    ]
}


def resolve_entities(schema_data: list[dict], ontology: dict) -> list[dict]:
    """
    Ask the LLM to identify which records across sources refer to the same real-world entity.
    Returns a list of resolved entity dicts with confidence and status flags.
    """
    provider = get_provider()
    thresholds = _thresholds()
    auto = thresholds.get("auto_commit", 0.85)
    review = thresholds.get("needs_review", 0.50)

    classes_str = json.dumps(
        [{"name": c["name"], "source_hints": c.get("source_hints", [])} for c in ontology.get("classes", [])],
        indent=2,
    )
    samples_str = json.dumps(schema_data, indent=2)[:10000]

    prompt = f"""
You are an entity resolution expert for a cross-source knowledge graph.

## Skill guidance
{_SKILL}


Ontology classes with source hints:
{classes_str}

Source schemas and sample rows (truncated):
{samples_str}

Task:
- Identify records that refer to the same real-world entity (e.g., LP-4471 in Postgres products.product_id,
  Druid inventory_events.sku_code, DynamoDB product_inventory.product_sku, and text "SKU LP-4471" in documents).
- For each resolved entity, assign:
  - canonical_id: a stable unique ID (e.g., "product:LP-4471")
  - canonical_label: human-readable name
  - class: the ontology class name
  - confidence: float 0–1 (how sure you are this is the same entity)
  - sources: list of all source records that map to this entity
  - status: "auto_commit" if confidence >= {auto}, "needs_review" if >= {review}, else "unresolved"
- Return valid JSON matching the schema.
"""
    result = provider.generate_structured(prompt, _RESOLUTION_SCHEMA)
    entities = result.get("entities", [])

    # enforce status from confidence — guard against non-numeric LLM output
    for e in entities:
        try:
            conf = float(e.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        if conf >= auto:
            e["status"] = "auto_commit"
        elif conf >= review:
            e["status"] = "needs_review"
        else:
            e["status"] = "unresolved"

    return entities
