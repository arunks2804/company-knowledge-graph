"""RAG-style investigation: find relevant chunks, build context, generate answer."""
from __future__ import annotations

from neo4j import GraphDatabase

from pathlib import Path

from ..llm import get_provider
from .search import vector_search, entity_search

_SKILL = (Path(__file__).parent.parent.parent.parent / "skills" / "investigation_rag.md").read_text()


def investigate(driver: GraphDatabase.driver, question: str) -> dict:
    """
    1. Find relevant document chunks via vector search.
    2. Find entities mentioned in the question.
    3. Fetch their graph neighbourhood.
    4. Ask the LLM to synthesise an answer.
    Returns {answer, sources, entities_used}.
    """
    chunks = vector_search(driver, question, top_k=6)
    entity_hits = entity_search(driver, question, top_k=5)

    # Fetch neighbourhood of found entities
    graph_context = ""
    entities_used = []
    if entity_hits:
        with driver.session() as session:
            for ent in entity_hits[:3]:
                r = session.run(
                    """
                    MATCH (e:Entity {canonical_id: $cid})
                    OPTIONAL MATCH (e)-[rel]->(other:Entity)
                    RETURN e.canonical_label AS label,
                           e.canonical_id AS id,
                           type(rel) AS rel_type,
                           other.canonical_label AS other_label
                    LIMIT 10
                    """,
                    cid=ent["id"],
                ).data()
                if r:
                    entities_used.append(ent["label"])
                    for row in r:
                        if row.get("rel_type"):
                            graph_context += (
                                f"{row['label']} -[{row['rel_type']}]-> {row['other_label']}\n"
                            )

    doc_context = "\n---\n".join(
        f"[{c.get('document', 'unknown')}]\n{c.get('text', '')}" for c in chunks
    )

    provider = get_provider()
    prompt = f"""
You are an analyst with access to a company knowledge graph.

## Skill guidance
{_SKILL}

Question: {question}

Graph relationships:
{graph_context or '(none found)'}

Document excerpts:
{doc_context or '(none found)'}

Answer the question concisely and accurately based on the above context.
If the context does not contain enough information, say so.
"""
    answer = provider.generate_text(prompt).strip()

    return {
        "answer": answer,
        "sources": [
            {"document": c.get("document"), "path": c.get("path"), "score": c.get("score")}
            for c in chunks
        ],
        "entities_used": entities_used,
    }
