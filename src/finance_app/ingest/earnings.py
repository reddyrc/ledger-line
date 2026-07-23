"""Resolve earnings events from FMP and/or yfinance based on EARNINGS_PRIMARY."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from finance_app.config import get_settings, normalize_earnings_primary
from finance_app.ingest.earnings_fmp import fetch_fmp_earnings_events, fmp_configured
from finance_app.ingest.prices_yfinance import fetch_yfinance_earnings_events

EMPTY = pd.DataFrame(
    columns=["report_datetime", "reported_eps", "eps_estimate", "surprise_pct"]
)


def effective_earnings_primary(override: Optional[str] = None) -> str:
    settings = get_settings()
    return normalize_earnings_primary(
        override if override is not None else settings.earnings_primary,
        fmp_configured=settings.fmp_configured,
    )


def fetch_earnings_events_with_fallback(
    symbol: str,
    *,
    earnings_primary: Optional[str] = None,
    limit: int = 100,
) -> tuple[pd.DataFrame, str]:
    """
    Prefer EARNINGS_PRIMARY (or override), then cross-fallback.
    Returns (dataframe, source) where source is fmp | yfinance | none.
    """
    primary = effective_earnings_primary(earnings_primary)
    order = (
        ("fmp", "yfinance") if primary == "fmp" else ("yfinance", "fmp")
    )

    for source in order:
        try:
            if source == "fmp":
                if not fmp_configured():
                    continue
                df = fetch_fmp_earnings_events(symbol, limit=limit)
            else:
                df = fetch_yfinance_earnings_events(symbol, limit=limit)
        except Exception:
            continue
        if df is not None and not df.empty:
            return df, source

    return EMPTY.copy(), "none"


def earnings_frame_to_rows(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    """Map events frame → upsert_earnings_events row tuples."""

    def _round(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            fv = float(v)
            if fv != fv:
                return None
            return round(fv, 6)
        except (TypeError, ValueError):
            return None

    rows: list[tuple[Any, ...]] = []
    for _, r in df.iterrows():
        dt = r["report_datetime"]
        dt_s = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        rows.append(
            (
                dt_s,
                _round(r.get("reported_eps")),
                _round(r.get("eps_estimate")),
                _round(r.get("surprise_pct")),
            )
        )
    return rows
