"""Enrichment helpers for the multi-ticker earnings calendar."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from finance_app.db import (
    get_latest_options_chain_cache,
    load_earnings_analysis_snapshot,
    load_earnings_events,
    load_ohlcv,
    load_options_iv_snapshots,
    upsert_earnings_analysis_snapshot,
)
from finance_app.metrics.valuation_history import _forward_returns

ANALYSIS_TTL = timedelta(hours=18)
ANALYSIS_WORKERS = 6
AVG_MOVE_LOOKBACK = 8


def _round(v: Any, nd: int = 6) -> Optional[float]:
    if v is None:
        return None
    try:
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            return None
        return round(fv, nd)
    except (TypeError, ValueError):
        return None


def earnings_session(report_datetime: Any) -> Optional[str]:
    """BMO if report hour < 12 local NY time, else AMC. Null if unparseable."""
    ts = pd.to_datetime(report_datetime, errors="coerce")
    if pd.isna(ts):
        return None
    # Naive timestamps from ingest are already America/New_York local.
    hour = int(ts.hour)
    if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
        # Date-only: unknown session
        return None
    return "BMO" if hour < 12 else "AMC"


def last_surprise_pct(
    symbol: str, before: Any
) -> Optional[float]:
    """Most recent surprise_pct strictly before this report datetime."""
    before_ts = pd.to_datetime(before, errors="coerce")
    if pd.isna(before_ts):
        return None
    try:
        hist = load_earnings_events(symbol)
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    hist = hist.dropna(subset=["report_datetime"]).sort_values("report_datetime")
    prior = hist[hist["report_datetime"] < before_ts]
    prior = prior.dropna(subset=["surprise_pct"])
    if prior.empty:
        return None
    return _round(prior.iloc[-1]["surprise_pct"])


def spot_price(symbol: str) -> Optional[float]:
    try:
        ohlcv = load_ohlcv(symbol)
    except Exception:
        return None
    if ohlcv is None or ohlcv.empty:
        return None
    col = (
        "adj_close"
        if "adj_close" in ohlcv.columns and ohlcv["adj_close"].notna().any()
        else "close"
    )
    return _round(ohlcv.iloc[-1][col])


def _price_frame(symbol: str) -> Optional[pd.DataFrame]:
    try:
        ohlcv = load_ohlcv(symbol)
    except Exception:
        return None
    if ohlcv is None or ohlcv.empty:
        return None
    px = ohlcv.copy()
    px["date"] = pd.to_datetime(px["date"])
    px = px.sort_values("date")
    col = (
        "adj_close"
        if "adj_close" in px.columns and px["adj_close"].notna().any()
        else "close"
    )
    px["price"] = px[col].astype(float)
    return px[["date", "price"]]


def avg_abs_move_1d(
    symbol: str,
    *,
    before: Any = None,
    lookback: int = AVG_MOVE_LOOKBACK,
) -> tuple[Optional[float], int]:
    """Mean |ret_1d| over past earnings reports (optionally before a datetime)."""
    try:
        hist = load_earnings_events(symbol)
    except Exception:
        return None, 0
    if hist is None or hist.empty:
        return None, 0
    hist = hist.dropna(subset=["report_datetime"]).sort_values("report_datetime")
    before_ts = pd.to_datetime(before, errors="coerce") if before is not None else None
    if before_ts is not None and not pd.isna(before_ts):
        hist = hist[hist["report_datetime"] < before_ts]
    hist = hist.tail(lookback)
    if hist.empty:
        return None, 0

    prices = _price_frame(symbol)
    if prices is None or prices.empty:
        return None, 0

    moves: list[float] = []
    for _, row in hist.iterrows():
        rets = _forward_returns(prices, row["report_datetime"])
        r1 = rets.get("ret_1d")
        if r1 is not None:
            moves.append(abs(float(r1)))
    if not moves:
        return None, 0
    return _round(float(np.mean(moves)), 6), len(moves)


def fetch_and_cache_analysis(symbol: str, *, force: bool = False) -> dict[str, Any]:
    """Return cached Yahoo analysis or refresh from yfinance."""
    symbol = symbol.upper()
    if not force:
        cached = load_earnings_analysis_snapshot(symbol)
        if cached and cached.get("fetched_at"):
            fetched = cached["fetched_at"]
            if isinstance(fetched, str):
                fetched = datetime.fromisoformat(fetched)
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - fetched <= ANALYSIS_TTL:
                return cached.get("payload") or {}

    from finance_app.ingest.prices_yfinance import fetch_yfinance_earnings_analysis

    try:
        payload = fetch_yfinance_earnings_analysis(symbol)
    except Exception:
        # Keep stale cache if present
        cached = load_earnings_analysis_snapshot(symbol)
        return (cached or {}).get("payload") or {}

    upsert_earnings_analysis_snapshot(symbol, payload)
    return payload


def refresh_analysis_batch(symbols: list[str], *, force: bool = False) -> None:
    tickers = [s.upper() for s in symbols[:15] if s]
    if not tickers:
        return

    def _one(sym: str) -> None:
        try:
            fetch_and_cache_analysis(sym, force=force)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS) as pool:
        futs = [pool.submit(_one, s) for s in tickers]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception:
                continue


def analysis_fields(symbol: str) -> dict[str, Optional[float]]:
    payload = fetch_and_cache_analysis(symbol, force=False)
    rev = payload.get("revenue_0q") or {}
    eps_rev = payload.get("eps_revisions_0q") or {}
    eps_trend = payload.get("eps_trend_0q") or {}
    eps_est = payload.get("earnings_0q") or {}

    current = _round(eps_trend.get("current"))
    ago30 = _round(eps_trend.get("30daysAgo") or eps_trend.get("30DaysAgo"))
    delta = None
    if current is not None and ago30 is not None:
        delta = _round(current - ago30)

    up30 = _round(eps_rev.get("upLast30days") or eps_rev.get("upLast30Days"), 0)
    down30 = _round(
        eps_rev.get("downLast30days") or eps_rev.get("downLast30Days"), 0
    )
    rev_net = None
    if up30 is not None or down30 is not None:
        rev_net = _round((up30 or 0) - (down30 or 0), 0)

    return {
        "revenue_estimate": _round(rev.get("avg")),
        "revenue_yoy": _round(rev.get("growth")),
        "eps_estimate_avg": _round(eps_est.get("avg")),
        "eps_revisions_up_30d": up30,
        "eps_revisions_down_30d": down30,
        "eps_revision_net_30d": rev_net,
        "eps_trend_delta_30d": delta,
    }


def options_context_cached(symbol: str) -> dict[str, Optional[float]]:
    """ATM IV / IV rank / expected move / avg IV crush from local caches only."""
    from finance_app.metrics.options import compute_iv_rank_percentile

    out: dict[str, Optional[float]] = {
        "atm_iv": None,
        "iv_rank_1y": None,
        "expected_move": None,
        "expected_move_pct": None,
        "avg_iv_crush": None,
    }
    symbol = symbol.upper()

    try:
        iv = load_options_iv_snapshots(symbol)
    except Exception:
        iv = pd.DataFrame()
    if iv is not None and not iv.empty:
        iv = iv.dropna(subset=["atm_iv"]).sort_values("as_of_date")
        if not iv.empty:
            # Prefer nearest-DTE snapshot on the latest as_of_date
            latest_date = str(iv.iloc[-1]["as_of_date"])[:10]
            day = iv[iv["as_of_date"].astype(str).str[:10] == latest_date]
            if "dte" in day.columns and day["dte"].notna().any():
                day = day.sort_values("dte")
            atm = _round(day.iloc[0]["atm_iv"])
            out["atm_iv"] = atm
            rank = compute_iv_rank_percentile(symbol, atm)
            out["iv_rank_1y"] = _round(rank.get("iv_rank_1y"), 4)

    # Expected move from freshest chain cache (any expiration)
    try:
        cached = get_latest_options_chain_cache(symbol)
    except Exception:
        cached = None
    if cached and cached.get("payload"):
        summary = (cached["payload"] or {}).get("summary") or {}
        out["expected_move"] = _round(summary.get("expected_move"))
        out["expected_move_pct"] = _round(summary.get("expected_move_pct"), 4)
        if out["atm_iv"] is None:
            iv_ctx = (cached["payload"] or {}).get("iv_context") or {}
            out["atm_iv"] = _round(iv_ctx.get("atm_iv") or summary.get("atm_iv"))
            if out["iv_rank_1y"] is None:
                out["iv_rank_1y"] = _round(iv_ctx.get("iv_rank_1y"), 4)

    # Avg historical IV crush when snapshot history exists
    try:
        from finance_app.metrics.options import earnings_crush_history

        crush_rows = earnings_crush_history(symbol, limit=8)
        crushes = [
            float(r["iv_crush"])
            for r in crush_rows
            if r.get("iv_crush") is not None
        ]
        if crushes:
            out["avg_iv_crush"] = _round(float(np.mean(crushes)), 4)
    except Exception:
        pass

    return out


def enrich_event(row: dict[str, Any]) -> dict[str, Any]:
    """Attach all enrichment fields to one calendar event dict."""
    symbol = str(row.get("symbol") or "").upper()
    report = row.get("report_datetime")
    out = dict(row)
    out["session"] = earnings_session(report)
    out["last_surprise_pct"] = last_surprise_pct(symbol, report)
    out["spot"] = spot_price(symbol)
    avg_move, n = avg_abs_move_1d(symbol, before=report)
    out["avg_abs_move_1d"] = avg_move
    out["avg_move_n"] = n

    try:
        out.update(analysis_fields(symbol))
    except Exception:
        out.update(
            {
                "revenue_estimate": None,
                "revenue_yoy": None,
                "eps_estimate_avg": None,
                "eps_revisions_up_30d": None,
                "eps_revisions_down_30d": None,
                "eps_revision_net_30d": None,
                "eps_trend_delta_30d": None,
            }
        )

    # Prefer analysis EPS estimate when event estimate is missing
    if out.get("eps_estimate") is None and out.get("eps_estimate_avg") is not None:
        out["eps_estimate"] = out["eps_estimate_avg"]

    try:
        out.update(options_context_cached(symbol))
    except Exception:
        out.update(
            {
                "atm_iv": None,
                "iv_rank_1y": None,
                "expected_move": None,
                "expected_move_pct": None,
                "avg_iv_crush": None,
            }
        )
    return out
