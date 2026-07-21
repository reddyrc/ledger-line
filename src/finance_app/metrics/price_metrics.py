from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd


def _price_series(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    col = "adj_close" if "adj_close" in df.columns and df["adj_close"].notna().any() else "close"
    s = df.set_index("date")[col].astype(float).sort_index()
    return s


def daily_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()


def log_returns(prices: pd.Series) -> pd.Series:
    return np.log(prices / prices.shift(1)).dropna()


def cumulative_return(prices: pd.Series) -> float:
    if len(prices) < 2:
        return float("nan")
    return float(prices.iloc[-1] / prices.iloc[0] - 1.0)


def realized_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    if returns.empty:
        return float("nan")
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def rolling_volatility(
    returns: pd.Series, window: int = 21, periods_per_year: int = 252
) -> pd.Series:
    return returns.rolling(window).std(ddof=1) * np.sqrt(periods_per_year)


def sharpe_ratio(
    returns: pd.Series,
    risk_free_annual: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    if returns.empty or returns.std(ddof=1) == 0:
        return float("nan")
    rf_daily = (1 + risk_free_annual) ** (1 / periods_per_year) - 1
    excess = returns - rf_daily
    return float(excess.mean() / excess.std(ddof=1) * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series,
    risk_free_annual: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    if returns.empty:
        return float("nan")
    rf_daily = (1 + risk_free_annual) ** (1 / periods_per_year) - 1
    excess = returns - rf_daily
    downside = excess[excess < 0]
    if downside.empty or downside.std(ddof=1) == 0:
        return float("nan")
    return float(excess.mean() / downside.std(ddof=1) * np.sqrt(periods_per_year))


def max_drawdown(prices: pd.Series) -> float:
    if prices.empty:
        return float("nan")
    peak = prices.cummax()
    dd = prices / peak - 1.0
    return float(dd.min())


def calmar_ratio(prices: pd.Series, periods_per_year: int = 252) -> float:
    if len(prices) < 2:
        return float("nan")
    years = len(prices) / periods_per_year
    if years <= 0:
        return float("nan")
    cagr = (prices.iloc[-1] / prices.iloc[0]) ** (1 / years) - 1
    mdd = abs(max_drawdown(prices))
    if mdd == 0:
        return float("nan")
    return float(cagr / mdd)


def beta(asset_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    aligned = pd.concat([asset_returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return float("nan")
    a, b = aligned.iloc[:, 0], aligned.iloc[:, 1]
    var_b = b.var(ddof=1)
    if var_b == 0 or np.isnan(var_b):
        return float("nan")
    return float(a.cov(b) / var_b)


def correlation(a: pd.Series, b: pd.Series) -> float:
    aligned = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return float("nan")
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def compute_price_metrics(
    ohlcv: pd.DataFrame,
    benchmark_ohlcv: Optional[pd.DataFrame] = None,
    risk_free_annual: float = 0.0,
) -> dict[str, Any]:
    prices = _price_series(ohlcv)
    rets = daily_returns(prices)
    out: dict[str, Any] = {
        "bars": int(len(prices)),
        "start": prices.index.min().strftime("%Y-%m-%d") if len(prices) else None,
        "end": prices.index.max().strftime("%Y-%m-%d") if len(prices) else None,
        "last_price": float(prices.iloc[-1]) if len(prices) else None,
        "cumulative_return": _nan_to_none(cumulative_return(prices)),
        "realized_volatility_ann": _nan_to_none(realized_volatility(rets)),
        "sharpe": _nan_to_none(sharpe_ratio(rets, risk_free_annual=risk_free_annual)),
        "sortino": _nan_to_none(sortino_ratio(rets, risk_free_annual=risk_free_annual)),
        "max_drawdown": _nan_to_none(max_drawdown(prices)),
        "calmar": _nan_to_none(calmar_ratio(prices)),
        "risk_free_annual": risk_free_annual,
    }

    if benchmark_ohlcv is not None and not benchmark_ohlcv.empty:
        b_prices = _price_series(benchmark_ohlcv)
        b_rets = daily_returns(b_prices)
        out["beta"] = _nan_to_none(beta(rets, b_rets))
        out["correlation_to_benchmark"] = _nan_to_none(correlation(rets, b_rets))
    else:
        out["beta"] = None
        out["correlation_to_benchmark"] = None

    return out


def rolling_metrics_series(
    ohlcv: pd.DataFrame,
    window: int = 63,
) -> list[dict[str, Any]]:
    prices = _price_series(ohlcv)
    rets = daily_returns(prices)
    roll_vol = rolling_volatility(rets, window=min(window, 21))
    cum = (1 + rets).cumprod() - 1

    rows = []
    for dt in rets.index:
        rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "return": _nan_to_none(float(rets.loc[dt])),
                "cumulative_return": _nan_to_none(float(cum.loc[dt])),
                "rolling_vol_ann": _nan_to_none(
                    float(roll_vol.loc[dt]) if dt in roll_vol.index else float("nan")
                ),
            }
        )
    return rows


def _nan_to_none(v: Any) -> Any:
    if v is None:
        return None
    try:
        if isinstance(v, (float, np.floating)) and (np.isnan(v) or np.isinf(v)):
            return None
    except TypeError:
        pass
    return v
