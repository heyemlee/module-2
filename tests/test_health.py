"""Smoke tests for the infra scaffold (no business logic)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "ok"
    assert body["contract_version"]


def test_root_serves_demo() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "生产工程演示" in body            # the Module 1 -> Module 2 demo
    assert "Module 1" in body               # starts from Module 1's output
    assert "production-packages" in body    # its JS calls the real API


def test_console_is_served() -> None:
    resp = client.get("/console")
    assert resp.status_code == 200
    assert "测试台" in resp.text             # raw JSON tester
