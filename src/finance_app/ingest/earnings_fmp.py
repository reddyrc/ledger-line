"""Financial Modeling Prep earnings calendar / EPS ingest."""

from __future__ import annotations

from typing import Any, Optional

import httpx
import pandas as pd

from finance_app.config import get_settings

FMP_STABLE = "https://financialmodelingprep.com/stable"

EMPTY_EVENTS = pd.DataFrame(
    columns=["report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
)


def _api_key() -> str:
    return (get_settings().fmp_api_key or "").strip()


def fmp_configured() -> bool:
    return bool(_api_key())


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


def _surprise_pct(actual: Optional[float], estimate: Optional[float]) -> Optional[float]:
    if actual is None or estimate is None:
        return None
    if estimate == 0:
        return None
    return ((actual - estimate) / abs(estimate)) * 100.0


def _session_offset_hours(time_raw: Any) -> int:
    """Map FMP bmo/amc/time hints to a naive NY local hour for session tagging."""
    if time_raw is None:
        return 0
    t = str(time_raw).strip().lower()
    if t in ("bmo", "before market open", "before-market", "pre-market"):
        return 8
    if t in ("amc", "after market close", "after-market", "post-market"):
        return 16
    # Already an hour like "16:00" or "4:00 PM"
    if ":" in t:
        try:
            hour = int(t.split(":")[0])
            if 0 <= hour <= 23:
                return hour
        except ValueError:
            pass
    return 0


def _rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        date_raw = r.get("date") or r.get("earningsDate") or r.get("reportDate")
        if not date_raw:
            continue
        date_s = str(date_raw)[:10]
        hour = _session_offset_hours(
            r.get("time") or r.get("hour") or r.get("when")
        )
        # Store as naive local-ish datetime (matches yfinance ingest convention).
        report_dt = pd.Timestamp(f"{date_s} {hour:02d}:00:00")
        actual = _num(r.get("epsActual", r.get("eps_actual", r.get("reportedEPS"))))
        estimate = _num(
            r.get("epsEstimated", r.get("eps_estimated", r.get("estimatedEPS")))
        )
        surprise = _num(r.get("surprisePercent", r.get("surprise_pct")))
        if surprise is None:
            surprise = _surprise_pct(actual, estimate)
        records.append(
            {
                "report_datetime": report_dt,
                "reported_eps": actual,
                "eps_estimate": estimate,
                "surprise_pct": surprise,
            }
        )
    if not records:
        return EMPTY_EVENTS.copy()
    df = pd.DataFrame(records)
    df = df.dropna(subset=["report_datetime"]).sort_values("report_datetime")
    return df.reset_index(drop=True)[
        ["report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
    ]


def fetch_fmp_earnings_events(
    symbol: str,
    *,
    limit: int = 100,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """Historical + upcoming earnings for one symbol (EPS actual/estimate)."""
    key = (api_key if api_key is not None else _api_key()).strip()
    if not key:
        return EMPTY_EVENTS.copy()

    symbol = symbol.upper()
    params = {
        "symbol": symbol,
        "limit": str(max(1, min(int(limit), 1000))),
        "apikey": key,
    }
    try:
        with httpx.Client(timeout=45.0, trust_env=False) as client:
            resp = client.get(f"{FMP_STABLE}/earnings", params=params)
            if resp.status_code != 200:
                return EMPTY_EVENTS.copy()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return EMPTY_EVENTS.copy()

    if isinstance(data, dict):
        # Some FMP errors return {"Error Message": "..."}
        if "Error Message" in data or "error" in data:
            return EMPTY_EVENTS.copy()
        data = data.get("historical") or data.get("earnings") or []
    if not isinstance(data, list):
        return EMPTY_EVENTS.copy()
    return _rows_to_frame(data)


def fetch_fmp_earnings_calendar(
    start: str,
    end: str,
    *,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Earnings in a date window across symbols.
    Returns columns: symbol, report_datetime, reported_eps, eps_estimate, surprise_pct
    """
    key = (api_key if api_key is not None else _api_key()).strip()
    empty = EMPTY_EVENTS.copy()
    empty.insert(0, "symbol", pd.Series(dtype=str))
    if not key:
        return empty

    params = {
        "from": start[:10],
        "to": end[:10],
        "apikey": key,
    }
    try:
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.get(f"{FMP_STABLE}/earnings-calendar", params=params)
            if resp.status_code != 200:
                return empty
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return empty

    if not isinstance(data, list):
        return empty

    # Attach symbol then reuse row mapper per group
    records: list[dict[str, Any]] = []
    for r in data:
        if not isinstance(r, dict):
            continue
        sym = (r.get("symbol") or "").upper()
        if not sym:
            continue
        frame = _rows_to_frame([r])
        if frame.empty:
            continue
        row = frame.iloc[0].to_dict()
        row["symbol"] = sym
        records.append(row)
    if not records:
        return empty
    out = pd.DataFrame(records)
    return out[
        ["symbol", "report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
    ].sort_values(["report_datetime", "symbol"]).reset_index(drop=True)
