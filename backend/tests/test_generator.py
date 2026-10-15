import app.ontology.generator as generator
import app.ontology.taxonomy as taxonomy

SCHEMA = [{"source": "postgres", "schema": {
    "products": [{"column": "product_id"}, {"column": "category"}],
    "orders": [{"column": "order_id"}],
    "invoices": [{"column": "invoice_id"}, {"column": "order_id"}],
    "payments": [{"column": "invoice_id"}],
}, "samples": {}}]

# what a local 8B model actually proposed, plus one class the schemas really support
PROPOSAL = {
    "classes": [
        {"name": "ProductVariant", "source_hints": ["postgres.products.product_id", "dynamo.product_inventory.product_sku"]},
        {"name": "ProductFamily", "source_hints": ["postgres.products.category", "dynamo.product_inventory.product_family"]},
        {"name": "OrderSummary", "source_hints": ["postgres.orders.order_id", "dynamo.billing_events.order_ref"]},
        {"name": "Invoice", "source_hints": ["postgres.invoices.invoice_id", "postgres.payments.invoice_id"]},
    ],
    "relationships": [
        {"from": "Customer", "name": "PLACED_BY", "to": "Order"},       # reverse duplicate of PLACED
        {"from": "Order", "name": "FOLLOWS", "to": "OrderSummary"},     # endpoint rejected
        {"from": "Invoice", "name": "BILLS", "to": "Order"},
    ],
}


class Fake:
    def generate_structured(self, prompt, schema):
        return PROPOSAL


def test_only_evidence_backed_classes_and_new_links_survive(monkeypatch, tmp_path):
    monkeypatch.setattr(generator, "get_provider", lambda: Fake())
    monkeypatch.setattr(taxonomy, "org_dir", lambda org_id: tmp_path)
    onto = generator.generate_ontology(SCHEMA, "example")

    added = {c["name"] for c in onto["classes"]} - {c["name"] for c in taxonomy.load()["classes"]}
    assert added == {"Invoice"}
    rels = {(r["from"], taxonomy.rel_name(r), r["to"]) for r in onto["relationships"]}
    assert ("Invoice", "BILLS", "Order") in rels
    assert ("Customer", "PLACED_BY", "Order") not in rels
    assert not any("OrderSummary" in r for r in rels)
