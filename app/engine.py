"""Deterministic cabinet -> panel decomposition (ai_ctx §17.3).

Pure functions, no FastAPI / DB dependency, so the orchestrator could later call
them as a tool. All geometry is computed in millimetres (input inches are
converted on the way in). Finished sizes feed the BOM; cut sizes (edge-band
allowance removed) feed actual cutting. Phase A produces a grouped cut list;
the stack_efficiency nesting is Phase B.
"""

from app.ids import cabinet_instance_id, panel_id
from app.responses import Blocker
from app.rules import get_library
from app.schemas import (
    ApprovedCabinetOrderPackage,
    CabinetRecord,
    CutGroup,
    EdgeBandingItem,
    PackageStatus,
    PanelBOM,
    ProductionEngineeringPackage,
)

# ---- Global constants (mm), ai_ctx §17.3 ----
INCHES_TO_MM = 25.4
T = 18.0                 # panel thickness
GROOVE = 3.0            # back-panel groove per side (g)
EDGE_BAND = 1.0        # edge banding thickness (eb)
ADJ_SHELF_SETBACK = 20.0
STRETCHER_DEPTH = 101.6  # 4"
WALL_VERTICAL_REDUCTION = 2.0  # vr, wall only

SHEET_SIZE = "1219.2x2438.4"
BANDING = "matching"

# Edge banding edge-sets
_FRONT = ["front"]
_ALL = ["front", "back", "left", "right"]
_NONE: list[str] = []


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
) -> dict:
    return {
        "name": name,
        "qty": qty,
        "length": r1(length),
        "width": r1(width),
        "cut_length": r1(cut_length),
        "cut_width": r1(cut_width),
        "edges": edges,
    }


def decompose(
    cabinet_type: str,
    width_mm: float,
    depth_mm: float,
    height_mm: float,
    adjustable_shelves: int,
    fixed_shelves: int,
) -> list[dict]:
    """Return part specs for one cabinet (quantities are per-part, not expanded).

    Caller is responsible for type support; this assumes a known type and applies
    the §17.3 table. W/D/H are external dimensions in mm.
    """
    W, D, H = width_mm, depth_mm, height_mm
    vr = WALL_VERTICAL_REDUCTION if cabinet_type == "wall" else 0.0
    lib = get_library()
    rule = lib.rule_for_type(cabinet_type)
    assert rule is not None  # support checked by caller

    parts: list[dict] = []

    # Side x2: finished H x D ; cut (H-vr) x (D-eb) ; front edge
    parts.append(_part("side", 2, H, D, H - vr, D - EDGE_BAND, _FRONT))

    # Top (wall/tall): finished (W-2t) x (D-t) ; cut x (D-t-eb) ; front
    if rule.has_top:
        parts.append(
            _part("top", 1, W - 2 * T, D - T, W - 2 * T, D - T - EDGE_BAND, _FRONT)
        )

    # Bottom (all): same as top geometry
    if rule.has_bottom:
        parts.append(
            _part("bottom", 1, W - 2 * T, D - T, W - 2 * T, D - T - EDGE_BAND, _FRONT)
        )

    # Back (all): finished H x (W-2t+2g) ; cut (H-vr) x (W-2t+2g) ; no edge
    back_width = W - 2 * T + 2 * GROOVE
    parts.append(_part("back", 1, H, back_width, H - vr, back_width, _NONE))

    # Stretcher (base): finished (W-2t) x 101.6 ; cut same ; no edge
    if rule.stretchers:
        parts.append(
            _part(
                "stretcher",
                rule.stretchers,
                W - 2 * T,
                STRETCHER_DEPTH,
                W - 2 * T,
                STRETCHER_DEPTH,
                _NONE,
            )
        )

    # Adjustable shelves: finished (W-2t) x (D-t-20) ; cut (W-2t-2eb) x (D-t-20-2eb) ; all edges
    if adjustable_shelves > 0:
        adj_w = D - T - ADJ_SHELF_SETBACK
        parts.append(
            _part(
                "adjustable_shelf",
                adjustable_shelves,
                W - 2 * T,
                adj_w,
                W - 2 * T - 2 * EDGE_BAND,
                adj_w - 2 * EDGE_BAND,
                _ALL,
            )
        )

    # Fixed shelves: same geometry as bottom ; front edge
    if fixed_shelves > 0:
        parts.append(
            _part(
                "fixed_shelf",
                fixed_shelves,
                W - 2 * T,
                D - T,
                W - 2 * T,
                D - T - EDGE_BAND,
                _FRONT,
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
    cabinets: list[CabinetRecord] = []
    panels: list[PanelBOM] = []
    edge_banding: list[EdgeBandingItem] = []
    blockers: list[Blocker] = []

    panel_seq = 0
    for ci, cab in enumerate(order.cabinets):
        rule = lib.rule_for_type(cab.type)
        if rule is None or not rule.can_auto_decompose:
            inferred = lib.type_for_code(cab.cabinet_code)
            blockers.append(
                Blocker(
                    code="UNSUPPORTED_CABINET_CODE",
                    owner="module2",
                    field=f"cabinets[{ci}].cabinet_code",
                    message=(
                        f"No decomposition rule for cabinet type '{cab.type}' "
                        f"(code '{cab.cabinet_code}')"
                        + (f"; did you mean type '{inferred}'?" if inferred else "")
                    ),
                )
            )
            continue

        w_mm, d_mm, h_mm = to_mm(cab.width), to_mm(cab.depth), to_mm(cab.height)
        adj = cab.adjustable_shelves
        if adj is None:
            adj = rule.default_adjustable_shelves
        fixed = cab.fixed_shelves
        if fixed is None:
            fixed = rule.default_fixed_shelves

        specs = decompose(cab.type, w_mm, d_mm, h_mm, adj, fixed)

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
                        thickness=T,
                        cut_length=spec["cut_length"],
                        cut_width=spec["cut_width"],
                        quantity=spec["qty"],
                        material=cab.material,
                        finish=cab.finish,
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
                            thickness=EDGE_BAND,
                        )
                    )
            cabinets.append(
                CabinetRecord(
                    cabinet_id=inst_id,
                    source_cabinet_id=cab.cabinet_id,
                    cabinet_code=cab.cabinet_code,
                    type=cab.type,
                    width=cab.width,
                    depth=cab.depth,
                    height=cab.height,
                    panels=inst_panel_ids,
                )
            )

    cut_list = _group_cut_list(panels)
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
        edge_banding_list=edge_banding,
        blockers=blockers,
    )


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
