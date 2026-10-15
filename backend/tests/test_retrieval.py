from app.retrieval.cypher_access import _unscoped_node_patterns
from app.retrieval.search import extract_mentions


def test_mentions_pull_ids_out_of_a_question():
    m = extract_mentions("Which products had defects at WH-EAST?")
    assert "WH-EAST" in m
    assert "Which" not in m and "at" not in m
    assert "products" in m and "defects" in m


def test_mentions_multiple_ids_and_names():
    m = extract_mentions("Did order ORD-20240115 for Bob Okafor include LP-4471 or MNT-2024-001?")
    for token in ["ORD-20240115", "LP-4471", "MNT-2024-001", "Bob", "Okafor"]:
        assert token in m


def test_cypher_guard_accepts_scoped_queries():
    q = ("MATCH (c:Customer {org_id: $org_id})-[:PLACED]->(o:Order {org_id: $org_id}) "
         "WHERE toLower(c.canonical_label) = 'bob' WITH c, count(o) AS n "
         "MATCH (c)-[:PLACED]->(o2:Order {org_id: $org_id}) RETURN c, n, collect(o2) LIMIT 10")
    assert not _unscoped_node_patterns(q)


def test_cypher_guard_rejects_unscoped_queries():
    assert _unscoped_node_patterns("MATCH (p:Product) RETURN p LIMIT 5")
    assert _unscoped_node_patterns("MATCH (p:Product {org_id: $org_id})-[:SUPPLIED_BY]->(s:Supplier) RETURN s")
    assert _unscoped_node_patterns("MATCH ()-[r]->() RETURN r LIMIT 5")
    assert _unscoped_node_patterns("MATCH (a:Product {org_id: $org_id}), (b) RETURN b")
    assert _unscoped_node_patterns("MATCH (p:Product {org_id: 'other'}) RETURN p")


def test_plain_answer_strips_citation_markup():
    from app.retrieval.investigate import plain_answer
    raw = ("The products with defects at WH-EAST are Laptop Pro 14 (product:LP-4471) "
           "[graph: Laptop Pro 14 (product:LP-4471) -[STOCKED_AT]-> WH-EAST (warehouse:WH-EAST)], "
           "which has 4 defective units. The supplier is SUP-001 [graph: Laptop Pro 14 -[SUPPLIED_BY]-> SUP-001]. "
           "[doc: report_003.txt] and [doc: report_001.txt] both support this answer.")
    out = plain_answer(raw)
    assert out == ("The products with defects at WH-EAST are Laptop Pro 14 (LP-4471), which has 4 defective units. "
                   "The supplier is SUP-001.")


def test_plain_answer_leaves_normal_text_alone():
    from app.retrieval.investigate import plain_answer
    text = "Join orders and order_items on order_id (both in Postgres)."
    assert plain_answer(text) == text


def test_plain_answer_drops_sources_list_and_lead_in():
    from app.retrieval.investigate import plain_answer
    raw = ("Here is the answer: The Laptop Pro 14 (LP-4471) had defects at the East warehouse (WH-EAST). "
           "It is supplied by SUP-001. Sources: - Supplier quality review report SQR-2024-001 - Maintenance report")
    assert plain_answer(raw) == ("The Laptop Pro 14 (LP-4471) had defects at the East warehouse (WH-EAST). "
                                 "It is supplied by SUP-001.")
    assert plain_answer("Based on the graph relationships and document excerpts, the supplier is SUP-001.") \
        == "The supplier is SUP-001."
