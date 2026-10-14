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

from pathlib import Path

from neo4j import GraphDatabase

from ..llm import get_provider
from .search import extract_mentions, find_entities, vector_search

_SKILL = (Path(__file__).parent.parent.parent.parent / "skills" / "investigation_rag.md").read_text()

MAX_HOPS = 2
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

Rewrite the follow-up as a standalone question that can be understood without the conversation,
replacing pronouns and references like "those products" or "that warehouse" with the specific
entity names and ids from the conversation. Also list every entity name or id the standalone
question refers to (e.g. "LP-4471", "WH-EAST", "Laptop Pro 14").
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


def _traverse(session, org_id: str, canonical_ids: list[str], limit: int = 60) -> list[dict]:
    """Distinct entity-to-entity edges within MAX_HOPS of the seed entities, in either direction."""
    return session.run(
        f"""
        MATCH (e:Entity {{org_id: $org}}) WHERE e.canonical_id IN $cids
        MATCH (e)-[rels*1..{MAX_HOPS}]-(:Entity {{org_id: $org}})
        WHERE none(r IN rels WHERE type(r) = 'MENTIONED_IN')
        UNWIND rels AS r
        WITH DISTINCT r
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
    if seed_ids:
        with driver.session() as session:
            edges = _traverse(session, org_id, seed_ids)
            graph_chunks = _mentioning_chunks(session, org_id, seed_ids)

    vector_chunks = vector_search(driver, org_id, standalone, top_k=6)

    chunks: list[dict] = []
    seen = set()
    for c in graph_chunks + vector_chunks:
        key = (c.get("path"), c.get("text"))
        if key not in seen:
            seen.add(key)
            chunks.append(c)

    graph_context = "\n".join(
        f"{e['src_label']} ({e['src']}) -[{e['rel']}]-> {e['tgt_label']} ({e['tgt']})" for e in edges
    )
    entity_context = "\n".join(
        f"- {e['label']} ({e['id']}) [{', '.join(e.get('classes') or [])}]" for e in entity_hits[:5]
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

Entities matched in the question:
{entity_context or '(none found)'}

Graph relationships (up to {MAX_HOPS} hops from those entities):
{graph_context or '(none found)'}

Document excerpts:
{doc_context or '(none found)'}

Answer the question concisely and accurately based on the above context.
If the context does not contain enough information, say so.
"""
    answer = provider.generate_text(prompt).strip()

    return {
        "answer": answer,
        "standalone_question": standalone,
        "sources": [
            {"document": c.get("document"), "path": c.get("path"), "score": c.get("score")}
            for c in chunks
        ],
        "entities_used": [e["label"] or e["id"] for e in entity_hits[:5]],
        "relationships_used": len(edges),
    }
