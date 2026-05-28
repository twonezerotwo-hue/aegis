"""
Touche AI Limited — Faz 7: Makro Filtre (AEGIS Bridge)

Fundamental AI modülünden gelen makro skoru teknik analize entegre eder.

Kural Seti:
  - Fundamental skoru < 30  → Makro ortam çok kötü → HOLD zorla (passed=False)
  - Fundamental skoru 30-50 → Zayıf makro → EQS'yi düşür, güveni azalt
  - Fundamental skoru 50-70 → Nötr makro → Değişiklik yok
  - Fundamental skoru > 70  → Güçlü makro → EQS'ye bonus, güveni artır

AegisBridge üzerinden skor alınamazsa (timeout/hata), makro filtre devre dışı kalır.
"""
from .base import BasePhase, PhaseContext, PhaseResult
import structlog

logger = structlog.get_logger(__name__)


class MacroFilterPhase(BasePhase):
    """
    Faz 7: Fundamental AI Makro Filtresi.

    Eğer fundamental_score ctx'te None ise (bridge erişilemedi),
    faz nötr skora geçer ve pipeline'ı bloklamaz.
    """

    PHASE_ID = 7
    PHASE_NAME = "MacroFilter"

    async def run(self, ctx: PhaseContext) -> PhaseResult:
        try:
            return self._analyze(ctx)
        except Exception as e:
            logger.error("phase7_error", error=str(e))
            return self._neutral_result(f"Faz7 hatası: {e}")

    def _analyze(self, ctx: PhaseContext) -> PhaseResult:
        cfg = ctx.config.get("phases", {}).get("phase7_macro", {})
        block_threshold = cfg.get("fundamental_block_threshold", 30.0)
        boost_threshold = cfg.get("fundamental_boost_threshold", 70.0)

        fundamental_score = ctx.fundamental_score

        # ── Skor Alınamadı → Nötr, pass et ───────────────────────────────────
        if fundamental_score is None:
            logger.warning("phase7_no_fundamental_score", symbol=ctx.symbol)
            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=50.0,
                signal="NEUTRAL",
                passed=True,
                reason="Fundamental skor alınamadı (bridge bağlantısı yok), makro filtre atlandı",
                metadata={"fundamental_score": None},
            )

        fs = float(fundamental_score)

        # ── Kritik Makro Engel → HOLD ─────────────────────────────────────────
        if fs < block_threshold:
            logger.warning("phase7_macro_block", symbol=ctx.symbol, fundamental_score=fs)
            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=0.0,
                signal="NEUTRAL",
                passed=False,   # ← Pipeline'ı HOLD'a iter
                reason=f"Makro filtre devrede: Fundamental skor={fs:.1f} < {block_threshold} eşiği",
                metadata={"fundamental_score": fs, "threshold": block_threshold},
            )

        # ── Zayıf Makro → Düşük skor ─────────────────────────────────────────
        if fs < 50.0:
            score = 40.0 + (fs - block_threshold) / (50.0 - block_threshold) * 10.0
            signal = "NEUTRAL"
            reason = f"Zayıf makro ortam (fundamental={fs:.1f}): İhtiyatlı devam"

        # ── Nötr Makro ────────────────────────────────────────────────────────
        elif fs <= boost_threshold:
            score = 50.0
            signal = "NEUTRAL"
            reason = f"Nötr makro ortam (fundamental={fs:.1f}): Teknik analiz belirleyici"

        # ── Güçlü Makro → Bonus ───────────────────────────────────────────────
        else:
            score = 70.0 + (fs - boost_threshold) / (100.0 - boost_threshold) * 30.0
            score = min(100.0, score)
            signal = "BULLISH"
            reason = f"Güçlü makro destek (fundamental={fs:.1f}): EQS boost aktif"

        logger.info("phase7_result", symbol=ctx.symbol, fundamental=fs,
                    signal=signal, score=round(score, 2))
        return PhaseResult(
            phase_id=self.PHASE_ID,
            phase_name=self.PHASE_NAME,
            score=round(score, 2),
            signal=signal,
            passed=True,
            reason=reason,
            metadata={"fundamental_score": fs},
        )
