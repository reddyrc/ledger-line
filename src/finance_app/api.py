from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from finance_app.ingest.fred import DEFAULT_SERIES
from finance_app.metrics.option_strategies import (
    strategies_scan,
    strategy_detail,
    generate_strategies,
)
from finance_app.metrics.options import options_contract_payload, options_payload
from finance_app.metrics.peers import compute_peer_comparison
from finance_app.services import (
    bootstrap_macro,
    earnings_calendar_payload,
    fundamentals_payload,
    macro_payload,
    screen_payload,
    screen_refresh_payload,
    screen_sectors_payload,
    short_interest_payload,
    symbol_history,
    symbol_metrics,
    symbol_rolling,
    symbol_technicals,
    valuation_history_payload,
)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/symbols/{symbol}/history")
def get_history(
    symbol: str,
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    refresh: bool = Query(False, description="Force re-fetch from free price sources"),
) -> dict:
    return symbol_history(symbol, start=start, end=end, force_refresh=refresh)


@router.get("/symbols/{symbol}/metrics")
def get_metrics(
    symbol: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    benchmark: Optional[str] = Query(None, description="Benchmark ticker, default SPY"),
    refresh: bool = False,
) -> dict:
    result = symbol_metrics(
        symbol, start=start, end=end, benchmark=benchmark, force_refresh=refresh
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/symbols/{symbol}/technicals")
def get_technicals(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    refresh: bool = False,
) -> dict:
    result = symbol_technicals(symbol, start=start, end=end, force_refresh=refresh)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/symbols/{symbol}/rolling")
def get_rolling(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    window: int = Query(63, ge=5, le=504),
    refresh: bool = False,
) -> dict:
    return symbol_rolling(
        symbol, start=start, end=end, window=window, force_refresh=refresh
    )


@router.get("/symbols/{symbol}/fundamentals")
def get_fundamentals(
    symbol: str,
    refresh: bool = Query(False, description="Re-pull SEC EDGAR companyfacts"),
) -> dict:
    result = fundamentals_payload(symbol, refresh=refresh)
    if result.get("error") and not result.get("raw"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/symbols/{symbol}/valuation-history")
def get_valuation_history(
    symbol: str,
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    refresh: bool = Query(
        False, description="Re-fetch prices and SEC EDGAR companyfacts"
    ),
) -> dict:
    result = valuation_history_payload(
        symbol, start=start, end=end, force_refresh=refresh
    )
    if result.get("error") and not result.get("series"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/symbols/{symbol}/short-interest")
def get_short_interest(
    symbol: str,
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    refresh: bool = Query(False, description="Force re-fetch from FINRA"),
) -> dict:
    result = short_interest_payload(
        symbol, start=start, end=end, force_refresh=refresh
    )
    if result.get("error") and not result.get("series") and not result.get("latest"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/symbols/{symbol}/peers")
def get_peers(
    symbol: str,
    limit: int = Query(12, ge=3, le=40, description="Nearest same-industry peers by market cap"),
    extra: Optional[str] = Query(
        None, description="Comma-separated user-added peer tickers (maximum 10)"
    ),
    refresh: bool = Query(False, description="Bypass 15-minute peer cache"),
) -> dict:
    extras = extra.split(",") if extra else []
    return compute_peer_comparison(
        symbol,
        limit=limit,
        extra_symbols=extras,
        force_refresh=refresh,
    )


@router.get("/symbols/{symbol}/options")
def get_options(
    symbol: str,
    expiration: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to nearest"),
    refresh: bool = Query(False, description="Bypass 5-minute options chain cache"),
) -> dict:
    return options_payload(
        symbol, expiration=expiration, full_chain=False, force_refresh=refresh
    )


@router.get("/symbols/{symbol}/options/chain")
def get_options_chain(
    symbol: str,
    expiration: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to nearest"),
    refresh: bool = Query(False, description="Bypass 5-minute options chain cache"),
) -> dict:
    return options_payload(
        symbol, expiration=expiration, full_chain=True, force_refresh=refresh
    )


@router.get("/symbols/{symbol}/options/contract")
def get_options_contract(
    symbol: str,
    contract: str = Query(..., description="OCC option contract symbol"),
    period: str = Query("3mo", description="History window: 1mo, 3mo, 6mo, 1y, ytd, max"),
    side: Optional[str] = Query(None),
    strike: Optional[float] = Query(None),
    day_low: Optional[float] = Query(None),
    day_high: Optional[float] = Query(None),
    refresh: bool = Query(False),
) -> dict:
    return options_contract_payload(
        symbol,
        contract,
        period=period,
        side=side,
        strike=strike,
        day_low=day_low,
        day_high=day_high,
        force_refresh=refresh,
    )


@router.get("/symbols/{symbol}/options/strategies")
def get_option_strategies(
    symbol: str,
    expiration: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to nearest"),
    limit: int = Query(20, ge=1, le=50),
    refresh: bool = Query(False),
    min_oi: Optional[float] = Query(None, description="Min open interest on every leg"),
    min_volume: Optional[float] = Query(None, description="Min volume on every leg"),
    max_spread_pct: Optional[float] = Query(
        None, description="Max (ask-bid)/mid across legs"
    ),
) -> dict:
    return generate_strategies(
        symbol,
        expiration=expiration,
        limit=limit,
        force_refresh=refresh,
        min_oi=min_oi,
        min_volume=min_volume,
        max_spread_pct=max_spread_pct,
    )


@router.get("/symbols/{symbol}/options/strategies/{idea_id}")
def get_option_strategy_detail(
    symbol: str,
    idea_id: str,
    expiration: Optional[str] = Query(None),
    refresh: bool = Query(False),
) -> dict:
    result = strategy_detail(
        symbol, idea_id, expiration=expiration, force_refresh=refresh
    )
    if result.get("error") and not result.get("idea"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/symbols/{symbol}/options/uoa")
def get_options_uoa(
    symbol: str,
    expiration: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    refresh: bool = Query(False),
) -> dict:
    chain = options_payload(
        symbol, expiration=expiration, full_chain=True, force_refresh=refresh
    )
    from finance_app.metrics.options import compute_uoa

    rows = chain.get("uoa") or compute_uoa(
        chain.get("calls") or [],
        chain.get("puts") or [],
        expiration=chain.get("expiration"),
        limit=limit,
    )
    return {
        "symbol": symbol.upper(),
        "expiration": chain.get("expiration"),
        "rows": rows[:limit],
        "freshness": chain.get("freshness"),
        "disclaimer": (
            "Heuristic unusual activity from same-day volume/OI vs chain median — "
            "not confirmed block prints."
        ),
        "error": chain.get("error"),
    }


@router.get("/strategies/scan")
def scan_strategies(
    symbols: Optional[str] = Query(
        None, description="Comma-separated tickers (max 15); default liquid watchlist"
    ),
    expiration: Optional[str] = Query(
        "nearest", description="nearest or YYYY-MM-DD"
    ),
    limit_per_symbol: int = Query(5, ge=1, le=15),
    refresh: bool = Query(False),
    min_oi: Optional[float] = Query(None),
    min_volume: Optional[float] = Query(None),
    max_spread_pct: Optional[float] = Query(None),
) -> dict:
    tickers = [s.strip() for s in symbols.split(",")] if symbols else None
    return strategies_scan(
        tickers,
        expiration=expiration,
        limit_per_symbol=limit_per_symbol,
        force_refresh=refresh,
        min_oi=min_oi,
        min_volume=min_volume,
        max_spread_pct=max_spread_pct,
    )


@router.get("/earnings/calendar")
def get_earnings_calendar(
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    symbols: Optional[str] = Query(
        None, description="Comma-separated tickers; default liquid watchlist"
    ),
    refresh: bool = Query(False, description="Refresh Yahoo earnings for listed symbols"),
) -> dict:
    tickers = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    return earnings_calendar_payload(
        start=start, end=end, symbols=tickers, refresh=refresh
    )


@router.get("/screen")
def get_screen(
    q: Optional[str] = Query(None, description="Ticker or name search"),
    sector: Optional[str] = Query(None),
    pe_min: Optional[float] = None,
    pe_max: Optional[float] = None,
    pb_min: Optional[float] = None,
    pb_max: Optional[float] = None,
    ps_min: Optional[float] = None,
    ps_max: Optional[float] = None,
    roe_min: Optional[float] = None,
    roe_max: Optional[float] = None,
    market_cap_min: Optional[float] = None,
    market_cap_max: Optional[float] = None,
    momentum_3m_min: Optional[float] = None,
    momentum_3m_max: Optional[float] = None,
    momentum_12m_min: Optional[float] = None,
    momentum_12m_max: Optional[float] = None,
    vol_ann_min: Optional[float] = None,
    vol_ann_max: Optional[float] = None,
    max_drawdown_1y_min: Optional[float] = None,
    max_drawdown_1y_max: Optional[float] = None,
    sort: str = Query("momentum_12m"),
    order: str = Query("desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    return screen_payload(
        q=q,
        sector=sector,
        pe_min=pe_min,
        pe_max=pe_max,
        pb_min=pb_min,
        pb_max=pb_max,
        ps_min=ps_min,
        ps_max=ps_max,
        roe_min=roe_min,
        roe_max=roe_max,
        market_cap_min=market_cap_min,
        market_cap_max=market_cap_max,
        momentum_3m_min=momentum_3m_min,
        momentum_3m_max=momentum_3m_max,
        momentum_12m_min=momentum_12m_min,
        momentum_12m_max=momentum_12m_max,
        vol_ann_min=vol_ann_min,
        vol_ann_max=vol_ann_max,
        max_drawdown_1y_min=max_drawdown_1y_min,
        max_drawdown_1y_max=max_drawdown_1y_max,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )


@router.get("/screen/sectors")
def get_screen_sectors() -> dict:
    return screen_sectors_payload()


@router.post("/screen/refresh")
def post_screen_refresh(
    limit: Optional[int] = Query(
        None, description="Process only N tickers (for partial/dev runs)"
    ),
    offset: int = Query(0, ge=0),
    sleep: float = Query(0.25, ge=0, le=5),
    skip_fundamentals: bool = Query(False),
) -> dict:
    """Rebuild screener snapshots. Can take a long time for full S&P 500."""
    return screen_refresh_payload(
        limit=limit,
        offset=offset,
        sleep_s=sleep,
        skip_fundamentals=skip_fundamentals,
    )


@router.get("/macro")
def list_macro_series() -> dict:
    return {"series": DEFAULT_SERIES}


@router.get("/macro/{series_id}")
def get_macro(
    series_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    refresh: bool = False,
) -> dict:
    return macro_payload(series_id.upper(), start=start, end=end, force_refresh=refresh)


@router.post("/macro/bootstrap")
def post_bootstrap_macro() -> dict:
    """Ingest the default FRED series set into the local cache."""
    counts = bootstrap_macro()
    return {"ingested": counts}
