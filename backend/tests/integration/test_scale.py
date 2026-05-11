"""
Scale test: walk all six protocol phases with 50 responders.

Exercises the trust model on a non-trivial graph derived from Theorem 4.4
parameters at m=50, medium security level (kappa=80). Asserts:
  - Every responder registers and certifies cleanly.
  - The certification graph matches the ideal graph (no fabricated / omitted edges).
  - The vote tally exactly reflects the injected mix of opt0 / opt1.
  - Local verification works for an arbitrary sample of nodes.
  - The full run completes in under a wall-clock budget so regressions are visible.

Marked `scale` so it can be excluded from the fast unit/integration loops via
`pytest -m "not scale"` while still running in CI by default.
"""

import time

import pytest

from app.crypto.graph import determine_neighbors
from app.crypto.params import recommend_params_for_poll

from tests.fixtures import (
    build_small_poll_payload,
    complete_certification_for_all,
    make_keypair,
    register_n_nodes,
)


# Total wall-clock budget for the whole test on a developer laptop. Generous —
# the goal is to catch order-of-magnitude regressions, not micro-optimize.
TIME_BUDGET_SECONDS = 30.0

# 30 opt0 / 20 opt1 -> tally lets us verify mixed voting tallies exactly.
N_USERS = 50
N_VOTE_OPT0 = 30
N_VOTE_OPT1 = N_USERS - N_VOTE_OPT0


def _vote_for_index(node_id: str, idx: int) -> dict:
    """First N_VOTE_OPT0 voters pick opt0 on q1; the rest pick opt1. q2 always opt0."""
    return {
        "node_id": node_id,
        "vote": {
            "q1": "opt0" if idx < N_VOTE_OPT0 else "opt1",
            "q2": "opt0",
        },
        "signatures": [],
        "signature": f"self-sig-{idx}",
    }


@pytest.mark.scale
def test_full_flow_at_scale_with_50_users(client, app_storage):
    started = time.perf_counter()

    # Use Theorem 4.4 medium-security parameters for m=50. p≈0.26 gives ~13 neighbors per
    # node on average, which keeps the graph sparse but still well-connected. Effort and
    # validity thresholds are loosened to keep this test about scale rather than tuning.
    params = recommend_params_for_poll(expected_responders=N_USERS, security_level="medium")
    payload = build_small_poll_payload(
        edge_probability=params.edge_probability,
        effort_threshold=0.5,
        validity_threshold=0.5,
    )

    create_resp = client.post("/api/poll/create", json=payload)
    assert create_resp.status_code == 200
    sid = create_resp.json()["session_id"]

    # 50 fresh keypairs (the session-scoped responder_keypairs fixture only carries 8)
    keypairs = [make_keypair() for _ in range(N_USERS)]

    # Phase 2: Registration. Walks captcha -> register for every one of the 50 users.
    node_ids = register_n_nodes(client, sid, N_USERS, keypairs)
    assert len(node_ids) == N_USERS
    assert len(set(node_ids)) == N_USERS, "node_ids must be unique"

    transition = client.post(f"/api/poll/{sid}/status", json={"new_status": "certification"})
    assert transition.status_code == 200

    # Phase 3: Certification. Seed every ideal edge as verified.
    edges_seeded = complete_certification_for_all(
        app_storage, sid, node_ids, edge_probability=params.edge_probability
    )
    expected_directed_edges = sum(
        len(determine_neighbors(nid, node_ids, params.edge_probability)) for nid in node_ids
    )
    assert edges_seeded == expected_directed_edges

    # Threshold endpoint reports all 50 certified.
    threshold = client.get(f"/api/poll/{sid}/certification/threshold").json()
    assert threshold["threshold_met"] is True
    assert len(threshold["certified_nodes"]) == N_USERS

    voting_resp = client.post(f"/api/poll/{sid}/status", json={"new_status": "voting"})
    assert voting_resp.status_code == 200

    # Phase 4: Response. 30 vote opt0 on q1, 20 vote opt1. All vote opt0 on q2.
    for idx, nid in enumerate(node_ids):
        vote_resp = client.post(f"/api/poll/{sid}/vote", json=_vote_for_index(nid, idx))
        assert vote_resp.status_code == 200, vote_resp.text

    # Phase 5: Results.
    publish_resp = client.post(f"/api/poll/{sid}/publish")
    assert publish_resp.status_code == 200

    results = client.get(f"/api/poll/{sid}/results").json()
    assert len(results["responses"]) == N_USERS
    assert set(results["certification_graph"]["nodes"]) == set(node_ids)
    assert len(results["certification_graph"]["edges"]) == expected_directed_edges

    # Phase 6: Global verification.
    body = client.post(f"/api/poll/{sid}/verify", json={"mode": "global"}).json()
    assert body["verification"] == "ACCEPT", body["details"]
    assert body["tally"] == {
        "q1": {"opt0": N_VOTE_OPT0, "opt1": N_VOTE_OPT1},
        "q2": {"opt0": N_USERS, "opt1": 0},
    }
    assert body["details"]["fabricated_edge_count"] == 0
    assert body["details"]["omitted_edge_count"] == 0
    assert body["details"]["excluded_nodes_count"] == 0
    assert body["details"]["valid_nodes"] == N_USERS

    # Local verification for a spread sample so we exercise different positions in the graph.
    sample_indices = [0, N_USERS // 4, N_USERS // 2, 3 * N_USERS // 4, N_USERS - 1]
    for i in sample_indices:
        local = client.post(
            f"/api/poll/{sid}/verify",
            json={"mode": "local", "node_id": node_ids[i]},
        ).json()
        assert local["verification"] == "ACCEPT", (i, node_ids[i], local)

    elapsed = time.perf_counter() - started
    assert elapsed < TIME_BUDGET_SECONDS, (
        f"Full 50-user flow took {elapsed:.2f}s, budget {TIME_BUDGET_SECONDS}s"
    )
