"""AEGIS API integration layer."""

from .client import get_cbr_decision, get_consensus
from .validator import validate_signal

__all__ = ["get_cbr_decision", "get_consensus", "validate_signal"]
