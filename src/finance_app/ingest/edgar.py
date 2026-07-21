from __future__ import annotations

import time
from typing import Optional

import httpx
import pandas as pd

from finance_app.config import get_settings
from finance_app.db import upsert_fundamentals

EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Prefer these US-GAAP tags when building ratios
CONCEPT_ALIASES: dict[str, list[str]] = {
    "Revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "NetIncome": ["NetIncomeLoss"],
    "EPS": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "Assets": ["Assets"],
    "Equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "Liabilities": ["Liabilities"],
    "GrossProfit": ["GrossProfit"],
    "OperatingIncome": ["OperatingIncomeLoss"],
    "Cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "Shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingDiluted",
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
}


def _headers(host: str = "www.sec.gov") -> dict[str, str]:
    # SEC fair-use: identify the app + contact email; Accept-Encoding helps avoid 403s.
    return {
        "User-Agent": get_settings().sec_user_agent,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Host": host,
    }


def fetch_ticker_cik_map(client: Optional[httpx.Client] = None) -> dict[str, str]:
    """Return {TICKER: zero-padded CIK}."""
    owns = client is None
    client = client or httpx.Client(timeout=60.0, headers=_headers("www.sec.gov"))
    try:
        resp = client.get(EDGAR_TICKERS_URL, headers=_headers("www.sec.gov"))
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns:
            client.close()

    mapping: dict[str, str] = {}
    for item in data.values():
        ticker = str(item.get("ticker", "")).upper()
        cik = str(item.get("cik_str", "")).zfill(10)
        if ticker and cik:
            mapping[ticker] = cik
    return mapping


def resolve_cik(ticker: str, mapping: Optional[dict[str, str]] = None) -> Optional[str]:
    mapping = mapping or fetch_ticker_cik_map()
    return mapping.get(ticker.upper())


def fetch_company_facts(cik: str, client: Optional[httpx.Client] = None) -> dict:
    owns = client is None
    client = client or httpx.Client(timeout=60.0, headers=_headers("data.sec.gov"))
    try:
        url = COMPANY_FACTS_URL.format(cik=cik.zfill(10))
        resp = client.get(url, headers=_headers("data.sec.gov"))
        resp.raise_for_status()
        return resp.json()
    finally:
        if owns:
            client.close()


def parse_company_facts(
    facts: dict,
    ticker: str,
    concepts: Optional[list[str]] = None,
) -> list[tuple]:
    """
    Flatten companyfacts JSON into DB rows:
    (cik, ticker, concept, end_date, value, unit, form, fy, fp, filed)
    """
    cik = str(facts.get("cik", "")).zfill(10)
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    wanted = set(concepts) if concepts else set(CONCEPT_ALIASES.keys())

    # Expand aliases → actual tag names we will store under the canonical concept key
    tag_to_canonical: dict[str, str] = {}
    for canonical, aliases in CONCEPT_ALIASES.items():
        if canonical not in wanted:
            continue
        for tag in aliases:
            tag_to_canonical[tag] = canonical

    rows: list[tuple] = []
    for tag, payload in us_gaap.items():
        canonical = tag_to_canonical.get(tag)
        if not canonical:
            continue
        units = payload.get("units", {})
        # Prefer the unit that matches the concept (shares for Shares, USD/shares for EPS)
        if canonical == "Shares" and "shares" in units:
            series = units["shares"]
            unit_name = "shares"
        elif "USD/shares" in units:
            series = units["USD/shares"]
            unit_name = "USD/shares"
        elif "USD" in units:
            series = units["USD"]
            unit_name = "USD"
        else:
            unit_name = next(iter(units.keys()), "")
            series = units.get(unit_name, [])
        for obs in series:
            end = obs.get("end")
            val = obs.get("val")
            if end is None or val is None:
                continue
            filed = obs.get("filed")
            rows.append(
                (
                    cik,
                    ticker.upper(),
                    canonical,
                    end,
                    float(val),
                    unit_name,
                    obs.get("form"),
                    obs.get("fy"),
                    obs.get("fp"),
                    filed if filed else None,
                )
            )
    return rows


def ingest_fundamentals(ticker: str) -> int:
    """Fetch EDGAR companyfacts for ticker and cache in SQLite. Returns row count."""
    # Separate hosts (www.sec.gov vs data.sec.gov) — set Host per request.
    with httpx.Client(timeout=60.0) as client:
        cik = resolve_cik(ticker, fetch_ticker_cik_map(client))
        if not cik:
            raise ValueError(f"No SEC CIK found for ticker {ticker}")
        # Fair-use: be polite between requests
        time.sleep(0.2)
        facts = fetch_company_facts(cik, client)

    rows = parse_company_facts(facts, ticker)
    return upsert_fundamentals(rows)


def latest_fundamental_values(ticker: str) -> dict[str, float]:
    from finance_app.db import load_fundamentals

    df = load_fundamentals(ticker)
    if df.empty:
        return {}
    out: dict[str, float] = {}
    for concept, group in df.groupby("concept"):
        # Prefer 10-K / 10-Q annual-ish latest end_date
        g = group.sort_values("end_date")
        out[concept] = float(g.iloc[-1]["value"])
    return out
