"""Cryptographic utilities for PPE polling system."""

from .graph import compute_node_id, determine_neighbors, compute_exclusions
from .signatures import verify_signature
from .keys import generate_server_keypair, export_public_key
from .params import (
    SecurityParams,
    compute_security_params,
    compute_adversary_advantage,
    compute_validity_threshold_from_advantage,
    recommend_params_for_poll,
    validate_params,
)
from .aggregation_tree import (
    build_aggregation_tree,
    get_merkle_proof,
    verify_merkle_proof,
    get_verification_subset,
    verify_partition,
    TreeNode,
    MerkleProof,
    EdgeSummary,
)

__all__ = [
    "compute_node_id",
    "determine_neighbors",
    "compute_exclusions",
    "verify_signature",
    "generate_server_keypair",
    "export_public_key",
    # Security parameter utilities
    "SecurityParams",
    "compute_security_params",
    "compute_adversary_advantage",
    "compute_validity_threshold_from_advantage",
    "recommend_params_for_poll",
    "validate_params",
    # Aggregation tree for distributed verification
    "build_aggregation_tree",
    "get_merkle_proof",
    "verify_merkle_proof",
    "get_verification_subset",
    "verify_partition",
    "TreeNode",
    "MerkleProof",
    "EdgeSummary",
]
