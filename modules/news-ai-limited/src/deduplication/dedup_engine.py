"""
News AI Limited — Deduplication Engine

Aynı haberin birden fazla kaynak veya fetch döngüsünde sisteme düşmesini engeller.

İki katmanlı strateji:
1. SHA-256 kesin eşleşme  : normalize edilmiş başlık hash'i + kaynak URL hash'i
   → Kalıcı: Redis (TTL 7 gün), geçici: in-memory set
2. Jaccard bulanık eşleşme: kelime kümesi benzerliği ≥ 0.75
   → Son 400 başlık üzerinde çalışan in-memory sürgülü pencere

Fallback: Redis erişilemezse tamamen in-memory çalışır.
"""

from __future__ import annotations

import hashlib
import re
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Sabitler ──────────────────────────────────────────────────────────────────
_DEDUP_TTL_DAYS: int = 7
_DEDUP_TTL_SEC: int = _DEDUP_TTL_DAYS * 86_400
_REDIS_KEY_HASH = "news:dedup:hash:{h}"          # STRING  (value="1")
_REDIS_KEY_STATS = "news:dedup:stats"             # HASH    (field: counter name)
_FUZZY_THRESHOLD: float = 0.75                    # Jaccard benzerlik eşiği
_MEMORY_WINDOW: int = 400                         # In-memory sürgülü pencere boyutu


# ── Yardımcı modeller ─────────────────────────────────────────────────────────

@dataclass
class DedupResult:
    unique_items: list = field(default_factory=list)
    total_input: int = 0
    duplicates_exact: int = 0
    duplicates_fuzzy: int = 0
    duplicates_url: int = 0

    @property
    def total_duplicates(self) -> int:
        return self.duplicates_exact + self.duplicates_fuzzy + self.duplicates_url

    @property
    def dedup_rate_pct(self) -> float:
        if self.total_input == 0:
            return 0.0
        return round(self.total_duplicates / self.total_input * 100, 1)


# ── Ana Motor ─────────────────────────────────────────────────────────────────

class DedupEngine:
    """
    İki katmanlı haber tekilleştirme motoru.

    Kullanım:
        engine = DedupEngine(redis_client)
        result = engine.deduplicate(news_items)
    """

    def __init__(self, redis_client=None):
        """
        Args:
            redis_client: Opsiyonel redis.Redis (veya aioredis) bağlantısı.
                          None ise tamamen bellek içi çalışır.
        """
        self._redis = redis_client
        # In-memory fallback setleri
        self._seen_hashes: set[str] = set()
        self._seen_urls: set[str] = set()
        # Bulanık eşleşme için sürgülü pencere: her eleman (normalized_title, word_set)
        self._fuzzy_window: deque[Tuple[str, frozenset]] = deque(maxlen=_MEMORY_WINDOW)
        # Yaşam boyu istatistikler (process yeniden başlatıncaya kadar)
        self._stats = {
            "total_seen": 0,
            "exact_dups": 0,
            "fuzzy_dups": 0,
            "url_dups": 0,
            "sessions": 0,
        }

    # ── Normalleştirme & hash ──────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Başlığı normalleştirir: küçük harf, noktalama temizleme, çoklu boşluk kaldırma.
        """
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _title_hash(self, title: str) -> str:
        return self._sha256(self._normalize(title))

    def _url_hash(self, url: str) -> str:
        return self._sha256(url.strip().lower())

    # ── Jaccard benzerliği ─────────────────────────────────────────────────────

    @staticmethod
    def _word_set(normalized_title: str) -> frozenset:
        """Stop-word'suz kelime kümesi oluşturur."""
        _STOPWORDS = {
            "the", "a", "an", "is", "in", "on", "at", "to", "for", "of", "and",
            "or", "but", "with", "by", "from", "as", "this", "that", "are", "was",
            "has", "have", "be", "it", "its", "will", "he", "she", "they", "we",
            "bir", "ve", "ile", "de", "da", "bu", "için", "olan", "olan", "olan",
        }
        tokens = set(normalized_title.split())
        return frozenset(tokens - _STOPWORDS) if len(tokens) > 3 else frozenset(tokens)

    def _jaccard(self, set_a: frozenset, set_b: frozenset) -> float:
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def _is_fuzzy_duplicate(self, word_set: frozenset) -> bool:
        """Sürgülü penceredeki tüm başlıklarla Jaccard karşılaştırması yapar."""
        for _, existing_set in self._fuzzy_window:
            if self._jaccard(word_set, existing_set) >= _FUZZY_THRESHOLD:
                return True
        return False

    # ── Redis yardımcıları ─────────────────────────────────────────────────────

    def _redis_seen(self, key_hash: str) -> bool:
        """Redis'te hash'in daha önce görülüp görülmediğini kontrol eder."""
        if self._redis is None:
            return key_hash in self._seen_hashes
        try:
            redis_key = _REDIS_KEY_HASH.format(h=key_hash)
            return bool(self._redis.exists(redis_key))
        except Exception:
            return key_hash in self._seen_hashes

    def _redis_mark(self, key_hash: str) -> None:
        """Hash'i Redis'e kaydeder (TTL ile)."""
        self._seen_hashes.add(key_hash)
        if self._redis is None:
            return
        try:
            redis_key = _REDIS_KEY_HASH.format(h=key_hash)
            self._redis.setex(redis_key, _DEDUP_TTL_SEC, "1")
        except Exception as exc:
            logger.debug("dedup_redis_set_failed: %s", exc)

    def _redis_increment_stat(self, field: str, amount: int = 1) -> None:
        if self._redis is None:
            return
        try:
            self._redis.hincrby(_REDIS_KEY_STATS, field, amount)
        except Exception:
            pass

    # ── Tekilleştirme akışı ───────────────────────────────────────────────────

    def _check_single(self, item) -> Tuple[bool, str]:
        """
        Tek bir NewsItem'ı kontrol eder.

        Returns:
            (is_duplicate, reason)
        """
        # 1) URL tekilleştirme
        url_h = self._url_hash(item.source_url)
        if self._redis_seen(url_h):
            return True, "url_duplicate"

        # 2) Başlık kesin eşleşme
        title_h = self._title_hash(item.title)
        if self._redis_seen(title_h):
            return True, "exact_title_duplicate"

        # 3) Bulanık başlık eşleşme
        normalized = self._normalize(item.title)
        wset = self._word_set(normalized)
        if len(wset) >= 3 and self._is_fuzzy_duplicate(wset):
            return True, "fuzzy_title_duplicate"

        return False, "unique"

    def _register(self, item) -> None:
        """
        Benzersiz olarak doğrulanan haberi tüm indekslere kaydeder.
        """
        url_h = self._url_hash(item.source_url)
        title_h = self._title_hash(item.title)

        self._redis_mark(url_h)
        self._redis_mark(title_h)

        normalized = self._normalize(item.title)
        wset = self._word_set(normalized)
        self._fuzzy_window.append((normalized, wset))

    # ── Toplu işleme (dışarıya açık API) ──────────────────────────────────────

    def deduplicate(self, items: list) -> DedupResult:
        """
        Bir haber listesini tekilleştirir.

        Args:
            items: List[NewsItem] — genkontrol edilecek haberler

        Returns:
            DedupResult — benzersiz haberler ve istatistikler
        """
        result = DedupResult(total_input=len(items))
        self._stats["sessions"] += 1

        for item in items:
            is_dup, reason = self._check_single(item)

            if is_dup:
                self._stats["total_seen"] += 1
                if reason == "url_duplicate":
                    result.duplicates_url += 1
                    self._stats["url_dups"] += 1
                    self._redis_increment_stat("url_dups")
                elif reason == "exact_title_duplicate":
                    result.duplicates_exact += 1
                    self._stats["exact_dups"] += 1
                    self._redis_increment_stat("exact_dups")
                else:
                    result.duplicates_fuzzy += 1
                    self._stats["fuzzy_dups"] += 1
                    self._redis_increment_stat("fuzzy_dups")

                logger.debug(
                    "dedup_dropped source=%s title=%.60s reason=%s",
                    getattr(item, "source_name", "?"),
                    item.title,
                    reason,
                )
            else:
                self._register(item)
                result.unique_items.append(item)

        # Toplam istatistik Redis güncellemesi
        self._redis_increment_stat("total_seen", result.total_input)
        self._redis_increment_stat("total_unique", len(result.unique_items))

        logger.info(
            "dedup_complete input=%d unique=%d dups=%d (exact=%d fuzzy=%d url=%d) rate=%.1f%%",
            result.total_input,
            len(result.unique_items),
            result.total_duplicates,
            result.duplicates_exact,
            result.duplicates_fuzzy,
            result.duplicates_url,
            result.dedup_rate_pct,
        )
        return result

    # ── İstatistik & bakım ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Dedup istatistiklerini döndürür (Redis + memory combined)."""
        redis_stats: dict = {}
        if self._redis is not None:
            try:
                redis_stats = {
                    k.decode() if isinstance(k, bytes) else k: int(v)
                    for k, v in (self._redis.hgetall(_REDIS_KEY_STATS) or {}).items()
                }
            except Exception:
                pass

        return {
            "memory_stats": self._stats.copy(),
            "redis_stats": redis_stats,
            "fuzzy_window_size": len(self._fuzzy_window),
            "memory_hash_count": len(self._seen_hashes),
            "thresholds": {
                "jaccard_threshold": _FUZZY_THRESHOLD,
                "ttl_days": _DEDUP_TTL_DAYS,
                "fuzzy_window_capacity": _MEMORY_WINDOW,
            },
            "redis_connected": self._redis is not None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear_memory_cache(self) -> dict:
        """In-memory önbelleği temizler (Redis'teki kalıcı kayıtlara dokunmaz)."""
        prev_hashes = len(self._seen_hashes)
        prev_urls = len(self._seen_urls)
        prev_window = len(self._fuzzy_window)

        self._seen_hashes.clear()
        self._seen_urls.clear()
        self._fuzzy_window.clear()

        logger.info(
            "dedup_memory_cleared hashes=%d urls=%d window=%d",
            prev_hashes, prev_urls, prev_window,
        )
        return {
            "cleared_hashes": prev_hashes,
            "cleared_urls": prev_urls,
            "cleared_fuzzy_window": prev_window,
        }

    def clear_redis_cache(self) -> dict:
        """
        Redis'teki tüm dedup kayıtlarını siler.
        UYARI: Benzersizlik geçmişi sıfırlanır — sadece bakım amaçlı kullanın.
        """
        if self._redis is None:
            return {"cleared": 0, "note": "redis_not_connected"}

        try:
            pattern = _REDIS_KEY_HASH.format(h="*")
            keys = list(self._redis.scan_iter(pattern, count=500))
            # Stats hash'ini de temizle
            keys.append(_REDIS_KEY_STATS)
            if keys:
                deleted = self._redis.delete(*keys)
            else:
                deleted = 0
            logger.warning("dedup_redis_cache_cleared keys_deleted=%d", deleted)
            return {"cleared": deleted}
        except Exception as exc:
            logger.error("dedup_redis_clear_failed: %s", exc)
            return {"cleared": -1, "error": str(exc)}
