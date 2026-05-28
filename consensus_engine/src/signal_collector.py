"""
Consensus Engine — Signal Collector

Touche AI ve Fundamental AI'dan sinyal toplar ve standart
formata dönüştürür.
"""
from typing import Optional, Any, Dict
from datetime import datetime, timezone

import structlog

from .models import ToucheSignal, FundamentalSignal

logger = structlog.get_logger(__name__)


class SignalCollector:
    """Her iki AI'dan sinyal toplar."""
    
    @staticmethod
    def collect_touche_signal(
        symbol: str,
        timeframe: str,
        touche_result: Dict[str, Any]
    ) -> ToucheSignal:
        """
        Touche AI sonucunu ToucheSignal'e dönüştürür.
        
        Args:
            symbol: İşlem çifti (BTCUSDT vb.)
            timeframe: Zaman çerçevesi (4h, 1d vb.)
            touche_result: Touche Orchestrator sonucu
        
        Returns:
            ToucheSignal nesnesi
        """
        try:
            # Touche AI sonucundan çıkarılan bilgiler
            eqs = touche_result.get("eqs", 50.0)
            recommendation = touche_result.get("recommendation", "HOLD")
            
            # Recommendation → Signal dönüşümü
            signal = SignalCollector._convert_touche_recommendation(recommendation)
            
            # Metadata ve phase sonuçları
            phase_results = touche_result.get("phase_results", {})
            metadata = {
                "eqs": eqs,
                "recommendation": recommendation,
                "timestamp": touche_result.get("timestamp", datetime.now(timezone.utc).isoformat()),
            }
            
            touche_signal = ToucheSignal(
                symbol=symbol,
                timeframe=timeframe,
                signal=signal,
                eqs=eqs,
                score=eqs,  # Touche için EQS = score
                reason=touche_result.get("reasoning", "No reasoning provided"),
                phase_results=phase_results,
                metadata=metadata,
            )
            
            logger.info(
                "touche_signal_collected",
                symbol=symbol,
                signal=signal,
                eqs=eqs,
            )
            
            return touche_signal
            
        except Exception as e:
            logger.error("touche_signal_collection_error", error=str(e), symbol=symbol)
            # Fallback: HOLD sinyali
            return ToucheSignal(
                symbol=symbol,
                timeframe=timeframe,
                signal="BEKLE",
                eqs=50.0,
                score=50.0,
                reason=f"Signal collection error: {str(e)}",
                phase_results={},
                metadata={"error": str(e)},
            )
    
    @staticmethod
    def collect_fundamental_signal(
        symbol: str,
        fundamental_result: Dict[str, Any]
    ) -> FundamentalSignal:
        """
        Fundamental AI sonucunu FundamentalSignal'e dönüştürür.
        
        Args:
            symbol: İşlem çifti
            fundamental_result: Fundamental AI sonucu
        
        Returns:
            FundamentalSignal nesnesi
        """
        try:
            # Fundamental AI sonucundan çıkarılan bilgiler
            signal = fundamental_result.get("signal", "NEUTRAL")  # BULLISH/BEARISH/NEUTRAL
            score = fundamental_result.get("score", 50.0)  # 0-100
            factors = fundamental_result.get("factors", {})
            
            fundamental_signal = FundamentalSignal(
                symbol=symbol,
                signal=signal,
                score=score,
                factors=factors,
                reason=fundamental_result.get("reasoning", "No reasoning provided"),
                metadata={
                    "timestamp": fundamental_result.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "analysis_type": fundamental_result.get("analysis_type", "standard"),
                },
            )
            
            logger.info(
                "fundamental_signal_collected",
                symbol=symbol,
                signal=signal,
                score=score,
            )
            
            return fundamental_signal
            
        except Exception as e:
            logger.error("fundamental_signal_collection_error", error=str(e), symbol=symbol)
            # Fallback: NEUTRAL sinyali
            return FundamentalSignal(
                symbol=symbol,
                signal="NEUTRAL",
                score=50.0,
                factors={},
                reason=f"Signal collection error: {str(e)}",
                metadata={"error": str(e)},
            )
    
    @staticmethod
    def _convert_touche_recommendation(recommendation: str) -> str:
        """Touche recommendation'ı standard signal'e çevirme."""
        recommendation = recommendation.upper()

        if "BUY" in recommendation or "AL" in recommendation:
            return "AL"
        elif "SELL" in recommendation or "SAT" in recommendation:
            return "SAT"
        else:
            return "BEKLE"

    @staticmethod
    def collect_news_signal(news_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        News AI Limited'dan gelen sinyali işleme ve standart formata çevirme.

        Args:
            news_result: News AI /signals endpoint'inden dönen sonuç

        Returns:
            Standart format signal veya None (hata durumunda)
        """
        try:
            if not news_result:
                logger.warning("news_signal_empty")
                return None

            # News signal'dan temel metrikleri çıkar
            impact_score = news_result.get("weighted_impact", 0.0)  # -100 to +100
            total_articles = news_result.get("total_articles", 0)
            avg_sentiment = news_result.get("average_sentiment", 0.0)  # -1 to +1

            # Impact score'u 0-100 aralığına normalize et
            # -100 to +100 → 0 to 100 (neutral = 50)
            normalized_impact = ((impact_score + 100) / 2)
            normalized_impact = max(0, min(100, normalized_impact))

            # Sinyal belirle (impact score'a göre)
            if impact_score > 20:
                signal = "AL"  # BUY
                confidence = min(0.95, 0.6 + (impact_score / 200))
            elif impact_score < -20:
                signal = "SAT"  # SELL
                confidence = min(0.95, 0.6 + (abs(impact_score) / 200))
            else:
                signal = "BEKLE"  # HOLD
                confidence = 0.5

            news_signal = {
                "signal": signal,
                "score": normalized_impact,  # 0-100
                "raw_impact": impact_score,  # -100 to +100
                "confidence": confidence,
                "articles_count": total_articles,
                "average_sentiment": avg_sentiment,
                "timestamp": news_result.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "metadata": {
                    "source": "news-ai-limited",
                    "version": "1.0",
                    "period": news_result.get("period_hours", 1),
                }
            }

            logger.info(
                "news_signal_collected",
                signal=signal,
                impact_score=impact_score,
                normalized_score=normalized_impact,
                articles=total_articles,
                confidence=confidence,
            )

            return news_signal

        except Exception as e:
            logger.error("news_signal_collection_error", error=str(e))
            # Fallback: neutral News signal
            return {
                "signal": "BEKLE",
                "score": 50.0,
                "confidence": 0.0,
                "articles_count": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {"error": str(e)},
            }

