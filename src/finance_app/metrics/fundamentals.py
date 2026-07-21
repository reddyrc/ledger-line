from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from finance_app.db import load_fundamentals, load_ohlcv
from finance_app.ingest.edgar import ingest_fundamentals, latest_fundamental_values

# Ordered balance-sheet presentation (SEC XBRL canonical keys).
BALANCE_SHEET_LINES: list[dict[str, str]] = [
    {"key": "Cash", "label": "Cash & equivalents", "section": "assets"},
    {"key": "ShortTermInvestments", "label": "Short-term investments", "section": "assets"},
    {"key": "AccountsReceivable", "label": "Accounts receivable", "section": "assets"},
    {"key": "Inventory", "label": "Inventory", "section": "assets"},
    {"key": "CurrentAssets", "label": "Total current assets", "section": "assets"},
    {"key": "PropertyPlantEquipment", "label": "Property, plant & equipment", "section": "assets"},
    {"key": "Goodwill", "label": "Goodwill", "section": "assets"},
    {"key": "IntangibleAssets", "label": "Intangible assets", "section": "assets"},
    {"key": "Assets", "label": "Total assets", "section": "assets"},
    {"key": "AccountsPayable", "label": "Accounts payable", "section": "liabilities"},
    {"key": "ShortTermDebt", "label": "Short-term debt", "section": "liabilities"},
    {"key": "CurrentLiabilities", "label": "Total current liabilities", "section": "liabilities"},
    {"key": "LongTermDebt", "label": "Long-term debt", "section": "liabilities"},
    {"key": "Liabilities", "label": "Total liabilities", "section": "liabilities"},
    {"key": "CommonStock", "label": "Common stock", "section": "equity"},
    {"key": "RetainedEarnings", "label": "Retained earnings", "section": "equity"},
    {"key": "Equity", "label": "Total equity", "section": "equity"},
]

BALANCE_SHEET_KEYS = [row["key"] for row in BALANCE_SHEET_LINES]


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
                "growth": {},
                "balance_sheet": None,
            }

    raw = latest_fundamental_values(ticker)
    # Derive total liabilities when companies omit the tag but report Assets & Equity
    if raw.get("Liabilities") is None and raw.get("Assets") and raw.get("Equity"):
        raw["Liabilities"] = float(raw["Assets"]) - float(raw["Equity"])

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
    current_assets = raw.get("CurrentAssets")
    current_liabilities = raw.get("CurrentLiabilities")

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
        "current_ratio": (
            (current_assets / current_liabilities)
            if (current_assets and current_liabilities and current_liabilities != 0)
            else None
        ),
        "price": price,
        "market_cap_approx": market_cap,
    }

    history = _growth_history(ticker)
    balance_sheet = build_balance_sheet(ticker)

    return {
        "ticker": ticker,
        "ratios": {k: _round(v) for k, v in ratios.items()},
        "raw": {k: _round(v) for k, v in raw.items()},
        "growth": history,
        "balance_sheet": balance_sheet,
        "disclaimer": (
            "Ratios and balance sheet use SEC EDGAR XBRL tags joined to cached prices; "
            "line items may be missing when a company uses nonstandard tags. "
            "Market cap is approximated from shares × price when available."
        ),
    }


def build_balance_sheet(ticker: str, *, max_periods: int = 8) -> dict[str, Any]:
    """Latest balance sheet + multi-period history (prefer annual 10-K)."""
    df = load_fundamentals(ticker, concepts=BALANCE_SHEET_KEYS)
    empty = {
        "as_of": None,
        "form": None,
        "lines": [],
        "history": {"periods": [], "rows": []},
    }
    if df.empty:
        return empty

    # Prefer 10-K for period columns; fall back to all forms
    annual = df[df["form"] == "10-K"]
    use = annual if not annual.empty else df
    periods = sorted(use["end_date"].dropna().unique().tolist())[-max_periods:]
    if not periods:
        return empty

    # Pivot concept × period (last value wins for duplicate end_date)
    by_concept: dict[str, dict[str, float]] = {}
    for concept, group in use.groupby("concept"):
        g = group.sort_values(["end_date", "filed"]).drop_duplicates(
            subset=["end_date"], keep="last"
        )
        by_concept[str(concept)] = {
            str(r["end_date"])[:10]: float(r["value"]) for _, r in g.iterrows()
        }

    # Fill Liabilities from Assets − Equity per period when missing
    for p in periods:
        p = str(p)[:10]
        assets = by_concept.get("Assets", {}).get(p)
        equity = by_concept.get("Equity", {}).get(p)
        liab_map = by_concept.setdefault("Liabilities", {})
        if p not in liab_map and assets is not None and equity is not None:
            liab_map[p] = assets - equity

    latest_period = str(periods[-1])[:10]
    # Find form for latest period
    latest_form = None
    latest_rows = use[use["end_date"].astype(str).str[:10] == latest_period]
    if not latest_rows.empty:
        latest_form = latest_rows.iloc[-1].get("form")

    lines: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    for spec in BALANCE_SHEET_LINES:
        key = spec["key"]
        values_map = by_concept.get(key, {})
        values = [_round(values_map.get(str(p)[:10])) for p in periods]
        # Skip lines that have never appeared
        if all(v is None for v in values):
            continue
        latest_val = values[-1] if values else None
        prev_val = values[-2] if len(values) >= 2 else None
        yoy = None
        if latest_val is not None and prev_val is not None and prev_val != 0:
            yoy = (latest_val / prev_val) - 1.0
        line = {
            "key": key,
            "label": spec["label"],
            "section": spec["section"],
            "value": _round(latest_val),
            "yoy": _round(yoy),
        }
        lines.append(line)
        history_rows.append(
            {
                "key": key,
                "label": spec["label"],
                "section": spec["section"],
                "values": values,
            }
        )

    return {
        "as_of": latest_period,
        "form": latest_form,
        "lines": lines,
        "history": {
            "periods": [str(p)[:10] for p in periods],
            "rows": history_rows,
        },
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
        f = float(v)
        if pd.isna(f):
            return None
        return round(f, nd)
    except (TypeError, ValueError):
        return None
