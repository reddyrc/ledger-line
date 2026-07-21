"""Unit tests for options strategy screener (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _opt(strike, mid, *, side="call", bid=None, ask=None, last=None, iv=0.3):
    bid = mid - 0.05 if bid is None else bid
    ask = mid + 0.05 if ask is None else ask
    return {
        "contract_symbol": f"{side[0].upper()}{strike}",
        "side": side,
        "strike": float(strike),
        "bid": bid,
        "ask": ask,
        "last": last if last is not None else mid,
        "mid": mid,
        "volume": 10,
        "open_interest": 100,
        "implied_volatility": iv,
    }


def test_breakevens_verticals():
    from finance_app.metrics.option_strategies import compute_breakevens

    bull_put_legs = [
        {"action": "sell", "right": "put", "strike": 100},
        {"action": "buy", "right": "put", "strike": 95},
    ]
    assert compute_breakevens("bull_put_spread", bull_put_legs, 1.5) == [98.5]

    bull_call_legs = [
        {"action": "buy", "right": "call", "strike": 100},
        {"action": "sell", "right": "call", "strike": 105},
    ]
    assert compute_breakevens("bull_call_spread", bull_call_legs, -2.0) == [102.0]


def test_idea_id_stable():
    from finance_app.metrics.option_strategies import idea_id

    legs = [
        {"action": "sell", "right": "put", "strike": 95},
        {"action": "buy", "right": "put", "strike": 90},
    ]
    a = idea_id("AAPL", "2025-01-17", "bull_put_spread", legs)
    b = idea_id("AAPL", "2025-01-17", "bull_put_spread", list(reversed(legs)))
    assert a == b
    assert len(a) == 16


def test_pop_proxy_and_payoff():
    from finance_app.metrics.option_strategies import _pop_proxy, payoff_at_expiration

    assert _pop_proxy(1.0, 5.0) == 0.8
    legs = [
        {"action": "sell", "right": "put", "strike": 100, "mid": 2.0},
        {"action": "buy", "right": "put", "strike": 95, "mid": 0.5},
    ]
    # At 100: both puts OTM → pnl = credit 1.5
    assert abs(payoff_at_expiration(legs, 100) - 1.5) < 1e-9
    # At 90: short put worth 10, long put worth 5 → intrinsic -5 + credit 1.5 = -3.5
    assert abs(payoff_at_expiration(legs, 90) - (-3.5)) < 1e-9


def test_credit_debit_and_parity_generation(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics import option_strategies as strat

    db_path = tmp_path / "strat.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    spot = 100.0
    calls = [
        _opt(95, 6.0, side="call"),
        _opt(100, 3.0, side="call"),
        _opt(105, 1.5, side="call"),
        _opt(110, 0.7, side="call"),
    ]
    puts = [
        _opt(90, 0.6, side="put"),
        _opt(95, 1.4, side="put"),
        _opt(100, 3.0, side="put"),
        _opt(105, 6.0, side="put"),
    ]

    def fake_payload(symbol, expiration=None, full_chain=False, force_refresh=False, **_k):
        return {
            "symbol": symbol,
            "expiration": expiration or "2025-01-17",
            "expirations": ["2025-01-17"],
            "spot": spot,
            "summary": {
                "max_pain": 100.0,
                "expected_move": {
                    "expected_move": 4.0,
                    "atm_strike": 100.0,
                },
            },
            "calls": calls,
            "puts": puts,
        }

    monkeypatch.setattr(strat, "options_payload", fake_payload)

    result = strat.generate_strategies("TEST", limit=30)
    assert result.get("error") is None
    families = {i["family"] for i in result["ideas"]}
    assert "credit" in families
    assert "debit" in families
    assert "mispricing" in families
    kinds = {i["kind"] for i in result["ideas"]}
    assert "bull_put_spread" in kinds or "bear_call_spread" in kinds or "iron_condor" in kinds

    top = result["ideas"][0]
    detail = strat.strategy_detail("TEST", top["id"], expiration="2025-01-17")
    assert detail["idea"]["id"] == top["id"]
    assert len(detail["payoff"]) >= 10

    # Cache hit
    again = strat.generate_strategies("TEST", limit=30)
    assert again["freshness"] == "cached"


def test_strategies_scan_caps_symbols(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics import option_strategies as strat

    db_path = tmp_path / "scan.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    def fake_gen(symbol, expiration=None, limit=5, force_refresh=False, **_kwargs):
        return {
            "symbol": symbol,
            "expiration": "2025-01-17",
            "ideas": [
                {
                    "id": f"{symbol}-1",
                    "symbol": symbol,
                    "family": "credit",
                    "kind": "bull_put_spread",
                    "title": f"{symbol} idea",
                    "expiration": "2025-01-17",
                    "legs": [],
                    "metrics": {"edge_score": 50},
                }
            ],
        }

    monkeypatch.setattr(strat, "generate_strategies", fake_gen)
    many = [f"T{i}" for i in range(20)]
    scan = strat.strategies_scan(many, limit_per_symbol=2)
    assert len(scan["symbols"]) == 15
    assert len(scan["ideas"]) == 15
