"""Historical valuation series: PE, PB, PS, market cap from OHLCV + EDGAR."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from finance_app.db import (
    load_earnings_events,
    load_fundamentals,
    load_ohlcv,
    upsert_earnings_events,
)
from finance_app.ingest.edgar import ingest_fundamentals
from finance_app.ingest.prices_yfinance import fetch_yfinance_earnings_events

FILING_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}

# Index proxies used for post-earnings benchmark returns:
# SPY = S&P 500, DIA = Dow Jones Industrial Average, QQQ = Nasdaq-100.
INDEX_BENCHMARKS = ("SPY", "DIA", "QQQ")


def compute_valuation_history(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    refresh: bool = False,
    refresh_earnings: bool = False,
) -> dict[str, Any]:
    """
    Build daily PE / PB / PS / market-cap series by joining prices to
    as-of EDGAR fundamentals (TTM EPS & revenue when quarterly data exists).
    """
    ticker = ticker.upper()
    existing = load_fundamentals(ticker)
    data_refreshed = refresh or existing.empty
    if refresh_earnings or data_refreshed:
        try:
            ingest_fundamentals(ticker)
        except Exception as exc:
            return {
                "symbol": ticker,
                "error": str(exc),
                "summary": {},
                "series": [],
                "earnings": [],
            }

    ohlcv = load_ohlcv(ticker, start=start, end=end)
    if ohlcv.empty:
        # Try full history then filter — caller may not have ingested prices yet
        ohlcv = load_ohlcv(ticker)
        if ohlcv.empty:
            return {
                "symbol": ticker,
                "error": "No price data available",
                "summary": {},
                "series": [],
                "earnings": [],
            }
        if start:
            ohlcv = ohlcv[ohlcv["date"] >= pd.to_datetime(start)]
        if end:
            ohlcv = ohlcv[ohlcv["date"] <= pd.to_datetime(end)]

    fund = load_fundamentals(
        ticker, concepts=["EPS", "Equity", "Revenue", "Shares", "NetIncome"]
    )
    if fund.empty:
        return {
            "symbol": ticker,
            "error": "No fundamental data available",
            "summary": {},
            "series": [],
            "earnings": [],
        }

    report_events = load_earnings_events(ticker)
    if data_refreshed or refresh_earnings:
        try:
            fetched_events = fetch_yfinance_earnings_events(ticker)
            rows = [
                (
                    r["report_datetime"].isoformat(),
                    _round(r.get("reported_eps")),
                    _round(r.get("eps_estimate")),
                    _round(r.get("surprise_pct")),
                )
                for _, r in fetched_events.iterrows()
            ]
            upsert_earnings_events(ticker, rows)
            report_events = load_earnings_events(ticker)
        except Exception:
            # Earnings returns remain unavailable rather than using a false date.
            pass

    asof = _build_asof_fundamentals(fund)

    prices = ohlcv.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values("date")
    price_col = (
        "adj_close"
        if "adj_close" in prices.columns and prices["adj_close"].notna().any()
        else "close"
    )
    prices["price"] = prices[price_col].astype(float)

    # Use full price history for post-earnings returns (needs days after range end).
    ohlcv_full = load_ohlcv(ticker)
    if ohlcv_full.empty:
        ohlcv_full = ohlcv
    prices_full = ohlcv_full.copy()
    prices_full["date"] = pd.to_datetime(prices_full["date"])
    prices_full = prices_full.sort_values("date")
    full_col = (
        "adj_close"
        if "adj_close" in prices_full.columns and prices_full["adj_close"].notna().any()
        else "close"
    )
    prices_full["price"] = prices_full[full_col].astype(float)

    benchmark_prices = _benchmark_price_frames(ticker)

    earnings = _earnings_series(
        fund,
        prices=prices_full[["date", "price"]],
        report_events=report_events,
        start=start,
        end=end,
        benchmark_prices=benchmark_prices,
    )

    if asof.empty:
        return {
            "symbol": ticker,
            "error": "Could not build fundamental as-of series",
            "summary": {},
            "series": [],
            "earnings": earnings,
        }

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
    # Cap absurd PE from tiny EPS near zero for chart stability (keep raw otherwise)
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

    if start:
        merged = merged[merged["date"] >= pd.to_datetime(start)]
    if end:
        merged = merged[merged["date"] <= pd.to_datetime(end)]

    series_rows: list[dict[str, Any]] = []
    for _, r in merged.iterrows():
        series_rows.append(
            {
                "date": r["date"].strftime("%Y-%m-%d"),
                "price": _round(r["price"]),
                "pe": _round(r["pe"]),
                "pb": _round(r["pb"]),
                "ps": _round(r["ps"]),
                "market_cap": _round(r["market_cap"]),
            }
        )

    summary = _summary_stats(merged)
    return {
        "symbol": ticker,
        "summary": summary,
        "series": series_rows,
        "earnings": earnings,
        "benchmarks": list(benchmark_prices.keys()),
        "disclaimer": (
            "Valuation uses daily prices joined as-of to SEC EDGAR facts. "
            "TTM EPS/revenue sum the last four quarterly reports when available; "
            "otherwise annual 10-K figures. Market cap uses diluted shares when "
            "reported, else NetIncome/EPS."
        ),
    }


def _concept_frame(fund: pd.DataFrame, concept: str) -> pd.DataFrame:
    g = fund[fund["concept"] == concept].copy()
    cols = ["end_date", "value", "form", "fy", "fp", "filed"]
    empty = pd.DataFrame(columns=cols)
    if g.empty:
        return empty
    g["end_date"] = pd.to_datetime(g["end_date"])
    if "filed" not in g.columns:
        g["filed"] = None
    # Prefer standard filings
    g = g[g["form"].isin(FILING_FORMS) | g["form"].isna()]
    if g.empty:
        g = fund[fund["concept"] == concept].copy()
        g["end_date"] = pd.to_datetime(g["end_date"])
        if "filed" not in g.columns:
            g["filed"] = None
    g = g.sort_values(["end_date", "form"])
    g = g.drop_duplicates(subset=["end_date"], keep="last")
    for c in cols:
        if c not in g.columns:
            g[c] = None
    return g[cols].reset_index(drop=True)


def _is_quarterly(row: pd.Series) -> bool:
    form = str(row.get("form") or "")
    fp = str(row.get("fp") or "")
    if form.startswith("10-Q"):
        return True
    if fp in {"Q1", "Q2", "Q3", "Q4"}:
        return True
    return False


def _is_annual(row: pd.Series) -> bool:
    form = str(row.get("form") or "")
    fp = str(row.get("fp") or "")
    if form.startswith("10-K"):
        return True
    if fp in {"FY", "Q4"} and form.startswith("10-K"):
        return True
    if fp == "FY":
        return True
    return False


def _ttm_from_flow(flow: pd.DataFrame) -> pd.DataFrame:
    """
    For each period end, TTM = sum of last 4 quarterly values if available,
    else the latest annual value as of that date.
    """
    if flow.empty:
        return pd.DataFrame(columns=["end_date", "ttm"])

    flow = flow.sort_values("end_date").reset_index(drop=True)
    quarterly = flow[flow.apply(_is_quarterly, axis=1)].copy()
    annual = flow[flow.apply(_is_annual, axis=1)].copy()
    if quarterly.empty and annual.empty:
        annual = flow.copy()

    rows = []
    for end in flow["end_date"].unique():
        end = pd.Timestamp(end)
        ttm = None
        q = quarterly[quarterly["end_date"] <= end].tail(4)
        if len(q) >= 4:
            ttm = float(q["value"].sum())
        else:
            a = annual[annual["end_date"] <= end]
            if not a.empty:
                ttm = float(a.iloc[-1]["value"])
        rows.append({"end_date": end, "ttm": ttm})

    return pd.DataFrame(rows).drop_duplicates(subset=["end_date"], keep="last")


def _point_in_time(frame: pd.DataFrame, col_name: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["end_date", col_name])
    f = frame.sort_values("end_date")[["end_date", "value"]].copy()
    f = f.rename(columns={"value": col_name})
    return f.drop_duplicates(subset=["end_date"], keep="last")


def _build_asof_fundamentals(fund: pd.DataFrame) -> pd.DataFrame:
    eps = _concept_frame(fund, "EPS")
    revenue = _concept_frame(fund, "Revenue")
    equity = _concept_frame(fund, "Equity")
    shares = _concept_frame(fund, "Shares")
    net_income = _concept_frame(fund, "NetIncome")

    ttm_eps = _ttm_from_flow(eps).rename(columns={"ttm": "ttm_eps"})
    ttm_rev = _ttm_from_flow(revenue).rename(columns={"ttm": "ttm_revenue"})
    eq = _point_in_time(equity, "equity")
    sh = _point_in_time(shares, "shares")

    # Shares approx from NI/EPS at matching period ends
    shares_approx = pd.DataFrame(columns=["end_date", "shares_approx"])
    if not net_income.empty and not eps.empty:
        ni = net_income.rename(columns={"value": "ni"})[["end_date", "ni"]]
        ep = eps.rename(columns={"value": "eps"})[["end_date", "eps"]]
        joined = pd.merge(ni, ep, on="end_date", how="inner")
        joined = joined[joined["eps"] != 0]
        joined["shares_approx"] = joined["ni"] / joined["eps"]
        shares_approx = joined[["end_date", "shares_approx"]]

    dates = sorted(
        set(ttm_eps["end_date"].tolist())
        | set(ttm_rev["end_date"].tolist())
        | set(eq["end_date"].tolist())
        | set(sh["end_date"].tolist())
        | set(shares_approx["end_date"].tolist())
    )
    if not dates:
        return pd.DataFrame()

    base = pd.DataFrame({"end_date": pd.to_datetime(dates)}).sort_values("end_date")
    for frame in (ttm_eps, ttm_rev, eq, sh, shares_approx):
        if frame.empty:
            continue
        base = pd.merge_asof(
            base,
            frame.sort_values("end_date"),
            on="end_date",
            direction="backward",
        )

    for col in ("ttm_eps", "ttm_revenue", "equity", "shares", "shares_approx"):
        if col not in base.columns:
            base[col] = np.nan

    return base


def _forward_returns(
    prices: pd.DataFrame,
    event_date: pd.Timestamp,
) -> dict[str, Optional[float]]:
    """
    Return from last close before event_date to the Nth trading day after that
    baseline close. Horizons: 1d, 3d, 5d, 1m (21 trading days).
    """
    empty = {"ret_1d": None, "ret_3d": None, "ret_5d": None, "ret_1m": None}
    if prices is None or prices.empty or pd.isna(event_date):
        return empty
    px = prices.sort_values("date").reset_index(drop=True).copy()
    px["date"] = pd.to_datetime(px["date"]).dt.normalize()
    event_date = pd.Timestamp(event_date)
    event_day = event_date.normalize()

    # Yahoo timestamps are New York local time. Before-market reports use the
    # previous close; reports at noon or later use that day's close as baseline.
    if event_date.hour < 12:
        before = px[px["date"] < event_day]
    else:
        before = px[px["date"] <= event_day]
    if before.empty:
        return empty
    base_idx = int(before.index[-1])
    base_price = float(before.iloc[-1]["price"])
    if base_price == 0 or np.isnan(base_price):
        return empty

    def ret_at(n: int) -> Optional[float]:
        j = base_idx + n
        if j >= len(px):
            return None
        p = float(px.iloc[j]["price"])
        if np.isnan(p):
            return None
        return _round((p / base_price) - 1.0)

    return {
        "ret_1d": ret_at(1),
        "ret_3d": ret_at(3),
        "ret_5d": ret_at(5),
        "ret_1m": ret_at(21),
    }


def _benchmark_price_frames(ticker: str) -> dict[str, pd.DataFrame]:
    """
    Daily close series for each index proxy (SPY/DIA/QQQ) available locally.

    Reads only the local cache — the valuation history service prefetches
    these, so this avoids network calls inside metric computation.
    """
    frames: dict[str, pd.DataFrame] = {}
    for sym in INDEX_BENCHMARKS:
        if ticker.upper() == sym:
            continue
        try:
            bench = load_ohlcv(sym)
        except Exception:
            continue
        if bench is None or bench.empty:
            continue
        bench = bench.copy()
        bench["date"] = pd.to_datetime(bench["date"])
        bench = bench.sort_values("date")
        col = (
            "adj_close"
            if "adj_close" in bench.columns and bench["adj_close"].notna().any()
            else "close"
        )
        bench["price"] = bench[col].astype(float)
        frames[sym] = bench[["date", "price"]]
    return frames


def _earnings_series(
    fund: pd.DataFrame,
    prices: Optional[pd.DataFrame] = None,
    report_events: Optional[pd.DataFrame] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    benchmark_prices: Optional[dict[str, pd.DataFrame]] = None,
) -> list[dict[str, Any]]:
    eps = _concept_frame(fund, "EPS")
    if eps.empty:
        return []
    if start:
        eps = eps[eps["end_date"] >= pd.to_datetime(start)]
    if end:
        eps = eps[eps["end_date"] <= pd.to_datetime(end)]
    reports = (
        report_events.dropna(subset=["report_datetime"])
        .sort_values("report_datetime")
        .reset_index(drop=True)
        if report_events is not None and not report_events.empty
        else pd.DataFrame()
    )
    out = []
    for _, r in eps.iterrows():
        filed_raw = r.get("filed")
        filed_str = None
        if pd.notna(filed_raw) and str(filed_raw).strip():
            try:
                filed_str = pd.to_datetime(filed_raw).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                filed_str = None

        period_end = pd.Timestamp(r["end_date"])
        report_datetime = None
        if not reports.empty:
            candidates = reports[
                (reports["report_datetime"] > period_end)
                & (reports["report_datetime"] <= period_end + pd.Timedelta(days=120))
            ]
            if not candidates.empty:
                report_datetime = pd.Timestamp(candidates.iloc[0]["report_datetime"])

        rets = (
            _forward_returns(prices, report_datetime)
            if prices is not None and report_datetime is not None
            else {
            "ret_1d": None,
            "ret_3d": None,
            "ret_5d": None,
            "ret_1m": None,
            }
        )

        index_returns: dict[str, dict[str, Optional[float]]] = {}
        if benchmark_prices and report_datetime is not None:
            for sym, frame in benchmark_prices.items():
                index_returns[sym] = _forward_returns(frame, report_datetime)

        out.append(
            {
                "date": r["end_date"].strftime("%Y-%m-%d"),
                "eps": _round(float(r["value"])),
                "form": r["form"],
                "fy": int(r["fy"]) if pd.notna(r.get("fy")) else None,
                "fp": r["fp"] if pd.notna(r.get("fp")) else None,
                "filed": filed_str,
                "report_datetime": (
                    report_datetime.isoformat() if report_datetime is not None else None
                ),
                "report_date": (
                    report_datetime.strftime("%Y-%m-%d")
                    if report_datetime is not None
                    else None
                ),
                "anchor": "report_date" if report_datetime is not None else None,
                **rets,
                "index_returns": index_returns or None,
            }
        )
    return out


def _summary_stats(merged: pd.DataFrame) -> dict[str, Any]:
    def stats(col: str) -> dict[str, Optional[float]]:
        s = merged[col].replace([np.inf, -np.inf], np.nan).dropna()
        # Drop extreme PE outliers (>|500|) from avg/median for usability
        if col == "pe":
            s = s[(s > -500) & (s < 500)]
        if s.empty:
            return {"avg": None, "median": None, "latest": None, "count": 0}
        return {
            "avg": _round(float(s.mean())),
            "median": _round(float(s.median())),
            "latest": _round(float(s.iloc[-1])),
            "count": int(len(s)),
        }

    return {
        "pe": stats("pe"),
        "pb": stats("pb"),
        "ps": stats("ps"),
        "market_cap": stats("market_cap"),
        "bars": int(len(merged)),
        "start": merged["date"].min().strftime("%Y-%m-%d") if len(merged) else None,
        "end": merged["date"].max().strftime("%Y-%m-%d") if len(merged) else None,
    }


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
