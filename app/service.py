"""Use-case orchestration for production packages.

Sequences the pure pieces (gate -> idempotency -> engine -> store) and shapes the
unified `ApiResponse`. This is the only business layer that touches the DB; gate
and engine stay pure so they remain reusable as orchestrator tools.
"""

import json
import os
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import ids, store
from app.config import settings
from app.cutting import (
    build_cutting_plan,
    build_cutting_plan_multi,
    build_cutting_plan_with_stock,
    render_text,
)
from app.engine import engineer
from app.gate import validate_gate
from app.intake import partition_cabinets
from app.responses import ApiResponse, Blocker, failure, success
from app.schemas import (
    ApprovedCabinetOrderPackage,
    OffcutStockItem,
    PanelBOM,
    ProductionEngineeringPackage,
    QuickCutPanelInput,
)


def _package_data(pkg: ProductionEngineeringPackage) -> dict:
    return {
        "order_id": pkg.source_order_id,
        "work_order_id": pkg.work_order_id,
        "input_fingerprint": pkg.input_fingerprint,
        "package_url": f"/api/module2/production-packages/{pkg.work_order_id}",
    }


def create_production_package(
    db: Session,
    order: ApprovedCabinetOrderPackage,
    idempotency_key: str | None = None,
) -> ApiResponse:
    key = idempotency_key or ids.idempotency_key(
        order.order_id, order.source.cabinet_list_version
    )

    # 1. Idempotency: same key returns the existing package, never recomputed.
    existing = store.get_by_key(db, key)
    if existing is not None:
        pkg = store.load_package(existing)
        return ApiResponse(
            ok=pkg.status == "engineering_ready",
            status=pkg.status,
            data=_package_data(pkg),
            blockers=pkg.blockers,
        )

    # 2. Intake filter: drop fillers / panels / toe-kicks (non-cabinets) so an order
    #    that mixes them with real cabinets isn't failed wholesale. Mirrors kabi.
    carcasses, filtered = partition_cabinets(order.cabinets)
    filtered_codes = [c.cabinet_code or c.cabinet_id for c in filtered]
    if not carcasses:
        return failure(
            status="gate_failed",
            blockers=[
                Blocker(
                    code="NO_STANDARD_CABINETS",
                    owner="module1",
                    field="cabinets",
                    message="no standard cabinets to produce — all items were "
                    "fillers/panels/toe-kicks",
                )
            ],
        )
    order = order.model_copy(update={"cabinets": carcasses})

    # 3. Production gate (Module-1-owned input validation). Not persisted: the
    #    same version can be re-submitted once Module 1 fixes the source.
    gate_blockers: list[Blocker] = validate_gate(order)
    if gate_blockers:
        return failure(status="gate_failed", blockers=gate_blockers)

    # 4. Decompose + assemble the package.
    pkg = engineer(
        order,
        work_order_id=ids.work_order_id(
            order.order_id, order.source.cabinet_list_version
        ),
        input_fingerprint=ids.input_fingerprint(order),
        contract_version=settings.contract_version,
    )
    pkg.filtered_non_cabinets = filtered_codes

    # 5. Persist (ready or blocked) and respond.
    store.save(db, key, pkg, order.source.cabinet_list_version)
    return ApiResponse(
        ok=pkg.status == "engineering_ready",
        status=pkg.status,
        data=_package_data(pkg),
        blockers=pkg.blockers,
    )


def get_production_package(db: Session, work_order_id: str) -> ApiResponse:
    row = store.get_by_work_order_id(db, work_order_id)
    if row is None:
        return failure(
            status="not_found",
            blockers=[
                Blocker(
                    code="WORK_ORDER_NOT_FOUND",
                    owner="integration",
                    field="work_order_id",
                    message=f"No production package for work_order_id '{work_order_id}'",
                )
            ],
        )
    pkg = store.load_package(row)
    return success(status=pkg.status, data=pkg.model_dump())


def list_production_packages(db: Session, limit: int = 100) -> ApiResponse:
    """A browsable view of stored packages (newest first) — summary rows only."""
    items = []
    for row in store.list_packages(db, limit):
        pkg = store.load_package(row)
        items.append(
            {
                "work_order_id": row.work_order_id,
                "order_id": row.order_id,
                "status": row.status,
                "created_at": row.created_at,
                "cabinets": len(pkg.cabinets),
                "panels": len(pkg.panels),
                "sheets": pkg.cutting_plan.sheets_total if pkg.cutting_plan else 0,
                "package_url": f"/api/module2/production-packages/{row.work_order_id}",
            }
        )
    return success(status="ok", data={"count": len(items), "packages": items})


def get_cutting_plan_text(db: Session, work_order_id: str) -> str | None:
    """Worker-readable cut sheet, or None if the work order is unknown."""
    row = store.get_by_work_order_id(db, work_order_id)
    if row is None:
        return None
    pkg = store.load_package(row)
    if pkg.cutting_plan is None:
        return ""
    return render_text(pkg.cutting_plan)


def recompute_cutting_plan(
    db: Session, work_order_id: str, objective: str = "waste", stages: int = 3
) -> ApiResponse:
    """Re-nest a stored package's panels under a chosen objective/stages mode.

    The persisted plan is the default (waste, 3-stage); this lets the UI compare modes
    (省料 3-stage vs 少翻板 2-stage) without re-engineering the package. Pure recompute
    from the same panels — nothing is persisted.
    """
    row = store.get_by_work_order_id(db, work_order_id)
    if row is None:
        return failure(
            status="not_found",
            blockers=[
                Blocker(
                    code="WORK_ORDER_NOT_FOUND",
                    owner="integration",
                    field="work_order_id",
                    message=f"No production package for work_order_id '{work_order_id}'",
                )
            ],
        )
    pkg = store.load_package(row)
    obj = objective if objective in ("waste", "throughput") else "waste"
    stg = 2 if str(stages) == "2" else 3
    plan = build_cutting_plan(
        pkg.panels, order_id=pkg.source_order_id, objective=obj, stages=stg
    )
    return success(status="ok", data=plan.model_dump())


# --- Cutting batches (cross-order merged plans) ---


def _batch_data(batch_id: str, work_order_ids: list[str], plan) -> dict:
    return {
        "batch_id": batch_id,
        "work_order_ids": sorted(work_order_ids),
        "objective": plan.objective,
        "sheets_total": plan.sheets_total,
        "fresh_sheets": plan.fresh_sheets,
        "offcut_sheets": plan.offcut_sheets,
        "distinct_patterns": sum(g.distinct_patterns for g in plan.groups),
        "plan_url": f"/api/module2/cutting-batches/{batch_id}",
        "cutting_plan": plan.model_dump(),
    }


def create_cutting_batch(
    db: Session,
    work_order_ids: list[str],
    batch_id: str | None = None,
    use_offcut_stock: bool = True,
    objective: str = "waste",
) -> ApiResponse:
    """Merge several engineered orders into one cross-order cutting plan.

    `objective` picks waste (fewest sheets) or throughput (fewest distinct patterns,
    stackable). When `use_offcut_stock` is set (and objective=waste), available offcuts
    are nested onto first, consumed offcuts marked used, and fresh-sheet leftovers
    deposited back to inventory.
    """
    if not work_order_ids:
        return failure(
            status="batch_failed",
            blockers=[
                Blocker(
                    code="EMPTY_BATCH",
                    owner="integration",
                    field="work_order_ids",
                    message="work_order_ids must be a non-empty list",
                )
            ],
        )

    bid = batch_id or ids.batch_id(
        work_order_ids, objective=objective, use_offcut_stock=use_offcut_stock
    )

    # Idempotency: the same work-order set returns the existing batch unchanged and,
    # crucially, does NOT touch inventory a second time.
    existing = store.get_batch(db, bid)
    if existing is not None:
        plan = store.load_batch_plan(existing)
        return success(
            status="batch_ready",
            data=_batch_data(bid, store.load_batch_work_order_ids(existing), plan),
        )

    # Collect each order's panels; a missing or not-ready package blocks the batch.
    sources: list[tuple[str, list]] = []
    blockers: list[Blocker] = []
    for wid in work_order_ids:
        row = store.get_by_work_order_id(db, wid)
        if row is None:
            blockers.append(
                Blocker(
                    code="WORK_ORDER_NOT_FOUND",
                    owner="integration",
                    field=wid,
                    message=f"No production package for work_order_id '{wid}'",
                )
            )
            continue
        pkg = store.load_package(row)
        if pkg.status != "engineering_ready":
            blockers.append(
                Blocker(
                    code="PACKAGE_NOT_READY",
                    owner="integration",
                    field=wid,
                    message=f"package '{wid}' is '{pkg.status}', not engineering_ready",
                )
            )
            continue
        sources.append((pkg.source_order_id, pkg.panels))

    if blockers:
        return failure(status="batch_failed", blockers=blockers)

    if use_offcut_stock:
        result = build_cutting_plan_with_stock(
            sources, store.available_offcut_bins(db), objective=objective
        )
        store.consume_offcuts(db, result.consumed_offcut_ids, bid)
        store.deposit_offcuts(db, bid, result.new_offcuts)
        plan = result.plan
    else:
        plan = build_cutting_plan_multi(sources, objective=objective)

    store.save_batch(db, bid, work_order_ids, plan)
    return success(status="batch_ready", data=_batch_data(bid, work_order_ids, plan))


def get_cutting_batch(db: Session, batch_id: str) -> ApiResponse:
    row = store.get_batch(db, batch_id)
    if row is None:
        return failure(
            status="not_found",
            blockers=[
                Blocker(
                    code="BATCH_NOT_FOUND",
                    owner="integration",
                    field="batch_id",
                    message=f"No cutting batch for batch_id '{batch_id}'",
                )
            ],
        )
    plan = store.load_batch_plan(row)
    return success(
        status="batch_ready",
        data=_batch_data(batch_id, store.load_batch_work_order_ids(row), plan),
    )


def get_cutting_batch_text(db: Session, batch_id: str) -> str | None:
    """Worker-readable cut sheet for a batch, or None if unknown."""
    row = store.get_batch(db, batch_id)
    if row is None:
        return None
    return render_text(store.load_batch_plan(row))


def save_construction_rules(payload: dict) -> ApiResponse:
    """Append a factory construction-rules submission to data/ (one JSON per line).

    Free-form by design — these confirm pending §B items; an engineer maps them into
    cabinets.yaml / board_config.yaml. Persisted so submissions aren't lost."""
    record = {"received_at": datetime.now(UTC).isoformat(), "payload": payload}
    os.makedirs("data", exist_ok=True)
    with open(
        os.path.join("data", "construction_submissions.jsonl"), "a", encoding="utf-8"
    ) as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return success(
        status="received", data={"saved": True, "fields": sorted(payload.keys())}
    )


def get_contract() -> ApiResponse:
    """The module's input/output contracts as JSON Schema — the shared interface that
    Module 1 produces against (input) and Module 3 reads (output). Generated from the
    Pydantic models, so it can never drift from what the gate actually validates."""
    return success(
        status="ok",
        data={
            "contract_version": settings.contract_version,
            "input": ApprovedCabinetOrderPackage.model_json_schema(),
            "output": ProductionEngineeringPackage.model_json_schema(),
        },
    )


def quick_cut(
    panels: list[QuickCutPanelInput],
    stages: int = 3,
    objective: str = "waste",
) -> ApiResponse:
    """Cut a flat panel list by dimension — no cabinet decomposition needed."""
    bom = [
        PanelBOM(
            panel_id=f"P{i:04d}",
            cabinet_id="QUICK",
            name=f"panel-{i}",
            length=p.height,
            width=p.width,
            thickness=p.thickness,
            cut_length=p.height,
            cut_width=p.width,
            quantity=p.quantity,
            material=p.material,
            finish=p.finish or "",
            grain_direction="length",
        )
        for i, p in enumerate(panels, start=1)
    ]
    plan = build_cutting_plan(bom, order_id="QUICK", objective=objective, stages=stages)
    return success(status="ok", data=plan.model_dump())


def list_offcut_stock(db: Session) -> ApiResponse:
    """Available recovered offcuts (reusable stock)."""
    items = [
        OffcutStockItem(
            offcut_id=o.offcut_id,
            material=o.material,
            thickness=o.thickness,
            finish=o.finish,
            width=o.width,
            length=o.length,
            source_batch_id=o.source_batch_id,
        ).model_dump()
        for o in store.available_offcuts(db)
    ]
    return success(status="ok", data={"count": len(items), "offcuts": items})
