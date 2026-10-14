"""Entity resolution: maps records from all sources — structured and documents — to canonical graph nodes.

Source tables and documents are packed into batches that fit the prompt budget and resolved in
order (Postgres first, documents last). Each batch sees the canonical ids resolved so far, so a
Druid sku_code or a "SKU LP-4471" mention in a maintenance report resolves onto the same
product:LP-4471 node rather than a new one. Batch results are then merged on canonical_id.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..llm import get_provider
from ..graph.relationships import normalise_key
from .taxonomy import rel_name

_CFG_PATH = Path(__file__).parent.parent.parent / "config" / "llm_config.yaml"
_SKILL = (Path(__file__).parent.parent.parent.parent / "skills" / "entity_resolution.md").read_text()

BATCH_CHARS = 10000          # per-batch budget for source material in the prompt
DOC_EXCERPT_CHARS = 3000     # documents are split into excerpts of at most this size
MAX_KNOWN_IDS = 400          # cap on the "already resolved" id list passed to later batches

# Postgres is the id authority (see skills/entity_resolution.md), so it is resolved first
_SOURCE_ORDER = ["postgres", "timescaledb", "dynamodb", "druid", "iceberg"]


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
            "match_notes": "string",
        }
    ],
    "relationships": [
        {"from_id": "string", "type": "string", "to_id": "string", "confidence": 0.0, "evidence": "string"}
    ],
}


def _source_units(schema_data: list[dict]) -> list[dict]:
    """One unit per source table: its columns plus sample rows."""
    def rank(src: dict) -> int:
        name = src.get("source", "")
        return _SOURCE_ORDER.index(name) if name in _SOURCE_ORDER else len(_SOURCE_ORDER)

    units = []
    for src in sorted(schema_data, key=rank):
        if src.get("error"):
            continue
        source = src.get("source", "unknown")
        schema = src.get("schema") or {}
        samples = src.get("samples") or {}
        tables = schema.keys() if isinstance(schema, dict) else []
        if not tables:
            units.append({"kind": "source", "source": source, "body": src})
        for table in tables:
            units.append({
                "kind": "source",
                "source": source,
                "body": {"source": source, "table": table,
                         "columns": schema.get(table), "samples": samples.get(table, [])},
            })
    return units


def _document_units(documents: list[dict]) -> list[dict]:
    units = []
    for doc in documents:
        text = doc.get("text", "")
        for i in range(0, len(text), DOC_EXCERPT_CHARS):
            units.append({
                "kind": "document",
                "source": "document",
                "body": {"source_type": "document", "document": doc.get("name"),
                         "excerpt": text[i:i + DOC_EXCERPT_CHARS]},
            })
    return units


def _batches(units: list[dict]) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for u in units:
        # oversized units (huge sample sets) are trimmed rather than silently dropped mid-JSON
        text = json.dumps(u["body"], default=str)[:BATCH_CHARS]
        u = {**u, "text": text}
        if current and size + len(text) > BATCH_CHARS:
            batches.append(current)
            current, size = [], 0
        current.append(u)
        size += len(text)
    if current:
        batches.append(current)
    return batches


def _prompt(batch: list[dict], classes_str: str, rels_str: str, known: list[dict], auto: float, review: float) -> str:
    material = "\n\n".join(u["text"] for u in batch)
    known_str = json.dumps(known[-MAX_KNOWN_IDS:]) if known else "(none yet)"
    return f"""
You are an entity resolution expert for a cross-source knowledge graph.

## Skill guidance
{_SKILL}


Ontology classes with source hints:
{classes_str}

Ontology relationships (from_class -[TYPE]-> to_class):
{rels_str}

Entities already resolved from earlier batches (reuse these canonical_ids when a record or
document mention refers to the same real-world thing; add the new source reference to it):
{known_str}

Source material for this batch (structured tables with sample rows, and/or document excerpts):
{material}

Task:
- Identify records and document mentions that refer to the same real-world entity (e.g., LP-4471 in
  Postgres products.product_id, Druid inventory_events.sku_code, DynamoDB product_inventory.product_sku,
  and text "SKU LP-4471" in a maintenance report).
- Document mentions are sources too: use source_type "document", table_or_datasource = document name,
  key_column = "mention", key_value = the exact text identifying the entity (e.g. "LP-4471", "WH-EAST").
- Entities that only exist in documents (e.g. a maintenance incident MNT-2024-001) are valid entities.
- For each resolved entity, assign:
  - canonical_id: a stable unique ID (e.g., "product:LP-4471")
  - canonical_label: human-readable name
  - class: the ontology class name
  - confidence: float 0–1 (how sure you are this is the same entity)
  - sources: list of all source records in THIS batch that map to this entity
  - status: "auto_commit" if confidence >= {auto}, "needs_review" if >= {review}, else "unresolved"
- Under "relationships", list edges between entities that the material states directly
  (e.g. a report saying incident MNT-2024-001 affects LP-4471 at WH-EAST). Use only relationship
  types listed in the ontology, in the listed direction, and only canonical_ids from this batch or
  the already-resolved list. Put the supporting document or table in "evidence".
- Return valid JSON matching the schema.
"""


def _merge_into(merged: dict[str, dict], entity: dict) -> str | None:
    """Merge a batch entity into the running result on canonical_id (with normalised key fallback).
    Returns the canonical_id it was stored under."""
    cid = entity.get("canonical_id")
    if not cid:
        return None
    target = merged.get(cid)
    if target is None:
        cls, _, key = cid.partition(":")
        for existing_id, existing in merged.items():
            ecls, _, ekey = existing_id.partition(":")
            if ecls == cls and normalise_key(ekey) == normalise_key(key):
                target = existing
                break
    if target is None:
        merged[cid] = {**entity, "sources": list(entity.get("sources") or [])}
        return cid
    seen = {json.dumps(s, sort_keys=True, default=str) for s in target["sources"]}
    for s in entity.get("sources") or []:
        if json.dumps(s, sort_keys=True, default=str) not in seen:
            target["sources"].append(s)
    target["confidence"] = max(_as_float(target.get("confidence")), _as_float(entity.get("confidence")))
    if not target.get("canonical_label"):
        target["canonical_label"] = entity.get("canonical_label", "")
    return target["canonical_id"]


def _as_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def resolve_entities(schema_data: list[dict], ontology: dict,
                     documents: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """
    Ask the LLM to identify which records across sources and documents refer to the same real-world entity.
    Returns (entities, proposed_relationships). Entities carry confidence and status flags.
    """
    provider = get_provider()
    thresholds = _thresholds()
    auto = thresholds.get("auto_commit", 0.85)
    review = thresholds.get("needs_review", 0.50)

    classes_str = json.dumps(
        [{"name": c["name"], "source_hints": c.get("source_hints", [])} for c in ontology.get("classes", [])],
        indent=2,
    )
    rels_str = "\n".join(
        f"- {r.get('from')} -[{rel_name(r)}]-> {r.get('to')}" for r in ontology.get("relationships", [])
    ) or "(none)"

    units = _source_units(schema_data) + _document_units(documents or [])
    merged: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    proposed: list[dict] = []
    for batch in _batches(units):
        known = [{"canonical_id": e["canonical_id"], "label": e.get("canonical_label", "")} for e in merged.values()]
        result = provider.generate_structured(_prompt(batch, classes_str, rels_str, known, auto, review),
                                              _RESOLUTION_SCHEMA)
        for e in result.get("entities", []) or []:
            if isinstance(e, dict):
                stored = _merge_into(merged, e)
                if stored and stored != e.get("canonical_id"):
                    aliases[e["canonical_id"]] = stored
        proposed.extend(r for r in result.get("relationships", []) or [] if isinstance(r, dict))

    entities = list(merged.values())
    for r in proposed:
        r["from_id"] = aliases.get(r.get("from_id"), r.get("from_id"))
        r["to_id"] = aliases.get(r.get("to_id"), r.get("to_id"))

    # enforce status from confidence — guard against non-numeric LLM output
    for e in entities:
        conf = _as_float(e.get("confidence", 0))
        e["confidence"] = conf
        if conf >= auto:
            e["status"] = "auto_commit"
        elif conf >= review:
            e["status"] = "needs_review"
        else:
            e["status"] = "unresolved"

    return entities, proposed
