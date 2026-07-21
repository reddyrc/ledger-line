"""Options analytics: max pain, expected move, PCR, contract traded range."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import pandas as pd

from finance_app.db import (
    get_options_chain_cache,
    get_options_contract_cache,
    load_ohlcv,
    upsert_options_chain_cache,
    upsert_options_contract_cache,
)
from finance_app.ingest.options_yfinance import (
    fetch_contract_history,
    fetch_option_chain,
    fetch_underlying_spot,
    list_expirations,
)

CHAIN_TTL = timedelta(minutes=5)
CONTRACT_TTL = timedelta(minutes=15)
PREVIEW_STRIKES = 21
ALLOWED_CONTRACT_PERIODS = {"1mo", "3mo", "6mo", "1y", "ytd", "max"}


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


def compute_max_pain(
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
) -> Optional[float]:
    """
    Strike that minimizes total dollar pain to option holders
    (maximize writer value) based on open interest.
    """
    call_oi = {
        _round(c.get("strike")): (_num(c.get("open_interest")) or 0.0)
        for c in calls
        if c.get("strike") is not None
    }
    put_oi = {
        _round(p.get("strike")): (_num(p.get("open_interest")) or 0.0)
        for p in puts
        if p.get("strike") is not None
    }
    strikes = sorted({s for s in list(call_oi) + list(put_oi) if s is not None})
    if not strikes:
        return None

    best_strike = None
    best_pain = None
    for s in strikes:
        pain = 0.0
        for k, oi in call_oi.items():
            if k is not None and s > k:
                pain += (s - k) * oi * 100.0
        for k, oi in put_oi.items():
            if k is not None and s < k:
                pain += (k - s) * oi * 100.0
        if best_pain is None or pain < best_pain:
            best_pain = pain
            best_strike = s
    return best_strike


def compute_put_call_totals(
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
) -> dict[str, Any]:
    call_oi = sum((_num(c.get("open_interest")) or 0.0) for c in calls)
    put_oi = sum((_num(p.get("open_interest")) or 0.0) for p in puts)
    call_vol = sum((_num(c.get("volume")) or 0.0) for c in calls)
    put_vol = sum((_num(p.get("volume")) or 0.0) for p in puts)
    return {
        "call_oi": _round(call_oi, 0),
        "put_oi": _round(put_oi, 0),
        "call_volume": _round(call_vol, 0),
        "put_volume": _round(put_vol, 0),
        "pcr_oi": _round(put_oi / call_oi) if call_oi > 0 else None,
        "pcr_volume": _round(put_vol / call_vol) if call_vol > 0 else None,
    }


def _nearest_by_strike(rows: list[dict[str, Any]], spot: float) -> Optional[dict[str, Any]]:
    best = None
    best_dist = None
    for r in rows:
        strike = _num(r.get("strike"))
        if strike is None:
            continue
        dist = abs(strike - spot)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = r
    return best


def compute_expected_move(
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
    spot: Optional[float],
) -> dict[str, Any]:
    """ATM straddle mid ≈ expected move (approx) through expiration."""
    empty = {
        "atm_strike": None,
        "call_mid": None,
        "put_mid": None,
        "expected_move": None,
        "expected_move_pct": None,
        "price_low": None,
        "price_high": None,
    }
    if spot is None or spot <= 0:
        return empty
    call = _nearest_by_strike(calls, spot)
    put = _nearest_by_strike(puts, spot)
    if not call or not put:
        return empty
    # Prefer matching strikes when possible
    if call.get("strike") != put.get("strike"):
        put = next((p for p in puts if p.get("strike") == call.get("strike")), put)
    c_mid = _num(call.get("mid"))
    p_mid = _num(put.get("mid"))
    if c_mid is None or p_mid is None:
        return {
            **empty,
            "atm_strike": call.get("strike"),
            "call_mid": _round(c_mid),
            "put_mid": _round(p_mid),
        }
    move = c_mid + p_mid
    return {
        "atm_strike": call.get("strike"),
        "call_mid": _round(c_mid),
        "put_mid": _round(p_mid),
        "expected_move": _round(move),
        "expected_move_pct": _round(move / spot),
        "price_low": _round(spot - move),
        "price_high": _round(spot + move),
    }


def contract_breakeven(side: str, strike: Optional[float], premium: Optional[float]) -> Optional[float]:
    if strike is None or premium is None:
        return None
    if side == "call":
        return _round(strike + premium)
    if side == "put":
        return _round(strike - premium)
    return None


def enrich_contract(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    premium = out.get("mid") if out.get("mid") is not None else out.get("last")
    out["breakeven"] = contract_breakeven(out.get("side") or "", out.get("strike"), premium)
    return out


def near_atm_preview(
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
    spot: Optional[float],
    *,
    width: int = PREVIEW_STRIKES,
) -> list[dict[str, Any]]:
    """Unified strike rows near ATM for summary preview."""
    call_by = {c.get("strike"): enrich_contract(c) for c in calls if c.get("strike") is not None}
    put_by = {p.get("strike"): enrich_contract(p) for p in puts if p.get("strike") is not None}
    strikes = sorted(set(call_by) | set(put_by))
    if not strikes:
        return []
    if spot is None:
        mid_idx = len(strikes) // 2
    else:
        mid_idx = min(range(len(strikes)), key=lambda i: abs(float(strikes[i]) - spot))
    half = max(1, width // 2)
    lo = max(0, mid_idx - half)
    hi = min(len(strikes), lo + width)
    lo = max(0, hi - width)
    out = []
    for s in strikes[lo:hi]:
        out.append(
            {
                "strike": s,
                "call": call_by.get(s),
                "put": put_by.get(s),
            }
        )
    return out


def build_expiration_summary(
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
    spot: Optional[float],
) -> dict[str, Any]:
    expected = compute_expected_move(calls, puts, spot)
    return {
        "max_pain": compute_max_pain(calls, puts),
        "expected_move": expected,
        "totals": compute_put_call_totals(calls, puts),
        "atm_strike": expected.get("atm_strike"),
    }


def traded_range_from_history(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        return {
            "traded_low": None,
            "traded_high": None,
            "traded_last": None,
            "series": [],
        }
    lows = [_num(v) for v in df["low"].tolist()]
    highs = [_num(v) for v in df["high"].tolist()]
    closes = [_num(v) for v in df["close"].tolist()]
    valid_lows = [v for v in lows if v is not None]
    valid_highs = [v for v in highs if v is not None]
    series = []
    for _, r in df.iterrows():
        d = r["date"]
        series.append(
            {
                "date": d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10],
                "open": _round(r.get("open")),
                "high": _round(r.get("high")),
                "low": _round(r.get("low")),
                "close": _round(r.get("close")),
                "volume": _round(r.get("volume"), 0),
            }
        )
    return {
        "traded_low": _round(min(valid_lows)) if valid_lows else None,
        "traded_high": _round(max(valid_highs)) if valid_highs else None,
        "traded_last": _round(closes[-1]) if closes and closes[-1] is not None else None,
        "series": series,
    }


def _spot_for_symbol(symbol: str) -> Optional[float]:
    ohlcv = load_ohlcv(symbol)
    if not ohlcv.empty:
        col = (
            "adj_close"
            if "adj_close" in ohlcv.columns and ohlcv["adj_close"].notna().any()
            else "close"
        )
        return _round(ohlcv.iloc[-1][col])
    return fetch_underlying_spot(symbol)


def _fresh(updated_at: Optional[datetime], ttl: timedelta) -> bool:
    if not updated_at:
        return False
    now = datetime.now(timezone.utc)
    ts = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    return (now - ts) <= ttl


def options_payload(
    symbol: str,
    *,
    expiration: Optional[str] = None,
    full_chain: bool = False,
    force_refresh: bool = False,
    list_exp_fn: Callable[..., list[str]] = list_expirations,
    fetch_chain_fn: Callable[..., dict[str, Any]] = fetch_option_chain,
) -> dict[str, Any]:
    """Summary (+ optional full chain) for a symbol/expiration."""
    symbol = symbol.upper()
    disclaimer = (
        "Options data from Yahoo Finance via yfinance. Max pain uses open interest; "
        "expected move approximates the ATM straddle mid. Not for live trading."
    )
    try:
        expirations = list_exp_fn(symbol)
    except Exception as exc:
        return {
            "symbol": symbol,
            "expirations": [],
            "expiration": None,
            "spot": None,
            "summary": None,
            "preview": [],
            "calls": [],
            "puts": [],
            "freshness": "error",
            "stale": False,
            "error": str(exc),
            "disclaimer": disclaimer,
        }

    if not expirations:
        return {
            "symbol": symbol,
            "expirations": [],
            "expiration": None,
            "spot": _spot_for_symbol(symbol),
            "summary": None,
            "preview": [],
            "calls": [],
            "puts": [],
            "freshness": "error",
            "stale": False,
            "error": "No option expirations available for this symbol.",
            "disclaimer": disclaimer,
        }

    expiration = (expiration or expirations[0])[:10]
    if expiration not in expirations:
        # allow requested date even if list drifted; else fall back
        expiration = expirations[0]

    cache_key = f"{symbol}:{expiration}"
    cached = get_options_chain_cache(cache_key)
    spot = _spot_for_symbol(symbol)

    if cached and not force_refresh and _fresh(cached.get("updated_at"), CHAIN_TTL):
        payload = dict(cached["payload"])
        payload["freshness"] = "cached"
        payload["stale"] = False
        payload["fetched_at"] = cached["updated_at"].isoformat()
        payload["spot"] = spot or payload.get("spot")
        if not full_chain:
            payload["calls"] = []
            payload["puts"] = []
        return payload

    try:
        raw = fetch_chain_fn(symbol, expiration)
        calls = [enrich_contract(c) for c in raw.get("calls") or []]
        puts = [enrich_contract(p) for p in raw.get("puts") or []]
        summary = build_expiration_summary(calls, puts, spot)
        preview = near_atm_preview(calls, puts, spot)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "symbol": symbol,
            "expirations": expirations,
            "expiration": expiration,
            "spot": spot,
            "summary": summary,
            "preview": preview,
            "calls": calls,
            "puts": puts,
            "fetched_at": now,
            "freshness": "live",
            "stale": False,
            "disclaimer": disclaimer,
        }
        upsert_options_chain_cache(
            cache_key,
            symbol=symbol,
            expiration=expiration,
            spot=spot,
            payload=payload,
        )
        if not full_chain:
            out = dict(payload)
            out["calls"] = []
            out["puts"] = []
            return out
        return payload
    except Exception as exc:
        if cached and cached.get("payload"):
            payload = dict(cached["payload"])
            payload["freshness"] = "stale"
            payload["stale"] = True
            payload["warning"] = f"Live options fetch failed; showing cached chain. ({exc})"
            payload["fetched_at"] = (
                cached["updated_at"].isoformat() if cached.get("updated_at") else None
            )
            payload["spot"] = spot or payload.get("spot")
            if not full_chain:
                payload["calls"] = []
                payload["puts"] = []
            return payload
        return {
            "symbol": symbol,
            "expirations": expirations,
            "expiration": expiration,
            "spot": spot,
            "summary": None,
            "preview": [],
            "calls": [],
            "puts": [],
            "freshness": "error",
            "stale": False,
            "error": f"Unable to load options chain: {exc}",
            "disclaimer": disclaimer,
        }


def options_contract_payload(
    symbol: str,
    contract_symbol: str,
    *,
    period: str = "3mo",
    side: Optional[str] = None,
    strike: Optional[float] = None,
    day_low: Optional[float] = None,
    day_high: Optional[float] = None,
    force_refresh: bool = False,
    fetch_history_fn: Callable[..., pd.DataFrame] = fetch_contract_history,
) -> dict[str, Any]:
    """Historical traded premium range for one OCC contract."""
    symbol = symbol.upper()
    contract_symbol = contract_symbol.upper()
    period = period if period in ALLOWED_CONTRACT_PERIODS else "3mo"
    cache_key = f"{contract_symbol}:{period}"
    cached = get_options_contract_cache(cache_key)

    if cached and not force_refresh and _fresh(cached.get("updated_at"), CONTRACT_TTL):
        payload = dict(cached["payload"])
        payload["freshness"] = "cached"
        payload["stale"] = False
        if day_low is not None:
            payload["session_day_low"] = _round(day_low)
        if day_high is not None:
            payload["session_day_high"] = _round(day_high)
        return payload

    try:
        hist = fetch_history_fn(contract_symbol, period=period)
        rng = traded_range_from_history(hist)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "symbol": symbol,
            "contract_symbol": contract_symbol,
            "period": period,
            "side": side,
            "strike": _round(strike),
            "session_day_low": _round(day_low),
            "session_day_high": _round(day_high),
            "traded_low": rng["traded_low"],
            "traded_high": rng["traded_high"],
            "traded_last": rng["traded_last"],
            "series": rng["series"],
            "fetched_at": now,
            "freshness": "live",
            "stale": False,
            "disclaimer": (
                "Contract history from Yahoo Finance. Traded range is the high/low of "
                "daily option premiums over the selected period."
            ),
        }
        upsert_options_contract_cache(
            cache_key,
            contract_symbol=contract_symbol,
            period=period,
            payload=payload,
        )
        return payload
    except Exception as exc:
        if cached and cached.get("payload"):
            payload = dict(cached["payload"])
            payload["freshness"] = "stale"
            payload["stale"] = True
            payload["warning"] = f"Live contract history failed; showing cache. ({exc})"
            if day_low is not None:
                payload["session_day_low"] = _round(day_low)
            if day_high is not None:
                payload["session_day_high"] = _round(day_high)
            return payload
        return {
            "symbol": symbol,
            "contract_symbol": contract_symbol,
            "period": period,
            "side": side,
            "strike": _round(strike),
            "session_day_low": _round(day_low),
            "session_day_high": _round(day_high),
            "traded_low": None,
            "traded_high": None,
            "traded_last": None,
            "series": [],
            "freshness": "error",
            "stale": False,
            "error": f"Unable to load contract history: {exc}",
        }
