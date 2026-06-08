# AEGIS Provider Registry Report

Date: 2026-06-08

## What Changed

Added `aegis_platform.providers`:

- `contract.py`: `ProviderManifest`, `ProviderState`.
- `registry.py`: provider catalog and credential/import status resolver.

Added API route:

- `GET /api/system/providers`

## Providers

| Provider | Fields | Credential behavior | Safe mode |
|---|---|---|---|
| `yfinance` | DXY, VIX, US10Y, Brent, XAU, HG | no key; optional package must exist | read-only |
| `coingecko.public` | BTC.D, USDT.D | no key | read-only |
| `sentinel.macro` | event risk, hours to event, regime | internal service URL | read-only evidence |
| `binance.public` | ticker, OHLCV | no private key | public read-only |
| `fred` | macro series | `FRED_API_KEY`; missing key returns `CREDENTIALS_MISSING` | read-only |
| `newsapi` | news items | `NEWSAPI_KEY`; missing key returns `CREDENTIALS_MISSING` | read-only |
| `openbb.placeholder` | future provider catalog | optional package; license review needed | metadata/research |
| `ccxt.read_only.placeholder` | ticker, OHLCV | optional package; no credentials exposed | read-only placeholder |

## Behavior

The registry never prints secret values. It only reports missing environment variable names.

Provider statuses:

- `AVAILABLE`
- `UNAVAILABLE_PROVIDER`
- `CREDENTIALS_MISSING`
- `DISABLED_PROVIDER`
- `DEGRADED_PROVIDER`

## Macro Route Integration

`/api/macro` keeps its current response contract and field-level provenance. It now also includes `provider_registry` metadata so dashboard/debug panels can explain provider availability without changing macro scoring behavior.

## Remaining Risks

- Provider registry is capability/status metadata; it is not yet a unified fetch layer.
- yfinance/CoinGecko/Sentinel field degradation still happens in the existing macro implementation.
- FRED and NewsAPI are not fetched yet; they are credential-aware placeholders.
