"""Vector search over DocumentChunks and mention-based search over Entities, scoped to one org."""
from __future__ import annotations

import re

from neo4j import GraphDatabase

from ..llm import get_provider
from ..graph.relationships import normalise_key

# ID-like tokens: WH-EAST, LP-4471, ORD-20240115, MNT-2024-001, SUP_001
_ID_TOKEN_RE = re.compile(r"\b[A-Za-z]{1,6}[-_][A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*\b|\b[A-Z]{2,}\d+[A-Z0-9]*\b")

_STOPWORDS = {
    "a", "an", "and", "any", "are", "at", "be", "by", "did", "do", "does", "for", "from", "had", "has",
    "have", "how", "in", "is", "it", "its", "many", "me", "of", "on", "or", "show", "that", "the",
    "their", "them", "these", "this", "those", "to", "was", "were", "what", "when", "where", "which",
    "who", "whom", "why", "with", "list", "all", "give", "tell", "about",
}


def vector_search(driver: GraphDatabase.driver, org_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Embed query and run Neo4j vector index search over this org's DocumentChunk nodes."""
    provider = get_provider()
    embedding = provider.embed(query)

    with driver.session() as session:
        # the vector index is shared across orgs, so over-fetch and filter to this org
        result = session.run(
            """
            CALL db.index.vector.queryNodes('chunk_embedding', $fetch, $embedding)
            YIELD node AS chunk, score
            WHERE chunk.org_id = $org
            OPTIONAL MATCH (d:Document {org_id: $org})-[:HAS_CHUNK]->(chunk)
            RETURN chunk.text AS text,
                   chunk.chunk_index AS chunk_index,
                   d.name AS document,
                   d.path AS path,
                   score
            ORDER BY score DESC
            LIMIT $k
            """,
            fetch=top_k * 10,
            k=top_k,
            embedding=embedding,
            org=org_id,
        )
        return [dict(r) for r in result]


def extract_mentions(text: str) -> list[str]:
    """Candidate entity mentions in free text: ID-like tokens plus remaining content words."""
    ids = _ID_TOKEN_RE.findall(text)
    rest = _ID_TOKEN_RE.sub(" ", text)
    words = [w for w in re.findall(r"[A-Za-z0-9]+", rest) if len(w) >= 3 and w.lower() not in _STOPWORDS]
    seen, out = set(), []
    for m in ids + words:
        if m.lower() not in seen:
            seen.add(m.lower())
            out.append(m)
    return out


def find_entities(driver: GraphDatabase.driver, org_id: str, mentions: list[str], top_k: int = 10) -> list[dict]:
    """
    Match each mention against entity ids, labels and source key values (normalised, so
    'wh east', 'WH-EAST' and 'wh_east' all hit warehouse:WH-EAST). Exact key matches rank first.
    """
    terms = [normalise_key(m) for m in mentions if len(normalise_key(m)) >= 3]
    if not terms:
        return []
    with driver.session() as session:
        result = session.run(
            """
            UNWIND $terms AS term
            MATCH (e:Entity {org_id: $org})
            WITH e, term,
                 [t IN coalesce(e.match_terms, []) + [e.canonical_label, split(e.canonical_id, ':')[-1]] |
                    replace(replace(replace(toLower(t), '-', ''), '_', ''), ' ', '')] AS keys,
                 replace(replace(replace(toLower(coalesce(e.canonical_label, '')), '-', ''), '_', ''), ' ', '') AS lbl
            // exact key/label match, or a word inside a label ("laptop" → "Laptop Pro 14")
            WHERE term IN keys OR (size(term) >= 4 AND lbl CONTAINS term)
            WITH e, max(CASE WHEN term IN keys THEN 2 ELSE 1 END) AS rank
            RETURN e.canonical_id AS id,
                   e.canonical_label AS label,
                   [l IN labels(e) WHERE l <> 'Entity'] AS classes,
                   e.status AS status,
                   e.confidence AS confidence,
                   rank
            ORDER BY rank DESC, confidence DESC
            LIMIT $k
            """,
            terms=terms,
            org=org_id,
            k=top_k,
        )
        return [dict(r) for r in result]


def entity_search(driver: GraphDatabase.driver, org_id: str, query: str, top_k: int = 10) -> list[dict]:
    """Search entities by the mentions in a free-text query (not the whole query as one substring)."""
    return find_entities(driver, org_id, extract_mentions(query), top_k=top_k)
