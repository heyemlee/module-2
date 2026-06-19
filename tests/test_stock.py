"""Per-material stock sheet sizes: each cutting group nests on its material's sheet."""

from app.boards import get_board_config
from app.engine import engineer
from app.schemas import CabinetInput
from tests.conftest import make_order

CV = "module2.v1"
CFG = get_board_config()


def _plan(material):
    cab = CabinetInput(
        cabinet_id="C1", cabinet_code="B302435", type="base",
        width=30, depth=24, height=34.5, quantity=1,
        material=material, finish="white",
    )
    return engineer(make_order(cabinet=cab), "WO-T", "fp", CV).cutting_plan


def test_for_material_picks_matching_stock():
    cleaf = CFG.for_material("Cleaf-LR22-19mm")
    assert (cleaf.sheet_width, cleaf.sheet_length) == (2065.0, 2800.0)
    # no match -> default 4x8
    default = CFG.for_material("White melamine plywood 18mm")
    assert (default.sheet_width, default.sheet_length) == (
        CFG.sheet_width,
        CFG.sheet_length,
    )


def test_plan_uses_material_stock_size():
    plywood = _plan("plywood-3/4")
    cleaf = _plan("Cleaf-LR22-19mm")
    assert plywood.groups[0].sheet_size == "1219.2x2438.4"   # default 4x8
    assert cleaf.groups[0].sheet_size == "2065.0x2800.0"     # Cleaf stock
    # both still place every panel (conservation), just on different stock
    for plan in (plywood, cleaf):
        placed = [
            p for g in plan.groups for sh in g.sheets
            for st in sh.strips for b in st.blocks for p in b.pieces
        ]
        assert len(placed) == 7
