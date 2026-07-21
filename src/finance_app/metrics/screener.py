"""Compute a single-ticker screener snapshot from cached OHLCV + fundamentals."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from finance_app.db import load_fundamentals, load_ohlcv
from finance_app.ingest.edgar import latest_fundamental_values
from finance_app.metrics.price_metrics import (
    cumulative_return,
    daily_returns,
    max_drawdown,
    realized_volatility,
)


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


def _price_series(ohlcv: pd.DataFrame) -> pd.Series:
    if ohlcv.empty:
        return pd.Series(dtype=float)
    col = (
        "adj_close"
        if "adj_close" in ohlcv.columns and ohlcv["adj_close"].notna().any()
        else "close"
    )
    return ohlcv.set_index("date")[col].astype(float).sort_index()


def _window_return(prices: pd.Series, trading_days: int) -> Optional[float]:
    if len(prices) < 2:
        return None
    if len(prices) > trading_days:
        window = prices.iloc[-(trading_days + 1) :]
    else:
        window = prices
    return _round(cumulative_return(window))


def compute_screen_metrics(ticker: str) -> dict[str, Any]:
    """
    Build screener row metrics from already-cached data.
    Does not fetch remotely — caller ensures cache is warm.
    """
    ticker = ticker.upper()
    ohlcv = load_ohlcv(ticker)
    prices = _price_series(ohlcv)

    out: dict[str, Any] = {
        "ticker": ticker,
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
        "error": None,
    }

    if prices.empty:
        out["error"] = "no_price_data"
        return out

    out["price"] = _round(float(prices.iloc[-1]))
    out["momentum_3m"] = _window_return(prices, 63)
    out["momentum_12m"] = _window_return(prices, 252)

    one_year = prices.iloc[-min(len(prices), 253) :]
    rets = daily_returns(one_year)
    out["vol_ann"] = _round(realized_volatility(rets))
    out["max_drawdown_1y"] = _round(max_drawdown(one_year))

    raw = latest_fundamental_values(ticker)
    if not raw and load_fundamentals(ticker).empty:
        # Prices ok but no fundamentals — still a valid row
        return out

    eps = raw.get("EPS")
    equity = raw.get("Equity")
    revenue = raw.get("Revenue")
    net_income = raw.get("NetIncome")
    shares = raw.get("Shares")

    shares_approx = None
    if shares and shares > 0:
        shares_approx = shares
    elif eps and net_income and eps != 0:
        shares_approx = net_income / eps

    price = out["price"]
    market_cap = (price * shares_approx) if (price and shares_approx) else None
    out["market_cap"] = _round(market_cap)

    if price and eps and eps != 0:
        out["pe"] = _round(price / eps)
    if market_cap and equity and equity != 0:
        out["pb"] = _round(market_cap / equity)
    if market_cap and revenue and revenue != 0:
        out["ps"] = _round(market_cap / revenue)
    if net_income and equity and equity != 0:
        out["roe"] = _round(net_income / equity)
    if net_income and revenue and revenue != 0:
        out["net_margin"] = _round(net_income / revenue)

    return out
