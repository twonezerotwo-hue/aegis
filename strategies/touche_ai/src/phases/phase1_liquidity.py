"""
Touche AI Limited — Faz 1: Likidite Süpürmesi (Liquidity Sweep Detection)

Smart Money Concept: Kurumsal oyuncular retail stop emirlerini tetiklemek için
fiyatı kısa süreliğine bir seviyenin ötesine taşır ve geri döner.

Tespit Mantığı:
- Son N bardaki swing high/low seviyeleri tespit edilir
- Güncel bar bu seviyelerin ötesine wick atar ve kapanışta geri döner
- Wick boyu ATR'ın belirli katından büyük olmalı
- Sonuç: Güçlü ters yönde bir hamle için zemin hazır
"""
from .base import BasePhase, PhaseContext, PhaseResult
import structlog

logger = structlog.get_logger(__name__)


class LiquiditySweepPhase(BasePhase):
    """
    Faz 1: Likidite Süpürme Tespiti

    Skor Mantığı:
    - Sweep tespit edildi + güçlü kapanış  → 75-100
    - Sweep tespit edildi + zayıf kapanış  → 50-74
    - Sweep tespit edilmedi                → 0-49
    """

    PHASE_ID = 1
    PHASE_NAME = "LiquiditySweep"

    async def run(self, ctx: PhaseContext) -> PhaseResult:
        try:
            return self._analyze(ctx)
        except Exception as e:
            logger.error("phase1_error", error=str(e))
            return self._neutral_result(f"Faz1 hatası: {e}")

    def _analyze(self, ctx: PhaseContext) -> PhaseResult:
        df = ctx.df
        cfg = ctx.config.get("phases", {}).get("phase1_liquidity", {})
        atr = ctx.atr
        lookback = cfg.get("lookback_bars", 20)
        sweep_atr_mult = cfg.get("sweep_atr_threshold", 0.5)
        wick_body_ratio = cfg.get("min_wick_body_ratio", 0.6)

        if atr <= 0 or len(df) < lookback + 2:
            return self._neutral_result("Yetersiz veri veya ATR=0")

        # Son bar değerleri
        o = float(df["open"][-1])
        h = float(df["high"][-1])
        l = float(df["low"][-1])
        c = float(df["close"][-1])

        body_size = abs(c - o)
        total_range = h - l
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l

        if total_range < 1e-10:
            return self._neutral_result("Sıfır aralıklı bar")

        # Önceki N bar içindeki swing seviyeleri
        lookback_df = df[-(lookback + 1):-1]
        if "swing_high_price" not in df.columns or "swing_low_price" not in df.columns:
            return self._neutral_result("swing_high_price / swing_low_price sütunu eksik")

        prev_swing_highs = lookback_df["swing_high_price"].drop_nulls().to_list()
        prev_swing_lows = lookback_df["swing_low_price"].drop_nulls().to_list()

        # ── Yukarı Likidite Süpürmesi (Bearish Setup) ───────────────────────
        # Wick, bir swing high'ı aştı, kapanış aşağıda → bearish
        bullish_sweep_hit = any(h > sh for sh in prev_swing_highs)
        upper_wick_ok = upper_wick >= sweep_atr_mult * atr
        upper_wick_dominant = (upper_wick / (total_range + 1e-10)) >= wick_body_ratio
        bearish_close = c < max(o, prev_swing_highs[-1] if prev_swing_highs else h)

        bearish_sweep = (
            bullish_sweep_hit
            and upper_wick_ok
            and upper_wick_dominant
            and c < o  # Kapanış açılışın altında
        )

        # ── Aşağı Likidite Süpürmesi (Bullish Setup) ────────────────────────
        # Wick, bir swing low'u aştı, kapanış yukarıda → bullish
        bearish_sweep_hit = any(l < sl for sl in prev_swing_lows)
        lower_wick_ok = lower_wick >= sweep_atr_mult * atr
        lower_wick_dominant = (lower_wick / (total_range + 1e-10)) >= wick_body_ratio

        bullish_sweep = (
            bearish_sweep_hit
            and lower_wick_ok
            and lower_wick_dominant
            and c > o  # Kapanış açılışın üstünde
        )

        # ── Skor ve Sinyal Belirleme ─────────────────────────────────────────
        metadata = {
            "upper_wick": round(upper_wick, 4),
            "lower_wick": round(lower_wick, 4),
            "atr": round(atr, 4),
            "prev_swing_highs": [round(x, 4) for x in prev_swing_highs[-3:]],
            "prev_swing_lows": [round(x, 4) for x in prev_swing_lows[-3:]],
        }

        if bullish_sweep:
            # Kapanışın dip wicke göre ne kadar güçlü döndüğünü ölç
            close_recovery = (c - l) / (total_range + 1e-10)
            score = min(100.0, 60.0 + close_recovery * 40.0)
            logger.info("phase1_bullish_sweep", symbol=ctx.symbol, score=score)
            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=score,
                signal="BULLISH",
                passed=True,
                reason=f"Aşağı likidite süpürmesi: lower_wick={lower_wick:.4f}, ATR={atr:.4f}",
                metadata=metadata,
            )

        if bearish_sweep:
            close_rejection = (h - c) / (total_range + 1e-10)
            score = min(100.0, 60.0 + close_rejection * 40.0)
            logger.info("phase1_bearish_sweep", symbol=ctx.symbol, score=score)
            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=score,
                signal="BEARISH",
                passed=True,
                reason=f"Yukarı likidite süpürmesi: upper_wick={upper_wick:.4f}, ATR={atr:.4f}",
                metadata=metadata,
            )

        # Süpürme yok — düşük skor, pipeline devam eder ama zayıf
        logger.info("phase1_no_sweep", symbol=ctx.symbol)
        return PhaseResult(
            phase_id=self.PHASE_ID,
            phase_name=self.PHASE_NAME,
            score=20.0,
            signal="NEUTRAL",
            passed=True,   # Bloke etmez ama EQS'yi düşürür
            reason="Anlamlı likidite süpürmesi tespit edilmedi",
            metadata=metadata,
        )
