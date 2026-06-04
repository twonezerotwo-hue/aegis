"""
AEGIS Geçmiş Makro + Fundamental Veri — backtest için GERÇEK tarihli veri.

Proxy yerine gerçek tarihsel değerler:
  • Sentinel  ← VIX, DXY, US10Y (yfinance, gerçek, tarihli)
  • Fundamental ← Fear & Greed Index geçmişi (alternative.me, 2018'den)

Her backtest barının TARİHİNE göre o günkü gerçek makro/F&G değeri eşlenir.
Hafta sonu/boşluklar forward-fill. Tüm seri 1 kez çekilir, önbelleğe alınır.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Önbellek: (start_date, end_date) → DataFrame
_MACRO_CACHE: dict[str, pd.DataFrame] = {}
_FNG_CACHE: dict[str, pd.Series] = {}
_CACHE_TS: dict[str, float] = {}
_TTL = 6 * 3600  # 6 saat


def _yf_series(ticker: str, start: str, end: str) -> Optional[pd.Series]:
    """yfinance'ten günlük kapanış serisi (tarih index'li)."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
        if hist.empty:
            return None
        s = hist["Close"].copy()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        return s
    except Exception as exc:
        logger.warning("yfinance %s başarısız: %s", ticker, exc)
        return None


def get_macro_history(start: str, end: str) -> pd.DataFrame:
    """
    Gerçek tarihsel makro: VIX, DXY, US10Y günlük.
    Çıktı: tarih-index'li DataFrame [vix, dxy, us10y], forward-fill.
    """
    key = f"{start}|{end}"
    now = time.time()
    if key in _MACRO_CACHE and (now - _CACHE_TS.get("macro_" + key, 0)) < _TTL:
        return _MACRO_CACHE[key]

    vix = _yf_series("^VIX", start, end)
    dxy = _yf_series("DX-Y.NYB", start, end)
    us10y = _yf_series("^TNX", start, end)   # 10Y yield ×10 (örn 45 = %4.5)

    # Ortak tarih indeksi
    idx = None
    for s in (vix, dxy, us10y):
        if s is not None:
            idx = s.index if idx is None else idx.union(s.index)
    if idx is None:
        return pd.DataFrame(columns=["vix", "dxy", "us10y"])

    df = pd.DataFrame(index=idx.sort_values())
    df["vix"] = vix.reindex(df.index).ffill() if vix is not None else 18.0
    df["dxy"] = dxy.reindex(df.index).ffill() if dxy is not None else 100.0
    df["us10y"] = (us10y.reindex(df.index).ffill() / 10.0) if us10y is not None else 4.0
    df = df.ffill().bfill()

    _MACRO_CACHE[key] = df
    _CACHE_TS["macro_" + key] = now
    logger.info("Geçmiş makro çekildi: %d gün (%s–%s)", len(df), start, end)
    return df


def get_fng_history(start: str, end: str) -> pd.Series:
    """
    Gerçek tarihsel Fear & Greed Index (alternative.me).
    Çıktı: tarih-index'li Series (0-100). 2018'den itibaren mevcut.
    """
    key = f"{start}|{end}"
    now = time.time()
    if key in _FNG_CACHE and (now - _CACHE_TS.get("fng_" + key, 0)) < _TTL:
        return _FNG_CACHE[key]
    try:
        import httpx
        # limit=0 → tüm geçmiş
        days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 30
        r = httpx.get(f"https://api.alternative.me/fng/?limit={max(days, 60)}&format=json", timeout=15)
        data = r.json().get("data", [])
        rows = []
        for d in data:
            ts = datetime.fromtimestamp(int(d["timestamp"]), tz=timezone.utc).date()
            rows.append((pd.Timestamp(ts), int(d["value"])))
        if not rows:
            return pd.Series(dtype=float)
        s = pd.Series({ts: v for ts, v in rows}).sort_index()
        _FNG_CACHE[key] = s
        _CACHE_TS["fng_" + key] = now
        logger.info("Geçmiş F&G çekildi: %d gün", len(s))
        return s
    except Exception as exc:
        logger.warning("F&G geçmişi başarısız: %s", exc)
        return pd.Series(dtype=float)


def _map_to_dates(timestamps: pd.Series, source: pd.Series | pd.DataFrame):
    """Backtest timestamp'lerini tarihsel seriye eşle (asof/forward-fill)."""
    dates = pd.to_datetime(timestamps).dt.tz_localize(None).dt.normalize()
    if isinstance(source, pd.DataFrame):
        out = source.reindex(source.index.union(dates)).ffill().reindex(dates)
        return out.reset_index(drop=True)
    out = source.reindex(source.index.union(dates)).ffill().reindex(dates)
    return out.reset_index(drop=True)


def compute_real_sentinel(timestamps: pd.Series, start: str, end: str) -> Optional[pd.Series]:
    """
    GERÇEK Sentinel skoru: tarihsel VIX/DXY/US10Y'den.
    Düşük VIX + zayıf DXY = risk-on (yüksek skor). Yüksek VIX = risk-off (düşük).
    """
    macro = get_macro_history(start, end)
    if macro.empty:
        return None
    m = _map_to_dates(timestamps, macro)
    vix = m["vix"].fillna(18.0)
    dxy = m["dxy"].fillna(100.0)
    # VIX: 12=sakin(1.0) 40=panik(0.0)
    vix_score = (1.0 - ((vix - 12) / 28).clip(0, 1))
    # DXY: 90=zayıf dolar/risk-on(1.0) 110=güçlü/risk-off(0.0)
    dxy_score = (1.0 - ((dxy - 90) / 20).clip(0, 1))
    sentinel = (vix_score * 0.65 + dxy_score * 0.35).clip(0.05, 0.95)
    return sentinel.reset_index(drop=True)


_CUR_CACHE = {"data": None, "ts": 0.0}

def get_current_macro() -> dict:
    """Anlık gerçek makro (yfinance VIX/DXY/US10Y) — 10dk önbellekli."""
    now = time.time()
    if _CUR_CACHE["data"] and (now - _CUR_CACHE["ts"]) < 600:
        return _CUR_CACHE["data"]
    out = {"vix": None, "dxy": None, "us10y": None}
    try:
        from datetime import timedelta
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
        for tic, key in [("^VIX", "vix"), ("DX-Y.NYB", "dxy"), ("^TNX", "us10y")]:
            s = _yf_series(tic, start, end)
            if s is not None and len(s):
                v = float(s.iloc[-1])
                out[key] = v / 10.0 if key == "us10y" and v > 20 else v
    except Exception as exc:
        logger.debug("current macro failed: %s", exc)
    _CUR_CACHE["data"] = out; _CUR_CACHE["ts"] = now
    return out


def compute_current_sentinel() -> Optional[float]:
    """Anlık GERÇEK Sentinel skoru (yfinance VIX/DXY). Düşük VIX/DXY = risk-on."""
    m = get_current_macro()
    vix, dxy = m.get("vix"), m.get("dxy")
    if vix is None and dxy is None:
        return None
    vix = vix if vix is not None else 18.0
    dxy = dxy if dxy is not None else 100.0
    vix_score = 1.0 - min(max((vix - 12) / 28, 0), 1)
    dxy_score = 1.0 - min(max((dxy - 90) / 20, 0), 1)
    return round(min(max(vix_score * 0.65 + dxy_score * 0.35, 0.05), 0.95), 4)


def compute_real_fundamental(timestamps: pd.Series, start: str, end: str) -> Optional[pd.Series]:
    """
    GERÇEK Fundamental skoru: tarihsel Fear & Greed'den (kontrarian).
    Aşırı korku (F&G düşük) = al fırsatı (yüksek skor). Açgözlülük = sat.
    """
    fng = get_fng_history(start, end)
    if fng.empty:
        return None
    f = _map_to_dates(timestamps, fng).fillna(50.0)
    # F&G 0 (aşırı korku) → 0.85, F&G 100 (açgözlülük) → 0.15
    fund = (0.85 - (f / 100.0) * 0.70).clip(0.05, 0.95)
    return fund.reset_index(drop=True)
