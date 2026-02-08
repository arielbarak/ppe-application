"""Protocol 3: Certification graph — neighbor computation and PPE status."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query

from app.models import NeighborsResponse
from app.storage import storage
from app.crypto import determine_neighbors
from .helpers import get_session_or_404

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{session_id}/certification/graph")
async def get_certification_graph(session_id: str):
    """Get the current certification graph with all edges for visualization."""
    session = get_session_or_404(session_id)

    if session.status not in ["certification", "voting", "results"]:
        raise HTTPException(
            status_code=400,
            detail=f"Certification graph not available (current status: {session.status})"
        )

    graph = storage.get_certification_graph(session_id)
    registered_nodes = storage.get_registered_nodes(session_id)
    node_ids = [node.node_id for node in registered_nodes]

    # Flatten edges from all nodes
    edges = []
    seen_edges = set()
    for from_node, edge_list in graph.items():
        for edge in edge_list:
            # Create unique edge key (sorted to handle bidirectional)
            edge_key = tuple(sorted([from_node, edge.to_node]))
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({
                    "from": from_node,
                    "to": edge.to_node,
                    "verified": edge.verified,
                })

    return {
        "nodes": node_ids,
        "edges": edges,
        "total_nodes": len(node_ids),
        "total_edges": len(edges),
        "verified_edges": len([e for e in edges if e["verified"]]),
    }


@router.get("/{session_id}/neighbors")
async def get_neighbors(
    session_id: str,
    node_id: Optional[str] = Header(None, alias="X-Node-ID"),
    detailed: bool = Query(False, description="Include public keys and status for each neighbor")
):
    """Return certification neighbors for node_id using deterministic graph: H(min(i,j):max(i,j)) <= p."""
    if not node_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Node-ID header"
        )

    session = get_session_or_404(session_id)

    if session.status not in ["certification", "voting"]:
        raise HTTPException(
            status_code=400,
            detail=f"Poll not in certification phase (current status: {session.status})"
        )

    registered_nodes = storage.get_registered_nodes(session_id)
    all_node_ids = [n.node_id for n in registered_nodes]

    if node_id not in all_node_ids:
        raise HTTPException(
            status_code=403,
            detail=f"Node {node_id} not registered in this poll"
        )

    neighbor_ids = determine_neighbors(
        node_id=node_id,
        all_node_ids=all_node_ids,
        probability=session.edge_probability
    )

    logger.info(f"Node {node_id} has {len(neighbor_ids)} neighbors (p={session.edge_probability})")

    if detailed:
        node_to_pubkey = {n.node_id: n.pseudonym for n in registered_nodes}
        edges = storage.get_node_edges(session_id, node_id)

        neighbors = []
        for nid in neighbor_ids:
            edge = next((e for e in edges if e.to_node == nid), None)
            neighbors.append({
                "node_id": nid,
                "public_key": node_to_pubkey.get(nid, ""),
                "status": "verified" if edge and edge.verified else "failed" if edge else "pending"
            })

        return {
            "neighbors": neighbors,
            "my_public_key": node_to_pubkey.get(node_id, ""),
            "graph_parameters": {
                "edge_probability": session.edge_probability,
                "total_nodes": len(all_node_ids)
            }
        }

    return NeighborsResponse(
        neighbors=neighbor_ids,
        graph_parameters={
            "edge_probability": session.edge_probability,
            "total_nodes": len(all_node_ids)
        }
    )


@router.get("/{session_id}/neighbors/detailed")
async def get_neighbors_detailed(
    session_id: str,
    node_id: Optional[str] = Header(None, alias="X-Node-ID"),
):
    """Return certification neighbors with public keys and status (P2P mode)."""
    if not node_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Node-ID header"
        )

    session = get_session_or_404(session_id)

    if session.status not in ["certification", "voting"]:
        raise HTTPException(
            status_code=400,
            detail=f"Poll not in certification phase (current status: {session.status})"
        )

    registered_nodes = storage.get_registered_nodes(session_id)
    all_node_ids = [n.node_id for n in registered_nodes]

    if node_id not in all_node_ids:
        raise HTTPException(
            status_code=403,
            detail=f"Node {node_id} not registered in this poll"
        )

    neighbor_ids = determine_neighbors(
        node_id=node_id,
        all_node_ids=all_node_ids,
        probability=session.edge_probability
    )

    logger.info(f"Node {node_id} has {len(neighbor_ids)} neighbors (p={session.edge_probability})")

    node_to_pubkey = {n.node_id: n.pseudonym for n in registered_nodes}
    edges = storage.get_node_edges(session_id, node_id)

    neighbors = []
    for nid in neighbor_ids:
        edge = next((e for e in edges if e.to_node == nid), None)
        neighbors.append({
            "node_id": nid,
            "public_key": node_to_pubkey.get(nid, ""),
            "status": "verified" if edge and edge.verified else "failed" if edge else "pending"
        })

    return {
        "neighbors": neighbors,
        "my_public_key": node_to_pubkey.get(node_id, ""),
        "graph_parameters": {
            "edge_probability": session.edge_probability,
            "total_nodes": len(all_node_ids)
        }
    }


@router.get("/{session_id}/certification/status")
async def get_certification_status(
    session_id: str,
    node_id: Optional[str] = Header(None, alias="X-Node-ID")
):
    """PPE progress for node_id: completed vs. total neighbors."""
    if not node_id:
        raise HTTPException(status_code=400, detail="Missing X-Node-ID header")

    session = get_session_or_404(session_id)

    edges = storage.get_node_edges(session_id, node_id)

    registered_nodes = storage.get_registered_nodes(session_id)
    all_node_ids = [n.node_id for n in registered_nodes]
    neighbors = determine_neighbors(
        node_id=node_id,
        all_node_ids=all_node_ids,
        probability=session.edge_probability
    )

    completed_edges = len([e for e in edges if e.verified or (not e.verified)])
    verified_edges = len([e for e in edges if e.verified])

    neighbor_statuses = {}
    for neighbor_id in neighbors:
        edge = next((e for e in edges if e.to_node == neighbor_id), None)
        if edge:
            neighbor_statuses[neighbor_id] = 'verified' if edge.verified else 'failed'
        else:
            neighbor_statuses[neighbor_id] = 'pending'

    return {
        "node_id": node_id,
        "total_neighbors": len(neighbors),
        "completed_edges": completed_edges,
        "verified_edges": verified_edges,
        "pending_edges": len(neighbors) - completed_edges,
        "completion_percentage": (completed_edges / len(neighbors) * 100) if neighbors else 0,
        "neighbor_statuses": neighbor_statuses
    }
