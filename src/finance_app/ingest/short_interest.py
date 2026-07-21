"""FINRA consolidated short interest ingest (biweekly settlement dates)."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import pandas as pd

from finance_app.db import (
    get_meta_updated_at,
    load_short_interest,
    set_meta,
    upsert_short_interest,
)

# Consolidated dataset includes exchange-listed + OTC (mid-2021 onward for listed).
FINRA_URL = (
    "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
)
SHORT_INTEREST_CACHE_HOURS = 24 * 7  # weekly cadence; refresh at least weekly


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        fv = float(v)
        if fv != fv:  # NaN
            return None
        return fv
    except (TypeError, ValueError):
        return None


def map_finra_row(row: dict[str, Any], symbol: str) -> Optional[tuple]:
    """Map a FINRA consolidated JSON row into a short_interest upsert tuple."""
    settlement = row.get("settlementDate")
    if not settlement:
        return None
    try:
        settlement = pd.to_datetime(settlement).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None

    shares = _f(
        row.get("currentShortPositionQuantity", row.get("currentShortShareNumber"))
    )
    if shares is None:
        return None

    prior = _f(
        row.get(
            "previousShortPositionQuantity", row.get("previousShortShareNumber")
        )
    )
    avg_vol = _f(
        row.get(
            "averageDailyVolumeQuantity",
            row.get("averageDailyShareVolume", row.get("averageShortShareNumber")),
        )
    )
    days = _f(row.get("daysToCoverQuantity", row.get("daysToCoverNumber")))
    # Legacy OTC sentinel
    if days is not None and days >= 999.0:
        days = None

    return (
        symbol.upper(),
        settlement,
        shares,
        prior,
        _f(row.get("changePercent")),
        avg_vol,
        days,
        "finra",
    )


def approximate_settlement_dates(start: date, end: date) -> list[str]:
    """
    Approximate FINRA mid-month (15th or prior business day) and month-end
    settlement dates. Used only if symbol-filtered query fails.
    """
    out: list[str] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        mid = date(y, m, 15)
        while mid.weekday() >= 5:
            mid -= timedelta(days=1)
        last_day = calendar.monthrange(y, m)[1]
        month_end = date(y, m, last_day)
        while month_end.weekday() >= 5:
            month_end -= timedelta(days=1)
        for d in (mid, month_end):
            if start <= d <= end:
                out.append(d.isoformat())
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def _finra_post(
    client: httpx.Client,
    filters: list[dict[str, Any]],
    *,
    limit: int = 5000,
    offset: int = 0,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "compareFilters": filters,
        "limit": limit,
        "offset": offset,
    }
    resp = client.post(
        FINRA_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=60.0,
    )
    if resp.status_code == 204:
        return []
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "results", "records"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def fetch_finra_short_interest(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> pd.DataFrame:
    """Fetch short interest for a symbol from FINRA consolidatedShortInterest."""
    symbol = symbol.upper()
    owns = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True)
    rows: list[dict[str, Any]] = []
    try:
        filters: list[dict[str, Any]] = [
            {
                "compareType": "EQUAL",
                "fieldName": "symbolCode",
                "fieldValue": symbol,
            }
        ]
        # Date filters are optional — symbol filter alone returns history.
        try:
            offset = 0
            while True:
                chunk = _finra_post(client, filters, limit=5000, offset=offset)
                if not chunk:
                    break
                rows.extend(chunk)
                if len(chunk) < 5000:
                    break
                offset += len(chunk)
                if offset > 20_000:
                    break
        except Exception:
            rows = []

        # Fallback: walk settlement dates with symbol filter
        if not rows:
            start_d = pd.to_datetime(start or "2021-06-01").date()
            end_d = pd.to_datetime(end or date.today().isoformat()).date()
            for settle in approximate_settlement_dates(start_d, end_d):
                try:
                    chunk = _finra_post(
                        client,
                        [
                            {
                                "compareType": "EQUAL",
                                "fieldName": "settlementDate",
                                "fieldValue": settle,
                            },
                            {
                                "compareType": "EQUAL",
                                "fieldName": "symbolCode",
                                "fieldValue": symbol,
                            },
                        ],
                        limit=50,
                    )
                    rows.extend(chunk)
                except Exception:
                    continue
    finally:
        if owns:
            client.close()

    mapped = []
    for r in rows:
        t = map_finra_row(r, symbol)
        if t:
            mapped.append(t)

    empty_cols = [
        "settlement_date",
        "shares_short",
        "shares_short_prior",
        "change_pct",
        "avg_daily_volume",
        "days_to_cover",
        "source",
    ]
    if not mapped:
        return pd.DataFrame(columns=empty_cols)

    df = pd.DataFrame(
        mapped,
        columns=[
            "symbol",
            "settlement_date",
            "shares_short",
            "shares_short_prior",
            "change_pct",
            "avg_daily_volume",
            "days_to_cover",
            "source",
        ],
    )
    df = df.drop_duplicates(subset=["settlement_date"], keep="last")
    df["settlement_date"] = pd.to_datetime(df["settlement_date"])
    if start:
        df = df[df["settlement_date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["settlement_date"] <= pd.to_datetime(end)]
    return df.sort_values("settlement_date").reset_index(drop=True)


def short_interest_cache_fresh(symbol: str) -> bool:
    updated = get_meta_updated_at(f"short_interest:{symbol.upper()}")
    if not updated:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - updated
    return age < timedelta(hours=SHORT_INTEREST_CACHE_HOURS)


def ingest_short_interest(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force: bool = False,
) -> int:
    """Fetch FINRA short interest into SQLite. Returns rows upserted."""
    symbol = symbol.upper()
    cached = load_short_interest(symbol)
    if not force and short_interest_cache_fresh(symbol) and not cached.empty:
        return 0

    # Always pull full history into cache; range filter applied on read.
    df = fetch_finra_short_interest(symbol, start=None, end=None)
    if df.empty:
        set_meta(f"short_interest:{symbol}", "empty")
        return 0

    rows = []
    for _, r in df.iterrows():
        rows.append(
            (
                symbol,
                r["settlement_date"].strftime("%Y-%m-%d"),
                _f(r["shares_short"]),
                _f(r["shares_short_prior"]),
                _f(r["change_pct"]),
                _f(r["avg_daily_volume"]),
                _f(r["days_to_cover"]),
                "finra",
            )
        )
    n = upsert_short_interest(rows)
    set_meta(f"short_interest:{symbol}", str(n))
    return n
