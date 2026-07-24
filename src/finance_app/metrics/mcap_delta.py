"""Market-cap change over a date window for a watchlist of tickers."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from finance_app.db import load_fundamentals, load_ohlcv
from finance_app.ingest.edgar import ingest_fundamentals
from finance_app.metrics.valuation_history import _build_asof_fundamentals, _round

MAX_SYMBOLS = 15


def build_mcap_frame(ohlcv: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame:
    """
    Daily market-cap series: price × as-of EDGAR shares (same merge as valuation history).
    Returns columns: date, price, shares, market_cap.
    """
    if ohlcv is None or ohlcv.empty:
        return pd.DataFrame(columns=["date", "price", "shares", "market_cap"])
    asof = _build_asof_fundamentals(fund)
    if asof.empty:
        return pd.DataFrame(columns=["date", "price", "shares", "market_cap"])

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
    return merged[["date", "price", "shares", "market_cap"]].dropna(
        subset=["market_cap"]
    )


def delta_from_mcap_frame(
    frame: pd.DataFrame,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict[str, Any]:
    """
    Signed Δ market cap = end_mcap − start_mcap.

    Uses first valid bar on/after start and last valid bar on/before end.
    Pure helper — no I/O.
    """
    empty = {
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
        "error": "No market-cap points in range",
    }
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

    start_mcap = float(start_row["market_cap"])
    end_mcap = float(end_row["market_cap"])
    delta = end_mcap - start_mcap
    start_price = float(start_row["price"])
    end_price = float(end_row["price"])

    return {
        "start_date": pd.Timestamp(start_row["date"]).strftime("%Y-%m-%d"),
        "end_date": pd.Timestamp(end_row["date"]).strftime("%Y-%m-%d"),
        "start_mcap": _round(start_mcap, 2),
        "end_mcap": _round(end_mcap, 2),
        "delta_mcap": _round(delta, 2),
        "delta_mcap_pct": _round(delta / start_mcap, 6) if start_mcap else None,
        "start_price": _round(start_price, 4),
        "end_price": _round(end_price, 4),
        "delta_price_pct": (
            _round((end_price / start_price) - 1.0, 6) if start_price else None
        ),
        "shares_start": _round(float(start_row["shares"]), 0),
        "shares_end": _round(float(end_row["shares"]), 0),
        "error": None,
    }


def compute_symbol_mcap_delta(
    symbol: str,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Load local OHLCV + EDGAR fundamentals and compute Δ market cap."""
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

    # Prefer a bit of lookback so as-of shares exist at window start
    ohlcv_full = load_ohlcv(symbol)
    if not ohlcv_full.empty:
        # Build mcap on full history, then slice endpoints from window
        frame = build_mcap_frame(ohlcv_full, existing)
    else:
        frame = build_mcap_frame(ohlcv, existing)

    if frame.empty:
        return {**base, "error": "Could not build market-cap series"}

    result = delta_from_mcap_frame(frame, start=start, end=end)
    return {**base, **result}


def compute_mcap_delta_batch(
    symbols: list[str],
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Watchlist Δ market cap with cumulative totals over successful rows."""
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

    return {
        "start": start,
        "end": end,
        "rows": rows,
        "totals": {
            "delta_mcap": _sum("delta_mcap"),
            "start_mcap": _sum("start_mcap"),
            "end_mcap": _sum("end_mcap"),
            "included": len(ok),
            "failed": failed,
        },
        "disclaimer": (
            "Market cap = daily price × as-of SEC EDGAR shares (diluted when "
            "reported, else NetIncome/EPS). Δ = end − start over the selected window."
        ),
    }
