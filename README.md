# Ledgerline — Finance Quant Metrics

Historical quant metrics for US equities & ETFs, with a React UI and FastAPI backend on free data sources.

## Data stack

| Role | Source | Notes |
|------|--------|--------|
| Prices | [yfinance](https://github.com/ranaroussi/yfinance) → Stooq fallback | Daily OHLCV, cached in SQLite. Stooq is best-effort (often bot-blocked). |
| Fundamentals | [SEC EDGAR companyfacts](https://www.sec.gov/edgar/sec-api-documentation) | US GAAP XBRL → ratios |
| Macro | [FRED](https://fred.stlouisfed.org/docs/api/fred/) | Risk-free rate, VIX, CPI, etc. |

Most quant metrics (returns, vol, Sharpe, drawdown, beta, RSI/MACD, …) are **computed locally** from cached OHLCV.

## Setup

```bash
cd finance-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set SEC_USER_AGENT to include your email (required by SEC).
# Optionally set FRED_API_KEY (free) — CSV fallback works without it.

cd web
npm install
cp .env.example .env   # VITE_API_URL=http://localhost:8000/api/v1
```

## Run (API + UI)

One command (frees ports 8000/5180 if needed, starts both, Ctrl+C stops both):

```bash
cd finance-app
chmod +x dev.sh   # once
./dev.sh
```

Then open **http://localhost:5180** (e.g. `/s/INTC`).

```bash
./dev.sh --status   # what's running
./dev.sh --stop     # stop API + UI
```

Or run the two processes yourself:

Terminal 1 — API on `:8000`:

```bash
cd finance-app
source .venv/bin/activate
export PYTHONPATH=src
uvicorn finance_app.main:app --reload --port 8000
```

Terminal 2 — React app on `:5180`:

```bash
cd finance-app/web
npm run dev
```

Open **http://localhost:5180** — search a ticker (e.g. `INTC`) or go to `/s/INTC`.

API docs: http://localhost:8000/docs

## Docker / Railway

Single container: builds the Vite UI, serves it from FastAPI, API under `/api/v1`.

```bash
docker build -t ledgerline .
docker run --rm -p 8000:8000 \
  -e SEC_USER_AGENT="Ledgerline/0.1 (you@example.com)" \
  -e FRED_API_KEY= \
  -v ledgerline-data:/data \
  ledgerline
```

Open **http://localhost:8000**. Health: `/health`. Docs: `/docs`.

### Railway

Repo includes `Dockerfile` + `railway.json`. Recommended vars:

| Variable | Example |
|----------|---------|
| `SEC_USER_AGENT` | `Ledgerline/0.1 (you@example.com)` |
| `FRED_API_KEY` | optional |
| `DATABASE_PATH` | `/data/finance.db` |

Attach a Railway volume at `/data` so the SQLite cache survives redeploys.

## Screener

S&P 500 snapshot screener (price + EDGAR metrics).

```bash
# Partial refresh (recommended first — free APIs are slow)
export PYTHONPATH=src
python -m finance_app.jobs.refresh_screener --limit 25

# Or via API while the server is running
curl -X POST "http://localhost:8000/api/v1/screen/refresh?limit=25"

# Query
curl "http://localhost:8000/api/v1/screen?pe_max=25&sort=momentum_12m&order=desc"
```

UI: **http://localhost:5180/screen** (or `/screen` in Docker)

## Example API endpoints

```bash
curl "http://localhost:8000/api/v1/symbols/INTC/metrics"
curl "http://localhost:8000/api/v1/symbols/INTC/history?start=2020-01-01"
curl "http://localhost:8000/api/v1/symbols/INTC/technicals"
curl "http://localhost:8000/api/v1/symbols/INTC/fundamentals"
curl "http://localhost:8000/api/v1/macro/VIXCLS"
```

## Tests

```bash
export PYTHONPATH=src
python3 -m pytest tests/ -q
```

```bash
cd web && npm run build
```

## Disclaimer

Free price feeds are unofficial / delayed and are not suitable as a sole source for live trading decisions.
