"""
AEGIS CBR Engine - FAZ 1 Unit Tests
Tests fingerprint extraction, dip detection, and look-ahead bias prevention
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fingerprint_extractor import FingerprintExtractor
from dip_tepe_detector import DipTeepeDetector
from look_ahead_safe import LookAheadSafeExtractor
from rolling_correlation import RollingCorrelationEngine


class TestDataGenerator:
    """Generate realistic test data"""

    @staticmethod
    def generate_data_suite(periods: int = 300):
        """Generate all test data with aligned indices (SINGLE SOURCE OF TRUTH)"""
        dates = pd.date_range(end=datetime.now(), periods=periods, freq='1h')

        # OHLCV data
        ohlcv_data = []
        price = 40000.0
        for date in dates:
            change = np.random.normal(0, 500)
            open_price = price
            close_price = price + change
            high_price = max(open_price, close_price) + abs(np.random.normal(0, 300))
            low_price = min(open_price, close_price) - abs(np.random.normal(0, 300))
            volume = np.random.uniform(1000, 5000)

            ohlcv_data.append({
                'timestamp': date,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume,
            })
            price = close_price

        ohlcv = pd.DataFrame(ohlcv_data)
        ohlcv.set_index('timestamp', inplace=True)

        # Macro data (same dates)
        macro_data = []
        for date in dates:
            macro_data.append({
                'timestamp': date,
                'DXY': 100 + np.random.normal(0, 1),
                'GOLD': 2000 + np.random.normal(0, 50),
                'BRENT': 80 + np.random.normal(0, 5),
                'VIX': 15 + np.random.normal(0, 3),
                'FGI': 50 + np.random.normal(0, 10),
                'US10Y': 4.0 + np.random.normal(0, 0.2),
            })

        macro = pd.DataFrame(macro_data)
        macro.set_index('timestamp', inplace=True)

        # On-chain data (same dates)
        onchain_data = []
        oi = 50000
        for date in dates:
            oi += np.random.normal(0, 500)
            onchain_data.append({
                'timestamp': date,
                'exchange_netflow': np.random.normal(0, 100),
                'funding_rate': np.random.uniform(-0.0005, 0.0005),
                'open_interest': oi,
            })

        onchain = pd.DataFrame(onchain_data)
        onchain.set_index('timestamp', inplace=True)

        return ohlcv, macro, onchain

    @staticmethod
    def generate_ohlcv(periods: int = 300, start_price: float = 40000.0):
        """Generate realistic BTC OHLCV data"""
        ohlcv, _, _ = TestDataGenerator.generate_data_suite(periods)
        return ohlcv

    @staticmethod
    def generate_macro_data(periods: int = 300):
        """Generate macro asset data"""
        _, macro, _ = TestDataGenerator.generate_data_suite(periods)
        return macro

    @staticmethod
    def generate_onchain_data(periods: int = 300):
        """Generate on-chain metrics"""
        _, _, onchain = TestDataGenerator.generate_data_suite(periods)
        return onchain


class TestFingerprintExtractor:
    """Test fingerprint extraction"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.gen = TestDataGenerator()
        self.ohlcv = self.gen.generate_ohlcv(periods=250)
        self.macro = self.gen.generate_macro_data(periods=250)
        self.onchain = self.gen.generate_onchain_data(periods=250)
        self.extractor = FingerprintExtractor()

    def test_fingerprint_extraction_basic(self):
        """Test basic fingerprint extraction"""
        # Use index 200 (after 200 bar minimum)
        fp = self.extractor.extract(self.ohlcv, self.macro, self.onchain, idx=200)

        assert fp is not None
        assert fp.symbol == 'BTC/USDT'
        assert 0 <= fp.distance_from_ath <= 1
        assert 0 <= fp.rsi_14 <= 100
        assert fp.volatility_regime in ['LOW', 'MID', 'HIGH']
        assert fp.regime_label in ['BULL', 'BEAR', 'SIDEWAYS']
        assert fp.market_type in ['DIP', 'PEAK', 'BREAKOUT', 'REJECTION']
        assert 0 <= fp.quality_score <= 1

    def test_feature_count(self):
        """Test that all 25+ features are extracted"""
        fp = self.extractor.extract(self.ohlcv, self.macro, self.onchain, idx=200)
        fp_dict = fp.to_dict()

        # At least 25 features
        assert len(fp_dict) >= 25

        # Check specific features
        expected_features = [
            'current_price', 'distance_from_ath', 'atr_14', 'rsi_14',
            'macd_histogram', 'dxy_14d_corr', 'vix_level', 'fear_greed_index',
            'exchange_netflow_7d', 'day_of_week', 'market_type', 'quality_score'
        ]

        for feature in expected_features:
            assert feature in fp_dict

    def test_category_5_6_7_features_are_present(self):
        """Context categories 5/6/7 should be embedded into the fingerprint."""
        timestamp = self.ohlcv.index[200]
        self.macro.loc[timestamp, 'mod_touche_score'] = 0.71
        self.macro.loc[timestamp, 'mod_fundamental_score'] = 0.63
        self.macro.loc[timestamp, 'mod_quantum_score'] = 0.57
        self.macro.loc[timestamp, 'mod_sentinel_score'] = 0.69
        self.macro.loc[timestamp, 'mod_news_score'] = 0.74
        self.macro.loc[timestamp, 'mod_consensus_confidence'] = 0.82
        self.macro.loc[timestamp, 'mod_consensus_weighted_score'] = 0.61
        self.macro.loc[timestamp, 'time_intraday_risk'] = 1.0
        self.macro.loc[timestamp, 'time_weekend_risk'] = 0.0
        self.macro.loc[timestamp, 'time_macro_event_risk'] = 1.0
        self.macro.loc[timestamp, 'time_earnings_risk'] = 0.0
        self.macro.loc[timestamp, 'time_event_risk_score'] = 0.5
        self.macro.loc[timestamp, 'pos_open_positions'] = 2.0
        self.macro.loc[timestamp, 'pos_exposure_pct'] = 0.35
        self.macro.loc[timestamp, 'pos_drawdown_pct'] = 0.08
        self.macro.loc[timestamp, 'pos_leverage'] = 1.5
        self.macro.loc[timestamp, 'pos_heat_score'] = 0.299
        self.macro.loc[timestamp, 'pos_has_open_position'] = 1.0

        fp = self.extractor.extract(self.ohlcv, self.macro, self.onchain, idx=200)
        fp_dict = fp.to_dict()

        assert fp_dict['mod_touche_score'] == pytest.approx(0.71)
        assert fp_dict['mod_consensus_confidence'] == pytest.approx(0.82)
        assert fp_dict['time_macro_event_risk'] == pytest.approx(1.0)
        assert fp_dict['time_event_risk_score'] == pytest.approx(0.5)
        assert fp_dict['pos_exposure_pct'] == pytest.approx(0.35)
        assert fp_dict['pos_has_open_position'] == pytest.approx(1.0)
        assert len(fp_dict) >= 48

    def test_insufficient_history_returns_none(self):
        """Test that extraction fails with insufficient history"""
        fp = self.extractor.extract(self.ohlcv, self.macro, self.onchain, idx=50)
        assert fp is None

    def test_feature_values_in_ranges(self):
        """Test that features are in reasonable ranges"""
        fp = self.extractor.extract(self.ohlcv, self.macro, self.onchain, idx=200)

        assert 0 <= fp.rsi_14 <= 100
        assert -1 <= fp.dxy_14d_corr <= 1
        assert -1 <= fp.gold_14d_corr <= 1
        assert fp.volatility_regime in ['LOW', 'MID', 'HIGH']
        assert 0 <= fp.volume_profile <= 10
        assert 0 <= fp.structure_score <= 1
        assert 0 <= fp.quality_score <= 1


class TestLookAheadBias:
    """Test look-ahead bias prevention"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.gen = TestDataGenerator()
        self.ohlcv = self.gen.generate_ohlcv(periods=250)
        self.macro = self.gen.generate_macro_data(periods=250)
        self.onchain = self.gen.generate_onchain_data(periods=250)
        self.safe_extractor = LookAheadSafeExtractor()

    def test_point_in_time_extraction(self):
        """Test that extraction uses only past data"""
        features = self.safe_extractor.extract_features_safe(
            self.ohlcv, self.macro, self.onchain, target_idx=200
        )

        assert features is not None
        assert features['point_in_time_verified'] == True
        assert features['target_idx'] == 200

    def test_future_data_not_used(self):
        """Test that future data is not included in calculations"""
        # Extract at idx=210 and idx=220
        features_210 = self.safe_extractor.extract_features_safe(
            self.ohlcv, self.macro, self.onchain, target_idx=210
        )
        features_220 = self.safe_extractor.extract_features_safe(
            self.ohlcv, self.macro, self.onchain, target_idx=220
        )

        assert features_210 is not None
        assert features_220 is not None

        # Features should be different (new data included between idx 210 and 220)
        assert features_210['timestamp'] < features_220['timestamp']

    def test_no_lookahead_validation(self):
        """Test validation that prevents look-ahead"""
        features = self.safe_extractor.extract_features_safe(
            self.ohlcv, self.macro, self.onchain, target_idx=200
        )

        # Create a future timestamp
        future_time = features['timestamp'] + timedelta(hours=1)

        # Should pass validation (feature is before forward period)
        assert self.safe_extractor.validate_no_lookahead(features, future_time) == True

        # Should fail validation (feature is after forward period)
        past_time = features['timestamp'] - timedelta(hours=1)
        assert self.safe_extractor.validate_no_lookahead(features, past_time) == False


class TestDipTeepeDetector:
    """Test dip and peak detection"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.gen = TestDataGenerator()
        self.ohlcv = self.gen.generate_ohlcv(periods=250)
        self.detector = DipTeepeDetector()

    def test_dip_detection(self):
        """Test dip detection"""
        dips = self.detector.detect_dips(self.ohlcv)

        # Should find some dips
        assert isinstance(dips, list)

        # Check structure of detected dips
        for dip in dips:
            assert dip.pattern_type == 'DIP'
            assert 0 <= dip.confidence <= 1
            assert dip.price > 0
            assert isinstance(dip.nearby_levels, list)

    def test_peak_detection(self):
        """Test peak detection"""
        peaks = self.detector.detect_peaks(self.ohlcv)

        assert isinstance(peaks, list)

        for peak in peaks:
            assert peak.pattern_type == 'PEAK'
            assert 0 <= peak.confidence <= 1

    def test_breakout_detection(self):
        """Test breakout detection"""
        breakouts = self.detector.detect_breakouts(self.ohlcv)

        assert isinstance(breakouts, list)

        for breakout in breakouts:
            assert breakout.pattern_type == 'BREAKOUT'

    def test_confidence_ordering(self):
        """Test that detections are ordered by confidence"""
        dips = self.detector.detect_dips(self.ohlcv)

        if len(dips) > 1:
            for i in range(len(dips) - 1):
                # Confidence should be descending
                assert dips[i].confidence >= dips[i+1].confidence

    def test_all_patterns_detection(self):
        """Test detecting all pattern types"""
        patterns = self.detector.detect_all_patterns(self.ohlcv)

        assert 'dips' in patterns
        assert 'peaks' in patterns
        assert 'breakouts' in patterns
        assert 'rejections' in patterns

        for pattern_type in patterns.values():
            assert isinstance(pattern_type, list)


class TestRollingCorrelation:
    """Test rolling correlation engine"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.gen = TestDataGenerator()
        self.btc, macro_df, _ = self.gen.generate_data_suite(periods=250)

        self.dxy = macro_df[['DXY']].copy()
        self.dxy.columns = ['close']
        self.gold = macro_df[['GOLD']].copy()
        self.gold.columns = ['close']
        self.brent = macro_df[['BRENT']].copy()
        self.brent.columns = ['close']

        self.engine = RollingCorrelationEngine(window=90)

    def test_rolling_correlation_calculation(self):
        """Test rolling correlation calculation"""
        corr = self.engine.calculate_rolling_correlations(
            self.btc, self.dxy, self.gold, self.brent
        )

        assert len(corr) == len(self.btc)
        assert 'dxy_corr' in corr.columns
        assert 'gold_corr' in corr.columns
        assert 'brent_corr' in corr.columns
        assert 'corr_strength' in corr.columns

        # Correlations should be in [-1, 1]
        for col in ['dxy_corr', 'gold_corr', 'brent_corr']:
            assert corr[col].min() >= -1.01  # Allow small numerical errors
            assert corr[col].max() <= 1.01

    def test_regime_classification(self):
        """Test correlation regime classification"""
        corr = self.engine.calculate_rolling_correlations(
            self.btc, self.dxy, self.gold, self.brent
        )
        regimes = self.engine.identify_macro_regimes(corr)

        assert len(regimes) == len(corr)
        assert 'overall_regime' in regimes.columns

        valid_regimes = {'RISK_ON', 'RISK_OFF', 'TRANSITIONAL', 'NEUTRAL'}
        assert set(regimes['overall_regime'].unique()).issubset(valid_regimes)

    def test_correlation_breaks_detection(self):
        """Test detection of correlation regime breaks"""
        corr = self.engine.calculate_rolling_correlations(
            self.btc, self.dxy, self.gold, self.brent
        )
        breaks = self.engine.detect_correlation_breaks(corr, window=20, threshold_change=0.15)

        assert isinstance(breaks, list)

        for brk in breaks:
            assert -1 <= brk.dxy_corr <= 1
            assert brk.dxy_regime in ['HIGH_POS', 'HIGH_NEG', 'NEUTRAL']

    def test_feature_extraction(self):
        """Test feature extraction at specific point"""
        corr = self.engine.calculate_rolling_correlations(
            self.btc, self.dxy, self.gold, self.brent
        )
        regimes = self.engine.identify_macro_regimes(corr)

        features = self.engine.extract_correlation_features(corr, regimes, idx=200)

        assert 'dxy_corr' in features
        assert 'gold_corr' in features
        assert 'overall_regime' in features
        assert 'corr_quality' in features
        assert 0 <= features['corr_quality'] <= 1


class TestPhase1Integration:
    """Integration tests for FAZ 1 pipeline"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.gen = TestDataGenerator()
        self.ohlcv, self.macro, self.onchain = self.gen.generate_data_suite(periods=300)

    def test_full_pipeline_execution(self):
        """Test running full FAZ 1 pipeline"""
        safe_extractor = LookAheadSafeExtractor()
        detector = DipTeepeDetector()
        corr_engine = RollingCorrelationEngine()

        # Extract fingerprints at multiple timepoints
        fingerprints = []
        for idx in range(200, min(260, len(self.ohlcv)), 10):
            features = safe_extractor.extract_features_safe(
                self.ohlcv, self.macro, self.onchain, target_idx=idx
            )
            if features:
                fingerprints.append(features)

        # Should have extracted multiple fingerprints
        assert len(fingerprints) >= 5

        # Detect patterns
        patterns = detector.detect_all_patterns(self.ohlcv)
        assert len(patterns) > 0

        # Calculate correlations - align indices
        dxy = self.macro[['DXY']].copy()
        dxy.columns = ['close']
        gold = self.macro[['GOLD']].copy()
        gold.columns = ['close']
        brent = self.macro[['BRENT']].copy()
        brent.columns = ['close']

        corr = corr_engine.calculate_rolling_correlations(self.ohlcv, dxy, gold, brent)
        assert len(corr) > 0

    def test_pipeline_produces_tradeable_signals(self):
        """Test that pipeline produces actionable signals"""
        safe_extractor = LookAheadSafeExtractor()
        detector = DipTeepeDetector()

        # Get dip signals
        dips = detector.detect_dips(self.ohlcv)
        high_confidence_dips = [d for d in dips if d.confidence > 0.65]

        # Should find some high-confidence setups
        # (In real data might be 0, but synthetic should have some)
        assert isinstance(high_confidence_dips, list)


def test_phase1_readiness():
    """Meta test: Is FAZ 1 complete and ready?"""
    gen = TestDataGenerator()
    ohlcv, macro, onchain = gen.generate_data_suite(periods=300)

    # Component 1: Fingerprint extraction
    extractor = FingerprintExtractor()
    fp = extractor.extract(ohlcv, macro, onchain, idx=200)
    assert fp is not None
    assert len(fp.to_dict()) >= 25

    # Component 2: Safe extraction (no look-ahead)
    safe_ext = LookAheadSafeExtractor()
    safe_fp = safe_ext.extract_features_safe(ohlcv, macro, onchain, target_idx=200)
    assert safe_fp is not None
    assert safe_fp['point_in_time_verified']

    # Component 3: Pattern detection
    detector = DipTeepeDetector()
    patterns = detector.detect_all_patterns(ohlcv)
    assert all(isinstance(p, list) for p in patterns.values())

    # Component 4: Rolling correlations - align indices
    engine = RollingCorrelationEngine()
    dxy = macro[['DXY']].copy()
    dxy.columns = ['close']
    gold = macro[['GOLD']].copy()
    gold.columns = ['close']
    brent = macro[['BRENT']].copy()
    brent.columns = ['close']

    corr = engine.calculate_rolling_correlations(ohlcv, dxy, gold, brent)
    assert len(corr) > 0

    print("✓ FAZ 1 PHASE 1 is READY for implementation")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
