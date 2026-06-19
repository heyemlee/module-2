"""Export Module 2's API contracts as JSON Schema files (the shared interface).

These are the authoritative shapes the pipeline aligns on:
  - input  : ApprovedCabinetOrderPackage   (Module 1 produces this)
  - output : ProductionEngineeringPackage   (Module 3 reads this)

Generated straight from the Pydantic models, so the files can never drift from what
the gate actually validates. Commit the `contracts/` dir and let Module 1 / Module 3
generate types or validate against it.

Run:  python scripts/export_contracts.py
"""

import json
import sys
from pathlib import Path

# Make `app` importable no matter how this is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.schemas import (  # noqa: E402
    ApprovedCabinetOrderPackage,
    ProductionEngineeringPackage,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "contracts"

ARTIFACTS = {
    "approved-cabinet-order-package.schema.json": ApprovedCabinetOrderPackage,
    "production-engineering-package.schema.json": ProductionEngineeringPackage,
}


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for filename, model in ARTIFACTS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema.setdefault("title", model.__name__)
        schema["x-contractVersion"] = settings.contract_version
        path = OUT_DIR / filename
        path.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        fields = len(schema.get("properties", {}))
        print(f"wrote {path}  ({fields} top-level fields)")

    (OUT_DIR / "contract_version.txt").write_text(
        settings.contract_version + "\n", encoding="utf-8"
    )
    print(f"contract_version = {settings.contract_version}")


if __name__ == "__main__":
    main()
