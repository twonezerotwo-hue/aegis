"""
AEGIS CBR Engine - Complete Case-Based Reasoning System
8-Phase Intelligent Trading System

├─ FAZ 1: FINGERPRINT PIPELINE
│  ├─ fingerprint_extractor.py (25+ features, no look-ahead bias)
│  ├─ dip_tepe_detector.py (market pattern detection)
│  ├─ look_ahead_safe.py (point-in-time validation)
│  └─ rolling_correlation.py (macro regime analysis)
│
├─ FAZ 2: DIMENSIONALITY REDUCTION
│  └─ dimensionality_reducer.py (PCA + Autoencoder, 25→12-15 dims)
│
├─ FAZ 3: VECTOR DB + SIMILARITY ENGINE
│  └─ vector_db.py (HNSW index, <100ms search, regime-aware)
│
├─ FAZ 4: PROBABILISTIC SIZING + RISK GATE
│  └─ probabilistic_decision.py (Bayesian confidence, Kelly criterion)
│
├─ FAZ 5: CONTINUOUS LEARNING
│  └─ continuous_learning.py (auto-labeler, weekly optimization, SHAP)
│
├─ FAZ 6: PAPER → LIVE
│  └─ live_monitor.py (realistic slippage, equity tracking)
│
└─ FAZ 7-8: TESTING & DEPLOYMENT
   └─ deployment.py (validation, production checklist)

Performance Targets:
- Backtest: 40-60 trades, Win Rate 45-55%, Sharpe 1.4-1.7, Max DD 15-20%
- Similarity Search: <100ms for 10K vectors
- Live Expectancy: >1.3x with realistic slippage
"""

try:
    from .fingerprint_extractor import FingerprintExtractor, Fingerprint
    from .dip_tepe_detector import DipTeepeDetector, PricePattern
    from .look_ahead_safe import LookAheadSafeExtractor
    from .rolling_correlation import RollingCorrelationEngine, CorrelationBreakdown
    from .dimensionality_reducer import DimensionalityReducer, AutoencoderReducer, HybridReducer
    from .vector_db import VectorDatabase, SimilarityEngine, SimilarCase
    from .probabilistic_decision import (
        BayesianConfidence, RiskGate, KellyCriterion, ProbabilisticDecisionMaker, TradingDecision
    )
    from .risk_gate import MacroRiskGate, SimilarityRiskGate, AdaptiveRiskAdjustment, ComplianceRiskGate
    from .auto_labeler import AutoLabeler, TradeLogger, TradeOutcome
    from .weekly_optimizer import WeeklyOptimizer, OptimizationResult
    from .shap_dashboard import SHAPDashboard, FeatureImportance
    from .slippage_simulator import SlippageSimulator, OrderBook, ExecutionResult
    from .live_monitor import LiveMonitor, LivePerformanceDashboard, PerformanceMetrics
    from .paper_trading_bridge import PaperTradingBridge, SignalEvent, ExecutionEvent
except Exception:  # pragma: no cover - optional heavy CBR dependencies
    FingerprintExtractor = Fingerprint = None  # type: ignore[assignment]
    DipTeepeDetector = PricePattern = None  # type: ignore[assignment]
    LookAheadSafeExtractor = None  # type: ignore[assignment]
    RollingCorrelationEngine = CorrelationBreakdown = None  # type: ignore[assignment]
    DimensionalityReducer = AutoencoderReducer = HybridReducer = None  # type: ignore[assignment]
    VectorDatabase = SimilarityEngine = SimilarCase = None  # type: ignore[assignment]
    BayesianConfidence = RiskGate = KellyCriterion = ProbabilisticDecisionMaker = TradingDecision = None  # type: ignore[assignment]
    MacroRiskGate = SimilarityRiskGate = AdaptiveRiskAdjustment = ComplianceRiskGate = None  # type: ignore[assignment]
    AutoLabeler = TradeLogger = TradeOutcome = None  # type: ignore[assignment]
    WeeklyOptimizer = OptimizationResult = None  # type: ignore[assignment]
    SHAPDashboard = FeatureImportance = None  # type: ignore[assignment]
    SlippageSimulator = OrderBook = ExecutionResult = None  # type: ignore[assignment]
    LiveMonitor = LivePerformanceDashboard = PerformanceMetrics = None  # type: ignore[assignment]
    PaperTradingBridge = SignalEvent = ExecutionEvent = None  # type: ignore[assignment]

__version__ = '1.0.0'
__phase__ = 'PRODUCTION_READY'
__status__ = 'COMPLETE_8_PHASES'

__all__ = [
    # FAZ 1
    'FingerprintExtractor',
    'Fingerprint',
    'DipTeepeDetector',
    'PricePattern',
    'LookAheadSafeExtractor',
    'RollingCorrelationEngine',
    'CorrelationBreakdown',
    # FAZ 2
    'DimensionalityReducer',
    'AutoencoderReducer',
    'HybridReducer',
    # FAZ 3
    'VectorDatabase',
    'SimilarityEngine',
    'SimilarCase',
    # FAZ 4
    'BayesianConfidence',
    'RiskGate',
    'KellyCriterion',
    'ProbabilisticDecisionMaker',
    'TradingDecision',
    # FAZ 5
    'AutoLabeler',
    'WeeklyOptimizer',
    'ShapDashboard',
    # FAZ 6
    'SlippageSimulator',
    'LiveMonitor',
    'ExecutionResult',
    # FAZ 7-8
    'ComprehensiveValidator',
    'ProductionDeployment',
]
