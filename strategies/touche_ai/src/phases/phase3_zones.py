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
from typing import List, Optional, Tuple

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
        zone_max_age = cfg.get("zone_max_age_bars", 50)  # Zone expiry

        # NaN KORUMASI: current_price sıfır ise anlamlı hesap yapılamaz
        current_price = self._safe_float(df["close"])
        if current_price <= 0:
            return self._neutral_result("Geçersiz fiyat (0 veya negatif)")

        tolerance = atr * tol_atr

        # ── Bölge Tespiti (expiry + FVG dahil) ───────────────────────────────
        demand_zone = self._find_demand_zone(df, max_age=zone_max_age)
        supply_zone = self._find_supply_zone(df, max_age=zone_max_age)

        # Fair Value Gap tespiti (SMC — kurumsal boşluklar)
        bullish_fvgs, bearish_fvgs = self._find_fair_value_gaps(df, max_age=zone_max_age)

        in_demand = demand_zone and (demand_zone[0] - tolerance <= current_price <= demand_zone[1] + tolerance)
        in_supply = supply_zone and (supply_zone[0] - tolerance <= current_price <= supply_zone[1] + tolerance)

        # FVG kontrolü
        in_bullish_fvg = any(
            fvg[0] - tolerance <= current_price <= fvg[1] + tolerance
            for fvg in bullish_fvgs
        )
        in_bearish_fvg = any(
            fvg[0] - tolerance <= current_price <= fvg[1] + tolerance
            for fvg in bearish_fvgs
        )

        # ── Confluence Sayımı ─────────────────────────────────────────────────
        confluences = 0
        confluence_details = []

        if in_demand:
            confluences += 1
            confluence_details.append("demand_zone")
        if in_supply:
            confluences += 1
            confluence_details.append("supply_zone")

        # FVG confluences (SMC teyidi — daha güçlü bölgeler)
        if in_bullish_fvg:
            confluences += 1.5   # FVG > klasik zone (kurumsal imbalance)
            confluence_details.append("bullish_FVG(+1.5)")
        if in_bearish_fvg:
            confluences += 1.5
            confluence_details.append("bearish_FVG(+1.5)")

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
        # FVG bullish + demand zone = güçlü kurumsal destek
        in_bullish_zone = in_demand or in_bullish_fvg
        in_bearish_zone = in_supply or in_bearish_fvg

        if in_bullish_zone and confluences >= confluence_min:
            score = min(100.0, 50.0 + confluences * 12.0)
            signal = "BULLISH"
            zone_type = "FVG+Demand" if (in_demand and in_bullish_fvg) else ("FVG" if in_bullish_fvg else "Demand")
            reason = f"{zone_type} bölgesinde {confluences:.1f} confluence: {', '.join(confluence_details)}"
        elif in_bearish_zone and confluences >= confluence_min:
            score = min(100.0, 50.0 + confluences * 12.0)
            signal = "BEARISH"
            zone_type = "FVG+Supply" if (in_supply and in_bearish_fvg) else ("FVG" if in_bearish_fvg else "Supply")
            reason = f"{zone_type} bölgesinde {confluences:.1f} confluence: {', '.join(confluence_details)}"
        elif confluences >= confluence_min:
            score = 45.0 + confluences * 5.0
            signal = "NEUTRAL"
            reason = f"Bölge dışı {confluences:.1f} confluence"
        else:
            score = 20.0
            signal = "NEUTRAL"
            reason = f"Yetersiz confluence ({confluences:.1f}/{confluence_min})"

        metadata = {
            "current_price": round(current_price, 4),
            "demand_zone": [round(x, 4) for x in demand_zone] if demand_zone else None,
            "supply_zone": [round(x, 4) for x in supply_zone] if supply_zone else None,
            "in_demand": in_demand,
            "in_supply": in_supply,
            "bullish_fvgs": [[round(f[0], 4), round(f[1], 4)] for f in bullish_fvgs[:3]],
            "bearish_fvgs": [[round(f[0], 4), round(f[1], 4)] for f in bearish_fvgs[:3]],
            "in_bullish_fvg": in_bullish_fvg,
            "in_bearish_fvg": in_bearish_fvg,
            "confluences": round(confluences, 2),
            "confluence_details": confluence_details,
            "tolerance": round(tolerance, 4),
            "atr": round(atr, 4),
            "zone_max_age": zone_max_age,
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

    def _find_demand_zone(
        self, df, max_age: int = 50
    ) -> Optional[Tuple[float, float]]:
        """Son 'impulsif yukarı hamle'nin başındaki order block = Talep Bölgesi.

        Zone expiry: Son `max_age` bar dışındaki bölgeler geçersiz sayılır.
        """
        closes = df["close"].to_list()
        opens  = df["open"].to_list()
        lows   = df["low"].to_list()
        highs  = df["high"].to_list()
        n = len(closes)

        best_idx  = None
        best_move = 0.0
        search_start = max(0, n - max_age)  # Zone expiry: sadece son max_age bar

        for i in range(search_start, n - 3):
            if closes[i] > opens[i]:  # Yukarı mum (order block adayı)
                move = closes[i + 2] - closes[i] if i + 2 < n else 0
                if move > best_move:
                    best_move = move
                    best_idx  = i

        if best_idx is None:
            return None

        zone_low  = min(lows [max(0, best_idx - 1): best_idx + 1])
        zone_high = max(highs[max(0, best_idx - 1): best_idx + 1])
        return (zone_low, zone_high)

    def _find_supply_zone(
        self, df, max_age: int = 50
    ) -> Optional[Tuple[float, float]]:
        """Son 'impulsif aşağı hamle'nin başındaki order block = Arz Bölgesi.

        Zone expiry: Son `max_age` bar dışındaki bölgeler geçersiz sayılır.
        """
        closes = df["close"].to_list()
        opens  = df["open"].to_list()
        highs  = df["high"].to_list()
        lows   = df["low"].to_list()
        n = len(closes)

        best_idx  = None
        best_move = 0.0
        search_start = max(0, n - max_age)

        for i in range(search_start, n - 3):
            if closes[i] < opens[i]:  # Aşağı mum
                move = closes[i] - closes[i + 2] if i + 2 < n else 0
                if move > best_move:
                    best_move = move
                    best_idx  = i

        if best_idx is None:
            return None

        zone_low  = min(lows [max(0, best_idx - 1): best_idx + 1])
        zone_high = max(highs[max(0, best_idx - 1): best_idx + 1])
        return (zone_low, zone_high)

    def _find_fair_value_gaps(
        self, df, max_age: int = 30
    ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
        """
        Fair Value Gap (FVG / Imbalance) tespiti — SMC konsepti.

        3 ardışık mum:
          Bullish FVG: mum[i-2].high < mum[i].low  → fiyat boşluk bıraktı yukarı
          Bearish FVG: mum[i-2].low  > mum[i].high → fiyat boşluk bıraktı aşağı

        Fiyat bu boşluğa döndüğünde güçlü tepki beklenir (kurumsal sipariş dolumu).
        """
        highs  = df["high"].to_list()
        lows   = df["low"].to_list()
        closes = df["close"].to_list()
        n = len(highs)

        bullish_fvgs: List[Tuple[float, float]] = []
        bearish_fvgs: List[Tuple[float, float]] = []

        search_start = max(2, n - max_age)
        current_price = closes[-1] if closes else 0.0

        for i in range(search_start, n):
            if i < 2:
                continue
            h0 = highs[i - 2];  l0 = lows[i - 2]  # Bar[i-2]
            # Bar[i-1] = orta/impulse bar
            h2 = highs[i];      l2 = lows[i]       # Bar[i]

            # Bullish FVG: gap between bar[i-2].high and bar[i].low
            if h0 < l2 and l2 > h0:
                fvg_low  = h0
                fvg_high = l2
                # Sadece fiyat henüz doldurulmamış FVG'leri dahil et
                if current_price <= fvg_high * 1.05:  # Yakın veya içinde
                    bullish_fvgs.append((fvg_low, fvg_high))

            # Bearish FVG: gap between bar[i-2].low and bar[i].high
            elif l0 > h2 and h2 < l0:
                fvg_low  = h2
                fvg_high = l0
                if current_price >= fvg_low * 0.95:
                    bearish_fvgs.append((fvg_low, fvg_high))

        # En yakın FVG'leri önce döndür (son X bar)
        return bullish_fvgs[-3:], bearish_fvgs[-3:]
