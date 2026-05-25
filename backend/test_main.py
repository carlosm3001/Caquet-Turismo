from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_read_main():
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "online"

def test_root():
    response = client.get("/")
    assert response.status_code == 200
