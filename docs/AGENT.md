# AEGIS Otonom Agent

Mevcut analiz/consensus sistemi üstüne eklenen **otonom karar döngüsü**.
Sistemi değiştirmez — eklemeli (additive) bir orkestrasyon katmanıdır.

## 🛡 Güvenlik İlkeleri

1. **Güvenli-varsayılan**: `AGENT_ENABLED=false` → agent kapalı başlar.
2. **Gerçek para koruması**: Agent **asla otomatik gerçek emir göndermez**.
   - `DRY_RUN` → sadece karar günlüğü (emir yok) — **varsayılan**
   - `MANUAL_APPROVAL` → sinyali onay kuyruğuna koyar, insan onaylar
   - `AUTO_LIMITED` → "would execute" loglar; gerçek emir için ayrı, elle
     açılan execution endpoint gerekir (bu katmanda yok)
3. **Kill switch**: Her döngüde kontrol; aktifse sinyal üretilmez.
4. **Günlük limit**: `AGENT_MAX_SIGNALS_DAY` ile sinyal sayısı sınırlı.

## Mimari

```
services/agent_loop.py   → AgentOrchestrator (karar döngüsü, günlük, kalıcılık)
routes/agent.py          → kontrol endpoint'leri
main.py @startup         → bağımlılık enjeksiyonu (consensus, kuyruk, kill-switch, fiyat)
```

Agent `main.py`'yi import etmez — bağımlılıklar startup'ta enjekte edilir
(dairesel bağımlılık yok, çözük tasarım).

## Karar Döngüsü

Her `AGENT_INTERVAL_SEC` saniyede:
1. Kill switch kontrol → aktifse atla
2. Her sembol için consensus çek
3. Politika: `action != HOLD` ve `confidence ≥ min_confidence` ve
   `|score-0.5| ≥ min_score_edge` → aday sinyal
4. Cross-source fiyat doğrulaması (sapma > %1 → reddet)
5. Karar günlüğüne yaz (JSONL, kalıcı)
6. Moda göre yönlendir (yukarıdaki güvenlik tablosu)

## API

| Endpoint | Açıklama |
|---|---|
| `GET /api/agent/status` | Durum, config, heartbeat |
| `GET /api/agent/journal?limit=50` | Son kararlar |
| `POST /api/agent/start` | Döngüyü başlat |
| `POST /api/agent/stop` | Döngüyü durdur |
| `POST /api/agent/run_once` | Tek döngü (test) |
| `POST /api/agent/config` | Çalışma zamanı config (mode hariç) |

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `AGENT_ENABLED` | `false` | Açılışta otomatik başlat |
| `AGENT_INTERVAL_SEC` | `300` | Döngü aralığı (sn) |
| `AGENT_SYMBOLS` | `BTC/USDT,ETH/USDT` | İzlenen semboller |
| `AGENT_TIMEFRAME` | `4h` | Analiz timeframe |
| `AGENT_HORIZON` | `medium` | Vade |
| `AGENT_MIN_CONFIDENCE` | `0.62` | Min güven eşiği |
| `AGENT_MIN_SCORE_EDGE` | `0.08` | Min skor kenarı `|score-0.5|` |
| `AGENT_MAX_SIGNALS_DAY` | `6` | Günlük sinyal limiti |
| `EXECUTION_MODE` | `DRY_RUN` | Yönlendirme modu (güvenlik) |

## Canlıya Alma Yol Haritası (insan kararı gerektirir)

1. ✅ **Şu an**: DRY_RUN — karar günlüğü üretir, emir yok
2. **Adım 1**: `EXECUTION_MODE=MANUAL_APPROVAL` — her sinyal onaya gelir
3. **Adım 2**: Paper trading ile sinyal kalitesini doğrula (haftalar)
4. **Adım 3**: Küçük sermaye + manuel onay ile canlı test
5. **Adım 4**: (opsiyonel) Otomatik execution — ayrı, bilinçli bir karar

Her adım açık insan onayı ister. Agent kendi başına bu adımları geçemez.
