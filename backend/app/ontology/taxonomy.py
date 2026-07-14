"""Loads and queries the ontology as a lightweight taxonomy structure."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ONTOLOGY_PATH = Path(__file__).parent.parent.parent.parent / "ontology" / "core_ontology.yaml"


def load() -> dict:
    with open(_ONTOLOGY_PATH) as f:
        return yaml.safe_load(f)


def class_names() -> list[str]:
    return [c["name"] for c in load().get("classes", [])]


def get_class(name: str) -> dict | None:
    for c in load().get("classes", []):
        if c["name"] == name:
            return c
    return None


def relationships_from(class_name: str) -> list[dict]:
    return [r for r in load().get("relationships", []) if r.get("from") == class_name]


def relationships_to(class_name: str) -> list[dict]:
    return [r for r in load().get("relationships", []) if r.get("to") == class_name]


def describe() -> str:
    """Return a human-readable summary of the ontology."""
    onto = load()
    lines = ["## Classes"]
    for c in onto.get("classes", []):
        hints = ", ".join(c.get("source_hints", [])) or "—"
        lines.append(f"- **{c['name']}**: {c.get('description', '')} (source hints: {hints})")
    lines.append("\n## Relationships")
    for r in onto.get("relationships", []):
        lines.append(f"- ({r.get('from')}) -[{r['name']}]-> ({r.get('to')}): {r.get('description', '')}")
    return "\n".join(lines)
