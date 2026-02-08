"""
Pydantic models for poll creation and management (Protocol 1)
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PollQuestion(BaseModel):
    """A single poll question"""
    id: str = Field(..., description="Unique question identifier")
    text: str = Field(..., description="Question text")
    options: List[str] = Field(..., description="Answer options")


class CreatePollRequest(BaseModel):
    """Request to create a new poll (Protocol 1)"""
    questions: List[PollQuestion] = Field(..., description="List of poll questions")
    edge_probability: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Probability 'p' for certification graph edge existence"
    )
    effort_threshold: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="η_E threshold - fraction of failed PPEs before node exclusion"
    )
    validity_threshold: float = Field(
        0.025,
        ge=0.0,
        le=1.0,
        description="η_V threshold - max fraction of deleted nodes before poll is invalid"
    )
    ppe_type: str = Field(
        "math_captcha",
        description="PPE provider type for certification challenges"
    )


class CreatePollResponse(BaseModel):
    """Response after creating a poll"""
    session_id: str
    public_key: str
    questions: List[PollQuestion]
    parameters: Dict[str, Any]


class PollInfoResponse(BaseModel):
    """Poll session information"""
    session_id: str
    status: str
    questions: List[PollQuestion]
    public_key: str
    parameters: Dict[str, Any]
    registered_nodes_count: Optional[int] = 0
    created_at: str


class CaptchaResponse(BaseModel):
    """CAPTCHA challenge response (Protocol 2)"""
    token: str = Field(..., description="Unique token for this CAPTCHA")
    challenge: str = Field(..., description="The CAPTCHA question")
    expires_at: str = Field(..., description="Expiration timestamp")


class RegisterRequest(BaseModel):
    """Registration request (Protocol 2)"""
    pseudonym: str = Field(..., description="Base64-encoded public key")
    captcha_solution: str = Field(..., description="Solution to CAPTCHA challenge")
    captcha_token: str = Field(..., description="CAPTCHA token from challenge")


class RegisterResponse(BaseModel):
    """Registration response"""
    registered: bool
    node_id: str
    registration_position: int


class NeighborsResponse(BaseModel):
    """Certification graph neighbors (Protocol 3)"""
    neighbors: List[str] = Field(..., description="List of neighbor node IDs")
    graph_parameters: Dict[str, float]
