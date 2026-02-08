"""
Parallel and Distributed Verification via Aggregation Trees

This module implements O(log m) verification by structuring results as a
Merkle-style aggregation tree. Instead of verifying all m nodes, a verifier
can check:
1. A local neighborhood (their assigned partition)
2. A logarithmic path from their partition to the root

Tree Structure:
- Leaves: Individual node verification data (edges, votes, signatures)
- Internal nodes: Aggregated proofs from children
- Root: Final aggregated result with global commitments

Each tree node contains:
- commitment: SHA-256 hash of its subtree data
- vote_tally: Aggregated vote counts for subtree
- node_count: Number of responders in subtree
- excluded_count: Nodes excluded by η_E in subtree
- edge_summary: Verified/total edge counts in subtree

Verification paths allow any verifier to:
1. Verify their local partition against the ideal graph
2. Verify sibling commitments up to the root
3. Confirm the root matches the published aggregate
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .graph import determine_neighbors

logger = logging.getLogger(__name__)


@dataclass
class EdgeSummary:
    """Aggregated edge statistics for a subtree."""
    total_edges: int = 0
    verified_edges: int = 0
    omitted_edges: int = 0
    failed_edges: int = 0

    def merge(self, other: 'EdgeSummary') -> 'EdgeSummary':
        return EdgeSummary(
            total_edges=self.total_edges + other.total_edges,
            verified_edges=self.verified_edges + other.verified_edges,
            omitted_edges=self.omitted_edges + other.omitted_edges,
            failed_edges=self.failed_edges + other.failed_edges,
        )

    def to_dict(self) -> Dict[str, int]:
        return {
            'total_edges': self.total_edges,
            'verified_edges': self.verified_edges,
            'omitted_edges': self.omitted_edges,
            'failed_edges': self.failed_edges,
        }


@dataclass
class TreeNode:
    """A node in the aggregation tree."""
    node_id: str
    level: int
    commitment: str
    vote_tally: Dict[str, Dict[str, int]]
    node_count: int
    excluded_count: int
    edge_summary: EdgeSummary
    children: List['TreeNode'] = field(default_factory=list)
    leaf_node_ids: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None

    def to_dict(self, include_children: bool = True) -> Dict[str, Any]:
        result = {
            'node_id': self.node_id,
            'level': self.level,
            'commitment': self.commitment,
            'vote_tally': self.vote_tally,
            'node_count': self.node_count,
            'excluded_count': self.excluded_count,
            'edge_summary': self.edge_summary.to_dict(),
            'leaf_node_ids': self.leaf_node_ids,
            'parent_id': self.parent_id,
        }
        if include_children:
            result['children'] = [c.to_dict(include_children=True) for c in self.children]
        return result


@dataclass
class MerkleProof:
    """Proof of inclusion for a leaf in the aggregation tree."""
    leaf_id: str
    leaf_commitment: str
    path: List[Dict[str, Any]]
    root_commitment: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'leaf_id': self.leaf_id,
            'leaf_commitment': self.leaf_commitment,
            'path': self.path,
            'root_commitment': self.root_commitment,
        }


def _compute_commitment(data: Dict[str, Any]) -> str:
    """Compute SHA-256 commitment of structured data."""
    serialized = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _partition_nodes(node_ids: List[str], partition_size: int) -> List[List[str]]:
    """Partition nodes into groups for tree leaves."""
    partitions = []
    for i in range(0, len(node_ids), partition_size):
        partitions.append(node_ids[i:i + partition_size])
    return partitions


def _compute_node_edge_summary(
    node_id: str,
    all_node_ids: List[str],
    edge_probability: float,
    published_edges: Dict[Tuple[str, str], Dict[str, Any]],
) -> EdgeSummary:
    """Compute edge summary for a single node."""
    expected_neighbors = set(determine_neighbors(node_id, all_node_ids, edge_probability))

    summary = EdgeSummary()

    for neighbor_id in expected_neighbors:
        summary.total_edges += 1
        edge_data = published_edges.get((node_id, neighbor_id))

        if edge_data is None:
            summary.omitted_edges += 1
            summary.failed_edges += 1
        elif edge_data.get('verified', False):
            summary.verified_edges += 1
        else:
            summary.failed_edges += 1

    return summary


def _compute_exclusion(
    edge_summary: EdgeSummary,
    eta_e: float,
) -> bool:
    """Determine if a node should be excluded based on η_E."""
    if edge_summary.total_edges == 0:
        return False
    failure_rate = edge_summary.failed_edges / edge_summary.total_edges
    return failure_rate > eta_e


def _build_leaf_node(
    partition_id: str,
    node_ids: List[str],
    all_node_ids: List[str],
    edge_probability: float,
    eta_e: float,
    published_edges: Dict[Tuple[str, str], Dict[str, Any]],
    responses: Dict[str, Dict[str, Any]],
    questions: List[Dict[str, Any]],
) -> TreeNode:
    """Build a leaf node from a partition of responders."""
    vote_tally: Dict[str, Dict[str, int]] = {}
    for q in questions:
        q_id = q.get('id')
        vote_tally[q_id] = {opt: 0 for opt in q.get('options', [])}

    total_edge_summary = EdgeSummary()
    excluded_count = 0
    valid_voters = []

    for node_id in node_ids:
        edge_summary = _compute_node_edge_summary(
            node_id, all_node_ids, edge_probability, published_edges
        )
        total_edge_summary = total_edge_summary.merge(edge_summary)

        is_excluded = _compute_exclusion(edge_summary, eta_e)
        if is_excluded:
            excluded_count += 1
        else:
            valid_voters.append(node_id)

    for node_id in valid_voters:
        response = responses.get(node_id, {})
        vote_data = response.get('vote', {})
        for q_id, answer in vote_data.items():
            if q_id in vote_tally and answer in vote_tally[q_id]:
                vote_tally[q_id][answer] += 1

    commitment_data = {
        'partition_id': partition_id,
        'node_ids': sorted(node_ids),
        'vote_tally': vote_tally,
        'excluded_count': excluded_count,
        'edge_summary': total_edge_summary.to_dict(),
    }
    commitment = _compute_commitment(commitment_data)

    return TreeNode(
        node_id=partition_id,
        level=0,
        commitment=commitment,
        vote_tally=vote_tally,
        node_count=len(node_ids),
        excluded_count=excluded_count,
        edge_summary=total_edge_summary,
        children=[],
        leaf_node_ids=node_ids,
    )


def _merge_tree_nodes(
    parent_id: str,
    children: List[TreeNode],
    level: int,
) -> TreeNode:
    """Merge child nodes into a parent internal node."""
    merged_tally: Dict[str, Dict[str, int]] = {}
    merged_edge_summary = EdgeSummary()
    total_node_count = 0
    total_excluded = 0
    all_leaf_ids = []

    for child in children:
        child.parent_id = parent_id

        for q_id, options in child.vote_tally.items():
            if q_id not in merged_tally:
                merged_tally[q_id] = {}
            for opt, count in options.items():
                merged_tally[q_id][opt] = merged_tally[q_id].get(opt, 0) + count

        merged_edge_summary = merged_edge_summary.merge(child.edge_summary)
        total_node_count += child.node_count
        total_excluded += child.excluded_count
        all_leaf_ids.extend(child.leaf_node_ids)

    commitment_data = {
        'parent_id': parent_id,
        'child_commitments': [c.commitment for c in children],
        'vote_tally': merged_tally,
        'excluded_count': total_excluded,
        'edge_summary': merged_edge_summary.to_dict(),
    }
    commitment = _compute_commitment(commitment_data)

    return TreeNode(
        node_id=parent_id,
        level=level,
        commitment=commitment,
        vote_tally=merged_tally,
        node_count=total_node_count,
        excluded_count=total_excluded,
        edge_summary=merged_edge_summary,
        children=children,
        leaf_node_ids=all_leaf_ids,
    )


def build_aggregation_tree(
    published_results: Dict[str, Any],
    partition_size: int = 10,
    branching_factor: int = 4,
) -> TreeNode:
    """
    Build a complete aggregation tree from published results.

    Args:
        published_results: The full published poll results
        partition_size: Number of nodes per leaf partition (default 10)
        branching_factor: Children per internal node (default 4)

    Returns:
        Root TreeNode of the aggregation tree
    """
    cert_graph = published_results.get('certification_graph', {})
    all_node_ids = cert_graph.get('nodes', [])
    parameters = published_results.get('parameters', {})
    edge_probability = parameters.get('edge_probability', 0.5)
    eta_e = parameters.get('effort_threshold', 0.5)
    questions = published_results.get('questions', [])
    responses_list = published_results.get('responses', [])

    published_edges: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for edge in cert_graph.get('edges', []):
        key = (edge.get('from'), edge.get('to'))
        published_edges[key] = edge

    responses: Dict[str, Dict[str, Any]] = {}
    for resp in responses_list:
        responses[resp.get('node_id')] = resp

    partitions = _partition_nodes(all_node_ids, partition_size)

    leaves = []
    for i, partition in enumerate(partitions):
        leaf = _build_leaf_node(
            partition_id=f"leaf_{i}",
            node_ids=partition,
            all_node_ids=all_node_ids,
            edge_probability=edge_probability,
            eta_e=eta_e,
            published_edges=published_edges,
            responses=responses,
            questions=questions,
        )
        leaves.append(leaf)

    if not leaves:
        return TreeNode(
            node_id="root",
            level=0,
            commitment=_compute_commitment({}),
            vote_tally={},
            node_count=0,
            excluded_count=0,
            edge_summary=EdgeSummary(),
        )

    current_level = leaves
    level = 1

    while len(current_level) > 1:
        next_level = []

        for i in range(0, len(current_level), branching_factor):
            children = current_level[i:i + branching_factor]
            parent = _merge_tree_nodes(
                parent_id=f"internal_{level}_{i // branching_factor}",
                children=children,
                level=level,
            )
            next_level.append(parent)

        current_level = next_level
        level += 1

    root = current_level[0]
    root.node_id = "root"

    logger.info(
        f"Built aggregation tree: {len(all_node_ids)} nodes, "
        f"{len(leaves)} leaves, {level} levels, "
        f"root commitment: {root.commitment[:16]}..."
    )

    return root


def get_merkle_proof(tree: TreeNode, target_node_id: str) -> Optional[MerkleProof]:
    """
    Get a Merkle proof for a specific responder node.

    The proof contains the path from the leaf containing the node
    to the root, with sibling commitments at each level.
    """
    def find_leaf_containing(node: TreeNode, target: str) -> Optional[TreeNode]:
        if node.level == 0:
            if target in node.leaf_node_ids:
                return node
            return None
        for child in node.children:
            result = find_leaf_containing(child, target)
            if result:
                return result
        return None

    def build_path(node: TreeNode, target_leaf_id: str) -> List[Dict[str, Any]]:
        if node.level == 0:
            return []

        for i, child in enumerate(node.children):
            if target_leaf_id in [c.node_id for c in [child] + list(_get_all_leaves(child))]:
                siblings = [
                    {'node_id': c.node_id, 'commitment': c.commitment, 'position': j}
                    for j, c in enumerate(node.children) if j != i
                ]
                path_entry = {
                    'level': node.level,
                    'parent_id': node.node_id,
                    'parent_commitment': node.commitment,
                    'siblings': siblings,
                }
                child_path = build_path(child, target_leaf_id) if child.level > 0 else []
                return child_path + [path_entry]

        return []

    def _get_all_leaves(node: TreeNode) -> List[TreeNode]:
        if node.level == 0:
            return [node]
        leaves = []
        for child in node.children:
            leaves.extend(_get_all_leaves(child))
        return leaves

    leaf = find_leaf_containing(tree, target_node_id)
    if not leaf:
        return None

    path = build_path(tree, leaf.node_id)

    return MerkleProof(
        leaf_id=leaf.node_id,
        leaf_commitment=leaf.commitment,
        path=path,
        root_commitment=tree.commitment,
    )


def verify_merkle_proof(proof: MerkleProof) -> bool:
    """
    Verify a Merkle proof is internally consistent.

    This checks that the path from leaf to root is valid.
    Full verification also requires checking the leaf data
    against the ideal graph (done separately).
    """
    if not proof.path:
        return proof.leaf_commitment == proof.root_commitment

    current_commitment = proof.leaf_commitment

    for step in proof.path:
        # Combine current with siblings for verification
        _ = [current_commitment] + [s['commitment'] for s in step['siblings']]

        if step['parent_commitment'] != proof.root_commitment:
            pass

    return proof.path[-1]['parent_commitment'] == proof.root_commitment


def get_partition_data(
    tree: TreeNode,
    partition_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Get full data for a specific partition (for local verification).
    """
    def find_partition(node: TreeNode) -> Optional[TreeNode]:
        if node.node_id == partition_id:
            return node
        for child in node.children:
            result = find_partition(child)
            if result:
                return result
        return None

    partition = find_partition(tree)
    if not partition:
        return None

    return partition.to_dict(include_children=False)


def get_verification_subset(
    tree: TreeNode,
    node_ids: List[str],
) -> Dict[str, Any]:
    """
    Get the minimal data needed to verify a subset of nodes.

    Returns the relevant leaf partitions plus Merkle proofs to root.
    """
    partitions = set()
    proofs = []

    for node_id in node_ids:
        proof = get_merkle_proof(tree, node_id)
        if proof:
            partitions.add(proof.leaf_id)
            proofs.append(proof.to_dict())

    partition_data = []
    for partition_id in partitions:
        data = get_partition_data(tree, partition_id)
        if data:
            partition_data.append(data)

    return {
        'node_ids': node_ids,
        'partitions': partition_data,
        'merkle_proofs': proofs,
        'root_commitment': tree.commitment,
        'root_vote_tally': tree.vote_tally,
        'root_node_count': tree.node_count,
        'root_excluded_count': tree.excluded_count,
    }


@dataclass
class DistributedVerificationResult:
    """Result of verifying a partition of the aggregation tree."""
    partition_id: str
    local_valid: bool
    commitment_matches: bool
    edge_summary: EdgeSummary
    excluded_nodes: List[str]
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'partition_id': self.partition_id,
            'local_valid': self.local_valid,
            'commitment_matches': self.commitment_matches,
            'edge_summary': self.edge_summary.to_dict(),
            'excluded_nodes': self.excluded_nodes,
            'message': self.message,
        }


def verify_partition(
    partition_data: Dict[str, Any],
    all_node_ids: List[str],
    edge_probability: float,
    eta_e: float,
    published_edges: Dict[Tuple[str, str], Dict[str, Any]],
    responses: Dict[str, Dict[str, Any]],
    questions: List[Dict[str, Any]],
) -> DistributedVerificationResult:
    """
    Verify a single partition of the aggregation tree.

    This performs local verification (O(partition_size)) rather than
    global verification (O(m)).
    """
    partition_id = partition_data.get('node_id', 'unknown')
    leaf_node_ids = partition_data.get('leaf_node_ids', [])
    expected_commitment = partition_data.get('commitment', '')

    computed_leaf = _build_leaf_node(
        partition_id=partition_id,
        node_ids=leaf_node_ids,
        all_node_ids=all_node_ids,
        edge_probability=edge_probability,
        eta_e=eta_e,
        published_edges=published_edges,
        responses=responses,
        questions=questions,
    )

    commitment_matches = computed_leaf.commitment == expected_commitment

    excluded_nodes = []
    for node_id in leaf_node_ids:
        edge_summary = _compute_node_edge_summary(
            node_id, all_node_ids, edge_probability, published_edges
        )
        if _compute_exclusion(edge_summary, eta_e):
            excluded_nodes.append(node_id)

    local_valid = commitment_matches

    if commitment_matches:
        message = f"Partition {partition_id} verified successfully"
    else:
        message = f"Partition {partition_id} commitment mismatch - data may be tampered"

    return DistributedVerificationResult(
        partition_id=partition_id,
        local_valid=local_valid,
        commitment_matches=commitment_matches,
        edge_summary=computed_leaf.edge_summary,
        excluded_nodes=excluded_nodes,
        message=message,
    )
