"""
News AI Limited - Configuration & Settings

Loads environment variables and provides configuration for the module.
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # === SERVICE CONFIG ===
    service_name: str = "news-ai-limited"
    service_version: str = "1.0.0"
    api_port: int = int(os.getenv("NEWS_API_PORT", "8006"))
    api_host: str = os.getenv("NEWS_API_HOST", "0.0.0.0")

    # === LOGGING ===
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = "json"  # json or text

    # === REDIS ===
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
    consensus_channel: str = "consensus:signals:news"

    # === DATABASE (for storing news history) ===
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://aegis:aegis_secure_pass@localhost:5432/aegis"
    )

    # === SENTIMENT MODEL ===
    sentiment_model: str = os.getenv("SENTIMENT_MODEL", "finbert")  # finbert or distilbert
    model_cache_dir: str = os.getenv("MODEL_CACHE_DIR", "/tmp/models")

    # === NEWS SOURCES ===
    rss_feeds_enabled: bool = os.getenv("RSS_FEEDS_ENABLED", "true").lower() == "true"
    official_apis_enabled: bool = os.getenv("OFFICIAL_APIS_ENABLED", "true").lower() == "true"
    web_scraping_enabled: bool = os.getenv("WEB_SCRAPING_ENABLED", "true").lower() == "true"

    # === NEWS UPDATE FREQUENCY ===
    news_update_interval_minutes: int = int(os.getenv("NEWS_UPDATE_INTERVAL_MINUTES", "15"))

    # === CACHING ===
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 hour
    cache_enabled: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"

    # === API KEYS ===
    newsapi_key: Optional[str] = os.getenv("NEWSAPI_KEY", None)
    cryptopanic_api_key: Optional[str] = os.getenv("CRYPTOPANIC_API_KEY", None)

    # === RESILIENCE ===
    circuit_breaker_failure_threshold: int = int(
        os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
    )
    circuit_breaker_recovery_timeout_seconds: int = int(
        os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "60")
    )
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    retry_initial_delay_seconds: float = float(os.getenv("RETRY_INITIAL_DELAY", "1.0"))

    # === RATE LIMITING ===
    rate_limit_max_calls: int = int(os.getenv("RATE_LIMIT_MAX_CALLS", "100"))
    rate_limit_time_period_seconds: int = int(os.getenv("RATE_LIMIT_TIME_PERIOD", "60"))

    # === DATA LIMITS ===
    max_news_items_per_analysis: int = int(os.getenv("MAX_NEWS_ITEMS_PER_ANALYSIS", "100"))
    max_news_age_hours: int = int(os.getenv("MAX_NEWS_AGE_HOURS", "72"))

    # === IMPACT SCORING WEIGHTS ===
    weight_regulatory: float = float(os.getenv("WEIGHT_REGULATORY", "0.35"))
    weight_market_mention: float = float(os.getenv("WEIGHT_MARKET_MENTION", "0.25"))
    weight_source_credibility: float = float(os.getenv("WEIGHT_SOURCE_CREDIBILITY", "0.20"))
    weight_temporal: float = float(os.getenv("WEIGHT_TEMPORAL", "0.15"))
    weight_sentiment: float = float(os.getenv("WEIGHT_SENTIMENT", "0.05"))

    temporal_decay_half_life_hours: float = float(os.getenv("TEMPORAL_DECAY_HALF_LIFE", "72"))

    # === MOCK MODE (for development) ===
    mock_news_generation: bool = os.getenv("MOCK_NEWS_GENERATION", "false").lower() == "true"
    mock_sentiment_scores: bool = os.getenv("MOCK_SENTIMENT_SCORES", "false").lower() == "true"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def validate_weights(self):
        """Ensure impact scoring weights sum to 1.0"""
        total_weight = (
            self.weight_regulatory +
            self.weight_market_mention +
            self.weight_source_credibility +
            self.weight_temporal +
            self.weight_sentiment
        )
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"Impact scoring weights must sum to 1.0, got {total_weight}")

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.log_level == "WARNING" or self.log_level == "ERROR"

    @property
    def redis_options(self) -> dict:
        """Redis connection options"""
        return {
            "url": self.redis_url,
            "max_connections": self.redis_max_connections,
            "decode_responses": True,
        }


# Global settings singleton
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance"""
    global settings
    if settings is None:
        settings = Settings()
        settings.validate_weights()
    return settings
