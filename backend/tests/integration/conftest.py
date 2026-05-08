"""Integration-test fixtures: TestClient and autouse global singleton reset."""

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.websocket import manager as _manager
from app.main import app, p2p as _p2p
from app.ppe import coordinator as _coordinator
from app.storage import storage as _storage


def _reset_all_singletons() -> None:
    """Clear every module-level singleton the app touches."""
    _storage.clear()
    _coordinator.sessions.clear()
    _manager.active_connections.clear()
    _p2p.session_states.clear()


@pytest.fixture(autouse=True)
def reset_global_singletons() -> Iterator[None]:
    """Reset the storage / coordinator / manager / p2p globals around every integration test."""
    _reset_all_singletons()
    yield
    _reset_all_singletons()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """FastAPI TestClient for sync integration tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def app_storage():
    """Direct handle to the live app storage singleton (cleared by reset_global_singletons)."""
    return _storage
