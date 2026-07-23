from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from finance_app import __version__
from finance_app.api import router
from finance_app.config import get_settings
from finance_app.db import init_db, list_known_symbols
from finance_app.seo import inject_meta, robots_txt, sitemap_xml

# Built React assets (Docker / production). Dev still uses Vite on :5180.
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="Ledgerline API",
    description=(
        "Historical quant metrics from free data sources: "
        "Tiingo/Stooq/yfinance (prices), SEC EDGAR (fundamentals), FRED (macro)."
    ),
    version=__version__,
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api")
def api_root() -> dict:
    return {
        "name": "Ledgerline API",
        "version": __version__,
        "docs": "/docs",
        "sources": {
            "prices": ["tiingo", "stooq", "yfinance"],
            "price_primary": get_settings().price_primary_normalized,
            "earnings": ["fmp", "yfinance"],
            "earnings_primary": get_settings().earnings_primary_normalized,
            "fundamentals": ["sec_edgar"],
            "macro": ["fred"],
            "news": ["tiingo"],
        },
    }


def _base_url(request: Request) -> str:
    configured = get_settings().public_base_url.strip()
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request) -> str:
    return robots_txt(_base_url(request))


@app.get("/sitemap.xml")
def sitemap(request: Request) -> Response:
    try:
        symbols = list_known_symbols()
    except Exception:
        symbols = []
    xml = sitemap_xml(_base_url(request), symbols)
    return Response(content=xml, media_type="application/xml")


if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    def _spa_html(path: str, request: Request) -> HTMLResponse:
        index_html = (WEB_DIST / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(inject_meta(index_html, path, _base_url(request)))

    @app.get("/")
    def spa_index(request: Request) -> HTMLResponse:
        return _spa_html("/", request)

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request) -> Response:
        # Let API / docs / OpenAPI through; serve SPA for client routes.
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "health")):
            return FileResponse(WEB_DIST / "index.html", status_code=404)
        candidate = WEB_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return _spa_html(full_path, request)
else:

    @app.get("/")
    def root() -> dict:
        return {
            "name": "Ledgerline API",
            "version": __version__,
            "docs": "/docs",
            "hint": "UI not bundled — run Vite locally or build web/dist",
            "sources": {
                "prices": ["tiingo", "stooq", "yfinance"],
                "price_primary": get_settings().price_primary_normalized,
                "earnings": ["fmp", "yfinance"],
                "earnings_primary": get_settings().earnings_primary_normalized,
                "fundamentals": ["sec_edgar"],
                "macro": ["fred"],
                "news": ["tiingo"],
            },
        }
