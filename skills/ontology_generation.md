# Skill: Ontology Generation

## Purpose
Guide the LLM to extend core_ontology.yaml with classes and relationships derived
from observed database schemas. The output is merged directly into the live ontology
and consumed by entity resolution — quality here propagates everywhere.

## Rules

1. **Minimum evidence**: Never propose a new class unless at least 2 distinct
   source_hints are observed (e.g. 2 different table names or 2 different column
   names that refer to the same concept). A class implied by only one column is noise.

2. **Naming convention**: Class names MUST be PascalCase singular nouns
   (Product, not products, not ProductItem, not product_item).
   Relationship names MUST be SCREAMING_SNAKE_CASE verbs in active voice
   (PLACED_BY, FULFILLED_BY). Never use gerunds (PLACING) or nouns (FULFILLMENT).

3. **source_hints format**: Each source_hint MUST be a string in the form
   `<connector>.<table_or_datasource>.<column>`, e.g.
   `postgres.products.product_id`, `druid.inventory_events.sku_code`,
   `dynamo.product_inventory.product_sku`.
   Do not use short-form like `product_id` alone.

4. **Extend, don't duplicate**: Before proposing a new class, check whether an
   existing seed class covers it. If the new concept is a sub-type of an existing
   class, add a `parent` field pointing to the existing class instead of creating a
   peer. Never create a class whose name is a synonym of an existing class.

5. **Description quality**: Every class description MUST answer three questions
   in one sentence: what is this thing, which systems track it, and what makes it
   distinct from neighbouring classes. Example:
   "A physical inventory count of a product SKU at a specific warehouse,
   tracked by Druid inventory_events and DynamoDB product_inventory,
   distinct from Product (which describes the SKU itself)."

6. **Relationship completeness**: For every relationship, `from`, `to`, and `name`
   are required. `description` must name the direction:
   "A Customer placed an Order" not "Customer and Order are linked".

7. **No deletions**: The output JSON must NOT omit any class or relationship from
   the seed. The merger logic preserves the seed, but do not output partial
   replacements that exclude existing entries.

## Output contract
Return only valid JSON. No markdown fences. No explanatory prose outside the JSON.
The top-level keys are exactly `classes` and `relationships`.

## Good example
```json
{
  "classes": [
    {
      "name": "Invoice",
      "description": "A billing record for an order issued to a customer, tracked in Postgres invoices table and referenced in DynamoDB billing_events, distinct from Order (which records the purchase intent).",
      "source_hints": ["postgres.invoices.invoice_id", "dynamo.billing_events.invoice_ref"]
    }
  ],
  "relationships": [
    {
      "from": "Order",
      "to": "Invoice",
      "name": "INVOICED_BY",
      "description": "An Order is invoiced by an Invoice."
    }
  ]
}
```

## Anti-patterns
- ❌ Class `ProductItem` when `Product` already exists
- ❌ source_hint `"product_id"` (missing connector and table prefix)
- ❌ Relationship `PRODUCT_WAREHOUSE` (noun, not a verb)
- ❌ Description: `"A product."` (answers nothing)
- ❌ New class with a single source_hint from one column
- ❌ Omitting existing seed classes from the output
