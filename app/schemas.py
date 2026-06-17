"""Module 2 contracts: input from Module 1, output for Module 3.

These Pydantic models *are* the API contract (see `module-2-api-contract.md`).
Input dimensions are inches; output panel dimensions are millimetres (the factory
cutting spec is authoritative — see `ai_ctx.md` §17). Keep field names stable:
adding fields is fine, renaming/removing requires a new `contract_version`.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.responses import Blocker

# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class CabinetType(StrEnum):
    base = "base"
    wall = "wall"
    tall = "tall"


class SourceStage(StrEnum):
    final = "final"
    round1 = "round1"
    preliminary = "preliminary"
    estimate = "estimate"


class PackageStatus(StrEnum):
    gate_failed = "gate_failed"
    engineering_blocked = "engineering_blocked"
    engineering_ready = "engineering_ready"


# ---------------------------------------------------------------------------
# Input — ApprovedCabinetOrderPackage (from Module 1, dimensions in inches)
# ---------------------------------------------------------------------------


class Project(BaseModel):
    customer_name: str
    address: str | None = None


class Approval(BaseModel):
    customer_confirmed: bool = False
    sales_confirmed: bool = False
    designer_approved: bool = False


class Source(BaseModel):
    stage: str
    layout_version: str | None = None
    cabinet_list_version: str


class ConfirmationItem(BaseModel):
    """An item Module 1 flagged as needing confirmation. `closed` must be true
    for the order to pass the gate."""

    item_id: str
    closed: bool = False
    note: str | None = None


class CabinetInput(BaseModel):
    cabinet_id: str
    cabinet_code: str
    type: str
    width: float       # inches
    depth: float       # inches
    height: float      # inches
    quantity: int
    material: str
    finish: str
    # Optional shelf counts; default to standard-library values when omitted.
    adjustable_shelves: int | None = None
    fixed_shelves: int | None = None


class ApprovedCabinetOrderPackage(BaseModel):
    order_id: str
    project: Project
    approval: Approval
    source: Source
    cabinets: list[CabinetInput] = Field(default_factory=list)
    confirmation_required_items: list[ConfirmationItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Output — ProductionEngineeringPackage (for Module 3, dimensions in mm)
# ---------------------------------------------------------------------------


class PanelBOM(BaseModel):
    panel_id: str                 # e.g. P0001
    cabinet_id: str               # expanded instance id, e.g. C001-1
    name: str                     # left_side / top / bottom / back / stretcher / ...
    length: float                 # finished length (mm, along 2438.4 long axis)
    width: float                  # finished width (mm, along 1219.2 short axis)
    thickness: float              # mm
    cut_length: float             # cutting length incl. edge-band allowance (mm)
    cut_width: float              # cutting width (mm)
    quantity: int
    material: str
    finish: str
    grain_direction: str | None = None
    edge_banding: list[str] = Field(default_factory=list)  # front / all / []
    production_note: str = ""


class CabinetRecord(BaseModel):
    cabinet_id: str               # expanded instance id
    source_cabinet_id: str        # original id from Module 1
    cabinet_code: str
    type: str
    width: float                  # inches (as received)
    depth: float
    height: float
    panels: list[str] = Field(default_factory=list)  # panel_ids


class CutGroup(BaseModel):
    """Phase A: grouping by material/thickness/finish/sheet. Phase B will add the
    stack_efficiency nesting/layout payload."""

    group_id: str
    material: str
    thickness: float
    finish: str
    sheet_size: str               # e.g. "1219.2x2438.4"
    panels: list[str] = Field(default_factory=list)


class EdgeBandingItem(BaseModel):
    panel_id: str
    edges: list[str]
    banding: str
    thickness: float = 1.0        # mm


class ProductionEngineeringPackage(BaseModel):
    work_order_id: str
    source_order_id: str
    status: str
    contract_version: str
    input_fingerprint: str
    cabinets: list[CabinetRecord] = Field(default_factory=list)
    panels: list[PanelBOM] = Field(default_factory=list)
    cut_list: list[CutGroup] = Field(default_factory=list)
    edge_banding_list: list[EdgeBandingItem] = Field(default_factory=list)
    blockers: list[Blocker] = Field(default_factory=list)
