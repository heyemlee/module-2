"""Module 2 HTTP routes (API contract §3).

POST creates a production engineering package from an approved cabinet order;
GET reads it back by work_order_id for Module 3. Both return the unified
`ApiResponse` envelope.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app import service
from app.db import get_db
from app.responses import ApiResponse
from app.schemas import ApprovedCabinetOrderPackage, CuttingBatchRequest, QuickCutRequest

router = APIRouter(prefix="/api/module2", tags=["production-packages"])

_FORM_PATH = Path(__file__).parent / "static" / "construction_form.html"


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


@router.get(
    "/production-packages/{work_order_id}/cutting-plan",
    response_class=PlainTextResponse,
)
def read_cutting_plan(
    work_order_id: str,
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Worker-readable cut sheet (text). The structured plan is in the JSON package."""
    text = service.get_cutting_plan_text(db, work_order_id)
    if text is None:
        return PlainTextResponse(
            f"No production package for work_order_id '{work_order_id}'",
            status_code=404,
        )
    return PlainTextResponse(text)


@router.get(
    "/production-packages/{work_order_id}/plan",
    response_model=ApiResponse,
)
def recompute_plan(
    work_order_id: str,
    response: Response,
    objective: str = "waste",
    stages: int = 3,
    db: Session = Depends(get_db),
) -> ApiResponse:
    """Re-nest the stored panels under a chosen mode (省料 stages=3 | 少翻板 stages=2,
    objective waste|throughput) so the UI can compare without re-engineering."""
    result = service.recompute_cutting_plan(db, work_order_id, objective, stages)
    if result.status == "not_found":
        response.status_code = 404
    return result


@router.post("/quick-cut", response_model=ApiResponse)
def quick_cut(request: QuickCutRequest) -> ApiResponse:
    """Generate a cutting plan directly from panel dimensions — no cabinet decomposition."""
    return service.quick_cut(request.panels, request.stages, request.objective)


@router.post("/cutting-batches", response_model=ApiResponse)
def create_batch(
    request: CuttingBatchRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse:
    """Merge several engineered orders into one cross-order cutting plan."""
    result = service.create_cutting_batch(
        db,
        request.work_order_ids,
        request.batch_id,
        use_offcut_stock=request.use_offcut_stock,
        objective=request.objective,
    )
    if result.status == "batch_failed":
        response.status_code = 422
    return result


@router.get("/offcut-stock", response_model=ApiResponse)
def list_offcut_stock(db: Session = Depends(get_db)) -> ApiResponse:
    """Available recovered offcuts that future batches will reuse before fresh stock."""
    return service.list_offcut_stock(db)


@router.get("/contract", response_model=ApiResponse)
def get_contract() -> ApiResponse:
    """JSON Schema of the input/output contracts — the shared interface for Module 1
    (produces input) and Module 3 (reads output). No DB; generated from the models."""
    return service.get_contract()


@router.get("/construction-form", response_class=HTMLResponse)
def construction_form() -> HTMLResponse:
    """Browser form the factory fills in to confirm the pending construction rules
    (back inset, shelf setback, dado, board sizes, sink base...). Works offline too."""
    return HTMLResponse(_FORM_PATH.read_text(encoding="utf-8"))


@router.post("/construction-rules", response_model=ApiResponse)
def submit_construction_rules(payload: dict) -> ApiResponse:
    """Receive the factory's filled construction-rules form (free-form JSON)."""
    return service.save_construction_rules(payload)


@router.get("/cutting-batches/{batch_id}", response_model=ApiResponse)
def read_batch(
    batch_id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse:
    result = service.get_cutting_batch(db, batch_id)
    if result.status == "not_found":
        response.status_code = 404
    return result


@router.get(
    "/cutting-batches/{batch_id}/cutting-plan",
    response_class=PlainTextResponse,
)
def read_batch_cutting_plan(
    batch_id: str,
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Worker-readable cut sheet for a batch (pieces tagged by order)."""
    text = service.get_cutting_batch_text(db, batch_id)
    if text is None:
        return PlainTextResponse(
            f"No cutting batch for batch_id '{batch_id}'", status_code=404
        )
    return PlainTextResponse(text)
