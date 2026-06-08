"""
AEGIS Holding — Unified Optimizer

Touche AI'ın şu iki optimizasyonu birleştirir:
1. Ağırlık Optimizasyonu (phases'ın katkısını optimize et)
2. Parametre Optimizasyonu (RSI, MACD, Fibonacci vb. optimize et)

Mantık:
- Her işlemden öğren (kazanç → ağırlıkları güçlendir, zarar → parametreleri düzelt)
- Belirli aralıklarda (30 işlem) ağırlıkları ve parametreleri grid/bayesian search ile optimize et
- Optimize edilen ayarları YAML'a kaydet ve gelecek işlemlerde kullan
"""
import logging
from typing import Dict, List, Optional, Tuple, Callable, Any
from datetime import datetime, timezone
import yaml
import numpy as np
from dataclasses import dataclass, field
import copy
import os

# COMPONENT 3: Optuna optimizer imports
try:
    import optuna
    from optuna.samplers import TPESampler
    from optuna.pruners import MedianPruner
except Exception:  # pragma: no cover - optional local dependency
    optuna = None  # type: ignore[assignment]
    TPESampler = None  # type: ignore[assignment]
    MedianPruner = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """İşlem kaydı"""
    entry_price: float
    exit_price: float
    pnl: float
    winning_phases: List[int] = field(default_factory=list)
    losing_phases: List[int] = field(default_factory=list)
    rsi_at_entry: float = 0.0
    macd_at_entry: float = 0.0
    volatility: float = 0.0
    fibonacci_level: float = 0.618
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_winning: bool = field(init=False)

    # PHASE 1: Trade Log Enhancement - Stage Signals
    stage_signals: Dict[int, float] = field(default_factory=dict)  # Signal strength per phase (0-1)
    entry_reason: str = ""  # Which phase triggered entry
    exit_reason: str = ""   # Which phase triggered exit

    def __post_init__(self):
        self.is_winning = self.pnl > 0


class UnifiedOptimizer:
    """
    Tek bir unified optimizer interface'i sağlar:
    - Weight optimization: Phase ağırlıkları optimize et
    - Parameter optimization: Step parametreleri optimize et
    - Trade learning: Her işlemden öğren
    - Periodic optimization: Belirli aralıklarla full optimization yap
    """

    def __init__(self, backtest_fn: Optional[Callable] = None, learning_rate: float = 0.01):
        """
        Args:
            backtest_fn: Parametrelerle backtest yapan fonksiyon
            learning_rate: Öğrenme hızı (0.01 = 1%)
        """
        self.backtest_fn = backtest_fn
        self.learning_rate = learning_rate

        # Phase Weights (7 faz)
        self.weights = {
            1: 0.15,  # Likidite
            2: 0.20,  # Piyasa Yapısı
            3: 0.20,  # Bölgeler
            4: 0.15,  # Teyit
            5: 0.15,  # Zamanlama
            6: 0.05,  # Risk
            7: 0.10,  # Makro
        }

        # Module-level weights for feedback loop updates.
        self.module_weights = {
            "touche": 0.50,
            "fundamental": 0.35,
            "news": 0.15,
        }

        # Phase-Specific Parameters for ALL 7 Phases
        self.phase_params = {
            # Phase 1: Likidite (Liquidity)
            1: {
                "swing_lookback": 3,
                "sweep_threshold": 0.01,
                "min_volume_factor": 1.0,
                "spread_threshold": 0.02,
            },
            # Phase 2: Piyasa Yapısı (Market Structure)
            2: {
                "structure_strength": 0.6,
                "trend_strength": 0.6,
                "ma_period": 20,
                "breakout_confirmation": 1,
            },
            # Phase 3: Bölgeler (Fibonacci Zones)
            3: {
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "rsi_period": 14,
                "fibonacci_levels": "0.382,0.5,0.618",
                "zone_confluence": 2,
            },
            # Phase 4: Teyit (Confirmation)
            4: {
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "volume_ratio": 1.3,
                "confirmation_candles": 1,
                "confirmation_strength": 0.7,
            },
            # Phase 5: Zamanlama (Timing)
            5: {
                "stochrsi_period": 14,
                "stochrsi_oversold": 25,
                "stochrsi_overbought": 75,
                "candle_weight": 1.0,
                "momentum_threshold": 0.5,
            },
            # Phase 6: Risk (Risk Management)
            6: {
                "atr_multiplier": 1.5,
                "rr_min": 2.0,
                "max_drawdown": 5.0,
                "stop_loss_pct": 2.0,
                "position_size_adj": 1.0,
            },
            # Phase 7: Makro (Macro Conditions)
            7: {
                "vix_threshold": 20.0,
                "dxy_threshold": 105.0,
                "correlation_threshold": 0.7,
                "btc_dominance_min": 50.0,
                "market_regime": "normal",
            },
        }

        # Phase-wise Parameter Ranges for Grid Search
        self.param_ranges = {
            # Phase 1: Likidite (Liquidity)
            1: {
                "swing_lookback": [2, 3, 4, 5],
                "sweep_threshold": [0.005, 0.01, 0.02],
                "min_volume_factor": [0.5, 0.75, 1.0, 1.25],
            },
            # Phase 2: Piyasa Yapısı (Market Structure)
            2: {
                "structure_strength": [0.6, 0.7, 0.8],
                "trend_strength": [0.5, 0.6, 0.7, 0.8],
                "ma_period": [15, 20, 25, 30],
                "breakout_confirmation": [0, 1, 2],
            },
            # Phase 3: Bölgeler (Fibonacci Zones)
            3: {
                "rsi_oversold": [20, 25, 30, 35, 40],
                "rsi_overbought": [60, 65, 70, 75, 80],
                "rsi_period": [10, 12, 14, 16],
                "fibonacci_levels": ["0.382,0.5,0.618", "0.236,0.5,0.786"],
                "zone_confluence": [1, 2, 3],
            },
            # Phase 4: Teyit (Confirmation)
            4: {
                "macd_fast": [8, 10, 12, 14],
                "macd_slow": [20, 24, 26, 30],
                "macd_signal": [7, 9, 11],
                "volume_ratio": [1.2, 1.3, 1.5, 2.0],
                "confirmation_candles": [0, 1, 2, 3],
            },
            # Phase 5: Zamanlama (Timing)
            5: {
                "stochrsi_period": [7, 14, 21],
                "stochrsi_oversold": [20, 25, 30],
                "stochrsi_overbought": [70, 75, 80],
                "candle_weight": [0.5, 1.0, 1.5],
                "momentum_threshold": [0.3, 0.5, 0.7],
            },
            # Phase 6: Risk (Risk Management)
            6: {
                "atr_multiplier": [1.0, 1.5, 2.0, 2.5],
                "rr_min": [1.5, 2.0, 2.5],
                "max_drawdown": [3.0, 5.0, 7.0, 10.0],
                "stop_loss_pct": [1.0, 1.5, 2.0, 2.5],
                "position_size_adj": [0.8, 1.0, 1.2],
            },
            # Phase 7: Makro (Macro Conditions)
            7: {
                "vix_threshold": [20, 25, 30],
                "dxy_threshold": [103, 105, 107],
                "correlation_threshold": [0.5, 0.6, 0.7, 0.8],
                "btc_dominance_min": [45.0, 50.0, 55.0],
            },
        }

        # Trade History
        self.trade_history: List[TradeRecord] = []
        self.winning_trades: List[TradeRecord] = []
        self.losing_trades: List[TradeRecord] = []

        # Weight Ranges for All 7 Phases (for weight optimization)
        self.weight_ranges = {
            1: np.linspace(0.05, 0.25, 5),  # Phase 1: 5%-25%
            2: np.linspace(0.05, 0.25, 5),  # Phase 2: 5%-25%
            3: np.linspace(0.10, 0.30, 5),  # Phase 3: 10%-30%
            4: np.linspace(0.05, 0.25, 5),  # Phase 4: 5%-25%
            5: np.linspace(0.10, 0.25, 5),  # Phase 5: 10%-25%
            6: np.linspace(0.02, 0.15, 5),  # Phase 6: 2%-15%
            7: np.linspace(0.05, 0.20, 5),  # Phase 7: 5%-20%
        }

        # Statistics
        self.stats = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "optimization_count": 0,
            "last_optimization": None,
        }

        # Optimization History
        self.optimization_history: List[Dict[str, Any]] = []

    def record_trade(self, trade: TradeRecord) -> None:
        """
        İşlemi kaydet ve istatistikleri güncelle.

        Args:
            trade: İşlem kaydı
        """
        # PHASE 1: Backward compatibility - ensure all fields present
        trade = self._migrate_trade_record(trade)

        self.trade_history.append(trade)

        if trade.is_winning:
            self.winning_trades.append(trade)
            # Kazanç işleminden öğren: winning phases'ın ağırlığını artır
            self._learn_from_win(trade)
        else:
            self.losing_trades.append(trade)
            # Zarar işleminden öğren: parametreleri optimize et
            self._learn_from_loss(trade)

        # İstatistikleri güncelle
        self._update_stats()

        # SORUN 10: Her islem sonunda geri besleme dongusunu calistir.
        module_scores = self._extract_module_scores_from_trade(trade)
        self.update_weights_from_trade(trade.pnl, module_scores)

        logger.info(
            "trade_recorded",
            pnl=trade.pnl,
            is_winning=trade.is_winning,
            total_trades=len(self.trade_history),
        )

        # Her 30 işlemde bir full optimization yap
        if len(self.trade_history) % 30 == 0:
            self.optimize_periodic()

    def update_weights_from_trade(self, pnl: float, module_scores: Dict[str, float]) -> Dict[str, float]:
        """
        Geri besleme dongusu ile module agirliklarini guncelle.

        Kural:
        - Kazanan modul agirligi +%1
        - Kaybeden modul agirligi -%0.5
        """
        if not module_scores:
            return self.module_weights

        valid_scores = {
            k: float(v)
            for k, v in module_scores.items()
            if k in self.module_weights
        }
        if not valid_scores:
            return self.module_weights

        winner = max(valid_scores, key=valid_scores.get)
        loser = min(valid_scores, key=valid_scores.get)

        self.module_weights[winner] *= 1.01
        self.module_weights[loser] *= 0.995

        # Negatif agirliklari engelle ve normalize et.
        for module in self.module_weights:
            self.module_weights[module] = max(self.module_weights[module], 0.01)

        total = sum(self.module_weights.values())
        if total > 0:
            self.module_weights = {
                k: v / total for k, v in self.module_weights.items()
            }

        logger.info(
            "module_weights_updated_from_trade",
            pnl=round(float(pnl), 4),
            winner=winner,
            loser=loser,
            module_weights={k: round(v, 4) for k, v in self.module_weights.items()},
        )

        return self.module_weights

    def _extract_module_scores_from_trade(self, trade: TradeRecord) -> Dict[str, float]:
        """Trade kaydindan module-bazli skor haritasi uret."""
        scores: Dict[str, float] = {"touche": 0.0, "fundamental": 0.0, "news": 0.0}

        # If caller already passed module keys in stage_signals, use them directly.
        for key in ("touche", "fundamental", "news"):
            if key in trade.stage_signals:
                try:
                    scores[key] = float(trade.stage_signals[key])
                except Exception:
                    pass

        # Fallback mapping from phase-level signals.
        phase_scores = trade.stage_signals or {}
        touche_phases = [phase_scores.get(i) for i in [1, 2, 3, 4, 5] if phase_scores.get(i) is not None]
        if touche_phases and scores["touche"] == 0.0:
            scores["touche"] = float(sum(touche_phases) / len(touche_phases))

        if scores["fundamental"] == 0.0 and phase_scores.get(7) is not None:
            scores["fundamental"] = float(phase_scores.get(7))

        if scores["news"] == 0.0 and phase_scores.get(6) is not None:
            # News skoru yoksa phase-6'yi zayif proxy olarak kullan.
            scores["news"] = float(phase_scores.get(6))

        return scores

    def _learn_from_win(self, trade: TradeRecord) -> None:
        """
        Kazanan işlemden öğren:
        - Winning phases'ın ağırlığını artır
        - Losing phases'ın ağırlığını azalt
        """
        for phase_id in trade.winning_phases:
            if phase_id in self.weights:
                self.weights[phase_id] *= (1.0 + self.learning_rate)

        for phase_id in trade.losing_phases:
            if phase_id in self.weights:
                self.weights[phase_id] *= (1.0 - self.learning_rate * 0.5)

        # Ağırlıkları normalize et (toplam = 1.0)
        total_weight = sum(self.weights.values())
        self.weights = {k: v / total_weight for k, v in self.weights.items()}

        logger.info(
            "learned_from_win",
            winning_phases=trade.winning_phases,
            new_weights=self.weights,
        )

    def _learn_from_loss(self, trade: TradeRecord) -> None:
        """
        Zararlı işlemden öğren:
        - Nedensal parametreleri ayarla
        - Losing phases'ın ağırlığını azalt
        """
        # Zarar nedenini analiz et ve kritik parametreleri belirle
        critical_phases = self._identify_critical_phases(trade)

        for phase_id in critical_phases:
            # Bu phase'in parametrelerini ince ayar yap
            self._fine_tune_phase_params(phase_id, trade)

            # Bu phase'in ağırlığını azalt
            if phase_id in self.weights:
                self.weights[phase_id] *= (1.0 - self.learning_rate)

        # Ağırlıkları normalize et
        total_weight = sum(self.weights.values())
        self.weights = {k: v / total_weight for k, v in self.weights.items()}

        logger.info(
            "learned_from_loss",
            critical_phases=critical_phases,
            new_weights=self.weights,
        )

    def _identify_critical_phases(self, trade: TradeRecord) -> List[int]:
        """Zarar işleminde hangi phases'ın sorumlu olduğunu tespit et"""
        critical = []

        # RSI parametreleri zayıfsa → Phase 3 (Bölgeler)
        if trade.rsi_at_entry < 40:
            critical.append(3)

        # MACD zayıfsa → Phase 5 (Zamanlama)
        if abs(trade.macd_at_entry) < 0.001:
            critical.append(5)

        # Volatilite yüksekse → Phase 6 (Risk)
        if trade.volatility > 3.0:
            critical.append(6)

        # Trend zayıfsa → Phase 2 (Piyasa Yapısı)
        if trade.volatility < 1.0:
            critical.append(2)

        # Likidite sorunu olabilir → Phase 1
        if abs(trade.entry_price - trade.exit_price) < 0.001:
            critical.append(1)

        return critical if critical else [4, 5]  # Default: Teyit ve Zamanlama

    def _fine_tune_phase_params(self, phase_id: int, trade: TradeRecord) -> None:
        """
        Phase'ın parametrelerini fine-tune yap.

        Basit heuristic:
        - Boundary değerleri ayarla (RSI, MACD, vb.)
        - Confirmation şartlarını sıkılaştır
        """
        if phase_id == 3:  # Bölgeler - RSI
            current_rsi_oversold = self.phase_params[3]["rsi_oversold"]
            # Trade'deki RSI'ya doğru hareket et
            if trade.rsi_at_entry > current_rsi_oversold:
                self.phase_params[3]["rsi_oversold"] = min(
                    current_rsi_oversold + 1,
                    40
                )

        elif phase_id == 5:  # Zamanlama - MACD
            # MACD parametrelerini hafif ayarla
            if abs(trade.macd_at_entry) < 0.001:
                self.phase_params[5].setdefault("macd_fast", 12)
                self.phase_params[5]["macd_fast"] = max(
                    self.phase_params[5]["macd_fast"] - 1,
                    8
                )

        elif phase_id == 6:  # Risk - Stop Loss
            if trade.volatility > 3.0:
                self.phase_params[6]["stop_loss_pct"] = min(
                    self.phase_params[6]["stop_loss_pct"] + 0.5,
                    3.0
                )

    def optimize_periodic(self, optimization_type: str = "light") -> Dict[str, Any]:
        """
        Belirli aralıklarla (örn. 30 işlem) full optimization yap.

        Args:
            optimization_type: "light" (Optuna - kritik fazlar) veya "heavy" (tüm 7 faz)

        Returns:
            Optimizasyon sonuçları
        """
        logger.info(f"Periodic optimization started: {optimization_type}")

        # En son 10 zararlı işlemi al
        recent_losses = self.losing_trades[-10:]
        if not recent_losses:
            logger.warning("No losing trades to optimize from")
            return {"status": "no_data"}

        best_params = self._deep_copy_params(self.phase_params)
        best_score = -999.0

        if optimization_type == "light":
            # COMPONENT 3: Optuna - kritik fazları optimize et (50 trial)
            critical_phases = self._identify_critical_phases_batch(recent_losses)

            for phase_id in sorted(critical_phases.keys()):
                phase_best_params, phase_score = self._create_optuna_study_per_phase(
                    phase_id=phase_id,
                    loss_trades=recent_losses,
                    n_trials=50,  # Hızlı optimizasyon
                )

                if phase_best_params:
                    best_params[phase_id].update(phase_best_params)

                if phase_score > best_score:
                    best_score = phase_score

        else:
            # COMPONENT 3: Heavy optimization - tüm 7 fazı optimize et (100 trial)
            for phase_id in range(1, 8):
                phase_best_params, phase_score = self._create_optuna_study_per_phase(
                    phase_id=phase_id,
                    loss_trades=recent_losses,
                    n_trials=100,  # Daha kapsamlı optimizasyon
                )

                if phase_best_params:
                    best_params[phase_id].update(phase_best_params)

                if phase_score > best_score:
                    best_score = phase_score

        # En iyi parametreleri kaydet
        self.phase_params = best_params
        self.stats["optimization_count"] += 1

        result = {
            "optimization_type": optimization_type,
            "optimizer": "optuna_tpe",  # Mark as Optuna-based
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "best_score": best_score,
            "trades_analyzed": len(recent_losses),
            "new_params": best_params,
        }

        self.optimization_history.append(result)
        self.stats["last_optimization"] = result["timestamp"]

        # COMPONENT 1: After optimization, calculate and log attribution
        self.calculate_and_log_attribution(output_dir="./attribution_logs")

        logger.info("periodic_optimization_complete", result=result)
        return result

    def calculate_and_log_attribution(self, output_dir: str = "./attribution_logs") -> Optional[Dict]:
        """
        COMPONENT 1 & 2: Calculate phase attribution from trade history and save report.
        Called automatically after optimize_periodic().

        Args:
            output_dir: Directory to save YAML reports

        Returns:
            Attribution report dict or None if calculation fails
        """
        if not self.trade_history:
            return None

        try:
            os.makedirs(output_dir, exist_ok=True)

            from .attribution_logger import AttributionLogger

            logger_instance = AttributionLogger(min_trades_for_correlation=20)
            report = logger_instance.calculate_attribution(self.trade_history)

            # YAML raporunu kaydet (timestamp ile)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(output_dir, f"attribution_report_{timestamp}.yaml")
            logger_instance.save_report(report, filepath)

            logger.info(
                "attribution_logged",
                report_file=filepath,
                phases_analyzed=len(report.phase_attribution),
                total_trades=report.total_trades_analyzed,
            )

            return {
                "filepath": filepath,
                "total_trades": report.total_trades_analyzed,
                "phase_attribution": report.phase_attribution,
                "recommendations": report.recommendations,
            }

        except Exception as e:
            logger.error(f"Attribution logging hatası: {e}")
            return None

    def _grid_search_params(self, loss_trades: List[TradeRecord]) -> Tuple[Dict, float]:
        """
        Adaptif grid search - tüm 7 fazın parametrelerini optimize et.

        Stratejisi:
        1. Zararlı işlemlerden hangi fazların sorumlu olduğunu tespit et
        2. O fazların parametrelerini grid search ile test et
        3. Kombinatoryal patlamayı önlemek için seçici arama yap
        """
        best_params = self._deep_copy_params(self.phase_params)
        best_score = -999.0
        tested_combinations = 0

        # Hangi fazlar sorun yarattı tespit et
        critical_phases = self._identify_critical_phases_batch(loss_trades)
        logger.info(f"Critical phases identified: {critical_phases}")

        # Her faz için ayrı ayrı optimize et (kombinatoryal patlama engelle)
        for phase_id in sorted(critical_phases.keys()):
            phase_score = self._optimize_phase(
                phase_id,
                loss_trades,
                best_params,
            )
            tested_combinations += phase_score.get("tested", 0)

            if phase_score.get("score", -999.0) > best_score:
                best_score = phase_score["score"]
                logger.info(
                    f"Phase {phase_id} optimized",
                    score=phase_score["score"],
                    tested=phase_score["tested"],
                )

        logger.info(
            "full_grid_search_complete",
            tested_combinations=tested_combinations,
            best_score=best_score,
            critical_phases=list(critical_phases.keys()),
        )

        return best_params, best_score

    def _create_optuna_study_per_phase(
        self,
        phase_id: int,
        loss_trades: List[TradeRecord],
        n_trials: int = 100,
    ) -> Tuple[Dict[str, float], float]:
        """
        COMPONENT 3: Optuna TPE sampler ile tek bir aşama için parametreleri optimize et.

        Args:
            phase_id: Optimize edilecek aşama (1-7)
            loss_trades: Değerlendirilecek trade geçmişi
            n_trials: Çalıştırılacak maksimum trial sayısı

        Returns:
            (best_params_dict, best_score)
        """
        param_ranges = self.param_ranges.get(phase_id, {})
        if not param_ranges:
            return {}, 0.0

        if optuna is None:
            fallback_params = {
                name: values[0]
                for name, values in param_ranges.items()
                if isinstance(values, list) and values
            }
            return fallback_params, self._estimate_score_for_phase(phase_id, loss_trades, fallback_params)

        # Trial objective fonksiyonu tanımla
        def trial_objective(trial):
            """Bu aşama için parametre kombinasyonunu değerlendir"""
            params = {}

            # Aralıklara göre parametreleri öner
            for param_name, values in param_ranges.items():
                if isinstance(values[0], (int, float)):
                    # Sayısal parametre
                    if isinstance(values[0], int):
                        params[param_name] = trial.suggest_int(
                            param_name,
                            int(min(values)),
                            int(max(values)),
                        )
                    else:
                        params[param_name] = trial.suggest_float(
                            param_name,
                            float(min(values)),
                            float(max(values)),
                        )
                else:
                    # Kategorik parametre (örn: string)
                    params[param_name] = trial.suggest_categorical(
                        param_name,
                        values
                    )

            # Bu parametre kombinasyonunu değerlendir
            score = self._estimate_score_for_phase(
                phase_id,
                loss_trades,
                params
            )

            return score

        # Optuna study'si oluştur TPE sampler ile
        sampler = TPESampler(seed=42)
        pruner = MedianPruner()
        study = optuna.create_study(
            sampler=sampler,
            pruner=pruner,
            direction="maximize"
        )

        # Optimize et
        study.optimize(
            trial_objective,
            n_trials=n_trials,
            show_progress_bar=False,
        )

        # Best parametreleri çıkart
        best_trial = study.best_trial
        best_params = best_trial.params
        best_score = best_trial.value

        logger.info(
            "optuna_phase_optimization_complete",
            phase_id=phase_id,
            best_score=best_score,
            n_trials=len(study.trials),
            best_params=best_params,
        )

        return best_params, best_score

    def _estimate_score_for_params(self,
                                   trades: List[TradeRecord],
                                   rsi_oversold: float,
                                   macd_fast: float) -> float:
        """
        Parametreler için tahmini Sharpe ratio hesapla.

        Basit heuristic: parametreler loss trade'lerin nedenlerini ne kadar iyi
        açıklıyor?
        """
        score = 0.0

        for trade in trades:
            # RSI parametresi iyiyse
            if abs(trade.rsi_at_entry - rsi_oversold) < 10:
                score += 1.0
            else:
                score -= 0.5

            # MACD parametresi iyiyse
            if 8 <= macd_fast <= 14:
                score += 0.5

        avg_score = score / max(len(trades), 1)
        return max(-1.0, avg_score)

    def _deep_copy_params(self, params: Dict) -> Dict:
        """Parametreleri deep copy yap"""
        return copy.deepcopy(params)

    def _identify_critical_phases_batch(self, loss_trades: List[TradeRecord]) -> Dict[int, float]:
        """
        Zararlı işlemler grubundan hangi fazların sorumlu olduğunu tespit et.

        Returns: {phase_id: frequency_score}
        """
        phase_scores = {i: 0.0 for i in range(1, 8)}

        for trade in loss_trades:
            # RSI zayıfsa → Phase 3 (Bölgeler)
            if trade.rsi_at_entry < 40 or trade.rsi_at_entry > 80:
                phase_scores[3] += 1.5

            # MACD zayıfsa → Phase 5 (Zamanlama)
            if abs(trade.macd_at_entry) < 0.001:
                phase_scores[5] += 1.5

            # MACD güçlüyse ama fiyat hareket etmediyse → Phase 4 (Teyit)
            if abs(trade.macd_at_entry) > 0.01 and abs(trade.entry_price - trade.exit_price) < 0.001:
                phase_scores[4] += 1.0

            # Volatilite yüksekse → Phase 6 (Risk)
            if trade.volatility > 3.0:
                phase_scores[6] += 1.5

            # Volatilite düşükse → Phase 2 (Piyasa Yapısı)
            if trade.volatility < 1.0:
                phase_scores[2] += 1.0

            # Likidite sorunu olabilir → Phase 1
            if abs(trade.entry_price - trade.exit_price) < 0.001:
                phase_scores[1] += 1.0

            # Fibonacci seviyesi zayıfsa → Phase 3
            if abs(trade.fibonacci_level - 0.618) > 0.2:
                phase_scores[3] += 0.5

            # Makro koşullar zayıf olabilir → Phase 7
            # (Burada VIX/DXY data yoksa tahmin de yapabiliriz)
            phase_scores[7] += 0.5

        # Normalize et ve sıfırdan büyük olanları döndür
        return {k: v for k, v in phase_scores.items() if v > 0}

    def _optimize_phase(self, phase_id: int, loss_trades: List[TradeRecord],
                       params: Dict) -> Dict[str, Any]:
        """
        Bir fazın parametrelerini grid search ile optimize et.

        Args:
            phase_id: Faz numarası (1-7)
            loss_trades: Zararlı işlemler
            params: Mevcut parametreler

        Returns: {score, tested, best_params}
        """
        param_ranges = self.param_ranges.get(phase_id, {})
        if not param_ranges:
            return {"score": 0.0, "tested": 0}

        best_phase_params = params.get(phase_id, {}).copy()
        best_score = -999.0
        tested = 0

        # Phase'in parametrelerinin tüm kombinasyonlarını test et
        param_names = list(param_ranges.keys())
        param_values = [param_ranges[name] for name in param_names]

        # Kombinasyonlar çok fazlaysa (exponential) sample yap
        total_combinations = 1
        for values in param_values:
            total_combinations *= len(values)

        if total_combinations > 100:
            # Random sampling: max 50 kombinasyon test et
            import random
            combinations_to_test = []
            for _ in range(min(50, total_combinations)):
                combo = {}
                for param_name, values in zip(param_names, param_values):
                    combo[param_name] = random.choice(values)
                combinations_to_test.append(combo)
        else:
            # Tüm kombinasyonlar test et
            combinations_to_test = self._generate_combinations(param_names, param_values)

        # Her kombinasyonu test et
        for combo in combinations_to_test:
            tested += 1

            # Bu parametrelerle score hesapla
            score = self._estimate_score_for_phase(
                phase_id,
                loss_trades,
                combo,
            )

            if score > best_score:
                best_score = score
                best_phase_params.update(combo)

                logger.info(
                    f"phase_{phase_id}_improvement",
                    score=score,
                    params=combo,
                )

        params[phase_id] = best_phase_params
        return {"score": best_score, "tested": tested, "best_params": best_phase_params}

    def _generate_combinations(self, param_names: List[str],
                              param_values: List[List]) -> List[Dict]:
        """Tüm parametre kombinasyonlarını üret (Cartesian product)"""
        import itertools
        combinations = []
        for combo_values in itertools.product(*param_values):
            combo = dict(zip(param_names, combo_values))
            combinations.append(combo)
        return combinations

    def _estimate_score_for_phase(self, phase_id: int,
                                 loss_trades: List[TradeRecord],
                                 params: Dict[str, Any]) -> float:
        """
        Belirli bir fazın parametreleri için score hesapla.

        Stratejisi: Zararlı işlemler bu parametrelerle daha iyi olur muydu?
        """
        score = 0.0

        for trade in loss_trades:
            phase_match = 0.0

            if phase_id == 1:  # Likidite
                # Sweep threshold düşükse daha iyi catch eder
                if params.get("sweep_threshold", 0.01) < 0.015:
                    phase_match += 0.5
                if params.get("swing_lookback", 3) >= 3:
                    phase_match += 0.5

            elif phase_id == 2:  # Piyasa Yapısı
                # Düşük volatilitede structure_strength yüksek olmalı
                if trade.volatility < 1.0 and params.get("structure_strength", 0.6) > 0.6:
                    phase_match += 1.0

            elif phase_id == 3:  # Bölgeler (Fibonacci)
                # RSI boundary kontrolü
                rsi_oversold = params.get("rsi_oversold", 30)
                rsi_overbought = params.get("rsi_overbought", 70)
                if rsi_oversold <= trade.rsi_at_entry <= rsi_overbought:
                    phase_match += 1.0
                # Fibonacci seviyeleri
                fib_levels = params.get("fibonacci_levels", "0.382,0.5,0.618")
                if "0.618" in fib_levels or "0.5" in fib_levels:
                    phase_match += 0.5

            elif phase_id == 4:  # Teyit (MACD + Volume)
                # MACD parametreleri makul
                macd_fast = params.get("macd_fast", 12)
                macd_slow = params.get("macd_slow", 26)
                if 8 <= macd_fast <= 14 and 20 <= macd_slow <= 30:
                    phase_match += 0.5
                # Volume ratio yüksekse güçlü signal
                if params.get("volume_ratio", 1.3) >= 1.2:
                    phase_match += 0.5

            elif phase_id == 5:  # Zamanlama (StochRSI)
                # StochRSI oversold/overbought
                oversold = params.get("stochrsi_oversold", 25)
                overbought = params.get("stochrsi_overbought", 75)
                if 20 <= oversold <= 30 and 70 <= overbought <= 80:
                    phase_match += 1.0
                # Candle weight yüksekse öncelik
                if params.get("candle_weight", 1.0) >= 1.0:
                    phase_match += 0.5

            elif phase_id == 6:  # Risk (ATR + RR)
                # ATR multiplier yüksekse stop daha geniş
                if trade.volatility > 2.0 and params.get("atr_multiplier", 1.5) >= 1.5:
                    phase_match += 1.0
                # Risk/Reward düşük
                if params.get("rr_min", 2.0) >= 1.5:
                    phase_match += 0.5

            elif phase_id == 7:  # Makro
                # VIX/DXY heuristics (verisi yoksa neutral)
                if params.get("vix_threshold", 20) > 15:
                    phase_match += 0.3
                if params.get("dxy_threshold", 105) > 100:
                    phase_match += 0.3

            score += phase_match

        avg_score = score / max(len(loss_trades), 1)
        return max(-1.0, avg_score)

    def _update_stats(self) -> None:
        """İstatistikleri güncelle"""
        self.stats["total_trades"] = len(self.trade_history)
        self.stats["winning_trades"] = len(self.winning_trades)
        self.stats["losing_trades"] = len(self.losing_trades)
        self.stats["win_rate"] = (
            self.stats["winning_trades"] / self.stats["total_trades"] * 100
            if self.stats["total_trades"] > 0
            else 0.0
        )
        self.stats["total_pnl"] = sum(t.pnl for t in self.trade_history)
        self.stats["avg_pnl"] = (
            self.stats["total_pnl"] / self.stats["total_trades"]
            if self.stats["total_trades"] > 0
            else 0.0
        )

    def _migrate_trade_record(self, trade: TradeRecord) -> TradeRecord:
        """
        PHASE 1: Backward compatibility - ensure all fields present.
        Called for every recorded trade to handle old format trades.

        Args:
            trade: Trade record (may be from old format without stage_signals)

        Returns:
            Migrated trade record with all fields populated
        """
        if not hasattr(trade, 'stage_signals') or trade.stage_signals is None:
            trade.stage_signals = {}
        if not hasattr(trade, 'entry_reason') or trade.entry_reason is None:
            trade.entry_reason = "Unknown"
        if not hasattr(trade, 'exit_reason') or trade.exit_reason is None:
            trade.exit_reason = "Unknown"
        return trade

    def record_phase_signals(
        self,
        trade_or_phase_signals,
        phase_signals: Optional[Dict[int, float]] = None,
        entry_reason: str = "",
        exit_reason: str = ""
    ) -> None:
        """
        PHASE 1: Record phase signals for the last recorded trade.
        Called after trade is recorded but during attribution phase.

        Args:
            phase_signals: Dict mapping phase_id (1-7) to signal strength (0-1)
            entry_reason: Which phase triggered entry
            exit_reason: Which phase triggered exit
        """
        if isinstance(trade_or_phase_signals, TradeRecord):
            trade = trade_or_phase_signals
            signals = dict(phase_signals or {})
        elif len(self.trade_history) > 0:
            trade = self.trade_history[-1]
            signals = dict(trade_or_phase_signals or {})
        else:
            return

        if trade is not None:
            trade.stage_signals = signals
            trade.entry_reason = entry_reason
            trade.exit_reason = exit_reason

            logger.info(
                "phase_signals_recorded",
                entry_reason=entry_reason,
                exit_reason=exit_reason,
                phase_signals=signals,
            )

    def get_status(self) -> Dict[str, Any]:
        """Optimizer'ın mevcut durumunu döndür"""
        return {
            "weights": self.weights.copy(),
            "phase_params": self.phase_params.copy(),
            "stats": self.stats.copy(),
            "optimization_count": self.stats["optimization_count"],
            "last_optimization": self.stats["last_optimization"],
        }

    def save_config(self, filepath: str) -> None:
        """Optimize edilen ağırlıklar ve parametreleri YAML'a kaydet"""
        config = {
            "weights": {f"phase_{k}": v for k, v in self.weights.items()},
            "phase_parameters": {
                f"phase_{k}": {str(kk): vv for kk, vv in v.items()}
                for k, v in self.phase_params.items()
            },
            "statistics": self.stats,
            # PHASE 1: Add sample phase_signals from winning trades
            "phase_signals_log": {
                f"phase_{phase_id}": {
                    "sample_signals": [
                        t.stage_signals.get(phase_id, 0.0)
                        for t in self.winning_trades[-5:]  # Last 5 winning trades
                    ],
                    "avg_signal": float(np.mean([
                        t.stage_signals.get(phase_id, 0.0)
                        for t in self.winning_trades
                    ])) if self.winning_trades else 0.0,
                }
                for phase_id in range(1, 8)
            },
            "optimization_method": "optuna",  # Mark as Optuna (will be set when optimizing)
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        with open(filepath, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

        logger.info(f"Config saved to {filepath}")
        return config

    def load_config(self, filepath: str) -> None:
        """YAML'dan ayarları yükle"""
        try:
            with open(filepath, 'r') as f:
                config = yaml.safe_load(f)

            # Ağırlıkları yükle
            if "weights" in config:
                self.weights = {
                    int(k.split("_")[1]): v
                    for k, v in config["weights"].items()
                }

            # Phase parametrelerini yükle
            if "phase_parameters" in config:
                self.phase_params = {
                    int(k.split("_")[1]): v
                    for k, v in config["phase_parameters"].items()
                }

            logger.info(f"Config loaded from {filepath}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
