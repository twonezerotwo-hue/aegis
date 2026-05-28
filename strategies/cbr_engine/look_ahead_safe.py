"""
AEGIS CBR Engine - Look-Ahead Bias Prevention
Ensures features are extracted only from past data at each point in time
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class LookAheadSafeExtractor:
    """
    Wraps fingerprint extraction to prevent look-ahead bias.

    Key principle: At each timestamp, use ONLY data available at that time.
    Forward returns are calculated AFTER feature extraction (backtesting phase).
    """

    def __init__(self, min_history_bars: int = 200):
        """
        Args:
            min_history_bars: Minimum bars needed before first feature extraction
        """
        self.min_history_bars = min_history_bars

    def extract_features_safe(
        self,
        ohlcv: pd.DataFrame,
        macro_data: pd.DataFrame,
        onchain_data: pd.DataFrame,
        target_idx: int
    ) -> Optional[Dict]:
        """
        Extract features at target_idx using ONLY historical data.

        Args:
            ohlcv: Full OHLCV history (indexed by timestamp)
            macro_data: Macro indicators (indexed by timestamp, up to target_idx)
            onchain_data: On-chain data (indexed by timestamp, up to target_idx)
            target_idx: Current index (integer position, NOT timestamp)

        Returns:
            Dict with features or None if insufficient data

        CRITICAL: Do NOT use df.iloc[target_idx+1:] or any future data
        """
        # Validation: ensure we have enough history
        if target_idx < self.min_history_bars:
            logger.warning(f"Insufficient history: {target_idx} < {self.min_history_bars}")
            return None

        # === SAFE DATA ACCESS PATTERN ===
        # Get data slice from start to target_idx INCLUSIVE
        historical_ohlcv = ohlcv.iloc[:target_idx + 1].copy()
        historical_macro = macro_data.iloc[:target_idx + 1].copy()
        historical_onchain = onchain_data.iloc[:target_idx + 1].copy()

        timestamp = ohlcv.index[target_idx]
        current_price = ohlcv['close'].iloc[target_idx]

        try:
            features = {
                'timestamp': timestamp,
                'target_idx': target_idx,
                'symbol': 'BTC/USDT',
            }

            # === PRICE STRUCTURE ===
            features['current_price'] = float(current_price)
            features['distance_from_ath'] = self._safe_distance_from_ath(historical_ohlcv)
            features['distance_from_200ma'] = self._safe_distance_from_ma(historical_ohlcv, period=200)
            features['atr_14'] = self._safe_atr(historical_ohlcv, period=14)
            features['volatility_regime'] = self._safe_volatility_regime(historical_ohlcv)

            # === TECHNICAL INDICATORS ===
            features['rsi_14'] = self._safe_rsi(historical_ohlcv, period=14)
            features['macd_histogram'] = self._safe_macd_histogram(historical_ohlcv)
            features['stoch_rsi'] = self._safe_stoch_rsi(historical_ohlcv)
            features['obv_trend'] = self._safe_obv_trend(historical_ohlcv)
            features['volume_profile'] = self._safe_volume_profile(historical_ohlcv)
            features['liquidity_sweep'] = self._safe_liquidity_sweep(historical_ohlcv)
            features['structure_score'] = self._safe_structure_score(historical_ohlcv)

            # === MACRO CORRELATION ===
            features['dxy_14d_corr'] = self._safe_rolling_corr(historical_ohlcv, historical_macro, 'DXY', 90)
            features['gold_14d_corr'] = self._safe_rolling_corr(historical_ohlcv, historical_macro, 'GOLD', 90)
            features['brent_14d_corr'] = self._safe_rolling_corr(historical_ohlcv, historical_macro, 'BRENT', 90)
            features['vix_level'] = self._safe_get_value(historical_macro, 'VIX')

            # === SENTIMENT ===
            features['fear_greed_index'] = self._safe_get_value(historical_macro, 'FGI')
            features['us_10y_yield'] = self._safe_get_value(historical_macro, 'US10Y')

            # === ON-CHAIN ===
            features['exchange_netflow_7d'] = self._safe_exchange_netflow(historical_onchain, days=7)
            features['funding_rate_avg'] = self._safe_get_value(historical_onchain, 'funding_rate')
            features['open_interest_change'] = self._safe_oi_change(historical_onchain, days=1)

            # === TEMPORAL ===
            features['day_of_week'] = int(timestamp.weekday())
            features['hour_of_day'] = int(timestamp.hour)
            features['days_from_halving'] = self._days_to_halving(timestamp)
            features['macro_event_window'] = self._is_macro_event(timestamp)

            # === CLASSIFICATION ===
            features['market_type'] = self._classify_market_type(historical_ohlcv, features['distance_from_ath'])
            features['regime_label'] = self._classify_regime(historical_ohlcv)
            features['quality_score'] = self._calculate_quality(historical_ohlcv, features)

            # Mark this as safe extraction
            features['point_in_time_verified'] = True

            return features

        except Exception as e:
            logger.error(f"Error in safe extraction at {timestamp}: {e}", exc_info=True)
            return None

    def validate_no_lookahead(
        self,
        features: Dict,
        forward_data_timestamp: datetime
    ) -> bool:
        """
        Verify that feature timestamp is strictly before forward_data_timestamp

        Args:
            features: Extracted features dict
            forward_data_timestamp: End timestamp of forward period

        Returns:
            True if no look-ahead bias detected
        """
        feature_time = features['timestamp']

        # Features must be strictly in the past of forward data
        if feature_time >= forward_data_timestamp:
            logger.error(f"Look-ahead bias detected: feature_time {feature_time} >= forward_time {forward_data_timestamp}")
            return False

        return True

    # ========== SAFE CALCULATION PRIMITIVES ==========

    def _safe_distance_from_ath(self, df: pd.DataFrame) -> float:
        """Distance from all-time high in historical data"""
        ath = df['high'].max()
        current = df['close'].iloc[-1]
        return float((1 - current / ath) if ath > 0 else 0.0)

    def _safe_distance_from_ma(self, df: pd.DataFrame, period: int) -> float:
        """Distance from moving average (using only available data)"""
        available_bars = min(period, len(df))
        if available_bars < period:
            # Use what we have
            ma = df['close'].tail(available_bars).mean()
        else:
            ma = df['close'].tail(period).mean()

        current = df['close'].iloc[-1]
        return float((current - ma) / ma if ma > 0 else 0.0)

    def _safe_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Average True Range using only historical data"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        available = min(period, len(tr))
        if available < 3:
            return 0.0

        atr = tr.tail(available).mean()
        return float(atr) if not np.isnan(atr) else 0.0

    def _safe_volatility_regime(self, df: pd.DataFrame) -> str:
        """Classify volatility from historical data"""
        available = min(30, len(df))
        if available < 5:
            return 'LOW'

        returns = df['close'].pct_change().tail(available)
        volatility = returns.std()

        if volatility < 0.02:
            return 'LOW'
        elif volatility < 0.04:
            return 'MID'
        else:
            return 'HIGH'

    def _safe_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """RSI using only historical data"""
        close = df['close']
        delta = close.diff()

        available = min(period * 2, len(delta))
        if available < period:
            return 50.0

        gain = (delta.where(delta > 0, 0)).tail(available).mean()
        loss = (-delta.where(delta < 0, 0)).tail(available).mean()

        if loss == 0:
            return 100.0 if gain > 0 else 0.0

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi) if not np.isnan(rsi) else 50.0

    def _safe_macd_histogram(self, df: pd.DataFrame) -> float:
        """MACD histogram from historical data"""
        if len(df) < 26:
            return 0.0

        close = df['close']
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal

        return float(histogram.iloc[-1]) if len(histogram) > 0 else 0.0

    def _safe_stoch_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Stochastic RSI from historical data"""
        if len(df) < period * 2:
            return 0.5

        rsi_values = []
        for i in range(max(period, len(df) - period * 4), len(df)):
            close_slice = df['close'].iloc[:i+1]
            if len(close_slice) >= period:
                rsi = self._safe_rsi(df.iloc[:i+1], period)
                rsi_values.append(rsi)

        if not rsi_values:
            return 0.5

        rsi_min = min(rsi_values)
        rsi_max = max(rsi_values)
        current_rsi = self._safe_rsi(df, period)

        if rsi_max == rsi_min:
            return 0.5

        stoch_rsi = (current_rsi - rsi_min) / (rsi_max - rsi_min)
        return float(stoch_rsi) if not np.isnan(stoch_rsi) else 0.5

    def _safe_obv_trend(self, df: pd.DataFrame) -> float:
        """OBV trend direction"""
        obv = (df['volume'].where(df['close'].diff() > 0, -df['volume'])).cumsum()
        obv_ma = obv.tail(min(20, len(obv))).mean()
        obv_current = obv.iloc[-1]
        trend = (obv_current - obv_ma) / obv_ma if obv_ma > 0 else 0.0
        return float(trend)

    def _safe_volume_profile(self, df: pd.DataFrame) -> int:
        """Volume profile ranking"""
        vol_avg = df['volume'].tail(min(20, len(df))).mean()
        vol_current = df['volume'].iloc[-1]
        profile = int(min(10, (vol_current / vol_avg) * 5))
        return profile

    def _safe_liquidity_sweep(self, df: pd.DataFrame) -> float:
        """Liquidity sweep detection"""
        recent_bars = min(24, len(df))
        if recent_bars < 3:
            return 0.0

        recent = df.tail(recent_bars)
        volume_spike = recent['volume'].max() / (recent['volume'].mean() + 0.0001)
        price_range = (recent['high'].max() - recent['low'].min()) / df['close'].iloc[-1]

        sweep_score = (volume_spike * 0.6 + price_range * 40 * 0.4)
        return float(min(1.0, sweep_score))

    def _safe_structure_score(self, df: pd.DataFrame) -> float:
        """Structure integrity"""
        recent_bars = min(20, len(df))
        if recent_bars < 3:
            return 0.5

        recent = df.tail(recent_bars)
        lows = recent['low'].values

        higher_lows = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])
        structure = higher_lows / len(lows) if len(lows) > 0 else 0.5
        return float(structure)

    def _safe_rolling_corr(
        self,
        btc_df: pd.DataFrame,
        macro_df: pd.DataFrame,
        symbol: str,
        window: int = 90
    ) -> float:
        """Rolling correlation with safety checks"""
        try:
            available = min(window, len(btc_df), len(macro_df))
            if available < 10:
                return 0.0

            btc_returns = btc_df['close'].pct_change().tail(available)
            macro_returns = macro_df[symbol].pct_change().tail(available)

            corr = btc_returns.corr(macro_returns)
            return float(corr) if not np.isnan(corr) else 0.0
        except:
            return 0.0

    def _safe_get_value(self, df: pd.DataFrame, column: str) -> float:
        """Safely get latest value from DataFrame"""
        try:
            if column in df.columns and len(df) > 0:
                val = df[column].iloc[-1]
                return float(val) if not np.isnan(val) else 0.0
        except:
            pass
        return 0.0

    def _safe_exchange_netflow(self, df: pd.DataFrame, days: int = 7) -> float:
        """Exchange netflow calculation"""
        try:
            available_days = min(days, len(df))
            if available_days < 2:
                return 0.0
            return float(df['exchange_netflow'].tail(available_days).mean())
        except:
            return 0.0

    def _safe_oi_change(self, df: pd.DataFrame, days: int = 1) -> float:
        """Open interest percent change"""
        try:
            if len(df) < days + 1:
                return 0.0
            oi_current = df['open_interest'].iloc[-1]
            oi_prev = df['open_interest'].iloc[-(days+1)]
            return float((oi_current - oi_prev) / oi_prev) if oi_prev > 0 else 0.0
        except:
            return 0.0

    def _days_to_halving(self, timestamp: datetime) -> int:
        """Days to next BTC halving"""
        halving_dates = [
            datetime(2024, 4, 19),
            datetime(2028, 4, 9),
            datetime(2032, 3, 29),
        ]

        next_halving = None
        for date in halving_dates:
            if date > timestamp:
                next_halving = date
                break

        if next_halving is None:
            next_halving = halving_dates[-1] + pd.Timedelta(days=4*365)

        days = (next_halving - timestamp).days
        return max(0, min(days, 1500))

    def _is_macro_event(self, timestamp: datetime) -> bool:
        """Check for macro event window"""
        macro_days = [2, 4]  # Wed, Fri
        return timestamp.weekday() in macro_days and 12 <= timestamp.hour <= 20

    def _classify_market_type(self, df: pd.DataFrame, distance_from_ath: float) -> str:
        """Classify market phase"""
        recent_high = df['high'].tail(20).max()
        current = df['close'].iloc[-1]
        recent_low = df['low'].tail(20).min()

        if distance_from_ath < 0.05:
            return 'PEAK'
        elif current < recent_low * 1.02:
            return 'DIP'
        elif current > recent_high * 0.99:
            return 'BREAKOUT'
        else:
            return 'REJECTION'

    def _classify_regime(self, df: pd.DataFrame) -> str:
        """Classify market regime"""
        ma50 = df['close'].tail(min(50, len(df))).mean()
        ma200 = df['close'].tail(min(200, len(df))).mean()
        current = df['close'].iloc[-1]

        if current > ma50 > ma200:
            return 'BULL'
        elif current < ma50 < ma200:
            return 'BEAR'
        else:
            return 'SIDEWAYS'

    def _calculate_quality(self, df: pd.DataFrame, features: Dict) -> float:
        """Calculate data quality score"""
        score = 0.0

        # Data availability
        score += min(1.0, len(df) / 500) * 0.25

        # Structure quality
        score += features['structure_score'] * 0.25

        # Volatility (MID is best)
        if features['volatility_regime'] == 'MID':
            score += 0.3
        else:
            score += 0.15

        # Price positioning
        dfa = features['distance_from_ath']
        if dfa < 0.1 or dfa > 0.4:
            score += 0.2
        else:
            score += 0.1

        return min(1.0, score)
