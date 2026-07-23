from __future__ import annotations

from typing import Any, Optional

from finance_app.config import get_settings
from finance_app.db import load_short_interest, load_tiingo_context, upsert_tiingo_context
from finance_app.ingest import get_or_fetch_ohlcv
from finance_app.ingest.fred import DEFAULT_SERIES, get_or_fetch_macro, ingest_default_macro
from finance_app.ingest.prices_tiingo import (
    fetch_tiingo_meta,
    fetch_tiingo_news,
    tiingo_configured,
)
from finance_app.ingest.prices_yfinance import fetch_yfinance_short_snapshot
from finance_app.ingest.short_interest import ingest_short_interest
from finance_app.metrics import (
    compute_fundamental_ratios,
    compute_price_metrics,
    compute_technicals,
    compute_valuation_history,
    rolling_metrics_series,
)

TIINGO_CONTEXT_TTL_HOURS = 12


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
    price_primary: Optional[str] = None,
) -> dict[str, Any]:
    settings = get_settings()
    benchmark = (benchmark or settings.default_benchmark).upper()
    symbol = symbol.upper()
    primary = price_primary

    ohlcv = get_or_fetch_ohlcv(
        symbol,
        start=start,
        end=end,
        force_refresh=force_refresh,
        price_primary=primary,
    )
    if ohlcv.empty:
        return {"symbol": symbol, "error": "No price data available", "metrics": {}}

    bench = get_or_fetch_ohlcv(
        benchmark,
        start=start,
        end=end,
        force_refresh=force_refresh,
        price_primary=primary,
    )
    rf = latest_risk_free_annual()
    metrics = compute_price_metrics(ohlcv, benchmark_ohlcv=bench, risk_free_annual=rf)
    metrics["benchmark"] = benchmark
    metrics["source"] = ohlcv["source"].iloc[-1] if "source" in ohlcv.columns else None

    return {
        "symbol": symbol,
        "metrics": metrics,
        "disclaimer": (
            "Price data uses PRICE_PRIMARY (tiingo|yfinance), then Stooq fallback. "
            "Not for live trading decisions."
        ),
    }


def symbol_tiingo_context(
    symbol: str,
    *,
    news_limit: int = 8,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Cached Tiingo meta + news for a symbol (empty when key unset)."""
    from datetime import datetime, timedelta, timezone

    symbol = symbol.upper()
    if not tiingo_configured():
        return {
            "symbol": symbol,
            "configured": False,
            "meta": None,
            "news": [],
            "source": None,
        }

    if not force_refresh:
        cached = load_tiingo_context(symbol)
        if cached and cached.get("fetched_at"):
            try:
                fetched = datetime.fromisoformat(str(cached["fetched_at"]))
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - fetched < timedelta(
                    hours=TIINGO_CONTEXT_TTL_HOURS
                ):
                    payload = cached.get("payload") or {}
                    return {
                        "symbol": symbol,
                        "configured": True,
                        "meta": payload.get("meta"),
                        "news": payload.get("news") or [],
                        "source": "tiingo",
                        "freshness": "cached",
                    }
            except (TypeError, ValueError):
                pass

    meta = fetch_tiingo_meta(symbol)
    news = fetch_tiingo_news(symbol, limit=news_limit)
    payload = {"meta": meta, "news": news}
    try:
        upsert_tiingo_context(symbol, payload)
    except Exception:
        pass
    return {
        "symbol": symbol,
        "configured": True,
        "meta": meta,
        "news": news,
        "source": "tiingo",
        "freshness": "live",
    }


def symbol_technicals(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
    price_primary: Optional[str] = None,
) -> dict[str, Any]:
    ohlcv = get_or_fetch_ohlcv(
        symbol,
        start=start,
        end=end,
        force_refresh=force_refresh,
        price_primary=price_primary,
    )
    if ohlcv.empty:
        return {"symbol": symbol.upper(), "error": "No price data available"}
    tech = compute_technicals(ohlcv)
    return {"symbol": symbol.upper(), **tech}


def symbol_history(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
    price_primary: Optional[str] = None,
) -> dict[str, Any]:
    ohlcv = get_or_fetch_ohlcv(
        symbol,
        start=start,
        end=end,
        force_refresh=force_refresh,
        price_primary=price_primary,
    )
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
    price_primary: Optional[str] = None,
) -> dict[str, Any]:
    ohlcv = get_or_fetch_ohlcv(
        symbol,
        start=start,
        end=end,
        force_refresh=force_refresh,
        price_primary=price_primary,
    )
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
    earnings_primary: Optional[str] = None,
) -> dict[str, Any]:
    """Ensure data is cached and refresh earnings dates on every ticker load."""
    from finance_app.metrics.valuation_history import INDEX_BENCHMARKS

    get_or_fetch_ohlcv(symbol, start=start, end=end, force_refresh=force_refresh)
    # Keep index proxies cached so post-earnings benchmark returns can be computed.
    for bench in INDEX_BENCHMARKS:
        if bench == symbol.upper():
            continue
        try:
            get_or_fetch_ohlcv(bench)
        except Exception:
            pass
    return compute_valuation_history(
        symbol,
        start=start,
        end=end,
        refresh=force_refresh,
        refresh_earnings=True,
        earnings_primary=earnings_primary,
    )


def refresh_symbol_earnings(
    symbol: str,
    *,
    earnings_primary: Optional[str] = None,
) -> dict[str, Any]:
    """Fetch earnings dates/EPS into earnings_events (FMP or yfinance)."""
    from finance_app.db import upsert_earnings_events
    from finance_app.ingest.earnings import (
        earnings_frame_to_rows,
        fetch_earnings_events_with_fallback,
    )

    symbol = symbol.upper()
    try:
        fetched, source = fetch_earnings_events_with_fallback(
            symbol, earnings_primary=earnings_primary
        )
    except Exception as exc:
        return {"symbol": symbol, "upserted": 0, "source": None, "error": str(exc)}
    if fetched is None or fetched.empty:
        return {"symbol": symbol, "upserted": 0, "source": source}

    rows = earnings_frame_to_rows(fetched)
    n = upsert_earnings_events(symbol, rows)
    return {"symbol": symbol, "upserted": n, "source": source}


def earnings_calendar_payload(
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    symbols: Optional[list[str]] = None,
    refresh: bool = False,
    earnings_primary: Optional[str] = None,
) -> dict[str, Any]:
    """Upcoming/past earnings events for a date window, with trader context."""
    from datetime import datetime, timedelta, timezone

    import pandas as pd

    from finance_app.config import get_settings
    from finance_app.db import load_earnings_events_range
    from finance_app.ingest.earnings import effective_earnings_primary
    from finance_app.metrics.earnings_calendar import (
        enrich_event,
        refresh_analysis_batch,
    )
    from finance_app.metrics.option_strategies import DEFAULT_SCAN_SYMBOLS

    now = datetime.now(timezone.utc)
    if not start:
        start = now.strftime("%Y-%m-%d")
    if not end:
        end = (now + timedelta(days=45)).strftime("%Y-%m-%d")

    primary = effective_earnings_primary(earnings_primary)
    tickers = [s.upper() for s in (symbols or DEFAULT_SCAN_SYMBOLS)][:15]
    sources_used: list[str] = []
    if refresh:
        for sym in tickers:
            try:
                result = refresh_symbol_earnings(sym, earnings_primary=primary)
                if result.get("source"):
                    sources_used.append(str(result["source"]))
            except Exception:
                continue
        # Warm Yahoo analysis snapshots (TTL-cached; parallel) — best-effort
        try:
            refresh_analysis_batch(tickers, force=True)
        except Exception:
            pass
    else:
        # Ensure we have at least cached rows; light refresh if empty for a ticker
        for sym in tickers:
            try:
                existing = load_earnings_events_range(
                    start=start, end=end + "T23:59:59", symbols=[sym]
                )
                if existing is None or existing.empty:
                    result = refresh_symbol_earnings(sym, earnings_primary=primary)
                    if result.get("source"):
                        sources_used.append(str(result["source"]))
            except Exception:
                continue

    df = load_earnings_events_range(start=start, end=end + "T23:59:59", symbols=tickers)
    # Soft-warm analysis from cache / TTL without blocking on missing data
    try:
        refresh_analysis_batch(tickers, force=False)
    except Exception:
        pass

    events: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        report = r["report_datetime"]
        if hasattr(report, "isoformat"):
            report_s = report.isoformat()
        else:
            report_s = str(report)
        days = None
        try:
            ts = pd.to_datetime(report, errors="coerce")
            if not pd.isna(ts):
                days = (ts.date() - now.date()).days
        except Exception:
            days = None
        base = {
            "symbol": str(r["symbol"]).upper(),
            "report_datetime": report_s,
            "reported_eps": _f(r.get("reported_eps")),
            "eps_estimate": _f(r.get("eps_estimate")),
            "surprise_pct": _f(r.get("surprise_pct")),
            "days_to_earnings": days,
        }
        try:
            events.append(enrich_event(base))
        except Exception:
            events.append(base)

    source_label = primary
    if sources_used:
        # Majority source from this refresh
        fmp_n = sum(1 for s in sources_used if s == "fmp")
        yf_n = sum(1 for s in sources_used if s == "yfinance")
        if fmp_n or yf_n:
            source_label = "fmp" if fmp_n >= yf_n else "yfinance"

    return {
        "from": start,
        "to": end,
        "symbols": tickers,
        "events": events,
        "earnings_primary": primary,
        "source": source_label,
        "fmp_configured": get_settings().fmp_configured,
        "disclaimer": (
            "Earnings dates and EPS prefer Financial Modeling Prep when "
            "EARNINGS_PRIMARY=fmp (toggleable to Yahoo). Times may be estimates. "
            "Post-print moves use local price history (Tiingo/Yahoo OHLCV). "
            "Options IV / expected move use cached snapshots when available. "
            "Analysis revision chips remain Yahoo best-effort."
        ),
    }


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
