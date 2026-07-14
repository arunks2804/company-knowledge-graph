"""Write-back operations for ontology editing from the UI."""
from __future__ import annotations

from pathlib import Path

import yaml

_ONTOLOGY_PATH = Path(__file__).parent.parent.parent.parent / "ontology" / "core_ontology.yaml"


def _load() -> dict:
    with open(_ONTOLOGY_PATH) as f:
        return yaml.safe_load(f)


def _save(data: dict) -> None:
    with open(_ONTOLOGY_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def update_class(name: str, new_name: str | None, description: str | None, source_hints: list[str] | None) -> dict:
    data = _load()
    for c in data.get("classes", []):
        if c["name"] == name:
            if new_name:
                c["name"] = new_name
                # update any relationships that reference the old name
                for r in data.get("relationships", []):
                    if r.get("from") == name:
                        r["from"] = new_name
                    if r.get("to") == name:
                        r["to"] = new_name
            if description is not None:
                c["description"] = description
            if source_hints is not None:
                c["source_hints"] = source_hints
            break
    _save(data)
    return {"ok": True}


def remove_class(name: str) -> dict:
    data = _load()
    data["classes"] = [c for c in data.get("classes", []) if c["name"] != name]
    data["relationships"] = [
        r for r in data.get("relationships", [])
        if r.get("from") != name and r.get("to") != name
    ]
    _save(data)
    return {"ok": True}


def add_class(name: str, description: str, source_hints: list[str]) -> dict:
    data = _load()
    existing = {c["name"] for c in data.get("classes", [])}
    if name in existing:
        return {"ok": False, "error": f"Class '{name}' already exists"}
    data.setdefault("classes", []).append({
        "name": name,
        "description": description,
        "source_hints": source_hints,
        "properties": [],
    })
    _save(data)
    return {"ok": True}


def update_relationship(from_class: str, to_class: str, old_name: str, new_name: str) -> dict:
    data = _load()
    for r in data.get("relationships", []):
        if r.get("from") == from_class and r.get("to") == to_class and r.get("name") == old_name:
            r["name"] = new_name
            break
    _save(data)
    return {"ok": True}


def remove_relationship(from_class: str, to_class: str, name: str) -> dict:
    data = _load()
    data["relationships"] = [
        r for r in data.get("relationships", [])
        if not (r.get("from") == from_class and r.get("to") == to_class and r.get("name") == name)
    ]
    _save(data)
    return {"ok": True}


def add_relationship(from_class: str, to_class: str, name: str, description: str) -> dict:
    data = _load()
    data.setdefault("relationships", []).append({
        "from": from_class,
        "to": to_class,
        "name": name,
        "description": description,
    })
    _save(data)
    return {"ok": True}
