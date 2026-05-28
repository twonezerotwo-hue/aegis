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
        """Birikim/Dağıtım teyidi yap"""
        try:
            df = ctx.df
            vol_ratio = 0.0
            obv_slope = 0.0
            
            # Hacim oranı
            if "volume_ratio" not in df.columns:
                logger.warning("volume_ratio_missing")
                vol_ratio = 0.0
            else:
                vol_ratio = float(df["volume_ratio"][-1])
            
            # OBV trendi
            obv_trend = "NEUTRAL"
            if "obv_ema_slope" in df.columns:
                obv_slope = float(df["obv_ema_slope"][-1])
                if obv_slope > 0:
                    obv_trend = "BULLISH"
                elif obv_slope < 0:
                    obv_trend = "BEARISH"
            
            # Hacim teyidi
            volume_confirmation = vol_ratio > 1.2 if vol_ratio else False
            
            # OBV teyidi
            obv_confirmation = obv_trend != "NEUTRAL"
            
            # Kombine teyit
            is_accumulating = volume_confirmation and obv_trend == "BULLISH"
            is_distributing = volume_confirmation and obv_trend == "BEARISH"
            
            # Skor hesaplama
            if is_accumulating:
                score = 80.0
                signal = "BULLISH"
                reason = "Birikim teyit edildi (yüksek hacim + OBV yükselişi)"
            elif is_distributing:
                score = 80.0
                signal = "BEARISH"
                reason = "Dağıtım teyit edildi (yüksek hacim + OBV düşüşü)"
            elif volume_confirmation:
                score = 60.0
                signal = "NEUTRAL"
                reason = "Hacim teyidi var, OBV trendi nötr"
            else:
                score = 40.0
                signal = "NEUTRAL"
                reason = "Teyit yok"
            
            # Metadata - always include vol_ratio
            metadata = {
                "vol_ratio": float(vol_ratio) if vol_ratio else None,
                "volume_confirmation": volume_confirmation,
                "obv_slope": round(obv_slope, 4),
                "obv_trend": obv_trend,
                "obv_confirmation": obv_confirmation,
                "is_accumulating": is_accumulating,
                "is_distributing": is_distributing,
                "atr": round(ctx.atr, 4),
            }
            
            logger.info("phase4_result", symbol=ctx.symbol, signal=signal, score=score)
            
            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=score,
                signal=signal,
                passed=True,
                reason=reason,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error("phase4_error", error=str(e))
            return self._neutral_result(f"Faz4 hatası: {str(e)}", metadata={
                "vol_ratio": None,
                "obv_trend": "NEUTRAL",
                "atr": round(ctx.atr, 4),
            })
