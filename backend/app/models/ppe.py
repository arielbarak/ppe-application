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


