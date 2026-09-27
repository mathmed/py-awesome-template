from fastapi.testclient import TestClient

from app.main.main import app


def test_should_return_ok() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
