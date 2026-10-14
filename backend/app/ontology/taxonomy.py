"""Loads and queries the ontology as a lightweight taxonomy structure.

The core ontology in ontology/core_ontology.yaml is the shared seed. Each org gets its own
copy at orgs/<org_id>/ontology.yaml once ingestion or editing extends it, so one org's
source hints and generated classes never leak into another's.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..orgs.config import org_dir

_CORE_PATH = Path(__file__).parent.parent.parent.parent / "ontology" / "core_ontology.yaml"


def ontology_path(org_id: str | None = None) -> Path:
    if org_id:
        p = org_dir(org_id) / "ontology.yaml"
        if p.exists():
            return p
    return _CORE_PATH


def load(org_id: str | None = None) -> dict:
    with open(ontology_path(org_id)) as f:
        return yaml.safe_load(f) or {}


def save(data: dict, org_id: str | None = None) -> None:
    path = org_dir(org_id) / "ontology.yaml" if org_id else _CORE_PATH
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def rel_name(r: dict) -> str:
    """Relationship type; older ontology files used `type` instead of `name`."""
    return r.get("name") or r.get("type") or ""


def class_names(org_id: str | None = None) -> list[str]:
    return [c["name"] for c in load(org_id).get("classes", [])]


def get_class(name: str, org_id: str | None = None) -> dict | None:
    for c in load(org_id).get("classes", []):
        if c["name"] == name:
            return c
    return None


def relationships_from(class_name: str, org_id: str | None = None) -> list[dict]:
    return [r for r in load(org_id).get("relationships", []) if r.get("from") == class_name]


def relationships_to(class_name: str, org_id: str | None = None) -> list[dict]:
    return [r for r in load(org_id).get("relationships", []) if r.get("to") == class_name]


def describe(org_id: str | None = None) -> str:
    """Return a human-readable summary of the ontology."""
    onto = load(org_id)
    lines = ["## Classes"]
    for c in onto.get("classes", []):
        hints = ", ".join(c.get("source_hints", [])) or "—"
        lines.append(f"- **{c['name']}**: {c.get('description', '')} (source hints: {hints})")
    lines.append("\n## Relationships")
    for r in onto.get("relationships", []):
        lines.append(f"- ({r.get('from')}) -[{rel_name(r)}]-> ({r.get('to')}): {r.get('description', '')}")
    return "\n".join(lines)
