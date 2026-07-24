"""Finnhub free-tier ingest: OHLCV candles, profile, news, earnings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import pandas as pd

from finance_app.config import get_settings

FINNHUB_BASE = "https://finnhub.io/api/v1"

EMPTY_OHLCV = pd.DataFrame(
    columns=["date", "open", "high", "low", "close", "adj_close", "volume"]
)

EMPTY_EVENTS = pd.DataFrame(
    columns=["report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
)


def _api_key() -> str:
    return (get_settings().finnhub_api_key or "").strip()


def finnhub_configured() -> bool:
    return bool(_api_key())


def _get_json(
    path: str,
    params: dict[str, Any],
    *,
    api_key: Optional[str] = None,
) -> Any:
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return None
    q = {**params, "token": key}
    try:
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.get(f"{FINNHUB_BASE}{path}", params=q)
            if resp.status_code != 200:
                return None
            return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        fv = float(v)
        if fv != fv:
            return None
        return fv
    except (TypeError, ValueError):
        return None


def _to_unix(date_s: Optional[str], *, end_of_day: bool = False) -> int:
    if not date_s:
        # Finnhub candles need from/to; default ~50y lookback
        ts = datetime(1970, 1, 2, tzinfo=timezone.utc)
    else:
        ts = datetime.strptime(str(date_s)[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    if end_of_day:
        ts = ts.replace(hour=23, minute=59, second=59)
    return int(ts.timestamp())


def candles_json_to_ohlcv(payload: Any) -> pd.DataFrame:
    """Map Finnhub /stock/candle JSON → standard OHLCV frame."""
    if not isinstance(payload, dict) or payload.get("s") != "ok":
        return EMPTY_OHLCV.copy()
    ts = payload.get("t") or []
    opens = payload.get("o") or []
    highs = payload.get("h") or []
    lows = payload.get("l") or []
    closes = payload.get("c") or []
    vols = payload.get("v") or []
    n = min(len(ts), len(opens), len(highs), len(lows), len(closes), len(vols))
    if n == 0:
        return EMPTY_OHLCV.copy()
    records = []
    for i in range(n):
        close = closes[i]
        records.append(
            {
                "date": datetime.fromtimestamp(int(ts[i]), tz=timezone.utc).strftime(
                    "%Y-%m-%d"
                ),
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": close,
                "adj_close": close,
                "volume": vols[i],
            }
        )
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return df[
        ["date", "open", "high", "low", "close", "adj_close", "volume"]
    ]


def fetch_ohlcv_finnhub(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """Daily OHLCV from Finnhub stock candles (US free tier)."""
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return EMPTY_OHLCV.copy()

    symbol = symbol.upper()
    data = _get_json(
        "/stock/candle",
        {
            "symbol": symbol,
            "resolution": "D",
            "from": _to_unix(start),
            "to": _to_unix(end or datetime.now(timezone.utc).strftime("%Y-%m-%d"), end_of_day=True),
        },
        api_key=key,
    )
    return candles_json_to_ohlcv(data)


def fetch_profile_finnhub(
    symbol: str,
    *,
    api_key: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Company profile2 → Tiingo-like meta dict."""
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return None
    data = _get_json("/stock/profile2", {"symbol": symbol.upper()}, api_key=key)
    if not isinstance(data, dict) or not data:
        return None
    name = data.get("name")
    if not name and not data.get("ticker"):
        return None
    return {
        "ticker": (data.get("ticker") or symbol).upper(),
        "name": name,
        "exchange": data.get("exchange"),
        "industry": data.get("finnhubIndustry") or data.get("industry"),
        "currency": data.get("currency"),
        "country": data.get("country"),
        "website": data.get("weburl"),
        "market_cap": _num(data.get("marketCapitalization")),
    }


def company_news_json_to_items(payload: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    """Map Finnhub company-news list → Tiingo-like news items."""
    if not isinstance(payload, list):
        return []
    items: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        title = (row.get("headline") or row.get("title") or "").strip()
        if not title:
            continue
        published = None
        dt = row.get("datetime")
        if dt is not None:
            try:
                published = datetime.fromtimestamp(int(dt), tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
            except (TypeError, ValueError, OSError):
                published = str(dt)
        items.append(
            {
                "title": title,
                "url": row.get("url"),
                "source": row.get("source"),
                "published": published,
                "summary": row.get("summary"),
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_company_news_finnhub(
    symbol: str,
    *,
    limit: int = 8,
    api_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return []
    today = datetime.now(timezone.utc).date()
    # Free tier: ~1 year of company news
    from_d = today.replace(year=max(1970, today.year - 1))
    data = _get_json(
        "/company-news",
        {
            "symbol": symbol.upper(),
            "from": from_d.isoformat(),
            "to": today.isoformat(),
        },
        api_key=key,
    )
    return company_news_json_to_items(data, limit=limit)


def _session_hour(hour_raw: Any) -> int:
    if hour_raw is None:
        return 0
    t = str(hour_raw).strip().lower()
    if t in ("bmo", "before market open", "pre-market"):
        return 8
    if t in ("amc", "after market close", "post-market"):
        return 16
    if ":" in t:
        try:
            hour = int(t.split(":")[0])
            if 0 <= hour <= 23:
                return hour
        except ValueError:
            pass
    return 0


def _surprise_pct(actual: Optional[float], estimate: Optional[float]) -> Optional[float]:
    if actual is None or estimate is None or estimate == 0:
        return None
    return ((actual - estimate) / abs(estimate)) * 100.0


def earnings_json_to_frame(payload: Any) -> pd.DataFrame:
    """Map Finnhub /stock/earnings list → events frame."""
    if not isinstance(payload, list):
        return EMPTY_EVENTS.copy()
    records: list[dict[str, Any]] = []
    for r in payload:
        if not isinstance(r, dict):
            continue
        period = r.get("period") or r.get("date")
        if not period:
            continue
        date_s = str(period)[:10]
        actual = _num(r.get("actual"))
        estimate = _num(r.get("estimate"))
        surprise = _num(r.get("surprisePercent"))
        if surprise is None:
            surprise = _surprise_pct(actual, estimate)
        records.append(
            {
                "report_datetime": pd.Timestamp(f"{date_s} 00:00:00"),
                "reported_eps": actual,
                "eps_estimate": estimate,
                "surprise_pct": surprise,
            }
        )
    if not records:
        return EMPTY_EVENTS.copy()
    df = pd.DataFrame(records)
    return (
        df.dropna(subset=["report_datetime"])
        .sort_values("report_datetime")
        .reset_index(drop=True)[
            ["report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
        ]
    )


def fetch_earnings_events_finnhub(
    symbol: str,
    *,
    limit: int = 100,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return EMPTY_EVENTS.copy()
    data = _get_json(
        "/stock/earnings",
        {"symbol": symbol.upper(), "limit": max(1, min(int(limit), 100))},
        api_key=key,
    )
    df = earnings_json_to_frame(data)
    if len(df) > limit:
        return df.tail(limit).reset_index(drop=True)
    return df


def fetch_earnings_calendar_finnhub(
    start: str,
    end: str,
    *,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """Bulk calendar window → symbol + EPS columns."""
    key = (api_key if api_key is not None else _api_key()).strip()
    empty = EMPTY_EVENTS.copy()
    empty.insert(0, "symbol", pd.Series(dtype=str))
    if not key:
        return empty

    data = _get_json(
        "/calendar/earnings",
        {"from": start[:10], "to": end[:10]},
        api_key=key,
    )
    rows = []
    if isinstance(data, dict):
        rows = data.get("earningsCalendar") or data.get("earnings") or []
    elif isinstance(data, list):
        rows = data
    if not isinstance(rows, list):
        return empty

    records: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sym = (r.get("symbol") or "").upper()
        date_raw = r.get("date") or r.get("period")
        if not sym or not date_raw:
            continue
        date_s = str(date_raw)[:10]
        hour = _session_hour(r.get("hour") or r.get("time"))
        actual = _num(r.get("epsActual", r.get("actual")))
        estimate = _num(r.get("epsEstimate", r.get("estimate")))
        surprise = _surprise_pct(actual, estimate)
        records.append(
            {
                "symbol": sym,
                "report_datetime": pd.Timestamp(f"{date_s} {hour:02d}:00:00"),
                "reported_eps": actual,
                "eps_estimate": estimate,
                "surprise_pct": surprise,
            }
        )
    if not records:
        return empty
    out = pd.DataFrame(records)
    return out[
        ["symbol", "report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
    ].sort_values(["report_datetime", "symbol"]).reset_index(drop=True)
