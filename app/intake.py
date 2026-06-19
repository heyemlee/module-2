"""Intake filter — keep standard carcass cabinets, skip fillers / panels / toe-kicks.

Mirrors kabi-console's `isCarcass` rule (approved-order-package.ts): a line item is a
real cabinet when it has interior parts — doors, drawers, or shelves. Pure fillers,
decorative panels, toe-kicks and moldings carry none of those and have zero depth; they
are flat parts Module 2 does not decompose. We filter them out so an order that mixes
them with real cabinets still produces the cabinets, instead of failing wholesale.

Module 1 (kabi) filters too; this is Module 2's own independent guard ("都要过滤").
"""

from app.schemas import CabinetInput


def _has_interior_parts(cab: CabinetInput) -> bool:
    return (
        (cab.door_qty or 0) > 0
        or (cab.drawer_qty or 0) > 0
        or (cab.adjustable_shelves or 0) > 0
        or (cab.fixed_shelves or 0) > 0
    )


def is_cabinet(cab: CabinetInput) -> bool:
    """True for a standard carcass to decompose.

    A filler / panel / toe-kick has no interior parts AND no depth (it is a flat 2D
    part). Anything with parts, or with positive depth, is treated as a cabinet — the
    gate and the manufacturability guard catch genuinely malformed cabinets later.
    """
    if _has_interior_parts(cab):
        return True
    return cab.depth > 0


def partition_cabinets(
    cabinets: list[CabinetInput],
) -> tuple[list[CabinetInput], list[CabinetInput]]:
    """Split into (cabinets_to_build, filtered_non_cabinets), order preserved."""
    keep: list[CabinetInput] = []
    filtered: list[CabinetInput] = []
    for cab in cabinets:
        (keep if is_cabinet(cab) else filtered).append(cab)
    return keep, filtered
