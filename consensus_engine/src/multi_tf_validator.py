"""Multi-timeframe validator for consensus layer-3 checks."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class MultiTFValidationResult:
    is_valid: bool
    final_signal: str
    reason: str
    holding_period_hours: int


class MultiTFValidator:
    """
    Timeframe roles:
    - 15m: entry optimization
    - 1h: main decision layer
    - 4h: trend filter
    - 1D: holding period
    """

    @staticmethod
    def _to_dir(signal: str) -> str:
        s = (signal or "HOLD").upper()
        if s in {"BUY", "AL", "BULLISH", "LONG"}:
            return "BUY"
        if s in {"SELL", "SAT", "BEARISH", "SHORT"}:
            return "SELL"
        return "HOLD"

    def validate(self, tf_signals: Dict[str, str]) -> MultiTFValidationResult:
        signal_15m = self._to_dir(tf_signals.get("15m", "HOLD"))
        signal_1h = self._to_dir(tf_signals.get("1h", "HOLD"))
        signal_4h = self._to_dir(tf_signals.get("4h", "HOLD"))
        signal_1d = self._to_dir(tf_signals.get("1d", "HOLD"))

        # Critical rule: 1h and 4h opposite -> HOLD
        opposite = (signal_1h == "BUY" and signal_4h == "SELL") or (signal_1h == "SELL" and signal_4h == "BUY")
        if opposite:
            return MultiTFValidationResult(
                is_valid=False,
                final_signal="HOLD",
                reason="1h and 4h signals are opposite",
                holding_period_hours=0,
            )

        # 1D decides holding horizon
        holding_period = 24 if signal_1d in {"BUY", "SELL"} else 6

        # 15m can only refine entry timing, never override the core 1h/4h stack.
        final_signal = signal_1h

        if final_signal == "HOLD":
            return MultiTFValidationResult(
                is_valid=False,
                final_signal="HOLD",
                reason="1h is neutral; 15m reserved for entry optimization only",
                holding_period_hours=0,
            )

        if signal_4h == "HOLD":
            return MultiTFValidationResult(
                is_valid=False,
                final_signal="HOLD",
                reason="4h trend filter is neutral",
                holding_period_hours=0,
            )

        if signal_15m not in {"HOLD", final_signal}:
            return MultiTFValidationResult(
                is_valid=True,
                final_signal=final_signal,
                reason="validated; 15m disagrees so use only for entry timing",
                holding_period_hours=holding_period,
            )

        return MultiTFValidationResult(
            is_valid=True,
            final_signal=final_signal,
            reason="validated",
            holding_period_hours=holding_period,
        )
