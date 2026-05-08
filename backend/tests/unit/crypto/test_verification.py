"""
Unit tests for app.crypto.verification — the trust model.

These tests exercise verify_global, verify_local, and the helpers that
reconstruct the ideal graph and reconcile it against published data.
"""

import copy

import pytest

from app.crypto.graph import determine_neighbors
from app.crypto.verification import (
    GraphDiscrepancies,
    _build_published_edge_index,
    _check_edge_symmetry,
    _check_node_consistency,
    _edge_should_exist,
    _reconcile_graph,
    _reconstruct_ideal_graph,
    verify_global,
    verify_local,
)

from tests.fixtures import STABLE_NODE_IDS, build_published_results


def _find_absent_pair(node_ids, p):
    """Return some (a, b) such that the ideal graph has no edge between them."""
    for a in node_ids:
        for b in node_ids:
            if a != b and not _edge_should_exist(a, b, p):
                return a, b
    raise RuntimeError("All pairs are edges - pick a smaller p")


def _find_present_pair(node_ids, p):
    """Return some (a, b) such that the ideal graph has an edge between them."""
    for a in node_ids:
        for b in node_ids:
            if a != b and _edge_should_exist(a, b, p):
                return a, b
    raise RuntimeError("No edges exist - pick a larger p")


# Ideal graph reconstruction


def test_reconstruct_ideal_graph_matches_determine_neighbors():
    """Locks the cross-module invariant between verification.py and graph.py."""
    nodes = STABLE_NODE_IDS
    ideal = _reconstruct_ideal_graph(nodes, edge_probability=0.5)

    for nid in nodes:
        expected = set(determine_neighbors(nid, nodes, 0.5))
        assert ideal[nid] == expected


def test_reconstruct_ideal_graph_symmetric():
    nodes = STABLE_NODE_IDS
    ideal = _reconstruct_ideal_graph(nodes, edge_probability=0.5)

    for a in nodes:
        for b in ideal[a]:
            assert a in ideal[b], f"Asymmetry: {a}->{b} but not {b}->{a}"


@pytest.mark.parametrize("p", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_edge_should_exist_min_max_invariant(p):
    nodes = STABLE_NODE_IDS
    for a in nodes:
        for b in nodes:
            if a == b:
                continue
            assert _edge_should_exist(a, b, p) == _edge_should_exist(b, a, p)


# index / consistency / symmetry helpers


def test_build_published_edge_index():
    cert_graph = {
        "edges": [
            {"from": "a", "to": "b", "verified": True},
            {"from": "b", "to": "a", "verified": True},
        ],
    }
    idx = _build_published_edge_index(cert_graph)
    assert ("a", "b") in idx
    assert ("b", "a") in idx
    assert idx[("a", "b")]["verified"] is True


def test_check_node_consistency_missing_and_extra():
    published = ["a", "b", "c"]
    voted = {"a", "b", "ghost"}
    missing, extra = _check_node_consistency(published, voted)

    assert missing == ["ghost"]
    assert extra == ["c"]


def test_check_edge_symmetry_flags_one_directional():
    idx = {
        ("a", "b"): {"verified": True},  # only one direction
        ("c", "d"): {"verified": True},
        ("d", "c"): {"verified": True},  # symmetric
    }
    asymmetric = _check_edge_symmetry(idx)
    assert asymmetric == [("a", "b")]


# _reconcile_graph


def test_reconcile_graph_perfect_match_no_discrepancies():
    nodes = STABLE_NODE_IDS[:4]
    p = 0.5
    ideal = _reconstruct_ideal_graph(nodes, p)
    published = build_published_results(nodes, p)
    idx = _build_published_edge_index(published["certification_graph"])

    _, disc = _reconcile_graph(nodes, ideal, idx, set(nodes))

    assert disc.omitted_edges == []
    assert disc.fabricated_edges == []
    assert disc.missing_nodes == []
    assert disc.extra_nodes == []


def test_reconcile_graph_omitted_edge_synthesized_as_failed():
    nodes = STABLE_NODE_IDS[:4]
    p = 0.5
    ideal = _reconstruct_ideal_graph(nodes, p)
    a, b = _find_present_pair(nodes, p)

    published = build_published_results(nodes, p, drop_edges={(a, b)})
    idx = _build_published_edge_index(published["certification_graph"])

    verification_graph, disc = _reconcile_graph(nodes, ideal, idx, set(nodes))

    assert (a, b) in disc.omitted_edges
    # The synthesized edge for the omission must be present and marked unverified
    edge_objs = [e for e in verification_graph[a] if e.to_node == b]
    assert len(edge_objs) == 1
    assert edge_objs[0].omitted is True
    assert edge_objs[0].verified is False


def test_reconcile_graph_fabricated_edge_detected():
    nodes = STABLE_NODE_IDS[:4]
    p = 0.5
    ideal = _reconstruct_ideal_graph(nodes, p)
    a, b = _find_absent_pair(nodes, p)

    published = build_published_results(nodes, p, extra_edges=[(a, b)])
    idx = _build_published_edge_index(published["certification_graph"])

    _, disc = _reconcile_graph(nodes, ideal, idx, set(nodes))
    assert (a, b) in disc.fabricated_edges


def test_reconcile_graph_missing_node_in_response():
    nodes = STABLE_NODE_IDS[:4]
    p = 0.5
    ideal = _reconstruct_ideal_graph(nodes, p)
    published = build_published_results(nodes, p)
    idx = _build_published_edge_index(published["certification_graph"])

    response_nodes = set(nodes) | {"phantom-node"}
    _, disc = _reconcile_graph(nodes, ideal, idx, response_nodes)

    assert "phantom-node" in disc.missing_nodes


def test_graph_discrepancies_has_critical_issues():
    crit_fab = GraphDiscrepancies(fabricated_edges=[("a", "b")])
    crit_miss = GraphDiscrepancies(missing_nodes=["ghost"])
    not_crit = GraphDiscrepancies(omitted_edges=[("a", "b")], asymmetric_edges=[("c", "d")])

    assert crit_fab.has_critical_issues is True
    assert crit_miss.has_critical_issues is True
    assert not_crit.has_critical_issues is False


# verify_global - clean path


def test_verify_global_clean_path_accept():
    nodes = STABLE_NODE_IDS[:4]
    pub = build_published_results(nodes, edge_probability=0.5)

    result = verify_global(pub, eta_e=0.5, eta_v=0.5)

    assert result["verification"] == "ACCEPT"
    assert result["details"]["fabricated_edge_count"] == 0
    assert result["details"]["omitted_edge_count"] == 0
    # All four nodes voted opt0 on q1, q2 -> tally reflects unanimous vote
    assert result["tally"]["q1"]["opt0"] == 4
    assert result["tally"]["q1"]["opt1"] == 0
    assert result["tally"]["q2"]["opt0"] == 4


# verify_global - critical issues


def test_verify_global_fabricated_edge_rejects():
    nodes = STABLE_NODE_IDS[:4]
    p = 0.5
    a, b = _find_absent_pair(nodes, p)

    pub = build_published_results(nodes, p, extra_edges=[(a, b)])

    result = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert result["verification"] == "REJECT"
    assert result["tally"] == {}
    assert result["details"]["fabricated_edge_count"] >= 1


def test_verify_global_missing_node_rejects():
    nodes = STABLE_NODE_IDS[:4]
    pub = build_published_results(nodes, edge_probability=0.5)
    # Inject a vote from a node not in the cert_graph node list
    pub["responses"].append({
        "node_id": "phantom-node",
        "vote": {"q1": "opt0", "q2": "opt0"},
        "signatures": [],
        "self_signature": "x",
        "timestamp": "2024-01-01T12:00:00",
    })

    result = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert result["verification"] == "REJECT"
    assert result["details"]["missing_node_count"] == 1


def test_verify_global_no_nodes_returns_reject():
    pub = build_published_results(STABLE_NODE_IDS[:4], 0.5)
    pub["certification_graph"]["nodes"] = []

    result = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert result["verification"] == "REJECT"
    assert "no nodes" in result["details"]["message"].lower()


# verify_global - omission and asymmetry (non-critical)


def test_verify_global_omitted_edge_counted_but_accept_under_loose_eta_e():
    nodes = STABLE_NODE_IDS[:4]
    p = 1.0  # K4: every pair is an edge, both directions
    a, b = nodes[0], nodes[1]

    pub = build_published_results(
        nodes, p,
        effort_threshold=0.5,  # tolerate one omission per node
        validity_threshold=0.5,
        drop_edges={(a, b), (b, a)},
    )

    result = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert result["verification"] == "ACCEPT"
    assert result["details"]["omitted_edge_count"] == 2


def test_verify_global_asymmetric_edges_flagged_but_accept():
    nodes = STABLE_NODE_IDS[:4]
    p = 1.0
    a, b = nodes[0], nodes[1]

    # Drop A->B but keep B->A: omission on A's side, asymmetry on B's side
    pub = build_published_results(
        nodes, p,
        effort_threshold=0.5,
        validity_threshold=0.5,
        drop_edges={(a, b)},
    )

    result = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert result["verification"] == "ACCEPT"
    assert result["details"]["asymmetric_edge_count"] >= 1


def test_verify_global_extra_node_in_graph_not_critical():
    """Node listed in cert_graph['nodes'] but didn't vote -> ACCEPT, extra_node_count=1."""
    nodes = STABLE_NODE_IDS[:4]
    pub = build_published_results(nodes, edge_probability=0.5)
    # Drop the last response so node[3] is "extra" (in graph, but didn't vote)
    pub["responses"] = [r for r in pub["responses"] if r["node_id"] != nodes[3]]

    result = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert result["verification"] == "ACCEPT"
    assert result["details"]["extra_node_count"] == 1


# verify_global - exclusions and tally


def test_verify_global_excluded_node_vote_skipped_from_tally():
    nodes = STABLE_NODE_IDS[:4]
    p = 1.0
    a = nodes[0]
    # Mark all of A's outgoing edges as unverified -> A's failure rate = 1.0
    pub = build_published_results(
        nodes, p,
        validity_threshold=0.5,
        mark_unverified_edges={(a, nodes[1]), (a, nodes[2]), (a, nodes[3])},
    )

    result = verify_global(pub, eta_e=0.2, eta_v=0.5)
    assert result["verification"] == "ACCEPT"
    assert a in result["excluded_nodes"]
    # 3 votes counted (A's vote dropped)
    assert result["tally"]["q1"]["opt0"] == 3


def test_verify_global_eta_v_invalid_when_too_many_excluded():
    nodes = STABLE_NODE_IDS[:4]
    p = 1.0
    a = nodes[0]
    pub = build_published_results(
        nodes, p,
        mark_unverified_edges={(a, nodes[1]), (a, nodes[2]), (a, nodes[3])},
    )

    # m=4 voters, η_V=0.01 -> max_allowed = 0.04, 1 exclusion exceeds it
    result = verify_global(pub, eta_e=0.2, eta_v=0.01)
    assert result["verification"] == "INVALID"


def test_verify_global_eta_v_boundary_at_max_allowed_passes():
    """Locks the `<=` semantic at verification.py:466."""
    nodes = STABLE_NODE_IDS[:4]
    p = 1.0
    a = nodes[0]
    pub = build_published_results(
        nodes, p,
        mark_unverified_edges={(a, nodes[1]), (a, nodes[2]), (a, nodes[3])},
    )

    # 4 voters, η_V=0.25 -> max_allowed=1.0, exactly 1 exclusion
    result = verify_global(pub, eta_e=0.2, eta_v=0.25)
    assert result["verification"] == "ACCEPT"
    assert result["details"]["excluded_nodes_count"] == 1


def test_verify_global_invalid_vote_option_warned_not_counted():
    nodes = STABLE_NODE_IDS[:4]
    pub = build_published_results(nodes, edge_probability=0.5)
    # Replace one vote's q1 with an invalid option
    pub["responses"][0]["vote"]["q1"] = "garbage-option"

    result = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert result["verification"] == "ACCEPT"
    # The garbage vote is NOT in tally; only the 3 valid q1 votes counted
    assert result["tally"]["q1"]["opt0"] == 3
    assert "garbage-option" not in result["tally"]["q1"]


# verify_local


def test_verify_local_vote_found_passes():
    nodes = STABLE_NODE_IDS[:4]
    pub = build_published_results(nodes, edge_probability=0.5)

    success, message, details = verify_local(nodes[0], pub)
    assert success is True
    assert details["vote_found"] is True
    assert details["in_node_list"] is True


def test_verify_local_vote_missing_fails():
    nodes = STABLE_NODE_IDS[:4]
    pub = build_published_results(nodes, edge_probability=0.5)

    success, message, _ = verify_local("never-voted-node", pub)
    assert success is False
    assert "not found" in message.lower()


def test_verify_local_node_not_in_published_list_fails():
    nodes = STABLE_NODE_IDS[:4]
    pub = build_published_results(nodes, edge_probability=0.5)
    # Add a vote for a phantom node but leave it out of the node list
    pub["responses"].append({
        "node_id": "phantom",
        "vote": {"q1": "opt0", "q2": "opt0"},
        "signatures": [],
        "self_signature": "x",
        "timestamp": "2024-01-01T12:00:00",
    })

    success, message, _ = verify_local("phantom", pub)
    assert success is False
    assert "not in published node list" in message.lower()


def test_verify_local_omitted_edge_fails():
    nodes = STABLE_NODE_IDS[:4]
    p = 1.0
    a = nodes[0]
    # Drop one of A's outgoing edges -> verify_local on A should fail "missing from published"
    pub = build_published_results(nodes, p, drop_edges={(a, nodes[1])})

    success, message, details = verify_local(a, pub)
    assert success is False
    assert "missing from published" in message.lower()
    assert nodes[1] in details["omitted_edges"]


def test_verify_local_fabricated_wins_over_omitted():
    """Locks the order at verification.py:299 - fabricated returned before omitted."""
    nodes = STABLE_NODE_IDS[:4]
    p = 0.5
    pub = build_published_results(nodes, p)

    # Find a non-edge from nodes[0] and inject a fabricated outgoing edge
    a = nodes[0]
    target = next(
        n for n in nodes
        if n != a and not _edge_should_exist(a, n, p)
    )
    pub["certification_graph"]["edges"].append({
        "from": a, "to": target, "verified": True,
        "signature": "forged", "timestamp": "2024-01-01T12:00:00",
    })

    # Also drop a real edge so both fabricated and omitted exist
    real_neighbor = next(
        n for n in nodes
        if n != a and _edge_should_exist(a, n, p)
    )
    pub["certification_graph"]["edges"] = [
        e for e in pub["certification_graph"]["edges"]
        if not (e["from"] == a and e["to"] == real_neighbor)
    ]

    success, message, _ = verify_local(a, pub)
    assert success is False
    assert "fabricated" in message.lower()


def test_verify_local_unverified_edge_count():
    nodes = STABLE_NODE_IDS[:4]
    p = 1.0
    a = nodes[0]
    pub = build_published_results(nodes, p, mark_unverified_edges={(a, nodes[1])})

    success, _, details = verify_local(a, pub)
    assert success is True
    assert details["unverified_edges"] == 1


# Mutation safety for build_published_results


def test_build_published_results_can_be_deepcopied_safely():
    nodes = STABLE_NODE_IDS[:4]
    base = build_published_results(nodes, edge_probability=0.5)
    mutated = copy.deepcopy(base)
    mutated["responses"][0]["node_id"] = "altered"

    assert base["responses"][0]["node_id"] == nodes[0]
    assert mutated["responses"][0]["node_id"] == "altered"
