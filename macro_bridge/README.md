# AEGIS Macro Bridge

Macro Bridge, AEGIS kararlarini makro rejim ile filtreleyip pozisyon boyutu ve stop-loss onerisi ureten bir katmandir.

## Ozellikler

- Makro rejim tespiti: `liquidity_expansion`, `risk_off`, `stagflation`, `normalization`
- Makro skor hesaplama: `[-1, +1]`
- AEGIS consensus + CBR API entegrasyonu
- Sinyal dogrulama ve celiski tespiti
- Pozisyon boyutu / stop-loss / hedge kontrolu
- Streamlit dashboard

## Kurulum

```bash
cd macro_bridge
python -m pip install -r requirements.txt
```

## Calistirma

```bash
python run.py
```

## Dashboard

```bash
streamlit run dashboard/app.py --server.port 8601
```

## Test

```bash
pytest tests -q
```

## Pipeline Akisi

1. Veri cek
2. Rejim tespit et
3. Makro skor hesapla
4. AEGIS kararlarini cek
5. Sinyali dogrula
6. Pozisyon ve stop-loss hesapla
7. Hedge uyarisini uret
