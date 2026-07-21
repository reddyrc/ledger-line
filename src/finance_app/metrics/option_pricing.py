"""Black–Scholes pricing and greeks for strategy mark-to-model."""

from __future__ import annotations

import math
from typing import Any, Literal, Optional

Right = Literal["call", "put"]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes(
    spot: float,
    strike: float,
    t_years: float,
    iv: float,
    *,
    right: Right = "call",
    rate: float = 0.04,
) -> dict[str, Optional[float]]:
    """
    European BS price + first-order greeks.
    Returns None greeks when inputs are degenerate (T<=0 or IV<=0).
    """
    if spot <= 0 or strike <= 0:
        return {
            "price": None,
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "rho": None,
        }

    # At/after expiration: intrinsic only
    if t_years <= 1e-8:
        if right == "call":
            intrinsic = max(spot - strike, 0.0)
            delta = 1.0 if spot > strike else (0.5 if spot == strike else 0.0)
        else:
            intrinsic = max(strike - spot, 0.0)
            delta = -1.0 if spot < strike else (-0.5 if spot == strike else 0.0)
        return {
            "price": intrinsic,
            "delta": delta,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "rho": 0.0,
        }

    sigma = max(iv, 1e-6)
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * t_years) / (
        sigma * sqrt_t
    )
    d2 = d1 - sigma * sqrt_t
    pdf = _norm_pdf(d1)

    if right == "call":
        price = spot * _norm_cdf(d1) - strike * math.exp(-rate * t_years) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        rho = strike * t_years * math.exp(-rate * t_years) * _norm_cdf(d2) / 100.0
        theta = (
            -(spot * pdf * sigma) / (2.0 * sqrt_t)
            - rate * strike * math.exp(-rate * t_years) * _norm_cdf(d2)
        ) / 365.0
    else:
        price = strike * math.exp(-rate * t_years) * _norm_cdf(-d2) - spot * _norm_cdf(
            -d1
        )
        delta = _norm_cdf(d1) - 1.0
        rho = -strike * t_years * math.exp(-rate * t_years) * _norm_cdf(-d2) / 100.0
        theta = (
            -(spot * pdf * sigma) / (2.0 * sqrt_t)
            + rate * strike * math.exp(-rate * t_years) * _norm_cdf(-d2)
        ) / 365.0

    gamma = pdf / (spot * sigma * sqrt_t)
    vega = spot * pdf * sqrt_t / 100.0  # per 1 vol point

    return {
        "price": round(price, 6),
        "delta": round(delta, 6),
        "gamma": round(gamma, 6),
        "theta": round(theta, 6),
        "vega": round(vega, 6),
        "rho": round(rho, 6),
    }


def years_to_expiration(expiration: str, as_of: Optional[str] = None) -> float:
    """Calendar years from as_of (YYYY-MM-DD) to expiration date."""
    from datetime import date

    exp = date.fromisoformat(expiration[:10])
    if as_of:
        today = date.fromisoformat(as_of[:10])
    else:
        today = date.today()
    days = (exp - today).days
    return max(days, 0) / 365.0


def leg_bs(
    leg: dict[str, Any],
    spot: float,
    expiration: str,
    *,
    rate: float = 0.04,
    spot_mult: float = 1.0,
    iv_mult: float = 1.0,
) -> dict[str, Optional[float]]:
    """Price/greeks for one strategy leg; sign by buy/sell."""
    strike = float(leg.get("strike") or 0)
    iv = float(leg.get("implied_volatility") or 0)
    right = "put" if str(leg.get("right")).lower() == "put" else "call"
    action = str(leg.get("action") or "buy").lower()
    sign = 1.0 if action == "buy" else -1.0
    t = years_to_expiration(expiration)
    shocked_spot = spot * spot_mult
    shocked_iv = max(iv * iv_mult, 1e-6)
    raw = black_scholes(
        shocked_spot, strike, t, shocked_iv, right=right, rate=rate
    )
    out: dict[str, Optional[float]] = {}
    for key in ("price", "delta", "gamma", "theta", "vega", "rho"):
        val = raw.get(key)
        out[key] = None if val is None else round(sign * float(val), 6)
    out["unsigned_price"] = raw.get("price")
    return out
