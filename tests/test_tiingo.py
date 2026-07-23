"""Tests for Tiingo price ingest and fallback order."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from finance_app.ingest.prices_tiingo import (
    fetch_tiingo_meta,
    fetch_tiingo_news,
    fetch_tiingo_ohlcv,
)


SAMPLE_PRICES = [
    {
        "date": "2024-01-02T00:00:00.000Z",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "adjClose": 104.0,
        "volume": 1_000_000,
    },
    {
        "date": "2024-01-03T00:00:00.000Z",
        "open": 104.0,
        "high": 106.0,
        "low": 103.0,
        "close": 105.5,
        "adjClose": 105.5,
        "volume": 900_000,
    },
]


def test_fetch_tiingo_ohlcv_empty_without_key():
    df = fetch_tiingo_ohlcv("AAPL", api_key="")
    assert df.empty
    assert list(df.columns) == [
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
    ]


def test_fetch_tiingo_ohlcv_maps_rows():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_PRICES

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("finance_app.ingest.prices_tiingo.httpx.Client", return_value=mock_client):
        df = fetch_tiingo_ohlcv("aapl", api_key="test-key")

    assert len(df) == 2
    assert df.iloc[0]["close"] == pytest.approx(104.0)
    assert df.iloc[1]["adj_close"] == pytest.approx(105.5)
    assert str(df.iloc[0]["date"].date()) == "2024-01-02"
    mock_client.get.assert_called_once()
    args, kwargs = mock_client.get.call_args
    assert "AAPL" in args[0]
    assert kwargs["headers"]["Authorization"] == "Token test-key"
    assert kwargs["params"]["startDate"] == "1970-01-01"


def test_fetch_tiingo_meta_parses():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "ticker": "MSFT",
        "name": "Microsoft Corporation",
        "exchangeCode": "NASDAQ",
        "description": "Software company",
        "startDate": "1986-03-13",
        "endDate": "2024-01-03",
    }
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("finance_app.ingest.prices_tiingo.httpx.Client", return_value=mock_client):
        meta = fetch_tiingo_meta("msft", api_key="k")

    assert meta["name"] == "Microsoft Corporation"
    assert meta["exchange"] == "NASDAQ"
    assert meta["start_date"] == "1986-03-13"


def test_fetch_tiingo_news_parses():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "title": "Earnings beat",
            "url": "https://example.com/a",
            "publishedDate": "2024-01-02T12:00:00Z",
            "source": "example.com",
        }
    ]
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("finance_app.ingest.prices_tiingo.httpx.Client", return_value=mock_client):
        news = fetch_tiingo_news("AAPL", limit=5, api_key="k")

    assert len(news) == 1
    assert news[0]["title"] == "Earnings beat"
    assert news[0]["url"] == "https://example.com/a"


def test_fallback_prefers_tiingo_when_configured(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.ingest as ingest
    from finance_app.config import Settings

    monkeypatch.setenv("TIINGO_API_KEY", "unit-test-key")
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(
        cfg,
        "get_settings",
        lambda: Settings(
            database_path=str(tmp_path / "t.db"),
            tiingo_api_key="unit-test-key",
            price_primary="tiingo",
        ),
    )

    tiingo_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "adj_close": [1.0],
            "volume": [100],
        }
    )

    with patch(
        "finance_app.ingest.fetch_tiingo_ohlcv", return_value=tiingo_df
    ) as mock_t, patch(
        "finance_app.ingest.fetch_stooq_ohlcv"
    ) as mock_s, patch(
        "finance_app.ingest.fetch_yfinance_ohlcv"
    ) as mock_y:
        df, source = ingest._fetch_with_fallback("AAPL", primary="tiingo")
        assert source == "tiingo"
        assert len(df) == 1
        mock_t.assert_called_once()
        mock_s.assert_not_called()
        mock_y.assert_not_called()


def test_fallback_prefers_yfinance_when_primary(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.ingest as ingest
    from finance_app.config import Settings

    monkeypatch.setenv("TIINGO_API_KEY", "unit-test-key")
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(
        cfg,
        "get_settings",
        lambda: Settings(
            database_path=str(tmp_path / "ty.db"),
            tiingo_api_key="unit-test-key",
            price_primary="yfinance",
        ),
    )

    yf_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "open": [3.0],
            "high": [3.0],
            "low": [3.0],
            "close": [3.0],
            "adj_close": [3.0],
            "volume": [300],
        }
    )

    with patch(
        "finance_app.ingest.fetch_yfinance_ohlcv", return_value=yf_df
    ) as mock_y, patch(
        "finance_app.ingest.fetch_stooq_ohlcv"
    ) as mock_s, patch(
        "finance_app.ingest.fetch_tiingo_ohlcv"
    ) as mock_t:
        df, source = ingest._fetch_with_fallback("AAPL", primary="yfinance")
        assert source == "yfinance"
        assert df.iloc[0]["close"] == pytest.approx(3.0)
        mock_y.assert_called_once()
        mock_s.assert_not_called()
        mock_t.assert_not_called()


def test_fallback_skips_tiingo_without_key(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.ingest as ingest
    from finance_app.config import Settings

    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(
        cfg,
        "get_settings",
        lambda: Settings(database_path=str(tmp_path / "t2.db"), tiingo_api_key=""),
    )

    stooq_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "open": [2.0],
            "high": [2.0],
            "low": [2.0],
            "close": [2.0],
            "adj_close": [2.0],
            "volume": [200],
        }
    )

    with patch(
        "finance_app.ingest.tiingo_configured", return_value=False
    ), patch(
        "finance_app.ingest.fetch_stooq_ohlcv", return_value=stooq_df
    ) as mock_s, patch(
        "finance_app.ingest.fetch_yfinance_ohlcv"
    ) as mock_y:
        df, source = ingest._fetch_with_fallback("AAPL", primary="tiingo")
        assert source == "stooq"
        assert df.iloc[0]["close"] == pytest.approx(2.0)
        mock_s.assert_called_once()
        mock_y.assert_not_called()


def test_normalize_price_primary():
    from finance_app.config import normalize_price_primary

    assert normalize_price_primary("YFINANCE") == "yfinance"
    assert normalize_price_primary("tiingo") == "tiingo"
    assert normalize_price_primary("nope") == "tiingo"
    assert normalize_price_primary(None) == "tiingo"
