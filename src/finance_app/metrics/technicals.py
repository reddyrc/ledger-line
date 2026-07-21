from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd


def _close(df: pd.DataFrame) -> pd.Series:
    col = "adj_close" if "adj_close" in df.columns and df["adj_close"].notna().any() else "close"
    return df.set_index("date")[col].astype(float).sort_index()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    ef = ema(series, fast)
    es = ema(series, slow)
    line = ef - es
    sig = ema(line, signal)
    hist = line - sig
    return pd.DataFrame({"macd": line, "signal": sig, "histogram": hist})


def bollinger(
    series: pd.Series, window: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    mid = sma(series, window)
    std = series.rolling(window).std(ddof=1)
    return pd.DataFrame(
        {
            "mid": mid,
            "upper": mid + num_std * std,
            "lower": mid - num_std * std,
        }
    )


def compute_technicals(
    ohlcv: pd.DataFrame,
    rsi_window: int = 14,
    sma_windows: Optional[list[int]] = None,
) -> dict[str, Any]:
    sma_windows = sma_windows or [20, 50, 200]
    prices = _close(ohlcv)
    if prices.empty:
        return {"bars": 0, "latest": {}, "series": []}

    rsi_s = rsi(prices, rsi_window)
    macd_df = macd(prices)
    bb = bollinger(prices)

    smas = {f"sma_{w}": sma(prices, w) for w in sma_windows}

    latest = {
        "date": prices.index[-1].strftime("%Y-%m-%d"),
        "price": float(prices.iloc[-1]),
        "rsi": _n(rsi_s.iloc[-1]),
        "macd": _n(macd_df["macd"].iloc[-1]),
        "macd_signal": _n(macd_df["signal"].iloc[-1]),
        "macd_histogram": _n(macd_df["histogram"].iloc[-1]),
        "bb_mid": _n(bb["mid"].iloc[-1]),
        "bb_upper": _n(bb["upper"].iloc[-1]),
        "bb_lower": _n(bb["lower"].iloc[-1]),
    }
    for w, s in smas.items():
        latest[w] = _n(s.iloc[-1])

    # Return last ~252 points for charting
    tail = prices.tail(252)
    series = []
    for dt in tail.index:
        row = {
            "date": dt.strftime("%Y-%m-%d"),
            "price": float(prices.loc[dt]),
            "rsi": _n(rsi_s.loc[dt]) if dt in rsi_s.index else None,
            "macd": _n(macd_df["macd"].loc[dt]) if dt in macd_df.index else None,
            "macd_signal": _n(macd_df["signal"].loc[dt]) if dt in macd_df.index else None,
        }
        for w, s in smas.items():
            row[w] = _n(s.loc[dt]) if dt in s.index else None
        series.append(row)

    return {"bars": int(len(prices)), "latest": latest, "series": series}


def _n(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    try:
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            return None
        return fv
    except (TypeError, ValueError):
        return None
