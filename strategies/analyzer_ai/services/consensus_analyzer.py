import logging
from models.schemas import ConsensusAnalysis

logger = logging.getLogger(__name__)

class ConsensusAnalyzer:
    def __init__(self, weights: dict = None):
        """
        weights: Dictionary with keys: touche, fundamental, quantum, sentinel, news
        """
        self.weights = weights or {
            "touche": 0.35,
            "fundamental": 0.30,
            "quantum": 0.15,
            "sentinel": 0.15,
            "news": 0.05
        }

    def analyze(self, touche_score: float, fundamental_score: float,
                quantum_score: float, sentinel_score: float,
                news_score: float) -> ConsensusAnalysis:
        """
        Calculate weighted consensus score from all analyzers
        Scores should be 0.0-1.0, where:
        - 0.0-0.35 = SHORT
        - 0.35-0.65 = NÖTR
        - 0.65-1.0 = LONG
        """

        # Calculate weighted score
        weighted_score = (
            touche_score * self.weights["touche"] +
            fundamental_score * self.weights["fundamental"] +
            quantum_score * self.weights["quantum"] +
            sentinel_score * self.weights["sentinel"] +
            news_score * self.weights["news"]
        )

        # Convert to percentage (0-100)
        weighted_percentage = weighted_score * 100

        # Determine final direction
        if weighted_score > 0.65:
            final_direction = "LONG"
            confidence = min(weighted_score, 1.0)
        elif weighted_score < 0.35:
            final_direction = "SHORT"
            confidence = 1.0 - weighted_score
        else:
            final_direction = "NÖTR"
            confidence = 0.5

        return ConsensusAnalysis(
            touche_score=touche_score * 100,
            fundamental_score=fundamental_score * 100,
            quantum_score=quantum_score * 100,
            sentinel_score=sentinel_score * 100,
            news_score=news_score * 100,
            weighted_score=weighted_percentage,
            final_direction=final_direction,
            confidence=confidence
        )

    def get_summary(self, analysis: ConsensusAnalysis) -> str:
        """Get human-readable consensus summary"""
        scores = [
            f"Touche: {analysis.touche_score:.1f}%",
            f"Fundamental: {analysis.fundamental_score:.1f}%",
            f"Quantum: {analysis.quantum_score:.1f}%",
            f"Sentinel: {analysis.sentinel_score:.1f}%",
            f"News: {analysis.news_score:.1f}%"
        ]

        summary = (
            f"{', '.join(scores)} → "
            f"Toplam Skor: {analysis.weighted_score:.2f}% "
            f"({analysis.final_direction}) "
            f"Confidence: {analysis.confidence*100:.1f}%"
        )

        return summary
