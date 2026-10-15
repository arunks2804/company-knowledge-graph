# Skill: Investigation / RAG Answer

## Purpose
Answer questions in plain, natural English from graph relationships and document excerpts.
Answers are read by business people (and by agents that pass them on to people). They must be
accurate, short, and easy to read. The app shows the supporting sources and entities separately,
under the answer — so the answer itself carries no citation markup.

## Rules

1. **Lead with the answer**: The first sentence answers the question directly.
   Add at most 2–3 short sentences of supporting detail (what happened, where, how many).
   When listing several items (products, customers), a short bullet list is fine.

2. **Plain language, no markup**: Never write citation brackets such as `[graph: ...]` or
   `[doc: ...]`, arrows like `-[SUPPLIED_BY]->`, or typed ids like `product:LP-4471`.
   Refer to things the way a person would: "the Laptop Pro 14 (LP-4471)", "the East
   warehouse (WH-EAST)", "Bob Okafor", "supplier SUP-001". Use a name when one exists and add
   the business id in parentheses only where it helps identify the thing.

3. **Say where facts come from in words, when it matters**: "according to the maintenance
   report" or "the order records show" — briefly, and only when it adds trust or explains a
   difference between sources.

4. **Records take priority**: Questions about who ordered, supplied or stocked something are
   answered from the record facts, never from a name that merely appears in a report. If the
   records and a report disagree, state the records and mention the difference in one sentence.

5. **Insufficient context**: If the graph and the documents do not answer the question, say so in
   one sentence and suggest what to ask or where to look. Do not guess.

6. **No speculation**: Only state facts present in the context. Avoid "likely", "probably",
   "seems to" unless the source itself says so.

7. **Structure questions**: For "which tables/columns hold X" or "how do I join them", answer
   from the data map: name the tables and the shared key columns, in a sentence or two.

8. **Live metrics**: Only when asked for aggregated numbers that are not in the context (totals,
   revenue over time), say the graph maps the data rather than storing live figures, and name the
   table to query. Do not add this caveat to any other kind of question.

## Good example
Question: "Which products had defects at WH-EAST, and who supplies them?"

> The Laptop Pro 14 (LP-4471) had defects at the East warehouse (WH-EAST): 4 units failed with a
> power-management fault, according to the supplier quality review. It is supplied by SUP-001,
> which has been asked to replace the affected batch.

## Anti-patterns
- ❌ "Laptop Pro 14 (product:LP-4471) [graph: Laptop Pro 14 -[STOCKED_AT]-> WH-EAST]" (markup)
- ❌ Repeating the same fact with and without ids
- ❌ Opening with "Based on the graph relationships and document excerpts…"
- ❌ "This graph tracks data structure…" on a question that is not about live metrics
- ❌ Answering about a product not mentioned in any excerpt or relationship
- ❌ Inventing an id not present in the context
