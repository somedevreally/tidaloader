import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import sys
import os
from pathlib import Path

# Set dummy auth for tests
os.environ["AUTH_USERNAME"] = "test"
os.environ["AUTH_PASSWORD"] = "test"

# Add backend directory to path so we can import api modules
sys.path.append(str(Path(__file__).parent.parent))

# Initialize DB before importing app (which triggers init_db via lifespan)
import database as db
db.DB_PATH = Path(__file__).parent / "test_tidaloader.db"

from api.main import app
from api.clients import tidal_client


@pytest.fixture(autouse=True)
def setup_test_db():
    """Create a fresh test database for each test."""
    # Ensure clean state
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    
    # Reset thread-local connection
    if hasattr(db._local, 'connection') and db._local.connection:
        db._local.connection.close()
        db._local.connection = None
    
    db.init_db()
    yield
    
    # Cleanup
    if hasattr(db._local, 'connection') and db._local.connection:
        db._local.connection.close()
        db._local.connection = None
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()


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
