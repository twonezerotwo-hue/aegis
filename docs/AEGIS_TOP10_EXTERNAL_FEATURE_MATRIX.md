# AEGIS Top 10 Trading ve News Repo Ozellik Matrisi

Tarih: 2026-06-08  
Kapsam: OpenBB, Freqtrade, Qlib, CCXT, yfinance, Backtrader, Lean, Hummingbot, finBERT ve FinnewsHunter.

Bu matrisin amaci dis repolardaki en iyi fikirleri AEGIS'e guvenli sekilde tasimaktir. Tasima siniri nettir: `aegis_core` signal-only kalir; broker, state-changing exchange call, full bot runtime ve production config mutation eklenmez.

## Karar Tablosu

| Repo | En iyi ozellikler | AEGIS'te durum | AEGIS'teki mevcut karsilik | Eksik / zayif taraf | Guvenli entegrasyon hedefi | Alinmayacak kisim | Faz |
|---|---|---|---|---|---|---|---|
| [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB) | Multi-provider finansal veri soyutlamasi; analyst workflow; AI-agent-ready data platform | KISMEN VAR | Dashboard market/macro route'lari; `aegis_research` adapter inventory; provenance labels | Unified provider registry; standard quote/fundamental/news snapshot schema; provider health/freshness scoring | Read-only provider catalog; `DataSnapshot` uyumlu market/fundamental adapter; research inventory endpoint | Buyuk platform vendoring; lisans netlesmeden dependency; research verisini verified live diye gostermek | Faz 1 |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | Strategy lifecycle; dry-run/backtest ayrimi; hyper-parameter experiment UX | KISMEN VAR | Agent `DRY_RUN` journal; dashboard backtest route'lari; threshold suggestions | Experiment registry; strategy result comparison; safe hyper-parameter audit trail | Experiment metadata schema; backtest report normalization; shadow-only threshold comparison | GPL production dependency; bot runtime; broker-facing modul tasima | Faz 2 |
| [microsoft/qlib](https://github.com/microsoft/qlib) | Feature engineering pipeline; walk-forward model research; experiment tracking | KISMEN VAR | `aegis_research` metrics/calibration; agent outcome store; module score journal | Feature store abstraction; walk-forward validation runner; model-vs-rule comparison | Offline research runner design; feature importance report schema; shadow-only model score evidence | Otomatik production config yazimi; owner onaysiz model output promotion | Faz 2 |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | Coklu exchange market-data interface; symbol normalization; rate-limit/capability metadata | KISMEN VAR | Touche Binance public data; price validator; data freshness labels | Read-only multi-exchange allowlist; exchange capability inventory; cross-source price validation | Read-only OHLCV/ticker adapter; exchange health metadata; source disagreement warning | Private credentials; broker-facing method exposure; state-changing exchange calls | Faz 1 |
| [ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) | Basit equity/index/fundamental data access; genis ticker coverage; hizli research prototyping | KISMEN VAR | `YFinanceReadOnlyAdapter` availability; research/dev warning | Actual snapshot fetcher; value-level timestamp provenance; UI research-only labeling | `DataSnapshot` fetch methods; research-only dashboard display; `verified=false` labels | Yahoo kaynakli veriyi verified live exchange data gibi gostermek | Faz 1 |
| [mementum/backtrader](https://github.com/mementum/backtrader) | Mature event-style backtest; indicator/strategy ayrimi; analyzer summaries | KISMEN VAR | Dashboard backtest route'lari; `aegis_core` backtest evidence formatter | Analyzer schema; walk-forward result comparison; look-ahead safety checklist | Backtest evidence normalization; analyzer metric naming; look-ahead-safe report checklist | GPL production dependency; framework vendoring | Faz 2 |
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | Algorithm lifecycle; data subscription model; backtest/live parity discipline | YOK | Legacy servisler safe core'dan ayri; `aegis_core` signal-only | Formal research job lifecycle; dataset subscription manifest; runtime'dan bagimsiz benchmark harness | Research job lifecycle interface; dataset manifest schema; external benchmark notes | Full engine merge; safe core'a live trading parity path eklemek | Faz 3 |
| [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) | Connector architecture; market microstructure data patterns; strategy config discipline | YOK | Touche technical metrics; legacy quantum/market modules | Orderbook imbalance evidence; spread/liquidity snapshots; connector capability registry | Read-only orderbook evidence schema; liquidity feature scoring; connector capability inventory | Market-making runtime; inventory management; exchange state-changing calls | Faz 3 |
| [ProsusAI/finBERT](https://github.com/ProsusAI/finBERT) | Financial-domain sentiment; pos/neg/neutral probability shape; news scoring baseline | KISMEN VAR | `news-ai-limited` sentiment engine references FinBERT; crypto lexicon/pattern fallback; news score in consensus | Model availability in inventory; probability calibration report; source-level contribution audit | Sentiment model availability snapshot; calibration metrics; auditable article-level evidence | Unlabeled sentiment as standalone signal; large model forced into default runtime | Faz 1 |
| [DemonDamon/FinnewsHunter](https://github.com/DemonDamon/FinnewsHunter) | Multi-agent financial news analysis; sentiment fusion; alpha factor mining workflow | KISMEN VAR | `news-ai-limited` source registry; impact scoring; source reliability manager | Event taxonomy; cross-source dedup audit; news-to-outcome factor mining reports | News event taxonomy; source fusion evidence; shadow factor-mining reports | Mined factors'i otomatik production weights yapmak; unverified breaking-news'i live truth gibi gostermek | Faz 1 |

## Ilk Yazilacak Parcalar

1. `aegis_research.external_repo_matrix`
   - Top 10 repo matrisi makine-okunabilir hale getirildi.
   - Cikti research-only; runtime config degistirmez.

2. `GET /api/agent/research/external-repo-matrix`
   - Dashboard/agent tarafindan okunabilir katalog.
   - `SIGNAL_ONLY / NO_EXECUTION` guard metadata ile doner.

3. Faz 1 sonraki kod hedefleri
   - OpenBB benzeri provider registry ama lightweight ve read-only.
   - yfinance snapshot fetcher: `verified=false`, timestamp/provenance zorunlu.
   - finBERT/news model availability inventory.
   - FinnewsHunter benzeri event taxonomy ve source-fusion evidence.
   - ccxt icin sadece public read-only method allowlist tasarimi.

## Guvenlik Sinirlari

- Full trading bot veya engine merge edilmeyecek.
- GPL/AGPL kod production path'e vendoring yapilmayacak.
- Research-only data live/verified gibi gosterilmeyecek.
- Research suggestion production config'i otomatik degistirmeyecek.
- Safe core'a broker, state-changing exchange call veya final portfolio command eklenmeyecek.
