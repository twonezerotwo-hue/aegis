import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

class MarketRegimeWeights(BaseModel):
    """
    AEGIS Holding - Dynamic Weight Engine Çıktı Modeli
    """
    regime: str
    onchain: float
    flow: float
    sentiment: float
    network: float

class DynamicWeightEngine:
    """
    Piyasa koşullarını (Rejim/Regime) ölçerek, AEGIS metrik kategorilerine (onchain, flow vs) 
    dinamik olarak dağıtılacak yüzdesel ağırlıkları belirler.
    """
    
    # İsterlere Göre Konfigüre Edilmiş Rejim Ağırlıkları
    REGIMES = {
        "TRENDING": {"onchain": 0.5, "flow": 0.3, "sentiment": 0.1, "network": 0.1},
        "RANGING":  {"onchain": 0.3, "flow": 0.4, "sentiment": 0.2, "network": 0.1},
        "PANIC":    {"onchain": 0.2, "flow": 0.2, "sentiment": 0.5, "network": 0.1},
        "EUPHORIA": {"onchain": 0.4, "flow": 0.2, "sentiment": 0.3, "network": 0.1}
    }

    @classmethod
    def determine_weights(cls, adx: float, bb_width_pct: float, funding_rate: float, fear_greed: float) -> MarketRegimeWeights:
        """
        Rejim tespit algoritması. 
        Girdiler:
        - adx: Trend gücünü ölçer (Average Directional Index)
        - bb_width_pct: Yüzde cinsinden Bollinger Band Genişliği
        - funding_rate: Fonlama oranı (ikincil check, ileride eklenebilir)
        - fear_greed: Korku (0) ve Açgözlülük (100) endeksi
        
        Öncelik Sırası:
        1. Ekstrem duygu durumları (PANIC veya EUPHORIA) marketin her zaman en dominant rejimini oluşturur.
        2. Ekstrem bir duygu yoksa varlığın belirgin trendi (TRENDING).
        3. Trend yoksa, konsolidasyon (RANGING) bölgesi.
        """
        
        regime = "RANGING" # Güvenli (Default) yapı
        
        # 1. Öncelik: Aşırı Duygu Durumları (Extreme Sentiment)
        if fear_greed < 20:
            regime = "PANIC"
        elif fear_greed > 80:
            regime = "EUPHORIA"
            
        # 2. Öncelik: Kararlı Trend Durumu (Strong Trend)
        elif adx > 25:
            regime = "TRENDING"
            
        # 3. Öncelik: Kısa Sıkışma veya Yatay Konsolidasyon
        elif bb_width_pct < 3.0:
            regime = "RANGING"
            
        # 4. Hiçbir şarta uymayan Araftaki piyasa durumu varsayılan (RANGING) devam eder.

        weights = cls.REGIMES[regime]
        
        # Toplamın matematitksel olarak 1.0 (Yani %100) olma kontrolü (Safety)
        total = round(sum(weights.values()), 3)
        if total != 1.0:
            logger.warning("weights_sum_mismatch", regime=regime, total=total)
        
        logger.info(
            "market_regime_identified", 
            regime=regime, 
            adx=adx, 
            bb_width=bb_width_pct, 
            fg=fear_greed, 
            weights=weights
        )
        
        return MarketRegimeWeights(
            regime=regime,
            onchain=weights["onchain"],
            flow=weights["flow"],
            sentiment=weights["sentiment"],
            network=weights["network"]
        )
