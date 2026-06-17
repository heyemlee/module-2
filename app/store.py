"""Persistence + idempotency for production engineering packages.

One row per generated package, keyed by `work_order_id` (PK) and the
idempotency key (unique). The full `ProductionEngineeringPackage` is stored as
JSON so reads return exactly what was generated — Module 3 pulls it verbatim by
work_order_id. A new `cabinet_list_version` yields a new key -> new package,
never an in-place overwrite (API contract §9b).
"""

from datetime import UTC, datetime

from sqlalchemy import String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.schemas import ProductionEngineeringPackage


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
