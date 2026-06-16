"""Build canonical published_results dicts that match storage.publish_results() output."""

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from app.crypto.graph import determine_neighbors

from .keypair_factory import sign_b64


def _canonical_vote_message(vote: Dict[str, Any]) -> str:
    return json.dumps(vote, separators=(",", ":"), ensure_ascii=False)


def _edge_message(from_node: str, to_node: str, from_pub_b64: str) -> str:
    return f"PPE:{'-'.join(sorted([from_node, to_node]))}:{from_pub_b64}"


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
    keypairs: Optional[List] = None,
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

    # When keypairs are supplied, publish the node->pubkey map and stamp every
    # verified edge / ballot with a *genuine* signature so the signature-checking
    # verification path can be exercised. Otherwise fall back to placeholders
    # (verification then has no public keys and skips the signature checks).
    index = {kp[3]: (kp[0], kp[2]) for kp in keypairs} if keypairs else {}
    public_keys = {nid: index[nid][1] for nid in node_ids if nid in index} if index else None

    edges: List[Dict[str, Any]] = []
    for node_id in node_ids:
        for neighbor in determine_neighbors(node_id, node_ids, edge_probability):
            if (node_id, neighbor) in drop_set:
                continue
            verified = (node_id, neighbor) not in unverified_set
            sig = edge_signature
            if verified and index and node_id in index and neighbor in index:
                # edge (A->B) carries B's signature over PPE:{sorted(A,B)}:{pubkey(A)}
                sig = sign_b64(
                    index[neighbor][0],
                    _edge_message(node_id, neighbor, index[node_id][1]),
                )
            edges.append({
                "from": node_id,
                "to": neighbor,
                "verified": verified,
                "signature": sig,
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
        sig = self_signature
        if index and node_id in index:
            sig = sign_b64(index[node_id][0], _canonical_vote_message(vote))
        responses.append({
            "node_id": node_id,
            "public_key": index[node_id][1] if node_id in index else None,
            "vote": vote,
            "signatures": voter_signatures if voter_signatures is not None else [],
            "self_signature": sig,
            "timestamp": timestamp,
        })

    cert_graph: Dict[str, Any] = {
        "nodes": list(node_ids),
        "edges": edges,
    }
    if public_keys is not None:
        cert_graph["public_keys"] = public_keys

    results: Dict[str, Any] = {
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
        "certification_graph": cert_graph,
        "published_at": timestamp,
    }
    if public_keys is not None:
        results["public_keys"] = public_keys
    return results
