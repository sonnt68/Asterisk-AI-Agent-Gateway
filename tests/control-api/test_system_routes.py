from app.main import app
from fastapi.testclient import TestClient


def test_control_api_exposes_the_versioned_health_route() -> None:
    response = TestClient(app).get("/api/v1/system/health")

    assert response.status_code == 200
    assert response.json() == {"service": "control-api", "status": "ok", "version": "1.0.0"}
