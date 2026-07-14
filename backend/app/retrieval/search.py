"""Vector and keyword search over DocumentChunks in Neo4j."""
from __future__ import annotations

from neo4j import GraphDatabase

from ..llm import get_provider


def vector_search(driver: GraphDatabase.driver, query: str, top_k: int = 5) -> list[dict]:
    """Embed query and run Neo4j vector index search over DocumentChunk nodes."""
    provider = get_provider()
    embedding = provider.embed(query)

    with driver.session() as session:
        result = session.run(
            """
            CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding)
            YIELD node AS chunk, score
            OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(chunk)
            RETURN chunk.text AS text,
                   chunk.chunk_index AS chunk_index,
                   d.name AS document,
                   d.path AS path,
                   score
            ORDER BY score DESC
            """,
            k=top_k,
            embedding=embedding,
        )
        return [dict(r) for r in result]


def entity_search(driver: GraphDatabase.driver, query: str, top_k: int = 10) -> list[dict]:
    """Full-text search over entity canonical labels."""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (e:Entity)
            WHERE toLower(e.canonical_label) CONTAINS toLower($q)
               OR toLower(e.canonical_id) CONTAINS toLower($q)
            RETURN e.canonical_id AS id,
                   e.canonical_label AS label,
                   labels(e) AS classes,
                   e.status AS status,
                   e.confidence AS confidence
            LIMIT $k
            """,
            q=query,
            k=top_k,
        )
        return [dict(r) for r in result]
