# AEGIS Proje İnceleme Raporu

Tarih: 2026-04-20
Kapsam: Kod tabanı, servis mimarisi, dağıtım yapısı, test olgunluğu, operasyonel riskler
Depo yolu: `C:\Users\twone\Desktop\aegis_codex`

## 1. Yönetici Özeti

AEGIS, mikro servis tabanlı bir kripto işlem ve karar destek platformu olarak tasarlanmış. Ana omurga; teknik analiz (`touche_ai`), temel/on-chain analiz (`fundamental_ai`), makro risk (`sentinel_ai`), nicel/futures likidite katmanı (`quantum_ai`), haber analizi (`news-ai-limited`), merkezi karar verme (`consensus_engine`), optimizasyon (`optimizer_service`), React tabanlı dashboard ve gözlemlenebilirlik yığını (Prometheus, Grafana, exporter’lar, Pushgateway) etrafında kurulmuş.

Kod tabanı geniş ve niyet açısından iddialı. Mimari olarak servis sınırları belirgin, Docker Compose ile tam platform orkestrasyonu düşünülmüş ve gözlemlenebilirlik katmanı erken aşamada sisteme eklenmiş. Bununla birlikte üretim güvenilirliğini doğrudan etkileyen birkaç kritik sorun mevcut:

- Repo kökünde düz metin API anahtarları ve işlem anahtarları bulunuyor.
- `sentinel_ai` içinde gerçek bir Python syntax hatası var; bu modülün bir alt bileşeni derlenemiyor.
- `optimizer_service`, mevcut YAML şemasını yanlış okuyup canlı ağırlıkları değil fallback değerleri kullanıyor.
- Optimizasyon/backtest motoru şu an sentetik trade üretimiyle çalışıyor; gerçek tarihsel veri entegrasyonu tamamlanmış görünmüyor.
- Testler dağınık; bir kısmı gerçek test yerine canlı servislere vuran doğrulama scripti niteliğinde.

Kısacası proje mimari olarak güçlü bir prototip/ileri seviye PoC görüntüsü veriyor, ancak üretim ortamına tam güvenle alınmadan önce güvenlik, doğrulama ve bazı çekirdek entegrasyon hatalarının kapatılması gerekiyor.

## 2. Kod Tabanı Özeti

Üçüncü parti klasörler (`node_modules`, `__pycache__`, rapor çıktıları) hariç yaklaşık görünüm:

- 475 dosya
- 144 dizin
- 298 Python dosyası
- Yaklaşık 44.322 satır Python
- 75 TypeScript/TSX dosyası
- Yaklaşık 10.945 satır TypeScript/TSX
- Test klasörleri depo geneline dağılmış durumda

En büyük ve bakım maliyeti yüksek görünen sıcak noktalar:

- `dashboard_react/backend/routes/backtest_routes.py`
- `consensus_engine/main.py`
- `dashboard_react/backend/main.py`
- `strategies/touche_ai/src/engine/unified_optimizer.py`
- `dashboard_react/frontend/src/pages/BacktestV2.tsx`
- `dashboard_react/frontend/src/services/apiV2.ts`
- `optimizer_service/src/optimizer_engine.py`

Bu dağılım, ürünün esas karmaşıklığının backtest/gateway tarafı, karar motoru ve gösterge panellerinde toplandığını gösteriyor.

## 3. Mimari Resim

### 3.1 Platform topolojisi

`docker-compose.yml` içinde 22 servis tanımlı:

- Veri katmanı: PostgreSQL, Redis, ClickHouse, Qdrant
- Monitoring: Prometheus, Grafana, postgres-exporter, redis-exporter, Pushgateway, metrics-pusher
- Geçit/erişim: Nginx
- Çekirdek AI servisleri: Touche, Fundamental, Quantum, Sentinel, Consensus, News AI, Analyzer AI
- Uygulama yüzeyi: Dashboard backend, Dashboard frontend
- Yardımcı servis: Optimizer, Macro Bridge

Bu yapı, sistemin yalnızca bir API değil; veri, karar, arayüz ve operasyon katmanlarını birlikte ele alan tam bir platform olarak tasarlandığını gösteriyor.

### 3.2 Ana veri akışı

İncelemeye göre beklenen akış kabaca şöyle:

1. Piyasa ve makro veri ilgili modüller tarafından toplanır.
2. `touche_ai`, `fundamental_ai`, `quantum_ai`, `sentinel_ai`, `news-ai-limited` bağımsız skor/sinyal üretir.
3. `consensus_engine`, bu modül skorlarını rejim ve risk bağlamına göre birleştirir.
4. `dashboard_react/backend`, bu servislerin önünde gateway ve toplama katmanı gibi davranır.
5. `dashboard_react/frontend`, gateway üzerinden canlı dashboard ve backtest ekranlarını besler.
6. `optimizer_service`, backtest motorunu kullanarak ağırlık ve eşik optimizasyonu yapmayı hedefler.
7. Prometheus/Grafana ile metrikler toplanır ve izlenir.

## 4. Modül Bazlı İnceleme

### 4.1 `consensus_engine`

Rol:
- Beş modülden gelen sinyalleri toplayan ve nihai aksiyonu üreten merkez
- Risk parametreleri, çoklu zaman dilimi doğrulaması, meta skor ve attribution altyapısı içeriyor

Güçlü yanlar:
- `config/consensus_weights.yaml` ile ağırlıklar ve rejim bazlı konfigürasyon dışsallaştırılmış
- Rejim ağırlıkları, korelasyon override’ları ve event override’ları aynı dosyada toplanmış
- Prometheus metrikleri doğrudan servis içine eklenmiş

Dikkat çeken noktalar:
- `main.py` oldukça büyük ve birçok sorumluluğu tek dosyada topluyor
- CBR fallback ve meta scoring katmanı eklenmiş, fakat servis büyüdükçe bakım maliyeti artıyor

### 4.2 `strategies/touche_ai`

Rol:
- Teknik analiz ve çok fazlı scoring motoru
- Canlı veri için Binance fetcher ve mock fallback desteği

Güçlü yanlar:
- Fazlara ayrılmış yapı (`phase1_liquidity` ... `phase7_macro`)
- İndikatör katmanı modüler
- Canlı veri ile fallback arasında açık ayrım var

Zayıf yanlar:
- `main.py` ve `unified_optimizer.py` büyümüş durumda
- Mock/canlı mod geçişi ve logging katmanı yer yer karmaşık

### 4.3 `strategies/fundamental_ai`

Rol:
- On-chain ve temel veri odaklı skor üretimi
- Glassnode/Twelve Data benzeri sağlayıcılardan veri tüketimi

Güçlü yanlar:
- Client, scoring ve engine katmanları ayrılmış
- Test klasörü var

Sınırlamalar:
- API anahtarı yoksa fallback moduna düşüyor; bu pratik ama üretim benzeri doğrulama için yetersiz olabilir

### 4.4 `strategies/sentinel_ai`

Rol:
- Makro risk, olay riski ve rejim tespiti
- Korelasyon analizi ve risk multiplier üretimi

Güçlü yanlar:
- Makro endpoint yüzeyi zengin
- Korelasyon motoru var
- Dashboard ile entegre düşünülmüş

Kritik sorun:
- `src/macro_indicators/crypto_specific.py` derlenemiyor; dosyada gerçek syntax hatası var

### 4.5 `strategies/quantum_ai`

Rol:
- Futures, likidite, funding ve market-making bakış açısı

Güçlü yanlar:
- Risk/likidite filtresi olarak kullanılabilecek endpointler mevcut
- Futures metrikleri ve inventory/risk mantığı ayrı klasörlerde

Sınırlamalar:
- Canlı veri yoksa deterministic fallback’a dönmesi ürün davranışını ciddi şekilde değiştiriyor

### 4.6 `modules/news-ai-limited`

Rol:
- Haber, kaynak güvenilirliği, deduplication ve sentiment pipeline’ı

Güçlü yanlar:
- Source registry, dedup ve scoring katmanları mevcut
- Redis bağlantısı yoksa bellek içi moda düşebiliyor

Zayıf yanlar:
- `periodic_analysis_task()` içinde analiz ve publish akışı halen `TODO`
- Yani servis iskeleti güçlü olsa da tam otomatik sürekli analiz döngüsü tamamlanmış görünmüyor

### 4.7 `optimizer_service`

Rol:
- Optuna tabanlı ağırlık/eşik optimizasyonu
- Walk-forward tipi değerlendirme üretme hedefi

Güçlü yanlar:
- API yüzeyi düzenli
- Optuna pruner/sampler kullanımı düşünülmüş
- Trial logging ve Prometheus metrikleri var

Temel sınırlamalar:
- Ağırlıkları yanlış YAML anahtarından okuyor
- Backtest motoru gerçek trade verisi yerine sentetik trade üretiyor
- Bu nedenle optimize edilen sonuçların canlı stratejiye ne kadar temsil gücü taşıdığı sınırlı

### 4.8 `dashboard_react`

Rol:
- Sistem arayüzü
- Backend tarafı gateway/aggregation, frontend tarafı React/Vite dashboard

Backend:
- Çok sayıda route ve servis adapter’ı içeriyor
- Rejim bazlı ağırlık yükleme ve backtest entegrasyonu var

Frontend:
- React 18 + Vite + TypeScript + Tailwind
- V1 ve V2 ekranlar bir arada tutuluyor
- `DashboardV2`, `BacktestV2`, optimizer ve paper trading bileşenleri var

Gözlem:
- Ürün UI katmanı ciddi şekilde büyümüş ve bakım için artık açık bir modül sınırlandırmasına ihtiyaç duyuyor

### 4.9 `macro_bridge`

Rol:
- Makro rejim ile AEGIS kararlarını filtreleyen ayrı bir köprü katmanı
- Streamlit dashboard içeriyor

Değerlendirme:
- Ana platform dışında ama aynı problem uzayına hizmet eden yan bir uygulama
- Mantıksal olarak yararlı, fakat ana dashboard ve sentinel fonksiyonlarıyla kısmen örtüşüyor

## 5. Dağıtım ve Operasyon

### 5.1 Docker ve konteynerleşme

Pozitif noktalar:

- Compose orkestrasyonu kapsamlı
- Servis healthcheck’leri büyük ölçüde eklenmiş
- Monitoring stack hazır
- Frontend ve backend ayrı konteynerler halinde düşünülmüş

Riskler:

- Bazı bileşenler volume mount olmadan eksik kalıyor; örneğin dashboard backend, `strategies` klasörünü çalışma anında compose volume’u ile alıyor
- Bu durum tek başına image çalıştırmayı zorlaştırıyor

### 5.2 Nginx gateway

Nginx konfigürasyonu temel reverse proxy işlevini sağlıyor. Touche, Fundamental, Quantum, Sentinel ve Consensus için ayrı upstream tanımları var. Basit rate limiting mevcut. Bu, güvenlik için iyi bir başlangıç ancak auth, TLS ve ayrıntılı erişim politikaları görünmüyor.

### 5.3 Gözlemlenebilirlik

Olumlu taraf:

- Her ana servis Prometheus metriği yayımlıyor
- Grafana provisioning dosyaları var
- Exporter’lar ayrı konteynerlerde tanımlı

Not:

- Sağlık kontrollerinin bir kısmı gerçek işlev yerine `exit 0` dönüyor; bu, “container ayakta mı?” ile “servis gerçekten sağlıklı mı?” ayrımını zayıflatıyor

## 6. Test ve Doğrulama Durumu

### 6.1 Mevcut görünüm

Test dosyaları aşağıdaki alanlara dağılmış:

- `consensus_engine/tests`
- `macro_bridge/tests`
- `modules/news-ai-limited/tests`
- `strategies/*/tests`
- kök `tests/`

Bu olumlu; çünkü ekip test yazmış. Ancak test stratejisi homojen değil.

### 6.2 Doğrudan doğrulama bulguları

Yapılan teknik doğrulamalar:

- `pytest` doğrudan çalıştırılamadı çünkü çalışma ortamında `pytest` kurulu değildi
- Buna karşın yerleşik Python 3.12 runtime ile `compileall` çalıştırıldı
- `compileall`, büyük bölümün parse edilebildiğini ama `sentinel_ai` altında syntax hatası olduğunu gösterdi

### 6.3 Test olgunluğu değerlendirmesi

Kök `tests` klasöründeki bazı dosyalar klasik pytest unit testi değil; örneğin `tests/test_v2_consistency.py` doğrudan `localhost:8502` ve `localhost:3001` üstüne istek atan, çıktı yazdıran bir doğrulama scripti. Bu yaklaşım manuel smoke test için yararlı ama CI/CD içinde kararlı otomatik test olarak zayıf.

Sonuç:

- Test kapsamı niyet olarak var
- Otomasyon kalitesi ve izolasyon seviyesi ise karışık
- Unit, integration ve live smoke test sınırları net değil

## 7. Kritik Bulgular

### 7.1 Düz metin gizli anahtarlar repo kökünde duruyor

`/.env` içinde gerçek görünümlü servis anahtarları ve işlem anahtarları bulunuyor. Bu, bu rapordaki en kritik bulgudur.

Etkisi:

- Anahtar sızıntısı
- Testnet/gerçek hesap erişim riski
- Yanlışlıkla canlı çağrı ve emir riski
- Repo paylaşımı veya ekran görüntüsüyle istem dışı ifşa

Kanıt:

- `.env:2`
- `.env:3`
- `.env:8`
- `.env:9`
- `.env:10`
- `.env:27`

Not:

- Bu rapor güvenlik nedeniyle değerleri tekrar etmiyor

### 7.2 `sentinel_ai` içinde syntax hatası var

`strategies/sentinel_ai/src/macro_indicators/crypto_specific.py:345` satırında `24h_change=...` kullanımı Python’da geçersiz. Sayıyla başlayan keyword argüman adı derlemeyi kırıyor.

Etkisi:

- İlgili modül import/çalıştırma sırasında hata verebilir
- Sentinel alt bileşeninin bir kısmı tamamen devre dışı kalabilir
- Test ve dağıtım güvenilirliği düşer

Kanıt:

- `strategies/sentinel_ai/src/macro_indicators/crypto_specific.py:342-347`
- `compileall` çıktısı bu dosyada `SyntaxError: invalid decimal literal` verdi

### 7.3 Optimizer, canlı consensus ağırlıklarını yanlış okuyor

`optimizer_service/main.py` içindeki `_current_weights()`, YAML’den `weights` anahtarını okumaya çalışıyor. Oysa `consensus_engine/config/consensus_weights.yaml` dosyasında üst seviye anahtar `modules` ve `regime_weights`.

Etkisi:

- Optimizer gerçekte kullanılan ağırlıkları değil fallback değerleri baz alıyor olabilir
- Optimize edilen sonuç ile çalışan strateji arasında şema uyumsuzluğu doğar
- Sonuçların uygulanabilirliği düşer

Kanıt:

- `optimizer_service/main.py:45-55`
- `consensus_engine/config/consensus_weights.yaml:1-7`
- `consensus_engine/config/consensus_weights.yaml:14-61`

### 7.4 Optimizer/backtest hâlen sentetik trade üretimine dayanıyor

`optimizer_service/src/backtest_engine.py`, gerçek trade/history entegrasyonu yerine deterministic mock trade üretimi yapıyor ve `run_simple()` bu veriyi kullanıyor.

Etkisi:

- Backtest/optimizasyon sonuçları gerçek piyasa davranışını tam temsil etmeyebilir
- Optuna iyi görünen ama sahada karşılığı olmayan parametreler üretebilir
- Ürün yöneticisi veya yatırım mantığı için yanlış güven hissi doğurabilir

Kanıt:

- `optimizer_service/src/backtest_engine.py:70-123`
- `optimizer_service/src/backtest_engine.py:239-260`

### 7.5 CORS yapılandırması güvenlik ve tarayıcı davranışı açısından sorunlu

Dashboard backend, `allow_credentials=True` ile birlikte `allow_origins=[..., "*"]` kullanıyor.

Etkisi:

- Tarayıcı tarafında credential’lı isteklerde beklenmedik CORS davranışı oluşabilir
- Üretim güvenliği açısından gereğinden geniş yüzey açılır

Kanıt:

- `dashboard_react/backend/main.py:150-157`

## 8. Orta Seviye Bulgular ve Mimari Borç

### 8.1 `Dockerfile.dashboard` büyük olasılıkla eski/stale

Bu dosya `dashboard/requirements.txt` ve `dashboard/app_pro.py` gibi depoda görünmeyen yolları referanslıyor. Ayrıca compose içinde ilgili dashboard servisi zaten “deprecated” olarak yorum satırına alınmış.

Kanıt:

- `Dockerfile.dashboard:6`
- `Dockerfile.dashboard:10-12`
- `docker-compose.yml:178-190`

Değerlendirme:

- Aktif üretim akışında kullanılmıyor olabilir
- Fakat repoda tutulduğu için yeni geliştiricileri yanıltır

### 8.2 Haber servisi sürekli analiz döngüsünde tam uygulanmamış görev taşıyor

`modules/news-ai-limited/src/main.py` içindeki periyodik görevde “actual analysis and publish to Redis” halen TODO.

Kanıt:

- `modules/news-ai-limited/src/main.py:39-56`

Anlamı:

- Haber servisi tam otomatik yayın moduna geçmiş görünmüyor
- Yapı hazır, ama iş mantığının bir kısmı beklemede

### 8.3 Kök test klasörü kısmen canlı smoke script’lerden oluşuyor

Örneğin `tests/test_v2_consistency.py`, pytest assertion yerine yerel servis endpoint’lerine HTTP isteği atıyor ve çıktı yazdırıyor.

Kanıt:

- `tests/test_v2_consistency.py:8-24`
- `tests/test_v2_consistency.py:76-111`

Değerlendirme:

- Faydalı doğrulama aracı
- Ama CI dostu, izole ve deterministik test sınıfına girmiyor

## 9. Güçlü Yönler

- Servis ayrımı düşünülmüş; problem alanı modüllere bölünmüş
- Gözlemlenebilirlik katmanı erken eklenmiş
- Rejim tabanlı ağırlıklandırma ve override yaklaşımı olgun bir tasarım işareti
- React dashboard tarafı sadece basit panel değil; optimizer, paper trading, backtest ve canlı veri ekranlarını içeriyor
- Farklı modüllerde test yazma kültürü mevcut
- Docker Compose ile tek komutta büyük sistem ayağa kaldırılabilecek şekilde tasarlanmış

## 10. Genel Yargı

AEGIS, teknik olarak “basit bot” seviyesinin üstünde bir çalışma. Tasarım dili; modüler, veri odaklı, rejim duyarlı ve operasyonel gözlemlenebilirliği ciddiye alan bir ürün vizyonu gösteriyor. Bu önemli bir artı.

Buna karşılık mevcut haliyle sistemde üç ana kırılganlık var:

1. Güvenlik hijyeni yeterli değil.
2. Doğrulama zinciri kısmen sentetik/veri bağımlı ve tam otomasyon seviyesinde değil.
3. Bazı modüller ve dosyalar aynı anda hem aktif ürün hem de birikmiş legacy kod taşıyor.

Bu nedenle proje “mimari olarak güçlü, operasyonel olarak henüz tam sertleşmemiş” kategorisinde değerlendirilebilir.

## 11. Öncelikli Öneriler

### İlk 24 saat içinde

1. `.env` içindeki tüm gerçek anahtarları iptal et veya döndür.
2. Repo dışı secret management kullan.
3. `crypto_specific.py` syntax hatasını düzelt.
4. `DRY_RUN=false` ve anahtar birlikteliğini yeniden gözden geçir.

### İlk 1 hafta içinde

1. `optimizer_service/main.py` içindeki YAML okuma şemasını gerçek config ile hizala.
2. Optimizer için gerçek veri kaynağı ile sentetik veri yolunu açık feature flag’lerle ayır.
3. Kök `tests/` altındaki script testleri `smoke/` veya `scripts/` benzeri ayrı bir yere taşı.
4. CORS yapılandırmasını açık domain listesi ile daralt.
5. Legacy Dockerfile ve deprecated dashboard parçalarını temizle veya `archive/` altına taşı.

### İlk 2-4 hafta içinde

1. `consensus_engine/main.py` ve dashboard backend’i daha küçük servis/modül birimlerine böl.
2. CI pipeline’a en az şu doğrulamaları ekle:
   - Python syntax/compile check
   - pytest unit suite
   - frontend typecheck/build
   - temel container build smoke test
3. Gerçek tarihsel veri ile backtest doğrulama zinciri kur.
4. Sağlık kontrollerini `exit 0` yerine gerçek servis fonksiyonlarıyla değiştir.

## 12. Bu İncelemede Yapılan Doğrulamalar

- Dosya/dizin haritası çıkarıldı
- Ana FastAPI giriş noktaları okundu
- React frontend ve gateway/backend yapısı incelendi
- Compose, Dockerfile, Nginx ve Prometheus yapılandırmaları incelendi
- Test dosyalarının yapısı örneklenerek değerlendirildi
- Yerleşik Python runtime ile `compileall` çalıştırıldı
- `pytest` doğrudan çalıştırılamadı çünkü ortamda `pytest` paketi yüklü değildi
- Node/TypeScript doğrulaması sandbox yol çözümlemesi nedeniyle tam tamamlanamadı

## 13. Sonuç

Bu repo, ciddi emek verilmiş, geniş kapsamlı ve modüler bir işlem platformu iskeleti sunuyor. Ancak üretim sertliği açısından şu anda en çok güvenlik, config uyumu, test ayrımı ve gerçek veri doğrulaması alanlarında güçlendirmeye ihtiyaç duyuyor. Bu alanlar toparlandığında proje, mevcut mimari avantajlarını çok daha iyi taşıyabilecek durumda.
