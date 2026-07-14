"""Embeds text chunks and stores them in Neo4j with a vector index."""
from __future__ import annotations

from neo4j import GraphDatabase

from ..llm import get_provider


def embed_and_store(driver: GraphDatabase.driver, doc: dict, chunks: list[str]) -> None:
    """
    For each chunk:
      1. Embed via LLM provider.
      2. Create a DocumentChunk node in Neo4j with the embedding.
      3. Link it to its parent Document node (create if absent).
    """
    provider = get_provider()
    with driver.session() as session:
        session.run(
            "MERGE (d:Document {path: $path}) "
            "SET d.name = $name, d.source = 'file'",
            path=doc["path"],
            name=doc["name"],
        )
        for i, chunk in enumerate(chunks):
            embedding = provider.embed(chunk)
            session.run(
                """
                MATCH (d:Document {path: $path})
                CREATE (c:DocumentChunk {
                    chunk_index: $idx,
                    text: $text,
                    embedding: $embedding,
                    doc_path: $path
                })
                CREATE (d)-[:HAS_CHUNK]->(c)
                """,
                path=doc["path"],
                idx=i,
                text=chunk,
                embedding=embedding,
            )
