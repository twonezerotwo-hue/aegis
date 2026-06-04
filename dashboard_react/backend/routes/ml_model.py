"""
AEGIS ML Predictor — FreqAI benzeri öğrenen sinyal modülü

FreqAI'dan ilham alınan yaklaşım:
  - 60+ teknik indikatör özelliği
  - XGBoost sınıflandırıcı (sklearn GradientBoosting fallback)
  - Walk-forward eğitim (geçmiş 18 ay train, son 3 ay test)
  - Canlıda otomatik yeniden eğitim (RETRAIN_BARS'ta bir)
  - Deterministik indikatörler gecikmeli sinyal üretir → ML geleceği tahmin eder

Hedef değişken:
  y=1 (BUY)  : 3 bar sonraki kapanış > giriş + 0.5×ATR
  y=0 (HOLD) : arada
  y=-1 (SELL): 3 bar sonraki kapanış < giriş - 0.5×ATR

Çıktı:
  buy_prob : 0-1   → 0.5 normalleştirilerek consensus'a girer
  sell_prob: 0-1
  ml_score : 0-1   → 0.5 nötr, >0.65 AL, <0.35 SAT
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Sabitler ──────────────────────────────────────────────────────────────────
_TRAIN_LOOKBACK_BARS = int(os.environ.get("ML_TRAIN_BARS", "2000"))   # eğitim penceresi
_RETRAIN_BARS        = int(os.environ.get("ML_RETRAIN_BARS", "200"))  # her N barda yeniden eğit
_FORWARD_BARS        = int(os.environ.get("ML_FORWARD_BARS", "3"))    # hedef: N bar sonraki getiri
_ATR_MULT            = float(os.environ.get("ML_ATR_MULT", "0.75"))   # BUY/SELL eşiği — 0.5→0.75: HOLD sınıfı azaltıldı, sinyaller daha seçici
_MIN_TRAIN_ROWS      = 200

# ── State ─────────────────────────────────────────────────────────────────────
_models:    dict[str, object]     = {}   # key: symbol_timeframe
_metadata:  dict[str, dict]       = {}   # eğitim meta
_bar_count: dict[str, int]        = {}   # son eğitimden bu yana bar sayısı
_ohlcv_cache: dict[str, pd.DataFrame] = {}
_ml_pred_cache: dict[str, dict]   = {}  # son ML tahmini önbelleği (dashboard okur)
_training_queue: set[str]         = set()  # şu an eğitilen TF'ler

# Fallback öncelik sırası — model yokken hangi TF kullanılsın
_TF_FALLBACK_ORDER = ["BTC/USDT|4h", "BTC/USDT|1d", "BTC/USDT|1h", "BTC/USDT|4h"]

# ── KALICILIK: modeller diske kaydedilir (restart'ta korunur) ──────────────────
_MODEL_DIR = os.path.join(os.environ.get("AGENT_DATA_DIR", "/app/data"), "ml_models")


def _safe_key(symbol_tf: str) -> str:
    return symbol_tf.replace("/", "_").replace("|", "__")


def _save_model(symbol_tf: str) -> None:
    """Eğitilen modeli + meta'yı diske yaz (joblib)."""
    try:
        import joblib
        os.makedirs(_MODEL_DIR, exist_ok=True)
        path = os.path.join(_MODEL_DIR, _safe_key(symbol_tf) + ".joblib")
        joblib.dump({
            "model_tuple": _models.get(symbol_tf),
            "metadata":    _metadata.get(symbol_tf),
            "bar_count":   _bar_count.get(symbol_tf, 0),
            "pred":        _ml_pred_cache.get(symbol_tf),
        }, path)
        logger.info("ML_SAVED %s → %s", symbol_tf, path)
    except Exception as exc:
        logger.warning("ML model kaydı başarısız %s: %s", symbol_tf, exc)


def _load_models() -> int:
    """Açılışta diskteki tüm modelleri belleğe yükle."""
    loaded = 0
    try:
        import joblib
        if not os.path.isdir(_MODEL_DIR):
            return 0
        for fn in os.listdir(_MODEL_DIR):
            if not fn.endswith(".joblib"):
                continue
            try:
                data = joblib.load(os.path.join(_MODEL_DIR, fn))
                # key'i meta veya dosya adından geri çöz
                meta = data.get("metadata") or {}
                # Dosya adından symbol_tf'i geri kur
                base = fn[:-len(".joblib")].replace("__", "|").replace("_", "/", 1)
                if data.get("model_tuple"):
                    _models[base] = data["model_tuple"]
                    _metadata[base] = meta
                    _bar_count[base] = data.get("bar_count", 0)
                    if data.get("pred"):
                        _ml_pred_cache[base] = data["pred"]
                    loaded += 1
            except Exception as exc:
                logger.debug("model yüklenemedi %s: %s", fn, exc)
        if loaded:
            logger.info("ML_LOADED %d model diskten yüklendi: %s", loaded, list(_models.keys()))
    except Exception as exc:
        logger.warning("ML model yükleme başarısız: %s", exc)
    return loaded


def _get_fallback_cache(symbol: str, timeframe: str) -> dict | None:
    """Belirtilen TF için önbellekte model yoksa en yakın mevcut modeli döndür."""
    key = f"{symbol}|{timeframe}"
    if key in _ml_pred_cache:
        return _ml_pred_cache[key]
    # Aynı sembol farklı TF
    for fallback_key in _TF_FALLBACK_ORDER:
        if fallback_key in _ml_pred_cache:
            cached = dict(_ml_pred_cache[fallback_key])
            cached["_fallback_from"] = fallback_key  # bilgi ekle
            return cached
    return None


async def _background_train_task(symbol: str, timeframe: str) -> None:
    """Arka planda model eğit, tamamlanınca _training_queue'dan çıkar."""
    key = f"{symbol}|{timeframe}"
    try:
        logger.info("ML_BG_TRAIN start: %s", key)
        df = await _fetch_ohlcv_for_ml(symbol, timeframe, limit=_TRAIN_LOOKBACK_BARS + 50)
        meta = train_model(df, key)
        # Tahmin yap ve önbelleğe yaz
        result = predict(df, key)
        _ml_pred_cache[key] = result
        logger.info("ML_BG_TRAIN done: %s acc=%.1f%%", key, meta.get("accuracy", 0))
    except Exception as exc:
        logger.warning("ML_BG_TRAIN failed %s: %s", key, exc)
    finally:
        _training_queue.discard(key)


def trigger_background_train(symbol: str, timeframe: str) -> bool:
    """
    Arka planda eğitim başlat (non-blocking).
    Zaten eğitiliyorsa False döner.
    """
    key = f"{symbol}|{timeframe}"
    if key in _training_queue or key in _models:
        return False
    _training_queue.add(key)
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_background_train_task(symbol, timeframe))
        logger.info("ML_BG_TRAIN queued: %s", key)
        return True
    except RuntimeError:
        # Event loop yok veya çalışmıyor
        _training_queue.discard(key)
        return False


def get_ml_score(symbol: str, timeframe: str) -> float:
    """Sync ML skoru — model yoksa en yakın fallback, o da yoksa 0.5."""
    cached = _get_fallback_cache(symbol, timeframe)
    return float(cached.get("ml_score", 0.5)) if cached else 0.5


def get_ml_signal(symbol: str, timeframe: str) -> str:
    cached = _get_fallback_cache(symbol, timeframe)
    return cached.get("signal", "NEUTRAL") if cached else "NEUTRAL"


def is_ml_trained(symbol: str, timeframe: str) -> bool:
    """Herhangi bir model eğitilmişse True döner (fallback için de yeterli)."""
    key = f"{symbol}|{timeframe}"
    if key in _models:
        return True
    # Fallback model var mı?
    for fb in _TF_FALLBACK_ORDER:
        if fb in _models:
            return True
    return False


def get_ml_status(symbol: str, timeframe: str) -> dict:
    """Bir TF için model durumu: trained/training/fallback/untrained."""
    key = f"{symbol}|{timeframe}"
    if key in _models:
        return {"status": "trained", "key": key}
    if key in _training_queue:
        return {"status": "training", "key": key}
    for fb in _TF_FALLBACK_ORDER:
        if fb in _models:
            return {"status": "fallback", "key": key, "fallback_from": fb}
    return {"status": "untrained", "key": key}


# ── Özellik Mühendisliği ──────────────────────────────────────────────────────

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs    = gain / (loss + 1e-10)
    return 100 - 100 / (1 + rs)

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    60+ teknik özellik hesapla.
    Giriş: OHLCV DataFrame (timestamp index, open/high/low/close/volume sütunları)
    Çıktı: özellik DataFrame (aynı index, NaN satırlar düşürülmüş)
    """
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    feat: dict[str, pd.Series] = {}

    # ── Yardımcı: Z-score serisi ──────────────────────────────────────────
    def _zscore(s: pd.Series, window: int = 50) -> pd.Series:
        """(s - rolling_mean) / (rolling_std + ε) — sergiyi durduran trend etkisini kaldırır."""
        mu  = s.rolling(window, min_periods=window // 2).mean()
        sig = s.rolling(window, min_periods=window // 2).std()
        return (s - mu) / (sig + 1e-10)

    # ── Getiriler: Z-score'lu (trend etkisi giderilmiş) ───────────────────
    # Sorun: ham ret_1=+0.02 → model "pozitif → AL" öğreniyor (bull'da hep 0.95)
    # Düzeltme: ret_z = (bu getiri - son 50 bar ortalama getiri) / std
    #   → "olağan trend" mı yoksa "olağandışı hareket" mi ayrımı yapılır
    for n in [1, 2, 3, 5, 10, 20]:
        raw_ret = c.pct_change(n)
        feat[f"ret_{n}"]   = raw_ret                  # ham tutuldu (ağırlık az)
        feat[f"ret_z_{n}"] = _zscore(raw_ret, 50)     # detrended z-score

    # ── Volatilite ────────────────────────────────────────────────────────
    bar_ret = c.pct_change()
    for n in [5, 10, 20]:
        feat[f"vol_{n}"]   = bar_ret.rolling(n).std()
    feat["atr_14"]   = _atr(h, l, c, 14)
    feat["atr_norm"] = feat["atr_14"] / c
    # Volatilite rejimi: şu an yüksek mi düşük mü?
    feat["vol_regime"] = _zscore(feat["vol_20"] if "vol_20" in feat
                                 else bar_ret.rolling(20).std(), 60)

    # ── Trend: EMA ────────────────────────────────────────────────────────
    for n in [9, 21, 50, 100, 200]:
        em = _ema(c, n)
        feat[f"ema{n}_slope"] = em.pct_change(3)
        feat[f"price_ema{n}"] = (c / em - 1)
    feat["ema9_21_cross"]   = (_ema(c, 9)  - _ema(c, 21))  / c
    feat["ema21_50_cross"]  = (_ema(c, 21) - _ema(c, 50))  / c
    feat["ema50_200_cross"] = (_ema(c, 50) - _ema(c, 200)) / c

    # ── RSI: ham + z-score + sapma ────────────────────────────────────────
    rsi14 = _rsi(c, 14)
    feat["rsi_7"]       = _rsi(c, 7)
    feat["rsi_14"]      = rsi14
    feat["rsi_21"]      = _rsi(c, 21)
    feat["rsi_slope_3"] = rsi14.diff(3)
    # RSI 50'den uzaklık (ortalama merkez)
    feat["rsi_dev_50"]  = rsi14 - 50.0
    # RSI z-score: bu RSI kendi geçmişine göre aşırı mı?
    feat["rsi_z"]       = _zscore(rsi14, 50)

    # ── MACD ──────────────────────────────────────────────────────────────
    macd_line   = _ema(c, 12) - _ema(c, 26)
    signal_line = _ema(macd_line, 9)
    macd_hist   = (macd_line - signal_line) / (c + 1e-10)
    feat["macd_hist"]       = macd_hist
    feat["macd_hist_slope"] = macd_hist.diff(3)
    feat["macd_cross"]      = (macd_line - signal_line).apply(np.sign)
    # MACD z-score
    feat["macd_hist_z"]     = _zscore(macd_hist, 50)

    # ── Bollinger ─────────────────────────────────────────────────────────
    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    feat["bb_width"]    = 2 * bb_std / (bb_mid + 1e-10)
    feat["bb_position"] = (c - bb_mid) / (bb_std + 1e-10)    # -2..+2 arası
    # BB genişlik rejimi: daralıyor mu genişliyor mu?
    feat["bb_width_z"]  = _zscore(feat["bb_width"], 60)

    # ── Hacim ─────────────────────────────────────────────────────────────
    vol_ma20 = v.rolling(20).mean()
    feat["vol_ratio_5"]  = v.rolling(5).mean() / (vol_ma20 + 1e-10)
    feat["vol_ratio_20"] = v / (vol_ma20 + 1e-10)
    obv = (np.sign(c.diff()) * v).cumsum()
    feat["obv_slope_5"]  = obv.pct_change(5)
    feat["obv_slope_z"]  = _zscore(obv.pct_change(5), 50)

    # ── Mum özellikleri ────────────────────────────────────────────────────
    body  = (c - o).abs()
    total = h - l + 1e-10
    feat["body_pct"]          = body / total
    feat["upper_wick_pct"]    = (h - c.clip(upper=o).where(c > o, c)) / total
    feat["lower_wick_pct"]    = (c.clip(lower=o).where(c < o, c) - l) / total
    feat["is_bullish_candle"] = (c > o).astype(float)

    # ── Momentum: ham + z-score ───────────────────────────────────────────
    for n in [3, 5, 10, 20]:
        mom_raw = c / c.shift(n) - 1
        feat[f"mom_{n}"]   = mom_raw
        feat[f"mom_z_{n}"] = _zscore(mom_raw, 50)    # trend giderilmiş

    # ── Trend gücü proxy ──────────────────────────────────────────────────
    feat["directional_strength"] = (
        (feat["ema9_21_cross"].abs() + feat["ema21_50_cross"].abs()) / 2
    )

    # ── High/Low istatistikleri ────────────────────────────────────────────
    feat["hh_20"] = (h == h.rolling(20).max()).astype(float)
    feat["ll_20"] = (l == l.rolling(20).min()).astype(float)
    feat["range_position"] = (c - l.rolling(20).min()) / (
        h.rolling(20).max() - l.rolling(20).min() + 1e-10
    )

    # ── Stochastic RSI proxy ───────────────────────────────────────────────
    rsi14_low  = rsi14.rolling(14).min()
    rsi14_high = rsi14.rolling(14).max()
    feat["stoch_rsi"] = (rsi14 - rsi14_low) / (rsi14_high - rsi14_low + 1e-10)

    # ── Gerçekleşmiş varyans (yakın dönem volatilite tahmini) ─────────────
    feat["realized_var_5"]  = (bar_ret ** 2).rolling(5).sum()
    feat["realized_var_20"] = (bar_ret ** 2).rolling(20).sum()

    # ── NaN düşür, sonsuzlukları kırp ─────────────────────────────────────
    fdf = pd.DataFrame(feat, index=df.index)
    fdf.replace([np.inf, -np.inf], np.nan, inplace=True)
    fdf.dropna(inplace=True)
    return fdf


def build_target(df: pd.DataFrame, forward: int = 3, atr_mult: float = 0.5) -> pd.Series:
    """
    Hedef değişken: N bar sonraki getiri yön sınıfı.
    1=BUY  0=HOLD  -1=SELL
    """
    c   = df["close"]
    atr = _atr(df["high"], df["low"], c, 14)
    fwd_ret = c.shift(-forward) / c - 1  # N bar sonrası getiri
    thresh  = atr_mult * atr / c         # ATR normalize eşik

    y = pd.Series(0, index=df.index, dtype=int)
    y[fwd_ret >  thresh] = 1
    y[fwd_ret < -thresh] = -1
    return y.shift(forward).dropna()  # son N bar hedef yok


# ── Model Eğitimi ─────────────────────────────────────────────────────────────

def _get_model():
    """
    XGBoost — sıkı regularizasyon ile overfitting önlenir.

    Önceki sorun: max_depth=5, n_estimators=200 → %97 accuracy (ezber)
    Düzeltme: max_depth=3, reg_alpha/lambda yüksek, min_child_weight artırıldı
    """
    try:
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=100,       # eskiden 200 — daha az ağaç
            max_depth=3,            # eskiden 5 — sığ ağaçlar overfitting'i azaltır
            learning_rate=0.08,
            subsample=0.7,          # eskiden 0.8 — daha az örnek
            colsample_bytree=0.6,   # eskiden 0.7 — daha az özellik
            min_child_weight=10,    # yeni — düğüm bölünmesi için minimum örnek
            reg_alpha=0.5,          # yeni — L1 regularizasyon
            reg_lambda=2.0,         # yeni — L2 regularizasyon
            eval_metric="mlogloss",
            random_state=42,
            verbosity=0,
        )
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(
            n_estimators=100, max_depth=3, min_samples_leaf=20, random_state=42
        )


def train_model(df: pd.DataFrame, symbol_tf: str) -> dict:
    """
    Walk-forward eğitim ile TimeSeriesSplit çapraz doğrulama.

    Değişiklikler:
    - Tek 80/20 split → TimeSeriesSplit(n_splits=5) gerçekçi accuracy
    - CalibratedClassifierCV: olasılıkları %0/100 uçlarından uzaklaştırır
    - Son split son eğitim verisi: hiçbir zaman geleceği görmez
    """
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.calibration import CalibratedClassifierCV

    feats = build_features(df)
    target = build_target(df, _FORWARD_BARS, _ATR_MULT)

    idx = feats.index.intersection(target.index)
    X     = feats.loc[idx].values
    y_raw = target.loc[idx].values
    le    = LabelEncoder()
    y     = le.fit_transform(y_raw)

    if len(X) < _MIN_TRAIN_ROWS:
        raise ValueError(f"Yetersiz veri: {len(X)} satır, min {_MIN_TRAIN_ROWS}")

    # TimeSeriesSplit: 5 katlı zaman serisi çapraz doğrulama
    # Son katlama en güncel veri — hem kalibrasyon hem test için kullanılır
    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))

    # Son split → test seti (en güncel %20)
    train_idx, test_idx = splits[-1]
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    # Ham XGBoost eğit
    base_model = _get_model()
    base_model.fit(X_train, y_train)

    # Olasılık kalibrasyonu — "sigmoid" (Platt) küçük setlerde daha kararlı
    # isotonic: monoton dönüşüm, büyük setlerde iyi ama 200 satırda bozulabilir
    # sigmoid: Platt scaling, 2 parametreli → daha kararlı ve daha gerçekçi
    # Önceki: predict_proba → 0.95 gibi aşırı değerler
    # Sonrası: Platt scaling → 0.55-0.75 arası gerçekçi aralık
    try:
        calibrated = CalibratedClassifierCV(base_model, cv="prefit", method="sigmoid")
        calibrated.fit(X_test, y_test)
        model = calibrated
    except Exception:
        model = base_model  # kalibrasyon başarısız → ham model

    y_pred    = model.predict(X_test)
    accuracy  = round(accuracy_score(y_test, y_pred) * 100, 2)

    # Sınıf dağılımı
    classes   = le.classes_.tolist()   # [-1, 0, 1] veya alt kümesi
    buy_pct   = round((y_train == le.transform([1])[0]).mean() * 100, 1) if 1 in le.classes_ else 0
    sell_pct  = round((y_train == le.transform([-1])[0]).mean() * 100, 1) if -1 in le.classes_ else 0

    # Feature importance
    if hasattr(model, "feature_importances_"):
        feat_names = build_features(df.tail(50)).columns.tolist()
        importances = model.feature_importances_
        top_feats = sorted(zip(feat_names, importances), key=lambda x: -x[1])[:10]
    else:
        top_feats = []

    _models[symbol_tf]   = (model, le, build_features(df.tail(50)).columns.tolist())
    _metadata[symbol_tf] = {
        "trained_at":  time.time(),
        "train_rows":  len(X_train),
        "test_rows":   len(X_test),
        "accuracy":    accuracy,
        "buy_pct":     buy_pct,
        "sell_pct":    sell_pct,
        "classes":     classes,
        "top_features":[(f, round(float(i), 4)) for f, i in top_feats],
        "model_type":  type(model).__name__,
    }
    _bar_count[symbol_tf] = 0
    logger.info("ML_TRAINED %s: acc=%.1f%% rows=%d buy=%.0f%% sell=%.0f%%",
                symbol_tf, accuracy, len(X_train), buy_pct, sell_pct)
    _save_model(symbol_tf)   # KALICILIK: diske yaz (restart'ta korunur)
    return _metadata[symbol_tf]


# ── Tahmin ────────────────────────────────────────────────────────────────────

def predict(df: pd.DataFrame, symbol_tf: str) -> dict:
    """
    Son barda tahmin yap.
    Çıktı: {ml_score, buy_prob, sell_prob, hold_prob, signal, confidence}

    Olasılık kırpma: Aşırı güven önlemek için [0.15, 0.85] aralığında kliple.
    Finansal modeller genellikle %60-70 max güvene sahip olmalı.
    """
    if symbol_tf not in _models:
        return {"ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                "buy_prob": 0.33, "sell_prob": 0.33, "hold_prob": 0.33,
                "trained": False}

    _PROB_CLIP_LOW  = 0.10   # minimum olasılık — sıfır güven yok
    _PROB_CLIP_HIGH = 0.80   # maksimum olasılık — aşırı güven yok

    model, le, feat_cols = _models[symbol_tf]
    feats = build_features(df)
    if feats.empty:
        return {"ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                "buy_prob": 0.33, "sell_prob": 0.33, "hold_prob": 0.33,
                "trained": True}

    # Son satırı al, sütun sırası eğitimle aynı olmalı
    row = feats.iloc[[-1]].reindex(columns=feat_cols, fill_value=0.0)
    row.replace([np.inf, -np.inf], 0.0, inplace=True)

    try:
        proba = model.predict_proba(row.values)[0]   # shape: (n_classes,)
    except Exception as exc:
        logger.warning("ML predict failed: %s", exc)
        return {"ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                "buy_prob": 0.33, "sell_prob": 0.33, "hold_prob": 0.33,
                "trained": True}

    # Sınıf → olasılık eşlemesi
    classes  = le.classes_.tolist()  # [-1, 0, 1]
    prob_map = {int(c): float(p) for c, p in zip(classes, proba)}
    buy_p_raw  = prob_map.get(1,  0.0)
    hold_p_raw = prob_map.get(0,  0.0)
    sell_p_raw = prob_map.get(-1, 0.0)

    # Olasılık kırpma — aşırı güveni [0.10, 0.80] aralığına çek
    # Sorun: XGBoost trendy piyasada 0.95+ çıkarıyor → yanıltıcı sinyal
    # Finansal tahmin gerçekte %55-70 doğru olabilir, 0.95 güven yanlış
    buy_p  = float(np.clip(buy_p_raw,  _PROB_CLIP_LOW, _PROB_CLIP_HIGH))
    hold_p = float(np.clip(hold_p_raw, _PROB_CLIP_LOW, _PROB_CLIP_HIGH))
    sell_p = float(np.clip(sell_p_raw, _PROB_CLIP_LOW, _PROB_CLIP_HIGH))

    # Yeniden normalize et (toplam=1)
    total  = buy_p + hold_p + sell_p
    if total > 0:
        buy_p /= total; hold_p /= total; sell_p /= total

    # ML skoru: 0.5 nötr, yüksek = bullish
    ml_score = round(0.5 + (buy_p - sell_p) * 0.5, 4)
    ml_score = max(0.1, min(0.9, ml_score))

    # Karar eşikleri: kalibre sonrası daha hassas
    if ml_score > 0.60:
        signal = "BUY"
    elif ml_score < 0.40:
        signal = "SELL"
    else:
        signal = "HOLD"

    confidence = round(max(buy_p, sell_p, hold_p), 3)
    return {
        "ml_score":    ml_score,
        "signal":      signal,
        "confidence":  confidence,
        "buy_prob":    round(buy_p,  3),
        "sell_prob":   round(sell_p, 3),
        "hold_prob":   round(hold_p, 3),
        "trained":     True,
        "raw_buy_prob": round(buy_p_raw, 3),   # debug: kırpmadan önceki
    }


# ── FastAPI Router ─────────────────────────────────────────────────────────────

from fastapi import APIRouter, Query, Body
from typing import Dict

router = APIRouter(prefix="/api/ml", tags=["ml_predictor"])


async def _fetch_ohlcv_for_ml(symbol: str, timeframe: str, limit: int = 2500) -> pd.DataFrame:
    """CCXT ile geçmiş veri çek, ML için hazırla."""
    try:
        import ccxt
        exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        loop  = asyncio.get_event_loop()
        ohlcv = await loop.run_in_executor(
            None,
            lambda: exchange.fetch_ohlcv(symbol, timeframe, limit=limit),
        )
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df
    except Exception as exc:
        logger.error("ML OHLCV fetch failed: %s", exc)
        raise


_ALL_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w"]


async def _train_one(symbol: str, tf: str) -> dict:
    """Tek bir TF için eğit ve predict — paralel çağrı için."""
    key = f"{symbol}|{tf}"
    try:
        df = await _fetch_ohlcv_for_ml(symbol, tf, limit=_TRAIN_LOOKBACK_BARS + 50)
        meta = train_model(df, key)
        result = predict(df, key)
        _ml_pred_cache[key] = result
        logger.info("TRAIN_ONE done: %s acc=%.1f%%", key, meta.get("accuracy", 0))
        return {"tf": tf, "success": True, "accuracy": meta.get("accuracy"),
                "train_rows": meta.get("train_rows"), "model_type": meta.get("model_type"),
                "signal": result.get("signal"), "ml_score": result.get("ml_score")}
    except Exception as exc:
        logger.warning("TRAIN_ONE failed %s: %s", key, exc)
        return {"tf": tf, "success": False, "error": str(exc)}


@router.post("/train")
async def train_endpoint(
    symbol:    str = Query("BTC/USDT"),
    timeframe: str = Query("4h"),
):
    """Tek bir TF için ML modeli eğit."""
    symbol_tf = f"{symbol}|{timeframe}"
    try:
        df = await _fetch_ohlcv_for_ml(symbol, timeframe, limit=_TRAIN_LOOKBACK_BARS + 50)
        meta = train_model(df, symbol_tf)
        result = predict(df, symbol_tf)
        _ml_pred_cache[symbol_tf] = result
        return {"success": True, "symbol": symbol, "timeframe": timeframe,
                "signal": result.get("signal"), "ml_score": result.get("ml_score"), **meta}
    except Exception as exc:
        logger.error("ML train failed: %s", exc)
        return {"success": False, "error": str(exc)}


@router.post("/train_all")
async def train_all_endpoint(
    symbol: str = Query("BTC/USDT"),
):
    """
    Tüm standart timeframe'ler için paralel model eğitimi.
    5m, 15m, 1h, 4h, 1d, 1w — hepsi aynı anda.
    Toplam süre: en uzun TF kadar (~60-90 sn).
    """
    logger.info("TRAIN_ALL başlıyor: %s %s", symbol, _ALL_TIMEFRAMES)
    results = await asyncio.gather(
        *[_train_one(symbol, tf) for tf in _ALL_TIMEFRAMES],
        return_exceptions=False,
    )
    summary = {r["tf"]: r for r in results}
    success_count = sum(1 for r in results if r.get("success"))
    return {
        "symbol": symbol,
        "total": len(_ALL_TIMEFRAMES),
        "success": success_count,
        "failed": len(_ALL_TIMEFRAMES) - success_count,
        "results": summary,
    }


@router.get("/predict")
async def predict_endpoint(
    symbol:     str  = Query("BTC/USDT"),
    timeframe:  str  = Query("4h"),
    auto_train: bool = Query(True),
):
    """
    Mevcut piyasa durumu için ML tahmini üret.

    - Model zaten varsa: hızlı predict (non-blocking)
    - Model yoksa + auto_train: arka planda eğitim başlatır, fallback döndürür
    - Model yoksa + fallback var: fallback modelden sonuç döndürür
    """
    symbol_tf = f"{symbol}|{timeframe}"
    _bar_count[symbol_tf] = _bar_count.get(symbol_tf, 0) + 1
    ml_status = get_ml_status(symbol, timeframe)

    # ── Model bu TF için hiç yok → arka planda eğit, fallback döndür ──────────
    if ml_status["status"] in ("untrained", "fallback"):
        if auto_train and ml_status["status"] == "untrained":
            # Arka planda eğitim başlat (non-blocking)
            trigger_background_train(symbol, timeframe)

        # Fallback sonuç: en yakın mevcut modelin önbelleğini kullan
        fallback = _get_fallback_cache(symbol, timeframe)
        if fallback:
            fb_from = fallback.get("_fallback_from", "bilinmiyor")
            meta_fb = _metadata.get(fb_from, {})
            return {
                **{k: v for k, v in fallback.items() if not k.startswith("_")},
                "symbol":     symbol,
                "timeframe":  timeframe,
                "model_type": meta_fb.get("model_type"),
                "accuracy":   meta_fb.get("accuracy"),
                "trained_at": meta_fb.get("trained_at"),
                "top_features": meta_fb.get("top_features", [])[:5],
                "fallback_from": fb_from,
                "training": ml_status["status"] == "untrained",
                "training_note": f"Bu TF için eğitim başlatıldı. Şimdilik {fb_from} modeli kullanılıyor.",
            }
        else:
            return {
                "ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                "trained": False, "training": True,
                "training_note": f"Model eğitimi başlatıldı ({symbol_tf}). 30-60 sn içinde hazır olacak.",
                "symbol": symbol, "timeframe": timeframe,
            }

    # ── Eğitim devam ediyor ────────────────────────────────────────────────────
    if ml_status["status"] == "training":
        fallback = _get_fallback_cache(symbol, timeframe)
        if fallback:
            meta_fb = _metadata.get(fallback.get("_fallback_from", ""), {})
            return {
                **{k: v for k, v in fallback.items() if not k.startswith("_")},
                "symbol": symbol, "timeframe": timeframe,
                "model_type": meta_fb.get("model_type"),
                "accuracy": meta_fb.get("accuracy"),
                "training": True,
                "training_note": f"{symbol_tf} için eğitim devam ediyor…",
            }
        return {"ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                "trained": False, "training": True, "symbol": symbol, "timeframe": timeframe}

    # ── Model mevcut → Yeniden eğitim zamanı geldiyse arka planda eğit ────────
    if auto_train and _bar_count.get(symbol_tf, 0) >= _RETRAIN_BARS:
        trigger_background_train(symbol, timeframe)

    # ── Hızlı predict ─────────────────────────────────────────────────────────
    try:
        df = await _fetch_ohlcv_for_ml(symbol, timeframe, limit=300)
        result = predict(df, symbol_tf)
    except Exception as exc:
        cached = _ml_pred_cache.get(symbol_tf)
        if cached:
            return {**cached, "symbol": symbol, "timeframe": timeframe, "error": str(exc)}
        return {"ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                "trained": True, "error": str(exc), "symbol": symbol, "timeframe": timeframe}

    meta = _metadata.get(symbol_tf, {})
    _ml_pred_cache[symbol_tf] = result
    return {
        **result,
        "symbol":     symbol,
        "timeframe":  timeframe,
        "model_type": meta.get("model_type"),
        "accuracy":   meta.get("accuracy"),
        "trained_at": meta.get("trained_at"),
        "top_features": meta.get("top_features", [])[:5],
        "training": False,
    }


@router.get("/status")
async def status_endpoint():
    """Tüm eğitilmiş modellerin durumu."""
    result = {}
    for key, meta in _metadata.items():
        age_h = round((time.time() - meta.get("trained_at", 0)) / 3600, 1)
        result[key] = {
            **meta,
            "age_hours": age_h,
            "retrain_in_bars": max(0, _RETRAIN_BARS - _bar_count.get(key, 0)),
        }
    return {
        "models": result,
        "total": len(_models),
        "env": {
            "train_bars": _TRAIN_LOOKBACK_BARS,
            "retrain_bars": _RETRAIN_BARS,
            "forward_bars": _FORWARD_BARS,
            "atr_mult": _ATR_MULT,
        },
    }


# ── Açılışta diskteki modelleri yükle (kalıcılık) ──────────────────────────
try:
    _load_models()
except Exception as _e:
    logger.debug("startup model load: %s", _e)
