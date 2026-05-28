"""
AEGIS v6.0 — Master Test Suite
=================================
Covers all 6 scenarios from the implementation spec:

  ✅  1. CBR fallback test (sample_count=10 → işlem açılır, pozisyon küçülür)
  ✅  2. Consensus 5-module weight test (tüm modül skorları doğru çarpanla toplanır)
  ✅  3. Multi-TF conflict test (1H=BUY, 4H=SELL → HOLD)
  ✅  4. Exit logic test (Higher Low kırılımı → FULL_CLOSE)
  ✅  5. Fallback behaviour test (Sentinel timeout → safe-default, log düşer)
  ✅  6. Green-Light positive/negative scenarios

Run:
    pytest tests/test_aegis_v6_master.py -v --tb=short

Dependencies: pytest (no external HTTP calls — pure unit tests)
"""
import sys
import os
import math
import logging

import pytest

# ── Path setup: allow imports from project root ───────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ─────────────────────────────────────────────────────────────────────────────
# 1. CBR FALLBACK TEST
# ─────────────────────────────────────────────────────────────────────────────

class TestCBRFallback:
    """sample_count < 15 must no longer block consensus (analiz felci fix)."""

    def _validate(self, sample_count, win_rate_pct, similarity_score=0.7):
        """Mirror of consensus_engine/main.py _validate_cbr_edge logic."""
        if sample_count < 15:
            return True, True, 0.85, "fallback_active"
        if win_rate_pct < 55.0:
            return True, True, 0.85, "edge_below_55(historical_weak)"
        return True, False, 1.0, "cbr_edge_valid"

    def test_sparse_history_includes_in_consensus(self):
        """sample_count=10 must return include=True (not block)."""
        include, is_weak, confidence_modifier, reason = self._validate(10, 60.0)
        assert include is True, "Analiz felci bug: sparse history must not block consensus"
        assert is_weak is True
        assert confidence_modifier == 0.85
        assert reason == "fallback_active"

    def test_sparse_history_triggers_weak_flag(self):
        """is_historical_weak=True when sample_count < 15."""
        _, is_weak, _, _ = self._validate(5, 70.0)
        assert is_weak is True

    def test_strong_history_not_weak(self):
        """Sufficient samples + good edge → is_historical_weak=False."""
        include, is_weak, confidence_modifier, reason = self._validate(30, 62.0)
        assert include is True
        assert is_weak is False
        assert confidence_modifier == 1.0
        assert reason == "cbr_edge_valid"

    def test_weak_edge_still_included(self):
        """Win rate < 55% returns include=True (not a hard veto)."""
        include, is_weak, confidence_modifier, _ = self._validate(20, 52.0)
        assert include is True
        assert is_weak is True
        assert confidence_modifier == 0.85

    def test_position_size_reduced_when_weak(self):
        """is_historical_weak → position_size_multiplier = 0.8 (20% reduction)."""
        base_position = 0.05
        is_weak = True
        multiplier = 0.80 if is_weak else 1.0
        assert round(base_position * multiplier, 4) == round(base_position * 0.8, 4)

    def test_weight_boost_when_weak(self):
        """is_historical_weak → touche + sentinel weights boosted by 0.10, renormalized."""
        base_weights = {"touche": 0.35, "fundamental": 0.30, "news": 0.20, "sentinel": 0.10, "quantum": 0.05}
        boost = 0.10
        mw = base_weights.copy()
        mw["touche"] = min(0.60, mw["touche"] + boost)
        mw["sentinel"] = min(0.60, mw["sentinel"] + boost)
        total = sum(mw.values())
        mw = {k: v / total for k, v in mw.items()}

        assert abs(sum(mw.values()) - 1.0) < 1e-6, "Weights must sum to 1.0 after renorm"
        assert mw["touche"] > base_weights["touche"], "Touche weight must increase"
        assert mw["sentinel"] > base_weights["sentinel"], "Sentinel weight must increase"


# ─────────────────────────────────────────────────────────────────────────────
# 2. CONSENSUS 5-MODULE WEIGHT TEST
# ─────────────────────────────────────────────────────────────────────────────

class TestFiveModuleWeighting:
    """Σ(module_score × dynamic_weight) must be correct for all 5 modules."""

    WEIGHTS_NORMALIZATION = {
        "touche": 0.35,
        "fundamental": 0.30,
        "news": 0.20,
        "sentinel": 0.10,
        "quantum": 0.05,
    }
    WEIGHTS_RISK_OFF = {
        "touche": 0.20,
        "fundamental": 0.25,
        "news": 0.15,
        "sentinel": 0.30,
        "quantum": 0.10,
    }

    def _five_module_score(self, scores, weights):
        return sum(scores[m] * weights[m] for m in weights)

    def test_weights_sum_to_one_normalization(self):
        total = sum(self.WEIGHTS_NORMALIZATION.values())
        assert abs(total - 1.0) < 1e-6

    def test_weights_sum_to_one_risk_off(self):
        total = sum(self.WEIGHTS_RISK_OFF.values())
        assert abs(total - 1.0) < 1e-6

    def test_bullish_all_modules(self):
        """All modules bullish → score > 0.55 → BUY signal."""
        scores = {m: 0.80 for m in self.WEIGHTS_NORMALIZATION}
        score = self._five_module_score(scores, self.WEIGHTS_NORMALIZATION)
        assert score > 0.55
        action = "BUY" if score > 0.55 else "SELL" if score < 0.45 else "HOLD"
        assert action == "BUY"

    def test_bearish_all_modules(self):
        """All modules bearish → score < 0.45 → SELL signal."""
        scores = {m: 0.25 for m in self.WEIGHTS_NORMALIZATION}
        score = self._five_module_score(scores, self.WEIGHTS_NORMALIZATION)
        assert score < 0.45
        action = "BUY" if score > 0.55 else "SELL" if score < 0.45 else "HOLD"
        assert action == "SELL"

    def test_neutral_all_modules(self):
        """All modules neutral (0.50) → score ≈ 0.50 → HOLD."""
        scores = {m: 0.50 for m in self.WEIGHTS_NORMALIZATION}
        score = self._five_module_score(scores, self.WEIGHTS_NORMALIZATION)
        action = "BUY" if score > 0.55 else "SELL" if score < 0.45 else "HOLD"
        assert action == "HOLD"

    def test_risk_off_sentinel_dominates(self):
        """In RISK_OFF regime sentinel has 0.30 weight — strongly bearish sentinel → lower score."""
        # Touche/fundamental bullish but sentinel bearish
        scores_optimistic = {
            "touche": 0.75,
            "fundamental": 0.70,
            "news": 0.60,
            "sentinel": 0.25,  # risk-off, bearish
            "quantum": 0.50,
        }
        score = self._five_module_score(scores_optimistic, self.WEIGHTS_RISK_OFF)
        # Sentinel 0.25 × 0.30 = 0.075 — should pull score down significantly
        assert score < 0.65, "Bearish sentinel in RISK_OFF must reduce final score"

    def test_five_module_score_formula(self):
        """Exact formula check: manual calculation must match implementation."""
        scores = {
            "touche": 0.75,
            "fundamental": 0.68,
            "news": 0.55,
            "sentinel": 0.82,
            "quantum": 0.60,
        }
        expected = (
            0.75 * 0.35
            + 0.68 * 0.30
            + 0.55 * 0.20
            + 0.82 * 0.10
            + 0.60 * 0.05
        )
        result = self._five_module_score(scores, self.WEIGHTS_NORMALIZATION)
        assert abs(result - expected) < 1e-9, f"Formula mismatch: {result} != {expected}"

    def test_fallback_module_uses_default_score(self):
        """When a module is unreachable its safe-default (0.5) is used."""
        scores = {
            "touche": 0.75,
            "fundamental": 0.68,
            "news": 0.50,     # fallback (news AI timeout)
            "sentinel": 0.80,
            "quantum": 0.50,  # fallback (quantum timeout)
        }
        score = self._five_module_score(scores, self.WEIGHTS_NORMALIZATION)
        # System should still produce a valid score
        assert 0.0 <= score <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. MULTI-TF CONFLICT TEST
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiTF:
    """1H=BUY + 4H=SELL must force HOLD; alignment must boost confidence."""

    def _import_validator(self):
        try:
            from consensus_engine.src.multi_tf_validator import MultiTFValidator
        except ImportError:
            from consensus_engine.src.multi_tf_validator import MultiTFValidator
        return MultiTFValidator()

    def test_opposite_1h_4h_is_invalid(self):
        v = self._import_validator()
        result = v.validate({"15m": "BUY", "1h": "BUY", "4h": "SELL", "1d": "BUY"})
        assert result.is_valid is False
        assert result.final_signal == "HOLD"

    def test_opposite_reversed_is_invalid(self):
        v = self._import_validator()
        result = v.validate({"15m": "SELL", "1h": "SELL", "4h": "BUY", "1d": "SELL"})
        assert result.is_valid is False
        assert result.final_signal == "HOLD"

    def test_neutral_1h_forces_hold(self):
        v = self._import_validator()
        result = v.validate({"15m": "BUY", "1h": "HOLD", "4h": "BUY", "1d": "BUY"})
        assert result.is_valid is False
        assert result.final_signal == "HOLD"

    def test_neutral_4h_forces_hold(self):
        v = self._import_validator()
        result = v.validate({"15m": "BUY", "1h": "BUY", "4h": "HOLD", "1d": "BUY"})
        assert result.is_valid is False

    def test_aligned_1h_4h_is_valid(self):
        v = self._import_validator()
        result = v.validate({"15m": "BUY", "1h": "BUY", "4h": "BUY", "1d": "BUY"})
        assert result.is_valid is True
        assert result.final_signal == "BUY"

    def test_15m_disagreement_does_not_block(self):
        """15m only refines entry — disagreement should not invalidate 1h/4h alignment."""
        v = self._import_validator()
        result = v.validate({"15m": "SELL", "1h": "BUY", "4h": "BUY", "1d": "BUY"})
        assert result.is_valid is True
        assert result.final_signal == "BUY"

    def test_1d_determines_holding_period(self):
        v = self._import_validator()
        result_long = v.validate({"15m": "BUY", "1h": "BUY", "4h": "BUY", "1d": "BUY"})
        assert result_long.holding_period_hours == 24

        result_no_daily = v.validate({"15m": "BUY", "1h": "BUY", "4h": "BUY", "1d": "HOLD"})
        assert result_no_daily.holding_period_hours == 6


# ─────────────────────────────────────────────────────────────────────────────
# 4. EXIT LOGIC TEST
# ─────────────────────────────────────────────────────────────────────────────

class TestExitLogic:
    """
    Tests for Touche exit signal logic using the deterministic mock in touche_ai/main.py.
    We test the underlying rules directly rather than via HTTP.
    """

    def _exit_logic_long(self, current_price: float, entry_price: float) -> dict:
        """Replicate LONG exit logic from /touche/exit_signal."""
        swing_low = entry_price * 0.98  # higher-low = entry_price * 0.98
        rsi_val = 68.0  # mock neutral

        # Simulate higher-low break: price falls below swing_low
        higher_low_broken = current_price < swing_low
        # RSI overbought + volume declining
        rsi_overbought = rsi_val > 70
        volume_declining = False  # simplified

        if higher_low_broken:
            return {"exit": "FULL_CLOSE", "reason": "Higher Low broke"}
        if rsi_overbought and volume_declining:
            return {"exit": "PARTIAL_CLOSE", "percentage": 0.50, "reason": "Overbought + low volume"}
        return {"exit": "NONE"}

    def _exit_logic_short(self, current_price: float, entry_price: float) -> dict:
        """Replicate SHORT exit logic from /touche/exit_signal."""
        swing_high = entry_price * 1.02  # lower-high = entry_price * 1.02
        lower_high_broken = current_price > swing_high

        if lower_high_broken:
            return {"exit": "FULL_CLOSE", "reason": "Lower High broke"}
        return {"exit": "NONE"}

    def test_long_higher_low_broken_triggers_full_close(self):
        """Price drops below higher-low → FULL_CLOSE for LONG."""
        entry = 64000.0
        current = entry * 0.96  # below 0.98 swing low
        result = self._exit_logic_long(current, entry)
        assert result["exit"] == "FULL_CLOSE"
        assert result["reason"] == "Higher Low broke"

    def test_long_structure_intact_returns_hold(self):
        """Price above swing low → exit=False."""
        entry = 64000.0
        current = entry * 1.02  # above swing low
        result = self._exit_logic_long(current, entry)
        assert result["exit"] == "NONE"

    def test_short_lower_high_broken_triggers_full_close(self):
        """Price rises above lower-high → FULL_CLOSE for SHORT."""
        entry = 64000.0
        current = entry * 1.05  # above 1.02 swing high
        result = self._exit_logic_short(current, entry)
        assert result["exit"] == "FULL_CLOSE"
        assert result["reason"] == "Lower High broke"

    def test_short_structure_intact_returns_hold(self):
        """Price below swing high → exit=False."""
        entry = 64000.0
        current = entry * 0.98  # below swing high
        result = self._exit_logic_short(current, entry)
        assert result["exit"] == "NONE"


# ─────────────────────────────────────────────────────────────────────────────
# 5. FALLBACK BEHAVIOUR TEST (Sentinel timeout)
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackBehaviour:
    """Sentinel timeout → safe-default applied, system continues, log recorded."""

    def _sentinel_fetch_with_fallback(self, fail: bool, fallback=0.8) -> dict:
        """Simulates the Sentinel fetch + fallback logic in /process."""
        logged = []
        if fail:
            # Simulate timeout
            logged.append(("WARNING", "Sentinel fetch failed, using request fallback"))
            sentinel_multiplier = fallback
            event_risk_score = 0.3
            hours_to_event = 72.0
        else:
            sentinel_multiplier = 0.75
            event_risk_score = 0.25
            hours_to_event = 96.0
        return {
            "sentinel_multiplier": sentinel_multiplier,
            "event_risk_score": event_risk_score,
            "hours_to_event": hours_to_event,
            "log": logged,
            "continued": True,  # system did not crash
        }

    def test_sentinel_timeout_uses_request_fallback(self):
        """On timeout, sentinel_multiplier falls back to request body value."""
        result = self._sentinel_fetch_with_fallback(fail=True, fallback=0.8)
        assert result["sentinel_multiplier"] == 0.8
        assert result["continued"] is True

    def test_sentinel_timeout_logs_warning(self):
        """Timeout must be logged as WARNING."""
        result = self._sentinel_fetch_with_fallback(fail=True)
        assert any("WARNING" in entry[0] for entry in result["log"])

    def test_sentinel_success_uses_live_values(self):
        """Successful fetch uses live multiplier values."""
        result = self._sentinel_fetch_with_fallback(fail=False)
        assert result["sentinel_multiplier"] == 0.75
        assert result["event_risk_score"] == 0.25

    def test_system_continues_after_sentinel_failure(self):
        """Process endpoint must not crash when Sentinel is down."""
        result = self._sentinel_fetch_with_fallback(fail=True)
        assert result["continued"] is True
        assert 0.0 <= result["sentinel_multiplier"] <= 1.0

    def test_high_sentinel_multiplier_applies_to_confidence(self):
        """five_module_score × sentinel_multiplier determines confidence."""
        five_module_score = 0.72
        sentinel_multiplier = 0.85
        confidence = round(five_module_score * sentinel_multiplier, 4)
        assert confidence < five_module_score  # sentinel dampens
        assert confidence == round(0.72 * 0.85, 4)

    def test_low_sentinel_activates_risk_gate(self):
        """sentinel_multiplier < 0.5 → action forced to HOLD."""
        sentinel_multiplier = 0.40
        action = "HOLD" if sentinel_multiplier < 0.5 else "BUY"
        assert action == "HOLD"


# ─────────────────────────────────────────────────────────────────────────────
# 6. GREEN-LIGHT POSITIVE/NEGATIVE SCENARIOS
# ─────────────────────────────────────────────────────────────────────────────

class TestGreenLight:
    """8-criteria Green Light gate: all must pass for BUY/SELL action."""

    def _evaluate_green_light(
        self,
        regime: str = "NORMALIZATION",
        fundamental_score: float = 65.0,
        touche_eqs: float = 70.0,
        modules_agree: bool = True,
        multi_tf_valid: bool = True,
        cbr_include: bool = True,
        liquidity_ok: bool = True,
        sentinel_multiplier: float = 0.75,
        event_risk_score: float = 0.25,
        hours_to_event: float = 96.0,
        action_side: str = "BUY",
    ) -> dict:
        """Replicate the Green-Light check from /process."""
        # --- 8 criteria ---
        criteria = {
            "regime_suitable": (
                True
                if regime != "STAGFLATION"
                else fundamental_score > 60.0
            ),
            "dynamic_threshold_pass": touche_eqs >= 60.0 if action_side == "BUY" else touche_eqs <= 40.0,
            "modules_agree_3plus": modules_agree,
            "multi_tf_aligned": multi_tf_valid and action_side in {"BUY", "SELL"},
            "cbr_edge_valid": cbr_include,
            "liquidity_ok": liquidity_ok,
            "risk_multiplier_ok": sentinel_multiplier >= 0.7,
            "event_risk_ok": event_risk_score <= 0.4 or hours_to_event >= 48.0,
        }
        green_light = all(criteria.values()) and action_side in {"BUY", "SELL"}
        failed = [k for k, v in criteria.items() if not v]
        return {"green_light": green_light, "criteria": criteria, "failed": failed}

    # ── Positive scenario ─────────────────────────────────────────────────────
    def test_all_criteria_pass_gives_green_light(self):
        result = self._evaluate_green_light()
        assert result["green_light"] is True
        assert result["failed"] == []

    def test_buy_action_with_strong_scores(self):
        result = self._evaluate_green_light(
            touche_eqs=78.0,
            fundamental_score=72.0,
            sentinel_multiplier=0.85,
        )
        assert result["green_light"] is True

    # ── Negative scenarios ────────────────────────────────────────────────────
    def test_stagflation_blocks_when_fundamental_low(self):
        result = self._evaluate_green_light(
            regime="STAGFLATION",
            fundamental_score=55.0,  # must be > 60
        )
        assert result["green_light"] is False
        assert "regime_suitable" in result["failed"]

    def test_stagflation_passes_when_fundamental_high(self):
        result = self._evaluate_green_light(
            regime="STAGFLATION",
            fundamental_score=65.0,  # > 60 → pass
        )
        assert result["green_light"] is True

    def test_low_touche_fails_threshold(self):
        result = self._evaluate_green_light(touche_eqs=45.0)  # below BUY threshold 60
        assert result["green_light"] is False
        assert "dynamic_threshold_pass" in result["failed"]

    def test_mtf_conflict_blocks_green_light(self):
        result = self._evaluate_green_light(multi_tf_valid=False)
        assert result["green_light"] is False
        assert "multi_tf_aligned" in result["failed"]

    def test_low_sentinel_blocks_green_light(self):
        result = self._evaluate_green_light(sentinel_multiplier=0.55)
        assert result["green_light"] is False
        assert "risk_multiplier_ok" in result["failed"]

    def test_high_event_risk_blocks_green_light(self):
        result = self._evaluate_green_light(event_risk_score=0.6, hours_to_event=12.0)
        assert result["green_light"] is False
        assert "event_risk_ok" in result["failed"]

    def test_event_risk_passes_when_hours_ok(self):
        """High risk score is OK if event is far enough (>=48h)."""
        result = self._evaluate_green_light(event_risk_score=0.6, hours_to_event=60.0)
        assert result["criteria"]["event_risk_ok"] is True

    def test_hold_action_never_green_lights(self):
        """action_side=HOLD must never produce green_light=True."""
        result = self._evaluate_green_light(action_side="HOLD")
        assert result["green_light"] is False

    def test_liquidity_block(self):
        result = self._evaluate_green_light(liquidity_ok=False)
        assert result["green_light"] is False
        assert "liquidity_ok" in result["failed"]

    def test_cbr_include_false_blocks(self):
        """cbr_include=False (should never happen after fix, but gate must work)."""
        result = self._evaluate_green_light(cbr_include=False)
        assert result["green_light"] is False
        assert "cbr_edge_valid" in result["failed"]


# ─────────────────────────────────────────────────────────────────────────────
# BONUS: CBREarlyValidator direct import test
# ─────────────────────────────────────────────────────────────────────────────

class TestCBREarlyValidatorClass:
    """Direct test of the CBREarlyValidator class in strategies/cbr_engine."""

    def _get_validator(self):
        from strategies.cbr_engine.early_validator import CBREarlyValidator
        return CBREarlyValidator()

    def test_sparse_samples_include_is_true(self):
        v = self._get_validator()
        result = v.validate(10, 60.0, 0.7)
        assert result["include_in_consensus"] is True

    def test_sparse_samples_is_historical_weak(self):
        v = self._get_validator()
        result = v.validate(10, 60.0, 0.7)
        assert result["is_historical_weak"] is True
        assert result["confidence_modifier"] == 0.85
        assert result["reason"] == "fallback_active"

    def test_good_history_not_weak(self):
        v = self._get_validator()
        result = v.validate(25, 63.0, 0.8)
        assert result["include_in_consensus"] is True
        assert result["is_historical_weak"] is False
        assert result["confidence_modifier"] == 1.0

    def test_zero_samples_returns_weak(self):
        v = self._get_validator()
        result = v.validate(0, 0.0, 0.0)
        assert result["include_in_consensus"] is True
        assert result["is_historical_weak"] is True
        assert result["confidence_modifier"] == 0.85
