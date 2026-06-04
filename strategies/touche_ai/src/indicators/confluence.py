"""
AEGIS Touche — Dünya Çapında Teknik Konfluens Motoru.

18+ profesyonel gösterge tek bir konviksiyon-ağırlıklı skora indirgenir.
Kurumsal TA mantığı: çok sayıda BAĞIMSIZ gösterge aynı yönü gösterince
güven artar; AŞIRI okumalar (RSI<20, %B<0) yüksek-konviksiyon dönüş sinyalidir.

Her gösterge [-1, +1] arası oy verir (ayı→boğa) + bir ağırlık.
Aşırı durumlar ağırlığı 2x'e çıkarır (en güçlü TA sinyalleri uçlardadır).

Çıktı:
  eqs            : 0-100 (50 nötr, yön + güç yansıtır)
  signal         : STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL
  conviction     : 0-100 (göstergeler ne kadar hizalı)
  bias           : -1..+1 net yön
  confluences    : aktif sinyallerin listesi (şeffaflık)
  extremes       : aşırı okumalar (yüksek öncelik)
  indicators     : tüm ham değerler
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ── Düşük seviye gösterge yardımcıları ─────────────────────────────────────────
def _ema(s, n):  return s.ewm(span=n, adjust=False).mean()
def _sma(s, n):  return s.rolling(n).mean()

def _rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + g / (l + 1e-10))

def _atr(h, l, c, n=14):
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def _stoch(h, l, c, n=14, k=3):
    ll, hh = l.rolling(n).min(), h.rolling(n).max()
    raw = 100 * (c - ll) / (hh - ll + 1e-10)
    return raw.rolling(k).mean()

def _cci(h, l, c, n=20):
    tp = (h + l + c) / 3
    sma = tp.rolling(n).mean()
    md = (tp - sma).abs().rolling(n).mean()
    return (tp - sma) / (0.015 * md + 1e-10)

def _williams(h, l, c, n=14):
    hh, ll = h.rolling(n).max(), l.rolling(n).min()
    return -100 * (hh - c) / (hh - ll + 1e-10)

def _adx(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = _atr(h, l, c, n)
    pdi = 100 * pd.Series(plus, index=h.index).ewm(alpha=1/n, adjust=False).mean() / (atr + 1e-10)
    mdi = 100 * pd.Series(minus, index=h.index).ewm(alpha=1/n, adjust=False).mean() / (atr + 1e-10)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-10)
    return dx.ewm(alpha=1/n, adjust=False).mean(), pdi, mdi

def _mfi(h, l, c, v, n=14):
    tp = (h + l + c) / 3
    mf = tp * v
    pos = mf.where(tp > tp.shift(), 0.0).rolling(n).sum()
    neg = mf.where(tp < tp.shift(), 0.0).rolling(n).sum()
    return 100 - 100 / (1 + pos / (neg + 1e-10))

def _obv(c, v):
    return (np.sign(c.diff()).fillna(0) * v).cumsum()

def _aroon(h, l, n=14):
    up = h.rolling(n + 1).apply(lambda x: float(np.argmax(x)) / n * 100, raw=True)
    dn = l.rolling(n + 1).apply(lambda x: float(np.argmin(x)) / n * 100, raw=True)
    return up, dn

def _supertrend(h, l, c, n=10, mult=3.0):
    atr = _atr(h, l, c, n)
    hl2 = (h + l) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    st = pd.Series(index=c.index, dtype=float)
    dir_ = pd.Series(index=c.index, dtype=float)
    for i in range(len(c)):
        if i == 0:
            st.iloc[i] = lower.iloc[i]; dir_.iloc[i] = 1; continue
        if c.iloc[i] > st.iloc[i-1]:
            dir_.iloc[i] = 1
        elif c.iloc[i] < st.iloc[i-1]:
            dir_.iloc[i] = -1
        else:
            dir_.iloc[i] = dir_.iloc[i-1]
        if dir_.iloc[i] == 1:
            st.iloc[i] = max(lower.iloc[i], st.iloc[i-1]) if dir_.iloc[i-1] == 1 else lower.iloc[i]
        else:
            st.iloc[i] = min(upper.iloc[i], st.iloc[i-1]) if dir_.iloc[i-1] == -1 else upper.iloc[i]
    return dir_

def _vwap(h, l, c, v):
    tp = (h + l + c) / 3
    return (tp * v).cumsum() / (v.cumsum() + 1e-10)


# ── Konfluens analizi ───────────────────────────────────────────────────────────
def analyze_confluence(df: pd.DataFrame) -> dict:
    """
    OHLCV DataFrame → kapsamlı çok-gösterge teknik analiz.
    df sütunları: open, high, low, close, volume
    """
    if df is None or len(df) < 50:
        return {"available": False, "reason": "yetersiz veri (<50 bar)"}

    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    last = -1

    votes: list[tuple[str, float, float]] = []   # (isim, oy[-1,1], ağırlık)
    confluences: list[str] = []
    extremes: list[str] = []
    ind: dict = {}

    def vote(name, score, weight=1.0, extreme=False):
        votes.append((name, float(np.clip(score, -1, 1)), float(weight)))
        if abs(score) >= 0.5:
            confluences.append(f"{name}:{'AL' if score > 0 else 'SAT'}")
        if extreme:
            # score>0 = boğa oyu = AŞIRI-SATIM koşulu (oversold → dip al)
            # score<0 = ayı oyu = AŞIRI-ALIM koşulu (overbought → tepe sat)
            extremes.append(f"{name}:{'AŞIRI-SATIM' if score > 0 else 'AŞIRI-ALIM'}")

    # 1) RSI (aşırı uçlarda 2x ağırlık)
    rsi = _rsi(c, 14); rsi_v = float(rsi.iloc[last]); ind["rsi"] = round(rsi_v, 1)
    if rsi_v < 20:   vote("RSI", +1.0, 2.0, extreme=True)
    elif rsi_v > 80: vote("RSI", -1.0, 2.0, extreme=True)
    elif rsi_v < 30: vote("RSI", +0.7, 1.5)
    elif rsi_v > 70: vote("RSI", -0.7, 1.5)
    else:            vote("RSI", (50 - rsi_v) / 50 * 0.5, 1.0)

    # 2) Stochastic
    stoch = _stoch(h, l, c); st_v = float(stoch.iloc[last]); ind["stoch"] = round(st_v, 1)
    if st_v < 20:   vote("Stoch", +0.8, 1.3, extreme=st_v < 10)
    elif st_v > 80: vote("Stoch", -0.8, 1.3, extreme=st_v > 90)
    else:           vote("Stoch", (50 - st_v) / 50 * 0.4, 0.8)

    # 3) StochRSI
    rsi_min, rsi_max = rsi.rolling(14).min(), rsi.rolling(14).max()
    stochrsi = ((rsi - rsi_min) / (rsi_max - rsi_min + 1e-10)).iloc[last]
    srsi_v = float(stochrsi); ind["stoch_rsi"] = round(srsi_v, 2)
    if srsi_v < 0.15:  vote("StochRSI", +0.8, 1.2, extreme=True)
    elif srsi_v > 0.85: vote("StochRSI", -0.8, 1.2, extreme=True)
    else:              vote("StochRSI", (0.5 - srsi_v) * 0.8, 0.7)

    # 4) MACD histogram + eğim
    macd_line = _ema(c, 12) - _ema(c, 26)
    sig_line = _ema(macd_line, 9)
    hist = macd_line - sig_line
    h_now, h_prev = float(hist.iloc[last]), float(hist.iloc[last - 1])
    ind["macd_hist"] = round(h_now / float(c.iloc[last]) * 100, 3)
    macd_score = np.tanh(h_now / (float(c.iloc[last]) * 0.005))
    if h_now > h_prev: macd_score = min(1, macd_score + 0.2)
    else:              macd_score = max(-1, macd_score - 0.2)
    vote("MACD", macd_score, 1.4)

    # 5) CCI
    cci = float(_cci(h, l, c).iloc[last]); ind["cci"] = round(cci, 0)
    if cci < -200:   vote("CCI", +1.0, 1.5, extreme=True)
    elif cci > 200:  vote("CCI", -1.0, 1.5, extreme=True)
    elif cci < -100: vote("CCI", +0.6, 1.0)
    elif cci > 100:  vote("CCI", -0.6, 1.0)
    else:            vote("CCI", -cci / 100 * 0.3, 0.6)

    # 6) Williams %R
    wr = float(_williams(h, l, c).iloc[last]); ind["williams_r"] = round(wr, 1)
    if wr < -90:    vote("Williams%R", +0.9, 1.3, extreme=True)
    elif wr > -10:  vote("Williams%R", -0.9, 1.3, extreme=True)
    elif wr < -80:  vote("Williams%R", +0.6, 1.0)
    elif wr > -20:  vote("Williams%R", -0.6, 1.0)
    else:           vote("Williams%R", (-50 - wr) / 50 * 0.3, 0.6)

    # 7) Bollinger %B
    bb_mid = _sma(c, 20); bb_std = c.rolling(20).std()
    pct_b = float(((c - (bb_mid - 2*bb_std)) / (4*bb_std + 1e-10)).iloc[last])
    ind["bb_pct_b"] = round(pct_b, 2)
    if pct_b < 0:    vote("Bollinger", +0.9, 1.4, extreme=True)
    elif pct_b > 1:  vote("Bollinger", -0.9, 1.4, extreme=True)
    elif pct_b < 0.2: vote("Bollinger", +0.5, 0.9)
    elif pct_b > 0.8: vote("Bollinger", -0.5, 0.9)
    else:            vote("Bollinger", (0.5 - pct_b) * 0.6, 0.6)

    # 8) ADX + DI yön (trend gücü)
    adx, pdi, mdi = _adx(h, l, c)
    adx_v = float(adx.iloc[last]); pdi_v = float(pdi.iloc[last]); mdi_v = float(mdi.iloc[last])
    ind["adx"] = round(adx_v, 1); ind["di_plus"] = round(pdi_v, 1); ind["di_minus"] = round(mdi_v, 1)
    di_dir = 1 if pdi_v > mdi_v else -1
    trend_strength = min(1.0, adx_v / 40)
    vote("ADX/DI", di_dir * trend_strength, 1.5 if adx_v > 25 else 0.7)

    # 9) EMA ribbon hizalanması (9/21/50/200)
    e9, e21, e50, e200 = _ema(c,9).iloc[last], _ema(c,21).iloc[last], _ema(c,50).iloc[last], _ema(c,200).iloc[last]
    cl = float(c.iloc[last])
    ribbon = sum([cl > e9, e9 > e21, e21 > e50, e50 > e200]) - sum([cl < e9, e9 < e21, e21 < e50, e50 < e200])
    ind["ema_ribbon"] = ribbon  # -4..+4
    vote("EMA Ribbon", ribbon / 4, 1.3)

    # 10) MFI (hacim ağırlıklı)
    mfi = float(_mfi(h, l, c, v).iloc[last]); ind["mfi"] = round(mfi, 1)
    if mfi < 20:    vote("MFI", +0.8, 1.2, extreme=mfi < 10)
    elif mfi > 80:  vote("MFI", -0.8, 1.2, extreme=mfi > 90)
    else:           vote("MFI", (50 - mfi) / 50 * 0.4, 0.7)

    # 11) ROC (momentum)
    roc = float((c.iloc[last] / c.iloc[last-10] - 1) * 100) if len(c) > 10 else 0
    ind["roc_10"] = round(roc, 2)
    vote("ROC", np.tanh(roc / 5), 0.8)

    # 12) OBV eğimi (hacim trendi)
    obv = _obv(c, v); obv_slope = float((obv.iloc[last] - obv.iloc[last-5]) / (abs(obv.iloc[last-5]) + 1e-6)) if len(obv) > 5 else 0
    ind["obv_slope"] = round(obv_slope, 3)
    vote("OBV", np.tanh(obv_slope * 3), 0.8)

    # 13) Aroon
    ar_up, ar_dn = _aroon(h, l)
    aru, ard = float(ar_up.iloc[last]), float(ar_dn.iloc[last])
    ind["aroon_up"] = round(aru, 0); ind["aroon_down"] = round(ard, 0)
    vote("Aroon", (aru - ard) / 100, 0.9)

    # 14) Supertrend
    try:
        st_dir = float(_supertrend(h, l, c).iloc[last])
        ind["supertrend"] = "yukarı" if st_dir > 0 else "aşağı"
        vote("Supertrend", st_dir, 1.3)
    except Exception:
        pass

    # 15) VWAP konumu
    vwap = _vwap(h, l, c, v); vwap_v = float(vwap.iloc[last])
    ind["vwap_dist_pct"] = round((cl - vwap_v) / vwap_v * 100, 2)
    vote("VWAP", np.tanh((cl - vwap_v) / vwap_v / 0.02), 0.9)

    # 16) Ichimoku (tenkan/kijun + bulut)
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2)
    span_b = (h.rolling(52).max() + l.rolling(52).min()) / 2
    tk, kj = float(tenkan.iloc[last]), float(kijun.iloc[last])
    cloud_top = max(float(span_a.iloc[last]), float(span_b.iloc[last]))
    cloud_bot = min(float(span_a.iloc[last]), float(span_b.iloc[last]))
    ichi = 0.0
    if cl > cloud_top: ichi += 0.5
    elif cl < cloud_bot: ichi -= 0.5
    ichi += 0.5 if tk > kj else -0.5
    ind["ichimoku"] = "boğa" if ichi > 0 else "ayı" if ichi < 0 else "nötr"
    vote("Ichimoku", ichi, 1.2)

    # 17) Mum formasyonu (son bar)
    body = abs(cl - float(o.iloc[last])); rng = float(h.iloc[last] - l.iloc[last]) + 1e-10
    upper_wick = float(h.iloc[last]) - max(cl, float(o.iloc[last]))
    lower_wick = min(cl, float(o.iloc[last])) - float(l.iloc[last])
    candle = 0.0
    if lower_wick > body * 2 and upper_wick < body:      candle = +0.6; confluences.append("Çekiç(boğa)")
    elif upper_wick > body * 2 and lower_wick < body:    candle = -0.6; confluences.append("Kayan yıldız(ayı)")
    elif cl > float(o.iloc[last]) and body > rng * 0.7:  candle = +0.4
    elif cl < float(o.iloc[last]) and body > rng * 0.7:  candle = -0.4
    if candle != 0: vote("Mum", candle, 0.7)

    # 18) RSI diverjans (fiyat dip yaparken RSI yükseliyor = boğa)
    if len(c) > 20:
        price_low_now = float(c.iloc[last]) <= float(c.iloc[last-10:last].min())
        price_high_now = float(c.iloc[last]) >= float(c.iloc[last-10:last].max())
        rsi_rising = float(rsi.iloc[last]) > float(rsi.iloc[last-10])
        if price_low_now and rsi_rising:
            vote("Diverjans", +0.8, 1.4); confluences.append("Boğa diverjansı")
        elif price_high_now and not rsi_rising:
            vote("Diverjans", -0.8, 1.4); confluences.append("Ayı diverjansı")

    # ── Agregasyon ─────────────────────────────────────────────────────────────
    tot_w = sum(w for _, _, w in votes)
    net_bias = sum(s * w for _, s, w in votes) / (tot_w + 1e-10)   # -1..+1

    # ── AŞIRI-DÖNÜŞ OVERRIDE (mean-reversion) ─────────────────────────────────
    # Profesyonel TA: çok sayıda osilatör AYNI ANDA aşırı uçtaysa, bu en güçlü
    # dönüş sinyalidir — trend takibini geçersiz kılar. RSI=12 + 4 başka aşırı
    # satım = "trend aşağı olsa bile burası dip" → BUY. Kullanıcının istediği bu.
    ext_oversold   = sum(1 for e in extremes if "AŞIRI-SATIM" in e)  # dönüş YUKARI sinyali
    ext_overbought = sum(1 for e in extremes if "AŞIRI-ALIM" in e)   # dönüş AŞAĞI sinyali
    reversal_note = None
    if ext_oversold >= 2:
        # Aşırı satım kümesi → yukarı dönüş bias'ı (sayıyla orantılı)
        boost = min(0.6, 0.20 + ext_oversold * 0.12)
        net_bias = max(net_bias, -0.05) + boost     # aşağı trendi nötralize et + yukarı it
        reversal_note = f"{ext_oversold} aşırı-satım kümesi → dip dönüş kurulumu"
        confluences.insert(0, f"🔥 AŞIRI-SATIM KÜMESİ ({ext_oversold})")
    elif ext_overbought >= 2:
        boost = min(0.6, 0.20 + ext_overbought * 0.12)
        net_bias = min(net_bias, 0.05) - boost
        reversal_note = f"{ext_overbought} aşırı-alım kümesi → tepe dönüş kurulumu"
        confluences.insert(0, f"🔥 AŞIRI-ALIM KÜMESİ ({ext_overbought})")
    net_bias = float(np.clip(net_bias, -1, 1))

    # Hizalanma: aynı yöndeki oy oranı (konviksiyon)
    bull = sum(w for _, s, w in votes if s > 0.15)
    bear = sum(w for _, s, w in votes if s < -0.15)
    aligned = max(bull, bear)
    extreme_cluster = max(ext_oversold, ext_overbought)
    conviction = round(min(100, (aligned / (tot_w + 1e-10)) * 100 * (1 + 0.15 * extreme_cluster)), 1)

    # EQS: 50 nötr, net_bias × konviksiyon yönlendirir
    eqs = 50 + net_bias * (0.45 + 0.55 * conviction / 100) * 50
    eqs = round(float(np.clip(eqs, 2, 98)), 2)

    # Sinyal — aşırı kümeler düşük eşikle bile tetiklenir
    has_extreme = extreme_cluster >= 1
    strong_extreme = extreme_cluster >= 2
    if net_bias > 0.40 or (net_bias > 0.20 and strong_extreme):
        signal = "STRONG_BUY"
    elif net_bias > 0.15 or (net_bias > 0.08 and has_extreme):
        signal = "BUY"
    elif net_bias < -0.40 or (net_bias < -0.20 and strong_extreme):
        signal = "STRONG_SELL"
    elif net_bias < -0.15 or (net_bias < -0.08 and has_extreme):
        signal = "SELL"
    else:
        signal = "HOLD"

    result = {
        "available": True,
        "eqs": eqs,
        "signal": signal,
        "bias": round(net_bias, 4),
        "conviction": conviction,
        "vote_count": len(votes),
        "bull_weight": round(bull, 2),
        "bear_weight": round(bear, 2),
        "confluences": confluences[:12],
        "extremes": extremes,
        "reversal_note": reversal_note,
        "indicators": ind,
    }
    return _to_native(result)


def _to_native(obj):
    """numpy tiplerini JSON-uyumlu native Python tiplerine çevir (recursive)."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(x) for x in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return round(float(obj), 4)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        return round(obj, 4)
    return obj
