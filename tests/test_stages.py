"""2-stage (少翻板 / single-flip) vs 3-stage (省料) cutting modes.

The factory saw is single-pusher and 要人翻: every guillotine stage beyond the first
costs a 90° re-feed. 2-stage mode guarantees one flip — each strip holds pieces of a
single width, one piece per block (no 3rd-stage re-rip). Asserted as the invariant
"no block has more than one piece", which is what an extra flip would create.
"""

from fastapi.testclient import TestClient

from app.boards import get_board_config
from app.cutting import _pack_into_sheets, build_cutting_plan
from app.db import init_db
from app.engine import engineer
from app.main import app
from app.schemas import CabinetInput, CutPiece, PanelBOM
from tests.conftest import make_order

CV = "module2.v1"
init_db()  # lifespan isn't run by a bare TestClient; create tables here.
client = TestClient(app)


def _panel(name, w, length, qty):
    return PanelBOM(
        panel_id=name, cabinet_id="C", name=name, length=length, width=w, thickness=18,
        cut_length=length, cut_width=w, quantity=qty, material="plywood-3/4",
        finish="white", grain_direction="length", edge_banding=[], production_note="",
    )


def _pieces(plan):
    return sorted(
        (p.length, p.width)
        for g in plan.groups for sh in g.sheets for st in sh.strips
        for b in st.blocks for p in b.pieces
    )


def _max_block(plan):
    return max(
        (len(b.pieces)
         for g in plan.groups for sh in g.sheets for st in sh.strips for b in st.blocks),
        default=0,
    )


def _piece(name, w, length):
    return CutPiece(
        panel_id=name, name=name, cabinet_id="C", order_id="O",
        material="plywood-3/4", thickness=18, finish="white", length=length, width=w,
    )


def test_two_stage_never_pairs_pieces_in_a_block():
    """Single-flip invariant: in 2-stage every block is exactly one piece."""
    panels = [_panel("wide", 600, 500, 2), _panel("narrow", 280, 900, 12)]
    plan2 = build_cutting_plan(panels, order_id="O", stages=2)
    assert plan2.stages == 2
    assert _max_block(plan2) == 1


def test_raw_three_stage_packer_pairs_same_length_narrow_pieces():
    """The 3-stage mechanism itself re-rips: narrow same-length parts share a block."""
    cfg = get_board_config()
    pieces = [_piece("wide", 600, 500) for _ in range(2)] + [
        _piece("narrow", 280, 900) for _ in range(12)
    ]
    sheets = _pack_into_sheets(pieces, cfg, two_stage=False)
    max_block = max(len(b.pieces) for s in sheets for st in s.strips for b in st.blocks)
    assert max_block >= 2


def test_material_mode_never_worse_than_labor_mode():
    """省料 (stages=3, best-of) must never burn more sheets than 少翻板 (stages=2)."""
    pkg = engineer(
        make_order(
            cabinet=CabinetInput(
                cabinet_id="C1", cabinet_code="B302435", type="base",
                width=30, depth=24, height=34.5, quantity=3,
                material="plywood-3/4", finish="white",
            )
        ),
        "WO-T", "fp", CV,
    )
    f2 = build_cutting_plan(pkg.panels, stages=2).fresh_sheets
    f3 = build_cutting_plan(pkg.panels, stages=3).fresh_sheets
    assert f3 <= f2  # before the best-of fix the greedy made 3-stage *worse*


def test_modes_place_the_same_pieces():
    """Switching mode changes the layout, never the set of pieces cut."""
    panels = [_panel("wide", 600, 500, 2), _panel("narrow", 280, 900, 12)]
    assert _pieces(build_cutting_plan(panels, stages=2)) == _pieces(
        build_cutting_plan(panels, stages=3)
    )


def test_recompute_endpoint_switches_mode():
    order = make_order(
        cabinet=CabinetInput(
            cabinet_id="C1", cabinet_code="B302435", type="base",
            width=30, depth=24, height=34.5, quantity=3,
            material="plywood-3/4", finish="white",
        )
    )
    created = client.post("/api/module2/production-packages", json=order.model_dump()).json()
    wid = created["data"]["work_order_id"]

    for stages in (2, 3):
        r = client.get(
            f"/api/module2/production-packages/{wid}/plan",
            params={"stages": stages, "objective": "waste"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["stages"] == stages


def test_recompute_unknown_work_order_is_404():
    r = client.get("/api/module2/production-packages/WO-nope/plan")
    assert r.status_code == 404
