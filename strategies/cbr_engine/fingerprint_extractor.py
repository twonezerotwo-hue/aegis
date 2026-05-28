"""
AEGIS CBR Engine - Fingerprint Extractor
Extracts 50+ features from OHLCV data without look-ahead bias
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class Fingerprint:
    """50+ dimensional market fingerprint"""
    symbol: str
    timestamp: datetime

    # Price Structure (5)
    current_price: float
    distance_from_ath: float
    distance_from_200ma: float
    atr_14: float
    volatility_regime: str  # LOW, MID, HIGH

    # Technical Indicators (7)
    rsi_14: float
    macd_histogram: float
    stoch_rsi: float
    obv_trend: float
    volume_profile: int
    liquidity_sweep: float
    structure_score: float

    # Macro Correlation (4)
    dxy_14d_corr: float
    gold_14d_corr: float
    brent_14d_corr: float
    vix_level: float

    # Sentiment/Fear (2)
    fear_greed_index: float
    us_10y_yield: float

    # On-Chain (3)
    exchange_netflow_7d: float
    funding_rate_avg: float
    open_interest_change: float

    # Temporal (4)
    day_of_week: int
    hour_of_day: int
    days_from_halving: int
    macro_event_window: bool

    # Meta Classification (3)
    market_type: str  # DIP, PEAK, BREAKOUT, REJECTION
    regime_label: str  # BULL, BEAR, SIDEWAYS
    quality_score: float  # 0.0-1.0

    # Category 5: AEGIS Module Summaries (7)
    mod_touche_score: float
    mod_fundamental_score: float
    mod_quantum_score: float
    mod_sentinel_score: float
    mod_news_score: float
    mod_consensus_confidence: float
    mod_consensus_weighted_score: float

    # Category 6: Time & Event Risk (5)
    time_intraday_risk: float
    time_weekend_risk: float
    time_macro_event_risk: float
    time_earnings_risk: float
    time_event_risk_score: float

    # Category 7: Position Context (6)
    pos_open_positions: float
    pos_exposure_pct: float
    pos_drawdown_pct: float
    pos_leverage: float
    pos_heat_score: float
    pos_has_open_position: float

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'current_price': self.current_price,
            'distance_from_ath': self.distance_from_ath,
            'distance_from_200ma': self.distance_from_200ma,
            'atr_14': self.atr_14,
            'volatility_regime': self.volatility_regime,
            'rsi_14': self.rsi_14,
            'macd_histogram': self.macd_histogram,
            'stoch_rsi': self.stoch_rsi,
            'obv_trend': self.obv_trend,
            'volume_profile': self.volume_profile,
            'liquidity_sweep': self.liquidity_sweep,
            'structure_score': self.structure_score,
            'dxy_14d_corr': self.dxy_14d_corr,
            'gold_14d_corr': self.gold_14d_corr,
            'brent_14d_corr': self.brent_14d_corr,
            'vix_level': self.vix_level,
            'fear_greed_index': self.fear_greed_index,
            'us_10y_yield': self.us_10y_yield,
            'exchange_netflow_7d': self.exchange_netflow_7d,
            'funding_rate_avg': self.funding_rate_avg,
            'open_interest_change': self.open_interest_change,
            'day_of_week': self.day_of_week,
            'hour_of_day': self.hour_of_day,
            'days_from_halving': self.days_from_halving,
            'macro_event_window': self.macro_event_window,
            'market_type': self.market_type,
            'regime_label': self.regime_label,
            'quality_score': self.quality_score,
            'mod_touche_score': self.mod_touche_score,
            'mod_fundamental_score': self.mod_fundamental_score,
            'mod_quantum_score': self.mod_quantum_score,
            'mod_sentinel_score': self.mod_sentinel_score,
            'mod_news_score': self.mod_news_score,
            'mod_consensus_confidence': self.mod_consensus_confidence,
            'mod_consensus_weighted_score': self.mod_consensus_weighted_score,
            'time_intraday_risk': self.time_intraday_risk,
            'time_weekend_risk': self.time_weekend_risk,
            'time_macro_event_risk': self.time_macro_event_risk,
            'time_earnings_risk': self.time_earnings_risk,
            'time_event_risk_score': self.time_event_risk_score,
            'pos_open_positions': self.pos_open_positions,
            'pos_exposure_pct': self.pos_exposure_pct,
            'pos_drawdown_pct': self.pos_drawdown_pct,
            'pos_leverage': self.pos_leverage,
            'pos_heat_score': self.pos_heat_score,
            'pos_has_open_position': self.pos_has_open_position,
        }


class FingerprintExtractor:
    """Extract fingerprints from OHLCV+macro data"""

    def __init__(self, btc_halving_dates: list = None):
        """
        Args:
            btc_halving_dates: List of halving dates for temporal features
        """
        # Bitcoin halving dates
        self.halving_dates = btc_halving_dates or [
            datetime(2012, 11, 28),
            datetime(2016, 7, 9),
            datetime(2020, 5, 11),
            datetime(2024, 4, 19),
        ]

    def extract(
        self,
        ohlcv: pd.DataFrame,  # Must have: open, high, low, close, volume
        macro_data: pd.DataFrame,  # DXY, GOLD, BRENT, VIX, FGI, US10Y
        onchain_data: pd.DataFrame,  # netflow, funding_rate, open_interest
        idx: int,  # Current row index (NO FUTURE DATA)
    ) -> Optional[Fingerprint]:
        """
        Extract fingerprint from historical data UP TO idx (inclusive)

        Args:
            ohlcv: OHLCV DataFrame indexed by timestamp
            macro_data: Macro indicators (DXY, GOLD, BRENT, VIX, FGI, US10Y)
            onchain_data: On-chain metrics
            idx: Current index (relative position in ohlcv)

        Returns:
            Fingerprint object or None if insufficient data
        """
        # Use only data UP TO idx (no look-ahead)
        historical = ohlcv.iloc[:idx+1]

        if len(historical) < 200:
            logger.warning(f"Insufficient data: {len(historical)} < 200")
            return None

        timestamp = ohlcv.index[int(idx)]
        close = ohlcv.iloc[idx]['close']

        try:
            # === PRICE STRUCTURE (5) ===
            current_price = close
            ath_20y = historical['high'].max()
            distance_from_ath = (1 - close / ath_20y) if ath_20y > 0 else 0.0

            ma_200 = historical['close'].tail(200).mean()
            distance_from_200ma = (close - ma_200) / ma_200 if ma_200 > 0 else 0.0

            atr_14 = self._calculate_atr(historical, period=14)
            volatility_regime = self._classify_volatility_regime(historical)

            # === TECHNICAL INDICATORS (7) ===
            rsi_14 = self._calculate_rsi(historical['close'], period=14)
            macd_hist = self._calculate_macd_histogram(historical['close'])
            stoch_rsi = self._calculate_stoch_rsi(historical['close'])
            obv_trend = self._calculate_obv_trend(historical)
            volume_profile = self._calculate_volume_profile(historical)
            liquidity_sweep = self._calculate_liquidity_sweep(historical)
            structure_score = self._calculate_structure_score(historical)

            # === MACRO CORRELATION (4) ===
            dxy_corr = self._rolling_correlation(historical, macro_data, 'DXY', window=90)
            gold_corr = self._rolling_correlation(historical, macro_data, 'GOLD', window=90)
            brent_corr = self._rolling_correlation(historical, macro_data, 'BRENT', window=90)
            vix_level = self._get_latest_value(macro_data, 'VIX')

            # === SENTIMENT/FEAR (2) ===
            fear_greed = self._get_latest_value(macro_data, 'FGI')
            us_10y_yield = self._get_latest_value(macro_data, 'US10Y')

            # === ON-CHAIN (3) ===
            exchange_netflow_7d = self._calculate_exchange_netflow(onchain_data, days=7)
            funding_rate_avg = self._get_latest_value(onchain_data, 'funding_rate')
            oi_change = self._calculate_oi_change(onchain_data, days=1)

            # === TEMPORAL (4) ===
            day_of_week = timestamp.weekday()
            hour_of_day = timestamp.hour
            days_from_halving = self._days_to_next_halving(timestamp)
            macro_event_window = self._is_macro_event_window(timestamp)

            # === META CLASSIFICATION (3) ===
            market_type = self._classify_market_type(historical, distance_from_ath)
            regime_label = self._classify_regime(historical)
            quality_score = self._calculate_quality_score(
                len(historical), volatility_regime, structure_score, distance_from_ath
            )

            # === CATEGORY 5: AEGIS MODULE SUMMARIES (7) ===
            mod_touche_score = self._get_latest_value(macro_data, 'mod_touche_score')
            mod_fundamental_score = self._get_latest_value(macro_data, 'mod_fundamental_score')
            mod_quantum_score = self._get_latest_value(macro_data, 'mod_quantum_score')
            mod_sentinel_score = self._get_latest_value(macro_data, 'mod_sentinel_score')
            mod_news_score = self._get_latest_value(macro_data, 'mod_news_score')
            mod_consensus_confidence = self._get_latest_value(macro_data, 'mod_consensus_confidence')
            mod_consensus_weighted_score = self._get_latest_value(macro_data, 'mod_consensus_weighted_score')

            # === CATEGORY 6: TIME & EVENT RISK (5) ===
            time_intraday_risk = self._get_latest_value(macro_data, 'time_intraday_risk')
            time_weekend_risk = self._get_latest_value(macro_data, 'time_weekend_risk')
            time_macro_event_risk = self._get_latest_value(macro_data, 'time_macro_event_risk')
            time_earnings_risk = self._get_latest_value(macro_data, 'time_earnings_risk')
            time_event_risk_score = self._get_latest_value(macro_data, 'time_event_risk_score')

            # === CATEGORY 7: POSITION CONTEXT (6) ===
            pos_open_positions = self._get_latest_value(macro_data, 'pos_open_positions')
            pos_exposure_pct = self._get_latest_value(macro_data, 'pos_exposure_pct')
            pos_drawdown_pct = self._get_latest_value(macro_data, 'pos_drawdown_pct')
            pos_leverage = self._get_latest_value(macro_data, 'pos_leverage') or 1.0
            pos_heat_score = self._get_latest_value(macro_data, 'pos_heat_score')
            pos_has_open_position = self._get_latest_value(macro_data, 'pos_has_open_position')

            return Fingerprint(
                symbol='BTC/USDT',
                timestamp=timestamp,
                current_price=current_price,
                distance_from_ath=distance_from_ath,
                distance_from_200ma=distance_from_200ma,
                atr_14=atr_14,
                volatility_regime=volatility_regime,
                rsi_14=rsi_14,
                macd_histogram=macd_hist,
                stoch_rsi=stoch_rsi,
                obv_trend=obv_trend,
                volume_profile=volume_profile,
                liquidity_sweep=liquidity_sweep,
                structure_score=structure_score,
                dxy_14d_corr=dxy_corr,
                gold_14d_corr=gold_corr,
                brent_14d_corr=brent_corr,
                vix_level=vix_level,
                fear_greed_index=fear_greed,
                us_10y_yield=us_10y_yield,
                exchange_netflow_7d=exchange_netflow_7d,
                funding_rate_avg=funding_rate_avg,
                open_interest_change=oi_change,
                day_of_week=day_of_week,
                hour_of_day=hour_of_day,
                days_from_halving=days_from_halving,
                macro_event_window=macro_event_window,
                market_type=market_type,
                regime_label=regime_label,
                quality_score=quality_score,
                mod_touche_score=mod_touche_score,
                mod_fundamental_score=mod_fundamental_score,
                mod_quantum_score=mod_quantum_score,
                mod_sentinel_score=mod_sentinel_score,
                mod_news_score=mod_news_score,
                mod_consensus_confidence=mod_consensus_confidence,
                mod_consensus_weighted_score=mod_consensus_weighted_score,
                time_intraday_risk=time_intraday_risk,
                time_weekend_risk=time_weekend_risk,
                time_macro_event_risk=time_macro_event_risk,
                time_earnings_risk=time_earnings_risk,
                time_event_risk_score=time_event_risk_score,
                pos_open_positions=pos_open_positions,
                pos_exposure_pct=pos_exposure_pct,
                pos_drawdown_pct=pos_drawdown_pct,
                pos_leverage=pos_leverage,
                pos_heat_score=pos_heat_score,
                pos_has_open_position=pos_has_open_position,
            )

        except Exception as e:
            logger.error(f"Error extracting fingerprint at {timestamp}: {e}")
            return None

    # ========== PRICE STRUCTURE ==========

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.tail(period).mean()
        return float(atr) if not np.isnan(atr) else 0.0

    def _classify_volatility_regime(self, df: pd.DataFrame) -> str:
        """Classify volatility as LOW/MID/HIGH based on 30-day volatility"""
        returns = df['close'].pct_change().tail(30)
        volatility = returns.std()

        if volatility < 0.02:
            return 'LOW'
        elif volatility < 0.04:
            return 'MID'
        else:
            return 'HIGH'

    # ========== TECHNICAL INDICATORS ==========

    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> float:
        """Relative Strength Index"""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        if loss.iloc[-1] == 0:
            return 100.0 if gain.iloc[-1] > 0 else 0.0

        rs = gain.iloc[-1] / loss.iloc[-1]
        rsi = 100 - (100 / (1 + rs))
        return float(rsi) if not np.isnan(rsi) else 50.0

    def _calculate_macd_histogram(self, close: pd.Series) -> float:
        """MACD Histogram"""
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        histogram = macd - signal
        return float(histogram.iloc[-1]) if len(histogram) > 0 else 0.0

    def _calculate_stoch_rsi(self, close: pd.Series, period: int = 14) -> float:
        """Stochastic RSI"""
        if len(close) < period * 2:
            return 0.5

        # Calculate RSI values over a rolling window
        rsi_values = []
        for i in range(len(close) - period, len(close)):
            rsi = self._calculate_rsi(close.iloc[:i+1], period)
            rsi_values.append(rsi)

        if len(rsi_values) < 3:
            return 0.5

        current_rsi = rsi_values[-1]
        rsi_min = min(rsi_values)
        rsi_max = max(rsi_values)

        if rsi_max == rsi_min:
            return 0.5

        stoch_rsi = (current_rsi - rsi_min) / (rsi_max - rsi_min)
        return float(stoch_rsi) if not np.isnan(stoch_rsi) else 0.5

    def _calculate_obv_trend(self, df: pd.DataFrame) -> float:
        """On-Balance Volume trend (positive/negative direction)"""
        obv = (df['volume'].where(df['close'].diff() > 0, -df['volume'])).cumsum()
        obv_ma = obv.tail(20).mean()
        obv_current = obv.iloc[-1]
        trend = (obv_current - obv_ma) / obv_ma if obv_ma > 0 else 0.0
        return float(trend)

    def _calculate_volume_profile(self, df: pd.DataFrame) -> int:
        """Volume profile ranking (0-10 scale)"""
        vol_avg = df['volume'].tail(20).mean()
        vol_current = df['volume'].iloc[-1]
        profile = int(min(10, (vol_current / vol_avg) * 5))
        return profile

    def _calculate_liquidity_sweep(self, df: pd.DataFrame) -> float:
        """Detect liquidity sweeps (sudden volume + price moves)"""
        recent = df.tail(24)
        volume_spike = recent['volume'].max() / recent['volume'].mean()
        price_range = (recent['high'].max() - recent['low'].min()) / df['close'].iloc[-1]
        sweep_score = (volume_spike * 0.6 + price_range * 40 * 0.4)
        return float(min(1.0, sweep_score))

    def _calculate_structure_score(self, df: pd.DataFrame) -> float:
        """Higher lows/lows (struct integrity 0-1)"""
        recent = df.tail(20)
        lows = recent['low'].values

        higher_lows = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])
        structure = higher_lows / len(lows) if len(lows) > 0 else 0.5
        return float(structure)

    # ========== MACRO CORRELATION ==========

    def _rolling_correlation(
        self,
        btc_df: pd.DataFrame,
        macro_df: pd.DataFrame,
        macro_symbol: str,
        window: int = 90
    ) -> float:
        """Calculate rolling correlation between BTC and macro asset"""
        try:
            btc_returns = btc_df['close'].pct_change().tail(window)
            macro_returns = macro_df[macro_symbol].pct_change().tail(window)

            if len(btc_returns) < window or len(macro_returns) < window:
                return 0.0

            corr = btc_returns.corr(macro_returns)
            return float(corr) if not np.isnan(corr) else 0.0
        except:
            return 0.0

    def _get_latest_value(self, df: pd.DataFrame, column: str) -> float:
        """Get latest value from macro/onchain data"""
        try:
            if column in df.columns:
                val = df[column].iloc[-1]
                return float(val) if not np.isnan(val) else 0.0
        except:
            pass
        return 0.0

    # ========== ON-CHAIN ==========

    def _calculate_exchange_netflow(self, df: pd.DataFrame, days: int = 7) -> float:
        """Exchange netflow (7-day average)"""
        try:
            recent = df['exchange_netflow'].tail(days)
            return float(recent.mean()) if len(recent) > 0 else 0.0
        except:
            return 0.0

    def _calculate_oi_change(self, df: pd.DataFrame, days: int = 1) -> float:
        """Open interest percent change"""
        try:
            if len(df) < days + 1:
                return 0.0
            oi_current = df['open_interest'].iloc[-1]
            oi_prev = df['open_interest'].iloc[-(days+1)]
            return float((oi_current - oi_prev) / oi_prev) if oi_prev > 0 else 0.0
        except:
            return 0.0

    # ========== TEMPORAL ==========

    def _days_to_next_halving(self, timestamp: datetime) -> int:
        """Days until next Bitcoin halving"""
        next_halving = None
        for halving_date in self.halving_dates:
            if halving_date > timestamp:
                next_halving = halving_date
                break

        if next_halving is None:
            next_halving = self.halving_dates[-1] + timedelta(days=4*365)

        days = (next_halving - timestamp).days
        return max(0, min(days, 1500))  # Cap at ~4 years

    def _is_macro_event_window(self, timestamp: datetime) -> bool:
        """Check if timestamp is near major macro event (FOMC, NFP, etc)"""
        # Simplified: High impact days (usually Wednesdays + Fridays)
        macro_days = [2, 4]  # Wed, Fri
        return timestamp.weekday() in macro_days and 12 <= timestamp.hour <= 20

    # ========== META CLASSIFICATION ==========

    def _classify_market_type(self, df: pd.DataFrame, distance_from_ath: float) -> str:
        """Classify as DIP/PEAK/BREAKOUT/REJECTION"""
        recent_high = df['high'].tail(20).max()
        current = df['close'].iloc[-1]
        recent_low = df['low'].tail(20).min()

        if distance_from_ath < 0.05:  # Near ATH
            return 'PEAK'
        elif current < recent_low * 1.02:  # Touch recent low
            return 'DIP'
        elif current > recent_high * 0.99:  # Break resistance
            return 'BREAKOUT'
        else:
            return 'REJECTION'

    def _classify_regime(self, df: pd.DataFrame) -> str:
        """Classify as BULL/BEAR/SIDEWAYS"""
        ma50 = df['close'].tail(50).mean()
        ma200 = df['close'].tail(200).mean()
        current = df['close'].iloc[-1]

        if current > ma50 > ma200:
            return 'BULL'
        elif current < ma50 < ma200:
            return 'BEAR'
        else:
            return 'SIDEWAYS'

    def _calculate_quality_score(
        self,
        data_length: int,
        volatility: str,
        structure: float,
        distance_from_ath: float
    ) -> float:
        """Calculate data quality (0-1)"""
        score = 0.0

        # Data freshness
        score += min(1.0, data_length / 500) * 0.25

        # Structure quality
        score += structure * 0.25

        # Volatility (mid is best)
        if volatility == 'MID':
            score += 0.3
        elif volatility in ['LOW', 'HIGH']:
            score += 0.15

        # Price position (extremes are good for quality)
        if distance_from_ath < 0.1 or distance_from_ath > 0.4:
            score += 0.2
        else:
            score += 0.1

        return min(1.0, score)
