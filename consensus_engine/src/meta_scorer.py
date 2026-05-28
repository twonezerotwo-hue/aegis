"""
AEGIS v7.0 — Meta-Scorer

Pairwise 30-day rolling Pearson correlation across 5 modules.
When corr(mod_a, mod_b) > 0.8, the lower-scoring module's weight is
multiplied by CORR_PENALTY_MULTIPLIER, then all weights are re-normalized.

Design rules:
- If history < MIN_HISTORY_DAYS  → corr_penalty = 1.0 (no penalty)
- Never raises exceptions         → safe default returned on any error
- Pure function: does NOT mutate YAML or module-level state
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MIN_HISTORY_DAYS: int = 15
CORR_THRESHOLD: float = 0.8
CORR_PENALTY_MULT: float = 0.7

MODULES = ("touche", "fundamental", "news", "sentinel", "quantum")

# Short-key aliases accepted in module_history_30d payloads
_ALIAS_MAP = {
    "T": "touche",
    "F": "fundamental",
    "N": "news",
    "S": "sentinel",
    "Q": "quantum",
}


def _normalize_history_keys(
    history: Dict[str, List[float]]
) -> Dict[str, List[float]]:
    """Accept both short (T/F/N/S/Q) and full module name keys."""
    normalized: Dict[str, List[float]] = {}
    for raw_key, values in history.items():
        canonical = _ALIAS_MAP.get(raw_key.upper(), raw_key.lower())
        if canonical in MODULES and isinstance(values, list):
            normalized[canonical] = [float(v) for v in values]
    return normalized


def _min_history_len(history: Dict[str, List[float]]) -> int:
    if not history:
        return 0
    return min(len(v) for v in history.values())


def _pearson(x: List[float], y: List[float]) -> float:
    """Pearson r. Returns 0.0 if inputs are too short or degenerate."""
    n = len(x)
    if n < 2:
        return 0.0
    try:
        import numpy as np  # numpy is in requirements, prefer it
        r = float(np.corrcoef(x, y)[0, 1])
        return r if r == r else 0.0  # guard NaN
    except Exception:
        pass
    # Pure-Python fallback
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den_x = sum((xi - mx) ** 2 for xi in x) ** 0.5
    den_y = sum((yi - my) ** 2 for yi in y) ** 0.5
    if den_x == 0.0 or den_y == 0.0:
        return 0.0
    r = num / (den_x * den_y)
    return r if r == r else 0.0  # guard NaN


class MetaScorer:
    """
    Adjusts 5-module weights by penalizing redundant (highly correlated)
    module pairs, then re-normalizes to preserve Σ=1.0.
    """

    def score(
        self,
        base_weights: Dict[str, float],
        current_scores: Dict[str, float],
        history_30d: Optional[Dict[str, List[float]]] = None,
    ) -> Dict:
        """
        Parameters
        ----------
        base_weights    : Module weights before any correlation penalty.
                          Keys: touche, fundamental, news, sentinel, quantum.
        current_scores  : Raw scores 0–100 for this request tick.
        history_30d     : 30-day daily score history per module.
                          Accepts short keys (T/F/N/S/Q) or full names.

        Returns
        -------
        dict with keys:
            adjusted_weights  : dict[str, float] — re-normalized weights
            corr_matrix       : dict["mod_a:mod_b", float] — all pairs
            penalized_pairs   : list of dicts describing each penalized pair
            corr_penalty      : float in (0, 1] — 1.0 = no penalty applied
        """
        try:
            return self._compute(base_weights, current_scores, history_30d)
        except Exception as exc:
            logger.error(f"[MetaScorer] Unexpected error: {exc} — returning base weights")
            return {
                "adjusted_weights": dict(base_weights),
                "corr_matrix": {},
                "penalized_pairs": [],
                "corr_penalty": 1.0,
            }

    def _compute(
        self,
        base_weights: Dict[str, float],
        current_scores: Dict[str, float],
        history_30d: Optional[Dict[str, List[float]]],
    ) -> Dict:
        # Normalize incoming history keys
        history = _normalize_history_keys(history_30d) if history_30d else {}

        # Insufficient history → no penalty
        if not history or _min_history_len(history) < MIN_HISTORY_DAYS:
            logger.info(
                "[MetaScorer] history=%d days < %d → corr_penalty=1.0",
                _min_history_len(history),
                MIN_HISTORY_DAYS,
            )
            return {
                "adjusted_weights": dict(base_weights),
                "corr_matrix": {},
                "penalized_pairs": [],
                "corr_penalty": 1.0,
            }

        # Modules present in both history and base_weights
        active_modules = [
            m for m in MODULES if m in history and m in base_weights
        ]

        corr_matrix: Dict[str, float] = {}
        penalized_pairs: list = []
        adjusted = dict(base_weights)

        for i, mod_a in enumerate(active_modules):
            for mod_b in active_modules[i + 1:]:
                hist_a = history[mod_a]
                hist_b = history[mod_b]
                min_len = min(len(hist_a), len(hist_b))
                corr = _pearson(hist_a[-min_len:], hist_b[-min_len:])
                pair_key = f"{mod_a}:{mod_b}"
                corr_matrix[pair_key] = round(corr, 4)

                if corr > CORR_THRESHOLD:
                    score_a = float(current_scores.get(mod_a, 50.0))
                    score_b = float(current_scores.get(mod_b, 50.0))
                    loser = mod_a if score_a <= score_b else mod_b

                    if loser in adjusted:
                        prev_weight = adjusted[loser]
                        adjusted[loser] = prev_weight * CORR_PENALTY_MULT
                        penalized_pairs.append({
                            "pair": pair_key,
                            "corr": round(corr, 4),
                            "penalized_module": loser,
                            "weight_before": round(prev_weight, 6),
                            "weight_after": round(adjusted[loser], 6),
                        })
                        logger.info(
                            "[MetaScorer] corr(%s, %s)=%.3f > %.1f → penalize %s "
                            "%.4f → %.4f",
                            mod_a, mod_b, corr, CORR_THRESHOLD, loser,
                            prev_weight, adjusted[loser],
                        )

        # Re-normalize
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: round(v / total, 6) for k, v in adjusted.items()}

        # corr_penalty scalar: ratio of (weight-sum before normalization) vs original
        # Measures how much total weight was "removed" across all modules
        pre_norm_sum = 0.0
        orig_sum = 0.0
        for mod in adjusted:
            orig_w = base_weights.get(mod, 0.0)
            orig_sum += orig_w
            # re-derive pre-norm adjusted weight from penalty applications
            adj_w = base_weights.get(mod, 0.0)
            for pp in penalized_pairs:
                if pp["penalized_module"] == mod:
                    adj_w = adj_w * CORR_PENALTY_MULT
            pre_norm_sum += adj_w

        corr_penalty = round(pre_norm_sum / orig_sum, 4) if orig_sum > 0 else 1.0

        return {
            "adjusted_weights": adjusted,
            "corr_matrix": corr_matrix,
            "penalized_pairs": penalized_pairs,
            "corr_penalty": corr_penalty,
        }
