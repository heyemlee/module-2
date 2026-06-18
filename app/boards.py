"""Board / cutting-machine config loader (rules-as-data).

Loads `rules_data/board_config.yaml` once and exposes derived usable dimensions.
Mirrors rules.py so machine parameters can later move to a DB or admin UI without
touching the nesting math in cutting.py.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_CONFIG_PATH = Path(__file__).parent / "rules_data" / "board_config.yaml"


class StockSheet(BaseModel):
    """A material-specific stock sheet size; `match` is a substring of the material."""

    match: str
    width: float
    length: float


class BoardConfig(BaseModel):
    version: int
    sheet_width: float       # mm, short axis (default stock)
    sheet_length: float      # mm, long axis
    trim: float              # mm removed per trimmed edge
    saw_kerf: float          # mm consumed per cut
    recovery_min_width: float
    rail_min: float
    max_stack: int
    stock: list[StockSheet] = Field(default_factory=list)

    @property
    def usable_width(self) -> float:
        """Board width after trimming both long edges."""
        return self.sheet_width - 2 * self.trim

    @property
    def usable_length(self) -> float:
        """Board length after trimming both ends."""
        return self.sheet_length - 2 * self.trim

    @property
    def sheet_size(self) -> str:
        return f"{self.sheet_width}x{self.sheet_length}"

    def for_material(self, material: str) -> "BoardConfig":
        """Config with this material's stock sheet, or self if none matches.

        Different materials come on different stock (e.g. Cleaf 2800×2065 vs plywood
        4×8), so each cutting group nests on its own sheet size."""
        m = (material or "").lower()
        for s in self.stock:
            if s.match.lower() in m:
                return self.model_copy(
                    update={"sheet_width": s.width, "sheet_length": s.length}
                )
        return self


@lru_cache
def get_board_config() -> BoardConfig:
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return BoardConfig.model_validate(raw)
