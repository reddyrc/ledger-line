"""Live Yahoo Finance peer discovery and metric enrichment."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from yfinance import EquityQuery
from yfinance.const import EQUITY_SCREENER_EQ_MAP

from finance_app.metrics.price_metrics import (
    cumulative_return,
    daily_returns,
    max_drawdown,
    realized_volatility,
)

VALID_INDUSTRIES: set[str] = set().union(*EQUITY_SCREENER_EQ_MAP["industry"].values())
VALID_SECTORS: set[str] = set(EQUITY_SCREENER_EQ_MAP["sector"])

# Cap concurrent Yahoo profile lookups.
_PROFILE_WORKERS = 6
_SCREEN_SIZE = 100


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


def _normalize_label(s: str) -> str:
    return (
        s.replace("—", "-")
        .replace("–", "-")
        .replace("‑", "-")
        .strip()
        .lower()
    )


def match_screener_value(raw: Optional[str], valid: set[str]) -> Optional[str]:
    """Map a Yahoo profile label onto an EquityQuery-valid industry/sector string."""
    if not raw:
        return None
    if raw in valid:
        return raw
    want = _normalize_label(raw)
    for v in valid:
        if _normalize_label(v) == want:
            return v
    return None


def profile_from_info(info: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Normalize a yfinance `.info` dict into peer metric fields."""
    price = (
        _num(info.get("currentPrice"))
        or _num(info.get("regularMarketPrice"))
        or _num(info.get("previousClose"))
    )
    return {
        "ticker": symbol.upper(),
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": _round(price),
        "market_cap": _round(info.get("marketCap")),
        "pe": _round(info.get("trailingPE")),
        "pb": _round(info.get("priceToBook")),
        "ps": _round(info.get("priceToSalesTrailing12Months")),
        "roe": _round(info.get("returnOnEquity")),
        "net_margin": _round(info.get("profitMargins")),
        "momentum_3m": None,
        "momentum_12m": None,
        "vol_ann": None,
        "max_drawdown_1y": None,
        "error": None,
    }


def fetch_yahoo_profile(symbol: str) -> dict[str, Any]:
    """Fetch Yahoo quote summary / info for one ticker."""
    symbol = symbol.upper()
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception as exc:
        return {
            "ticker": symbol,
            "name": None,
            "sector": None,
            "industry": None,
            "price": None,
            "market_cap": None,
            "pe": None,
            "pb": None,
            "ps": None,
            "roe": None,
            "net_margin": None,
            "momentum_3m": None,
            "momentum_12m": None,
            "vol_ann": None,
            "max_drawdown_1y": None,
            "error": str(exc)[:240],
        }
    if not info:
        row = profile_from_info({}, symbol)
        row["error"] = "empty_yahoo_info"
        return row
    return profile_from_info(info, symbol)


def fetch_yahoo_profiles(
    symbols: list[str],
    *,
    max_workers: int = _PROFILE_WORKERS,
    fetch_one: Callable[[str], dict[str, Any]] = fetch_yahoo_profile,
) -> dict[str, dict[str, Any]]:
    """Fetch profiles concurrently; returns {TICKER: profile}."""
    out: dict[str, dict[str, Any]] = {}
    uniq = list(dict.fromkeys(s.upper() for s in symbols if s))
    if not uniq:
        return out
    workers = max(1, min(max_workers, len(uniq)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_one, t): t for t in uniq}
        for fut in as_completed(futs):
            ticker = futs[fut]
            try:
                out[ticker] = fut.result()
            except Exception as exc:
                out[ticker] = {
                    "ticker": ticker,
                    "error": str(exc)[:240],
                    "name": None,
                    "sector": None,
                    "industry": None,
                    "price": None,
                    "market_cap": None,
                    "pe": None,
                    "pb": None,
                    "ps": None,
                    "roe": None,
                    "net_margin": None,
                    "momentum_3m": None,
                    "momentum_12m": None,
                    "vol_ann": None,
                    "max_drawdown_1y": None,
                }
    return out


def _quote_to_candidate(q: dict[str, Any]) -> Optional[dict[str, Any]]:
    symbol = (q.get("symbol") or "").upper()
    if not symbol:
        return None
    price = (
        _num(q.get("regularMarketPrice"))
        or _num(q.get("intradayprice"))
        or _num(q.get("eodprice"))
    )
    mcap = _num(q.get("marketCap")) or _num(q.get("intradaymarketcap"))
    return {
        "ticker": symbol,
        "name": q.get("shortName") or q.get("longName"),
        "price": _round(price),
        "market_cap": _round(mcap),
        "pe": _round(q.get("trailingPE") or q.get("peratio.lasttwelvemonths")),
        "pb": _round(q.get("priceToBook") or q.get("pricebookratio.quarterly")),
        "ps": _round(
            q.get("priceToSalesTrailing12Months")
            or q.get("lastclosemarketcaptotalrevenue.lasttwelvemonths")
        ),
    }


def screen_yahoo_peers(
    *,
    peer_basis: str,
    basis_value: str,
    size: int = _SCREEN_SIZE,
    screen_fn: Optional[Callable[..., dict]] = None,
) -> list[dict[str, Any]]:
    """
    Run Yahoo EquityQuery for US equities matching industry or sector.
    peer_basis: 'industry' | 'sector'
    """
    field = "industry" if peer_basis == "industry" else "sector"
    query = EquityQuery(
        "and",
        [
            EquityQuery("eq", ["region", "us"]),
            EquityQuery("eq", [field, basis_value]),
        ],
    )
    runner = screen_fn or yf.screen
    resp = runner(
        query,
        size=min(250, max(size, 25)),
        sortField="intradaymarketcap",
        sortAsc=False,
    )
    quotes = resp.get("quotes") if isinstance(resp, dict) else None
    if not quotes:
        return []
    out: list[dict[str, Any]] = []
    for q in quotes:
        cand = _quote_to_candidate(q)
        if cand:
            out.append(cand)
    return out


def rank_by_market_cap(
    subject_mcap: Optional[float],
    candidates: list[dict[str, Any]],
    *,
    exclude: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Nearest peers by log market-cap distance."""
    peers = [c for c in candidates if c.get("ticker") and c["ticker"] != exclude.upper()]
    if subject_mcap and subject_mcap > 0:

        def dist(r: dict) -> float:
            m = r.get("market_cap")
            if not m or m <= 0:
                return 1e18
            return abs(math.log(float(m)) - math.log(float(subject_mcap)))

        peers = sorted(peers, key=dist)
    return peers[: max(1, limit)]


def _window_return(prices: pd.Series, trading_days: int) -> Optional[float]:
    if len(prices) < 2:
        return None
    window = prices.iloc[-(trading_days + 1) :] if len(prices) > trading_days else prices
    return _round(cumulative_return(window))


def price_metrics_from_series(prices: pd.Series) -> dict[str, Optional[float]]:
    if prices is None or prices.empty:
        return {
            "momentum_3m": None,
            "momentum_12m": None,
            "vol_ann": None,
            "max_drawdown_1y": None,
        }
    prices = prices.dropna().astype(float).sort_index()
    one_year = prices.iloc[-min(len(prices), 253) :]
    rets = daily_returns(one_year)
    return {
        "momentum_3m": _window_return(prices, 63),
        "momentum_12m": _window_return(prices, 252),
        "vol_ann": _round(realized_volatility(rets)),
        "max_drawdown_1y": _round(max_drawdown(one_year)),
    }


def fetch_batch_price_metrics(
    symbols: list[str],
    *,
    download_fn: Optional[Callable[..., Any]] = None,
) -> dict[str, dict[str, Optional[float]]]:
    """One-shot yfinance download for 1Y history → momentum/vol/drawdown."""
    uniq = list(dict.fromkeys(s.upper() for s in symbols if s))
    empty = {
        "momentum_3m": None,
        "momentum_12m": None,
        "vol_ann": None,
        "max_drawdown_1y": None,
    }
    if not uniq:
        return {}
    downloader = download_fn or yf.download
    try:
        raw = downloader(
            " ".join(uniq),
            period="1y",
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False,
        )
    except Exception:
        return {t: dict(empty) for t in uniq}

    out: dict[str, dict[str, Optional[float]]] = {}
    if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
        return {t: dict(empty) for t in uniq}

    if len(uniq) == 1:
        ticker = uniq[0]
        df = raw
        col = "Adj Close" if "Adj Close" in df.columns else "Close"
        if col in df.columns:
            out[ticker] = price_metrics_from_series(df[col])
        else:
            out[ticker] = dict(empty)
        return out

    # Multi-ticker: columns are (ticker, field) or (field, ticker) depending on yfinance.
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        if uniq[0] in level0 or any(t in level0 for t in uniq):
            for t in uniq:
                if t not in raw.columns.get_level_values(0):
                    out[t] = dict(empty)
                    continue
                sub = raw[t]
                col = "Adj Close" if "Adj Close" in sub.columns else "Close"
                out[t] = (
                    price_metrics_from_series(sub[col])
                    if col in sub.columns
                    else dict(empty)
                )
        else:
            for t in uniq:
                if t not in raw.columns.get_level_values(1):
                    out[t] = dict(empty)
                    continue
                series = raw.xs(t, axis=1, level=1)
                col = "Adj Close" if "Adj Close" in series.columns else "Close"
                out[t] = (
                    price_metrics_from_series(series[col])
                    if col in series.columns
                    else dict(empty)
                )
    else:
        for t in uniq:
            out[t] = dict(empty)
    return out


def discover_live_peers(
    symbol: str,
    *,
    limit: int = 12,
    extra_symbols: Optional[list[str]] = None,
    fetch_profile: Callable[[str], dict[str, Any]] = fetch_yahoo_profile,
    fetch_profiles: Callable[..., dict[str, dict[str, Any]]] = fetch_yahoo_profiles,
    screen_fn: Optional[Callable[..., dict]] = None,
    download_fn: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """
    Resolve same-industry (or sector-fallback) peers and live metrics.

    Returns:
      subject, peers (list), peer_basis ('industry'|'sector'), basis_label,
      peer_count (candidates before limit), industry, sector
    """
    symbol = symbol.upper()
    subject = fetch_profile(symbol)
    if subject.get("error") and subject.get("market_cap") is None and subject.get("price") is None:
        raise RuntimeError(subject.get("error") or "Failed to fetch Yahoo profile")

    industry = match_screener_value(subject.get("industry"), VALID_INDUSTRIES)
    sector = match_screener_value(subject.get("sector"), VALID_SECTORS)

    if industry:
        peer_basis = "industry"
        basis_label = industry
    elif sector:
        peer_basis = "sector"
        basis_label = sector
    else:
        raise RuntimeError(
            "Yahoo did not provide an industry or sector for this ticker; "
            "cannot discover peers."
        )

    try:
        candidates = screen_yahoo_peers(
            peer_basis=peer_basis,
            basis_value=basis_label,
            size=_SCREEN_SIZE,
            screen_fn=screen_fn,
        )
    except Exception as exc:
        raise RuntimeError(f"Yahoo peer screen failed: {exc}") from exc

    # Ensure subject mcap available for ranking; prefer profile.
    subject_mcap = subject.get("market_cap")
    if not subject_mcap:
        for c in candidates:
            if c["ticker"] == symbol and c.get("market_cap"):
                subject_mcap = c["market_cap"]
                subject["market_cap"] = subject_mcap
                break

    ranked = rank_by_market_cap(
        subject_mcap, candidates, exclude=symbol, limit=limit
    )
    automatic_tickers = [p["ticker"] for p in ranked]
    extras = [
        ticker.upper()
        for ticker in (extra_symbols or [])
        if ticker and ticker.upper() != symbol and ticker.upper() not in automatic_tickers
    ]
    peer_tickers = automatic_tickers + list(dict.fromkeys(extras))
    candidates_by_ticker = {row["ticker"]: row for row in ranked}
    for ticker in extras:
        candidates_by_ticker.setdefault(
            ticker,
            {
                "ticker": ticker,
                "name": None,
                "price": None,
                "market_cap": None,
                "pe": None,
                "pb": None,
                "ps": None,
            },
        )

    # Enrich peers with full valuation/profitability from info (bounded concurrency).
    profiles = fetch_profiles(peer_tickers) if peer_tickers else {}
    peers: list[dict[str, Any]] = []
    for t in peer_tickers:
        cand = candidates_by_ticker[t]
        prof = profiles.get(t) or {}
        row = {
            "ticker": t,
            "name": prof.get("name") or cand.get("name"),
            "sector": prof.get("sector") or subject.get("sector"),
            "industry": prof.get("industry") or subject.get("industry"),
            "price": prof.get("price") if prof.get("price") is not None else cand.get("price"),
            "market_cap": (
                prof.get("market_cap")
                if prof.get("market_cap") is not None
                else cand.get("market_cap")
            ),
            "pe": prof.get("pe") if prof.get("pe") is not None else cand.get("pe"),
            "pb": prof.get("pb") if prof.get("pb") is not None else cand.get("pb"),
            "ps": prof.get("ps") if prof.get("ps") is not None else cand.get("ps"),
            "roe": prof.get("roe"),
            "net_margin": prof.get("net_margin"),
            "momentum_3m": None,
            "momentum_12m": None,
            "vol_ann": None,
            "max_drawdown_1y": None,
            "error": prof.get("error"),
            "custom": t in extras,
        }
        peers.append(row)

    # Price-derived metrics for subject + peers in one download.
    all_syms = [symbol] + peer_tickers
    px = fetch_batch_price_metrics(all_syms, download_fn=download_fn)
    for key in ("momentum_3m", "momentum_12m", "vol_ann", "max_drawdown_1y"):
        if symbol in px:
            subject[key] = px[symbol].get(key)
        for p in peers:
            t = p["ticker"]
            if t in px:
                p[key] = px[t].get(key)

    subject["sector"] = subject.get("sector") or sector
    subject["industry"] = subject.get("industry") or industry

    return {
        "subject": subject,
        "peers": peers,
        "peer_basis": peer_basis,
        "basis_label": basis_label,
        "industry": subject.get("industry"),
        "sector": subject.get("sector"),
        "peer_count": len([c for c in candidates if c.get("ticker") != symbol]),
        "custom_tickers": extras,
    }
