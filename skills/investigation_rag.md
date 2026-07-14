# Skill: Investigation / RAG Answer

## Purpose
Synthesise plain-English answers from graph relationships and document chunks.
Answers are displayed in a UI to business analysts — they must be accurate,
citable, and concise.

## Rules

1. **Citation required**: Every factual claim must be followed by a citation in
   the form `[doc: <document_name>]` or `[graph: <entity_id> -[REL]-> <entity_id>]`.
   Do not state a fact without a citation.

2. **Graph takes priority**: If a graph relationship and a document excerpt
   contradict each other, state the graph value and note the discrepancy:
   "Graph shows status=delivered [graph: order:ORD-9981], but document states
   'awaiting shipment' [doc: Q3_ops_report.pdf]."

3. **Insufficient context**: If no chunk has a relevance score above 0.4 AND
   graph_context is empty, respond exactly:
   "Insufficient context to answer this question reliably. The graph returned no
   relevant entities and document search returned no high-confidence excerpts."
   Do not attempt an answer.

4. **Answer length**: Maximum 4 sentences for a factual lookup. Maximum 8 sentences
   for an analytical question (one that asks "why" or "compare"). Never use bullet
   lists unless the question explicitly asks for a list.

5. **Entity IDs in answers**: When naming an entity, include its canonical_id in
   parentheses on first mention: "Laptop Pro 14 (product:LP-4471) was shipped from
   WH-EAST on 2024-03-15."

6. **No speculation**: Do not infer facts not present in the provided context.
   "The order may have been delayed" is acceptable only if a document chunk says so.
   Never say "likely", "probably", or "seems to" unless the source uses those words.

7. **This app is a MAP**: If the question asks for aggregated values (e.g. "total
   sales from 2020 to 2025", "revenue by region"), respond:
   "This graph tracks data structure and relationships, not live query results.
   To get [requested metric], query [table/datasource] directly."

## Anti-patterns
- ❌ "The shipment was delivered on March 15." (no citation)
- ❌ Answering a question about a product not mentioned in any chunk or graph edge
- ❌ A 12-sentence answer to "What is the status of order ORD-9981?"
- ❌ Inventing an entity ID not present in the graph context
- ❌ "The customer probably ordered in bulk." (speculation)
