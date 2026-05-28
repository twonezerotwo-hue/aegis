"""
AEGIS CBR Engine - Dimensionality Reduction
Reduce 25+ features to 12-15 principal components using PCA + Autoencoder
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import joblib
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DimensionalityResult:
    """Result of dimensionality reduction"""
    original_features: int
    reduced_features: int
    explained_variance: float
    pca_components: np.ndarray
    scaler: StandardScaler
    feature_names: List[str]
    reduction_ratio: float


class DimensionalityReducer:
    """
    Reduce high-dimensional fingerprint features to low-dimensional space.

    Goal: 25+ features → 12-15 principal components with >95% explained variance

    Pipeline:
    1. Standardize features
    2. Apply PCA (99% variance explained)
    3. Validate coverage
    """

    def __init__(self, target_components: int = 12, variance_threshold: float = 0.95):
        """
        Args:
            target_components: Target number of dimensions
            variance_threshold: Minimum variance to preserve
        """
        self.target_components = target_components
        self.variance_threshold = variance_threshold
        self.pca = None
        self.scaler = None
        self.feature_names = None

    def fit(self, fingerprints_df: pd.DataFrame) -> DimensionalityResult:
        """
        Fit PCA to fingerprint data.

        Args:
            fingerprints_df: DataFrame with fingerprints (rows: samples, cols: features)
                Example columns: current_price, rsi_14, macd_histogram, dxy_14d_corr, etc.

        Returns:
            DimensionalityResult with fit info
        """
        # Exclude non-numeric and meta columns
        exclude_cols = {'symbol', 'timestamp', 'market_type', 'regime_label',
                       'volatility_regime', 'macro_event_window', 'quality_score'}

        numeric_features = [col for col in fingerprints_df.columns
                           if col not in exclude_cols and fingerprints_df[col].dtype != 'object']

        if len(numeric_features) == 0:
            raise ValueError("No numeric features found in fingerprints")

        # Extract numeric data
        X = fingerprints_df[numeric_features].values

        # Handle missing values
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        logger.info(f"Fitting dimensionality reducer on {X.shape[0]} samples, {X.shape[1]} features")

        # Standardize
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Apply PCA - find n_components needed for 99% variance
        pca_full = PCA(n_components=min(X.shape[0], X.shape[1]))
        pca_full.fit(X_scaled)

        # Calculate cumulative variance
        cumsum_var = np.cumsum(pca_full.explained_variance_ratio_)

        # Find components needed for threshold
        n_components_threshold = np.argmax(cumsum_var >= self.variance_threshold) + 1

        # Use max(target, threshold) to ensure variance preservation
        n_components = max(self.target_components, n_components_threshold)

        logger.info(f"Using {n_components} components for {self.variance_threshold:.1%} variance")

        # Refit with determined components
        self.pca = PCA(n_components=n_components)
        X_transformed = self.pca.fit_transform(X_scaled)

        explained_var = np.sum(self.pca.explained_variance_ratio_)
        self.feature_names = numeric_features

        logger.info(f"Explained variance: {explained_var:.4f} ({n_components} components)")

        return DimensionalityResult(
            original_features=len(numeric_features),
            reduced_features=n_components,
            explained_variance=explained_var,
            pca_components=self.pca.components_,
            scaler=self.scaler,
            feature_names=numeric_features,
            reduction_ratio=n_components / len(numeric_features)
        )

    def transform(self, fingerprints_df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform fingerprints to reduced dimensions.

        Args:
            fingerprints_df: DataFrame with same features as training data

        Returns:
            DataFrame with principal components (PC0, PC1, ..., PCn)
        """
        if self.pca is None or self.scaler is None:
            raise ValueError("Reducer not fitted yet. Call fit() first.")

        # Extract numeric features (same order as training)
        X = fingerprints_df[self.feature_names].values
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Scale and transform
        X_scaled = self.scaler.transform(X)
        X_reduced = self.pca.transform(X_scaled)

        # Create output DataFrame
        n_components = self.pca.n_components_
        pc_cols = [f'PC{i}' for i in range(n_components)]

        df_reduced = pd.DataFrame(X_reduced, columns=pc_cols, index=fingerprints_df.index)

        # Preserve non-numeric columns (for reference)
        for col in fingerprints_df.columns:
            if col not in self.feature_names and col not in pc_cols:
                df_reduced[col] = fingerprints_df[col].values

        return df_reduced

    def get_feature_importance(self) -> pd.DataFrame:
        """
        Calculate feature importance for each principal component.

        Returns:
            DataFrame showing how much each original feature contributes to each PC
        """
        if self.pca is None:
            raise ValueError("Reducer not fitted yet")

        components = self.pca.components_
        loadings = pd.DataFrame(
            components.T,
            columns=[f'PC{i}' for i in range(len(components))],
            index=self.feature_names
        )

        # Add absolute contributions
        loadings['importance'] = (loadings ** 2).sum(axis=1)

        return loadings.sort_values('importance', ascending=False)

    def reduce_variance_report(self) -> Dict:
        """
        Generate report on variance reduction.

        Returns:
            Dict with variance statistics
        """
        if self.pca is None:
            raise ValueError("Reducer not fitted yet")

        var_ratio = self.pca.explained_variance_ratio_
        cumsum_var = np.cumsum(var_ratio)

        return {
            'total_components': len(var_ratio),
            'explained_variance_ratio': float(cumsum_var[-1]),
            'variance_by_component': {f'PC{i}': float(v) for i, v in enumerate(var_ratio)},
            'cumulative_variance': {f'PC{i}': float(v) for i, v in enumerate(cumsum_var)},
            'component_0_variance': float(var_ratio[0]),  # First PC variance
            'component_1_variance': float(var_ratio[1]) if len(var_ratio) > 1 else 0.0,
        }

    def save(self, filepath: str):
        """Save reducer to disk"""
        if self.pca is None:
            raise ValueError("Nothing to save - reducer not fitted")

        model_dict = {
            'pca': self.pca,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'target_components': self.target_components,
            'variance_threshold': self.variance_threshold,
        }

        joblib.dump(model_dict, filepath)
        logger.info(f"Reducer saved to {filepath}")

    @staticmethod
    def load(filepath: str) -> 'DimensionalityReducer':
        """Load reducer from disk"""
        model_dict = joblib.load(filepath)

        reducer = DimensionalityReducer(
            target_components=model_dict['target_components'],
            variance_threshold=model_dict['variance_threshold']
        )

        reducer.pca = model_dict['pca']
        reducer.scaler = model_dict['scaler']
        reducer.feature_names = model_dict['feature_names']

        logger.info(f"Reducer loaded from {filepath}")
        return reducer


class AutoencoderReducer:
    """
    Autoencoder-based dimensionality reduction (alternative to PCA).

    Useful for non-linear relationships between features.
    Architecture: input → 12 → 6 → 12 → output
    """

    def __init__(self, encoding_dim: int = 12, epochs: int = 50):
        """
        Args:
            encoding_dim: Bottleneck dimension
            epochs: Training epochs
        """
        self.encoding_dim = encoding_dim
        self.epochs = epochs
        self.encoder = None
        self.autoencoder = None
        self.scaler = None

        # Try to import TensorFlow (optional)
        try:
            import tensorflow as tf
            from tensorflow import keras
            self.tf = tf
            self.keras = keras
            self.has_tensorflow = True
        except ImportError:
            logger.warning("TensorFlow not available - autoencoder disabled")
            self.has_tensorflow = False

    def fit(self, fingerprints_df: pd.DataFrame) -> Optional[Dict]:
        """
        Fit autoencoder to data.

        Args:
            fingerprints_df: Input features

        Returns:
            Training history or None if TensorFlow unavailable
        """
        if not self.has_tensorflow:
            logger.warning("Skipping autoencoder (TensorFlow not available)")
            return None

        # Prepare data (same as PCA)
        exclude_cols = {'symbol', 'timestamp', 'market_type', 'regime_label',
                       'volatility_regime', 'macro_event_window', 'quality_score'}

        numeric_features = [col for col in fingerprints_df.columns
                           if col not in exclude_cols and fingerprints_df[col].dtype != 'object']

        X = fingerprints_df[numeric_features].values
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        input_dim = X_scaled.shape[1]

        # Build autoencoder
        input_layer = self.keras.layers.Input(shape=(input_dim,))
        encoded = self.keras.layers.Dense(self.encoding_dim, activation='relu')(input_layer)
        decoded = self.keras.layers.Dense(input_dim, activation='linear')(encoded)

        self.autoencoder = self.keras.models.Model(input_layer, decoded)
        self.autoencoder.compile(optimizer='adam', loss='mse')

        # Build encoder
        self.encoder = self.keras.models.Model(input_layer, encoded)

        # Train
        history = self.autoencoder.fit(
            X_scaled, X_scaled,
            epochs=self.epochs,
            batch_size=32,
            validation_split=0.1,
            verbose=0
        )

        logger.info(f"Autoencoder trained: final loss = {history.history['loss'][-1]:.6f}")

        return history.history

    def transform(self, fingerprints_df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Transform using encoder"""
        if self.encoder is None:
            return None

        # Same feature extraction as training
        exclude_cols = {'symbol', 'timestamp', 'market_type', 'regime_label',
                       'volatility_regime', 'macro_event_window', 'quality_score'}

        numeric_features = [col for col in fingerprints_df.columns
                           if col not in exclude_cols and fingerprints_df[col].dtype != 'object']

        X = fingerprints_df[numeric_features].values
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        X_scaled = self.scaler.transform(X)
        X_encoded = self.encoder.predict(X_scaled, verbose=0)

        df_encoded = pd.DataFrame(
            X_encoded,
            columns=[f'AE{i}' for i in range(self.encoding_dim)],
            index=fingerprints_df.index
        )

        # Preserve metadata
        for col in fingerprints_df.columns:
            if col not in numeric_features:
                df_encoded[col] = fingerprints_df[col].values

        return df_encoded


class HybridReducer:
    """
    Combine PCA (linear) + Autoencoder (nonlinear) for best results.

    Use both and ensemble their outputs.
    """

    def __init__(self, pca_components: int = 8, ae_components: int = 8):
        """
        Args:
            pca_components: Principal components from PCA
            ae_components: Autoencoder encoding dimension
        """
        self.pca_reducer = DimensionalityReducer(target_components=pca_components)
        self.ae_reducer = AutoencoderReducer(encoding_dim=ae_components)

    def fit(self, fingerprints_df: pd.DataFrame):
        """Fit both PCA and Autoencoder"""
        self.pca_reducer.fit(fingerprints_df)
        self.ae_reducer.fit(fingerprints_df)

    def transform(self, fingerprints_df: pd.DataFrame) -> pd.DataFrame:
        """Transform with both methods and concatenate"""
        pca_reduced = self.pca_reducer.transform(fingerprints_df)
        ae_reduced = self.ae_reducer.transform(fingerprints_df)

        if ae_reduced is None:
            return pca_reduced

        # Combine both
        combined = pd.concat([pca_reduced, ae_reduced], axis=1)

        # Remove duplicate non-numeric columns
        pca_cols = [c for c in pca_reduced.columns if c.startswith('PC')]
        ae_cols = [c for c in ae_reduced.columns if c.startswith('AE')]
        meta_cols = [c for c in ae_reduced.columns if not c.startswith('AE')]

        combined = pd.concat([
            pca_reduced[pca_cols],
            ae_reduced[ae_cols],
            ae_reduced[meta_cols]
        ], axis=1)

        return combined
