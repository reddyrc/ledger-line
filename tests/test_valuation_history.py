"""Unit tests for historical valuation series (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_app.metrics.valuation_history import (  # noqa: E402
    _summary_stats,
    _ttm_from_flow,
    compute_valuation_history,
)


def test_ttm_sums_last_four_quarters():
    flow = pd.DataFrame(
        {
            "end_date": pd.to_datetime(
                ["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31"]
            ),
            "value": [1.0, 1.1, 1.2, 1.3, 1.4],
            "form": ["10-Q", "10-Q", "10-Q", "10-Q", "10-Q"],
            "fy": [2023, 2023, 2023, 2023, 2024],
            "fp": ["Q1", "Q2", "Q3", "Q4", "Q1"],
        }
    )
    ttm = _ttm_from_flow(flow)
    last = ttm.iloc[-1]["ttm"]
    assert abs(last - (1.1 + 1.2 + 1.3 + 1.4)) < 1e-9


def test_ttm_falls_back_to_annual():
    flow = pd.DataFrame(
        {
            "end_date": pd.to_datetime(["2022-12-31", "2023-12-31"]),
            "value": [4.0, 5.0],
            "form": ["10-K", "10-K"],
            "fy": [2022, 2023],
            "fp": ["FY", "FY"],
        }
    )
    ttm = _ttm_from_flow(flow)
    assert ttm.iloc[-1]["ttm"] == 5.0


def test_summary_stats_avg_median():
    dates = pd.bdate_range("2024-01-01", periods=5)
    merged = pd.DataFrame(
        {
            "date": dates,
            "pe": [10.0, 20.0, 30.0, 40.0, 50.0],
            "pb": [1.0, 2.0, 3.0, 4.0, 5.0],
            "ps": [2.0, 2.0, 2.0, 2.0, 2.0],
            "market_cap": [100.0, 200.0, 300.0, 400.0, 500.0],
        }
    )
    summary = _summary_stats(merged)
    assert summary["pe"]["avg"] == 30.0
    assert summary["pe"]["median"] == 30.0
    assert summary["pe"]["latest"] == 50.0
    assert summary["pe"]["count"] == 5
    assert summary["ps"]["avg"] == 2.0


def test_compute_valuation_history_synthetic(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings

    db_path = tmp_path / "val.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    # Prices: 100 trading days at $100
    dates = pd.bdate_range("2023-01-03", periods=100)
    ohlcv = pd.DataFrame(
        {
            "date": dates,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "adj_close": 100.0,
            "volume": 1_000_000,
        }
    )
    db.upsert_ohlcv(ohlcv, "TEST", source="unit")

    # Fundamentals: annual EPS=5, equity=50e9, revenue=100e9, shares=1e9
    # PE = 100/5 = 20, mkt cap = 100*1e9 = 1e11, PB = 1e11/50e9 = 2, PS = 1e11/100e9 = 1
    rows = [
        ("0000000001", "TEST", "EPS", "2022-12-31", 5.0, "USD/shares", "10-K", 2022, "FY"),
        ("0000000001", "TEST", "Equity", "2022-12-31", 50_000_000_000.0, "USD", "10-K", 2022, "FY"),
        ("0000000001", "TEST", "Revenue", "2022-12-31", 100_000_000_000.0, "USD", "10-K", 2022, "FY"),
        ("0000000001", "TEST", "Shares", "2022-12-31", 1_000_000_000.0, "shares", "10-K", 2022, "FY"),
    ]
    db.upsert_fundamentals(rows)

    # Avoid network refresh
    result = compute_valuation_history("TEST", refresh=False)
    assert not result.get("error"), result.get("error")
    assert len(result["series"]) == 100
    pe_vals = [p["pe"] for p in result["series"] if p["pe"] is not None]
    assert len(pe_vals) > 0
    assert abs(pe_vals[-1] - 20.0) < 1e-6
    assert abs(result["series"][-1]["pb"] - 2.0) < 1e-6
    assert abs(result["series"][-1]["ps"] - 1.0) < 1e-6
    assert abs(result["summary"]["pe"]["avg"] - 20.0) < 1e-6
    assert abs(result["summary"]["pe"]["median"] - 20.0) < 1e-6
    assert len(result["earnings"]) >= 1
    assert result["earnings"][0]["eps"] == 5.0
