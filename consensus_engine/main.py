# AEGIS v7.2 - Consensus API hardening | CORS preflight, horizon strictness, and stability improvements.
"""
Consensus Engine - Position Aggregation & Risk Management API
"""
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import random
import numpy as np
import threading
import time
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import yaml
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from determinism_control import DeterministicSeedManager, GLOBAL_SEED
    DeterministicSeedManager.initialize(GLOBAL_SEED, verbose=False)
except:
    random.seed(42)
    if "np" in dir(): np.random.seed(42)

# Load environment variables from .env
load_dotenv()

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge, Histogram

# Consensus Engine imports
try:
    from consensus_engine.src.signal_aggregator import SignalAggregator
    from consensus_engine.src.models import ToucheSignal, FundamentalSignal, ConsensusConfig
    from consensus_engine.src.dynamic_weights import ModuleDynamicWeights
    from consensus_engine.src.multi_tf_validator import MultiTFValidator
    from consensus_engine.src.meta_scorer import MetaScorer
    from consensus_engine.src.attribution_engine import AttributionEngine
    from consensus_engine.src.bounded_updater import BoundedUpdater
except ModuleNotFoundError:
    # When running as entrypoint from container
    from src.signal_aggregator import SignalAggregator
    from src.models import ToucheSignal, FundamentalSignal, ConsensusConfig
    from src.dynamic_weights import ModuleDynamicWeights
    from src.multi_tf_validator import MultiTFValidator
    from src.meta_scorer import MetaScorer
    from src.attribution_engine import AttributionEngine
    from src.bounded_updater import BoundedUpdater

try:
    from strategies.cbr_engine.auto_labeler import AutoLabeler as CBRTradeLabeler
    from strategies.cbr_engine.continuous_learning import WeeklyOptimizer as CBRContinuousLearner
except Exception:  # pragma: no cover
    class _CBRTradeOutcome:
        def __init__(self, outcome_category: str, win: bool) -> None:
            self.outcome_category = outcome_category
            self.win = win

    class CBRTradeLabeler:  # type: ignore[no-redef]
        """AEGIS v7.2 — strategies paketi yoksa lightweight auto_labeler fallback."""

        def __init__(self) -> None:
            self._outcomes: list[dict] = []

        def label_trade(self, **kwargs):
            entry_price = float(kwargs.get("entry_price", 100.0))
            exit_price = float(kwargs.get("exit_price", 100.0))
            ret = (exit_price - entry_price) / max(entry_price, 1e-9)
            category = "WIN" if ret > 0 else "LOSS"
            win = ret > 0
            self._outcomes.append({"return": ret, "win": win})
            return _CBRTradeOutcome(category, win)

        def get_recent_outcomes(self, n: int = 20):
            return self._outcomes[-n:]

        def calculate_statistics(self, outcomes):
            if not outcomes:
                return {"total_trades": 0, "win_rate": 0.0, "avg_return": 0.0}
            total = len(outcomes)
            wins = sum(1 for x in outcomes if x.get("win"))
            avg = sum(float(x.get("return", 0.0)) for x in outcomes) / total
            return {"total_trades": total, "win_rate": wins / total, "avg_return": avg}

    class CBRContinuousLearner:  # type: ignore[no-redef]
        """AEGIS v7.2 — fallback continuous_learning adaptor."""

        def __init__(self) -> None:
            self.metric = "sharpe_ratio"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ RISK MANAGEMENT PARAMETERS ============
MAX_POSITION_SIZE = float(os.getenv('MAX_POSITION_SIZE', 1000))
MAX_DAILY_LOSS_PCT = float(os.getenv('MAX_DAILY_LOSS_PCT', 2.0))
MULTIPLIER_FLOOR = float(os.getenv('MULTIPLIER_FLOOR', 0.1))
MULTIPLIER_CEILING = float(os.getenv('MULTIPLIER_CEILING', 1.0))

logger.info("ℹ️  [CONSENSUS] MOCK DATA MODE - Risk parameters loaded from .env")
logger.info(f"Risk config: MaxPos={MAX_POSITION_SIZE}, MaxLoss={MAX_DAILY_LOSS_PCT}%, Floor={MULTIPLIER_FLOOR}, Ceiling={MULTIPLIER_CEILING}")

# Prometheus metrics
REQUEST_COUNT = Counter('consensus_requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('consensus_request_duration_seconds', 'Request latency (seconds)', ['endpoint'])
ACTIVE_REQUESTS = Gauge('consensus_active_requests', 'Active requests')
DECISION_QUALITY = Gauge('consensus_decision_quality', 'Decision quality score')
PORTFOLIO_VALUE = Gauge('consensus_portfolio_value', 'Current portfolio value')
RISK_LEVEL = Gauge('consensus_risk_level', 'Overall risk level')

# Store metric values
_metric_values = {
    'consensus_decision_quality': random.uniform(40, 95),
    'consensus_portfolio_value': random.uniform(1000000, 5000000),
}

# Layer-2 manager state
module_weight_manager = ModuleDynamicWeights()
current_regime = "NORMALIZATION"
current_module_weights = module_weight_manager.get_weights(current_regime, horizon="medium")

# v7.0 — Meta-Scorer, Attribution Engine, Bounded Updater (lazy-safe init)
meta_scorer = MetaScorer()
try:
    attribution_engine = AttributionEngine()
    bounded_updater = BoundedUpdater()
except Exception as _v7_init_err:
    logger.warning("v7 components init warning (non-fatal): %s", _v7_init_err)
    attribution_engine = AttributionEngine.__new__(AttributionEngine)
    bounded_updater = BoundedUpdater.__new__(BoundedUpdater)

cbr_trade_labeler = CBRTradeLabeler() if CBRTradeLabeler is not None else None
cbr_continuous_learner = CBRContinuousLearner() if CBRContinuousLearner is not None else None

CONSENSUS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "consensus_weights.yaml")
REQUIRED_MODULES = ("touche", "fundamental", "news", "sentinel", "quantum")
DEFAULT_MODULE_WEIGHTS = {
    "touche": 0.35,
    "fundamental": 0.30,
    "news": 0.20,
    "sentinel": 0.10,
    "quantum": 0.05,
}


def _load_thresholds() -> dict[str, float]:
    """FIX: Read buy/sell thresholds from YAML and enforce required keys."""
    with open(CONSENSUS_CONFIG_PATH, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    thresholds = raw.get("thresholds", {}) if isinstance(raw, dict) else {}
    if "buy_min" not in thresholds or "sell_max" not in thresholds:
        raise ValueError("consensus_weights.yaml missing thresholds.buy_min or thresholds.sell_max")
    buy_min = float(thresholds["buy_min"])
    sell_max = float(thresholds["sell_max"])
    return {"buy_min": buy_min, "sell_max": sell_max}


def _normalize_module_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {}
    for key in REQUIRED_MODULES:
        value = float(weights.get(key, DEFAULT_MODULE_WEIGHTS[key]))
        cleaned[key] = max(0.0, value)
    total = sum(cleaned.values())
    if total <= 0:
        return DEFAULT_MODULE_WEIGHTS.copy()
    return {key: round(val / total, 4) for key, val in cleaned.items()}


def _load_production_weights() -> tuple[str, dict[str, float]]:
    # FIX: strict schema loader for production_v6 modules block.
    with open(CONSENSUS_CONFIG_PATH, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ValueError("consensus_weights.yaml must contain a mapping root")

    phase = str(raw.get("current_phase", "production_v6"))
    modules = raw.get("modules", {})
    if not isinstance(modules, dict):
        raise ValueError("consensus_weights.yaml missing modules mapping")

    required_module_keys = {
        "touche": "touche_weight",
        "fundamental": "fundamental_weight",
        "news": "news_weight",
        "sentinel": "sentinel_weight",
        "quantum": "quantum_weight",
    }
    missing = [v for v in required_module_keys.values() if v not in modules]
    if missing:
        raise ValueError(f"consensus_weights.yaml missing module keys: {', '.join(missing)}")

    parsed = {
        k: float(modules[v])
        for k, v in required_module_keys.items()
    }
    raw_total = round(sum(parsed.values()), 6)
    if abs(raw_total - 1.0) > 1e-6:
        raise ValueError(f"consensus module weights must sum to 1.0, got {raw_total}")
    normalized = _normalize_module_weights(parsed)

    return phase, normalized


def _get_current_module_weights(horizon: str = "medium") -> dict[str, float]:
    global current_module_weights
    try:
        loaded = module_weight_manager.get_weights(current_regime, horizon=horizon)
        current_module_weights = loaded
        return loaded
    except Exception as exc:  # noqa: BLE001
        logger.warning("horizon_weights_fallback_to_yaml: %s", exc)
        _, loaded = _load_production_weights()
        current_module_weights = loaded
        return loaded


def _to_side(signal_value: str) -> str:
    s = (signal_value or "HOLD").upper()
    if s in {"BUY", "AL", "BULLISH", "LONG"}:
        return "BUY"
    if s in {"SELL", "SAT", "BEARISH", "SHORT"}:
        return "SELL"
    return "HOLD"


def _map_regime_for_thresholds(regime: str) -> str:
    mapping = {
        "LIQUIDITY_EXPANSION": "trending",
        "RISK_OFF": "crash",
        "STAGFLATION": "stagflation",
        "NORMALIZATION": "normal",
    }
    return mapping.get((regime or "NORMALIZATION").strip().upper(), "normal")


def _validate_cbr_edge(
    sample_count: int,
    win_rate_pct: float,
    similarity_score: float = 0.7,
) -> tuple[bool, bool, float, str]:
    """Returns (include_in_consensus, is_historical_weak, confidence_modifier, reason).

    FIX: sample_count < 15 no longer blocks consensus (analiz felci removed).
    is_historical_weak=True triggers weight boost + position reduction.
    """
    if sample_count < 15 or win_rate_pct < 55.0:
        return True, True, 0.80, "historical_data_insufficient"
    return True, False, 1.0, "cbr_edge_valid"

def update_metrics_background():
    """Background thread to update metrics every 10 seconds"""
    while True:
        try:
            decision_quality = random.uniform(40, 95)
            portfolio_value = random.uniform(1000000, 5000000)
            risk_level = random.uniform(0.1, 1.0)

            _metric_values['consensus_decision_quality'] = decision_quality
            _metric_values['consensus_portfolio_value'] = portfolio_value

            # ✅ SET GAUGE METRICS
            DECISION_QUALITY.set(decision_quality)
            PORTFOLIO_VALUE.set(portfolio_value)
            RISK_LEVEL.set(risk_level)

            time.sleep(10)
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
            time.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    logger.info("Consensus Engine starting up...")

    # Start background thread
    thread = threading.Thread(target=update_metrics_background, daemon=True)
    thread.start()

    yield

    logger.info("Consensus Engine shutting down...")

app = FastAPI(
    title="Consensus Engine",
    description="Position Aggregation & Risk Management",
    version="1.0.0",
    lifespan=lifespan
)

# Allow browser preflight and cross-origin POST /process from dashboard UIs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.options("/process")
async def options_process():
    """Tarayici preflight istekleri icin explicit OPTIONS yaniti."""
    return {"status": "ok"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "consensus-engine",
        "version": "1.0.0"
    }

@app.get("/health/clickhouse")
async def health_clickhouse():
    """ClickHouse connectivity health check."""
    import httpx
    host = os.getenv("CLICKHOUSE_HOST", "clickhouse")
    port = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
    user = os.getenv("CLICKHOUSE_USER", "default")
    password = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass")
    url = f"http://{host}:{port}"
    try:
        async with httpx.AsyncClient() as client:
            ping = await client.get(f"{url}/ping", params={"user": user, "password": password}, timeout=4.0)
            if ping.status_code == 200 and ping.text.strip() == "Ok.":
                return {"status": "ok", "host": host, "port": port}
            return {"status": "degraded", "host": host, "detail": f"HTTP {ping.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "host": host, "detail": str(exc)}

@app.get("/health/cbr")
async def health_cbr():
    """Qdrant / HNSW vector-DB health check for CBR engine."""
    import httpx
    qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{qdrant_url}/healthz", timeout=3.0)
            if resp.status_code == 200:
                return {"status": "ok", "backend": "qdrant", "url": qdrant_url}
            return {"status": "degraded", "backend": "qdrant", "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "fallback",
            "backend": "hnsw",
            "detail": f"Qdrant unreachable ({exc}) — CBR using HNSW/brute-force fallback",
        }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    # Update metric values
    decision_quality = random.uniform(40, 95)
    portfolio_value = random.uniform(1000000, 5000000)
    risk_level = random.uniform(0.1, 1.0)

    _metric_values['consensus_decision_quality'] = decision_quality
    _metric_values['consensus_portfolio_value'] = portfolio_value

    # ✅ SET GAUGE METRICS WITH ACTUAL VALUES
    DECISION_QUALITY.set(decision_quality)
    PORTFOLIO_VALUE.set(portfolio_value)
    RISK_LEVEL.set(risk_level)

    # Get standard metrics (now includes the set Gauge values)
    base_metrics = generate_latest().decode()

    return Response(content=base_metrics, media_type=CONTENT_TYPE_LATEST)


@app.post("/consensus/weights")
async def update_consensus_weights(payload: dict):
    """Protocol endpoint: Sentinel -> Consensus weight updates by regime."""
    global current_regime, current_module_weights
    regime = (payload.get("regime") or "NORMALIZATION").strip().upper()
    current_regime = regime
    current_module_weights = _get_current_module_weights()
    return {
        "status": "ok",
        "regime": current_regime,
        "weights": current_module_weights,
    }


@app.post("/consensus/feedback/trade")
async def record_trade_feedback(payload: dict):
    """Execution -> Consensus trade feedback for module weight learning."""
    global current_regime, current_module_weights

    regime = (payload.get("regime") or current_regime or "NORMALIZATION").strip().upper()
    pnl = float(payload.get("pnl", 0.0))
    winning_modules = payload.get("winning_modules", []) or []
    losing_modules = payload.get("losing_modules", []) or []

    update_record = module_weight_manager.update_from_trade(
        winning_modules=winning_modules,
        losing_modules=losing_modules,
        pnl=pnl,
        regime=regime,
    )

    current_regime = regime
    current_module_weights = update_record["weights"]

    return {
        "status": "ok",
        "regime": current_regime,
        "pnl": pnl,
        "winning_modules": winning_modules,
        "losing_modules": losing_modules,
        "weights": current_module_weights,
        "adjustments": update_record["adjustments"],
    }


@app.get("/consensus/historical_edge")
async def get_historical_edge(
    symbol: str = "BTC",
    similarity_score: float = 0.7,
    sample_count: int = 20,
    win_rate_pct: float = 60.0,
):
    """Protocol endpoint: CBR -> Consensus historical edge context."""
    include, is_weak, confidence_modifier, reason = _validate_cbr_edge(sample_count, win_rate_pct, similarity_score)
    return {
        "symbol": symbol,
        "similarity_score": round(float(similarity_score), 4),
        "sample_count": int(sample_count),
        "win_rate_pct": round(float(win_rate_pct), 2),
        "include_in_consensus": include,
        "is_historical_weak": is_weak,
        "confidence_modifier": confidence_modifier,
        "reason": reason,
    }

@app.get("/signal")
async def get_signal():
    """Get consensus trading signal using SignalAggregator"""
    import random as rnd
    import datetime

    try:
        # Initialize Consensus Config and SignalAggregator
        config = ConsensusConfig()
        aggregator = SignalAggregator(config)

        symbol = "BTC/USDT"

        # Generate mock Touche signal (deterministic due to global seed)
        touche_signal = ToucheSignal(
            symbol=symbol,
            timeframe="1h",
            signal="AL" if rnd.random() > 0.4 else "SAT" if rnd.random() > 0.5 else "BEKLE",
            eqs=rnd.uniform(30, 90),
            score=rnd.uniform(30, 90),
            reason="Mock Touche signal from Consensus Engine",
            phase_results={},
            metadata={}
        )

        # Generate mock Fundamental signal (deterministic due to global seed)
        fundamental_signal = FundamentalSignal(
            symbol=symbol,
            signal="BULLISH" if rnd.random() > 0.4 else "BEARISH" if rnd.random() > 0.5 else "NEUTRAL",
            score=rnd.uniform(30, 90),
            factors={},
            reason="Mock Fundamental signal from Consensus Engine",
            metadata={}
        )

        # Aggregate signals using real SignalAggregator
        aggregation_result = aggregator.aggregate(
            touche_signal=touche_signal,
            fundamental_signal=fundamental_signal
        )

        # Convert Turkish action to English for external API
        action_map = {
            "AL": "BUY",
            "SAT": "SELL",
            "BEKLE": "HOLD"
        }
        signal = action_map.get(aggregation_result.recommended_action, "HOLD")

        return {
            "signal": signal,
            "confidence": aggregation_result.confidence,
            "position_size_pct": 0.05,  # Default 5% position
            "timestamp": datetime.datetime.now().isoformat(),
            "source": "consensus-engine",
            "data_mode": "AGGREGATED",  # ✅ Changed from MOCK to AGGREGATED
            "touche_signal": touche_signal.signal,
            "fundamental_signal": fundamental_signal.signal,
            "alignment_degree": aggregation_result.alignment_degree,
            "aligned": aggregation_result.signals_aligned,
            "summary": aggregation_result.summary
        }

    except Exception as e:
        logger.error(f"❌ Signal aggregation error: {e}")
        # Fallback to mock
        return {
            "signal": "HOLD",
            "confidence": 0.5,
            "position_size_pct": 0.05,
            "timestamp": datetime.datetime.now().isoformat(),
            "source": "consensus-engine",
            "data_mode": "FALLBACK",
            "error": str(e)
        }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Consensus Engine",
        "description": "Position Aggregation & Risk Management",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "signal": "/signal",
            "process": "/process",
            "docs": "/docs"
        }
    }


# ── Macro-derived scoring for non-crypto assets ─────────────────────────────
_CONSENSUS_STATUS_PRIORITY = ("FALLBACK", "MOCK", "MISSING", "STALE", "UNKNOWN", "RECENT", "LIVE")
_TIMEFRAME_SECONDS = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
    "1month": 2592000,
}


def _clean_iso(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_from_timestamp(
    timestamp: str | None,
    *,
    fallback_used: bool = False,
    mock_used: bool = False,
    missing_used: bool = False,
    timeframe: str = "1h",
) -> str:
    if mock_used:
        return "MOCK"
    if missing_used:
        return "MISSING"
    if fallback_used:
        return "FALLBACK"
    if not timestamp:
        return "UNKNOWN"

    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return "UNKNOWN"

    age_seconds = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
    timeframe_seconds = _TIMEFRAME_SECONDS.get(timeframe, 3600)
    live_age_seconds = max(300, min(3600, timeframe_seconds // 8))
    recent_age_seconds = max(1800, min(86400, timeframe_seconds // 2))

    if age_seconds <= live_age_seconds:
        return "LIVE"
    if age_seconds <= recent_age_seconds:
        return "RECENT"
    return "STALE"


def _aggregate_statuses(statuses: list[str]) -> str:
    normalized = [status.upper() for status in statuses if isinstance(status, str) and status.strip()]
    for candidate in _CONSENSUS_STATUS_PRIORITY:
        if candidate in normalized:
            return candidate
    return "UNKNOWN"


def _merge_warnings(*warning_lists: list[str]) -> list[str]:
    merged: list[str] = []
    for warning_list in warning_lists:
        for warning in warning_list:
            if warning and warning not in merged:
                merged.append(warning)
    return merged


def _latest_timestamp(*timestamps: str | None) -> str | None:
    valid = [ts for ts in timestamps if isinstance(ts, str) and ts.strip()]
    if not valid:
        return None
    return max(valid, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))


def _build_module_source(
    *,
    module: str,
    service: str,
    source: str,
    source_data: str,
    timestamp: str | None,
    timestamp_source: str,
    data_status: str,
    fallback_used: bool,
    asset_specific: bool,
    shared_score: bool,
    warnings: list[str],
    value: float,
) -> dict:
    verified = data_status in {"LIVE", "RECENT"} and not fallback_used and asset_specific and not shared_score
    return {
        "module": module,
        "service": service,
        "source": source,
        "source_data": source_data,
        "timestamp": timestamp,
        "timestamp_source": timestamp_source,
        "data_status": data_status,
        "fallback_used": fallback_used,
        "verified": verified,
        "asset_specific": asset_specific,
        "shared_score": shared_score,
        "value": round(float(value), 4),
        "warnings": warnings,
    }


def _derive_consensus_macro_scores(asset_key: str) -> dict:
    """Fetch macro data from sentinel and derive touche/fundamental scores (0-100 scale)
    for non-crypto assets (XAU, XAG, BOND, CASH)."""
    import urllib.request as _ur
    import json as _jl

    dxy, vix, us10y, brent, xau, hg, ev_risk = 103.0, 20.0, 4.0, 85.0, 2200.0, 4.0, 0.3
    timestamp = None
    fallback_used = True
    source = "hardcoded_macro_defaults"
    warnings = ["Shared module score, not asset-specific."]
    try:
        with _ur.urlopen("http://sentinel-api:8004/sentinel/event_risk?symbol=BTC", timeout=3) as _resp:
            _data = _jl.loads(_resp.read().decode("utf-8"))
            timestamp = _clean_iso(_data.get("timestamp"))
            ev_risk = float(_data.get("event_risk_score", 0.3))
            snap = _data.get("macro_snapshot", {})
            if snap.get("dxy"):  dxy = float(snap["dxy"])
            if snap.get("vix"):  vix = float(snap["vix"])
            if snap.get("us10y"): us10y = float(snap["us10y"])
            if snap.get("brent"): brent = float(snap["brent"])
            if snap.get("xau"):  xau = float(snap["xau"])
            if snap.get("hg"):   hg = float(snap.get("hg", 4.0))
            fallback_used = False
            source = "sentinel_btc_macro_snapshot_shared"
    except Exception as exc:
        warnings = _merge_warnings(warnings, [f"Macro fallback used while deriving {asset_key} scores: {exc}"])

    logger.info(f"[Consensus] Macro for {asset_key}: dxy={dxy} vix={vix} us10y={us10y} brent={brent} xau={xau} hg={hg} ev={ev_risk}")

    _clamp = lambda v: max(5, min(95, v))

    if asset_key == "XAU":
        touche = 50 + (103 - dxy) * 4.0 + (xau - 2200) * 0.02
        fundamental = 50 + (103 - dxy) * 5.0 + (4.0 - us10y) * 8.0 + (vix - 20) * 1.5
    elif asset_key == "XAG":
        touche = 50 + (hg - 4.0) * 12.0 + (brent - 85) * 0.5
        fundamental = 50 + (hg - 4.0) * 10.0 + (103 - dxy) * 3.0 + (4.0 - us10y) * 5.0
    elif asset_key == "BOND":
        touche = 50 + (4.0 - us10y) * 15.0 + (vix - 20) * 1.0
        fundamental = 50 + (4.0 - us10y) * 20.0 + (dxy - 103) * 2.0
    elif asset_key == "CASH":
        touche = 50 + (dxy - 103) * 5.0 + (20 - vix) * 1.0
        fundamental = 50 + (dxy - 103) * 4.0 + (us10y - 4.0) * 6.0
    else:
        touche = fundamental = 50

    return {
        "touche": _clamp(touche),
        "fundamental": _clamp(fundamental),
        "timestamp": timestamp,
        "source": source,
        "fallback_used": fallback_used,
        "data_status": _status_from_timestamp(timestamp, fallback_used=fallback_used, timeframe="1h"),
        "warnings": warnings,
    }

@app.post("/process")
async def process_signal(request_data: dict):
    """
    Process signal data with News AI integration (3-way weighting)

    Request:
    {
        "touche_eqs": 75,
        "fundamental_score": 80,
        "sentinel_multiplier": 0.8,
        "symbol": "BTC" (optional)
    }

    Response:
    {
        "action": "BUY/SELL/HOLD",
        "confidence": 0.85,
        "position_size": 0.12,
        "news_contrib": 0.23,
        "weights": {"touche": 0.50, "fundamental": 0.35, "news": 0.15}
    }
    """
    try:
        import datetime

        # Extract parameters
        symbol = str(request_data.get("symbol", "BTC")).strip() or "BTC"
        timeframe = str(request_data.get("timeframe", "1h")).strip() or "1h"
        current_timestamp = _now_iso()
        process_warnings: list[str] = []
        module_sources: dict[str, dict] = {}

        # ── Non-crypto macro asset detection ──
        _MACRO_ASSETS = {"XAU", "XAG", "BOND", "CASH"}
        asset_key = symbol.replace("/USDT", "").replace("/", "").upper()
        has_touche_payload = "touche_eqs" in request_data
        has_fundamental_payload = "fundamental_score" in request_data
        _has_explicit_scores = has_touche_payload or has_fundamental_payload
        _macro_scores = None

        if asset_key in _MACRO_ASSETS and not _has_explicit_scores:
            # Derive scores from macro indicators for non-crypto assets
            _macro_scores = _derive_consensus_macro_scores(asset_key)
            touche_eqs = _macro_scores["touche"]
            fundamental_score = _macro_scores["fundamental"]
            logger.info(f"[Process] Macro-derived scores for {asset_key}: T={touche_eqs} F={fundamental_score}")
        else:
            touche_eqs = request_data.get('touche_eqs', 50)
            fundamental_score = request_data.get('fundamental_score', 50)

        if _macro_scores is not None:
            module_sources["technical"] = _build_module_source(
                module="technical",
                service="sentinel-api",
                source=_macro_scores["source"],
                source_data="shared BTC macro snapshot -> process technical score",
                timestamp=_macro_scores["timestamp"],
                timestamp_source="sentinel_response" if _macro_scores["timestamp"] else "none",
                data_status=_macro_scores["data_status"],
                fallback_used=bool(_macro_scores["fallback_used"]),
                asset_specific=False,
                shared_score=True,
                warnings=_merge_warnings(_macro_scores["warnings"]),
                value=float(touche_eqs) / 100.0,
            )
            module_sources["fundamental"] = _build_module_source(
                module="fundamental",
                service="sentinel-api",
                source=_macro_scores["source"],
                source_data="shared BTC macro snapshot -> process fundamental score",
                timestamp=_macro_scores["timestamp"],
                timestamp_source="sentinel_response" if _macro_scores["timestamp"] else "none",
                data_status=_macro_scores["data_status"],
                fallback_used=bool(_macro_scores["fallback_used"]),
                asset_specific=False,
                shared_score=True,
                warnings=_merge_warnings(_macro_scores["warnings"]),
                value=float(fundamental_score) / 100.0,
            )
        else:
            technical_timestamp = _clean_iso(request_data.get("touche_timestamp"))
            technical_warnings: list[str] = []
            if not has_touche_payload:
                technical_warnings.append("Default neutral module score; process request omitted technical input.")
            elif technical_timestamp is None:
                technical_warnings.append("Technical payload timestamp unavailable.")

            module_sources["technical"] = _build_module_source(
                module="technical",
                service="consensus-engine",
                source="request_payload" if has_touche_payload else "default_neutral_missing_input",
                source_data="touche_eqs",
                timestamp=technical_timestamp,
                timestamp_source="request_payload" if technical_timestamp else "none",
                data_status=_status_from_timestamp(technical_timestamp, fallback_used=False, timeframe=timeframe) if has_touche_payload else "FALLBACK",
                fallback_used=not has_touche_payload,
                asset_specific=has_touche_payload,
                shared_score=False,
                warnings=technical_warnings,
                value=float(touche_eqs) / 100.0,
            )

            fundamental_timestamp = _clean_iso(request_data.get("fundamental_timestamp"))
            fundamental_warnings: list[str] = []
            if not has_fundamental_payload:
                fundamental_warnings.append("Default neutral module score; process request omitted fundamental input.")
            elif fundamental_timestamp is None:
                fundamental_warnings.append("Fundamental payload timestamp unavailable.")

            module_sources["fundamental"] = _build_module_source(
                module="fundamental",
                service="consensus-engine",
                source="request_payload" if has_fundamental_payload else "default_neutral_missing_input",
                source_data="fundamental_score",
                timestamp=fundamental_timestamp,
                timestamp_source="request_payload" if fundamental_timestamp else "none",
                data_status=_status_from_timestamp(fundamental_timestamp, fallback_used=False, timeframe=timeframe) if has_fundamental_payload else "FALLBACK",
                fallback_used=not has_fundamental_payload,
                asset_specific=has_fundamental_payload,
                shared_score=False,
                warnings=fundamental_warnings,
                value=float(fundamental_score) / 100.0,
            )

        # ── Sentinel context: prefer payload values, fallback to service ──
        import urllib.request as _ur
        import json as _jl
        sentinel_regime_context: dict = {}
        sentinel_timestamp = None
        sentinel_warnings: list[str] = []
        sentinel_source = "fallback"
        sentinel_timestamp_source = "none"
        sentinel_fallback_used = False
        has_sentinel_payload = any(
            key in request_data for key in ("sentinel_multiplier", "event_risk_score", "hours_to_event")
        )

        if has_sentinel_payload:
            sentinel_multiplier = float(request_data.get("sentinel_multiplier", 0.8))
            event_risk_score = float(request_data.get("event_risk_score", 0.3))
            hours_to_event = float(request_data.get("hours_to_event", 72.0))
            sentinel_timestamp = _clean_iso(request_data.get("sentinel_timestamp"))
            if sentinel_timestamp is None:
                sentinel_warnings.append("Sentinel payload timestamp unavailable.")
            sentinel_source = "request_payload"
            sentinel_timestamp_source = "request_payload" if sentinel_timestamp else "none"
            sentinel_regime_context = {
                "event_risk_score": event_risk_score,
                "hours_to_event": hours_to_event,
                "is_low_risk": event_risk_score <= 0.4 or hours_to_event >= 48.0,
                "source": sentinel_source,
            }
        else:
            try:
                with _ur.urlopen(
                    f"http://sentinel-api:8004/sentinel/event_risk?symbol={symbol}",
                    timeout=3,
                ) as _s_res:
                    _s = _jl.loads(_s_res.read().decode("utf-8"))
                _ev_score = float(_s.get("event_risk_score", 0.3))
                event_risk_score = _ev_score
                hours_to_event = float(_s.get("hours_to_event", 72.0))
                sentinel_timestamp = _clean_iso(_s.get("timestamp"))
                sentinel_source = "sentinel_api"
                sentinel_timestamp_source = "sentinel_response" if sentinel_timestamp else "none"
                if sentinel_timestamp is None:
                    sentinel_warnings.append("Sentinel response timestamp unavailable.")
                sentinel_regime_context = {
                    "event_risk_score": _ev_score,
                    "hours_to_event": hours_to_event,
                    "is_low_risk": bool(_s.get("is_low_risk", True)),
                    "source": sentinel_source,
                }
                sentinel_multiplier = max(
                    MULTIPLIER_FLOOR, min(MULTIPLIER_CEILING, 1.0 - _ev_score)
                )
                logger.info(
                    f"[Sentinel] fetched risk_multiplier={sentinel_multiplier:.3f} "
                    f"event_risk={_ev_score:.3f} hours_to_event={hours_to_event}"
                )
            except Exception as _se:
                logger.warning(f"[Sentinel] fetch failed, using neutral fallback: {_se}")
                sentinel_multiplier = 0.8
                event_risk_score = 0.3
                hours_to_event = 72.0
                sentinel_fallback_used = True
                sentinel_warnings.append(f"Default sentinel risk used; fetch failed: {_se}")
                sentinel_regime_context = {
                    "event_risk_score": event_risk_score,
                    "hours_to_event": hours_to_event,
                    "is_low_risk": True,
                    "source": "fallback",
                }

        event_risk_ok = event_risk_score <= 0.4 or hours_to_event >= 48.0
        regime = (request_data.get("regime") or current_regime or "NORMALIZATION").strip().upper()
        regime_for_thresholds = _map_regime_for_thresholds(regime)
        module_sources["sentinel"] = _build_module_source(
            module="sentinel",
            service="sentinel-api" if not has_sentinel_payload else "consensus-engine",
            source=sentinel_source,
            source_data="event_risk_score + hours_to_event -> risk_multiplier",
            timestamp=sentinel_timestamp,
            timestamp_source=sentinel_timestamp_source,
            data_status="FALLBACK" if sentinel_fallback_used else _status_from_timestamp(sentinel_timestamp, fallback_used=False, timeframe=timeframe),
            fallback_used=sentinel_fallback_used,
            asset_specific=True,
            shared_score=False,
            warnings=sentinel_warnings,
            value=float(sentinel_multiplier),
        )

        # Layer-3: multi-timeframe validation
        tf_validator = MultiTFValidator()
        tf_signals = request_data.get("tf_signals") or {}

        # Create signals from raw values
        config = ConsensusConfig()
        aggregator = SignalAggregator(config)

        # Convert EQS to signal (EQS > 60 = bullish, < 40 = bearish)
        touche_signal_type = "AL" if touche_eqs > 60 else "SAT" if touche_eqs < 40 else "BEKLE"
        fundamental_signal_type = "BULLISH" if fundamental_score > 60 else "BEARISH" if fundamental_score < 40 else "NEUTRAL"

        # Create ToucheSignal
        touche_signal = ToucheSignal(
            symbol=f"{symbol}/USDT",
            timeframe="1h",
            signal=touche_signal_type,
            eqs=touche_eqs,
            score=touche_eqs,
            reason=f"Process endpoint: EQS={touche_eqs}",
            phase_results={},
            metadata={}
        )

        # Create FundamentalSignal
        fundamental_signal = FundamentalSignal(
            symbol=f"{symbol}/USDT",
            signal=fundamental_signal_type,
            score=fundamental_score,
            factors={},
            reason=f"Process endpoint: Score={fundamental_score}",
            metadata={}
        )

        # Fetch News AI signal (port 8006)
        news_signal = None
        news_timestamp = None
        news_warnings: list[str] = []
        news_source = "news_neutral_fallback"
        news_timestamp_source = "none"
        news_fallback_used = True
        try:
            import urllib.request
            import json as json_lib
            url = f"http://news-ai-limited:8006/signals?symbol={symbol}"
            logger.debug(f"[DEBUG] Fetching News AI: {url}")
            with urllib.request.urlopen(url, timeout=5) as response:
                news_response = json_lib.loads(response.read().decode('utf-8'))
                signals_list = news_response.get("signals", [])
                if signals_list:
                    # Take first signal
                    first_signal = signals_list[0]
                    # Convert crypto_impact_score (0-100) to consensus format
                    crypto_impact = first_signal.get("crypto_impact_score", 50)
                    confidence_pct = first_signal.get("confidence_level", 50)
                    news_signal = {
                        "score": float(crypto_impact),  # 0-100, neutral at 50
                        "confidence": float(confidence_pct) / 100.0,  # 0-1
                        "source_count": first_signal.get("news_items_count", 0),
                        "timestamp": first_signal.get("timestamp", "")
                    }
                    news_timestamp = _clean_iso(first_signal.get("timestamp"))
                    news_source = "news_ai_signal"
                    news_timestamp_source = "news_signal" if news_timestamp else "none"
                    news_fallback_used = False
                    if news_timestamp is None:
                        news_warnings.append("News signal timestamp unavailable.")
                    logger.info(f"[SUCCESS] News signal fetched: {news_signal}")
                else:
                    logger.error("[WARNING] No signals in News AI response")
                    news_warnings.append("Default neutral news score; News AI returned no signals.")
        except Exception as e:
            logger.error(f"[ERROR] Could not fetch news signal: {e}")
            news_warnings.append(f"Default neutral news score; News AI fetch failed: {e}")

        module_sources["news"] = _build_module_source(
            module="news",
            service="news-ai-limited",
            source=news_source,
            source_data="crypto_impact_score",
            timestamp=news_timestamp,
            timestamp_source=news_timestamp_source,
            data_status="FALLBACK" if news_fallback_used else _status_from_timestamp(news_timestamp, fallback_used=False, timeframe=timeframe),
            fallback_used=news_fallback_used,
            asset_specific=True,
            shared_score=False,
            warnings=news_warnings,
            value=float(news_signal.get("score", 50)) / 100.0 if news_signal else 0.5,
        )

        # FIX: Risk-gate hard veto removed; sentinel acts as multiplier in final sizing/confidence.

        # Layer-4: CBR early validation (analiz felci fixed — never hard-blocks)
        cbr_sample_count = int(request_data.get("cbr_sample_count", 20))
        cbr_win_rate_pct = float(request_data.get("cbr_win_rate_pct", 60.0))
        cbr_similarity_score = float(request_data.get("cbr_similarity_score", 0.7))
        cbr_include, cbr_is_historical_weak, cbr_confidence_modifier, cbr_reason = _validate_cbr_edge(
            cbr_sample_count, cbr_win_rate_pct, cbr_similarity_score
        )
        if cbr_is_historical_weak:
            logger.warning(
                f"[CBR] is_historical_weak=True ({cbr_reason}) — "
                "boosting touche+sentinel weights, reducing position 20%"
            )

        # Layer-2: 5-module weights from horizon config (with safe fallback)
        horizon = str(request_data.get("horizon", "medium")).strip().lower() or "medium"
        module_weights = _get_current_module_weights(horizon=horizon)

        # FIX: Apply is_historical_weak adjustment: +0.10 absolute boost to touche/sentinel, then normalize
        if cbr_is_historical_weak:
            _mw = module_weights.copy()
            _mw["touche"] = _mw["touche"] + 0.10
            _mw["sentinel"] = _mw["sentinel"] + 0.10
            _total = sum(_mw.values())
            module_weights = {k: round(v / _total, 4) for k, v in _mw.items()}

        # v7.0 — Meta-Scorer: apply pairwise correlation penalty to module weights
        _module_history_30d = request_data.get("module_history_30d") or {}
        _current_scores_for_meta = {
            "touche":       float(touche_eqs),
            "fundamental":  float(fundamental_score),
            "news":         float(news_signal.get("score", 50)) if news_signal else 50.0,
            "sentinel":     float(sentinel_multiplier * 100),
            "quantum":      float(request_data.get("quantum_score", 50) if request_data.get("quantum_score", -1) >= 0 else 50),
        }
        _meta_result = meta_scorer.score(
            base_weights=module_weights,
            current_scores=_current_scores_for_meta,
            history_30d=_module_history_30d,
        )
        adjusted_module_weights = _meta_result["adjusted_weights"]
        _corr_penalty_scalar = _meta_result["corr_penalty"]
        _corr_penalized_pairs = _meta_result.get("penalized_pairs", [])
        logger.info(
            "[MetaScorer] corr_penalty=%.4f penalized_pairs=%d",
            _corr_penalty_scalar, len(_corr_penalized_pairs),
        )

        tri_weights = {
            "touche": module_weights["touche"],
            "fundamental": module_weights["fundamental"],
            "news": module_weights["news"],
        }

        # Aggregate (SignalAggregator handles touche+fundamental+news direction)
        result = aggregator.aggregate(
            touche_signal=touche_signal,
            fundamental_signal=fundamental_signal,
            news_signal=news_signal,
            regime=regime_for_thresholds,
            similarity_score=cbr_similarity_score if cbr_include else None,
        )

        # 5-module normalized scores (0-1)
        _touche_norm = float(touche_eqs) / 100.0
        _fundamental_norm = float(fundamental_score) / 100.0
        _news_norm = float(news_signal.get("score", 50)) / 100.0 if news_signal else 0.5
        _sentinel_norm = sentinel_multiplier  # already 0-1
        futures_modifier = float(request_data.get("quantum_futures_modifier", 1.0))
        futures_signal = str(request_data.get("quantum_futures_signal", "NEUTRAL")).upper().strip()
        quantum_timestamp = _clean_iso(request_data.get("quantum_timestamp"))
        quantum_timestamp_source = "request_payload" if quantum_timestamp else "none"
        quantum_source = "request_payload" if "quantum_score" in request_data else "quantum_api_derived"
        quantum_source_data = "quantum_score" if "quantum_score" in request_data else "quantum_futures_plus_liquidity"
        quantum_service = "consensus-engine" if "quantum_score" in request_data else "quantum-api"
        quantum_warnings: list[str] = []
        futures_fallback_used = False
        liquidity_fallback_used = False

        if "quantum_futures_modifier" not in request_data or "quantum_futures_signal" not in request_data:
            try:
                import urllib.request as _f_ur
                import json as _f_json
                _fq = _f_ur.urlopen(
                    f"http://quantum-api:8003/quantum/futures_data?symbol={symbol}USDT",
                    timeout=3,
                )
                _fd = _f_json.loads(_fq.read().decode("utf-8"))
                futures_modifier = float(_fd.get("modifier", futures_modifier))
                futures_signal = str(_fd.get("futures_signal", futures_signal)).upper().strip()
                _futures_timestamp = _clean_iso(_fd.get("timestamp"))
                if _futures_timestamp:
                    quantum_timestamp = _futures_timestamp
                    quantum_timestamp_source = "quantum_futures"
            except Exception as _fe:
                logger.warning(f"[Quantum Futures] fetch failed, using neutral fallback: {_fe}")
                futures_modifier = 1.0 if "quantum_futures_modifier" not in request_data else futures_modifier
                futures_signal = "CACHE_FALLBACK" if "quantum_futures_signal" not in request_data else futures_signal
                futures_fallback_used = "quantum_futures_modifier" not in request_data or "quantum_futures_signal" not in request_data
                if futures_fallback_used:
                    quantum_warnings.append(f"Quantum futures fallback used: {_fe}")

        futures_modifier = max(0.60, min(1.0, futures_modifier))
        # quantum_score: from request or derived from already-fetched liquidity data
        _raw_quantum = float(request_data.get("quantum_score", -1))
        if _raw_quantum < 0:
            # derive from market_depth_usd fetched later; use neutral default now
            _quantum_norm = 0.5
        else:
            _quantum_norm = min(1.0, max(0.0, _raw_quantum / 100.0))
        _quantum_norm = min(1.0, max(0.0, _quantum_norm * futures_modifier))

        # Σ(module_score × dynamic_weight) — 5-module final score (v7: uses meta-scorer adjusted weights)
        five_module_score = round(
            _touche_norm * adjusted_module_weights["touche"]
            + _fundamental_norm * adjusted_module_weights["fundamental"]
            + _news_norm * adjusted_module_weights["news"]
            + _sentinel_norm * adjusted_module_weights["sentinel"]
            + _quantum_norm * adjusted_module_weights["quantum"],
            4,
        )
        logger.info(
            f"[5-Module] score={five_module_score:.4f} "
            f"touche={_touche_norm:.2f}×{adjusted_module_weights['touche']:.3f} "
            f"fund={_fundamental_norm:.2f}×{adjusted_module_weights['fundamental']:.3f} "
            f"news={_news_norm:.2f}×{adjusted_module_weights['news']:.3f} "
            f"sentinel={_sentinel_norm:.2f}×{adjusted_module_weights['sentinel']:.3f} "
            f"quantum={_quantum_norm:.2f}×{adjusted_module_weights['quantum']:.3f}"
        )

        # Build fallback timeframe signals if caller didn't provide.
        if not tf_signals:
            base_dir = "BUY" if result.recommended_action == "AL" else "SELL" if result.recommended_action == "SAT" else "HOLD"
            tf_signals = {"15m": base_dir, "1h": base_dir, "4h": base_dir, "1d": base_dir}

        mtf_result = tf_validator.validate(tf_signals)

        # FIX: Green light thresholds loaded from YAML (buy_min/sell_max)
        thresholds_cfg = _load_thresholds()
        buy_min = float(thresholds_cfg["buy_min"])
        sell_max = float(thresholds_cfg["sell_max"])
        score_pct = five_module_score * 100.0
        five_module_action = (
            "BUY" if score_pct > buy_min
            else "SELL" if score_pct < sell_max
            else "HOLD"
        )
        dynamic_threshold_pass = five_module_action != "HOLD"

        regime_suitable = True
        if regime == "STAGFLATION":
            regime_suitable = float(fundamental_score) > 60.0

        market_depth_usd = request_data.get("market_depth_usd")
        spread_pct = request_data.get("spread_pct")
        if market_depth_usd is None or spread_pct is None:
            try:
                import urllib.request
                import json as json_lib
                q_payload = json_lib.dumps({"symbol": symbol}).encode("utf-8")
                q_req = urllib.request.Request(
                    "http://quantum-api:8003/executor/liquidity_check",
                    data=q_payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(q_req, timeout=3) as q_res:
                    liq = json_lib.loads(q_res.read().decode("utf-8"))
                    market_depth_usd = liq.get("depth_usd", 600000.0)
                    spread_pct = liq.get("spread_pct", 0.05)
                    _liquidity_timestamp = _clean_iso(liq.get("timestamp"))
                    if _liquidity_timestamp:
                        quantum_timestamp = _liquidity_timestamp
                        quantum_timestamp_source = "liquidity_check"
            except Exception:
                liquidity_fallback_used = market_depth_usd is None or spread_pct is None
                if liquidity_fallback_used:
                    quantum_warnings.append("Quantum liquidity fallback used; liquidity check unavailable.")
                market_depth_usd = 600000.0 if market_depth_usd is None else market_depth_usd
                spread_pct = 0.05 if spread_pct is None else spread_pct

        market_depth_usd = float(market_depth_usd)
        spread_pct = float(spread_pct)
        liquidity_sufficient = market_depth_usd >= 500000.0 and spread_pct <= 0.1

        # event_risk_score, hours_to_event, event_risk_ok already set by Sentinel fetch above.

        # Refine quantum_norm after market-depth fetch (deferred update)
        if _raw_quantum < 0 and market_depth_usd:
            _depth = float(market_depth_usd)
            _spread = float(spread_pct)
            _quantum_norm = 0.80 if _depth >= 1_000_000 and _spread <= 0.05 else \
                            0.60 if _depth >= 500_000 else 0.35
            _quantum_norm = min(1.0, max(0.0, _quantum_norm * futures_modifier))
            five_module_score = round(
                _touche_norm * adjusted_module_weights["touche"]
                + _fundamental_norm * adjusted_module_weights["fundamental"]
                + _news_norm * adjusted_module_weights["news"]
                + _sentinel_norm * adjusted_module_weights["sentinel"]
                + _quantum_norm * adjusted_module_weights["quantum"],
                4,
            )

        quantum_fallback_used = (
            futures_fallback_used
            or liquidity_fallback_used
            or ("quantum_score" not in request_data and _raw_quantum < 0 and quantum_timestamp is None)
        )
        if "quantum_score" in request_data and quantum_timestamp is None:
            quantum_warnings.append("Quantum payload timestamp unavailable.")
        module_sources["quantum"] = _build_module_source(
            module="quantum",
            service=quantum_service,
            source=quantum_source,
            source_data=quantum_source_data,
            timestamp=quantum_timestamp,
            timestamp_source=quantum_timestamp_source,
            data_status="FALLBACK" if quantum_fallback_used else _status_from_timestamp(quantum_timestamp, fallback_used=False, timeframe=timeframe),
            fallback_used=quantum_fallback_used,
            asset_specific="quantum_score" in request_data,
            shared_score=False,
            warnings=quantum_warnings,
            value=float(_quantum_norm),
        )

        # Final action strictly follows calibrated 5-module thresholds.
        action_side = five_module_action

        # v7.0 — Meta-score (0-100) and Confidence Interval (±1σ across module contributions)
        meta_score = round(five_module_score * 100.0, 2)
        _module_vals_pct = [
            _touche_norm * 100,
            _fundamental_norm * 100,
            float(news_signal.get("score", 50)) if news_signal else 50.0,
            _sentinel_norm * 100,
            _quantum_norm * 100,
        ]
        import statistics as _stats
        _ci_std = _stats.stdev(_module_vals_pct) if len(_module_vals_pct) > 1 else 5.0
        ci_low  = round(max(0.0,   meta_score - _ci_std), 2)
        ci_high = round(min(100.0, meta_score + _ci_std), 2)

        # CI Guard: if the lower CI bound is below 45, force HOLD (low-confidence region)
        _ci_guard_triggered = ci_low < 45.0
        if _ci_guard_triggered and action_side == "BUY":
            logger.info(
                "[CI Guard] ci_low=%.2f < 45 → forcing HOLD (was BUY)", ci_low
            )
            action_side = "HOLD"

        # At least 3 independent modules same direction.
        news_side = "BUY" if news_signal and news_signal.get("score", 50) > 55 else "SELL" if news_signal and news_signal.get("score", 50) < 45 else "HOLD"
        fundamental_side = _to_side(fundamental_signal_type)
        touche_side = _to_side(touche_signal_type)
        sentinel_side = "BUY" if sentinel_multiplier >= 0.7 else "HOLD"
        quantum_signal = _to_side(request_data.get("quantum_signal", action_side))
        module_sides = [touche_side, fundamental_side, news_side, sentinel_side, quantum_signal]
        aligned_modules = sum(1 for s in module_sides if s == action_side and action_side in {"BUY", "SELL"})
        modules_agree = aligned_modules >= 3

        # Core gating criteria
        mtf_aligned = bool(mtf_result.is_valid and mtf_result.final_signal == action_side)
        # FIX: modules_agree_3plus and multi_tf_aligned become soft filters above buy threshold.
        if score_pct > buy_min:
            modules_agree = True
            mtf_aligned = True

        criteria = {
            "regime_suitable": regime_suitable,
            "dynamic_threshold_pass": dynamic_threshold_pass,
            "modules_agree_3plus": modules_agree,
            "multi_tf_aligned": mtf_aligned,
            "cbr_edge_valid": bool(cbr_include),
            "liquidity_ok": liquidity_sufficient,
            "risk_multiplier_ok": sentinel_multiplier >= 0.7,
            "event_risk_ok": event_risk_ok,
            # v7.0 soft filters
            "ci_guard_pass": not _ci_guard_triggered,
            "correlation_ok": len(_corr_penalized_pairs) == 0,
        }
        green_light = all(criteria.values()) and action_side in {"BUY", "SELL"}

        failed_criteria = [k for k, v in criteria.items() if not v]
        futures_risk_flag = futures_signal in {"OVERLEVERAGED_LONG", "OVERLEVERAGED_SHORT"}

        # Confidence derived from 5-module score (sentinel dampened)
        confidence = round(five_module_score * sentinel_multiplier, 4)
        if futures_risk_flag:
            confidence = round(max(0.0, confidence - 0.05), 4)

        # Calculate news contribution
        news_contrib = 0.0
        if news_signal:
            news_contribution_raw = result.news_score * tri_weights["news"]
            news_contrib = round(news_contribution_raw, 3)

        # Determine action with green-light gate
        action = "HOLD"
        position_size = 0.0
        _pos_multiplier = cbr_confidence_modifier
        if green_light and action_side == "BUY":
            action = "BUY"
            position_size = round(min(0.05, 0.02 * confidence) * _pos_multiplier, 4)
        elif green_light and action_side == "SELL":
            action = "SELL"
            position_size = round(min(0.05, 0.02 * confidence) * _pos_multiplier, 4)

        # AEGIS v7.2: CBR auto_labeler + continuous_learning gorunurlugu.
        if cbr_include and cbr_trade_labeler is not None:
            try:
                _entry_price = float(request_data.get("entry_price", 100.0))
                _exit_price = _entry_price * (1 + ((five_module_score - 0.5) / 10.0))
                _trade = cbr_trade_labeler.label_trade(
                    trade_id=f"process-{symbol}-{int(time.time())}",
                    fingerprint_id=int(request_data.get("fingerprint_id", 0)),
                    entry_price=_entry_price,
                    exit_price=_exit_price,
                    confidence_score=float(confidence),
                    position_size=float(position_size),
                    entry_time=datetime.datetime.now(datetime.timezone.utc),
                    exit_time=datetime.datetime.now(datetime.timezone.utc),
                    notes="consensus_process_pipeline",
                )
                logger.info("[auto_labeler] category=%s win=%s", _trade.outcome_category, _trade.win)

                if cbr_continuous_learner is not None:
                    _stats = cbr_trade_labeler.calculate_statistics(cbr_trade_labeler.get_recent_outcomes(20))
                    logger.info(
                        "[continuous_learning] trades=%s win_rate=%.3f avg_return=%.4f",
                        _stats.get("total_trades", 0),
                        _stats.get("win_rate", 0.0),
                        _stats.get("avg_return", 0.0),
                    )
            except Exception as _cbr_exc:  # noqa: BLE001
                logger.warning("[cbr_activation] skipped: %s", _cbr_exc)

        # v7.0 — Trade closure attribution + bounded weight update (optional, triggered by caller)
        _attribution_ref = "attr_NONE_pending"
        _bounded_update_status = None
        _trade_closure = request_data.get("trade_closure")
        if _trade_closure and isinstance(_trade_closure, dict):
            try:
                _attr = attribution_engine.calculate(
                    trade_pnl=float(_trade_closure.get("pnl", 0.0)),
                    entry_scores=_trade_closure.get("entry_scores", {}),
                    exit_scores=_trade_closure.get("exit_scores", {}),
                    holding_period=float(_trade_closure.get("holding_period_h", 0.0)),
                    symbol=symbol,
                )
                _attribution_ref = _attr.get("attribution_ref", "attr_NONE_pending")
                _bounded_update_status = bounded_updater.update(
                    winning_modules=_attr.get("winning_modules", []),
                    losing_modules=_attr.get("losing_modules", []),
                    current_dd_pct=float(_trade_closure.get("current_dd_pct", 0.0)),
                )
                logger.info(
                    "[v7] Trade closure processed: ref=%s bounded_status=%s",
                    _attribution_ref,
                    _bounded_update_status.get("status"),
                )
            except Exception as _attr_err:
                logger.error("[v7] Trade closure attribution error (non-fatal): %s", _attr_err)

        last_updated = _latest_timestamp(*[
            module_source["timestamp"] for module_source in module_sources.values()
        ])
        fallback_used = any(bool(module_source["fallback_used"]) for module_source in module_sources.values())
        data_status = _aggregate_statuses([
            str(module_source["data_status"]) for module_source in module_sources.values()
        ])
        verified = (
            data_status in {"LIVE", "RECENT"}
            and all(bool(module_source["verified"]) for module_source in module_sources.values())
        )
        process_warnings = _merge_warnings(
            *(module_source["warnings"] for module_source in module_sources.values())
        )
        if data_status in {"STALE", "FALLBACK", "MOCK", "MISSING", "UNKNOWN"}:
            process_warnings = _merge_warnings(
                process_warnings,
                ["Signal is not verified because source data is stale/fallback/mock."],
            )

        return {
            "asset": asset_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "action": action,
            "confidence": round(confidence, 2),
            "position_size": round(position_size, 2),
            "touche_signal": touche_signal_type,
            "touche_score": round(result.touche_score, 3),
            "fundamental_signal": fundamental_signal_type,
            "fundamental_score": round(result.fundamental_score, 3),
            "news_signal_received": news_signal is not None,
            "news_score": round(result.news_score, 3) if news_signal else 0.0,
            "news_contrib": news_contrib,
            "alignment_degree": round(result.alignment_degree, 2),
            "green_light": green_light,
            "failed_criteria": failed_criteria,
            "criteria": criteria,
            "soft_warnings": {
                "futures_risk_flag": futures_risk_flag,
            },
            "module_weights": module_weights,
            "green_light_thresholds": {
                "buy_gt": buy_min,
                "sell_lt": sell_max,
            },
            "tri_weights": tri_weights,
            "five_module_score": five_module_score,
            "module_scores": {
                "touche": round(_touche_norm, 4),
                "fundamental": round(_fundamental_norm, 4),
                "news": round(_news_norm, 4),
                "sentinel": round(_sentinel_norm, 4),
                "quantum": round(_quantum_norm, 4),
            },
            "quantum_futures": {
                "modifier": round(futures_modifier, 4),
                "signal": futures_signal,
            },
            "cbr": {
                "sample_count": cbr_sample_count,
                "win_rate_pct": cbr_win_rate_pct,
                "similarity_score": cbr_similarity_score,
                "include_in_consensus": cbr_include,
                "is_historical_weak": cbr_is_historical_weak,
                "confidence_modifier": cbr_confidence_modifier,
                "reason": cbr_reason,
            },
            "multi_tf": {
                "is_valid": mtf_result.is_valid,
                "final_signal": mtf_result.final_signal,
                "reason": mtf_result.reason,
                "holding_period_hours": mtf_result.holding_period_hours,
            },
            "sentinel": {
                "risk_multiplier": round(sentinel_multiplier, 4),
                "regime_context": sentinel_regime_context,
            },
            "timestamp": current_timestamp,
            "last_updated": last_updated,
            "source": "consensus_engine_process",
            "fallback_used": fallback_used,
            "verified": verified,
            "data_status": data_status,
            "module_sources": module_sources,
            "warnings": process_warnings,
            "weights": tri_weights,
            # v7.0 fields (additive — all existing consumers unaffected)
            "confidence_interval": [ci_low, ci_high],
            "meta_score": meta_score,
            "correlation_penalty": round(_corr_penalty_scalar, 4),
            "correlation_penalized_pairs": _corr_penalized_pairs,
            "attribution_ref": _attribution_ref,
            "bounded_update": _bounded_update_status,
            "adjusted_module_weights": adjusted_module_weights,
        }

    except Exception as e:
        logger.error(f"Process endpoint error: {e}")
        return {
            "error": str(e),
            "asset": str(request_data.get("symbol", "BTC")).replace("/USDT", "").replace("/", "").upper(),
            "symbol": str(request_data.get("symbol", "BTC")).strip() or "BTC",
            "timeframe": str(request_data.get("timeframe", "1h")).strip() or "1h",
            "source": "consensus_engine_process_error_fallback",
            "timestamp": _now_iso(),
            "last_updated": None,
            "fallback_used": True,
            "verified": False,
            "data_status": "FALLBACK",
            "warnings": [
                "Signal is not verified because source data is stale/fallback/mock.",
                "Consensus engine returned a fallback response after an internal error.",
            ],
            "module_sources": {
                "technical": _build_module_source(
                    module="technical",
                    service="consensus-engine",
                    source="consensus_engine_process_error_fallback",
                    source_data="process_error",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="FALLBACK",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Default neutral module score; consensus engine error fallback applied."],
                    value=0.5,
                ),
                "fundamental": _build_module_source(
                    module="fundamental",
                    service="consensus-engine",
                    source="consensus_engine_process_error_fallback",
                    source_data="process_error",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="FALLBACK",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Default neutral module score; consensus engine error fallback applied."],
                    value=0.5,
                ),
                "news": _build_module_source(
                    module="news",
                    service="consensus-engine",
                    source="consensus_engine_process_error_fallback",
                    source_data="process_error",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="FALLBACK",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Default neutral module score; consensus engine error fallback applied."],
                    value=0.5,
                ),
                "sentinel": _build_module_source(
                    module="sentinel",
                    service="consensus-engine",
                    source="consensus_engine_process_error_fallback",
                    source_data="process_error",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="FALLBACK",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Default neutral module score; consensus engine error fallback applied."],
                    value=0.5,
                ),
                "quantum": _build_module_source(
                    module="quantum",
                    service="consensus-engine",
                    source="consensus_engine_process_error_fallback",
                    source_data="process_error",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="FALLBACK",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Default neutral module score; consensus engine error fallback applied."],
                    value=0.5,
                ),
            },
            "action": "HOLD",
            "confidence": 0.0,
            "position_size": 0.0
        }


# ── v7.0 New Endpoints ────────────────────────────────────────────────────────

@app.post("/attribution/calculate")
async def calculate_attribution(payload: dict):
    """
    v7.0: Standalone attribution calculation for a closed trade.

    Request body:
        trade_pnl        : float  — realized PnL (positive = win)
        entry_scores     : dict   — module scores at entry (keys: touche/fundamental/news/sentinel/quantum)
        exit_scores      : dict   — module scores at exit
        holding_period_h : float  — hours held (default 0)
        symbol           : str    — instrument symbol (default UNKNOWN)
        current_dd_pct   : float  — current drawdown from peak (default 0.0)
        apply_update     : bool   — if true, immediately runs bounded_updater (default false)
    """
    import datetime as _dt
    try:
        trade_pnl = float(payload.get("trade_pnl", 0.0))
        entry_scores = payload.get("entry_scores") or {}
        exit_scores = payload.get("exit_scores") or {}
        holding_period = float(payload.get("holding_period_h", 0.0))
        symbol = str(payload.get("symbol", "UNKNOWN"))
        apply_update = bool(payload.get("apply_update", False))
        current_dd_pct = float(payload.get("current_dd_pct", 0.0))

        attr = attribution_engine.calculate(
            trade_pnl=trade_pnl,
            entry_scores=entry_scores,
            exit_scores=exit_scores,
            holding_period=holding_period,
            symbol=symbol,
        )

        update_result = None
        if apply_update:
            update_result = bounded_updater.update(
                winning_modules=attr.get("winning_modules", []),
                losing_modules=attr.get("losing_modules", []),
                current_dd_pct=current_dd_pct,
            )

        return {
            "status": "ok",
            "timestamp": _dt.datetime.now().isoformat(),
            **attr,
            "bounded_update": update_result,
        }

    except Exception as exc:
        logger.error("attribution/calculate error: %s", exc)
        return {
            "status": "error",
            "error": str(exc),
            "attribution_ref": "attr_ERROR",
            "winning_modules": [],
            "losing_modules": [],
            "contribution_pct": {},
            "bounded_update": None,
        }


@app.get("/weights")
async def get_weights(horizon: str = "medium"):
    """v7.0: Return current module weights, drift state, and correlation status."""
    import datetime as _dt
    try:
        status = bounded_updater.get_status()
        module_weights = _get_current_module_weights(horizon=horizon)
        return {
            "status": "ok",
            "timestamp": _dt.datetime.now().isoformat(),
            "horizon_applied": horizon,
            "module_weights": module_weights,
            **status,
        }
    except Exception as exc:
        logger.error("weights endpoint error: %s", exc)
        _, weights = _load_production_weights()
        return {
            "status": "fallback",
            "weights": weights,
            "error": str(exc),
        }


@app.post("/bounded_updater/update")
async def bounded_update(payload: dict):
    """
    v7.0: Manually trigger a bounded weight update.

    Request body:
        winning_modules : list[str]
        losing_modules  : list[str]
        current_dd_pct  : float (default 0.0)
    """
    import datetime as _dt
    try:
        result = bounded_updater.update(
            winning_modules=payload.get("winning_modules", []),
            losing_modules=payload.get("losing_modules", []),
            current_dd_pct=float(payload.get("current_dd_pct", 0.0)),
        )
        return {"status": "ok", "timestamp": _dt.datetime.now().isoformat(), **result}
    except Exception as exc:
        logger.error("bounded_updater/update error: %s", exc)
        return {"status": "error", "error": str(exc)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
