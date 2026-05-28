"""
CONSENSUS ENGINE - Dynamic Weighting & Conflict Resolution

Özellikler:
- Dinamik modül ağırlıklandırması (performansa göre)
- Modül çelişki çözme mekanizması
- Geri beslemesi döngüsü (kazanan modülü boost)
- Performans tracking ve learning
"""
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import structlog
import json
from pathlib import Path

logger = structlog.get_logger(__name__)


@dataclass
class ModulePerformance:
    """Modül performans metriği"""
    module_name: str
    accuracy_7d: float  # 7 günlük doğruluk (0-1)
    accuracy_30d: float  # 30 günlük doğruluk
    win_rate: float  # Kaç % doğru tahmin yaptığı
    false_positive_rate: float  # Yanlış alarm yüzdesi
    last_updated: int  # timestamp


class DynamicWeightingEngine:
    """
    Modüllerin performansa göre dinamik ağırlıklandırması

    Kurall:
    - Başlangıç: Statik ağırlıklar (Touche 50%, Fundamental 35%, News 15%)
    - Haftalık: Performansa göre +/- 5% ayarlama
    - Maksimum range: [30%, 60%] (extreme swings'i engelle)
    """

    DEFAULT_WEIGHTS = {
        "Touche": 0.50,
        "Fundamental": 0.35,
        "News": 0.15,
    }

    MIN_MAX_WEIGHTS = {
        "Touche": (0.30, 0.65),
        "Fundamental": (0.20, 0.50),
        "News": (0.05, 0.30),
    }

    def __init__(self, config: dict = None, persistence_path: str = None):
        self.config = config or {}
        self.persistence_path = persistence_path or Path("./consensus_weights.json")
        self.current_weights = self.DEFAULT_WEIGHTS.copy()
        self.performance_history: Dict[str, List[ModulePerformance]] = {}

        # Önceki ağırlıkları yükle
        self._load_weights()

    def _load_weights(self):
        """Kaydedilmiş ağırlıkları yükle"""
        if self.persistence_path.exists():
            try:
                with open(self.persistence_path, "r") as f:
                    data = json.load(f)
                    self.current_weights = data.get("weights", self.DEFAULT_WEIGHTS.copy())
                    logger.info("weights_loaded_from_persistence", weights=self.current_weights)
            except Exception as e:
                logger.warning("failed_to_load_weights", error=str(e))
                self.current_weights = self.DEFAULT_WEIGHTS.copy()

    def _save_weights(self):
        """Ağırlıkları kaydet"""
        try:
            with open(self.persistence_path, "w") as f:
                json.dump({"weights": self.current_weights}, f, indent=2)
                logger.info("weights_saved", weights=self.current_weights)
        except Exception as e:
            logger.error("failed_to_save_weights", error=str(e))

    def update_weights_from_performance(
        self, performance_data: Dict[str, ModulePerformance]
    ) -> Dict[str, float]:
        """
        Modüllerin performansına göre ağırlıkları güncelle

        Args:
            performance_data: {
                'Touche': ModulePerformance,
                'Fundamental': ModulePerformance,
                'News': ModulePerformance,
            }

        Returns:
            Güncellenmiş ağırlıklar
        """
        if not performance_data:
            logger.warning("no_performance_data_provided")
            return self.current_weights.copy()

        # Performans ortalamalarını hesapla
        weight_adjustments = {}
        total_accuracy = 0
        accuracy_details = {}

        for module_name, perf in performance_data.items():
            # 7 günlük accuracy'ye ağırlık ver (daha yeni veri)
            weighted_accuracy = (perf.accuracy_7d * 0.6) + (perf.accuracy_30d * 0.4)
            accuracy_details[module_name] = round(weighted_accuracy, 3)
            total_accuracy += weighted_accuracy

        if total_accuracy == 0:
            logger.warning("all_modules_have_zero_accuracy")
            return self.current_weights.copy()

        # Normalize edilmiş accuracy
        normalized_accuracy = {
            name: acc / total_accuracy for name, acc in accuracy_details.items()
        }

        # Ağırlık ayarla (gradual transition: 80% eski, 20% yeni)
        new_weights = {}
        for module_name in self.current_weights.keys():
            old_weight = self.current_weights[module_name]
            normalized_acc = normalized_accuracy.get(module_name, 1.0 / len(self.current_weights))

            # 20% weight adjustment per update
            new_weight = (old_weight * 0.8) + (normalized_acc * 0.2)

            # Bounds kontrolü
            min_w, max_w = self.MIN_MAX_WEIGHTS.get(module_name, (0.0, 1.0))
            new_weight = max(min_w, min(max_w, new_weight))

            new_weights[module_name] = new_weight

        # Normalize to 1.0
        total_weight = sum(new_weights.values())
        new_weights = {k: v / total_weight for k, v in new_weights.items()}

        self.current_weights = new_weights
        self._save_weights()

        logger.info(
            "weights_updated",
            old_weights=self.DEFAULT_WEIGHTS,
            new_weights={k: round(v, 3) for k, v in new_weights.items()},
            accuracy_scores={k: round(v, 3) for k, v in accuracy_details.items()},
        )

        return new_weights

    def get_current_weights(self) -> Dict[str, float]:
        """Mevcut ağırlıkları al"""
        return self.current_weights.copy()


class ConflictResolutionEngine:
    """
    Modülerin çelişki yaptığı durumlarda optimal karar ver

    Senaryo:
    - Touche BULLISH, Fundamental BEARISH, News NEUTRAL
    → Karar mekanizması devreye girer
    """

    CONFLICT_RESOLUTION_STRATEGIES = {
        # (Touche, Fundamental, News) → (Action, Confidence Penalty)
        ("BULLISH", "BEARISH", "NEUTRAL"): ("WAIT", -0.2),  # Conflicting signals
        ("BULLISH", "BEARISH", "BULLISH"): ("BUY", 0.0),  # Majority wins
        ("BULLISH", "BEARISH", "BEARISH"): ("SELL", 0.0),  # Majority wins
        ("BEARISH", "BULLISH", "NEUTRAL"): ("WAIT", -0.2),
        ("BEARISH", "BULLISH", "BEARISH"): ("SELL", 0.0),
        ("BEARISH", "BULLISH", "BULLISH"): ("BUY", 0.0),
        ("NEUTRAL", "NEUTRAL", "NEUTRAL"): ("HOLD", 0.0),
    }

    def resolve_conflict(
        self,
        touche_signal: str,
        fundamental_signal: str,
        news_signal: str,
        weights: Dict[str, float],
    ) -> Dict:
        """
        Çelişkili sinyalleri çöz

        Args:
            touche_signal: BULLISH | BEARISH | NEUTRAL
            fundamental_signal: BULLISH | BEARISH | NEUTRAL
            news_signal: BULLISH | BEARISH | NEUTRAL
            weights: Modül ağırlıkları

        Returns:
            {
                'action': str,              # BUY, SELL, HOLD, WAIT
                'confidence': float,        # 0-1
                'resolution_method': str,   # MAJORITY, WEIGHTED, STRATEGY
                'explanation': str,
            }
        """
        # Adım 1: Basit kurallı çelişki kontrolü
        signal_tuple = (touche_signal, fundamental_signal, news_signal)

        if signal_tuple in self.CONFLICT_RESOLUTION_STRATEGIES:
            action, confidence_penalty = self.CONFLICT_RESOLUTION_STRATEGIES[signal_tuple]
            logger.info(
                "conflict_resolved_by_strategy",
                signals=signal_tuple,
                action=action,
            )
            return {
                "action": action,
                "confidence": round(0.7 + confidence_penalty, 2),
                "resolution_method": "STRATEGY",
                "explanation": f"Strategy matched for {signal_tuple}",
            }

        # Adım 2: Weighted karar
        return self._resolve_by_weight(touche_signal, fundamental_signal, news_signal, weights)

    def _resolve_by_weight(
        self,
        touche_signal: str,
        fundamental_signal: str,
        news_signal: str,
        weights: Dict[str, float],
    ) -> Dict:
        """Ağırlık bazlı çelişki çözümü"""
        # Sinyalleri skora dönüştür
        signal_scores = {
            "BULLISH": 1.0,
            "NEUTRAL": 0.0,
            "BEARISH": -1.0,
        }

        # Ağırlıklı ortalama
        touche_score = signal_scores.get(touche_signal, 0) * weights.get("Touche", 0.5)
        fundamental_score = signal_scores.get(fundamental_signal, 0) * weights.get(
            "Fundamental", 0.35
        )
        news_score = signal_scores.get(news_signal, 0) * weights.get("News", 0.15)

        weighted_sum = touche_score + fundamental_score + news_score
        total_weight = sum(weights.values())
        final_score = weighted_sum / total_weight if total_weight > 0 else 0

        # Score'dan action'a dönüştür
        if final_score > 0.3:
            action = "BUY"
            confidence = min(1.0, final_score)
        elif final_score < -0.3:
            action = "SELL"
            confidence = min(1.0, abs(final_score))
        else:
            action = "HOLD"
            confidence = 1.0 - abs(final_score)

        logger.info(
            "conflict_resolved_by_weight",
            signals=(touche_signal, fundamental_signal, news_signal),
            final_score=round(final_score, 3),
            action=action,
        )

        return {
            "action": action,
            "confidence": round(confidence, 2),
            "resolution_method": "WEIGHTED",
            "explanation": f"Weighted avg: {round(final_score, 2)}",
        }


class PerformanceFeedbackLoop:
    """
    Modüllerin performansını takip et ve learning döngüsü oluştur

    Track:
    - Signal accuracy (trade sonucuyla karşılaştır)
    - Win/loss rate
    - False positives/negatives
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.trade_history: List[Dict] = []
        self.module_stats: Dict[str, Dict] = {}

    def record_trade_outcome(
        self,
        trade_id: str,
        module_signals: Dict[str, str],
        consensus_action: str,
        entry_price: float,
        exit_price: float,
        profit_loss_pct: float,
    ) -> Dict:
        """
        Trade sonucunu kaydet ve modül performansını güncelle

        Args:
            trade_id: Trade kimliği
            module_signals: {'Touche': 'BULLISH', 'Fundamental': 'NEUTRAL', ...}
            consensus_action: 'BUY' | 'SELL' | 'HOLD'
            entry_price: Entry fiyatı
            exit_price: Exit fiyatı
            profit_loss_pct: Kar/zarar yüzdesi

        Returns:
            Güncellenen stats
        """
        # Trade sonucu
        is_profitable = profit_loss_pct > 0

        # Her modülün doğruluğunu hesapla
        module_accuracy = {}
        for module_name, signal in module_signals.items():
            # BUY signal + profitable → correct
            # SELL signal + loss → correct (risk yönetim)
            if (signal == "BULLISH" and is_profitable) or (
                signal == "BEARISH" and not is_profitable
            ):
                module_accuracy[module_name] = 1.0  # Correct
            elif signal == "NEUTRAL":
                module_accuracy[module_name] = 0.5  # Neutral
            else:
                module_accuracy[module_name] = 0.0  # Incorrect

        # Module stats güncelle
        for module_name, accuracy in module_accuracy.items():
            if module_name not in self.module_stats:
                self.module_stats[module_name] = {
                    "total_signals": 0,
                    "correct_signals": 0,
                    "win_rate": 0.0,
                    "accuracy_7d": 0.0,
                    "accuracy_30d": 0.0,
                }

            stats = self.module_stats[module_name]
            stats["total_signals"] += 1
            stats["correct_signals"] += accuracy
            stats["win_rate"] = stats["correct_signals"] / stats["total_signals"]

        # Trade history ekle
        self.trade_history.append({
            "timestamp": datetime.now().isoformat(),
            "trade_id": trade_id,
            "action": consensus_action,
            "pnl_pct": profit_loss_pct,
            "module_accuracy": module_accuracy,
        })

        logger.info(
            "trade_outcome_recorded",
            trade_id=trade_id,
            pnl_pct=round(profit_loss_pct, 2),
            module_accuracy={k: round(v, 2) for k, v in module_accuracy.items()},
        )

        return {
            "trade_id": trade_id,
            "module_accuracy": module_accuracy,
            "updated_module_stats": self.get_module_stats(),
        }

    def calculate_7d_30d_accuracy(self) -> Dict[str, ModulePerformance]:
        """
        7 gün ve 30 günlük accuracy hesapla

        Returns:
            {
                'Touche': ModulePerformance,
                'Fundamental': ModulePerformance,
                ...
            }
        """
        now = datetime.now(timezone.utc)
        cutoff_7d = now - timedelta(days=7)
        cutoff_30d = now - timedelta(days=30)

        performance_data = {}

        for module_name in self.module_stats.keys():
            # 7 günlük
            trades_7d = [
                t
                for t in self.trade_history
                if datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc) > cutoff_7d
            ]
            accuracy_7d = 0.0
            if trades_7d:
                acc_sum = sum(t["module_accuracy"].get(module_name, 0) for t in trades_7d)
                accuracy_7d = acc_sum / len(trades_7d)

            # 30 günlük
            trades_30d = [
                t
                for t in self.trade_history
                if datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc) > cutoff_30d
            ]
            accuracy_30d = 0.0
            if trades_30d:
                acc_sum = sum(t["module_accuracy"].get(module_name, 0) for t in trades_30d)
                accuracy_30d = acc_sum / len(trades_30d)

            stats = self.module_stats.get(module_name, {})
            performance_data[module_name] = ModulePerformance(
                module_name=module_name,
                accuracy_7d=accuracy_7d,
                accuracy_30d=accuracy_30d,
                win_rate=stats.get("win_rate", 0.0),
                false_positive_rate=0.0,  # TODO: Calculate
                last_updated=int(now.timestamp()),
            )

        return performance_data

    def get_module_stats(self) -> Dict:
        """Mevcut modül istatistiklerini al"""
        return self.module_stats.copy()
