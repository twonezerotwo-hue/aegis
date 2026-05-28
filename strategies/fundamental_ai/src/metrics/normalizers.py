import numpy as np
from typing import Union, List
from scipy.stats import percentileofscore

class Normalizer:
    """
    AEGIS Holding - Metrik Normalizasyon Motoru (0-100 Skalası)
    Gelen ham verileri (time-series veya single float) çeşitli metodolojilerle standardize eder.
    """
    
    @classmethod
    def process(
        cls, 
        raw_value: Union[float, List[float], np.ndarray], 
        method: str, 
        lookback_days: int = 30,
        **kwargs
    ) -> float:
        """
        Ana yönlendirici (Router) metodu.
        
        Parametreler:
        - raw_value: Tek bir değer veya güncel metrik sondaki öğe olacak şekilde tarihsel dizi. 
        - method: 'zscore_to_0100', 'percentile_30d', 'bounded_linear', 'sigmoid', 'inverse'
        - lookback_days: Tarihsel veriler dizisi iletildiğinde, hesaplanacak gün sayısı.
        """
        if isinstance(raw_value, (list, np.ndarray)):
            data = np.array(raw_value, dtype=float)
            # Tarihsel veriyi lookback limitiyle kes
            if len(data) > lookback_days:
                data = data[-lookback_days:]
            val = data[-1]
        else:
            val = float(raw_value)
            data = np.array([val])

        if method == "zscore_to_0100":
            return cls.zscore_to_0100(data, kwargs.get("clip_limit", 3.0))
        elif method == "percentile_30d":
            return cls.percentile(data)
        elif method == "bounded_linear":
            return cls.bounded_linear(val, kwargs.get("min_val", 0.0), kwargs.get("max_val", 100.0))
        elif method == "sigmoid":
            return cls.sigmoid(val, kwargs.get("center", 0.0), kwargs.get("steepness", 1.0))
        elif method == "inverse":
            return cls.inverse(val)
        else:
            raise ValueError(f"Bilinmeyen normalize metodu: {method}")

    @staticmethod
    def zscore_to_0100(data: np.ndarray, clip_limit: float = 3.0) -> float:
        """
        Gelen dizinin Standart Z-Score sapmasını bulur.
        [ -clip_limit, +clip_limit ] aralığındaki z-score değerini, [0, 100] formuna sıkıştırır.
        """
        if len(data) < 2:
            return 50.0  # Karar verilemeyecek kadar az veri ise nötr(50) döner.
            
        x = data[-1]
        mu = np.mean(data)
        sigma = np.std(data)
        
        if sigma == 0:
            return 50.0
            
        z = (x - mu) / sigma
        z_clipped = np.clip(z, -clip_limit, clip_limit)
        
        # Min(-3) Max(3) varsayımını Min(0) Max(100) aralığına çeviriyoruz
        normalized = ((z_clipped + clip_limit) / (2 * clip_limit)) * 100.0
        return float(np.round(normalized, 2))

    @staticmethod
    def percentile(data: np.ndarray) -> float:
        """
        Sondaki değerin (güncel değer), iletilen dizi serisi içindeki Yüzdelik (Rank) dilimini bulur.
        """
        if len(data) < 2:
            return 50.0
            
        x = data[-1]
        p = percentileofscore(data, x, kind='rank')
        return float(np.round(p, 2))

    @staticmethod
    def bounded_linear(val: float, min_val: float, max_val: float) -> float:
        """
        Doğrusal Lineer oranlama (Min-Max Scaling). Belirlenmiş range dışındakileri kırpar (Clip).
        """
        if max_val == min_val:
            return 50.0
            
        val_clipped = np.clip(val, min_val, max_val)
        normalized = ((val_clipped - min_val) / (max_val - min_val)) * 100.0
        return float(np.round(normalized, 2))

    @staticmethod
    def sigmoid(val: float, center: float = 0.0, steepness: float = 1.0) -> float:
        """
        Lojistik dönüşüm. Veriyi doğrusal olmayan pürüzsüz S kavisinde dağılıma oturtur. 
        Hızlı artış ve stabil azalış gösteren non-linear piyasa indikatörleri için idealdir.
        """
        s = 1.0 / (1.0 + np.exp(-steepness * (val - center)))
        return float(np.round(s * 100.0, 2))

    @staticmethod
    def inverse(val: float) -> float:
        """
        Normalize edilmiş bir metrik değerini tam tersine çevirir.
        Bearish bir artış sinyalinin, sistem için düşüş ifade etmesini (inversin) sağlar.
        Örnek: Borsalara çekilen coin artışı aslında = ayı sinyali, yani 0'a yakınsın.
        """
        inversed = 100.0 - np.clip(val, 0.0, 100.0)
        return float(np.round(inversed, 2))
