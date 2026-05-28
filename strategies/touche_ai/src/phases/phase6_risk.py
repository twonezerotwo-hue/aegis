"""
Touche AI Limited — Faz 6: Risk Yönetimi (SL/TP + Position Sizing)

ATR tabanlı Stop Loss, R:R oranı tabanlı Take Profit ve
risk bütçesine göre pozisyon büyüklüğü hesaplar.

Bu faz bir filtredir: R:R min eşiğin altındaysa pipeline HOLD'a zorlar.
"""
from typing import Optional

from .base import BasePhase, PhaseContext, PhaseResult
import structlog

logger = structlog.get_logger(__name__)


class RiskManagementPhase(BasePhase):
    """
    Faz 6: Risk Yönetimi — SL, TP, Pozisyon Büyüklüğü.

    passed=False → R:R kabul edilemez → Orchestrator HOLD döner.
    """

    PHASE_ID = 6
    PHASE_NAME = "RiskManagement"

    async def run(self, ctx: PhaseContext) -> PhaseResult:
        try:
            return self._analyze(ctx)
        except Exception as e:
            logger.error("phase6_error", error=str(e))
            return self._neutral_result(f"Faz6 hatası: {e}")

    def _analyze(self, ctx: PhaseContext) -> PhaseResult:
        df = ctx.df
        cfg = ctx.config.get("phases", {}).get("phase6_risk", {})
        atr = ctx.atr
        sl_mult = cfg.get("sl_atr_multiplier", 1.5)
        min_rr = cfg.get("min_rr_ratio", 1.5)
        max_rr = cfg.get("max_rr_ratio", 10.0)
        tp_rr = cfg.get("tp_rr_ratio", 2.0)

        if atr <= 0:
            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=0.0,
                signal="NEUTRAL",
                passed=False,
                reason="ATR=0: Risk hesaplanamıyor",
            )

        current_price = float(df["close"][-1])
        direction = ctx.direction_hint  # Önceki fazlardan gelen yön ipucu

        # ── SL/TP Hesabı ──────────────────────────────────────────────────────
        sl_distance = atr * sl_mult

        if direction == "BULLISH":
            stop_loss = current_price - sl_distance
            # Swing low varsa SL'yi oraya çek (daha gerçekçi)
            sl_prices = df["swing_low_price"].drop_nulls().to_list()
            if sl_prices:
                swing_sl = sl_prices[-1] - atr * 0.3  # Swing low'un biraz altı
                if swing_sl < current_price:
                    stop_loss = max(stop_loss, swing_sl)  # En yakın güvenli SL
            take_profit = current_price + sl_distance * tp_rr

        elif direction == "BEARISH":
            stop_loss = current_price + sl_distance
            sh_prices = df["swing_high_price"].drop_nulls().to_list()
            if sh_prices:
                swing_sl = sh_prices[-1] + atr * 0.3
                if swing_sl > current_price:
                    stop_loss = min(stop_loss, swing_sl)
            take_profit = current_price - sl_distance * tp_rr

        else:
            # Yön belirsiz — risk hesabı yapılamaz
            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=30.0,
                signal="NEUTRAL",
                passed=False,
                reason="Yön belirsiz (NEUTRAL): Risk hesabı yapılamıyor",
                metadata={"atr": round(atr, 4)},
            )

        actual_sl_dist = abs(current_price - stop_loss)
        actual_tp_dist = abs(take_profit - current_price)
        rr_ratio = actual_tp_dist / (actual_sl_dist + 1e-10)

        # ── R:R Filtresi ──────────────────────────────────────────────────────
        rr_acceptable = min_rr <= rr_ratio <= max_rr

        if not rr_acceptable:
            logger.warning("phase6_rr_rejected", symbol=ctx.symbol,
                           rr=round(rr_ratio, 2), min_rr=min_rr)
            return PhaseResult(
                phase_id=self.PHASE_ID,
                phase_name=self.PHASE_NAME,
                score=10.0,
                signal=direction,
                passed=False,
                reason=f"R:R kabul edilemez: {rr_ratio:.2f} (min={min_rr})",
                metadata={
                    "stop_loss": round(stop_loss, 4),
                    "take_profit": round(take_profit, 4),
                    "rr_ratio": round(rr_ratio, 2),
                    "atr": round(atr, 4),
                },
            )

        # ── Pozisyon Büyüklüğü (Fixed Risk) ──────────────────────────────────
        # Hesap büyüklüğünü context'ten alamıyoruz → None döner, Orchestrator doldurur
        position_size: Optional[float] = None

        # R:R ne kadar iyi? 2.0 ideal, üstü bonus
        score = min(100.0, 50.0 + (rr_ratio - min_rr) * 15.0)

        logger.info("phase6_result", symbol=ctx.symbol, rr=round(rr_ratio, 2),
                    sl=round(stop_loss, 4), tp=round(take_profit, 4))
        return PhaseResult(
            phase_id=self.PHASE_ID,
            phase_name=self.PHASE_NAME,
            score=round(score, 2),
            signal=direction,
            passed=True,
            reason=f"R:R={rr_ratio:.2f} kabul edildi (min={min_rr})",
            metadata={
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "sl_distance": round(actual_sl_dist, 4),
                "tp_distance": round(actual_tp_dist, 4),
                "rr_ratio": round(rr_ratio, 2),
                "atr": round(atr, 4),
                "position_size": position_size,
            },
        )
