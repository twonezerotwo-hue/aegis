"""
Touche AI Limited — Faz 3: Arz/Talep Bölgeleri + Confluence

Supply/Demand Zone Tespiti:
  - Talep Bölgesi (Demand Zone): Güçlü yükselişin başladığı son aşağı mum(lar)
  - Arz Bölgesi (Supply Zone): Güçlü düşüşün başladığı son yukarı mum(lar)

Confluence (Çakışma) Sayımı:
  - Fiyat bölgedeyse +1
  - RSI oversold/overbought bölgedeyse +1
  - Pivot seviyesi yakınındaysa +1
  - Bollinger alt/üst bandındaysa +1
  Confluences ne kadar çoksa sinyal o kadar güçlü.
"""
from typing import Optional, Tuple

from .base import BasePhase, PhaseContext, PhaseResult
import structlog

logger = structlog.get_logger(__name__)


class ZoneConfluencePhase(BasePhase):
    """Faz 3: Arz/Talep Bölgesi ve Confluence Analizi"""

    PHASE_ID = 3
    PHASE_NAME = "ZoneConfluence"

    async def run(self, ctx: PhaseContext) -> PhaseResult:
        try:
            return self._analyze(ctx)
        except Exception as e:
            logger.error("phase3_error", error=str(e))
            return self._neutral_result(f"Faz3 hatası: {e}")

    def _analyze(self, ctx: PhaseContext) -> PhaseResult:
        df = ctx.df
        cfg = ctx.config.get("phases", {}).get("phase3_zones", {})
        atr = ctx.atr
        tol_atr = cfg.get("zone_tolerance_atr", 0.3)
        confluence_min = cfg.get("confluence_min", 2)

        tolerance = atr * tol_atr
        last = df[-1]
        current_price = self._safe_float(df["close"])

        # ── Bölge Tespiti ─────────────────────────────────────────────────────
        demand_zone = self._find_demand_zone(df)
        supply_zone = self._find_supply_zone(df)

        in_demand = demand_zone and (demand_zone[0] - tolerance <= current_price <= demand_zone[1] + tolerance)
        in_supply = supply_zone and (supply_zone[0] - tolerance <= current_price <= supply_zone[1] + tolerance)

        # ── Confluence Sayımı ─────────────────────────────────────────────────
        confluences = 0
        confluence_details = []

        if in_demand:
            confluences += 1
            confluence_details.append("demand_zone")
        if in_supply:
            confluences += 1
            confluence_details.append("supply_zone")

        # RSI + Bollinger Band Confluence — korelasyonlu göstergeler
        # DÜZELTME #3: 35/65 → 30/70 (standart TA eşikleri)
        # DÜZELTME #4: RSI oversold + BB lower touch çoğu zaman aynı anda oluşur
        # (aynı piyasa koşulunu iki göstergeyle iki kez saymak skoru şişirir).
        # Çözüm: Her iki koşul aynı anda gerçekleşirse tek "teknik aşırılık" sayılır
        # (1.5 puan), sadece biri tetiklenirse 1 puan.
        rsi_oversold = False
        rsi_overbought = False
        bb_lower_touch = False
        bb_upper_touch = False

        if "rsi_14" in df.columns:
            rsi = self._safe_float(df["rsi_14"])
            if rsi < 30:       # Standart TA oversold (eskiden 35 — çok erken tetikleniyordu)
                rsi_oversold = True
            elif rsi > 70:     # Standart TA overbought (eskiden 65 — çok erken tetikleniyordu)
                rsi_overbought = True

        if "bb_lower" in df.columns and "bb_upper" in df.columns:
            bb_low = self._safe_float(df["bb_lower"])
            bb_up  = self._safe_float(df["bb_upper"])
            if current_price <= bb_low * (1 + tol_atr * 0.1):
                bb_lower_touch = True
            elif current_price >= bb_up * (1 - tol_atr * 0.1):
                bb_upper_touch = True

        # Korelasyon farkındalıklı sayım
        if rsi_oversold and bb_lower_touch:
            # İkisi aynı koşulu yansıtıyor → 1.5 puan (2 değil)
            confluences += 1.5
            confluence_details.append(f"rsi_oversold+bb_lower(corr,+1.5)")
        elif rsi_overbought and bb_upper_touch:
            confluences += 1.5
            confluence_details.append(f"rsi_overbought+bb_upper(corr,+1.5)")
        else:
            if rsi_oversold:
                confluences += 1
                confluence_details.append(f"rsi_oversold({rsi:.1f})")
            elif rsi_overbought:
                confluences += 1
                confluence_details.append(f"rsi_overbought({rsi:.1f})")
            if bb_lower_touch:
                confluences += 1
                confluence_details.append("bb_lower_touch")
            elif bb_upper_touch:
                confluences += 1
                confluence_details.append("bb_upper_touch")

        # Pivot Seviyesi Confluence
        if "s1" in df.columns and "r1" in df.columns:
            s1 = self._safe_float(df["s1"])
            r1 = self._safe_float(df["r1"])
            pivot = self._safe_float(df["pivot"]) if "pivot" in df.columns else 0.0
            if abs(current_price - s1) <= tolerance or abs(current_price - pivot) <= tolerance:
                confluences += 1
                confluence_details.append(f"pivot_s1({s1:.4f})")
            if abs(current_price - r1) <= tolerance:
                confluences += 1
                confluence_details.append(f"pivot_r1({r1:.4f})")

        # ── Sinyal ve Skor ────────────────────────────────────────────────────
        if in_demand and confluences >= confluence_min:
            score = min(100.0, 50.0 + confluences * 12.0)
            signal = "BULLISH"
            reason = f"Talep bölgesinde {confluences} confluence: {', '.join(confluence_details)}"
        elif in_supply and confluences >= confluence_min:
            score = min(100.0, 50.0 + confluences * 12.0)
            signal = "BEARISH"
            reason = f"Arz bölgesinde {confluences} confluence: {', '.join(confluence_details)}"
        elif confluences >= confluence_min:
            # Bölge yok ama diğer confluences var
            score = 45.0 + confluences * 5.0
            signal = "BULLISH" if in_demand else ("BEARISH" if in_supply else "NEUTRAL")
            reason = f"Bölge dışı {confluences} confluence"
        else:
            score = 20.0
            signal = "NEUTRAL"
            reason = f"Yetersiz confluence ({confluences}/{confluence_min})"

        metadata = {
            "current_price": round(current_price, 4),
            "demand_zone": [round(x, 4) for x in demand_zone] if demand_zone else None,
            "supply_zone": [round(x, 4) for x in supply_zone] if supply_zone else None,
            "in_demand": in_demand,
            "in_supply": in_supply,
            "confluences": confluences,
            "confluence_details": confluence_details,
            "tolerance": round(tolerance, 4),
            "atr": round(atr, 4),
        }

        logger.info("phase3_result", symbol=ctx.symbol, signal=signal,
                    score=round(score, 2), confluences=confluences)
        return PhaseResult(
            phase_id=self.PHASE_ID,
            phase_name=self.PHASE_NAME,
            score=round(score, 2),
            signal=signal,
            passed=True,
            reason=reason,
            metadata=metadata,
        )

    def _find_demand_zone(self, df) -> Optional[Tuple[float, float]]:
        """Son 'impulsif yukarı hamle'nin başındaki konsolidasyon bölgesi = Talep."""
        closes = df["close"].to_list()
        opens = df["open"].to_list()
        lows = df["low"].to_list()
        n = len(closes)

        # Son 50 bar içinde en güçlü yukarı mum'u bul (order block)
        best_idx = None
        best_move = 0.0
        for i in range(max(0, n - 50), n - 3):
            # Yukarı mum mu?
            if closes[i] > opens[i]:
                # Sonraki 2 barda ne kadar ilerledi?
                move = closes[i + 2] - closes[i] if i + 2 < n else 0
                if move > best_move:
                    best_move = move
                    best_idx = i

        if best_idx is None:
            return None

        # O mum + önceki mum → Talep bölgesi (lower: min low, upper: max high of those bars)
        zone_low = min(lows[max(0, best_idx - 1): best_idx + 1])
        zone_high = max(
            df["high"].to_list()[max(0, best_idx - 1): best_idx + 1]
        )
        return (zone_low, zone_high)

    def _find_supply_zone(self, df) -> Optional[Tuple[float, float]]:
        """Son 'impulsif aşağı hamle'nin başındaki konsolidasyon bölgesi = Arz."""
        closes = df["close"].to_list()
        opens = df["open"].to_list()
        highs = df["high"].to_list()
        lows = df["low"].to_list()
        n = len(closes)

        best_idx = None
        best_move = 0.0
        for i in range(max(0, n - 50), n - 3):
            if closes[i] < opens[i]:  # Aşağı mum
                move = closes[i] - closes[i + 2] if i + 2 < n else 0
                if move > best_move:
                    best_move = move
                    best_idx = i

        if best_idx is None:
            return None

        zone_low = min(lows[max(0, best_idx - 1): best_idx + 1])
        zone_high = max(highs[max(0, best_idx - 1): best_idx + 1])
        return (zone_low, zone_high)
