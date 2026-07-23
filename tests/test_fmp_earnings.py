"""Tests for FMP earnings ingest and provider fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from finance_app.ingest.earnings_fmp import (
    _rows_to_frame,
    fetch_fmp_earnings_events,
)


SAMPLE_FMP = [
    {
        "date": "2024-01-25",
        "epsActual": 2.18,
        "epsEstimated": 2.1,
        "time": "amc",
    },
    {
        "date": "2023-10-26",
        "epsActual": 1.46,
        "epsEstimated": 1.39,
        "time": "amc",
    },
]


def test_rows_to_frame_maps_and_computes_surprise():
    df = _rows_to_frame(SAMPLE_FMP)
    assert len(df) == 2
    assert df.iloc[0]["reported_eps"] == pytest.approx(1.46)
    assert df.iloc[1]["eps_estimate"] == pytest.approx(2.1)
    # (2.18 - 2.1) / 2.1 * 100
    assert df.iloc[1]["surprise_pct"] == pytest.approx((2.18 - 2.1) / 2.1 * 100)
    assert df.iloc[1]["report_datetime"].hour == 16


def test_fetch_fmp_empty_without_key():
    df = fetch_fmp_earnings_events("AAPL", api_key="")
    assert df.empty


def test_fetch_fmp_maps_http(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_FMP
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch(
        "finance_app.ingest.earnings_fmp.httpx.Client", return_value=mock_client
    ):
        df = fetch_fmp_earnings_events("aapl", api_key="test-key")
    assert len(df) == 2
    args, kwargs = mock_client.get.call_args
    assert "earnings" in args[0]
    assert kwargs["params"]["symbol"] == "AAPL"
    assert kwargs["params"]["apikey"] == "test-key"


def test_fallback_prefers_fmp(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.ingest.earnings as earnings
    import finance_app.ingest.earnings_fmp as earnings_fmp
    from finance_app.config import Settings
    from finance_app.ingest.earnings import fetch_earnings_events_with_fallback

    settings = Settings(
        database_path=str(tmp_path / "e.db"),
        fmp_api_key="k",
        earnings_primary="fmp",
    )
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: settings)
    monkeypatch.setattr(earnings, "get_settings", lambda: settings)
    monkeypatch.setattr(earnings_fmp, "get_settings", lambda: settings)

    fmp_df = pd.DataFrame(
        {
            "report_datetime": pd.to_datetime(["2024-01-25"]),
            "reported_eps": [1.0],
            "eps_estimate": [0.9],
            "surprise_pct": [11.1],
        }
    )
    with patch(
        "finance_app.ingest.earnings.fetch_fmp_earnings_events", return_value=fmp_df
    ) as mock_f, patch(
        "finance_app.ingest.earnings.fetch_yfinance_earnings_events"
    ) as mock_y:
        df, source = fetch_earnings_events_with_fallback("AAPL", earnings_primary="fmp")
        assert source == "fmp"
        assert len(df) == 1
        mock_f.assert_called_once()
        mock_y.assert_not_called()


def test_fallback_prefers_yfinance_when_primary(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.ingest.earnings as earnings
    import finance_app.ingest.earnings_fmp as earnings_fmp
    from finance_app.config import Settings
    from finance_app.ingest.earnings import fetch_earnings_events_with_fallback

    settings = Settings(
        database_path=str(tmp_path / "e2.db"),
        fmp_api_key="k",
        earnings_primary="yfinance",
    )
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: settings)
    monkeypatch.setattr(earnings, "get_settings", lambda: settings)
    monkeypatch.setattr(earnings_fmp, "get_settings", lambda: settings)

    yf_df = pd.DataFrame(
        {
            "report_datetime": pd.to_datetime(["2024-01-25"]),
            "reported_eps": [2.0],
            "eps_estimate": [1.8],
            "surprise_pct": [11.1],
        }
    )
    with patch(
        "finance_app.ingest.earnings.fetch_yfinance_earnings_events",
        return_value=yf_df,
    ) as mock_y, patch(
        "finance_app.ingest.earnings.fetch_fmp_earnings_events"
    ) as mock_f:
        df, source = fetch_earnings_events_with_fallback(
            "AAPL", earnings_primary="yfinance"
        )
        assert source == "yfinance"
        assert df.iloc[0]["reported_eps"] == pytest.approx(2.0)
        mock_y.assert_called_once()
        mock_f.assert_not_called()


def test_fmp_primary_falls_back_to_yfinance(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.ingest.earnings as earnings
    import finance_app.ingest.earnings_fmp as earnings_fmp
    from finance_app.config import Settings
    from finance_app.ingest.earnings import fetch_earnings_events_with_fallback

    settings = Settings(
        database_path=str(tmp_path / "e3.db"),
        fmp_api_key="k",
        earnings_primary="fmp",
    )
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: settings)
    monkeypatch.setattr(earnings, "get_settings", lambda: settings)
    monkeypatch.setattr(earnings_fmp, "get_settings", lambda: settings)

    yf_df = pd.DataFrame(
        {
            "report_datetime": pd.to_datetime(["2024-01-25"]),
            "reported_eps": [3.0],
            "eps_estimate": [2.5],
            "surprise_pct": [20.0],
        }
    )
    empty = pd.DataFrame(
        columns=["report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
    )
    with patch(
        "finance_app.ingest.earnings.fetch_fmp_earnings_events", return_value=empty
    ), patch(
        "finance_app.ingest.earnings.fetch_yfinance_earnings_events",
        return_value=yf_df,
    ):
        df, source = fetch_earnings_events_with_fallback("AAPL", earnings_primary="fmp")
        assert source == "yfinance"
        assert df.iloc[0]["reported_eps"] == pytest.approx(3.0)


def test_normalize_earnings_primary_without_key():
    from finance_app.config import normalize_earnings_primary

    assert (
        normalize_earnings_primary("fmp", fmp_configured=False) == "yfinance"
    )
    assert normalize_earnings_primary("fmp", fmp_configured=True) == "fmp"
    assert normalize_earnings_primary("yfinance", fmp_configured=True) == "yfinance"
