"""
AEGIS Holding — Consensus Engine

Touche AI ve Fundamental AI sinyallerini birleştirerek
nihai investment kararı üretir.
"""
from .orchestrator import ConsensusOrchestrator
from .src.models import (
    ConsensusConfig,
    ToucheSignal,
    FundamentalSignal,
    ConsensusDecision,
    RiskMetrics,
)

__version__ = "1.0.0"
__all__ = [
    "ConsensusOrchestrator",
    "ConsensusConfig",
    "ToucheSignal",
    "FundamentalSignal",
    "ConsensusDecision",
    "RiskMetrics",
]
