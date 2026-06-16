"""
Protocol 6: Verification logic for local and global verification

Implements independent graph reconstruction as required by the PPE research
paper. The verifier MUST NOT trust the published edge list blindly. Instead,
it recomputes the Ideal Graph G_c from the public parameters (p, node list)
and compares it against the published certification graph to detect:

  - Omitted edges:   edges in G_c that the pollster failed to report.
                      Treated as FAILED for both endpoints.
  - Fabricated edges: edges NOT in G_c that appear in the published data.
                      Immediate REJECT (graph manipulation).
  - Missing nodes:   nodes that voted but aren't in the published node list.
  - Extra nodes:     nodes in the graph that never registered/voted.
  - Asymmetric edges: edges that exist only in one direction (should be symmetric).

Only after this reconciliation are exclusions (η_E) and validity (η_V)
computed against the full, independently-verified graph.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Set, Tuple, Optional

from .graph import compute_exclusions, validate_certification_graph, determine_neighbors, compute_node_id
from .signatures import verify_signature

logger = logging.getLogger(__name__)

# Maximum value of a 256-bit SHA-256 hash (64 hex chars of 'f')
_MAX_HASH = int('f' * 64, 16)


def _canonical_vote_message(vote: Dict[str, Any]) -> str:
    """Reproduce the exact string the client signed for its vote.

    The frontend signs ``JSON.stringify(vote)`` (VotingView.tsx), which emits
    compact JSON with no whitespace and preserves key insertion order. We mirror
    that here so a genuine signature reconciles.
    """
    return json.dumps(vote, separators=(',', ':'), ensure_ascii=False)


def _bound_public_key(node_id: str, public_keys: Dict[str, str]) -> Optional[str]:
    """Return a node's public key only if it is self-consistent with its id.

    Because ``node_id = SHA-256(public_key)[:16]`` (graph.compute_node_id), the
    id-to-key binding is self-certifying: a verifier recomputes the id from the
    published key and rejects any key that does not hash to it. This stops a
    malicious pollster from substituting its own keypair for a participant and
    then forging that participant's signatures.
    """
    pubkey = public_keys.get(node_id)
    if not pubkey:
        return None
    if compute_node_id(pubkey) != node_id:
        logger.warning(f"Published public key does not match node id {node_id}")
        return None
    return pubkey


def _edge_signature_message(from_node: str, to_node: str, public_keys: Dict[str, str]) -> Optional[str]:
    """Reproduce the message signed for a directed certification edge.

    For a stored edge ``(from=A, to=B)`` the recorded signature is *B's*
    signature over ``PPE:{sorted(A,B) joined by '-'}:{pubkey(A)}`` — see
    usePpeHandshake.ts, where each peer signs the other's public key. Returns
    None when A's public key is unknown (cannot reconstruct the message).
    """
    from_pubkey = _bound_public_key(from_node, public_keys)
    if not from_pubkey:
        return None
    edge_label = '-'.join(sorted([from_node, to_node]))
    return f"PPE:{edge_label}:{from_pubkey}"


def _verify_edge_signature(
    from_node: str,
    to_node: str,
    signature: Optional[str],
    public_keys: Dict[str, str],
) -> Optional[bool]:
    """Verify a certification edge signature.

    Returns True/False when the check can be performed, or None when there is
    not enough information (no signature, or a missing public key) to decide —
    in which case the caller falls back to the deterministic edge rule alone.
    """
    if not signature:
        return None
    signer_pubkey = _bound_public_key(to_node, public_keys)  # edge (A->B) carries B's signature
    message = _edge_signature_message(from_node, to_node, public_keys)
    if not signer_pubkey or message is None:
        # If the bulletin publishes keys at all (strict mode), a missing or
        # unbindable key for a signed edge is a failure; otherwise (legacy
        # bulletin with no keys) we cannot check and defer to the edge rule.
        return False if public_keys else None
    return verify_signature(signer_pubkey, message, signature)


def _verify_vote_signature(
    response: Dict[str, Any],
    public_keys: Dict[str, str],
) -> Optional[bool]:
    """Verify a voter's self-signature over its ballot.

    Returns True/False when checkable, or None when the signature or the
    voter's public key is unavailable.
    """
    signature = response.get('self_signature')
    if not signature:
        return None
    node_id = response.get('node_id')

    # Prefer the self-certifying map; fall back to a key carried on the response
    # only if it too hashes to the claimed node id.
    pubkey = _bound_public_key(node_id, public_keys)
    if not pubkey:
        candidate = response.get('public_key')
        if candidate and compute_node_id(candidate) == node_id:
            pubkey = candidate
    if not pubkey:
        # Strict mode (bulletin publishes keys): an unbindable key for a signed
        # ballot is a failure. Legacy bulletin (no keys): cannot check.
        return False if public_keys else None
    message = _canonical_vote_message(response.get('vote', {}))
    return verify_signature(pubkey, message, signature)


@dataclass
class EdgeObj:
    """Edge object used during verification with full metadata."""
    from_node: str
    to_node: str
    verified: bool
    signature: Optional[str] = None
    omitted: bool = False
    asymmetric: bool = False


@dataclass
class GraphDiscrepancies:
    """Detailed report of all discrepancies found during graph reconciliation."""
    omitted_edges: List[Tuple[str, str]] = field(default_factory=list)
    fabricated_edges: List[Tuple[str, str]] = field(default_factory=list)
    asymmetric_edges: List[Tuple[str, str]] = field(default_factory=list)
    missing_nodes: List[str] = field(default_factory=list)
    extra_nodes: List[str] = field(default_factory=list)
    unverified_edges: List[Tuple[str, str]] = field(default_factory=list)
    # Edges whose published signature failed cryptographic verification. The
    # edge is downgraded to "failed" so it cannot count toward certification.
    invalid_signature_edges: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def has_critical_issues(self) -> bool:
        """Fabricated edges or missing nodes are critical - immediate REJECT."""
        return len(self.fabricated_edges) > 0 or len(self.missing_nodes) > 0

    @property
    def total_issues(self) -> int:
        return (
            len(self.omitted_edges) +
            len(self.fabricated_edges) +
            len(self.asymmetric_edges) +
            len(self.missing_nodes) +
            len(self.extra_nodes)
        )


def _compute_edge_hash(node_a: str, node_b: str) -> int:
    """Compute deterministic edge hash using SHA-256(min:max) ordering."""
    edge_key = f"{min(node_a, node_b)}:{max(node_a, node_b)}"
    return int(hashlib.sha256(edge_key.encode('utf-8')).hexdigest(), 16)


def _edge_should_exist(node_a: str, node_b: str, edge_probability: float) -> bool:
    """Determine if an edge should exist based on the SHA-256 hash threshold."""
    threshold = int(_MAX_HASH * edge_probability)
    edge_hash = _compute_edge_hash(node_a, node_b)
    return edge_hash <= threshold


def _reconstruct_ideal_graph(
    all_node_ids: List[str],
    edge_probability: float,
) -> Dict[str, Set[str]]:
    """
    Recompute the Ideal Graph G_c from public parameters alone.
    This is the mathematical truth of the session — independent of anything
    the pollster reported.

    The graph is symmetric: if edge(A,B) exists, both A→B and B→A are present.
    """
    ideal: Dict[str, Set[str]] = {nid: set() for nid in all_node_ids}

    for node_id in all_node_ids:
        neighbors = determine_neighbors(node_id, all_node_ids, edge_probability)
        ideal[node_id] = set(neighbors)

    return ideal


def _build_published_edge_index(
    cert_graph_data: Dict[str, Any],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Index published edges as (from, to) -> edge_dict for O(1) lookup."""
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for edge_data in cert_graph_data.get('edges', []):
        from_node = edge_data.get('from')
        to_node = edge_data.get('to')
        if from_node and to_node:
            index[(from_node, to_node)] = edge_data

    return index


def _check_node_consistency(
    published_nodes: List[str],
    response_node_ids: Set[str],
) -> Tuple[List[str], List[str]]:
    """
    Verify node list consistency between the graph and responses.

    Returns (missing_nodes, extra_nodes):
    - missing_nodes: nodes that voted but aren't in the published node list
    - extra_nodes: nodes in the graph that never voted
    """
    published_set = set(published_nodes)

    missing = [nid for nid in response_node_ids if nid not in published_set]
    extra = [nid for nid in published_set if nid not in response_node_ids]

    return missing, extra


def _check_edge_symmetry(
    published_index: Dict[Tuple[str, str], Dict[str, Any]],
) -> List[Tuple[str, str]]:
    """
    Check that all edges are symmetric (if A→B exists, B→A should too).
    Returns list of asymmetric edges.
    """
    asymmetric = []

    for (from_node, to_node) in published_index:
        reverse_key = (to_node, from_node)
        if reverse_key not in published_index:
            asymmetric.append((from_node, to_node))

    return asymmetric


def _reconcile_graph(
    all_node_ids: List[str],
    ideal_graph: Dict[str, Set[str]],
    published_index: Dict[Tuple[str, str], Dict[str, Any]],
    response_node_ids: Set[str],
    public_keys: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, List[EdgeObj]], GraphDiscrepancies]:
    """
    Walk every ideal edge. If the pollster published it, keep the reported
    status; if they omitted it, inject a synthetic failed edge. Also flags
    any fabricated edges (published but not in the ideal graph).

    Returns (verification_graph, discrepancies).
    """
    verification_graph: Dict[str, List[EdgeObj]] = {nid: [] for nid in all_node_ids}
    discrepancies = GraphDiscrepancies()
    public_keys = public_keys or {}

    # Check node consistency
    missing_nodes, extra_nodes = _check_node_consistency(
        all_node_ids, response_node_ids
    )
    discrepancies.missing_nodes = missing_nodes
    discrepancies.extra_nodes = extra_nodes

    # Check edge symmetry in published data
    discrepancies.asymmetric_edges = _check_edge_symmetry(published_index)

    # Build set of all ideal edges for fabrication detection
    ideal_edge_set: Set[Tuple[str, str]] = set()
    for node_id, neighbors in ideal_graph.items():
        for neighbor_id in neighbors:
            ideal_edge_set.add((node_id, neighbor_id))

    # Reconcile ideal graph against published data
    for node_id in all_node_ids:
        for neighbor_id in ideal_graph.get(node_id, set()):
            published = published_index.get((node_id, neighbor_id))

            if published is not None:
                is_verified = published.get('verified', False)
                signature = published.get('signature')

                # Cryptographically check the edge signature when possible. A
                # claimed-verified edge whose signature does not validate is
                # downgraded to failed: the pollster cannot manufacture
                # certification by attaching a bogus signature string.
                if is_verified:
                    sig_ok = _verify_edge_signature(
                        node_id, neighbor_id, signature, public_keys
                    )
                    if sig_ok is False:
                        is_verified = False
                        discrepancies.invalid_signature_edges.append((node_id, neighbor_id))

                edge = EdgeObj(
                    from_node=node_id,
                    to_node=neighbor_id,
                    verified=is_verified,
                    signature=signature,
                    omitted=False,
                )
                verification_graph[node_id].append(edge)

                if not is_verified:
                    discrepancies.unverified_edges.append((node_id, neighbor_id))
            else:
                # Edge exists in ideal graph but not published - omitted
                discrepancies.omitted_edges.append((node_id, neighbor_id))
                verification_graph[node_id].append(EdgeObj(
                    from_node=node_id,
                    to_node=neighbor_id,
                    verified=False,
                    omitted=True,
                ))

    # Detect fabricated edges (in published but not in ideal graph)
    for (from_node, to_node) in published_index:
        if (from_node, to_node) not in ideal_edge_set:
            discrepancies.fabricated_edges.append((from_node, to_node))

    return verification_graph, discrepancies


def verify_local(
    node_id: str,
    published_results: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    A responder's self-check: is my vote in the published results, and are
    all my expected edges (per the ideal graph) accounted for?

    Returns (success, message, details).
    """
    details: Dict[str, Any] = {
        'node_id': node_id,
        'vote_found': False,
        'in_node_list': False,
        'expected_neighbors': 0,
        'published_neighbors': 0,
        'omitted_edges': [],
        'fabricated_edges': [],
        'verified_edges': 0,
        'unverified_edges': 0,
        'self_signature_valid': None,
        'invalid_signature_edges': [],
    }

    try:
        responses = published_results.get('responses', [])
        node_vote = None

        for response in responses:
            if response.get('node_id') == node_id:
                node_vote = response
                break

        if not node_vote:
            return False, f"Vote for node {node_id} not found in published results", details

        details['vote_found'] = True

        cert_graph = published_results.get('certification_graph', {})
        parameters = published_results.get('parameters', {})
        all_node_ids = cert_graph.get('nodes', [])
        edge_probability = parameters.get('edge_probability', 0.5)
        public_keys = (
            published_results.get('public_keys')
            or cert_graph.get('public_keys')
            or {}
        )

        if node_id not in all_node_ids:
            return False, f"Node {node_id} not in published node list", details

        details['in_node_list'] = True

        # Confirm the recorded ballot really carries this node's signature.
        self_sig_ok = _verify_vote_signature(node_vote, public_keys)
        details['self_signature_valid'] = self_sig_ok
        if self_sig_ok is False:
            return False, (
                f"Local verification FAILED: the published vote for node {node_id} "
                f"does not carry a valid self-signature"
            ), details

        # Reconstruct expected neighbors using SHA-256 hash logic
        expected_neighbors = set()
        for other_id in all_node_ids:
            if other_id != node_id and _edge_should_exist(node_id, other_id, edge_probability):
                expected_neighbors.add(other_id)

        details['expected_neighbors'] = len(expected_neighbors)

        # Get published edges from this node
        published_edges = cert_graph.get('edges', [])
        published_from_node: Dict[str, Dict[str, Any]] = {}
        for edge in published_edges:
            if edge.get('from') == node_id:
                published_from_node[edge.get('to')] = edge

        details['published_neighbors'] = len(published_from_node)

        # Cryptographically check the signatures on this node's own edges.
        invalid_sig_edges = []
        for to_node, edge in published_from_node.items():
            if edge.get('verified', False):
                sig_ok = _verify_edge_signature(
                    node_id, to_node, edge.get('signature'), public_keys
                )
                if sig_ok is False:
                    invalid_sig_edges.append(to_node)
        details['invalid_signature_edges'] = invalid_sig_edges

        # An edge with a bad signature does not count as verified.
        verified_count = sum(
            1 for to_node, e in published_from_node.items()
            if e.get('verified', False) and to_node not in invalid_sig_edges
        )
        details['verified_edges'] = verified_count
        details['unverified_edges'] = len(published_from_node) - verified_count

        # Check for omitted edges (expected but not published)
        omitted = expected_neighbors - set(published_from_node.keys())
        details['omitted_edges'] = list(omitted)

        # Check for fabricated edges (published but not expected)
        fabricated = set(published_from_node.keys()) - expected_neighbors
        details['fabricated_edges'] = list(fabricated)

        if fabricated:
            fab_list = ', '.join(sorted(fabricated)[:5])
            suffix = f"... and {len(fabricated) - 5} more" if len(fabricated) > 5 else ""
            return False, (
                f"Local verification FAILED: {len(fabricated)} fabricated edges detected "
                f"(edges that shouldn't exist per SHA-256 hash). "
                f"Fabricated: [{fab_list}{suffix}]"
            ), details

        if omitted:
            omitted_list = ', '.join(sorted(omitted)[:5])
            suffix = f"... and {len(omitted) - 5} more" if len(omitted) > 5 else ""
            return False, (
                f"Local verification FAILED: {len(omitted)} expected edges from "
                f"node {node_id} are missing from published results. "
                f"Omitted neighbors: [{omitted_list}{suffix}]"
            ), details

        logger.info(
            f"Local verification for {node_id}: vote found, "
            f"{len(expected_neighbors)} expected edges all accounted for, "
            f"{verified_count} verified"
        )
        return True, (
            f"Local verification passed: vote found, all "
            f"{len(expected_neighbors)} expected edges published "
            f"({verified_count} verified, {len(published_from_node) - verified_count} unverified)"
        ), details

    except Exception as e:
        logger.error(f"Local verification error: {e}")
        return False, f"Local verification failed: {str(e)}", details


def verify_global(
    published_results: Dict[str, Any],
    eta_e: float,
    eta_v: float = 0.025,
) -> Dict[str, Any]:
    """
    Full independent verification (Protocol 6). Reconstructs the ideal graph
    from scratch using SHA-256 hash logic, reconciles it against the published
    data, runs η_E exclusion and η_V validity, then tallies votes from
    non-excluded nodes only.

    The verification process:
    1. Extract all node IDs and edge probability from published data
    2. Reconstruct the Ideal Graph G_c using SHA-256(min(i,j):max(i,j)) <= p * MAX_HASH
    3. Cross-reference published edges against the ideal graph
    4. Detect omitted edges (in ideal but not published) - treated as failures
    5. Detect fabricated edges (in published but not ideal) - immediate REJECT
    6. Detect missing/extra nodes
    7. Check edge symmetry
    8. Compute η_E exclusions on the reconciled graph
    9. Check η_V validity threshold
    10. Tally votes from non-excluded nodes only

    Critical issues cause immediate REJECT:
    - Fabricated edges (not in ideal graph)
    - Missing nodes (voted but not in published node list)
    """
    try:
        responses = published_results.get('responses', [])
        cert_graph_data = published_results.get('certification_graph', {})
        questions = published_results.get('questions', [])
        parameters = published_results.get('parameters', {})

        edge_probability = parameters.get('edge_probability', 0.5)
        all_node_ids = cert_graph_data.get('nodes', [])

        # node_id -> public key map (published so verification needs no pollster
        # cooperation). Tolerate either placement for backwards compatibility.
        public_keys = (
            published_results.get('public_keys')
            or cert_graph_data.get('public_keys')
            or {}
        )

        if not all_node_ids:
            return _error_result("No nodes in published certification graph")

        # Get set of nodes that actually submitted votes
        response_node_ids = {r.get('node_id') for r in responses if r.get('node_id')}

        logger.info(
            f"Verification starting: {len(all_node_ids)} published nodes, "
            f"{len(response_node_ids)} voting nodes, p={edge_probability}"
        )

        # Step 1: Reconstruct the Ideal Graph from public parameters
        ideal_graph = _reconstruct_ideal_graph(all_node_ids, edge_probability)
        ideal_edge_count = sum(len(nbrs) for nbrs in ideal_graph.values())

        logger.info(
            f"Ideal graph reconstructed: {len(all_node_ids)} nodes, "
            f"{ideal_edge_count} directed edges"
        )

        # Step 2: Index published edges for efficient lookup
        published_index = _build_published_edge_index(cert_graph_data)
        published_edge_count = len(published_index)

        # Step 3: Reconcile graphs and detect all discrepancies
        verification_graph, discrepancies = _reconcile_graph(
            all_node_ids, ideal_graph, published_index, response_node_ids,
            public_keys,
        )

        logger.info(
            f"Graph reconciliation complete: "
            f"{len(discrepancies.omitted_edges)} omitted, "
            f"{len(discrepancies.fabricated_edges)} fabricated, "
            f"{len(discrepancies.asymmetric_edges)} asymmetric, "
            f"{len(discrepancies.missing_nodes)} missing nodes, "
            f"{len(discrepancies.extra_nodes)} extra nodes"
        )

        # Step 4: Check for critical issues (immediate REJECT)
        if discrepancies.has_critical_issues:
            issues = []

            if discrepancies.fabricated_edges:
                sample = discrepancies.fabricated_edges[:5]
                sample_str = ", ".join(f"{f}->{t}" for f, t in sample)
                suffix = f" (+{len(discrepancies.fabricated_edges) - 5} more)" if len(discrepancies.fabricated_edges) > 5 else ""
                issues.append(
                    f"{len(discrepancies.fabricated_edges)} fabricated edges "
                    f"(not in Ideal Graph): [{sample_str}{suffix}]"
                )

            if discrepancies.missing_nodes:
                sample = discrepancies.missing_nodes[:5]
                sample_str = ", ".join(sample)
                suffix = f" (+{len(discrepancies.missing_nodes) - 5} more)" if len(discrepancies.missing_nodes) > 5 else ""
                issues.append(
                    f"{len(discrepancies.missing_nodes)} missing nodes "
                    f"(voted but not in graph): [{sample_str}{suffix}]"
                )

            message = f"REJECT: {'; '.join(issues)}"
            logger.error(message)

            return {
                'verification': 'REJECT',
                'tally': {},
                'excluded_nodes': [],
                'details': {
                    'total_nodes': len(all_node_ids),
                    'valid_nodes': 0,
                    'excluded_nodes_count': 0,
                    'edge_verification_passed': False,
                    'validity_check_passed': False,
                    'eta_e': eta_e,
                    'eta_v': eta_v,
                    'max_allowed_exclusions': eta_v * len(responses),
                    'ideal_edge_count': ideal_edge_count,
                    'published_edge_count': published_edge_count,
                    'omitted_edge_count': len(discrepancies.omitted_edges),
                    'fabricated_edge_count': len(discrepancies.fabricated_edges),
                    'asymmetric_edge_count': len(discrepancies.asymmetric_edges),
                    'missing_node_count': len(discrepancies.missing_nodes),
                    'extra_node_count': len(discrepancies.extra_nodes),
                    'fabricated_edges': discrepancies.fabricated_edges[:10],
                    'missing_nodes': discrepancies.missing_nodes[:10],
                    'message': message,
                },
            }

        # Step 5: Compute η_E exclusions on the reconciled graph
        excluded_nodes = compute_exclusions(verification_graph, eta_e)

        total_responders = len(responses)
        excluded_count = len(excluded_nodes)
        max_allowed_exclusions = eta_v * total_responders

        # Step 6: Check η_V validity threshold
        validity_check_passed = excluded_count <= max_allowed_exclusions

        if not validity_check_passed:
            logger.warning(
                f"Poll INVALID: {excluded_count} nodes excluded exceeds η_V "
                f"({excluded_count} > {max_allowed_exclusions:.1f} = "
                f"{eta_v * 100:.1f}% of {total_responders})"
            )

        # Step 7: Validate graph structure
        edge_verification_passed = validate_certification_graph(
            verification_graph,
            all_node_ids,
        )

        # Step 8: Tally votes from non-excluded nodes
        tally: Dict[str, Dict[str, int]] = {}
        valid_vote_count = 0
        invalid_vote_signatures: List[str] = []

        for question in questions:
            q_id = question.get('id')
            tally[q_id] = {}
            for option in question.get('options', []):
                tally[q_id][option] = 0

        for response in responses:
            resp_node_id = response.get('node_id')

            if resp_node_id in excluded_nodes:
                logger.debug(f"Skipping vote from excluded node {resp_node_id}")
                continue

            # Drop ballots whose self-signature does not verify against the
            # voter's published key: a vote nobody can prove was cast by its
            # claimed owner must not be counted. Unsigned/unverifiable-key
            # ballots (sig_ok is None) fall through to the legacy behaviour.
            sig_ok = _verify_vote_signature(response, public_keys)
            if sig_ok is False:
                invalid_vote_signatures.append(resp_node_id)
                logger.warning(f"Dropping vote from {resp_node_id}: invalid self-signature")
                continue

            valid_vote_count += 1
            vote_data = response.get('vote', {})

            for q_id, answer in vote_data.items():
                if q_id in tally:
                    if answer in tally[q_id]:
                        tally[q_id][answer] += 1
                    else:
                        logger.warning(
                            f"Invalid answer '{answer}' for question {q_id}"
                        )

        # Step 9: Determine final verification status
        verification_status = "ACCEPT"
        if not edge_verification_passed:
            verification_status = "REJECT"
        if not validity_check_passed:
            verification_status = "INVALID"

        # Build result message
        if verification_status == "INVALID":
            exclusion_pct = (
                (excluded_count / total_responders * 100)
                if total_responders > 0
                else 0
            )
            message = (
                f"POLL INVALID: {excluded_count} nodes excluded "
                f"({exclusion_pct:.1f}%) exceeds η_V threshold of "
                f"{eta_v * 100:.1f}%"
            )
        elif verification_status == "REJECT":
            message = "Verification failed: certification graph validation error"
        else:
            notes = []
            if discrepancies.omitted_edges:
                notes.append(f"{len(discrepancies.omitted_edges)} omitted edges counted as failures")
            if discrepancies.invalid_signature_edges:
                notes.append(
                    f"{len(discrepancies.invalid_signature_edges)} edges downgraded "
                    f"(invalid signature)"
                )
            if invalid_vote_signatures:
                notes.append(
                    f"{len(invalid_vote_signatures)} votes dropped (invalid self-signature)"
                )
            if discrepancies.asymmetric_edges:
                notes.append(f"{len(discrepancies.asymmetric_edges)} asymmetric edges detected")
            if discrepancies.extra_nodes:
                notes.append(f"{len(discrepancies.extra_nodes)} extra nodes in graph")

            note_str = f" ({'; '.join(notes)})" if notes else ""
            message = (
                f"Verified {valid_vote_count} valid votes against "
                f"independently reconstructed ideal graph{note_str}"
            )

        logger.info(
            f"Global verification: {verification_status}, "
            f"{valid_vote_count}/{total_responders} valid votes, "
            f"{excluded_count} excluded nodes"
        )

        return {
            'verification': verification_status,
            'tally': tally,
            'excluded_nodes': list(excluded_nodes),
            'details': {
                'total_nodes': total_responders,
                'valid_nodes': valid_vote_count,
                'excluded_nodes_count': excluded_count,
                'edge_verification_passed': edge_verification_passed,
                'validity_check_passed': validity_check_passed,
                'eta_e': eta_e,
                'eta_v': eta_v,
                'max_allowed_exclusions': max_allowed_exclusions,
                'ideal_edge_count': ideal_edge_count,
                'published_edge_count': published_edge_count,
                'matched_edge_count': published_edge_count - len(discrepancies.fabricated_edges),
                'omitted_edge_count': len(discrepancies.omitted_edges),
                'fabricated_edge_count': len(discrepancies.fabricated_edges),
                'asymmetric_edge_count': len(discrepancies.asymmetric_edges),
                'unverified_edge_count': len(discrepancies.unverified_edges),
                'invalid_signature_edge_count': len(discrepancies.invalid_signature_edges),
                'invalid_vote_signature_count': len(invalid_vote_signatures),
                'missing_node_count': len(discrepancies.missing_nodes),
                'extra_node_count': len(discrepancies.extra_nodes),
                'omitted_edges': discrepancies.omitted_edges[:20],
                'asymmetric_edges': discrepancies.asymmetric_edges[:10],
                'invalid_signature_edges': discrepancies.invalid_signature_edges[:10],
                'invalid_vote_signatures': invalid_vote_signatures[:10],
                'message': message,
            },
        }

    except Exception as e:
        logger.error(f"Global verification error: {e}")
        return _error_result(f"Verification failed: {str(e)}")


def _error_result(message: str) -> Dict[str, Any]:
    """Build a REJECT result for unrecoverable errors."""
    return {
        'verification': 'REJECT',
        'tally': {},
        'excluded_nodes': [],
        'details': {
            'total_nodes': 0,
            'valid_nodes': 0,
            'excluded_nodes_count': 0,
            'edge_verification_passed': False,
            'message': message,
        },
    }
