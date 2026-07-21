"""Options analytics: max pain, expected move, PCR, contract traded range."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import pandas as pd

from finance_app.db import (
    get_options_chain_cache,
    get_options_contract_cache,
    load_earnings_events,
    load_ohlcv,
    load_options_iv_snapshots,
    upsert_options_chain_cache,
    upsert_options_contract_cache,
    upsert_options_iv_snapshot,
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
TERM_STRUCTURE_MAX = 8
IV_RANK_MIN_SAMPLES = 20
ALLOWED_CONTRACT_PERIODS = {"1mo", "3mo", "6mo", "1y", "ytd", "max"}


def _dte(expiration: str, as_of: Optional[datetime] = None) -> Optional[int]:
    try:
        exp = datetime.strptime(expiration[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    today = (as_of or datetime.now(timezone.utc)).date()
    return (exp - today).days


def atm_iv_from_chain(
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
    spot: Optional[float],
) -> Optional[float]:
    """Average ATM call+put implied volatility."""
    if spot is None or spot <= 0:
        return None
    call = _nearest_by_strike(calls, spot)
    put = _nearest_by_strike(puts, spot)
    if not call or not put:
        return None
    if call.get("strike") != put.get("strike"):
        put = next((p for p in puts if p.get("strike") == call.get("strike")), put)
    vals = [
        v
        for v in (_num(call.get("implied_volatility")), _num(put.get("implied_volatility")))
        if v is not None and v > 0
    ]
    if not vals:
        return None
    return _round(sum(vals) / len(vals), 6)


def snapshot_chain_iv(
    symbol: str,
    expiration: str,
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
    spot: Optional[float],
) -> Optional[float]:
    """Persist today's ATM IV + activity for one expiration; return atm_iv."""
    atm_iv = atm_iv_from_chain(calls, puts, spot)
    totals = compute_put_call_totals(calls, puts)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    upsert_options_iv_snapshot(
        symbol=symbol,
        as_of_date=as_of,
        expiration=expiration,
        dte=_dte(expiration),
        atm_iv=atm_iv,
        spot=spot,
        call_volume=totals.get("call_volume"),
        put_volume=totals.get("put_volume"),
        call_oi=totals.get("call_oi"),
        put_oi=totals.get("put_oi"),
    )
    return atm_iv


def compute_iv_rank_percentile(symbol: str, current_iv: Optional[float]) -> dict[str, Any]:
    """IV rank / percentile from stored snapshots (nearest-expiry series preferred)."""
    end = datetime.now(timezone.utc).date()
    start = (end - timedelta(days=370)).isoformat()
    df = load_options_iv_snapshots(symbol, start=start, end=end.isoformat())
    if df.empty or current_iv is None:
        return {
            "atm_iv": _round(current_iv),
            "iv_rank_1y": None,
            "iv_percentile_1y": None,
            "sample_count": 0,
            "building_history": True,
        }

    # Prefer one row per day: take min-dte expiration that day
    df = df.dropna(subset=["atm_iv"]).copy()
    if df.empty:
        return {
            "atm_iv": _round(current_iv),
            "iv_rank_1y": None,
            "iv_percentile_1y": None,
            "sample_count": 0,
            "building_history": True,
        }
    df = df.sort_values(["as_of_date", "dte"], ascending=[True, True])
    daily = df.groupby("as_of_date", as_index=False).first()
    series = [float(x) for x in daily["atm_iv"].tolist() if x is not None]
    n = len(series)
    if n < IV_RANK_MIN_SAMPLES:
        return {
            "atm_iv": _round(current_iv),
            "iv_rank_1y": None,
            "iv_percentile_1y": None,
            "sample_count": n,
            "building_history": True,
        }

    lo, hi = min(series), max(series)
    iv_rank = None if hi <= lo else (current_iv - lo) / (hi - lo)
    below = sum(1 for v in series if v <= current_iv)
    iv_pct = below / n
    return {
        "atm_iv": _round(current_iv),
        "iv_rank_1y": _round(iv_rank, 4),
        "iv_percentile_1y": _round(iv_pct, 4),
        "sample_count": n,
        "building_history": False,
    }


def build_term_structure(
    symbol: str,
    expirations: list[str],
    spot: Optional[float],
    *,
    primary_expiration: str,
    primary_calls: list[dict[str, Any]],
    primary_puts: list[dict[str, Any]],
    fetch_chain_fn: Callable[..., dict[str, Any]],
    max_expiries: int = TERM_STRUCTURE_MAX,
) -> list[dict[str, Any]]:
    """ATM IV across nearest expirations (rate-limited)."""
    out: list[dict[str, Any]] = []
    chosen = expirations[:max_expiries]
    for exp in chosen:
        if exp == primary_expiration:
            calls, puts = primary_calls, primary_puts
        else:
            try:
                raw = fetch_chain_fn(symbol, exp)
                calls = [enrich_contract(c) for c in raw.get("calls") or []]
                puts = [enrich_contract(p) for p in raw.get("puts") or []]
            except Exception:
                continue
        atm_iv = snapshot_chain_iv(symbol, exp, calls, puts, spot)
        em = compute_expected_move(calls, puts, spot)
        out.append(
            {
                "expiration": exp,
                "dte": _dte(exp),
                "atm_iv": atm_iv,
                "expected_move": em.get("expected_move"),
            }
        )
    return out


def next_earnings_info(symbol: str) -> dict[str, Any]:
    """Upcoming earnings from local earnings_events (may be empty)."""
    empty = {
        "next_earnings": None,
        "days_to_earnings": None,
        "eps_estimate": None,
    }
    try:
        df = load_earnings_events(symbol)
    except Exception:
        return empty
    if df.empty:
        return empty

    today = datetime.now(timezone.utc).date()
    dates = pd.to_datetime(df["report_datetime"], errors="coerce")
    # Stored values may be tz-naive; compare on dates only
    df = df.assign(_report_date=dates.dt.date)
    future = df[df["_report_date"].notna() & (df["_report_date"] >= today)]
    if future.empty:
        return empty

    future = future.sort_values("_report_date")
    row = future.iloc[0]
    report_date = row["_report_date"]
    report_raw = row["report_datetime"]
    report_s = (
        report_raw.isoformat()
        if hasattr(report_raw, "isoformat")
        else str(report_raw)
    )
    return {
        "next_earnings": report_s,
        "days_to_earnings": (report_date - today).days,
        "eps_estimate": _round(row.get("eps_estimate")),
    }


def compute_uoa(
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
    *,
    expiration: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Heuristic unusual activity from volume/OI vs chain median."""
    dte = _dte(expiration) if expiration else None
    rows: list[dict[str, Any]] = []
    for side, contracts in (("call", calls), ("put", puts)):
        for c in contracts:
            vol = _num(c.get("volume")) or 0.0
            oi = _num(c.get("open_interest")) or 0.0
            mid = _num(c.get("mid")) or _num(c.get("last")) or 0.0
            if vol <= 0:
                continue
            oi_eff = max(oi, 1.0)
            vol_oi = vol / oi_eff
            # Cap extreme ratios when OI is tiny
            if oi < 10:
                vol_oi = min(vol_oi, 20.0)
            notional = vol * mid * 100.0
            rows.append(
                {
                    "contract_symbol": c.get("contract_symbol"),
                    "side": side,
                    "strike": c.get("strike"),
                    "expiration": expiration,
                    "dte": dte,
                    "volume": _round(vol, 0),
                    "open_interest": _round(oi, 0),
                    "mid": _round(mid),
                    "implied_volatility": _round(c.get("implied_volatility")),
                    "volume_oi": _round(vol_oi, 4),
                    "premium_notional": _round(notional, 0),
                    "day_low": c.get("day_low"),
                    "day_high": c.get("day_high"),
                }
            )
    if not rows:
        return []

    ratios = sorted(r["volume_oi"] for r in rows if r["volume_oi"] is not None)
    mid_idx = len(ratios) // 2
    median = ratios[mid_idx] if ratios else 1.0
    median = median if median and median > 0 else 1.0

    for r in rows:
        ratio = r["volume_oi"] or 0.0
        # Score 0-100: blend volume/OI vs median and notional size
        rel = ratio / median
        notional = r["premium_notional"] or 0.0
        score = min(100.0, 40.0 * min(rel, 5.0) / 5.0 + 40.0 * min(notional / 250_000.0, 1.0) + 20.0 * min(ratio / 5.0, 1.0))
        r["score"] = _round(score, 1)
        r["vs_median_vol_oi"] = _round(rel, 2)

    rows.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return rows[:limit]


def _expected_move_from_iv(
    spot: Optional[float], atm_iv: Optional[float], dte: Optional[float]
) -> Optional[float]:
    """Approx expected move: spot * IV * sqrt(DTE/365)."""
    if spot is None or atm_iv is None or dte is None:
        return None
    if spot <= 0 or atm_iv <= 0 or dte < 0:
        return None
    return spot * atm_iv * math.sqrt(max(dte, 0.0) / 365.0)


def _daily_iv_frame(
    symbol: str,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    expiration: Optional[str] = None,
) -> pd.DataFrame:
    """One ATM-IV row per as_of_date (nearest DTE unless expiration pinned)."""
    df = load_options_iv_snapshots(
        symbol, start=start, end=end, expiration=expiration
    )
    if df.empty:
        return df
    df = df.copy()
    df = df.sort_values(["as_of_date", "dte"], ascending=[True, True])
    if expiration:
        return df.drop_duplicates(subset=["as_of_date"], keep="first")
    return df.groupby("as_of_date", as_index=False).first()


def _hv_frame(symbol: str, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    """Rolling annualized HV (10/20/30d) aligned to calendar dates."""
    from finance_app.metrics.price_metrics import (
        _price_series,
        daily_returns,
        rolling_volatility,
    )

    # Pad start so rolling windows warm up
    pad_start = start
    if start:
        try:
            pad_start = (
                datetime.strptime(start[:10], "%Y-%m-%d").date() - timedelta(days=60)
            ).isoformat()
        except ValueError:
            pad_start = start
    ohlcv = load_ohlcv(symbol, start=pad_start, end=end)
    if ohlcv.empty:
        return pd.DataFrame(columns=["date", "hv_10", "hv_20", "hv_30"])
    prices = _price_series(ohlcv)
    rets = daily_returns(prices)
    out = pd.DataFrame({"date": [d.strftime("%Y-%m-%d") for d in rets.index]})
    out["hv_10"] = rolling_volatility(rets, window=10).values
    out["hv_20"] = rolling_volatility(rets, window=20).values
    out["hv_30"] = rolling_volatility(rets, window=30).values
    if start:
        out = out[out["date"] >= start[:10]]
    if end:
        out = out[out["date"] <= end[:10]]
    return out.reset_index(drop=True)


def iv_history_payload(
    symbol: str,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    expiration: Optional[str] = None,
) -> dict[str, Any]:
    """ATM IV + HV + PCR/OI history from options_iv_snapshots and ohlcv."""
    symbol = symbol.upper()
    end_d = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_d = start
    if not start_d:
        start_d = (
            datetime.strptime(end_d[:10], "%Y-%m-%d").date() - timedelta(days=370)
        ).isoformat()

    daily = _daily_iv_frame(
        symbol, start=start_d, end=end_d, expiration=expiration
    )
    hv = _hv_frame(symbol, start_d, end_d)
    hv_by_date: dict[str, dict[str, Any]] = {}
    if not hv.empty:
        for _, row in hv.iterrows():
            hv_by_date[str(row["date"])[:10]] = {
                "hv_10": row.get("hv_10"),
                "hv_20": row.get("hv_20"),
                "hv_30": row.get("hv_30"),
            }

    series: list[dict[str, Any]] = []
    for _, r in daily.iterrows():
        d = str(r["as_of_date"])[:10]
        call_oi = _num(r.get("call_oi"))
        put_oi = _num(r.get("put_oi"))
        call_vol = _num(r.get("call_volume"))
        put_vol = _num(r.get("put_volume"))
        atm_iv = _num(r.get("atm_iv"))
        hv_row = hv_by_date.get(d, {})
        hv_20 = _num(hv_row.get("hv_20"))
        pcr_oi = (
            put_oi / call_oi
            if call_oi is not None and put_oi is not None and call_oi > 0
            else None
        )
        pcr_vol = (
            put_vol / call_vol
            if call_vol is not None and put_vol is not None and call_vol > 0
            else None
        )
        total_oi = None
        if call_oi is not None or put_oi is not None:
            total_oi = (call_oi or 0.0) + (put_oi or 0.0)
        premium = None
        if atm_iv is not None and hv_20 is not None:
            premium = atm_iv - hv_20
        series.append(
            {
                "date": d,
                "expiration": r.get("expiration"),
                "dte": int(r["dte"]) if r.get("dte") is not None and not pd.isna(r.get("dte")) else None,
                "atm_iv": _round(atm_iv),
                "spot": _round(r.get("spot")),
                "hv_10": _round(hv_row.get("hv_10")),
                "hv_20": _round(hv_20),
                "hv_30": _round(hv_row.get("hv_30")),
                "iv_hv_premium": _round(premium, 4),
                "call_oi": _round(call_oi, 0),
                "put_oi": _round(put_oi, 0),
                "total_oi": _round(total_oi, 0),
                "call_volume": _round(call_vol, 0),
                "put_volume": _round(put_vol, 0),
                "pcr_oi": _round(pcr_oi, 4),
                "pcr_volume": _round(pcr_vol, 4),
            }
        )

    # Also emit HV-only points when IV is missing so HV line stays continuous
    iv_dates = {p["date"] for p in series}
    for d, hv_row in hv_by_date.items():
        if d in iv_dates:
            continue
        series.append(
            {
                "date": d,
                "expiration": None,
                "dte": None,
                "atm_iv": None,
                "spot": None,
                "hv_10": _round(hv_row.get("hv_10")),
                "hv_20": _round(hv_row.get("hv_20")),
                "hv_30": _round(hv_row.get("hv_30")),
                "iv_hv_premium": None,
                "call_oi": None,
                "put_oi": None,
                "total_oi": None,
                "call_volume": None,
                "put_volume": None,
                "pcr_oi": None,
                "pcr_volume": None,
            }
        )
    series.sort(key=lambda x: x["date"])

    latest_iv = next((p for p in reversed(series) if p.get("atm_iv") is not None), None)
    latest_hv = next((p for p in reversed(series) if p.get("hv_20") is not None), None)
    iv_count = sum(1 for p in series if p.get("atm_iv") is not None)
    premium = None
    if latest_iv and latest_iv.get("atm_iv") is not None and latest_hv and latest_hv.get("hv_20") is not None:
        premium = latest_iv["atm_iv"] - latest_hv["hv_20"]

    earnings = earnings_crush_history(symbol, start=start_d, end=end_d)

    return {
        "symbol": symbol,
        "start": start_d,
        "end": end_d,
        "expiration": expiration,
        "series": series,
        "sample_count": iv_count,
        "building_history": iv_count < IV_RANK_MIN_SAMPLES,
        "latest": {
            "atm_iv": latest_iv.get("atm_iv") if latest_iv else None,
            "hv_20": latest_hv.get("hv_20") if latest_hv else None,
            "iv_hv_premium": _round(premium, 4),
            "pcr_oi": latest_iv.get("pcr_oi") if latest_iv else None,
            "total_oi": latest_iv.get("total_oi") if latest_iv else None,
            "date": latest_iv.get("date") if latest_iv else None,
        },
        "earnings_history": earnings,
        "disclaimer": (
            "ATM IV from collected chain snapshots (grows when options are loaded or "
            "via the IV snapshot job). HV is annualized realized vol from daily closes. "
            "Expected move around earnings uses IV × √(DTE/365) when a pre-event snapshot exists."
        ),
    }


def earnings_crush_history(
    symbol: str,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Past earnings: actual spot move vs IV-implied expected move, pre/post ATM IV."""
    symbol = symbol.upper()
    try:
        events = load_earnings_events(symbol)
    except Exception:
        return []
    if events.empty:
        return []

    ohlcv = load_ohlcv(symbol)
    price_map: dict[date, float] = {}
    if not ohlcv.empty:
        from finance_app.metrics.price_metrics import _price_series

        prices = _price_series(ohlcv)
        for idx, val in prices.items():
            try:
                d = pd.Timestamp(idx).date()
                price_map[d] = float(val)
            except (TypeError, ValueError):
                continue
    price_dates = sorted(price_map.keys())

    # Load a wide IV window around events
    iv_df = load_options_iv_snapshots(symbol)
    if not iv_df.empty:
        iv_df = iv_df.dropna(subset=["atm_iv"]).copy()
        iv_df = iv_df.sort_values(["as_of_date", "dte"], ascending=[True, True])
        iv_daily = iv_df.groupby("as_of_date", as_index=False).first()
        iv_daily["as_of_date"] = iv_daily["as_of_date"].astype(str).str[:10]
    else:
        iv_daily = pd.DataFrame()

    dates = pd.to_datetime(events["report_datetime"], errors="coerce")
    events = events.assign(_report_date=dates.dt.date)
    events = events[events["_report_date"].notna()].sort_values("_report_date")

    start_d = datetime.strptime(start[:10], "%Y-%m-%d").date() if start else None
    end_d = datetime.strptime(end[:10], "%Y-%m-%d").date() if end else None

    def _close_on_or_before(target: date) -> tuple[Optional[date], Optional[float]]:
        for d in reversed(price_dates):
            if d <= target:
                return d, price_map.get(d)
        return None, None

    def _close_on_or_after(target: date) -> tuple[Optional[date], Optional[float]]:
        for d in price_dates:
            if d >= target:
                return d, price_map.get(d)
        return None, None

    def _iv_near(target: date, *, before: bool, window: int = 5) -> Optional[dict[str, Any]]:
        if iv_daily.empty:
            return None
        best = None
        best_dist = None
        for _, row in iv_daily.iterrows():
            try:
                d = datetime.strptime(str(row["as_of_date"])[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if before:
                if d >= target or (target - d).days > window:
                    continue
                dist = (target - d).days
            else:
                if d <= target or (d - target).days > window:
                    continue
                dist = (d - target).days
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = row
        if best is None:
            return None
        dte_raw = best.get("dte")
        dte_val = None
        if dte_raw is not None and not pd.isna(dte_raw):
            dte_val = int(dte_raw)
        return {
            "date": str(best["as_of_date"])[:10],
            "atm_iv": _round(best.get("atm_iv")),
            "spot": _round(best.get("spot")),
            "dte": dte_val,
        }

    rows: list[dict[str, Any]] = []
    for _, ev in events.iterrows():
        report_date = ev["_report_date"]
        if start_d and report_date < start_d:
            continue
        if end_d and report_date > end_d:
            continue

        pre_d, pre_px = _close_on_or_before(report_date - timedelta(days=1))
        post_d, post_px = _close_on_or_after(report_date)
        if post_d == report_date:
            nxt = None
            for d in price_dates:
                if d > report_date:
                    nxt = d
                    break
            if nxt is not None:
                post_d, post_px = nxt, price_map.get(nxt)

        actual_pct = None
        if pre_px is not None and post_px is not None and pre_px > 0:
            actual_pct = (post_px / pre_px) - 1.0

        iv_before = _iv_near(report_date, before=True)
        iv_after = _iv_near(report_date, before=False)
        expected_move = None
        expected_pct = None
        if iv_before:
            # One-session implied move from ATM IV (common earnings comparison)
            expected_move = _expected_move_from_iv(
                iv_before.get("spot") or pre_px,
                iv_before.get("atm_iv"),
                1.0,
            )
            spot_ref = iv_before.get("spot") or pre_px
            if expected_move is not None and spot_ref and spot_ref > 0:
                expected_pct = expected_move / spot_ref

        iv_crush = None
        if (
            iv_before
            and iv_after
            and iv_before.get("atm_iv") is not None
            and iv_after.get("atm_iv") is not None
        ):
            iv_crush = iv_after["atm_iv"] - iv_before["atm_iv"]

        hit = None
        if actual_pct is not None and expected_pct is not None:
            hit = abs(actual_pct) >= expected_pct

        report_raw = ev["report_datetime"]
        report_s = (
            report_raw.isoformat()
            if hasattr(report_raw, "isoformat")
            else str(report_raw)
        )
        rows.append(
            {
                "report_datetime": report_s,
                "report_date": report_date.isoformat(),
                "reported_eps": _round(ev.get("reported_eps")),
                "eps_estimate": _round(ev.get("eps_estimate")),
                "surprise_pct": _round(ev.get("surprise_pct")),
                "pre_close": _round(pre_px),
                "post_close": _round(post_px),
                "actual_move_pct": _round(actual_pct, 4),
                "expected_move": _round(expected_move),
                "expected_move_pct": _round(expected_pct, 4),
                "hit_expected": hit,
                "iv_before": iv_before.get("atm_iv") if iv_before else None,
                "iv_after": iv_after.get("atm_iv") if iv_after else None,
                "iv_crush": _round(iv_crush, 4),
                "iv_before_date": iv_before.get("date") if iv_before else None,
                "iv_after_date": iv_after.get("date") if iv_after else None,
            }
        )

    rows.sort(key=lambda x: x["report_date"], reverse=True)
    return rows[:limit]


def attach_iv_and_earnings(
    payload: dict[str, Any],
    *,
    term_structure: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Mutate/return payload with iv_context + earnings proximity. Never raises."""
    try:
        return _attach_iv_and_earnings(payload, term_structure=term_structure)
    except Exception:
        return payload


def _attach_iv_and_earnings(
    payload: dict[str, Any],
    *,
    term_structure: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    symbol = payload.get("symbol") or ""
    calls = payload.get("calls") or []
    puts = payload.get("puts") or []
    spot = _num(payload.get("spot"))
    atm_iv = atm_iv_from_chain(calls, puts, spot) if (calls or puts) else None
    # Fall back to term structure primary
    if atm_iv is None and term_structure:
        for row in term_structure:
            if row.get("expiration") == payload.get("expiration") and row.get("atm_iv") is not None:
                atm_iv = row["atm_iv"]
                break
        if atm_iv is None and term_structure:
            atm_iv = term_structure[0].get("atm_iv")

    iv_stats = compute_iv_rank_percentile(symbol, atm_iv)
    earnings = next_earnings_info(symbol)
    iv_context = {
        **iv_stats,
        "term_structure": term_structure
        or (
            [
                {
                    "expiration": payload.get("expiration"),
                    "dte": _dte(payload.get("expiration") or ""),
                    "atm_iv": atm_iv,
                    "expected_move": (payload.get("summary") or {})
                    .get("expected_move", {})
                    .get("expected_move")
                    if isinstance((payload.get("summary") or {}).get("expected_move"), dict)
                    else None,
                }
            ]
            if payload.get("expiration")
            else []
        ),
    }
    payload["iv_context"] = iv_context
    payload["next_earnings"] = earnings.get("next_earnings")
    payload["days_to_earnings"] = earnings.get("days_to_earnings")
    payload["eps_estimate"] = earnings.get("eps_estimate")
    summary = dict(payload.get("summary") or {})
    summary["iv_context"] = iv_context
    summary["days_to_earnings"] = earnings.get("days_to_earnings")
    summary["next_earnings"] = earnings.get("next_earnings")
    payload["summary"] = summary
    return payload


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
        # Refresh IV rank / earnings from durable stores without refetching Yahoo
        attach_iv_and_earnings(
            payload,
            term_structure=(payload.get("iv_context") or {}).get("term_structure"),
        )
        if full_chain and "uoa" not in payload:
            payload["uoa"] = compute_uoa(
                payload.get("calls") or [],
                payload.get("puts") or [],
                expiration=expiration,
            )
        if not full_chain:
            payload["calls"] = []
            payload["puts"] = []
            payload.pop("uoa", None)
        return payload

    try:
        raw = fetch_chain_fn(symbol, expiration)
        calls = [enrich_contract(c) for c in raw.get("calls") or []]
        puts = [enrich_contract(p) for p in raw.get("puts") or []]
        summary = build_expiration_summary(calls, puts, spot)
        preview = near_atm_preview(calls, puts, spot)
        snapshot_chain_iv(symbol, expiration, calls, puts, spot)

        term_structure: list[dict[str, Any]]
        if full_chain:
            term_structure = build_term_structure(
                symbol,
                expirations,
                spot,
                primary_expiration=expiration,
                primary_calls=calls,
                primary_puts=puts,
                fetch_chain_fn=fetch_chain_fn,
            )
        else:
            atm_iv = atm_iv_from_chain(calls, puts, spot)
            em = summary.get("expected_move") or {}
            term_structure = [
                {
                    "expiration": expiration,
                    "dte": _dte(expiration),
                    "atm_iv": atm_iv,
                    "expected_move": em.get("expected_move")
                    if isinstance(em, dict)
                    else None,
                }
            ]

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
            "uoa": compute_uoa(calls, puts, expiration=expiration) if full_chain else [],
            "fetched_at": now,
            "freshness": "live",
            "stale": False,
            "disclaimer": disclaimer,
        }
        attach_iv_and_earnings(payload, term_structure=term_structure)
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
            out.pop("uoa", None)
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
            attach_iv_and_earnings(
                payload,
                term_structure=(payload.get("iv_context") or {}).get("term_structure"),
            )
            if not full_chain:
                payload["calls"] = []
                payload["puts"] = []
                payload.pop("uoa", None)
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
