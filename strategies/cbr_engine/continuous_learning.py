"""
AEGIS CBR Engine - Continuous Learning System
Auto-labels trades, optimizes weights weekly using Optuna
"""

import numpy as np
from typing import Dict, List
from datetime import datetime
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Recorded trade outcome"""
    trade_id: str
    timestamp: datetime
    action: str  # LONG/SHORT
    entry_price: float
    exit_price: float
    position_size: float
    return_pct: float
    duration_hours: float
    fingerprint_id: int


class AutoLabeler:
    """Automatically labels trade outcomes for case base"""

    @staticmethod
    def label_trade(
        entry_time: datetime,
        exit_time: datetime,
        entry_price: float,
        exit_price: float,
        position_size: float,
        action: str
    ) -> Dict:
        """
        Generate label for closed trade.

        Args:
            entry_time: Entry timestamp
            exit_time: Exit timestamp
            entry_price: Entry price
            exit_price: Exit price
            position_size: Position size used
            action: LONG or SHORT

        Returns:
            Label dict with return, duration, etc.
        """
        if action == 'LONG':
            return_pct = (exit_price - entry_price) / entry_price
        else:  # SHORT
            return_pct = (entry_price - exit_price) / entry_price

        duration = (exit_time - entry_time).total_seconds() / 3600  # hours

        return {
            'return_pct': float(return_pct),
            'return_abs': float(exit_price - entry_price),
            'duration_hours': float(duration),
            'profitable': return_pct > 0,
            'pnl': float(return_pct * position_size * 100),  # PnL in bps
            'labeled_at': datetime.now().isoformat(),
        }

    @staticmethod
    def categorize_outcome(return_pct: float) -> str:
        """Categorize trade outcome"""
        if return_pct > 0.05:
            return 'GREAT_WIN'
        elif return_pct > 0.01:
            return 'WIN'
        elif return_pct > -0.01:
            return 'BREAKEVEN'
        elif return_pct > -0.05:
            return 'SMALL_LOSS'
        else:
            return 'BIG_LOSS'


class WeeklyOptimizer:
    """
    Weekly weight optimization using Optuna.

    Optimizes:
    - Feature weights (price_weight, technical_weight, macro_weight, onchain_weight, temporal_weight)
    - Similarity thresholds
    - Position size multipliers

    Objective: Maximize Sharpe ratio on past week's trades
    """

    def __init__(self, objective_metric: str = 'sharpe_ratio'):
        """
        Args:
            objective_metric: What to optimize (sharpe_ratio, win_rate, expectancy, etc.)
        """
        self.objective_metric = objective_metric
        self.best_params = None
        self.optimization_history = []

        try:
            import optuna
            self.optuna = optuna
            self.has_optuna = True
        except ImportError:
            logger.warning("Optuna not available - skipping weekly optimization")
            self.has_optuna = False

    def run_weekly_optimization(
        self,
        past_trades: List[TradeResult],
        n_trials: int = 100
    ) -> Dict:
        """
        Optimize weights for past week's performance.

        Args:
            past_trades: List of TradeResult from past 7 days
            n_trials: Number of Optuna trials

        Returns:
            Dict with optimal parameters and metrics
        """
        if not self.has_optuna or len(past_trades) < 5:
            logger.warning(f"Skipping optimization: {len(past_trades)} trades")
            return {'status': 'skipped', 'reason': 'insufficient_data'}

        returns = np.array([t.return_pct for t in past_trades])
        win_rate = np.mean(returns > 0)

        # Calculate current metrics before optimization
        current_sharpe = self._calculate_sharpe(returns)
        current_win_rate = win_rate

        logger.info(f"Optimizing on {len(past_trades)} trades")
        logger.info(f"Current Sharpe: {current_sharpe:.3f}, Win rate: {current_win_rate:.1%}")

        # Define objective function
        def objective(trial):
            # Suggest parameters
            price_weight = trial.suggest_float('price_weight', 0.1, 0.5)
            technical_weight = trial.suggest_float('technical_weight', 0.1, 0.5)
            macro_weight = trial.suggest_float('macro_weight', 0.0, 0.3)
            onchain_weight = trial.suggest_float('onchain_weight', 0.0, 0.3)
            temporal_weight = trial.suggest_float('temporal_weight', 0.0, 0.2)
            similarity_threshold = trial.suggest_float('similarity_threshold', 0.5, 0.8)
            position_multiplier = trial.suggest_float('position_multiplier', 0.5, 2.0)

            # Normalize weights
            total_weight = price_weight + technical_weight + macro_weight + onchain_weight + temporal_weight
            weights = {
                'price': price_weight / total_weight,
                'technical': technical_weight / total_weight,
                'macro': macro_weight / total_weight,
                'onchain': onchain_weight / total_weight,
                'temporal': temporal_weight / total_weight,
                'similarity': similarity_threshold,
                'position_mult': position_multiplier,
            }

            # Simulate trades with these weights (placeholder)
            simulated_returns = returns * position_multiplier * (1 + 0.1 * similarity_threshold)

            # Calculate metric
            if self.objective_metric == 'sharpe_ratio':
                metric = self._calculate_sharpe(simulated_returns)
            elif self.objective_metric == 'win_rate':
                metric = np.mean(simulated_returns > 0)
            elif self.objective_metric == 'expectancy':
                metric = np.mean(simulated_returns) / (np.std(simulated_returns) + 1e-8)
            else:
                metric = np.mean(simulated_returns)

            return metric

        # Create study and optimize
        study = self.optuna.create_study(direction='maximize', load_if_exists=False)
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best_trial = study.best_trial
        best_params = best_trial.params

        logger.info(f"Best {self.objective_metric}: {best_trial.value:.4f}")
        logger.info(f"Best params: {best_params}")

        # Store result
        result = {
            'optimization_timestamp': datetime.now().isoformat(),
            'metric': self.objective_metric,
            'metric_value': float(best_trial.value),
            'n_trials': n_trials,
            'trades_evaluated': len(past_trades),
            'parameters': best_params,
            'improvement': float(best_trial.value - current_sharpe),
        }

        self.optimization_history.append(result)
        self.best_params = best_params

        return result

    def _calculate_sharpe(self, returns: np.ndarray, rf_rate: float = 0.02) -> float:
        """Calculate annualized Sharpe ratio"""
        if len(returns) < 2:
            return 0.0

        excess_return = np.mean(returns) - (rf_rate / 252)
        volatility = np.std(returns)

        if volatility == 0:
            return 0.0

        sharpe = np.sqrt(252) * excess_return / volatility
        return float(sharpe)


class ShapDashboard:
    """
    SHAP-based feature importance for decision explainability.

    Shows which features/factors influenced each trading decision.
    """

    def __init__(self):
        """Initialize SHAP integration"""
        try:
            import shap
            self.shap = shap
            self.has_shap = True
        except ImportError:
            logger.warning("SHAP not available")
            self.has_shap = False

    def explain_decision(
        self,
        fingerprint: Dict,
        similar_cases_stats: Dict,
        decision_score: float
    ) -> Dict:
        """
        Explain trading decision using SHAP-like feature importance.

        Args:
            fingerprint: Current market fingerprint
            similar_cases_stats: Statistics from similar cases
            decision_score: Final decision confidence

        Returns:
            Dict with feature importance breakdown
        """
        explanation = {
            'decision_score': decision_score,
            'feature_importance': {},
            'top_factors': [],
        }

        # Calculate contribution of each group
        fingerprint_factors = {
            'price_structure': 0.0,
            'technical_indicators': 0.0,
            'macro_factors': 0.0,
            'onchain_data': 0.0,
            'temporal_factors': 0.0,
        }

        # Price structure contribution
        if 'distance_from_ath' in fingerprint:
            price_contrib = abs(fingerprint['distance_from_ath']) * 0.4
            fingerprint_factors['price_structure'] += price_contrib

        # Technical contribution
        if 'rsi_14' in fingerprint:
            rsi_contrib = abs(fingerprint['rsi_14'] - 50) / 50 * 0.3
            fingerprint_factors['technical_indicators'] += rsi_contrib

        # Macro contribution
        if 'dxy_14d_corr' in fingerprint:
            macro_contrib = abs(fingerprint['dxy_14d_corr']) * 0.2
            fingerprint_factors['macro_factors'] += macro_contrib

        # On-chain contribution
        if 'exchange_netflow_7d' in fingerprint:
            onchain_contrib = abs(fingerprint['exchange_netflow_7d']) / 1000 * 0.1
            fingerprint_factors['onchain_data'] += onchain_contrib

        # Case similarity contribution
        case_contrib = similar_cases_stats.get('mean_similarity', 0.5) * 0.5
        fingerprint_factors['similar_cases'] = case_contrib

        # Normalize
        total = sum(fingerprint_factors.values())
        if total > 0:
            fingerprint_factors = {k: v / total for k, v in fingerprint_factors.items()}

        explanation['feature_importance'] = fingerprint_factors

        # Top factors
        top_factors = sorted(
            fingerprint_factors.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        explanation['top_factors'] = [{'factor': k, 'weight': v} for k, v in top_factors]

        return explanation

    def generate_report(self, trades: List[TradeResult], explanations: List[Dict]) -> Dict:
        """
        Generate comprehensive SHAP-based performance report.

        Returns:
            Dict with insights on what drives profitability
        """
        if not trades or not explanations:
            return {'status': 'no_data'}

        returns = np.array([t.return_pct for t in trades])
        winners = returns > 0

        winning_explanations = [exp for i, exp in enumerate(explanations) if i < len(winners) and winners[i]]
        losing_explanations = [exp for i, exp in enumerate(explanations) if i < len(winners) and not winners[i]]

        # Average factor importance for winners vs losers
        report = {
            'total_trades': len(trades),
            'winner_count': int(np.sum(winners)),
            'avg_return': float(np.mean(returns)),
            'sharpe_ratio': float(np.std(returns) / (np.mean(returns) + 1e-8) if np.mean(returns) > 0 else 0),
        }

        if winning_explanations:
            winner_factors = {}
            for exp in winning_explanations:
                for factor, importance in exp.get('feature_importance', {}).items():
                    winner_factors[factor] = winner_factors.get(factor, 0) + importance

            report['winning_factors'] = {k: v / len(winning_explanations) for k, v in winner_factors.items()}

        if losing_explanations:
            loser_factors = {}
            for exp in losing_explanations:
                for factor, importance in exp.get('feature_importance', {}).items():
                    loser_factors[factor] = loser_factors.get(factor, 0) + importance

            report['losing_factors'] = {k: v / len(losing_explanations) for k, v in loser_factors.items()}

        return report
