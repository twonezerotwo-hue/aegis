"""
News AI Limited - Source Registry

Dynamically manages all data sources (RSS, APIs, scrapers).
Allows runtime enable/disable, tracks availability, manages configuration.
"""
from typing import Dict, Optional
import asyncio
from datetime import datetime, timezone
from .base_source import BaseDataSource
from .rss_aggregator import RSSAggregator
from .official_statements import OfficialStatementsAPI
from ..logging.logger_config import get_logger
from ..config import get_settings
from ..deduplication import DedupEngine

logger = get_logger(__name__)


class SourceRegistry:
    """
    Registry for managing all data sources

    Features:
    - Dynamic enable/disable of sources
    - Track source health and statistics
    - Concurrent fetching from all enabled sources
    - Configuration persistence
    """

    def __init__(self):
        """Initialize source registry"""
        self.sources: Dict[str, BaseDataSource] = {}
        self.settings = get_settings()
        self._initialize_default_sources()
        # Deduplication engine — Redis client injected lazily after startup
        self.dedup_engine: DedupEngine = DedupEngine(redis_client=None)

    def _initialize_default_sources(self):
        """Initialize default sources based on settings"""
        logger.info("source_registry_initializing")

        # Add RSS Aggregator
        if self.settings.rss_feeds_enabled:
            self.register_source("rss_aggregator", RSSAggregator())
            logger.info("rss_aggregator_registered")

        # Add Official Statements API
        if self.settings.official_apis_enabled:
            self.register_source("official_statements", OfficialStatementsAPI())
            logger.info("official_statements_registered")

        # Note: WebScraper will be added by Phase 2B implementation
        # if self.settings.web_scraping_enabled:
        #     self.register_source("web_scraper", WebScraper())

    def register_source(self, source_id: str, source: BaseDataSource):
        """
        Register a new data source

        Args:
            source_id: Unique identifier for the source
            source: BaseDataSource instance
        """
        self.sources[source_id] = source
        logger.info(
            "source_registered",
            source_id=source_id,
            source_name=source.source_name,
        )

    def unregister_source(self, source_id: str):
        """Unregister a data source"""
        if source_id in self.sources:
            del self.sources[source_id]
            logger.info("source_unregistered", source_id=source_id)

    def enable_source(self, source_id: str):
        """Enable a data source"""
        if source_id in self.sources:
            self.sources[source_id].is_enabled = True
            logger.info("source_enabled", source_id=source_id)

    def disable_source(self, source_id: str):
        """Disable a data source"""
        if source_id in self.sources:
            self.sources[source_id].is_enabled = False
            logger.info("source_disabled", source_id=source_id)

    async def fetch_from_all_sources(self):
        """
        Fetch news from all enabled sources concurrently

        Returns:
            List of all news items from all sources
        """
        logger.info(
            "fetch_from_all_sources_started",
            enabled_sources_count=len([s for s in self.sources.values() if s.is_enabled]),
        )

        tasks = []
        for source_id, source in self.sources.items():
            if source.is_enabled:
                task = source.fetch()
                tasks.append((source_id, task))

        all_news_items = []

        # Run all sources concurrently with timeout
        for source_id, task in tasks:
            try:
                news_items = await asyncio.wait_for(task, timeout=30)
                all_news_items.extend(news_items)
                logger.debug(f"fetch_source_success: {source_id}, items: {len(news_items)}")
            except asyncio.TimeoutError:
                logger.warning(f"fetch_source_timeout: {source_id}")
            except Exception as e:
                logger.error(f"fetch_source_error: {source_id}, error: {str(e)}")

        logger.info(
            "fetch_from_all_sources_completed",
            total_items=len(all_news_items),
        )

        # ── Deduplication ───────────────────────────────────────────────────
        dedup_result = self.dedup_engine.deduplicate(all_news_items)
        logger.info(
            "fetch_dedup_applied input=%d unique=%d duplicates=%d rate=%.1f%%",
            dedup_result.total_input,
            len(dedup_result.unique_items),
            dedup_result.total_duplicates,
            dedup_result.dedup_rate_pct,
        )
        return dedup_result.unique_items

    def inject_redis(self, redis_client) -> None:
        """Attach a live Redis client to the dedup engine after startup."""
        self.dedup_engine = DedupEngine(redis_client=redis_client)
        logger.info("source_registry_redis_injected")

    def get_source_status(self, source_id: str) -> Optional[Dict]:
        """
        Get status of a specific source

        Returns:
            Dict with source status information
        """
        if source_id not in self.sources:
            return None

        source = self.sources[source_id]
        return {
            "source_id": source_id,
            "source_name": source.source_name,
            "country": source.country,
            "is_enabled": source.is_enabled,
            "is_healthy": source.is_healthy,
            "total_fetches": source.total_fetches,
            "failed_fetches": source.failed_fetches,
            "success_rate": source.success_rate,
        }

    def get_all_sources_status(self) -> Dict[str, Dict]:
        """
        Get status of all sources

        Returns:
            Dict mapping source_id to status information
        """
        status = {}
        for source_id in self.sources.keys():
            source_status = self.get_source_status(source_id)
            if source_status:
                status[source_id] = source_status

        return status

    def get_health_summary(self) -> Dict:
        """
        Get health summary of the registry

        Returns:
            Dict with overall health metrics
        """
        all_status = self.get_all_sources_status()

        enabled = [s for s in all_status.values() if s["is_enabled"]]
        healthy = [s for s in enabled if s["is_healthy"]]
        total_fetches = sum(s["total_fetches"] for s in all_status.values())
        total_failures = sum(s["failed_fetches"] for s in all_status.values())

        return {
            "total_sources": len(all_status),
            "enabled_sources": len(enabled),
            "healthy_sources": len(healthy),
            "total_fetches": total_fetches,
            "total_failures": total_failures,
            "average_success_rate": (
                sum(s["success_rate"] for s in all_status.values()) / len(all_status)
                if all_status
                else 0.0
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def export_config(self) -> Dict:
        """
        Export current registry configuration as JSON

        Returns:
            Configuration dict
        """
        config = {
            "sources": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for source_id, source in self.sources.items():
            config["sources"][source_id] = {
                "name": source.source_name,
                "country": source.country,
                "enabled": source.is_enabled,
            }

        return config

    def import_config(self, config: Dict):
        """
        Import configuration from JSON

        Args:
            config: Configuration dict with source settings
        """
        if "sources" not in config:
            logger.warning("invalid_config_format")
            return

        for source_id, settings in config["sources"].items():
            if source_id in self.sources:
                self.sources[source_id].is_enabled = settings.get("enabled", True)
                logger.info(
                    "config_imported_for_source",
                    source_id=source_id,
                    enabled=settings.get("enabled"),
                )


# Global registry singleton
_registry: Optional[SourceRegistry] = None


def get_source_registry() -> SourceRegistry:
    """Get or create the global source registry"""
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
    return _registry
