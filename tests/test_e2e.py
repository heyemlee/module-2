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


def test_full_kitchen_order_end_to_end():
    """A realistic mixed kitchen: base run + wall run + pantry, two materials —
    through POST -> GET -> cut sheet -> batch, asserting it all holds together."""
    from app.schemas import (
        Approval,
        ApprovedCabinetOrderPackage,
        CabinetInput,
        Project,
        Source,
    )

    def cab(cid, code, typ, w, d, h, qty, mat):
        return CabinetInput(
            cabinet_id=cid, cabinet_code=code, type=typ, width=w, depth=d, height=h,
            quantity=qty, material=mat, finish="white-shaker",
        )

    order = ApprovedCabinetOrderPackage(
        order_id="ORD-KITCHEN-1",
        project=Project(customer_name="Chen", address="1 Maple"),
        approval=Approval(
            customer_confirmed=True, sales_confirmed=True, designer_approved=True
        ),
        source=Source(stage="final", cabinet_list_version="k1"),
        cabinets=[
            cab("B1", "B302435", "base", 30, 24, 34.5, 2, "plywood-3/4"),
            cab("B2", "FDB24T", "base", 24, 24, 34.5, 1, "plywood-3/4"),
            cab("S1", "SPB12", "base", 12, 24, 34.5, 1, "plywood-3/4"),
            cab("W1", "W301230", "wall", 30, 12, 30, 3, "plywood-3/4"),
            cab("T1", "TP1272L", "tall", 12, 24, 72, 1, "plywood-3/4"),
            cab("A1", "B362435", "base", 36, 24, 34.5, 1, "Cleaf-LR22-19mm"),
        ],
    )
    resp = _post(order)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "engineering_ready"
    wid = body["data"]["work_order_id"]

    pkg = client.get(f"/api/module2/production-packages/{wid}").json()["data"]
    # 8 physical cabinets (2+1+1+3+1 plywood + 1 cleaf), all decomposed
    assert len(pkg["cabinets"]) == 9
    assert len(pkg["panels"]) > 30
    cp = pkg["cutting_plan"]
    # two materials -> at least two cutting groups on their own stock
    sizes = {g["sheet_size"] for g in cp["groups"]}
    assert "1219.2x2438.4" in sizes and "2065.0x2800.0" in sizes

    text = client.get(
        f"/api/module2/production-packages/{wid}/cutting-plan"
    ).text
    assert "图案" in text and "纵切条" in text

    batch = client.post(
        "/api/module2/cutting-batches", json={"work_order_ids": [wid]}
    ).json()["data"]
    assert batch["sheets_total"] >= 1
