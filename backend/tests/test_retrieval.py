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
