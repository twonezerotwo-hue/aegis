"""
Consensus Engine — Orchestrator

Ana çalıştırıcı: Touche AI ve Fundamental AI sinyallerini
birleştirerek nihai kararı üretir.
"""
from typing import Dict, Any, Optional, List

import structlog

from .src.models import (
    ConsensusConfig,
    ConsensusDecision,
    PortfolioPosition,
)
from .src.signal_collector import SignalCollector
from .src.signal_aggregator import SignalAggregator
from .src.position_optimizer import PositionOptimizer
from .src.risk_manager import RiskManager
from .src.final_allocator import FinalAllocator

logger = structlog.get_logger(__name__)


class ConsensusOrchestrator:
    """
    AEGIS Holding — Consensus Engine Orchestrator
    
    Touche AI ve Fundamental AI sinyallerini birleştirerek
    nihai investment kararı üretir.
    """
    
    def __init__(self, config: ConsensusConfig):
        """
        Args:
            config: Consensus konfigürasyonu
        """
        self.config = config
        self.signal_aggregator = SignalAggregator(config)
        self.position_optimizer = PositionOptimizer(config)
        self.risk_manager = RiskManager(config)
        
        logger.info("consensus_orchestrator_initialized")
    
    async def process(
        self,
        symbol: str,
        touche_result: Dict[str, Any],
        fundamental_result: Dict[str, Any],
        portfolio: Optional[Dict[str, PortfolioPosition]] = None,
        portfolio_value: float = 100000.0,
        current_price: float = 100.0,
        atr: float = 2.0,
        sentinel_multiplier: float = 1.0,
        regime: Optional[str] = None,
    ) -> ConsensusDecision:
        """
        İki AI'dan sinyalleri al, birleştir, nihai karar üret.
        
        Args:
            symbol: İşlem çifti
            touche_result: Touche AI sonucu
            fundamental_result: Fundamental AI sonucu
            portfolio: Mevcut portfolio pozisyonları
            portfolio_value: Portfolio toplam değeri
            current_price: Mevcut fiyat
            atr: Average True Range
        
        Returns:
            ConsensusDecision
        """
        try:
            logger.info("consensus_processing_started", symbol=symbol)
            
            # Step 1: Sinyalleri topla
            touche_signal = SignalCollector.collect_touche_signal(
                symbol=symbol,
                timeframe="4h",
                touche_result=touche_result,
            )
            
            fundamental_signal = SignalCollector.collect_fundamental_signal(
                symbol=symbol,
                fundamental_result=fundamental_result,
            )

            # Step 2: Risk filtresi (consensus ONCESI)
            if sentinel_multiplier < 0.5:
                logger.warning(
                    "risk_filter_hold_before_consensus",
                    symbol=symbol,
                    sentinel_multiplier=sentinel_multiplier,
                )
                return self._risk_gate_hold_decision(
                    symbol=symbol,
                    touche_signal=touche_signal,
                    fundamental_signal=fundamental_signal,
                    sentinel_multiplier=sentinel_multiplier,
                )
            
            # Step 3: Sinyalleri birleştir
            aggregation_result = self.signal_aggregator.aggregate(
                touche_signal,
                fundamental_signal,
                regime=regime,
            )
            
            # Step 4: Position boyutunu hesapla
            kelly_f, fundamental_mult, position_size = self.position_optimizer.calculate_position_size(
                aggregation_result,
                fundamental_score=fundamental_signal.score,
            )
            
            # Step 5: Risk parametrelerini hesapla
            risk_params = self.position_optimizer.calculate_risk_levels(
                aggregation_result,
                current_price=current_price,
                atr=atr,
            )
            
            # Step 6: Risk kontrolü yap
            portfolio = portfolio or {}
            risk_metrics = self.risk_manager.calculate_portfolio_metrics(
                positions=portfolio,
                portfolio_value=portfolio_value,
                cash_reserve=portfolio_value * 0.05,
            )

            # Max position size kontrolü
            if position_size > 0.15:
                logger.warning("position_size_too_large", position_size=position_size, symbol=symbol)
                position_size = 0.15
            
            # Step 7: Nihai karar oluştur
            decision = FinalAllocator.create_consensus_decision(
                aggregation_result=aggregation_result,
                position_size=position_size,
                fundamental_multiplier=fundamental_mult,
                kelly_fraction=kelly_f,
                stop_loss=risk_params.get("stop_loss") or 0.0,
                take_profit=risk_params.get("take_profit") or 0.0,
                stop_loss_percent=risk_params.get("stop_loss_percent") or 0.0,
                take_profit_target=risk_params.get("take_profit_target") or 0.0,
                risk_level=risk_params.get("risk_level", "MEDIUM"),
            )
            
            logger.info(
                "consensus_processing_completed",
                symbol=symbol,
                action=decision.action,
                confidence=round(decision.confidence, 3),
                position_size=round(position_size, 4),
            )
            
            return decision
            
        except Exception as e:
            logger.error("consensus_processing_error", error=str(e), symbol=symbol)
            # Return neutral decision on error
            return self._neutral_decision(symbol, str(e))

    def _risk_gate_hold_decision(
        self,
        symbol: str,
        touche_signal,
        fundamental_signal,
        sentinel_multiplier: float,
    ) -> ConsensusDecision:
        """Risk gate nedeniyle consensus oncesi zorunlu HOLD karari dondur."""
        return ConsensusDecision(
            symbol=symbol,
            action="BEKLE",
            confidence=0.0,
            position_size=0.0,
            touche_signal=touche_signal,
            fundamental_signal=fundamental_signal,
            fundamental_multiplier=1.0,
            position_multiplier=0.0,
            kelly_fraction=0.0,
            alignment_score=0.0,
            contradiction_score=1.0,
            aggregate_score=0.0,
            risk_level="HIGH",
            stop_loss_percent=0.0,
            take_profit_target=0.0,
            reasoning=f"Risk gate activated: sentinel_multiplier={sentinel_multiplier:.2f} < 0.50",
            metadata={
                "risk_filtered": True,
                "sentinel_multiplier": sentinel_multiplier,
                "filter_order": "before_consensus",
            },
        )
    
    def _neutral_decision(self, symbol: str, error: str) -> ConsensusDecision:
        """Hata durumunda neutral karar döndür."""
        from .src.models import ToucheSignal, FundamentalSignal
        
        touche = ToucheSignal(
            symbol=symbol,
            timeframe="4h",
            signal="BEKLE",
            eqs=50.0,
            score=50.0,
            reason=f"Error: {error}",
            phase_results={},
        )
        
        fundamental = FundamentalSignal(
            symbol=symbol,
            signal="NEUTRAL",
            score=50.0,
            factors={},
            reason=f"Error: {error}",
        )
        
        return ConsensusDecision(
            symbol=symbol,
            action="BEKLE",
            confidence=0.0,
            position_size=0.0,
            touche_signal=touche,
            fundamental_signal=fundamental,
            fundamental_multiplier=1.0,
            position_multiplier=0.0,
            kelly_fraction=0.0,
            alignment_score=0.0,
            contradiction_score=1.0,
            aggregate_score=0.0,
            risk_level="NEUTRAL",
            stop_loss_percent=0.0,
            take_profit_target=0.0,
            reasoning=f"Error in processing: {error}",
        )

    # ──────────────────────────────────────────────────────────────
    # Light Screening
    # ──────────────────────────────────────────────────────────────

    async def light_screening(
        self,
        symbols: List[str],
        touche_url: str = "http://touche-api:8001",
        top_n: int = 2,
    ) -> List[str]:
        """
        Hızlı ön-eleme: Her sembol için sadece Touche ve Fundamental
        modüllerini kullanarak basit bir light_score hesaplar,
        en yüksek skorlu `top_n` sembolü döndürür.

        Touche skoru: /touche/key_levels pivot konumundan türetilir.
        Fundamental skoru: mevcut API skore endpoint olmadığında 50.0 (nötr).
        light_score = touche_score * 0.60 + fundamental_score * 0.40

        Args:
            symbols: Taranacak sembol listesi (örn. ["BTC", "ETH", "SOL"])
            touche_url: Touche API base URL (Docker service: touche-api:8001)
            top_n: Döndürülecek en iyi sembol sayısı

        Returns:
            En yüksek skorlu `top_n` sembolün list'i.
        """
        import urllib.request as _ur
        import json as _jl

        scores: Dict[str, float] = {}

        for symbol in symbols:
            try:
                # ── Touche: pivot-based technical score ──────────────
                with _ur.urlopen(
                    f"{touche_url}/touche/key_levels?symbol={symbol}", timeout=3
                ) as _resp:
                    kl = _jl.loads(_resp.read().decode("utf-8"))

                support_levels: List[float] = kl.get("support_levels") or []
                resistance_levels: List[float] = kl.get("resistance_levels") or []
                pivot: float = float(kl.get("pivot", 0.0))

                if support_levels and resistance_levels and pivot:
                    avg_sup = sum(support_levels) / len(support_levels)
                    avg_res = sum(resistance_levels) / len(resistance_levels)
                    level_range = avg_res - avg_sup
                    if level_range > 0:
                        touche_score = max(0.0, min(100.0, (pivot - avg_sup) / level_range * 100.0))
                    else:
                        touche_score = 50.0
                else:
                    touche_score = 50.0

            except Exception as _te:
                logger.warning("light_screening_touche_error", symbol=symbol, error=str(_te))
                touche_score = 50.0

            # ── Fundamental: no scoring endpoint → neutral fallback ──
            fundamental_score = 50.0

            light_score = touche_score * 0.60 + fundamental_score * 0.40
            scores[symbol] = round(light_score, 4)
            logger.info(
                "light_screening_scored",
                symbol=symbol,
                touche_score=round(touche_score, 2),
                fundamental_score=fundamental_score,
                light_score=round(light_score, 4),
            )

        shortlist = sorted(scores, key=lambda s: scores[s], reverse=True)[:top_n]
        logger.info("light_screening_shortlist", shortlist=shortlist, scores=scores)
        return shortlist

    # ──────────────────────────────────────────────────────────────
    # Main Pipeline
    # ──────────────────────────────────────────────────────────────

    async def main_pipeline(
        self,
        symbols: List[str],
        touche_url: str = "http://touche-api:8001",
        portfolio: Optional[Dict[str, "PortfolioPosition"]] = None,
        portfolio_value: float = 100000.0,
        current_prices: Optional[Dict[str, float]] = None,
        sentinel_multiplier: float = 1.0,
        regime: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ana pipeline: önce light_screening ile shortlist al,
        ardından shortlist'teki her sembol için full_analysis
        (process) çalıştır; en yüksek consensus_score'a sahip
        sonucu döndür.

        Args:
            symbols: Aday sembol listesi
            touche_url: Touche API base URL
            portfolio: Mevcut portfolio pozisyonları
            portfolio_value: Portfolio toplam değeri
            current_prices: {symbol: price} eşlemesi (opsiyonel)
            sentinel_multiplier: Risk çarpanı
            regime: Piyasa rejimi

        Returns:
            {"best_symbol": str, "decision": ConsensusDecision,
             "consensus_score": float, "all_results": [...]}
        """
        import urllib.request as _ur
        import json as _jl

        current_prices = current_prices or {}

        # Step 1: Hızlı ön-eleme — top 2 sem
        shortlist = await self.light_screening(symbols, touche_url=touche_url)

        all_results: List[Dict[str, Any]] = []

        # Step 2: Full analysis — shortlist semboller için process() çağır
        for symbol in shortlist:
            # Touche key_levels'ten touche_result oluştur
            try:
                with _ur.urlopen(
                    f"{touche_url}/touche/key_levels?symbol={symbol}", timeout=3
                ) as _resp:
                    kl = _jl.loads(_resp.read().decode("utf-8"))

                support_levels: List[float] = kl.get("support_levels") or []
                resistance_levels: List[float] = kl.get("resistance_levels") or []
                pivot: float = float(kl.get("pivot", 0.0))

                avg_sup = sum(support_levels) / len(support_levels) if support_levels else pivot * 0.97
                avg_res = sum(resistance_levels) / len(resistance_levels) if resistance_levels else pivot * 1.03
                level_range = avg_res - avg_sup
                eqs = max(0.0, min(100.0, (pivot - avg_sup) / level_range * 100.0)) if level_range > 0 else 50.0
                recommendation = "BUY" if eqs >= 60 else "SELL" if eqs <= 40 else "HOLD"

                touche_result: Dict[str, Any] = {
                    "eqs": eqs,
                    "recommendation": recommendation,
                    "reasoning": f"Light: pivot={pivot} sup={avg_sup:.0f} res={avg_res:.0f}",
                    "phase_results": {"key_levels": kl},
                }
            except Exception as _te:
                logger.warning("main_pipeline_touche_error", symbol=symbol, error=str(_te))
                touche_result = {"eqs": 50.0, "recommendation": "HOLD", "reasoning": "fetch_error", "phase_results": {}}

            # Fundamental result — neutral fallback (no scoring endpoint)
            fundamental_result: Dict[str, Any] = {
                "signal": "NEUTRAL",
                "score": 50.0,
                "factors": {},
                "reasoning": "fundamental_api_no_scoring_endpoint",
                "analysis_type": "light",
            }

            current_price = float(current_prices.get(symbol, 100.0))

            decision = await self.process(
                symbol=symbol,
                touche_result=touche_result,
                fundamental_result=fundamental_result,
                portfolio=portfolio,
                portfolio_value=portfolio_value,
                current_price=current_price,
                sentinel_multiplier=sentinel_multiplier,
                regime=regime,
            )

            consensus_score = float(getattr(decision, "aggregate_score", 0.0) or decision.confidence)
            all_results.append(
                {
                    "symbol": symbol,
                    "decision": decision,
                    "consensus_score": round(consensus_score, 4),
                }
            )
            logger.info(
                "main_pipeline_full_analysis",
                symbol=symbol,
                action=decision.action,
                consensus_score=round(consensus_score, 4),
            )

        if not all_results:
            logger.warning("main_pipeline_no_results")
            return {"best_symbol": None, "decision": None, "consensus_score": 0.0, "all_results": []}

        best = max(all_results, key=lambda r: r["consensus_score"])
        logger.info(
            "main_pipeline_completed",
            best_symbol=best["symbol"],
            consensus_score=best["consensus_score"],
        )
        return {
            "best_symbol": best["symbol"],
            "decision": best["decision"],
            "consensus_score": best["consensus_score"],
            "all_results": all_results,
        }
