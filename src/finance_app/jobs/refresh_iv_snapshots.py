"""CLI: python -m finance_app.jobs.refresh_iv_snapshots [--symbols AAPL,MSFT] [--sleep 0.4]

Fetches the nearest option chain for each symbol so ATM IV / OI land in
options_iv_snapshots. Run daily (or on a schedule) so IV rank has enough history
without relying only on interactive page loads.
"""

from __future__ import annotations

import argparse
import json
import time

from finance_app.db import init_db
from finance_app.metrics.option_strategies import DEFAULT_SCAN_SYMBOLS
from finance_app.metrics.options import options_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh options IV snapshots")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated tickers (default: strategy scan watchlist)",
    )
    parser.add_argument("--sleep", type=float, default=0.4, help="Pause between symbols")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Bypass options chain cache",
    )
    args = parser.parse_args()

    init_db()
    tickers = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else list(DEFAULT_SCAN_SYMBOLS)
    )

    results: list[dict] = []
    for i, symbol in enumerate(tickers):
        row: dict = {"symbol": symbol}
        try:
            payload = options_payload(
                symbol, full_chain=True, force_refresh=args.refresh
            )
            iv = (payload.get("iv_context") or {}).get("atm_iv")
            row["ok"] = not bool(payload.get("error"))
            row["expiration"] = payload.get("expiration")
            row["atm_iv"] = iv
            row["error"] = payload.get("error")
        except Exception as exc:
            row["ok"] = False
            row["error"] = str(exc)
        results.append(row)
        if i + 1 < len(tickers) and args.sleep > 0:
            time.sleep(args.sleep)

    print(
        json.dumps(
            {
                "count": len(results),
                "ok": sum(1 for r in results if r.get("ok")),
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
