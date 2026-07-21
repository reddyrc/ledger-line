"""Tests for earnings calendar enrichment helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from finance_app.metrics.earnings_calendar import (
    avg_abs_move_1d,
    earnings_session,
    enrich_event,
    last_surprise_pct,
)
from finance_app.ingest.prices_yfinance import _period_dict


def test_earnings_session_bmo_amc():
    assert earnings_session("2024-04-30T08:00:00") == "BMO"
    assert earnings_session("2024-04-30T16:00:00") == "AMC"
    assert earnings_session("2024-04-30T00:00:00") is None
    assert earnings_session("not-a-date") is None


def test_period_dict_extracts_0q():
    df = pd.DataFrame(
        {
            "avg": [1.5, 2.0],
            "growth": [0.12, 0.08],
            "numberOfAnalysts": [20, 18],
        },
        index=["0q", "+1q"],
    )
    row = _period_dict(df, "0q")
    assert row["avg"] == pytest.approx(1.5)
    assert row["growth"] == pytest.approx(0.12)


def test_last_surprise_and_avg_move(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings

    db_path = tmp_path / "earn_cal.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    dates = pd.bdate_range("2023-01-03", periods=200)
    # Step up after each earnings report day
    prices = []
    for d in dates:
        p = 100.0
        if d >= pd.Timestamp("2023-02-01"):
            p = 110.0
        if d >= pd.Timestamp("2023-05-01"):
            p = 121.0
        prices.append(p)
    ohlcv = pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "adj_close": prices,
            "volume": 1_000_000,
        }
    )
    db.upsert_ohlcv(ohlcv, "TEST", source="unit")

    db.upsert_earnings_events(
        "TEST",
        [
            ("2023-02-01T08:00:00", 1.0, 0.9, 11.1),
            ("2023-05-01T16:00:00", 1.2, 1.1, 9.1),
            ("2023-08-01T16:00:00", None, 1.3, None),
        ],
    )

    prior = last_surprise_pct("TEST", "2023-05-01T16:00:00")
    assert prior == pytest.approx(11.1)

    prior2 = last_surprise_pct("TEST", "2023-08-01T16:00:00")
    assert prior2 == pytest.approx(9.1)

    avg, n = avg_abs_move_1d("TEST", before="2023-08-01T16:00:00")
    assert n >= 1
    assert avg is not None
    assert avg > 0

    enriched = enrich_event(
        {
            "symbol": "TEST",
            "report_datetime": "2023-08-01T16:00:00",
            "reported_eps": None,
            "eps_estimate": 1.3,
            "surprise_pct": None,
            "days_to_earnings": 10,
        }
    )
    assert enriched["session"] == "AMC"
    assert enriched["last_surprise_pct"] == pytest.approx(9.1)
    assert enriched["spot"] == pytest.approx(121.0)
    assert enriched["avg_abs_move_1d"] is not None
    assert enriched["avg_move_n"] >= 1
    # Options / analysis keys present even if null
    for key in (
        "revenue_estimate",
        "revenue_yoy",
        "eps_revision_net_30d",
        "atm_iv",
        "iv_rank_1y",
        "expected_move",
        "avg_iv_crush",
    ):
        assert key in enriched


def test_earnings_calendar_payload_shape(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.services import earnings_calendar_payload

    db_path = tmp_path / "earn_cal2.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    # Stub analysis / options network paths
    import finance_app.metrics.earnings_calendar as ec

    monkeypatch.setattr(ec, "refresh_analysis_batch", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ec,
        "analysis_fields",
        lambda _sym: {
            "revenue_estimate": 1e9,
            "revenue_yoy": 0.1,
            "eps_estimate_avg": 1.5,
            "eps_revisions_up_30d": 3,
            "eps_revisions_down_30d": 1,
            "eps_revision_net_30d": 2,
            "eps_trend_delta_30d": 0.05,
        },
    )
    monkeypatch.setattr(
        ec,
        "options_context_cached",
        lambda _sym: {
            "atm_iv": 0.3,
            "iv_rank_1y": 0.55,
            "expected_move": 5.0,
            "expected_move_pct": 0.04,
            "avg_iv_crush": -0.08,
        },
    )

    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT16:00:00")
    db.upsert_earnings_events("AAA", [(soon, None, 2.0, None)])

    # Minimal OHLCV so spot works
    day = pd.Timestamp(soon[:10])
    db.upsert_ohlcv(
        pd.DataFrame(
            {
                "date": [day],
                "open": [50.0],
                "high": [50.0],
                "low": [50.0],
                "close": [50.0],
                "adj_close": [50.0],
                "volume": [1],
            }
        ),
        "AAA",
        source="unit",
    )

    result = earnings_calendar_payload(symbols=["AAA"], refresh=False)
    assert result["events"]
    ev = result["events"][0]
    assert ev["symbol"] == "AAA"
    assert ev["session"] == "AMC"
    assert ev["revenue_estimate"] == pytest.approx(1e9)
    assert ev["atm_iv"] == pytest.approx(0.3)
    assert "guidance" not in ev
    assert "guidance" in result["disclaimer"].lower()
    assert "segment" in result["disclaimer"].lower()
