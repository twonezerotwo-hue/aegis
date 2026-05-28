"""
AEGIS CBR Engine - FAZ 5: SHAP Feature Importance Dashboard
Explain which features drive trading decisions using SHAP
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    logger.warning("SHAP not installed - dashboard will use fallback mode")


@dataclass
class FeatureImportance:
    """Feature importance record"""
    feature_name: str
    importance_score: float  # Mean absolute SHAP value
    impact_on_decision: str  # HIGH, MEDIUM, LOW
    direction: str  # POSITIVE (increases decision) or NEGATIVE (decreases)
    trade_examples: List[Dict]  # Example trades where this feature was important


class SHAPDashboard:
    """
    SHAP-based feature importance and decision explanation.

    Answers:
    - Which features most influence trading decisions?
    - For a specific trade, what was the main driver?
    - Are we over-reliant on certain features?
    """

    def __init__(self):
        """Initialize dashboard"""
        self.feature_importances = {}
        self.trade_explanations = {}  # trade_id -> explanations
        logger.info(f"SHAPDashboard initialized (SHAP available: {SHAP_AVAILABLE})")

    def calculate_feature_importance(
        self,
        feature_names: List[str],
        features_data: np.ndarray,  # Shape: (n_samples, n_features)
        decisions: np.ndarray,  # Shape: (n_samples,) - confidence/position scores
    ) -> Dict[str, FeatureImportance]:
        """
        Calculate SHAP-based feature importance.

        Args:
            feature_names: List of feature names
            features_data: Feature matrix (samples x features)
            decisions: Trading decision scores (to explain)

        Returns:
            Dict mapping feature names to FeatureImportance
        """
        if not SHAP_AVAILABLE:
            logger.warning("SHAP not available - using fallback importance calculation")
            return self._calculate_fallback_importance(feature_names, features_data, decisions)

        try:
            # Use KernelExplainer for model-agnostic explanation
            background = shap.sample(features_data, min(len(features_data), 100))

            # Create a simple model: correlation with decisions
            def predict_fn(X):
                """Predict using correlation with decisions"""
                correlations = []
                for i in range(len(X)):
                    corr = np.corrcoef(X[i], decisions)[0, 1]
                    correlations.append(corr if not np.isnan(corr) else 0.0)
                return np.array(correlations)

            explainer = shap.KernelExplainer(predict_fn, background)
            shap_values = explainer.shap_values(features_data)

            # Calculate mean absolute SHAP values
            mean_abs_shap = np.mean(np.abs(shap_values), axis=0)

            # Create importance records
            importances = {}
            for idx, feature_name in enumerate(feature_names):
                abs_impact = mean_abs_shap[idx]
                avg_direction = np.mean(shap_values[:, idx])

                importance = FeatureImportance(
                    feature_name=feature_name,
                    importance_score=float(abs_impact),
                    impact_on_decision='HIGH' if abs_impact > 0.1 else 'MEDIUM' if abs_impact > 0.05 else 'LOW',
                    direction='POSITIVE' if avg_direction > 0 else 'NEGATIVE',
                    trade_examples=[]
                )

                importances[feature_name] = importance

            self.feature_importances = importances
            logger.info(f"Calculated importance for {len(importances)} features")

            return importances

        except Exception as e:
            logger.error(f"Error in SHAP calculation: {e}")
            return self._calculate_fallback_importance(feature_names, features_data, decisions)

    def _calculate_fallback_importance(
        self,
        feature_names: List[str],
        features_data: np.ndarray,
        decisions: np.ndarray,
    ) -> Dict[str, FeatureImportance]:
        """
        Fallback: calculate importance using correlation.
        """
        logger.info("Using fallback importance calculation (correlation-based)")

        importances = {}

        for idx, feature_name in enumerate(feature_names):
            feature_values = features_data[:, idx]

            # Calculate correlation with decisions
            valid_idx = ~(np.isnan(feature_values) | np.isnan(decisions))
            if np.sum(valid_idx) > 2:
                corr = np.corrcoef(feature_values[valid_idx], decisions[valid_idx])[0, 1]
                abs_corr = abs(corr) if not np.isnan(corr) else 0.0
            else:
                abs_corr = 0.0

            importance = FeatureImportance(
                feature_name=feature_name,
                importance_score=float(abs_corr),
                impact_on_decision='HIGH' if abs_corr > 0.3 else 'MEDIUM' if abs_corr > 0.15 else 'LOW',
                direction='POSITIVE' if (not np.isnan(corr) and corr > 0) else 'NEGATIVE',
                trade_examples=[]
            )

            importances[feature_name] = importance

        self.feature_importances = importances
        return importances

    def explain_trade_decision(
        self,
        trade_id: str,
        features: np.ndarray,  # Single sample
        feature_names: List[str],
        decision_score: float,
    ) -> Dict:
        """
        Explain why a specific trade was made.

        Args:
            trade_id: Trade identifier
            features: Feature vector for this trade
            feature_names: Feature names
            decision_score: Final decision confidence/score

        Returns:
            Explanation dict with top drivers
        """
        explanation = {
            'trade_id': trade_id,
            'decision_score': decision_score,
            'feature_values': {},
            'top_drivers': [],
            'explanation': ''
        }

        # Store feature values
        for fname, fvalue in zip(feature_names, features):
            explanation['feature_values'][fname] = float(fvalue)

        # Identify top drivers (features far from mean)
        feature_means = [0] * len(features)  # Placeholder
        feature_stds = [1] * len(features)  # Placeholder

        drivers = []
        for idx, (fname, fvalue) in enumerate(zip(feature_names, features)):
            if fname in self.feature_importances:
                importance = self.feature_importances[fname]
                z_score = abs((fvalue - feature_means[idx]) / (feature_stds[idx] + 1e-8))

                impact = importance.importance_score * z_score

                drivers.append({
                    'feature': fname,
                    'value': float(fvalue),
                    'importance': float(importance.importance_score),
                    'z_score': float(z_score),
                    'impact': float(impact),
                    'direction': importance.direction,
                })

        # Sort by impact and take top 5
        drivers.sort(key=lambda x: x['impact'], reverse=True)
        explanation['top_drivers'] = drivers[:5]

        # Generate text explanation
        if drivers:
            top_driver = drivers[0]['feature']
            explanation['explanation'] = (
                f"Decision mainly driven by {top_driver} ({drivers[0]['impact']:.3f} impact). "
                f"Top 3 factors: {drivers[0]['feature']}, {drivers[1]['feature']}, {drivers[2]['feature']}"
            )

        self.trade_explanations[trade_id] = explanation
        logger.info(f"Trade {trade_id} explained. Top driver: {explanation['top_drivers'][0]['feature'] if explanation['top_drivers'] else 'N/A'}")

        return explanation

    def get_feature_importance_summary(self, top_n: int = 10) -> pd.DataFrame:
        """
        Get top N most important features.

        Returns:
            DataFrame sorted by importance
        """
        if not self.feature_importances:
            return pd.DataFrame()

        data = []
        for fname, importance in self.feature_importances.items():
            data.append({
                'Feature': fname,
                'Importance Score': importance.importance_score,
                'Impact Level': importance.impact_on_decision,
                'Direction': importance.direction,
            })

        df = pd.DataFrame(data)
        df = df.sort_values('Importance Score', ascending=False)

        return df.head(top_n)

    def detect_feature_drift(
        self,
        historical_importance: Dict[str, float],
        threshold: float = 0.3
    ) -> List[Tuple[str, float, float]]:
        """
        Detect if feature importance has shifted significantly.

        Args:
            historical_importance: Previous feature importance scores
            threshold: Change threshold to flag

        Returns:
            List of (feature, old_importance, new_importance) for drifted features
        """
        drifted = []

        for fname, current in self.feature_importances.items():
            if fname in historical_importance:
                old_importance = historical_importance[fname]
                change = abs(current.importance_score - old_importance) / (old_importance + 1e-8)

                if change > threshold:
                    drifted.append((fname, old_importance, current.importance_score))

        return sorted(drifted, key=lambda x: x[2] - x[1], reverse=True)

    def get_trade_explanation(self, trade_id: str) -> Optional[Dict]:
        """Get explanation for a specific trade"""
        return self.trade_explanations.get(trade_id)

    def get_all_explanations(self) -> List[Dict]:
        """Get all trade explanations"""
        return list(self.trade_explanations.values())

    def summary_report(self) -> str:
        """Generate text summary report"""
        if not self.feature_importances:
            return "No feature importances calculated yet."

        # Get sorted importances
        sorted_features = sorted(
            self.feature_importances.items(),
            key=lambda x: x[1].importance_score,
            reverse=True
        )

        report = "=== SHAP Feature Importance Summary ===\n\n"

        # Top features
        report += "TOP 5 MOST IMPORTANT FEATURES:\n"
        for idx, (fname, importance) in enumerate(sorted_features[:5], 1):
            report += f"{idx}. {fname}: {importance.importance_score:.4f} ({importance.impact_on_decision})\n"
            report += f"   Direction: {importance.direction}\n\n"

        # Statistics
        report += "\nFEATURE IMPORTANCE STATISTICS:\n"
        scores = [i.importance_score for i in self.feature_importances.values()]
        report += f"Mean importance: {np.mean(scores):.4f}\n"
        report += f"Std importance: {np.std(scores):.4f}\n"
        report += f"Max importance: {np.max(scores):.4f}\n"
        report += f"Min importance: {np.min(scores):.4f}\n"

        # Impact distribution
        high_impact = sum(1 for i in self.feature_importances.values() if i.impact_on_decision == 'HIGH')
        med_impact = sum(1 for i in self.feature_importances.values() if i.impact_on_decision == 'MEDIUM')
        low_impact = sum(1 for i in self.feature_importances.values() if i.impact_on_decision == 'LOW')

        report += "\nIMPACT DISTRIBUTION:\n"
        report += f"HIGH impact: {high_impact} features\n"
        report += f"MEDIUM impact: {med_impact} features\n"
        report += f"LOW impact: {low_impact} features\n"

        return report

    def export_to_dataframe(self) -> pd.DataFrame:
        """Export all importances to DataFrame"""
        return self.get_feature_importance_summary(top_n=len(self.feature_importances))
