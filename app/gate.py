"""Production gate — Module-1-owned input validation.

`validate_gate` is a pure function: it takes an `ApprovedCabinetOrderPackage`
and returns a list of `Blocker`s. An empty list means the order may proceed to
decomposition. This covers the §5 gate rules of the API contract: only-final
orders, full approval, closed confirmation items, and presence/validity of the
required cabinet fields. Cabinet-code/rule support is checked later by the
engine (owner=module2) and surfaces as `engineering_blocked`, per ai_ctx §14.4.
"""

from app.responses import Blocker
from app.schemas import ApprovedCabinetOrderPackage


def validate_gate(order: ApprovedCabinetOrderPackage) -> list[Blocker]:
    blockers: list[Blocker] = []

    # --- Units must be inches (Module 2 V1 converts inches -> mm internally) ---
    if order.units != "inches":
        blockers.append(
            Blocker(
                code="UNSUPPORTED_UNITS",
                owner="integration",
                field="units",
                message=f"Module 2 V1 accepts inches only, got '{order.units}'",
            )
        )

    # --- Source must prove this is final, not Round 1 / estimate ---
    if order.source.stage != "final":
        blockers.append(
            Blocker(
                code="NOT_FINAL_ORDER",
                owner="module1",
                field="source.stage",
                message=f"source.stage must be 'final', got '{order.source.stage}'",
            )
        )

    # --- Full approval required ---
    approval_checks = {
        "approval.customer_confirmed": order.approval.customer_confirmed,
        "approval.sales_confirmed": order.approval.sales_confirmed,
        "approval.designer_approved": order.approval.designer_approved,
    }
    for field, ok in approval_checks.items():
        if not ok:
            blockers.append(
                Blocker(
                    code="UNAPPROVED_ORDER",
                    owner="module1",
                    field=field,
                    message=f"{field.split('.')[-1]} must be true",
                )
            )

    # --- No open confirmation-required items ---
    for i, item in enumerate(order.confirmation_required_items):
        if not item.closed:
            blockers.append(
                Blocker(
                    code="OPEN_CONFIRMATION_ITEM",
                    owner="module1",
                    field=f"confirmation_required_items[{i}]",
                    message=f"confirmation item '{item.item_id}' is not closed",
                )
            )

    # --- Cabinet list must be non-empty ---
    if not order.cabinets:
        blockers.append(
            Blocker(
                code="EMPTY_CABINET_LIST",
                owner="module1",
                field="cabinets",
                message="cabinet list is empty",
            )
        )

    # --- Per-cabinet field presence / validity ---
    for i, cab in enumerate(order.cabinets):
        prefix = f"cabinets[{i}]"
        if not cab.cabinet_code.strip():
            blockers.append(_missing(prefix, "cabinet_code"))
        if not cab.type.strip():
            blockers.append(_missing(prefix, "type"))
        # material/finish are NOT gate-required: a missing box material defaults to the
        # standard carcass stock in the engine (DEFAULT_BOX_MATERIAL), and door finish is a
        # Module-3 pass-through (Module 2 cuts box panels, not doors).
        for dim in ("width", "depth", "height"):
            if getattr(cab, dim) <= 0:
                blockers.append(
                    Blocker(
                        code="INVALID_DIMENSION",
                        owner="module1",
                        field=f"{prefix}.{dim}",
                        message=f"{dim} must be a positive number",
                    )
                )
        if cab.quantity <= 0:
            blockers.append(
                Blocker(
                    code="INVALID_QUANTITY",
                    owner="module1",
                    field=f"{prefix}.quantity",
                    message="quantity must be a positive integer",
                )
            )

    return blockers


def _missing(prefix: str, field: str) -> Blocker:
    return Blocker(
        code="MISSING_FIELD",
        owner="module1",
        field=f"{prefix}.{field}",
        message=f"{field} is required",
    )
