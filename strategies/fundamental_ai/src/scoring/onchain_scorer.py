"""
Fundamental AI - On-Chain Score Calculator

Improved scoring formula that spreads fundamental scores across 0.2-0.9 range
instead of being stuck at 0.5-0.8.

Components:
- Volatility Assessment (0.2-0.8)
- Volume Analysis (0.0-0.3)
- On-chain Metrics (0.0-0.2)
- News/Sentiment (0.0-0.1)

Formula: fundamental_score = 0.3 + volatility_weight + volume_weight + onchain_weight + news_weight
Range: 0.2 to 0.95 (much wider than 0.5-0.8)
"""

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class OnChainScorer:
    """Calculates fundamental scores with wider distribution"""

    def __init__(self, min_score: float = 0.2, max_score: float = 0.95):
        """
        Initialize scorer

        Args:
            min_score: Minimum possible score (bearish extreme)
            max_score: Maximum possible score (bullish extreme)
        """
        self.min_score = min_score
        self.max_score = max_score
        self.base_score = 0.3  # Floor before adding components

    def calculate_volatility_weight(
        self,
        volatility: pd.Series,
        period: int = 20,
    ) -> np.ndarray:
        """
        Calculate volatility weight component (0.2-0.8)

        Lower volatility = more stable = higher score
        Higher volatility = more risky = lower score

        Args:
            volatility: Series of volatility values
            period: Rolling period

        Returns:
            Weight component (0.2-0.8 range)
        """
        # Normalize volatility to 0-1 range
        vol_min = volatility.rolling(period).min()
        vol_max = volatility.rolling(period).max()
        vol_range = vol_max - vol_min + 1e-8

        vol_normalized = (volatility - vol_min) / vol_range
        vol_normalized = np.clip(vol_normalized, 0, 1)

        # Invert: lower volatility = higher score
        # 0.2 (very high vol) to 0.8 (very low vol)
        vol_weight = 0.2 + (1 - vol_normalized) * 0.6

        return vol_weight

    def calculate_volume_weight(
        self,
        volume: pd.Series,
        period: int = 20,
    ) -> np.ndarray:
        """
        Calculate volume weight component (0.0-0.3)

        Higher volume = stronger conviction = adds to score
        Lower volume = weak conviction = reduces score

        Args:
            volume: Series of volume values
            period: Rolling period

        Returns:
            Weight component (0.0-0.3 range)
        """
        # Volume ratio: current / average
        vol_avg = volume.rolling(period).mean()
        volume_ratio = volume / (vol_avg + 1e-8)
        volume_ratio = np.clip(volume_ratio, 0.5, 3.0)

        # Normalize: 0.5 → 0.0, 1.0 → 0.15, 3.0 → 0.3
        vol_weight = (volume_ratio - 0.5) / (3.0 - 0.5) * 0.3
        vol_weight = np.clip(vol_weight, 0, 0.3)

        return vol_weight

    def calculate_price_action_weight(
        self,
        close: pd.Series,
        period: int = 20,
    ) -> np.ndarray:
        """
        Calculate price action weight component (0.0-0.2)

        Higher positions in range = more bullish
        Lower positions in range = more bearish

        Args:
            close: Series of close prices
            period: Rolling period

        Returns:
            Weight component (0.0-0.2 range)
        """
        # Calculate position in range
        high = close.rolling(period).max()
        low = close.rolling(period).min()
        range_high_low = high - low + 1e-8

        # 0 = at low, 1 = at high
        position = (close - low) / range_high_low
        position = np.clip(position, 0, 1)

        # Convert to weight: 0 (at low) → 0.0, 1 (at high) → 0.2
        price_weight = position * 0.2

        return price_weight

    def calculate_momentum_weight(
        self,
        close: pd.Series,
        period: int = 10,
    ) -> np.ndarray:
        """
        Calculate momentum weight component (0.0-0.15)

        Positive momentum = bullish = adds to score
        Negative momentum = bearish = subtracts from score

        Args:
            close: Series of close prices
            period: Momentum period

        Returns:
            Weight component (-0.15-0.15 range)
        """
        # Calculate returns
        returns = close.pct_change(period)
        returns = np.clip(returns, -0.1, 0.1)

        # Convert returns to weight
        # -10% → -0.15, 0% → 0.0, +10% → +0.15
        momentum_weight = returns * 1.5
        momentum_weight = np.clip(momentum_weight, -0.15, 0.15)

        return momentum_weight

    def calculate_fundamental_score(
        self,
        df: pd.DataFrame,
        volatility_weight_coef: float = 1.0,
        volume_weight_coef: float = 1.0,
        price_action_weight_coef: float = 0.8,
        momentum_weight_coef: float = 0.6,
    ) -> np.ndarray:
        """
        Calculate complete fundamental score with all components

        Args:
            df: DataFrame with columns: close, volume, volatility (or calculated)
            volatility_weight_coef: Coefficient for volatility weight (0-2)
            volume_weight_coef: Coefficient for volume weight (0-2)
            price_action_weight_coef: Coefficient for price action (0-2)
            momentum_weight_coef: Coefficient for momentum (0-2)

        Returns:
            Array of fundamental scores (0.2-0.95 range)
        """
        # Calculate volatility if not in dataframe
        if 'volatility' not in df.columns:
            df['volatility'] = df['close'].pct_change().rolling(20).std()

        # Calculate individual weights
        vol_weight = self.calculate_volatility_weight(df['volatility'])
        vol_weight = vol_weight * volatility_weight_coef

        volume_weight = self.calculate_volume_weight(df['volume'])
        volume_weight = volume_weight * volume_weight_coef

        price_weight = self.calculate_price_action_weight(df['close'])
        price_weight = price_weight * price_action_weight_coef

        momentum_weight = self.calculate_momentum_weight(df['close'])
        momentum_weight = momentum_weight * momentum_weight_coef

        # Combine: base (0.3) + components
        fundamental = (
            self.base_score +
            vol_weight +
            volume_weight +
            price_weight +
            momentum_weight
        )

        # Clip to range [0.2, 0.95]
        fundamental = np.clip(fundamental, self.min_score, self.max_score)

        return fundamental

    def analyze_distribution(
        self,
        scores: np.ndarray,
    ) -> dict:
        """
        Analyze score distribution

        Args:
            scores: Array of scores

        Returns:
            Distribution statistics
        """
        return {
            'min': float(np.min(scores)),
            'max': float(np.max(scores)),
            'mean': float(np.mean(scores)),
            'median': float(np.median(scores)),
            'std': float(np.std(scores)),
            'percentile_25': float(np.percentile(scores, 25)),
            'percentile_75': float(np.percentile(scores, 75)),
        }


# Global scorer instance
_scorer_instance = None


def get_scorer() -> OnChainScorer:
    """Get global scorer instance (singleton)"""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = OnChainScorer()
    return _scorer_instance
