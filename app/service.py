"""Use-case orchestration for production packages.

Sequences the pure pieces (gate -> idempotency -> engine -> store) and shapes the
unified `ApiResponse`. This is the only business layer that touches the DB; gate
and engine stay pure so they remain reusable as orchestrator tools.
"""

from sqlalchemy.orm import Session

from app import ids, store
from app.config import settings
from app.engine import engineer
from app.gate import validate_gate
from app.responses import ApiResponse, Blocker, failure, success
from app.schemas import ApprovedCabinetOrderPackage, ProductionEngineeringPackage


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

    # 2. Production gate (Module-1-owned input validation). Not persisted: the
    #    same version can be re-submitted once Module 1 fixes the source.
    gate_blockers: list[Blocker] = validate_gate(order)
    if gate_blockers:
        return failure(status="gate_failed", blockers=gate_blockers)

    # 3. Decompose + assemble the package.
    pkg = engineer(
        order,
        work_order_id=ids.work_order_id(
            order.order_id, order.source.cabinet_list_version
        ),
        input_fingerprint=ids.input_fingerprint(order),
        contract_version=settings.contract_version,
    )

    # 4. Persist (ready or blocked) and respond.
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
