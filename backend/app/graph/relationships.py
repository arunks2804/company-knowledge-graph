"""Derives entity-to-entity edges from resolved entities, source rows, and the ontology.

Two sources of edges:
1. Deterministic — a sample row that references two resolved entities (e.g. an orders row
   holding both ORD-20240101 and CUST-001) yields an edge whenever the ontology defines a
   relationship between their classes (Customer -PLACED-> Order). This turns foreign keys
   into graph edges without needing FK metadata from every connector.
2. LLM-proposed — the resolver may propose edges (typically from documents, e.g.
   MaintenanceIncident -AFFECTS-> Product). These are kept only if both endpoints were
   resolved and the ontology allows that relationship between their classes.
"""
from __future__ import annotations

import re
from itertools import permutations

from ..ontology.taxonomy import rel_name

_NORM_RE = re.compile(r"[\s\-_]")
_SAFE_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def normalise_key(value) -> str:
    """LP-4471, lp4471 and LP_4471 all normalise to 'lp4471'."""
    return _NORM_RE.sub("", str(value)).lower()


def safe_ident(name: str, fallback: str) -> str:
    """Strip anything that is not valid in an unquoted Cypher label or relationship type."""
    cleaned = _SAFE_IDENT_RE.sub("", name or "")
    return cleaned if cleaned and not cleaned[0].isdigit() else fallback


def ontology_rel_index(ontology: dict) -> dict[tuple[str, str], list[str]]:
    """{(from_class, to_class): [REL_NAME, ...]}"""
    index: dict[tuple[str, str], list[str]] = {}
    for r in ontology.get("relationships", []):
        name = rel_name(r)
        if r.get("from") and r.get("to") and name:
            index.setdefault((r["from"], r["to"]), []).append(name)
    return index


def entity_key_index(entities: list[dict]) -> dict[str, set[str]]:
    """{normalised key value: {canonical_id, ...}} built from every source reference."""
    index: dict[str, set[str]] = {}
    for e in entities:
        cid = e.get("canonical_id")
        if not cid:
            continue
        keys = {s.get("key_value") for s in e.get("sources", []) if isinstance(s, dict)}
        # canonical_id's key part (product:LP-4471 → LP-4471) is a key too
        keys.add(cid.split(":", 1)[-1])
        for k in keys:
            if k is None:
                continue
            nk = normalise_key(k)
            if len(nk) >= 3:  # ignore tiny keys like "1" that would match everything
                index.setdefault(nk, set()).add(cid)
    return index


def _iter_rows(schema_data: list[dict]):
    """Yield (source, table, row) for every sample row across connectors."""
    for src in schema_data:
        samples = src.get("samples")
        if not isinstance(samples, dict):
            continue
        for table, rows in samples.items():
            for row in rows or []:
                if isinstance(row, dict):
                    yield src.get("source", "unknown"), table, row


def derive_row_relationships(entities: list[dict], schema_data: list[dict], ontology: dict) -> list[dict]:
    rel_index = ontology_rel_index(ontology)
    key_index = entity_key_index(entities)
    class_of = {e["canonical_id"]: e.get("class") for e in entities if e.get("canonical_id")}
    conf_of = {e["canonical_id"]: _as_float(e.get("confidence")) for e in entities if e.get("canonical_id")}

    edges: dict[tuple[str, str, str], dict] = {}
    for source, table, row in _iter_rows(schema_data):
        referenced: set[str] = set()
        for value in row.values():
            if value is None or isinstance(value, (dict, list)):
                continue
            referenced |= key_index.get(normalise_key(value), set())
        for a, b in permutations(referenced, 2):
            for name in rel_index.get((class_of.get(a), class_of.get(b)), []):
                key = (a, name, b)
                if key not in edges:
                    edges[key] = {
                        "from_id": a,
                        "to_id": b,
                        "type": name,
                        "confidence": min(conf_of.get(a, 0.0), conf_of.get(b, 0.0)),
                        "evidence": f"{source}.{table}",
                    }
    return list(edges.values())


def validate_proposed_relationships(proposed: list[dict], entities: list[dict], ontology: dict) -> list[dict]:
    rel_index = ontology_rel_index(ontology)
    class_of = {e["canonical_id"]: e.get("class") for e in entities if e.get("canonical_id")}
    kept = []
    for r in proposed:
        a, b, name = r.get("from_id"), r.get("to_id"), r.get("type")
        if a in class_of and b in class_of and name in rel_index.get((class_of[a], class_of[b]), []):
            kept.append({
                "from_id": a,
                "to_id": b,
                "type": name,
                "confidence": _as_float(r.get("confidence"), 0.5),
                "evidence": r.get("evidence") or "llm",
            })
    return kept


def build_relationships(entities: list[dict], schema_data: list[dict], ontology: dict,
                        proposed: list[dict] | None = None) -> list[dict]:
    """All edges to write, deduplicated on (from, type, to); row-derived evidence wins."""
    merged: dict[tuple[str, str, str], dict] = {}
    for r in validate_proposed_relationships(proposed or [], entities, ontology):
        merged[(r["from_id"], r["type"], r["to_id"])] = r
    for r in derive_row_relationships(entities, schema_data, ontology):
        merged[(r["from_id"], r["type"], r["to_id"])] = r
    return list(merged.values())


def _as_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
