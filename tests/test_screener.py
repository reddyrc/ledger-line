"""Tests for screener snapshot compute + query (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_load_sp500_universe():
    from finance_app.universe import load_sp500

    tickers = load_sp500()
    assert len(tickers) > 400
    assert any(t["ticker"] == "AAPL" for t in tickers)


def test_screen_metrics_and_query(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics.screener import compute_screen_metrics

    db_path = tmp_path / "screen.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    dates = pd.bdate_range("2023-01-03", periods=300)
    prices = [100 * (1.001**i) for i in range(300)]
    ohlcv = pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "adj_close": prices,
            "volume": 1_000_000,
        }
    )
    db.upsert_ohlcv(ohlcv, "AAA", source="unit")
    db.upsert_fundamentals(
        [
            ("1", "AAA", "EPS", "2023-12-31", 5.0, "USD/shares", "10-K", 2023, "FY"),
            ("1", "AAA", "Equity", "2023-12-31", 50e9, "USD", "10-K", 2023, "FY"),
            ("1", "AAA", "Revenue", "2023-12-31", 100e9, "USD", "10-K", 2023, "FY"),
            ("1", "AAA", "NetIncome", "2023-12-31", 10e9, "USD", "10-K", 2023, "FY"),
            ("1", "AAA", "Shares", "2023-12-31", 1e9, "shares", "10-K", 2023, "FY"),
        ]
    )

    row = compute_screen_metrics("AAA")
    assert row["price"] is not None
    assert row["pe"] is not None
    assert row["momentum_12m"] is not None
    row["name"] = "Test Co"
    row["sector"] = "Information Technology"
    db.upsert_screen_snapshot(row)

    rows, total = db.query_screen_snapshots(
        filters={"pe": (None, 1000)},
        sort="ticker",
        order="asc",
    )
    assert total == 1
    assert rows[0]["ticker"] == "AAA"
