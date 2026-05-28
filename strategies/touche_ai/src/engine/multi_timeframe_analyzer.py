"""
TOUCHE AI - Multi-Timeframe Analysis Engine
Çoklu zaman dilimlerinde (15m, 1h, 4h, 1d) senkronize analız
+ Dinamik volatilite rejimi tespiti
"""
from typing import Dict, Tuple, Optional
import structlog
import pandas as pd
from enum import Enum

logger = structlog.get_logger(__name__)


class VolatilityRegime(Enum):
    """Volatilite rejim kategorileri"""
    LOW = "LOW"           # ATR < 0.5% | BB width < 1%
    NORMAL = "NORMAL"     # ATR 0.5-2% | BB width 1-3%
    HIGH = "HIGH"         # ATR > 2% | BB width > 3%


class TimeFrame(Enum):
    """Desteklenen zaman dilimleri"""
    M15 = (15, "15m")
    H1 = (60, "1h")
    H4 = (240, "4h")
    D1 = (1440, "1d")


class MultiTimeFrameAnalyzer:
    """
    Çoklu zaman diliminde senkronize analiz yapan motor.

    Özellikler:
    - 4 zaman diliminde (15m, 1h, 4h, 1d) eşzamanlı sinyal
    - Volatilite rejimi otomatik tespiti (ATR, Bollinger Band)
    - Dinamik parametre ayarı rejime göre
    - Zaman dilimleri arası uyum (confluence) hesapla
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.timeframes = [TimeFrame.M15, TimeFrame.H1, TimeFrame.H4, TimeFrame.D1]

        # Volatilite eşikleri (config'den oku)
        vol_cfg = self.config.get("volatility", {})
        self.atr_low_threshold = vol_cfg.get("atr_low", 0.005)      # 0.5%
        self.atr_high_threshold = vol_cfg.get("atr_high", 0.02)     # 2%
        self.bb_width_low = vol_cfg.get("bb_width_low", 0.01)       # 1%
        self.bb_width_high = vol_cfg.get("bb_width_high", 0.03)     # 3%

        # Dinamik parametreler rejime göre
        self.dynamic_params = {
            "LOW": {
                "zone_tolerance_atr": 0.2,    # Daha dar tolerans
                "confluence_min": 2,
                "signal_threshold": 40.0,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
            },
            "NORMAL": {
                "zone_tolerance_atr": 0.3,
                "confluence_min": 2,
                "signal_threshold": 50.0,
                "rsi_oversold": 35,
                "rsi_overbought": 65,
            },
            "HIGH": {
                "zone_tolerance_atr": 0.5,    # Daha geniş tolerans
                "confluence_min": 3,
                "signal_threshold": 60.0,
                "rsi_oversold": 40,
                "rsi_overbought": 60,
            },
        }

    def analyze_multiple_timeframes(self, dataframes: Dict[str, pd.DataFrame]) -> Dict[str, any]:
        """
        Çoklu zaman diliminde analız yap ve senkronize sinyal üret.

        Args:
            dataframes: {'15m': df, '1h': df, '4h': df, '1d': df} formatında dataframeler

        Returns:
            {
                'timeframe_signals': {},      # Her zaman dilimi için sinyal
                'volatility_regime': str,     # Tespit edilen rejim
                'dynamic_params': {},         # Aktif dinamik parametreler
                'confluence_score': float,    # Zaman dilimleri uyum skoru
                'final_signal': str,          # BULLISH/BEARISH/NEUTRAL
                'confidence': float,          # 0-1 uyum güveni
            }
        """
        try:
            # Adım 1: Volatilite rejimini tespit et (en uzun timeframe'den)
            primary_df = dataframes.get('1d') or dataframes.get('4h')
            if primary_df is None:
                logger.error("no_valid_dataframe_for_volatility_detection")
                return self._neutral_result()

            volatility_regime = self._detect_volatility_regime(primary_df)
            dynamic_params = self.dynamic_params[volatility_regime.value]

            logger.info(
                "volatility_regime_detected",
                regime=volatility_regime.value,
                params=dynamic_params
            )

            # Adım 2: Her zaman diliminde analız yap
            timeframe_signals = {}
            timeframe_scores = []

            for tf_key, df in dataframes.items():
                if df is None or len(df) < 20:
                    continue

                signal = self._analyze_single_timeframe(df, tf_key, dynamic_params)
                timeframe_signals[tf_key] = signal
                timeframe_scores.append(signal['score'])

            # Adım 3: Zaman dilimleri uyumunu hesapla
            confluence_score, alignment = self._calculate_confluence(timeframe_signals)

            # Adım 4: Nihai sinyal ve güven
            if len(timeframe_signals) > 0:
                final_signal = self._determine_final_signal(timeframe_signals, confluence_score)
                confidence = confluence_score / 100.0  # 0-1 skalası
            else:
                final_signal = "NEUTRAL"
                confidence = 0.0

            result = {
                'volatility_regime': volatility_regime.value,
                'dynamic_params': dynamic_params,
                'timeframe_signals': timeframe_signals,
                'confluence_score': round(confluence_score, 2),
                'alignment': alignment,
                'final_signal': final_signal,
                'confidence': round(confidence, 3),
                'timeframe_count': len(timeframe_signals),
            }

            logger.info(
                "multi_timeframe_analysis_complete",
                final_signal=final_signal,
                confidence=round(confidence, 3),
                confluence=round(confluence_score, 2),
                timeframes=list(timeframe_signals.keys())
            )

            return result

        except Exception as e:
            logger.error("multi_timeframe_analysis_failed", error=str(e))
            return self._neutral_result()

    def _detect_volatility_regime(self, df: pd.DataFrame) -> VolatilityRegime:
        """
        Volatilite rejimini tespit et (ATR ve Bollinger Band genişliği üzerinden)
        """
        try:
            # ATR hesapla
            atr = self._calculate_atr(df, period=14)
            atr_pct = atr / df['close'].iloc[-1]

            # Bollinger Band genişliğini hesapla
            bb_width = self._calculate_bb_width(df, period=20)
            bb_width_pct = bb_width / df['close'].iloc[-1]

            # Regim belirleme mantığı
            if atr_pct < self.atr_low_threshold and bb_width_pct < self.bb_width_low:
                regime = VolatilityRegime.LOW
            elif atr_pct > self.atr_high_threshold and bb_width_pct > self.bb_width_high:
                regime = VolatilityRegime.HIGH
            else:
                regime = VolatilityRegime.NORMAL

            logger.debug(
                "volatility_calculated",
                atr_pct=round(atr_pct, 4),
                bb_width_pct=round(bb_width_pct, 4),
                regime=regime.value
            )

            return regime

        except Exception as e:
            logger.error("volatility_detection_failed", error=str(e))
            return VolatilityRegime.NORMAL

    def _analyze_single_timeframe(self, df: pd.DataFrame, tf_key: str, params: dict) -> dict:
        """Tek bir zaman dilimini analiz et"""
        try:
            current_price = df['close'].iloc[-1]
            atr = self._calculate_atr(df, period=14)

            # RSI analizi
            rsi = self._calculate_rsi(df, period=14)

            # Supply/Demand bölgeleri
            demand_zone = self._find_demand_zone(df)
            supply_zone = self._find_supply_zone(df)

            # Bölgelerdeki fiyat konumu
            tolerance = atr * params['zone_tolerance_atr']
            in_demand = demand_zone and (demand_zone[0] - tolerance <= current_price <= demand_zone[1] + tolerance)
            in_supply = supply_zone and (supply_zone[0] - tolerance <= current_price <= supply_zone[1] + tolerance)

            # Confluence sayımı
            confluences = 0
            confluence_details = []

            if in_demand:
                confluences += 1
                confluence_details.append("demand_zone")
            if in_supply:
                confluences += 1
                confluence_details.append("supply_zone")

            if rsi < params['rsi_oversold']:
                confluences += 1
                confluence_details.append("rsi_oversold")
            elif rsi > params['rsi_overbought']:
                confluences += 1
                confluence_details.append("rsi_overbought")

            # Sinyal belirleme
            if confluences >= params['confluence_min']:
                if in_demand:
                    signal = "BULLISH"
                    score = 50 + confluences * 15
                elif in_supply:
                    signal = "BEARISH"
                    score = 50 + confluences * 15
                else:
                    signal = "NEUTRAL"
                    score = 45 + confluences * 5
            else:
                signal = "NEUTRAL"
                score = 20

            return {
                'timeframe': tf_key,
                'signal': signal,
                'score': min(100, score),
                'rsi': round(rsi, 2),
                'atr': round(atr, 6),
                'current_price': round(current_price, 4),
                'demand_zone': [round(x, 4) for x in demand_zone] if demand_zone else None,
                'supply_zone': [round(x, 4) for x in supply_zone] if supply_zone else None,
                'confluences': confluences,
            }

        except Exception as e:
            logger.error("single_timeframe_analysis_failed", timeframe=tf_key, error=str(e))
            return {'timeframe': tf_key, 'signal': 'NEUTRAL', 'score': 0, 'error': str(e)}

    def _calculate_confluence(self, signals: Dict[str, dict]) -> Tuple[float, str]:
        """
        Zaman dilimleri arasında uyum hesapla

        Returns:
            (confluence_score: 0-100, alignment: "strong"/"moderate"/"weak")
        """
        if not signals:
            return 0.0, "weak"

        bullish_count = sum(1 for s in signals.values() if s.get('signal') == 'BULLISH')
        bearish_count = sum(1 for s in signals.values() if s.get('signal') == 'BEARISH')
        neutral_count = sum(1 for s in signals.values() if s.get('signal') == 'NEUTRAL')

        total = len(signals)

        # Tam uyum: tüm sinyaller aynı yönde
        if bullish_count == total or bearish_count == total:
            alignment = "strong"
            confluence = 100.0
        # Kısmi uyum: %66+ aynı yönde
        elif max(bullish_count, bearish_count) >= total * 0.66:
            alignment = "moderate"
            confluence = 60.0 + (max(bullish_count, bearish_count) / total) * 20
        # Zayıf uyum
        else:
            alignment = "weak"
            confluence = 30.0

        return confluence, alignment

    def _determine_final_signal(self, signals: Dict[str, dict], confluence_score: float) -> str:
        """Zaman dilimleri uyuma göre nihai sinyal belirle"""
        if not signals:
            return "NEUTRAL"

        bullish_count = sum(1 for s in signals.values() if s.get('signal') == 'BULLISH')
        bearish_count = sum(1 for s in signals.values() if s.get('signal') == 'BEARISH')

        # Köşelik kuralı: En az 2 zaman dilimi aynı yönde + confluence >= 50
        if bullish_count >= 2 and confluence_score >= 50:
            return "BULLISH"
        elif bearish_count >= 2 and confluence_score >= 50:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """ATR hesapla"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return atr if not pd.isna(atr) else 0.0

    def _calculate_bb_width(self, df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> float:
        """Bollinger Band genişliğini hesapla"""
        sma = df['close'].rolling(period).mean()
        std = df['close'].rolling(period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        width = (upper - lower).iloc[-1]
        return width if not pd.isna(width) else 0.0

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """RSI hesapla"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0

    def _find_demand_zone(self, df: pd.DataFrame) -> Optional[Tuple[float, float]]:
        """Talep bölgesi bul"""
        closes = df['close'].tolist()
        opens = df['open'].tolist()
        lows = df['low'].tolist()
        n = len(closes)

        best_idx = None
        best_move = 0.0
        for i in range(max(0, n - 50), n - 3):
            if closes[i] > opens[i]:
                move = closes[i + 2] - closes[i] if i + 2 < n else 0
                if move > best_move:
                    best_move = move
                    best_idx = i

        if best_idx is None:
            return None

        zone_low = min(lows[max(0, best_idx - 1): best_idx + 1])
        zone_high = max(df['high'].tolist()[max(0, best_idx - 1): best_idx + 1])
        return (zone_low, zone_high)

    def _find_supply_zone(self, df: pd.DataFrame) -> Optional[Tuple[float, float]]:
        """Arz bölgesi bul"""
        closes = df['close'].tolist()
        opens = df['open'].tolist()
        highs = df['high'].tolist()
        lows = df['low'].tolist()
        n = len(closes)

        best_idx = None
        best_move = 0.0
        for i in range(max(0, n - 50), n - 3):
            if closes[i] < opens[i]:
                move = closes[i] - closes[i + 2] if i + 2 < n else 0
                if move > best_move:
                    best_move = move
                    best_idx = i

        if best_idx is None:
            return None

        zone_low = min(lows[max(0, best_idx - 1): best_idx + 1])
        zone_high = max(highs[max(0, best_idx - 1): best_idx + 1])
        return (zone_low, zone_high)

    def _neutral_result(self) -> dict:
        """Nötr sonuç dön"""
        return {
            'volatility_regime': 'NORMAL',
            'dynamic_params': self.dynamic_params['NORMAL'],
            'timeframe_signals': {},
            'confluence_score': 0.0,
            'alignment': 'weak',
            'final_signal': 'NEUTRAL',
            'confidence': 0.0,
        }
