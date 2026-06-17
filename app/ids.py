"""Stable ID and fingerprint generation.

`work_order_id` is derived deterministically from the idempotency key
(order_id + cabinet_list_version), so the same input always maps to the same
work order — idempotency falls out for free (see store.py). Cabinet instance
and panel IDs are positional within a package.
"""

import hashlib

from app.schemas import ApprovedCabinetOrderPackage


def idempotency_key(order_id: str, cabinet_list_version: str) -> str:
    return f"module2:{order_id}:{cabinet_list_version}"


def _short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def work_order_id(order_id: str, cabinet_list_version: str) -> str:
    key = idempotency_key(order_id, cabinet_list_version)
    return f"WO-{_short_hash(key)}"


def input_fingerprint(order: ApprovedCabinetOrderPackage) -> str:
    """`{cabinet_list_version}:{hash}` — hash covers the cabinet list so the same
    version with different cabinets is still distinguishable."""
    payload = order.model_dump_json(include={"cabinets"})
    return f"{order.source.cabinet_list_version}:{_short_hash(payload)}"


def cabinet_instance_id(source_cabinet_id: str, n: int) -> str:
    """nth physical copy of a cabinet line (1-based)."""
    return f"{source_cabinet_id}-{n}"


def panel_id(seq: int) -> str:
    """Package-global sequential panel id, e.g. P0001."""
    return f"P{seq:04d}"
