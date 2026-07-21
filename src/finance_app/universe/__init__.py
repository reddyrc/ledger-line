"""Universe loaders (S&P 500, etc.)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


UNIVERSE_DIR = Path(__file__).resolve().parent


@lru_cache
def load_sp500() -> list[dict[str, Any]]:
    path = UNIVERSE_DIR / "sp500.json"
    data = json.loads(path.read_text())
    return list(data.get("tickers", []))


def list_universe(name: str = "sp500") -> list[dict[str, Any]]:
    if name == "sp500":
        return load_sp500()
    raise ValueError(f"Unknown universe: {name}")
