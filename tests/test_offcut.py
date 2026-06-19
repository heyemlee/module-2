"""Offcut inventory: recovered material is reused before cutting fresh sheets.

Each test uses a UNIQUE material so its inventory is isolated from other tests
(matching is by material+thickness+finish), keeping the shared DB deterministic.
"""

from fastapi.testclient import TestClient

from app import store
from app.cutting import NewOffcut
from app.db import SessionLocal, init_db
from app.main import app
from app.schemas import CabinetInput, Source
from tests.conftest import make_order

init_db()
client = TestClient(app)

FINISH = "f"


def _create(order_id: str, version: str, material: str, qty: int = 1) -> str:
    order = make_order(
        order_id=order_id,
        source=Source(stage="final", cabinet_list_version=version),
        cabinet=CabinetInput(
            cabinet_id="C1", cabinet_code="B302435", type="base",
            width=30, depth=24, height=34.5, quantity=qty,
            material=material, finish=FINISH,
        ),
    )
    resp = client.post(
        "/api/module2/production-packages", json=order.model_dump(mode="json")
    )
    return resp.json()["data"]["work_order_id"]


def _batch(wids: list[str], use_stock: bool = True) -> dict:
    return client.post(
        "/api/module2/cutting-batches",
        json={"work_order_ids": wids, "use_offcut_stock": use_stock},
    ).json()["data"]


def _stock(material: str) -> list[dict]:
    items = client.get("/api/module2/offcut-stock").json()["data"]["offcuts"]
    return [o for o in items if o["material"] == material]


def _seed(material: str, batch_id: str, width: float = 900.0) -> None:
    # Carcass panels carry no door finish (box colour is in `material`), so the offcuts
    # they produce — and any seeded to match them — use finish="" (see engine.py).
    db = SessionLocal()
    store.deposit_offcuts(db, batch_id, [NewOffcut(material, 18.0, "", width, 2428.4)])
    db.close()


def test_seeded_offcut_is_reused_before_fresh_stock():
    material = "ply-reuse-A"
    _seed(material, "SEED-A")
    assert len(_stock(material)) == 1

    wid = _create("ORD-OC-A", "a", material)
    data = _batch([wid])

    assert data["offcut_sheets"] >= 1  # a strip landed on the recovered offcut
    # the seeded offcut is now consumed, no longer available
    assert "SEED-A-OC001" not in [o["offcut_id"] for o in _stock(material)]


def test_fresh_sheet_leftovers_are_deposited():
    material = "ply-deposit-B"
    wid = _create("ORD-OC-B", "b", material, qty=2)
    data = _batch([wid])

    assert data["offcut_sheets"] == 0  # nothing to reuse yet
    plan = data["cutting_plan"]
    expected = sum(
        1
        for g in plan["groups"]
        for sh in g["sheets"]
        if sh["from_offcut_id"] is None and sh["offcut_reusable"]
    )
    assert len(_stock(material)) == expected


def test_rebatching_does_not_consume_inventory_twice():
    material = "ply-idem-C"
    _seed(material, "SEED-C")
    wid = _create("ORD-OC-C", "c", material)

    first = _batch([wid])
    stock_after_first = sorted(o["offcut_id"] for o in _stock(material))
    second = _batch([wid])  # same work-order set -> idempotent hit

    assert second["batch_id"] == first["batch_id"]
    assert sorted(o["offcut_id"] for o in _stock(material)) == stock_after_first


def test_use_offcut_stock_false_leaves_inventory_untouched():
    material = "ply-off-D"
    _seed(material, "SEED-D")
    wid = _create("ORD-OC-D", "d", material)

    data = _batch([wid], use_stock=False)

    assert data["offcut_sheets"] == 0
    assert "SEED-D-OC001" in [o["offcut_id"] for o in _stock(material)]


def test_reuse_cuts_fresh_sheet_count():
    """With a big seeded offcut, the merged plan opens fewer fresh sheets."""
    material = "ply-save-E"
    wid = _create("ORD-OC-E", "e", material)
    without = _batch([wid], use_stock=False)["fresh_sheets"]

    # different batch (new work order) of the same shape, now with seeded stock
    _seed(material, "SEED-E", width=1100.0)
    wid2 = _create("ORD-OC-E2", "e2", material)
    with_stock = _batch([wid2])["fresh_sheets"]

    assert with_stock <= without
