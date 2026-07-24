"""Tests for Finnhub ingest mapping and primary normalize (no network)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from finance_app.config import normalize_earnings_primary, normalize_price_primary
from finance_app.ingest.finnhub import (
    candles_json_to_ohlcv,
    company_news_json_to_items,
    earnings_json_to_frame,
    fetch_ohlcv_finnhub,
)


SAMPLE_CANDLES = {
    "s": "ok",
    "t": [1704153600, 1704240000],  # 2024-01-02, 2024-01-03 UTC
    "o": [100.0, 104.0],
    "h": [105.0, 106.0],
    "l": [99.0, 103.0],
    "c": [104.0, 105.5],
    "v": [1_000_000, 900_000],
}

SAMPLE_EARNINGS = [
    {
        "actual": 1.46,
        "estimate": 1.39,
        "period": "2023-10-26",
        "symbol": "AAPL",
        "surprisePercent": 5.0,
    },
    {
        "actual": 2.18,
        "estimate": 2.1,
        "period": "2024-01-25",
        "symbol": "AAPL",
    },
]


def test_normalize_price_primary_accepts_finnhub():
    assert normalize_price_primary("finnhub") == "finnhub"
    assert normalize_price_primary("TIINGO") == "tiingo"
    assert normalize_price_primary("nope") == "tiingo"


def test_normalize_earnings_primary_finnhub():
    assert (
        normalize_earnings_primary(
            "finnhub", fmp_configured=True, finnhub_configured=True
        )
        == "finnhub"
    )
    assert (
        normalize_earnings_primary(
            "finnhub", fmp_configured=True, finnhub_configured=False
        )
        == "fmp"
    )
    assert (
        normalize_earnings_primary(
            "finnhub", fmp_configured=False, finnhub_configured=False
        )
        == "yfinance"
    )
    assert (
        normalize_earnings_primary(
            "fmp", fmp_configured=False, finnhub_configured=True
        )
        == "finnhub"
    )


def test_candles_json_to_ohlcv():
    df = candles_json_to_ohlcv(SAMPLE_CANDLES)
    assert len(df) == 2
    assert df.iloc[0]["close"] == pytest.approx(104.0)
    assert df.iloc[1]["adj_close"] == pytest.approx(105.5)
    assert list(df.columns) == [
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
    ]


def test_candles_json_no_ok():
    assert candles_json_to_ohlcv({"s": "no_data"}).empty


def test_fetch_ohlcv_finnhub_empty_without_key():
    df = fetch_ohlcv_finnhub("AAPL", api_key="")
    assert df.empty


def test_fetch_ohlcv_finnhub_maps_rows():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_CANDLES

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("finance_app.ingest.finnhub.httpx.Client", return_value=mock_client):
        df = fetch_ohlcv_finnhub("aapl", api_key="test-key")

    assert len(df) == 2
    args, kwargs = mock_client.get.call_args
    assert "/stock/candle" in args[0]
    assert kwargs["params"]["symbol"] == "AAPL"
    assert kwargs["params"]["token"] == "test-key"
    assert kwargs["params"]["resolution"] == "D"


def test_earnings_json_to_frame():
    df = earnings_json_to_frame(SAMPLE_EARNINGS)
    assert len(df) == 2
    assert df.iloc[0]["reported_eps"] == pytest.approx(1.46)
    assert df.iloc[1]["eps_estimate"] == pytest.approx(2.1)
    # surprise from actual/estimate when surprisePercent missing
    assert df.iloc[1]["surprise_pct"] == pytest.approx((2.18 - 2.1) / 2.1 * 100)


def test_company_news_json_to_items():
    items = company_news_json_to_items(
        [
            {
                "headline": "Hello",
                "url": "https://example.com/a",
                "source": "Reuters",
                "datetime": 1704153600,
            },
            {"headline": "", "url": "https://example.com/b"},
        ],
        limit=5,
    )
    assert len(items) == 1
    assert items[0]["title"] == "Hello"
    assert items[0]["source"] == "Reuters"


def test_price_fallback_order_finnhub_primary():
    from finance_app.ingest import _fetch_with_fallback

    empty = pd.DataFrame(
        columns=["date", "open", "high", "low", "close", "adj_close", "volume"]
    )
    hit = empty.copy()
    hit.loc[0] = [pd.Timestamp("2024-01-02"), 1, 1, 1, 1, 1, 1]

    calls: list[str] = []

    def fake_fh(*_a, **_k):
        calls.append("finnhub")
        return hit

    def fake_ti(*_a, **_k):
        calls.append("tiingo")
        return empty

    def fake_st(*_a, **_k):
        calls.append("stooq")
        return empty

    def fake_yf(*_a, **_k):
        calls.append("yfinance")
        return empty

    settings = MagicMock()
    settings.price_primary_normalized = "finnhub"
    settings.finnhub_ohlcv_enabled = True

    with (
        patch("finance_app.ingest.get_settings", return_value=settings),
        patch("finance_app.ingest.finnhub_configured", return_value=True),
        patch("finance_app.ingest.tiingo_configured", return_value=True),
        patch("finance_app.ingest.fetch_ohlcv_finnhub", side_effect=fake_fh),
        patch("finance_app.ingest.fetch_tiingo_ohlcv", side_effect=fake_ti),
        patch("finance_app.ingest.fetch_stooq_ohlcv", side_effect=fake_st),
        patch("finance_app.ingest.fetch_yfinance_ohlcv", side_effect=fake_yf),
    ):
        df, source = _fetch_with_fallback("AAPL", primary="finnhub")

    assert source == "finnhub"
    assert calls == ["finnhub"]
    assert not df.empty


def test_finnhub_ohlcv_skipped_when_disabled():
    from finance_app.ingest import _fetch_with_fallback

    empty = pd.DataFrame(
        columns=["date", "open", "high", "low", "close", "adj_close", "volume"]
    )
    hit = empty.copy()
    hit.loc[0] = [pd.Timestamp("2024-01-02"), 1, 1, 1, 1, 1, 1]

    calls: list[str] = []

    def fake_fh(*_a, **_k):
        calls.append("finnhub")
        return hit

    def fake_ti(*_a, **_k):
        calls.append("tiingo")
        return hit

    settings = MagicMock()
    settings.price_primary_normalized = "finnhub"
    settings.finnhub_ohlcv_enabled = False

    with (
        patch("finance_app.ingest.get_settings", return_value=settings),
        patch("finance_app.ingest.finnhub_configured", return_value=True),
        patch("finance_app.ingest.tiingo_configured", return_value=True),
        patch("finance_app.ingest.fetch_ohlcv_finnhub", side_effect=fake_fh),
        patch("finance_app.ingest.fetch_tiingo_ohlcv", side_effect=fake_ti),
        patch("finance_app.ingest.fetch_stooq_ohlcv", return_value=empty),
        patch("finance_app.ingest.fetch_yfinance_ohlcv", return_value=empty),
    ):
        df, source = _fetch_with_fallback("AAPL", primary="finnhub")

    assert source == "tiingo"
    assert "finnhub" not in calls
    assert not df.empty


def test_earnings_order_finnhub_primary():
    from finance_app.ingest.earnings import fetch_earnings_events_with_fallback

    frame = pd.DataFrame(
        {
            "report_datetime": [pd.Timestamp("2024-01-25")],
            "reported_eps": [1.0],
            "eps_estimate": [0.9],
            "surprise_pct": [11.1],
        }
    )
    calls: list[str] = []

    def fake_fh(*_a, **_k):
        calls.append("finnhub")
        return frame

    def fake_fmp(*_a, **_k):
        calls.append("fmp")
        return frame

    with (
        patch(
            "finance_app.ingest.earnings.effective_earnings_primary",
            return_value="finnhub",
        ),
        patch("finance_app.ingest.earnings.finnhub_configured", return_value=True),
        patch("finance_app.ingest.earnings.fmp_configured", return_value=True),
        patch(
            "finance_app.ingest.earnings.fetch_earnings_events_finnhub",
            side_effect=fake_fh,
        ),
        patch(
            "finance_app.ingest.earnings.fetch_fmp_earnings_events",
            side_effect=fake_fmp,
        ),
    ):
        df, source = fetch_earnings_events_with_fallback("AAPL")

    assert source == "finnhub"
    assert calls == ["finnhub"]
    assert not df.empty
