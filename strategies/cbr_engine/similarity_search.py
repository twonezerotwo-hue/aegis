"""
AEGIS CBR Engine - FAZ 3: Similarity Search Engine
Regime-aware filtering + Cosine + DTW hybrid similarity
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class SimilarityResult:
    """Single similarity match result"""
    id: int
    similarity_score: float  # 0-1, 1=perfect match
    regime_label: str
    market_type: str
    timestamp: datetime
    price: float
    forward_return_24h: Optional[float]
    distance_type: str  # "cosine", "dtw", "hybrid"
    rank: int


class DynamicTimeWarping:
    """
    DTW (Dynamic Time Warping) for sequence similarity.

    Useful for comparing multivariate time series where timing might vary.
    """

    @staticmethod
    def dtw_distance(x: np.ndarray, y: np.ndarray) -> float:
        """
        Calculate DTW distance between two sequences.

        Args:
            x: Sequence 1 (1D array)
            y: Sequence 2 (1D array)

        Returns:
            DTW distance (lower = more similar)
        """
        n, m = len(x), len(y)

        # DP table
        dtw_matrix = np.full((n + 1, m + 1), np.inf)
        dtw_matrix[0, 0] = 0

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = abs(x[i - 1] - y[j - 1])
                dtw_matrix[i, j] = cost + min(
                    dtw_matrix[i - 1, j],  # insertion
                    dtw_matrix[i, j - 1],  # deletion
                    dtw_matrix[i - 1, j - 1]  # match
                )

        return dtw_matrix[n, m]

    @staticmethod
    def dtw_similarity(x: np.ndarray, y: np.ndarray) -> float:
        """
        Convert DTW distance to similarity score (0-1).

        Args:
            x: Sequence 1
            y: Sequence 2

        Returns:
            Similarity score (1 = identical, 0 = very different)
        """
        distance = DynamicTimeWarping.dtw_distance(x, y)

        # Normalize: similarity = 1 / (1 + distance)
        similarity = 1.0 / (1.0 + distance)

        return float(similarity)


class SimilaritySearchEngine:
    """
    Main similarity search engine with multiple distance metrics.

    Features:
    - Cosine similarity (fast, standard)
    - DTW similarity (handles temporal variation)
    - Hybrid: weighted combination
    - Regime-aware filtering
    """

    def __init__(
        self,
        cosine_weight: float = 0.7,
        dtw_weight: float = 0.3,
        normalize_scores: bool = True
    ):
        """
        Args:
            cosine_weight: Weight for cosine similarity (0-1)
            dtw_weight: Weight for DTW similarity
            normalize_scores: Rescale scores to 0-1 range
        """
        self.cosine_weight = cosine_weight
        self.dtw_weight = dtw_weight
        self.normalize_scores = normalize_scores

        # Validate weights
        total_weight = cosine_weight + dtw_weight
        self.cosine_weight /= total_weight
        self.dtw_weight /= total_weight

        logger.info(
            f"SimilaritySearchEngine initialized: "
            f"cosine_weight={self.cosine_weight:.2f}, "
            f"dtw_weight={self.dtw_weight:.2f}"
        )

    def cosine_similarity(
        self,
        query_embedding: np.ndarray,
        case_embeddings: np.ndarray
    ) -> np.ndarray:
        """
        Calculate cosine similarity between query and all cases.

        Args:
            query_embedding: Query vector (1D)
            case_embeddings: Case vectors (2D, shape: n_cases x dim)

        Returns:
            Similarity scores (0-1 range)
        """
        # Normalize vectors
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        case_norms = case_embeddings / (np.linalg.norm(case_embeddings, axis=1, keepdims=True) + 1e-8)

        # Cosine similarity via dot product
        similarities = np.dot(case_norms, query_norm)

        # Map from [-1, 1] to [0, 1]
        similarities = (similarities + 1) / 2

        return np.clip(similarities, 0, 1)

    def dtw_similarity_batch(
        self,
        query_embedding: np.ndarray,
        case_embeddings: np.ndarray,
        sample_rate: float = 1.0
    ) -> np.ndarray:
        """
        Calculate DTW similarity (with sampling for speed).

        Args:
            query_embedding: Query vector
            case_embeddings: Case vectors
            sample_rate: Fraction of cases to calculate DTW for (1.0 = all)

        Returns:
            DTW similarity scores
        """
        n_cases = case_embeddings.shape[0]
        dtw_scores = np.zeros(n_cases)

        # Sample cases if needed (DTW is slow)
        if sample_rate < 1.0:
            sampled_indices = np.random.choice(n_cases, int(n_cases * sample_rate), replace=False)
        else:
            sampled_indices = np.arange(n_cases)

        # Calculate DTW for sampled cases
        for idx, case_idx in enumerate(sampled_indices):
            dtw_sim = DynamicTimeWarping.dtw_similarity(
                query_embedding,
                case_embeddings[case_idx]
            )
            dtw_scores[case_idx] = dtw_sim

        # For unsampled cases, use cosine as proxy
        if sample_rate < 1.0:
            unsampled_mask = np.ones(n_cases, dtype=bool)
            unsampled_mask[sampled_indices] = False
            cosine_scores = self.cosine_similarity(query_embedding, case_embeddings)
            dtw_scores[unsampled_mask] = cosine_scores[unsampled_mask] * 0.8  # Discount

        return np.clip(dtw_scores, 0, 1)

    def hybrid_similarity(
        self,
        query_embedding: np.ndarray,
        case_embeddings: np.ndarray,
        use_dtw: bool = False,
        dtw_sample_rate: float = 0.1
    ) -> np.ndarray:
        """
        Hybrid similarity: weighted combination of Cosine + DTW.

        Args:
            query_embedding: Query vector
            case_embeddings: Case vectors
            use_dtw: Whether to include DTW (slower)
            dtw_sample_rate: Fraction of cases to calculate DTW

        Returns:
            Hybrid similarity scores (0-1)
        """
        # Always use cosine
        cosine_scores = self.cosine_similarity(query_embedding, case_embeddings)

        if not use_dtw or self.dtw_weight == 0:
            return cosine_scores

        # Add DTW if enabled
        dtw_scores = self.dtw_similarity_batch(
            query_embedding,
            case_embeddings,
            sample_rate=dtw_sample_rate
        )

        # Weighted combination
        hybrid_scores = (self.cosine_weight * cosine_scores +
                         self.dtw_weight * dtw_scores)

        return np.clip(hybrid_scores, 0, 1)

    def search(
        self,
        query_embedding: np.ndarray,
        cases_df: pd.DataFrame,
        embeddings_df: pd.DataFrame,
        k: int = 50,
        regime_filter: Optional[str] = None,
        market_type_filter: Optional[str] = None,
        min_similarity: float = 0.50,
        use_dtw: bool = False,
        dtw_sample_rate: float = 0.1
    ) -> List[SimilarityResult]:
        """
        Search for most similar cases.

        Args:
            query_embedding: Query embedding vector
            cases_df: DataFrame with case metadata (regime_label, market_type, etc.)
            embeddings_df: DataFrame with case embeddings (PC0, PC1, ...)
            k: Number of results to return
            regime_filter: Filter to specific regime (BULL, BEAR, SIDEWAYS)
            market_type_filter: Filter to specific market type (DIP, PEAK, etc.)
            min_similarity: Minimum similarity threshold (0-1)
            use_dtw: Use DTW (slower but more robust)
            dtw_sample_rate: DTW sampling rate (0.1 = 10% of cases)

        Returns:
            List of SimilarityResult sorted by similarity (descending)
        """
        start_time = time.time()

        # Extract embedding columns
        embedding_cols = [c for c in embeddings_df.columns if c.startswith('PC') or c.startswith('AE')]
        case_embeddings = embeddings_df[embedding_cols].values

        # Step 1: Regime filtering
        if regime_filter:
            regime_mask = cases_df['regime_label'] == regime_filter
            filtered_indices = np.where(regime_mask)[0]
            logger.info(f"Regime filter '{regime_filter}': {len(filtered_indices)} / {len(cases_df)} cases")
        else:
            filtered_indices = np.arange(len(cases_df))

        if len(filtered_indices) == 0:
            logger.warning(f"No cases found for regime '{regime_filter}'")
            return []

        # Extract filtered embeddings
        filtered_embeddings = case_embeddings[filtered_indices]

        # Step 2: Market type filtering
        if market_type_filter:
            mt_mask = cases_df.iloc[filtered_indices]['market_type'].values == market_type_filter
            filtered_indices = filtered_indices[mt_mask]
            filtered_embeddings = filtered_embeddings[mt_mask]
            logger.info(f"Market type filter '{market_type_filter}': {len(filtered_indices)} cases remaining")

        if len(filtered_indices) == 0:
            logger.warning(f"No cases found for market type '{market_type_filter}'")
            return []

        # Step 3: Similarity calculation
        similarities = self.hybrid_similarity(
            query_embedding,
            filtered_embeddings,
            use_dtw=use_dtw,
            dtw_sample_rate=dtw_sample_rate
        )

        # Step 4: Threshold filtering
        above_threshold = similarities >= min_similarity
        top_indices = np.argsort(-similarities[above_threshold])[:k]

        # Step 5: Build results
        results = []
        for rank, local_idx in enumerate(top_indices):
            local_mask = np.where(above_threshold)[0]
            global_idx = filtered_indices[local_mask[local_idx]]

            case = cases_df.iloc[global_idx]

            result = SimilarityResult(
                id=int(global_idx),
                similarity_score=float(similarities[np.where(above_threshold)[0][local_idx]]),
                regime_label=case.get('regime_label', 'UNKNOWN'),
                market_type=case.get('market_type', 'UNKNOWN'),
                timestamp=case.get('timestamp'),
                price=float(case.get('price', 0)),
                forward_return_24h=case.get('forward_return_24h'),
                distance_type='hybrid' if use_dtw else 'cosine',
                rank=rank + 1
            )
            results.append(result)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Search completed in {elapsed_ms:.2f}ms, found {len(results)} results")

        return results

    def batch_search(
        self,
        query_embeddings: np.ndarray,
        cases_df: pd.DataFrame,
        embeddings_df: pd.DataFrame,
        k: int = 50,
        regime_filter: Optional[str] = None
    ) -> List[List[SimilarityResult]]:
        """
        Search for multiple queries.

        Args:
            query_embeddings: Multiple query vectors (n_queries x embedding_dim)
            cases_df: Case metadata
            embeddings_df: Case embeddings
            k: Results per query
            regime_filter: Optional regime filter

        Returns:
            List of result lists, one per query
        """
        results = []

        for i, query_emb in enumerate(query_embeddings):
            query_results = self.search(
                query_emb,
                cases_df,
                embeddings_df,
                k=k,
                regime_filter=regime_filter
            )
            results.append(query_results)

        return results

    def benchmark_search_speed(
        self,
        query_embedding: np.ndarray,
        cases_df: pd.DataFrame,
        embeddings_df: pd.DataFrame,
        n_trials: int = 10
    ) -> Dict:
        """
        Benchmark search performance.

        Returns:
            Dict with timing statistics
        """
        times = []

        for _ in range(n_trials):
            start = time.time()
            self.search(query_embedding, cases_df, embeddings_df, k=50)
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)

        times = np.array(times)

        return {
            'n_trials': n_trials,
            'mean_time_ms': float(times.mean()),
            'std_time_ms': float(times.std()),
            'min_time_ms': float(times.min()),
            'max_time_ms': float(times.max()),
            'p95_time_ms': float(np.percentile(times, 95)),
            'passes_100ms_target': float(np.percentile(times, 95)) < 100.0,
        }


class RegimeAwareSearch:
    """
    Advanced regime-aware similarity search.

    Strategies:
    - Within-regime search (high similarity, same regime)
    - Cross-regime search (find similar patterns across regimes)
    - Regime transition search (find patterns before regime changes)
    """

    def __init__(self, search_engine: SimilaritySearchEngine):
        """
        Args:
            search_engine: SimilaritySearchEngine instance
        """
        self.search_engine = search_engine

    def within_regime_search(
        self,
        query_embedding: np.ndarray,
        cases_df: pd.DataFrame,
        embeddings_df: pd.DataFrame,
        query_regime: str,
        k: int = 50
    ) -> List[SimilarityResult]:
        """
        Search only within same regime (high confidence).

        Args:
            query_embedding: Query vector
            cases_df: Case metadata
            embeddings_df: Case embeddings
            query_regime: Current regime
            k: Top results

        Returns:
            Similar cases in same regime
        """
        return self.search_engine.search(
            query_embedding,
            cases_df,
            embeddings_df,
            k=k,
            regime_filter=query_regime,
            min_similarity=0.65
        )

    def cross_regime_search(
        self,
        query_embedding: np.ndarray,
        cases_df: pd.DataFrame,
        embeddings_df: pd.DataFrame,
        exclude_regime: Optional[str] = None,
        k: int = 50
    ) -> List[SimilarityResult]:
        """
        Search across regimes (find universal patterns).

        Args:
            query_embedding: Query vector
            cases_df: Case metadata
            embeddings_df: Case embeddings
            exclude_regime: Regime to exclude
            k: Top results

        Returns:
            Cross-regime similar cases
        """
        results = self.search_engine.search(
            query_embedding,
            cases_df,
            embeddings_df,
            k=k * 2,  # Get more to filter
            min_similarity=0.50
        )

        # Filter out excluded regime
        if exclude_regime:
            results = [r for r in results if r.regime_label != exclude_regime]

        return results[:k]

    def hybrid_regime_search(
        self,
        query_embedding: np.ndarray,
        cases_df: pd.DataFrame,
        embeddings_df: pd.DataFrame,
        query_regime: str,
        k: int = 50
    ) -> Dict[str, List[SimilarityResult]]:
        """
        Return both within-regime and cross-regime results.

        Args:
            query_embedding: Query vector
            cases_df: Case metadata
            embeddings_df: Case embeddings
            query_regime: Current regime
            k: Results per category

        Returns:
            Dict with 'same_regime' and 'cross_regime' keys
        """
        same_regime = self.within_regime_search(
            query_embedding, cases_df, embeddings_df, query_regime, k=k
        )

        cross_regime = self.cross_regime_search(
            query_embedding, cases_df, embeddings_df, exclude_regime=query_regime, k=k
        )

        return {
            'same_regime': same_regime,
            'cross_regime': cross_regime,
        }
