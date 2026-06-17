"""Module 2 HTTP routes (API contract §3).

POST creates a production engineering package from an approved cabinet order;
GET reads it back by work_order_id for Module 3. Both return the unified
`ApiResponse` envelope.
"""

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app import service
from app.db import get_db
from app.responses import ApiResponse
from app.schemas import ApprovedCabinetOrderPackage

router = APIRouter(prefix="/api/module2", tags=["production-packages"])


@router.post("/production-packages", response_model=ApiResponse)
def create_package(
    order: ApprovedCabinetOrderPackage,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ApiResponse:
    result = service.create_production_package(db, order, idempotency_key)
    if result.status == "gate_failed":
        response.status_code = 422
    return result


@router.get("/production-packages/{work_order_id}", response_model=ApiResponse)
def read_package(
    work_order_id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse:
    result = service.get_production_package(db, work_order_id)
    if result.status == "not_found":
        response.status_code = 404
    return result
