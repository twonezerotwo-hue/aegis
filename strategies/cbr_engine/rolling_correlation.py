"""
AEGIS CBR Engine - Rolling Correlation Analysis
Calculates 90-day rolling correlations between BTC and macro assets
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CorrelationBreakdown:
    """Track correlation regime breaks"""
    timestamp: pd.Timestamp
    dxy_corr: float
    gold_corr: float
    brent_corr: float
    dxy_regime: str  # HIGH_POS, NEUTRAL, HIGH_NEG
    gold_regime: str
    brent_regime: str
    correlation_strength: float  # 0.0-1.0


class RollingCorrelationEngine:
    """
    Calculate and analyze rolling correlations between BTC and macro assets.

    Key insight: Correlation regimes are different from price regimes.
    A DXY correlation break can signal regime shift even if price hasn't moved much.
    """

    def __init__(self, window: int = 90):
        """
        Args:
            window: Rolling window size (days) for correlation calculation
        """
        self.window = window

    def calculate_rolling_correlations(
        self,
        btc_data: pd.DataFrame,  # Must have 'close' column
        dxy_data: pd.DataFrame,  # DXY prices
        gold_data: pd.DataFrame,  # Gold prices
        brent_data: pd.DataFrame,  # Brent oil prices
    ) -> pd.DataFrame:
        """
        Calculate rolling correlations between BTC and macro assets.

        Args:
            btc_data: BTC OHLCV data with 'close' column
            dxy_data: DXY price data
            gold_data: Gold price data
            brent_data: Brent oil price data

        Returns:
            DataFrame with columns: dxy_corr, gold_corr, brent_corr, corr_strength
        """
        # Calculate returns (log returns for stability)
        btc_returns = np.log(btc_data['close'] / btc_data['close'].shift(1))
        dxy_returns = np.log(dxy_data['close'] / dxy_data['close'].shift(1))
        gold_returns = np.log(gold_data['close'] / gold_data['close'].shift(1))
        brent_returns = np.log(brent_data['close'] / brent_data['close'].shift(1))

        # Align indices
        aligned = pd.DataFrame({
            'btc_ret': btc_returns,
            'dxy_ret': dxy_returns,
            'gold_ret': gold_returns,
            'brent_ret': brent_returns
        })

        # Calculate rolling correlations
        results = pd.DataFrame(index=aligned.index)

        # DXY correlation (typical: -0.5 to -0.1 during normal periods)
        results['dxy_corr'] = aligned['btc_ret'].rolling(self.window).corr(aligned['dxy_ret'])

        # Gold correlation (typical: 0.0 to 0.4, negative during risk-off)
        results['gold_corr'] = aligned['btc_ret'].rolling(self.window).corr(aligned['gold_ret'])

        # Brent correlation (typical: 0.3 to 0.6, risk-on proxy)
        results['brent_corr'] = aligned['btc_ret'].rolling(self.window).corr(aligned['brent_ret'])

        # Correlation strength (mean absolute of three correlations)
        results['corr_strength'] = (
            results['dxy_corr'].abs() +
            results['gold_corr'].abs() +
            results['brent_corr'].abs()
        ) / 3.0

        # Clean NaN values
        results = results.fillna(0.0)

        return results

    def classify_correlation_regime(self, corr: float) -> str:
        """
        Classify correlation regime

        Args:
            corr: Correlation value (-1.0 to 1.0)

        Returns:
            Regime string
        """
        if corr >= 0.3:
            return 'HIGH_POS'
        elif corr <= -0.3:
            return 'HIGH_NEG'
        else:
            return 'NEUTRAL'

    def detect_correlation_breaks(
        self,
        correlations: pd.DataFrame,
        window: int = 20,
        threshold_change: float = 0.2
    ) -> List[CorrelationBreakdown]:
        """
        Detect significant correlation regime breaks.

        A regime break is when correlation changes significantly.
        This often precedes major price moves.

        Args:
            correlations: DataFrame from calculate_rolling_correlations()
            window: Lookback window for change detection
            threshold_change: Minimum correlation change to flag as break

        Returns:
            List of detected breaks with metadata
        """
        breaks = []

        for i in range(window, len(correlations)):
            current = correlations.iloc[i]

            # Get previous regime (window bars ago)
            previous = correlations.iloc[i - window]

            # Check for significant changes
            dxy_change = abs(current['dxy_corr'] - previous['dxy_corr'])
            gold_change = abs(current['gold_corr'] - previous['gold_corr'])
            brent_change = abs(current['brent_corr'] - previous['brent_corr'])

            if (dxy_change > threshold_change or
                gold_change > threshold_change or
                brent_change > threshold_change):

                breakdown = CorrelationBreakdown(
                    timestamp=correlations.index[i],
                    dxy_corr=current['dxy_corr'],
                    gold_corr=current['gold_corr'],
                    brent_corr=current['brent_corr'],
                    dxy_regime=self.classify_correlation_regime(current['dxy_corr']),
                    gold_regime=self.classify_correlation_regime(current['gold_corr']),
                    brent_regime=self.classify_correlation_regime(current['brent_corr']),
                    correlation_strength=current['corr_strength']
                )
                breaks.append(breakdown)

        return breaks

    def identify_macro_regimes(
        self,
        correlations: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Classify correlation regimes at each point in time.

        Returns:
            DataFrame with regime classifications
        """
        regimes = pd.DataFrame(index=correlations.index)

        regimes['dxy_regime'] = correlations['dxy_corr'].apply(
            self.classify_correlation_regime
        )
        regimes['gold_regime'] = correlations['gold_corr'].apply(
            self.classify_correlation_regime
        )
        regimes['brent_regime'] = correlations['brent_corr'].apply(
            self.classify_correlation_regime
        )

        # Compound regime (crypto-macro alignment)
        regimes['overall_regime'] = self._classify_overall_regime(correlations)

        return regimes

    def _classify_overall_regime(self, correlations: pd.DataFrame) -> pd.Series:
        """
        Classify overall macro-crypto regime.

        Risk-On: BTC-Brent high pos, BTC-DXY high neg (risky assets correlate positively)
        Risk-Off: BTC correlates with DXY (flight to safety), low oil correlation
        Transitional: Unstable correlations
        """
        regimes = []

        for i in range(len(correlations)):
            row = correlations.iloc[i]

            # Risk-On: Brent high pos + DXY high neg
            if row['brent_corr'] > 0.3 and row['dxy_corr'] < -0.3:
                regimes.append('RISK_ON')
            # Risk-Off: DXY high pos + Brent low
            elif row['dxy_corr'] > 0.3 and row['brent_corr'] < 0.1:
                regimes.append('RISK_OFF')
            # Transitional: High correlation strength but conflicting
            elif row['corr_strength'] > 0.4:
                regimes.append('TRANSITIONAL')
            else:
                regimes.append('NEUTRAL')

        return pd.Series(regimes, index=correlations.index)

    def calculate_correlation_momentum(
        self,
        correlations: pd.DataFrame,
        window: int = 20
    ) -> pd.DataFrame:
        """
        Calculate momentum of correlation changes (acceleration/deceleration).

        Fast correlation changes may signal rapid regime shifts.

        Args:
            correlations: DataFrame from calculate_rolling_correlations()
            window: Window for momentum calculation

        Returns:
            DataFrame with momentum indicators
        """
        momentum = pd.DataFrame(index=correlations.index)

        # DXY correlation momentum (acceleration of change)
        dxy_vel = correlations['dxy_corr'].diff()
        momentum['dxy_accel'] = dxy_vel.rolling(window).std()

        # Gold correlation momentum
        gold_vel = correlations['gold_corr'].diff()
        momentum['gold_accel'] = gold_vel.rolling(window).std()

        # Brent correlation momentum
        brent_vel = correlations['brent_corr'].diff()
        momentum['brent_accel'] = brent_vel.rolling(window).std()

        # Overall momentum (mean of accelerations)
        momentum['overall_momentum'] = (
            momentum['dxy_accel'] +
            momentum['gold_accel'] +
            momentum['brent_accel']
        ) / 3.0

        return momentum.fillna(0.0)

    def find_anomalous_correlations(
        self,
        correlations: pd.DataFrame,
        percentile_threshold: float = 95
    ) -> List[Tuple[pd.Timestamp, float]]:
        """
        Find periods with anomalous (extreme) correlations.

        These periods may signal market stress or unusual macro conditions.

        Args:
            correlations: DataFrame from calculate_rolling_correlations()
            percentile_threshold: Percentile to flag as anomalous

        Returns:
            List of (timestamp, anomaly_score) tuples
        """
        anomalies = []

        # Calculate composite anomaly score
        dxy_anomaly = (
            (correlations['dxy_corr'].abs() - correlations['dxy_corr'].abs().quantile(0.5)) /
            (correlations['dxy_corr'].abs().std() + 0.01)
        )

        gold_anomaly = (
            (correlations['gold_corr'].abs() - correlations['gold_corr'].abs().quantile(0.5)) /
            (correlations['gold_corr'].abs().std() + 0.01)
        )

        brent_anomaly = (
            (correlations['brent_corr'].abs() - correlations['brent_corr'].abs().quantile(0.5)) /
            (correlations['brent_corr'].abs().std() + 0.01)
        )

        composite_anomaly = (dxy_anomaly + gold_anomaly + brent_anomaly) / 3.0
        threshold = composite_anomaly.quantile(percentile_threshold / 100)

        for i in range(len(correlations)):
            if composite_anomaly.iloc[i] > threshold:
                anomalies.append((
                    correlations.index[i],
                    float(composite_anomaly.iloc[i])
                ))

        return anomalies

    def extract_correlation_features(
        self,
        correlations: pd.DataFrame,
        regimes: pd.DataFrame,
        idx: int
    ) -> Dict:
        """
        Extract correlation-based features for a specific point in time.

        Args:
            correlations: Rolling correlations
            regimes: Regime classifications
            idx: Current index

        Returns:
            Dict with correlation features
        """
        if idx >= len(correlations):
            idx = len(correlations) - 1

        corr_row = correlations.iloc[idx]
        regime_row = regimes.iloc[idx]

        return {
            'dxy_corr': float(corr_row['dxy_corr']),
            'gold_corr': float(corr_row['gold_corr']),
            'brent_corr': float(corr_row['brent_corr']),
            'corr_strength': float(corr_row['corr_strength']),
            'dxy_regime': regime_row['dxy_regime'],
            'gold_regime': regime_row['gold_regime'],
            'brent_regime': regime_row['brent_regime'],
            'overall_regime': regime_row['overall_regime'],
            'corr_quality': self._rate_correlation_quality(corr_row),
        }

    def _rate_correlation_quality(self, corr_row) -> float:
        """
        Rate correlation data quality (0-1).

        Higher values = more stable, interpretable correlations.
        """
        strength = corr_row['corr_strength']

        # Medium strength is good (0.3-0.5)
        if 0.3 <= strength <= 0.5:
            return 0.8
        elif 0.2 <= strength < 0.3 or 0.5 < strength <= 0.6:
            return 0.6
        else:
            return 0.3

    def backtest_correlation_signal(
        self,
        correlations: pd.DataFrame,
        forward_returns: pd.Series,
        regime_filter: str = None
    ) -> Dict:
        """
        Backtest correlation-based trading signal performance.

        Args:
            correlations: Rolling correlations
            forward_returns: Forward returns (1h, 4h, 24h, etc)
            regime_filter: Optional regime to filter for (RISK_ON, RISK_OFF, etc)

        Returns:
            Dict with signal stats
        """
        regimes = self.identify_macro_regimes(correlations)

        # Filter by regime if specified
        if regime_filter:
            mask = regimes['overall_regime'] == regime_filter
            filtered_corr = correlations[mask]
            filtered_returns = forward_returns[mask]
        else:
            filtered_corr = correlations
            filtered_returns = forward_returns

        # Signal: Buy when DXY-BTC correlation breaks negative (flight to crypto)
        # This is a simple signal for backtesting
        dxy_signal = filtered_corr['dxy_corr'] < -0.3

        if dxy_signal.sum() == 0:
            return {
                'signal': None,
                'sample_count': 0,
                'win_rate': 0.0,
                'avg_return': 0.0,
            }

        signal_returns = filtered_returns[dxy_signal]

        return {
            'signal': 'BTC_FLIGHT_TO_CRYPTO',
            'sample_count': int(dxy_signal.sum()),
            'win_rate': float((signal_returns > 0).sum() / len(signal_returns)) if len(signal_returns) > 0 else 0.0,
            'avg_return': float(signal_returns.mean()),
            'std_return': float(signal_returns.std()),
        }
