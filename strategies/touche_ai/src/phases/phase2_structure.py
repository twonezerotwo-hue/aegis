"""
Touche AI Limited — Faz 2: Piyasa Yapısı + Diverjans

Piyasa Yapısı:
  - HH (Higher High) + HL (Higher Low) → Bullish yapı
  - LH (Lower High)  + LL (Lower Low)  → Bearish yapı
  - Kırılım (Break of Structure) yapı değişimini sinyaller

Diverjans Tespiti:
  - Bullish Regular Divergence : Fiyat LL yaparken RSI/MACD HL yapıyor
  - Bearish Regular Divergence : Fiyat HH yaparken RSI/MACD LH yapıyor
  - Hidden divergence daha güçlü trend teyididir (opsiyonel)
"""
from typing import List, Tuple

from .base import BasePhase, PhaseContext, PhaseResult
import structlog

logger = structlog.get_logger(__name__)


class MarketStructurePhase(BasePhase):
    """Faz 2: Piyasa Yapısı + Diverjans Analizi"""

    PHASE_ID = 2
    PHASE_NAME = "MarketStructure"

    async def run(self, ctx: PhaseContext) -> PhaseResult:
        try:
            return self._analyze(ctx)
        except Exception as e:
            logger.error("phase2_error", error=str(e))
            return self._neutral_result(f"Faz2 hatası: {e}")

    def _analyze(self, ctx: PhaseContext) -> PhaseResult:
        df = ctx.df
        cfg = ctx.config.get("phases", {}).get("phase2_structure", {})
        min_swings = cfg.get("min_swing_points", 2)

        # Swing noktalarını çek
        sh_prices = self._last_n_non_null(df, "swing_high_price", 6)
        sl_prices = self._last_n_non_null(df, "swing_low_price", 6)

        if len(sh_prices) < min_swings or len(sl_prices) < min_swings:
            return self._neutral_result(
                f"Yetersiz swing noktası: highs={len(sh_prices)}, lows={len(sl_prices)}"
            )

        # ── Yapı Analizi ──────────────────────────────────────────────────────
        structure_signal, structure_score = self._determine_structure(sh_prices, sl_prices)

        # ── Diverjans Analizi ─────────────────────────────────────────────────
        divergence_signal, divergence_score = self._detect_divergence(df, sl_prices, sh_prices)

        # ── Birleşik Değerlendirme ────────────────────────────────────────────
        # Yapı + Diverjans aynı yöndeyse güçlü sinyal
        if structure_signal == divergence_signal and structure_signal != "NEUTRAL":
            final_score = min(100.0, (structure_score * 0.6 + divergence_score * 0.4) * 1.2)
            final_signal = structure_signal
            reason = f"Yapı ({structure_signal}) + Diverjans teyidi"
        elif structure_signal != "NEUTRAL":
            final_score = structure_score * 0.7
            final_signal = structure_signal
            reason = f"Yapı ({structure_signal}), diverjans yok"
        elif divergence_signal != "NEUTRAL":
            final_score = divergence_score * 0.5
            final_signal = divergence_signal
            reason = f"Sadece diverjans ({divergence_signal}), yapı nötr"
        else:
            final_score = 30.0
            final_signal = "NEUTRAL"
            reason = "Belirgin yapı veya diverjans yok"

        metadata = {
            "structure_signal": structure_signal,
            "structure_score": round(structure_score, 2),
            "divergence_signal": divergence_signal,
            "divergence_score": round(divergence_score, 2),
            "swing_highs": [round(x, 4) for x in sh_prices[-3:]],
            "swing_lows": [round(x, 4) for x in sl_prices[-3:]],
        }

        logger.info("phase2_result", symbol=ctx.symbol, signal=final_signal, score=round(final_score, 2))
        return PhaseResult(
            phase_id=self.PHASE_ID,
            phase_name=self.PHASE_NAME,
            score=round(final_score, 2),
            signal=final_signal,
            passed=True,
            reason=reason,
            metadata=metadata,
        )

    def _determine_structure(
        self, sh_prices: List[float], sl_prices: List[float]
    ) -> Tuple[str, float]:
        """HH/HL veya LH/LL yapısını belirler."""
        # Son iki swing high karşılaştırması
        hh = sh_prices[-1] > sh_prices[-2] if len(sh_prices) >= 2 else None
        hl = sl_prices[-1] > sl_prices[-2] if len(sl_prices) >= 2 else None
        lh = sh_prices[-1] < sh_prices[-2] if len(sh_prices) >= 2 else None
        ll = sl_prices[-1] < sl_prices[-2] if len(sl_prices) >= 2 else None

        if hh and hl:
            # Trend ne kadar güçlü? Artış yüzdesiyle ölç
            strength = abs(sh_prices[-1] - sh_prices[-2]) / (sh_prices[-2] + 1e-10) * 100
            score = min(90.0, 60.0 + strength * 10.0)
            return "BULLISH", score

        if lh and ll:
            strength = abs(sl_prices[-2] - sl_prices[-1]) / (sl_prices[-2] + 1e-10) * 100
            score = min(90.0, 60.0 + strength * 10.0)
            return "BEARISH", score

        return "NEUTRAL", 40.0

    def _detect_divergence(
        self, df, sl_prices: List[float], sh_prices: List[float]
    ) -> Tuple[str, float]:
        """RSI ve MACD Histogram üzerinde Regular Divergence tespiti."""
        rsi_col = "rsi_14"
        macd_col = "macd_hist"

        if rsi_col not in df.columns:
            return "NEUTRAL", 40.0

        rsi_vals = self._last_n_non_null(df, rsi_col, 20)
        if len(rsi_vals) < 4:
            return "NEUTRAL", 40.0

        # Bullish Regular Divergence:
        # Fiyat LL (sl_prices[-1] < sl_prices[-2]) ama RSI HL yapıyor
        if len(sl_prices) >= 2 and sl_prices[-1] < sl_prices[-2]:
            # RSI'nın ilgili dip noktaları
            rsi_recent = rsi_vals[-1]
            rsi_prev = min(rsi_vals[-10:-1]) if len(rsi_vals) > 10 else rsi_vals[-2]
            if rsi_recent > rsi_prev:
                score = 70.0 + (rsi_recent - rsi_prev) * 0.5
                return "BULLISH", min(90.0, score)

        # Bearish Regular Divergence:
        # Fiyat HH (sh_prices[-1] > sh_prices[-2]) ama RSI LH yapıyor
        if len(sh_prices) >= 2 and sh_prices[-1] > sh_prices[-2]:
            rsi_recent = rsi_vals[-1]
            rsi_prev = max(rsi_vals[-10:-1]) if len(rsi_vals) > 10 else rsi_vals[-2]
            if rsi_recent < rsi_prev:
                score = 70.0 + (rsi_prev - rsi_recent) * 0.5
                return "BEARISH", min(90.0, score)

        return "NEUTRAL", 40.0
