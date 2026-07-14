# Skill: Cypher Generation

## Purpose
Translate natural language questions into read-only Neo4j Cypher queries against
the company knowledge graph. Queries are executed live — incorrect property names
or reversed relationship directions return empty results with no error.

## Graph schema

Every node carries `:Entity` plus one class label from the ontology.

**Properties on all Entity nodes:**
- `canonical_id` (string) — primary key, format `<class_lower>:<value>`
- `canonical_label` (string) — human-readable name
- `class` (string) — ontology class name
- `confidence` (float)
- `status` (string: auto_commit | needs_review | unresolved)

**Relationship types and FIXED directions (never reverse these):**
```
(Customer)-[:PLACED]->(Order)
(Order)-[:CONTAINS]->(Product)
(Order)-[:FULFILLED_BY]->(Shipment)
(Product)-[:STOCKED_AT]->(Warehouse)
(Product)-[:SUPPLIED_BY]->(Supplier)
(MaintenanceIncident)-[:AFFECTS]->(Product)
(MaintenanceIncident)-[:LOCATED_AT]->(Warehouse)
(Entity)-[:MENTIONED_IN]->(DocumentChunk)
```

## Rules

1. **Always include LIMIT**: Every MATCH clause that returns nodes must end with
   `LIMIT 50` unless the question requests a count or aggregate.

2. **Case-insensitive string matching**: Use
   `toLower(e.canonical_label) = toLower($value)` for label comparisons.
   Use `e.canonical_id = $id` for ID lookups (IDs are already normalised).
   Never use bare `=` on `canonical_label`.

3. **Use canonical_id for ID lookups**: When the question contains an ID-like
   string (LP-4471, ORD-9981, CUST-0042), match on `canonical_id`, not
   `canonical_label`.

4. **Relationship direction is fixed**: Never reverse the directions above.
   To find what a customer ordered:
   `MATCH (c:Customer)-[:PLACED]->(o:Order)`
   Never write `(o:Order)-[:PLACED]->(c:Customer)`.

5. **Read-only only**: Never emit CREATE, MERGE, SET, DELETE, REMOVE, or DROP.

6. **Return named properties**: Always return `e.canonical_label` and
   `e.canonical_id` so results are self-describing. Never return a raw node
   object like `RETURN e`.

7. **explanation field**: The explanation must be one sentence describing what
   the query returns, written for a business analyst, not a developer.
   Good: "Returns all orders placed by customers in the North region."
   Bad: "Matches Order nodes via PLACED edges from Customer nodes."

## Output contract
Return only valid JSON with exactly two keys: `cypher` (string) and
`explanation` (string). No markdown fences. No prose outside the JSON.

## Good example
```json
{
  "cypher": "MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product) WHERE p.canonical_id = 'product:LP-4471' RETURN c.canonical_label AS customer, o.canonical_id AS order_id LIMIT 50",
  "explanation": "Returns all customers who placed orders containing the Laptop Pro 14 product."
}
```

## Anti-patterns
- ❌ `MATCH (p:Product) WHERE p.name = "Laptop Pro"` — `name` does not exist; use `canonical_label`
- ❌ `MATCH (o:Order)-[:PLACED]->(c:Customer)` — direction is reversed
- ❌ No LIMIT clause on a node traversal
- ❌ `RETURN e` — returns a raw node object; return named properties instead
- ❌ `explanation: "Matches nodes via Cypher pattern."` — describes syntax, not result
