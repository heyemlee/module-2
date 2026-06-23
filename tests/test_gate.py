"""One failing case per gate rule; assert the blocker code/owner."""

from app.gate import validate_gate
from app.schemas import Approval, CabinetInput, ConfirmationItem, Source
from tests.conftest import make_order


def _codes(blockers):
    return {b.code for b in blockers}


def test_valid_order_passes():
    assert validate_gate(make_order()) == []


def test_non_final_stage_blocks():
    order = make_order(source=Source(stage="round1", cabinet_list_version="v1"))
    blockers = validate_gate(order)
    assert "NOT_FINAL_ORDER" in _codes(blockers)
    assert all(b.owner == "module1" for b in blockers)


def test_missing_approval_blocks():
    order = make_order(
        approval=Approval(
            customer_confirmed=True, sales_confirmed=True, designer_approved=False
        )
    )
    blockers = validate_gate(order)
    assert "UNAPPROVED_ORDER" in _codes(blockers)
    assert any(b.field == "approval.designer_approved" for b in blockers)


def test_open_confirmation_item_blocks():
    order = make_order(
        confirmation_required_items=[ConfirmationItem(item_id="CI-1", closed=False)]
    )
    assert "OPEN_CONFIRMATION_ITEM" in _codes(validate_gate(order))


def test_empty_cabinet_list_blocks():
    order = make_order(cabinets=[])
    assert "EMPTY_CABINET_LIST" in _codes(validate_gate(order))


def test_missing_material_passes_gate():
    # Box material is optional now — the engine defaults it to standard carcass stock.
    cab = CabinetInput(
        cabinet_id="C001",
        cabinet_code="B302435",
        type="base",
        width=30,
        depth=24,
        height=34.5,
        quantity=1,
        material="",
        finish="white",
    )
    assert "MISSING_FIELD" not in _codes(validate_gate(make_order(cabinet=cab)))


def test_invalid_dimension_blocks():
    cab = CabinetInput(
        cabinet_id="C001",
        cabinet_code="B302435",
        type="base",
        width=0,
        depth=24,
        height=34.5,
        quantity=1,
        material="plywood",
        finish="white",
    )
    assert "INVALID_DIMENSION" in _codes(validate_gate(make_order(cabinet=cab)))


def test_null_material_and_finish_pass_gate():
    # material/finish nullable and no longer gate-required (engine defaults box material).
    cab = CabinetInput(
        cabinet_id="C001", cabinet_code="B302435", type="base",
        width=30, depth=24, height=34.5, quantity=1, material=None, finish=None,
    )
    assert "MISSING_FIELD" not in _codes(validate_gate(make_order(cabinet=cab)))


def test_non_inches_units_blocks():
    order = make_order()
    order.units = "mm"
    codes = _codes(validate_gate(order))
    assert "UNSUPPORTED_UNITS" in codes


def test_invalid_quantity_blocks():
    cab = CabinetInput(
        cabinet_id="C001",
        cabinet_code="B302435",
        type="base",
        width=30,
        depth=24,
        height=34.5,
        quantity=0,
        material="plywood",
        finish="white",
    )
    assert "INVALID_QUANTITY" in _codes(validate_gate(make_order(cabinet=cab)))
