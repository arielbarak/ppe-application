"""
Pydantic models for verification (Protocol 6)
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class VerificationRequest(BaseModel):
    """Verification request (Protocol 6)"""
    mode: Literal["local", "global"] = Field(..., description="Verification mode")
    node_id: Optional[str] = Field(None, description="Node ID for local verification")


class VerificationDetails(BaseModel):
    """Detailed verification information from Protocol 6 graph reconstruction"""
    total_nodes: int
    valid_nodes: int
    excluded_nodes_count: int
    edge_verification_passed: bool
    validity_check_passed: Optional[bool] = None

    # Threshold parameters
    eta_e: Optional[float] = Field(None, description="η_E effort threshold used")
    eta_v: Optional[float] = Field(None, description="η_V validity threshold used")
    max_allowed_exclusions: Optional[float] = None

    # Independent graph audit fields (Protocol 6 paper compliance)
    # These are computed by reconstructing the ideal graph from SHA-256 hashes
    ideal_edge_count: Optional[int] = Field(
        None, description="Edges in reconstructed ideal graph G_c"
    )
    published_edge_count: Optional[int] = Field(
        None, description="Edges in pollster's published graph"
    )
    matched_edge_count: Optional[int] = Field(
        None, description="Edges matching between ideal and published"
    )
    omitted_edge_count: Optional[int] = Field(
        None, description="Edges in ideal but missing from published (treated as failures)"
    )
    fabricated_edge_count: Optional[int] = Field(
        None, description="Edges in published but not in ideal (critical error)"
    )
    asymmetric_edge_count: Optional[int] = Field(
        None, description="Edges that exist only in one direction"
    )
    unverified_edge_count: Optional[int] = Field(
        None, description="Edges published but marked as unverified"
    )

    # Node consistency fields
    missing_node_count: Optional[int] = Field(
        None, description="Nodes that voted but aren't in published node list"
    )
    extra_node_count: Optional[int] = Field(
        None, description="Nodes in graph that never voted"
    )

    # Detailed discrepancy lists (truncated for large results)
    omitted_edges: Optional[List[tuple]] = Field(
        None, description="Sample of omitted edge pairs [(from, to), ...]"
    )
    fabricated_edges: Optional[List[tuple]] = Field(
        None, description="Sample of fabricated edge pairs"
    )
    asymmetric_edges: Optional[List[tuple]] = Field(
        None, description="Sample of asymmetric edge pairs"
    )
    missing_nodes: Optional[List[str]] = Field(
        None, description="Sample of missing node IDs"
    )

    message: Optional[str] = None


class VerificationResponse(BaseModel):
    """Verification result (Protocol 6)"""
    verification: Literal["ACCEPT", "REJECT", "INVALID"]
    tally: Dict[str, Dict[str, int]]  # {question_id: {option: count}}
    excluded_nodes: List[str]
    details: VerificationDetails
