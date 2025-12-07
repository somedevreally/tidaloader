import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import sys
from pathlib import Path

# Add backend directory to path so we can import api modules
sys.path.append(str(Path(__file__).parent.parent))

from api.main import app
from api.clients import tidal_client

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_tidal_client(monkeypatch):
    mock = MagicMock()
    # Replace the global tidal_client instance with our mock
    monkeypatch.setattr("api.routers.search.tidal_client", mock)
    monkeypatch.setattr("api.routers.downloads.tidal_client", mock)
    monkeypatch.setattr("api.clients.tidal_client", mock)
    return mock

@pytest.fixture
def mock_background_tasks(monkeypatch):
    # Mock background tasks to prevent actual execution
    mock = MagicMock()
    return mock
