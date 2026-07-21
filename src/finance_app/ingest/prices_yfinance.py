from __future__ import annotations

from typing import Optional

import pandas as pd
import yfinance as yf


def fetch_yfinance_ohlcv(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: str = "max",
) -> pd.DataFrame:
    """Fetch daily OHLCV (adjusted) for a US equity/ETF ticker via Yahoo Finance."""
    ticker = yf.Ticker(symbol.upper())
    kwargs = {"auto_adjust": False, "actions": False}
    if start or end:
        hist = ticker.history(start=start, end=end, **kwargs)
    else:
        hist = ticker.history(period=period, **kwargs)

    if hist is None or hist.empty:
        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "adj_close", "volume"]
        )

    hist = hist.reset_index()
    # Column name is usually Datetime or Date
    date_col = "Date" if "Date" in hist.columns else hist.columns[0]
    hist = hist.rename(
        columns={
            date_col: "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    if "adj_close" not in hist.columns:
        hist["adj_close"] = hist["close"]

    hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None)
    return hist[["date", "open", "high", "low", "close", "adj_close", "volume"]].dropna(
        subset=["close"]
    )


def fetch_yfinance_earnings_events(symbol: str, limit: int = 100) -> pd.DataFrame:
    """Fetch historical earnings report timestamps and reported/estimated EPS."""
    events = yf.Ticker(symbol.upper()).get_earnings_dates(limit=limit)
    if events is None or events.empty:
        return pd.DataFrame(
            columns=[
                "report_datetime",
                "reported_eps",
                "eps_estimate",
                "surprise_pct",
            ]
        )

    events = events.reset_index()
    date_col = "Earnings Date" if "Earnings Date" in events.columns else events.columns[0]
    events = events.rename(
        columns={
            date_col: "report_datetime",
            "Reported EPS": "reported_eps",
            "EPS Estimate": "eps_estimate",
            "Surprise(%)": "surprise_pct",
        }
    )
    events["report_datetime"] = pd.to_datetime(
        events["report_datetime"], utc=True, errors="coerce"
    ).dt.tz_convert("America/New_York").dt.tz_localize(None)
    for col in ("reported_eps", "eps_estimate", "surprise_pct"):
        if col not in events.columns:
            events[col] = None
    return events[
        ["report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
    ].dropna(subset=["report_datetime"])
