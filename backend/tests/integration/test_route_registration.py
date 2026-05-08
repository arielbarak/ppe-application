"""Integration tests for app.api.routes.registration (Protocol 2)."""

from datetime import datetime, timedelta

from tests.fixtures import build_small_poll_payload, register_n_nodes, solve_math_captcha


def _create_poll(client) -> str:
    return client.post("/api/poll/create", json=build_small_poll_payload()).json()["session_id"]


def test_get_captcha_returns_token_and_question(client):
    sid = _create_poll(client)
    resp = client.get(f"/api/poll/{sid}/captcha")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["challenge"].endswith("= ?")


def test_register_with_valid_captcha_succeeds(client, responder_keypairs):
    sid = _create_poll(client)
    node_ids = register_n_nodes(client, sid, 1, responder_keypairs)
    assert len(node_ids) == 1
    assert len(node_ids[0]) == 16


def test_register_with_wrong_captcha_solution_400(client, responder_keypairs):
    sid = _create_poll(client)
    captcha = client.get(f"/api/poll/{sid}/captcha").json()
    _, _, pub_b64, _ = responder_keypairs[0]

    resp = client.post(
        f"/api/poll/{sid}/register",
        json={
            "pseudonym": pub_b64,
            "captcha_solution": "wrong-answer",
            "captcha_token": captcha["token"],
        },
    )
    assert resp.status_code == 400


def test_register_with_already_used_token_400(client, responder_keypairs):
    sid = _create_poll(client)
    captcha = client.get(f"/api/poll/{sid}/captcha").json()
    _, _, pub_b64, _ = responder_keypairs[0]
    solution = solve_math_captcha(captcha["challenge"])

    first = client.post(
        f"/api/poll/{sid}/register",
        json={
            "pseudonym": pub_b64,
            "captcha_solution": solution,
            "captcha_token": captcha["token"],
        },
    )
    assert first.status_code == 200

    # Re-using the same token (with the same or fresh pubkey) is rejected
    _, _, pub2, _ = responder_keypairs[1]
    second = client.post(
        f"/api/poll/{sid}/register",
        json={
            "pseudonym": pub2,
            "captcha_solution": solution,
            "captcha_token": captcha["token"],
        },
    )
    assert second.status_code == 400


def test_register_with_expired_token_400(client, responder_keypairs, app_storage):
    sid = _create_poll(client)
    captcha = client.get(f"/api/poll/{sid}/captcha").json()
    token = captcha["token"]
    solution = solve_math_captcha(captcha["challenge"])

    # Force the challenge to be expired by mutating the storage record
    challenge = app_storage.get_session(sid).captcha_challenges[token]
    challenge.expires_at = datetime.now() - timedelta(seconds=1)

    _, _, pub_b64, _ = responder_keypairs[0]
    resp = client.post(
        f"/api/poll/{sid}/register",
        json={
            "pseudonym": pub_b64,
            "captcha_solution": solution,
            "captcha_token": token,
        },
    )
    assert resp.status_code == 400


def test_get_captcha_outside_registration_phase_400(client, app_storage):
    sid = _create_poll(client)
    app_storage.update_session_status(sid, "voting")
    resp = client.get(f"/api/poll/{sid}/captcha")
    assert resp.status_code == 400


def test_register_duplicate_pseudonym_400(client, responder_keypairs):
    """Same pubkey -> same node_id -> add_registered_node returns None -> 400."""
    sid = _create_poll(client)

    register_n_nodes(client, sid, 1, responder_keypairs)
    # Try to register the same pubkey again with a fresh captcha
    captcha = client.get(f"/api/poll/{sid}/captcha").json()
    solution = solve_math_captcha(captcha["challenge"])
    _, _, pub_b64, _ = responder_keypairs[0]
    resp = client.post(
        f"/api/poll/{sid}/register",
        json={
            "pseudonym": pub_b64,
            "captcha_solution": solution,
            "captcha_token": captcha["token"],
        },
    )
    assert resp.status_code == 400


def test_get_registered_nodes_endpoint(client, responder_keypairs):
    sid = _create_poll(client)
    node_ids = register_n_nodes(client, sid, 3, responder_keypairs)

    resp = client.get(f"/api/poll/{sid}/registered")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_registered"] == 3
    assert {n["node_id"] for n in body["nodes"]} == set(node_ids)
