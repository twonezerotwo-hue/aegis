"""
Touche AI Weight Optimizer — Faz Ağırlıklarını Otomatik Optimize Eden Sistem

Öğrenme Yöntemleri:
1. REINFORCEMENT: Her işlemden sonra ağırlıkları güncelle
2. GRID_SEARCH: Tüm kombinasyonları dene (backtest sonrası)
3. BAYESIAN: En iyi kombinasyonu akıllıca bul (bayesian-optimization kütüphanesi gerekli)
"""
import logging
from typing import Dict, List, Tuple
import numpy as np
from datetime import datetime, timezone
import yaml

logger = logging.getLogger(__name__)


class TradeResult:
    """İşlem sonucu (win/loss) ile hangi fazların katkı sağladığının kaydı"""
    def __init__(self, pnl: float, winning_phases: List[int], losing_phases: List[int]):
        self.pnl = pnl
        self.winning_phases = winning_phases  # İşlemi kazanan fazlar
        self.losing_phases = losing_phases    # İşlemi kaybettiren fazlar
        self.timestamp = datetime.now(timezone.utc)


class ToucheWeightOptimizer:
    """
    Touche AI faz ağırlıklarını dinamik olarak optimize eden sistem.

    Örnek kullanım:
        optimizer = ToucheWeightOptimizer()

        # Işlemden sonra öğren
        optimizer.learn_from_trade(TradeResult(pnl=100, winning_phases=[1,2,3], losing_phases=[]))

        # Backtest ile optimize et
        best_weights = optimizer.grid_search_optimize(backtest_engine, symbol="BTC/USDT")
    """

    def __init__(self, initial_weights: Dict[int, float] = None, learning_rate: float = 0.01):
        """
        Args:
            initial_weights: İlk faz ağırlıkları (phase_id: weight)
            learning_rate: Her işlemden sonra ağırlık değişim hızı (0.001-0.1)
        """
        self.weights = initial_weights or {
            1: 0.15,  # Likidite
            2: 0.20,  # Piyasa Yapısı
            3: 0.20,  # Bölgeler
            4: 0.15,  # Teyit
            5: 0.15,  # Zamanlama
            6: 0.05,  # Risk
            7: 0.10,  # Makro
        }

        self.learning_rate = learning_rate
        self.trade_history: List[TradeResult] = []
        self.optimization_history: List[Dict] = []
        self.phase_names = {
            1: "Likidite", 2: "Piyasa Yapısı", 3: "Bölgeler",
            4: "Teyit", 5: "Zamanlama", 6: "Risk", 7: "Makro"
        }

    # ══════════════════════════════════════════════════════════════════════════════
    # 1. REINFORCEMENT LEARNING - Her işlemden öğren
    # ══════════════════════════════════════════════════════════════════════════════

    def learn_from_trade(self, trade_result: TradeResult) -> Dict[int, float]:
        """
        Işlem sonucundan öğrenerek ağırlıkları güncelle.

        Mantık:
        - Kazanan işlemlerdeki fazları ödüllendirmek (weight arttir)
        - Kaybeden işlemlerdeki fazları cezalandırmak (weight azalt)
        - Tüm ağırlıkları 1.0 olacak şekilde normalize et

        Args:
            trade_result: İşlem sonucu (pnl, winning_phases, losing_phases)

        Returns:
            Güncellenmiş ağırlıklar
        """
        self.trade_history.append(trade_result)

        # Işlem sonucuna göre öğren
        if trade_result.pnl > 0:
            # Kazanan işlem: kazanan fazları ödüllendir
            for phase_id in trade_result.winning_phases:
                if phase_id in self.weights:
                    self.weights[phase_id] += self.learning_rate
                    logger.info(f"Fase {self.phase_names[phase_id]} ödüllendirildi (PnL: +{trade_result.pnl:.2f})")
        else:
            # Kaybeden işlem: kaybeden fazları cezalandır
            for phase_id in trade_result.losing_phases:
                if phase_id in self.weights:
                    self.weights[phase_id] -= self.learning_rate * 2  # 2x ceza
                    logger.info(f"Fase {self.phase_names[phase_id]} cezalandırıldı (PnL: {trade_result.pnl:.2f})")

        # Ağırlıkları normalize et (toplam = 1.0)
        self._normalize_weights()

        return self.weights.copy()

    # ══════════════════════════════════════════════════════════════════════════════
    # 2. GRID SEARCH - Tüm kombinasyonları dene
    # ══════════════════════════════════════════════════════════════════════════════

    def grid_search_optimize(self,
                            backtest_func,
                            symbol: str = "BTC/USDT",
                            lookback_days: int = 30,
                            step: float = 0.05) -> Tuple[Dict[int, float], float]:
        """
        Grid Search ile en iyi ağırlık kombinasyonunu bul.

        Tüm kombinasyonları test eder ve en yüksek Sharpe oranını verenini seçer.

        Args:
            backtest_func: Backtest fonksiyonu (weights -> sharpe_ratio döndürür)
            symbol: Trading symbol (BTC/USDT, ETH/USDT, etc.)
            lookback_days: Kaç günlük veri ile test edeceği
            step: Ağırlık artış adımı (0.05 = %5)

        Returns:
            (en_iyi_ağırlıklar, en_yüksek_sharpe)
        """
        logger.info(f"Grid Search başlıyor... (step={step}, lookback={lookback_days}d)")

        best_sharpe = -999.0
        best_weights = self.weights.copy()
        tested_combinations = 0

        # Phase 1, 2, 3'ün ağırlıklarını ayarla (diğerleri otomatik normalize olur)
        weight_values = np.arange(0.05, 0.40, step)

        for w1 in weight_values:  # Phase 1 (Likidite)
            for w2 in weight_values:  # Phase 2 (Piyasa Yapısı)
                for w3 in weight_values:  # Phase 3 (Bölgeler)
                    # Constraint: main phases en az 0.5 toplam ağırlık
                    main_total = w1 + w2 + w3
                    if main_total < 0.50 or main_total > 0.70:
                        continue

                    # Kalan ağırlıkları dağıt
                    remaining = 1.0 - main_total
                    w4 = 0.15 * (remaining / 0.45)  # Phase 4 (Teyit)
                    w5 = 0.15 * (remaining / 0.45)  # Phase 5 (Zamanlama)
                    w6 = 0.05 * (remaining / 0.45)  # Phase 6 (Risk)
                    w7 = 0.10 * (remaining / 0.45)  # Phase 7 (Makro)

                    # Test et
                    test_weights = {1: w1, 2: w2, 3: w3, 4: w4, 5: w5, 6: w6, 7: w7}

                    try:
                        sharpe = backtest_func(test_weights, symbol, lookback_days)
                        tested_combinations += 1

                        if sharpe > best_sharpe:
                            best_sharpe = sharpe
                            best_weights = test_weights.copy()
                            logger.info(f"Yeni en iyi Sharpe: {sharpe:.2f} | Weights: {self._format_weights(best_weights)}")

                    except Exception as e:
                        logger.warning(f"Test sırasında hata: {e}")
                        continue

        logger.info(f"Grid Search tamamlandı! ({tested_combinations} kombinasyon test edildi)")
        logger.info(f"En iyi Sharpe: {best_sharpe:.2f}")

        # En iyi ağırlıkları kaydet ve döndür
        self.weights = best_weights
        self._log_optimization_result(best_sharpe, best_weights, "grid_search")

        return best_weights, best_sharpe

    # ══════════════════════════════════════════════════════════════════════════════
    # 3. BAYESIAN OPTIMIZATION - Akıllı arama (bayesian-optimization gerekli)
    # ══════════════════════════════════════════════════════════════════════════════

    def bayesian_optimize(self,
                         backtest_func,
                         symbol: str = "BTC/USDT",
                         lookback_days: int = 30,
                         iterations: int = 50) -> Tuple[Dict[int, float], float]:
        """
        Bayesian Optimization ile en iyi ağırlıkları bulma sistemi.

        Grid search'ten daha verimli - akıllıca kombinasyonları seçer.
        Requires: pip install bayesian-optimization

        Args:
            backtest_func: Backtest fonksiyonu
            symbol: Trading symbol
            lookback_days: Kaç gün ile backtest yapacak
            iterations: Kaç kombinasyon deneyeceği

        Returns:
            (en_iyi_ağırlıklar, en_yüksek_sharpe)
        """
        try:
            from bayes_opt import BayesianOptimization
        except ImportError:
            logger.warning("bayesian-optimization yüklü değil, Grid Search'e dönülüyor")
            return self.grid_search_optimize(backtest_func, symbol, lookback_days)

        logger.info(f"Bayesian Optimization başlıyor...({iterations} iterasyon)")

        def objective(w1, w2, w3):
            """Optimize edilecek fonksiyon (Sharpe ratio'yu maksimize et)"""
            main_total = w1 + w2 + w3
            if main_total < 0.50 or main_total > 0.70:
                return -999.0  # Invalid constraint

            remaining = 1.0 - main_total
            w4 = 0.15 * (remaining / 0.45)
            w5 = 0.15 * (remaining / 0.45)
            w6 = 0.05 * (remaining / 0.45)
            w7 = 0.10 * (remaining / 0.45)

            test_weights = {1: w1, 2: w2, 3: w3, 4: w4, 5: w5, 6: w6, 7: w7}

            try:
                return backtest_func(test_weights, symbol, lookback_days)
            except:
                return -999.0

        # Bayesian Optimizer
        optimizer = BayesianOptimization(
            f=objective,
            pbounds={'w1': (0.05, 0.40), 'w2': (0.05, 0.40), 'w3': (0.05, 0.40)},
            random_state=42,
        )

        optimizer.maximize(init_points=5, n_iter=iterations)

        # En iyi sonuç
        best_params = optimizer.max['params']
        best_sharpe = optimizer.max['target']

        # Ağırlıkları rekonstru et
        w1, w2, w3 = best_params['w1'], best_params['w2'], best_params['w3']
        remaining = 1.0 - (w1 + w2 + w3)
        w4 = 0.15 * (remaining / 0.45)
        w5 = 0.15 * (remaining / 0.45)
        w6 = 0.05 * (remaining / 0.45)
        w7 = 0.10 * (remaining / 0.45)

        best_weights = {1: w1, 2: w2, 3: w3, 4: w4, 5: w5, 6: w6, 7: w7}

        logger.info("Bayesian Optimization tamamlandı!")
        logger.info(f"En iyi Sharpe: {best_sharpe:.2f}")

        self.weights = best_weights
        self._log_optimization_result(best_sharpe, best_weights, "bayesian")

        return best_weights, best_sharpe

    # ══════════════════════════════════════════════════════════════════════════════
    # Utility Functions
    # ══════════════════════════════════════════════════════════════════════════════

    def _normalize_weights(self):
        """Ağırlıkları 1.0 olacak şekilde normalize et"""
        total = sum(self.weights.values())
        if total > 0:
            for phase_id in self.weights:
                self.weights[phase_id] /= total

    def _format_weights(self, weights: Dict[int, float]) -> str:
        """Ağırlıkları güzel format'lı string olarak döndür"""
        parts = []
        for phase_id in sorted(weights.keys()):
            phase_name = self.phase_names.get(phase_id, f"Phase {phase_id}")
            parts.append(f"{phase_name}={weights[phase_id]:.3f}")
        return " | ".join(parts)

    def _log_optimization_result(self, sharpe: float, weights: Dict[int, float], method: str):
        """Optimizasyon sonucunu kaydet"""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "sharpe_ratio": sharpe,
            "weights": weights
        }
        self.optimization_history.append(record)
        logger.info(f"Optimization result logged: {record}")

    def save_weights_to_yaml(self, filepath: str):
        """Ağırlıkları YAML dosyasına kaydet"""
        config = {
            "scoring": {
                "weights": {
                    f"phase{phase_id}": weight
                    for phase_id, weight in self.weights.items()
                }
            },
            "last_optimized": datetime.now(timezone.utc).isoformat(),
        }

        with open(filepath, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

        logger.info(f"Ağırlıklar kaydedildi: {filepath}")

    def get_weights_summary(self) -> str:
        """Ağırlıklar özeti"""
        return f"Touche AI Ağırlıkları:\n{self._format_weights(self.weights)}"

    def get_recent_trades(self, limit: int = 10) -> List[TradeResult]:
        """Son N işlemi getir"""
        return self.trade_history[-limit:]

    def get_win_rate(self) -> float:
        """Son işlemlerin kazanma oranı"""
        if not self.trade_history:
            return 0.0
        wins = sum(1 for t in self.trade_history if t.pnl > 0)
        return (wins / len(self.trade_history)) * 100
