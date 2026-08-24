from fastapi.testclient import TestClient
from mecha_api.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_greeting() -> None:
    response = client.get("/api/hello/mecha")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, mecha!"}
