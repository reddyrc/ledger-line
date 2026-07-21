from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

import pandas as pd

from finance_app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume REAL,
    source TEXT NOT NULL DEFAULT 'yfinance',
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS ingest_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fundamentals (
    cik TEXT NOT NULL,
    ticker TEXT,
    concept TEXT NOT NULL,
    end_date TEXT NOT NULL,
    value REAL,
    unit TEXT,
    form TEXT,
    fy INTEGER,
    fp TEXT,
    filed TEXT,
    PRIMARY KEY (cik, concept, end_date, form)
);

CREATE TABLE IF NOT EXISTS macro_series (
    series_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (series_id, date)
);

CREATE TABLE IF NOT EXISTS earnings_events (
    symbol TEXT NOT NULL,
    report_datetime TEXT NOT NULL,
    reported_eps REAL,
    eps_estimate REAL,
    surprise_pct REAL,
    PRIMARY KEY (symbol, report_datetime)
);

CREATE TABLE IF NOT EXISTS earnings_analysis_snapshots (
    symbol TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS short_interest (
    symbol TEXT NOT NULL,
    settlement_date TEXT NOT NULL,
    shares_short REAL,
    shares_short_prior REAL,
    change_pct REAL,
    avg_daily_volume REAL,
    days_to_cover REAL,
    source TEXT NOT NULL DEFAULT 'finra',
    PRIMARY KEY (symbol, settlement_date)
);

CREATE TABLE IF NOT EXISTS screen_snapshots (
    ticker TEXT PRIMARY KEY,
    name TEXT,
    sector TEXT,
    price REAL,
    market_cap REAL,
    pe REAL,
    pb REAL,
    ps REAL,
    roe REAL,
    net_margin REAL,
    momentum_3m REAL,
    momentum_12m REAL,
    vol_ann REAL,
    max_drawdown_1y REAL,
    error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS peer_cache (
    cache_key TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    peer_limit INTEGER NOT NULL,
    peer_basis TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS options_chain_cache (
    cache_key TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    expiration TEXT NOT NULL,
    spot REAL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS options_contract_cache (
    cache_key TEXT PRIMARY KEY,
    contract_symbol TEXT NOT NULL,
    period TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS options_strategy_cache (
    cache_key TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    expiration TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS options_iv_snapshots (
    symbol TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    expiration TEXT NOT NULL,
    dte INTEGER,
    atm_iv REAL,
    spot REAL,
    call_volume REAL,
    put_volume REAL,
    call_oi REAL,
    put_oi REAL,
    PRIMARY KEY (symbol, as_of_date, expiration)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol ON ohlcv(symbol);
CREATE INDEX IF NOT EXISTS idx_fund_ticker ON fundamentals(ticker);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings_events(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_analysis_symbol ON earnings_analysis_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_short_interest_symbol ON short_interest(symbol);
CREATE INDEX IF NOT EXISTS idx_macro_series ON macro_series(series_id);
CREATE INDEX IF NOT EXISTS idx_screen_sector ON screen_snapshots(sector);
CREATE INDEX IF NOT EXISTS idx_screen_pe ON screen_snapshots(pe);
CREATE INDEX IF NOT EXISTS idx_peer_cache_symbol ON peer_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_options_chain_symbol ON options_chain_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_options_contract_symbol ON options_contract_cache(contract_symbol);
CREATE INDEX IF NOT EXISTS idx_options_strategy_symbol ON options_strategy_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_options_iv_symbol_date ON options_iv_snapshots(symbol, as_of_date);
"""


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate_fundamentals_filed(conn)
        conn.commit()


def _migrate_fundamentals_filed(conn: sqlite3.Connection) -> None:
    """Add filed column to existing fundamentals tables created before this field existed."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(fundamentals)").fetchall()}
    if "filed" not in cols:
        conn.execute("ALTER TABLE fundamentals ADD COLUMN filed TEXT")


@contextmanager
def get_conn(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_meta(key: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ingest_meta(key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, now),
        )


def get_meta(key: str) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM ingest_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None


def get_meta_updated_at(key: str) -> Optional[datetime]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT updated_at FROM ingest_meta WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        return datetime.fromisoformat(row["updated_at"])


def upsert_ohlcv(df: pd.DataFrame, symbol: str, source: str = "yfinance") -> int:
    """Upsert OHLCV rows. Expects columns: date, open, high, low, close, adj_close, volume."""
    if df.empty:
        return 0
    rows = []
    for _, r in df.iterrows():
        date = r["date"]
        if hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d")
        else:
            date = str(date)[:10]
        rows.append(
            (
                symbol.upper(),
                date,
                _f(r.get("open")),
                _f(r.get("high")),
                _f(r.get("low")),
                _f(r.get("close")),
                _f(r.get("adj_close", r.get("close"))),
                _f(r.get("volume")),
                source,
            )
        )
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO ohlcv(symbol, date, open, high, low, close, adj_close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                adj_close=excluded.adj_close,
                volume=excluded.volume,
                source=excluded.source
            """,
            rows,
        )
    set_meta(f"ohlcv:{symbol.upper()}", source)
    return len(rows)


def load_ohlcv(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    clauses = ["symbol = ?"]
    params: list = [symbol.upper()]
    if start:
        clauses.append("date >= ?")
        params.append(start)
    if end:
        clauses.append("date <= ?")
        params.append(end)
    sql = f"""
        SELECT date, open, high, low, close, adj_close, volume, source
        FROM ohlcv
        WHERE {' AND '.join(clauses)}
        ORDER BY date
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def upsert_macro(series_id: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    rows = []
    for _, r in df.iterrows():
        date = r["date"]
        if hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d")
        else:
            date = str(date)[:10]
        rows.append((series_id, date, _f(r["value"])))
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO macro_series(series_id, date, value)
            VALUES (?, ?, ?)
            ON CONFLICT(series_id, date) DO UPDATE SET value=excluded.value
            """,
            rows,
        )
    set_meta(f"macro:{series_id}", "fred")
    return len(rows)


def load_macro(
    series_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    clauses = ["series_id = ?"]
    params: list = [series_id]
    if start:
        clauses.append("date >= ?")
        params.append(start)
    if end:
        clauses.append("date <= ?")
        params.append(end)
    sql = f"""
        SELECT date, value FROM macro_series
        WHERE {' AND '.join(clauses)}
        ORDER BY date
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def upsert_fundamentals(rows: list[tuple]) -> int:
    """rows: (cik, ticker, concept, end_date, value, unit, form, fy, fp, filed)"""
    if not rows:
        return 0
    # Accept legacy 9-tuples (no filed) from older callers/tests.
    normalized: list[tuple] = []
    for row in rows:
        if len(row) == 9:
            normalized.append((*row, None))
        else:
            normalized.append(row)
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO fundamentals(cik, ticker, concept, end_date, value, unit, form, fy, fp, filed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cik, concept, end_date, form) DO UPDATE SET
                ticker=excluded.ticker,
                value=excluded.value,
                unit=excluded.unit,
                fy=excluded.fy,
                fp=excluded.fp,
                filed=COALESCE(excluded.filed, fundamentals.filed)
            """,
            normalized,
        )
    return len(normalized)


def load_fundamentals(ticker: str, concepts: Optional[list[str]] = None) -> pd.DataFrame:
    clauses = ["ticker = ?"]
    params: list = [ticker.upper()]
    if concepts:
        placeholders = ",".join("?" * len(concepts))
        clauses.append(f"concept IN ({placeholders})")
        params.extend(concepts)
    sql = f"""
        SELECT cik, ticker, concept, end_date, value, unit, form, fy, fp, filed
        FROM fundamentals
        WHERE {' AND '.join(clauses)}
        ORDER BY end_date
    """
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def upsert_earnings_events(symbol: str, rows: list[tuple]) -> int:
    """rows: (report_datetime, reported_eps, eps_estimate, surprise_pct)."""
    if not rows:
        return 0
    values = [(symbol.upper(), *row) for row in rows]
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO earnings_events(
                symbol, report_datetime, reported_eps, eps_estimate, surprise_pct
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol, report_datetime) DO UPDATE SET
                reported_eps=excluded.reported_eps,
                eps_estimate=excluded.eps_estimate,
                surprise_pct=excluded.surprise_pct
            """,
            values,
        )
    return len(values)


def load_earnings_events(symbol: str) -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            """
            SELECT report_datetime, reported_eps, eps_estimate, surprise_pct
            FROM earnings_events
            WHERE symbol = ?
            ORDER BY report_datetime
            """,
            conn,
            params=[symbol.upper()],
        )
    if not df.empty:
        df["report_datetime"] = pd.to_datetime(
            df["report_datetime"], errors="coerce"
        )
    return df


def upsert_short_interest(rows: list[tuple]) -> int:
    """
    rows: (symbol, settlement_date, shares_short, shares_short_prior,
           change_pct, avg_daily_volume, days_to_cover, source)
    """
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO short_interest(
                symbol, settlement_date, shares_short, shares_short_prior,
                change_pct, avg_daily_volume, days_to_cover, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, settlement_date) DO UPDATE SET
                shares_short=excluded.shares_short,
                shares_short_prior=excluded.shares_short_prior,
                change_pct=excluded.change_pct,
                avg_daily_volume=excluded.avg_daily_volume,
                days_to_cover=excluded.days_to_cover,
                source=excluded.source
            """,
            rows,
        )
    return len(rows)


def load_short_interest(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    clauses = ["symbol = ?"]
    params: list = [symbol.upper()]
    if start:
        clauses.append("settlement_date >= ?")
        params.append(start)
    if end:
        clauses.append("settlement_date <= ?")
        params.append(end)
    sql = f"""
        SELECT settlement_date, shares_short, shares_short_prior, change_pct,
               avg_daily_volume, days_to_cover, source
        FROM short_interest
        WHERE {' AND '.join(clauses)}
        ORDER BY settlement_date
    """
    with get_conn() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    if not df.empty:
        df["settlement_date"] = pd.to_datetime(df["settlement_date"], errors="coerce")
    return df


def upsert_screen_snapshot(row: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO screen_snapshots(
                ticker, name, sector, price, market_cap, pe, pb, ps, roe, net_margin,
                momentum_3m, momentum_12m, vol_ann, max_drawdown_1y, error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name=excluded.name,
                sector=excluded.sector,
                price=excluded.price,
                market_cap=excluded.market_cap,
                pe=excluded.pe,
                pb=excluded.pb,
                ps=excluded.ps,
                roe=excluded.roe,
                net_margin=excluded.net_margin,
                momentum_3m=excluded.momentum_3m,
                momentum_12m=excluded.momentum_12m,
                vol_ann=excluded.vol_ann,
                max_drawdown_1y=excluded.max_drawdown_1y,
                error=excluded.error,
                updated_at=excluded.updated_at
            """,
            (
                row["ticker"].upper(),
                row.get("name"),
                row.get("sector"),
                row.get("price"),
                row.get("market_cap"),
                row.get("pe"),
                row.get("pb"),
                row.get("ps"),
                row.get("roe"),
                row.get("net_margin"),
                row.get("momentum_3m"),
                row.get("momentum_12m"),
                row.get("vol_ann"),
                row.get("max_drawdown_1y"),
                row.get("error"),
                now,
            ),
        )


def count_screen_snapshots() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM screen_snapshots").fetchone()
        return int(row["n"]) if row else 0


def get_screen_snapshot(ticker: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT ticker, name, sector, price, market_cap, pe, pb, ps, roe, net_margin,
                   momentum_3m, momentum_12m, vol_ann, max_drawdown_1y, error, updated_at
            FROM screen_snapshots
            WHERE ticker = ?
            """,
            (ticker.upper(),),
        ).fetchone()
        return dict(row) if row else None


def query_screen_snapshots(
    *,
    q: Optional[str] = None,
    sector: Optional[str] = None,
    filters: Optional[dict[str, tuple[Optional[float], Optional[float]]]] = None,
    sort: str = "ticker",
    order: str = "asc",
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """
    filters: {column: (min, max)} where either bound may be None.
    Returns (rows, total_count_before_limit).
    """
    allowed = {
        "ticker",
        "name",
        "sector",
        "price",
        "market_cap",
        "pe",
        "pb",
        "ps",
        "roe",
        "net_margin",
        "momentum_3m",
        "momentum_12m",
        "vol_ann",
        "max_drawdown_1y",
        "updated_at",
    }
    clauses: list[str] = []
    params: list = []

    if q:
        clauses.append("(ticker LIKE ? OR name LIKE ?)")
        like = f"%{q.upper()}%"
        params.extend([like, f"%{q}%"])
    if sector:
        clauses.append("sector = ?")
        params.append(sector)

    filters = filters or {}
    for col, (lo, hi) in filters.items():
        if col not in allowed or col in ("ticker", "name", "sector", "updated_at"):
            continue
        if lo is not None:
            clauses.append(f"{col} >= ?")
            params.append(lo)
        if hi is not None:
            clauses.append(f"{col} <= ?")
            params.append(hi)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sort_col = sort if sort in allowed else "ticker"
    sort_dir = "DESC" if order.lower() == "desc" else "ASC"

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM screen_snapshots {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT ticker, name, sector, price, market_cap, pe, pb, ps, roe, net_margin,
                   momentum_3m, momentum_12m, vol_ann, max_drawdown_1y, error, updated_at
            FROM screen_snapshots
            {where}
            ORDER BY ({sort_col} IS NULL), {sort_col} {sort_dir}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return [dict(r) for r in rows], int(total)


def list_screen_sectors() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT sector FROM screen_snapshots
            WHERE sector IS NOT NULL AND sector != ''
            ORDER BY sector
            """
        ).fetchall()
        return [r["sector"] for r in rows]


def upsert_peer_cache(
    cache_key: str,
    *,
    symbol: str,
    peer_limit: int,
    peer_basis: str,
    payload: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO peer_cache(cache_key, symbol, peer_limit, peer_basis, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                symbol=excluded.symbol,
                peer_limit=excluded.peer_limit,
                peer_basis=excluded.peer_basis,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (
                cache_key,
                symbol.upper(),
                int(peer_limit),
                peer_basis,
                json.dumps(payload),
                now,
            ),
        )


def get_peer_cache(cache_key: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT cache_key, symbol, peer_limit, peer_basis, payload_json, updated_at
            FROM peer_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None
        return {
            "cache_key": row["cache_key"],
            "symbol": row["symbol"],
            "peer_limit": int(row["peer_limit"]),
            "peer_basis": row["peer_basis"],
            "payload": payload,
            "updated_at": datetime.fromisoformat(row["updated_at"]),
        }


def upsert_options_chain_cache(
    cache_key: str,
    *,
    symbol: str,
    expiration: str,
    spot: Optional[float],
    payload: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO options_chain_cache(cache_key, symbol, expiration, spot, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                symbol=excluded.symbol,
                expiration=excluded.expiration,
                spot=excluded.spot,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (
                cache_key,
                symbol.upper(),
                expiration,
                spot,
                json.dumps(payload),
                now,
            ),
        )


def get_options_chain_cache(cache_key: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT cache_key, symbol, expiration, spot, payload_json, updated_at
            FROM options_chain_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None
        return {
            "cache_key": row["cache_key"],
            "symbol": row["symbol"],
            "expiration": row["expiration"],
            "spot": row["spot"],
            "payload": payload,
            "updated_at": datetime.fromisoformat(row["updated_at"]),
        }


def get_latest_options_chain_cache(symbol: str) -> Optional[dict[str, Any]]:
    """Most recently updated chain cache row for a symbol (any expiration)."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT cache_key, symbol, expiration, spot, payload_json, updated_at
            FROM options_chain_cache
            WHERE symbol = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (symbol.upper(),),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None
        return {
            "cache_key": row["cache_key"],
            "symbol": row["symbol"],
            "expiration": row["expiration"],
            "spot": row["spot"],
            "payload": payload,
            "updated_at": datetime.fromisoformat(row["updated_at"]),
        }


def upsert_earnings_analysis_snapshot(symbol: str, payload: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO earnings_analysis_snapshots(symbol, payload_json, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                payload_json=excluded.payload_json,
                fetched_at=excluded.fetched_at
            """,
            (symbol.upper(), json.dumps(payload), now),
        )


def list_known_symbols(limit: int = 500) -> list[str]:
    """Distinct symbols with cached data (for sitemap)."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT symbol FROM (
                SELECT DISTINCT symbol FROM ohlcv
                UNION
                SELECT DISTINCT ticker AS symbol FROM screen_snapshots
            )
            ORDER BY symbol
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [str(r["symbol"]) for r in rows if r["symbol"]]


def load_earnings_analysis_snapshot(symbol: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT symbol, payload_json, fetched_at
            FROM earnings_analysis_snapshots
            WHERE symbol = ?
            """,
            (symbol.upper(),),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None
        return {
            "symbol": row["symbol"],
            "payload": payload,
            "fetched_at": row["fetched_at"],
        }


def upsert_options_contract_cache(
    cache_key: str,
    *,
    contract_symbol: str,
    period: str,
    payload: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO options_contract_cache(cache_key, contract_symbol, period, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                contract_symbol=excluded.contract_symbol,
                period=excluded.period,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (
                cache_key,
                contract_symbol.upper(),
                period,
                json.dumps(payload),
                now,
            ),
        )


def get_options_contract_cache(cache_key: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT cache_key, contract_symbol, period, payload_json, updated_at
            FROM options_contract_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None
        return {
            "cache_key": row["cache_key"],
            "contract_symbol": row["contract_symbol"],
            "period": row["period"],
            "payload": payload,
            "updated_at": datetime.fromisoformat(row["updated_at"]),
        }


def upsert_options_strategy_cache(
    cache_key: str,
    *,
    symbol: str,
    expiration: str,
    payload: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO options_strategy_cache(cache_key, symbol, expiration, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                symbol=excluded.symbol,
                expiration=excluded.expiration,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (
                cache_key,
                symbol.upper(),
                expiration,
                json.dumps(payload),
                now,
            ),
        )


def get_options_strategy_cache(cache_key: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT cache_key, symbol, expiration, payload_json, updated_at
            FROM options_strategy_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None
        return {
            "cache_key": row["cache_key"],
            "symbol": row["symbol"],
            "expiration": row["expiration"],
            "payload": payload,
            "updated_at": datetime.fromisoformat(row["updated_at"]),
        }


def upsert_options_iv_snapshot(
    *,
    symbol: str,
    as_of_date: str,
    expiration: str,
    dte: Optional[int],
    atm_iv: Optional[float],
    spot: Optional[float],
    call_volume: Optional[float] = None,
    put_volume: Optional[float] = None,
    call_oi: Optional[float] = None,
    put_oi: Optional[float] = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO options_iv_snapshots(
                symbol, as_of_date, expiration, dte, atm_iv, spot,
                call_volume, put_volume, call_oi, put_oi
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, as_of_date, expiration) DO UPDATE SET
                dte=excluded.dte,
                atm_iv=excluded.atm_iv,
                spot=excluded.spot,
                call_volume=excluded.call_volume,
                put_volume=excluded.put_volume,
                call_oi=excluded.call_oi,
                put_oi=excluded.put_oi
            """,
            (
                symbol.upper(),
                as_of_date[:10],
                expiration[:10],
                dte,
                atm_iv,
                spot,
                call_volume,
                put_volume,
                call_oi,
                put_oi,
            ),
        )


def load_options_iv_snapshots(
    symbol: str,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    expiration: Optional[str] = None,
) -> pd.DataFrame:
    clauses = ["symbol = ?"]
    params: list = [symbol.upper()]
    if start:
        clauses.append("as_of_date >= ?")
        params.append(start[:10])
    if end:
        clauses.append("as_of_date <= ?")
        params.append(end[:10])
    if expiration:
        clauses.append("expiration = ?")
        params.append(expiration[:10])
    where = " AND ".join(clauses)
    with get_conn() as conn:
        return pd.read_sql_query(
            f"""
            SELECT symbol, as_of_date, expiration, dte, atm_iv, spot,
                   call_volume, put_volume, call_oi, put_oi
            FROM options_iv_snapshots
            WHERE {where}
            ORDER BY as_of_date, expiration
            """,
            conn,
            params=params,
        )


def load_earnings_events_range(
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    symbols: Optional[list[str]] = None,
) -> pd.DataFrame:
    clauses: list[str] = []
    params: list = []
    if start:
        clauses.append("report_datetime >= ?")
        params.append(start)
    if end:
        clauses.append("report_datetime <= ?")
        params.append(end)
    if symbols:
        cleaned = [s.upper() for s in symbols if s]
        if cleaned:
            placeholders = ",".join("?" for _ in cleaned)
            clauses.append(f"symbol IN ({placeholders})")
            params.extend(cleaned)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        df = pd.read_sql_query(
            f"""
            SELECT symbol, report_datetime, reported_eps, eps_estimate, surprise_pct
            FROM earnings_events
            {where}
            ORDER BY report_datetime, symbol
            """,
            conn,
            params=params,
        )
    if not df.empty:
        df["report_datetime"] = pd.to_datetime(df["report_datetime"], errors="coerce")
    return df


def _f(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
