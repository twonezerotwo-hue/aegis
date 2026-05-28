"""
FUNDAMENTAL AI - Coin-Based Normalization & Flow Tracker

Her coin için ayrı normalizasyon parametreleri:
- BTC: Miner reserve, whale wallets, ETF flows
- ETH: Staking ratio, smart contract activity
- SOL: Network validators, token burning
"""
from typing import Optional, Dict
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CoinNormalizationParams:
    """Coin bazlı normalizasyon parametreleri"""
    symbol: str
    # MVRV Z-Score bounds
    mvrv_min: float
    mvrv_max: float
    mvrv_oversold: float
    mvrv_overbought: float

    # On-chain metric bounds
    metric_min: float
    metric_max: float

    # Whale tracking threshold (USD)
    whale_threshold_usd: float

    # Miner/Staker threshold
    large_holder_threshold: float


class CoinNormalizer:
    """
    Her cryptocurrency için özel normalizasyon kuralları.

    Standard:
    - BTC: En eski ve en likit piyasa
    - ETH: 2. tier, staking önemli
    - SOL, AVAX, POLYGON: Daha yüksek volatilite
    """

    COIN_PARAMS = {
        "BTC": CoinNormalizationParams(
            symbol="BTC",
            mvrv_min=0.5,
            mvrv_max=4.0,
            mvrv_oversold=1.0,      # BTC risk: 1.0 altında
            mvrv_overbought=3.5,    # BTC tepe: 3.5 üstünde
            metric_min=0.1,
            metric_max=0.9,
            whale_threshold_usd=1_000_000,  # 1M USD
            large_holder_threshold=10000,   # 10k BTC
        ),
        "ETH": CoinNormalizationParams(
            symbol="ETH",
            mvrv_min=0.8,
            mvrv_max=3.5,
            mvrv_oversold=1.2,
            mvrv_overbought=3.0,
            metric_min=0.15,
            metric_max=0.85,
            whale_threshold_usd=500_000,    # 500k USD
            large_holder_threshold=50000,   # 50k ETH
        ),
        "SOL": CoinNormalizationParams(
            symbol="SOL",
            mvrv_min=1.0,
            mvrv_max=3.0,
            mvrv_oversold=1.3,
            mvrv_overbought=2.7,
            metric_min=0.2,
            metric_max=0.8,
            whale_threshold_usd=200_000,    # 200k USD
            large_holder_threshold=100_000, # 100k SOL
        ),
    }

    def __init__(self):
        self.params = self.COIN_PARAMS

    def get_params(self, symbol: str) -> Optional[CoinNormalizationParams]:
        """Coin'in normalizasyon parametrelerini al"""
        return self.params.get(symbol.upper())

    def normalize_mvrv(self, symbol: str, raw_mvrv: float) -> float:
        """
        Coin-spesifik MVRV normalizasyon

        Args:
            symbol: BTC, ETH, SOL, vb.
            raw_mvrv: Glassnode'dan gelen raw MVRV değeri

        Returns:
            0-100 normalized score
        """
        params = self.get_params(symbol)
        if not params:
            logger.warning("unknown_symbol_using_default", symbol=symbol)
            params = self.COIN_PARAMS["BTC"]

        # Bounded linear normalizasyon
        min_val = params.mvrv_min
        max_val = params.mvrv_max

        # Clamp değeri bounds içine
        clamped = max(min_val, min(max_val, raw_mvrv))

        # Normalize et (0-100)
        if max_val > min_val:
            normalized = ((clamped - min_val) / (max_val - min_val)) * 100
        else:
            normalized = 50.0

        logger.debug(
            "mvrv_coin_normalized",
            symbol=symbol,
            raw=raw_mvrv,
            clamped=round(clamped, 2),
            normalized=round(normalized, 2),
        )

        return round(normalized, 2)

    def interpret_mvrv_signal(self, symbol: str, raw_mvrv: float) -> str:
        """MVRV değerine göre sinyal (coin-spesifik)"""
        params = self.get_params(symbol)
        if not params:
            params = self.COIN_PARAMS["BTC"]

        if raw_mvrv < params.mvrv_oversold:
            return "OVERSOLD_BUY"  # Güçlü satın alma sinyali
        elif raw_mvrv > params.mvrv_overbought:
            return "OVERBOUGHT_SELL"  # Güçlü satış sinyali
        elif raw_mvrv < (params.mvrv_min + params.mvrv_oversold) / 2:
            return "BULLISH"
        elif raw_mvrv > (params.mvrv_max + params.mvrv_overbought) / 2:
            return "BEARISH"
        else:
            return "NEUTRAL"


class WhaleTracker:
    """
    Whale ve Miner akışlarını izle

    Threshold'lar coin bazındaki büyük işlemlerdir
    """

    def __init__(self):
        self.coin_normalizer = CoinNormalizer()

    def analyze_whale_transactions(
        self, symbol: str, transactions: list, current_price: float
    ) -> Dict:
        """
        Belli büyüklükteki işlemleri analiz et

        Args:
            symbol: Coin symbolu (BTC, ETH, SOL)
            transactions: Transaction listesi
                [{
                    'amount': float,
                    'price_usd': float,
                    'type': 'buy' | 'sell',
                    'timestamp': int
                }]
            current_price: Mevcut fiyat

        Returns:
            {
                'whale_buy_volume': float,
                'whale_sell_volume': float,
                'net_whale_flow': float,
                'whale_sentiment': 'ACCUMULATING' | 'DISTRIBUTING' | 'NEUTRAL',
                'large_transaction_count': int,
                'signal': str,
            }
        """
        params = self.coin_normalizer.get_params(symbol)
        if not params:
            return self._neutral_whale_result()

        whale_threshold = params.whale_threshold_usd
        buy_volume = 0.0
        sell_volume = 0.0
        large_tx_count = 0

        if not transactions:
            return self._neutral_whale_result()

        for tx in transactions:
            try:
                amount_usd = float(tx.get("price_usd", 0)) * float(tx.get("amount", 0))

                if amount_usd >= whale_threshold:
                    large_tx_count += 1
                    tx_type = tx.get("type", "").lower()

                    if tx_type == "buy":
                        buy_volume += amount_usd
                    elif tx_type == "sell":
                        sell_volume += amount_usd

            except (ValueError, TypeError):
                continue

        net_flow = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume

        if total_volume == 0:
            return self._neutral_whale_result()

        # Sentiment
        if net_flow > total_volume * 0.3:
            sentiment = "ACCUMULATING"
            signal = "BULLISH"
        elif net_flow < -total_volume * 0.3:
            sentiment = "DISTRIBUTING"
            signal = "BEARISH"
        else:
            sentiment = "NEUTRAL"
            signal = "NEUTRAL"

        logger.info(
            "whale_analysis",
            symbol=symbol,
            whale_buy=round(buy_volume, 0),
            whale_sell=round(sell_volume, 0),
            sentiment=sentiment,
        )

        return {
            "whale_buy_volume_usd": round(buy_volume, 0),
            "whale_sell_volume_usd": round(sell_volume, 0),
            "net_whale_flow_usd": round(net_flow, 0),
            "whale_sentiment": sentiment,
            "large_transaction_count": large_tx_count,
            "signal": signal,
        }

    def track_miner_reserve(self, symbol: str, miner_data: Dict) -> Dict:
        """
        Miner reserve akışını takip et

        Args:
            symbol: BTC, ETH
            miner_data: {
                'miner_reserve_change': float,  # Son 24h değişim
                'miner_inflow': float,          # Exchange'e gönderilen
                'miner_outflow': float,         # Reserve'den çıkan
            }

        Returns:
            {
                'miner_data': dict,
                'miner_trend': 'SELLING_PRESSURE' | 'ACCUMULATING' | 'NEUTRAL',
                'signal': str,
            }
        """
        try:
            change = float(miner_data.get("miner_reserve_change", 0))
            inflow = float(miner_data.get("miner_inflow", 0))
            outflow = float(miner_data.get("miner_outflow", 0))

            net_flow = outflow - inflow

            if net_flow > 0:
                # Miners ağdan çıkarıyor → Satış baskısı
                trend = "SELLING_PRESSURE"
                signal = "BEARISH"
            elif net_flow < 0:
                # Miners reserve'e ekliyor → Birikme
                trend = "ACCUMULATING"
                signal = "BULLISH"
            else:
                trend = "NEUTRAL"
                signal = "NEUTRAL"

            logger.info(
                "miner_tracking",
                symbol=symbol,
                miner_inflow=round(inflow, 2),
                miner_outflow=round(outflow, 2),
                trend=trend,
            )

            return {
                "miner_inflow": round(inflow, 2),
                "miner_outflow": round(outflow, 2),
                "net_miner_flow": round(net_flow, 2),
                "miner_trend": trend,
                "signal": signal,
            }

        except Exception as e:
            logger.error("miner_tracking_failed", error=str(e))
            return {
                "miner_inflow": 0.0,
                "miner_outflow": 0.0,
                "net_miner_flow": 0.0,
                "miner_trend": "NEUTRAL",
                "signal": "NEUTRAL",
            }

    def track_etf_flows(self, symbol: str, etf_data: Dict) -> Dict:
        """
        ETF giriş/çıkış akışı (Sadece BTC ve ETH için)

        Args:
            symbol: BTC, ETH
            etf_data: {
                'gbtc_inflow': float,
                'ibit_inflow': float,
                'fbtc_inflow': float,
                'eth_etf_inflow': float,
            }

        Returns:
            {
                'etf_net_flow': float,
                'etf_trend': 'INFLOW' | 'OUTFLOW' | 'NEUTRAL',
                'etf_signal': str,
            }
        """
        if symbol not in ["BTC", "ETH"]:
            return {"etf_net_flow": 0.0, "etf_trend": "NEUTRAL", "etf_signal": "N/A"}

        try:
            if symbol == "BTC":
                inflows = [
                    float(etf_data.get("gbtc_inflow", 0)),
                    float(etf_data.get("ibit_inflow", 0)),
                    float(etf_data.get("fbtc_inflow", 0)),
                ]
            else:  # ETH
                inflows = [float(etf_data.get("eth_etf_inflow", 0))]

            net_flow = sum(inflows)

            if net_flow > 0:
                trend = "INFLOW"
                signal = "BULLISH"
            elif net_flow < 0:
                trend = "OUTFLOW"
                signal = "BEARISH"
            else:
                trend = "NEUTRAL"
                signal = "NEUTRAL"

            logger.info(
                "etf_flow_tracking",
                symbol=symbol,
                net_flow=round(net_flow, 2),
                trend=trend,
            )

            return {
                "etf_net_flow_usd": round(net_flow, 0),
                "etf_trend": trend,
                "etf_signal": signal,
            }

        except Exception as e:
            logger.error("etf_tracking_failed", error=str(e))
            return {"etf_net_flow_usd": 0.0, "etf_trend": "NEUTRAL", "etf_signal": "NEUTRAL"}

    def _neutral_whale_result(self) -> Dict:
        """Nötr whale sonucu dön"""
        return {
            "whale_buy_volume_usd": 0.0,
            "whale_sell_volume_usd": 0.0,
            "net_whale_flow_usd": 0.0,
            "whale_sentiment": "NEUTRAL",
            "large_transaction_count": 0,
            "signal": "NEUTRAL",
        }
