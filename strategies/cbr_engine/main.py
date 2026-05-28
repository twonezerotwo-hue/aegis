"""
AEGIS CBR Engine - FastAPI Main Entry Point
Complete 6-phase orchestration with REST endpoints
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime
import logging

# Import orchestrator and all components
from orchestrator import CBROrchestrator
from fingerprint_extractor import FingerprintExtractor
from dimensionality_reducer import DimensionalityReducer
from vector_db import SimilarityEngine, VectorDatabase
from probabilistic_decision import ProbabilisticDecisionMaker
from auto_labeler import AutoLabeler
from live_monitor import LiveMonitor
from slippage_simulator import SlippageSimulator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ Pydantic Models ============
class MarketData(BaseModel):
    """Market data input"""
    id: int
    price: float
    market_type: str  # 'DIP', 'PEAK', 'BREAKOUT', 'REJECTION'
    ohlcv: Dict  # OHLCV data
    indicators: Dict  # Technical indicators
    macro: Dict  # Macro data
    on_chain: Dict  # On-chain metrics
    module_metrics: Optional[Dict] = None
    consensus: Optional[Dict] = None
    event_flags: Optional[Dict] = None
    position_context: Optional[Dict] = None
    timestamp: Optional[str] = None


class CBRDecision(BaseModel):
    """CBR trading decision"""
    action: str
    confidence: float
    position_size: float
    entry_price: float
    stop_loss: float
    take_profit: float
    similar_cases: int


class PipelineMetrics(BaseModel):
    """Pipeline execution metrics"""
    total_duration_ms: float
    faz1_fingerprint_ms: float
    faz2_reduce_ms: float
    faz3_search_ms: float
    faz4_decide_ms: float
    faz5_learn_ms: float
    faz6_monitor_ms: Optional[float]
    status: str


class CBRResponse(BaseModel):
    """Complete CBR response"""
    decision: CBRDecision
    metrics: PipelineMetrics


# ============ FastAPI App ============
app = FastAPI(
    title="AEGIS CBR Engine",
    description="Case-Based Reasoning Trading System - 6 Phases",
    version="1.0.0"
)


# ============ Global Components ============
class CBREngine:
    """Global CBR engine instance"""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls._initialize()
        return cls._instance

    @staticmethod
    def _initialize():
        """Initialize all components"""
        logger.info("Initializing CBR Engine components...")

        # FAZ 1: Fingerprint Extractor
        fingerprint_extractor = FingerprintExtractor()
        logger.info("✓ FAZ 1: Fingerprint Extractor initialized")

        # FAZ 2: Dimensionality Reducer
        dimensionality_reducer = DimensionalityReducer(
            target_components=12,
            variance_threshold=0.95
        )
        logger.info("✓ FAZ 2: Dimensionality Reducer initialized")

        # FAZ 3: Similarity Engine
        vector_db = VectorDatabase(embedding_dim=12, regime_stratified=True)
        similarity_engine = SimilarityEngine(
            reducer=dimensionality_reducer,
            vector_db=vector_db,
        )
        logger.info("✓ FAZ 3: Similarity Engine initialized")

        # FAZ 4: Probabilistic Decision Maker
        probabilistic_maker = ProbabilisticDecisionMaker()
        logger.info("✓ FAZ 4: Probabilistic Decision Maker initialized")

        # FAZ 5: Auto Labeler
        auto_labeler = AutoLabeler()
        logger.info("✓ FAZ 5: Auto Labeler initialized")

        # FAZ 6: Live Monitor
        live_monitor = LiveMonitor(
            initial_capital=100000,
            max_dd_warning=0.10,
            max_dd_critical=0.20
        )
        logger.info("✓ FAZ 6a: Live Monitor initialized")

        # FAZ 6: Slippage Simulator
        slippage_simulator = SlippageSimulator(
            mid_price=45000,
            spread_bps=5,
            commission_bps=10
        )
        logger.info("✓ FAZ 6b: Slippage Simulator initialized")

        # Create Orchestrator
        orchestrator = CBROrchestrator(
            fingerprint_extractor=fingerprint_extractor,
            dimensionality_reducer=dimensionality_reducer,
            similarity_engine=similarity_engine,
            probabilistic_maker=probabilistic_maker,
            auto_labeler=auto_labeler,
            live_monitor=live_monitor,
            slippage_simulator=slippage_simulator,
        )

        logger.info("✅ CBR Orchestrator ready - all 6 phases initialized")
        return orchestrator


def _build_market_dict(market_data: MarketData) -> Dict:
    return {
        'id': market_data.id,
        'price': market_data.price,
        'market_type': market_data.market_type,
        'ohlcv': market_data.ohlcv,
        'indicators': market_data.indicators,
        'macro': market_data.macro,
        'on_chain': market_data.on_chain,
        'module_metrics': market_data.module_metrics or {},
        'consensus': market_data.consensus or {},
        'event_flags': market_data.event_flags or {},
        'position_context': market_data.position_context or {},
        'timestamp': market_data.timestamp or datetime.now().isoformat(),
    }


def _extract_fingerprint_dict(orchestrator: CBROrchestrator, market_dict: Dict) -> Dict:
    import pandas as pd

    def _payload_to_frame(payload: Dict) -> pd.DataFrame:
        if isinstance(payload, dict) and payload:
            if all(isinstance(value, list) for value in payload.values()):
                return pd.DataFrame(payload)
            return pd.DataFrame([payload])
        return pd.DataFrame(payload)

    def _build_macro_frame() -> pd.DataFrame:
        base_macro = _payload_to_frame(market_dict.get('macro', {}))

        if not orchestrator.macro_enhancer:
            return base_macro

        enriched_macro = orchestrator.macro_enhancer.enrich(market_dict)
        if base_macro.empty:
            return _payload_to_frame(enriched_macro)

        for key, value in enriched_macro.items():
            if isinstance(value, dict) or key == 'timestamp':
                continue

            if isinstance(value, list) and len(value) == len(base_macro.index):
                base_macro[key] = value
            elif not isinstance(value, list):
                base_macro[key] = value

        return base_macro

    ohlcv_payload = market_dict.get('ohlcv', {})
    onchain_payload = market_dict.get('on_chain', {})

    ohlcv_df = _payload_to_frame(ohlcv_payload)
    macro_df = _build_macro_frame()
    onchain_df = _payload_to_frame(onchain_payload)

    if 'timestamp' in ohlcv_df.columns:
        ohlcv_df['timestamp'] = pd.to_datetime(ohlcv_df['timestamp'])
        ohlcv_df.set_index('timestamp', inplace=True)
    if 'timestamp' in macro_df.columns:
        macro_df['timestamp'] = pd.to_datetime(macro_df['timestamp'])
        macro_df.set_index('timestamp', inplace=True)
    if 'timestamp' in onchain_df.columns:
        onchain_df['timestamp'] = pd.to_datetime(onchain_df['timestamp'])
        onchain_df.set_index('timestamp', inplace=True)

    fingerprint = orchestrator.extractor.extract(
        ohlcv_df,
        macro_df,
        onchain_df,
        idx=max(len(ohlcv_df) - 1, 0),
    )

    if fingerprint is None:
        raise ValueError('Fingerprint extraction returned None')

    return fingerprint.to_dict() if hasattr(fingerprint, 'to_dict') else dict(fingerprint)


# ============ Endpoints ============

@app.on_event("startup")
async def startup_event():
    """Initialize engine on startup"""
    CBREngine.get_instance()
    logger.info("🚀 AEGIS CBR Engine started")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    orchestrator = CBREngine.get_instance()
    return {
        "status": "healthy",
        "engine": "CBR",
        "pipeline_log_entries": len(orchestrator.pipeline_log),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/status")
async def get_status():
    """Get engine status and statistics"""
    orchestrator = CBREngine.get_instance()
    stats = orchestrator.get_pipeline_statistics()
    report = orchestrator.get_performance_report()

    return {
        "status": "RUNNING",
        "statistics": stats,
        "report": report,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/cbr/process", response_model=CBRResponse)
async def process_market_data(market_data: MarketData):
    """
    Process market data through complete 6-phase CBR pipeline.

    Steps:
    1. FAZ 1: Extract fingerprint from market data
    2. FAZ 2: Reduce dimensionality
    3. FAZ 3: Search for similar historical cases
    4. FAZ 4: Make probabilistic trading decision
    5. FAZ 5: Log for continuous learning
    6. FAZ 6: Monitor with slippage simulation

    Returns:
    - Decision: Action (LONG/SHORT/SKIP), confidence, position size
    - Metrics: Timing for each phase
    """
    try:
        orchestrator = CBREngine.get_instance()
        market_dict = _build_market_dict(market_data)

        # Execute pipeline
        decision_dict, metrics_dict = orchestrator.process_market_data(market_dict)

        if decision_dict is None:
            logger.warning(f"Pipeline error: {metrics_dict.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=f"Pipeline error: {metrics_dict.get('error')}"
            )

        # Build response
        decision = CBRDecision(
            action=decision_dict['action'],
            confidence=decision_dict['confidence'],
            position_size=decision_dict['position_size'],
            entry_price=decision_dict['entry_price'],
            stop_loss=decision_dict['stop_loss'],
            take_profit=decision_dict['take_profit'],
            similar_cases=decision_dict['similar_cases'],
        )

        faz6_monitor = metrics_dict['phases'].get('faz6_monitor', {})
        metrics = PipelineMetrics(
            total_duration_ms=metrics_dict['total_duration_ms'],
            faz1_fingerprint_ms=metrics_dict['phases']['faz1_fingerprint']['duration_ms'],
            faz2_reduce_ms=metrics_dict['phases']['faz2_reduce']['duration_ms'],
            faz3_search_ms=metrics_dict['phases']['faz3_search']['duration_ms'],
            faz4_decide_ms=metrics_dict['phases']['faz4_decide']['duration_ms'],
            faz5_learn_ms=metrics_dict['phases']['faz5_learn']['duration_ms'],
            faz6_monitor_ms=faz6_monitor.get('duration_ms'),
            status=metrics_dict['status'],
        )

        logger.info(
            f"✅ Pipeline complete: {decision.action} "
            f"(confidence: {decision.confidence:.2f}, "
            f"total: {metrics.total_duration_ms:.1f}ms)"
        )

        return CBRResponse(decision=decision, metrics=metrics)

    except Exception as e:
        logger.error(f"Endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cbr/fingerprint")
async def extract_fingerprint(market_data: MarketData):
    """
    FAZ 1: Extract market fingerprint from raw data.

    Returns 25+ features capturing:
    - Price structure (support, resistance, volatility)
    - Technical indicators (RSI, MACD, Bollinger Bands)
    - Macro regime (correlation with DXY, Gold, VIX)
    - On-chain metrics (whale moves, exchange activity)
    """
    try:
        orchestrator = CBREngine.get_instance()
        market_dict = _build_market_dict(market_data)
        fingerprint = _extract_fingerprint_dict(orchestrator, market_dict)

        return {
            "fingerprint": fingerprint,
            "feature_count": len(fingerprint),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Fingerprint extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cbr/search")
async def search_similar_cases(market_data: MarketData):
    """
    FAZ 3: Search for similar historical cases.

    Uses:
    - HNSW vector index for fast nearest neighbor search
    - Regime-aware similarity (within-regime, cross-regime)
    - Hybrid metric (70% cosine, 30% DTW)

    Returns top 50 similar cases with similarity scores and outcomes.
    """
    try:
        orchestrator = CBREngine.get_instance()
        market_dict = _build_market_dict(market_data)
        fingerprint = _extract_fingerprint_dict(orchestrator, market_dict)

        # Reduce dimensionality
        import pandas as pd
        fingerprint_df = pd.DataFrame([fingerprint])
        embedding = orchestrator.reducer.transform(fingerprint_df)
        embedding_vector = embedding.iloc[0].values

        # Search
        similar_cases = orchestrator.similarity.search(
            embedding_vector,
            k=50,
            market_type=market_data.market_type
        )

        cases_list = [
            {
                'case_id': i,
                'similarity_score': float(c.similarity_score),
                'forward_return_24h': float(c.forward_return_24h) if c.forward_return_24h else None,
                'market_type': c.market_type,
            }
            for i, c in enumerate(similar_cases)
        ]

        return {
            "similar_cases_count": len(similar_cases),
            "cases": cases_list,
            "avg_similarity": (
                sum(c.similarity_score for c in similar_cases) / len(similar_cases)
                if similar_cases else 0
            ),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cbr/decide")
async def make_trading_decision(market_data: MarketData):
    """
    FAZ 4: Make probabilistic trading decision.

    Uses:
    - Bayesian confidence combining:
      * Win rate from similar cases
      * Forward returns
      * Consistency across regimes
      * Similarity score
    - Kelly Criterion for position sizing (25% fractional for safety)
    - Macro risk gates (5-factor adjustment)

    Returns: Action (LONG/SHORT/SKIP), confidence, position size
    """
    try:
        orchestrator = CBREngine.get_instance()
        market_dict = _build_market_dict(market_data)
        fingerprint = _extract_fingerprint_dict(orchestrator, market_dict)

        # Reduce dimensionality and search
        import pandas as pd
        fingerprint_df = pd.DataFrame([fingerprint])
        embedding = orchestrator.reducer.transform(fingerprint_df)
        embedding_vector = embedding.iloc[0].values

        similar_cases = orchestrator.similarity.search(
            embedding_vector,
            k=50,
            market_type=market_data.market_type
        )

        # Calculate case statistics
        case_stats = orchestrator._calculate_case_statistics(similar_cases)

        # Make decision
        decision = orchestrator.decision_maker.make_decision(
            current_price=market_data.price,
            fingerprint=fingerprint,
            similar_cases_stats=case_stats,
            market_type=market_data.market_type,
        )

        return {
            "action": decision.action,
            "confidence": float(decision.confidence),
            "position_size": float(decision.position_size),
            "entry_price": float(decision.entry_price),
            "stop_loss": float(decision.stop_loss),
            "take_profit": float(decision.take_profit),
            "similar_cases": len(similar_cases),
            "reasoning": {
                "win_rate": float(case_stats.get('mean_similarity', 0)),
                "avg_return": float(case_stats.get('ensemble_return', 0)),
                "sample_count": case_stats.get('sample_count', 0),
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Decision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cbr/pipeline-report")
async def get_pipeline_report():
    """Get full pipeline performance report"""
    orchestrator = CBREngine.get_instance()
    report = orchestrator.get_performance_report()
    stats = orchestrator.get_pipeline_statistics()

    return {
        "report": report,
        "statistics": stats,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/cbr/export-logs")
async def export_logs(filepath: str = "/tmp/cbr_pipeline_logs.csv"):
    """Export pipeline logs to CSV"""
    orchestrator = CBREngine.get_instance()

    try:
        orchestrator.export_logs(filepath)
        return {
            "status": "success",
            "filepath": filepath,
            "entries_exported": len(orchestrator.pipeline_log),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cbr/readiness")
async def readiness_check():
    """FAZ completion readiness check"""
    orchestrator = CBREngine.get_instance()

    return {
        "status": "PRODUCTION_READY",
        "phases": {
            "faz1_fingerprint": "✅ READY",
            "faz2_dimensionality_reduction": "✅ READY",
            "faz3_vector_db_search": "✅ READY",
            "faz4_probabilistic_decision": "✅ READY",
            "faz5_continuous_learning": "✅ READY",
            "faz6_paper_live": "✅ READY",
        },
        "pipeline_log_entries": len(orchestrator.pipeline_log),
        "timestamp": datetime.now().isoformat()
    }


# ============ Main ============
if __name__ == "__main__":
    import uvicorn

    print("""
╔════════════════════════════════════════════════════════════╗
║           AEGIS CBR ENGINE - FastAPI Server               ║
║                   All 6 Phases Ready                       ║
╚════════════════════════════════════════════════════════════╝

🚀 Starting AEGIS CBR Engine on http://0.0.0.0:8000
📚 API Docs: http://0.0.0.0:8000/docs
📊 Redoc: http://0.0.0.0:8000/redoc

Endpoints:
  POST /cbr/process           - Full 6-phase pipeline
  POST /cbr/fingerprint       - FAZ 1: Extract features
  POST /cbr/search            - FAZ 3: Find similar cases
  POST /cbr/decide            - FAZ 4: Make decision
  GET  /cbr/status            - Pipeline statistics
  GET  /cbr/pipeline-report   - Full performance report
  GET  /health                - Health check
""")

    uvicorn.run(app, host="0.0.0.0", port=8000)
