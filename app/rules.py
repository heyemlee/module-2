"""Standard cabinet library lookup (rules-as-data).

Loads `rules_data/cabinets.yaml` once and exposes lookups for the engine and
gate. Keeping this separate from the geometry (engine.py) means rule coverage
can later move to a DB or admin UI without touching the decomposition math.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

_RULES_PATH = Path(__file__).parent / "rules_data" / "cabinets.yaml"


class CabinetRule(BaseModel):
    type: str
    has_top: bool
    has_bottom: bool
    stretchers: int
    default_adjustable_shelves: int
    default_fixed_shelves: int
    can_auto_decompose: bool


class CabinetLibrary(BaseModel):
    version: int
    code_prefix_to_type: dict[str, str]
    cabinets: dict[str, CabinetRule]

    def rule_for_type(self, cabinet_type: str) -> CabinetRule | None:
        return self.cabinets.get(cabinet_type)

    def type_for_code(self, cabinet_code: str) -> str | None:
        """Infer cabinet type from the leading letter of the code, e.g. B302435."""
        if not cabinet_code:
            return None
        return self.code_prefix_to_type.get(cabinet_code[0].upper())


@lru_cache
def get_library() -> CabinetLibrary:
    with _RULES_PATH.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return CabinetLibrary.model_validate(raw)
