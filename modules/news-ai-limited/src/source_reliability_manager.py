"""
NEWS AI - Source Reliability Score & Event Impact Duration

Özellikler:
- Kaynak güvenilirlik skoru (Fed=100, Twitter=30)
- Olay etki süresi ne kadar etkili kalır?
- FUD/fake news filtreleme
- Kaynak bazlı ağırlıklandırma
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class SourceType(Enum):
    """Haber kaynağı türleri"""
    OFFICIAL = "OFFICIAL"          # Resmi (Fed, ECB, SEC)
    CRYPTO_NATIVE = "CRYPTO_NATIVE"  # CoinDesk, The Block
    MAINSTREAM = "MAINSTREAM"      # Bloomberg, Reuters
    SOCIAL = "SOCIAL"              # Twitter, Discord, Reddit
    FORUM = "FORUM"                # Bitcointalk, ETH research


@dataclass
class SourceReliabilityProfile:
    """Haber kaynağı güvenilirlik profili"""
    name: str
    source_type: SourceType
    reliability_score: float  # 0-100
    bias_score: float  # 0-100 (0=objective, 100=highly biased)
    history_accuracy: float  # 0-100
    track_record: str  # EXCELLENT, GOOD, AVERAGE, POOR


class SourceReliabilityManager:
    """
    Haber kaynaklarına güvenilirlik skoru atanır

    Sıralama:
    - Fed/ECB: 100 (most reliable)
    - SEC/CFTC: 95
    - CoinDesk, The Block: 80
    - Reuters, Bloomberg: 75 (Crypto haberleri için)
    - Official company blogs: 70
    - Mainstream media: 60
    - Crypto Twitter: 30-50 (source'a bağlı)
    - Reddit, Discord: 20-30
    """

    SOURCE_DATABASE = {
        "fed.gov": SourceReliabilityProfile(
            name="Federal Reserve",
            source_type=SourceType.OFFICIAL,
            reliability_score=100,
            bias_score=5,
            history_accuracy=98,
            track_record="EXCELLENT",
        ),
        "ecb.int": SourceReliabilityProfile(
            name="European Central Bank",
            source_type=SourceType.OFFICIAL,
            reliability_score=100,
            bias_score=5,
            history_accuracy=98,
            track_record="EXCELLENT",
        ),
        "sec.gov": SourceReliabilityProfile(
            name="SEC",
            source_type=SourceType.OFFICIAL,
            reliability_score=95,
            bias_score=10,
            history_accuracy=95,
            track_record="EXCELLENT",
        ),
        "coindesk.com": SourceReliabilityProfile(
            name="CoinDesk",
            source_type=SourceType.CRYPTO_NATIVE,
            reliability_score=80,
            bias_score=15,
            history_accuracy=85,
            track_record="GOOD",
        ),
        "theblock.co": SourceReliabilityProfile(
            name="The Block",
            source_type=SourceType.CRYPTO_NATIVE,
            reliability_score=78,
            bias_score=18,
            history_accuracy=82,
            track_record="GOOD",
        ),
        "reuters.com": SourceReliabilityProfile(
            name="Reuters",
            source_type=SourceType.MAINSTREAM,
            reliability_score=75,
            bias_score=20,
            history_accuracy=88,
            track_record="GOOD",
        ),
        "cointelegraph.com": SourceReliabilityProfile(
            name="CoinTelegraph",
            source_type=SourceType.CRYPTO_NATIVE,
            reliability_score=78,
            bias_score=20,
            history_accuracy=80,
            track_record="GOOD",
        ),
        "beincrypto.com": SourceReliabilityProfile(
            name="BeInCrypto",
            source_type=SourceType.CRYPTO_NATIVE,
            reliability_score=70,
            bias_score=25,
            history_accuracy=74,
            track_record="GOOD",
        ),
        "fxstreet.com": SourceReliabilityProfile(
            name="FXStreet",
            source_type=SourceType.MAINSTREAM,
            reliability_score=72,
            bias_score=18,
            history_accuracy=80,
            track_record="GOOD",
        ),
        "matriks.com": SourceReliabilityProfile(
            name="Matriks",
            source_type=SourceType.MAINSTREAM,
            reliability_score=68,
            bias_score=20,
            history_accuracy=75,
            track_record="GOOD",
        ),
        "muhabbit.com": SourceReliabilityProfile(
            name="Muhabbit",
            source_type=SourceType.CRYPTO_NATIVE,
            reliability_score=60,
            bias_score=30,
            history_accuracy=65,
            track_record="AVERAGE",
        ),
        "uzmancoins.com": SourceReliabilityProfile(
            name="UzmanCoin",
            source_type=SourceType.CRYPTO_NATIVE,
            reliability_score=58,
            bias_score=32,
            history_accuracy=62,
            track_record="AVERAGE",
        ),
        "bloomberg.com": SourceReliabilityProfile(
            name="Bloomberg",
            source_type=SourceType.MAINSTREAM,
            reliability_score=75,
            bias_score=20,
            history_accuracy=87,
            track_record="GOOD",
        ),
        "twitter": SourceReliabilityProfile(
            name="Crypto Twitter (Average)",
            source_type=SourceType.SOCIAL,
            reliability_score=35,
            bias_score=70,
            history_accuracy=40,
            track_record="POOR",
        ),
        "reddit": SourceReliabilityProfile(
            name="Reddit r/cryptocurrency",
            source_type=SourceType.SOCIAL,
            reliability_score=25,
            bias_score=75,
            history_accuracy=30,
            track_record="POOR",
        ),
    }

    def get_source_profile(self, source: str) -> Optional[SourceReliabilityProfile]:
        """Kaynağın güvenilirlik profilini al"""
        source_lower = source.lower()
        for key, profile in self.SOURCE_DATABASE.items():
            if key in source_lower:
                return profile
        # Default: Unknown source
        return SourceReliabilityProfile(
            name=source,
            source_type=SourceType.SOCIAL,
            reliability_score=40,
            bias_score=60,
            history_accuracy=50,
            track_record="AVERAGE",
        )

    def calculate_weighted_sentiment(
        self, news_items: List[Dict]
    ) -> Tuple[float, float]:
        """
        Kaynak güvenilirliğine göre ağırlıklı sentiment hesapla

        Args:
            news_items: [{
                'source': str,
                'sentiment': float,  # -1 to 1 (-1=bearish, 1=bullish)
                'headline': str,
            }]

        Returns:
            (weighted_sentiment: -1 to 1, confidence: 0 to 1)
        """
        if not news_items:
            return 0.0, 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        for item in news_items:
            profile = self.get_source_profile(item.get("source", "unknown"))
            weight = profile.reliability_score / 100.0
            sentiment = float(item.get("sentiment", 0))

            weighted_sum += sentiment * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0, 0.0

        weighted_sentiment = weighted_sum / total_weight
        # Normalizează
        weighted_sentiment = max(-1.0, min(1.0, weighted_sentiment))

        # Confidence = normalized total weight
        confidence = min(1.0, total_weight / len(self.SOURCE_DATABASE))

        logger.info(
            "weighted_sentiment_calculated",
            items=len(news_items),
            weighted_sentiment=round(weighted_sentiment, 3),
            confidence=round(confidence, 2),
        )

        return weighted_sentiment, confidence


class EventImpactDurationAnalyzer:
    """
    Haber etkinliğinin piyasada ne kadar süre etkili kalacağını tahmin et

    Kategoriler:
    - Flash impact (dakikalar): Social media pump
    - Short-term (saatler): Teknik etkinlikler
    - Medium-term (günler): Mandata değişiklikleri
    - Long-term (haftalar/aylar): Regulatory changes
    """

    IMPACT_DURATION_MODELS = {
        "REGULATORY_APPROVAL": {
            "base_duration_hours": 72,  # 3 gün
            "intensity": 0.9,
            "decay_rate": 0.05,  # Günlük %5 azalış
        },
        "REGULATORY_REJECTION": {
            "base_duration_hours": 120,  # 5 gün
            "intensity": 0.95,
            "decay_rate": 0.03,
        },
        "HACK_EXPLOIT": {
            "base_duration_hours": 48,  # 2 gün
            "intensity": 0.85,
            "decay_rate": 0.08,
        },
        "PARTNERSHIP_ANNOUNCEMENT": {
            "base_duration_hours": 24,  # 1 gün
            "intensity": 0.7,
            "decay_rate": 0.15,
        },
        "EARNINGS_MISS": {
            "base_duration_hours": 36,
            "intensity": 0.8,
            "decay_rate": 0.10,
        },
        "SOCIAL_MEDIA_HYPE": {
            "base_duration_hours": 4,  # Çok kısa
            "intensity": 0.5,
            "decay_rate": 0.5,  # Hızlı azalış
        },
        "MAINSTREAM_NEGATIVE": {
            "base_duration_hours": 96,
            "intensity": 0.75,
            "decay_rate": 0.04,
        },
    }

    def estimate_impact_duration(
        self, event_type: str, source_reliability: float, market_conditions: Dict = None
    ) -> Dict:
        """
        Etkinliğin piyasada ne kadar etkili kalacağını tahmin et

        Args:
            event_type: "REGULATORY_APPROVAL", "HACK_EXPLOIT", vb.
            source_reliability: 0-100 kaynak güvenilirlik skoru
            market_conditions: {
                'volatility': float,  # Current volatility
                'news_volume': int,   # News count in last 24h
            }

        Returns:
            {
                'impact_start_time': int,       # Başlama zamanı (timestamp)
                'expected_peak_time': int,      # En yüksek etki zamanı
                'half_life_hours': float,       # Etki yarı ömrü
                'expected_end_time': int,       # Etki sonu
                'current_impact_intensity': float,  # 0-1 (mevcut etki gücü)
                'impact_phase': str,            # 'RISING' | 'PEAK' | 'DECLINING' | 'RESOLVED'
            }
        """
        model = self.IMPACT_DURATION_MODELS.get(event_type, None)
        if model is None:
            logger.warning("unknown_event_type", event_type=event_type)
            model = self.IMPACT_DURATION_MODELS["PARTNERSHIP_ANNOUNCEMENT"]

        # Base model parametreleri
        base_hours = model["base_duration_hours"]
        base_intensity = model["intensity"]
        decay_rate = model["decay_rate"]

        # Kaynak güvenilirliğine göre ayarla
        reliability_factor = source_reliability / 75.0  # Normalize to ~1.0 for 75
        adjusted_hours = base_hours * reliability_factor
        adjusted_intensity = min(1.0, base_intensity * (source_reliability / 80.0))

        # Market conditions'a göre ayarla
        market_vol = 1.0
        if market_conditions:
            vol = float(market_conditions.get("volatility", 0.01))
            market_vol = 1.0 + vol  # Volatilite arttıkça adjustment
            adjusted_hours *= market_vol

        # Half-life (decay rate'ten hesapla)
        half_life_hours = adjusted_hours / 2

        # Zaman noktaları (şimdi itibaren)
        import time
        now = time.time()
        start_time = int(now)
        peak_time = int(now + (adjusted_hours / 3) * 3600)  # 1/3 noktada peak
        end_time = int(now + adjusted_hours * 3600)

        logger.info(
            "impact_duration_estimated",
            event_type=event_type,
            base_hours=base_hours,
            adjusted_hours=round(adjusted_hours, 1),
            half_life_hours=round(half_life_hours, 1),
            intensity=round(adjusted_intensity, 2),
        )

        return {
            "impact_start_time": start_time,
            "expected_peak_time": peak_time,
            "half_life_hours": round(half_life_hours, 1),
            "expected_end_time": end_time,
            "current_impact_intensity": round(adjusted_intensity, 2),
            "impact_phase": "RISING",
            "expected_duration_hours": round(adjusted_hours, 1),
        }


class FUDFilterEngine:
    """
    FUD (Fear, Uncertainty, Doubt) ve fake news'ları filtrele

    Detect:
    - Unverified claims
    - Manipulative language
    - Pump & dump coordinator posts
    - Historical misinformation sources
    """

    # Şüpheli terimler
    SUSPICIOUS_KEYWORDS = [
        "guaranteed",
        "can't lose",
        "moon shot",
        "lambo",
        "hold the line",
        "diamond hands",
        "massive pump incoming",
        "gonna explode",
        "100x potential",
        "financial advice",  # Tavsiye veriyor
    ]

    # Çoğunlukla yanlış bilgi veren kaynaklar
    FUD_SOURCES = [
        "safemoon",
        "telegram_groups",
        "discord_channels",
        "tiktok_crypto",
    ]

    def score_fud_risk(self, article: Dict) -> Dict:
        """
        Haber yazısı FUD risk skoru hesapla

        Args:
            article: {
                'source': str,
                'headline': str,
                'content': str,
                'author': str,
            }

        Returns:
            {
                'fud_risk_score': float,    # 0-100 (0=trusty, 100=pure FUD)
                'fud_indicators': list,     # Tespit edilen FUD belirtileri
                'credibility_rating': str,  # VERIFIED, LIKELY_TRUE, SUSPICIOUS, MISINFORMATION
            }
        """
        fud_score = 0
        indicators = []

        source = article.get("source", "").lower()
        headline = article.get("headline", "").lower()
        content = article.get("content", "").lower()

        # 1. Kaynak kontrolü
        if any(fud_src in source for fud_src in self.FUD_SOURCES):
            fud_score += 30
            indicators.append("known_fud_source")

        # 2. Başlık kontrolü (spam gibi)
        if headline.count("!") > 2 or headline.count("?") > 2:
            fud_score += 20
            indicators.append("excessive_punctuation")

        # 3. Büyük harf abartısı
        uppercase_ratio = sum(1 for c in headline if c.isupper()) / max(1, len(headline))
        if uppercase_ratio > 0.5:
            fud_score += 15
            indicators.append("excessive_caps")

        # 4. Şüpheli terimler
        suspicious_count = sum(1 for keyword in self.SUSPICIOUS_KEYWORDS if keyword in content)
        fud_score += min(25, suspicious_count * 5)
        if suspicious_count > 0:
            indicators.append(f"suspicious_terms({suspicious_count})")

        # 5. Haber olmayan content (kişisel görüş)
        if article.get("author", "").lower() in ["twitter_user", "reddit_user", "discord_user"]:
            fud_score += 30
            indicators.append("personal_opinion_not_news")

        # 6. Doğrulanabilir kaynak yok
        if len(article.get("sources", [])) == 0:
            fud_score += 20
            indicators.append("no_sources_cited")

        # Clamping
        fud_score = min(100, max(0, fud_score))

        # Credibility rating
        if fud_score < 20:
            credibility = "VERIFIED"
        elif fud_score < 40:
            credibility = "LIKELY_TRUE"
        elif fud_score < 70:
            credibility = "SUSPICIOUS"
        else:
            credibility = "MISINFORMATION"

        logger.info(
            "fud_risk_scored",
            fud_score=fud_score,
            indicators=indicators,
            credibility=credibility,
        )

        return {
            "fud_risk_score": fud_score,
            "fud_indicators": indicators,
            "credibility_rating": credibility,
            "confidence": round((100 - fud_score) / 100, 2),
        }
