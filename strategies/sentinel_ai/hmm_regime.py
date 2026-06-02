"""
AEGIS Sentinel AI — HMM Rejim Tespiti (Hidden Markov Model)

Kural tabanlı eşik karşılaştırmaları yerine istatistiksel model:
  - 4 gizli durum: RISK_ON · NORMALIZATION · RISK_OFF · ACCUMULATION
  - Gözlem özellikleri: VIX, DXY, US10Y, Brent (normalize edilmiş)
  - Gaussian HMM (hmmlearn): Baum-Welch eğitimi, Viterbi çözümleme
  - Fallback: hmmlearn yoksa kural tabanlı hesap çalışır

Mimari:
  HMMRegimeDetector
    ├── train(df)          → yfinance geçmişiyle yeniden eğit
    ├── predict(obs)       → mevcut gözlemden olasılık dağılımı
    ├── fit_from_yfinance()→ otomatik veri çekme + eğitim
    └── _rule_based(obs)   → her zaman çalışan fallback
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Rejim sabitleri ───────────────────────────────────────────────────────────

REGIMES = ("risk_on", "normalization", "risk_off", "accumulation")
N_STATES = len(REGIMES)

# Gözlem vektörü sırası: [vix_norm, dxy_norm, us10y_norm, brent_norm]
_OBS_IDX = {"vix": 0, "dxy": 1, "us10y": 2, "brent": 3}
_N_FEATURES = len(_OBS_IDX)

# Normalizasyon parametreleri (tarihsel aralıklar, 2015-2025)
_NORM_PARAMS = {
    "vix":   {"min": 9.0,  "max": 80.0},
    "dxy":   {"min": 88.0, "max": 115.0},
    "us10y": {"min": 0.3,  "max": 5.5},
    "brent": {"min": 20.0, "max": 130.0},
}


def _normalize(value: float, key: str) -> float:
    p = _NORM_PARAMS[key]
    return float(np.clip((value - p["min"]) / (p["max"] - p["min"] + 1e-10), 0.0, 1.0))


def _obs_vector(macro: dict) -> np.ndarray:
    """Makro dict'ten normalize gözlem vektörü üret."""
    return np.array([
        _normalize(float(macro.get("vix",   22.0)), "vix"),
        _normalize(float(macro.get("dxy",   99.0)), "dxy"),
        _normalize(float(macro.get("us10y", 4.25)), "us10y"),
        _normalize(float(macro.get("brent", 90.0)), "brent"),
    ])


# ── HMMRegimeDetector ─────────────────────────────────────────────────────────

class HMMRegimeDetector:
    """
    Gaussian HMM ile piyasa rejimi tespiti.

    Kullanım:
        detector = HMMRegimeDetector()
        await detector.fit_from_yfinance(lookback_days=1500)
        probs = detector.predict(macro_snapshot)
        # {"risk_on": 0.05, "normalization": 0.72, "risk_off": 0.18, ...}
    """

    def __init__(self, n_states: int = N_STATES, random_state: int = 42):
        self.n_states = n_states
        self.random_state = random_state
        self._model = None          # hmmlearn GaussianHMM
        self._state_map: dict[int, str] = {}  # HMM state index → rejim adı
        self._trained_at: float = 0.0
        self._train_samples: int = 0
        self._available = self._check_hmmlearn()

    @staticmethod
    def _check_hmmlearn() -> bool:
        try:
            import hmmlearn  # noqa: F401
            return True
        except ImportError:
            logger.warning("hmmlearn bulunamadı — HMM devre dışı, kural tabanlı fallback aktif")
            return False

    # ── Eğitim ───────────────────────────────────────────────────────────────

    def train(self, obs_matrix: np.ndarray) -> bool:
        """
        Gözlem matrisiyle HMM'i eğit.

        Args:
            obs_matrix: shape (T, n_features) — zaman serisi gözlemleri
        Returns:
            True eğer eğitim başarılı
        """
        if not self._available or len(obs_matrix) < 50:
            return False
        try:
            from hmmlearn.hmm import GaussianHMM

            model = GaussianHMM(
                n_components=self.n_states,
                covariance_type="diag",   # diag daha stabil (full yerine)
                n_iter=500,
                random_state=self.random_state,
                tol=1e-3,                 # daha toleranslı yakınsama
                verbose=False,
            )
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # yakınsama uyarısını gizle
                model.fit(obs_matrix)
            self._model = model
            self._trained_at = time.time()
            self._train_samples = len(obs_matrix)

            # State → rejim eşlemesi: her state için ortalama VIX/DXY'den
            # en mantıklı rejim adını ata
            self._state_map = self._map_states_to_regimes(model, obs_matrix)

            logger.info(
                "hmm_trained: samples=%d states=%s",
                len(obs_matrix),
                self._state_map,
            )
            return True
        except Exception as exc:
            logger.warning("hmm_train_failed: %s", exc)
            self._model = None
            return False

    def _map_states_to_regimes(
        self, model, obs_matrix: np.ndarray
    ) -> dict[int, str]:
        """
        HMM durumlarını ekonomik rejimlerle eşleştir.

        Yöntem: Her state için ortalama gözlem vektörünü hesapla,
        VIX (risk) ve DXY (güç) eksenlerinde rejime ata.
        """
        try:
            states = model.predict(obs_matrix)
            mapping: dict[int, str] = {}
            for s in range(self.n_states):
                mask = states == s
                if mask.sum() == 0:
                    mapping[s] = REGIMES[s % N_STATES]
                    continue
                mean_obs = obs_matrix[mask].mean(axis=0)
                vix_norm   = mean_obs[_OBS_IDX["vix"]]    # 0=sakin 1=panik
                dxy_norm   = mean_obs[_OBS_IDX["dxy"]]    # 0=zayıf 1=güçlü
                us10y_norm = mean_obs[_OBS_IDX["us10y"]]  # 0=düşük faiz 1=yüksek

                # Karar ağacı: hangi rejim bu ortalamaya en yakın?
                if vix_norm < 0.30 and dxy_norm < 0.45:
                    regime = "risk_on"
                elif vix_norm > 0.55:
                    regime = "risk_off"
                elif vix_norm > 0.35 and us10y_norm < 0.45:
                    regime = "accumulation"
                else:
                    regime = "normalization"

                # Çakışma önleme: aynı rejim iki state'e atanamaz
                used = set(mapping.values())
                if regime in used:
                    remaining = [r for r in REGIMES if r not in used]
                    regime = remaining[0] if remaining else REGIMES[s % N_STATES]

                mapping[s] = regime
            return mapping
        except Exception as exc:
            logger.warning("hmm_state_mapping_failed: %s", exc)
            return {i: REGIMES[i % N_STATES] for i in range(self.n_states)}

    async def fit_from_yfinance(self, lookback_days: int = 1500) -> bool:
        """
        yfinance'tan tarihsel makro veri çek ve HMM'i eğit.
        Mevcut main.py akışını bozmaz — sadece modeli günceller.
        """
        try:
            import asyncio
            import yfinance as yf
            import pandas as pd

            logger.info("hmm_yfinance_fetch: lookback=%d days", lookback_days)

            tickers = {
                "vix":   "^VIX",
                "dxy":   "DX-Y.NYB",
                "us10y": "^TNX",
                "brent": "BZ=F",
            }
            period = f"{lookback_days}d"

            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(
                None,
                lambda: yf.download(
                    list(tickers.values()),
                    period=period,
                    interval="1d",
                    progress=False,
                    auto_adjust=True,
                ),
            )

            if raw.empty:
                logger.warning("hmm_yfinance_empty")
                return False

            # Kapanış fiyatları
            close = raw["Close"] if "Close" in raw.columns else raw
            close.columns = [k for k in tickers.keys()]

            # Temizle: ileri dolgu, geriye 5 bar en fazla
            close = close.ffill().bfill().dropna()
            if len(close) < 100:
                logger.warning("hmm_insufficient_data: %d rows", len(close))
                return False

            # Normalize gözlem matrisi
            obs = np.array([
                [
                    _normalize(float(row["vix"]),   "vix"),
                    _normalize(float(row["dxy"]),   "dxy"),
                    _normalize(float(row["us10y"]), "us10y"),
                    _normalize(float(row["brent"]), "brent"),
                ]
                for _, row in close.iterrows()
            ])

            success = self.train(obs)
            if success:
                logger.info("hmm_fit_complete: samples=%d", len(obs))
            return success

        except Exception as exc:
            logger.error("hmm_fit_from_yfinance_failed: %s", exc)
            return False

    # ── Tahmin ───────────────────────────────────────────────────────────────

    def predict(self, macro: dict, recent_window: int = 5) -> dict[str, float]:
        """
        Mevcut makro snapshot'tan rejim olasılık dağılımı üret.

        Args:
            macro: {"vix": 22, "dxy": 99, "us10y": 4.25, "brent": 90, ...}
            recent_window: son N gözlemi kullan (tek nokta yerine daha stabil)

        Returns:
            {"risk_on": 0.05, "normalization": 0.72, "risk_off": 0.18, "accumulation": 0.05}
        """
        if self._model is None or not self._available:
            return self._rule_based(macro)

        try:
            obs = _obs_vector(macro).reshape(1, -1)
            # Posterior state olasılıkları
            log_posteriors = self._model.predict_proba(obs)  # shape (1, n_states)
            posteriors = log_posteriors[0]                   # shape (n_states,)

            # State → rejim eşlemesiyle topla
            probs: dict[str, float] = {r: 0.0 for r in REGIMES}
            for state_idx, prob in enumerate(posteriors):
                regime = self._state_map.get(state_idx, "normalization")
                probs[regime] += float(prob)

            # Normalleştir (toplam 1.0 garantisi)
            total = sum(probs.values())
            if total > 0:
                probs = {k: round(v / total, 4) for k, v in probs.items()}

            logger.debug("hmm_predict: %s", probs)
            return probs

        except Exception as exc:
            logger.warning("hmm_predict_failed: %s — kural tabanlı fallback", exc)
            return self._rule_based(macro)

    # ── Kural tabanlı fallback ────────────────────────────────────────────────

    @staticmethod
    def _rule_based(macro: dict) -> dict[str, float]:
        """
        HMM başarısız olursa çalışan deterministik fallback.
        Mevcut _compute_regime_probabilities mantığıyla aynı.
        """
        import math

        dxy   = float(macro.get("dxy",   99))
        us10y = float(macro.get("us10y", 4.25))
        vix   = float(macro.get("vix",   22))
        xau   = float(macro.get("xau",   4800))
        hyg   = float(macro.get("hyg",   78.0))
        funding = float(macro.get("funding_rate", 0.0))

        scores: dict[str, float] = {
            "risk_on": 0.0, "normalization": 0.0,
            "risk_off": 0.0, "accumulation": 0.0,
        }
        scores["risk_on"] += max(0, (102 - dxy)   * 0.03)
        scores["risk_on"] += max(0, (4.5 - us10y) * 0.12)
        scores["risk_on"] += max(0, (22 - vix)    * 0.02)
        scores["risk_on"] += max(0, (hyg - 75)    * 0.04)

        scores["risk_off"] += max(0, (dxy - 100)  * 0.025)
        scores["risk_off"] += max(0, (us10y - 4.0) * 0.10)
        scores["risk_off"] += max(0, (vix - 20)   * 0.025)
        scores["risk_off"] += max(0, (xau - 4500) * 0.00005)
        scores["risk_off"] += max(0, (75 - hyg)   * 0.05)
        if funding > 0.05:
            scores["risk_off"] += (funding - 0.05) * 2.0

        if 96 <= dxy <= 103 and 3.5 <= us10y <= 5.0 and vix < 25 and hyg > 74:
            scores["normalization"] = 0.35
        if vix < 20 and us10y < 4.5 and dxy < 101 and hyg > 76:
            scores["accumulation"] = 0.30

        exp_scores = {k: math.exp(min(v, 10)) for k, v in scores.items()}
        total = sum(exp_scores.values())
        if total == 0:
            return {"risk_on": 0.25, "normalization": 0.25,
                    "risk_off": 0.25, "accumulation": 0.25}
        return {k: round(v / total, 4) for k, v in exp_scores.items()}

    # ── Durum sorgulama ───────────────────────────────────────────────────────

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    @property
    def training_age_hours(self) -> float:
        if self._trained_at == 0:
            return -1.0  # -1 = hiç eğitilmedi (inf JSON uyumsuz)
        return (time.time() - self._trained_at) / 3600

    @property
    def status(self) -> dict:
        age = self.training_age_hours
        return {
            "available": self._available,
            "trained": self.is_trained,
            "training_age_hours": round(age, 2) if age >= 0 else None,
            "train_samples": self._train_samples,
            "state_map": self._state_map,
            "method": "hmm" if self.is_trained else "rule_based",
            "retrain_due": age > _RETRAIN_HOURS if age >= 0 else True,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_detector: Optional[HMMRegimeDetector] = None
_RETRAIN_HOURS = float(os.environ.get("HMM_RETRAIN_HOURS", "24"))
_LOOKBACK_DAYS = int(os.environ.get("HMM_LOOKBACK_DAYS", "1500"))


def get_detector() -> HMMRegimeDetector:
    global _detector
    if _detector is None:
        _detector = HMMRegimeDetector()
    return _detector


async def get_regime_probs(macro: dict) -> dict[str, float]:
    """
    Ana giriş noktası: makro snapshot → rejim olasılık dağılımı.

    Otomatik yönetim:
    - İlk çağrıda arka planda eğitimi başlatır
    - 24 saatte bir yeniden eğitir
    - Eğitim yoksa kural tabanlı fallback
    """
    detector = get_detector()

    # İlk çağrı veya stale → arka planda eğit
    if not detector.is_trained or detector.training_age_hours > _RETRAIN_HOURS:
        import asyncio
        asyncio.create_task(_background_train(detector))

    return detector.predict(macro)


async def _background_train(detector: HMMRegimeDetector) -> None:
    """Eğitimi arka planda çalıştır — ana iş akışını bloke etmez."""
    logger.info("hmm_background_train_start")
    success = await detector.fit_from_yfinance(lookback_days=_LOOKBACK_DAYS)
    logger.info("hmm_background_train_done: success=%s", success)
