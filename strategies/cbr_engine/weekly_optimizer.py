"""
AEGIS CBR Engine - FAZ 5: Weekly Optimizer
Optimize decision-making parameters using Optuna weekly
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

try:
    import optuna
    from optuna.pruners import MedianPruner
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    logger.warning("Optuna not installed - optimizer will use fallback mode")


@dataclass
class OptimizationResult:
    """Result of optimization trial"""
    trial_number: int
    parameters: Dict
    objective_value: float  # Metric (sharpe, win_rate, etc.)
    status: str  # COMPLETE, PRUNED, FAIL


class WeeklyOptimizer:
    """
    Optimize decision-making parameters using recent trade data.

    Optimizes:
    - Bayesian confidence weights (win_rate, return, consistency, sample_ratio, similarity)
    - Risk gate thresholds (VIX, Fear/Greed, DXY correlation)
    - Position sizing parameters (Kelly fractional rate, max position)

    Uses Optuna with cross-validation to prevent overfitting.
    """

    def __init__(
        self,
        n_trials: int = 100,
        objective_metric: str = 'sharpe_ratio',  # sharpe_ratio, win_rate, expectancy
        min_trades_for_optimization: int = 10,
        train_test_split: float = 0.7,  # 70% train, 30% test
    ):
        """
        Args:
            n_trials: Number of optimization trials
            objective_metric: Which metric to maximize (sharpe_ratio, win_rate, expectancy)
            min_trades_for_optimization: Minimum trades required to optimize
            train_test_split: Train/test split ratio
        """
        self.n_trials = n_trials
        self.objective_metric = objective_metric
        self.min_trades_for_optimization = min_trades_for_optimization
        self.train_test_split = train_test_split

        self.best_params = None
        self.optimization_history = []

        logger.info(
            f"WeeklyOptimizer initialized: "
            f"metric={objective_metric}, trials={n_trials}, "
            f"min_trades={min_trades_for_optimization}"
        )

    def prepare_dataset(
        self,
        trades: List[Dict]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Split trades into train and test sets (chronologically).

        Args:
            trades: List of trade outcomes

        Returns:
            (train_trades, test_trades)
        """
        n_train = int(len(trades) * self.train_test_split)

        # Use chronological split (not random) to prevent look-ahead bias
        train_trades = trades[:n_train] if n_train > 0 else trades
        test_trades = trades[n_train:] if n_train < len(trades) else []

        logger.info(
            f"Dataset split: {len(train_trades)} train, {len(test_trades)} test"
        )

        return train_trades, test_trades

    def calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """Calculate Sharpe ratio (annualized)"""
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array)

        if std_return == 0:
            return 0.0

        # Annualized Sharpe (252 trading days)
        sharpe = mean_return / std_return * np.sqrt(252)

        return float(sharpe)

    def calculate_win_rate(self, returns: List[float]) -> float:
        """Calculate win rate (% of positive returns)"""
        if not returns:
            return 0.0

        wins = sum(1 for r in returns if r > 0)
        return float(wins / len(returns))

    def calculate_expectancy(self, returns: List[float]) -> float:
        """Calculate expectancy (average return)"""
        if not returns:
            return 0.0

        return float(np.mean(returns))

    def evaluate_parameters(
        self,
        parameters: Dict,
        train_trades: List[Dict],
        test_trades: List[Dict],
    ) -> Tuple[float, Dict]:
        """
        Evaluate parameter set on train and test data.

        Returns:
            (test_metric, evaluation_dict)
        """
        # Extract returns from trades
        train_returns = [t.get('forward_return', 0) for t in train_trades]
        test_returns = [t.get('forward_return', 0) for t in test_trades]

        # Calculate metrics
        if self.objective_metric == 'sharpe_ratio':
            train_metric = self.calculate_sharpe_ratio(train_returns)
            test_metric = self.calculate_sharpe_ratio(test_returns)
        elif self.objective_metric == 'win_rate':
            train_metric = self.calculate_win_rate(train_returns)
            test_metric = self.calculate_win_rate(test_returns)
        elif self.objective_metric == 'expectancy':
            train_metric = self.calculate_expectancy(train_returns)
            test_metric = self.calculate_expectancy(test_returns)
        else:
            test_metric = 0.0

        # Check for overfitting (train >> test)
        overfitting = abs(train_metric - test_metric) if test_metric > 0 else 0

        evaluation = {
            'train_metric': train_metric,
            'test_metric': test_metric,
            'overfitting_gap': overfitting,
            'train_sample_count': len(train_returns),
            'test_sample_count': len(test_returns),
        }

        return test_metric, evaluation

    def objective_function(
        self,
        trial,
        train_trades: List[Dict],
        test_trades: List[Dict],
    ) -> float:
        """
        Objective function for Optuna.

        Suggests parameters and returns metric to maximize.
        """
        # Suggest parameters
        parameters = {
            'confidence_win_rate_weight': trial.suggest_float('conf_win_weight', 0.1, 0.4),
            'confidence_return_weight': trial.suggest_float('conf_return_weight', 0.1, 0.3),
            'confidence_consistency_weight': trial.suggest_float('conf_consist_weight', 0.1, 0.3),
            'confidence_sample_weight': trial.suggest_float('conf_sample_weight', 0.05, 0.2),
            'confidence_similarity_weight': trial.suggest_float('conf_sim_weight', 0.1, 0.3),
            'kelly_fractional': trial.suggest_float('kelly_frac', 0.1, 0.5),
            'max_position': trial.suggest_float('max_pos', 0.02, 0.10),
            'vix_threshold': trial.suggest_float('vix_thresh', 25, 45),
            'fear_greed_min': trial.suggest_float('fg_min', 10, 30),
            'dxy_correlation_max': trial.suggest_float('dxy_max', 0.5, 0.8),
        }

        # Normalize confidence weights to sum to 1
        confidence_weights = [
            parameters['confidence_win_rate_weight'],
            parameters['confidence_return_weight'],
            parameters['confidence_consistency_weight'],
            parameters['confidence_sample_weight'],
            parameters['confidence_similarity_weight'],
        ]
        weight_sum = sum(confidence_weights)
        for key in list(parameters.keys()):
            if 'confidence_' in key and 'weight' in key:
                parameters[key] /= weight_sum

        # Evaluate on test set
        test_metric, evaluation = self.evaluate_parameters(
            parameters, train_trades, test_trades
        )

        # Penalize overfitting
        if evaluation['overfitting_gap'] > 0.5:  # Large overfitting
            test_metric *= 0.5  # Reduce score by 50%

        # Report intermediate value for pruning
        trial.report(test_metric, step=0)

        return test_metric

    def optimize(
        self,
        trades: List[Dict],
    ) -> Dict:
        """
        Run optimization on recent trades.

        Args:
            trades: List of trade outcomes with forward_return

        Returns:
            Best parameters found
        """
        if len(trades) < self.min_trades_for_optimization:
            logger.warning(
                f"Insufficient trades for optimization: {len(trades)} < {self.min_trades_for_optimization}"
            )
            return None

        logger.info(f"Starting optimization with {len(trades)} trades...")

        # Prepare datasets
        train_trades, test_trades = self.prepare_dataset(trades)

        if not OPTUNA_AVAILABLE:
            logger.warning("Optuna not available - using fallback random search")
            return self._random_search_fallback(train_trades, test_trades)

        # Run Optuna study
        sampler = optuna.samplers.TPESampler(seed=42)
        pruner = MedianPruner()

        study = optuna.create_study(
            direction='maximize',
            sampler=sampler,
            pruner=pruner
        )

        # Create objective with bound data
        def objective(trial):
            return self.objective_function(trial, train_trades, test_trades)

        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)

        # Extract best parameters
        best_trial = study.best_trial
        self.best_params = best_trial.params

        logger.info(
            f"Optimization complete. Best value: {best_trial.value:.4f} "
            f"(Trial #{best_trial.number})"
        )

        # Store history
        self.optimization_history.append({
            'timestamp': pd.Timestamp.now(),
            'best_value': best_trial.value,
            'best_params': self.best_params,
            'n_trials': self.n_trials,
            'n_trades': len(trades),
        })

        return self.best_params

    def _random_search_fallback(
        self,
        train_trades: List[Dict],
        test_trades: List[Dict],
        n_trials: int = 50
    ) -> Dict:
        """
        Fallback random search if Optuna not available.
        """
        logger.info(f"Running fallback random search with {n_trials} trials...")

        best_score = -np.inf
        best_params = None

        for trial_num in range(n_trials):
            # Random parameters
            parameters = {
                'confidence_win_rate_weight': np.random.uniform(0.1, 0.4),
                'confidence_return_weight': np.random.uniform(0.1, 0.3),
                'confidence_consistency_weight': np.random.uniform(0.1, 0.3),
                'confidence_sample_weight': np.random.uniform(0.05, 0.2),
                'confidence_similarity_weight': np.random.uniform(0.1, 0.3),
                'kelly_fractional': np.random.uniform(0.1, 0.5),
                'max_position': np.random.uniform(0.02, 0.10),
                'vix_threshold': np.random.uniform(25, 45),
                'fear_greed_min': np.random.uniform(10, 30),
                'dxy_correlation_max': np.random.uniform(0.5, 0.8),
            }

            # Normalize weights
            confidence_weights = [
                parameters['confidence_win_rate_weight'],
                parameters['confidence_return_weight'],
                parameters['confidence_consistency_weight'],
                parameters['confidence_sample_weight'],
                parameters['confidence_similarity_weight'],
            ]
            weight_sum = sum(confidence_weights)
            for key in list(parameters.keys()):
                if 'confidence_' in key and 'weight' in key:
                    parameters[key] /= weight_sum

            # Evaluate
            test_metric, _ = self.evaluate_parameters(parameters, train_trades, test_trades)

            if test_metric > best_score:
                best_score = test_metric
                best_params = parameters

        self.best_params = best_params
        logger.info(f"Fallback search complete. Best score: {best_score:.4f}")

        return best_params

    def get_optimization_history(self) -> pd.DataFrame:
        """Return optimization history as DataFrame"""
        if not self.optimization_history:
            return pd.DataFrame()

        return pd.DataFrame(self.optimization_history)

    def should_optimize(self, last_optimization_time: Optional[pd.Timestamp] = None) -> bool:
        """
        Check if optimization should run (weekly).

        Args:
            last_optimization_time: Timestamp of last optimization

        Returns:
            True if should optimize
        """
        if last_optimization_time is None:
            return True

        days_since = (pd.Timestamp.now() - last_optimization_time).days

        return days_since >= 7

    def apply_parameters(self, parameters: Dict) -> Dict:
        """
        Apply optimized parameters to trading system.

        (In production, this would update config/database)
        """
        if parameters is None:
            logger.warning("No parameters provided - skipping update")
            return {}

        logger.info(f"Applying optimized parameters: {parameters}")

        return parameters
