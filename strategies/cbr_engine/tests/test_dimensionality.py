"""
AEGIS CBR Engine - FAZ 2: Dimensionality Reduction Tests
Test PCA, Autoencoder, and hybrid reduction methods
"""

import pytest
import numpy as np
import pandas as pd
import sys
from pathlib import Path
import tempfile
import os

sys.path.insert(0, str(Path(__file__).parent.parent))

from dimensionality_reducer import (
    DimensionalityReducer, AutoencoderReducer, HybridReducer, DimensionalityResult
)


class TestDataGenerator:
    """Generate test features"""

    @staticmethod
    def generate_features(n_samples: int = 200, n_features: int = 25) -> np.ndarray:
        """Generate synthetic feature matrix"""
        np.random.seed(42)
        # Create correlated features (realistic scenario)
        X = np.random.randn(n_samples, n_features)

        # Add correlations
        for i in range(5, n_features):
            X[:, i] += 0.5 * X[:, i-5]

        return X

    @staticmethod
    def generate_features_df(n_samples: int = 200) -> pd.DataFrame:
        """Generate feature DataFrame"""
        features = TestDataGenerator.generate_features(n_samples, 25)
        feature_cols = [f'feature_{i}' for i in range(25)]

        return pd.DataFrame(features, columns=feature_cols)


class TestDimensionalityReducer:
    """Test PCA-based dimensionality reduction"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.X = TestDataGenerator.generate_features(n_samples=200, n_features=25)
        self.df = TestDataGenerator.generate_features_df(n_samples=200)
        self.reducer = DimensionalityReducer(target_components=12, variance_threshold=0.95)

    def test_initialization(self):
        """Test reducer initialization"""
        assert self.reducer.target_components == 12
        assert self.reducer.variance_threshold == 0.95
        assert self.reducer.pca is None

    def test_fit(self):
        """Test fitting on DataFrame"""
        result = self.reducer.fit(self.df)

        assert result is not None  # Reducer returns DimensionalityResult
        # Result should have components
        assert result.reduced_features >= 10
        assert result.explained_variance > 0.95

    def test_transform(self):
        """Test transform after fitting"""
        self.reducer.fit(self.df)
        X_reduced = self.reducer.transform(self.df)

        # Should have >= 10 PC columns
        pc_cols = [c for c in X_reduced.columns if c.startswith('PC')]
        assert len(pc_cols) >= 10
        # Should be finite
        assert X_reduced[pc_cols].isnull().sum().sum() == 0

    def test_fit_transform(self):
        """Test fit -> transform pipeline"""
        self.reducer.fit(self.df)
        X_reduced = self.reducer.transform(self.df)

        pc_cols = [c for c in X_reduced.columns if c.startswith('PC')]
        assert len(pc_cols) >= 10
        assert X_reduced[pc_cols].isnull().sum().sum() == 0

    def test_explained_variance(self):
        """Test explained variance > 95%"""
        self.reducer.fit(self.df)

        explained_var = np.sum(self.reducer.pca.explained_variance_ratio_)

        # Should be > 95%
        assert explained_var > 0.95
        print(f"Explained variance: {explained_var:.2%}")

    def test_variance_by_component(self):
        """Test variance decreases by component"""
        self.reducer.fit(self.df)

        variances = self.reducer.pca.explained_variance_ratio_

        # First component should have highest variance
        assert variances[0] == variances.max()

        # Variances should be decreasing
        for i in range(len(variances) - 1):
            assert variances[i] >= variances[i + 1]

    def test_feature_importance(self):
        """Test feature importance calculation"""
        self.reducer.fit(self.df)
        importance_df = self.reducer.get_feature_importance()

        # Should have features in index
        assert len(importance_df) > 0
        assert 'importance' in importance_df.columns
        assert importance_df['importance'].sum() > 0

    def test_save_load(self):
        """Test saving and loading model"""
        self.reducer.fit(self.df)

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, 'reducer.pkl')

            # Save
            self.reducer.save(model_path)
            assert os.path.exists(model_path)

            # Load
            loaded_reducer = DimensionalityReducer.load(model_path)

            # Test loaded model
            X_reduced_orig = self.reducer.transform(self.df.iloc[:10])
            X_reduced_loaded = loaded_reducer.transform(self.df.iloc[:10])

            # Should produce same results
            pd.testing.assert_frame_equal(X_reduced_orig, X_reduced_loaded)

    def test_reduce_variance_report(self):
        """Test variance reduction report"""
        self.reducer.fit(self.df)
        report = self.reducer.reduce_variance_report()

        assert 'total_components' in report
        assert 'explained_variance_ratio' in report
        assert 'variance_by_component' in report
        assert report['explained_variance_ratio'] > 0.95

    def test_dimensionality_result(self):
        """Test DimensionalityResult dataclass"""
        self.reducer.fit(self.df)

        result = DimensionalityResult(
            original_features=25,
            reduced_features=12,
            explained_variance=0.96,
            pca_components=self.reducer.pca.components_,
            scaler=self.reducer.scaler,
            feature_names=[f'f_{i}' for i in range(25)],
            reduction_ratio=12/25
        )

        assert result.original_features == 25
        assert result.reduced_features == 12
        assert result.reduction_ratio == 0.48


class TestAutoEncoderReducer:
    """Test Autoencoder-based reduction (if TensorFlow available)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup"""
        self.X = TestDataGenerator.generate_features(n_samples=100, n_features=25)
        self.df = TestDataGenerator.generate_features_df(n_samples=100)
        self.reducer = AutoencoderReducer(encoding_dim=12, epochs=5)

    def test_initialization(self):
        """Test initialization"""
        assert self.reducer.encoding_dim == 12
        assert self.reducer.epochs == 5

    def test_fit(self):
        """Test fitting (skip if TensorFlow not available)"""
        if not self.reducer.has_tensorflow:
            pytest.skip("TensorFlow not available")

        history = self.reducer.fit(self.df)

        assert history is not None
        assert 'loss' in history or self.reducer.autoencoder is not None

    def test_transform(self):
        """Test transform"""
        if not self.reducer.has_tensorflow:
            pytest.skip("TensorFlow not available")

        self.reducer.fit(self.df)
        X_encoded = self.reducer.transform(self.df)

        if X_encoded is not None:
            assert X_encoded.shape[0] == len(self.df)
            assert X_encoded.shape[1] == 12


class TestHybridReducer:
    """Test combined PCA + Autoencoder"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup"""
        self.X = TestDataGenerator.generate_features(n_samples=100, n_features=25)
        self.df = TestDataGenerator.generate_features_df(n_samples=100)
        self.hybrid = HybridReducer(pca_components=8, ae_components=8)

    def test_fit(self):
        """Test fitting hybrid model"""
        self.hybrid.fit(self.df)

        assert self.hybrid.pca_reducer.pca is not None
        # Autoencoder fitting may be skipped if TensorFlow not available

    def test_transform(self):
        """Test hybrid transform"""
        self.hybrid.fit(self.df)
        X_combined = self.hybrid.transform(self.df)

        # Should have at least PCA columns
        pca_cols = [c for c in X_combined.columns if c.startswith('PC')]
        assert len(pca_cols) >= 8


class TestPhase2Integration:
    """Integration tests for FAZ 2"""

    def test_full_pipeline(self):
        """Test complete dimensionality reduction pipeline"""
        # Generate realistic fingerprints
        df = TestDataGenerator.generate_features_df(n_samples=300)

        # Fit reducer
        reducer = DimensionalityReducer(target_components=12)
        reducer.fit(df)
        reduced = reducer.transform(df)

        # Validate
        pc_cols = [c for c in reduced.columns if c.startswith('PC')]
        assert len(pc_cols) >= 10

        # Check variance
        explained = reducer.reduce_variance_report()
        assert explained['explained_variance_ratio'] > 0.95

        # Test on new data
        new_df = TestDataGenerator.generate_features_df(n_samples=50)
        new_reduced = reducer.transform(new_df)

        pc_cols_new = [c for c in new_reduced.columns if c.startswith('PC')]
        assert len(pc_cols_new) >= 10

    def test_dimensionality_reduction_quality(self):
        """Test that reduction maintains information quality"""
        df = TestDataGenerator.generate_features_df(n_samples=200)

        reducer = DimensionalityReducer(target_components=15)
        reducer.fit(df)
        reduced = reducer.transform(df)

        # Original variance
        orig_var = df.values.var(axis=0).sum()

        # Reduced variance (should preserve most information)
        reduced_val = reduced[[c for c in reduced.columns if c.startswith('PC')]].values
        reduced_var = reduced_val.var(axis=0).sum()

        # Ratio should be high (most variance preserved)
        preservation_ratio = reduced_var / orig_var

        print(f"Variance preservation: {preservation_ratio:.2%}")
        assert preservation_ratio > 0.5  # At least 50% of variance preserved


def test_faz2_readiness():
    """Meta test: Is FAZ 2 complete and ready?"""
    # Generate test data
    df = TestDataGenerator.generate_features_df(n_samples=250)

    # Component 1: PCA reduction
    pca_reducer = DimensionalityReducer(target_components=12)
    result = pca_reducer.fit(df)
    X_pca = pca_reducer.transform(df)

    pc_cols = [c for c in X_pca.columns if c.startswith('PC')]
    assert len(pc_cols) >= 10
    assert pca_reducer.reduce_variance_report()['explained_variance_ratio'] > 0.95

    # Component 2: Hybrid reduction
    hybrid = HybridReducer(pca_components=8, ae_components=8)
    hybrid.fit(df)
    X_hybrid = hybrid.transform(df)

    assert X_hybrid.shape[0] == 250

    # Component 3: Model persistence
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, 'model.pkl')
        pca_reducer.save(path)

        loaded = DimensionalityReducer.load(path)
        X_reloaded = loaded.transform(df)

        pd.testing.assert_frame_equal(X_pca, X_reloaded)

    print("✅ FAZ 2 DIMENSIONALITY REDUCTION - READY FOR PRODUCTION")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
