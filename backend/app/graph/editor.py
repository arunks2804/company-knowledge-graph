"""Write-back operations for graph editing from the UI."""
from __future__ import annotations

import json

from neo4j import GraphDatabase

from .relationships import safe_ident


def update_entity(driver, org_id: str, canonical_id: str, label: str | None, class_name: str | None, status: str | None) -> dict:
    updates = []
    params: dict = {"cid": canonical_id, "org": org_id}
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
            f"MATCH (e:Entity {{org_id: $org, canonical_id: $cid}}) SET {', '.join(updates)}",
            **params,
        )
    return {"ok": True}


def remove_entity(driver, org_id: str, canonical_id: str) -> dict:
    with driver.session() as session:
        session.run(
            "MATCH (e:Entity {org_id: $org, canonical_id: $cid}) DETACH DELETE e",
            cid=canonical_id,
            org=org_id,
        )
    return {"ok": True}


def update_relationship(driver, org_id: str, source_id: str, target_id: str, old_type: str, new_type: str) -> dict:
    old_type = safe_ident(old_type, "RELATED_TO")
    new_type = safe_ident(new_type, "RELATED_TO")
    with driver.session() as session:
        # Neo4j cannot rename relationship types — delete old, create new
        session.run(
            f"""
            MATCH (a:Entity {{org_id: $org, canonical_id: $src}})-[r:{old_type}]->(b:Entity {{org_id: $org, canonical_id: $tgt}})
            DELETE r
            WITH a, b
            CALL apoc.create.relationship(a, $new_type, {{}}, b) YIELD rel
            RETURN rel
            """,
            org=org_id,
            src=source_id,
            tgt=target_id,
            new_type=new_type,
        )
    return {"ok": True}


def remove_relationship(driver, org_id: str, source_id: str, target_id: str, rel_type: str) -> dict:
    rel_type = safe_ident(rel_type, "RELATED_TO")
    with driver.session() as session:
        session.run(
            f"""
            MATCH (a:Entity {{org_id: $org, canonical_id: $src}})-[r:{rel_type}]->(b:Entity {{org_id: $org, canonical_id: $tgt}})
            DELETE r
            """,
            org=org_id,
            src=source_id,
            tgt=target_id,
        )
    return {"ok": True}


def approve_entity(driver, org_id: str, canonical_id: str) -> dict:
    with driver.session() as session:
        session.run(
            "MATCH (e:Entity {org_id: $org, canonical_id: $cid}) SET e.status = 'auto_commit'",
            cid=canonical_id,
            org=org_id,
        )
    return {"ok": True}


def reject_entity(driver, org_id: str, canonical_id: str) -> dict:
    return remove_entity(driver, org_id, canonical_id)


def split_entity(driver, org_id: str, canonical_id: str, entity_a: dict, entity_b: dict) -> dict:
    """
    Split one entity into two. entity_a and entity_b each have:
      canonical_id, canonical_label, class, sources (list of source dicts to assign)
    """
    with driver.session() as session:
        session.run(
            "MATCH (e:Entity {org_id: $org, canonical_id: $cid}) DETACH DELETE e",
            cid=canonical_id,
            org=org_id,
        )
        for ent in [entity_a, entity_b]:
            label = safe_ident(ent.get("class", ""), "Unclassified")
            session.run(
                f"""
                MERGE (e:Entity {{org_id: $org, canonical_id: $cid}})
                SET e:{label},
                    e.class = $cls,
                    e.canonical_label = $label,
                    e.status = 'auto_commit',
                    e.confidence = 1.0,
                    e.sources = $sources
                """,
                org=org_id,
                cid=ent["canonical_id"],
                cls=label,
                label=ent["canonical_label"],
                sources=json.dumps(ent.get("sources", [])),
            )
    return {"ok": True, "created": [entity_a["canonical_id"], entity_b["canonical_id"]]}
