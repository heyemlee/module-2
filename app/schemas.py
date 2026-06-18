"""Module 2 contracts: input from Module 1, output for Module 3.

These Pydantic models *are* the API contract (see `module-2-api-contract.md`).
Input dimensions are inches; output panel dimensions are millimetres (the factory
cutting spec is authoritative — see `ai_ctx.md` §17). Keep field names stable:
adding fields is fine, renaming/removing requires a new `contract_version`.
"""

from enum import StrEnum
from typing import Any, Literal

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
    width: float       # in `units` (inches by default)
    depth: float
    height: float      # actual physical height (not the rounded code height)
    quantity: int = 1
    # Nullable until the order matures to `final` — the gate requires them at final.
    material: str | None = None
    finish: str | None = None
    # Optional shelf counts; default to standard-library values when omitted.
    adjustable_shelves: int | None = None
    fixed_shelves: int | None = None
    # Pipeline pass-through: data Module 2 doesn't compute but carries to its output
    # for Module 3 (e.g. hinge side L/R, door/drawer counts, install location,
    # exposed/finished sides). Open by design so new needs don't break the contract.
    attributes: dict[str, Any] = Field(default_factory=dict)


class ApprovedCabinetOrderPackage(BaseModel):
    order_id: str
    project: Project
    approval: Approval
    source: Source
    units: str = "inches"  # Module 2 V1 accepts inches; declared not assumed (gate checks)
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
    attributes: dict[str, Any] = Field(default_factory=dict)  # passed through for Module 3


class CutGroup(BaseModel):
    """Phase A: grouping by material/thickness/finish/sheet. Phase B will add the
    stack_efficiency nesting/layout payload."""

    group_id: str
    material: str
    thickness: float
    finish: str
    sheet_size: str               # e.g. "1219.2x2438.4"
    panels: list[str] = Field(default_factory=list)


# ---- Cutting plan (Phase B): real guillotine nesting, not just grouping ----


class CutPiece(BaseModel):
    """One physical panel placed on a strip (cut dimensions, mm).

    Carries material/thickness/finish so pieces from many panels — and many orders
    in a batch — can be grouped uniformly without the source PanelBOM.
    """

    panel_id: str
    name: str
    cabinet_id: str               # instance id, for sorting cut pieces back per cabinet
    order_id: str = ""            # source order, set when batching across orders
    material: str
    thickness: float
    finish: str
    length: float                 # cut_length, runs along the strip's long axis
    width: float                  # cut_width, equals the strip rip width


class CutBlock(BaseModel):
    """Stage-3 unit: pieces of one length, side by side, ripped from a strip block.

    All pieces share `length` (one crosscut frees the block); their widths sum within
    the strip's rip width. A block with a single piece is the degenerate 2-stage case.
    """

    length: float                 # block height along the long axis (shared crosscut)
    pieces: list[CutPiece] = Field(default_factory=list)


class CutStrip(BaseModel):
    """A rip-width strip crosscut into blocks (stage 2), each block ripped into pieces
    of that block's length (stage 3) — the 3-stage guillotine structure."""

    strip_no: int
    rip_width: float              # strip width (1219.2 short axis)
    usable_length: float          # length budget along the 2438.4 long axis
    used_length: float            # sum of block lengths + kerfs
    offcut_length: float          # end-of-strip remainder
    offcut_reusable: bool
    skip_trim: bool = False       # full-length piece: ends not trimmed (usable = full sheet)
    blocks: list[CutBlock] = Field(default_factory=list)


class CutSheet(BaseModel):
    """One bin ripped into strips: a fresh stock sheet, or a recovered offcut."""

    sheet_no: int
    sheet_size: str
    from_offcut_id: str | None = None  # set when this bin is a reused offcut, not fresh stock
    pattern_id: str = ""          # sheets with the same layout share this -> one book
    usable_width: float
    usable_length: float = 0.0    # length budget along the long axis
    used_width: float             # sum of rip widths + kerfs
    offcut_width: float           # leftover width band (full usable length)
    offcut_reusable: bool
    strips: list[CutStrip] = Field(default_factory=list)


class PatternStrip(BaseModel):
    """One rip of a cutting pattern's shared layout (geometry only, no panel ids)."""

    rip_width: float
    crosscuts: list[float]        # crosscut lengths along the strip, in cut order
    skip_trim: bool = False


class CuttingPattern(BaseModel):
    """A distinct sheet layout cut over N stock sheets (book cutting).

    The layout is identical across the repeats; only the panel labels differ per
    sheet. `books` is the stack height of each saw pass (<= max_stack), e.g. [4, 1]
    means cut 4 sheets stacked, then 1 — the industry-standard pattern×repeat×book form.
    """

    pattern_id: str
    repeat_count: int             # stock sheets sharing this layout
    books: list[int]              # stack height per stacked saw pass, sums to repeat_count
    sheet_nos: list[int]          # concrete sheet_nos with this layout
    layout: list[PatternStrip] = Field(default_factory=list)


class CuttingPlanGroup(BaseModel):
    """Sheets for one material + thickness + finish group."""

    group_id: str
    material: str
    thickness: float
    finish: str
    sheet_size: str
    sheets_total: int             # total bins used (fresh + reused offcuts)
    fresh_sheets: int = 0         # fresh full stock sheets consumed (the real cost)
    offcut_sheets: int = 0        # recovered offcuts reused as bins
    distinct_patterns: int = 0    # number of distinct layouts (fewer = more stackable)
    pieces_total: int
    utilization: float            # placed area / bins used, percent
    patterns: list[CuttingPattern] = Field(default_factory=list)
    sheets: list[CutSheet] = Field(default_factory=list)


class CuttingPlan(BaseModel):
    objective: str = "waste"      # waste (fewest sheets) | throughput (fewest patterns)
    stages: int = 3               # guillotine passes: 3 (省料) | 2 (少翻板, 1 flip)
    sheets_total: int = 0
    fresh_sheets: int = 0
    offcut_sheets: int = 0
    groups: list[CuttingPlanGroup] = Field(default_factory=list)


class OffcutStockItem(BaseModel):
    """A recovered offcut available as reusable stock (a full-length width band)."""

    offcut_id: str
    material: str
    thickness: float
    finish: str
    width: float
    length: float
    source_batch_id: str


class CuttingBatchRequest(BaseModel):
    """Orchestrator asks Module 2 to merge several engineered orders into one
    cross-order cutting plan (so they share stock sheets)."""

    work_order_ids: list[str] = Field(default_factory=list)
    batch_id: str | None = None   # optional override; otherwise derived from the ids
    use_offcut_stock: bool = True  # reuse recovered offcuts before cutting fresh sheets
    objective: Literal["waste", "throughput"] = "waste"  # fewest sheets vs fewest patterns


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
    cutting_plan: CuttingPlan | None = None
    edge_banding_list: list[EdgeBandingItem] = Field(default_factory=list)
    blockers: list[Blocker] = Field(default_factory=list)
