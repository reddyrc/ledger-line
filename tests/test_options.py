"""Unit tests for options metrics (no network)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _c(strike, oi, mid=None, volume=0, **extra):
    return {
        "contract_symbol": f"C{strike}",
        "side": "call",
        "strike": strike,
        "bid": (mid or 1) - 0.05,
        "ask": (mid or 1) + 0.05,
        "last": mid,
        "mid": mid,
        "volume": volume,
        "open_interest": oi,
        "implied_volatility": 0.3,
        "day_low": 0.5,
        "day_high": 1.5,
        **extra,
    }


def _p(strike, oi, mid=None, volume=0, **extra):
    return {
        "contract_symbol": f"P{strike}",
        "side": "put",
        "strike": strike,
        "bid": (mid or 1) - 0.05,
        "ask": (mid or 1) + 0.05,
        "last": mid,
        "mid": mid,
        "volume": volume,
        "open_interest": oi,
        "implied_volatility": 0.3,
        "day_low": 0.4,
        "day_high": 1.2,
        **extra,
    }


def test_max_pain_simple():
    from finance_app.metrics.options import compute_max_pain

    # Heavy call OI above 100, heavy put OI below 100 → pain minimized near 100
    calls = [_c(90, 10), _c(100, 100), _c(110, 200)]
    puts = [_p(90, 200), _p(100, 100), _p(110, 10)]
    assert compute_max_pain(calls, puts) == 100.0


def test_expected_move_and_pcr():
    from finance_app.metrics.options import (
        compute_expected_move,
        compute_put_call_totals,
    )

    calls = [_c(100, 50, mid=2.0, volume=10)]
    puts = [_p(100, 100, mid=3.0, volume=20)]
    move = compute_expected_move(calls, puts, spot=100.0)
    assert move["expected_move"] == 5.0
    assert move["price_low"] == 95.0
    assert move["price_high"] == 105.0
    totals = compute_put_call_totals(calls, puts)
    assert totals["pcr_oi"] == 2.0
    assert totals["pcr_volume"] == 2.0


def test_traded_range_from_history():
    from finance_app.metrics.options import traded_range_from_history

    dates = pd.bdate_range("2024-01-02", periods=5)
    df = pd.DataFrame(
        {
            "date": dates,
            "open": [1, 1.1, 1.2, 1.0, 1.3],
            "high": [1.2, 1.3, 1.5, 1.1, 1.4],
            "low": [0.8, 0.9, 1.0, 0.7, 1.1],
            "close": [1.1, 1.2, 1.4, 0.9, 1.35],
            "volume": [10, 20, 30, 40, 50],
        }
    )
    rng = traded_range_from_history(df)
    assert rng["traded_low"] == 0.7
    assert rng["traded_high"] == 1.5
    assert rng["traded_last"] == 1.35
    assert len(rng["series"]) == 5


def test_normalize_option_row():
    from finance_app.ingest.options_yfinance import normalize_option_row

    row = normalize_option_row(
        {
            "contractSymbol": "AAPL250117C00150000",
            "strike": 150,
            "bid": 1.0,
            "ask": 1.2,
            "lastPrice": 1.1,
            "volume": 5,
            "openInterest": 100,
            "impliedVolatility": 0.25,
            "dayLow": 0.9,
            "dayHigh": 1.3,
            "inTheMoney": True,
        },
        "call",
    )
    assert row["contract_symbol"] == "AAPL250117C00150000"
    assert row["mid"] == 1.1
    assert row["day_low"] == 0.9
    assert row["day_high"] == 1.3


def test_options_payload_cache(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics import options as opt

    db_path = tmp_path / "opt.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    calls_n = {"n": 0}

    def fake_list(_symbol):
        return ["2025-01-17", "2025-02-21"]

    def fake_chain(symbol, expiration):
        calls_n["n"] += 1
        return {
            "expiration": expiration,
            "calls": [_c(100, 50, mid=2.0)],
            "puts": [_p(100, 80, mid=2.5)],
        }

    first = opt.options_payload(
        "TEST",
        list_exp_fn=fake_list,
        fetch_chain_fn=fake_chain,
    )
    assert first["freshness"] == "live"
    assert first["summary"]["max_pain"] == 100.0
    assert calls_n["n"] == 1

    second = opt.options_payload(
        "TEST",
        list_exp_fn=fake_list,
        fetch_chain_fn=fake_chain,
    )
    assert second["freshness"] == "cached"
    assert calls_n["n"] == 1

    # Expire and fail → stale
    key = "TEST:2025-01-17"
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE options_chain_cache SET updated_at = ? WHERE cache_key = ?",
            (old, key),
        )

    def boom(*_a, **_k):
        calls_n["n"] += 1
        raise RuntimeError("yahoo down")

    stale = opt.options_payload(
        "TEST",
        list_exp_fn=fake_list,
        fetch_chain_fn=boom,
    )
    assert stale["freshness"] == "stale"
    assert stale["summary"]["max_pain"] == 100.0


def test_contract_payload(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics.options import options_contract_payload

    db_path = tmp_path / "opt_c.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    dates = pd.bdate_range("2024-06-03", periods=4)

    def fake_hist(contract_symbol, period="3mo"):
        return pd.DataFrame(
            {
                "date": dates,
                "open": [1, 1, 1, 1],
                "high": [2, 2.5, 2.2, 2.1],
                "low": [0.5, 0.6, 0.4, 0.8],
                "close": [1.5, 1.8, 1.2, 1.9],
                "volume": [1, 2, 3, 4],
            }
        )

    result = options_contract_payload(
        "AAPL",
        "AAPL250117C00150000",
        period="3mo",
        day_low=0.9,
        day_high=1.4,
        fetch_history_fn=fake_hist,
    )
    assert result["traded_low"] == 0.4
    assert result["traded_high"] == 2.5
    assert result["session_day_low"] == 0.9
    assert result["session_day_high"] == 1.4
    assert len(result["series"]) == 4
