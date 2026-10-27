"""Load the demo order data set."""

from __future__ import annotations

import json
from pathlib import Path

from orderflow.models import Order

DATA_FILE = Path(__file__).resolve().parent / "data" / "orders.json"


def load_orders(path: Path | str | None = None) -> tuple[Order, ...]:
    """Read orders from ``path`` (defaults to the bundled data file)."""

    source = Path(path) if path is not None else DATA_FILE
    with source.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return tuple(Order.from_mapping(item) for item in raw)
