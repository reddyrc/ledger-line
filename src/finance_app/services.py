from __future__ import annotations

from typing import Any, Optional

from finance_app.config import get_settings
from finance_app.db import load_short_interest
from finance_app.ingest import get_or_fetch_ohlcv
from finance_app.ingest.fred import DEFAULT_SERIES, get_or_fetch_macro, ingest_default_macro
from finance_app.ingest.prices_yfinance import fetch_yfinance_short_snapshot
from finance_app.ingest.short_interest import ingest_short_interest
from finance_app.metrics import (
    compute_fundamental_ratios,
    compute_price_metrics,
    compute_technicals,
    compute_valuation_history,
    rolling_metrics_series,
)


def latest_risk_free_annual() -> float:
    """Use 3M Treasury (DGS3MO) from FRED, fall back to TB3MS, else 0."""
    for series_id in ("DGS3MO", "TB3MS"):
        df = get_or_fetch_macro(series_id)
        if df.empty:
            continue
        # FRED rates are percent (e.g. 5.25) → decimal
        return float(df.iloc[-1]["value"]) / 100.0
    return 0.0


def symbol_metrics(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    benchmark: Optional[str] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    benchmark = (benchmark or settings.default_benchmark).upper()
    symbol = symbol.upper()

    ohlcv = get_or_fetch_ohlcv(symbol, start=start, end=end, force_refresh=force_refresh)
    if ohlcv.empty:
        return {"symbol": symbol, "error": "No price data available", "metrics": {}}

    bench = get_or_fetch_ohlcv(benchmark, start=start, end=end, force_refresh=force_refresh)
    rf = latest_risk_free_annual()
    metrics = compute_price_metrics(ohlcv, benchmark_ohlcv=bench, risk_free_annual=rf)
    metrics["benchmark"] = benchmark
    metrics["source"] = ohlcv["source"].iloc[-1] if "source" in ohlcv.columns else None

    return {
        "symbol": symbol,
        "metrics": metrics,
        "disclaimer": (
            "Price data from free unofficial feeds (Yahoo via yfinance, Stooq fallback). "
            "Not for live trading decisions."
        ),
    }


def symbol_technicals(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    ohlcv = get_or_fetch_ohlcv(symbol, start=start, end=end, force_refresh=force_refresh)
    if ohlcv.empty:
        return {"symbol": symbol.upper(), "error": "No price data available"}
    tech = compute_technicals(ohlcv)
    return {"symbol": symbol.upper(), **tech}


def symbol_history(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    ohlcv = get_or_fetch_ohlcv(symbol, start=start, end=end, force_refresh=force_refresh)
    if ohlcv.empty:
        return {"symbol": symbol.upper(), "bars": []}
    rows = []
    for _, r in ohlcv.iterrows():
        rows.append(
            {
                "date": r["date"].strftime("%Y-%m-%d")
                if hasattr(r["date"], "strftime")
                else str(r["date"])[:10],
                "open": _f(r["open"]),
                "high": _f(r["high"]),
                "low": _f(r["low"]),
                "close": _f(r["close"]),
                "adj_close": _f(r["adj_close"]),
                "volume": _f(r["volume"]),
            }
        )
    return {"symbol": symbol.upper(), "bars": rows, "count": len(rows)}


def symbol_rolling(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    window: int = 63,
    force_refresh: bool = False,
) -> dict[str, Any]:
    ohlcv = get_or_fetch_ohlcv(symbol, start=start, end=end, force_refresh=force_refresh)
    if ohlcv.empty:
        return {"symbol": symbol.upper(), "series": []}
    return {
        "symbol": symbol.upper(),
        "window": window,
        "series": rolling_metrics_series(ohlcv, window=window),
    }


def macro_payload(
    series_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    df = get_or_fetch_macro(series_id, start=start, end=end, force_refresh=force_refresh)
    observations = []
    for _, r in df.iterrows():
        observations.append(
            {
                "date": r["date"].strftime("%Y-%m-%d")
                if hasattr(r["date"], "strftime")
                else str(r["date"])[:10],
                "value": float(r["value"]),
            }
        )
    return {
        "series_id": series_id,
        "description": DEFAULT_SERIES.get(series_id),
        "count": len(observations),
        "observations": observations,
    }


def bootstrap_macro() -> dict[str, int]:
    return ingest_default_macro()


def fundamentals_payload(ticker: str, refresh: bool = False) -> dict[str, Any]:
    # Ensure we have prices for market-cap / PE
    get_or_fetch_ohlcv(ticker)
    return compute_fundamental_ratios(ticker, refresh=refresh)


def valuation_history_payload(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Ensure data is cached and refresh earnings dates on every ticker load."""
    get_or_fetch_ohlcv(symbol, start=start, end=end, force_refresh=force_refresh)
    return compute_valuation_history(
        symbol,
        start=start,
        end=end,
        refresh=force_refresh,
        refresh_earnings=True,
    )


def short_interest_payload(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """FINRA biweekly short interest series + optional Yahoo enrichment."""
    symbol = symbol.upper()
    try:
        ingest_short_interest(
            symbol, start=start, end=end, force=force_refresh
        )
    except Exception as exc:
        cached = load_short_interest(symbol, start=start, end=end)
        if cached.empty:
            return {
                "symbol": symbol,
                "latest": None,
                "series": [],
                "yahoo": None,
                "error": str(exc),
                "disclaimer": (
                    "Short interest from FINRA Equity Short Interest (biweekly). "
                    "Exchange-listed coverage is most reliable from mid-2021 onward."
                ),
            }

    df = load_short_interest(symbol, start=start, end=end)
    series: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        series.append(
            {
                "date": r["settlement_date"].strftime("%Y-%m-%d")
                if hasattr(r["settlement_date"], "strftime")
                else str(r["settlement_date"])[:10],
                "shares_short": _f(r["shares_short"]),
                "shares_short_prior": _f(r["shares_short_prior"]),
                "change_pct": _f(r["change_pct"]),
                "avg_daily_volume": _f(r["avg_daily_volume"]),
                "days_to_cover": _f(r["days_to_cover"]),
            }
        )

    latest = None
    if series:
        last = series[-1]
        latest = {
            "settlement_date": last["date"],
            "shares_short": last["shares_short"],
            "shares_short_prior": last["shares_short_prior"],
            "change_pct": last["change_pct"],
            "avg_daily_volume": last["avg_daily_volume"],
            "days_to_cover": last["days_to_cover"],
            "source": "finra",
        }

    yahoo = None
    try:
        yahoo = fetch_yfinance_short_snapshot(symbol)
        if latest is not None and yahoo:
            if yahoo.get("short_pct_float") is not None:
                latest["short_pct_float"] = yahoo["short_pct_float"]
            if yahoo.get("short_ratio") is not None and latest.get("days_to_cover") is None:
                latest["days_to_cover"] = yahoo["short_ratio"]
    except Exception:
        yahoo = None

    return {
        "symbol": symbol,
        "latest": latest,
        "series": series,
        "yahoo": yahoo,
        "disclaimer": (
            "Short interest from FINRA Equity Short Interest (biweekly settlement). "
            "Short % of float is from Yahoo Finance when available. "
            "Exchange-listed FINRA coverage is most reliable from mid-2021 onward."
        ),
    }


def screen_payload(
    *,
    q: Optional[str] = None,
    sector: Optional[str] = None,
    pe_min: Optional[float] = None,
    pe_max: Optional[float] = None,
    pb_min: Optional[float] = None,
    pb_max: Optional[float] = None,
    ps_min: Optional[float] = None,
    ps_max: Optional[float] = None,
    roe_min: Optional[float] = None,
    roe_max: Optional[float] = None,
    market_cap_min: Optional[float] = None,
    market_cap_max: Optional[float] = None,
    momentum_3m_min: Optional[float] = None,
    momentum_3m_max: Optional[float] = None,
    momentum_12m_min: Optional[float] = None,
    momentum_12m_max: Optional[float] = None,
    vol_ann_min: Optional[float] = None,
    vol_ann_max: Optional[float] = None,
    max_drawdown_1y_min: Optional[float] = None,
    max_drawdown_1y_max: Optional[float] = None,
    sort: str = "momentum_12m",
    order: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    from finance_app.db import count_screen_snapshots, query_screen_snapshots

    filters = {
        "pe": (pe_min, pe_max),
        "pb": (pb_min, pb_max),
        "ps": (ps_min, ps_max),
        "roe": (roe_min, roe_max),
        "market_cap": (market_cap_min, market_cap_max),
        "momentum_3m": (momentum_3m_min, momentum_3m_max),
        "momentum_12m": (momentum_12m_min, momentum_12m_max),
        "vol_ann": (vol_ann_min, vol_ann_max),
        "max_drawdown_1y": (max_drawdown_1y_min, max_drawdown_1y_max),
    }
    # Drop unused filter keys
    filters = {
        k: v for k, v in filters.items() if v[0] is not None or v[1] is not None
    }
    rows, total = query_screen_snapshots(
        q=q,
        sector=sector,
        filters=filters,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return {
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "snapshot_count": count_screen_snapshots(),
        "sort": sort,
        "order": order,
    }


def screen_sectors_payload() -> dict[str, Any]:
    from finance_app.db import list_screen_sectors

    return {"sectors": list_screen_sectors()}


def screen_refresh_payload(
    *,
    limit: Optional[int] = None,
    offset: int = 0,
    sleep_s: float = 0.25,
    skip_fundamentals: bool = False,
) -> dict[str, Any]:
    from finance_app.ingest.screener import refresh_screener

    return refresh_screener(
        universe="sp500",
        limit=limit,
        offset=offset,
        sleep_s=sleep_s,
        skip_fundamentals=skip_fundamentals,
    )


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
