"""
Touche AI Limited — Faz 5: Giriş Zamanlaması (Entry Timing)

Mum Formasyonu Tespiti:
  Bullish: Hammer, Bullish Engulfing, Bullish Pin Bar, Morning Star (basit)
  Bearish: Shooting Star, Bearish Engulfing, Bearish Pin Bar, Evening Star (basit)

Teyit koşulu: Hacim ortalamanın üstündeyse +bonus
StochRSI giriş yönünü destekliyorsa +bonus
"""
from .base import BasePhase, PhaseContext, PhaseResult
import structlog

logger = structlog.get_logger(__name__)


class EntryTimingPhase(BasePhase):
    """Faz 5: Mum Formasyonu Tabanlı Giriş Zamanlaması"""

    PHASE_ID = 5
    PHASE_NAME = "EntryTiming"

    async def run(self, ctx: PhaseContext) -> PhaseResult:
        try:
            return self._analyze(ctx)
        except Exception as e:
            logger.error("phase5_error", error=str(e))
            return self._neutral_result(f"Faz5 hatası: {e}")

    def _analyze(self, ctx: PhaseContext) -> PhaseResult:
        df = ctx.df
        cfg = ctx.config.get("phases", {}).get("phase5_timing", {})
        engulf_ratio = cfg.get("engulfing_ratio", 1.2)
        pin_ratio = cfg.get("pin_bar_wick_ratio", 0.65)
        doji_ratio = cfg.get("doji_body_ratio", 0.1)

        if len(df) < 3:
            return self._neutral_result("Mum analizi için yetersiz bar")

        # Get last 2 bars
        o  = float(df["open"][-1])
        h  = float(df["high"][-1])
        l  = float(df["low"][-1])
        c  = float(df["close"][-1])
        
        po = float(df["open"][-2])
        ph = float(df["high"][-2])
        pl = float(df["low"][-2])
        pc = float(df["close"][-2])

        body = abs(c - o)
        total = h - l
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        prev_body = abs(pc - po)

        if total < 1e-10:
            return self._neutral_result("Geçersiz bar (sıfır aralık)")

        pattern = None
        base_score = 0.0
        signal = "NEUTRAL"

        # ── Bullish Formasyonlar ───────────────────────────────────────────────

        # 1. Hammer / Bullish Pin Bar
        if (
            lower_wick / (total + 1e-10) >= pin_ratio
            and body / (total + 1e-10) <= (1 - pin_ratio)
            and c > o  # Bullish kapanış
        ):
            pattern = "Hammer/BullishPinBar"
            base_score = 70.0
            signal = "BULLISH"

        # 2. Bullish Engulfing
        elif (
            c > o                   # Mevcut bar bullish
            and pc < po             # Önceki bar bearish
            and c > po              # Kapanış önceki açılışı geçiyor
            and o < pc              # Açılış önceki kapanışın altında
            and body >= prev_body * engulf_ratio
        ):
            pattern = "BullishEngulfing"
            base_score = 80.0
            signal = "BULLISH"

        # ── Bearish Formasyonlar ───────────────────────────────────────────────

        # 3. Shooting Star / Bearish Pin Bar
        elif (
            upper_wick / (total + 1e-10) >= pin_ratio
            and body / (total + 1e-10) <= (1 - pin_ratio)
            and c < o  # Bearish kapanış
        ):
            pattern = "ShootingStar/BearishPinBar"
            base_score = 70.0
            signal = "BEARISH"

        # 4. Bearish Engulfing
        elif (
            c < o                   # Mevcut bar bearish
            and pc > po             # Önceki bar bullish
            and c < po              # Kapanış önceki açılışın altında
            and o > pc              # Açılış önceki kapanışın üstünde
            and body >= prev_body * engulf_ratio
        ):
            pattern = "BearishEngulfing"
            base_score = 80.0
            signal = "BEARISH"

        # 5. Doji — nötr / belirsizlik (pipelines'ı yavaşlatır ama bloke etmez)
        elif body / (total + 1e-10) <= doji_ratio:
            pattern = "Doji"
            base_score = 35.0
            signal = "NEUTRAL"

        if pattern is None:
            # Standart formasyon yok
            base_score = 30.0
            reason = "Bilinen formasyon tespit edilmedi"
        else:
            reason = f"Formasyon: {pattern}"

        # ── Teyit Bonusları ───────────────────────────────────────────────────
        bonus = 0.0
        vol_ratio = 0.0

        # Hacim teyidi
        if "vol_ratio" in df.columns:
            vol_ratio = self._safe_float(df["vol_ratio"])
            if vol_ratio >= 1.5:
                bonus += 10.0
                reason += f" | Yüksek hacim({vol_ratio:.2f}x)"

        # StochRSI teyidi
        if "stochrsi_k" in df.columns and "stochrsi_d" in df.columns:
            k = self._safe_float(df["stochrsi_k"])
            d = self._safe_float(df["stochrsi_d"])
            if signal == "BULLISH" and k < 25 and k > d:
                bonus += 10.0
                reason += f" | StochRSI oversold+cross({k:.1f})"
            elif signal == "BEARISH" and k > 75 and k < d:
                bonus += 10.0
                reason += f" | StochRSI overbought+cross({k:.1f})"

        final_score = min(100.0, base_score + bonus)

        metadata = {
            "pattern": pattern,
            "body_size": round(body, 4),
            "upper_wick": round(upper_wick, 4),
            "lower_wick": round(lower_wick, 4),
            "total_range": round(total, 4),
            "bonus": round(bonus, 2),
            "vol_ratio": round(vol_ratio, 4),
            "atr": round(ctx.atr, 4),
        }

        logger.info("phase5_result", symbol=ctx.symbol, pattern=pattern,
                    signal=signal, score=round(final_score, 2))
        return PhaseResult(
            phase_id=self.PHASE_ID,
            phase_name=self.PHASE_NAME,
            score=round(final_score, 2),
            signal=signal,
            passed=True,
            reason=reason,
            metadata=metadata,
        )
