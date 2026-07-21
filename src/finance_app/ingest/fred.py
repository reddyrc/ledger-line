from __future__ import annotations

from typing import Optional

import httpx
import pandas as pd

from finance_app.config import get_settings
from finance_app.db import load_macro, upsert_macro

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"

# Common series used by the metric layer
DEFAULT_SERIES = {
    "DGS3MO": "3-Month Treasury Constant Maturity Rate",
    "TB3MS": "3-Month Treasury Bill Secondary Market Rate",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
    "DGS2": "2-Year Treasury Constant Maturity Rate",
    "FEDFUNDS": "Effective Federal Funds Rate",
    "CPIAUCSL": "CPI All Urban Consumers",
    "UNRATE": "Unemployment Rate",
    "VIXCLS": "CBOE Volatility Index",
    "USREC": "NBER Recession Indicator",
}


def fetch_fred_series(
    series_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch a FRED series. Free API key recommended; some CSV fallbacks exist but
    the JSON API is preferred when a key is configured.
    """
    key = api_key if api_key is not None else get_settings().fred_api_key
    if not key:
        return _fetch_fred_csv(series_id, start=start, end=end)

    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "observation_start": start or "1900-01-01",
    }
    if end:
        params["observation_end"] = end

    with httpx.Client(timeout=60.0) as client:
        resp = client.get(FRED_OBS_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    rows = []
    for obs in data.get("observations", []):
        val = obs.get("value")
        if val in (None, "."):
            continue
        rows.append({"date": obs["date"], "value": float(val)})

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _fetch_fred_csv(
    series_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """No-key CSV fallback from FRED graph endpoint."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        from io import StringIO

        df = pd.read_csv(StringIO(resp.text))
    if df.empty or len(df.columns) < 2:
        return pd.DataFrame(columns=["date", "value"])
    df = df.rename(columns={df.columns[0]: "date", df.columns[1]: "value"})
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["value"] != "."]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]
    return df[["date", "value"]]


def get_or_fetch_macro(
    series_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    cached = load_macro(series_id, start=start, end=end)
    if force_refresh or cached.empty:
        df = fetch_fred_series(series_id, start=start, end=end)
        if not df.empty:
            upsert_macro(series_id, df)
            cached = load_macro(series_id, start=start, end=end)
    return cached


def ingest_default_macro(force_refresh: bool = False) -> dict[str, int]:
    counts: dict[str, int] = {}
    for series_id in DEFAULT_SERIES:
        df = fetch_fred_series(series_id) if force_refresh else None
        if df is None:
            existing = load_macro(series_id)
            if not existing.empty:
                counts[series_id] = len(existing)
                continue
            df = fetch_fred_series(series_id)
        n = upsert_macro(series_id, df) if df is not None and not df.empty else 0
        counts[series_id] = n
    return counts
