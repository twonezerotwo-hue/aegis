from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import os
import uuid
import yaml
from pydantic import BaseModel
from dotenv import load_dotenv
from services.prometheus_client import PrometheusClient
from services.sentinel_client import SentinelClient
try:
    from routes import aegis_core_routes as _aegis_core_routes_mod
    _aegis_core_available = True
except Exception as _aegis_core_import_err:
    _aegis_core_routes_mod = None  # type: ignore[assignment]
    _aegis_core_available = False
    import logging as _log
    _log.getLogger(__name__).warning("aegis_core_routes unavailable: %s", _aegis_core_import_err)

from routes import dashboard
from routes import paper_trading
from routes import macro
from routes import stream

# Setup logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import Touche AI components
try:
    from strategies.touche_ai.src.engine.scoring import EQSScorer
    from strategies.touche_ai.src.engine.unified_optimizer import UnifiedOptimizer, TradeRecord
    touche_available = True
    logger.info("Touche AI modules imported successfully")
except ImportError as e:
    touche_available = False
    logger.warning(f"Touche AI import failed: {e}")

load_dotenv()


# ========== AUTO REGIME â†’ WEIGHT SWITCHING ==========
# Sentinel regime â†’ consensus_weights.yaml'den dinamik aÄŸÄ±rlÄ±k getir
_CONSENSUS_WEIGHTS_PATH = os.environ.get(
    "CONSENSUS_WEIGHTS_PATH",
    "/app/consensus_engine/config/consensus_weights.yaml",
)

# Sentinel regime â†’ YAML regime_weights key mapping
_REGIME_MAP = {
    "LIQUIDITY_EXPANSION": "mega_bull",
    "NORMALIZATION": "bull",
    "RISK_OFF": "bear_2022",
    "ACCUMULATION": "accumulation",
}


async def get_regime_aware_weights(symbol: str = "BTC", timeframe: str = "1h") -> dict | None:
    """Query sentinel for market regime + correlation, return matching weights from consensus_weights.yaml."""
    sentinel_url = os.environ.get("SENTINEL_URL", "http://sentinel-api:8004")
    corr_regime = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{sentinel_url}/sentinel/macro", params={"horizon": "medium"})
            if resp.status_code == 200:
                data = resp.json()
                regime_raw = data.get("regime", "NORMALIZATION").upper()
                corr_data = data.get("correlation", {})
                corr_regime = corr_data.get("regime")
            else:
                regime_raw = "NORMALIZATION"
    except Exception as e:
        logger.warning(f"Regime detection failed, using default: {e}")
        return None

    regime_key = _REGIME_MAP.get(regime_raw, "default")

    try:
        with open(_CONSENSUS_WEIGHTS_PATH) as f:
            cfg = yaml.safe_load(f)

        # Check if correlation override should take precedence
        corr_overrides = cfg.get("correlation_overrides", {})
        if corr_regime and corr_regime in corr_overrides:
            override = corr_overrides[corr_regime]
            modifier = override.get("modifier", "none")

            if modifier == "override":
                weights = override.get("weights", {})
                if weights:
                    logger.info(f"auto_regime_switch: regime={regime_raw}, corr_regime={corr_regime} â†’ correlation override weights={weights}")
                    return weights
            elif modifier == "multiply":
                # First get base regime weights, then apply boost multipliers
                rw = cfg.get("regime_weights", {}).get(regime_key) or cfg.get("regime_weights", {}).get("default")
                if rw:
                    base_w = {
                        "touche": rw.get("touche_weight", 0.30),
                        "fundamental": rw.get("fundamental_weight", 0.40),
                        "news": rw.get("news_weight", 0.10),
                        "sentinel": rw.get("sentinel_weight", 0.15),
                        "quantum": rw.get("quantum_weight", 0.05),
                    }
                    boost = override.get("weights_boost", {})
                    for k in base_w:
                        base_w[k] = round(base_w[k] * boost.get(k, 1.0), 4)
                    # Re-normalize to sum=1.0
                    total = sum(base_w.values())
                    if total > 0:
                        base_w = {k: round(v / total, 4) for k, v in base_w.items()}
                    logger.info(f"auto_regime_switch: regime={regime_raw}, corr_regime={corr_regime} â†’ boost modifier â†’ weights={base_w}")
                    return base_w

        rw = cfg.get("regime_weights", {}).get(regime_key) or cfg.get("regime_weights", {}).get("default")
        if rw:
            weights = {
                "touche": rw.get("touche_weight", 0.30),
                "fundamental": rw.get("fundamental_weight", 0.40),
                "news": rw.get("news_weight", 0.10),
                "sentinel": rw.get("sentinel_weight", 0.15),
                "quantum": rw.get("quantum_weight", 0.05),
            }
            logger.info(f"auto_regime_switch: regime={regime_raw} â†’ key={regime_key} â†’ weights={weights}")
            return weights
    except FileNotFoundError:
        logger.warning(f"Consensus weights file not found at {_CONSENSUS_WEIGHTS_PATH}")
    except Exception as e:
        logger.warning(f"Failed to load regime weights: {e}")
    return None


# ========== LAZY-LOAD BACKTEST ROUTES ==========

def get_backtest_router():
    """Load backtest routes module."""
    try:
        from routes import backtest_routes as br
        logger.info("Backtest routes loaded successfully")
        return br
    except Exception as e:
        logger.error(f"Failed to load backtest routes: {e}", exc_info=True)
        return None


# FastAPI app
app = FastAPI(
    title="AEGIS Dashboard API",
    description="Real-time metrics aggregation for AEGIS Holding",
    version="2.0.0",
)

# CORS middleware - Allow React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3005", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include dashboard routes
app.include_router(dashboard.router)

# Include signal-only AEGIS Core routes (optional — skipped if module unavailable)
if _aegis_core_available and _aegis_core_routes_mod is not None:
    app.include_router(_aegis_core_routes_mod.router)
    logger.info("aegis_core_routes loaded")

# Include paper trading routes
app.include_router(paper_trading.router)

# Include macro routes
app.include_router(macro.router)

# Include SSE live-feed route
app.include_router(stream.router)

# Include backtest routes EARLY so they take priority over inline deprecated endpoint
_br = get_backtest_router()
if _br and hasattr(_br, 'router'):
    app.include_router(_br.router)
    logger.info("Backtest router loaded at module level (priority over inline)")
else:
    logger.warning("Backtest router not available at module level — inline fallback active")


# ========== STARTUP EVENT ==========

@app.on_event("startup")
async def load_backtest_on_startup():
    """Verify backtest router is loaded (fallback if module-level load failed)."""
    # Check if router is already loaded
    _loaded = any(
        hasattr(r, 'path') and r.path == '/backtest/run' and
        hasattr(r, 'endpoint') and r.endpoint.__name__ != 'run_backtest'
        for r in app.routes
    )
    if _loaded:
        logger.info("Backtest router already loaded at module level")
        return
    try:
        br = get_backtest_router()
        if br and hasattr(br, 'router'):
            app.include_router(br.router)
            logger.info("Backtest router loaded at startup (fallback)")
    except Exception as e:
        logger.error(f"Failed to load backtest router at startup: {e}", exc_info=True)


# Service URLs from environment
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
TOUCHE_URL = os.getenv("TOUCHE_URL", "http://localhost:8001")
FUNDAMENTAL_URL = os.getenv("FUNDAMENTAL_URL", "http://localhost:8002")
QUANTUM_URL = os.getenv("QUANTUM_URL", "http://localhost:8003")
SENTINEL_URL = os.getenv("SENTINEL_URL", "http://localhost:8004")
NEWS_URL = os.getenv("NEWS_URL", "http://localhost:8006")
ANALYZER_URL = os.getenv("ANALYZER_URL", "http://localhost:8007")

# Valid timeframes
VALID_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w", "1month"]

# Initialize Prometheus client
prometheus_client = PrometheusClient(PROMETHEUS_URL)
sentinel_client = SentinelClient(SENTINEL_URL)

# Initialize Touche AI Unified Optimizer
unified_optimizer: Optional[Any] = None
if touche_available:
    try:
        unified_optimizer = UnifiedOptimizer(learning_rate=0.01)
        logger.info("Unified optimizer initialized successfully")
    except Exception as e:
        logger.warning(f"Could not initialize unified optimizer: {e}")

# In-memory backtest run storage (used when volume-mounted backtest engine is unavailable)
BACKTEST_RUNS: Dict[str, Dict[str, Any]] = {}
LATEST_BACKTEST_ID: Optional[str] = None


def _data_status(timestamp: Optional[str], fallback_used: bool = False, mock_used: bool = False, missing_used: bool = False) -> str:
    if mock_used:
        return "MOCK"
    if missing_used:
        return "MISSING"
    if fallback_used:
        return "FALLBACK"
    return "LIVE" if timestamp else "UNKNOWN"


def _clean_timestamp(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value.strip() else None


class SignalRequest(BaseModel):
    symbol: str
    action: str
    timeframe: str
    quantity: float
    price: Optional[float] = None
    risk_pct: float = 0.02


# ============ HEALTH CHECK ============

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "aegis-dashboard-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "port": 8502,
        "prometheus": PROMETHEUS_URL,
    }


@app.get("/api/config")
async def get_config():
    """Return tradable symbols and default selection for the frontend."""
    return {
        "symbols": ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XAU/USDT"],
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "valid_timeframes": VALID_TIMEFRAMES,
    }


@app.post("/execute")
async def execute_signal(request: SignalRequest):
    """Execute AI signal on Binance Testnet, limited to configured live timeframes."""
    allowed = [tf.strip() for tf in os.getenv("LIVE_TIMEFRAMES", "4h,1d").split(",") if tf.strip()]
    if request.timeframe not in allowed:
        return {"success": False, "reason": f"Timeframe {request.timeframe} not allowed for live execution"}

    max_risk = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))
    if request.risk_pct > max_risk:
        return {"success": False, "reason": "Risk exceeds MAX_RISK_PER_TRADE"}

    kill_switch_dd = float(os.getenv("KILL_SWITCH_DRAWDOWN", "0.10"))
    if kill_switch_dd <= 0:
        return {"success": False, "reason": "Kill switch active due to invalid drawdown setting"}

    try:
        from strategies.execution_engine import BinanceTestnetExecutor
    except Exception as e:
        logger.error(f"Executor import failed: {e}", exc_info=True)
        return {"success": False, "reason": f"Executor unavailable: {e}"}

    executor = BinanceTestnetExecutor(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        base_url=os.getenv("BINANCE_BASE_URL", "https://testnet.binance.vision"),
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
    )

    try:
        result = await executor.place_order(
            symbol=request.symbol,
            side=request.action,
            qty=request.quantity,
            price=request.price,
            order_type="LIMIT",
        )
    finally:
        await executor.close()

    logger.info(
        f"EXECUTE: {request.symbol} {request.action} {request.quantity} @ {request.price} "
        f"| timeframe={request.timeframe} | dry_run={executor.dry_run} | result={result}"
    )
    return result


# Individual metrics (/api/metrics/touche etc.), /api/consensus, and /api/health
# are served by dashboard.router (routes/dashboard.py) â€” included above via app.include_router().


# ============ AGGREGATED DASHBOARD DATA ============

@app.get("/api/dashboard")
async def get_dashboard(symbol: str = Query("BTC/USDT"), timeframe: str = Query("1h")):
    """Single aggregated endpoint for all dashboard data with timeframe (5m, 15m, 1h, 4h, 1d, 1w, 1month)"""
    try:
        # Validate timeframe
        valid_timeframes = ["5m", "15m", "1h", "4h", "1d", "1w", "1month"]
        if timeframe not in valid_timeframes:
            timeframe = "1h"

        logger.info(f"Dashboard query: symbol={symbol}, timeframe={timeframe}")

        # Get REAL metrics from Prometheus in parallel - NO FALLBACK, NO MOCK DATA
        (touche_score, fundamental_score, quantum_score, sentinel_score, news_score) = await asyncio.gather(
            prometheus_client.get_touche_score(symbol, timeframe),
            prometheus_client.get_fundamental_score(symbol, timeframe),
            prometheus_client.get_quantum_pnl(symbol, timeframe),
            prometheus_client.get_sentinel_multiplier(symbol, timeframe),
            prometheus_client.get_news_sentiment_score(timeframe)
        )

        # Log data availability status
        logger.info(f"Prometheus metrics for {symbol}/{timeframe}: Touche={touche_score}, Fundamental={fundamental_score}, Quantum={quantum_score}, Sentinel={sentinel_score}, News={news_score}")

        missing_metrics = {
            "touche": touche_score is None,
            "fundamental": fundamental_score is None,
            "quantum": quantum_score is None,
            "sentinel": sentinel_score is None,
            "news": news_score is None,
        }

        # If any metric is None, log warning
        if any(missing_metrics.values()):
            logger.warning(f"Some metrics are None for {symbol}/{timeframe} - Check if AI modules are running and pushing to Prometheus")

        # Use 0.0 if None (instead of mock values) to indicate missing data
        touche_score = touche_score if touche_score is not None else 0.0
        fundamental_score = fundamental_score if fundamental_score is not None else 0.0
        quantum_score = quantum_score if quantum_score is not None else 0.0
        sentinel_score = sentinel_score if sentinel_score is not None else 0.0
        news_score = news_score if news_score is not None else 0.0

        # Extended macro metrics from Sentinel client.
        macro_metrics = await sentinel_client.fetch_macro_metrics()

        # Normalize to 0-1
        touche_score = min(max(float(touche_score), 0.0), 1.0)
        if touche_score > 1:
            touche_score = touche_score / 100.0
        fundamental_score = min(max(float(fundamental_score), 0.0), 1.0)
        if fundamental_score > 1:
            fundamental_score = fundamental_score / 100.0
        quantum_score = min(max(float(quantum_score), 0.0), 1.0)
        sentinel_score = min(max(float(sentinel_score), 0.0), 1.0)
        news_score = min(max(float(news_score), 0.0), 1.0)

        # 3-way weighted consensus
        weights = {"touche": 0.50, "fundamental": 0.35, "news": 0.15}
        weighted_score = (
            touche_score * weights["touche"] +
            fundamental_score * weights["fundamental"] +
            news_score * weights["news"]
        )

        # Determine action
        if weighted_score > 0.65:
            action = "BUY"
            confidence = weighted_score
        elif weighted_score < 0.35:
            action = "SELL"
            confidence = 1.0 - weighted_score
        else:
            action = "HOLD"
            confidence = 0.5

        def _metric_payload(name: str, score: float, color: str, missing: bool, include_symbol: bool = True, include_macro: bool = False) -> Dict[str, Any]:
            payload: Dict[str, Any] = {
                "name": name,
                "score": round(score, 4),
                "health": "healthy" if score > 0.5 else "warning" if score > 0.3 else "down",
                "color": color,
                "timeframe": timeframe,
                "timestamp": None,
                "last_updated": None,
                "source": "prometheus_missing_metric" if missing else "prometheus_live_query",
                "fallback_used": missing,
                "data_status": _data_status(None, fallback_used=False, missing_used=missing),
            }
            if include_symbol:
                payload["symbol"] = symbol
            if include_macro:
                payload["macro"] = macro_metrics
            return payload

        dashboard_fallback_used = any(missing_metrics.values())
        dashboard_status = _data_status(None, fallback_used=dashboard_fallback_used)

        # Get system health (mock for now)
        system_health = {
            "overall_status": "healthy",
            "services": {"touche": "UP", "fundamental": "UP", "quantum": "UP", "sentinel": "UP", "news": "UP", "analyzer": "UP"},
            "up_count": 6,
            "total_count": 6,
            "timestamp": None,
            "last_updated": None,
            "source": "mock_system_health",
            "fallback_used": True,
            "data_status": _data_status(None, mock_used=True),
        }

        return {
            "timestamp": None,
            "last_updated": None,
            "source": "dashboard_aggregate",
            "fallback_used": dashboard_fallback_used,
            "data_status": dashboard_status,
            "symbol": symbol,
            "timeframe": timeframe,
            "metrics": {
                "touche": _metric_payload("Touche EQS", touche_score, "#3B82F6", missing_metrics["touche"]),
                "fundamental": _metric_payload("Fundamental Score", fundamental_score, "#10B981", missing_metrics["fundamental"]),
                "quantum": _metric_payload("Quantum Score", quantum_score, "#F59E0B", missing_metrics["quantum"]),
                "sentinel": _metric_payload("Sentinel Score", sentinel_score, "#8B5CF6", missing_metrics["sentinel"], include_macro=True),
                "news": _metric_payload("News Sentiment", news_score, "#EC4899", missing_metrics["news"], include_symbol=False),
            },
            "consensus": {
                "weighted_score": round(weighted_score, 4),
                "action": action,
                "confidence": round(confidence, 4),
                "weights": weights,
                "components": {
                    "touche": {"score": round(touche_score, 4), "weight": 0.50},
                    "fundamental": {"score": round(fundamental_score, 4), "weight": 0.35},
                    "news": {"score": round(news_score, 4), "weight": 0.15},
                },
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": None,
                "last_updated": None,
                "source": "dashboard_aggregate",
                "fallback_used": dashboard_fallback_used,
                "data_status": dashboard_status,
            },
            "macro": macro_metrics,
            "health": system_health,
        }
    except Exception as e:
        logger.error(f"Error in get_dashboard: {e}")
        return {
            "error": str(e),
            "timestamp": None,
            "last_updated": None,
            "source": "dashboard_error",
            "fallback_used": True,
            "data_status": _data_status(None, fallback_used=True),
            "symbol": symbol,
            "timeframe": timeframe,
        }



# ============ BACKTEST ENDPOINT - DEPRECATED (using backtest_routes router) ============
# Note: Real backtest implementation is in backtest/routes/backtest_routes.py
# This mock endpoint is kept for backward compatibility but should not be used.
# The real router has been included above via app.include_router(backtest_routes.router)

# To run backtest, requests go to POST /backtest/run which is now handled by backtest_routes router
# The router provides real AI signal backtesting with improved fundamental scores and consensus weights


@app.get("/backtest/supported-timeframes")
async def get_backtest_timeframes():
    """Get supported timeframes"""
    return {
        "timeframes": ["5m", "15m", "1h", "4h", "1d", "1w", "1month"],
        "strategy": "AI Consensus (Touche 50% + Fundamental 35% + News 15%)",
        "ai_modules": ["Touche", "Fundamental", "Quantum", "Sentinel", "News", "Consensus"],
    }


@app.post("/backtest/run")
async def run_backtest_fallback(request_data: Dict = Body(...)):
    """Safety-net fallback — the backtest_routes router handles this path first.
    Only reached if the router failed to load at startup.
    """
    raise HTTPException(
        status_code=503,
        detail="Backtest router unavailable. Check service logs for import errors.",
    )


@app.get("/backtest/status")
async def backtest_status():
    """Return latest backtest run status."""
    if LATEST_BACKTEST_ID and LATEST_BACKTEST_ID in BACKTEST_RUNS:
        item = BACKTEST_RUNS[LATEST_BACKTEST_ID]
        return {
            "status": item.get("status", "unknown"),
            "backtest_id": LATEST_BACKTEST_ID,
            "started_at": item.get("started_at"),
            "completed_at": item.get("completed_at"),
        }
    return {"status": "idle", "backtest_id": None}


@app.get("/backtest/status/{backtest_id}")
async def backtest_status_by_id(backtest_id: str):
    """Return status for a specific backtest run id."""
    item = BACKTEST_RUNS.get(backtest_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backtest status not found")
    return {
        "status": item.get("status", "unknown"),
        "backtest_id": backtest_id,
        "started_at": item.get("started_at"),
        "completed_at": item.get("completed_at"),
    }


@app.get("/backtest/report/{backtest_id}")
async def backtest_report(backtest_id: str):
    """Return stored backtest report."""
    item = BACKTEST_RUNS.get(backtest_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backtest report not found")
    return item.get("result", {})


# ============ AI ANALYSIS (Analyzer Service) ============

@app.get("/api/analysis")
async def get_analysis(symbol: str = Query("BTC/USDT"), timeframe: str = Query("4h")):
    """Get comprehensive AI analysis from Analyzer Service"""
    try:
        # Get actual scores from Prometheus
        touche_score = await prometheus_client.get_touche_score(symbol, timeframe) or 50.0
        fundamental_score = await prometheus_client.get_fundamental_score(symbol, timeframe) or 50.0
        news_score = await prometheus_client.get_news_sentiment_score(timeframe) or 50.0

        # Normalize to 0-100 range
        touche_score = min(max(float(touche_score), 0.0), 100.0)
        fundamental_score = min(max(float(fundamental_score), 0.0), 100.0)
        news_score = min(max(float(news_score), 0.0), 100.0)

        # Call analyzer with POST (send scores as JSON body)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ANALYZER_URL}/analyze",
                json={
                    "touche": touche_score,
                    "fundamental": fundamental_score,
                    "news": news_score
                },
                timeout=30.0
            )

            if response.status_code != 200:
                logger.warning(f"Analyzer returned {response.status_code}")
                return {
                    "success": False,
                    "error": f"Analyzer service returned {response.status_code}",
                    "timestamp": None,
                    "last_updated": None,
                    "source": "analyzer_error",
                    "fallback_used": True,
                    "data_status": _data_status(None, fallback_used=True),
                }

            analyzer_data = response.json()
            analyzer_data = analyzer_data if isinstance(analyzer_data, dict) else {}
            analysis_timestamp = _clean_timestamp(analyzer_data.get("timestamp"))
            analysis_source = str(analyzer_data.get("source", "analyzer_bridge"))

            # Extract data
            recommendation = analyzer_data.get("recommendation", "HOLD")
            score = analyzer_data.get("score", 50.0)
            confidence = analyzer_data.get("confidence", 0.5)

            # Generate detailed analysis comments
            def get_touche_comment(val):
                if val > 65: return "GÃ¼Ã§lÃ¼ AL sinyali"
                elif val > 55: return "AL bÃ¶lgesine yakÄ±n"
                elif val < 35: return "GÃ¼Ã§lÃ¼ SAT sinyali"
                elif val < 45: return "SAT bÃ¶lgesine yakÄ±n"
                else: return "KararsÄ±z bÃ¶lge"

            def get_fundamental_comment(val):
                if val > 65: return "Blockchain aÄŸÄ± Ã§ok aktif"
                elif val > 55: return "Blockchain aÄŸÄ± aktif"
                elif val < 35: return "AÄŸ aktivitesi dÃ¼ÅŸÃ¼k"
                elif val < 45: return "AÄŸ aktivitesi azalÄ±yor"
                else: return "AÄŸ aktivitesi nÃ¶tr"

            def get_quantum_comment(val):
                if val > 60: return "Likidite iyi, emirler rahat"
                elif val > 40: return "Likidite orta seviye"
                elif val < 30: return "Likidite dÃ¼ÅŸÃ¼k, uyarÄ±!"
                else: return "Likidite sÄ±nÄ±rlandÄ±rÄ±lmÄ±ÅŸ"

            def get_sentinel_comment(val):
                if val > 65: return "Piyasa sakin, iÅŸlem iÃ§inde"
                elif val > 45: return "Piyasa normal seviyede"
                elif val < 35: return "Piyasa riskli, dikkat"
                else: return "OynaklÄ±k yÃ¼ksek"

            def get_news_comment(val):
                if val > 65: return "Haberler Ã§ok pozitif"
                elif val > 55: return "Haberler pozitif yÃ¶nde"
                elif val < 35: return "Haberler negatif yÃ¶nde"
                elif val < 45: return "Haberler olumsuz"
                else: return "Haberler kararsÄ±z"

            # Build detailed analysis
            risk_notes = []
            action_points = []

            if score < 40:
                risk_notes.append(f"âš ï¸ GÃ¼Ã§lÃ¼ SAT sinyali - {score:.1f} puanÄ±nda")
                action_points.append("SAT pozisyonu dÃ¼ÅŸÃ¼n (65+ beklenildiÄŸinde tekrar AL)")

            elif score > 65:
                risk_notes.append(f"âœ… GÃ¼Ã§lÃ¼ AL sinyali - {score:.1f} puanÄ±nda")
                action_points.append(f"AL pozisyonu dÃ¼ÅŸÃ¼n (Risk: Likidite={fundamental_score:.1f})")

            else:
                risk_notes.append(f"ğŸŸ¡ KararsÄ±z bÃ¶lge - {score:.1f} puanÄ±nda BEKLE")
                action_points.append("65+ veya 35- beklemeye devam et")

            if fundamental_score < 40:
                risk_notes.append("ğŸ”— Fundamental skor dÃ¼ÅŸÃ¼k - on-chain aktivite azalÄ±ÅŸ")

            if touche_score > 60 and news_score < 40:
                risk_notes.append("ğŸ“° Teknik + hediye - News olumsuz, dikkatli ol")

            return {
                "success": True,
                "timestamp": analysis_timestamp,
                "last_updated": analysis_timestamp,
                "source": analysis_source,
                "fallback_used": False,
                "data_status": _data_status(analysis_timestamp),
                "report": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": analysis_timestamp,
                    "consensus": {
                        "weighted_score": score,
                        "final_direction": recommendation,
                        "confidence": confidence * 100  # Convert to 0-100 percentage
                    },
                    "final_recommendation": recommendation,
                    "final_reason": (
                        f"ğŸ“ˆ Teknik: {touche_score:.1f}% - {get_touche_comment(touche_score)}\n"
                        f"ğŸ”— Temel: {fundamental_score:.1f}% - {get_fundamental_comment(fundamental_score)}\n"
                        f"ğŸ’§ Likidite: {touche_score:.1f}% - {get_quantum_comment(touche_score)}\n"
                        f"âš ï¸ Risk: {fundamental_score:.1f}% - {get_sentinel_comment(fundamental_score)}\n"
                        f"ğŸ“° Haber: {news_score:.1f}% - {get_news_comment(news_score)}\n\n"
                        f"ğŸ¯ Ã–neri: {recommendation} - Skor={score:.2f}% (Confidence={confidence*100:.0f}%)"
                    ),
                    "risk_notes": [note for note in risk_notes if note],
                    "action_points": action_points
                },
            }

    except httpx.ConnectError:
        logger.error(f"Cannot connect to Analyzer at {ANALYZER_URL}")
        return {
            "success": False,
            "error": f"Cannot connect to Analyzer service at {ANALYZER_URL}",
            "report": None,
            "timestamp": None,
            "last_updated": None,
            "source": "analyzer_unavailable",
            "fallback_used": True,
            "data_status": _data_status(None, fallback_used=True),
        }
    except Exception as e:
        logger.error(f"Error calling analyzer: {e}")
        return {
            "success": False,
            "error": str(e),
            "report": None,
            "timestamp": None,
            "last_updated": None,
            "source": "analyzer_error",
            "fallback_used": True,
            "data_status": _data_status(None, fallback_used=True),
        }


@app.get("/api/analysis/report")
async def get_analysis_report(symbol: str = Query("BTC/USDT"), timeframe: str = Query("4h")):
    """Get formatted text report from Analyzer Service"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ANALYZER_URL}/report",
                params={"symbol": symbol, "timeframe": timeframe},
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "success": False,
                    "error": f"Report service returned {response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
    except Exception as e:
        logger.error(f"Error getting report: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ============ TOUCHE AI WEIGHT OPTIMIZER ENDPOINTS ============

@app.get("/api/optimizer/status")
async def get_unified_optimizer_status():
    """Get unified optimizer status (weights + parameters + statistics)"""
    if not unified_optimizer:
        return {"enabled": False, "error": "Unified optimizer not available"}

    try:
        status = unified_optimizer.get_status()
        return {
            "enabled": True,
            **status,
        }
    except Exception as e:
        logger.error(f"Error getting optimizer status: {e}")
        return {"enabled": True, "error": str(e)}


@app.post("/api/optimizer/record-trade")
async def record_trade_to_optimizer(
    entry_price: float = Body(...),
    exit_price: float = Body(...),
    pnl: float = Body(...),
    winning_phases: List[int] = Body(default=[]),
    losing_phases: List[int] = Body(default=[]),
    rsi_at_entry: float = Body(default=0.0),
    macd_at_entry: float = Body(default=0.0),
    volatility: float = Body(default=0.0),
    fibonacci_level: float = Body(default=0.618),
):
    """
    Record a trade and let optimizer learn from it.

    Args:
        entry_price: Entry price
        exit_price: Exit price
        pnl: Profit/Loss
        winning_phases: Phases that contributed to win (1-7)
        losing_phases: Phases that contributed to loss (1-7)
        rsi_at_entry: RSI value at entry
        macd_at_entry: MACD value at entry
        volatility: Market volatility
        fibonacci_level: Fibonacci retracement level
    """
    if not unified_optimizer:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")

    try:
        trade_record = TradeRecord(
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            winning_phases=winning_phases,
            losing_phases=losing_phases,
            rsi_at_entry=rsi_at_entry,
            macd_at_entry=macd_at_entry,
            volatility=volatility,
            fibonacci_level=fibonacci_level,
        )

        unified_optimizer.record_trade(trade_record)

        return {
            "success": True,
            "message": "Trade recorded successfully",
            "status": unified_optimizer.get_status(),
        }
    except Exception as e:
        logger.error(f"Error recording trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimizer/weights")
async def get_unified_optimizer_weights():
    """Get current phase weights from unified optimizer"""
    if not unified_optimizer:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")

    return {
        "weights": unified_optimizer.weights.copy(),
        "phase_params": unified_optimizer.phase_params.copy(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/optimizer/stats")
async def get_optimizer_statistics():
    """Get optimizer trading statistics"""
    if not unified_optimizer:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")

    return {
        "stats": unified_optimizer.stats.copy(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/optimizer/periodic-optimize")
async def trigger_periodic_optimization(optimization_type: str = Query("light")):
    """
    Trigger periodic optimization (light or heavy).

    Args:
        optimization_type: "light" (grid search) or "heavy" (bayesian)
    """
    if not unified_optimizer:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")

    if len(unified_optimizer.trade_history) < 10:
        return {
            "success": False,
            "message": f"Need at least 10 trades to optimize. Currently have {len(unified_optimizer.trade_history)}",
        }

    try:
        result = unified_optimizer.optimize_periodic(optimization_type=optimization_type)
        return {
            "success": True,
            **result,
        }
    except Exception as e:
        logger.error(f"Periodic optimization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/optimizer/save-config")
async def save_unified_optimizer_config(filepath: str = Query("unified_optimizer_config.yaml")):
    """Save unified optimizer configuration to YAML file"""
    if not unified_optimizer:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")

    try:
        full_path = os.path.join(
            os.path.dirname(__file__),
            "../../strategies/touche_ai/config",
            filepath
        )
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        unified_optimizer.save_config(full_path)

        return {
            "success": True,
            "message": "Configuration saved successfully",
            "filepath": full_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/optimizer/load-config")
async def load_unified_optimizer_config(filepath: str = Query("unified_optimizer_config.yaml")):
    """Load unified optimizer configuration from YAML file"""
    if not unified_optimizer:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")

    try:
        full_path = os.path.join(
            os.path.dirname(__file__),
            "../../strategies/touche_ai/config",
            filepath
        )
        unified_optimizer.load_config(full_path)

        return {
            "success": True,
            "message": "Configuration loaded successfully",
            "filepath": full_path,
            "status": unified_optimizer.get_status(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimizer/trade-history")
async def get_trade_history(limit: int = Query(20)):
    """Get recent trade history"""
    if not unified_optimizer:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")

    try:
        recent_trades = unified_optimizer.trade_history[-limit:]
        return {
            "trades": [
                {
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl": t.pnl,
                    "is_winning": t.is_winning,
                    "winning_phases": t.winning_phases,
                    "losing_phases": t.losing_phases,
                    "rsi_at_entry": t.rsi_at_entry,
                    "macd_at_entry": t.macd_at_entry,
                    "volatility": t.volatility,
                    "timestamp": t.timestamp,
                }
                for t in recent_trades
            ],
            "count": len(recent_trades),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting trade history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimizer/optimization-history")
async def get_optimization_history(limit: int = Query(10)):
    """Get recent optimization history"""
    if not unified_optimizer:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")

    try:
        history = unified_optimizer.optimization_history[-limit:]
        return {
            "history": history,
            "count": len(history),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting optimization history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("DASHBOARD_API_PORT", "8502"))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
