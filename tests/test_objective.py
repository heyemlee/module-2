"""Objective switch: throughput trades sheets for fewer, repeated (stackable) patterns."""

from app.cutting import build_cutting_plan_multi
from app.engine import engineer
from app.schemas import CabinetInput
from tests.conftest import make_order

CV = "module2.v1"


def _panels(qty: int):
    cab = CabinetInput(
        cabinet_id="C1", cabinet_code="W301236", type="wall",
        width=30, depth=12, height=36, quantity=qty,
        material="plywood-3/4", finish="white-shaker",
    )
    return engineer(make_order(cabinet=cab), "WO-T", "fp", CV).panels


def _distinct(plan):
    return sum(g.distinct_patterns for g in plan.groups)


def _placed_ids(plan):
    return sorted(
        p.panel_id
        for g in plan.groups
        for sh in g.sheets
        for st in sh.strips
        for b in st.blocks
        for p in b.pieces
    )


def test_throughput_has_fewer_patterns_than_waste():
    panels = _panels(5)  # 5 identical wall cabinets
    waste = build_cutting_plan_multi([("ORD-A", panels)], objective="waste")
    thru = build_cutting_plan_multi([("ORD-A", panels)], objective="throughput")

    # throughput collapses identical cabinets into far fewer, repeated patterns
    assert _distinct(thru) < _distinct(waste)
    # ...at the cost of (>=) sheets — the documented tradeoff
    assert thru.sheets_total >= waste.sheets_total
    assert thru.objective == "throughput"


def test_throughput_patterns_repeat_per_identical_cabinet():
    panels = _panels(5)
    thru = build_cutting_plan_multi([("ORD-A", panels)], objective="throughput")
    # every distinct cabinet layout repeats once per instance (here: 5)
    for g in thru.groups:
        for pat in g.patterns:
            assert pat.repeat_count == 5
            assert sum(pat.books) == 5  # e.g. [4, 1] with max_stack 4


def test_both_objectives_conserve_pieces():
    panels = _panels(3)
    waste = build_cutting_plan_multi([("ORD-A", panels)], objective="waste")
    thru = build_cutting_plan_multi([("ORD-A", panels)], objective="throughput")
    # no piece lost or duplicated either way
    assert _placed_ids(waste) == _placed_ids(thru)
    expected = sorted(p.panel_id for p in panels for _ in range(p.quantity))
    assert _placed_ids(thru) == expected


def test_batch_endpoint_accepts_objective():
    from fastapi.testclient import TestClient

    from app.db import init_db
    from app.main import app
    from app.schemas import Source

    init_db()
    client = TestClient(app)

    def _wid(oid):
        order = make_order(
            order_id=oid, source=Source(stage="final", cabinet_list_version="v"),
            cabinet=CabinetInput(
                cabinet_id="C1", cabinet_code="W301236", type="wall",
                width=30, depth=12, height=36, quantity=4,
                material="plywood-3/4", finish="white-shaker",
            ),
        )
        return client.post(
            "/api/module2/production-packages", json=order.model_dump(mode="json")
        ).json()["data"]["work_order_id"]

    wid = _wid("ORD-OBJ-1")
    resp = client.post(
        "/api/module2/cutting-batches",
        json={"work_order_ids": [wid], "objective": "throughput",
              "use_offcut_stock": False},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["objective"] == "throughput"
    assert data["distinct_patterns"] >= 1
