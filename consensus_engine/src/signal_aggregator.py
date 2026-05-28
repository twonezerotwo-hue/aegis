"""
Consensus Engine — Signal Aggregator

Touche AI, Fundamental AI ve News AI sinyallerini birleştirerek
nihai consensus kararı üretir.
"""
import os
from typing import Tuple, Optional, Dict, Any

import structlog
import yaml

from .models import (
    ToucheSignal,
    FundamentalSignal,
    AggregationResult,
    ConsensusConfig,
)

logger = structlog.get_logger(__name__)

# Consensus weights YAML konfigürasyonu yolu
_CONSENSUS_WEIGHTS_PATH = os.path.join(
    os.path.dirname(__file__), "../config/consensus_weights.yaml"
)


class SignalAggregator:
    """Has sinyali (Touche, Fundamental, News) birleştirerek consensus karar üretir."""

    def __init__(self, config: ConsensusConfig):
        """
        Args:
            config: Consensus konfigürasyonu
        """
        self.config = config
        self.phase_weights = self._load_phase_weights()

    def _load_phase_weights(self) -> Dict[str, Dict[str, float]]:
        """
        Consensus weights YAML dosyasından faz-spesifik ağırlıkları yükle.

        Returns:
            Faz başına ağırlıklar: {'phase1': {...}, 'phase2': {...}, ...}
        """
        try:
            if not os.path.exists(_CONSENSUS_WEIGHTS_PATH):
                logger.warning("consensus_weights_file_not_found", path=_CONSENSUS_WEIGHTS_PATH)
                return self._default_weights()

            with open(_CONSENSUS_WEIGHTS_PATH, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

            phases = config_data.get("phases", {})
            if not phases:
                logger.warning("no_phases_in_config")
                return self._default_weights()

            # Faz ağırlıklarını çıkar
            phase_weights = {}
            for phase_name in ["phase1", "phase2", "phase3"]:
                phase_config = phases.get(phase_name, {})
                phase_weights[phase_name] = {
                    "touche": phase_config.get("touche_weight", 0.50),
                    "fundamental": phase_config.get("fundamental_weight", 0.35),
                    "news": phase_config.get("news_weight", 0.15),
                }

            logger.info("phase_weights_loaded", phases=list(phase_weights.keys()))
            return phase_weights

        except Exception as e:
            logger.error("phase_weights_load_error", error=str(e))
            return self._default_weights()

    def _default_weights(self) -> Dict[str, Dict[str, float]]:
        """Varsayılan faz ağırlıkları."""
        return {
            "phase1": {"touche": 0.50, "fundamental": 0.35, "news": 0.15},
            "phase2": {"touche": 0.40, "fundamental": 0.35, "news": 0.25},
            "phase3": {"touche": 0.40, "fundamental": 0.30, "news": 0.30},
        }

    def _get_current_phase_weights(self) -> Dict[str, float]:
        """
        Mevcut faza ait ağırlıkları al.

        Returns:
            {'touche': 0.50, 'fundamental': 0.35, 'news': 0.15}
        """
        try:
            with open(_CONSENSUS_WEIGHTS_PATH, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

            current_phase = config_data.get("current_phase", 1)
            if isinstance(current_phase, str):
                phase_name = current_phase if current_phase.startswith("phase") else f"phase{current_phase}"
            else:
                phase_name = f"phase{current_phase}"

            # Backward-compat: production_v6 lives in the v7 YAML root schema,
            # while aggregator phase buckets remain phase1/2/3.
            if phase_name == "phaseproduction_v6":
                phase_name = "phase1"

            if phase_name not in self.phase_weights:
                logger.warning("phase_not_found", phase=phase_name)
                phase_name = "phase1"

            weights = self.phase_weights[phase_name]
            logger.info("using_phase_weights", phase=phase_name, weights=weights)
            return weights

        except Exception as e:
            logger.error("get_phase_weights_error", error=str(e))
            return self.phase_weights.get("phase1", {"touche": 0.50, "fundamental": 0.35, "news": 0.15})

    def get_dynamic_weights(self, regime: str) -> Dict[str, float]:
        """
        Market rejimine gore dinamik agirliklari dondur.

        Rejimler:
        - stagflation: Touche 20%, Fundamental 30%, News 50%
        - trending: Touche 60%, Fundamental 30%, News 10%
        - crash: Touche 10%, Fundamental 40%, News 50%
        """
        normalized = (regime or "").strip().lower()

        mapping = {
            "stagflation": {"touche": 0.20, "fundamental": 0.30, "news": 0.50},
            "trending": {"touche": 0.60, "fundamental": 0.30, "news": 0.10},
            "crash": {"touche": 0.10, "fundamental": 0.40, "news": 0.50},
            "normal": {"touche": 0.50, "fundamental": 0.35, "news": 0.15},
            "normalization": {"touche": 0.50, "fundamental": 0.35, "news": 0.15},
        }

        if normalized in mapping:
            weights = mapping[normalized]
            logger.info("using_dynamic_weights", regime=normalized, weights=weights)
            return weights

        logger.info("dynamic_weights_fallback_to_phase", regime=normalized or "unknown")
        return self._get_current_phase_weights()

    def get_cbr_adjusted_weights(self, regime: str, similarity_score: float) -> Dict[str, float]:
        """
        CBR benzerlik skoruna gore agirliklari ayarla.

        similarity_score > 0.8 ise, ilgili rejimde gecmiste kazanan modulun
        agirligi artirilir ve tum agirliklar normalize edilir.
        """
        weights = dict(self.get_dynamic_weights(regime) if regime else self._get_current_phase_weights())

        if similarity_score <= 0.8:
            return weights

        # Rejim-bazli tarihsel kazanan modul varsayimi.
        winner_by_regime = {
            "trending": "touche",
            "stagflation": "news",
            "crash": "fundamental",
        }
        winner = winner_by_regime.get((regime or "").strip().lower(), "touche")

        if winner in weights:
            weights[winner] *= 1.15

        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        logger.info(
            "using_cbr_adjusted_weights",
            regime=(regime or "normal"),
            similarity_score=round(similarity_score, 4),
            winner=winner,
            weights=weights,
        )
        return weights

    def get_dynamic_thresholds(self, regime: str) -> Dict[str, float]:
        """
        Rejime gore al/sat esiklerini dondur (0-100 skala).

        trending: buy=52/sell=48
        stagflation: buy=60/sell=40
        crash: buy=65/sell=35
        normal: buy=55/sell=45
        """
        normalized = (regime or "normal").strip().lower()
        mapping = {
            "trending": {"buy": 52.0, "sell": 48.0},
            "stagflation": {"buy": 60.0, "sell": 40.0},
            "crash": {"buy": 65.0, "sell": 35.0},
            "normal": {"buy": 55.0, "sell": 45.0},
        }
        thresholds = mapping.get(normalized, mapping["normal"])
        logger.info("using_dynamic_thresholds", regime=normalized, thresholds=thresholds)
        return thresholds
    
    def _apply_historical_weak_boost(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        FIX: is_historical_weak=True ise touche ve sentinel ağırlıklarını +0.10 artırır ve normalize eder.
        (Bu aggregator'da sentinel yoksa sadece touche artırılır.)
        """
        boosted = dict(weights)
        for key in ("touche", "sentinel"):
            if key in boosted:
                boosted[key] += 0.10
        total = sum(boosted.values())
        if total > 0:
            boosted = {k: v / total for k, v in boosted.items()}
        return boosted

    def aggregate(
        self,
        touche_signal: ToucheSignal,
        fundamental_signal: FundamentalSignal,
        news_signal: Optional[Dict[str, Any]] = None,
        regime: Optional[str] = None,
        similarity_score: Optional[float] = None,
        is_historical_weak: bool = False,
    ) -> AggregationResult:
        """
        Üç sinyali birleştirerek consensus kararı üretir.

        Args:
            touche_signal: Touche AI sinyali
            fundamental_signal: Fundamental AI sinyali
            news_signal: (Optional) News AI Limited sinyali

        Returns:
            AggregationResult
        """
        symbol = touche_signal.symbol

        # Rejim verilirse dinamik agirlik, similarity_score yuksekse CBR ayari uygula.
        if similarity_score is not None:
            weights = self.get_cbr_adjusted_weights(regime or "normal", float(similarity_score))
        else:
            weights = self.get_dynamic_weights(regime) if regime else self._get_current_phase_weights()

        # CBR geçmişi zayıfsa touche (+10%) ve sentinel (+10%) ağırlıklarını artır.
        if is_historical_weak:
            weights = self._apply_historical_weak_boost(weights)
            logger.info("historical_weak_boost_applied", weights=weights)

        # Adım 1: Sinyalleri normalize et (0-1 skala)
        touche_score = self._normalize_touche_signal(touche_signal)
        fundamental_score = self._normalize_fundamental_signal(fundamental_signal)
        news_score = self._normalize_news_signal(news_signal) if news_signal else 0.0

        # Adım 2: Uyumu kontrol et
        signals_aligned, alignment_degree = self._check_alignment(
            touche_signal, fundamental_signal, news_signal
        )

        # Adım 3: Raw scores'u ağırlıklandır
        bullish_score = self._calculate_bullish_score(
            touche_score,
            fundamental_score,
            news_score,
            alignment_degree,
            weights,
        )
        bearish_score = self._calculate_bearish_score(
            touche_score,
            fundamental_score,
            news_score,
            alignment_degree,
            weights,
        )

        # Neutral score - FIX: proper neutral calculation
        # Instead of 1.0 - (bullish + bearish)/2, use max of bullish/bearish
        max_action_score = max(bullish_score, bearish_score)
        neutral_score = 1.0 - max_action_score  # Neutral is complement of max action

        # Adım 4: Nihai kararı ver
        thresholds = self.get_dynamic_thresholds(regime or "normal")
        action, confidence = self._determine_action(
            bullish_score,
            bearish_score,
            neutral_score,
            buy_threshold=thresholds["buy"] / 100.0,
            sell_threshold=thresholds["sell"] / 100.0,
        )

        # Adım 5: Summary oluştur
        summary = self._create_summary(
            touche_signal,
            fundamental_signal,
            news_signal,
            action,
            alignment_degree,
            weights,
        )

        result = AggregationResult(
            symbol=symbol,
            touche_signal=touche_signal,
            fundamental_signal=fundamental_signal,
            news_signal=news_signal,
            touche_score=touche_score,
            fundamental_score=fundamental_score,
            news_score=news_score,
            signals_aligned=signals_aligned,
            alignment_degree=alignment_degree,
            aggregate_bullish_score=bullish_score,
            aggregate_bearish_score=bearish_score,
            aggregate_neutral_score=neutral_score,
            recommended_action=action,
            confidence=confidence,
            summary=summary,
        )

        logger.info(
            "signals_aggregated",
            symbol=symbol,
            action=action,
            confidence=round(confidence, 3),
            aligned=signals_aligned,
            touche_weight=weights["touche"],
            fundamental_weight=weights["fundamental"],
            news_weight=weights["news"],
        )

        return result
    
    def _normalize_touche_signal(self, signal: ToucheSignal) -> float:
        """Touche sinyalini 0-1 normalizasyon."""
        if signal.is_bullish:
            return signal.confidence
        elif signal.is_bearish:
            return -signal.confidence
        else:
            return 0.0
    
    def _normalize_fundamental_signal(self, signal: FundamentalSignal) -> float:
        """Fundamental sinyalini 0-1 normalizasyon."""
        if signal.signal == "BULLISH":
            return signal.confidence
        elif signal.signal == "BEARISH":
            return -signal.confidence
        else:
            return 0.0

    def _normalize_news_signal(self, signal: Optional[Dict[str, Any]]) -> float:
        """
        News AI sinyalini -1 to +1 normalizasyon.

        News signal score: 0-100 (neutral=50)
        Çıktı: -1 to +1
        """
        if not signal:
            return 0.0

        try:
            score = signal.get("score", 50.0)  # 0-100
            # 0-100 → -1 to +1 transform: (score - 50) / 50
            normalized = (score - 50.0) / 50.0
            # Clamp to [-1, 1]
            normalized = max(-1.0, min(1.0, normalized))
            return normalized
        except Exception as e:
            logger.error("normalize_news_signal_error", error=str(e))
            return 0.0
    
    def _check_alignment(
        self,
        touche: ToucheSignal,
        fundamental: FundamentalSignal,
        news: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, float]:
        """
        Sinyalların uyumunu kontrol eder.
        """
        touche_bullish = touche.is_bullish
        touche_bearish = touche.is_bearish
        fundamental_bullish = fundamental.signal == "BULLISH"
        fundamental_bearish = fundamental.signal == "BEARISH"

        # News sinyalini al
        news_bullish = False
        news_bearish = False
        if news:
            news_score = news.get("score", 50.0)
            news_bullish = news_score > 60.0  # 60+ = bullish
            news_bearish = news_score < 40.0  # <40 = bearish

        # Alignment logic: 2 veya 3 sinyal uyumlu mu?
        bullish_count = sum([touche_bullish, fundamental_bullish, news_bullish]) if news else sum([touche_bullish, fundamental_bullish])
        bearish_count = sum([touche_bearish, fundamental_bearish, news_bearish]) if news else sum([touche_bearish, fundamental_bearish])

        signal_count = 3 if news else 2

        # Tam uyum
        if (bullish_count == signal_count) or (bearish_count == signal_count):
            aligned = True
            degrees = [touche.confidence, fundamental.confidence]
            if news:
                news_confidence = news.get("confidence", 0.5)
                degrees.append(news_confidence)
            degree = sum(degrees) / len(degrees)
        # Zıt yönde
        elif (bullish_count > 0 and bearish_count > 0):
            aligned = False
            degree = 0.0
        # Biri NEUTRAL (veya kısmi uyum)
        else:
            aligned = True
            degrees = []
            if touche_bullish or touche_bearish:
                degrees.append(touche.confidence)
            if fundamental_bullish or fundamental_bearish:
                degrees.append(fundamental.confidence)
            if news and (news_bullish or news_bearish):
                degrees.append(news.get("confidence", 0.5))

            degree = sum(degrees) / len(degrees) if degrees else 0.5

        return aligned, degree
    
    def _calculate_bullish_score(
        self,
        touche_score: float,
        fundamental_score: float,
        news_score: float,
        alignment_degree: float,
        weights: Dict[str, float],
    ) -> float:
        """AL için toplam skor hesapla."""
        # Bullish sinyalları ayıkla
        touche_bullish = max(0, touche_score)
        fundamental_bullish = max(0, fundamental_score)
        news_bullish = max(0, news_score)

        # Ağırlıklı kombinasyon
        combined = (
            weights["touche"] * touche_bullish +
            weights["fundamental"] * fundamental_bullish +
            weights["news"] * news_bullish
        )

        # Uyum bonus
        if touche_score > 0 and fundamental_score > 0:
            combined += alignment_degree * self.config.alignment_bonus

        return max(0.0, min(1.0, combined))
    
    def _calculate_bearish_score(
        self,
        touche_score: float,
        fundamental_score: float,
        news_score: float,
        alignment_degree: float,
        weights: Dict[str, float],
    ) -> float:
        """SAT için toplam skor hesapla."""
        # Bearish sinyalları ayıkla
        touche_bearish = abs(min(0, touche_score))
        fundamental_bearish = abs(min(0, fundamental_score))
        news_bearish = abs(min(0, news_score))

        # Ağırlıklı kombinasyon
        combined = (
            weights["touche"] * touche_bearish +
            weights["fundamental"] * fundamental_bearish +
            weights["news"] * news_bearish
        )

        # Uyum bonus
        if touche_score < 0 and fundamental_score < 0:
            combined += alignment_degree * self.config.alignment_bonus

        return max(0.0, min(1.0, combined))
    
    def _determine_action(
        self,
        bullish: float,
        bearish: float,
        neutral: float,
        buy_threshold: Optional[float] = None,
        sell_threshold: Optional[float] = None,
    ) -> Tuple[str, float]:
        """Skor yapısından nihai aksiyonu belirle."""
        buy_thr = buy_threshold if buy_threshold is not None else self.config.min_confidence
        sell_thr = sell_threshold if sell_threshold is not None else self.config.min_confidence

        if bullish >= buy_thr and bullish >= bearish:
            return "AL", bullish
        if bearish >= sell_thr and bearish > bullish:
            return "SAT", bearish
        return "BEKLE", neutral
    
    def _create_summary(
        self,
        touche: ToucheSignal,
        fundamental: FundamentalSignal,
        news: Optional[Dict[str, Any]],
        action: str,
        alignment_degree: float,
        weights: Dict[str, float],
    ) -> str:
        """Kararın özeti yazı."""
        parts = [
            f"Touche: {touche.signal} (EQS={touche.eqs:.0f}, w={weights['touche']:.0%})",
            f"Fundamental: {fundamental.signal} (Score={fundamental.score:.0f}, w={weights['fundamental']:.0%})",
        ]

        if news:
            news_signal = news.get("signal", "BEKLE")
            news_score = news.get("score", 50.0)
            parts.append(f"News: {news_signal} (Score={news_score:.0f}, w={weights['news']:.0%})")

        if alignment_degree > 0.7:
            parts.append("OK Sinyaller uyumlu")
        elif alignment_degree > 0.3:
            parts.append("Half OK Sinyaller kismen uyumlu")
        else:
            parts.append("Not OK Sinyaller cesitli")

        parts.append(f"Karar: {action}")

        return " | ".join(parts)
