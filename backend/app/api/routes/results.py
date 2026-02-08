"""Protocol 5: Publish poll results for public verification."""

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Header, Query, Body

from app.models import (
    PublishResultsResponse,
    ResultsResponse,
    EdgeSummaryModel,
    TreeNodeModel,
)
from app.storage import storage
from app.api.websocket import manager
from app.crypto.aggregation_tree import (
    build_aggregation_tree,
    get_merkle_proof,
    get_verification_subset,
    get_partition_data,
    TreeNode,
)
from app.crypto.verification import verify_global, verify_local
from .helpers import get_session_or_404, require_status, get_session_with_published_results

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache for aggregation trees (in production, use Redis or similar)
_tree_cache: dict = {}


@router.post("/{session_id}/publish", response_model=PublishResultsResponse)
async def publish_results(
    session_id: str,
    x_pollster_key: Optional[str] = Header(None, alias="X-Pollster-Key")
):
    """Freeze and publish all session data (votes, graph, signatures) as a public bulletin."""
    session = get_session_or_404(session_id)
    require_status(session, "voting", "publish results")

    # TODO: verify pollster key matches session.public_key
    if not x_pollster_key:
        logger.warning("Publishing without pollster key verification")

    published_results = storage.publish_results(session_id)

    if not published_results:
        raise HTTPException(
            status_code=500,
            detail="Failed to publish results"
        )

    results_url = f"/api/poll/{session_id}/results"

    await manager.notify_results_published(session_id, results_url)

    logger.info(f"Results published for session {session_id}")

    return PublishResultsResponse(
        published=True,
        results_url=results_url
    )


@router.get("/{session_id}/results", response_model=ResultsResponse)
async def get_results(session_id: str):
    """Fetch published results for independent verification (O(m) full verification)."""
    _, published_results = get_session_with_published_results(session_id)
    return ResultsResponse(**published_results)


def _get_or_build_tree(session_id: str, partition_size: int = 10) -> TreeNode:
    """Get cached tree or build a new one."""
    cache_key = f"{session_id}:{partition_size}"

    if cache_key in _tree_cache:
        return _tree_cache[cache_key]

    published_results = storage.get_published_results(session_id)
    if not published_results:
        raise HTTPException(status_code=404, detail="Published results not found")

    tree = build_aggregation_tree(published_results, partition_size=partition_size)
    _tree_cache[cache_key] = tree

    return tree


def _tree_node_to_model(node: TreeNode, include_children: bool = True) -> TreeNodeModel:
    """Convert TreeNode dataclass to Pydantic model."""
    children = None
    if include_children and node.children:
        children = [_tree_node_to_model(c, include_children=True) for c in node.children]

    return TreeNodeModel(
        node_id=node.node_id,
        level=node.level,
        commitment=node.commitment,
        vote_tally=node.vote_tally,
        node_count=node.node_count,
        excluded_count=node.excluded_count,
        edge_summary=EdgeSummaryModel(**node.edge_summary.to_dict()),
        leaf_node_ids=node.leaf_node_ids,
        parent_id=node.parent_id,
        children=children,
    )


def _count_tree_depth(node: TreeNode) -> int:
    """Count the depth of the tree."""
    if not node.children:
        return 1
    return 1 + max(_count_tree_depth(c) for c in node.children)


def _count_leaves(node: TreeNode) -> int:
    """Count leaf nodes in the tree."""
    if node.level == 0:
        return 1
    return sum(_count_leaves(c) for c in node.children)


@router.get("/{session_id}/results/distributed")
async def get_distributed_results(
    session_id: str,
    partition_size: int = Query(10, ge=1, le=100, description="Nodes per partition"),
    include_full_tree: bool = Query(False, description="Include full tree structure"),
):
    """
    Fetch results structured for parallel/distributed verification.

    This returns an aggregation tree that enables O(log m) verification:
    - Each partition can be verified independently
    - Merkle proofs connect partitions to the root
    - Multiple verifiers can work in parallel

    Args:
        partition_size: Number of nodes per leaf partition (default 10)
        include_full_tree: Whether to include all tree nodes or just root

    Returns:
        DistributedResultsResponse with tree structure and commitments
    """
    _, published_results = get_session_with_published_results(session_id)
    tree = _get_or_build_tree(session_id, partition_size)
    tree_root = _tree_node_to_model(tree, include_children=include_full_tree)

    return {
        'session_id': session_id,
        'public_key': published_results.get('public_key'),
        'questions': published_results.get('questions', []),
        'parameters': published_results.get('parameters', {}),
        'tree_root': tree_root.model_dump(),
        'tree_depth': _count_tree_depth(tree),
        'partition_count': _count_leaves(tree),
        'partition_size': partition_size,
        'total_nodes': tree.node_count,
        'total_excluded': tree.excluded_count,
        'final_tally': tree.vote_tally,
        'published_at': published_results.get('published_at'),
        'verification_complexity': {
            'full_verification': f"O({tree.node_count})",
            'distributed_verification': f"O({partition_size} + log({_count_leaves(tree)}))",
        },
    }


@router.get("/{session_id}/results/partition/{partition_id}")
async def get_partition(
    session_id: str,
    partition_id: str,
    partition_size: int = Query(10, ge=1, le=100),
):
    """
    Get data for a specific partition for local verification.

    Returns the partition data plus a Merkle proof to the root.
    """
    get_session_with_published_results(session_id)
    tree = _get_or_build_tree(session_id, partition_size)

    partition_data = get_partition_data(tree, partition_id)
    if not partition_data:
        raise HTTPException(status_code=404, detail=f"Partition {partition_id} not found")

    if partition_data.get('leaf_node_ids'):
        first_node = partition_data['leaf_node_ids'][0]
        proof = get_merkle_proof(tree, first_node)
        if proof:
            partition_data['merkle_proof'] = proof.to_dict()

    partition_data['root_commitment'] = tree.commitment
    partition_data['root_vote_tally'] = tree.vote_tally

    return partition_data


@router.get("/{session_id}/results/proof/{node_id}")
async def get_node_proof(
    session_id: str,
    node_id: str,
    partition_size: int = Query(10, ge=1, le=100),
):
    """
    Get a Merkle proof for a specific node.

    This provides the O(log m) verification path from the node's
    partition to the root of the aggregation tree.
    """
    get_session_with_published_results(session_id)
    tree = _get_or_build_tree(session_id, partition_size)

    proof = get_merkle_proof(tree, node_id)
    if not proof:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found in tree")

    return {
        'node_id': node_id,
        'proof': proof.to_dict(),
        'root_commitment': tree.commitment,
        'verification_path_length': len(proof.path),
    }


@router.post("/{session_id}/results/verify-subset")
async def verify_node_subset(
    session_id: str,
    node_ids: List[str],
    partition_size: int = Query(10, ge=1, le=100),
):
    """
    Get minimal data needed to verify a subset of nodes.

    Returns only the relevant partitions and their Merkle proofs,
    enabling O(k + log m) verification for k nodes instead of O(m).
    """
    get_session_with_published_results(session_id)
    tree = _get_or_build_tree(session_id, partition_size)

    subset_data = get_verification_subset(tree, node_ids)

    subset_data['verification_complexity'] = {
        'nodes_requested': len(node_ids),
        'partitions_needed': len(subset_data['partitions']),
        'full_verification_cost': f"O({tree.node_count})",
        'subset_verification_cost': f"O({len(subset_data['partitions']) * partition_size})",
    }

    return subset_data


@router.get("/{session_id}/results/tree-summary")
async def get_tree_summary(
    session_id: str,
    partition_size: int = Query(10, ge=1, le=100),
):
    """
    Get a summary of the aggregation tree structure.

    Useful for verifiers to understand the tree layout before
    requesting specific partitions.
    """
    get_session_with_published_results(session_id)
    tree = _get_or_build_tree(session_id, partition_size)

    def get_partition_ids(node: TreeNode) -> List[str]:
        if node.level == 0:
            return [node.node_id]
        ids = []
        for child in node.children:
            ids.extend(get_partition_ids(child))
        return ids

    partition_ids = get_partition_ids(tree)

    return {
        'session_id': session_id,
        'tree_depth': _count_tree_depth(tree),
        'partition_count': len(partition_ids),
        'partition_size': partition_size,
        'partition_ids': partition_ids,
        'total_nodes': tree.node_count,
        'total_excluded': tree.excluded_count,
        'root_commitment': tree.commitment,
        'final_tally': tree.vote_tally,
        'edge_summary': tree.edge_summary.to_dict(),
    }


@router.post("/{session_id}/verify")
async def verify_poll(
    session_id: str,
    mode: Literal["global", "local"] = Body(..., embed=True),
    node_id: Optional[str] = Body(None, embed=True),
):
    """
    Run verification on published poll results.

    Modes:
    - global: Full independent verification (Protocol 6). Reconstructs the ideal
              graph and validates all edges, exclusions, and vote tallies.
    - local: Single node verification. Checks if a specific node's vote and
             edges are correctly included.
    """
    session, published_results = get_session_with_published_results(session_id)

    if mode == "global":
        eta_e = session.effort_threshold
        eta_v = session.validity_threshold

        result = verify_global(published_results, eta_e=eta_e, eta_v=eta_v)

        logger.info(
            f"Global verification for {session_id}: {result['verification']}"
        )

        return result

    elif mode == "local":
        if not node_id:
            raise HTTPException(
                status_code=400,
                detail="node_id is required for local verification"
            )

        success, message, details = verify_local(node_id, published_results)

        logger.info(
            f"Local verification for {node_id} in {session_id}: "
            f"{'PASS' if success else 'FAIL'}"
        )

        return {
            'verification': 'ACCEPT' if success else 'REJECT',
            'node_id': node_id,
            'message': message,
            'details': details,
        }

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verification mode: {mode}. Use 'global' or 'local'."
        )
