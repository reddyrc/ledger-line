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
    assert "collar" in families
    kinds = {i["kind"] for i in result["ideas"]}
    assert "bull_put_spread" in kinds or "bear_call_spread" in kinds or "iron_condor" in kinds
    assert "collar" in kinds
    assert "free_collar" not in kinds

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


def test_free_collar_selection_and_payoff(tmp_path, monkeypatch):
    """Free pair kept; expensive pair dropped from free set; floor/cap payoff matches."""
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics import option_strategies as strat

    db_path = tmp_path / "collar.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    spot = 100.0
    # Free: sell 110 call bid 2.00, buy 95 put ask 1.50 → net +0.50
    # Debit: sell 105 call bid 0.40, buy 95 put ask 1.50 → net -1.10 (kept as debit collar)
    calls = [
        _opt(105, 0.50, side="call", bid=0.40, ask=0.60),
        _opt(110, 2.10, side="call", bid=2.00, ask=2.20),
    ]
    puts = [
        _opt(95, 1.40, side="put", bid=1.30, ask=1.50),
        _opt(90, 0.80, side="put", bid=0.70, ask=0.90),
    ]

    def fake_payload(symbol, expiration=None, full_chain=False, force_refresh=False, **_k):
        return {
            "symbol": symbol,
            "expiration": expiration or "2025-01-17",
            "expirations": ["2025-01-17"],
            "spot": spot,
            "summary": {
                "max_pain": 100.0,
                "expected_move": {"expected_move": 8.0, "atm_strike": 100.0},
            },
            "calls": calls,
            "puts": puts,
        }

    monkeypatch.setattr(strat, "options_payload", fake_payload)
    result = strat.generate_strategies("TEST", limit=50, force_refresh=True)
    collars = [i for i in result["ideas"] if i["kind"] == "collar"]
    assert collars, "expected at least one collar"

    def pair(i):
        return (
            next(lg["strike"] for lg in i["legs"] if lg["right"] == "put"),
            next(lg["strike"] for lg in i["legs"] if lg["right"] == "call"),
        )

    freeish = [
        i
        for i in collars
        if i["metrics"]["credit_or_debit"] is not None
        and i["metrics"]["credit_or_debit"] >= -strat.FREE_COLLAR_MAX_DEBIT
    ]
    free_pairs = {pair(i) for i in freeish}
    assert (95.0, 110.0) in free_pairs
    assert (95.0, 105.0) not in free_pairs

    debit_pairs = {
        pair(i)
        for i in collars
        if i["metrics"]["credit_or_debit"] is not None
        and i["metrics"]["credit_or_debit"] < -strat.FREE_COLLAR_MAX_DEBIT
    }
    assert (95.0, 105.0) in debit_pairs

    idea = next(i for i in freeish if pair(i) == (95.0, 110.0))
    assert idea["family"] == "collar"
    assert abs(idea["metrics"]["credit_or_debit"] - 0.5) < 1e-9

    pnl_floor = strat.payoff_at_expiration(idea["legs"], 95.0)
    assert abs(pnl_floor - (-idea["metrics"]["max_loss"])) < 1e-6

    pnl_cap = strat.payoff_at_expiration(idea["legs"], 110.0)
    assert abs(pnl_cap - idea["metrics"]["max_profit"]) < 1e-6

    bes = strat.compute_breakevens("collar", idea["legs"], 0.5)
    assert bes == [99.5]


def test_free_collar_breakeven_and_stock_payoff():
    from finance_app.metrics.option_strategies import (
        compute_breakevens,
        payoff_at_expiration,
    )

    legs = [
        {
            "action": "buy",
            "right": "stock",
            "strike": None,
            "mid": 100.0,
        },
        {"action": "buy", "right": "put", "strike": 95, "mid": 1.5},
        {"action": "sell", "right": "call", "strike": 110, "mid": 2.0},
    ]
    # Deep ITM put: stock −20 + put (20−1.5) + call credit 2 = −20 + 18.5 + 2 = 0.5
    # Wait: put intrinsic at 80 = 15, not 20. stock (80-100)=-20; put 15-1.5=13.5; call 2-0=2 → -4.5
    assert abs(payoff_at_expiration(legs, 80.0) - (-4.5)) < 1e-9
    assert compute_breakevens("collar", legs, 0.5) == [99.5]


def test_collar_limit_reserves_slots():
    from finance_app.metrics.option_strategies import _take_ideas_for_limit

    ideas = (
        [{"family": "credit", "id": f"c{i}", "metrics": {"edge_score": 90 - i}} for i in range(30)]
        + [{"family": "collar", "id": f"k{i}", "metrics": {"edge_score": 40 - i}} for i in range(10)]
    )
    taken = _take_ideas_for_limit(ideas, 20)
    assert len(taken) == 20
    assert sum(1 for i in taken if i["family"] == "collar") == 10


def test_collar_mid_fallback_when_bid_ask_missing():
    from finance_app.metrics.option_strategies import _collars

    spot = 100.0
    # Mid only — no bid/ask (common on thin Yahoo rows)
    puts = {
        95.0: {
            "strike": 95.0,
            "side": "put",
            "bid": None,
            "ask": None,
            "mid": 1.5,
            "last": 1.5,
            "volume": 1,
            "open_interest": 10,
            "implied_volatility": 0.3,
            "contract_symbol": "P95",
        }
    }
    calls = {
        110.0: {
            "strike": 110.0,
            "side": "call",
            "bid": None,
            "ask": None,
            "mid": 2.0,
            "last": 2.0,
            "volume": 1,
            "open_interest": 10,
            "implied_volatility": 0.3,
            "contract_symbol": "C110",
        }
    }
    ideas = _collars("TEST", "2025-01-17", calls, puts, spot, 8.0, None)
    assert ideas
    assert ideas[0]["metrics"]["credit_or_debit"] == 0.5
