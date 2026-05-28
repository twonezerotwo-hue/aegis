"""Risk wrappers for safe AEGIS Core integration surfaces."""

from .kill_switch import evaluate_kill_switch
from .risk_engine import evaluate_signal_risk

__all__ = ["evaluate_kill_switch", "evaluate_signal_risk"]
