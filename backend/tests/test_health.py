from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_ok_with_live_database(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["timezone"] == "Asia/Karachi"
