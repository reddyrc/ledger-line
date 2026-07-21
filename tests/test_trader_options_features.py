"""Tests for trader options features: BS, IVR, liquidity, UOA, scenarios."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_black_scholes_call_put():
    from finance_app.metrics.option_pricing import black_scholes

    call = black_scholes(100, 100, 0.25, 0.2, right="call", rate=0.04)
    put = black_scholes(100, 100, 0.25, 0.2, right="put", rate=0.04)
    assert call["price"] is not None and call["price"] > 0
    assert put["price"] is not None and put["price"] > 0
    assert 0.4 < call["delta"] < 0.7
    assert -0.7 < put["delta"] < -0.3
    assert call["vega"] is not None and call["vega"] > 0


def test_iv_rank_percentile(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics.options import compute_iv_rank_percentile

    db_path = tmp_path / "iv.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    today = date.today()
    for i in range(25):
        d = (today - timedelta(days=25 - i)).isoformat()
        db.upsert_options_iv_snapshot(
            symbol="TEST",
            as_of_date=d,
            expiration=(today + timedelta(days=30)).isoformat(),
            dte=30,
            atm_iv=0.2 + i * 0.01,
            spot=100.0,
        )

    stats = compute_iv_rank_percentile("TEST", 0.4)
    assert stats["building_history"] is False
    assert stats["iv_rank_1y"] is not None
    assert 0.7 < stats["iv_rank_1y"] <= 1.0
    assert stats["iv_percentile_1y"] is not None


def test_liquidity_filter():
    from finance_app.metrics.option_strategies import passes_liquidity

    idea = {
        "legs": [
            {
                "open_interest": 500,
                "volume": 50,
                "bid": 1.0,
                "ask": 1.05,
                "mid": 1.025,
            },
            {
                "open_interest": 200,
                "volume": 20,
                "bid": 0.5,
                "ask": 0.8,
                "mid": 0.65,
            },
        ],
        "metrics": {},
    }
    # second leg spread = 0.3/0.65 ≈ 46%
    assert passes_liquidity(idea, max_spread_pct=0.25) is False
    assert idea["metrics"]["liquidity"]["ok"] is False

    tight = {
        "legs": [
            {
                "open_interest": 500,
                "volume": 50,
                "bid": 1.0,
                "ask": 1.05,
                "mid": 1.025,
            }
        ],
        "metrics": {},
    }
    assert passes_liquidity(tight, min_oi=100, min_volume=10, max_spread_pct=0.25)


def test_uoa_ranking():
    from finance_app.metrics.options import compute_uoa

    calls = [
        {
            "contract_symbol": "C1",
            "strike": 100,
            "volume": 10000,
            "open_interest": 500,
            "mid": 2.0,
            "implied_volatility": 0.3,
        },
        {
            "contract_symbol": "C2",
            "strike": 105,
            "volume": 10,
            "open_interest": 1000,
            "mid": 1.0,
            "implied_volatility": 0.25,
        },
    ]
    rows = compute_uoa(calls, [], expiration="2026-08-01", limit=5)
    assert rows[0]["contract_symbol"] == "C1"
    assert rows[0]["score"] > rows[1]["score"]


def test_scenario_grid_long_call_benefits_from_up_move():
    from finance_app.metrics.option_strategies import scenario_grid

    idea = {
        "expiration": (date.today() + timedelta(days=45)).isoformat(),
        "legs": [
            {
                "action": "buy",
                "right": "call",
                "strike": 100,
                "mid": 3.0,
                "implied_volatility": 0.3,
            }
        ],
        "metrics": {"spot": 100.0},
    }
    grid = scenario_grid(idea)
    up = next(g for g in grid["grid"] if g["spot_pct"] == 0.05 and g["iv_pct"] == 0.0)
    down = next(g for g in grid["grid"] if g["spot_pct"] == -0.05 and g["iv_pct"] == 0.0)
    assert up["pnl"] is not None and down["pnl"] is not None
    assert up["pnl"] > down["pnl"]


def test_iv_history_includes_hv_and_pcr(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics.options import iv_history_payload

    db_path = tmp_path / "ivhist.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    today = date.today()
    prices = []
    px = 100.0
    for i in range(40):
        d = today - timedelta(days=40 - i)
        px *= 1.0 + ((i % 5) - 2) * 0.01
        prices.append(
            {
                "date": d.isoformat(),
                "open": px,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "adj_close": px,
                "volume": 1_000_000,
            }
        )
    db.upsert_ohlcv(pd.DataFrame(prices), "TEST", source="test")

    exp = (today + timedelta(days=30)).isoformat()
    for i in range(25):
        d = (today - timedelta(days=25 - i)).isoformat()
        db.upsert_options_iv_snapshot(
            symbol="TEST",
            as_of_date=d,
            expiration=exp,
            dte=30,
            atm_iv=0.25 + i * 0.002,
            spot=100.0 + i,
            call_volume=1000,
            put_volume=1200,
            call_oi=5000,
            put_oi=6000,
        )

    payload = iv_history_payload("TEST")
    assert payload["sample_count"] >= 20
    assert payload["latest"]["atm_iv"] is not None
    assert payload["latest"]["hv_20"] is not None
    assert payload["latest"]["iv_hv_premium"] is not None
    assert payload["latest"]["pcr_oi"] is not None
    assert any(p.get("atm_iv") is not None for p in payload["series"])
    assert any(p.get("hv_20") is not None for p in payload["series"])
    assert any(p.get("pcr_oi") is not None for p in payload["series"])


def test_earnings_crush_actual_move(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics.options import earnings_crush_history

    db_path = tmp_path / "crush.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    report = date.today() - timedelta(days=10)
    prices = []
    for i, px in enumerate([100.0, 100.0, 100.0, 110.0, 110.0]):
        d = report - timedelta(days=2) + timedelta(days=i)
        prices.append(
            {
                "date": d.isoformat(),
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "adj_close": px,
                "volume": 1e6,
            }
        )
    db.upsert_ohlcv(pd.DataFrame(prices), "TEST", source="test")
    db.upsert_earnings_events(
        "TEST",
        [(report.isoformat() + "T16:00:00", 1.0, 0.9, 0.11)],
    )
    db.upsert_options_iv_snapshot(
        symbol="TEST",
        as_of_date=(report - timedelta(days=1)).isoformat(),
        expiration=(report + timedelta(days=20)).isoformat(),
        dte=20,
        atm_iv=0.5,
        spot=100.0,
    )
    db.upsert_options_iv_snapshot(
        symbol="TEST",
        as_of_date=(report + timedelta(days=1)).isoformat(),
        expiration=(report + timedelta(days=20)).isoformat(),
        dte=18,
        atm_iv=0.3,
        spot=110.0,
    )

    rows = earnings_crush_history("TEST")
    assert rows
    row = rows[0]
    assert row["actual_move_pct"] is not None
    assert row["actual_move_pct"] > 0.05
    assert row["iv_before"] == 0.5
    assert row["iv_after"] == 0.3
    assert row["iv_crush"] is not None and row["iv_crush"] < 0


def test_rolling_series_includes_sharpe():
    from finance_app.metrics.price_metrics import rolling_metrics_series

    today = date.today()
    rows = []
    px = 100.0
    for i in range(90):
        d = today - timedelta(days=90 - i)
        px *= 1.001
        rows.append(
            {
                "date": pd.Timestamp(d),
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "adj_close": px,
                "volume": 1e6,
            }
        )
    series = rolling_metrics_series(pd.DataFrame(rows), window=63)
    assert series
    assert "rolling_sharpe" in series[-1]
    assert series[-1]["rolling_vol_ann"] is not None
