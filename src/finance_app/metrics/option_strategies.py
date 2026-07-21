"""Heuristic options strategy screener (credit, debit, mispricing)."""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from finance_app.config import get_settings
from finance_app.db import (
    get_options_strategy_cache,
    get_screen_snapshot,
    upsert_options_strategy_cache,
)
from finance_app.metrics.option_pricing import black_scholes, leg_bs, years_to_expiration
from finance_app.metrics.options import next_earnings_info, options_payload

STRATEGY_TTL = timedelta(minutes=5)
DISCLAIMER = (
    "Heuristic screen from delayed Yahoo option mids. Scores are not probabilities of "
    "profit, ignore fills/fees/assignment, and are not trade advice. Mispricing flags "
    "are quote anomalies—not executable arbitrage."
)
DEFAULT_SCAN_SYMBOLS = [
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
]


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            return None
        return fv
    except (TypeError, ValueError):
        return None


def _round(v: Any, nd: int = 6) -> Optional[float]:
    fv = _num(v)
    return None if fv is None else round(fv, nd)


def _mid(row: Optional[dict]) -> Optional[float]:
    if not row:
        return None
    m = _num(row.get("mid"))
    if m is not None:
        return m
    return _num(row.get("last"))


def _leg(row: dict, right: str, action: str) -> dict[str, Any]:
    return {
        "action": action,  # buy | sell
        "right": right,  # call | put
        "strike": row.get("strike"),
        "mid": _mid(row),
        "bid": row.get("bid"),
        "ask": row.get("ask"),
        "last": row.get("last"),
        "implied_volatility": row.get("implied_volatility"),
        "contract_symbol": row.get("contract_symbol"),
        "open_interest": row.get("open_interest"),
        "volume": row.get("volume"),
    }


def idea_id(symbol: str, expiration: str, kind: str, legs: list[dict]) -> str:
    parts = [
        symbol.upper(),
        expiration,
        kind,
        *[
            f"{lg.get('action')}:{lg.get('right')}:{lg.get('strike')}"
            for lg in sorted(
                legs,
                key=lambda x: (
                    str(x.get("right")),
                    float(x.get("strike") or 0),
                    str(x.get("action")),
                ),
            )
        ],
    ]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _by_strike(rows: list[dict]) -> dict[float, dict]:
    out: dict[float, dict] = {}
    for r in rows:
        s = _num(r.get("strike"))
        if s is None or _mid(r) is None:
            continue
        out[s] = r
    return out


def _nearest_strikes(strikes: list[float], spot: float, n: int = 8) -> list[float]:
    ordered = sorted(strikes, key=lambda s: abs(s - spot))
    return sorted(ordered[:n])


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _spread_pct(row: Optional[dict]) -> Optional[float]:
    if not row:
        return None
    bid, ask = _num(row.get("bid")), _num(row.get("ask"))
    mid = _mid(row)
    if bid is None or ask is None or mid is None or mid <= 0:
        return None
    return (ask - bid) / mid


def idea_liquidity(legs: list[dict], chain_rows: Optional[dict] = None) -> dict[str, Any]:
    """Aggregate liquidity across idea legs (using bid/ask on legs)."""
    ois: list[float] = []
    vols: list[float] = []
    spreads: list[float] = []
    for lg in legs:
        oi = _num(lg.get("open_interest"))
        vol = _num(lg.get("volume"))
        bid, ask = _num(lg.get("bid")), _num(lg.get("ask"))
        mid = _num(lg.get("mid"))
        if oi is not None:
            ois.append(oi)
        if vol is not None:
            vols.append(vol)
        if bid is not None and ask is not None and mid and mid > 0:
            spreads.append((ask - bid) / mid)
    min_oi = min(ois) if ois else None
    min_vol = min(vols) if vols else None
    max_spread = max(spreads) if spreads else None
    return {
        "min_oi": _round(min_oi, 0),
        "min_volume": _round(min_vol, 0),
        "max_spread_pct": _round(max_spread, 4),
        "ok": True,
    }


def passes_liquidity(
    idea: dict[str, Any],
    *,
    min_oi: Optional[float] = None,
    min_volume: Optional[float] = None,
    max_spread_pct: Optional[float] = None,
) -> bool:
    liq = idea_liquidity(idea.get("legs") or [])
    idea.setdefault("metrics", {})["liquidity"] = liq
    if min_oi is not None and (liq["min_oi"] is None or liq["min_oi"] < min_oi):
        liq["ok"] = False
        return False
    if min_volume is not None and (
        liq["min_volume"] is None or liq["min_volume"] < min_volume
    ):
        liq["ok"] = False
        return False
    if max_spread_pct is not None and (
        liq["max_spread_pct"] is None or liq["max_spread_pct"] > max_spread_pct
    ):
        liq["ok"] = False
        return False
    return True


def annotate_earnings_risk(idea: dict[str, Any], days_to_earnings: Optional[int]) -> None:
    if days_to_earnings is None:
        return
    idea.setdefault("metrics", {})["days_to_earnings"] = days_to_earnings
    if days_to_earnings <= 7 and idea.get("family") == "credit":
        notes = list((idea.get("metrics") or {}).get("notes") or [])
        notes.append(f"Earnings in {days_to_earnings}d — credit risk into print")
        idea["metrics"]["notes"] = notes


def net_greeks_for_idea(
    idea: dict[str, Any],
    *,
    rate: Optional[float] = None,
) -> dict[str, Any]:
    settings = get_settings()
    rf = rate if rate is not None else float(settings.options_risk_free)
    legs = idea.get("legs") or []
    spot = _num((idea.get("metrics") or {}).get("spot"))
    expiration = idea.get("expiration") or ""
    if spot is None or spot <= 0 or not expiration:
        return {
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "rho": None,
            "source": "bs_from_mid_iv",
            "legs": [],
        }

    leg_greeks: list[dict[str, Any]] = []
    totals = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    for lg in legs:
        iv = _num(lg.get("implied_volatility"))
        if iv is None or iv <= 0:
            # try price from mid as IV-less skip
            g = {
                "contract_symbol": lg.get("contract_symbol"),
                "delta": None,
                "gamma": None,
                "theta": None,
                "vega": None,
                "rho": None,
            }
            leg_greeks.append(g)
            continue
        signed = leg_bs(lg, spot, expiration, rate=rf)
        g = {
            "contract_symbol": lg.get("contract_symbol"),
            "action": lg.get("action"),
            "right": lg.get("right"),
            "strike": lg.get("strike"),
            "delta": signed.get("delta"),
            "gamma": signed.get("gamma"),
            "theta": signed.get("theta"),
            "vega": signed.get("vega"),
            "rho": signed.get("rho"),
            "model_price": signed.get("unsigned_price"),
        }
        leg_greeks.append(g)
        for k in totals:
            if g.get(k) is not None:
                totals[k] += float(g[k])

    return {
        "delta": _round(totals["delta"], 4),
        "gamma": _round(totals["gamma"], 6),
        "theta": _round(totals["theta"], 4),
        "vega": _round(totals["vega"], 4),
        "rho": _round(totals["rho"], 4),
        "source": "bs_from_mid_iv",
        "legs": leg_greeks,
    }


def scenario_grid(
    idea: dict[str, Any],
    *,
    rate: Optional[float] = None,
    spot_shocks: Optional[list[float]] = None,
    iv_shocks: Optional[list[float]] = None,
) -> dict[str, Any]:
    """Mark-to-model PnL grid (per share) under spot × IV shocks."""
    settings = get_settings()
    rf = rate if rate is not None else float(settings.options_risk_free)
    legs = idea.get("legs") or []
    spot = _num((idea.get("metrics") or {}).get("spot"))
    expiration = idea.get("expiration") or ""
    spots = spot_shocks or [-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10]
    ivs = iv_shocks or [-0.20, 0.0, 0.20]
    if spot is None or spot <= 0 or not legs:
        return {
            "horizon": "mark_to_model",
            "note": "Insufficient data for scenarios.",
            "grid": [],
        }

    grid: list[dict[str, Any]] = []
    for sp in spots:
        for ivs_pct in ivs:
            value = 0.0
            entry_value = 0.0
            ok = True
            for lg in legs:
                mid = _num(lg.get("mid")) or 0.0
                iv = _num(lg.get("implied_volatility"))
                strike = _num(lg.get("strike"))
                if iv is None or strike is None:
                    ok = False
                    break
                right = "put" if lg.get("right") == "put" else "call"
                t = years_to_expiration(expiration)
                px = black_scholes(
                    spot * (1.0 + sp),
                    strike,
                    t,
                    max(iv * (1.0 + ivs_pct), 1e-6),
                    right=right,
                    rate=rf,
                ).get("price")
                if px is None:
                    ok = False
                    break
                if lg.get("action") == "buy":
                    value += float(px)
                    entry_value += mid
                else:
                    value -= float(px)
                    entry_value -= mid
            if not ok:
                continue
            pnl = value - entry_value
            grid.append(
                {
                    "spot_pct": sp,
                    "iv_pct": ivs_pct,
                    "pnl": _round(pnl, 4),
                }
            )

    return {
        "horizon": "mark_to_model",
        "note": (
            "Black–Scholes reprice of delayed mids under spot/IV shocks — not expiration "
            "payoff and not a live quote."
        ),
        "spot_shocks": spots,
        "iv_shocks": ivs,
        "grid": grid,
    }


def _apply_liquidity_defaults(
    *,
    for_scan: bool,
    min_oi: Optional[float],
    min_volume: Optional[float],
    max_spread_pct: Optional[float],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    if for_scan:
        return (
            100.0 if min_oi is None else min_oi,
            10.0 if min_volume is None else min_volume,
            0.25 if max_spread_pct is None else max_spread_pct,
        )
    return (min_oi, min_volume, max_spread_pct)


def _pop_proxy(credit: float, width: float) -> Optional[float]:
    if width <= 0 or credit is None:
        return None
    # Crude vertical POP proxy; capped
    return _round(_clamp(1.0 - credit / width, 0.05, 0.95), 4)


def payoff_at_expiration(legs: list[dict], spot: float) -> float:
    """Per-share PnL at expiration (not ×100)."""
    total = 0.0
    for lg in legs:
        k = _num(lg.get("strike"))
        mid = _num(lg.get("mid")) or 0.0
        right = lg.get("right")
        action = lg.get("action")
        if k is None:
            continue
        if right == "call":
            intrinsic = max(spot - k, 0.0)
        else:
            intrinsic = max(k - spot, 0.0)
        signed = intrinsic - mid if action == "buy" else mid - intrinsic
        total += signed
    return total


def payoff_curve(legs: list[dict], spot: Optional[float], points: int = 41) -> list[dict]:
    strikes = [_num(lg.get("strike")) for lg in legs]
    strikes = [s for s in strikes if s is not None]
    if not strikes:
        return []
    lo = min(strikes) * 0.9
    hi = max(strikes) * 1.1
    if spot is not None:
        lo = min(lo, spot * 0.85)
        hi = max(hi, spot * 1.15)
    if hi <= lo:
        hi = lo + 1.0
    step = (hi - lo) / max(points - 1, 1)
    out = []
    for i in range(points):
        s = lo + i * step
        out.append({"spot": _round(s, 4), "pnl": _round(payoff_at_expiration(legs, s), 4)})
    return out


def _credit_verticals(
    symbol: str,
    expiration: str,
    calls: dict[float, dict],
    puts: dict[float, dict],
    spot: float,
    expected_move: Optional[float],
    max_pain: Optional[float],
) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    em = expected_move or spot * 0.03
    put_strikes = sorted(puts.keys())
    call_strikes = sorted(calls.keys())

    # Bull put: sell higher put, buy lower put below spot
    below = [s for s in put_strikes if s < spot]
    for i, short_k in enumerate(below[-6:]):
        longs = [s for s in below if s < short_k]
        if not longs:
            continue
        long_k = longs[-1]
        short_row, long_row = puts[short_k], puts[long_k]
        credit = (_mid(short_row) or 0) - (_mid(long_row) or 0)
        width = short_k - long_k
        if credit <= 0 or width <= 0:
            continue
        clearance = (spot - short_k) / em if em else 0
        pop = _pop_proxy(credit, width)
        pain_bonus = 0.0
        if max_pain is not None and abs(max_pain - short_k) <= em:
            pain_bonus = 8.0
        score = _clamp(
            (pop or 0) * 55
            + min(clearance, 2.0) * 15
            + (credit / width) * 20
            + pain_bonus
        )
        legs = [_leg(short_row, "put", "sell"), _leg(long_row, "put", "buy")]
        ideas.append(
            _idea(
                symbol,
                expiration,
                "credit",
                "bull_put_spread",
                f"Bull put {long_k:g}/{short_k:g}",
                legs,
                credit=credit,
                max_profit=credit,
                max_loss=width - credit,
                pop_proxy=pop,
                edge_score=score,
                notes=[
                    f"Short put {clearance:.1f}× expected-move below spot",
                    f"Credit {credit:.2f} on {width:.2f} width",
                ],
                spot=spot,
                expected_move=em,
                max_pain=max_pain,
            )
        )

    # Bear call: sell lower call, buy higher call above spot
    above = [s for s in call_strikes if s > spot]
    for short_k in above[:6]:
        longs = [s for s in above if s > short_k]
        if not longs:
            continue
        long_k = longs[0]
        short_row, long_row = calls[short_k], calls[long_k]
        credit = (_mid(short_row) or 0) - (_mid(long_row) or 0)
        width = long_k - short_k
        if credit <= 0 or width <= 0:
            continue
        clearance = (short_k - spot) / em if em else 0
        pop = _pop_proxy(credit, width)
        pain_bonus = 0.0
        if max_pain is not None and abs(max_pain - short_k) <= em:
            pain_bonus = 8.0
        score = _clamp(
            (pop or 0) * 55
            + min(clearance, 2.0) * 15
            + (credit / width) * 20
            + pain_bonus
        )
        legs = [_leg(short_row, "call", "sell"), _leg(long_row, "call", "buy")]
        ideas.append(
            _idea(
                symbol,
                expiration,
                "credit",
                "bear_call_spread",
                f"Bear call {short_k:g}/{long_k:g}",
                legs,
                credit=credit,
                max_profit=credit,
                max_loss=width - credit,
                pop_proxy=pop,
                edge_score=score,
                notes=[
                    f"Short call {clearance:.1f}× expected-move above spot",
                    f"Credit {credit:.2f} on {width:.2f} width",
                ],
                spot=spot,
                expected_move=em,
                max_pain=max_pain,
            )
        )

    # Iron condors: combine OTM put credit + OTM call credit with similar widths
    put_cands = [s for s in put_strikes if s < spot - 0.5 * em][-4:]
    call_cands = [s for s in call_strikes if s > spot + 0.5 * em][:4]
    for put_short in put_cands:
        put_longs = [s for s in put_strikes if s < put_short]
        if not put_longs:
            continue
        put_long = put_longs[-1]
        for call_short in call_cands:
            call_longs = [s for s in call_strikes if s > call_short]
            if not call_longs:
                continue
            call_long = call_longs[0]
            put_w = put_short - put_long
            call_w = call_long - call_short
            if put_w <= 0 or call_w <= 0:
                continue
            # Prefer similar wing widths
            if abs(put_w - call_w) / max(put_w, call_w) > 0.35:
                continue
            put_credit = (_mid(puts[put_short]) or 0) - (_mid(puts[put_long]) or 0)
            call_credit = (_mid(calls[call_short]) or 0) - (_mid(calls[call_long]) or 0)
            credit = put_credit + call_credit
            width = max(put_w, call_w)
            if credit <= 0:
                continue
            wing_clear = min(spot - put_short, call_short - spot) / em if em else 0
            pop = _pop_proxy(credit, width)
            score = _clamp(
                (pop or 0) * 45
                + min(wing_clear, 2.0) * 20
                + (credit / width) * 25
                + 5
            )
            legs = [
                _leg(puts[put_short], "put", "sell"),
                _leg(puts[put_long], "put", "buy"),
                _leg(calls[call_short], "call", "sell"),
                _leg(calls[call_long], "call", "buy"),
            ]
            ideas.append(
                _idea(
                    symbol,
                    expiration,
                    "credit",
                    "iron_condor",
                    f"Iron condor {put_long:g}/{put_short:g}/{call_short:g}/{call_long:g}",
                    legs,
                    credit=credit,
                    max_profit=credit,
                    max_loss=width - credit,
                    pop_proxy=pop,
                    edge_score=score,
                    notes=[
                        f"Wings ~{wing_clear:.1f}× expected-move from spot",
                        f"Net credit {credit:.2f}; max width {width:.2f}",
                    ],
                    spot=spot,
                    expected_move=em,
                    max_pain=max_pain,
                )
            )
    return ideas


def _debit_verticals(
    symbol: str,
    expiration: str,
    calls: dict[float, dict],
    puts: dict[float, dict],
    spot: float,
    expected_move: Optional[float],
    momentum_3m: Optional[float],
) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    em = expected_move or spot * 0.03
    call_strikes = sorted(calls.keys())
    put_strikes = sorted(puts.keys())
    near_calls = _nearest_strikes(call_strikes, spot, 10)
    near_puts = _nearest_strikes(put_strikes, spot, 10)

    # Bull call debit: buy lower, sell higher
    for i, long_k in enumerate(near_calls[:-1]):
        if long_k > spot + em:
            continue
        short_k = near_calls[i + 1]
        if short_k <= long_k:
            continue
        long_row, short_row = calls[long_k], calls[short_k]
        debit = (_mid(long_row) or 0) - (_mid(short_row) or 0)
        width = short_k - long_k
        if debit <= 0 or width <= 0 or debit >= width:
            continue
        rr = (width - debit) / debit
        mom_bonus = 10.0 if momentum_3m is not None and momentum_3m > 0 else 0.0
        iv = _num(long_row.get("implied_volatility")) or 0.4
        iv_penalty = max(0.0, (iv - 0.35) * 30)
        score = _clamp(min(rr, 3.0) * 22 + (1 - debit / width) * 35 + mom_bonus - iv_penalty)
        legs = [_leg(long_row, "call", "buy"), _leg(short_row, "call", "sell")]
        ideas.append(
            _idea(
                symbol,
                expiration,
                "debit",
                "bull_call_spread",
                f"Bull call {long_k:g}/{short_k:g}",
                legs,
                credit=-debit,
                max_profit=width - debit,
                max_loss=debit,
                pop_proxy=None,
                edge_score=score,
                notes=[
                    f"Debit {debit:.2f} for {width:.2f} width (R/R {rr:.2f})",
                    "Favors upside if momentum/IV supportive",
                ],
                spot=spot,
                expected_move=em,
                max_pain=None,
            )
        )

    # Bear put debit: buy higher put, sell lower put
    for i, long_k in enumerate(near_puts[1:], start=1):
        if long_k < spot - em:
            continue
        short_k = near_puts[i - 1]
        if short_k >= long_k:
            continue
        long_row, short_row = puts[long_k], puts[short_k]
        debit = (_mid(long_row) or 0) - (_mid(short_row) or 0)
        width = long_k - short_k
        if debit <= 0 or width <= 0 or debit >= width:
            continue
        rr = (width - debit) / debit
        mom_bonus = 10.0 if momentum_3m is not None and momentum_3m < 0 else 0.0
        iv = _num(long_row.get("implied_volatility")) or 0.4
        iv_penalty = max(0.0, (iv - 0.35) * 30)
        score = _clamp(min(rr, 3.0) * 22 + (1 - debit / width) * 35 + mom_bonus - iv_penalty)
        legs = [_leg(long_row, "put", "buy"), _leg(short_row, "put", "sell")]
        ideas.append(
            _idea(
                symbol,
                expiration,
                "debit",
                "bear_put_spread",
                f"Bear put {short_k:g}/{long_k:g}",
                legs,
                credit=-debit,
                max_profit=width - debit,
                max_loss=debit,
                pop_proxy=None,
                edge_score=score,
                notes=[
                    f"Debit {debit:.2f} for {width:.2f} width (R/R {rr:.2f})",
                    "Favors downside if momentum/IV supportive",
                ],
                spot=spot,
                expected_move=em,
                max_pain=None,
            )
        )
    return ideas


def _mispricing_flags(
    symbol: str,
    expiration: str,
    calls: dict[float, dict],
    puts: dict[float, dict],
    spot: float,
) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    strikes = sorted(set(calls) & set(puts))

    for k in strikes:
        c, p = calls[k], puts[k]
        c_mid, p_mid = _mid(c), _mid(p)
        if c_mid is None or p_mid is None:
            continue
        # Undiscounted parity: C - P ≈ S - K
        residual = (c_mid - p_mid) - (spot - k)
        abs_res = abs(residual)
        scale = max(abs(spot) * 0.002, 0.05)
        if abs_res >= scale:
            severity = "info"
            if abs_res >= scale * 3:
                severity = "warn"
            if abs_res >= scale * 6:
                severity = "strong"
            score = _clamp(min(abs_res / scale, 10) * 10)
            legs = [_leg(c, "call", "hold"), _leg(p, "put", "hold")]
            ideas.append(
                _idea(
                    symbol,
                    expiration,
                    "mispricing",
                    "put_call_parity",
                    f"Parity residual @ {k:g}",
                    legs,
                    credit=None,
                    max_profit=None,
                    max_loss=None,
                    pop_proxy=None,
                    edge_score=score,
                    notes=[
                        f"Residual (C−P)−(S−K) = {residual:.3f}",
                        f"Severity {severity} — quote anomaly, not arb",
                    ],
                    spot=spot,
                    expected_move=None,
                    max_pain=None,
                    severity=severity,
                    residual=residual,
                )
            )

        # Inverted quotes
        for right, row in (("call", c), ("put", p)):
            bid, ask = _num(row.get("bid")), _num(row.get("ask"))
            if bid is not None and ask is not None and bid > ask > 0:
                legs = [_leg(row, right, "hold")]
                ideas.append(
                    _idea(
                        symbol,
                        expiration,
                        "mispricing",
                        "inverted_quote",
                        f"Inverted {right} quote @ {k:g}",
                        legs,
                        credit=None,
                        max_profit=None,
                        max_loss=None,
                        pop_proxy=None,
                        edge_score=70,
                        notes=[f"Bid {bid} > ask {ask}"],
                        spot=spot,
                        expected_move=None,
                        max_pain=None,
                        severity="warn",
                    )
                )

            last = _num(row.get("last"))
            mid = _mid(row)
            if last is not None and mid is not None and last > 0:
                gap = abs(mid - last) / last
                if gap >= 0.25:
                    legs = [_leg(row, right, "hold")]
                    ideas.append(
                        _idea(
                            symbol,
                            expiration,
                            "mispricing",
                            "mid_vs_last",
                            f"Mid vs last gap @ {k:g} {right}",
                            legs,
                            credit=None,
                            max_profit=None,
                            max_loss=None,
                            pop_proxy=None,
                            edge_score=_clamp(gap * 100),
                            notes=[f"Mid {mid:.2f} vs last {last:.2f} ({gap:.0%})"],
                            spot=spot,
                            expected_move=None,
                            max_pain=None,
                            severity="info" if gap < 0.5 else "warn",
                        )
                    )
    return ideas


def compute_breakevens(
    kind: str,
    legs: list[dict],
    credit_or_debit: Optional[float],
) -> list[float]:
    """Underlying prices where expiration PnL ≈ 0 (per-share premium)."""
    if credit_or_debit is None:
        return []
    puts = sorted(
        [lg for lg in legs if lg.get("right") == "put"],
        key=lambda x: float(x.get("strike") or 0),
    )
    calls = sorted(
        [lg for lg in legs if lg.get("right") == "call"],
        key=lambda x: float(x.get("strike") or 0),
    )
    c = abs(float(credit_or_debit))

    if kind == "bull_put_spread" and len(puts) >= 2:
        short = next((lg for lg in puts if lg.get("action") == "sell"), puts[-1])
        k = _num(short.get("strike"))
        return [_round(k - c)] if k is not None else []
    if kind == "bear_call_spread" and len(calls) >= 2:
        short = next((lg for lg in calls if lg.get("action") == "sell"), calls[0])
        k = _num(short.get("strike"))
        return [_round(k + c)] if k is not None else []
    if kind == "bull_call_spread" and len(calls) >= 2:
        long = next((lg for lg in calls if lg.get("action") == "buy"), calls[0])
        k = _num(long.get("strike"))
        return [_round(k + c)] if k is not None else []
    if kind == "bear_put_spread" and len(puts) >= 2:
        long = next((lg for lg in puts if lg.get("action") == "buy"), puts[-1])
        k = _num(long.get("strike"))
        return [_round(k - c)] if k is not None else []
    if kind == "iron_condor" and len(puts) >= 2 and len(calls) >= 2:
        put_short = next((lg for lg in puts if lg.get("action") == "sell"), puts[-1])
        call_short = next((lg for lg in calls if lg.get("action") == "sell"), calls[0])
        pk, ck = _num(put_short.get("strike")), _num(call_short.get("strike"))
        out = []
        if pk is not None:
            out.append(_round(pk - c))
        if ck is not None:
            out.append(_round(ck + c))
        return [x for x in out if x is not None]
    return []


def _idea(
    symbol: str,
    expiration: str,
    family: str,
    kind: str,
    title: str,
    legs: list[dict],
    *,
    credit: Optional[float],
    max_profit: Optional[float],
    max_loss: Optional[float],
    pop_proxy: Optional[float],
    edge_score: float,
    notes: list[str],
    spot: Optional[float],
    expected_move: Optional[float],
    max_pain: Optional[float],
    severity: Optional[str] = None,
    residual: Optional[float] = None,
) -> dict[str, Any]:
    iid = idea_id(symbol, expiration, kind, legs)
    breakevens = compute_breakevens(kind, legs, credit)
    return {
        "id": iid,
        "symbol": symbol.upper(),
        "family": family,
        "kind": kind,
        "title": title,
        "expiration": expiration,
        "legs": legs,
        "metrics": {
            "credit_or_debit": _round(credit),
            "max_profit": _round(max_profit),
            "max_loss": _round(max_loss),
            "pop_proxy": pop_proxy,
            "edge_score": _round(edge_score, 2),
            "spot": _round(spot),
            "expected_move": _round(expected_move),
            "max_pain": _round(max_pain),
            "breakevens": breakevens,
            "severity": severity,
            "residual": _round(residual, 4),
            "notes": notes,
        },
        "disclaimer": DISCLAIMER,
    }


def generate_strategies(
    symbol: str,
    *,
    expiration: Optional[str] = None,
    limit: int = 20,
    force_refresh: bool = False,
    min_oi: Optional[float] = None,
    min_volume: Optional[float] = None,
    max_spread_pct: Optional[float] = None,
    for_scan: bool = False,
) -> dict[str, Any]:
    symbol = symbol.upper()
    min_oi, min_volume, max_spread_pct = _apply_liquidity_defaults(
        for_scan=for_scan,
        min_oi=min_oi,
        min_volume=min_volume,
        max_spread_pct=max_spread_pct,
    )
    chain = options_payload(
        symbol, expiration=expiration, full_chain=True, force_refresh=force_refresh
    )
    if chain.get("error") and not chain.get("calls") and not chain.get("puts"):
        return {
            "symbol": symbol,
            "expiration": chain.get("expiration"),
            "expirations": chain.get("expirations") or [],
            "spot": chain.get("spot"),
            "ideas": [],
            "freshness": "error",
            "error": chain.get("error"),
            "disclaimer": DISCLAIMER,
            "days_to_earnings": chain.get("days_to_earnings"),
            "next_earnings": chain.get("next_earnings"),
            "iv_context": chain.get("iv_context"),
        }

    exp = chain.get("expiration") or expiration
    earnings = {
        "days_to_earnings": chain.get("days_to_earnings"),
        "next_earnings": chain.get("next_earnings"),
    }
    if earnings["days_to_earnings"] is None:
        earnings = next_earnings_info(symbol)

    cache_key = f"{symbol}:{exp}"
    cached = get_options_strategy_cache(cache_key)
    now = datetime.now(timezone.utc)
    if cached and not force_refresh:
        age_ok = cached["updated_at"] and (now - cached["updated_at"]) <= STRATEGY_TTL
        if age_ok:
            payload = dict(cached["payload"])
            payload["freshness"] = "cached"
            ideas = payload.get("ideas") or []
            filtered = [
                i
                for i in ideas
                if passes_liquidity(
                    i,
                    min_oi=min_oi,
                    min_volume=min_volume,
                    max_spread_pct=max_spread_pct,
                )
            ]
            for idea in filtered:
                annotate_earnings_risk(idea, earnings.get("days_to_earnings"))
            payload["ideas"] = filtered[:limit]
            payload["days_to_earnings"] = earnings.get("days_to_earnings")
            payload["next_earnings"] = earnings.get("next_earnings")
            payload["iv_context"] = chain.get("iv_context") or payload.get("iv_context")
            return payload

    calls = _by_strike(chain.get("calls") or [])
    puts = _by_strike(chain.get("puts") or [])
    spot = _num(chain.get("spot"))
    summary = chain.get("summary") or {}
    em = _num((summary.get("expected_move") or {}).get("expected_move"))
    max_pain = _num(summary.get("max_pain"))

    if spot is None or spot <= 0 or (not calls and not puts):
        return {
            "symbol": symbol,
            "expiration": exp,
            "expirations": chain.get("expirations") or [],
            "spot": spot,
            "ideas": [],
            "freshness": "error",
            "error": "Insufficient chain data to build strategies.",
            "disclaimer": DISCLAIMER,
            "days_to_earnings": earnings.get("days_to_earnings"),
            "next_earnings": earnings.get("next_earnings"),
        }

    snap = get_screen_snapshot(symbol) or {}
    momentum_3m = _num(snap.get("momentum_3m"))

    ideas = []
    ideas.extend(
        _credit_verticals(symbol, exp, calls, puts, spot, em, max_pain)
    )
    ideas.extend(
        _debit_verticals(symbol, exp, calls, puts, spot, em, momentum_3m)
    )
    ideas.extend(_mispricing_flags(symbol, exp, calls, puts, spot))
    ideas.sort(key=lambda x: float(x["metrics"].get("edge_score") or 0), reverse=True)

    # Deduplicate by id
    seen = set()
    unique = []
    for idea in ideas:
        if idea["id"] in seen:
            continue
        seen.add(idea["id"])
        # Always attach liquidity metrics
        passes_liquidity(idea, min_oi=None, min_volume=None, max_spread_pct=None)
        annotate_earnings_risk(idea, earnings.get("days_to_earnings"))
        unique.append(idea)

    payload = {
        "symbol": symbol,
        "expiration": exp,
        "expirations": chain.get("expirations") or [],
        "spot": spot,
        "summary": {
            "max_pain": max_pain,
            "expected_move": em,
            "atm_strike": (summary.get("expected_move") or {}).get("atm_strike"),
        },
        "ideas": unique,
        "fetched_at": now.isoformat(),
        "freshness": "live",
        "stale": False,
        "disclaimer": DISCLAIMER,
        "days_to_earnings": earnings.get("days_to_earnings"),
        "next_earnings": earnings.get("next_earnings"),
        "iv_context": chain.get("iv_context"),
    }
    upsert_options_strategy_cache(
        cache_key, symbol=symbol, expiration=exp or "", payload=payload
    )
    filtered = [
        i
        for i in unique
        if passes_liquidity(
            i,
            min_oi=min_oi,
            min_volume=min_volume,
            max_spread_pct=max_spread_pct,
        )
    ]
    out = dict(payload)
    out["ideas"] = filtered[:limit]
    return out


def strategy_detail(
    symbol: str,
    idea_id_value: str,
    *,
    expiration: Optional[str] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    payload = generate_strategies(
        symbol, expiration=expiration, limit=200, force_refresh=force_refresh
    )
    ideas = payload.get("ideas") or []
    # Also search full cached list
    cache_key = f"{symbol.upper()}:{payload.get('expiration')}"
    cached = get_options_strategy_cache(cache_key)
    if cached and cached.get("payload"):
        ideas = cached["payload"].get("ideas") or ideas

    match = next((i for i in ideas if i.get("id") == idea_id_value), None)
    if not match:
        return {
            "symbol": symbol.upper(),
            "idea": None,
            "payoff": [],
            "greeks": None,
            "scenarios": None,
            "error": "Strategy idea not found. Refresh strategies for this expiration.",
            "disclaimer": DISCLAIMER,
        }
    legs = match.get("legs") or []
    spot = _num((match.get("metrics") or {}).get("spot")) or _num(payload.get("spot"))
    greeks = net_greeks_for_idea(match)
    scenarios = scenario_grid(match)
    return {
        "symbol": symbol.upper(),
        "expiration": payload.get("expiration"),
        "idea": match,
        "payoff": payoff_curve(legs, spot),
        "greeks": greeks,
        "scenarios": scenarios,
        "days_to_earnings": payload.get("days_to_earnings"),
        "next_earnings": payload.get("next_earnings"),
        "disclaimer": DISCLAIMER,
    }


def strategies_scan(
    symbols: Optional[list[str]] = None,
    *,
    expiration: Optional[str] = None,
    limit_per_symbol: int = 5,
    force_refresh: bool = False,
    min_oi: Optional[float] = None,
    min_volume: Optional[float] = None,
    max_spread_pct: Optional[float] = None,
) -> dict[str, Any]:
    raw = symbols or DEFAULT_SCAN_SYMBOLS
    cleaned: list[str] = []
    for s in raw:
        t = "".join(ch for ch in str(s).upper() if ch.isalnum() or ch in ".-")[:12]
        if t and t not in cleaned:
            cleaned.append(t)
        if len(cleaned) >= 15:
            break

    all_ideas: list[dict] = []
    errors: list[dict] = []
    for sym in cleaned:
        try:
            # nearest expiration unless concrete date provided
            exp = None if (not expiration or expiration == "nearest") else expiration
            result = generate_strategies(
                sym,
                expiration=exp,
                limit=limit_per_symbol,
                force_refresh=force_refresh,
                min_oi=min_oi,
                min_volume=min_volume,
                max_spread_pct=max_spread_pct,
                for_scan=True,
            )
            if result.get("error") and not result.get("ideas"):
                errors.append({"symbol": sym, "error": result["error"]})
            for idea in result.get("ideas") or []:
                all_ideas.append(idea)
        except Exception as exc:
            errors.append({"symbol": sym, "error": str(exc)[:200]})

    all_ideas.sort(key=lambda x: float(x["metrics"].get("edge_score") or 0), reverse=True)
    return {
        "symbols": cleaned,
        "ideas": all_ideas,
        "errors": errors,
        "disclaimer": DISCLAIMER,
    }
