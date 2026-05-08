"""Build canonical published_results dicts that match storage.publish_results() output."""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from app.crypto.graph import determine_neighbors


def build_published_results(
    node_ids: List[str],
    edge_probability: float,
    votes: Optional[Dict[str, Dict[str, str]]] = None,
    effort_threshold: float = 0.2,
    validity_threshold: float = 0.025,
    questions: Optional[List[Dict[str, Any]]] = None,
    ppe_type: str = "math_captcha",
    public_key: str = "test-pubkey-b64",
    session_id: str = "test-session",
    edge_signature: str = "test-edge-sig",
    self_signature: str = "test-self-sig",
    voter_signatures: Optional[List[Dict[str, str]]] = None,
    extra_edges: Optional[Iterable[tuple]] = None,
    drop_edges: Optional[Iterable[tuple]] = None,
    mark_unverified_edges: Optional[Iterable[tuple]] = None,
) -> Dict[str, Any]:
    """
    Assemble a published_results dict matching the shape produced by
    storage.publish_results(). Designed to be mutated by tests via copy.deepcopy
    plus targeted overrides.

    Behavior:
    - Generates the symmetric ideal graph for `node_ids` at `edge_probability`.
    - `extra_edges`: list of (from, to) pairs added on top (used to forge fabrications).
    - `drop_edges`: ideal edges to omit (used to test omission detection).
    - `mark_unverified_edges`: ideal edges kept but with verified=False.
    - `votes` defaults to every node voting opt0 on q1 and q2.
    """
    if questions is None:
        questions = [
            {"id": "q1", "text": "First question?", "options": ["opt0", "opt1"]},
            {"id": "q2", "text": "Second question?", "options": ["opt0", "opt1"]},
        ]

    if votes is None:
        votes = {nid: {q["id"]: q["options"][0] for q in questions} for nid in node_ids}

    drop_set = set(drop_edges or [])
    unverified_set = set(mark_unverified_edges or [])
    timestamp = datetime(2024, 1, 1, 12, 0, 0).isoformat()

    edges: List[Dict[str, Any]] = []
    for node_id in node_ids:
        for neighbor in determine_neighbors(node_id, node_ids, edge_probability):
            if (node_id, neighbor) in drop_set:
                continue
            edges.append({
                "from": node_id,
                "to": neighbor,
                "verified": (node_id, neighbor) not in unverified_set,
                "signature": edge_signature,
                "timestamp": timestamp,
            })

    for from_node, to_node in (extra_edges or []):
        edges.append({
            "from": from_node,
            "to": to_node,
            "verified": True,
            "signature": edge_signature,
            "timestamp": timestamp,
        })

    responses = []
    for node_id, vote in votes.items():
        responses.append({
            "node_id": node_id,
            "vote": vote,
            "signatures": voter_signatures if voter_signatures is not None else [],
            "self_signature": self_signature,
            "timestamp": timestamp,
        })

    return {
        "session_id": session_id,
        "public_key": public_key,
        "questions": questions,
        "parameters": {
            "edge_probability": edge_probability,
            "effort_threshold": effort_threshold,
            "validity_threshold": validity_threshold,
            "ppe_type": ppe_type,
        },
        "responses": responses,
        "certification_graph": {
            "nodes": list(node_ids),
            "edges": edges,
        },
        "published_at": timestamp,
    }
