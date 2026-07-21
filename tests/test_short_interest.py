"""Unit tests for FINRA short interest mapping (no network)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_app.ingest.short_interest import (  # noqa: E402
    approximate_settlement_dates,
    map_finra_row,
)
from finance_app.services import short_interest_payload  # noqa: E402


def test_map_finra_row_basic():
    row = {
        "symbolCode": "INTC",
        "settlementDate": "2024-06-14",
        "currentShortPositionQuantity": 1000,
        "previousShortPositionQuantity": 800,
        "changePercent": 25.0,
        "averageDailyVolumeQuantity": 200,
        "daysToCoverQuantity": 5.0,
    }
    mapped = map_finra_row(row, "intc")
    assert mapped is not None
    assert mapped[0] == "INTC"
    assert mapped[1] == "2024-06-14"
    assert mapped[2] == 1000.0
    assert mapped[3] == 800.0
    assert mapped[4] == 25.0
    assert mapped[5] == 200.0
    assert mapped[6] == 5.0
    assert mapped[7] == "finra"


def test_map_finra_row_caps_days_to_cover_sentinel():
    row = {
        "settlementDate": "2024-06-14",
        "currentShortPositionQuantity": 10,
        "daysToCoverQuantity": 999.99,
    }
    mapped = map_finra_row(row, "XYZ")
    assert mapped is not None
    assert mapped[6] is None


def test_map_finra_row_requires_settlement_and_shares():
    assert map_finra_row({"currentShortPositionQuantity": 1}, "A") is None
    assert map_finra_row({"settlementDate": "2024-01-01"}, "A") is None


def test_approximate_settlement_dates_includes_mid_and_month_end():
    dates = approximate_settlement_dates(date(2024, 1, 1), date(2024, 2, 29))
    assert "2024-01-15" in dates or "2024-01-12" in dates  # 15th or prior weekday
    assert any(d.startswith("2024-01-3") for d in dates)
    assert any(d.startswith("2024-02-") for d in dates)


def test_short_interest_payload_from_cache(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings

    db_path = tmp_path / "si.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    db.upsert_short_interest(
        [
            ("TEST", "2024-01-15", 1_000_000.0, 900_000.0, 11.1, 50_000.0, 20.0, "finra"),
            ("TEST", "2024-01-31", 1_100_000.0, 1_000_000.0, 10.0, 55_000.0, 20.0, "finra"),
        ]
    )
    # Avoid network: mark cache fresh and stub Yahoo
    db.set_meta("short_interest:TEST", "2")
    monkeypatch.setattr(
        "finance_app.services.ingest_short_interest",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        "finance_app.services.fetch_yfinance_short_snapshot",
        lambda _s: {
            "shares_short": 1_100_000.0,
            "short_pct_float": 0.045,
            "short_ratio": 19.5,
            "shares_short_prior_month": 1_000_000.0,
        },
    )

    result = short_interest_payload("TEST", start="2024-01-01", end="2024-02-01")
    assert result["symbol"] == "TEST"
    assert len(result["series"]) == 2
    assert result["series"][-1]["shares_short"] == 1_100_000.0
    assert result["latest"] is not None
    assert result["latest"]["settlement_date"] == "2024-01-31"
    assert result["latest"]["short_pct_float"] == 0.045
    assert result["disclaimer"]
