from __future__ import annotations

from copy import deepcopy
from typing import Any


SAFE_MODE = "RESEARCH_ONLY_NO_ORDER_ROUTING"
CATALOG_DATE = "2026-06-08"


_EXTERNAL_REPO_FEATURES: tuple[dict[str, Any], ...] = (
    {
        "repo": "OpenBB-finance/OpenBB",
        "url": "https://github.com/OpenBB-finance/OpenBB",
        "license": "NOASSERTION",
        "category": "financial data platform",
        "best_features": [
            "multi-provider financial data abstraction",
            "analyst-friendly research workflows",
            "AI-agent-ready data platform shape",
        ],
        "aegis_status": "PARTIAL",
        "current_aegis_surface": [
            "dashboard market/macro routes",
            "aegis_research read-only adapter inventory",
            "news and module provenance labels",
        ],
        "missing_or_weak": [
            "unified provider registry",
            "standard quote/fundamental/news snapshot schema",
            "provider health and freshness scoring per adapter",
        ],
        "safe_integration_target": [
            "read-only provider catalog",
            "DataSnapshot-compatible market/fundamental adapters",
            "dashboard research inventory endpoint",
        ],
        "blocked_from_integration": [
            "vendoring a large platform without license review",
            "presenting non-verified provider data as live exchange truth",
        ],
        "phase": "phase_1",
    },
    {
        "repo": "freqtrade/freqtrade",
        "url": "https://github.com/freqtrade/freqtrade",
        "license": "GPL-3.0",
        "category": "crypto bot and backtesting",
        "best_features": [
            "strategy lifecycle discipline",
            "dry-run/backtest separation",
            "hyper-parameter experiment UX",
        ],
        "aegis_status": "PARTIAL",
        "current_aegis_surface": [
            "agent DRY_RUN journal",
            "dashboard backtest routes",
            "research threshold suggestions",
        ],
        "missing_or_weak": [
            "consistent experiment registry",
            "clean strategy result comparison",
            "safe hyper-parameter audit trail",
        ],
        "safe_integration_target": [
            "experiment metadata schema",
            "strategy/backtest report normalization",
            "shadow-only threshold comparison",
        ],
        "blocked_from_integration": [
            "GPL production dependency",
            "bot runtime and broker-facing modules",
        ],
        "phase": "phase_2",
    },
    {
        "repo": "microsoft/qlib",
        "url": "https://github.com/microsoft/qlib",
        "license": "MIT",
        "category": "AI quant research",
        "best_features": [
            "feature engineering pipeline",
            "walk-forward model research",
            "model evaluation and experiment tracking patterns",
        ],
        "aegis_status": "PARTIAL",
        "current_aegis_surface": [
            "aegis_research metrics and calibration",
            "agent outcome store",
            "module score journal",
        ],
        "missing_or_weak": [
            "feature store abstraction",
            "walk-forward validation runner",
            "model-vs-rule comparison reports",
        ],
        "safe_integration_target": [
            "offline research runner design",
            "feature importance report schema",
            "shadow-only model score evidence",
        ],
        "blocked_from_integration": [
            "automatic production config writes",
            "direct model output promotion without owner approval",
        ],
        "phase": "phase_2",
    },
    {
        "repo": "ccxt/ccxt",
        "url": "https://github.com/ccxt/ccxt",
        "license": "MIT",
        "category": "crypto exchange API",
        "best_features": [
            "broad exchange market-data interface",
            "symbol normalization patterns",
            "rate-limit and exchange capability metadata",
        ],
        "aegis_status": "PARTIAL",
        "current_aegis_surface": [
            "Touche Binance public data",
            "price validator",
            "data freshness labels",
        ],
        "missing_or_weak": [
            "read-only multi-exchange adapter allowlist",
            "exchange capability inventory",
            "cross-source price validation",
        ],
        "safe_integration_target": [
            "read-only OHLCV/ticker adapter",
            "exchange health metadata",
            "source disagreement warning",
        ],
        "blocked_from_integration": [
            "private credentials",
            "broker-facing method exposure",
            "state-changing exchange calls",
        ],
        "phase": "phase_1",
    },
    {
        "repo": "ranaroussi/yfinance",
        "url": "https://github.com/ranaroussi/yfinance",
        "license": "Apache-2.0",
        "category": "market data",
        "best_features": [
            "simple equity/index/fundamental data access",
            "broad ticker coverage",
            "fast research prototyping",
        ],
        "aegis_status": "PARTIAL",
        "current_aegis_surface": [
            "YFinanceReadOnlyAdapter availability",
            "research/dev data warning",
        ],
        "missing_or_weak": [
            "actual snapshot fetcher behind the adapter",
            "timestamp provenance per value",
            "UI labeling for research-only snapshots",
        ],
        "safe_integration_target": [
            "DataSnapshot fetch methods",
            "research-only dashboard display",
            "freshness and verified=false labels",
        ],
        "blocked_from_integration": [
            "showing Yahoo-derived data as verified live exchange data",
        ],
        "phase": "phase_1",
    },
    {
        "repo": "mementum/backtrader",
        "url": "https://github.com/mementum/backtrader",
        "license": "GPL-3.0",
        "category": "backtesting",
        "best_features": [
            "mature event-style backtest concepts",
            "indicator and strategy separation",
            "analyzers for result summaries",
        ],
        "aegis_status": "PARTIAL",
        "current_aegis_surface": [
            "dashboard backtest routes",
            "aegis_core backtest evidence formatter",
        ],
        "missing_or_weak": [
            "consistent analyzer schema",
            "walk-forward result comparison",
            "look-ahead safety checklist per run",
        ],
        "safe_integration_target": [
            "backtest evidence normalization",
            "analyzer metric naming",
            "look-ahead-safe report checklist",
        ],
        "blocked_from_integration": [
            "GPL production dependency",
            "framework vendoring",
        ],
        "phase": "phase_2",
    },
    {
        "repo": "QuantConnect/Lean",
        "url": "https://github.com/QuantConnect/Lean",
        "license": "Apache-2.0",
        "category": "algorithmic engine",
        "best_features": [
            "clean algorithm lifecycle",
            "data subscription model",
            "backtest/live parity discipline",
        ],
        "aegis_status": "NO",
        "current_aegis_surface": [
            "legacy services are separate from aegis_core",
            "safe core is signal-only",
        ],
        "missing_or_weak": [
            "formal lifecycle contract for research jobs",
            "dataset subscription manifest",
            "benchmark harness independent of runtime services",
        ],
        "safe_integration_target": [
            "research job lifecycle interface",
            "dataset manifest schema",
            "external benchmark notes only",
        ],
        "blocked_from_integration": [
            "full engine merge",
            "live trading parity path inside safe core",
        ],
        "phase": "phase_3",
    },
    {
        "repo": "hummingbot/hummingbot",
        "url": "https://github.com/hummingbot/hummingbot",
        "license": "Apache-2.0",
        "category": "market making bot",
        "best_features": [
            "connector architecture",
            "market microstructure data patterns",
            "strategy configuration discipline",
        ],
        "aegis_status": "NO",
        "current_aegis_surface": [
            "Touche technical metrics",
            "legacy quantum/market modules",
        ],
        "missing_or_weak": [
            "orderbook imbalance evidence",
            "spread/liquidity feature snapshots",
            "connector capability registry",
        ],
        "safe_integration_target": [
            "read-only orderbook evidence schema",
            "liquidity feature scoring",
            "connector capability inventory",
        ],
        "blocked_from_integration": [
            "market-making runtime",
            "inventory management",
            "exchange state-changing calls",
        ],
        "phase": "phase_3",
    },
    {
        "repo": "ProsusAI/finBERT",
        "url": "https://github.com/ProsusAI/finBERT",
        "license": "Apache-2.0",
        "category": "financial sentiment",
        "best_features": [
            "financial-domain sentiment model",
            "positive/negative/neutral probability shape",
            "news text scoring baseline",
        ],
        "aegis_status": "PARTIAL",
        "current_aegis_surface": [
            "news-ai-limited sentiment engine references FinBERT",
            "crypto lexicon and pattern sentiment fallback",
            "news score in consensus weights",
        ],
        "missing_or_weak": [
            "model availability surfaced in research inventory",
            "probability calibration report",
            "source-level sentiment contribution audit",
        ],
        "safe_integration_target": [
            "sentiment model availability snapshot",
            "calibration metrics for news sentiment",
            "auditable article-level evidence",
        ],
        "blocked_from_integration": [
            "unlabeled sentiment as standalone signal",
            "large model dependency forced into default runtime",
        ],
        "phase": "phase_1",
    },
    {
        "repo": "DemonDamon/FinnewsHunter",
        "url": "https://github.com/DemonDamon/FinnewsHunter",
        "license": "Apache-2.0",
        "category": "financial news intelligence",
        "best_features": [
            "multi-agent financial news analysis",
            "sentiment fusion",
            "alpha factor mining workflow",
        ],
        "aegis_status": "PARTIAL",
        "current_aegis_surface": [
            "news-ai-limited source registry",
            "impact scoring",
            "source reliability manager",
        ],
        "missing_or_weak": [
            "event taxonomy across sources",
            "cross-source deduplication audit in dashboard",
            "news-to-outcome factor mining reports",
        ],
        "safe_integration_target": [
            "news event taxonomy",
            "source fusion evidence",
            "shadow factor-mining reports",
        ],
        "blocked_from_integration": [
            "auto-promoting mined factors into production weights",
            "unverified breaking-news claims as live truth",
        ],
        "phase": "phase_1",
    },
)


def top10_external_repo_matrix() -> dict[str, Any]:
    """Return the curated top-10 integration matrix.

    This is a research catalog. It intentionally contains no order routing,
    broker calls, credentials, or production config mutation.
    """

    matrix = deepcopy(list(_EXTERNAL_REPO_FEATURES))
    return {
        "status": "ok",
        "catalog_date": CATALOG_DATE,
        "safe_mode": SAFE_MODE,
        "count": len(matrix),
        "items": matrix,
        "next_build_order": [
            "provider catalog and read-only DataSnapshot adapters",
            "news sentiment/model availability and source-fusion audit",
            "backtest/analyzer normalization",
            "offline feature-store and walk-forward research",
            "read-only orderbook/liquidity evidence",
        ],
        "non_negotiable": [
            "do not add broker-facing or state-changing exchange methods",
            "do not vendor GPL/AGPL code into production paths",
            "do not show research-only data as verified live data",
            "do not let research suggestions mutate production config automatically",
        ],
    }


def repo_feature_table_rows() -> list[dict[str, Any]]:
    """Compact rows for docs/UI tables."""

    rows: list[dict[str, Any]] = []
    for item in _EXTERNAL_REPO_FEATURES:
        rows.append({
            "repo": item["repo"],
            "category": item["category"],
            "aegis_status": item["aegis_status"],
            "best_feature": item["best_features"][0],
            "safe_target": item["safe_integration_target"][0],
            "phase": item["phase"],
            "license": item["license"],
        })
    return rows


__all__ = [
    "SAFE_MODE",
    "top10_external_repo_matrix",
    "repo_feature_table_rows",
]
