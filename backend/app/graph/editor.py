"""Write-back operations for graph editing from the UI."""
from __future__ import annotations

from neo4j import GraphDatabase


def update_entity(driver, canonical_id: str, label: str | None, class_name: str | None, status: str | None) -> dict:
    updates = []
    params: dict = {"cid": canonical_id}
    if label is not None:
        updates.append("e.canonical_label = $label")
        params["label"] = label
    if class_name is not None:
        updates.append("e.class = $class_name")
        params["class_name"] = class_name
    if status is not None:
        updates.append("e.status = $status")
        params["status"] = status
    if not updates:
        return {"ok": True}
    with driver.session() as session:
        session.run(
            f"MATCH (e:Entity {{canonical_id: $cid}}) SET {', '.join(updates)}",
            **params,
        )
    return {"ok": True}


def remove_entity(driver, canonical_id: str) -> dict:
    with driver.session() as session:
        session.run(
            "MATCH (e:Entity {canonical_id: $cid}) DETACH DELETE e",
            cid=canonical_id,
        )
    return {"ok": True}


def update_relationship(driver, source_id: str, target_id: str, old_type: str, new_type: str) -> dict:
    with driver.session() as session:
        # Neo4j cannot rename relationship types — delete old, create new
        session.run(
            f"""
            MATCH (a:Entity {{canonical_id: $src}})-[r:{old_type}]->(b:Entity {{canonical_id: $tgt}})
            DELETE r
            WITH a, b
            CALL apoc.create.relationship(a, $new_type, {{}}, b) YIELD rel
            RETURN rel
            """,
            src=source_id,
            tgt=target_id,
            new_type=new_type,
        )
    return {"ok": True}


def remove_relationship(driver, source_id: str, target_id: str, rel_type: str) -> dict:
    with driver.session() as session:
        session.run(
            f"""
            MATCH (a:Entity {{canonical_id: $src}})-[r:{rel_type}]->(b:Entity {{canonical_id: $tgt}})
            DELETE r
            """,
            src=source_id,
            tgt=target_id,
        )
    return {"ok": True}


def approve_entity(driver, canonical_id: str) -> dict:
    with driver.session() as session:
        session.run(
            "MATCH (e:Entity {canonical_id: $cid}) SET e.status = 'auto_commit'",
            cid=canonical_id,
        )
    return {"ok": True}


def reject_entity(driver, canonical_id: str) -> dict:
    return remove_entity(driver, canonical_id)


def split_entity(driver, canonical_id: str, entity_a: dict, entity_b: dict) -> dict:
    """
    Split one entity into two. entity_a and entity_b each have:
      canonical_id, canonical_label, class, sources (list of source dicts to assign)
    """
    with driver.session() as session:
        session.run(
            "MATCH (e:Entity {canonical_id: $cid}) DETACH DELETE e",
            cid=canonical_id,
        )
        for ent in [entity_a, entity_b]:
            session.run(
                f"""
                MERGE (e:Entity:{ent['class']} {{canonical_id: $cid}})
                SET e.canonical_label = $label,
                    e.status = 'auto_commit',
                    e.confidence = 1.0,
                    e.sources = $sources
                """,
                cid=ent["canonical_id"],
                label=ent["canonical_label"],
                sources=str(ent.get("sources", [])),
            )
    return {"ok": True, "created": [entity_a["canonical_id"], entity_b["canonical_id"]]}
