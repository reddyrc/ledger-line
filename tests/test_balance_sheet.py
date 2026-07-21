"""Balance sheet history from cached EDGAR fundamentals."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_build_balance_sheet_history(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics.fundamentals import build_balance_sheet

    db_path = tmp_path / "bs.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    rows = []
    for year, cash, assets, equity in [
        (2022, 10e9, 100e9, 60e9),
        (2023, 12e9, 110e9, 65e9),
        (2024, 15e9, 120e9, 70e9),
    ]:
        end = f"{year}-12-31"
        for concept, value in [
            ("Cash", cash),
            ("Assets", assets),
            ("Equity", equity),
            ("CurrentAssets", cash + 20e9),
            ("CurrentLiabilities", 25e9),
            ("LongTermDebt", 30e9),
        ]:
            rows.append(
                (
                    "0000320193",
                    "AAPL",
                    concept,
                    end,
                    value,
                    "USD",
                    "10-K",
                    year,
                    "FY",
                    f"{year + 1}-01-15",
                )
            )
    db.upsert_fundamentals(rows)

    bs = build_balance_sheet("AAPL")
    assert bs["as_of"] == "2024-12-31"
    assert bs["form"] == "10-K"
    keys = {line["key"] for line in bs["lines"]}
    assert "Cash" in keys
    assert "Assets" in keys
    assert "Equity" in keys
    assert "Liabilities" in keys  # derived from Assets − Equity
    assert len(bs["history"]["periods"]) == 3

    cash_row = next(r for r in bs["history"]["rows"] if r["key"] == "Cash")
    assert cash_row["values"][-1] == 15e9
    liab = next(line for line in bs["lines"] if line["key"] == "Liabilities")
    assert liab["value"] == 50e9  # 120 − 70
