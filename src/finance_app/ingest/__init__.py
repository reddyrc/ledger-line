from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from finance_app.config import get_settings
from finance_app.db import get_meta_updated_at, load_ohlcv, upsert_ohlcv
from finance_app.ingest.prices_stooq import fetch_stooq_ohlcv
from finance_app.ingest.prices_yfinance import fetch_yfinance_ohlcv


def _cache_fresh(symbol: str) -> bool:
    settings = get_settings()
    updated = get_meta_updated_at(f"ohlcv:{symbol.upper()}")
    if not updated:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - updated
    return age < timedelta(hours=settings.price_cache_hours)


def get_or_fetch_ohlcv(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Return OHLCV from SQLite cache, refreshing from yfinance (Stooq fallback) when stale.
    """
    symbol = symbol.upper()
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
    )
    if needs_fetch:
        # Fetch full/extended history so subsequent range queries are served from cache
        fetch_start = start
        if coverage_gap or cached.empty:
            fetch_start = start  # may be None → yfinance period=max
        df, source = _fetch_with_fallback(symbol, start=fetch_start, end=None)
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
) -> tuple[pd.DataFrame, str]:
    try:
        df = fetch_yfinance_ohlcv(symbol, start=start, end=end)
        if not df.empty:
            return df, "yfinance"
    except Exception:
        pass

    df = fetch_stooq_ohlcv(symbol, start=start, end=end)
    return df, "stooq"
