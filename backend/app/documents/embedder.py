"""Embeds text chunks and stores them in Neo4j with a vector index."""
from __future__ import annotations

from neo4j import GraphDatabase

from ..llm import get_provider


def embed_and_store(driver: GraphDatabase.driver, org_id: str, doc: dict, chunks: list[str]) -> None:
    """
    For each chunk:
      1. Embed via LLM provider.
      2. Create a DocumentChunk node in Neo4j with the embedding.
      3. Link it to its parent Document node (create if absent).
    Re-ingesting a document replaces its previous chunks rather than duplicating them.
    """
    provider = get_provider()
    with driver.session() as session:
        session.run(
            "MERGE (d:Document {org_id: $org, path: $path}) "
            "SET d.name = $name, d.source = 'file' "
            "WITH d OPTIONAL MATCH (d)-[:HAS_CHUNK]->(old:DocumentChunk) DETACH DELETE old",
            org=org_id,
            path=doc["path"],
            name=doc["name"],
        )
        for i, chunk in enumerate(chunks):
            embedding = provider.embed(chunk)
            session.run(
                """
                MATCH (d:Document {org_id: $org, path: $path})
                CREATE (c:DocumentChunk {
                    chunk_index: $idx,
                    text: $text,
                    embedding: $embedding,
                    doc_path: $path,
                    org_id: $org
                })
                CREATE (d)-[:HAS_CHUNK]->(c)
                """,
                org=org_id,
                path=doc["path"],
                idx=i,
                text=chunk,
                embedding=embedding,
            )
