from unittest.mock import MagicMock
import os

# Set dummy auth for tests
os.environ["AUTH_USERNAME"] = "test"
os.environ["AUTH_PASSWORD"] = "test"

AUTH_HEADER = {"Authorization": "Basic dGVzdDp0ZXN0"}

def test_start_download_endpoint(client):
    response = client.post("/api/download/start", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json() == {"status": "started"}

def test_get_stream_url_success(client, mock_tidal_client):
    # Setup mock
    mock_tidal_client.get_track.return_value = {
        "OriginalTrackUrl": "http://stream.url"
    }
    
    response = client.get("/api/download/stream/123", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["stream_url"] == "http://stream.url"
    assert data["track_id"] == 123

def test_get_stream_url_not_found(client, mock_tidal_client):
    mock_tidal_client.get_track.return_value = None
    
    response = client.get("/api/download/stream/999", headers=AUTH_HEADER)
    assert response.status_code == 404

def test_download_track_post(client, mock_tidal_client, mock_background_tasks):
    # Setup mock track info
    mock_tidal_client.get_track.side_effect = [
        # First call gets metadata
        {
            "title": "Test Track",
            "artist": {"name": "Test Artist"},
            "trackNumber": 1,
            "duration": 300,
            "OriginalTrackUrl": "http://stream.url"  # Extracted here internally
        },
        # Second call gets stream url (called inside download logic again?)
        # Actually logic is: get_track -> check metadata -> extract stream url from same object usually or secondary call
        # In download_track_server_side, it calls get_track(id, quality)
        {
            "title": "Test Track",
            "OriginalTrackUrl": "http://stream.url"
        }
    ]
    
    payload = {
        "track_id": 1001,
        "artist": "Test Artist",
        "title": "Test Track",
        "quality": "LOSSLESS"
    }
    
    response = client.post("/api/download/track", json=payload, headers=AUTH_HEADER)
    
    # Since we are mocking background tasks, the actual download won't happen,
    # but the API should return success (starting)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "downloading"
    assert "filename" in data
