# Skill: Entity Resolution

## Purpose
Match records across Postgres, Druid, DynamoDB, Iceberg, TimescaleDB, and documents
to single canonical graph nodes. Confidence scores gate auto-commit vs human review —
calibrate them precisely. Under-merging is safer than over-merging.

## Rules

1. **Confidence calibration**:
   - 0.95–1.0: Exact ID match across 3+ sources with matching name.
   - 0.85–0.94: Exact ID match across 2 sources, or 3+ sources with ID normalisation
     only (hyphen removal, case fold).
   - 0.70–0.84: ID match in 2 sources but name differs; or ID match in 1 source +
     document mention with same text.
   - 0.50–0.69: Only one structured source matches; document mention is supporting
     evidence only.
   - Below 0.50: Only a document mention, or name similarity only with no ID overlap.
   Never assign confidence >= 0.85 when only one structured source is matched.

2. **canonical_id format**: MUST follow `<class_lower>:<primary_key_value>` using
   the Postgres primary key as the authority. Example: `product:LP-4471`,
   `customer:CUST-0042`, `order:ORD-9981`. If Postgres is absent, use
   `<class_lower>:<source_abbrev>-<key>`, e.g. `product:druid-LP4471`.

3. **canonical_label selection**: Prefer the Postgres `name` column. If absent,
   prefer DynamoDB. If absent, prefer Druid. Never invent a name not present in
   any source.

4. **ID normalisation**: When comparing IDs across sources, normalise by:
   lowercasing, stripping hyphens and underscores, trimming whitespace.
   `LP-4471`, `lp4471`, `LP_4471` are all the same. State the normalisation applied
   in a `match_notes` field on each entity.

5. **Do not over-merge**: Two records with similar names but no shared ID or
   document co-mention must NOT be merged. Assign each `status: unresolved`.

6. **Unresolved is valid**: It is correct to leave records unresolved. Do not
   force a match to hit a quota. Unresolved records are human-reviewed downstream.

7. **class field**: Must be an exact class name from the ontology provided.
   Never invent a class not in the list.

8. **sources field**: Must be a JSON array of objects, each with keys:
   `source_type`, `table_or_datasource`, `key_column`, `key_value`.

## Output contract
Return valid JSON with a single top-level key `entities` containing an array of entity objects:
`{"entities": [...]}`. Do NOT return a bare array. Each object must include:
`canonical_id`, `canonical_label`, `class`, `confidence` (float 0–1), `sources` (array),
`status` (auto_commit | needs_review | unresolved), `match_notes` (string).
No markdown fences. No extra keys at the top level.

## Good example
```json
{
  "entities": [
    {
      "canonical_id": "product:LP-4471",
      "canonical_label": "Laptop Pro 14",
      "class": "Product",
      "confidence": 0.97,
      "sources": [
        {"source_type": "postgres", "table_or_datasource": "products", "key_column": "product_id", "key_value": "LP-4471"},
        {"source_type": "dynamodb", "table_or_datasource": "product_inventory", "key_column": "product_sku", "key_value": "LP-4471"},
        {"source_type": "druid", "table_or_datasource": "inventory_events", "key_column": "sku_code", "key_value": "LP4471"}
      ],
      "status": "auto_commit",
      "match_notes": "Exact match across postgres and dynamo; druid normalised LP4471→LP-4471 by adding hyphen."
    }
  ]
}
```

## Anti-patterns
- ❌ `confidence: 0.9` when only one Druid row matched
- ❌ `canonical_id: "LP4471"` (missing class prefix)
- ❌ `canonical_label: "Laptop Pro Model X"` invented by the LLM
- ❌ Merging two customers because both are in the same region
- ❌ Omitting `match_notes`
