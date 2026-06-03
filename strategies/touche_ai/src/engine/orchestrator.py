"""
Touche AI Limited — Ana Orchestrator (7 Fazlı Pipeline)

Giriş: OHLCV Polars DataFrame
Çıkış: ToucheSignal (EQS skoru, sinyal, SL/TP, pozisyon büyüklüğü)

Pipeline:
  1. Tüm indikatörler hesaplanır
  2. PhaseContext oluşturulur
  3. 7 faz sırayla ve asenkron çalıştırılır
  4. EQS skoru hesaplanır
  5. Sonuç ToucheSignal olarak döndürülür
"""
import os
import sys
import time
from typing import Any, Dict, List, Optional

import polars as pl
import structlog
import yaml
from pydantic import BaseModel

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../..")))

from ..indicators.momentum import RSIIndicator, StochRSIIndicator, MACDIndicator
from ..indicators.trend import ADXIndicator, EMAIndicator
from ..indicators.volatility import ATRIndicator, BollingerIndicator
from ..indicators.volume import OBVIndicator, VolumeRatioIndicator, CMFIndicator
from ..indicators.structure import SwingPointsIndicator, PivotsIndicator
from ..validators.data_quality import DataQualityValidator
from ..phases.base import PhaseContext, PhaseResult
from ..phases.phase1_liquidity import LiquiditySweepPhase
from ..phases.phase2_structure import MarketStructurePhase
from ..phases.phase3_zones import ZoneConfluencePhase
from ..phases.phase4_confirm import AccumDistPhase
from ..phases.phase5_timing import EntryTimingPhase
from ..phases.phase6_risk import RiskManagementPhase
from ..phases.phase7_macro import MacroFilterPhase
from .scoring import EQSScorer, EQSResult

logger = structlog.get_logger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../config/strategy_params.yaml")


# ─── Çıktı Modeli ────────────────────────────────────────────────────────────

class ToucheSignal(BaseModel):
    """
    Touche AI — Nihai İşlem Sinyali Çıktısı.

    Consensus Engine ve Execution Bridge bu modeli bekler.
    """
    strategy_id: str = "touche_ai"
    symbol: str
    timeframe: str
    timestamp: int
    eqs_score: float
    signal: str                    # BULLISH | BEARISH | NEUTRAL
    signal_strength: str           # STRONG | MODERATE | WEAK | NO_TRADE
    recommendation: str            # BUY | SELL | HOLD
    confidence: float              # 0.0 - 1.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    phase_results: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class ToucheOrchestrator:
    """
    Touche AI Limited — 7 Fazlı Teknik Analiz Pipeline Yöneticisi.

    Kullanım:
        orc = ToucheOrchestrator(symbol="BTCUSDT", timeframe="4h")
        signal = await orc.analyze(df, fundamental_score=72.5)
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str = "4h",
        config: Optional[Dict[str, Any]] = None,
        account_balance: float = 10_000.0,
        risk_pct: float = 1.0,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.account_balance = account_balance
        self.risk_pct = risk_pct

        # Konfigürasyon yükle (yoksa varsayılan)
        self.config = config or self._load_config()

        # İndikatör sınıfları
        ind_cfg = self.config.get("indicators", {})
        self._indicators = [
            RSIIndicator(period=ind_cfg.get("rsi", {}).get("period", 14)),
            StochRSIIndicator(
                rsi_period=ind_cfg.get("stoch_rsi", {}).get("rsi_period", 14),
                stoch_period=ind_cfg.get("stoch_rsi", {}).get("stoch_period", 14),
                smooth_k=ind_cfg.get("stoch_rsi", {}).get("smooth_k", 3),
                smooth_d=ind_cfg.get("stoch_rsi", {}).get("smooth_d", 3),
            ),
            MACDIndicator(
                fast=ind_cfg.get("macd", {}).get("fast", 12),
                slow=ind_cfg.get("macd", {}).get("slow", 26),
                signal=ind_cfg.get("macd", {}).get("signal", 9),
            ),
            ADXIndicator(period=ind_cfg.get("adx", {}).get("period", 14)),
            EMAIndicator(periods=[
                ind_cfg.get("ema", {}).get("fast", 20),
                ind_cfg.get("ema", {}).get("slow", 50),
                ind_cfg.get("ema", {}).get("trend", 200),
            ]),
            ATRIndicator(period=ind_cfg.get("atr", {}).get("period", 14)),
            BollingerIndicator(
                period=ind_cfg.get("bollinger", {}).get("period", 20),
                std_dev=ind_cfg.get("bollinger", {}).get("std_dev", 2.0),
            ),
            OBVIndicator(),
            VolumeRatioIndicator(period=ind_cfg.get("volume_ratio", {}).get("period", 20)),
            CMFIndicator(period=ind_cfg.get("cmf", {}).get("period", 20)),
            # Swing lookback timeframe'e göre dinamik ayarlanır — sabit 5 değil.
            # Daha uzun TF → daha az bar gerekir; 1h'de 5 bar = 5 saat çok dar.
            SwingPointsIndicator(
                lookback=ind_cfg.get("swing_points", {}).get(
                    "lookback",
                    self._get_swing_lookback(timeframe),
                )
            ),
            PivotsIndicator(),
        ]

        self._data_validator = DataQualityValidator()

        # Faz sınıfları (sıra önemli)
        self._phases = [
            LiquiditySweepPhase(),
            MarketStructurePhase(),
            ZoneConfluencePhase(),
            AccumDistPhase(),
            EntryTimingPhase(),
            RiskManagementPhase(),
            MacroFilterPhase(),
        ]

        self._scorer = EQSScorer(self.config)

    def apply_quantum_signal_filters(
        self,
        signal: ToucheSignal,
        liquidity: float,
        order_book_skewness: float = 0.0,
    ) -> ToucheSignal:
        """
        COMPONENT 4: Apply Quantum AI signal quality filters to Touche signal.

        Args:
            signal: Original Touche signal
            liquidity: Liquidity score (0-1)
            order_book_skewness: Order book imbalance (-1 to 1)

        Returns:
            Signal with adjusted confidence
        """
        try:
            from strategies.quantum_ai.src.mm_engine.order_manager import OrderManager

            qm = OrderManager()
            original_confidence = signal.confidence

            # Apply signal quality filters
            filtered_confidence, filters = qm.apply_signal_quality_filters(
                entry_signal=original_confidence,
                liquidity=liquidity,
                order_book_skewness=order_book_skewness,
            )

            # Update signal with filtered confidence
            updated_signal = signal.model_copy(
                update={
                    "confidence": filtered_confidence,
                    "metadata": {
                        **signal.metadata,
                        "quantum_filters_applied": True,
                        "original_confidence": original_confidence,
                        "quantum_filter_breakdown": filters,
                        "liquidity_score": liquidity,
                        "order_book_skewness": order_book_skewness,
                    }
                }
            )

            logger.info(
                "quantum_signal_filter_applied",
                original_confidence=round(original_confidence, 3),
                filtered_confidence=round(filtered_confidence, 3),
                reduction_pct=round((1.0 - filtered_confidence/original_confidence)*100, 1) if original_confidence > 0 else 0.0,
            )

            return updated_signal

        except ImportError:
            logger.warning("quantum_ai_not_available_for_signal_filtering")
            return signal
        except Exception as e:
            logger.error("quantum_signal_filter_error", error=str(e))
            return signal

    @staticmethod
    def _get_swing_lookback(timeframe: str) -> int:
        """
        Swing point lookback'i timeframe'e göre ayarla.
        Yüksek TF'de 5 bar = çok uzun süre, düşük TF'de çok az.
        """
        _TF_LOOKBACK = {
            "1m": 10, "3m": 9, "5m": 8, "15m": 7, "30m": 7,
            "1h": 7,  "2h": 6, "4h": 6, "6h": 5,
            "1d": 4,  "3d": 4, "1w": 3, "1M": 3,
        }
        return _TF_LOOKBACK.get(timeframe.lower(), 5)

    async def analyze(
        self,
        df: pl.DataFrame,
        fundamental_score: Optional[float] = None,
    ) -> ToucheSignal:
        """
        Ana analiz metodudur. OHLCV DataFrame'i alır, pipeline'ı çalıştırır.

        Parametreler:
        - df               : OHLCV verisi (timestamp, open, high, low, close, volume)
        - fundamental_score: Fundamental AI'dan gelen makro skor (opsiyonel, Faz7 için)
        """
        ts = int(time.time())
        logger.info("touche_pipeline_start", symbol=self.symbol, timeframe=self.timeframe,
                    rows=len(df), fundamental=fundamental_score)

        # ── 0. Veri Kalite Kontrolü ───────────────────────────────────────────
        quality = self._data_validator.validate(df)
        if not quality.is_valid:
            logger.error("data_quality_failed_pipeline_abort",
                         errors=quality.errors, symbol=self.symbol)
            # Geçersiz veriyle analiz yapma — güvenli NEUTRAL sinyal döndür
            return ToucheSignal(
                symbol=self.symbol, timeframe=self.timeframe, timestamp=ts,
                eqs_score=0.0, signal="NEUTRAL", signal_strength="NO_TRADE",
                recommendation="HOLD", confidence=0.0,
                metadata={"data_quality_errors": quality.errors},
            )
        if quality.has_warnings:
            logger.warning("data_quality_warnings_pipeline_continues",
                           warnings=quality.warnings, symbol=self.symbol)

        # ── 1. İndikatörleri Hesapla ──────────────────────────────────────────
        enriched_df = self._compute_indicators(df)
        atr_col = "atr_14"
        atr = float(enriched_df[atr_col][-1]) if atr_col in enriched_df.columns else 0.001

        # ── 2. PhaseContext Oluştur ────────────────────────────────────────────
        ctx = PhaseContext(
            symbol=self.symbol,
            timeframe=self.timeframe,
            df=enriched_df,
            config=self.config,
            atr=atr,
            fundamental_score=fundamental_score,
            direction_hint="NEUTRAL",
        )

        # ── 3. Fazları Çalıştır ───────────────────────────────────────────────
        phase_results: List[PhaseResult] = []

        for phase in self._phases:
            result = await phase.run(ctx)
            phase_results.append(result)

            # Faz 6'ya girmeden dominant yönü context'e yaz
            # (Faz6 SL/TP hesabı için direction_hint lazım)
            if phase.PHASE_ID == 5:
                votes = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
                for r in phase_results:
                    votes[r.signal] = votes.get(r.signal, 0) + 1
                ctx = ctx.model_copy(update={"direction_hint": max(votes, key=votes.get)})

            # Bloke eden faz → kalan fazları çalıştırmaya gerek yok (verimlilik)
            if not result.passed and phase.PHASE_ID < 7:
                logger.info("pipeline_short_circuit", blocked_by=result.phase_name)
                # Kalan fazlar için placeholder ekle
                for remaining in self._phases[len(phase_results):]:
                    phase_results.append(remaining._neutral_result("Önceki faz bloke etti"))
                break

        # ── 4. EQS Skoru ─────────────────────────────────────────────────────
        eqs: EQSResult = self._scorer.compute(phase_results)

        # ── 5. SL/TP'yi Faz6 Metadata'sından Al ─────────────────────────────
        stop_loss, take_profit, position_size = self._extract_risk_params(
            phase_results, eqs.dominant_signal
        )

        # ── 6. Recommendation ────────────────────────────────────────────────
        recommendation = self._map_recommendation(eqs.dominant_signal, eqs.signal_strength)

        # ── Phase Hit-Rate Kaydı ──────────────────────────────────────────────
        # Her faz için: signal yönü, skor, passed durumu loglanır.
        # Gelecekte paper trade sonuçlarıyla ilişkilendirilerek hangi fazın
        # gerçekten doğru sinyal verdiği hesaplanabilir.
        phase_summary = {
            f"p{r.phase_id}_{r.phase_name}": {
                "signal":  r.signal,
                "score":   round(r.score, 2),
                "passed":  r.passed,
            }
            for r in phase_results
        }
        logger.info("phase_hit_rate_snapshot",
                    symbol=self.symbol,
                    dominant=eqs.dominant_signal,
                    phases=phase_summary)

        signal = ToucheSignal(
            symbol=self.symbol,
            timeframe=self.timeframe,
            timestamp=ts,
            eqs_score=eqs.eqs_score,
            signal=eqs.dominant_signal,
            signal_strength=eqs.signal_strength,
            recommendation=recommendation,
            confidence=eqs.confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            phase_results=[r.model_dump() for r in phase_results],
            metadata={
                "weighted_scores": eqs.weighted_scores,
                "phase_summary": phase_summary,
            },
        )

        logger.info(
            "touche_pipeline_complete",
            symbol=self.symbol,
            eqs=eqs.eqs_score,
            signal=eqs.dominant_signal,
            strength=eqs.signal_strength,
            recommendation=recommendation,
        )

        # COMPONENT 4: Apply Quantum AI signal quality filters
        try:
            from strategies.quantum_ai.src.mm_engine.order_manager import OrderManager

            qm = OrderManager()
            liquidity = qm.get_quantum_liquidity()
            signal = self.apply_quantum_signal_filters(
                signal=signal,
                liquidity=liquidity,
                order_book_skewness=0.0,  # Can be enhanced with real order book data
            )
        except Exception as e:
            logger.warning("quantum_filter_integration_failed", error=str(e))

        return signal

    def _compute_indicators(self, df: pl.DataFrame) -> pl.DataFrame:
        """Tüm indikatörleri sırayla uygular. Hatalı indikatör atlanır."""
        enriched = df
        for indicator in self._indicators:
            try:
                enriched = indicator.compute(enriched)
            except Exception as e:
                logger.warning("indicator_skipped", indicator=indicator.NAME, error=str(e))
        return enriched

    def _extract_risk_params(
        self, results: List[PhaseResult], signal: str
    ):
        """Faz6 metadata'sından SL/TP ve pozisyon büyüklüğünü çeker."""
        for r in results:
            if r.phase_id == 6 and r.passed and r.metadata:
                sl = r.metadata.get("stop_loss")
                tp = r.metadata.get("take_profit")
                # Pozisyon büyüklüğü: (Hesap × Risk%) / SL mesafesi
                sl_dist = r.metadata.get("sl_distance", 0)
                if sl_dist and sl_dist > 0:
                    risk_amount = self.account_balance * (self.risk_pct / 100.0)
                    pos_size = round(risk_amount / sl_dist, 4)
                else:
                    pos_size = None
                return sl, tp, pos_size
        return None, None, None

    @staticmethod
    def _map_recommendation(signal: str, strength: str) -> str:
        """Sinyal + güç kombinasyonunu işlem kararına çevirir."""
        if strength == "NO_TRADE" or signal == "NEUTRAL":
            return "HOLD"
        if signal == "BULLISH":
            return "BUY"
        if signal == "BEARISH":
            return "SELL"
        return "HOLD"

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """strategy_params.yaml'ı yükler; bulunamazsa boş dict döner."""
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("config_file_not_found", path=_CONFIG_PATH)
            return {}
        except Exception as e:
            logger.error("config_load_error", error=str(e))
            return {}


# Alias — Fundamental AI pattern ile tutarlılık
ToucheAIOrchestrator = ToucheOrchestrator
