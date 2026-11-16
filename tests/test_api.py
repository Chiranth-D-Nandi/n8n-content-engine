import json
import pytest


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert "jobs" in data
    assert "video_backend" in data


def test_health_ready_endpoint(client):
    res = client.get("/health/ready")
    assert res.status_code == 200
    data = res.get_json()
    assert "status" in data
    assert "database" in data
    assert "video_gateway" in data


def test_channels_crud(client):
    # 1. List channels
    res = client.get("/channels")
    assert res.status_code == 200
    channels = res.get_json()
    assert isinstance(channels, list)

    # 2. Add custom channel
    new_ch = {
        "id": "test_channel_dev",
        "name": "Dev Testing Channel",
        "niche": "software engineering",
        "target_audience": "developers",
        "duration_seconds": 45
    }
    res = client.post("/channels", json=new_ch)
    assert res.status_code == 201
    assert res.get_json()["success"] is True

    # 3. Update custom channel
    res = client.put("/channels/test_channel_dev", json={"name": "Updated Dev Channel"})
    assert res.status_code == 200
    assert res.get_json()["channel"]["name"] == "Updated Dev Channel"

    # 4. Delete channel
    res = client.delete("/channels/test_channel_dev")
    assert res.status_code == 200
    assert res.get_json()["success"] is True


def test_genres_endpoint(client):
    res = client.get("/genres")
    assert res.status_code == 200
    genres = res.get_json()
    assert len(genres) >= 5
    # Verify full data integrity for dashboard onChannelChange
    first = genres[0]
    assert "id" in first
    assert "name" in first
    assert "niche" in first
    assert "reel_style" in first


def test_caption_styles_endpoint(client):
    res = client.get("/caption-styles")
    assert res.status_code == 200
    styles = res.get_json()
    assert "bold_white" in styles

    # Add custom style
    res = client.post("/caption-styles", json={
        "name": "cyberpunk_neon",
        "style": {
            "font": "Impact",
            "font_size": 75,
            "primary_color": "#00FFCC",
            "stroke_color": "#000000",
            "stroke_width": 5,
            "position": "bottom",
            "bold": True,
            "italic": False
        }
    })
    assert res.status_code == 201


def test_metrics_endpoint(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    assert b"http_requests_total" in res.data
