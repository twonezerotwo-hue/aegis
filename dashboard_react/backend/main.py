from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRouter
import httpx
import asyncio
import importlib
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
from routes import macro
from routes import stream

# Setup logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


LEGACY_RUNTIME_ENABLED = _env_flag("AEGIS_ENABLE_LEGACY_RUNTIME", False)
PAPER_TRADING_ENABLED = _env_flag("AEGIS_ENABLE_PAPER_TRADING", LEGACY_RUNTIME_ENABLED)
EXECUTION_ENDPOINTS_ENABLED = _env_flag("AEGIS_ENABLE_EXECUTION_ENDPOINTS", LEGACY_RUNTIME_ENABLED)
OPTIMIZER_ENDPOINTS_ENABLED = _env_flag("AEGIS_ENABLE_OPTIMIZER_ENDPOINTS", LEGACY_RUNTIME_ENABLED)


def _legacy_feature_detail(feature: str, env_var: str, extra_reason: Optional[str] = None) -> Dict[str, Any]:
    detail: Dict[str, Any] = {
        "status": "disabled",
        "feature": feature,
        "reason": f"{feature} is disabled in the default safe runtime.",
        "env_var": env_var,
        "legacy_runtime_enabled": False,
    }
    if extra_reason:
        detail["extra_reason"] = extra_reason
    return detail


def _raise_legacy_feature_disabled(feature: str, env_var: str, extra_reason: Optional[str] = None) -> None:
    raise HTTPException(
        status_code=503,
        detail=_legacy_feature_detail(feature, env_var, extra_reason=extra_reason),
    )


def _legacy_runtime_state() -> Dict[str, Any]:
    return {
        "legacy_runtime_enabled": LEGACY_RUNTIME_ENABLED,
        "paper_trading_enabled": PAPER_TRADING_ENABLED,
        "execution_endpoints_enabled": EXECUTION_ENDPOINTS_ENABLED,
        "optimizer_endpoints_enabled": OPTIMIZER_ENDPOINTS_ENABLED,
    }


def _build_legacy_disabled_router(
    *,
    prefix: str,
    feature: str,
    env_var: str,
    tags: List[str],
    extra_reason: Optional[str] = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags)
    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

    @router.api_route("", methods=methods, include_in_schema=False)
    @router.api_route("/", methods=methods, include_in_schema=False)
    async def _disabled_root():
        _raise_legacy_feature_disabled(feature, env_var, extra_reason=extra_reason)

    @router.api_route("/{path:path}", methods=methods, include_in_schema=False)
    async def _disabled_path(path: str):
        _raise_legacy_feature_disabled(feature, env_var, extra_reason=extra_reason)

    return router


def _load_paper_trading_router() -> APIRouter:
    if not PAPER_TRADING_ENABLED:
        logger.info("Paper trading routes disabled in default safe runtime")
        return _build_legacy_disabled_router(
            prefix="/api/paper",
            feature="paper trading routes",
            env_var="AEGIS_ENABLE_PAPER_TRADING",
            tags=["paper_trading_disabled"],
        )

    try:
        module = importlib.import_module("routes.paper_trading")
        logger.info("Paper trading routes enabled explicitly")
        return module.router
    except Exception as exc:
        logger.warning("Paper trading router unavailable: %s", exc)
        return _build_legacy_disabled_router(
            prefix="/api/paper",
            feature="paper trading routes",
            env_var="AEGIS_ENABLE_PAPER_TRADING",
            tags=["paper_trading_disabled"],
            extra_reason=str(exc),
        )


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

# Include legacy paper trading routes behind an explicit opt-in runtime flag.
app.include_router(_load_paper_trading_router())

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

# Initialize legacy optimizer runtime only when explicitly enabled.
UnifiedOptimizerClass: Optional[Any] = None
TradeRecordClass: Optional[Any] = None
unified_optimizer: Optional[Any] = None
if OPTIMIZER_ENDPOINTS_ENABLED:
    try:
        from strategies.touche_ai.src.engine.unified_optimizer import UnifiedOptimizer as _UnifiedOptimizer
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord as _TradeRecord

        UnifiedOptimizerClass = _UnifiedOptimizer
        TradeRecordClass = _TradeRecord
        unified_optimizer = _UnifiedOptimizer(learning_rate=0.01)
        logger.info("Unified optimizer initialized successfully")
    except Exception as e:
        logger.warning(f"Could not initialize unified optimizer: {e}")
else:
    logger.info("Unified optimizer runtime disabled in default safe runtime")

# In-memory backtest run storage (used when volume-mounted backtest engine is unavailable)
BACKTEST_RUNS: Dict[str, Dict[str, Any]] = {}
LATEST_BACKTEST_ID: Optional[str] = None


class _DailyPnLTracker:
    """
    Günlük gerçekleşmiş P&L takibi — Kill Switch tetikleyici.

    Sorun: KILL_SWITCH_DRAWDOWN env var vardı ama P&L biriktirilmediği için
    kill switch hiçbir zaman tetiklenemiyordu.

    Çözüm: Her /execute sonucunda realized_pnl biriktirilir.
    UTC gece yarısında otomatik sıfırlanır.
    """
    def __init__(self):
        self._date: str = ""
        self._realized_pnl: float = 0.0
        self._trade_count: int = 0

    def _reset_if_new_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._date:
            if self._date:
                logger.info(f"KILL_SWITCH_RESET: yeni gün {today}, "
                            f"önceki gün P&L={self._realized_pnl:.4f}, "
                            f"işlem={self._trade_count}")
            self._date = today
            self._realized_pnl = 0.0
            self._trade_count = 0

    def record(self, pnl: float):
        self._reset_if_new_day()
        self._realized_pnl += pnl
        self._trade_count += 1
        logger.info(f"PNL_RECORD: +{pnl:.4f} → günlük={self._realized_pnl:.4f} "
                    f"işlem={self._trade_count}")

    def is_kill_switch_active(self, threshold: float) -> tuple[bool, str]:
        """True + mesaj döndürür eğer günlük kayıp eşiği aştıysa."""
        self._reset_if_new_day()
        if self._realized_pnl < -abs(threshold):
            return True, (f"Kill switch aktif: günlük kayıp {self._realized_pnl:.4f} "
                          f"< -{abs(threshold):.4f} eşiği")
        return False, ""

    @property
    def summary(self) -> dict:
        self._reset_if_new_day()
        return {
            "date": self._date,
            "realized_pnl": round(self._realized_pnl, 6),
            "trade_count": self._trade_count,
        }


_pnl_tracker = _DailyPnLTracker()


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


def _require_optimizer_runtime() -> None:
    if not OPTIMIZER_ENDPOINTS_ENABLED:
        _raise_legacy_feature_disabled(
            "optimizer endpoints",
            "AEGIS_ENABLE_OPTIMIZER_ENDPOINTS",
        )

    if unified_optimizer is None or TradeRecordClass is None:
        raise HTTPException(status_code=503, detail="Unified optimizer not available")


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
        "runtime": _legacy_runtime_state(),
    }


@app.get("/api/config")
async def get_config():
    """Return tradable symbols and default selection for the frontend."""
    return {
        "symbols": ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XAU/USDT"],
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "valid_timeframes": VALID_TIMEFRAMES,
        "runtime": _legacy_runtime_state(),
    }


@app.post("/api/signal/rationale")
async def signal_rationale(ctx: Dict = Body(...)):
    """
    Mevcut sinyal bağlamı için Türkçe LLM gerekçesi üretir.

    Body: { action, confidence_pct, five_module_score, regime,
            event_risk_pct, vix, hyg, funding_rate_pct,
            module_scores: {touche,fundamental,news,sentinel,quantum},
            symbol, timeframe, warnings }

    Returns: { text, source }  — source: "groq" | "ollama" | "rule_based"
    """
    from services.llm_service import get_llm_service
    result = await get_llm_service().signal_rationale(ctx)
    return result


@app.get("/api/llm/status")
async def llm_status():
    """LLM servis durumu — hangi kaynak aktif."""
    from services.llm_service import get_llm_service, _GROQ_API_KEY, _OLLAMA_BASE, _GROQ_MODEL, _OLLAMA_MODEL
    return {
        "groq": {"configured": bool(_GROQ_API_KEY), "model": _GROQ_MODEL},
        "ollama": {"base_url": _OLLAMA_BASE, "model": _OLLAMA_MODEL},
        "sources": get_llm_service().available_sources,
    }


@app.get("/api/pnl/daily")
async def get_daily_pnl():
    """Günlük P&L durumu ve kill switch eşiği."""
    kill_switch_dd = float(os.getenv("KILL_SWITCH_DRAWDOWN", "0.10"))
    triggered, msg = _pnl_tracker.is_kill_switch_active(kill_switch_dd)
    return {
        **_pnl_tracker.summary,
        "kill_switch_threshold": kill_switch_dd,
        "kill_switch_active": triggered,
        "message": msg or "Normal — işlem açılabilir",
    }


@app.post("/execute")
async def execute_signal(request: SignalRequest):
    """Execute AI signal on Binance, limited to configured live timeframes."""
    if not EXECUTION_ENDPOINTS_ENABLED:
        _raise_legacy_feature_disabled(
            "live execution endpoint",
            "AEGIS_ENABLE_EXECUTION_ENDPOINTS",
        )

    allowed = [tf.strip() for tf in os.getenv("LIVE_TIMEFRAMES", "4h,1d").split(",") if tf.strip()]
    if request.timeframe not in allowed:
        return {"success": False, "reason": f"Timeframe {request.timeframe} not allowed for live execution"}

    max_risk = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))
    if request.risk_pct > max_risk:
        return {"success": False, "reason": "Risk exceeds MAX_RISK_PER_TRADE"}

    # ── Gerçek kill switch kontrolü ───────────────────────────────────────────
    kill_switch_dd = float(os.getenv("KILL_SWITCH_DRAWDOWN", "0.10"))
    triggered, kill_msg = _pnl_tracker.is_kill_switch_active(kill_switch_dd)
    if triggered:
        logger.warning(f"KILL_SWITCH_BLOCKED: {kill_msg}")
        return {"success": False, "reason": kill_msg, "kill_switch": True}

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

    # ── P&L kaydı (realized pnl varsa tracker'a ekle) ────────────────────────
    # Executor gerçek P&L döndürmüyor ama risk_pct × quantity × price → tahmini kayıp
    # Gerçek P&L, pozisyon kapanırken /execute ile tekrar çağrıldığında güncellenecek
    if isinstance(result, dict) and result.get("pnl") is not None:
        _pnl_tracker.record(float(result["pnl"]))
    elif isinstance(result, dict) and result.get("success") and not executor.dry_run:
        # DRY_RUN değilse işlem açılmış sayılır; P&L kapatmada netleşir.
        # Şimdilik tahmini risk miktarını potansiyel kayıp olarak işaretle (muhafazakâr)
        estimated_exposure = request.risk_pct * (request.price or 0.0) * request.quantity
        logger.debug(f"PNL_ESTIMATE: exposure={estimated_exposure:.2f}")

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

        # Try live AI service calls first (real-time), fall back to Prometheus
        from routes.dashboard import (
            _aggregate_status,
            _build_metric_summary,
            _extract_payload_timestamp,
            _fetch_live_module_payloads,
            _fetch_live_scores,
            _fetch_module_details,
            _latest_timestamp,
            _payload_data_status,
        )
        live_scores, module_details, live_payloads = await asyncio.gather(
            _fetch_live_scores(symbol, timeframe),
            _fetch_module_details(symbol, timeframe),
            _fetch_live_module_payloads(symbol, timeframe),
        )

        # Prometheus as secondary source for anything the live call missed
        prom_scores = (None, None, None, None, None)
        if any(v is None for v in (live_scores["touche"], live_scores["fundamental"], live_scores["news"], live_scores["sentinel"])):
            prom_scores = await asyncio.gather(
                prometheus_client.get_touche_score(symbol, timeframe),
                prometheus_client.get_fundamental_score(symbol, timeframe),
                prometheus_client.get_quantum_pnl(symbol, timeframe),
                prometheus_client.get_sentinel_multiplier(symbol, timeframe),
                prometheus_client.get_news_sentiment_score(timeframe),
            )

        touche_score    = live_scores["touche"]    or prom_scores[0] or 0.0
        fundamental_score = live_scores["fundamental"] or prom_scores[1] or 0.0
        quantum_score   = live_scores["quantum"]   or prom_scores[2] or 0.5
        sentinel_score  = live_scores["sentinel"]  or prom_scores[3] or 0.5
        news_score      = live_scores["news"]      or prom_scores[4] or 0.0

        missing_metrics = {
            "touche":      live_scores["touche"] is None and prom_scores[0] is None,
            "fundamental": live_scores["fundamental"] is None and prom_scores[1] is None,
            "quantum":     live_scores["quantum"] is None and prom_scores[2] is None,
            "sentinel":    live_scores["sentinel"] is None and prom_scores[3] is None,
            "news":        live_scores["news"] is None and prom_scores[4] is None,
        }

        def _payload_timestamp(module: str) -> Optional[str]:
            payload = live_payloads.get(module) or {}
            return _extract_payload_timestamp(payload, module)

        def _payload_source(module: str) -> str:
            payload = live_payloads.get(module) or {}
            if payload:
                return str(payload.get("source", "live_service_api"))
            return "prometheus_fallback" if not missing_metrics[module] else "live_service_missing"

        def _payload_status(module: str) -> str:
            payload = live_payloads.get(module) or {}
            if payload:
                return _payload_data_status(payload, module, timeframe)
            return _data_status(None, fallback_used=False, missing_used=missing_metrics[module])

        module_statuses = {
            module: _payload_status(module)
            for module in ("touche", "fundamental", "quantum", "sentinel", "news")
        }

        sources = {module: _payload_source(module) for module in ("touche", "fundamental", "quantum", "sentinel", "news")}

        logger.info(f"Scores for {symbol}/{timeframe}: T={touche_score:.3f}({sources['touche']}) F={fundamental_score:.3f} N={news_score:.3f} S={sentinel_score:.3f}")

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

        def _metric_payload(name: str, module: str, score: float, color: str, missing: bool, include_symbol: bool = True, include_macro: bool = False, summary: str = "") -> Dict[str, Any]:
            timestamp = _payload_timestamp(module)
            data_status = module_statuses[module]
            payload: Dict[str, Any] = {
                "name": name,
                "score": round(score, 4),
                "health": "healthy" if score > 0.5 else "warning" if score > 0.3 else "down",
                "color": color,
                "summary": summary,
                "timeframe": timeframe,
                "timestamp": timestamp,
                "last_updated": timestamp,
                "source": sources[module],
                "fallback_used": data_status in {"FALLBACK", "PARTIAL_FALLBACK"},
                "data_status": data_status,
            }
            if include_symbol:
                payload["symbol"] = symbol
            if include_macro:
                payload["macro"] = macro_metrics
            return payload

        dashboard_fallback_used = any(
            status in {"FALLBACK", "PARTIAL_FALLBACK"} for status in module_statuses.values()
        ) or str(macro_metrics.get("data_status", "")).upper() in {"FALLBACK", "PARTIAL_FALLBACK"}
        metric_timestamps = [
            _payload_timestamp(module)
            for module in ("touche", "fundamental", "quantum", "sentinel", "news")
        ]
        macro_timestamp = _clean_timestamp(macro_metrics.get("timestamp")) or _clean_timestamp(macro_metrics.get("last_updated"))
        effective_timestamp = _latest_timestamp(macro_timestamp, *metric_timestamps)
        dashboard_status = _aggregate_status([
            module_statuses["touche"],
            module_statuses["fundamental"],
            module_statuses["quantum"],
            module_statuses["sentinel"],
            module_statuses["news"],
            str(macro_metrics.get("data_status", "")).upper(),
            "FALLBACK" if dashboard_fallback_used else "",
            "UNKNOWN" if effective_timestamp is None else "",
        ])
        consensus_timestamp = _latest_timestamp(
            _payload_timestamp("touche"),
            _payload_timestamp("fundamental"),
            _payload_timestamp("news"),
        )
        consensus_status = _aggregate_status([
            module_statuses["touche"],
            module_statuses["fundamental"],
            module_statuses["news"],
            "FALLBACK" if (
                module_statuses["touche"] in {"FALLBACK", "PARTIAL_FALLBACK"}
                or module_statuses["fundamental"] in {"FALLBACK", "PARTIAL_FALLBACK"}
                or module_statuses["news"] in {"FALLBACK", "PARTIAL_FALLBACK"}
            ) else "",
            "UNKNOWN" if consensus_timestamp is None else "",
        ])

        service_states = {
            "touche": "UP" if live_scores["touche"] is not None or not missing_metrics["touche"] else "DOWN",
            "fundamental": "UP" if live_scores["fundamental"] is not None or not missing_metrics["fundamental"] else "DOWN",
            "quantum": "UP" if live_scores["quantum"] is not None or not missing_metrics["quantum"] else "DOWN",
            "sentinel": "UP" if live_scores["sentinel"] is not None or macro_metrics.get("data_status") in {"LIVE", "RECENT"} else "DOWN",
            "news": "UP" if live_scores["news"] is not None or not missing_metrics["news"] else "DOWN",
            "analyzer": "UNKNOWN",
        }
        system_health = {
            "overall_status": "healthy" if all(status == "UP" for status in service_states.values() if status != "UNKNOWN") else "degraded",
            "services": service_states,
            "up_count": sum(1 for status in service_states.values() if status == "UP"),
            "total_count": 6,
            "timestamp": effective_timestamp,
            "last_updated": effective_timestamp,
            "source": "dashboard_live_service_probe",
            "fallback_used": False,
            "data_status": "LIVE" if any(status == "UP" for status in service_states.values()) else "MISSING",
        }

        return {
            "timestamp": effective_timestamp,
            "last_updated": effective_timestamp,
            "source": "dashboard_aggregate",
            "fallback_used": dashboard_fallback_used,
            "data_status": dashboard_status,
            "symbol": symbol,
            "timeframe": timeframe,
            "metrics": {
                "touche": _metric_payload("Touche EQS", "touche", touche_score, "#3B82F6", missing_metrics["touche"], summary=_build_metric_summary("touche", touche_score, module_details.get("touche"))),
                "fundamental": _metric_payload("Fundamental Score", "fundamental", fundamental_score, "#10B981", missing_metrics["fundamental"], summary=_build_metric_summary("fundamental", fundamental_score, module_details.get("fundamental"))),
                "quantum": _metric_payload("Quantum Score", "quantum", quantum_score, "#F59E0B", missing_metrics["quantum"], summary=_build_metric_summary("quantum", quantum_score, module_details.get("quantum"))),
                "sentinel": _metric_payload("Sentinel Score", "sentinel", sentinel_score, "#8B5CF6", missing_metrics["sentinel"], include_macro=True, summary=_build_metric_summary("sentinel", sentinel_score, module_details.get("sentinel"))),
                "news": _metric_payload("News Sentiment", "news", news_score, "#EC4899", missing_metrics["news"], include_symbol=False, summary=_build_metric_summary("news", news_score, module_details.get("news"))),
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
                "timestamp": consensus_timestamp,
                "last_updated": consensus_timestamp,
                "source": "dashboard_aggregate",
                "fallback_used": dashboard_fallback_used,
                "data_status": consensus_status,
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
        # Get live scores from AI service APIs
        from routes.dashboard import _fetch_live_scores
        live = await _fetch_live_scores(symbol, timeframe)
        touche_score = (live["touche"] * 100.0) if live["touche"] is not None else (await prometheus_client.get_touche_score(symbol, timeframe) or 50.0)
        fundamental_score = (live["fundamental"] * 100.0) if live["fundamental"] is not None else (await prometheus_client.get_fundamental_score(symbol, timeframe) or 50.0)
        news_score = (live["news"] * 100.0) if live["news"] is not None else (await prometheus_client.get_news_sentiment_score(timeframe) or 50.0)

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
                if val > 65: return "Guclu AL sinyali"
                elif val > 55: return "AL bolgesine yakin"
                elif val < 35: return "Guclu SAT sinyali"
                elif val < 45: return "SAT bolgesine yakin"
                else: return "Kararsiz bolge"

            def get_fundamental_comment(val):
                if val > 65: return "On-chain ag cok aktif"
                elif val > 55: return "On-chain ag aktif"
                elif val < 35: return "Ag aktivitesi dusuk"
                elif val < 45: return "Ag aktivitesi azaliyor"
                else: return "Ag aktivitesi notr"

            def get_quantum_comment(val):
                if val > 60: return "Likidite iyi, emirler rahat"
                elif val > 40: return "Likidite orta seviye"
                elif val < 30: return "Likidite dusuk, uyari!"
                else: return "Likidite sinirlandirilmis"

            def get_sentinel_comment(val):
                if val > 65: return "Piyasa sakin, islem icin uygun"
                elif val > 45: return "Piyasa normal seviyede"
                elif val < 35: return "Piyasa riskli, dikkat"
                else: return "Oynaklik yuksek"

            def get_news_comment(val):
                if val > 65: return "Haberler cok pozitif"
                elif val > 55: return "Haberler pozitif yonde"
                elif val < 35: return "Haberler negatif yonde"
                elif val < 45: return "Haberler olumsuz"
                else: return "Haberler kararsiz"

            # Build detailed analysis
            risk_notes = []
            action_points = []
            now_ts = datetime.now(timezone.utc).isoformat()

            if score < 40:
                risk_notes.append(f"Guclu SAT sinyali - {score:.1f} puaninda")
                action_points.append("SAT pozisyonu dusun (65+ beklediginde tekrar AL)")
            elif score > 65:
                risk_notes.append(f"Guclu AL sinyali - {score:.1f} puaninda")
                action_points.append(f"AL pozisyonu dusun (Risk: Fundamental={fundamental_score:.1f})")
            else:
                risk_notes.append(f"Kararsiz bolge - {score:.1f} puaninda BEKLE")
                action_points.append("65+ veya 35- beklemeye devam et")

            if fundamental_score < 40:
                risk_notes.append("Fundamental skor dusuk - on-chain aktivite azalis")
            if touche_score > 60 and news_score < 40:
                risk_notes.append("Teknik pozitif ama Haberler olumsuz - dikkatli ol")

            effective_ts = analysis_timestamp or now_ts
            return {
                "success": True,
                "timestamp": effective_ts,
                "last_updated": effective_ts,
                "source": analysis_source,
                "fallback_used": False,
                "data_status": "LIVE",
                "report": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": effective_ts,
                    "scores": {
                        "touche": round(touche_score, 2),
                        "fundamental": round(fundamental_score, 2),
                        "news": round(news_score, 2),
                    },
                    "consensus": {
                        "weighted_score": score,
                        "final_direction": recommendation,
                        "confidence": confidence * 100,
                    },
                    "final_recommendation": recommendation,
                    "final_reason": (
                        f"Teknik: {touche_score:.1f}% - {get_touche_comment(touche_score)}\n"
                        f"Temel: {fundamental_score:.1f}% - {get_fundamental_comment(fundamental_score)}\n"
                        f"Likidite: {touche_score:.1f}% - {get_quantum_comment(touche_score)}\n"
                        f"Risk: {fundamental_score:.1f}% - {get_sentinel_comment(fundamental_score)}\n"
                        f"Haber: {news_score:.1f}% - {get_news_comment(news_score)}\n\n"
                        f"Oneri: {recommendation} - Skor={score:.2f}% (Confidence={confidence*100:.0f}%)"
                    ),
                    "risk_notes": [note for note in risk_notes if note],
                    "action_points": action_points,
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
    if not OPTIMIZER_ENDPOINTS_ENABLED:
        return {
            "enabled": False,
            **_legacy_feature_detail(
                "optimizer endpoints",
                "AEGIS_ENABLE_OPTIMIZER_ENDPOINTS",
            ),
        }

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
    _require_optimizer_runtime()

    try:
        trade_record = TradeRecordClass(
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
    _require_optimizer_runtime()

    return {
        "weights": unified_optimizer.weights.copy(),
        "phase_params": unified_optimizer.phase_params.copy(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/optimizer/stats")
async def get_optimizer_statistics():
    """Get optimizer trading statistics"""
    _require_optimizer_runtime()

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
    _require_optimizer_runtime()

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
    _require_optimizer_runtime()

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
    _require_optimizer_runtime()

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
    _require_optimizer_runtime()

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
    _require_optimizer_runtime()

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
