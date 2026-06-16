"""Helpers for building polls and walking the protocol in tests."""

import json
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from app.crypto.graph import compute_node_id, determine_neighbors
from app.storage.memory import InMemoryStorage

from .keypair_factory import sign_b64


def _keypair_index(keypairs: List) -> Dict[str, tuple]:
    """Map node_id -> (private_key, public_key_b64) from (priv, pub, pub_b64, node_id) tuples."""
    return {kp[3]: (kp[0], kp[2]) for kp in keypairs}


def _canonical_vote_message(vote: Dict[str, Any]) -> str:
    """Match the frontend's JSON.stringify(vote): compact, insertion-ordered JSON."""
    return json.dumps(vote, separators=(",", ":"), ensure_ascii=False)


def _edge_message(from_node: str, to_node: str, from_pub_b64: str) -> str:
    """Message signed for a directed edge (from->to): carries the *from* node's pubkey."""
    edge_label = "-".join(sorted([from_node, to_node]))
    return f"PPE:{edge_label}:{from_pub_b64}"


def signed_vote_payload(
    keypair,
    vote: Dict[str, str],
    signatures: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Build a /vote request body with a genuine self-signature over the ballot."""
    priv, _pub, pub_b64, node_id = keypair
    return {
        "node_id": node_id,
        "vote": vote,
        "signatures": signatures or [],
        "signature": sign_b64(priv, _canonical_vote_message(vote)),
    }


# Five reproducible node IDs derived from fixed pubkey strings. Use these wherever
# graph behavior at a given p must be deterministic across runs.
STABLE_NODE_IDS: List[str] = [
    compute_node_id(f"test_pubkey_{i}") for i in range(5)
]


def build_small_poll_payload(
    m: int = 4,
    edge_probability: float = 0.5,
    effort_threshold: float = 0.2,
    validity_threshold: float = 0.025,
    ppe_type: str = "math_captcha",
) -> Dict[str, Any]:
    """Build a request body for POST /api/poll/create with two questions."""
    _ = m  # m is the expected responder count; not part of the create payload
    return {
        "questions": [
            {
                "id": "q1",
                "text": "First question?",
                "options": ["opt0", "opt1"],
            },
            {
                "id": "q2",
                "text": "Second question?",
                "options": ["opt0", "opt1"],
            },
        ],
        "edge_probability": edge_probability,
        "effort_threshold": effort_threshold,
        "validity_threshold": validity_threshold,
        "ppe_type": ppe_type,
    }


def solve_math_captcha(question: str) -> str:
    """Mirror MathCaptchaPPE.validate parsing; produces the expected answer."""
    parts = question.replace("?", "").replace("=", "").strip().split()
    if len(parts) != 3:
        raise ValueError(f"Unparseable challenge: {question!r}")
    a, op, b = int(parts[0]), parts[1], int(parts[2])
    if op == "+":
        return str(a + b)
    if op == "-":
        return str(a - b)
    if op == "*":
        return str(a * b)
    raise ValueError(f"Unknown operator: {op}")


def register_n_nodes(
    client: TestClient,
    session_id: str,
    n: int,
    keypairs: List,
) -> List[str]:
    """Walk CAPTCHA -> register for n responders; returns the list of node_ids."""
    if n > len(keypairs):
        raise ValueError(f"Need {n} keypairs, only {len(keypairs)} available")

    node_ids: List[str] = []
    for i in range(n):
        captcha_resp = client.get(f"/api/poll/{session_id}/captcha")
        assert captcha_resp.status_code == 200, captcha_resp.text
        captcha_data = captcha_resp.json()
        token = captcha_data["token"]
        question = captcha_data["challenge"]
        solution = solve_math_captcha(question)

        _, _, pub_b64, node_id = keypairs[i]

        reg_resp = client.post(
            f"/api/poll/{session_id}/register",
            json={
                "pseudonym": pub_b64,
                "captcha_solution": solution,
                "captcha_token": token,
            },
        )
        assert reg_resp.status_code == 200, reg_resp.text
        body = reg_resp.json()
        assert body["registered"] is True
        assert body["node_id"] == node_id
        node_ids.append(node_id)

    return node_ids


def complete_certification_for_all(
    storage: InMemoryStorage,
    session_id: str,
    node_ids: List[str],
    edge_probability: float,
    *,
    verified: bool = True,
    signature: str = "test-signature",
    keypairs: Optional[List] = None,
) -> int:
    """Seed every ideal-graph edge as a verified directed edge in storage. Returns edges added.

    When ``keypairs`` is provided, each directed edge (from->to) is stamped with
    a *genuine* signature: the recorded signature for (A->B) is B's signature
    over ``PPE:{sorted(A,B)}:{pubkey(A)}``, matching the real p2p handshake. This
    is required for tests that exercise the signature-checking verification path.
    Without keypairs the legacy placeholder ``signature`` string is used (only
    safe when the published results carry no public keys).
    """
    index = _keypair_index(keypairs) if keypairs else {}
    added = 0
    for node_id in node_ids:
        neighbors = determine_neighbors(node_id, node_ids, edge_probability)
        for neighbor in neighbors:
            edge_sig = signature
            if verified and index:
                from_pub_b64 = index[node_id][1]
                signer_priv = index[neighbor][0]  # edge (A->B) carries B's signature
                edge_sig = sign_b64(signer_priv, _edge_message(node_id, neighbor, from_pub_b64))
            storage.add_certification_edge(
                session_id=session_id,
                from_node=node_id,
                to_node=neighbor,
                verified=verified,
                signature=edge_sig,
            )
            added += 1
    return added
