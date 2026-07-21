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
