from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

PRICE_PRIMARY_CHOICES = frozenset({"tiingo", "yfinance", "finnhub"})
EARNINGS_PRIMARY_CHOICES = frozenset({"fmp", "yfinance", "finnhub"})


def normalize_price_primary(value: Optional[str], default: str = "tiingo") -> str:
    """Return tiingo | yfinance | finnhub; invalid/empty → default (tiingo)."""
    v = (value or default or "tiingo").strip().lower()
    return v if v in PRICE_PRIMARY_CHOICES else "tiingo"


def normalize_earnings_primary(
    value: Optional[str],
    *,
    default: str = "finnhub",
    fmp_configured: bool = False,
    finnhub_configured: bool = False,
) -> str:
    """
    Return fmp | yfinance | finnhub.
    If preferred needs a key that is missing, fall back to another available source.
    """
    v = (value or default or "finnhub").strip().lower()
    if v not in EARNINGS_PRIMARY_CHOICES:
        if finnhub_configured:
            v = "finnhub"
        elif fmp_configured:
            v = "fmp"
        else:
            v = "yfinance"
    if v == "finnhub" and not finnhub_configured:
        return "fmp" if fmp_configured else "yfinance"
    if v == "fmp" and not fmp_configured:
        return "finnhub" if finnhub_configured else "yfinance"
    return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fred_api_key: str = ""
    # Tiingo EOD prices / meta / news (https://api.tiingo.com) — set TIINGO_API_KEY
    tiingo_api_key: str = ""
    # Deploy-time OHLCV preference: tiingo | yfinance | finnhub (env: PRICE_PRIMARY)
    # Free Finnhub has no candles — default to tiingo for price history.
    price_primary: str = "tiingo"
    # Financial Modeling Prep — earnings calendar / EPS (env: FMP_API_KEY)
    fmp_api_key: str = ""
    # Finnhub — prices / earnings / news (env: FINNHUB_API_KEY)
    finnhub_api_key: str = ""
    # Paid Finnhub market-data plans only (env: FINNHUB_OHLCV)
    finnhub_ohlcv: bool = False
    # Deploy-time earnings preference: fmp | yfinance | finnhub (env: EARNINGS_PRIMARY)
    earnings_primary: str = "finnhub"
    # SEC requires a descriptive User-Agent with a contact email.
    sec_user_agent: str = "Ledgerline/0.1 (contact@example.com)"
    database_path: str = "./data/finance.db"
    default_benchmark: str = "SPY"
    # Cache TTL in hours before re-fetching prices
    price_cache_hours: int = 18
    # Default risk-free rate for Black–Scholes option greeks / scenarios
    options_risk_free: float = 0.04
    # Comma-separated browser origins allowed for CORS (empty = same-origin / * for local)
    cors_origins: str = (
        "http://localhost:5180,http://127.0.0.1:5180,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )
    # Canonical site origin for SEO (sitemap, canonical URLs), e.g. https://ledgerline.app
    public_base_url: str = ""

    @property
    def db_path(self) -> Path:
        return Path(self.database_path).expanduser().resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return origins or ["*"]

    @property
    def price_primary_normalized(self) -> str:
        return normalize_price_primary(self.price_primary)

    @property
    def fmp_configured(self) -> bool:
        return bool((self.fmp_api_key or "").strip())

    @property
    def finnhub_configured(self) -> bool:
        return bool((self.finnhub_api_key or "").strip())

    @property
    def finnhub_ohlcv_enabled(self) -> bool:
        """True when operator opts into Finnhub candles (paid market-data plan)."""
        return self.finnhub_configured and bool(self.finnhub_ohlcv)

    @property
    def earnings_primary_normalized(self) -> str:
        return normalize_earnings_primary(
            self.earnings_primary,
            fmp_configured=self.fmp_configured,
            finnhub_configured=self.finnhub_configured,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
