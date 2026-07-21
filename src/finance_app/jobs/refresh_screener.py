"""CLI: python -m finance_app.jobs.refresh_screener [--limit N] [--offset N]"""

from __future__ import annotations

import argparse
import json

from finance_app.db import init_db
from finance_app.ingest.screener import refresh_screener


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh screener snapshots")
    parser.add_argument("--universe", default="sp500")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="Only refresh price-based metrics (faster)",
    )
    args = parser.parse_args()

    init_db()
    result = refresh_screener(
        universe=args.universe,
        limit=args.limit,
        offset=args.offset,
        sleep_s=args.sleep,
        skip_fundamentals=args.skip_fundamentals,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
