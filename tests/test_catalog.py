"""Broad catalog coverage: real cabinet codes across every family + edge cases.

Each fixture says whether the cabinet should decompose (`ready`) or block, and why.
This stress-tests family resolution, decomposition, the feasibility guard, per-material
stock, and cutting conservation across ~22 representative codes — not just the golden
samples. See tests/fixtures/catalog_sample.json.
"""

import json
from pathlib import Path

import pytest

from app.engine import engineer
from app.schemas import CabinetInput
from tests.conftest import make_order

CV = "module2.v1"
CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "catalog_sample.json").read_text("utf-8")
)


def _engineer(case: dict):
    cab = CabinetInput(
        cabinet_id="C1", cabinet_code=case["code"], type=case["type"],
        width=case["w"], depth=case["d"], height=case["h"], quantity=2,
        material=case["material"], finish="white",
    )
    return engineer(make_order(cabinet=cab), "WO-T", "fp", CV)


def _placed(pkg):
    return sum(
        len(b.pieces)
        for g in pkg.cutting_plan.groups for sh in g.sheets
        for st in sh.strips for b in st.blocks
    )


@pytest.mark.parametrize("case", CASES, ids=[c["code"] for c in CASES])
def test_catalog_disposition(case):
    pkg = _engineer(case)

    if case["expect"] == "ready":
        assert pkg.status == "engineering_ready"
        assert pkg.panels, "ready cabinet produced no panels"
        # every emitted panel has sane, positive dimensions...
        assert all(p.cut_length > 0 and p.cut_width > 0 for p in pkg.panels)
        # ...and cutting conserves them (each placed exactly once)
        assert _placed(pkg) == sum(p.quantity for p in pkg.panels)
        assert not pkg.blockers
    else:
        assert pkg.status == "engineering_blocked"
        assert pkg.panels == []
        b = pkg.blockers[0]
        assert b.code == case["blocker"]
        assert b.owner == "module2"
        assert case["reason"].lower() in b.message.lower()


def test_catalog_counts_make_sense():
    """Sanity on the whole set: the ready/blocked split matches the fixtures."""
    ready = [c for c in CASES if c["expect"] == "ready"]
    blocked = [c for c in CASES if c["expect"] == "blocked"]
    assert len(ready) >= 8 and len(blocked) >= 8  # broad coverage both ways
    for c in ready:
        assert _engineer(c).status == "engineering_ready"
