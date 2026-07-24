from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from finance_app.config import get_settings, normalize_price_primary
from finance_app.db import get_meta, get_meta_updated_at, load_ohlcv, upsert_ohlcv
from finance_app.ingest.finnhub import fetch_ohlcv_finnhub, finnhub_configured
from finance_app.ingest.prices_stooq import fetch_stooq_ohlcv
from finance_app.ingest.prices_tiingo import fetch_tiingo_ohlcv, tiingo_configured
from finance_app.ingest.prices_yfinance import fetch_yfinance_ohlcv

EMPTY_OHLCV = pd.DataFrame(
    columns=["date", "open", "high", "low", "close", "adj_close", "volume"]
)


def _cache_fresh(symbol: str) -> bool:
    settings = get_settings()
    updated = get_meta_updated_at(f"ohlcv:{symbol.upper()}")
    if not updated:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - updated
    return age < timedelta(hours=settings.price_cache_hours)


def _source_coverage_thin(cached: pd.DataFrame, source: str) -> bool:
    """True when few rows are tagged with the preferred source (partial write)."""
    if cached.empty or "source" not in cached.columns:
        return True
    n = int((cached["source"] == source).sum())
    if n == 0:
        return True
    return n < max(30, int(0.5 * len(cached)))


def _needs_primary_upgrade(
    symbol: str, cached: pd.DataFrame, primary: str
) -> bool:
    """
    Re-fetch when deploy/UI primary disagrees with cached source tags,
    or when a prior fetch only wrote a sparse slice (e.g. missing startDate).
    """
    if cached.empty:
        return False
    if primary == "tiingo":
        if not tiingo_configured():
            return False
        if "source" not in cached.columns:
            return get_meta(f"ohlcv:{symbol}") != "tiingo"
        return _source_coverage_thin(cached, "tiingo")
    if primary == "yfinance":
        if "source" not in cached.columns:
            return get_meta(f"ohlcv:{symbol}") != "yfinance"
        return _source_coverage_thin(cached, "yfinance")
    if primary == "finnhub":
        # Free Finnhub cannot serve candles unless FINNHUB_OHLCV is enabled.
        if not get_settings().finnhub_ohlcv_enabled:
            return False
        if "source" not in cached.columns:
            return get_meta(f"ohlcv:{symbol}") != "finnhub"
        return _source_coverage_thin(cached, "finnhub")
    return False


def get_or_fetch_ohlcv(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
    price_primary: Optional[str] = None,
) -> pd.DataFrame:
    """
    Return OHLCV from SQLite cache, refreshing from the configured primary
    provider (and fallbacks) when stale.
    """
    symbol = symbol.upper()
    primary = normalize_price_primary(
        price_primary, default=get_settings().price_primary_normalized
    )
    cached = load_ohlcv(symbol)  # full series for coverage checks

    coverage_gap = False
    if start and not cached.empty:
        if pd.to_datetime(cached["date"].min()) > pd.to_datetime(start):
            coverage_gap = True

    needs_fetch = (
        force_refresh
        or not _cache_fresh(symbol)
        or cached.empty
        or coverage_gap
        or _needs_primary_upgrade(symbol, cached, primary)
    )
    if needs_fetch:
        # Always pull full history from the provider so source tags rewrite the
        # whole series (range filters apply after cache load below).
        df, source = _fetch_with_fallback(
            symbol, start=None, end=None, primary=primary
        )
        if not df.empty:
            upsert_ohlcv(df, symbol, source=source)
            cached = load_ohlcv(symbol)

    if start or end:
        cached = load_ohlcv(symbol, start=start, end=end)
    return cached


def _fetch_with_fallback(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    primary: Optional[str] = None,
) -> tuple[pd.DataFrame, str]:
    """
    Fetch OHLCV preferring PRICE_PRIMARY (or override).
    finnhub: Finnhub → Tiingo → Stooq → yfinance  (Finnhub only when primary)
    tiingo: Tiingo → Stooq → yfinance
    yfinance: yfinance → Stooq → Tiingo
    """
    primary = normalize_price_primary(
        primary, default=get_settings().price_primary_normalized
    )

    def try_finnhub() -> Optional[tuple[pd.DataFrame, str]]:
        # Skip candle calls on free Finnhub (HTTP 403) unless opted in.
        if not get_settings().finnhub_ohlcv_enabled:
            return None
        if not finnhub_configured():
            return None
        try:
            df = fetch_ohlcv_finnhub(symbol, start=start, end=end)
            if not df.empty:
                return df, "finnhub"
        except Exception:
            pass
        return None

    def try_tiingo() -> Optional[tuple[pd.DataFrame, str]]:
        if not tiingo_configured():
            return None
        try:
            df = fetch_tiingo_ohlcv(symbol, start=start, end=end)
            if not df.empty:
                return df, "tiingo"
        except Exception:
            pass
        return None

    def try_stooq() -> Optional[tuple[pd.DataFrame, str]]:
        try:
            df = fetch_stooq_ohlcv(symbol, start=start, end=end)
            if not df.empty:
                return df, "stooq"
        except Exception:
            pass
        return None

    def try_yfinance() -> Optional[tuple[pd.DataFrame, str]]:
        try:
            df = fetch_yfinance_ohlcv(symbol, start=start, end=end)
            if not df.empty:
                return df, "yfinance"
        except Exception:
            pass
        return None

    if primary == "finnhub":
        order = (try_finnhub, try_tiingo, try_stooq, try_yfinance)
    elif primary == "yfinance":
        order = (try_yfinance, try_stooq, try_tiingo)
    else:
        order = (try_tiingo, try_stooq, try_yfinance)

    for attempt in order:
        hit = attempt()
        if hit is not None:
            return hit

    return EMPTY_OHLCV.copy(), "none"
