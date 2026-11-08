"""Smoke tests for the web UI shell and the new status endpoint."""
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_root_serves_upload_ui():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Resurface" in response.text
    assert 'id="form"' in response.text
    assert "/queries" in response.text


def test_unknown_query_status_returns_404():
    response = client.get("/queries/00000000-0000-0000-0000-000000000000/status")

    assert response.status_code == 404
    assert response.json()["detail"] == "Query not found"


def test_unknown_query_report_returns_404():
    response = client.get("/queries/00000000-0000-0000-0000-000000000000/report")

    assert response.status_code == 404
    assert "decision" in response.json()["detail"].lower()


def test_malformed_query_id_returns_400():
    response = client.get("/queries/not-a-uuid/status")

    assert response.status_code == 400
    assert "uuid" in response.json()["detail"].lower()
