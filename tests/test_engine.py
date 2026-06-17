"""Golden-sample decomposition tests (ai_ctx §17.3 formulas, mm)."""

from app.engine import engineer
from app.schemas import CabinetInput
from tests.conftest import make_order

CV = "module2.v1"


def _by_name(pkg):
    return {p.name: p for p in pkg.panels}


def test_b302435_base_golden():
    """B302435 base 30x24x34.5 in -> W=762, D=609.6, H=876.3 mm."""
    pkg = engineer(make_order(), "WO-TEST", "fp", CV)
    assert pkg.status == "engineering_ready"
    parts = _by_name(pkg)

    # base has: side, bottom, back, stretcher, 1 adjustable shelf; no top
    assert set(parts) == {"side", "bottom", "back", "stretcher", "adjustable_shelf"}
    assert "top" not in parts

    side = parts["side"]
    assert (side.length, side.width) == (876.3, 609.6)         # finished H x D
    assert (side.cut_length, side.cut_width) == (876.3, 608.6)  # cut (H-vr) x (D-eb)
    assert side.quantity == 2
    assert side.edge_banding == ["front"]
    assert side.thickness == 18.0

    bottom = parts["bottom"]
    assert (bottom.length, bottom.width) == (726.0, 591.6)       # W-2t, D-t
    assert (bottom.cut_length, bottom.cut_width) == (726.0, 590.6)

    back = parts["back"]
    assert (back.length, back.width) == (876.3, 732.0)           # H, W-2t+2g
    assert back.edge_banding == []

    stretcher = parts["stretcher"]
    assert stretcher.quantity == 2
    assert (stretcher.length, stretcher.width) == (726.0, 101.6)

    shelf = parts["adjustable_shelf"]
    assert (shelf.length, shelf.width) == (726.0, 571.6)         # W-2t, D-t-20
    assert (shelf.cut_length, shelf.cut_width) == (724.0, 569.6)  # -2eb each
    assert shelf.edge_banding == ["front", "back", "left", "right"]


def test_wall_has_top_and_vertical_reduction():
    """W301236 wall 30x12x36 in; wall gets a top and vr=2 on side/back cut length."""
    cab = CabinetInput(
        cabinet_id="C010",
        cabinet_code="W301236",
        type="wall",
        width=30,
        depth=12,
        height=36,
        quantity=1,
        material="plywood-3/4",
        finish="white-shaker",
    )
    pkg = engineer(make_order(cabinet=cab), "WO-T", "fp", CV)
    parts = _by_name(pkg)
    assert "top" in parts
    assert "stretcher" not in parts

    H = round(36 * 25.4, 1)  # 914.4
    side = parts["side"]
    assert side.length == H                  # finished keeps full H
    assert side.cut_length == round(H - 2.0, 1)  # cut applies vr


def test_quantity_expands_into_instances():
    cab = CabinetInput(
        cabinet_id="C001",
        cabinet_code="B302435",
        type="base",
        width=30,
        depth=24,
        height=34.5,
        quantity=3,
        material="plywood-3/4",
        finish="white-shaker",
    )
    pkg = engineer(make_order(cabinet=cab), "WO-T", "fp", CV)
    assert len(pkg.cabinets) == 3
    assert {c.cabinet_id for c in pkg.cabinets} == {"C001-1", "C001-2", "C001-3"}
    # 5 part rows per instance
    assert len(pkg.panels) == 15
    # all panel ids unique and sequential
    assert pkg.panels[0].panel_id == "P0001"
    assert len({p.panel_id for p in pkg.panels}) == 15


def test_unsupported_type_blocks():
    cab = CabinetInput(
        cabinet_id="C099",
        cabinet_code="SB362435",
        type="sink_base",
        width=36,
        depth=24,
        height=34.5,
        quantity=1,
        material="plywood",
        finish="white",
    )
    pkg = engineer(make_order(cabinet=cab), "WO-T", "fp", CV)
    assert pkg.status == "engineering_blocked"
    assert pkg.blockers[0].code == "UNSUPPORTED_CABINET_CODE"
    assert pkg.blockers[0].owner == "module2"


def test_cut_list_groups_by_material():
    pkg = engineer(make_order(), "WO-T", "fp", CV)
    assert len(pkg.cut_list) == 1
    group = pkg.cut_list[0]
    assert group.material == "plywood-3/4"
    assert set(group.panels) == {p.panel_id for p in pkg.panels}
