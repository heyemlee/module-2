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
    # Salice correction: base back height = H - tkr (4.5" toe-kick+rail) = 876.3-114.3
    assert (back.length, back.width) == (762.0, 732.0)           # H-tkr, W-2t+2g
    assert back.edge_banding == []

    stretcher = parts["stretcher"]
    assert stretcher.quantity == 2
    assert (stretcher.length, stretcher.width) == (726.0, 76.2)   # 3" stretcher

    shelf = parts["adjustable_shelf"]
    assert (shelf.length, shelf.width) == (726.0, 571.6)         # W-2t, D-t-20
    assert (shelf.cut_length, shelf.cut_width) == (724.0, 569.6)  # -2eb each
    assert shelf.edge_banding == ["front", "back", "left", "right"]


def test_carcass_panels_drop_door_finish_and_merge_one_cut_group():
    """Box panels carry NO door finish — box colour is in `material`, and the box edge
    band = box colour (production flowchart 核心规则). Two cabinets with the same box
    material but different door finishes must cut as ONE group, not fragment by colour.
    """
    order = make_order(
        cabinets=[
            CabinetInput(
                cabinet_id="C1", cabinet_code="B302435", type="base",
                width=30, depth=24, height=34.5, quantity=1,
                material="White Birch plywood 18mm", finish="SM-Antracita",
            ),
            CabinetInput(
                cabinet_id="C2", cabinet_code="B302435", type="base",
                width=30, depth=24, height=34.5, quantity=1,
                material="White Birch plywood 18mm", finish="SM-Blanco",
            ),
        ]
    )
    pkg = engineer(order, "WO-FF", "fp", CV)
    assert pkg.status == "engineering_ready"
    # carcass panels carry no door finish ...
    assert all(p.finish == "" for p in pkg.panels)
    # ... but the door finish is preserved at cabinet level for Module 3 (doors).
    assert {c.finish for c in pkg.cabinets} == {"SM-Antracita", "SM-Blanco"}
    # same box material + thickness -> ONE cutting group, not split by door colour.
    assert len(pkg.cutting_plan.groups) == 1
    assert pkg.cutting_plan.groups[0].material == "White Birch plywood 18mm"


def test_edge_banding_ls_notation_by_board_length():
    """L/S label notation is geometric: the board's longer pair of edges = L, shorter = S.
    front/back run along `length`, left/right along `width`. Side front (the tall 876mm
    edge) is L; an all-4-banded shelf is L×2 + S×2 (matches the production flowchart).
    """
    from app.schemas import ls_notation

    # side 876.3 x 457.2, front-banded -> front runs along length(876) = the long edge.
    assert ls_notation(["front"], 876.3, 457.2) == "L×1"
    # shelf 726 x 591.6 banded all four -> L×2 (front/back=726) + S×2 (left/right=591).
    assert ls_notation(["front", "back", "left", "right"], 726.0, 591.6) == "L×2 + S×2"
    # back panel, no banding.
    assert ls_notation([], 762.0, 732.0) == ""
    # a panel wider than long flips which pair is L: front/back become the short edges.
    assert ls_notation(["front"], 300.0, 800.0) == "S×1"

    # end-to-end: the computed field rides on every PanelBOM in the package.
    pkg = engineer(make_order(), "WO-LS", "fp", CV)
    parts = _by_name(pkg)
    assert parts["side"].edge_banding_ls == "L×1"               # front of the side = long
    assert parts["adjustable_shelf"].edge_banding_ls == "L×2 + S×2"
    assert parts["back"].edge_banding_ls == ""                  # back unbanded


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


def test_missing_material_defaults_to_standard_stock():
    # M1 omits box material -> engine defaults it to White Birch 18mm, no blocker.
    cab = CabinetInput(
        cabinet_id="C001", cabinet_code="B302435", type="base",
        width=30, depth=24, height=34.5, quantity=1, material=None, finish=None,
    )
    pkg = engineer(make_order(cabinet=cab), "WO-DEF", "fp", CV)
    assert pkg.status == "engineering_ready"
    assert pkg.panels and all(p.material == "White Birch plywood 18mm" for p in pkg.panels)


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
