from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from finance_app.ingest.fred import DEFAULT_SERIES
from finance_app.services import (
    bootstrap_macro,
    fundamentals_payload,
    macro_payload,
    screen_payload,
    screen_refresh_payload,
    screen_sectors_payload,
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
