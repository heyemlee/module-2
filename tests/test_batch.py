"""Cross-order cutting batch: merge several orders into one shared cutting plan."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.schemas import Source
from tests.conftest import make_order

init_db()
client = TestClient(app)


def _create(order_id: str, version: str) -> str:
    order = make_order(
        order_id=order_id,
        source=Source(stage="final", cabinet_list_version=version),
    )
    resp = client.post(
        "/api/module2/production-packages", json=order.model_dump(mode="json")
    )
    return resp.json()["data"]["work_order_id"]


def _solo_sheets(wid: str) -> int:
    pkg = client.get(f"/api/module2/production-packages/{wid}").json()["data"]
    return pkg["cutting_plan"]["sheets_total"]


def test_batch_merges_two_orders():
    wid_a = _create("ORD-BATCH-A", "a")
    wid_b = _create("ORD-BATCH-B", "b")

    resp = client.post(
        "/api/module2/cutting-batches",
        json={"work_order_ids": [wid_a, wid_b], "use_offcut_stock": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "batch_ready"

    data = body["data"]
    assert set(data["work_order_ids"]) == {wid_a, wid_b}
    assert data["sheets_total"] >= 1
    assert data["cutting_plan"]["sheets_total"] == data["sheets_total"]


def test_batch_not_worse_than_cutting_separately():
    wid_a = _create("ORD-MERGE-A", "a")
    wid_b = _create("ORD-MERGE-B", "b")
    separate = _solo_sheets(wid_a) + _solo_sheets(wid_b)

    merged = client.post(
        "/api/module2/cutting-batches",
        json={"work_order_ids": [wid_a, wid_b], "use_offcut_stock": False},
    ).json()["data"]["sheets_total"]

    assert merged <= separate


def test_batch_is_idempotent_regardless_of_order():
    wid_a = _create("ORD-IDEM-A", "a")
    wid_b = _create("ORD-IDEM-B", "b")

    first = client.post(
        "/api/module2/cutting-batches",
        json={"work_order_ids": [wid_a, wid_b], "use_offcut_stock": False},
    ).json()["data"]["batch_id"]
    # same set, reversed order -> same batch
    second = client.post(
        "/api/module2/cutting-batches",
        json={"work_order_ids": [wid_b, wid_a], "use_offcut_stock": False},
    ).json()["data"]["batch_id"]
    assert first == second


def test_batch_unknown_work_order_fails():
    wid_a = _create("ORD-MISS-A", "a")
    resp = client.post(
        "/api/module2/cutting-batches",
        json={"work_order_ids": [wid_a, "WO-DOESNOTEXIST"]},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "batch_failed"
    assert any(b["code"] == "WORK_ORDER_NOT_FOUND" for b in body["blockers"])


def test_batch_empty_fails():
    resp = client.post("/api/module2/cutting-batches", json={"work_order_ids": []})
    assert resp.status_code == 422
    assert resp.json()["blockers"][0]["code"] == "EMPTY_BATCH"


def test_batch_text_tags_each_order():
    wid_a = _create("ORD-TXT-A", "a")
    wid_b = _create("ORD-TXT-B", "b")
    batch_id = client.post(
        "/api/module2/cutting-batches",
        json={"work_order_ids": [wid_a, wid_b], "use_offcut_stock": False},
    ).json()["data"]["batch_id"]

    text = client.get(f"/api/module2/cutting-batches/{batch_id}/cutting-plan").text
    assert "纵切条" in text
    # both orders identified so the mixed pile can be sorted back
    assert "ORD-TXT-A" in text
    assert "ORD-TXT-B" in text


def test_read_unknown_batch_404():
    resp = client.get("/api/module2/cutting-batches/BATCH-NOPE")
    assert resp.status_code == 404
    assert resp.json()["blockers"][0]["code"] == "BATCH_NOT_FOUND"
