"""
Certification graph primitives (Protocols 3 & 6).

Edges in the certification graph are NOT chosen by the pollster, and they are
NOT chosen by the participants either. They are derived deterministically from
a session-wide seed and each node's *canonical index*, so any party can
independently recompute the full "ideal graph" once registration has closed:

  edge(i, j) exists  <=>  SHA-256(seed : min(i,j) : max(i,j))  <=  p * MAX_HASH

where i and j are integer indices in [0, m), not node identifiers.

Why indices and a seed, rather than hashing the node ids
--------------------------------------------------------
The security argument of the PPE paper needs the certification graph to be a
sample of G(m, p) drawn independently of the adversary's choices. An earlier
version of this module hashed the node ids directly:

    SHA-256(min(id_i, id_j) : max(id_i, id_j)) <= p * MAX_HASH

Since node_id = SHA-256(public_key)[:16], that made a node's own row of the
adjacency matrix a pure function of a key it chose itself, while everybody
else's rows stayed fixed. A corrupt node could therefore shop for its own
neighbourhood: generate keypairs offline and keep the one whose row had the
fewest edges into the honest set, cutting its PPE workload without doing any
work and without leaving a trace a verifier could detect (the reconstructed
ideal graph was derived from the same ids, so it agreed with the fraud).

Two changes remove that freedom:

  * seed folds in a digest of *every* registered public key, so changing one
    key rerolls the entire graph rather than one row. Each grinding trial is a
    fresh independent sample of the whole matrix, so an adversary cannot
    accumulate progress -- and cannot lower the degree of several sybils at
    once, since a key that helps one rerolls the others.
  * seed also folds in a nonce the pollster commits to at poll creation,
    before any key is known, which stops the pollster from grinding the seed
    after seeing the participants.

Indices are assigned canonically from the frozen participant set -- rank in
lexicographic order of public key -- so neither the pollster's registration
ordering nor a node's own choice can steer them.

This module also handles eta_E exclusion: if a node fails more than eta_E of
its PPE challenges, it's excluded from the final tally.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import List, Set, Dict, Any, Mapping, Iterable

logger = logging.getLogger(__name__)

# Maximum value of a 256-bit SHA-256 hash (64 hex chars of 'f')
_MAX_HASH = int('f' * 64, 16)


def compute_node_id(public_key: str) -> str:
    """SHA-256 of the public key, truncated to 16 hex chars."""
    return hashlib.sha256(public_key.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Seed derivation (Protocol 1 commitment -> Protocol 3 reveal)
# ---------------------------------------------------------------------------

def compute_seed_commitment(seed_nonce: str) -> str:
    """The pollster publishes this at poll creation, before any key is known.

    Committing first is what stops the pollster from picking a nonce that
    produces a graph it likes after seeing the registered keys.
    """
    return hashlib.sha256(seed_nonce.encode('utf-8')).hexdigest()


def verify_seed_commitment(seed_nonce: str, seed_commitment: str) -> bool:
    """Check a revealed nonce against the commitment published at Protocol 1."""
    if not seed_nonce or not seed_commitment:
        return False
    return compute_seed_commitment(seed_nonce) == seed_commitment


def compute_participant_digest(public_keys: Iterable[str]) -> str:
    """Digest of the frozen participant set, order-independent.

    Sorting first means the pollster cannot change the digest by reordering
    registrations, and including every key means no single participant can
    steer it.
    """
    canonical = '\n'.join(sorted(public_keys))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def compute_graph_seed(seed_nonce: str, participant_digest: str) -> str:
    """Fix the session's graph once registration closes.

    Neither side controls this alone: the nonce is committed before the keys
    exist, and the digest covers all the keys.
    """
    return hashlib.sha256(
        f"{seed_nonce}:{participant_digest}".encode('utf-8')
    ).hexdigest()


def assign_indices(public_keys: Mapping[str, str]) -> Dict[str, int]:
    """Assign each node its canonical index in [0, m).

    Rank in lexicographic order of public key. Deterministic, recomputable by
    any verifier from the published key set, and independent of the order in
    which nodes happened to register -- so a pollster cannot permute the graph
    by delaying or reordering registrations.

    public_keys maps node_id -> public key. Raises if any entry breaks the
    node_id == SHA-256(public_key)[:16] binding, since an unbound key would let
    the pollster shift every index by publishing a key it made up.
    """
    for node_id, pubkey in public_keys.items():
        if compute_node_id(pubkey) != node_id:
            raise ValueError(
                f"Public key for node {node_id} does not hash to its node id"
            )

    ordered = sorted(public_keys.items(), key=lambda item: item[1])
    return {node_id: index for index, (node_id, _) in enumerate(ordered)}


@dataclass(frozen=True)
class GraphContext:
    """Everything needed to compute the ideal graph, frozen at registration close.

    Build it with build_graph_context rather than by hand, so the seed and the
    indices always come from the same participant set.
    """
    seed: str
    probability: float
    indices: Mapping[str, int]

    @property
    def node_ids(self) -> List[str]:
        """Registered node ids, in canonical index order."""
        return sorted(self.indices, key=lambda nid: self.indices[nid])

    @property
    def size(self) -> int:
        return len(self.indices)


def build_graph_context(
    seed_nonce: str,
    public_keys: Mapping[str, str],
    probability: float,
) -> GraphContext:
    """Derive the session's graph context from the frozen participant set."""
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"Probability must be between 0 and 1, got {probability}")
    if not seed_nonce:
        raise ValueError("seed_nonce is required to derive the graph seed")

    participant_digest = compute_participant_digest(public_keys.values())
    seed = compute_graph_seed(seed_nonce, participant_digest)

    return GraphContext(
        seed=seed,
        probability=probability,
        indices=assign_indices(public_keys),
    )


# ---------------------------------------------------------------------------
# The edge rule
# ---------------------------------------------------------------------------

def _edge_hash(seed: str, index_a: int, index_b: int) -> int:
    """SHA-256 over the seed and the ordered index pair, as an integer."""
    lo, hi = (index_a, index_b) if index_a < index_b else (index_b, index_a)
    return int(
        hashlib.sha256(f"{seed}:{lo}:{hi}".encode('utf-8')).hexdigest(), 16
    )


def edge_exists(node_a: str, node_b: str, ctx: GraphContext) -> bool:
    """Does the ideal graph contain the edge between these two nodes?

    Symmetric by construction: both endpoints order the index pair the same
    way, so they independently agree on the edge without coordinating.
    """
    if node_a == node_b:
        return False

    index_a = ctx.indices.get(node_a)
    index_b = ctx.indices.get(node_b)
    if index_a is None or index_b is None:
        return False

    threshold = int(_MAX_HASH * ctx.probability)
    return _edge_hash(ctx.seed, index_a, index_b) <= threshold


def determine_neighbors(node_id: str, ctx: GraphContext) -> List[str]:
    """The ideal-graph neighbours of node_id, in canonical index order."""
    if node_id not in ctx.indices:
        raise ValueError(f"Node {node_id} is not part of this graph context")

    neighbors = [
        other_id for other_id in ctx.node_ids
        if other_id != node_id and edge_exists(node_id, other_id, ctx)
    ]

    logger.info(
        f"Node {node_id} (index {ctx.indices[node_id]}) has "
        f"{len(neighbors)} neighbors (p={ctx.probability})"
    )
    return neighbors


def build_ideal_graph(ctx: GraphContext) -> Dict[str, Set[str]]:
    """The full ideal graph G_c as an adjacency map. Symmetric by construction."""
    return {
        node_id: set(determine_neighbors(node_id, ctx))
        for node_id in ctx.node_ids
    }


def compute_exclusions(
    certification_graph: Dict[str, Any],
    eta_e: float
) -> Set[str]:
    """
    eta_E exclusion pass. Any node whose failure rate exceeds eta_e gets
    kicked out of the final tally. Accepts both list-of-edge-objects
    (runtime format) and dict-of-dicts.
    """
    if not 0.0 <= eta_e <= 1.0:
        raise ValueError(f"eta_e must be between 0 and 1, got {eta_e}")

    excluded_nodes = set()

    for node_id, edges in certification_graph.items():
        if not edges:
            continue

        total_edges = len(edges)

        failed_edges = 0
        if isinstance(edges, list):
            for edge in edges:
                if hasattr(edge, 'verified'):
                    # CertificationEdge object
                    if not edge.verified:
                        failed_edges += 1
                elif isinstance(edge, dict):
                    # Dict with 'verified' key
                    if not edge.get('verified', False):
                        failed_edges += 1
        elif isinstance(edges, dict):
            failed_edges = sum(
                1 for neighbor_id, edge_data in edges.items()
                if isinstance(edge_data, dict) and not edge_data.get('verified', False)
            )

        failure_rate = failed_edges / total_edges
        if failure_rate > eta_e:
            excluded_nodes.add(node_id)
            logger.info(
                f"Node {node_id} excluded: {failed_edges}/{total_edges} failed "
                f"({failure_rate:.2%} > {eta_e:.2%})"
            )
        else:
            logger.debug(
                f"Node {node_id} valid: {failed_edges}/{total_edges} failed "
                f"({failure_rate:.2%} <= {eta_e:.2%})"
            )

    logger.info(f"Total excluded nodes: {len(excluded_nodes)}")
    return excluded_nodes


def validate_certification_graph(
    certification_graph: Dict[str, List[Any]],
    registered_nodes: List[str]
) -> bool:
    """Sanity check: every node and edge target in the graph must be in the registered set."""
    registered_set = set(registered_nodes)

    for node_id in certification_graph.keys():
        if node_id not in registered_set:
            logger.error(f"Invalid graph: Node {node_id} not in registered list")
            return False

    for node_id, edges in certification_graph.items():
        for edge in edges:
            to_node = None
            if hasattr(edge, 'to_node'):
                to_node = edge.to_node
            elif isinstance(edge, dict) and 'to_node' in edge:
                to_node = edge['to_node']

            if to_node is not None and to_node not in registered_set:
                logger.error(f"Invalid edge: {node_id} -> {to_node} (target not registered)")
                return False

    logger.info("Certification graph validation passed")
    return True
