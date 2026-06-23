"""Persistence + idempotency for production engineering packages.

One row per generated package, keyed by `work_order_id` (PK) and the
idempotency key (unique). The full `ProductionEngineeringPackage` is stored as
JSON so reads return exactly what was generated — Module 3 pulls it verbatim by
work_order_id. A new `cabinet_list_version` yields a new key -> new package,
never an in-place overwrite (API contract §9b).
"""

import json
from datetime import UTC, datetime

from sqlalchemy import Float, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.cutting import NewOffcut, OffcutBin
from app.db import Base
from app.schemas import CuttingPlan, ProductionEngineeringPackage


class ProductionPackage(Base):
    __tablename__ = "production_packages"

    work_order_id: Mapped[str] = mapped_column(String, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    order_id: Mapped[str] = mapped_column(String, index=True)
    cabinet_list_version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    input_fingerprint: Mapped[str] = mapped_column(String)
    package_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)


def get_by_key(db: Session, key: str) -> ProductionPackage | None:
    return db.scalar(
        select(ProductionPackage).where(ProductionPackage.idempotency_key == key)
    )


def get_by_work_order_id(db: Session, work_order_id: str) -> ProductionPackage | None:
    return db.get(ProductionPackage, work_order_id)


def save(
    db: Session,
    key: str,
    package: ProductionEngineeringPackage,
    cabinet_list_version: str,
) -> ProductionPackage:
    row = ProductionPackage(
        work_order_id=package.work_order_id,
        idempotency_key=key,
        order_id=package.source_order_id,
        cabinet_list_version=cabinet_list_version,
        status=package.status,
        input_fingerprint=package.input_fingerprint,
        package_json=package.model_dump_json(),
        created_at=datetime.now(UTC).isoformat(),
    )
    db.add(row)
    db.commit()
    return row


def load_package(row: ProductionPackage) -> ProductionEngineeringPackage:
    return ProductionEngineeringPackage.model_validate_json(row.package_json)


def list_packages(db: Session, limit: int = 100) -> list[ProductionPackage]:
    """Stored packages, newest first (created_at is ISO → lexical sort = chronological)."""
    return list(
        db.scalars(
            select(ProductionPackage)
            .order_by(ProductionPackage.created_at.desc())
            .limit(limit)
        )
    )


# --- Cutting batches (cross-order merged plans) ---


class ProductionBatch(Base):
    __tablename__ = "production_batches"

    batch_id: Mapped[str] = mapped_column(String, primary_key=True)
    work_order_ids: Mapped[str] = mapped_column(Text)  # JSON list, sorted
    sheets_total: Mapped[int] = mapped_column(Integer)
    plan_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)


def get_batch(db: Session, batch_id: str) -> ProductionBatch | None:
    return db.get(ProductionBatch, batch_id)


def save_batch(
    db: Session,
    batch_id: str,
    work_order_ids: list[str],
    plan: CuttingPlan,
) -> ProductionBatch:
    row = ProductionBatch(
        batch_id=batch_id,
        work_order_ids=json.dumps(sorted(work_order_ids)),
        sheets_total=plan.sheets_total,
        plan_json=plan.model_dump_json(),
        created_at=datetime.now(UTC).isoformat(),
    )
    db.add(row)
    db.commit()
    return row


def load_batch_plan(row: ProductionBatch) -> CuttingPlan:
    return CuttingPlan.model_validate_json(row.plan_json)


def load_batch_work_order_ids(row: ProductionBatch) -> list[str]:
    return json.loads(row.work_order_ids)


# --- Offcut stock (recovered material reused across batches) ---


class OffcutStock(Base):
    __tablename__ = "offcut_stock"

    offcut_id: Mapped[str] = mapped_column(String, primary_key=True)
    material: Mapped[str] = mapped_column(String, index=True)
    thickness: Mapped[float] = mapped_column(Float)
    finish: Mapped[str] = mapped_column(String)
    width: Mapped[float] = mapped_column(Float)
    length: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, index=True)  # available | consumed
    source_batch_id: Mapped[str] = mapped_column(String)
    consumed_by_batch_id: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String)


def available_offcuts(db: Session) -> list[OffcutStock]:
    """All reusable offcuts, ordered deterministically."""
    return list(
        db.scalars(
            select(OffcutStock)
            .where(OffcutStock.status == "available")
            .order_by(OffcutStock.width, OffcutStock.offcut_id)
        )
    )


def available_offcut_bins(db: Session) -> list[OffcutBin]:
    """Available offcuts as nesting bins for cutting.build_cutting_plan_with_stock."""
    return [
        OffcutBin(
            offcut_id=o.offcut_id,
            material=o.material,
            thickness=o.thickness,
            finish=o.finish,
            width=o.width,
            length=o.length,
        )
        for o in available_offcuts(db)
    ]


def deposit_offcuts(
    db: Session, batch_id: str, new_offcuts: list[NewOffcut]
) -> list[OffcutStock]:
    """Add fresh-sheet leftovers to inventory; ids are stable within a batch."""
    now = datetime.now(UTC).isoformat()
    rows: list[OffcutStock] = []
    for seq, oc in enumerate(new_offcuts, start=1):
        rows.append(
            OffcutStock(
                offcut_id=f"{batch_id}-OC{seq:03d}",
                material=oc.material,
                thickness=oc.thickness,
                finish=oc.finish,
                width=oc.width,
                length=oc.length,
                status="available",
                source_batch_id=batch_id,
                created_at=now,
            )
        )
    db.add_all(rows)
    db.commit()
    return rows


def consume_offcuts(db: Session, offcut_ids: list[str], batch_id: str) -> None:
    """Mark reused offcuts consumed by this batch."""
    for oid in offcut_ids:
        row = db.get(OffcutStock, oid)
        if row is not None and row.status == "available":
            row.status = "consumed"
            row.consumed_by_batch_id = batch_id
    db.commit()
