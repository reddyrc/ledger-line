"""Tiingo EOD prices, ticker meta, and news ingest."""

from __future__ import annotations

from typing import Any, Optional

import httpx
import pandas as pd

from finance_app.config import get_settings

TIINGO_DAILY = "https://api.tiingo.com/tiingo/daily"
TIINGO_NEWS = "https://api.tiingo.com/tiingo/news"

EMPTY_OHLCV = pd.DataFrame(
    columns=["date", "open", "high", "low", "close", "adj_close", "volume"]
)


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Token {api_key}",
    }


def _api_key() -> str:
    return (get_settings().tiingo_api_key or "").strip()


def tiingo_configured() -> bool:
    return bool(_api_key())


# Tiingo returns only the latest bar when startDate is omitted.
_DEFAULT_OHLCV_START = "1970-01-01"


def fetch_tiingo_ohlcv(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Daily OHLCV from Tiingo EOD endpoint.
    Returns empty frame when key missing or request fails.
    """
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return EMPTY_OHLCV.copy()

    symbol = symbol.upper()
    params: dict[str, str] = {
        "format": "json",
        # Required for history — no startDate ⇒ single latest bar only.
        "startDate": (start or _DEFAULT_OHLCV_START)[:10],
    }
    if end:
        params["endDate"] = end[:10]

    url = f"{TIINGO_DAILY}/{symbol}/prices"
    try:
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.get(url, params=params, headers=_headers(key))
            if resp.status_code != 200:
                return EMPTY_OHLCV.copy()
            rows = resp.json()
    except (httpx.HTTPError, ValueError):
        return EMPTY_OHLCV.copy()

    if not isinstance(rows, list) or not rows:
        return EMPTY_OHLCV.copy()

    records = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        date_raw = r.get("date") or r.get("Date")
        if not date_raw:
            continue
        adj = r.get("adjClose", r.get("adj_close", r.get("close")))
        records.append(
            {
                "date": str(date_raw)[:10],
                "open": r.get("open"),
                "high": r.get("high"),
                "low": r.get("low"),
                "close": r.get("close"),
                "adj_close": adj if adj is not None else r.get("close"),
                "volume": r.get("volume"),
            }
        )
    if not records:
        return EMPTY_OHLCV.copy()

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    for col in ("open", "high", "low", "close", "adj_close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["date", "open", "high", "low", "close", "adj_close", "volume"]]


def fetch_tiingo_meta(
    symbol: str,
    *,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Ticker metadata: name, exchange, description, start/end dates."""
    empty: dict[str, Any] = {
        "ticker": symbol.upper(),
        "name": None,
        "exchange": None,
        "description": None,
        "start_date": None,
        "end_date": None,
    }
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return empty

    symbol = symbol.upper()
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            resp = client.get(
                f"{TIINGO_DAILY}/{symbol}",
                headers=_headers(key),
            )
            if resp.status_code != 200:
                return empty
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return empty

    if not isinstance(data, dict):
        return empty

    start = data.get("startDate")
    end = data.get("endDate")
    return {
        "ticker": data.get("ticker") or symbol,
        "name": data.get("name"),
        "exchange": data.get("exchangeCode") or data.get("exchange"),
        "description": data.get("description"),
        "start_date": str(start)[:10] if start else None,
        "end_date": str(end)[:10] if end else None,
    }


def fetch_tiingo_news(
    symbol: str,
    *,
    limit: int = 8,
    api_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Recent news articles tagged with the ticker."""
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return []

    symbol = symbol.upper()
    params = {
        "tickers": symbol,
        "limit": str(max(1, min(limit, 25))),
        "sortBy": "publishedDate",
    }
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            resp = client.get(TIINGO_NEWS, params=params, headers=_headers(key))
            if resp.status_code != 200:
                return []
            rows = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    if not isinstance(rows, list):
        return []

    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        if not isinstance(r, dict):
            continue
        published = r.get("publishedDate") or r.get("crawlDate")
        source = None
        src = r.get("source")
        if isinstance(src, str):
            source = src
        elif isinstance(r.get("tags"), list) and r["tags"]:
            source = str(r["tags"][0])
        out.append(
            {
                "title": r.get("title"),
                "url": r.get("url") or r.get("articleUrl"),
                "published": str(published)[:19] if published else None,
                "source": source,
                "description": r.get("description"),
            }
        )
    return out
