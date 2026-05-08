"""Unit tests for app.crypto.graph."""

import string

import pytest

from app.crypto.graph import (
    compute_exclusions,
    compute_node_id,
    determine_neighbors,
    validate_certification_graph,
)
from app.storage.memory import CertificationEdge

from tests.fixtures import STABLE_NODE_IDS


# compute_node_id


def test_compute_node_id_deterministic():
    assert compute_node_id("pubkey-A") == compute_node_id("pubkey-A")
    assert compute_node_id("pubkey-A") != compute_node_id("pubkey-B")


def test_compute_node_id_length_16_lowercase_hex():
    nid = compute_node_id("any-public-key-string")
    assert len(nid) == 16
    assert all(c in string.hexdigits.lower() for c in nid)


# determine_neighbors


def test_determine_neighbors_p_zero_returns_empty():
    assert determine_neighbors(STABLE_NODE_IDS[0], STABLE_NODE_IDS, 0.0) == []


def test_determine_neighbors_p_one_returns_all_others():
    me = STABLE_NODE_IDS[0]
    neighbors = determine_neighbors(me, STABLE_NODE_IDS, 1.0)

    expected = [n for n in STABLE_NODE_IDS if n != me]
    assert sorted(neighbors) == sorted(expected)
    assert me not in neighbors


def test_determine_neighbors_excludes_self_at_any_p():
    for p in (0.0, 0.25, 0.5, 0.75, 1.0):
        for me in STABLE_NODE_IDS:
            assert me not in determine_neighbors(me, STABLE_NODE_IDS, p)


@pytest.mark.parametrize("p", [0.1, 0.3, 0.5, 0.7, 0.9])
def test_determine_neighbors_symmetry(p):
    """edge(A,B) <=> edge(B,A): same hash regardless of direction."""
    membership = {
        nid: set(determine_neighbors(nid, STABLE_NODE_IDS, p))
        for nid in STABLE_NODE_IDS
    }
    for a in STABLE_NODE_IDS:
        for b in STABLE_NODE_IDS:
            if a == b:
                continue
            assert (b in membership[a]) == (a in membership[b]), (
                f"Asymmetry detected at p={p}: {a}/{b}"
            )


def test_determine_neighbors_deterministic_repeated_calls():
    me = STABLE_NODE_IDS[0]
    first = determine_neighbors(me, STABLE_NODE_IDS, 0.5)
    second = determine_neighbors(me, STABLE_NODE_IDS, 0.5)
    assert first == second


def test_determine_neighbors_input_order_independent():
    """Shuffling the all_node_ids list must not change neighbor membership."""
    me = STABLE_NODE_IDS[0]
    forward = set(determine_neighbors(me, STABLE_NODE_IDS, 0.5))
    reversed_set = set(determine_neighbors(me, list(reversed(STABLE_NODE_IDS)), 0.5))
    assert forward == reversed_set


@pytest.mark.parametrize("bad_p", [-0.1, 1.5, -1.0, 2.0])
def test_determine_neighbors_invalid_probability_raises(bad_p):
    with pytest.raises(ValueError):
        determine_neighbors(STABLE_NODE_IDS[0], STABLE_NODE_IDS, bad_p)


# compute_exclusions


def _make_edge_objs(from_node: str, neighbors_with_status):
    return [
        CertificationEdge(from_node=from_node, to_node=t, verified=v)
        for t, v in neighbors_with_status
    ]


def test_compute_exclusions_below_threshold_not_excluded():
    """1 fail / 4 edges = 0.25, threshold 0.30 -> not excluded."""
    graph = {
        "node-a": _make_edge_objs("node-a", [
            ("b", True), ("c", True), ("d", True), ("e", False),
        ]),
    }
    assert compute_exclusions(graph, eta_e=0.30) == set()


def test_compute_exclusions_at_threshold_boundary_not_excluded():
    """Locks the strict `>` semantic at graph.py:98. failure_rate == eta_e -> NOT excluded."""
    graph = {
        "node-a": _make_edge_objs("node-a", [
            ("b", True), ("c", True), ("d", True), ("e", False),
        ]),
    }
    assert compute_exclusions(graph, eta_e=0.25) == set()


def test_compute_exclusions_above_threshold_excluded():
    graph = {
        "node-a": _make_edge_objs("node-a", [
            ("b", True), ("c", True), ("d", False), ("e", False),
        ]),
    }
    assert compute_exclusions(graph, eta_e=0.25) == {"node-a"}


def test_compute_exclusions_handles_certification_edge_objects():
    graph = {
        "n1": _make_edge_objs("n1", [("a", True), ("b", False)]),
        "n2": _make_edge_objs("n2", [("a", True), ("b", True)]),
    }
    assert compute_exclusions(graph, eta_e=0.4) == {"n1"}


def test_compute_exclusions_handles_dict_of_dict_edges():
    graph = {
        "n1": {
            "a": {"verified": True},
            "b": {"verified": False},
            "c": {"verified": False},
        },
    }
    assert compute_exclusions(graph, eta_e=0.5) == {"n1"}


def test_compute_exclusions_handles_list_of_dict_edges():
    graph = {
        "n1": [
            {"verified": True},
            {"verified": False},
            {"verified": False},
        ],
    }
    assert compute_exclusions(graph, eta_e=0.5) == {"n1"}


def test_compute_exclusions_empty_edges_skipped():
    graph = {"n-empty": []}
    assert compute_exclusions(graph, eta_e=0.1) == set()


@pytest.mark.parametrize("bad_eta", [-0.1, 1.5, 2.0])
def test_compute_exclusions_invalid_eta_raises(bad_eta):
    with pytest.raises(ValueError):
        compute_exclusions({"n1": []}, eta_e=bad_eta)


# validate_certification_graph


def test_validate_certification_graph_valid_passes():
    graph = {
        "a": _make_edge_objs("a", [("b", True)]),
        "b": _make_edge_objs("b", [("a", True)]),
    }
    assert validate_certification_graph(graph, ["a", "b"]) is True


def test_validate_certification_graph_unregistered_node_fails():
    graph = {
        "a": _make_edge_objs("a", [("b", True)]),
        "ghost": _make_edge_objs("ghost", []),
    }
    assert validate_certification_graph(graph, ["a", "b"]) is False


def test_validate_certification_graph_unregistered_edge_target_fails():
    graph = {
        "a": _make_edge_objs("a", [("zombie", True)]),
    }
    assert validate_certification_graph(graph, ["a"]) is False
