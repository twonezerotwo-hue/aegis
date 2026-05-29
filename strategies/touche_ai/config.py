"""
Touche AI - Configuration
LIVE_INTEGRATION: Pydantic v2 BaseSettings reading from .env
"""
from __future__ import annotations

from pydantic import Field
from pydantic import AliasChoices
from pydantic_settings import BaseSettings


class ToucheConfig(BaseSettings):
    # LIVE_INTEGRATION: data_mode controls LIVE vs MOCK path in data_fetcher
    data_mode: str = Field(default="LIVE", validation_alias="DATA_MODE")

    binance_base_url: str = Field(
        default="https://api.binance.com", validation_alias="BINANCE_BASE_URL"
    )
    # FIX: accept both BINANCE_TIMEOUT and BINANCE_REQUEST_TIMEOUT for backward compatibility
    binance_timeout: float = Field(
        default=5.0,
        validation_alias=AliasChoices("BINANCE_TIMEOUT", "BINANCE_REQUEST_TIMEOUT"),
    )
    binance_retries: int = 3
    binance_rate_limit_per_min: int = Field(
        default=1200, validation_alias="BINANCE_RATE_LIMIT_PER_MIN"
    )

    # LIVE_INTEGRATION: Keys read only from env – never hard-coded
    binance_api_key: str = Field(default="", validation_alias="BINANCE_API_KEY")
    binance_secret_key: str = Field(default="", validation_alias="BINANCE_API_SECRET")

    cache_ttl_seconds: int = 300
    fallback_to_mock: bool = False

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    redis_url: str = Field(
        default="redis://localhost:6379/0", validation_alias="REDIS_URL"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }


# Module-level singleton
config = ToucheConfig()
