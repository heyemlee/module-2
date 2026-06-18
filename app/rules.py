"""Standard cabinet library + decomposition rules loader (rules-as-data).

Loads `rules_data/cabinets.yaml` once and exposes the constants, the shared part-
geometry catalog, and per-type part lists. The geometry FORMULAS live in the YAML and
are evaluated by app/formula.py — engine.py only orchestrates. Adding a cabinet type is
a YAML edit; this module and the engine stay untouched.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_RULES_PATH = Path(__file__).parent / "rules_data" / "cabinets.yaml"


class PartGeometry(BaseModel):
    """Dimension formulas for one part shape (strings evaluated by app/formula.py)."""

    length: str
    width: str
    cut_length: str
    cut_width: str
    edges: str  # front | all | none
    thickness: float | None = None  # per-part override (mm); None -> constants.t (box)


class TypePart(BaseModel):
    """A part used by a cabinet type, with its quantity rule."""

    part: str
    qty: int | str        # fixed int, or an order field name (adjustable_shelves/...)
    default: int = 0      # used when qty names a field the order omitted


class CabinetRule(BaseModel):
    vr: float = 0.0       # vertical cut clearance (wall = 2mm)
    tkr: float = 0.0      # toe-kick + rail: back height reduction (base/tall = 114.3)
    can_auto_decompose: bool = True
    parts: list[TypePart] = Field(default_factory=list)


class CabinetLibrary(BaseModel):
    version: int
    code_prefix_to_type: dict[str, str]
    constants: dict[str, float]
    part_catalog: dict[str, PartGeometry]
    cabinets: dict[str, CabinetRule]
    code_families: dict[str, str] = Field(default_factory=dict)
    blocked_families: dict[str, str] = Field(default_factory=dict)

    def rule_for_type(self, cabinet_type: str) -> CabinetRule | None:
        return self.cabinets.get(cabinet_type)

    def geometry_for(self, part: str) -> PartGeometry | None:
        return self.part_catalog.get(part)

    def type_for_code(self, cabinet_code: str) -> str | None:
        """Infer cabinet type from the leading letter of the code, e.g. B302435."""
        if not cabinet_code:
            return None
        return self.code_prefix_to_type.get(cabinet_code[0].upper())

    def resolve_carcass(
        self, cabinet_code: str, fallback_type: str | None = None
    ) -> tuple[str | None, str | None]:
        """Map a real cabinet code to a carcass type, by longest family prefix.

        Returns ``(carcass_type, blocked_reason)``:
        - a known decomposable family -> ``(type, None)``
        - a blocked family (corner/appliance/open) -> ``(None, reason)``
        - no family match -> fall back to ``fallback_type`` if it's a known carcass
        - otherwise ``(None, None)`` (caller emits the unsupported blocker)
        Longest prefix wins across BOTH maps, so e.g. WBF->wall but WBC->blocked.
        """
        code = (cabinet_code or "").upper()

        carcass, carcass_len = None, -1
        for prefix, ctype in self.code_families.items():
            if code.startswith(prefix.upper()) and len(prefix) > carcass_len:
                carcass, carcass_len = ctype, len(prefix)

        reason, reason_len = None, -1
        for prefix, why in self.blocked_families.items():
            if code.startswith(prefix.upper()) and len(prefix) > reason_len:
                reason, reason_len = why, len(prefix)

        if carcass is not None and carcass_len >= reason_len:
            return carcass, None
        if reason is not None and reason_len > carcass_len:
            return None, reason
        if fallback_type in self.cabinets:
            return fallback_type, None
        return None, None


@lru_cache
def get_library() -> CabinetLibrary:
    with _RULES_PATH.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return CabinetLibrary.model_validate(raw)
