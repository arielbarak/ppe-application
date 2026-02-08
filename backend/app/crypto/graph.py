"""
Certification graph primitives (Protocols 3 & 6).

The key idea: edges in the certification graph are NOT chosen by the pollster.
They're derived deterministically from a hash over both node IDs, so any
party can independently recompute the full "ideal graph" from just the
participant list and edge probability p.

  edge(i, j) exists  ⟺  SHA-256(min(i,j) : max(i,j))  ≤  p × MAX_HASH

This module also handles η_E exclusion: if a node fails more than η_E of
its PPE challenges, it's excluded from the final tally.
"""

import hashlib
import logging
from typing import List, Set, Dict, Any

logger = logging.getLogger(__name__)

# Maximum value of a 256-bit SHA-256 hash (64 hex chars of 'f')
_MAX_HASH = int('f' * 64, 16)


def compute_node_id(public_key: str) -> str:
    """SHA-256 of the public key, truncated to 16 hex chars."""
    return hashlib.sha256(public_key.encode('utf-8')).hexdigest()[:16]


def determine_neighbors(
    node_id: str,
    all_node_ids: List[str],
    probability: float
) -> List[str]:
    """
    Deterministic neighbor computation. Both endpoints of a potential edge
    derive the same hash (thanks to min/max ordering), so they independently
    agree on whether the edge exists without any coordination.
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"Probability must be between 0 and 1, got {probability}")

    neighbors = []
    threshold = int(_MAX_HASH * probability)

    for other_id in all_node_ids:
        if other_id == node_id:
            continue

        edge_key = f"{min(node_id, other_id)}:{max(node_id, other_id)}"
        h = int(hashlib.sha256(edge_key.encode('utf-8')).hexdigest(), 16)

        if h <= threshold:
            neighbors.append(other_id)

    logger.info(f"Node {node_id} has {len(neighbors)} neighbors (p={probability})")
    return neighbors


def compute_exclusions(
    certification_graph: Dict[str, Any],
    eta_e: float
) -> Set[str]:
    """
    η_E exclusion pass. Any node whose failure rate exceeds eta_e gets
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
                f"({failure_rate:.2%} ≤ {eta_e:.2%})"
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
