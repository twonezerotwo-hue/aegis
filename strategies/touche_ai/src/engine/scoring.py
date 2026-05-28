"""
Touche AI Limited — EQS (Entry Quality Score) Hesaplama Motoru

Her fazdan gelen skorları ağırlıklı ortalamayla birleştirerek
0-100 arası bir nihai EQS skoru üretir.

Ağırlıklar ve parametreler UnifiedOptimizer tarafından işlemlerden öğrenerek otomatik optimize edilir.
"""
from typing import Dict, List, Optional, Callable

import structlog
from pydantic import BaseModel

from ..phases.base import PhaseResult
from .unified_optimizer import UnifiedOptimizer, TradeRecord

logger = structlog.get_logger(__name__)


class EQSResult(BaseModel):
    """EQS Motoru Çıktı Modeli"""
    eqs_score: float               # 0-100 nihai skor
    weighted_scores: Dict[str, float]  # Faz bazında ağırlıklı katkılar
    dominant_signal: str           # BULLISH | BEARISH | NEUTRAL
    signal_strength: str           # STRONG | MODERATE | WEAK | NO_TRADE
    confidence: float              # 0.0 - 1.0
    optimization_status: Optional[str] = None  # "optimized" | "learning" | None



# ─── Varsayılan Ağırlıklar (YAML'dan okunamazsa) ─────────────────────────────
DEFAULT_WEIGHTS = {
    1: 0.15,  # Likidite
    2: 0.20,  # Piyasa Yapısı
    3: 0.20,  # Bölgeler
    4: 0.15,  # Teyit
    5: 0.15,  # Zamanlama
    6: 0.05,  # Risk
    7: 0.10,  # Makro
}

SCORE_THRESHOLDS = {
    "strong":   75.0,
    "moderate": 50.0,
    "weak":     40.0,
}


class EQSScorer:
    """
    AEGIS Holding — Touche AI Entry Quality Score Motoru.

    Kullanım:
        scorer = EQSScorer(config)
        result = scorer.compute(phase_results, volatility_regime="NORMAL")

    Multi-timeframe desteği: volatility_regime'e göre ağırlıkları dinamik ayarla
    """

    def __init__(self, config: dict = None, use_optimizer: bool = True, backtest_fn: Optional[Callable] = None):
        self.config = config or {}
        weights_cfg = self.config.get("scoring", {}).get("weights", {})

        # Config'den ağırlıkları oku; eksik fazlar için varsayılan kullan
        self.weights = {
            1: float(weights_cfg.get("phase1", DEFAULT_WEIGHTS[1])),
            2: float(weights_cfg.get("phase2", DEFAULT_WEIGHTS[2])),
            3: float(weights_cfg.get("phase3", DEFAULT_WEIGHTS[3])),
            4: float(weights_cfg.get("phase4", DEFAULT_WEIGHTS[4])),
            5: float(weights_cfg.get("phase5", DEFAULT_WEIGHTS[5])),
            6: float(weights_cfg.get("phase6", DEFAULT_WEIGHTS[6])),
            7: float(weights_cfg.get("phase7", DEFAULT_WEIGHTS[7])),
        }

        thresholds = self.config.get("scoring", {}).get("thresholds", {})
        self.strong_threshold = float(thresholds.get("strong_signal", SCORE_THRESHOLDS["strong"]))
        self.weak_threshold   = float(thresholds.get("weak_signal",   SCORE_THRESHOLDS["moderate"]))
        self.no_trade_thresh  = float(thresholds.get("no_trade",      SCORE_THRESHOLDS["weak"]))

        # Volatilite rejimi başına dinamik ağırlık ayarı
        self.volatility_weight_adjustments = {
            "LOW": {1: 0.10, 2: 0.15, 3: 0.25, 4: 0.20, 5: 0.20, 6: 0.05, 7: 0.05},     # Düşük vol: bölgelere ağırlık
            "NORMAL": {1: 0.15, 2: 0.20, 3: 0.20, 4: 0.15, 5: 0.15, 6: 0.05, 7: 0.10},   # Normal: dengeli
            "HIGH": {1: 0.20, 2: 0.15, 3: 0.15, 4: 0.10, 5: 0.10, 6: 0.15, 7: 0.15},    # Yüksek vol: risk artır
        }

        # Unified Optimizer - Ağırlıklar ve parametreleri otomatik optimize et
        self.use_optimizer = use_optimizer
        self.optimizer: Optional[UnifiedOptimizer] = None
        if use_optimizer:
            self.optimizer = UnifiedOptimizer(backtest_fn=backtest_fn, learning_rate=0.01)
            logger.info("unified_optimizer_initialized", learning_rate=0.01)

    def compute(self, phase_results: List[PhaseResult], volatility_regime: str = "NORMAL") -> EQSResult:
        """
        Faz sonuçlarını ağırlıklı skor hesabına dönüştürür.

        Rüştü:
        - Volatilite rejimi dinamik ağırlık ayarlaması
        - UnifiedOptimizer'dan güncel ağırlıkları kullan
        - Herhangi bir faz passed=False döndürdüyse, dominant_signal = NEUTRAL

        Args:
            phase_results: Faz sonuçları listesi
            volatility_regime: Teşhis edilen volatilite rejimi ("LOW", "NORMAL", "HIGH")
        """
        # ── Optimizer'dan güncel ağırlıkları al ───────────────────────────────────
        active_weights = self.weights.copy()
        if self.optimizer:
            active_weights = self.optimizer.weights.copy()

        # ── Volatilite rejiminde ağırlık ayarla ─────────────────────────────────
        if volatility_regime in self.volatility_weight_adjustments:
            vol_adjustments = self.volatility_weight_adjustments[volatility_regime]
            for phase_id, adjusted_weight in vol_adjustments.items():
                active_weights[phase_id] = adjusted_weight
            logger.info("volatility_adjusted_weights", regime=volatility_regime, weights=vol_adjustments)

        # ── Bloklanmış Faz Kontrolü ───────────────────────────────────────────
        blocking_phases = [r for r in phase_results if not r.passed]
        if blocking_phases:
            blocker = blocking_phases[0]
            logger.warning(
                "eqs_pipeline_blocked",
                blocker_phase=blocker.phase_name,
                reason=blocker.reason,
            )
            return EQSResult(
                eqs_score=0.0,
                weighted_scores={},
                dominant_signal="NEUTRAL",
                signal_strength="NO_TRADE",
                confidence=0.0,
            )

        # ── Ağırlıklı Skor Hesabı ─────────────────────────────────────────────
        total_weight = 0.0
        total_score = 0.0
        weighted_scores: Dict[str, float] = {}

        for result in phase_results:
            w = active_weights.get(result.phase_id, 0.0)
            contribution = result.score * w
            weighted_scores[result.phase_name] = round(contribution, 3)
            total_score += contribution
            total_weight += w

        if total_weight <= 0:
            logger.error("eqs_zero_total_weight")
            return EQSResult(
                eqs_score=0.0,
                weighted_scores=weighted_scores,
                dominant_signal="NEUTRAL",
                signal_strength="NO_TRADE",
                confidence=0.0,
            )

        # Toplam ağırlık 1.0 değilse normalleştir
        eqs_score = round(total_score / total_weight, 2)

        # ── Dominant Sinyal (Çoğunluk Oyu) ───────────────────────────────────
        signal_votes = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
        for r in phase_results:
            w = active_weights.get(r.phase_id, 0.0)
            signal_votes[r.signal] = signal_votes.get(r.signal, 0) + w

        dominant_signal = max(signal_votes, key=signal_votes.get)

        # Baskın sinyal yeterince güçlü değilse NEUTRAL'a çek
        if signal_votes[dominant_signal] < 0.4:
            dominant_signal = "NEUTRAL"

        # ── Sinyal Gücü (Volatilite rejimi tabanlı) ───────────────────────────
        # Yüksek volatilite = daha yüksek eşik (daha dikkatli)
        if volatility_regime == "HIGH":
            adjusted_strong = self.strong_threshold + 10
            adjusted_weak = self.weak_threshold + 5
        elif volatility_regime == "LOW":
            adjusted_strong = self.strong_threshold - 5
            adjusted_weak = self.weak_threshold
        else:  # NORMAL
            adjusted_strong = self.strong_threshold
            adjusted_weak = self.weak_threshold

        if eqs_score >= adjusted_strong:
            strength = "STRONG"
        elif eqs_score >= adjusted_weak:
            strength = "MODERATE"
        elif eqs_score >= self.no_trade_thresh:
            strength = "WEAK"
        else:
            strength = "NO_TRADE"
            dominant_signal = "NEUTRAL"

        # Güven = Normalize edilmiş EQS
        confidence = round(min(1.0, eqs_score / 100.0), 3)

        logger.info(
            "eqs_computed",
            score=eqs_score,
            signal=dominant_signal,
            strength=strength,
            confidence=confidence,
            volatility_regime=volatility_regime,
        )

        return EQSResult(
            eqs_score=eqs_score,
            weighted_scores=weighted_scores,
            dominant_signal=dominant_signal,
            signal_strength=strength,
            confidence=confidence,
            optimization_status="learning" if self.use_optimizer else None,
        )

    def record_trade(self,
                    entry_price: float,
                    exit_price: float,
                    pnl: float,
                    winning_phases: List[int],
                    losing_phases: List[int],
                    rsi_at_entry: float = 0.0,
                    macd_at_entry: float = 0.0,
                    volatility: float = 0.0,
                    fibonacci_level: float = 0.618) -> bool:
        """
        İşlemi kaydet ve optimizer'a raporla.

        Args:
            entry_price: Giriş fiyatı
            exit_price: Çıkış fiyatı
            pnl: İşlem kârı/zararı
            winning_phases: İşlemi kazandıran fazlar
            losing_phases: İşlemi kaybettiren fazlar
            rsi_at_entry: Girişte RSI değeri
            macd_at_entry: Girişte MACD değeri
            volatility: Oynaklık
            fibonacci_level: Fibonacci seviyesi

        Returns:
            Başarılı olup olmadığı
        """
        if not self.optimizer:
            logger.warning("optimizer_not_enabled")
            return False

        trade = TradeRecord(
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            winning_phases=winning_phases,
            losing_phases=losing_phases,
            rsi_at_entry=rsi_at_entry,
            macd_at_entry=macd_at_entry,
            volatility=volatility,
            fibonacci_level=fibonacci_level,
        )

        self.optimizer.record_trade(trade)

        logger.info(
            "trade_recorded_to_optimizer",
            pnl=pnl,
            is_winning=pnl > 0,
            winning_phases=winning_phases,
            losing_phases=losing_phases,
        )
        return True

    def get_optimizer_status(self) -> Dict:
        """Optimizer'ın mevcut durumunu döndür"""
        if not self.optimizer:
            return {"enabled": False, "error": "Optimizer not initialized"}

        return self.optimizer.get_status()

    def save_optimizer_config(self, filepath: str) -> bool:
        """Optimizer'ın ayarlarını YAML'a kaydet"""
        if not self.optimizer:
            logger.warning("optimizer_not_enabled")
            return False

        self.optimizer.save_config(filepath)
        logger.info("optimizer_config_saved", filepath=filepath)
        return True

    def load_optimizer_config(self, filepath: str) -> bool:
        """Optimizer'ın ayarlarını YAML'dan yükle"""
        if not self.optimizer:
            logger.warning("optimizer_not_enabled")
            return False

        self.optimizer.load_config(filepath)
        logger.info("optimizer_config_loaded", filepath=filepath)
        return True


