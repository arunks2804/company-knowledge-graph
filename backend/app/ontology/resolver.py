"""Entity resolution: maps records from all sources — structured and documents — to canonical graph nodes.

Evidence first, LLM second:
1. Exact-key pass (no LLM): id columns are mapped to ontology classes by name or source hint
   (customer_id → Customer, product_sku → Product); records whose normalised ids match across
   sources merge into one entity, and any id or name found verbatim in a document adds a
   document mention. Confidence follows the calibration in skills/entity_resolution.md.
2. LLM pass: documents, plus tables with no recognisable id column, are packed into batches that
   fit the prompt budget. The LLM sees every id resolved so far and adds what keys cannot find —
   e.g. incidents that only exist in maintenance reports, and relationships stated in text.
   Every source reference it returns must appear verbatim in that batch's material, and every
   class must exist in the ontology; anything else is discarded as unsupported.
"""
from __future__ import annotations

import json
import re
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
    """Pack units into prompt-sized batches. Each document gets batches of its own: small local
    models lose track of which entity came from which report when several share one prompt."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for u in units:
        # oversized units (huge sample sets) are trimmed rather than silently dropped mid-JSON
        text = json.dumps(u["body"], default=str)[:BATCH_CHARS]
        u = {**u, "text": text}
        new_document = u["kind"] == "document" and (
            current[-1]["kind"] != "document" or current[-1]["body"].get("document") != u["body"].get("document")
        ) if current else False
        if current and (new_document or size + len(text) > BATCH_CHARS):
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

Entities already resolved (by exact id match or earlier batches). Reuse these canonical_ids when the
material refers to the same thing; do not repeat them unless you are adding a new source reference.
Focus on entities that are NOT in this list:
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


# ── exact-key pass ─────────────────────────────────────────────────────────────

# column suffixes that mark an identifier (customer_id, product_sku, sku_code, order_no)
_ID_SUFFIXES = ("_id", "_sku", "_code", "_key", "_no", "_number", "id", "sku")
# columns that describe an entity rather than identify it, even if a source hint names them
_NON_KEY_SUFFIXES = ("name", "description", "date", "status", "region", "category", "tier",
                     "email", "price", "amount", "qty", "quantity", "level", "days", "_at")
_NAME_COLUMNS = ("name", "full_name", "title", "display_name")
DOC_MENTION_MIN_CHARS = 4    # ignore very short ids/names when searching document text


def _class_lookup(ontology: dict) -> tuple[dict[str, str], dict[str, str]]:
    """({lowercase class name: Class}, {lowercase hinted column: Class}) for concrete classes."""
    names, hints = {}, {}
    for c in ontology.get("classes", []):
        if c.get("abstract") or not c.get("name"):
            continue
        names[c["name"].lower()] = c["name"]
        for h in c.get("source_hints") or []:
            col = str(h).split(".")[-1].strip().lower()
            if col:
                hints.setdefault(col, c["name"])
    return names, hints


def _singular(word: str) -> str:
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def _class_for_column(column: str, table: str, names: dict[str, str], hints: dict[str, str]) -> str | None:
    col = column.lower()
    if col.endswith(_NON_KEY_SUFFIXES):
        return None
    if col in hints:
        return hints[col]
    if col == "id":
        return names.get(_singular(table.lower()))
    for suffix in _ID_SUFFIXES:
        if col.endswith(suffix) and len(col) > len(suffix):
            stem = col[: -len(suffix)].rstrip("_")
            cls = names.get(stem) or names.get(_singular(stem))
            if cls:
                return cls
    return None


def _label_from_row(row: dict, cls: str, table: str) -> str | None:
    """Human name for the entity a row describes — only from the class's own table (products → Product)."""
    if _singular(table.lower()) != cls.lower():
        return None
    for col, value in row.items():
        c = col.lower()
        if isinstance(value, str) and value.strip() and (c in _NAME_COLUMNS or c == f"{cls.lower()}_name"):
            return value.strip()
    return None


def _evidence_confidence(entity: dict) -> float:
    """Calibration from skills/entity_resolution.md rule 1, computed from the sources actually found."""
    systems = {s.get("source_type") for s in entity["sources"] if s.get("source_type") != "document"}
    in_docs = any(s.get("source_type") == "document" for s in entity["sources"])
    if len(systems) >= 3:
        return 0.97
    if len(systems) == 2:
        return 0.90
    if len(systems) == 1:
        return 0.75 if in_docs else 0.60
    return 0.40


def _exact_key_entities(schema_data: list[dict], ontology: dict) -> tuple[dict[str, dict], set[tuple[str, str]]]:
    """Entities from id columns in sample rows, merged on (class, normalised id).
    Returns ({canonical_id: entity}, {(source, table) that yielded at least one key})."""
    names, hints = _class_lookup(ontology)
    by_key: dict[tuple[str, str], dict] = {}
    covered: set[tuple[str, str]] = set()

    def rank(src: dict) -> int:
        name = src.get("source", "")
        return _SOURCE_ORDER.index(name) if name in _SOURCE_ORDER else len(_SOURCE_ORDER)

    for src in sorted(schema_data, key=rank):
        source = src.get("source", "unknown")
        samples = src.get("samples")
        if src.get("error") or not isinstance(samples, dict):
            continue
        for table, rows in samples.items():
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                for column, value in row.items():
                    if value is None or isinstance(value, (dict, list, bool, float)):
                        continue
                    cls = _class_for_column(column, table, names, hints)
                    nk = normalise_key(value)
                    if not cls or len(nk) < 3:
                        continue
                    covered.add((source, table))
                    ent = by_key.get((cls, nk))
                    if ent is None:
                        # first source seen wins the id form; sources are ordered Postgres first
                        ent = by_key[(cls, nk)] = {
                            "canonical_id": f"{cls.lower()}:{value}",
                            "canonical_label": "",
                            "class": cls,
                            "sources": [],
                            "match_notes": "exact id match (normalised: case, hyphens, underscores)",
                        }
                    ref = {"source_type": source, "table_or_datasource": table,
                           "key_column": column, "key_value": str(value)}
                    if ref not in ent["sources"]:
                        ent["sources"].append(ref)
                    label = _label_from_row(row, cls, table)
                    if label and not ent["canonical_label"]:
                        ent["canonical_label"] = label
    entities = {}
    for ent in by_key.values():
        ent["canonical_label"] = ent["canonical_label"] or ent["canonical_id"].split(":", 1)[1]
        entities[ent["canonical_id"]] = ent
    return entities, covered


def _add_document_mentions(entities: dict[str, dict], documents: list[dict]) -> None:
    """Attach a document source wherever an entity's id or name appears verbatim in a document."""
    for doc in documents:
        text = doc.get("text", "")
        for ent in entities.values():
            terms = {s["key_value"] for s in ent["sources"] if s.get("source_type") != "document"}
            terms.add(ent.get("canonical_label") or "")
            for term in sorted(t for t in terms if len(t) >= DOC_MENTION_MIN_CHARS):
                if re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE):
                    ref = {"source_type": "document", "table_or_datasource": doc.get("name"),
                           "key_column": "mention", "key_value": term}
                    if ref not in ent["sources"]:
                        ent["sources"].append(ref)


_LABELLED_FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z _]{1,40}?)\s*:\s*([A-Za-z0-9][A-Za-z0-9_\-]{2,})\s*$")
DOC_HEADER_LINES = 15


def _class_words(cls: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Z][a-z]*|[a-z]+", cls)]


def _document_defined_entities(documents: list[dict], ontology: dict) -> dict[str, dict]:
    """Entities a document declares about itself in a labelled header field, e.g. a report titled
    MAINTENANCE INCIDENT REPORT with "Report ID: MNT-2024-001" (report_id is a MaintenanceIncident
    source hint). The title must name the class, so a SUPPLIER QUALITY REVIEW with its own
    Report ID is not mistaken for an incident."""
    _, hints = _class_lookup(ontology)
    found: dict[str, dict] = {}
    for doc in documents:
        lines = [l for l in doc.get("text", "").splitlines() if l.strip()]
        if not lines:
            continue
        title = lines[0].lower()
        for line in lines[1:DOC_HEADER_LINES]:
            m = _LABELLED_FIELD_RE.match(line)
            if not m:
                continue
            cls = hints.get(m.group(1).strip().lower().replace(" ", "_"))
            if not cls or not all(w in title for w in _class_words(cls)):
                continue
            value = m.group(2)
            cid = f"{cls.lower()}:{value}"
            found.setdefault(cid, {
                "canonical_id": cid, "canonical_label": value, "class": cls, "sources": [],
                "defined_in": doc.get("name"),
                "match_notes": f"declared in the header of {doc.get('name')} ({m.group(1).strip()})",
            })["sources"].append({"source_type": "document", "table_or_datasource": doc.get("name"),
                                  "key_column": m.group(1).strip(), "key_value": value})
    return found


def _co_mention_relationships(entities: dict[str, dict], defined: dict[str, dict],
                              proposed: list[dict], ontology: dict) -> list[dict]:
    """Fallback edges for a document-defined entity the LLM proposed nothing for: link it to the
    entities named in its own document wherever the ontology allows. Low confidence by design."""
    from ..graph.relationships import ontology_rel_index
    rel_index = ontology_rel_index(ontology)
    linked = {r.get("from_id") for r in proposed} | {r.get("to_id") for r in proposed}
    edges = []
    for cid, d in defined.items():
        if cid in linked or cid not in entities:
            continue
        doc = d["defined_in"]
        for other in entities.values():
            if other["canonical_id"] == cid or not any(
                    s.get("source_type") == "document" and s.get("table_or_datasource") == doc
                    for s in other["sources"]):
                continue
            for a, b in ((cid, other["canonical_id"]), (other["canonical_id"], cid)):
                for name in rel_index.get((entities[a]["class"], entities[b]["class"]), []):
                    edges.append({"from_id": a, "to_id": b, "type": name, "confidence": 0.5,
                                  "evidence": f"co-mentioned in {doc}"})
    return edges


def _supported_sources(entity: dict, batch: list[dict], material_norm: str) -> list[dict]:
    """Keep only source references the batch actually contains: the key value must occur in the
    material, and the source must be a table or document that was in this batch. This rejects real
    ids attached to invented tables (a report's MNT-2024-001 claimed as postgres.maintenanceincidents)."""
    tables = {(u["source"], u["body"].get("table")) for u in batch if u["kind"] == "source"}
    docs = {u["body"].get("document") for u in batch if u["kind"] == "document"}
    kept = []
    for s in entity.get("sources") or []:
        if not isinstance(s, dict) or s.get("key_value") in (None, ""):
            continue
        nk = normalise_key(s["key_value"])
        if len(nk) < 3 or nk not in material_norm:
            continue
        ref = {k: s.get(k) for k in ("source_type", "table_or_datasource", "key_column", "key_value")}
        if ref["source_type"] == "document":
            if ref["table_or_datasource"] not in docs:
                if len(docs) != 1:
                    continue
                ref["table_or_datasource"] = next(iter(docs))   # the only document it could be
            ref["key_column"] = ref["key_column"] or "mention"
        elif (ref["source_type"], ref["table_or_datasource"]) not in tables:
            continue
        kept.append(ref)
    return kept


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
    Resolve records across sources and documents into canonical entities (see module docstring).
    Returns (entities, proposed_relationships). Entities carry confidence and status flags.
    """
    documents = documents or []
    thresholds = _thresholds()
    auto = thresholds.get("auto_commit", 0.85)
    review = thresholds.get("needs_review", 0.50)
    class_names = {c["name"] for c in ontology.get("classes", []) if c.get("name") and not c.get("abstract")}

    merged, covered = _exact_key_entities(schema_data, ontology)
    exact_ids = set(merged)
    defined = _document_defined_entities(documents, ontology)
    for cid, ent in defined.items():
        merged.setdefault(cid, {k: v for k, v in ent.items() if k != "defined_in"})
    _add_document_mentions(merged, documents)

    classes_str = json.dumps(
        [{"name": c["name"], "source_hints": c.get("source_hints", [])} for c in ontology.get("classes", [])],
        indent=2,
    )
    rels_str = "\n".join(
        f"- {r.get('from')} -[{rel_name(r)}]-> {r.get('to')}" for r in ontology.get("relationships", [])
    ) or "(none)"

    # the LLM gets documents, plus only those tables the exact-key pass could not interpret
    units = [u for u in _source_units(schema_data)
             if (u["source"], u["body"].get("table")) not in covered] + _document_units(documents)
    aliases: dict[str, str] = {}
    proposed: list[dict] = []
    if units:
        provider = get_provider()
        for batch in _batches(units):
            material_norm = normalise_key(" ".join(u["text"] for u in batch))
            known = [{"canonical_id": e["canonical_id"], "label": e.get("canonical_label", "")} for e in merged.values()]
            result = provider.generate_structured(_prompt(batch, classes_str, rels_str, known, auto, review),
                                                  _RESOLUTION_SCHEMA)
            for e in result.get("entities", []) or []:
                if not isinstance(e, dict) or e.get("class") not in class_names or not e.get("canonical_id"):
                    continue
                sources = _supported_sources(e, batch, material_norm)
                if not sources:
                    continue  # nothing in the material backs this entity — likely invented
                stored = _merge_into(merged, {**e, "sources": sources})
                if stored and stored != e.get("canonical_id"):
                    aliases[e["canonical_id"]] = stored
            proposed.extend(r for r in result.get("relationships", []) or [] if isinstance(r, dict))

    entities = list(merged.values())
    # edge endpoints may use an alias or a differently formatted id (product:LP4471 for product:LP-4471)
    by_norm = {(cid.partition(":")[0], normalise_key(cid.partition(":")[2])): cid for cid in merged}

    def canonical(cid):
        cid = aliases.get(cid, cid)
        if cid in merged or not isinstance(cid, str):
            return cid
        cls, _, key = cid.partition(":")
        return by_norm.get((cls, normalise_key(key)), cid)

    for r in proposed:
        r["from_id"] = canonical(r.get("from_id"))
        r["to_id"] = canonical(r.get("to_id"))
    # Links between two database records come from the databases (foreign keys in rows). A report
    # mentioning an order and a product near each other is not evidence that one contains the other,
    # so the LLM may only add edges that involve an entity found solely in documents.
    proposed = [r for r in proposed if r.get("from_id") not in exact_ids or r.get("to_id") not in exact_ids]
    proposed.extend(_co_mention_relationships(merged, defined, proposed, ontology))

    for e in entities:
        if e["canonical_id"] in exact_ids or any(s.get("source_type") != "document" for s in e["sources"]):
            # structured evidence exists: confidence comes from what was matched, not the LLM's estimate
            conf = _evidence_confidence(e)
        elif e["canonical_id"] in defined:
            # a document declares this id explicitly — real, but only ever from one place: review it
            conf = 0.60
        else:
            # document-only entity proposed by the LLM — never auto-committed without a person
            conf = min(_as_float(e.get("confidence", 0)), auto - 0.01)
        e["confidence"] = conf
        if conf >= auto:
            e["status"] = "auto_commit"
        elif conf >= review:
            e["status"] = "needs_review"
        else:
            e["status"] = "unresolved"

    return entities, proposed
