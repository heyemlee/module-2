"""Deterministic cabinet -> panel decomposition (ai_ctx §17.3).

Pure functions, no FastAPI / DB dependency, so the orchestrator could later call
them as a tool. All geometry is computed in millimetres (input inches are
converted on the way in). Finished sizes feed the BOM; cut sizes (edge-band
allowance removed) feed actual cutting. Phase A produces a grouped cut list;
the stack_efficiency nesting is Phase B.
"""

from app.boards import get_board_config
from app.cutting import build_cutting_plan
from app.formula import evaluate
from app.ids import cabinet_instance_id, panel_id
from app.responses import Blocker
from app.rules import TypePart, get_library
from app.schemas import (
    ApprovedCabinetOrderPackage,
    CabinetRecord,
    CutGroup,
    EdgeBandingItem,
    PackageStatus,
    PanelBOM,
    ProductionEngineeringPackage,
)

# ---- Global constants (mm). Geometry constants live in cabinets.yaml now. ----
INCHES_TO_MM = 25.4
SHEET_SIZE = "1219.2x2438.4"
BANDING = "matching"

# part_catalog `edges:` name -> banded edges.
EDGE_SETS: dict[str, list[str]] = {
    "front": ["front"],
    "all": ["front", "back", "left", "right"],
    "none": [],
}


def r1(value: float) -> float:
    """Round to 0.1 mm."""
    return round(value + 0.0, 1)


def to_mm(inches: float) -> float:
    return r1(inches * INCHES_TO_MM)


def _part(
    name: str,
    qty: int,
    length: float,
    width: float,
    cut_length: float,
    cut_width: float,
    edges: list[str],
    thickness: float,
) -> dict:
    return {
        "name": name,
        "qty": qty,
        "length": r1(length),
        "width": r1(width),
        "cut_length": r1(cut_length),
        "cut_width": r1(cut_width),
        "edges": edges,
        "thickness": r1(thickness),
    }


def _resolve_qty(tp: TypePart, qty_fields: dict[str, int | None]) -> int:
    """A fixed integer, or an order field (with the part's default when omitted)."""
    if isinstance(tp.qty, int):
        return tp.qty
    value = qty_fields.get(tp.qty)
    return tp.default if value is None else value


def _infeasible_reason(
    specs: list[dict], usable_width: float, sheet_length: float
) -> str | None:
    """Why a cabinet's parts can't be cut, or None. Guards against silently emitting
    physically-invalid panels (a cabinet too small -> non-positive dims; a panel wider
    than the stock sheet -> can't nest, would overflow). Pure check over the formulas."""
    for s in specs:
        for dim in ("length", "width", "cut_length", "cut_width"):
            if s[dim] <= 0:
                return (
                    f"part '{s['name']}' has non-positive {dim} ({s[dim]}mm) — "
                    "cabinet too small to decompose"
                )
        if s["cut_width"] > usable_width:
            return (
                f"part '{s['name']}' cut width {s['cut_width']}mm exceeds usable "
                f"sheet width {usable_width}mm"
            )
        if s["cut_length"] > sheet_length:
            return (
                f"part '{s['name']}' cut length {s['cut_length']}mm exceeds "
                f"sheet length {sheet_length}mm"
            )
    return None


def decompose(
    cabinet_type: str,
    width_mm: float,
    depth_mm: float,
    height_mm: float,
    adjustable_shelves: int | None,
    fixed_shelves: int | None,
) -> list[dict]:
    """Return part specs for one cabinet from the data-driven rules (rules.py / YAML).

    Quantities are per-part (not expanded). Caller checks type support. All geometry
    comes from the `part_catalog` formulas — nothing here is cabinet-type-specific, so
    new types are added in YAML, not here. W/D/H are external dimensions in mm.
    """
    lib = get_library()
    rule = lib.rule_for_type(cabinet_type)
    assert rule is not None  # support checked by caller

    namespace: dict[str, float] = {
        "W": width_mm,
        "D": depth_mm,
        "H": height_mm,
        "vr": rule.vr,
        "tkr": rule.tkr,
        **lib.constants,
    }
    t_default = lib.constants["t"]
    qty_fields = {
        "adjustable_shelves": adjustable_shelves,
        "fixed_shelves": fixed_shelves,
    }

    parts: list[dict] = []
    for tp in rule.parts:
        qty = _resolve_qty(tp, qty_fields)
        if qty <= 0:
            continue
        geom = lib.geometry_for(tp.part)
        if geom is None:
            raise KeyError(
                f"cabinet type '{cabinet_type}' uses unknown part '{tp.part}'"
            )
        parts.append(
            _part(
                tp.part,
                qty,
                evaluate(geom.length, namespace),
                evaluate(geom.width, namespace),
                evaluate(geom.cut_length, namespace),
                evaluate(geom.cut_width, namespace),
                EDGE_SETS[geom.edges],
                geom.thickness if geom.thickness is not None else t_default,
            )
        )
    return parts


def engineer(
    order: ApprovedCabinetOrderPackage,
    work_order_id: str,
    input_fingerprint: str,
    contract_version: str,
) -> ProductionEngineeringPackage:
    """Build a full ProductionEngineeringPackage from a gate-passed order.

    Unsupported cabinet types/codes do not raise — they become module2-owned
    blockers and the package status becomes `engineering_blocked`.
    """
    lib = get_library()
    board = get_board_config()
    eb_mm = lib.constants["eb"]
    cabinets: list[CabinetRecord] = []
    panels: list[PanelBOM] = []
    edge_banding: list[EdgeBandingItem] = []
    blockers: list[Blocker] = []

    panel_seq = 0
    for ci, cab in enumerate(order.cabinets):
        # Resolve carcass from the real cabinet code (longest family prefix), falling
        # back to the order's `type`. Corners/appliance/open-shelf carry their reason.
        carcass_type, blocked_reason = lib.resolve_carcass(cab.cabinet_code, cab.type)
        if blocked_reason is not None:
            blockers.append(
                Blocker(
                    code="UNSUPPORTED_CABINET_CODE",
                    owner="module2",
                    field=f"cabinets[{ci}].cabinet_code",
                    message=f"Cabinet '{cab.cabinet_code}': {blocked_reason}",
                )
            )
            continue

        rule = lib.rule_for_type(carcass_type) if carcass_type else None
        if rule is None or not rule.can_auto_decompose:
            inferred = lib.type_for_code(cab.cabinet_code)
            reason = (
                f"decomposition for type '{carcass_type}' is not yet confirmed"
                if rule is not None
                else f"no decomposition rule for cabinet type '{cab.type}'"
            )
            blockers.append(
                Blocker(
                    code="UNSUPPORTED_CABINET_CODE",
                    owner="module2",
                    field=f"cabinets[{ci}].cabinet_code",
                    message=(
                        f"{reason} (code '{cab.cabinet_code}')"
                        + (f"; did you mean type '{inferred}'?" if inferred else "")
                    ),
                )
            )
            continue

        w_mm, d_mm, h_mm = to_mm(cab.width), to_mm(cab.depth), to_mm(cab.height)
        # Shelf counts default inside decompose() via each part's `default` in YAML.
        specs = decompose(
            carcass_type, w_mm, d_mm, h_mm, cab.adjustable_shelves, cab.fixed_shelves
        )

        # Feasibility guard: don't emit non-positive or oversize panels to the saw.
        # Check against this cabinet's material stock (a wide panel may fit larger stock).
        mat_board = board.for_material(cab.material or "")
        reason = _infeasible_reason(
            specs, mat_board.usable_width, mat_board.sheet_length
        )
        if reason is not None:
            blockers.append(
                Blocker(
                    code="CABINET_NOT_MANUFACTURABLE",
                    owner="module2",
                    field=f"cabinets[{ci}]",
                    message=f"Cabinet '{cab.cabinet_code}': {reason}",
                )
            )
            continue

        # Expand by quantity into independent cabinet instances.
        for n in range(1, cab.quantity + 1):
            inst_id = cabinet_instance_id(cab.cabinet_id, n)
            inst_panel_ids: list[str] = []
            for spec in specs:
                panel_seq += 1
                pid = panel_id(panel_seq)
                inst_panel_ids.append(pid)
                panels.append(
                    PanelBOM(
                        panel_id=pid,
                        cabinet_id=inst_id,
                        name=spec["name"],
                        length=spec["length"],
                        width=spec["width"],
                        thickness=spec["thickness"],
                        cut_length=spec["cut_length"],
                        cut_width=spec["cut_width"],
                        quantity=spec["qty"],
                        material=cab.material or "",
                        # Carcass panels carry NO door finish: they cut/group by box
                        # material+thickness (box colour is in `material`). Door colour
                        # lives on the CabinetRecord; the box edge band = box colour.
                        finish="",
                        grain_direction="length",
                        edge_banding=spec["edges"],
                        production_note="",
                    )
                )
                if spec["edges"]:
                    edge_banding.append(
                        EdgeBandingItem(
                            panel_id=pid,
                            edges=spec["edges"],
                            banding=BANDING,
                            thickness=eb_mm,
                        )
                    )
            cabinets.append(
                CabinetRecord(
                    cabinet_id=inst_id,
                    source_cabinet_id=cab.cabinet_id,
                    cabinet_code=cab.cabinet_code,
                    # Report the carcass actually decomposed, not the raw input hint —
                    # the real code (e.g. 3DRB -> base) overrides cab.type.
                    type=carcass_type,
                    width=cab.width,
                    depth=cab.depth,
                    height=cab.height,
                    panels=inst_panel_ids,
                    finish=cab.finish or "",  # door finish preserved for Module 3
                    attributes=cab.attributes,
                )
            )

    cut_list = _group_cut_list(panels)
    cutting_plan = build_cutting_plan(panels, order_id=order.order_id)
    # Integrity: every cabinet must yield panels and every cut piece must trace back to
    # a cabinet, with counts matching. A mismatch is a real bug, so it blocks loudly.
    blockers.extend(_verify_correspondence(cabinets, panels, cutting_plan))
    status = (
        PackageStatus.engineering_blocked.value
        if blockers
        else PackageStatus.engineering_ready.value
    )

    return ProductionEngineeringPackage(
        work_order_id=work_order_id,
        source_order_id=order.order_id,
        status=status,
        contract_version=contract_version,
        input_fingerprint=input_fingerprint,
        cabinets=cabinets,
        panels=panels,
        cut_list=cut_list,
        cutting_plan=cutting_plan,
        edge_banding_list=edge_banding,
        blockers=blockers,
    )


def _verify_correspondence(cabinets, panels, cutting_plan) -> list[Blocker]:
    """Check cabinet <-> panel <-> cut-piece correspondence; counts must match.

    Guards the 柔单 merge: a decomposed cabinet must produce panels, and every panel
    must be cut exactly `quantity` times and trace to a real cabinet. Catches panels
    lost or mixed up in nesting. Returns blockers (empty = consistent).
    """
    blockers: list[Blocker] = []
    cabinet_ids = {c.cabinet_id for c in cabinets}

    # 1. Every cabinet that was decomposed must own at least one panel.
    panel_cabinet_ids = {p.cabinet_id for p in panels}
    for c in cabinets:
        if c.cabinet_id not in panel_cabinet_ids:
            blockers.append(
                Blocker(
                    code="CABINET_NO_PANELS",
                    owner="module2",
                    field=f"cabinets[{c.cabinet_id}]",
                    message=f"cabinet '{c.cabinet_id}' ({c.cabinet_code}) produced no panels",
                )
            )

    # 2. Every cut piece placed exactly `quantity` times per panel, traced to a cabinet.
    expected = {p.panel_id: p.quantity for p in panels}
    placed: dict[str, int] = {}
    for group in cutting_plan.groups:
        for sheet in group.sheets:
            for strip in sheet.strips:
                for block in strip.blocks:
                    for piece in block.pieces:
                        placed[piece.panel_id] = placed.get(piece.panel_id, 0) + 1
                        if piece.cabinet_id not in cabinet_ids:
                            blockers.append(
                                Blocker(
                                    code="PANEL_CABINET_UNLINKED",
                                    owner="module2",
                                    field="cutting_plan",
                                    message=f"cut piece '{piece.panel_id}' references unknown "
                                    f"cabinet '{piece.cabinet_id}'",
                                )
                            )

    for pid, qty in expected.items():
        if placed.get(pid, 0) != qty:
            blockers.append(
                Blocker(
                    code="PANEL_COUNT_MISMATCH",
                    owner="module2",
                    field=f"panel.{pid}",
                    message=f"panel '{pid}' decomposed x{qty} but cut-planned "
                    f"x{placed.get(pid, 0)}",
                )
            )

    return blockers


def _group_cut_list(panels: list[PanelBOM]) -> list[CutGroup]:
    """Phase A: group panels by material + thickness + finish + sheet size."""
    groups: dict[tuple, CutGroup] = {}
    for p in panels:
        key = (p.material, p.thickness, p.finish, SHEET_SIZE)
        group = groups.get(key)
        if group is None:
            group = CutGroup(
                group_id=f"CUT-GROUP-{len(groups) + 1:03d}",
                material=p.material,
                thickness=p.thickness,
                finish=p.finish,
                sheet_size=SHEET_SIZE,
                panels=[],
            )
            groups[key] = group
        group.panels.append(p.panel_id)
    return list(groups.values())
