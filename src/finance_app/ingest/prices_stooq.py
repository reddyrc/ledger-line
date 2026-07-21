from __future__ import annotations

from typing import Optional

import httpx
import pandas as pd

STOOQ_URL = "https://stooq.com/q/d/l/"


def fetch_stooq_ohlcv(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch daily OHLCV from Stooq CSV download.
    US tickers use the .us suffix (e.g. aapl.us).

    Note: Stooq sometimes serves bot-challenge HTML instead of CSV; in that case
    this returns an empty frame so callers can fall back to other sources.
    """
    empty = pd.DataFrame(
        columns=["date", "open", "high", "low", "close", "adj_close", "volume"]
    )
    stooq_symbol = _to_stooq_symbol(symbol)
    params = {"s": stooq_symbol, "i": "d"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/csv,text/plain,*/*",
        "Referer": "https://stooq.com/",
    }
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(STOOQ_URL, params=params)
            if resp.status_code != 200:
                return empty
            text = resp.text.strip()
    except httpx.HTTPError:
        return empty

    if (
        not text
        or text.lower().startswith("<!")
        or "<html" in text[:200].lower()
        or "no data" in text.lower()
    ):
        return empty

    from io import StringIO

    try:
        df = pd.read_csv(StringIO(text))
    except Exception:
        return empty

    if df.empty or "Date" not in df.columns:
        return empty

    df = df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    # Stooq close is typically already adjusted for US equities downloads
    df["adj_close"] = df["close"]
    df = df.sort_values("date")

    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]

    return df[["date", "open", "high", "low", "close", "adj_close", "volume"]].dropna(
        subset=["close"]
    )


def _to_stooq_symbol(symbol: str) -> str:
    s = symbol.lower().strip()
    if "." in s:
        return s
    return f"{s}.us"
