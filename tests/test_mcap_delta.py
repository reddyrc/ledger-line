"""Unit tests for market-cap delta (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_app.metrics.mcap_delta import (  # noqa: E402
    compute_mcap_delta_batch,
    delta_from_mcap_frame,
)


def _frame(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """rows: (date, price, shares) → market_cap = price * shares."""
    data = []
    for date, price, shares in rows:
        data.append(
            {
                "date": pd.Timestamp(date),
                "price": price,
                "shares": shares,
                "market_cap": price * shares,
            }
        )
    return pd.DataFrame(data)


def test_delta_signed_loss_and_gain():
    # Loss: 100 → 80 (−20)
    loss = delta_from_mcap_frame(
        _frame(
            [
                ("2024-01-02", 10.0, 10.0),
                ("2024-06-03", 8.0, 10.0),
            ]
        ),
        start="2024-01-01",
        end="2024-06-30",
    )
    assert loss["error"] is None
    assert loss["start_mcap"] == 100.0
    assert loss["end_mcap"] == 80.0
    assert loss["delta_mcap"] == -20.0
    assert abs(loss["delta_mcap_pct"] - (-0.2)) < 1e-9

    # Gain: 50 → 75 (+25)
    gain = delta_from_mcap_frame(
        _frame(
            [
                ("2024-01-02", 5.0, 10.0),
                ("2024-06-03", 7.5, 10.0),
            ]
        ),
        start="2024-01-01",
        end="2024-06-30",
    )
    assert gain["delta_mcap"] == 25.0


def test_cumulative_totals_sum_signed_deltas(monkeypatch):
    """Batch totals = sum of per-ticker signed Δ (gain + loss)."""

    def fake_symbol(symbol, *, start=None, end=None, refresh=False):
        if symbol == "LOSER":
            return {
                "symbol": "LOSER",
                "start_date": "2024-01-02",
                "end_date": "2024-06-03",
                "start_mcap": 100.0,
                "end_mcap": 80.0,
                "delta_mcap": -20.0,
                "delta_mcap_pct": -0.2,
                "start_price": 10.0,
                "end_price": 8.0,
                "delta_price_pct": -0.2,
                "shares_start": 10.0,
                "shares_end": 10.0,
                "error": None,
            }
        if symbol == "WINNER":
            return {
                "symbol": "WINNER",
                "start_date": "2024-01-02",
                "end_date": "2024-06-03",
                "start_mcap": 50.0,
                "end_mcap": 75.0,
                "delta_mcap": 25.0,
                "delta_mcap_pct": 0.5,
                "start_price": 5.0,
                "end_price": 7.5,
                "delta_price_pct": 0.5,
                "shares_start": 10.0,
                "shares_end": 10.0,
                "error": None,
            }
        return {"symbol": symbol, "error": "missing", "delta_mcap": None}

    monkeypatch.setattr(
        "finance_app.metrics.mcap_delta.compute_symbol_mcap_delta",
        fake_symbol,
    )
    out = compute_mcap_delta_batch(
        ["LOSER", "WINNER", "BROKEN"],
        start="2024-01-01",
        end="2024-06-30",
    )
    assert out["totals"]["included"] == 2
    assert out["totals"]["failed"] == 1
    assert out["totals"]["delta_mcap"] == 5.0  # -20 + 25
    assert out["totals"]["start_mcap"] == 150.0
    assert out["totals"]["end_mcap"] == 155.0


def test_missing_window_returns_error():
    result = delta_from_mcap_frame(
        _frame([("2023-01-02", 10.0, 1.0)]),
        start="2024-01-01",
        end="2024-06-30",
    )
    assert result["error"]
    assert result["delta_mcap"] is None
