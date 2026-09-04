"""
The property that makes the certification graph unsteerable.

These tests exist because of a specific attack. When edges were derived from the
node ids alone -- SHA-256(min(id_a, id_b) : max(id_a, id_b)) <= p * MAX_HASH,
with node_id = SHA-256(public_key)[:16] -- a node's own row of the adjacency
matrix was a pure function of a key it chose itself, and everybody else's rows
stayed fixed while it varied its own. A corrupt node could generate keypairs
offline and keep the one whose row had the fewest edges into the honest set,
cutting its PPE workload with no detectable trace: the verifier reconstructed
the ideal graph from the same ids, so the reconstruction agreed with the fraud.

At the parameters this project documents, that was cheap. Against 50 honest
nodes at p=0.26 (expected degree ~13), reaching degree <= 3 takes roughly 3,400
keygens -- about a tenth of a second.

What stops it is that the seed folds in a digest of *every* registered key, so
one node changing its key rerolls the entire graph instead of one row. Each
grinding trial becomes a fresh independent sample of the whole matrix, and a
key that lowers one sybil's degree rerolls every other sybil at the same time,
so the cost of placing k sybils grows exponentially in k rather than linearly.

test_changing_one_key_rerolls_edges_between_other_nodes is the direct
regression: under the old rule it would find exactly one honest subgraph.
"""

import pytest

from app.crypto.graph import (
    assign_indices,
    build_graph_context,
    compute_graph_seed,
    compute_participant_digest,
    compute_seed_commitment,
    determine_neighbors,
    edge_exists,
    verify_seed_commitment,
)
from app.crypto.verification import verify_global

from tests.fixtures import (
    STABLE_KEYPAIRS,
    STABLE_NODE_IDS,
    STABLE_SEED_NONCE,
    build_published_results,
    deterministic_keypair,
    pubkeys_for,
)


HONEST = STABLE_KEYPAIRS[:5]
HONEST_IDS = [kp[3] for kp in HONEST]

# Candidate keys an adversary might grind through. Deterministic, so a failure
# here is reproducible rather than a flaky sample.
CANDIDATES = [deterministic_keypair(i) for i in range(100, 140)]


def _ctx_with_adversary(adversary, probability=0.5):
    keys = {kp[3]: kp[2] for kp in HONEST}
    keys[adversary[3]] = adversary[2]
    return build_graph_context(STABLE_SEED_NONCE, keys, probability)


def _honest_subgraph(ctx):
    """The undirected edge set among the honest nodes only."""
    return frozenset(
        frozenset((a, b))
        for a in HONEST_IDS
        for b in HONEST_IDS
        if a != b and edge_exists(a, b, ctx)
    )


# The core property


def test_changing_one_key_rerolls_edges_between_other_nodes():
    """One node's key choice must not leave the rest of the graph fixed.

    This is the whole fix. Under the old id-based rule the honest-to-honest
    edges were untouched by whatever key the adversary picked, so grinding
    accumulated progress against a stationary target. Now every candidate key
    produces a different graph, so there is no gradient to climb.
    """
    subgraphs = {_honest_subgraph(_ctx_with_adversary(c)) for c in CANDIDATES}

    assert len(subgraphs) > 1, (
        "The honest-to-honest edges did not change when the adversary changed "
        "its key. That means a node can vary its own row while holding the rest "
        "of the graph fixed -- the grinding attack is back."
    )


def test_own_degree_varies_with_key_but_never_alone():
    """Grinding still moves the adversary's degree -- it just cannot do so in
    isolation. Every candidate that changes the degree also changes the graph
    the honest nodes see, which is what makes trials independent rather than
    cumulative."""
    by_degree = {}
    for candidate in CANDIDATES:
        ctx = _ctx_with_adversary(candidate)
        degree = len(determine_neighbors(candidate[3], ctx))
        by_degree.setdefault(degree, []).append(_honest_subgraph(ctx))

    assert len(by_degree) > 1, "Expected candidate keys to differ in degree"

    # No two candidates reach a different own-degree off the same honest graph.
    for degree, subgraphs in by_degree.items():
        others = [
            sub
            for other_degree, subs in by_degree.items()
            if other_degree != degree
            for sub in subs
        ]
        assert not (set(subgraphs) & set(others)), (
            f"Degree {degree} is reachable from an honest subgraph that also "
            f"yields a different degree -- own degree is independently steerable"
        )


def test_seed_depends_on_every_participant_key():
    """Swapping any single key changes the seed, so no participant -- and no
    subset of them -- can pin the graph down."""
    keys = {kp[3]: kp[2] for kp in HONEST}
    baseline = build_graph_context(STABLE_SEED_NONCE, keys, 0.5).seed

    for victim in HONEST_IDS:
        mutated = dict(keys)
        del mutated[victim]
        replacement = deterministic_keypair(200)
        mutated[replacement[3]] = replacement[2]

        assert build_graph_context(STABLE_SEED_NONCE, mutated, 0.5).seed != baseline


def test_seed_depends_on_the_pollster_nonce():
    """The nonce is committed before any key exists, which is what stops the
    pollster from choosing a seed after seeing the participants."""
    keys = pubkeys_for(STABLE_NODE_IDS)
    a = build_graph_context("a" * 64, keys, 0.5)
    b = build_graph_context("b" * 64, keys, 0.5)
    assert a.seed != b.seed
    assert a.indices == b.indices  # indices come from the keys, not the nonce


# Index assignment


def test_indices_are_a_permutation_of_range_m():
    indices = assign_indices(pubkeys_for(STABLE_NODE_IDS))
    assert sorted(indices.values()) == list(range(len(STABLE_NODE_IDS)))


def test_assign_indices_rejects_unbound_public_key():
    """node_id == SHA-256(pubkey)[:16] is what keeps indices honest. An unbound
    key would let a pollster shift every index by inventing one."""
    keys = pubkeys_for(STABLE_NODE_IDS)
    victim = STABLE_NODE_IDS[0]
    keys[victim] = deterministic_keypair(300)[2]

    with pytest.raises(ValueError, match="does not hash to its node id"):
        assign_indices(keys)


# Commitment


def test_seed_commitment_opens_only_to_its_own_nonce():
    nonce = "c" * 64
    commitment = compute_seed_commitment(nonce)
    assert verify_seed_commitment(nonce, commitment)
    assert not verify_seed_commitment("d" * 64, commitment)
    assert not verify_seed_commitment("", commitment)
    assert not verify_seed_commitment(nonce, "")


def test_graph_seed_is_derived_from_nonce_and_digest():
    keys = pubkeys_for(STABLE_NODE_IDS)
    digest = compute_participant_digest(keys.values())
    ctx = build_graph_context(STABLE_SEED_NONCE, keys, 0.5)
    assert ctx.seed == compute_graph_seed(STABLE_SEED_NONCE, digest)


def test_participant_digest_ignores_registration_order():
    keys = pubkeys_for(STABLE_NODE_IDS)
    forward = compute_participant_digest(keys.values())
    backward = compute_participant_digest(list(reversed(list(keys.values()))))
    assert forward == backward


# What a verifier rejects


def test_verify_global_accepts_a_correctly_bound_bulletin():
    pub = build_published_results(STABLE_NODE_IDS[:4], edge_probability=0.5)
    assert verify_global(pub, eta_e=0.5, eta_v=0.5)["verification"] == "ACCEPT"


def test_verify_global_rejects_nonce_that_does_not_open_the_commitment():
    pub = build_published_results(
        STABLE_NODE_IDS[:4],
        edge_probability=0.5,
        graph_binding_overrides={"seed_commitment": compute_seed_commitment("z" * 64)},
    )
    out = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert out["verification"] == "REJECT"
    assert "does not open the published commitment" in out["details"]["message"]


def test_verify_global_rejects_forged_graph_seed():
    """A pollster that ran a different graph than its nonce and keys imply."""
    pub = build_published_results(
        STABLE_NODE_IDS[:4],
        edge_probability=0.5,
        graph_binding_overrides={"graph_seed": "0" * 64},
    )
    out = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert out["verification"] == "REJECT"
    assert "does not match the seed derived" in out["details"]["message"]


def test_verify_global_rejects_permuted_node_indices():
    """Indices are canonical, so a pollster cannot reshape the graph by
    reassigning them -- for instance to give a colluding node a low degree."""
    nodes = STABLE_NODE_IDS[:4]
    honest = build_published_results(nodes, edge_probability=0.5)
    permuted = dict(honest["graph_binding"]["node_indices"])
    a, b = nodes[0], nodes[1]
    permuted[a], permuted[b] = permuted[b], permuted[a]

    pub = build_published_results(
        nodes,
        edge_probability=0.5,
        graph_binding_overrides={"node_indices": permuted},
    )
    out = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert out["verification"] == "REJECT"
    assert "do not match the canonical assignment" in out["details"]["message"]


def test_verify_global_rejects_bulletin_with_no_graph_binding():
    """Bulletins from before the binding existed are no longer verifiable: there
    is no seed to reconstruct the graph from."""
    pub = build_published_results(STABLE_NODE_IDS[:4], edge_probability=0.5)
    del pub["graph_binding"]

    out = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert out["verification"] == "REJECT"
    assert "seed commitment" in out["details"]["message"]


def test_verify_global_rejects_bulletin_with_no_public_keys():
    """Without keys a verifier cannot assign indices or derive the seed."""
    pub = build_published_results(STABLE_NODE_IDS[:4], edge_probability=0.5)
    del pub["public_keys"]
    del pub["certification_graph"]["public_keys"]

    out = verify_global(pub, eta_e=0.5, eta_v=0.5)
    assert out["verification"] == "REJECT"
    assert "no public keys" in out["details"]["message"]
