"""End-to-end: POST an order -> GET the package; gate failure; idempotency."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from tests.conftest import make_order

init_db()  # lifespan isn't run by a bare TestClient; create tables here.
client = TestClient(app)


def _post(order, headers=None):
    return client.post(
        "/api/module2/production-packages",
        json=order.model_dump(mode="json"),
        headers=headers or {},
    )


def test_create_then_read():
    resp = _post(make_order())
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "engineering_ready"
    wid = body["data"]["work_order_id"]

    read = client.get(f"/api/module2/production-packages/{wid}")
    assert read.status_code == 200
    pkg = read.json()["data"]
    assert pkg["work_order_id"] == wid
    assert pkg["source_order_id"] == "ORD-2026-001"
    assert len(pkg["panels"]) == 5
    assert len(pkg["cut_list"]) == 1


def test_unapproved_order_gate_fails():
    order = make_order(order_id="ORD-UNAPPROVED")
    order.approval.designer_approved = False
    resp = _post(order)
    assert resp.status_code == 422
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "gate_failed"
    assert any(b["code"] == "UNAPPROVED_ORDER" for b in body["blockers"])


def test_idempotent_same_version_returns_same_work_order():
    order = make_order(order_id="ORD-IDEM")
    first = _post(order).json()["data"]["work_order_id"]
    second = _post(order).json()["data"]["work_order_id"]
    assert first == second


def test_read_unknown_work_order_404():
    resp = client.get("/api/module2/production-packages/WO-DOESNOTEXIST")
    assert resp.status_code == 404
    assert resp.json()["blockers"][0]["code"] == "WORK_ORDER_NOT_FOUND"
