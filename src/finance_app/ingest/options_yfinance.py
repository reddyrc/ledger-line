"""Yahoo Finance options chain + contract history ingest."""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

import pandas as pd
import yfinance as yf

GREEK_KEYS = ("delta", "gamma", "theta", "vega", "rho")


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            return None
        return fv
    except (TypeError, ValueError):
        return None


def _round(v: Any, nd: int = 6) -> Optional[float]:
    fv = _num(v)
    return None if fv is None else round(fv, nd)


def _mid(bid: Optional[float], ask: Optional[float], last: Optional[float]) -> Optional[float]:
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return _round((bid + ask) / 2.0)
    if last is not None:
        return _round(last)
    if bid is not None:
        return _round(bid)
    if ask is not None:
        return _round(ask)
    return None


def normalize_option_row(row: dict[str, Any], side: str) -> dict[str, Any]:
    """Normalize a Yahoo option chain row into a stable schema."""
    bid = _round(row.get("bid"))
    ask = _round(row.get("ask"))
    last = _round(row.get("lastPrice") if "lastPrice" in row else row.get("last"))
    out: dict[str, Any] = {
        "contract_symbol": row.get("contractSymbol") or row.get("contract_symbol"),
        "side": side,
        "strike": _round(row.get("strike")),
        "bid": bid,
        "ask": ask,
        "last": last,
        "mid": _mid(bid, ask, last),
        "volume": _round(row.get("volume"), 0),
        "open_interest": _round(
            row.get("openInterest") if "openInterest" in row else row.get("open_interest"),
            0,
        ),
        "implied_volatility": _round(
            row.get("impliedVolatility")
            if "impliedVolatility" in row
            else row.get("implied_volatility")
        ),
        "day_low": _round(row.get("dayLow") if "dayLow" in row else row.get("day_low")),
        "day_high": _round(row.get("dayHigh") if "dayHigh" in row else row.get("day_high")),
        "in_the_money": bool(row.get("inTheMoney")) if row.get("inTheMoney") is not None else None,
    }
    for g in GREEK_KEYS:
        camel = g
        out[g] = _round(row.get(camel))
    return out


def _df_to_rows(df: Optional[pd.DataFrame], side: str) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        rows.append(normalize_option_row(r.to_dict(), side))
    rows.sort(key=lambda x: (x.get("strike") is None, x.get("strike") or 0))
    return rows


def list_expirations(
    symbol: str,
    *,
    ticker_factory: Callable[[str], Any] = yf.Ticker,
) -> list[str]:
    """Return available option expiration dates (YYYY-MM-DD)."""
    symbol = symbol.upper()
    try:
        opts = ticker_factory(symbol).options or ()
    except Exception as exc:
        raise RuntimeError(f"Failed to list option expirations: {exc}") from exc
    return [str(d)[:10] for d in opts]


def fetch_option_chain(
    symbol: str,
    expiration: str,
    *,
    ticker_factory: Callable[[str], Any] = yf.Ticker,
) -> dict[str, Any]:
    """
    Fetch calls/puts for one expiration.
    Returns {expiration, calls, puts}.
    """
    symbol = symbol.upper()
    expiration = str(expiration)[:10]
    try:
        chain = ticker_factory(symbol).option_chain(expiration)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch option chain for {expiration}: {exc}") from exc

    calls_df = getattr(chain, "calls", None)
    puts_df = getattr(chain, "puts", None)
    return {
        "expiration": expiration,
        "calls": _df_to_rows(calls_df, "call"),
        "puts": _df_to_rows(puts_df, "put"),
    }


def fetch_underlying_spot(
    symbol: str,
    *,
    ticker_factory: Callable[[str], Any] = yf.Ticker,
) -> Optional[float]:
    """Best-effort last/underlying price from Yahoo info/fast_info."""
    symbol = symbol.upper()
    try:
        t = ticker_factory(symbol)
        fi = getattr(t, "fast_info", None)
        if fi is not None:
            for key in ("lastPrice", "last_price", "regularMarketPrice"):
                v = None
                try:
                    v = fi[key] if hasattr(fi, "__getitem__") else getattr(fi, key, None)
                except Exception:
                    v = getattr(fi, key, None) if not isinstance(fi, dict) else fi.get(key)
                spot = _round(v)
                if spot is not None:
                    return spot
        info = t.info or {}
        return _round(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
    except Exception:
        return None


def fetch_contract_history(
    contract_symbol: str,
    *,
    period: str = "3mo",
    ticker_factory: Callable[[str], Any] = yf.Ticker,
) -> pd.DataFrame:
    """Daily OHLCV history for an OCC option contract symbol."""
    contract_symbol = contract_symbol.upper()
    try:
        hist = ticker_factory(contract_symbol).history(period=period, auto_adjust=False)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch contract history: {exc}") from exc

    if hist is None or hist.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    hist = hist.reset_index()
    date_col = "Date" if "Date" in hist.columns else hist.columns[0]
    hist = hist.rename(
        columns={
            date_col: "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None)
    cols = ["date", "open", "high", "low", "close", "volume"]
    for c in cols:
        if c not in hist.columns:
            hist[c] = None
    return hist[cols].dropna(subset=["close"])
