"""Real cabinet-code family resolution (kabi-console catalog -> carcass / blocker)."""

from app.engine import engineer
from app.rules import get_library
from app.schemas import CabinetInput
from tests.conftest import make_order

CV = "module2.v1"
LIB = get_library()


def _engineer_one(code: str, ctype: str, w=24, d=24, h=34.5):
    cab = CabinetInput(
        cabinet_id="C1", cabinet_code=code, type=ctype,
        width=w, depth=d, height=h, quantity=1,
        material="plywood-3/4", finish="white-shaker",
    )
    return engineer(make_order(cabinet=cab), "WO-T", "fp", CV)


# --- resolve_carcass unit checks (longest prefix wins) ---


def test_real_codes_map_to_carcass():
    assert LIB.resolve_carcass("FDB09L") == ("base", None)
    assert LIB.resolve_carcass("DRB12L") == ("base", None)
    assert LIB.resolve_carcass("W3012L") == ("wall", None)
    assert LIB.resolve_carcass("WBF2430") == ("wall", None)   # WBF beats W
    assert LIB.resolve_carcass("TP1272L") == ("tall", None)
    assert LIB.resolve_carcass("SPB12") == ("base", None)


def test_blocked_families_carry_reason():
    t, reason = LIB.resolve_carcass("BCB36R")
    assert t is None and "corner" in reason
    t, reason = LIB.resolve_carcass("WOS0912")  # WOS beats W
    assert t is None and reason is not None
    t, reason = LIB.resolve_carcass("SO2484")
    assert t is None and "oven" in reason


def test_fallback_to_type_for_simple_codes():
    # module-2's own synthetic codes (no family prefix) fall back to the type field
    assert LIB.resolve_carcass("B302435", "base") == ("base", None)
    assert LIB.resolve_carcass("W301236", "wall") == ("wall", None)


def test_unknown_code_and_type_is_unresolved():
    assert LIB.resolve_carcass("ZZZ999", "mystery") == (None, None)


# --- end-to-end through the engine ---


def test_drawer_base_decomposes_as_base():
    pkg = _engineer_one("DRB12L", "base", w=12)
    assert pkg.status == "engineering_ready"
    names = {p.name for p in pkg.panels}
    assert names == {"side", "bottom", "back", "stretcher", "adjustable_shelf"}


def test_pantry_decomposes_as_tall():
    pkg = _engineer_one("TP1272L", "tall", w=12, d=24, h=72)
    assert pkg.status == "engineering_ready"
    assert "top" in {p.name for p in pkg.panels}
    assert "fixed_shelf" in {p.name for p in pkg.panels}


def test_corner_cabinet_blocks_with_reason():
    pkg = _engineer_one("BCB36R", "base", w=36)
    assert pkg.status == "engineering_blocked"
    b = pkg.blockers[0]
    assert b.code == "UNSUPPORTED_CABINET_CODE"
    assert b.owner == "module2"
    assert "corner" in b.message


def test_sink_base_blocks_pending_confirmation():
    pkg = _engineer_one("FDRSB30L", "base", w=30)
    assert pkg.status == "engineering_blocked"
    assert "not yet confirmed" in pkg.blockers[0].message
