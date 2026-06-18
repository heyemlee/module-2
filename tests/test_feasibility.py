"""Feasibility guards: too-small or too-wide cabinets block, not emit bad panels."""

from app.engine import engineer
from app.schemas import CabinetInput
from tests.conftest import make_order

CV = "module2.v1"


def _engineer(code, ctype, w, d, h):
    cab = CabinetInput(
        cabinet_id="C1", cabinet_code=code, type=ctype,
        width=w, depth=d, height=h, quantity=1,
        material="plywood-3/4", finish="white-shaker",
    )
    return engineer(make_order(cabinet=cab), "WO-T", "fp", CV)


def test_tiny_cabinet_blocks_instead_of_negative_panels():
    # width 1" -> W-2t < 0; must block, never emit a negative-dimension panel
    pkg = _engineer("B011224", "base", w=1, d=24, h=34.5)
    assert pkg.status == "engineering_blocked"
    assert pkg.panels == []
    b = pkg.blockers[0]
    assert b.code == "CABINET_NOT_MANUFACTURABLE"
    assert b.owner == "module2"
    assert "too small" in b.message


def test_oversize_panel_blocks_instead_of_overflow():
    # 50" wide base -> back cut width (W-2t+2g) exceeds usable sheet width 1209.2mm
    pkg = _engineer("B503524", "base", w=50, d=24, h=34.5)
    assert pkg.status == "engineering_blocked"
    assert pkg.panels == []
    assert pkg.blockers[0].code == "CABINET_NOT_MANUFACTURABLE"
    assert "exceeds" in pkg.blockers[0].message


def test_normal_cabinet_still_ready():
    pkg = _engineer("B302435", "base", w=30, d=24, h=34.5)
    assert pkg.status == "engineering_ready"
    assert pkg.panels
    # every emitted panel has strictly positive cut dimensions
    assert all(p.cut_length > 0 and p.cut_width > 0 for p in pkg.panels)


def test_one_bad_cabinet_blocks_only_itself():
    good = CabinetInput(
        cabinet_id="C1", cabinet_code="B302435", type="base",
        width=30, depth=24, height=34.5, quantity=1,
        material="plywood-3/4", finish="white-shaker",
    )
    bad = CabinetInput(
        cabinet_id="C2", cabinet_code="B011224", type="base",
        width=1, depth=24, height=34.5, quantity=1,
        material="plywood-3/4", finish="white-shaker",
    )
    order = make_order()
    order.cabinets = [good, bad]
    pkg = engineer(order, "WO-T", "fp", CV)
    # blocked overall, but the good cabinet's panels are still produced
    assert pkg.status == "engineering_blocked"
    assert any(c.source_cabinet_id == "C1" for c in pkg.cabinets)
    assert all(c.source_cabinet_id != "C2" for c in pkg.cabinets)
    assert len(pkg.blockers) == 1
