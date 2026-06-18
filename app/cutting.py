"""Cutting-plan nesting (ai_ctx §17.2/§17.3, Phase B).

Turns a flat panel list into a guillotine cutting plan a worker can follow刀-by-刀.
Pure functions, no FastAPI / DB dependency — the same `build_cutting_plan` works on
one order's panels today and on a merged multi-order batch later (just pass more
panels), per the §14.6 "zero-cost seam" stance.

Model (guillotine, fixed grain — panels are NOT rotated):
  1. RIP the stock sheet into strips along the long axis (2438.4mm).
  2. CROSSCUT each strip into blocks along its length; panel `cut_length` runs along
     the long axis.
  3. (3-stage only) re-RIP a block into several side-by-side pieces.
Two selectable modes (`stages`), since the factory saw is single-pusher and 要人翻 —
each guillotine stage past the first costs a 90° re-feed:
  - stages=2 (少翻板): strips are single-width, one piece per block — two passes, ONE
    flip. Matches the machine; costs a little material when part widths differ.
  - stages=3 (省料): allows the 3rd-stage re-rip, but the greedy can pack *worse* than
    2-stage, so it keeps whichever of the two burns fewer sheets (`_pack_for_waste`).
Efficiency comes from batching many same-width panels into one strip, not from rotation.

Phase B V1 scope: full T0 sheets only, kerf + edge trim accounted, offcuts recorded
for reuse. Stacking is surfaced as `pattern_id` (identical strips); reuse of recorded
offcuts as live inventory is a later step.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from app.boards import BoardConfig, get_board_config
from app.schemas import (
    CutBlock,
    CutPiece,
    CutSheet,
    CutStrip,
    CuttingPattern,
    CuttingPlan,
    CuttingPlanGroup,
    PanelBOM,
    PatternStrip,
)


def r1(value: float) -> float:
    """Round to 0.1 mm (matches engine.py)."""
    return round(value + 0.0, 1)


# --- Internal mutable working types (converted to schema models at the end) ---


@dataclass
class _Block:
    length: float
    pieces: list[CutPiece] = field(default_factory=list)


@dataclass
class _Strip:
    rip_width: float
    usable_length: float
    skip_trim: bool
    blocks: list[_Block] = field(default_factory=list)


@dataclass
class _Sheet:
    remaining: float                 # remaining width budget
    usable_width: float              # starting width budget (full sheet, or offcut width)
    usable_length: float             # length budget for strips on this bin
    from_offcut_id: str | None = None  # set when this bin is a reused offcut
    strips: list[_Strip] = field(default_factory=list)


@dataclass(frozen=True)
class OffcutBin:
    """An available recovered offcut to nest onto (a full-length width band)."""

    offcut_id: str
    material: str
    thickness: float
    finish: str
    width: float
    length: float


@dataclass(frozen=True)
class NewOffcut:
    """A reusable offcut produced by cutting a fresh sheet (deposit to inventory)."""

    material: str
    thickness: float
    finish: str
    width: float
    length: float


@dataclass
class PlanResult:
    """A cutting plan plus the inventory deltas it implies."""

    plan: CuttingPlan
    consumed_offcut_ids: list[str] = field(default_factory=list)
    new_offcuts: list[NewOffcut] = field(default_factory=list)


def _pack_region(
    width: float,
    length: float,
    pieces: list[CutPiece],
    cfg: BoardConfig,
    allow_skip: bool,
    two_stage: bool = False,
) -> tuple[list[_Strip], list[CutPiece]]:
    """Guillotine pack of one region (a fresh sheet or an offcut).

    Stage 1: rip strips, each strip's width = the widest remaining piece that fits.
    Stage 2: crosscut the strip into blocks (each block = one shared crosscut length).

    `two_stage=False` (3-stage / 省料):
        Stage 3: rip each block into several side-by-side pieces whose widths
        subset-sum-fit the rip width — packs tighter (less waste) but needs a THIRD
        saw pass, i.e. an extra 90° re-feed on a manual-flip saw.
    `two_stage=True` (2-stage / 少翻板):
        Each strip holds only pieces of EXACTLY the rip width, one piece per block
        (no 3rd-stage re-rip). Two passes total — rip then crosscut, one flip. Costs
        more material when part widths differ, but matches a single-pusher 要人翻 saw.

    Greedy on width then length; the within-strip fill is DP-optimal. Returns
    (strips, leftover pieces). `allow_skip` lets a strip take the full sheet length for
    a piece longer than the trimmed length (96" panels); offcuts pass False.
    """
    kerf = cfg.saw_kerf
    pool: list[CutPiece | None] = list(pieces)
    strips: list[_Strip] = []
    w_left = width

    while True:
        fits = [i for i, p in enumerate(pool) if p is not None and p.width <= w_left + 1e-6]
        if not fits:
            break
        rip = max(pool[i].width for i in fits)

        # 2-stage strips are single-width (no re-rip); 3-stage admits any narrower piece.
        if two_stage:
            members0 = [i for i in fits if abs(pool[i].width - rip) <= 1e-6]
        else:
            members0 = [i for i in fits if pool[i].width <= rip + 1e-6]
        skip = allow_skip and max(pool[i].length for i in members0) > length
        strip_len = cfg.sheet_length if skip else length
        strip = _Strip(rip_width=rip, usable_length=strip_len, skip_trim=skip)

        if two_stage:
            # One pass: subset-sum the exact-width pieces' lengths into the strip; each
            # chosen piece is its own single-piece block (a plain crosscut to length).
            sizes = [round((pool[i].length + kerf) * 10) for i in members0]
            for k in _max_fill(sizes, round((strip_len + kerf) * 10)):
                i = members0[k]
                strip.blocks.append(_Block(pool[i].length, [pool[i]]))
                pool[i] = None
        else:
            l_left = strip_len
            while True:
                cand = [
                    i
                    for i, p in enumerate(pool)
                    if p is not None and p.width <= rip + 1e-6 and p.length <= l_left + 1e-6
                ]
                if not cand:
                    break
                block_len = max(pool[i].length for i in cand)
                members = [i for i in cand if pool[i].length == block_len]
                sizes = [round((pool[i].width + kerf) * 10) for i in members]
                picked = _max_fill(sizes, round((rip + kerf) * 10))
                if not picked:
                    break
                chosen = [members[k] for k in picked]
                strip.blocks.append(_Block(block_len, [pool[i] for i in chosen]))
                for i in chosen:
                    pool[i] = None
                l_left -= block_len + kerf

        if not strip.blocks:
            break  # safety: nothing placeable
        strips.append(strip)
        w_left -= rip + kerf

    return strips, [p for p in pool if p is not None]


def _pack_into_sheets(
    pieces: list[CutPiece],
    cfg: BoardConfig,
    offcut_bins: list[_Sheet] | None = None,
    two_stage: bool = False,
) -> list[_Sheet]:
    """Pack all pieces into bins: recovered offcuts first (ascending width), then fresh
    full sheets, each filled by the guillotine packer until nothing remains."""
    remaining = list(pieces)
    result: list[_Sheet] = []

    for bin_ in sorted(offcut_bins or [], key=lambda b: b.usable_width):
        strips, remaining = _pack_region(
            bin_.usable_width, bin_.usable_length, remaining, cfg,
            allow_skip=False, two_stage=two_stage,
        )
        if strips:
            bin_.strips = strips
            result.append(bin_)

    while remaining:
        strips, rest = _pack_region(
            cfg.usable_width, cfg.usable_length, remaining, cfg,
            allow_skip=True, two_stage=two_stage,
        )
        if not strips:
            break  # safety; feasibility guard prevents un-packable pieces upstream
        sheet = _Sheet(
            remaining=0.0,
            usable_width=cfg.usable_width,
            usable_length=cfg.usable_length,
        )
        sheet.strips = strips
        result.append(sheet)
        remaining = rest

    return result


def _fresh_count(sheets: list[_Sheet]) -> int:
    """Fresh full stock sheets (the real material cost; reused offcuts are free)."""
    return sum(1 for s in sheets if s.from_offcut_id is None)


def _pack_for_waste(pieces, cfg, make_bins, stages: int) -> list[_Sheet]:
    """Least-material pack. stages==2 is strict single-flip 2-stage.

    stages==3 also tries the 3-stage pack and keeps whichever burns fewer fresh sheets
    — tie goes to 2-stage (one flip). The 3-stage greedy can be *worse* than 2-stage on
    real cabinets (it sets the rip to the widest piece, then fills with longer-but-narrower
    pieces, wasting width), so "省料" must never lose to "少翻板": pick the better of both.
    `make_bins` rebuilds the offcut bins per attempt (packing mutates them in place).
    """
    s2 = _pack_into_sheets(list(pieces), cfg, make_bins(), two_stage=True)
    if stages == 2:
        return s2
    s3 = _pack_into_sheets(list(pieces), cfg, make_bins(), two_stage=False)
    f2, f3 = _fresh_count(s2), _fresh_count(s3)
    if (f3, len(s3)) < (f2, len(s2)):
        return s3
    return s2


def _max_fill(sizes: list[int], capacity: int) -> list[int]:
    """Subset-sum DP: pick item indices whose sizes sum to the most <= capacity.

    0/1 knapsack with value = size, reconstructed via parent pointers. This is the
    single-bin-optimal fill that replaces first-fit: each sheet is packed as full as
    the saw allows, not just 'first strip that fits'. Pseudo-polynomial — O(n·capacity)
    — which is exactly why integer (0.1mm) units keep the state space bounded.
    """
    reach = bytearray(capacity + 1)
    reach[0] = 1
    parent = [-1] * (capacity + 1)
    item_of = [-1] * (capacity + 1)
    for i, si in enumerate(sizes):
        if si <= 0 or si > capacity:
            continue
        for s in range(capacity, si - 1, -1):
            if not reach[s] and reach[s - si]:
                reach[s] = 1
                parent[s] = s - si
                item_of[s] = i

    best = capacity
    while best > 0 and not reach[best]:
        best -= 1

    chosen: list[int] = []
    s = best
    while s > 0 and item_of[s] != -1:
        chosen.append(item_of[s])
        s = parent[s]
    return chosen


def _throughput_sheets(
    pieces: list[CutPiece], cfg: BoardConfig, two_stage: bool = False
) -> list[_Sheet]:
    """Nest for stackability: one layout per identical-cabinet spec, repeated per instance.

    Identical cabinet instances (same multiset of cut sizes) share one nested layout;
    that layout is cloned for each instance with its own panel ids. Result: few distinct
    patterns, each repeated -> book-cuttable. Costs more sheets than pooled FFD.
    """
    instances: dict[tuple, list[CutPiece]] = defaultdict(list)
    for p in pieces:
        instances[(p.order_id, p.cabinet_id)].append(p)

    by_spec: dict[tuple, list[list[CutPiece]]] = defaultdict(list)
    for inst_pieces in instances.values():
        spec = tuple(sorted((p.length, p.width) for p in inst_pieces))
        by_spec[spec].append(inst_pieces)

    sheets: list[_Sheet] = []
    for spec in sorted(by_spec):
        instance_list = by_spec[spec]
        template = _pack_into_sheets(instance_list[0], cfg, two_stage=two_stage)
        for inst_pieces in instance_list:
            sheets.extend(_clone_layout(template, inst_pieces))
    return sheets


def _clone_layout(template: list[_Sheet], inst_pieces: list[CutPiece]) -> list[_Sheet]:
    """Copy a nested layout, filling each slot with this instance's matching-size piece."""
    pool: dict[tuple, list[CutPiece]] = defaultdict(list)
    for p in inst_pieces:
        pool[(p.length, p.width)].append(p)

    out: list[_Sheet] = []
    for sh in template:
        new_strips = [
            _Strip(
                rip_width=st.rip_width,
                usable_length=st.usable_length,
                skip_trim=st.skip_trim,
                blocks=[
                    _Block(b.length, [pool[(p.length, p.width)].pop() for p in b.pieces])
                    for b in st.blocks
                ],
            )
            for st in sh.strips
        ]
        out.append(
            _Sheet(
                remaining=sh.remaining,
                usable_width=sh.usable_width,
                usable_length=sh.usable_length,
                from_offcut_id=None,
                strips=new_strips,
            )
        )
    return out


def _split_books(repeat: int, max_stack: int) -> list[int]:
    """Stack height per saw pass: e.g. 5 sheets, max 4 -> [4, 1]."""
    books: list[int] = []
    remaining = repeat
    while remaining > 0:
        h = min(max_stack, remaining)
        books.append(h)
        remaining -= h
    return books


def _to_group(
    group_id: str,
    material: str,
    thickness: float,
    finish: str,
    sheets: list[_Sheet],
    cfg: BoardConfig,
) -> tuple[CuttingPlanGroup, list[str], list[NewOffcut]]:
    """Build the schema group (sheets + patterns) and the inventory deltas.

    Consumed = reused offcut bins that held strips. Produced = the leftover width
    band of a *fresh* sheet at/above the recovery threshold. Sheets with an identical
    layout are grouped into a CuttingPattern (book cutting); pieces within a strip are
    ordered by length so every sheet in a book cuts at the same crosscut positions.
    """
    out_sheets: list[CutSheet] = []
    pieces_total = 0
    placed_area = 0.0
    used_area = 0.0
    fresh_sheets = 0
    consumed: list[str] = []
    new_offcuts: list[NewOffcut] = []

    for si, sh in enumerate(sheets, start=1):
        out_strips: list[CutStrip] = []
        used_width = 0.0
        for ti, st in enumerate(sh.strips, start=1):
            # Blocks in length-desc order; within a block, pieces in width-desc order —
            # keeps every sheet of a book aligned at the same crosscut/rip positions.
            blocks = sorted(st.blocks, key=lambda b: -b.length)
            nb = len(blocks)
            used_length = sum(b.length for b in blocks) + cfg.saw_kerf * (nb - 1)
            offcut_length = r1(st.usable_length - used_length)
            out_strips.append(
                CutStrip(
                    strip_no=ti,
                    rip_width=r1(st.rip_width),
                    usable_length=r1(st.usable_length),
                    used_length=r1(used_length),
                    offcut_length=max(offcut_length, 0.0),
                    offcut_reusable=offcut_length >= cfg.recovery_min_width,
                    skip_trim=st.skip_trim,
                    blocks=[
                        CutBlock(
                            length=r1(b.length),
                            pieces=sorted(b.pieces, key=lambda p: -p.width),
                        )
                        for b in blocks
                    ],
                )
            )
            used_width += st.rip_width if ti == 1 else cfg.saw_kerf + st.rip_width
            for b in blocks:
                pieces_total += len(b.pieces)
                placed_area += sum(p.length * p.width for p in b.pieces)

        offcut_width = r1(sh.usable_width - used_width)
        is_offcut = sh.from_offcut_id is not None
        out_sheets.append(
            CutSheet(
                sheet_no=si,
                sheet_size=(
                    f"{r1(sh.usable_width)}x{r1(sh.usable_length)}"
                    if is_offcut
                    else cfg.sheet_size
                ),
                from_offcut_id=sh.from_offcut_id,
                usable_width=r1(sh.usable_width),
                usable_length=r1(sh.usable_length),
                used_width=r1(used_width),
                offcut_width=max(offcut_width, 0.0),
                offcut_reusable=offcut_width >= cfg.recovery_min_width,
                strips=out_strips,
            )
        )
        used_area += sh.usable_width * sh.usable_length
        if is_offcut:
            consumed.append(sh.from_offcut_id)
        else:
            fresh_sheets += 1
            if offcut_width >= cfg.recovery_min_width:
                new_offcuts.append(
                    NewOffcut(
                        material=material,
                        thickness=thickness,
                        finish=finish,
                        width=r1(offcut_width),
                        length=r1(sh.usable_length),
                    )
                )

    patterns = _build_patterns(out_sheets, cfg)
    utilization = r1(100.0 * placed_area / used_area) if used_area else 0.0
    group = CuttingPlanGroup(
        group_id=group_id,
        material=material,
        thickness=thickness,
        finish=finish,
        sheet_size=cfg.sheet_size,
        sheets_total=len(out_sheets),
        fresh_sheets=fresh_sheets,
        offcut_sheets=len(out_sheets) - fresh_sheets,
        distinct_patterns=len(patterns),
        pieces_total=pieces_total,
        utilization=utilization,
        patterns=patterns,
        sheets=out_sheets,
    )
    return group, consumed, new_offcuts


def _build_patterns(sheets: list[CutSheet], cfg: BoardConfig) -> list[CuttingPattern]:
    """Group sheets with an identical layout into book-cuttable patterns.

    A sheet's layout signature is its usable size plus, per strip, the rip width and
    the multiset of crosscut lengths. Two sheets with the same signature cut as one
    book (stack <= max_stack). Sets each sheet's `pattern_id` in place.
    """
    sig_to_pid: dict[tuple, str] = {}
    grouped: dict[str, list[CutSheet]] = {}
    for sh in sheets:
        sig = (
            sh.usable_width,
            sh.usable_length,
            tuple(
                (
                    st.rip_width,
                    tuple(
                        (b.length, tuple(sorted(p.width for p in b.pieces)))
                        for b in st.blocks
                    ),
                )
                for st in sh.strips
            ),
        )
        pid = sig_to_pid.get(sig)
        if pid is None:
            pid = f"PAT-{len(sig_to_pid) + 1:02d}"
            sig_to_pid[sig] = pid
            grouped[pid] = []
        sh.pattern_id = pid
        grouped[pid].append(sh)

    patterns: list[CuttingPattern] = []
    for pid, shs in grouped.items():
        rep = shs[0]
        layout = [
            PatternStrip(
                rip_width=st.rip_width,
                crosscuts=[b.length for b in st.blocks],
                skip_trim=st.skip_trim,
            )
            for st in rep.strips
        ]
        patterns.append(
            CuttingPattern(
                pattern_id=pid,
                repeat_count=len(shs),
                books=_split_books(len(shs), cfg.max_stack),
                sheet_nos=[s.sheet_no for s in shs],
                layout=layout,
            )
        )
    return patterns


def _pieces_from_panels(panels: list[PanelBOM], order_id: str) -> list[CutPiece]:
    """Expand each panel by quantity into individual pieces, tagged with its order."""
    pieces: list[CutPiece] = []
    for p in panels:
        for _ in range(p.quantity):
            pieces.append(
                CutPiece(
                    panel_id=p.panel_id,
                    name=p.name,
                    cabinet_id=p.cabinet_id,
                    order_id=order_id,
                    material=p.material,
                    thickness=p.thickness,
                    finish=p.finish,
                    length=p.cut_length,
                    width=p.cut_width,
                )
            )
    return pieces


def _plan_from_pieces(
    pieces: list[CutPiece],
    cfg: BoardConfig | None = None,
    available: dict[tuple, list[OffcutBin]] | None = None,
    objective: str = "waste",
    stages: int = 3,
) -> PlanResult:
    """Nest a flat piece list into bins, grouped by material+thickness+finish.

    Shared nesting core. `objective` picks the packing strategy:
    - "waste": pool all pieces, FFD into the fewest sheets; reuses `available` offcut
      bins first. Minimises material; layouts rarely repeat.
    - "throughput": nest one representative per identical-cabinet spec and clone the
      layout per instance, so few distinct patterns repeat many times (stackable).
      Trades material for stackability; ignores offcut bins (odd sizes break stacking).
    `stages` picks the guillotine depth (orthogonal to objective):
    - 3 (省料): up to 3 saw passes, tighter packing, 2 flips on a manual saw.
    - 2 (少翻板): rip-by-width then crosscut-by-length only, 1 flip — matches a
      single-pusher 要人翻 saw at the cost of more material.
    Returns a PlanResult (plan + inventory deltas); non-inventory callers read `.plan`.
    """
    cfg = cfg or get_board_config()
    available = available or {}
    two_stage = stages == 2

    by_group: dict[tuple, list[CutPiece]] = defaultdict(list)
    for p in pieces:
        by_group[(p.material, p.thickness, p.finish)].append(p)

    groups: list[CuttingPlanGroup] = []
    consumed: list[str] = []
    new_offcuts: list[NewOffcut] = []
    sheets_total = fresh_total = offcut_total = 0

    for gi, key in enumerate(sorted(by_group), start=1):
        material, thickness, finish = key
        gcfg = cfg.for_material(material)  # this material's stock sheet size
        if objective == "throughput":
            sheets = _throughput_sheets(by_group[key], gcfg, two_stage=two_stage)
        else:
            def make_bins(k=key):
                return [
                    _Sheet(
                        remaining=b.width,
                        usable_width=b.width,
                        usable_length=b.length,
                        from_offcut_id=b.offcut_id,
                    )
                    for b in available.get(k, [])
                ]

            sheets = _pack_for_waste(by_group[key], gcfg, make_bins, stages)
        group, group_consumed, group_new = _to_group(
            f"CUT-GROUP-{gi:03d}", material, thickness, finish, sheets, gcfg
        )
        groups.append(group)
        consumed.extend(group_consumed)
        new_offcuts.extend(group_new)
        sheets_total += group.sheets_total
        fresh_total += group.fresh_sheets
        offcut_total += group.offcut_sheets

    plan = CuttingPlan(
        objective=objective,
        stages=2 if two_stage else 3,
        sheets_total=sheets_total,
        fresh_sheets=fresh_total,
        offcut_sheets=offcut_total,
        groups=groups,
    )
    return PlanResult(plan=plan, consumed_offcut_ids=consumed, new_offcuts=new_offcuts)


def build_cutting_plan(
    panels: list[PanelBOM],
    order_id: str = "",
    cfg: BoardConfig | None = None,
    objective: str = "waste",
    stages: int = 3,
) -> CuttingPlan:
    """Nest a single order's panels (all its cabinets merged), no inventory reuse."""
    return _plan_from_pieces(
        _pieces_from_panels(panels, order_id), cfg, objective=objective, stages=stages
    ).plan


def _pieces_from_sources(sources: list[tuple[str, list[PanelBOM]]]) -> list[CutPiece]:
    pieces: list[CutPiece] = []
    for order_id, panels in sources:
        pieces.extend(_pieces_from_panels(panels, order_id))
    return pieces


def build_cutting_plan_multi(
    sources: list[tuple[str, list[PanelBOM]]],
    cfg: BoardConfig | None = None,
    objective: str = "waste",
    stages: int = 3,
) -> CuttingPlan:
    """Merge several orders into one cross-order plan (no inventory reuse).

    `sources` is a list of (order_id, panels). Same-width pieces from different orders
    pack into shared strips; each piece keeps its order_id for sort-back after cutting.
    """
    return _plan_from_pieces(
        _pieces_from_sources(sources), cfg, objective=objective, stages=stages
    ).plan


def build_cutting_plan_with_stock(
    sources: list[tuple[str, list[PanelBOM]]],
    available: list[OffcutBin],
    cfg: BoardConfig | None = None,
    objective: str = "waste",
    stages: int = 3,
) -> PlanResult:
    """Cross-order plan that reuses available offcut stock before cutting fresh sheets.

    Returns the plan plus which offcuts were consumed and which new ones to deposit.
    Throughput mode ignores offcut stock (odd sizes break book stacking).
    """
    by_key: dict[tuple, list[OffcutBin]] = defaultdict(list)
    for b in available:
        by_key[(b.material, b.thickness, b.finish)].append(b)
    return _plan_from_pieces(
        _pieces_from_sources(sources), cfg, by_key, objective=objective, stages=stages
    )


def render_text(plan: CuttingPlan) -> str:
    """Human-readable cut sheet in the standard pattern×repeat×book form.

    Per pattern: the shared layout (set up once), how many sheets to cut, and the
    book stacking; then per physical sheet the panel labels (cut刀-by-刀, label each
    piece by panel_id on the edge before the next, since stock is平叠). When several
    orders are merged, each piece is tagged by order for sort-back.
    """
    order_ids = {
        p.order_id
        for g in plan.groups
        for sh in g.sheets
        for st in sh.strips
        for b in st.blocks
        for p in b.pieces
        if p.order_id
    }
    show_order = len(order_ids) > 1

    lines: list[str] = []
    for g in plan.groups:
        by_no = {sh.sheet_no: sh for sh in g.sheets}
        lines.append(f"━━━━━━ {g.material} · {g.thickness}mm · {g.finish} ━━━━━━")
        reuse = f" · 回收料 {g.offcut_sheets} 块" if g.offcut_sheets else ""
        lines.append(
            f"新整板 {g.fresh_sheets} 张 · 图案 {g.distinct_patterns} 个{reuse} · "
            f"利用率 {g.utilization}% · 板件 {g.pieces_total} 件"
        )

        for pat in g.patterns:
            rep = by_no[pat.sheet_nos[0]]
            origin = f"回收料 {rep.from_offcut_id}" if rep.from_offcut_id else "整板"
            book = "+".join(str(b) for b in pat.books)
            lines.append(
                f"\n【图案 {pat.pattern_id}】{origin} {rep.sheet_size}mm · "
                f"切 {pat.repeat_count} 张 · 堆叠 {book}"
            )
            # shared layout — the saw operator sets this up once per book
            lines.append("  布局（每摞共用）：")
            for i, ps in enumerate(pat.layout, start=1):
                note = "（整长·免扫边）" if ps.skip_trim else ""
                cross = " | ".join(str(c) for c in ps.crosscuts)
                lines.append(
                    f"    纵切条 {i}：宽 {ps.rip_width}mm → 横切块 {cross}{note}"
                )
            if rep.offcut_width > 0:
                mark = "留用→库存" if rep.offcut_reusable else "废料"
                lines.append(
                    f"    ▢ 边料带 宽 {rep.offcut_width}mm × 长 {rep.usable_length}mm（{mark}）"
                )
            # per physical sheet — the labels to stick on after cutting the book
            lines.append("  贴标（逐张，按上面布局对应）：")
            for no in pat.sheet_nos:
                sh = by_no[no]
                tag = f"板#{no}"
                parts = []
                for st in sh.strips:
                    ids = " ".join(
                        (f"{p.panel_id}[{p.order_id}]" if show_order and p.order_id
                         else p.panel_id)
                        for b in st.blocks
                        for p in b.pieces
                    )
                    parts.append(f"条{st.strip_no}:{ids}")
                lines.append(f"    {tag} → " + " · ".join(parts))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
