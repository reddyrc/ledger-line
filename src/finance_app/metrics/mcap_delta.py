"""Watchlist valuation deltas: market cap, PE, PB, PS over a date window."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from finance_app.db import load_fundamentals, load_ohlcv
from finance_app.ingest.edgar import ingest_fundamentals
from finance_app.metrics.valuation_history import _build_asof_fundamentals, _round

MAX_SYMBOLS = 15
RATIO_KEYS = ("pe", "pb", "ps")
METRIC_KEYS = ("market_cap", *RATIO_KEYS)


def build_valuation_frame(ohlcv: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame:
    """
    Daily PE / PB / PS / market-cap series (same join as valuation history).

    Returns columns: date, price, shares, market_cap, pe, pb, ps.
    """
    cols = ["date", "price", "shares", "market_cap", "pe", "pb", "ps"]
    if ohlcv is None or ohlcv.empty:
        return pd.DataFrame(columns=cols)
    asof = _build_asof_fundamentals(fund)
    if asof.empty:
        return pd.DataFrame(columns=cols)

    prices = ohlcv.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values("date")
    price_col = (
        "adj_close"
        if "adj_close" in prices.columns and prices["adj_close"].notna().any()
        else "close"
    )
    prices["price"] = prices[price_col].astype(float)

    asof = asof.sort_values("end_date")
    merged = pd.merge_asof(
        prices[["date", "price"]],
        asof,
        left_on="date",
        right_on="end_date",
        direction="backward",
    )
    merged["shares"] = merged["shares"].where(
        merged["shares"].notna() & (merged["shares"] > 0),
        merged["shares_approx"],
    )
    merged["market_cap"] = merged["price"] * merged["shares"]
    merged["pe"] = np.where(
        merged["ttm_eps"].notna() & (merged["ttm_eps"] != 0),
        merged["price"] / merged["ttm_eps"],
        np.nan,
    )
    merged["pb"] = np.where(
        merged["equity"].notna()
        & (merged["equity"] != 0)
        & merged["market_cap"].notna(),
        merged["market_cap"] / merged["equity"],
        np.nan,
    )
    merged["ps"] = np.where(
        merged["ttm_revenue"].notna()
        & (merged["ttm_revenue"] != 0)
        & merged["market_cap"].notna(),
        merged["market_cap"] / merged["ttm_revenue"],
        np.nan,
    )
    return merged[cols].dropna(subset=["market_cap"])


def build_mcap_frame(ohlcv: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible alias: valuation frame trimmed to mcap columns."""
    frame = build_valuation_frame(ohlcv, fund)
    if frame.empty:
        return pd.DataFrame(columns=["date", "price", "shares", "market_cap"])
    return frame[["date", "price", "shares", "market_cap"]]


def _empty_delta(error: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "start_date": None,
        "end_date": None,
        "start_mcap": None,
        "end_mcap": None,
        "delta_mcap": None,
        "delta_mcap_pct": None,
        "start_price": None,
        "end_price": None,
        "delta_price_pct": None,
        "shares_start": None,
        "shares_end": None,
        "error": error,
    }
    for key in RATIO_KEYS:
        out[f"start_{key}"] = None
        out[f"end_{key}"] = None
        out[f"delta_{key}"] = None
        out[f"delta_{key}_pct"] = None
    return out


def _metric_delta(
    start_val: Any, end_val: Any, *, digits: int = 4
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Return start, end, delta, delta_pct (fraction) for one metric."""
    if start_val is None or end_val is None or (
        isinstance(start_val, float) and np.isnan(start_val)
    ) or (isinstance(end_val, float) and np.isnan(end_val)):
        return None, None, None, None
    try:
        s = float(start_val)
        e = float(end_val)
    except (TypeError, ValueError):
        return None, None, None, None
    if np.isnan(s) or np.isnan(e):
        return None, None, None, None
    delta = e - s
    pct = (delta / s) if s != 0 else None
    return (
        _round(s, digits),
        _round(e, digits),
        _round(delta, digits),
        _round(pct, 6) if pct is not None else None,
    )


def delta_from_valuation_frame(
    frame: pd.DataFrame,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict[str, Any]:
    """
    Signed end − start for market_cap, PE, PB, PS on the same endpoint bars.

    Uses first valid market-cap bar on/after start and last on/before end.
    Pure helper — no I/O.
    """
    empty = _empty_delta("No market-cap points in range")
    if frame is None or frame.empty:
        return empty

    df = frame.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df = df[df["market_cap"].notna() & (df["market_cap"] > 0)]
    if df.empty:
        return empty

    if start:
        after = df[df["date"] >= pd.to_datetime(start)]
        if after.empty:
            return {**empty, "error": "No market-cap data on/after start"}
        start_row = after.iloc[0]
    else:
        start_row = df.iloc[0]

    if end:
        before = df[df["date"] <= pd.to_datetime(end)]
        if before.empty:
            return {**empty, "error": "No market-cap data on/before end"}
        end_row = before.iloc[-1]
    else:
        end_row = df.iloc[-1]

    if pd.Timestamp(start_row["date"]) > pd.Timestamp(end_row["date"]):
        return {**empty, "error": "Start bar is after end bar"}

    start_mcap, end_mcap, delta_mcap, delta_mcap_pct = _metric_delta(
        start_row["market_cap"], end_row["market_cap"], digits=2
    )
    start_price = float(start_row["price"])
    end_price = float(end_row["price"])

    out: dict[str, Any] = {
        "start_date": pd.Timestamp(start_row["date"]).strftime("%Y-%m-%d"),
        "end_date": pd.Timestamp(end_row["date"]).strftime("%Y-%m-%d"),
        "start_mcap": start_mcap,
        "end_mcap": end_mcap,
        "delta_mcap": delta_mcap,
        "delta_mcap_pct": delta_mcap_pct,
        "start_price": _round(start_price, 4),
        "end_price": _round(end_price, 4),
        "delta_price_pct": (
            _round((end_price / start_price) - 1.0, 6) if start_price else None
        ),
        "shares_start": _round(float(start_row["shares"]), 0),
        "shares_end": _round(float(end_row["shares"]), 0),
        "error": None,
    }

    for key in RATIO_KEYS:
        s, e, d, pct = _metric_delta(
            start_row.get(key), end_row.get(key), digits=4
        )
        out[f"start_{key}"] = s
        out[f"end_{key}"] = e
        out[f"delta_{key}"] = d
        out[f"delta_{key}_pct"] = pct

    return out


def delta_from_mcap_frame(
    frame: pd.DataFrame,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict[str, Any]:
    """Backward-compatible entry point (works with mcap-only or full frames)."""
    return delta_from_valuation_frame(frame, start=start, end=end)


def compute_symbol_mcap_delta(
    symbol: str,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Load local OHLCV + EDGAR fundamentals and compute valuation deltas."""
    symbol = symbol.upper().strip()
    base: dict[str, Any] = {"symbol": symbol}

    existing = load_fundamentals(symbol)
    if refresh or existing.empty:
        try:
            ingest_fundamentals(symbol)
        except Exception as exc:
            return {**base, "error": f"Fundamentals: {exc}"}
        existing = load_fundamentals(symbol)

    if existing.empty:
        return {**base, "error": "No fundamental data available"}

    ohlcv = load_ohlcv(symbol, start=start, end=end)
    if ohlcv.empty:
        ohlcv = load_ohlcv(symbol)
        if ohlcv.empty:
            return {**base, "error": "No price data available"}
        if start:
            ohlcv = ohlcv[ohlcv["date"] >= pd.to_datetime(start)]
        if end:
            ohlcv = ohlcv[ohlcv["date"] <= pd.to_datetime(end)]

    # Prefer full history so as-of fundamentals exist at window start
    ohlcv_full = load_ohlcv(symbol)
    if not ohlcv_full.empty:
        frame = build_valuation_frame(ohlcv_full, existing)
    else:
        frame = build_valuation_frame(ohlcv, existing)

    if frame.empty:
        return {**base, "error": "Could not build valuation series"}

    result = delta_from_valuation_frame(frame, start=start, end=end)
    return {**base, **result}


def compute_mcap_delta_batch(
    symbols: list[str],
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Watchlist valuation deltas with mcap sums and ratio averages."""
    tickers: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = str(raw).upper().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        tickers.append(sym)
        if len(tickers) >= MAX_SYMBOLS:
            break

    rows: list[dict[str, Any]] = []
    for sym in tickers:
        rows.append(
            compute_symbol_mcap_delta(
                sym, start=start, end=end, refresh=refresh
            )
        )

    ok = [r for r in rows if r.get("error") is None and r.get("delta_mcap") is not None]
    failed = len(rows) - len(ok)

    def _sum(key: str) -> Optional[float]:
        vals = [float(r[key]) for r in ok if r.get(key) is not None]
        if not vals:
            return None
        return _round(sum(vals), 2)

    def _avg(key: str, digits: int = 4) -> Optional[float]:
        vals = [float(r[key]) for r in ok if r.get(key) is not None]
        if not vals:
            return None
        return _round(sum(vals) / len(vals), digits)

    totals: dict[str, Any] = {
        "delta_mcap": _sum("delta_mcap"),
        "start_mcap": _sum("start_mcap"),
        "end_mcap": _sum("end_mcap"),
        "included": len(ok),
        "failed": failed,
    }
    for key in RATIO_KEYS:
        totals[f"avg_delta_{key}"] = _avg(f"delta_{key}")
        totals[f"avg_delta_{key}_pct"] = _avg(f"delta_{key}_pct", digits=6)

    return {
        "start": start,
        "end": end,
        "rows": rows,
        "totals": totals,
        "disclaimer": (
            "Market cap = daily price × as-of SEC EDGAR shares (diluted when "
            "reported, else NetIncome/EPS). PE / PB / PS use TTM EPS & revenue "
            "and equity joined as-of the same bars. Δ = end − start over the "
            "selected window."
        ),
    }
