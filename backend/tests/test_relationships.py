from app.graph.relationships import build_relationships, normalise_key, safe_ident
from app.ontology.taxonomy import load

ONTOLOGY = load()


def _e(cid, cls, table, col, key, conf=0.95):
    return {"canonical_id": cid, "canonical_label": key, "class": cls, "confidence": conf,
            "sources": [{"source_type": "postgres", "table_or_datasource": table, "key_column": col, "key_value": key}]}


ENTITIES = [
    _e("customer:CUST-001", "Customer", "customers", "customer_id", "CUST-001"),
    _e("order:ORD-20240101", "Order", "orders", "order_id", "ORD-20240101"),
    _e("product:LP-4471", "Product", "products", "product_id", "LP-4471"),
    _e("warehouse:WH-EAST", "Warehouse", "inventory", "warehouse_id", "WH-EAST", conf=0.7),
    _e("supplier:SUP-001", "Supplier", "products", "supplier_id", "SUP-001"),
]

SCHEMA_DATA = [{
    "source": "postgres",
    "schema": {},
    "samples": {
        "orders": [{"order_id": "ORD-20240101", "customer_id": "CUST-001", "status": "delivered", "region": "West"}],
        "order_items": [{"order_id": "ORD-20240101", "product_id": "LP-4471", "quantity": 1}],
        "inventory": [{"product_id": "LP-4471", "warehouse_id": "WH-EAST", "qty_on_hand": 12}],
        "products": [{"product_id": "LP-4471", "name": "Laptop Pro 14", "supplier_id": "SUP-001"}],
    },
}, {
    # druid stores the sku without a hyphen — must still link
    "source": "druid",
    "samples": {"inventory_events": [{"sku_code": "LP4471", "warehouse": "wh_east"}]},
}]


def _triples(rels):
    return {(r["from_id"], r["type"], r["to_id"]) for r in rels}


def test_foreign_keys_in_rows_become_ontology_edges():
    triples = _triples(build_relationships(ENTITIES, SCHEMA_DATA, ONTOLOGY))
    assert ("customer:CUST-001", "PLACED", "order:ORD-20240101") in triples
    assert ("order:ORD-20240101", "CONTAINS", "product:LP-4471") in triples
    assert ("product:LP-4471", "STOCKED_AT", "warehouse:WH-EAST") in triples
    assert ("product:LP-4471", "SUPPLIED_BY", "supplier:SUP-001") in triples
    # never the reverse direction
    assert ("order:ORD-20240101", "PLACED", "customer:CUST-001") not in triples


def test_edge_confidence_is_weakest_endpoint():
    rels = build_relationships(ENTITIES, SCHEMA_DATA, ONTOLOGY)
    stocked = next(r for r in rels if r["type"] == "STOCKED_AT")
    assert stocked["confidence"] == 0.7


def test_proposed_relationships_are_validated_against_ontology():
    entities = ENTITIES + [{"canonical_id": "maintenanceincident:MNT-2024-001", "class": "MaintenanceIncident",
                            "confidence": 0.9, "sources": []}]
    proposed = [
        {"from_id": "maintenanceincident:MNT-2024-001", "type": "AFFECTS", "to_id": "product:LP-4471"},
        {"from_id": "maintenanceincident:MNT-2024-001", "type": "LOCATED_AT", "to_id": "warehouse:WH-EAST"},
        {"from_id": "product:LP-4471", "type": "AFFECTS", "to_id": "maintenanceincident:MNT-2024-001"},  # reversed
        {"from_id": "maintenanceincident:MNT-2024-001", "type": "AFFECTS", "to_id": "product:XX-0000"},  # unknown
        {"from_id": "product:LP-4471", "type": "OWNS", "to_id": "supplier:SUP-001"},  # not in ontology
    ]
    triples = _triples(build_relationships(entities, [], ONTOLOGY, proposed))
    assert triples == {
        ("maintenanceincident:MNT-2024-001", "AFFECTS", "product:LP-4471"),
        ("maintenanceincident:MNT-2024-001", "LOCATED_AT", "warehouse:WH-EAST"),
    }


def test_short_values_do_not_create_edges():
    ents = [_e("customer:1", "Customer", "customers", "id", "1"), _e("order:2", "Order", "orders", "id", "2")]
    data = [{"source": "postgres", "samples": {"orders": [{"id": "2", "customer_id": "1"}]}}]
    assert build_relationships(ents, data, ONTOLOGY) == []


def test_helpers():
    assert normalise_key("LP-4471") == normalise_key("lp_4471") == normalise_key(" LP4471 ")
    assert safe_ident("Product`) DETACH DELETE (n", "X") == "ProductDETACHDELETEn"
    assert safe_ident("", "Unclassified") == "Unclassified"
    assert safe_ident("9Lives", "X") == "X"
