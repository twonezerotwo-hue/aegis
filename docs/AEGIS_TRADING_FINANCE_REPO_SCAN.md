# AEGIS Trading ve Finans Repo Tarama Raporu

Tarih: 2026-06-06  
Kapsam: GitHub uzerindeki yuksek sinyalli trading, quantitative finance, backtesting, market data, teknik analiz ve portfoy/risk kutuphaneleri. Bu rapor "tum GitHub" yerine pratik ve denetlenebilir bir filtre kullandi: yildiz sayisi, guncel aktivite, lisans okunabilirligi, Python ekosistemi, AEGIS'e execution tasimadan katki saglama potansiyeli.

## AEGIS icin ana sonuc

AEGIS'i daha verimli hale getirmenin en dogru yolu yeni bir trading botu iceri almak degil. Guvenli cekirdek zaten signal-only kalmali. En iyi kazanc, uc ayri katmani temiz ayirmaktan gelir:

1. `aegis_core`: sadece veri butunlugu, skor, risk sarmali, kill-switch, OwnerBrief ve audit. Execution yok.
2. `aegis_research` veya `research_lab`: backtest, model arastirma, performans metrikleri, auto-labeling, agirlik onerileri.
3. legacy runtime: paper/live execution, optimizer, broker, order routing gibi riskli yuzeyler. Varsayilan kapali, acik etiketli ve guvenli cekirdekten izole.

Bu ayrim yapilmadan Freqtrade, Hummingbot, Lean, OctoBot gibi buyuk bot/engine repolarini birlestirmek AEGIS'i karmasiklastirir ve mevcut signal-only kurallari bozar.

## AEGIS'e ne ekleyecegiz, ne cikaracagiz

Burada "cikaracagiz" fiziksel silme degil, varsayilan AEGIS/safe runtime'dan cikarma ve izole etme anlamina gelir. Legacy runtime explicit istenmedikce silinmeyecek.

### Eklenecekler

1. `aegis_research/` paketi
   - `aegis_core` disinda duracak.
   - Backtest, performans metrikleri, outcome labeling ve kalibrasyon burada olacak.
   - Safe core'a execution, broker, order veya position sizing tasimayacak.

2. Agent outcome store
   - Her agent sinyal adayini `signal_id`, timeframe, confidence, edge, module scores, data status ve timestamp ile kaydedecek.
   - 15m, 1h, 4h, 1d gibi ileri ufuklarda sonucu etiketleyecek.
   - "Neden sinyal uretmedi?" cevabini journal'dan okunur hale getirecek.

3. Performans metrik katmani
   - Ilk aday: [quantstats](https://github.com/ranaroussi/quantstats) veya [empyrical](https://github.com/quantopian/empyrical).
   - Hit rate, Brier score, calibration error, drawdown impact, MAE/MFE, confidence bucket performansi hesaplanacak.
   - Cikti sadece rapor/evidence olacak.

4. Weight ve threshold suggestion katmani
   - Agent kendi basina production config yazmayacak.
   - `proposed_weights`, `proposed_thresholds`, `sample_size`, `expected_improvement`, `risk_warning` uretecek.
   - Once shadow modda test edilecek, sonra owner onayi ile aktif edilecek.

5. Read-only data adapter katmani
   - Ilk dusuk risk adaylari: [yfinance](https://github.com/ranaroussi/yfinance), [FinanceToolkit](https://github.com/JerBouma/FinanceToolkit), [ta](https://github.com/bukosabino/ta).
   - Bu veriler research/dev icin olacak; live/verified gibi gosterilmeyecek.
   - Her veri `source`, `source_timestamp`, `data_status`, `verified`, `fallback_used` tasiyacak.

6. Dashboard kontrol sekmesi revizyonu
   - Agent odakli tek ekran: agent status, son dongu, neden sinyal yok, confidence/edge, data freshness, shadow vs live config.
   - "Final karar" dili kaldirilacak; "signal candidate/evidence" dili kullanilacak.
   - Fallback veya mock veri varsa kartin ustunde gorunur olacak.

7. Policy testleri
   - Safe endpoint'lerde forbidden field testi.
   - Production requirements'a GPL/AGPL/NOASSERTION dependency eklenmedigini kontrol eden statik test.
   - Agent'in otomatik config yazamadigini dogrulayan test.

### Cikarilacak veya izole edilecekler

1. `aegis_core` icinden cikacak/uzak tutulacaklar
   - Broker, paper trading, order router, execution engine, optimizer, bounded updater, final allocator.
   - `action`, `buy`, `sell`, `hold`, `rebalance`, `position_size`, `order`, `broker`, `execution` alanlari.

2. Varsayilan dashboard runtime'dan izole edilecekler
   - `dashboard_react/backend/routes/paper_trading.py`
   - `dashboard_react/backend/routes/paper_autotrader_routes.py`
   - `dashboard_react/backend/routes/optimizer_agent_routes.py`
   - `dashboard_react/backend/main.py` icindeki live execution ve optimizer endpoint yuzeyleri.
   - Bunlar silinmeyecek; explicit feature flag olmadan acilmamalari saglanacak.

3. Safe import zincirinden uzak tutulacak legacy moduller
   - `strategies/execution_engine.py`
   - `strategies/quantum_ai/src/execution/order_router.py`
   - `macro_bridge/executor/trade_executor.py`
   - `consensus_engine/src/final_allocator.py`
   - `consensus_engine/src/position_optimizer.py`
   - `consensus_engine/src/bounded_updater.py`
   - `optimizer_service/`

4. UI dilinden cikarilacaklar
   - Safe/agent ekranlarinda "AL", "SAT", "HOLD final karar", "pozisyon ac", "rebalance yap" dili.
   - Yerine: "bullish candidate", "bearish candidate", "no candidate", "insufficient data", "evidence", "risk warning".

5. Repo entegrasyonundan uzak tutulacaklar
   - Freqtrade, Hummingbot, OctoBot, Lumibot gibi full trading botlar.
   - AGPL/GPL kodlarin dogrudan vendoring edilmesi.
   - `NOASSERTION` lisansli repolarin lisans netlesmeden dependency yapilmasi.

## En iyi gelistirme stratejisi

### 1. Cekirdegi sade tut

Oncelik `aegis_core` icinde bitti: sinyal-only davranis, forbidden field kontrolleri, fallback olmayan yetersiz-veri durumu. Bundan sonra buraya yeni repo kodu eklenmemeli. Sadece adapter arayuzleri eklenebilir:

- `DataSnapshot`: kaynak, timestamp, freshness, status, warnings.
- `ModuleEvidence`: modul skoru, confidence, provenance, eksik veri nedenleri.
- `BacktestEvidence`: offline test sonucu, tarih araligi, sample size, metrikler.
- `WeightSuggestion`: otomatik uygulanmayan, owner onayi bekleyen oneriler.

### 2. Agent'i kendi kendine egitme yerine "kendini kalibre eden" yap

Canli agent kendi basina agirlik/config yazmamali. Dogru model:

- Sinyal adayi uretir.
- Sonraki 1h, 4h, 1d gibi ufuklarda sonucu etiketler.
- Modul bazinda Brier score, hit rate, drawdown etkisi, calibration error, sample size hesaplar.
- Yeni agirlik ve esik deger onerisi uretir.
- Oneriyi `shadow` modda test eder.
- Owner onayi veya release gate olmadan production config degismez.

Bu yapi AEGIS'in otomatik iyilesmesini saglar ama kontrolsuz trade motoruna donusturmez.

### 3. Dashboard temizligi

Dashboard'da iki dil ayrilmali:

- `Signal candidate`, `evidence`, `bias`, `confidence`, `edge`: guvenli.
- broker, order, quantity, position size, live execution: legacy/paper alaninda ve varsayilan kapali.

Mevcut kodda `dashboard_react/backend/main.py`, `routes/stream.py`, paper/optimizer route'lari ve legacy strateji modulleri hala riskli kavramlari tasiyor. Bunlar silinmeden once:

- route bazli feature flag zorunlu olmali,
- her fallback `FALLBACK`, `PARTIAL_FALLBACK`, `MOCK`, `UNKNOWN` etiketi ile gorunmeli,
- safe endpoint testleri forbidden field cikmadigini dogrulamali,
- UI'da agent karar kartlari "final karar" gibi gorunmemeli.

## GitHub repo karar matrisi

| Repo | Kullanim alani | Lisans | Risk | AEGIS karari |
|---|---|---:|---|---|
| [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB) | finansal veri ve arastirma platformu | NOASSERTION | buyuk bagimlilik, lisans incelemesi gerekli | Direkt merge degil. Veri connector tasarimi ve AI-agent research modeli incelenebilir. |
| [microsoft/qlib](https://github.com/microsoft/qlib) | AI odakli quant research, model/backtest pipeline | MIT | agir framework, production'a tasima riski | En guclu research lab adayi. `aegis_core` disinda offline deney ortami olarak kullan. |
| [ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) | Yahoo Finance market data | Apache-2.0 | verified live data degil | Research/dev data adapter icin iyi. Canli dogrulanmis veri gibi gosterilmemeli. |
| [JerBouma/FinanceToolkit](https://github.com/JerBouma/FinanceToolkit) | finansal oranlar, statement analizi, metrikler | MIT | veri kaynagi kalitesi etiketlenmeli | Fundamental/research adapter icin uygun. |
| [ranaroussi/quantstats](https://github.com/ranaroussi/quantstats) | performans ve risk raporlari | Apache-2.0 | dusuk | Ilk entegre edileceklerden. Agent performans paneli ve backtest raporu icin uygun. |
| [quantopian/empyrical](https://github.com/quantopian/empyrical) | ortak finansal risk ve performans metrikleri | Apache-2.0 | eski ama stabil | Hafif metrik katmani olarak uygun. |
| [skfolio/skfolio](https://github.com/skfolio/skfolio) | portfoy optimizasyonu ve risk yonetimi | BSD-3-Clause | optimizer sonucu final allocation gibi sunulmamali | Evidence-only portfoy risk onerileri icin uygun. |
| [dcajasn/Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib) | portfoy optimizasyonu | BSD-3-Clause | agir matematiksel bagimliliklar | `skfolio` alternatifi. Once POC. |
| [PyPortfolio/PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) | efficient frontier, Black-Litterman, HRP | MIT | notebook agirlikli, optimizer riski | Research-only. Production safe core'a girmemeli. |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | vectorized backtesting | NOASSERTION | lisans dogrulama gerekli | Harici opsiyonel backtest araci olarak degerli, vendoring yapma. |
| [pmorissette/bt](https://github.com/pmorissette/bt) | portfoy backtesting | MIT | orta, framework uyumu incelenmeli | Basit strategy/backtest raporu icin alternatif. |
| [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | Python backtesting | AGPL-3.0 | copyleft riski | Koda merge etme. Sadece mimari fikir veya ayri local deney. |
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | full algorithmic trading engine | Apache-2.0 | execution/backtest/live engine cok buyuk | AEGIS'e merge etme. Ayrik benchmark olarak incelenebilir. |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | crypto exchange API, market data ve trading API | MIT | execution API icerdigi icin yuksek | Safe core'a yasak. Sadece read-only market data adapter ve strict allowlist ile dusunulebilir. |
| [bmoscon/cryptofeed](https://github.com/bmoscon/cryptofeed) | websocket crypto market data | NOASSERTION | operasyonel karmasiklik, lisans kontrolu | Read-only live data ingestion icin POC olabilir. |
| [bukosabino/ta](https://github.com/bukosabino/ta) | pandas/numpy teknik analiz indikatorleri | MIT | dusuk | Touche teknik feature katmaninda kontrollu kullanilabilir. |
| [xgboosted/pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic) | 200+ TA indikator ve candlestick pattern | MIT | yeni fork, kalite/test kontrolu gerekir | Teknik feature kutuphanesi icin aday. Once indikator parite testi. |
| [peerchemist/finta](https://github.com/peerchemist/finta) | pandas teknik indikatorleri | LGPL-3.0 | repo archived, lisans | Yeni entegrasyon icin onermiyorum. |
| [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) | reinforcement learning trading research | MIT | overfit, notebook agirlikli, karar motoru riski | Sadece offline research. Production agent'a baglama. |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | crypto trading bot, backtest, hyperopt | GPL-3.0 | execution engine ve GPL riski | Merge etme. FreqAI, backtest UX ve dry-run disiplininden fikir al. |
| [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) | high-frequency crypto trading bots | Apache-2.0 | execution/market making riski | Merge etme. Quantum/market-making legacy alanina mimari referans olabilir. |
| [Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot) | crypto trading bot | GPL-3.0 | execution ve GPL riski | Merge etme. UI/strategy marketplace fikirleri disinda uzak dur. |
| [Lumiwealth/lumibot](https://github.com/Lumiwealth/lumibot) | broker baglantili AI trading agents | GPL-3.0 | execution, broker, GPL | AEGIS safe core icin uygun degil. |

## Oncelikli ekleme sirasi

### Faz 1 - Dusuk risk, hemen deger

1. `quantstats` veya `empyrical`: agent/backtest performans raporu.
2. `bukosabino/ta`: teknik indikator standardizasyonu.
3. `yfinance`: sadece research/dev market data, net `RECENT/FALLBACK/UNKNOWN` etiketiyle.
4. `FinanceToolkit`: fundamental veri ve oranlar icin research adapter.

Bu fazda hedef sinyal kalitesini olcmek. Yeni karar motoru veya execution yok.

### Faz 2 - Kalibrasyon ve research lab

1. `qlib`: offline model deneyi, feature importance, walk-forward evaluation.
2. `vectorbt` veya `bt`: opsiyonel backtest runner. Lisans netlestirmeden vendoring yok.
3. `skfolio`: risk/portfoy stress-test onerileri. Cikti sadece `evidence` veya `suggestion` olmali.

Bu fazda hedef agent'in skor/esik onerilerini sayisal kanita baglamak.

### Faz 3 - Read-only live veri

1. `cryptofeed`: websocket feed POC.
2. `ccxt`: sadece read-only endpoint allowlist. Trading metodlari import edilmemeli.

Bu fazda hedef canli veri kalitesi. Execution yuzeyi acilmamali.

## Kesinlikle merge edilmemesi gerekenler

- Full trading botlar: Freqtrade, Hummingbot, OctoBot, Lumibot.
- Broker/order router katmanlari.
- GPL/AGPL kodlarin dogrudan repo icine alinmasi.
- Lisansi `NOASSERTION` gorunen repolarin vendoring yapilmasi.
- Reinforcement learning agent'larin canli sinyal yoluna direkt baglanmasi.
- `optimizer_service`, `bounded_updater`, `final_allocator`, `position_optimizer` benzeri legacy karar/pozisyon modullerinin `aegis_core` icine alinmasi.

## Temizlik plani

### Kod organizasyonu

- Yeni `aegis_research/` paketi ac.
- Backtest, metric, labeler ve weight-suggestion kodunu buraya tasi.
- `aegis_core` import testlerine forbidden module listesi ekle.
- Legacy route'lari `legacy_runtime/` veya net prefix altina ayir.
- Dashboard'da "agent candidate" ve "execution/paper" ekranlarini ayri tut.

### Veri ve metrik kalitesi

- Her veri objesinde `source`, `source_timestamp`, `ingested_at`, `data_status`, `fallback_used`, `verified` zorunlu olsun.
- Eksik timestamp varsa `Date.now()` ile canli gibi gosterme.
- Fallback makro degerleri her UI panelinde uyarili gorunsun.
- Module score range'i tek yerde tanimli olsun: 0..1 mi 0..100 mu belirsiz kalmasin.

### Agent kalibrasyonu

- Agent journal'i outcome store'a donustur.
- Her sinyal adayi icin `signal_id`, `module_scores`, `confidence`, `edge`, `timeframe`, `data_status` sakla.
- Forward outcome hesapla: 15m, 1h, 4h, 1d.
- Metrikler: hit rate, precision by confidence bucket, Brier score, expected calibration error, max adverse excursion, max favorable excursion, drawdown impact.
- Weight update sadece oneridir: `proposed_weights`, `reason`, `sample_size`, `confidence_interval`, `shadow_result`.

### Test kapilari

- Safe route'lar forbidden field emit etmiyor.
- Fallback veri live gibi gorunmuyor.
- Lisans `NOASSERTION/GPL/AGPL` olan dependency production requirements'a girmiyor.
- Agent otomatik config yazamiyor.
- Shadow weight ile live weight ayriliyor.

## En mantikli ilk PR seti

1. `docs` ve mimari guard: bu rapor, forbidden dependency policy, safe/research ayrimi.
2. `aegis_research.metrics`: `quantstats` veya `empyrical` adapter ve test.
3. `aegis_research.outcomes`: agent journal outcome labeler.
4. `aegis_research.calibration`: module score calibration ve weight suggestion.
5. Dashboard kontrol sekmesi: agent odakli performans, data freshness, shadow/live config ayrimi.
6. Optional POC: `qlib` research notebook/script. Production path'e import yok.

## Kaynaklar

GitHub API ve repo sayfalari 2026-06-06 tarihinde tarandi. Ana kaynaklar:

- [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB)
- [microsoft/qlib](https://github.com/microsoft/qlib)
- [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade)
- [ccxt/ccxt](https://github.com/ccxt/ccxt)
- [ranaroussi/yfinance](https://github.com/ranaroussi/yfinance)
- [ranaroussi/quantstats](https://github.com/ranaroussi/quantstats)
- [quantopian/empyrical](https://github.com/quantopian/empyrical)
- [skfolio/skfolio](https://github.com/skfolio/skfolio)
- [dcajasn/Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib)
- [PyPortfolio/PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt)
- [polakowo/vectorbt](https://github.com/polakowo/vectorbt)
- [bukosabino/ta](https://github.com/bukosabino/ta)
- [xgboosted/pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic)
- [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL)
- [QuantConnect/Lean](https://github.com/QuantConnect/Lean)
- [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot)
- [Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot)
