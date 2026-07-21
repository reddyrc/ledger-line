"""Unit tests for metric computations and SQLite cache (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_app.metrics.price_metrics import (  # noqa: E402
    beta,
    compute_price_metrics,
    cumulative_return,
    max_drawdown,
    realized_volatility,
    sharpe_ratio,
)
from finance_app.metrics.technicals import rsi, sma  # noqa: E402


def _ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n)
    rets = rng.normal(0.0005, 0.01, size=n)
    prices = 100 * np.cumprod(1 + rets)
    return pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "adj_close": prices,
            "volume": rng.integers(1_000_000, 5_000_000, size=n),
        }
    )


def test_cumulative_and_drawdown():
    df = _ohlcv()
    prices = df.set_index("date")["adj_close"]
    cr = cumulative_return(prices)
    assert cr == prices.iloc[-1] / prices.iloc[0] - 1
    mdd = max_drawdown(prices)
    assert mdd <= 0


def test_vol_and_sharpe():
    df = _ohlcv()
    rets = df.set_index("date")["adj_close"].pct_change().dropna()
    vol = realized_volatility(rets)
    assert vol > 0
    s = sharpe_ratio(rets, risk_free_annual=0.02)
    assert isinstance(s, float)


def test_beta_identity():
    df = _ohlcv()
    rets = df.set_index("date")["adj_close"].pct_change().dropna()
    assert abs(beta(rets, rets) - 1.0) < 1e-9


def test_compute_price_metrics_shape():
    df = _ohlcv()
    bench = _ohlcv(seed=7)
    out = compute_price_metrics(df, benchmark_ohlcv=bench, risk_free_annual=0.04)
    for key in (
        "cumulative_return",
        "realized_volatility_ann",
        "sharpe",
        "sortino",
        "max_drawdown",
        "calmar",
        "beta",
        "correlation_to_benchmark",
    ):
        assert key in out


def test_sma_rsi():
    s = _ohlcv()["adj_close"]
    assert sma(s, 20).iloc[-1] > 0
    r = rsi(s, 14).iloc[-1]
    assert 0 <= r <= 100


def test_db_roundtrip(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()

    db.init_db()
    df = _ohlcv(30)
    n = db.upsert_ohlcv(df, "AAA", source="unit")
    assert n == 30
    loaded = db.load_ohlcv("AAA")
    assert len(loaded) == 30
    assert loaded.iloc[0]["close"] > 0

    macro = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-01", "2024-02-01"]), "value": [5.1, 5.2]}
    )
    assert db.upsert_macro("DGS3MO", macro) == 2
    assert len(db.load_macro("DGS3MO")) == 2

    cfg.get_settings.cache_clear()
