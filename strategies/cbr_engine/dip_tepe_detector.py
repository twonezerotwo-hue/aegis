"""
AEGIS CBR Engine - Dip & Peak Detector
Identifies high-probability market turning points
"""

import pandas as pd
from typing import List, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PricePattern:
    """Detected price pattern"""
    pattern_type: str  # 'DIP', 'PEAK', 'BREAKOUT', 'REJECTION'
    timestamp: pd.Timestamp
    price: float
    confidence: float  # 0.0-1.0
    lookback: int  # bars used for detection
    strength: float  # pattern magnitude
    nearby_levels: List[float]  # support/resistance


class DipTeepeDetector:
    """Detect dips and peaks with structural analysis"""

    def __init__(self, min_bars: int = 5, max_bars: int = 50):
        """
        Args:
            min_bars: Minimum bars for pattern
            max_bars: Maximum lookback for pattern
        """
        self.min_bars = min_bars
        self.max_bars = max_bars

    def detect_dips(self, df: pd.DataFrame) -> List[PricePattern]:
        """
        Detect buyable dips with multiple confirmations

        Args:
            df: OHLCV DataFrame (must have 'close', 'low', 'high', 'volume')

        Returns:
            List of detected DIP patterns
        """
        dips = []

        if len(df) < self.min_bars:
            return dips

        current_price = df['close'].iloc[-1]
        current_volume = df['volume'].iloc[-1]
        vol_avg = df['volume'].tail(20).mean()

        # Check multiple timeframe patterns
        for lookback in [5, 10, 15, 20]:
            if len(df) < lookback:
                continue

            recent = df.tail(lookback)
            low_price = recent['low'].min()
            low_idx = recent['low'].idxmin()

            # Dip confirmation criteria
            if (current_price > low_price and
                current_volume > vol_avg * 1.5):  # Volume surge

                bounce = (current_price - low_price) / low_price
                if 0.001 <= bounce <= 0.08:  # 0.1%-8% bounce

                    distance_from_low = current_price / low_price - 1.0
                    structure = self._analyze_structure(recent, low_idx)
                    confluence = self._find_confluence_levels(df, low_price)

                    confidence = self._calculate_dip_confidence(
                        bounce=bounce,
                        structure=structure,
                        volume_ratio=current_volume / vol_avg,
                        distance_from_low=distance_from_low,
                        confluence=len(confluence)
                    )

                    if confidence > 0.55:
                        dips.append(PricePattern(
                            pattern_type='DIP',
                            timestamp=df.index[-1],
                            price=low_price,
                            confidence=confidence,
                            lookback=lookback,
                            strength=bounce,
                            nearby_levels=confluence
                        ))

        return sorted(dips, key=lambda x: x.confidence, reverse=True)

    def detect_peaks(self, df: pd.DataFrame) -> List[PricePattern]:
        """
        Detect sellable peaks with structural analysis

        Args:
            df: OHLCV DataFrame

        Returns:
            List of detected PEAK patterns
        """
        peaks = []

        if len(df) < self.min_bars:
            return peaks

        current_price = df['close'].iloc[-1]
        current_volume = df['volume'].iloc[-1]
        vol_avg = df['volume'].tail(20).mean()

        # Check multiple timeframe exhaustion patterns
        for lookback in [5, 10, 15, 20]:
            if len(df) < lookback:
                continue

            recent = df.tail(lookback)
            high_price = recent['high'].max()
            high_idx = recent['high'].idxmin()

            pullback = (high_price - current_price) / high_price
            if 0.005 <= pullback <= 0.10:  # 0.5%-10% pullback

                # Divergence check (declining volume at higher prices)
                price_momentum = (current_price - recent['close'].iloc[0]) / recent['close'].iloc[0]
                vol_momentum = current_volume / vol_avg

                if price_momentum > 0 and vol_momentum < 0.8:  # Price up, volume down = exhaustion
                    structure = self._analyze_structure(recent, high_idx)
                    confluence = self._find_confluence_levels(df, high_price)

                    confidence = self._calculate_peak_confidence(
                        pullback=pullback,
                        structure=structure,
                        volume_ratio=vol_momentum,
                        price_momentum=price_momentum,
                        confluence=len(confluence)
                    )

                    if confidence > 0.55:
                        peaks.append(PricePattern(
                            pattern_type='PEAK',
                            timestamp=df.index[-1],
                            price=high_price,
                            confidence=confidence,
                            lookback=lookback,
                            strength=pullback,
                            nearby_levels=confluence
                        ))

        return sorted(peaks, key=lambda x: x.confidence, reverse=True)

    def detect_breakouts(self, df: pd.DataFrame) -> List[PricePattern]:
        """
        Detect breakouts (resistance/support breaks)

        Args:
            df: OHLCV DataFrame

        Returns:
            List of BREAKOUT patterns
        """
        breakouts = []

        if len(df) < 20:
            return breakouts

        current_price = df['close'].iloc[-1]
        current_high = df['high'].iloc[-1]
        vol_avg = df['volume'].tail(20).mean()

        # Find resistance level (highest high in last 50 bars)
        resistance = df['high'].tail(50).max()
        resistance_touches = (df.tail(50)['high'] >= resistance * 0.98).sum()

        breakout_pct = (current_high - resistance) / resistance

        if (breakout_pct > 0.0 and breakout_pct < 0.05 and
            resistance_touches >= 2 and
            df['volume'].iloc[-1] > vol_avg * 1.3):

            structure = self._analyze_structure(df.tail(20), None)
            confluence = self._find_confluence_levels(df, resistance)

            confidence = self._calculate_breakout_confidence(
                breakout_pct=breakout_pct,
                resistance_touches=resistance_touches,
                volume_ratio=df['volume'].iloc[-1] / vol_avg,
                structure=structure
            )

            if confidence > 0.55:
                breakouts.append(PricePattern(
                    pattern_type='BREAKOUT',
                    timestamp=df.index[-1],
                    price=resistance,
                    confidence=confidence,
                    lookback=20,
                    strength=breakout_pct,
                    nearby_levels=confluence
                ))

        return breakouts

    def detect_rejections(self, df: pd.DataFrame) -> List[PricePattern]:
        """
        Detect rejection candles (failed breakouts)

        Args:
            df: OHLCV DataFrame

        Returns:
            List of REJECTION patterns
        """
        rejections = []

        if len(df) < 10:
            return rejections

        for lookback in [3, 5, 7]:
            if len(df) < lookback:
                continue

            recent = df.tail(lookback)
            current = df.iloc[-1]
            prev = df.iloc[-2]

            # Long upper wick candle
            upper_wick = current['high'] - current['close']
            body = abs(current['close'] - current['open'])
            wick_ratio = upper_wick / (body + upper_wick + 0.0001)

            # Wick > 60% of candle height = rejection
            if wick_ratio > 0.6:
                rejection_price = current['high']
                confluence = self._find_confluence_levels(df, rejection_price)

                confidence = self._calculate_rejection_confidence(
                    wick_ratio=wick_ratio,
                    confluence=len(confluence),
                    volume=current['volume'] / df['volume'].tail(20).mean()
                )

                if confidence > 0.55:
                    rejections.append(PricePattern(
                        pattern_type='REJECTION',
                        timestamp=df.index[-1],
                        price=rejection_price,
                        confidence=confidence,
                        lookback=lookback,
                        strength=wick_ratio,
                        nearby_levels=confluence
                    ))

        return rejections

    # ========== INTERNAL HELPERS ==========

    def _analyze_structure(self, df: pd.DataFrame, pivot_idx) -> float:
        """
        Analyze structural integrity around pivot

        Returns: 0.0-1.0 score
        """
        if len(df) < 3:
            return 0.0

        lows = df['low'].values
        highs = df['high'].values

        # Count higher lows and lower highs
        higher_lows = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])
        lower_highs = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])

        structure_score = (higher_lows / len(lows) * 0.5 + lower_highs / len(highs) * 0.5)
        return float(structure_score)

    def _find_confluence_levels(self, df: pd.DataFrame, reference_price: float, tolerance: float = 0.01) -> List[float]:
        """
        Find support/resistance levels near reference price

        Returns: List of nearby levels
        """
        levels = []
        tolerance_abs = reference_price * tolerance

        # Find swing highs and lows
        recent = df.tail(50)
        swing_highs = recent[recent['high'] == recent['high'].max()]['high'].values
        swing_lows = recent[recent['low'] == recent['low'].min()]['low'].values

        for level in list(swing_highs) + list(swing_lows):
            if abs(level - reference_price) < tolerance_abs:
                levels.append(level)

        # Add moving averages
        ma20 = df['close'].tail(20).mean()
        ma50 = df['close'].tail(50).mean()

        for ma in [ma20, ma50]:
            if abs(ma - reference_price) < tolerance_abs:
                levels.append(ma)

        return levels

    def _calculate_dip_confidence(
        self,
        bounce: float,
        structure: float,
        volume_ratio: float,
        distance_from_low: float,
        confluence: int
    ) -> float:
        """Calculate confidence score for dip pattern"""
        score = 0.0

        # Bounce magnitude (optimal 0.5%-3%)
        if 0.005 <= bounce <= 0.03:
            score += 0.25
        elif bounce < 0.005:
            score += 0.10
        else:
            score += 0.15

        # Structure quality
        score += structure * 0.25

        # Volume confirmation
        score += min(0.25, (volume_ratio - 1.0) * 0.1)

        # Distance from low (recent is better)
        if distance_from_low < 0.02:
            score += 0.15
        else:
            score += max(0.0, 0.15 - distance_from_low * 5)

        # Confluence levels
        score += min(0.10, confluence * 0.05)

        return min(1.0, score)

    def _calculate_peak_confidence(
        self,
        pullback: float,
        structure: float,
        volume_ratio: float,
        price_momentum: float,
        confluence: int
    ) -> float:
        """Calculate confidence score for peak pattern"""
        score = 0.0

        # Pullback magnitude
        if 0.01 <= pullback <= 0.05:
            score += 0.25
        else:
            score += 0.15

        # Structure
        score += structure * 0.25

        # Volume divergence penalty (volume down = good for peak)
        if volume_ratio < 0.8:
            score += 0.20
        else:
            score += 0.05

        # Price momentum (weak momentum at highs = exhaustion)
        if price_momentum < 0.03:
            score += 0.15
        elif price_momentum < 0.10:
            score += 0.10

        # Confluence
        score += min(0.10, confluence * 0.05)

        return min(1.0, score)

    def _calculate_breakout_confidence(
        self,
        breakout_pct: float,
        resistance_touches: int,
        volume_ratio: float,
        structure: float
    ) -> float:
        """Calculate confidence score for breakout"""
        score = 0.0

        # Breakout freshness
        if breakout_pct < 0.02:
            score += 0.20
        else:
            score += 0.10

        # Resistance touches (more touches = more broken)
        score += min(0.25, resistance_touches * 0.08)

        # Volume confirmation
        if volume_ratio > 1.2:
            score += 0.25
        else:
            score += 0.10

        # Structure
        score += structure * 0.20

        return min(1.0, score)

    def _calculate_rejection_confidence(
        self,
        wick_ratio: float,
        confluence: int,
        volume: float
    ) -> float:
        """Calculate confidence score for rejection"""
        score = 0.0

        # Wick strength (60%-80% is good)
        if 0.60 <= wick_ratio <= 0.80:
            score += 0.35
        elif wick_ratio > 0.80:
            score += 0.25
        else:
            score += 0.15

        # Confluence levels
        score += min(0.30, confluence * 0.10)

        # Volume support
        if volume > 1.0:
            score += 0.20
        else:
            score += 0.10

        return min(1.0, score)

    def detect_all_patterns(self, df: pd.DataFrame) -> Dict[str, List[PricePattern]]:
        """Detect all pattern types"""
        return {
            'dips': self.detect_dips(df),
            'peaks': self.detect_peaks(df),
            'breakouts': self.detect_breakouts(df),
            'rejections': self.detect_rejections(df)
        }
