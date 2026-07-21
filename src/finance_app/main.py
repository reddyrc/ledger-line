from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from finance_app import __version__
from finance_app.api import router
from finance_app.config import get_settings
from finance_app.db import init_db

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
        "yfinance/Stooq (prices), SEC EDGAR (fundamentals), FRED (macro)."
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
            "prices": ["yfinance", "stooq"],
            "fundamentals": ["sec_edgar"],
            "macro": ["fred"],
        },
    }


if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        # Let API / docs / OpenAPI through; serve SPA for client routes.
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "health")):
            return FileResponse(WEB_DIST / "index.html", status_code=404)
        candidate = WEB_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
else:

    @app.get("/")
    def root() -> dict:
        return {
            "name": "Ledgerline API",
            "version": __version__,
            "docs": "/docs",
            "hint": "UI not bundled — run Vite locally or build web/dist",
            "sources": {
                "prices": ["yfinance", "stooq"],
                "fundamentals": ["sec_edgar"],
                "macro": ["fred"],
            },
        }
