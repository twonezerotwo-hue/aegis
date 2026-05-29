from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from ..signal_models import ImpactFactors, NewsItem, NewsSignal
from ..sentiment.sentiment_engine import get_sentiment_engine

_SOURCE_CREDIBILITY: dict[str, float] = {
    "Treasury.gov": 95.0,
    "SEC Announcements": 95.0,
    "CFTC": 95.0,
    "Federal Reserve": 95.0,
    "Reuters": 90.0,
    "Reuters Business": 90.0,
    "Reuters Technology": 90.0,
    "CoinDesk": 88.0,
    "Cointelegraph": 78.0,
    "FXStreet": 80.0,
}

_PERIOD_HOURS: dict[str, int] = {
    "realtime": 1,
    "1h": 1,
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
    "90d": 24 * 90,
}


def _avg(values: Iterable[float]) -> float:
    values = list(values)
    return float(sum(values) / len(values)) if values else 0.0


def _source_credibility(source_name: str) -> float:
    return _SOURCE_CREDIBILITY.get(source_name, 70.0)


def _filter_items(
    items: list[NewsItem],
    *,
    period: str,
    countries: list[str] | None,
    limit: int,
) -> list[NewsItem]:
    now = datetime.now(timezone.utc)
    max_age_hours = _PERIOD_HOURS.get(period, 24)
    country_set = {country.upper() for country in countries or []}
    filtered: list[NewsItem] = []
    for item in items:
        item_age_hours = max(0.0, (now - item.published_at.astimezone(timezone.utc)).total_seconds() / 3600.0)
        if item_age_hours > max_age_hours:
            continue
        if country_set and item.country.upper() not in country_set:
            continue
        filtered.append(item)
    filtered.sort(key=lambda item: item.published_at, reverse=True)
    return filtered[: max(1, min(limit, 50))]


async def build_live_news_signal(
    *,
    registry: Any,
    period: str,
    countries: list[str] | None,
    limit: int,
    horizon: str | None = None,
) -> dict[str, Any]:
    if registry is None:
        return _missing_signal("Source registry unavailable.", period, countries or [], horizon)

    items = await registry.fetch_from_all_sources()
    filtered_items = _filter_items(items, period=period, countries=countries, limit=limit)
    if not filtered_items:
        return _missing_signal("No live news items available for the requested window.", period, countries or [], horizon)

    sentiment_engine = await get_sentiment_engine()
    sentiment_scores = await sentiment_engine.analyze_batch(filtered_items)

    aggregated_sentiment = _avg(
        score.bullish_score - score.bearish_score for score in sentiment_scores
    )
    avg_confidence = _avg(score.confidence for score in sentiment_scores)
    avg_credibility = _avg(_source_credibility(item.source_name) for item in filtered_items)
    regulatory_ratio = _avg(1.0 if item.category == "regulatory" else 0.4 for item in filtered_items)
    now = datetime.now(timezone.utc)
    avg_age_hours = _avg(
        max(0.0, (now - item.published_at.astimezone(timezone.utc)).total_seconds() / 3600.0)
        for item in filtered_items
    )
    decay = max(0.4, min(1.0, 1.0 - (avg_age_hours / max(_PERIOD_HOURS.get(period, 24), 1)) * 0.6))
    market_mention_score = min(100.0, 20.0 + len(filtered_items) * 4.0)
    regulatory_score = min(100.0, regulatory_ratio * 100.0)
    sentiment_multiplier = max(0.7, min(1.3, 1.0 + aggregated_sentiment * 0.2))

    impact_score = min(
        100.0,
        max(
            0.0,
            (
                regulatory_score * 0.35
                + market_mention_score * 0.25
                + avg_credibility * 0.20
                + decay * 100.0 * 0.15
                + ((aggregated_sentiment + 1.0) / 2.0) * 100.0 * 0.05
            )
            * sentiment_multiplier,
        ),
    )

    signal = NewsSignal(
        signal_type="NEWS",
        timestamp=now,
        module_id="news-ai-limited-v1",
        crypto_impact_score=round(impact_score, 2),
        confidence_level=round(max(20.0, min(100.0, avg_confidence * 100.0)), 2),
        news_items_count=len(filtered_items),
        analysis_period=period,
        primary_countries=sorted({item.country for item in filtered_items})[:4],
        impact_factors=ImpactFactors(
            regulatory_score=round(regulatory_score, 2),
            market_mention_score=round(market_mention_score, 2),
            source_credibility=round(avg_credibility, 2),
            temporal_decay=round(decay, 4),
            sentiment_multiplier=round(sentiment_multiplier, 4),
        ),
        top_news_items=filtered_items[:10],
        aggregated_sentiment=round(aggregated_sentiment, 4),
        version="1.1",
    )

    return {
        "news_signal": signal,
        "source": "live_news_sources",
        "timestamp": signal.timestamp.isoformat(),
        "verified": True,
        "fallback_used": False,
        "data_status": "LIVE",
        "warnings": [],
        "horizon_applied": horizon,
    }


def _missing_signal(message: str, period: str, countries: list[str], horizon: str | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    signal = NewsSignal(
        signal_type="NEWS",
        timestamp=now,
        module_id="news-ai-limited-v1",
        crypto_impact_score=50.0,
        confidence_level=0.0,
        news_items_count=0,
        analysis_period=period,
        primary_countries=countries[:4],
        impact_factors=ImpactFactors(
            regulatory_score=0.0,
            market_mention_score=0.0,
            source_credibility=0.0,
            temporal_decay=0.0,
            sentiment_multiplier=1.0,
        ),
        top_news_items=[],
        aggregated_sentiment=0.0,
        version="1.1",
    )
    return {
        "news_signal": signal,
        "source": "live_news_unavailable",
        "timestamp": None,
        "verified": False,
        "fallback_used": False,
        "data_status": "MISSING",
        "warnings": [message],
        "horizon_applied": horizon,
    }
