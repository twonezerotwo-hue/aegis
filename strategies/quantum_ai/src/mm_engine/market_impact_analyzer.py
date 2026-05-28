"""
QUANTUM AI - Slippage & Market Impact Analysis

Kyle model tabanlı:
- Slippage hesaplama (order book derinliği)
- Market impact modeli (büyük siparişler)
- Hidden order detection
- Depth of Market (DoM) değişim analizi
"""
from typing import Dict, Tuple
import structlog
from dataclasses import dataclass

logger = structlog.get_logger(__name__)


@dataclass
class OrderBookState:
    """Order book durumu"""
    bids: list  # [(price, size), ...]
    asks: list  # [(price, size), ...]
    timestamp: int
    mid_price: float


class SlippageCalculator:
    """
    Slippage hesaplama (order book bazlı)

    Slippage = Execution price - Fair price
    """

    def __init__(self, config: dict = None):
        self.config = config or {}

    def calculate_slippage(
        self, order_size: float, market_price: float, order_book: OrderBookState
    ) -> Dict:
        """
        Verilen size için beklenen slippage hesapla

        Args:
            order_size: Alınacak/Satılacak miktar (base asset)
            market_price: Mevcut mid price
            order_book: Order book durumu

        Returns:
            {
                'buy_slippage_pct': float,      # Buy order slippagesi (%)
                'sell_slippage_pct': float,     # Sell order slippagesi (%)
                'buy_avg_price': float,         # Buy executino price
                'sell_avg_price': float,        # Sell execution price
                'available_buy_liquidity': float,
                'available_sell_liquidity': float,
                'slippage_risk': 'LOW' | 'MEDIUM' | 'HIGH',
            }
        """
        try:
            # Bid tarafında slippage (satış)
            sell_avg_price, sell_liquidity = self._calculate_execution_price(
                order_book.bids, order_size, "sell"
            )

            # Ask tarafında slippage (alış)
            buy_avg_price, buy_liquidity = self._calculate_execution_price(
                order_book.asks, order_size, "buy"
            )

            # Slippage hesapla
            buy_slippage_pct = ((market_price - buy_avg_price) / market_price) * 100 if market_price > 0 else 0
            sell_slippage_pct = ((sell_avg_price - market_price) / market_price) * 100 if market_price > 0 else 0

            # Risk belirleme
            avg_slippage = abs((buy_slippage_pct + sell_slippage_pct) / 2)
            if avg_slippage > 1.0:
                risk = "HIGH"
            elif avg_slippage > 0.5:
                risk = "MEDIUM"
            else:
                risk = "LOW"

            logger.info(
                "slippage_calculated",
                order_size=order_size,
                buy_slippage_pct=round(buy_slippage_pct, 4),
                sell_slippage_pct=round(sell_slippage_pct, 4),
                risk=risk,
            )

            return {
                "buy_slippage_pct": round(buy_slippage_pct, 4),
                "sell_slippage_pct": round(sell_slippage_pct, 4),
                "buy_avg_price": round(buy_avg_price, 6),
                "sell_avg_price": round(sell_avg_price, 6),
                "available_buy_liquidity": round(buy_liquidity, 6),
                "available_sell_liquidity": round(sell_liquidity, 6),
                "slippage_risk": risk,
            }

        except Exception as e:
            logger.error("slippage_calculation_failed", error=str(e))
            return self._neutral_slippage()

    def _calculate_execution_price(
        self, level_list: list, order_size: float, order_type: str
    ) -> Tuple[float, float]:
        """
        VWAP'e göre execution price hesapla

        Args:
            level_list: Bid/Ask seviyeleri [(price, size), ...]
            order_size: Alınacak toplam miktar
            order_type: "buy" veya "sell"

        Returns:
            (execution_price, filled_liquidity)
        """
        if not level_list or order_size <= 0:
            return 0.0, 0.0

        total_cost = 0.0
        filled = 0.0

        for price, size in level_list:
            if filled >= order_size:
                break

            fill_amount = min(size, order_size - filled)
            total_cost += price * fill_amount
            filled += fill_amount

        if filled <= 0:
            return 0.0, 0.0

        execution_price = total_cost / filled
        return execution_price, filled

    def _neutral_slippage(self) -> Dict:
        return {
            "buy_slippage_pct": 0.0,
            "sell_slippage_pct": 0.0,
            "buy_avg_price": 0.0,
            "sell_avg_price": 0.0,
            "available_buy_liquidity": 0.0,
            "available_sell_liquidity": 0.0,
            "slippage_risk": "UNKNOWN",
        }


class MarketImpactCalculator:
    """
    Market Impact Model (Kyle 1985)

    Impact Function: I = lambda * Q    (linear model)

    Parametreler:
    - lambda: Volatilite ve liquidity'e bağlı koeffisyent
    - Q: Order size
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        # Kyle model parametreleri
        self.base_lambda = self.config.get("base_lambda", 0.001)  # 0.1% per unit

    def calculate_market_impact(
        self,
        order_size: float,
        market_price: float,
        volatility: float,
        daily_volume: float,
    ) -> Dict:
        """
        Kyle model tabanlı market impact hesapla

        Args:
            order_size: Order size (ve ya quote currency'de fiyat)
            market_price: Mevcut fiyat
            volatility: 24h volatilite (%)
            daily_volume: 24h volume

        Returns:
            {
                'impact_pct': float,          # Market impact (%)
                'permanent_impact': float,    # Kalıcı impact
                'temporary_impact': float,    # Geçici impact
                'price_movement': float,      # Tahmini fiyat hareketi
                'impact_severity': str,       # LOW, MEDIUM, HIGH
            }
        """
        try:
            # Order Size / Volume oranı
            size_ratio = order_size / market_price / daily_volume if daily_volume > 0 else 0

            # Lambda'yı volatilite ve liquidity'ye göre dinamik ayarla
            # - Volatilite yüksek → lambda artar (impact büyür)
            # - Volume yüksek → lambda düşer (impact küçülür)
            volatility_factor = 1.0 + (volatility / 100.0)
            liquidity_factor = 1.0 / max(0.1, daily_volume / 1_000_000)  # Normalize to millions
            dynamic_lambda = self.base_lambda * volatility_factor * liquidity_factor

            # Kyle model: impact = lambda * Q
            permanent_impact = dynamic_lambda * size_ratio * 100  # %
            temporary_impact = permanent_impact * 0.5  # Temporary = 50% of permanent

            total_impact = permanent_impact + temporary_impact
            price_movement = (market_price * total_impact) / 100

            # Severity
            if total_impact > 2.0:
                severity = "HIGH"
            elif total_impact > 0.5:
                severity = "MEDIUM"
            else:
                severity = "LOW"

            logger.info(
                "market_impact_calculated",
                order_size=order_size,
                size_ratio=round(size_ratio, 4),
                total_impact_pct=round(total_impact, 4),
                severity=severity,
            )

            return {
                "impact_pct": round(total_impact, 4),
                "permanent_impact_pct": round(permanent_impact, 4),
                "temporary_impact_pct": round(temporary_impact, 4),
                "price_movement_usd": round(price_movement, 2),
                "impact_severity": severity,
                "order_size_ratio": round(size_ratio, 4),
            }

        except Exception as e:
            logger.error("market_impact_calculation_failed", error=str(e))
            return self._neutral_impact()

    def _neutral_impact(self) -> Dict:
        return {
            "impact_pct": 0.0,
            "permanent_impact_pct": 0.0,
            "temporary_impact_pct": 0.0,
            "price_movement_usd": 0.0,
            "impact_severity": "UNKNOWN",
            "order_size_ratio": 0.0,
        }


class HiddenOrderDetector:
    """
    Gizli siparişleri tespit et (icebergs, algorithms)

    Detect:
    - Repeated buy/sell pressure
    - Price holding patterns
    - Volume anomalies
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.history_window = self.config.get("window_size", 100)  # Last 100 trades

    def detect_hidden_orders(self, trades: list) -> Dict:
        """
        Icebergs ve büyük gizli siparişleri tespit et

        Args:
            trades: Trade listesi [{
                'price': float,
                'size': float,
                'action': 'buy' | 'sell',
                'timestamp': int
            }]

        Returns:
            {
                'hidden_buy_orders': int,      # Tespit edilen gizli buy
                'hidden_sell_orders': int,
                'accumulation_pattern': bool,  # Birikim deseni var mı?
                'distribution_pattern': bool,  # Dağıtım deseni var mı?
                'pattern_signal': str,          # ACCUMULATING, DISTRIBUTING, NEUTRAL
            }
        """
        try:
            if not trades or len(trades) < 10:
                return self._neutral_detection()

            recent_trades = trades[-self.history_window :]

            # Price level clustering
            price_counts = {}
            for trade in recent_trades:
                price = round(trade["price"], 2)
                price_counts[price] = price_counts.get(price, 0) + 1

            # Clustering points (3+ işlem aynı fiyatta)
            clustered_prices = [p for p, c in price_counts.items() if c >= 3]

            # Buy/Sell separation
            buy_trades = [t for t in recent_trades if t.get("action") == "buy"]
            sell_trades = [t for t in recent_trades if t.get("action") == "sell"]

            # Accumulation: Buy pressure + price holding
            accumulation_detected = len(buy_trades) > len(sell_trades) * 1.3 and len(clustered_prices) > 0
            distribution_detected = len(sell_trades) > len(buy_trades) * 1.3 and len(clustered_prices) > 0

            if accumulation_detected:
                pattern_signal = "ACCUMULATING"
            elif distribution_detected:
                pattern_signal = "DISTRIBUTING"
            else:
                pattern_signal = "NEUTRAL"

            logger.info(
                "hidden_orders_detected",
                clustered_levels=len(clustered_prices),
                accumulation=accumulation_detected,
                distribution=distribution_detected,
                pattern=pattern_signal,
            )

            return {
                "hidden_buy_orders": sum(1 for p in clustered_prices if price_counts[p] >= 3),
                "hidden_sell_orders": sum(1 for p in clustered_prices if price_counts[p] >= 3),
                "accumulation_pattern": accumulation_detected,
                "distribution_pattern": distribution_detected,
                "pattern_signal": pattern_signal,
            }

        except Exception as e:
            logger.error("hidden_order_detection_failed", error=str(e))
            return self._neutral_detection()

    def _neutral_detection(self) -> Dict:
        return {
            "hidden_buy_orders": 0,
            "hidden_sell_orders": 0,
            "accumulation_pattern": False,
            "distribution_pattern": False,
            "pattern_signal": "NEUTRAL",
        }


class DepthOfMarketAnalyzer:
    """
    Depth of Market (DoM) değişimini analiz et

    Detect:
    - Order book imbalance
    - Depth squeeze
    - Sudden depth changes
    """

    def __init__(self, config: dict = None):
        self.config = config or {}

    def analyze_dom_change(self, prev_state: OrderBookState, curr_state: OrderBookState) -> Dict:
        """
        Order book derinliğindeki değişimleri analiz et

        Args:
            prev_state: Önceki order book state
            curr_state: Mevcut order book state

        Returns:
            {
                'bid_depth_ratio': float,      # Bid derinliği oranı (curr/prev)
                'ask_depth_ratio': float,      # Ask derinliği oranı
                'imbalance_ratio': float,      # (Bid depth - Ask depth) / total
                'depth_squeeze': bool,         # Derinlik daraldı mı?
                'dom_signal': str,             # BULLISH, BEARISH, NEUTRAL
            }
        """
        try:
            prev_bid_depth = sum(size for _, size in prev_state.bids)
            prev_ask_depth = sum(size for _, size in prev_state.asks)
            curr_bid_depth = sum(size for _, size in curr_state.bids)
            curr_ask_depth = sum(size for _, size in curr_state.asks)

            # Depth değişim oranları
            bid_ratio = (curr_bid_depth / prev_bid_depth) if prev_bid_depth > 0 else 1.0
            ask_ratio = (curr_ask_depth / prev_ask_depth) if prev_ask_depth > 0 else 1.0

            # Imbalance
            total_depth = curr_bid_depth + curr_ask_depth
            if total_depth > 0:
                imbalance = (curr_bid_depth - curr_ask_depth) / total_depth
            else:
                imbalance = 0.0

            # Depth squeeze?
            prev_total = prev_bid_depth + prev_ask_depth
            curr_total = curr_bid_depth + curr_ask_depth
            squeeze = (curr_total < prev_total * 0.8) if prev_total > 0 else False

            # Sinyal
            if imbalance > 0.1 and bid_ratio > 1.0:
                dom_signal = "BULLISH"  # Buy side derinleşiyor
            elif imbalance < -0.1 and ask_ratio > 1.0:
                dom_signal = "BEARISH"  # Sell side derinleşiyor
            else:
                dom_signal = "NEUTRAL"

            logger.info(
                "dom_analyzed",
                bid_ratio=round(bid_ratio, 3),
                ask_ratio=round(ask_ratio, 3),
                imbalance=round(imbalance, 3),
                squeeze=squeeze,
                signal=dom_signal,
            )

            return {
                "bid_depth_ratio": round(bid_ratio, 3),
                "ask_depth_ratio": round(ask_ratio, 3),
                "imbalance_ratio": round(imbalance, 3),
                "depth_squeeze": squeeze,
                "dom_signal": dom_signal,
            }

        except Exception as e:
            logger.error("dom_analysis_failed", error=str(e))
            return self._neutral_dom()

    def _neutral_dom(self) -> Dict:
        return {
            "bid_depth_ratio": 1.0,
            "ask_depth_ratio": 1.0,
            "imbalance_ratio": 0.0,
            "depth_squeeze": False,
            "dom_signal": "NEUTRAL",
        }
