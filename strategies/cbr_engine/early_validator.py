"""CBR early validation before consensus scoring."""


class CBREarlyValidator:
    """Runs CBR edge checks before consensus stage."""

    def validate(self, sample_count: int, win_rate_pct: float, similarity_score: float) -> dict:
        has_similar_case = sample_count > 0 and similarity_score > 0.0
        edge_pct = float(win_rate_pct)

        # FIX: production behavior - weak history never blocks consensus.
        if sample_count < 15 or edge_pct < 55.0:
            return {
                "has_similar_case": has_similar_case,
                "sample_count": sample_count,
                "win_rate_pct": win_rate_pct,
                "edge_pct": edge_pct,
                "include_in_consensus": True,
                "is_historical_weak": True,
                "confidence_modifier": 0.85,
                "reason": "fallback_active",
            }

        return {
            "has_similar_case": has_similar_case,
            "sample_count": sample_count,
            "win_rate_pct": win_rate_pct,
            "edge_pct": edge_pct,
            "include_in_consensus": True,
            "is_historical_weak": False,
            "confidence_modifier": 1.0,
            "reason": "cbr_edge_valid",
        }
