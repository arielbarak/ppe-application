"""
Pydantic models for PPE, voting, and distributed verification (Protocols 3-6)
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SignatureData(BaseModel):
    """Signature from peer PPE"""
    from_node: str = Field(..., description="Node that provided the signature")
    signature: str = Field(..., description="Base64-encoded signature")
    edge_label: str = Field(..., description="Edge identifier (i-j)")


class VoteRequest(BaseModel):
    """Vote submission request (Protocol 4)"""
    node_id: str = Field(..., description="Voting node's ID")
    vote: Dict[str, str] = Field(..., description="Vote answers {question_id: option}")
    signatures: List[SignatureData] = Field(..., description="Collected peer signatures (Good_i)")
    signature: str = Field(..., description="Self-signature of the vote")


class VoteResponse(BaseModel):
    """Vote submission response"""
    accepted: bool
    vote_id: str


class PublishResultsResponse(BaseModel):
    """Results publication response (Protocol 5)"""
    published: bool
    results_url: str


class EdgeData(BaseModel):
    """Certification graph edge"""
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    verified: bool
    signature: Optional[str] = None
    timestamp: Optional[str] = None

    class Config:
        populate_by_name = True


class ResultsResponse(BaseModel):
    """Published poll results (Protocol 5)"""
    session_id: str
    public_key: str
    questions: List[Dict[str, Any]]
    parameters: Dict[str, Any]  # Contains floats (thresholds) and strings (ppe_type)
    responses: List[Dict[str, Any]]
    certification_graph: Dict[str, Any]
    published_at: str


class EdgeSummaryModel(BaseModel):
    """Aggregated edge statistics for a subtree."""
    total_edges: int
    verified_edges: int
    omitted_edges: int
    failed_edges: int


class TreeNodeModel(BaseModel):
    """A node in the aggregation tree for distributed verification."""
    node_id: str
    level: int
    commitment: str = Field(..., description="SHA-256 commitment of subtree data")
    vote_tally: Dict[str, Dict[str, int]]
    node_count: int
    excluded_count: int
    edge_summary: EdgeSummaryModel
    leaf_node_ids: List[str] = Field(default_factory=list)
    parent_id: Optional[str] = None
    children: Optional[List['TreeNodeModel']] = None

    class Config:
        from_attributes = True


class MerkleProofModel(BaseModel):
    """Merkle proof for O(log m) verification path."""
    leaf_id: str
    leaf_commitment: str
    path: List[Dict[str, Any]] = Field(
        ...,
        description="Path from leaf to root with sibling commitments"
    )
    root_commitment: str


class DistributedResultsResponse(BaseModel):
    """
    Results structured for parallel/distributed verification.

    Instead of O(m) verification, verifiers can:
    1. Verify their assigned partition locally
    2. Verify O(log m) path to root via Merkle proofs
    """
    session_id: str
    public_key: str
    questions: List[Dict[str, Any]]
    parameters: Dict[str, Any]  # Contains floats (thresholds) and strings (ppe_type)

    # Aggregation tree structure
    tree_root: TreeNodeModel = Field(
        ...,
        description="Root of aggregation tree with global commitments"
    )
    tree_depth: int
    partition_count: int
    partition_size: int

    # Summary from root (for quick access)
    total_nodes: int
    total_excluded: int
    final_tally: Dict[str, Dict[str, int]]

    published_at: str


class PartitionVerificationRequest(BaseModel):
    """Request to verify a specific partition."""
    partition_id: str
    node_ids: Optional[List[str]] = Field(
        None,
        description="Optional: specific node IDs to verify within partition"
    )


class PartitionVerificationResponse(BaseModel):
    """Result of verifying a partition."""
    partition_id: str
    local_valid: bool
    commitment_matches: bool
    edge_summary: EdgeSummaryModel
    excluded_nodes: List[str]
    merkle_proof: MerkleProofModel
    message: str


class VerificationSubsetRequest(BaseModel):
    """Request minimal data for verifying specific nodes."""
    node_ids: List[str] = Field(
        ...,
        description="Node IDs to verify"
    )


class VerificationSubsetResponse(BaseModel):
    """Minimal data needed to verify a subset of nodes (O(log m))."""
    node_ids: List[str]
    partitions: List[Dict[str, Any]]
    merkle_proofs: List[MerkleProofModel]
    root_commitment: str
    root_vote_tally: Dict[str, Dict[str, int]]
    root_node_count: int
    root_excluded_count: int
