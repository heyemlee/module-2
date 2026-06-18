"""Cutting-plan nesting tests (Phase B).

Asserts guillotine validity invariants rather than exact sheet counts (which depend
on the FFD heuristic): every piece placed once, nothing overflows a strip or sheet,
kerf/trim respected, and batching repeated cabinets surfaces stackable patterns.
"""

from app.boards import get_board_config
from app.cutting import _max_fill, _split_books, build_cutting_plan, render_text
from app.engine import engineer
from app.schemas import CabinetInput
from tests.conftest import make_order

CV = "module2.v1"
CFG = get_board_config()
EPS = 1e-6


def _all_pieces(plan):
    return [
        p
        for g in plan.groups
        for sh in g.sheets
        for st in sh.strips
        for b in st.blocks
        for p in b.pieces
    ]


def _panels(**over):
    return engineer(make_order(**over), "WO-T", "fp", CV).panels


def test_every_panel_piece_is_placed_once():
    pkg = engineer(make_order(), "WO-T", "fp", CV)
    plan = pkg.cutting_plan
    # B302435 base: side(2)+bottom(1)+back(1)+stretcher(2)+adj_shelf(1) = 7 pieces
    expected = sum(p.quantity for p in pkg.panels)
    assert expected == 7
    placed = _all_pieces(plan)
    assert len(placed) == 7
    assert sorted(p.panel_id for p in placed) == sorted(
        p.panel_id for p in pkg.panels for _ in range(p.quantity)
    )


def test_no_strip_or_sheet_overflows():
    """Guillotine validity: used length/width never exceed the usable budget."""
    plan = engineer(
        make_order(
            cabinet=CabinetInput(
                cabinet_id="C1", cabinet_code="B302435", type="base",
                width=30, depth=24, height=34.5, quantity=6,
                material="plywood-3/4", finish="white-shaker",
            )
        ),
        "WO-T", "fp", CV,
    ).cutting_plan

    for g in plan.groups:
        for sh in g.sheets:
            assert sh.used_width <= sh.usable_width + EPS
            for st in sh.strips:
                assert st.used_length <= st.usable_length + EPS
                for b in st.blocks:
                    # 3-stage: a block's pieces share one length; widths fit the rip
                    assert all(p.length == b.length for p in b.pieces)
                    block_w = sum(p.width for p in b.pieces) + EPS * len(b.pieces)
                    assert block_w <= st.rip_width + CFG.saw_kerf * len(b.pieces)
                    assert all(p.width <= st.rip_width + EPS for p in b.pieces)


def test_offcut_recovery_flag_uses_threshold():
    plan = engineer(make_order(), "WO-T", "fp", CV).cutting_plan
    for g in plan.groups:
        for sh in g.sheets:
            assert sh.offcut_reusable == (sh.offcut_width >= CFG.recovery_min_width)
            for st in sh.strips:
                assert st.offcut_reusable == (
                    st.offcut_length >= CFG.recovery_min_width
                )


def test_pattern_grouping_is_well_formed():
    """Sheets group into well-formed patterns (ids, repeat/book accounting).

    Repetition itself is a throughput-mode property (see test_objective); waste mode
    only guarantees the grouping is consistent.
    """
    plan = engineer(
        make_order(
            cabinet=CabinetInput(
                cabinet_id="C1", cabinet_code="W301236", type="wall",
                width=30, depth=12, height=36, quantity=4,
                material="plywood-3/4", finish="white-shaker",
            )
        ),
        "WO-T", "fp", CV,
    ).cutting_plan

    for g in plan.groups:
        assert all(sh.pattern_id for sh in g.sheets)
        assert g.distinct_patterns == len(g.patterns)
        total = 0
        for pat in g.patterns:
            assert sum(pat.books) == pat.repeat_count
            assert max(pat.books) <= CFG.max_stack
            assert len(pat.sheet_nos) == pat.repeat_count
            total += pat.repeat_count
        assert total == g.sheets_total


def test_batching_two_orders_groups_by_material():
    """Two materials -> two cutting groups; pieces stay within their group."""
    panels = _panels(
        cabinet=CabinetInput(
            cabinet_id="C1", cabinet_code="B302435", type="base",
            width=30, depth=24, height=34.5, quantity=1,
            material="mdf-3/4", finish="raw",
        )
    ) + _panels()  # default plywood-3/4 / white-shaker

    plan = build_cutting_plan(panels, order_id="ORD-MIX")
    assert len(plan.groups) == 2
    mats = {g.material for g in plan.groups}
    assert mats == {"mdf-3/4", "plywood-3/4"}
    assert plan.sheets_total == sum(g.sheets_total for g in plan.groups)


def test_empty_panels_yield_empty_plan():
    plan = build_cutting_plan([], order_id="ORD-NONE")
    assert plan.sheets_total == 0
    assert plan.groups == []


def test_max_fill_is_optimal_not_first_fit():
    # capacity 12: first-fit by size would take 7 then stop; optimal takes 6+6=12
    picked = _max_fill([7, 6, 6], 12)
    assert sorted(picked) == [1, 2]
    assert sum([7, 6, 6][i] for i in picked) == 12

    # distinct indices, never exceeds capacity, picks the best reachable sum
    picked = _max_fill([5, 4, 3], 8)
    assert len(set(picked)) == len(picked)
    total = sum([5, 4, 3][i] for i in picked)
    assert total == 8 and total <= 8


def test_max_fill_empty_when_nothing_fits():
    assert _max_fill([10, 12], 9) == []


def test_split_books_stacks_to_max():
    """Book heights split a pattern's repeats into stacked saw passes (<= max_stack)."""
    assert _split_books(1, 4) == [1]
    assert _split_books(4, 4) == [4]
    assert _split_books(5, 4) == [4, 1]
    assert _split_books(9, 4) == [4, 4, 1]
    assert _split_books(6, 2) == [2, 2, 2]


def test_render_text_shows_patterns_and_books():
    pkg = engineer(make_order(), "WO-T", "fp", CV)
    text = render_text(pkg.cutting_plan)
    assert "图案" in text          # pattern-based output
    assert "堆叠" in text          # book stacking
    assert "纵切条" in text         # the shared layout
    assert pkg.panels[0].panel_id in text
    assert "利用率" in text
