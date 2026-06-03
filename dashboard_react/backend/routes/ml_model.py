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
_ATR_MULT            = float(os.environ.get("ML_ATR_MULT", "0.5"))    # BUY/SELL eşiği
_MIN_TRAIN_ROWS      = 200

# ── State ─────────────────────────────────────────────────────────────────────
_models:    dict[str, object]     = {}   # key: symbol_timeframe
_metadata:  dict[str, dict]       = {}   # eğitim meta
_bar_count: dict[str, int]        = {}   # son eğitimden bu yana bar sayısı
_ohlcv_cache: dict[str, pd.DataFrame] = {}


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

    # ── Getiriler ─────────────────────────────────────────────────────────
    for n in [1, 2, 3, 5, 10, 20]:
        feat[f"ret_{n}"] = c.pct_change(n)

    # ── Volatilite ────────────────────────────────────────────────────────
    for n in [5, 10, 20]:
        feat[f"vol_{n}"]   = c.pct_change().rolling(n).std()
    feat["atr_14"]  = _atr(h, l, c, 14)
    feat["atr_norm"] = feat["atr_14"] / c  # ATR / fiyat (normalize)

    # ── Trend: EMA ────────────────────────────────────────────────────────
    for n in [9, 21, 50, 100, 200]:
        em = _ema(c, n)
        feat[f"ema{n}_slope"] = em.pct_change(3)
        feat[f"price_ema{n}"] = (c / em - 1)
    feat["ema9_21_cross"]  = (_ema(c, 9) - _ema(c, 21)) / c
    feat["ema21_50_cross"] = (_ema(c, 21) - _ema(c, 50)) / c
    feat["ema50_200_cross"]= (_ema(c, 50) - _ema(c, 200)) / c

    # ── RSI ───────────────────────────────────────────────────────────────
    feat["rsi_7"]  = _rsi(c, 7)
    feat["rsi_14"] = _rsi(c, 14)
    feat["rsi_21"] = _rsi(c, 21)
    feat["rsi_slope_3"] = feat["rsi_14"].diff(3)

    # ── MACD ──────────────────────────────────────────────────────────────
    macd_line   = _ema(c, 12) - _ema(c, 26)
    signal_line = _ema(macd_line, 9)
    feat["macd_hist"]      = (macd_line - signal_line) / c
    feat["macd_hist_slope"]= feat["macd_hist"].diff(3)
    feat["macd_cross"]     = (macd_line - signal_line).apply(np.sign)

    # ── Bollinger ─────────────────────────────────────────────────────────
    bb_mid   = c.rolling(20).mean()
    bb_std   = c.rolling(20).std()
    feat["bb_width"]   = 2 * bb_std / (bb_mid + 1e-10)
    feat["bb_position"]= (c - bb_mid) / (bb_std + 1e-10)

    # ── Hacim ─────────────────────────────────────────────────────────────
    vol_ma20 = v.rolling(20).mean()
    feat["vol_ratio_5"]  = v.rolling(5).mean() / (vol_ma20 + 1e-10)
    feat["vol_ratio_20"] = v / (vol_ma20 + 1e-10)
    # OBV slope
    obv = (np.sign(c.diff()) * v).cumsum()
    feat["obv_slope_5"] = obv.pct_change(5)

    # ── Mum özellikleri ────────────────────────────────────────────────────
    body     = (c - o).abs()
    total    = h - l + 1e-10
    feat["body_pct"]         = body / total
    feat["upper_wick_pct"]   = (h - c.clip(upper=o).where(c > o, c)) / total
    feat["lower_wick_pct"]   = (c.clip(lower=o).where(c < o, c) - l) / total
    feat["is_bullish_candle"]= (c > o).astype(float)

    # ── Momentum ──────────────────────────────────────────────────────────
    for n in [3, 5, 10, 20]:
        feat[f"mom_{n}"] = c / c.shift(n) - 1

    # ── ADX basit proxy ────────────────────────────────────────────────────
    # Gerçek ADX yerine trending/ranging sinyali
    feat["directional_strength"] = (
        (feat["ema9_21_cross"].abs() + feat["ema21_50_cross"].abs()) / 2
    )

    # ── High/Low istatistikleri ────────────────────────────────────────────
    feat["hh_20"] = (h == h.rolling(20).max()).astype(float)
    feat["ll_20"] = (l == l.rolling(20).min()).astype(float)
    feat["range_position"] = (c - l.rolling(20).min()) / (
        h.rolling(20).max() - l.rolling(20).min() + 1e-10
    )

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
    """XGBoost varsa kullan, yoksa GradientBoosting fallback."""
    try:
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.7,
            eval_metric="mlogloss",
            use_label_encoder=False,
            random_state=42,
            verbosity=0,
        )
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)


def train_model(df: pd.DataFrame, symbol_tf: str) -> dict:
    """
    Walk-forward eğitim:
    - İlk %80 train, son %20 test
    - Özellikleri ve hedefi hizala
    - Model + metadata sakla
    """
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import accuracy_score

    feats = build_features(df)
    target = build_target(df, _FORWARD_BARS, _ATR_MULT)

    # Ortak index
    idx = feats.index.intersection(target.index)
    X   = feats.loc[idx].values
    y_raw = target.loc[idx].values
    # -1,0,1 → 0,1,2
    le = LabelEncoder()
    y  = le.fit_transform(y_raw)

    if len(X) < _MIN_TRAIN_ROWS:
        raise ValueError(f"Yetersiz veri: {len(X)} satır, min {_MIN_TRAIN_ROWS}")

    split = int(len(X) * 0.80)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    model = _get_model()
    model.fit(X_train, y_train)

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
    return _metadata[symbol_tf]


# ── Tahmin ────────────────────────────────────────────────────────────────────

def predict(df: pd.DataFrame, symbol_tf: str) -> dict:
    """
    Son barda tahmin yap.
    Çıktı: {ml_score, buy_prob, sell_prob, hold_prob, signal, confidence}
    """
    if symbol_tf not in _models:
        return {"ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                "buy_prob": 0.33, "sell_prob": 0.33, "hold_prob": 0.33,
                "trained": False}

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
    buy_p    = prob_map.get(1,  0.0)
    hold_p   = prob_map.get(0,  0.0)
    sell_p   = prob_map.get(-1, 0.0)

    # ML skoru: 0.5 nötr, yüksek = bullish
    ml_score = round(0.5 + (buy_p - sell_p) * 0.5, 4)
    ml_score = max(0.05, min(0.95, ml_score))

    if ml_score > 0.62:
        signal = "BUY"
    elif ml_score < 0.38:
        signal = "SELL"
    else:
        signal = "HOLD"

    confidence = round(max(buy_p, sell_p, hold_p), 3)
    return {
        "ml_score":   ml_score,
        "signal":     signal,
        "confidence": confidence,
        "buy_prob":   round(buy_p,  3),
        "sell_prob":  round(sell_p, 3),
        "hold_prob":  round(hold_p, 3),
        "trained":    True,
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


@router.post("/train")
async def train_endpoint(
    symbol:    str = Query("BTC/USDT"),
    timeframe: str = Query("4h"),
):
    """
    ML modelini (yeniden) eğit.
    Binance'ten geçmiş 2500 bar çeker, XGBoost sınıflandırıcı eğitir.
    """
    symbol_tf = f"{symbol}|{timeframe}"
    try:
        df = await _fetch_ohlcv_for_ml(symbol, timeframe, limit=_TRAIN_LOOKBACK_BARS + 50)
        meta = train_model(df, symbol_tf)
        return {"success": True, "symbol": symbol, "timeframe": timeframe, **meta}
    except Exception as exc:
        logger.error("ML train failed: %s", exc)
        return {"success": False, "error": str(exc)}


@router.get("/predict")
async def predict_endpoint(
    symbol:    str = Query("BTC/USDT"),
    timeframe: str = Query("4h"),
    auto_train: bool = Query(True),
):
    """
    Mevcut piyasa durumu için ML tahmini üret.
    Model yoksa otomatik eğitir (auto_train=True).
    """
    symbol_tf = f"{symbol}|{timeframe}"
    _bar_count[symbol_tf] = _bar_count.get(symbol_tf, 0) + 1

    # Auto-train veya yeniden eğitim zamanı geldiyse
    needs_train = (
        symbol_tf not in _models or
        (auto_train and _bar_count.get(symbol_tf, 0) >= _RETRAIN_BARS)
    )
    if needs_train:
        try:
            df = await _fetch_ohlcv_for_ml(symbol, timeframe, limit=_TRAIN_LOOKBACK_BARS + 50)
            train_model(df, symbol_tf)
            # Son 200 bar predict için
            result = predict(df, symbol_tf)
        except Exception as exc:
            logger.error("ML auto-train failed: %s", exc)
            return {"ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                    "trained": False, "error": str(exc)}
    else:
        try:
            df = await _fetch_ohlcv_for_ml(symbol, timeframe, limit=300)
            result = predict(df, symbol_tf)
        except Exception as exc:
            return {"ml_score": 0.5, "signal": "NEUTRAL", "confidence": 0.0,
                    "trained": symbol_tf in _models, "error": str(exc)}

    meta = _metadata.get(symbol_tf, {})
    return {
        **result,
        "symbol":    symbol,
        "timeframe": timeframe,
        "model_type":  meta.get("model_type"),
        "accuracy":    meta.get("accuracy"),
        "trained_at":  meta.get("trained_at"),
        "top_features": meta.get("top_features", [])[:5],
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
