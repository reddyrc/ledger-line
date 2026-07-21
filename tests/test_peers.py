"""Unit tests for live Yahoo peer comparison + cache (no network)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _profile(
    ticker: str,
    *,
    industry: str = "Semiconductors",
    sector: str = "Technology",
    market_cap: float = 1e11,
    pe: float = 20.0,
    roe: float = 0.2,
) -> dict:
    return {
        "ticker": ticker,
        "name": f"{ticker} Corp",
        "sector": sector,
        "industry": industry,
        "price": 100.0,
        "market_cap": market_cap,
        "pe": pe,
        "pb": 5.0,
        "ps": 4.0,
        "roe": roe,
        "net_margin": 0.15,
        "momentum_3m": None,
        "momentum_12m": None,
        "vol_ann": None,
        "max_drawdown_1y": None,
        "error": None,
    }


def _price_series(start: float = 100.0, n: int = 260, growth: float = 1.001):
    dates = pd.bdate_range("2024-01-02", periods=n)
    # Deterministic wobble so realized vol is non-zero.
    prices = [
        start * (growth**i) * (1.0 + 0.01 * ((i % 7) - 3) / 3.0) for i in range(n)
    ]
    return pd.Series(prices, index=dates)


def test_match_screener_value_normalizes_dashes():
    from finance_app.ingest.peers_yfinance import VALID_INDUSTRIES, match_screener_value

    assert match_screener_value("Semiconductors", VALID_INDUSTRIES) == "Semiconductors"
    # hyphen vs em-dash variants
    matched = match_screener_value("Software-Infrastructure", VALID_INDUSTRIES)
    assert matched in VALID_INDUSTRIES
    assert "Software" in matched


def test_rank_by_market_cap():
    from finance_app.ingest.peers_yfinance import rank_by_market_cap

    cands = [
        {"ticker": "NEAR", "market_cap": 1.2e11},
        {"ticker": "FAR", "market_cap": 5e9},
        {"ticker": "SUBJ", "market_cap": 1e11},
        {"ticker": "MID", "market_cap": 9e10},
    ]
    ranked = rank_by_market_cap(1e11, cands, exclude="SUBJ", limit=2)
    assert [r["ticker"] for r in ranked] == ["MID", "NEAR"]


def test_price_metrics_from_series():
    from finance_app.ingest.peers_yfinance import price_metrics_from_series

    m = price_metrics_from_series(_price_series())
    assert m["momentum_3m"] is not None
    assert m["momentum_12m"] is not None
    assert m["vol_ann"] is not None and m["vol_ann"] > 0
    assert m["max_drawdown_1y"] is not None


def test_discover_live_peers_industry(monkeypatch):
    from finance_app.ingest import peers_yfinance as pyf

    def fake_profile(symbol: str):
        return _profile(symbol, market_cap=1e11, pe=25.0, roe=0.3)

    def fake_profiles(symbols, **_kwargs):
        return {
            t: _profile(
                t,
                market_cap=1.1e11 if t == "NEAR" else 5e9,
                pe=18.0 if t == "NEAR" else 40.0,
            )
            for t in symbols
        }

    def fake_screen(*_a, **_k):
        return {
            "quotes": [
                {"symbol": "SUBJ", "marketCap": 1e11, "regularMarketPrice": 100},
                {"symbol": "NEAR", "marketCap": 1.05e11, "regularMarketPrice": 90},
                {"symbol": "FAR", "marketCap": 5e9, "regularMarketPrice": 20},
                {"symbol": "OTHER", "marketCap": 2e11, "regularMarketPrice": 50},
            ]
        }

    def fake_download(tickers, **_kwargs):
        syms = tickers.split()
        frames = {}
        for i, t in enumerate(syms):
            s = _price_series(100 + i)
            frames[t] = pd.DataFrame(
                {"Open": s, "High": s, "Low": s, "Close": s, "Adj Close": s, "Volume": 1e6}
            )
        return pd.concat(frames, axis=1)

    live = pyf.discover_live_peers(
        "SUBJ",
        limit=2,
        fetch_profile=fake_profile,
        fetch_profiles=fake_profiles,
        screen_fn=fake_screen,
        download_fn=fake_download,
    )
    assert live["peer_basis"] == "industry"
    assert live["basis_label"] == "Semiconductors"
    assert live["subject"]["ticker"] == "SUBJ"
    assert live["subject"]["momentum_12m"] is not None
    tickers = [p["ticker"] for p in live["peers"]]
    assert tickers[0] == "NEAR"
    assert len(tickers) == 2
    assert live["peers"][0]["pe"] == 18.0


def test_discover_appends_custom_peer():
    from finance_app.ingest import peers_yfinance as pyf

    def fake_profile(symbol: str):
        return _profile(symbol, market_cap=1e11)

    def fake_profiles(symbols, **_kwargs):
        return {
            t: _profile(
                t,
                industry="Auto Manufacturers" if t == "TSLA" else "Semiconductors",
                sector="Consumer Cyclical" if t == "TSLA" else "Technology",
                market_cap=8e11 if t == "TSLA" else 1.05e11,
            )
            for t in symbols
        }

    def fake_screen(*_a, **_k):
        return {
            "quotes": [
                {"symbol": "SUBJ", "marketCap": 1e11},
                {"symbol": "NEAR", "marketCap": 1.05e11},
            ]
        }

    def fake_download(tickers, **_kwargs):
        frames = {}
        for ticker in tickers.split():
            series = _price_series()
            frames[ticker] = pd.DataFrame(
                {
                    "Close": series,
                    "Adj Close": series,
                }
            )
        return pd.concat(frames, axis=1)

    live = pyf.discover_live_peers(
        "SUBJ",
        limit=3,
        extra_symbols=["TSLA", "NEAR", "SUBJ"],
        fetch_profile=fake_profile,
        fetch_profiles=fake_profiles,
        screen_fn=fake_screen,
        download_fn=fake_download,
    )

    assert [p["ticker"] for p in live["peers"]] == ["NEAR", "TSLA"]
    assert live["peers"][0]["custom"] is False
    assert live["peers"][1]["custom"] is True
    assert live["peers"][1]["industry"] == "Auto Manufacturers"
    assert live["custom_tickers"] == ["TSLA"]


def test_discover_sector_fallback():
    from finance_app.ingest import peers_yfinance as pyf

    def fake_profile(symbol: str):
        row = _profile(symbol, industry=None, sector="Technology")  # type: ignore[arg-type]
        row["industry"] = None
        return row

    def fake_profiles(symbols, **_kwargs):
        return {t: _profile(t, industry=None, sector="Technology") for t in symbols}  # type: ignore

    def fake_screen(*_a, **_k):
        return {
            "quotes": [
                {"symbol": "AAA", "marketCap": 1.05e11, "regularMarketPrice": 10},
                {"symbol": "BBB", "marketCap": 2e11, "regularMarketPrice": 11},
            ]
        }

    def fake_download(tickers, **_kwargs):
        syms = tickers.split()
        s = _price_series()
        if len(syms) == 1:
            return pd.DataFrame(
                {"Open": s, "High": s, "Low": s, "Close": s, "Adj Close": s, "Volume": 1e6}
            )
        frames = {
            t: pd.DataFrame(
                {"Open": s, "High": s, "Low": s, "Close": s, "Adj Close": s, "Volume": 1e6}
            )
            for t in syms
        }
        return pd.concat(frames, axis=1)

    live = pyf.discover_live_peers(
        "SUBJ",
        limit=3,
        fetch_profile=fake_profile,
        fetch_profiles=fake_profiles,
        screen_fn=fake_screen,
        download_fn=fake_download,
    )
    assert live["peer_basis"] == "sector"
    assert live["basis_label"] == "Technology"


def test_peer_comparison_cache_and_stale(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics import peers as peers_mod

    db_path = tmp_path / "peers_live.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    calls = {"n": 0}

    def fake_discover(symbol, limit=12, **_kwargs):
        calls["n"] += 1
        return {
            "subject": _profile(symbol, pe=25.0),
            "peers": [
                _profile("NEAR", market_cap=1.2e11, pe=18.0),
                _profile("FAR", market_cap=5e9, pe=40.0),
            ],
            "peer_basis": "industry",
            "basis_label": "Semiconductors",
            "industry": "Semiconductors",
            "sector": "Technology",
            "peer_count": 2,
        }

    first = peers_mod.compute_peer_comparison("SUBJ", limit=12, discover_fn=fake_discover)
    assert first["freshness"] == "live"
    assert first.get("error") is None
    assert first["peer_basis"] == "industry"
    assert first["subject"]["ticker"] == "SUBJ"
    assert first["peers"][0]["ticker"] == "NEAR"
    assert calls["n"] == 1

    second = peers_mod.compute_peer_comparison("SUBJ", limit=12, discover_fn=fake_discover)
    assert second["freshness"] == "cached"
    assert second["stale"] is False
    assert calls["n"] == 1  # cache hit

    # Expire cache artificially
    key = peers_mod._cache_key("SUBJ", 12)
    cached = db.get_peer_cache(key)
    assert cached is not None
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE peer_cache SET updated_at = ? WHERE cache_key = ?",
            (old, key),
        )

    def boom(symbol, limit=12, **_kwargs):
        calls["n"] += 1
        raise RuntimeError("yahoo down")

    stale = peers_mod.compute_peer_comparison("SUBJ", limit=12, discover_fn=boom)
    assert stale["freshness"] == "stale"
    assert stale["stale"] is True
    assert stale["subject"]["ticker"] == "SUBJ"
    assert "warning" in stale
    assert calls["n"] == 2


def test_peer_comparison_no_cache_error(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics.peers import compute_peer_comparison

    db_path = tmp_path / "peers_err.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    def boom(*_a, **_k):
        raise RuntimeError("no yahoo")

    result = compute_peer_comparison("ZZZZ", discover_fn=boom)
    assert result["subject"] is None
    assert result["freshness"] == "error"
    assert result["error"]
    assert result["peers"] == []


def test_extra_tickers_are_normalized_and_partition_cache(tmp_path, monkeypatch):
    import finance_app.config as cfg
    import finance_app.db as db
    from finance_app.config import Settings
    from finance_app.metrics.peers import compute_peer_comparison

    db_path = tmp_path / "peers_extra.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg.get_settings.cache_clear()
    monkeypatch.setattr(cfg, "get_settings", lambda: Settings(database_path=str(db_path)))
    db.init_db()

    received: list[list[str]] = []

    def fake_discover(symbol, limit=12, extra_symbols=None):
        extras = list(extra_symbols or [])
        received.append(extras)
        peers = [
            {**_profile(t), "custom": True}
            for t in extras
        ]
        return {
            "subject": _profile(symbol),
            "peers": peers,
            "peer_basis": "industry",
            "basis_label": "Semiconductors",
            "industry": "Semiconductors",
            "sector": "Technology",
            "peer_count": 0,
            "custom_tickers": extras,
        }

    result = compute_peer_comparison(
        "SUBJ",
        extra_symbols=[" tsla ", "TSLA", "brk/b", "SUBJ"],
        discover_fn=fake_discover,
    )
    assert received == [["TSLA", "BRKB"]]
    assert result["custom_tickers"] == ["TSLA", "BRKB"]
    assert [p["ticker"] for p in result["peers"]] == ["TSLA", "BRKB"]

    # Same normalized extras reuse cache; a different set gets a separate fetch.
    compute_peer_comparison(
        "SUBJ", extra_symbols=["TSLA", "BRKB"], discover_fn=fake_discover
    )
    assert len(received) == 1
    compute_peer_comparison(
        "SUBJ", extra_symbols=["NVDA"], discover_fn=fake_discover
    )
    assert received[-1] == ["NVDA"]
