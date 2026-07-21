from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

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
    PRIMARY KEY (cik, concept, end_date, form)
);

CREATE TABLE IF NOT EXISTS macro_series (
    series_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (series_id, date)
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

CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol ON ohlcv(symbol);
CREATE INDEX IF NOT EXISTS idx_fund_ticker ON fundamentals(ticker);
CREATE INDEX IF NOT EXISTS idx_macro_series ON macro_series(series_id);
CREATE INDEX IF NOT EXISTS idx_screen_sector ON screen_snapshots(sector);
CREATE INDEX IF NOT EXISTS idx_screen_pe ON screen_snapshots(pe);
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
        conn.commit()


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
    """rows: (cik, ticker, concept, end_date, value, unit, form, fy, fp)"""
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO fundamentals(cik, ticker, concept, end_date, value, unit, form, fy, fp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cik, concept, end_date, form) DO UPDATE SET
                ticker=excluded.ticker,
                value=excluded.value,
                unit=excluded.unit,
                fy=excluded.fy,
                fp=excluded.fp
            """,
            rows,
        )
    return len(rows)


def load_fundamentals(ticker: str, concepts: Optional[list[str]] = None) -> pd.DataFrame:
    clauses = ["ticker = ?"]
    params: list = [ticker.upper()]
    if concepts:
        placeholders = ",".join("?" * len(concepts))
        clauses.append(f"concept IN ({placeholders})")
        params.extend(concepts)
    sql = f"""
        SELECT cik, ticker, concept, end_date, value, unit, form, fy, fp
        FROM fundamentals
        WHERE {' AND '.join(clauses)}
        ORDER BY end_date
    """
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


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


def _f(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
