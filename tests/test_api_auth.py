import pytest
from fastapi.testclient import TestClient

from support_bot import config
from support_bot.api.main import app

client = TestClient(app)  # no `with`: lifespan (DB) not started; auth runs first


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "test-key")


def test_health_is_public():
    assert client.get("/health").status_code == 200


def test_missing_key_401():
    assert client.post("/chat", json={"message": "hi"}).status_code == 401


def test_wrong_key_403():
    r = client.post("/chat", json={"message": "hi"}, headers={"X-API-Key": "nope"})
    assert r.status_code == 403


def test_invalid_body_422_with_valid_key():
    r = client.post("/chat", json={"message": ""}, headers={"X-API-Key": "test-key"})
    assert r.status_code == 422


def test_unconfigured_server_key_503(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    r = client.post("/chat", json={"message": "hi"}, headers={"X-API-Key": "x"})
    assert r.status_code == 503
