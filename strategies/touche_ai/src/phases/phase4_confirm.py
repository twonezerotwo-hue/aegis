"""
Touche AI Limited — Faz 4: Birikim/Dağıtım Teyidi (Accumulation/Distribution)

Akıllı Para bölgeye girince hacim deseni değişir:
  - Talep Bölgesinde Birikim: Yüksek hacimli alım + OBV yükselişi → Bullish teyit
  - Arz Bölgesinde Dağıtım:  Yüksek hacimli satış + OBV düşüşü   → Bearish teyit

OBV ve Hacim Oranı birlikte değerlendirilir.
"""

import structlog

from .base import BasePhase, PhaseContext, PhaseResult

logger = structlog.get_logger(__name__)


class AccumDistPhase(BasePhase):
    """Birikim/Dağıtım teyit fazı"""
    
    PHASE_ID = 4
    PHASE_NAME = "AccumDist"

    async def run(self, ctx: PhaseContext) -> PhaseResult:
        """Birikim/Dağıtım teyidi — OBV slope + CMF (Chaikin Money Flow)"""
        try:
            df = ctx.df

            # ── Hacim Oranı ───────────────────────────────────────────────────
            vol_ratio = float(df["volume_ratio"][-1]) if "volume_ratio" in df.columns else 0.0
            volume_confirmation = vol_ratio > 1.2

            # ── OBV Trendi ────────────────────────────────────────────────────
            obv_trend = "NEUTRAL"
            obv_slope = 0.0
            if "obv_ema" in df.columns and len(df) >= 5:
                obv_vals = df["obv_ema"].drop_nulls().to_list()
                if len(obv_vals) >= 5:
                    # Son 5 barlık OBV EMA eğimi
                    obv_slope = (obv_vals[-1] - obv_vals[-5]) / (abs(obv_vals[-5]) + 1e-10)
                    if obv_slope > 0.002:
                        obv_trend = "BULLISH"
                    elif obv_slope < -0.002:
                        obv_trend = "BEARISH"

            # ── CMF (Chaikin Money Flow) ───────────────────────────────────────
            # CMF > +0.1 = alım baskısı, < -0.1 = satış baskısı
            # OBV slope'tan daha güvenilir — hacim boyutunu ve kapanış pozisyonunu birleştirir
            cmf_col = "cmf_20"
            cmf_val  = 0.0
            cmf_signal = "NEUTRAL"
            if cmf_col in df.columns:
                cmf_val = float(df[cmf_col][-1]) if df[cmf_col][-1] is not None else 0.0
                if cmf_val > 0.10:
                    cmf_signal = "BULLISH"
                elif cmf_val < -0.10:
                    cmf_signal = "BEARISH"
            elif all(c in df.columns for c in ["high", "low", "close", "volume"]):
                # Inline CMF hesapla (gösterge sütunu yoksa)
                h = df["high"].to_list()
                l = df["low"].to_list()
                c = df["close"].to_list()
                v = df["volume"].to_list()
                period = 20
                end = len(h)
                start = max(0, end - period)
                sum_mfv = sum(
                    (((c[i] - l[i]) - (h[i] - c[i])) / (h[i] - l[i] + 1e-10)) * v[i]
                    for i in range(start, end)
                )
                sum_vol = sum(v[start:end]) + 1e-10
                cmf_val = sum_mfv / sum_vol
                if cmf_val > 0.10:
                    cmf_signal = "BULLISH"
                elif cmf_val < -0.10:
                    cmf_signal = "BEARISH"

            # ── Kombine Değerlendirme ─────────────────────────────────────────
            # OBV + CMF birleşik oyu
            bullish_votes = sum([
                obv_trend == "BULLISH",
                cmf_signal == "BULLISH",
                volume_confirmation,
            ])
            bearish_votes = sum([
                obv_trend == "BEARISH",
                cmf_signal == "BEARISH",
                volume_confirmation and obv_trend == "BEARISH",
            ])

            if bullish_votes >= 2 and obv_trend == "BULLISH" and cmf_signal == "BULLISH":
                score = 85.0 + min(10.0, abs(cmf_val) * 30)
                signal = "BULLISH"
                reason = f"Güçlü birikim: OBV↑ + CMF={cmf_val:+.3f}(BULLISH) + hacim teyidi"
            elif bullish_votes >= 2:
                score = 75.0
                signal = "BULLISH"
                reason = f"Birikim teyidi: OBV={obv_trend}, CMF={cmf_val:+.3f}"
            elif bearish_votes >= 2 and obv_trend == "BEARISH" and cmf_signal == "BEARISH":
                score = 85.0 + min(10.0, abs(cmf_val) * 30)
                signal = "BEARISH"
                reason = f"Güçlü dağıtım: OBV↓ + CMF={cmf_val:+.3f}(BEARISH) + hacim teyidi"
            elif bearish_votes >= 2:
                score = 75.0
                signal = "BEARISH"
                reason = f"Dağıtım teyidi: OBV={obv_trend}, CMF={cmf_val:+.3f}"
            elif volume_confirmation:
                score = 60.0
                signal = "NEUTRAL"
                reason = f"Yüksek hacim ama yön belirsiz (CMF={cmf_val:+.3f})"
            else:
                score = 40.0
                signal = "NEUTRAL"
                reason = "Teyit yok"

            metadata = {
                "vol_ratio":   round(vol_ratio, 4),
                "obv_slope":   round(obv_slope, 6),
                "obv_trend":   obv_trend,
                "cmf_value":   round(cmf_val, 4),
                "cmf_signal":  cmf_signal,
                "bullish_votes": bullish_votes,
                "bearish_votes": bearish_votes,
                "volume_confirmation": volume_confirmation,
                "atr":         round(ctx.atr, 4),
            }

            logger.info("phase4_result", symbol=ctx.symbol, signal=signal,
                        score=score, cmf=round(cmf_val, 4), obv=obv_trend)

            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=round(score, 2),
                signal=signal,
                passed=True,
                reason=reason,
                metadata=metadata,
            )

        except Exception as e:
            logger.error("phase4_error", error=str(e))
            return self._neutral_result(f"Faz4 hatası: {str(e)}", metadata={
                "vol_ratio": None,
                "obv_trend": "NEUTRAL",
                "cmf_value": None,
                "atr": round(ctx.atr, 4),
            })
