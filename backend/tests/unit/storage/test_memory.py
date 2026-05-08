"""Unit tests for app.storage.memory.InMemoryStorage."""

from datetime import datetime, timedelta

import pytest


def _create_session(storage, sid="session-1"):
    return storage.create_session(
        session_id=sid,
        public_key="test-pubkey-b64",
        questions=[{"id": "q1", "text": "Q?", "options": ["a", "b"]}],
        edge_probability=0.5,
        effort_threshold=0.2,
    )


# create_session / get_session / update_session_status


def test_create_session_stores_and_retrieves(storage):
    _create_session(storage, "s1")
    s = storage.get_session("s1")
    assert s is not None
    assert s.session_id == "s1"
    assert s.status == "registration"


def test_create_session_duplicate_id_raises(storage):
    _create_session(storage, "s1")
    with pytest.raises(ValueError):
        _create_session(storage, "s1")


def test_get_session_unknown_returns_none(storage):
    assert storage.get_session("nonexistent") is None


def test_update_session_status_unknown_session_returns_false(storage):
    assert storage.update_session_status("nonexistent", "voting") is False


def test_update_session_status_persists(storage):
    _create_session(storage, "s1")
    assert storage.update_session_status("s1", "voting") is True
    assert storage.get_session("s1").status == "voting"


# captcha


def test_store_validate_consume_captcha_happy_path(storage):
    _create_session(storage, "s1")
    storage.store_captcha_challenge(
        session_id="s1",
        token="tok-1",
        question="2 + 3 = ?",
        solution="5",
        expires_at=datetime.now() + timedelta(minutes=5),
    )

    assert storage.validate_and_consume_captcha("s1", "tok-1", "5") is True


def test_validate_captcha_wrong_solution_fails(storage):
    _create_session(storage, "s1")
    storage.store_captcha_challenge(
        session_id="s1", token="tok-1", question="2 + 3 = ?",
        solution="5", expires_at=datetime.now() + timedelta(minutes=5),
    )
    assert storage.validate_and_consume_captcha("s1", "tok-1", "6") is False


def test_validate_captcha_already_used_fails(storage):
    _create_session(storage, "s1")
    storage.store_captcha_challenge(
        session_id="s1", token="tok-1", question="2 + 3 = ?",
        solution="5", expires_at=datetime.now() + timedelta(minutes=5),
    )
    assert storage.validate_and_consume_captcha("s1", "tok-1", "5") is True
    assert storage.validate_and_consume_captcha("s1", "tok-1", "5") is False


def test_validate_captcha_expired_fails(storage):
    _create_session(storage, "s1")
    storage.store_captcha_challenge(
        session_id="s1", token="tok-1", question="2 + 3 = ?",
        solution="5", expires_at=datetime.now() - timedelta(seconds=1),
    )
    assert storage.validate_and_consume_captcha("s1", "tok-1", "5") is False


def test_validate_captcha_unknown_token_fails(storage):
    _create_session(storage, "s1")
    assert storage.validate_and_consume_captcha("s1", "missing-tok", "5") is False


def test_validate_captcha_unknown_session_fails(storage):
    assert storage.validate_and_consume_captcha("nonexistent", "tok", "5") is False


# registered nodes


def test_add_registered_node_assigns_position(storage):
    _create_session(storage, "s1")
    pos0 = storage.add_registered_node("s1", "node-a", "pubkey-a")
    pos1 = storage.add_registered_node("s1", "node-b", "pubkey-b")
    assert pos0 == 0
    assert pos1 == 1


def test_add_registered_node_duplicate_returns_none(storage):
    _create_session(storage, "s1")
    storage.add_registered_node("s1", "node-a", "pubkey-a")
    assert storage.add_registered_node("s1", "node-a", "pubkey-a") is None


def test_get_registered_nodes_returns_copy(storage):
    _create_session(storage, "s1")
    storage.add_registered_node("s1", "node-a", "pubkey-a")
    nodes = storage.get_registered_nodes("s1")
    nodes.clear()
    # Original list inside storage is untouched
    assert len(storage.get_registered_nodes("s1")) == 1


# certification edges


def test_add_certification_edge_creates_then_updates(storage):
    _create_session(storage, "s1")
    storage.add_certification_edge("s1", "a", "b", verified=False)
    storage.add_certification_edge("s1", "a", "b", verified=True, signature="new-sig")

    edges = storage.get_node_edges("s1", "a")
    assert len(edges) == 1
    assert edges[0].verified is True
    assert edges[0].signature == "new-sig"


def test_add_certification_edge_unknown_session(storage):
    assert storage.add_certification_edge("nope", "a", "b", verified=True) is False


def test_get_node_edges_returns_copy(storage):
    _create_session(storage, "s1")
    storage.add_certification_edge("s1", "a", "b", verified=True)
    edges = storage.get_node_edges("s1", "a")
    edges.clear()
    # Mutating the returned copy must not empty storage
    assert len(storage.get_node_edges("s1", "a")) == 1


def test_get_certification_graph_returns_per_node_copies(storage):
    _create_session(storage, "s1")
    storage.add_certification_edge("s1", "a", "b", verified=True)
    graph = storage.get_certification_graph("s1")
    graph["a"].clear()
    # Underlying graph is unaffected
    assert len(storage.get_certification_graph("s1")["a"]) == 1


# votes


def test_add_vote_records(storage):
    _create_session(storage, "s1")
    ok = storage.add_vote(
        session_id="s1", node_id="node-a",
        vote={"q1": "a"}, signatures=[], self_signature="self-sig",
    )
    assert ok is True
    votes = storage.get_votes("s1")
    assert "node-a" in votes


def test_add_vote_duplicate_returns_false(storage):
    _create_session(storage, "s1")
    storage.add_vote(session_id="s1", node_id="n", vote={"q1": "a"},
                    signatures=[], self_signature="x")
    ok = storage.add_vote(session_id="s1", node_id="n", vote={"q1": "b"},
                         signatures=[], self_signature="y")
    assert ok is False


# publish_results


def test_publish_results_assembles_full_payload(storage):
    _create_session(storage, "s1")
    storage.add_registered_node("s1", "node-a", "pubkey-a")
    storage.add_registered_node("s1", "node-b", "pubkey-b")
    storage.add_certification_edge("s1", "node-a", "node-b", verified=True, signature="sig-ab")
    storage.add_vote("s1", "node-a", {"q1": "a"}, [], "self-sig-a")

    results = storage.publish_results("s1")

    assert results["session_id"] == "s1"
    assert results["public_key"] == "test-pubkey-b64"
    assert "questions" in results
    assert "parameters" in results
    assert "responses" in results and len(results["responses"]) == 1
    assert "certification_graph" in results
    assert "node-a" in results["certification_graph"]["nodes"]
    assert any(
        e["from"] == "node-a" and e["to"] == "node-b" and e["verified"]
        for e in results["certification_graph"]["edges"]
    )
    assert "published_at" in results


def test_publish_results_status_set_to_results(storage):
    _create_session(storage, "s1")
    storage.publish_results("s1")
    assert storage.get_session("s1").status == "results"


def test_publish_results_unknown_session_returns_none(storage):
    assert storage.publish_results("nope") is None


# stats / clear


def test_get_session_stats_counts_correctly(storage):
    _create_session(storage, "s1")
    storage.add_registered_node("s1", "a", "pk-a")
    storage.add_registered_node("s1", "b", "pk-b")
    storage.add_certification_edge("s1", "a", "b", verified=True)
    storage.add_certification_edge("s1", "b", "a", verified=False)
    storage.add_vote("s1", "a", {"q1": "a"}, [], "self")

    stats = storage.get_session_stats("s1")
    assert stats["registered_nodes"] == 2
    assert stats["total_edges"] == 2
    assert stats["verified_edges"] == 1
    assert stats["votes_submitted"] == 1


def test_clear_resets_all_sessions(storage):
    _create_session(storage, "s1")
    _create_session(storage, "s2")
    storage.clear()
    assert storage.list_sessions() == []


# RLock reentry


def test_rlock_supports_sequential_reentry(storage):
    """RLock must allow same-thread reentry without deadlocking."""
    _create_session(storage, "s1")
    with storage._lock:
        # Re-enter the lock through a public method
        assert storage.get_session("s1") is not None
        assert storage.update_session_status("s1", "certification") is True
