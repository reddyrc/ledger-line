from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from finance_app.db import load_fundamentals, load_ohlcv
from finance_app.ingest.edgar import ingest_fundamentals, latest_fundamental_values


def compute_fundamental_ratios(
    ticker: str,
    refresh: bool = False,
) -> dict[str, Any]:
    """
    Build simple ratios from cached EDGAR facts + latest market price.
    """
    ticker = ticker.upper()
    existing = load_fundamentals(ticker)
    if refresh or existing.empty:
        try:
            ingest_fundamentals(ticker)
        except Exception as exc:
            return {
                "ticker": ticker,
                "error": str(exc),
                "ratios": {},
                "raw": {},
            }

    raw = latest_fundamental_values(ticker)
    price = _latest_price(ticker)
    shares_approx = None

    eps = raw.get("EPS")
    equity = raw.get("Equity")
    assets = raw.get("Assets")
    revenue = raw.get("Revenue")
    net_income = raw.get("NetIncome")
    gross = raw.get("GrossProfit")
    liabilities = raw.get("Liabilities")
    shares = raw.get("Shares")

    if shares and shares > 0:
        shares_approx = shares
    elif eps and net_income and eps != 0:
        shares_approx = net_income / eps

    market_cap = (price * shares_approx) if (price and shares_approx) else None

    ratios: dict[str, Optional[float]] = {
        "pe": (price / eps) if (price and eps and eps != 0) else None,
        "pb": (market_cap / equity) if (market_cap and equity and equity != 0) else None,
        "roe": (net_income / equity) if (net_income and equity and equity != 0) else None,
        "roa": (net_income / assets) if (net_income and assets and assets != 0) else None,
        "gross_margin": (gross / revenue) if (gross and revenue and revenue != 0) else None,
        "net_margin": (net_income / revenue) if (net_income and revenue and revenue != 0) else None,
        "debt_to_assets": (
            (liabilities / assets) if (liabilities and assets and assets != 0) else None
        ),
        "price": price,
        "market_cap_approx": market_cap,
    }

    history = _growth_history(ticker)

    return {
        "ticker": ticker,
        "ratios": {k: _round(v) for k, v in ratios.items()},
        "raw": {k: _round(v) for k, v in raw.items()},
        "growth": history,
        "disclaimer": (
            "Ratios use SEC EDGAR XBRL tags joined to cached prices; "
            "market cap is approximated from NetIncome/EPS when available."
        ),
    }


def _latest_price(ticker: str) -> Optional[float]:
    df = load_ohlcv(ticker)
    if df.empty:
        return None
    col = "adj_close" if df["adj_close"].notna().any() else "close"
    return float(df.iloc[-1][col])


def _growth_history(ticker: str) -> dict[str, list[dict[str, Any]]]:
    df = load_fundamentals(ticker, concepts=["Revenue", "NetIncome", "EPS"])
    out: dict[str, list[dict[str, Any]]] = {}
    if df.empty:
        return out
    for concept, group in df.groupby("concept"):
        # Prefer annual 10-K rows when present
        annual = group[group["form"] == "10-K"].sort_values("end_date")
        use = annual if not annual.empty else group.sort_values("end_date")
        use = use.drop_duplicates(subset=["end_date"], keep="last")
        series = []
        prev = None
        for _, row in use.iterrows():
            val = float(row["value"])
            yoy = ((val / prev) - 1.0) if prev and prev != 0 else None
            series.append(
                {
                    "end_date": row["end_date"],
                    "value": _round(val),
                    "yoy": _round(yoy),
                    "form": row["form"],
                }
            )
            prev = val
        out[concept] = series[-12:]
    return out


def _round(v: Optional[float], nd: int = 6) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None
