from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fred_api_key: str = ""
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

    @property
    def db_path(self) -> Path:
        return Path(self.database_path).expanduser().resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return origins or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
