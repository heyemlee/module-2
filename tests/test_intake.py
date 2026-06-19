"""Intake filter (non-cabinets skipped) + cabinet<->panel correspondence guard."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.intake import is_cabinet, partition_cabinets
from app.main import app
from app.schemas import CabinetInput
from tests.conftest import make_order

init_db()
client = TestClient(app)


def _post(order):
    return client.post(
        "/api/module2/production-packages", json=order.model_dump(mode="json")
    )


def _cab(**kw) -> CabinetInput:
    base = dict(
        cabinet_id="X", cabinet_code="W3636T", type="wall",
        width=36, depth=12, height=36, quantity=1,
        material="ply", finish="white",
    )
    base.update(kw)
    return CabinetInput(**base)


# --- is_cabinet / partition (mirrors kabi isCarcass) ---


def test_real_cabinet_is_kept():
    assert is_cabinet(_cab(depth=12, adjustable_shelves=2)) is True
    assert is_cabinet(_cab(depth=24, door_qty=2)) is True
    assert is_cabinet(_cab(depth=24, drawer_qty=3, door_qty=0)) is True


def test_filler_panel_toekick_is_filtered():
    # zero depth + no doors/drawers/shelves = filler / panel / toe-kick
    assert is_cabinet(_cab(cabinet_code="TK9", depth=0)) is False
    assert is_cabinet(_cab(cabinet_code="WP1360", depth=0, door_qty=0)) is False
    assert is_cabinet(_cab(cabinet_code="BF0435", depth=0)) is False


def test_positive_depth_without_counts_is_still_a_cabinet():
    # module-2's own golden inputs carry no door/drawer counts; depth>0 keeps them.
    assert is_cabinet(_cab(depth=24, door_qty=0, drawer_qty=0)) is True


def test_partition_splits_and_preserves_order():
    cabs = [
        _cab(cabinet_id="c1", depth=24, door_qty=2),
        _cab(cabinet_id="f1", cabinet_code="TK9", depth=0),
        _cab(cabinet_id="c2", depth=12, adjustable_shelves=1),
    ]
    keep, filtered = partition_cabinets(cabs)
    assert [c.cabinet_id for c in keep] == ["c1", "c2"]
    assert [c.cabinet_id for c in filtered] == ["f1"]


# --- end-to-end through the HTTP service ---


def test_mixed_order_builds_cabinets_and_reports_fillers():
    order = make_order(
        order_id="ORD-INTAKE-MIX",
        cabinets=[
            _cab(cabinet_id="C1", cabinet_code="W3636T", type="wall",
                 depth=12, door_qty=2, adjustable_shelves=2),
            _cab(cabinet_id="F1", cabinet_code="TK9", depth=0, height=96, width=4.5),
            _cab(cabinet_id="F2", cabinet_code="WP1360", depth=0, height=60, width=13),
        ],
    )
    body = _post(order).json()
    assert body["status"] == "engineering_ready"
    wid = body["data"]["work_order_id"]
    full = client.get(f"/api/module2/production-packages/{wid}").json()["data"]
    # only the real cabinet was engineered; the two fillers were filtered + reported.
    assert {c["cabinet_code"] for c in full["cabinets"]} == {"W3636T"}
    assert full["filtered_non_cabinets"] == ["TK9", "WP1360"]


def test_order_of_only_fillers_blocks_clearly():
    order = make_order(
        order_id="ORD-INTAKE-FILLERS",
        cabinets=[
            _cab(cabinet_id="F1", cabinet_code="TK9", depth=0, height=96, width=4.5),
            _cab(cabinet_id="F2", cabinet_code="BF0435", depth=0, height=35, width=4),
        ],
    )
    body = _post(order).json()
    assert body["status"] == "gate_failed"
    assert body["blockers"][0]["code"] == "NO_STANDARD_CABINETS"


def test_correspondence_conserves_panels_for_a_normal_order():
    body = _post(make_order(order_id="ORD-INTAKE-CORR")).json()
    wid = body["data"]["work_order_id"]
    full = client.get(f"/api/module2/production-packages/{wid}").json()["data"]
    codes = {b["code"] for b in full["blockers"]}
    assert "PANEL_COUNT_MISMATCH" not in codes
    assert "CABINET_NO_PANELS" not in codes
    # conservation: pieces placed == panels decomposed (by quantity)
    expected = sum(p["quantity"] for p in full["panels"])
    placed = sum(
        1
        for g in full["cutting_plan"]["groups"]
        for s in g["sheets"]
        for strip in s["strips"]
        for block in strip["blocks"]
        for _ in block["pieces"]
    )
    assert placed == expected
