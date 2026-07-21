"""Batch refresh of screener snapshots for a universe."""

from __future__ import annotations

import time
from typing import Any, Optional

from finance_app.db import (
    init_db,
    set_meta,
    upsert_screen_snapshot,
)
from finance_app.ingest import get_or_fetch_ohlcv
from finance_app.ingest.edgar import ingest_fundamentals
from finance_app.metrics.screener import compute_screen_metrics
from finance_app.universe import list_universe


def refresh_screener(
    universe: str = "sp500",
    limit: Optional[int] = None,
    offset: int = 0,
    sleep_s: float = 0.25,
    skip_fundamentals: bool = False,
) -> dict[str, Any]:
    """
    For each universe ticker: fetch prices (+ EDGAR), compute snapshot, upsert.
    Returns summary counts. Designed to be resumable via offset/limit.
    """
    init_db()
    tickers = list_universe(universe)
    slice_ = tickers[offset : (offset + limit) if limit is not None else None]

    ok = 0
    failed = 0
    errors: list[dict[str, str]] = []

    for i, meta in enumerate(slice_):
        ticker = meta["ticker"]
        name = meta.get("name")
        sector = meta.get("sector")
        try:
            get_or_fetch_ohlcv(ticker, force_refresh=False)
            if not skip_fundamentals:
                try:
                    ingest_fundamentals(ticker)
                except Exception as fund_exc:
                    # Keep going with price-only metrics
                    fund_err = str(fund_exc)[:200]
                else:
                    fund_err = None
            else:
                fund_err = None

            row = compute_screen_metrics(ticker)
            row["name"] = name
            row["sector"] = sector
            if fund_err and not row.get("error"):
                row["error"] = f"fundamentals: {fund_err}"
            upsert_screen_snapshot(row)
            if row.get("error") and row["error"] == "no_price_data":
                failed += 1
                errors.append({"ticker": ticker, "error": row["error"]})
            else:
                ok += 1
        except Exception as exc:
            failed += 1
            err = str(exc)[:240]
            errors.append({"ticker": ticker, "error": err})
            upsert_screen_snapshot(
                {
                    "ticker": ticker,
                    "name": name,
                    "sector": sector,
                    "error": err,
                }
            )

        if sleep_s > 0 and i < len(slice_) - 1:
            time.sleep(sleep_s)

    set_meta(f"screen:{universe}:last_refresh", f"ok={ok},failed={failed}")
    return {
        "universe": universe,
        "processed": len(slice_),
        "ok": ok,
        "failed": failed,
        "offset": offset,
        "limit": limit,
        "errors": errors[:50],
    }
