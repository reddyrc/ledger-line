"""Same-industry (or sector-fallback) peer comparison from live Yahoo data."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np

from finance_app.db import get_peer_cache, upsert_peer_cache
from finance_app.ingest.peers_yfinance import discover_live_peers

PEER_TTL = timedelta(minutes=15)

PEER_METRICS = [
    "pe",
    "pb",
    "ps",
    "roe",
    "net_margin",
    "momentum_3m",
    "momentum_12m",
    "vol_ann",
    "max_drawdown_1y",
    "market_cap",
]

HIGHER_IS_BETTER = {
    "pe": False,
    "pb": False,
    "ps": False,
    "roe": True,
    "net_margin": True,
    "momentum_3m": True,
    "momentum_12m": True,
    "vol_ann": False,
    "max_drawdown_1y": True,
    "market_cap": True,
}


def _round(v: Any, nd: int = 6) -> Optional[float]:
    if v is None:
        return None
    try:
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            return None
        return round(fv, nd)
    except (TypeError, ValueError):
        return None


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return _round(float(np.median(values)))


def _percentile_rank(
    value: Optional[float], pool: list[float], higher_better: bool
) -> Optional[float]:
    if value is None or not pool:
        return None
    arr = np.array(pool, dtype=float)
    if higher_better:
        rank = float(np.mean(arr <= value))
    else:
        rank = float(np.mean(arr >= value))
    return round(rank, 4)


def _row_metrics(row: dict) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "price": _round(row.get("price")),
        "custom": bool(row.get("custom")),
    }
    for m in PEER_METRICS:
        out[m] = _round(row.get(m))
    return out


def normalize_extra_symbols(symbol: str, extras: Optional[list[str]]) -> list[str]:
    """Normalize, deduplicate, and cap user-added peer tickers."""
    subject = symbol.upper()
    out: list[str] = []
    for raw in extras or []:
        ticker = re.sub(r"[^A-Z0-9.-]", "", str(raw).strip().upper())[:12]
        if ticker and ticker != subject and ticker not in out:
            out.append(ticker)
        if len(out) >= 10:
            break
    return out


def _cache_key(symbol: str, limit: int, extra_symbols: Optional[list[str]] = None) -> str:
    extras = ",".join(extra_symbols or [])
    return f"{symbol.upper()}:{int(limit)}:{extras}"


def _build_payload_from_live(live: dict[str, Any], symbol: str, limit: int) -> dict[str, Any]:
    subject = live["subject"]
    peers = live["peers"]
    cohort = [subject] + peers

    sector_stats: dict[str, Any] = {}
    for metric in PEER_METRICS:
        vals = [
            float(r[metric])
            for r in cohort
            if r.get(metric) is not None and np.isfinite(float(r[metric]))
        ]
        subj_v = _round(subject.get(metric))
        sector_stats[metric] = {
            "median": _median(vals),
            "count": len(vals),
            "subject": subj_v,
            "percentile": _percentile_rank(
                subj_v, vals, HIGHER_IS_BETTER.get(metric, True)
            ),
        }

    now = datetime.now(timezone.utc).isoformat()
    basis = live["peer_basis"]
    label = live["basis_label"]
    return {
        "symbol": symbol.upper(),
        "sector": live.get("sector") or subject.get("sector"),
        "industry": live.get("industry") or subject.get("industry"),
        "peer_basis": basis,
        "basis_label": label,
        "subject": _row_metrics(subject),
        "peers": [_row_metrics(p) for p in peers],
        "sector_stats": sector_stats,
        "peer_count": live.get("peer_count", len(peers)),
        "custom_tickers": live.get("custom_tickers", []),
        "fetched_at": now,
        "freshness": "live",
        "stale": False,
        "disclaimer": (
            f"Peers are US equities in the same Yahoo {basis} ({label}), "
            "ranked by market-cap proximity. Valuation and profitability come from "
            "Yahoo quote summary; momentum/vol/drawdown from trailing 1Y prices. "
            "Cached for 15 minutes."
        ),
    }


def compute_peer_comparison(
    symbol: str,
    *,
    limit: int = 12,
    extra_symbols: Optional[list[str]] = None,
    force_refresh: bool = False,
    discover_fn=discover_live_peers,
) -> dict[str, Any]:
    """
    Compare symbol to live Yahoo industry peers (sector fallback).

    Serves SQLite cache when younger than 15 minutes. On Yahoo failure, returns
    the last cached payload marked stale when available.
    """
    symbol = symbol.upper()
    limit = max(3, min(40, int(limit)))
    extras = normalize_extra_symbols(symbol, extra_symbols)
    key = _cache_key(symbol, limit, extras)
    cached = get_peer_cache(key)
    now = datetime.now(timezone.utc)

    if cached and not force_refresh:
        age_ok = cached["updated_at"] and (now - cached["updated_at"]) <= PEER_TTL
        if age_ok:
            payload = dict(cached["payload"])
            payload["freshness"] = "cached"
            payload["stale"] = False
            payload["fetched_at"] = cached["updated_at"].isoformat()
            payload.pop("error", None)
            return payload

    try:
        live = discover_fn(symbol, limit=limit, extra_symbols=extras)
        payload = _build_payload_from_live(live, symbol, limit)
        upsert_peer_cache(
            key,
            symbol=symbol,
            peer_limit=limit,
            peer_basis=payload["peer_basis"],
            payload=payload,
        )
        return payload
    except Exception as exc:
        if cached and cached.get("payload"):
            payload = dict(cached["payload"])
            payload["freshness"] = "stale"
            payload["stale"] = True
            payload["fetched_at"] = (
                cached["updated_at"].isoformat() if cached["updated_at"] else None
            )
            payload["warning"] = (
                f"Live Yahoo peer fetch failed; showing last cached result. ({exc})"
            )
            return payload
        return {
            "symbol": symbol,
            "sector": None,
            "industry": None,
            "peer_basis": None,
            "basis_label": None,
            "subject": None,
            "peers": [],
            "sector_stats": {},
            "peer_count": 0,
            "custom_tickers": extras,
            "fetched_at": None,
            "freshness": "error",
            "stale": False,
            "error": f"Unable to load live peers from Yahoo: {exc}",
            "disclaimer": (
                "Peers are discovered live from Yahoo Finance (same industry when "
                "available, otherwise same sector), ranked by market-cap proximity."
            ),
        }
