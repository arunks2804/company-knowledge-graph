"""Graph RAG investigation: resolve entities in the question, traverse the graph, gather documents, answer.

Pipeline:
1. If there is conversation history, rewrite a follow-up ("who supplies those products?") into a
   standalone question and list the entities it refers to.
2. Extract entity mentions (WH-EAST, LP-4471, "Laptop Pro") and map them to graph nodes.
3. Traverse up to MAX_HOPS in both directions from those nodes (Warehouse ← Incident → Product → Supplier).
4. Gather document chunks that mention those entities, plus vector-search hits.
5. Ask the LLM to synthesise a cited answer.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from neo4j import GraphDatabase

from ..llm import get_provider
from .search import extract_mentions, find_entities, vector_search

_SKILL = (Path(__file__).parent.parent.parent.parent / "skills" / "investigation_rag.md").read_text()

MAX_HOPS = 3
MAX_HISTORY_TURNS = 6
MAX_TURN_CHARS = 1500

_REWRITE_SCHEMA = {"standalone_question": "string", "mentions": ["string"]}


def _history_str(history: list[dict]) -> str:
    turns = history[-MAX_HISTORY_TURNS:]
    return "\n".join(
        f"{t.get('role', 'user').upper()}: {str(t.get('content', ''))[:MAX_TURN_CHARS]}" for t in turns
    )


def _rewrite_followup(provider, question: str, history: list[dict]) -> tuple[str, list[str]]:
    """Turn a follow-up into a standalone question plus the entity names/ids it refers to."""
    prompt = f"""
Conversation so far:
{_history_str(history)}

Follow-up question: {question}

Rewrite the follow-up as a short standalone question that can be understood without the
conversation: replace references like "those products", "it" or "that warehouse" with the specific
names and ids they point to. Keep the question as narrow as the follow-up — do not add conditions
or other entities from the conversation that the follow-up does not refer to.
Example: after an answer about the Laptop Pro 14 (LP-4471), "Which customers ordered those
products?" becomes "Which customers ordered the Laptop Pro 14 (LP-4471)?"
Also list only the entity names or ids that the standalone question refers to.
Return JSON with keys "standalone_question" and "mentions".
"""
    try:
        out = provider.generate_structured(prompt, _REWRITE_SCHEMA)
        standalone = str(out.get("standalone_question") or question)
        mentions = [str(m) for m in out.get("mentions") or [] if m]
        return standalone, mentions
    except Exception:
        # fall back to the raw question plus anything identifiable in the last answer
        last_answer = next((t.get("content", "") for t in reversed(history) if t.get("role") == "assistant"), "")
        return question, extract_mentions(str(last_answer))


def _traverse(session, org_id: str, canonical_ids: list[str], limit: int = 80) -> list[dict]:
    """Distinct entity-to-entity edges within MAX_HOPS of the seed entities, in either direction,
    nearest first so the limit drops the most distant edges."""
    return session.run(
        f"""
        MATCH (e:Entity {{org_id: $org}}) WHERE e.canonical_id IN $cids
        MATCH p = (e)-[rels*1..{MAX_HOPS}]-(:Entity {{org_id: $org}})
        WHERE none(r IN rels WHERE type(r) = 'MENTIONED_IN')
        UNWIND range(0, size(rels) - 1) AS i
        WITH rels[i] AS r, min(i) AS hop
        ORDER BY hop
        RETURN startNode(r).canonical_id AS src,
               startNode(r).canonical_label AS src_label,
               type(r) AS rel,
               endNode(r).canonical_id AS tgt,
               endNode(r).canonical_label AS tgt_label
        LIMIT $limit
        """,
        org=org_id,
        cids=canonical_ids,
        limit=limit,
    ).data()


def _paths(session, org_id: str, canonical_ids: list[str], limit: int = 40) -> list[str]:
    """Each path from a seed entity, up to MAX_HOPS, written as one line of readable facts —
    e.g. "ORD-20240101 contains Laptop Pro 14 (LP-4471); Alice Nakamura (CUST-001) placed ORD-20240101".
    Small models answer multi-hop questions reliably when the chain is already assembled."""
    rows = session.run(
        f"""
        MATCH (e:Entity {{org_id: $org}}) WHERE e.canonical_id IN $cids
        MATCH p = (e)-[rels*1..{MAX_HOPS}]-(:Entity {{org_id: $org}})
        WHERE none(r IN rels WHERE type(r) = 'MENTIONED_IN')
          AND all(i IN range(0, size(nodes(p)) - 2) WHERE NOT nodes(p)[i] IN nodes(p)[i + 1..])
          // no sideways hops to a sibling through a shared node — two consecutive edges of the same
          // type meeting the middle node from the same side: Laptop → SUP-001 ← Tablet, or
          // ORD-20240101 ← Alice → ORD-20240201 (an unrelated order of the same customer)
          AND none(i IN range(0, size(rels) - 2) WHERE type(rels[i]) = type(rels[i + 1])
                   AND ((endNode(rels[i]) = nodes(p)[i + 1] AND endNode(rels[i + 1]) = nodes(p)[i + 1])
                     OR (startNode(rels[i]) = nodes(p)[i + 1] AND startNode(rels[i + 1]) = nodes(p)[i + 1])))
        RETURN [n IN nodes(p) | {{id: n.canonical_id, label: n.canonical_label}}] AS ns,
               [r IN rels | {{type: type(r), start: startNode(r).canonical_id}}] AS rs,
               size(rels) AS hops
        ORDER BY hops DESC
        LIMIT $fetch
        """,
        org=org_id, cids=canonical_ids, fetch=limit * 4,
    ).data()
    lines, covered = [], set()
    for row in rows:
        ns, rs = row["ns"], row["rs"]
        steps = []
        for i, r in enumerate(rs):
            a, b = ns[i], ns[i + 1]
            src, tgt = (a, b) if r["start"] == a["id"] else (b, a)
            steps.append((src["id"], r["type"], tgt["id"],
                          f"{_display(src['label'], src['id'])} {_phrase(r['type'])} {_display(tgt['label'], tgt['id'])}"))
        key = frozenset(s[:3] for s in steps)
        if key <= covered:
            continue          # every fact on this path is already in a longer one
        covered |= key
        lines.append("; ".join(s[3] for s in steps))
        if len(lines) >= limit:
            break
    return lines


def _mentioning_chunks(session, org_id: str, canonical_ids: list[str], limit: int = 6) -> list[dict]:
    """Document chunks linked to the seed entities, most entities-mentioned first."""
    return session.run(
        """
        MATCH (e:Entity {org_id: $org})-[:MENTIONED_IN]->(c:DocumentChunk {org_id: $org})
        WHERE e.canonical_id IN $cids
        OPTIONAL MATCH (d:Document {org_id: $org})-[:HAS_CHUNK]->(c)
        WITH c, d, count(DISTINCT e) AS hits
        RETURN c.text AS text, d.name AS document, d.path AS path, NULL AS score, hits
        ORDER BY hits DESC
        LIMIT $limit
        """,
        org=org_id,
        cids=canonical_ids,
        limit=limit,
    ).data()


def _data_map(session, org_id: str, max_lines: int = 40) -> str:
    """Where each class lives in the source systems — tables, key columns, and the tables that share
    a key (i.e. how to join them). Built from the source references recorded on resolved entities."""
    rows = session.run(
        "MATCH (e:Entity {org_id: $org}) RETURN e.class AS cls, e.sources AS sources",
        org=org_id,
    ).data()
    locations: dict[str, set[str]] = {}
    for row in rows:
        try:
            sources = json.loads(row["sources"] or "[]")
        except (TypeError, ValueError):
            continue
        for src in sources:
            if not isinstance(src, dict) or src.get("source_type") in (None, "document"):
                continue
            loc = f"{src['source_type']}.{src.get('table_or_datasource')}.{src.get('key_column')}"
            locations.setdefault(row["cls"] or "Entity", set()).add(loc)
    lines = []
    for cls in sorted(locations):
        locs = sorted(locations[cls])
        line = f"- {cls}: {', '.join(locs)}"
        if len(locs) > 1:
            line += "  (tables sharing this key can be joined on it)"
        lines.append(line)
    return "\n".join(lines[:max_lines])


def _business_id(canonical_id: str) -> str:
    """product:LP-4471 → LP-4471"""
    return canonical_id.split(":", 1)[-1] if canonical_id else ""


def _display(label: str | None, canonical_id: str) -> str:
    key = _business_id(canonical_id)
    return f"{label} ({key})" if label and label != key else key


def _phrase(rel_type: str) -> str:
    """SUPPLIED_BY → supplied by"""
    return (rel_type or "related to").replace("_", " ").lower()


_CITATION_START = re.compile(r"\s*\[(?:graph|doc|source)s?\s*:", re.IGNORECASE)
_TYPED_ID_IN_PARENS = re.compile(r"\s*\((?:[a-z]+):([A-Za-z0-9][A-Za-z0-9_\-]*)\)")
_SOURCES_SECTION = re.compile(r"\s*\b(?:Sources?|References?|Citations?)\s*:", re.IGNORECASE)
_LEAD_IN = re.compile(r"^\s*(?:here(?:'s| is) (?:the|my) answer|answer|based on [^.:]{0,100}?)\s*[:,]\s*", re.IGNORECASE)
_TYPED_ID = re.compile(r"\b(?:product|customer|order|warehouse|supplier|shipment|maintenanceincident):([A-Za-z0-9][A-Za-z0-9_\-]*)")


def _strip_citations(text: str) -> str:
    """Remove [graph: …] / [doc: …] blocks, which can contain nested -[REL]-> brackets."""
    out, i = [], 0
    while i < len(text):
        m = _CITATION_START.match(text, i)
        if m:
            depth, j = 0, m.start() + text[m.start():].index("[")
            while j < len(text):
                depth += {"[": 1, "]": -1}.get(text[j], 0)
                j += 1
                if depth == 0:
                    break
            i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def plain_answer(text: str) -> str:
    """Remove citation markup a model may still emit despite instructions: [graph: …] / [doc: …]
    blocks and typed ids like product:LP-4471. A sentence whose subject was a citation
    ("[doc: a.txt] and [doc: b.txt] support this.") is dropped rather than left as a fragment."""
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", (text or "").strip()):
        stripped = _strip_citations(sentence).strip()
        if stripped != sentence.strip() and (not stripped.strip(" .") or not stripped[0].isupper()):
            continue   # a fragment whose subject was a citation, e.g. "and both support this answer."
        kept.append(stripped)
    text = " ".join(kept)
    # the app lists sources under the answer, so a "Sources:" section in the text is dropped
    m = _SOURCES_SECTION.search(text)
    if m and m.start() > 0:
        text = text[:m.start()]
    text = _LEAD_IN.sub("", text, count=1)
    text = text[:1].upper() + text[1:]
    text = _TYPED_ID_IN_PARENS.sub(lambda m: f" ({m.group(1)})", text)
    text = _TYPED_ID.sub(lambda m: m.group(1), text)
    text = re.sub(r"\((\w[\w\-]*)\)\s*\(\1\)", r"(\1)", text)    # "(LP-4471) (LP-4471)"
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _sources_by_document(chunks: list[dict]) -> list[dict]:
    """One entry per document (several excerpts can come from the same file), best score kept."""
    best: dict[str, dict] = {}
    for c in chunks:
        key = c.get("path") or c.get("document")
        score = c.get("score")
        entry = best.setdefault(key, {"document": c.get("document"), "path": c.get("path"), "score": score})
        if score is not None and (entry["score"] is None or score > entry["score"]):
            entry["score"] = score
    return list(best.values())


def investigate(driver: GraphDatabase.driver, org_id: str, question: str,
                history: list[dict] | None = None) -> dict:
    """
    Answer a question (optionally a follow-up in a conversation) from this org's graph and documents.
    Returns {answer, sources, entities_used, standalone_question}.
    """
    provider = get_provider()
    history = history or []

    standalone, llm_mentions = (question, [])
    if history:
        standalone, llm_mentions = _rewrite_followup(provider, question, history)

    mentions = llm_mentions + extract_mentions(standalone)
    entity_hits = find_entities(driver, org_id, mentions, top_k=8)
    seed_ids = [e["id"] for e in entity_hits[:5]]

    edges: list[dict] = []
    graph_chunks: list[dict] = []
    with driver.session() as session:
        data_map = _data_map(session, org_id)
        paths: list[str] = []
        if seed_ids:
            edges = _traverse(session, org_id, seed_ids)
            paths = _paths(session, org_id, seed_ids)
            graph_chunks = _mentioning_chunks(session, org_id, seed_ids)

    vector_chunks = vector_search(driver, org_id, standalone, top_k=6)

    chunks: list[dict] = []
    seen = set()
    for c in graph_chunks + vector_chunks:
        key = (c.get("path"), c.get("text"))
        if key not in seen:
            seen.add(key)
            chunks.append(c)

    # whole paths as readable phrases: the model echoes plain language and need not chain facts itself
    graph_context = "\n".join(f"- {line}" for line in paths)
    entity_context = "\n".join(
        f"- {_display(e['label'], e['id'])} — {', '.join(e.get('classes') or []) or 'entity'}" for e in entity_hits[:5]
    )
    doc_context = "\n---\n".join(
        f"[{c.get('document', 'unknown')}]\n{c.get('text', '')}" for c in chunks
    )
    history_context = _history_str(history) if history else ""

    prompt = f"""
You are an analyst with access to a company knowledge graph.

## Skill guidance
{_SKILL}

{f"Conversation so far:{chr(10)}{history_context}{chr(10)}" if history_context else ""}
Question: {question}
{f"(Interpreted as: {standalone})" if standalone != question else ""}

Data map — which source tables and key columns hold each kind of entity:
{data_map or '(nothing ingested yet)'}

Entities matched in the question:
{entity_context or '(none found)'}

Facts from the company's records (authoritative). Each line is a chain of linked facts, up to
{MAX_HOPS} steps from the entities above. Use these for who ordered, supplied, stocked or placed what:
{graph_context or '(none found)'}

Report excerpts (narrative; they describe events and may mention people or orders in other contexts).
If a report links someone or something to the item but the records above do not, answer from the
records and then add one sentence about the difference, e.g. "A maintenance report also says Bob
Okafor received one under order ORD-20240115, but the order records list that order as a Phone Max.":
{doc_context or '(none found)'}

Write the answer now: plain English, short, no brackets, no arrows, no typed ids (see the skill
guidance). The app lists the sources under your answer, so do not cite them inline and do not add
a "Sources" list. Start directly with the answer — no "Here is the answer" or "Based on…".
"""
    answer = plain_answer(provider.generate_text(prompt))
    for asked in (question, standalone):   # small models sometimes repeat the question first
        if asked and answer.lower().startswith(asked.strip().lower()):
            answer = answer[len(asked.strip()):].strip()

    return {
        "answer": answer,
        # only when a follow-up was actually rewritten, so the UI doesn't echo every question back
        "standalone_question": standalone if standalone.strip() != question.strip() else None,
        "sources": _sources_by_document(chunks),
        "entities_used": [e["label"] or e["id"] for e in entity_hits[:5]],
        "relationships_used": len(edges),
    }
