"""
Consensus routes - Dinamik ağırlıklandırma & Multi-module metrics
AEGIS v7.1: horizon query param forwarding (short/medium/long).
"""
from fastapi import APIRouter, Query
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../")))

# Import yeni modülleri
try:
    from consensus_engine.src.dynamic_consensus import (
        DynamicWeightingEngine,
        ConflictResolutionEngine,
        PerformanceFeedbackLoop,
    )
except ImportError:
    pass

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/consensus", tags=["consensus"])

# Horizon-specific module weights (mirrors horizon_configs.yaml)
_VALID_HORIZONS = {"short", "medium", "long"}
_HORIZON_WEIGHTS: dict[str, dict[str, float]] = {
    "short":  {"Touche": 0.40, "Fundamental": 0.25, "News": 0.15, "Sentinel": 0.12, "Quantum": 0.08},
    "medium": {"Touche": 0.35, "Fundamental": 0.30, "News": 0.20, "Sentinel": 0.10, "Quantum": 0.05},
    "long":   {"Touche": 0.25, "Fundamental": 0.40, "News": 0.10, "Sentinel": 0.15, "Quantum": 0.10},
}

# Global instances
dynamic_weighting = None
conflict_resolver = None
performance_loop = None


def init_consensus_engines(config: dict = None):
    """Initialize consensus engines"""
    global dynamic_weighting, conflict_resolver, performance_loop
    try:
        dynamic_weighting = DynamicWeightingEngine(config=config)
        conflict_resolver = ConflictResolutionEngine()
        performance_loop = PerformanceFeedbackLoop(config=config)
        logger.info("Consensus engines initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize consensus engines: {e}")


@router.get("/")
async def get_consensus_route(
    horizon: str = Query("medium", description="Investment horizon: short | medium | long"),
):
    """Get consensus dengan dinamik ağırlıklandırma"""
    # Validate horizon — fall back to medium for unknown values
    if horizon not in _VALID_HORIZONS:
        horizon = "medium"

    try:
        # Use horizon-specific weights; override with dynamic engine when available
        horizon_weights = _HORIZON_WEIGHTS[horizon]
        if dynamic_weighting:
            current_weights = dynamic_weighting.get_current_weights()
            # Merge: horizon base weights as fallback when dynamic engine lacks a key
            for k, v in horizon_weights.items():
                current_weights.setdefault(k, v)
        else:
            current_weights = horizon_weights

        # Mock modül sinyalleri (gerçi senaryoda live olacak)
        touche_signal = "BULLISH"
        fundamental_signal = "BULLISH"
        news_signal = "NEUTRAL"

        # Çelişki çözümü
        resolution = None
        if conflict_resolver:
            resolution = conflict_resolver.resolve_conflict(
                touche_signal, fundamental_signal, news_signal, current_weights
            )

        # Mock component scores
        components = {
            "touche": {"score": 75, "signal": touche_signal, "weight": round(current_weights.get("Touche", 0.5) * 100, 1)},
            "fundamental": {"score": 68, "signal": fundamental_signal, "weight": round(current_weights.get("Fundamental", 0.35) * 100, 1)},
            "news": {"score": 55, "signal": news_signal, "weight": round(current_weights.get("News", 0.15) * 100, 1)},
        }

        # Weighted score hesapla
        weighted_score = (
            (components["touche"]["score"] / 100) * current_weights.get("Touche", 0.5) +
            (components["fundamental"]["score"] / 100) * current_weights.get("Fundamental", 0.35) +
            (components["news"]["score"] / 100) * current_weights.get("News", 0.15)
        )

        action = resolution["action"] if resolution else "BUY"
        confidence = resolution["confidence"] if resolution else 0.75

        return {
            "weighted_score": round(weighted_score, 3),
            "action": action,
            "confidence": confidence,
            "weights": {
                "touche": round(current_weights.get("Touche", 0.5), 3),
                "fundamental": round(current_weights.get("Fundamental", 0.35), 3),
                "news": round(current_weights.get("News", 0.15), 3),
            },
            "components": components,
            "resolution_method": resolution.get("resolution_method", "WEIGHTED") if resolution else "N/A",
            "weight_mode": "DYNAMIC",  # Yeni: dinamik mod göstergesi
            "horizon_applied": horizon,
        }
    except Exception as e:
        logger.error(f"Error in consensus route: {e}")
        # Fallback
        return {
            "weighted_score": 0.706,
            "action": "HOLD",
            "confidence": 0.5,
            "weights": {"touche": 0.50, "fundamental": 0.35, "news": 0.15},
            "components": {
                "touche": {"score": 0.75, "weight": 50},
                "fundamental": {"score": 0.68, "weight": 35},
                "news": {"score": 0.55, "weight": 15},
            },
            "error": str(e),
            "horizon_applied": horizon,
        }


@router.get("/performance")
async def get_module_performance():
    """Modüllerin performans istatistikleri"""
    if performance_loop:
        stats = performance_loop.get_module_stats()
        perf_data = performance_loop.calculate_7d_30d_accuracy()

        return {
            "modules": {
                name: {
                    "accuracy_7d": round(perf.accuracy_7d, 3),
                    "accuracy_30d": round(perf.accuracy_30d, 3),
                    "win_rate": round(perf.win_rate, 3),
                }
                for name, perf in perf_data.items()
            },
            "total_trades_recorded": len(performance_loop.trade_history),
        }
    return {"error": "Performance loop not initialized"}


@router.get("/weights/history")
async def get_weights_history():
    """Ağırlıkların tarihsel değişimini al"""
    if dynamic_weighting:
        return {
            "current_weights": dynamic_weighting.get_current_weights(),
            "default_weights": dynamic_weighting.DEFAULT_WEIGHTS,
            "message": "Weights are dynamically adjusted based on module performance",
        }
    return {"error": "Dynamic weighting not initialized"}
