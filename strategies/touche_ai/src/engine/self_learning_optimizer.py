"""
Touche AI Self-Learning Optimizer — Zarar Edilen İşlemlerden Öğrenerek Parametreleri Otomatik Optimize Eden Sistem

Her zarar edilen işlemden sonra:
1. İşlem parametrelerini analiz et
2. Farklı parametre kombinasyonlarını test et
3. En iyi parametreleri bul ve kaydet
4. Gelecek işlemlerde kullan

Örnek kullanım:
    optimizer = SelfLearningOptimizer()
    best_params = optimizer.optimize_from_loss(trade_data)
    optimizer.save_optimized_params("learned_params.yaml")
"""
import logging
from typing import Dict, List, Any
from datetime import datetime, timezone
import yaml
import numpy as np

logger = logging.getLogger(__name__)


class LossTrade:
    """Zarar edilen işlem kaydı"""
    def __init__(self,
                 entry_price: float,
                 exit_price: float,
                 pnl: float,
                 rsi_at_entry: float,
                 macd_at_entry: float,
                 volatility: float,
                 fibonacci_level: float,
                 timestamp: str = None):
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.pnl = pnl
        self.rsi_at_entry = rsi_at_entry
        self.macd_at_entry = macd_at_entry
        self.volatility = volatility
        self.fibonacci_level = fibonacci_level
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()


class SelfLearningOptimizer:
    """
    Touche AI'ın zarar edilen işlemlerden öğrenerek kendini optimize etmesi sistemi.

    Parametreler (7 faz için optimize edilebilir):
    - Likidite: min_volume_factor, spread_threshold
    - Piyasa Yapısı: trend_strength, ma_period
    - Bölgeler: rsi_oversold, rsi_overbought
    - Teyit: confirmation_candles, confirmation_strength
    - Zamanlama: macd_fast, macd_slow, rsi_period
    - Risk: max_drawdown, stop_loss_pct
    - Makro: vix_threshold, correlation_threshold
    """

    def __init__(self):
        """Varsayılan parametreleri ve arama aralıklarını başlat"""
        self.current_params = {
            # Likidite Phase (1)
            "min_volume_factor": 1.0,
            "spread_threshold": 0.02,

            # Piyasa Yapısı Phase (2)
            "trend_strength": 0.6,
            "ma_period": 20,

            # Bölgeler Phase (3)
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "rsi_period": 14,

            # Teyit Phase (4)
            "confirmation_candles": 1,
            "confirmation_strength": 0.7,

            # Zamanlama Phase (5)
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,

            # Risk Phase (6)
            "max_drawdown": 5.0,
            "stop_loss_pct": 2.0,

            # Makro Phase (7)
            "vix_threshold": 20.0,
            "correlation_threshold": 0.7,
        }

        # Parametre arama aralıkları (grid search için)
        self.param_ranges = {
            "rsi_oversold": [20, 25, 30, 35, 40],
            "rsi_overbought": [60, 65, 70, 75, 80],
            "rsi_period": [10, 12, 14, 16],
            "macd_fast": [8, 10, 12, 14],
            "macd_slow": [24, 26, 28, 30],
            "confirmation_candles": [0, 1, 2, 3],
            "trend_strength": [0.5, 0.6, 0.7, 0.8],
            "ma_period": [15, 20, 25, 30],
            "min_volume_factor": [0.5, 0.75, 1.0, 1.25],
            "max_drawdown": [3.0, 5.0, 7.0, 10.0],
            "stop_loss_pct": [1.0, 1.5, 2.0, 2.5],
            "vix_threshold": [15.0, 20.0, 25.0, 30.0],
        }

        self.loss_history: List[LossTrade] = []
        self.optimization_history: List[Dict] = []
        self.learning_progress: Dict[str, Any] = {
            "losses_processed": 0,
            "total_optimizations_run": 0,
            "avg_improvement": 0.0,
            "best_improvement": 0.0,
        }

    def optimize_from_loss(self,
                          loss_trade: LossTrade,
                          backtest_func=None,
                          critical_params: List[str] = None) -> Dict[str, float]:
        """
        Zarar edilen işlemden öğrenerek parametreleri optimize et.

        Args:
            loss_trade: Zarar edilen işlem kaydı
            backtest_func: Parametrelerle backtest yapan fonksiyon (sharpe_ratio döndürür)
            critical_params: Optimize edilecek kritik parametreler (None = tümü)

        Returns:
            Optimize edilen parametreler
        """
        self.loss_history.append(loss_trade)

        logger.info(
            "loss_trade_received",
            pnl=loss_trade.pnl,
            entry_price=loss_trade.entry_price,
            exit_price=loss_trade.exit_price,
        )

        # Kritik parametreleri belirle
        if critical_params is None:
            # Kaybın nedenine göre kritik parametreleri seç
            critical_params = self._identify_critical_params(loss_trade)

        logger.info(f"Critical params to optimize: {critical_params}")

        # Grid search ile en iyi parametreleri bul
        best_sharpe = -999.0
        best_params = self.current_params.copy()
        tested_combinations = 0

        # Tüm kombinasyonları test et
        param_combinations = self._generate_param_combinations(critical_params)

        for param_combo in param_combinations:
            tested_combinations += 1

            # Parametrelerle backtest yap (mock fonksiyon)
            sharpe = self._simulate_backtest(loss_trade, param_combo)

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = {**self.current_params, **param_combo}

                logger.info(
                    f"New best Sharpe: {sharpe:.2f}",
                    params=param_combo,
                )

        # En iyi parametreleri kaydet
        old_params = self.current_params.copy()
        self.current_params = best_params
        improvement = best_sharpe - (-1.0)  # -1.0 = zarar edilen işlemin tahmini sharpe'i

        self.optimization_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "loss_trade_pnl": loss_trade.pnl,
            "optimized_params": best_params,
            "estimated_new_sharpe": best_sharpe,
            "tested_combinations": tested_combinations,
            "critical_params": critical_params,
        })

        self.learning_progress["losses_processed"] += 1
        self.learning_progress["total_optimizations_run"] += tested_combinations
        self.learning_progress["best_improvement"] = max(
            self.learning_progress["best_improvement"],
            improvement,
        )

        logger.info(
            "optimization_complete",
            old_params=old_params,
            new_params=best_params,
            improvement=improvement,
            tested_combinations=tested_combinations,
        )

        return best_params

    def _identify_critical_params(self, loss_trade: LossTrade) -> List[str]:
        """
        Kayıp nedenini analiz ederek kritik parametreleri belirle.

        Mantık:
        - RSI yüksek ise, RSI eşikleri optimize et
        - MACD zayıf ise, MACD parametreleri optimize et
        - Volatilite yüksek ise, stop-loss ayarı optimize et
        - Ne zaman girsek kapalı ise, confirmation parametreleri optimize et
        """
        critical_params = []

        # RSI değerine göre
        if loss_trade.rsi_at_entry < 40:  # Zayıf sinyal
            critical_params.extend(["rsi_oversold", "rsi_period"])

        # MACD değerine göre
        if abs(loss_trade.macd_at_entry) < 0.001:  # Zayıf MACD
            critical_params.extend(["macd_fast", "macd_slow", "macd_signal"])

        # Volatilite yüksekse
        if loss_trade.volatility > 3.0:
            critical_params.extend(["max_drawdown", "stop_loss_pct"])

        # Fibonacci seviyesi yanlış tahmin edildiyse
        if 0.382 < loss_trade.fibonacci_level < 0.786:
            critical_params.extend(["confirmation_candles", "confirmation_strength"])

        # Trendde ise trend parametreleri
        if loss_trade.volatility > 2.0:
            critical_params.extend(["trend_strength", "ma_period"])

        # En az 3 parametre seç
        if len(critical_params) < 3:
            critical_params.extend(["rsi_oversold", "macd_fast", "confirmation_candles"])

        return list(set(critical_params))[:5]  # İlk 5'i seç

    def _generate_param_combinations(self, critical_params: List[str]) -> List[Dict[str, float]]:
        """
        Kritik parametreler için tüm kombinasyonları oluştur.

        Örnek: ["rsi_oversold", "macd_fast"] için
        -> [{"rsi_oversold": 20, "macd_fast": 8}, {"rsi_oversold": 20, "macd_fast": 10}, ...]
        """
        combinations = []
        param_values = {}

        # Her parametre için değerleri al
        for param in critical_params:
            if param in self.param_ranges:
                param_values[param] = self.param_ranges[param]

        # Kartezyen çarpım yaparak kombinasyonları oluştur
        def generate_combos(params_list, values_dict, current_combo=None):
            if current_combo is None:
                current_combo = {}

            if not params_list:
                combinations.append(current_combo.copy())
                return

            param = params_list[0]
            for value in values_dict[param]:
                current_combo[param] = value
                generate_combos(params_list[1:], values_dict, current_combo)

        generate_combos(critical_params, param_values)
        return combinations

    def _simulate_backtest(self, loss_trade: LossTrade, params: Dict[str, float]) -> float:
        """
        Parametrelerle simüle edilen backtest sonucu (Sharpe ratio).

        Basit heuristic:
        - RSI parametreleri iyiyse, Sharpe artar
        - Confirmation parametreleri iyiyse, Sharpe artar
        - Stop loss doğru ayarlanmışsa, Sharpe artar
        """
        sharpe = 0.0

        # RSI parametreleri değerlendirmesi
        if "rsi_oversold" in params:
            rsi_oversold = params["rsi_oversold"]
            # Loss trade'in RSI'sı bu eşikten az ise, bu eşik iyi değil
            penalty = abs(loss_trade.rsi_at_entry - rsi_oversold) / 50.0
            sharpe += (1.0 - penalty)

        # MACD parametreleri değerlendirmesi
        if "macd_fast" in params:
            macd_fast = params["macd_fast"]
            # 12 civarı en iyi
            penalty = abs(macd_fast - 12) / 6.0
            sharpe += (1.0 - penalty)

        # Confirmation parametreleri değerlendirmesi
        if "confirmation_candles" in params:
            confirmation = params["confirmation_candles"]
            # Az confirmation daha iyi (hızlı giriş)
            sharpe += (1.0 - confirmation * 0.1)

        # Volatilite karşısında stop-loss değerlendirmesi
        if "stop_loss_pct" in params:
            stop_loss = params["stop_loss_pct"]
            volatility_ratio = loss_trade.volatility / 100.0
            ideal_stop = volatility_ratio * 2.0  # Volatilitenin 2x'i ideal
            penalty = abs(stop_loss - ideal_stop) / 5.0
            sharpe += (1.0 - penalty)

        return max(-1.0, sharpe)  # -1 ile 3 arasında

    def get_current_params(self) -> Dict[str, float]:
        """Güncel parametreleri döndür"""
        return self.current_params.copy()

    def get_learning_progress(self) -> Dict[str, Any]:
        """Öğrenme ilerleme raporu"""
        return {
            **self.learning_progress,
            "total_losses_processed": len(self.loss_history),
            "avg_loss": np.mean([t.pnl for t in self.loss_history]) if self.loss_history else 0.0,
            "worst_loss": np.min([t.pnl for t in self.loss_history]) if self.loss_history else 0.0,
        }

    def save_optimized_params(self, filepath: str):
        """Optimize edilen parametreleri YAML dosyasına kaydet"""
        config = {
            "phase_parameters": {
                "likidite": {
                    "min_volume_factor": self.current_params["min_volume_factor"],
                    "spread_threshold": self.current_params["spread_threshold"],
                },
                "piyasa_yapisi": {
                    "trend_strength": self.current_params["trend_strength"],
                    "ma_period": int(self.current_params["ma_period"]),
                },
                "bolgeler": {
                    "rsi_oversold": int(self.current_params["rsi_oversold"]),
                    "rsi_overbought": int(self.current_params["rsi_overbought"]),
                    "rsi_period": int(self.current_params["rsi_period"]),
                },
                "teyit": {
                    "confirmation_candles": int(self.current_params["confirmation_candles"]),
                    "confirmation_strength": self.current_params["confirmation_strength"],
                },
                "zamanlama": {
                    "macd_fast": int(self.current_params["macd_fast"]),
                    "macd_slow": int(self.current_params["macd_slow"]),
                    "macd_signal": int(self.current_params["macd_signal"]),
                },
                "risk": {
                    "max_drawdown": self.current_params["max_drawdown"],
                    "stop_loss_pct": self.current_params["stop_loss_pct"],
                },
                "makro": {
                    "vix_threshold": self.current_params["vix_threshold"],
                    "correlation_threshold": self.current_params["correlation_threshold"],
                },
            },
            "last_optimized": datetime.now(timezone.utc).isoformat(),
            "learning_progress": self.get_learning_progress(),
        }

        with open(filepath, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

        logger.info(f"Optimize edilen parametreler kaydedildi: {filepath}")

    def get_recent_losses(self, limit: int = 10) -> List[Dict]:
        """Son N zararlı işlemi getir"""
        return [
            {
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl": t.pnl,
                "rsi_at_entry": t.rsi_at_entry,
                "macd_at_entry": t.macd_at_entry,
                "timestamp": t.timestamp,
            }
            for t in self.loss_history[-limit:]
        ]

    def get_optimization_history(self, limit: int = 10) -> List[Dict]:
        """Son N optimizasyon kaydını getir"""
        return self.optimization_history[-limit:]
