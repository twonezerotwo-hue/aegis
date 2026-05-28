"""
AEGIS CBR Engine - Vector Database & Similarity Search
Fast similarity search using HNSW index + Cosine distance

Goal: Find similar past fingerprints in <100ms for 10K vectors

Backend priority (v7.2):
  1. Qdrant  — persistent, production-grade (requires qdrant container)
  2. HNSW    — in-process hnswlib (fast, ephemeral)
  3. Brute   — pure numpy fallback (slow, always available)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
_QDRANT_COLLECTION = "cbr_fingerprints"
_QDRANT_VECTOR_DIM_DEFAULT = 12


@dataclass
class SimilarCase:
    """Returned similar case"""
    fingerprint_id: int
    similarity: float
    regime_label: str
    market_type: str
    timestamp: datetime
    price: float
    forward_return_24h: Optional[float] = None

    @property
    def similarity_score(self) -> float:
        return self.similarity


# ── Qdrant backend helpers ──────────────────────────────────────────────────

class _QdrantBackend:
    """
    Thin wrapper around qdrant-client.
    Returns (available=True, client) on success, (False, None) on any failure.
    CBR pipeline calls this once at startup; if unavailable it falls back to
    the existing HNSW / brute-force path and logs a WARNING.
    """

    def __init__(self) -> None:
        self.client = None
        self.available = False
        self._try_connect()

    def _try_connect(self) -> None:
        try:
            from qdrant_client import QdrantClient  # type: ignore[import]
            from qdrant_client.http import exceptions as qex  # type: ignore[import]
            c = QdrantClient(url=_QDRANT_URL, timeout=3.0)
            c.get_collections()  # connectivity check
            self.client = c
            self.available = True
            logger.info("QDRANT: connected to %s", _QDRANT_URL)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "QDRANT: unavailable (%s) — falling back to HNSW/brute-force", exc
            )

    def ensure_collection(self, dim: int) -> bool:
        """Create collection if it does not exist. Returns success flag."""
        if not self.available:
            return False
        try:
            from qdrant_client.models import Distance, VectorParams  # type: ignore[import]
            existing = {c.name for c in self.client.get_collections().collections}
            if _QDRANT_COLLECTION not in existing:
                self.client.create_collection(
                    collection_name=_QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
                logger.info("QDRANT: created collection '%s' dim=%d", _QDRANT_COLLECTION, dim)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("QDRANT: ensure_collection failed — %s", exc)
            self.available = False
            return False

    def upsert(self, ids: List[int], vectors: List[List[float]], payloads: List[dict]) -> bool:
        if not self.available:
            return False
        try:
            from qdrant_client.models import PointStruct  # type: ignore[import]
            points = [
                PointStruct(id=i, vector=v, payload=p)
                for i, v, p in zip(ids, vectors, payloads)
            ]
            self.client.upsert(collection_name=_QDRANT_COLLECTION, points=points)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("QDRANT: upsert failed — %s", exc)
            self.available = False
            return False

    def search(
        self,
        query: List[float],
        k: int,
        regime_filter: Optional[str],
        threshold: float,
    ) -> List[SimilarCase]:
        if not self.available:
            return []
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore[import]
            qfilter = None
            if regime_filter:
                qfilter = Filter(
                    must=[FieldCondition(key="regime_label", match=MatchValue(value=regime_filter))]
                )
            hits = self.client.search(
                collection_name=_QDRANT_COLLECTION,
                query_vector=query,
                limit=k,
                query_filter=qfilter,
                score_threshold=threshold,
            )
            results: List[SimilarCase] = []
            for hit in hits:
                p = hit.payload or {}
                results.append(SimilarCase(
                    fingerprint_id=int(hit.id),
                    similarity=float(hit.score),
                    regime_label=p.get("regime_label", "UNKNOWN"),
                    market_type=p.get("market_type", "UNKNOWN"),
                    timestamp=p.get("timestamp"),  # type: ignore[arg-type]
                    price=float(p.get("price", 0.0)),
                    forward_return_24h=p.get("forward_return_24h"),
                ))
            return results
        except Exception as exc:  # noqa: BLE001
            logger.warning("QDRANT: search failed — %s — falling back", exc)
            self.available = False
            return []


class VectorDatabase:
    """
    Fast similarity search for CBR cases.

    Backend selection order (v7.2):
      1. Qdrant  — if qdrant-client is importable and the server is reachable
      2. HNSW    — hnswlib in-process index (fast, ephemeral)
      3. Brute   — pure numpy cosine (always available, slow on large sets)

    The caller never needs to know which backend is active.
    """

    def __init__(self, embedding_dim: int = 12, regime_stratified: bool = True):
        self.embedding_dim = embedding_dim
        self.regime_stratified = regime_stratified
        self.indices: dict = {}
        self.vectors: dict = {}
        self.metadata: dict = {}

        # Tier-1: Qdrant
        self._qdrant = _QdrantBackend()

        # Tier-2: HNSW
        try:
            import hnswlib
            self.hnswlib = hnswlib
            self.has_hnswlib = True
        except ImportError:
            logger.warning("hnswlib not available - using brute-force similarity (slow)")
            self.has_hnswlib = False

    def build_index(self, embeddings_df: pd.DataFrame, regime_column: str = 'regime_label'):
        """
        Build vector index from embeddings.

        Writes to Qdrant (if available) AND builds the local HNSW/brute-force
        index so that hot-restart and offline scenarios still work.
        """
        if not self.has_hnswlib:
            self._build_index_bruteforce(embeddings_df, regime_column)
        else:
            self._build_index_hnsw(embeddings_df, regime_column)

        # Also populate Qdrant if reachable
        self._build_index_qdrant(embeddings_df, regime_column)

    def _build_index_qdrant(self, embeddings_df: pd.DataFrame, regime_column: str) -> None:
        """Write all vectors to Qdrant. Soft-fail if Qdrant is unavailable."""
        if not self._qdrant.available:
            return
        embedding_cols = [c for c in embeddings_df.columns if c.startswith('PC') or c.startswith('AE')]
        if not embedding_cols:
            return
        dim = len(embedding_cols)
        if not self._qdrant.ensure_collection(dim):
            return
        vectors = embeddings_df[embedding_cols].values.astype('float32').tolist()
        ids = list(range(len(vectors)))
        payloads: List[dict] = []
        for _, row in embeddings_df.iterrows():
            payloads.append({
                "regime_label": row.get(regime_column, "UNKNOWN"),
                "market_type": row.get("market_type", "UNKNOWN"),
                "timestamp": str(row.get("timestamp", "")),
                "price": float(row.get("current_price", 0.0)),
                "forward_return_24h": row.get("forward_return_24h"),
            })
        self._qdrant.upsert(ids, vectors, payloads)
        logger.info("QDRANT: indexed %d vectors in '%s'", len(vectors), _QDRANT_COLLECTION)

    def _build_index_hnsw(self, embeddings_df: pd.DataFrame, regime_column: str) -> None:
        """Original HNSW index build (renamed from build_index, unchanged logic)."""
        embedding_cols = [c for c in embeddings_df.columns if c.startswith('PC') or c.startswith('AE')]

        if len(embedding_cols) != self.embedding_dim:
            logger.warning(f"Embedding dim mismatch: expected {self.embedding_dim}, got {len(embedding_cols)}")

        if self.regime_stratified:
            regimes = embeddings_df[regime_column].unique()

            for regime in regimes:
                mask = embeddings_df[regime_column] == regime
                regime_data = embeddings_df[mask]

                if len(regime_data) == 0:
                    continue

                vectors = regime_data[embedding_cols].values.astype('float32')
                n_samples = vectors.shape[0]

                # Create HNSW index
                idx = self.hnswlib.Index(space='cosine', dim=len(embedding_cols))
                idx.init_index(max_elements=n_samples + 1000, ef_construction=200, M=16)

                # Add vectors
                ids = np.arange(n_samples, dtype=np.int64)
                idx.add_items(vectors, ids)

                # Store
                self.indices[regime] = idx
                self.vectors[regime] = vectors

                # Store metadata for retrieval
                metadata = []
                for _, row in regime_data.iterrows():
                    metadata.append({
                        'id': len(metadata),
                        'regime_label': row[regime_column],
                        'market_type': row.get('market_type', 'UNKNOWN'),
                        'timestamp': row.get('timestamp'),
                        'price': row.get('current_price', np.nan),
                        'forward_return_24h': row.get('forward_return_24h'),
                    })
                self.metadata[regime] = metadata

                logger.info(f"Built index for regime {regime}: {n_samples} samples")
        else:
            # Single global index
            vectors = embeddings_df[embedding_cols].values.astype('float32')
            n_samples = vectors.shape[0]

            idx = self.hnswlib.Index(space='cosine', dim=len(embedding_cols))
            idx.init_index(max_elements=n_samples + 1000, ef_construction=200, M=16)

            ids = np.arange(n_samples, dtype=np.int64)
            idx.add_items(vectors, ids)

            self.indices['GLOBAL'] = idx
            self.vectors['GLOBAL'] = vectors

            metadata = []
            for _, row in embeddings_df.iterrows():
                metadata.append({
                    'id': len(metadata),
                    'regime_label': row[regime_column],
                    'market_type': row.get('market_type', 'UNKNOWN'),
                    'timestamp': row.get('timestamp'),
                    'price': row.get('current_price', np.nan),
                    'forward_return_24h': row.get('forward_return_24h'),
                })
            self.metadata['GLOBAL'] = metadata

            logger.info(f"Built global index: {n_samples} samples")

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 10,
        regime_filter: Optional[str] = None,
        similarity_threshold: float = 0.5
    ) -> List[SimilarCase]:
        """
        Search for most similar cases.

        Args:
            query_embedding: Query vector (length = embedding_dim)
            k: Number of results to return
            regime_filter: Filter to specific regime (or None for all)
            similarity_threshold: Minimum similarity (0-1, where 1=identical)

        Returns:
            List of SimilarCase ordered by similarity
        """
        if not self.has_hnswlib:
            return self._search_bruteforce(query_embedding, k, regime_filter, similarity_threshold)

        query = query_embedding.reshape(1, -1).astype('float32')

        results = []

        if regime_filter and regime_filter in self.indices:
            # Search single regime
            idx = self.indices[regime_filter]
            labels, distances = idx.knn_query(query, k=k)

            for dist, label in zip(distances[0], labels[0]):
                if label == -1:
                    continue

                # Convert distance to similarity (cosine distance -> similarity)
                similarity = 1 - dist  # In cosine space, dist in [0, 2]
                similarity = np.clip(similarity, 0, 1)

                if similarity < similarity_threshold:
                    continue

                metadata = self.metadata[regime_filter][label]
                results.append(SimilarCase(
                    fingerprint_id=metadata['id'],
                    similarity=float(similarity),
                    regime_label=metadata['regime_label'],
                    market_type=metadata['market_type'],
                    timestamp=metadata['timestamp'],
                    price=metadata['price'],
                    forward_return_24h=metadata.get('forward_return_24h')
                ))

        elif regime_filter is None:
            # Search all regimes - combine and sort
            for regime in self.indices:
                idx = self.indices[regime]
                labels, distances = idx.knn_query(query, k=k)

                for dist, label in zip(distances[0], labels[0]):
                    if label == -1:
                        continue

                    similarity = 1 - dist
                    similarity = np.clip(similarity, 0, 1)

                    if similarity < similarity_threshold:
                        continue

                    metadata = self.metadata[regime][label]
                    results.append(SimilarCase(
                        fingerprint_id=metadata['id'],
                        similarity=float(similarity),
                        regime_label=metadata['regime_label'],
                        market_type=metadata['market_type'],
                        timestamp=metadata['timestamp'],
                        price=metadata['price'],
                        forward_return_24h=metadata.get('forward_return_24h')
                    ))

        return sorted(results, key=lambda x: x.similarity, reverse=True)[:k]

    def _build_index_bruteforce(self, embeddings_df: pd.DataFrame, regime_column: str):
        """Fallback: store all vectors in memory"""
        embedding_cols = [c for c in embeddings_df.columns if c.startswith('PC') or c.startswith('AE')]

        self.vectors['GLOBAL'] = embeddings_df[embedding_cols].values
        self.metadata['GLOBAL'] = embeddings_df.to_dict('records')

        logger.info(f"Built brute-force index: {len(embeddings_df)} samples")

    def _search_bruteforce(
        self,
        query: np.ndarray,
        k: int,
        regime_filter: Optional[str],
        threshold: float
    ) -> List[SimilarCase]:
        """Brute-force similarity search"""
        vectors = self.vectors['GLOBAL']

        # Cosine similarity
        norms_query = np.linalg.norm(query)
        norms_vectors = np.linalg.norm(vectors, axis=1)

        similarities = np.dot(vectors, query) / (norms_vectors * norms_query + 1e-8)

        # Filter by regime if specified
        if regime_filter:
            mask = np.array([m['regime_label'] == regime_filter for m in self.metadata['GLOBAL']])
            similarities[~mask] = -2

        # Get top k
        top_indices = np.argsort(-similarities)[:k]

        results = []
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim < threshold:
                continue

            metadata = self.metadata['GLOBAL'][idx]
            results.append(SimilarCase(
                fingerprint_id=metadata['id'],
                similarity=sim,
                regime_label=metadata.get('regime_label'),
                market_type=metadata.get('market_type'),
                timestamp=metadata.get('timestamp'),
                price=metadata.get('price'),
                forward_return_24h=metadata.get('forward_return_24h')
            ))

        return results

    def get_statistics(self) -> Dict:
        """Index statistics"""
        stats = {
            'has_hnswlib': self.has_hnswlib,
            'regimes': list(self.indices.keys()),
            'total_vectors': sum(len(v) for v in self.vectors.values()),
        }

        for regime in self.indices:
            stats[f'vectors_in_{regime}'] = len(self.vectors.get(regime, []))

        return stats


class SimilarityEngine:
    """
    High-level API for case-based similarity matching.

    Uses VectorDatabase internally but adds filtering and ranking.
    """

    def __init__(self, reducer, vector_db: VectorDatabase):
        """
        Args:
            reducer: Dimensionality reducer (PCA or Autoencoder)
            vector_db: VectorDatabase instance
        """
        self.reducer = reducer
        self.vector_db = vector_db

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 10,
        market_type: Optional[str] = None,
        regime_filter: Optional[str] = None,
        similarity_threshold: float = 0.5,
    ) -> List[SimilarCase]:
        """Compatibility wrapper used by the orchestrator with precomputed embeddings."""
        results = self.vector_db.search(
            query_embedding,
            k=k,
            regime_filter=regime_filter,
            similarity_threshold=similarity_threshold,
        )

        if market_type is not None:
            filtered = [case for case in results if case.market_type == market_type]
            if filtered:
                return filtered[:k]

        return results[:k]

    def find_similar_cases(
        self,
        query_fingerprint: Dict,
        k: int = 10,
        regime_filter: Optional[str] = None,
        min_confidence: float = 0.65
    ) -> List[SimilarCase]:
        """
        Find similar historical cases for current fingerprint.

        Args:
            query_fingerprint: Current market fingerprint dict
            k: Number of similar cases to return
            regime_filter: Restrict to specific regime (BULL/BEAR/SIDEWAYS)
            min_confidence: Minimum similarity score (0-1)

        Returns:
            List of SimilarCase sorted by similarity
        """
        # Convert fingerprint to embedding
        fp_df = pd.DataFrame([query_fingerprint])
        embedding_df = self.reducer.transform(fp_df)

        # Extract embedding vector
        embedding_cols = [c for c in embedding_df.columns if c.startswith('PC') or c.startswith('AE')]
        embedding = embedding_df[embedding_cols].values[0]

        # Search
        results = self.vector_db.search(
            embedding,
            k=k,
            regime_filter=regime_filter,
            similarity_threshold=min_confidence
        )

        return results

    def ensemble_similar_cases(
        self,
        similar_cases: List[SimilarCase],
        weight_column: str = 'forward_return_24h'
    ) -> Dict:
        """
        Ensemble predictions from similar cases.

        Args:
            similar_cases: List of similar cases with outcomes
            weight_column: Which column to use for results (forward_return_24h, etc.)

        Returns:
            Dict with ensemble statistics
        """
        if not similar_cases or any(c.forward_return_24h is None for c in similar_cases):
            return {
                'ensemble_return': 0.0,
                'confidence': 0.0,
                'sample_count': len(similar_cases),
            }

        # Weight by similarity * outcome
        returns = np.array([c.forward_return_24h for c in similar_cases])
        similarities = np.array([c.similarity for c in similar_cases])

        # Weighted average
        ensemble_return = np.average(returns, weights=similarities)

        # Confidence: agreement among similar cases
        consistency = 1 - np.std(returns) / (np.abs(np.mean(returns)) + 1e-8)
        confidence = np.mean(similarities) * np.clip(consistency, 0, 1)

        return {
            'ensemble_return': float(ensemble_return),
            'ensemble_confidence': float(confidence),
            'mean_similarity': float(np.mean(similarities)),
            'std_similarity': float(np.std(similarities)),
            'sample_count': len(similar_cases),
            'agreement': float(consistency),
        }
