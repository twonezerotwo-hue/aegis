from metrics.normalizers import Normalizer

def test_bounded_linear_normalization():
    # 100-200 arasında tam orta değer 50'ye denk gelir.
    res = Normalizer.process(150, method="bounded_linear", min_val=100, max_val=200)
    assert res == 50.0
    
    # 200'ü aşan değer üst limite (100) kliplenir.
    res_max = Normalizer.process(300, method="bounded_linear", min_val=100, max_val=200)
    assert res_max == 100.0

def test_inverse_normalization():
    # Değer %80 ise ters çevrilip (100 - X) %20 olmalıdır. Bearish inversiyonları için kullanılır.
    res = Normalizer.process(80, method="inverse")
    assert res == 20.0

def test_percentile_30d_series():
    # Güncel veri olan 50 değeri listenin maksimimu olduğu için p=%100 çıkar
    data = [10, 20, 30, 40, 50]
    res = Normalizer.process(data, method="percentile_30d")
    assert res == 100.0
