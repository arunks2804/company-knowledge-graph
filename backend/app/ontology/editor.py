"""Write-back operations for ontology editing from the UI."""
from __future__ import annotations

from . import taxonomy
from .taxonomy import rel_name


def _load(org_id: str) -> dict:
    return taxonomy.load(org_id)


def _save(data: dict, org_id: str) -> None:
    taxonomy.save(data, org_id)


def update_class(org_id: str, name: str, new_name: str | None, description: str | None, source_hints: list[str] | None) -> dict:
    data = _load(org_id)
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
    _save(data, org_id)
    return {"ok": True}


def remove_class(org_id: str, name: str) -> dict:
    data = _load(org_id)
    data["classes"] = [c for c in data.get("classes", []) if c["name"] != name]
    data["relationships"] = [
        r for r in data.get("relationships", [])
        if r.get("from") != name and r.get("to") != name
    ]
    _save(data, org_id)
    return {"ok": True}


def add_class(org_id: str, name: str, description: str, source_hints: list[str]) -> dict:
    data = _load(org_id)
    existing = {c["name"] for c in data.get("classes", [])}
    if name in existing:
        return {"ok": False, "error": f"Class '{name}' already exists"}
    data.setdefault("classes", []).append({
        "name": name,
        "description": description,
        "source_hints": source_hints,
        "properties": [],
    })
    _save(data, org_id)
    return {"ok": True}


def update_relationship(org_id: str, from_class: str, to_class: str, old_name: str, new_name: str) -> dict:
    data = _load(org_id)
    for r in data.get("relationships", []):
        if r.get("from") == from_class and r.get("to") == to_class and rel_name(r) == old_name:
            r.pop("type", None)
            r["name"] = new_name
            break
    _save(data, org_id)
    return {"ok": True}


def remove_relationship(org_id: str, from_class: str, to_class: str, name: str) -> dict:
    data = _load(org_id)
    data["relationships"] = [
        r for r in data.get("relationships", [])
        if not (r.get("from") == from_class and r.get("to") == to_class and rel_name(r) == name)
    ]
    _save(data, org_id)
    return {"ok": True}


def add_relationship(org_id: str, from_class: str, to_class: str, name: str, description: str) -> dict:
    data = _load(org_id)
    data.setdefault("relationships", []).append({
        "from": from_class,
        "to": to_class,
        "name": name,
        "description": description,
    })
    _save(data, org_id)
    return {"ok": True}
