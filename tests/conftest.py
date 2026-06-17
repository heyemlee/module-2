"""Shared test fixtures / builders."""

# Point the DB at a throwaway temp file BEFORE any app module imports settings,
# so tests never touch the real ./data dir.
import os
import tempfile

os.environ["DATABASE_URL"] = (
    "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="module2-test-"), "test.db")
)

from app.schemas import (
    Approval,
    ApprovedCabinetOrderPackage,
    CabinetInput,
    Project,
    Source,
)


def make_order(**overrides) -> ApprovedCabinetOrderPackage:
    """A valid, gate-passing base-cabinet order (B302435, 30x24x34.5 in)."""
    cab = overrides.pop("cabinet", None) or CabinetInput(
        cabinet_id="C001",
        cabinet_code="B302435",
        type="base",
        width=30,
        depth=24,
        height=34.5,
        quantity=1,
        material="plywood-3/4",
        finish="white-shaker",
    )
    base = dict(
        order_id="ORD-2026-001",
        project=Project(customer_name="Test Customer"),
        approval=Approval(
            customer_confirmed=True, sales_confirmed=True, designer_approved=True
        ),
        source=Source(stage="final", cabinet_list_version="cabinet-v1"),
        cabinets=[cab],
        confirmation_required_items=[],
    )
    base.update(overrides)
    return ApprovedCabinetOrderPackage(**base)
