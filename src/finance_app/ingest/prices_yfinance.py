from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import yfinance as yf


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        fv = float(v)
        if fv != fv:  # NaN
            return None
        return fv
    except (TypeError, ValueError):
        return None


def _period_dict(df: Any, period: str = "0q") -> dict[str, Optional[float]]:
    """Extract one period row from a yfinance Analysis DataFrame."""
    if df is None:
        return {}
    try:
        if hasattr(df, "empty") and df.empty:
            return {}
        if period in getattr(df, "index", []):
            row = df.loc[period]
        elif hasattr(df, "iloc") and len(df):
            # Fall back to first row when index labels differ
            row = df.iloc[0]
        else:
            return {}
        out: dict[str, Optional[float]] = {}
        for k, v in row.items():
            out[str(k)] = _num(v)
        return out
    except Exception:
        return {}


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


def fetch_yfinance_short_snapshot(symbol: str) -> dict:
    """
    Point-in-time short interest enrichment from Yahoo quote summary.
    Keys: shares_short, short_pct_float, short_ratio, shares_short_prior_month.
    """
    empty = {
        "shares_short": None,
        "short_pct_float": None,
        "short_ratio": None,
        "shares_short_prior_month": None,
    }
    try:
        info = yf.Ticker(symbol.upper()).info or {}
    except Exception:
        return empty

    def num(key: str):
        v = info.get(key)
        if v is None:
            return None
        try:
            fv = float(v)
            if fv != fv:
                return None
            return fv
        except (TypeError, ValueError):
            return None

    # Yahoo sometimes returns shortPercentOfFloat as 0–1, sometimes as percent.
    pct = num("shortPercentOfFloat")
    if pct is not None and pct > 1.5:
        pct = pct / 100.0

    return {
        "shares_short": num("sharesShort"),
        "short_pct_float": pct,
        "short_ratio": num("shortRatio"),
        "shares_short_prior_month": num("sharesShortPriorMonth"),
    }


def fetch_yfinance_earnings_analysis(symbol: str) -> dict[str, Any]:
    """
    Yahoo Analysis module snapshot for the current quarter (0q):
    revenue/EPS estimates, EPS revisions, EPS trend.
    """
    empty: dict[str, Any] = {
        "revenue_0q": {},
        "earnings_0q": {},
        "eps_revisions_0q": {},
        "eps_trend_0q": {},
    }
    try:
        t = yf.Ticker(symbol.upper())
    except Exception:
        return empty

    def safe(attr: str):
        try:
            return getattr(t, attr, None)
        except Exception:
            return None

    return {
        "revenue_0q": _period_dict(safe("revenue_estimate"), "0q"),
        "earnings_0q": _period_dict(safe("earnings_estimate"), "0q"),
        "eps_revisions_0q": _period_dict(safe("eps_revisions"), "0q"),
        "eps_trend_0q": _period_dict(safe("eps_trend"), "0q"),
    }
