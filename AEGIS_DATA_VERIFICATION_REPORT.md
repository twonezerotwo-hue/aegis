# AEGIS Data Verification Report

**Finalized:** 2026-05-28 05:54 UTC  
**Endpoint:** `http://localhost:8502/api/macro`  
**Version:** AEGIS v7.2 — field-level data provenance

---

## Verification Result: PASS

`data_status: LIVE` — all 11 macro fields sourced from live APIs.

```
status          : ok
data_status     : LIVE
verified        : True
live            : True
fallback_used   : False
fallback_fields : []
source          : market_data_live
sentinel_ok     : True
warning         : None
```

---

## Field-Level Provenance (2026-05-28 05:54 UTC)

| Field | Value | Source | Verified | Fallback |
|-------|-------|--------|----------|---------|
| DXY | 99.42 | `yfinance:DX-Y.NYB` | ✓ | ✗ |
| VIX | 16.29 | `yfinance:^VIX` | ✓ | ✗ |
| US10Y | 4.481% | `yfinance:^TNX` | ✓ | ✗ |
| Brent | 95.08 | `yfinance:BZ=F` | ✓ | ✗ |
| XAU (Gold) | 4419.7 | `yfinance:GC=F` | ✓ | ✗ |
| HG (Copper) | 6.296 | `yfinance:HG=F` | ✓ | ✗ |
| BTC Dominance | 57.70% | `coingecko_public:btc_dominance` | ✓ | ✗ |
| USDT Dominance | 7.48% | `coingecko_public:usdt_dominance` | ✓ | ✗ |
| event_risk_score | 0.471 | `sentinel-ai` | ✓ | ✗ |
| hours_to_event | 48 | `sentinel-ai` | ✓ | ✗ |
| regime | NORMALIZATION | `sentinel-ai:regime_probability_distribution` | ✓ | ✗ |

---

## Before vs After

### Before Fix

The old `aegis_clean_v71-dashboard-backend` image:
- Returned hardcoded values: DXY=98.5, VIX=22.0, US10Y=4.25, Brent=92.0, XAU=4800.0, BTC.D=59.8, USDT.D=7.5
- Labelled all fields `source: "sentinel-ai"`, `fallback: false`
- No `data_status`, `verified`, `fallback_fields`, or `field_sources` fields in response
- Sentinel was passing through its own hardcoded fallback snapshot as if it were live

### After Fix

Real API integration via `services/market_data.py`:
- yfinance fetches DXY, VIX, US10Y, Brent, Gold, Copper (no API key required)
- CoinGecko public endpoint fetches BTC.D and USDT.D (no API key required)
- Sentinel provides event_risk_score, hours_to_event, regime (via internal Docker network)
- Every field carries `{value, source, timestamp, verified, fallback_used}` provenance
- `data_status: LIVE` only when ALL fields are from live sources

---

## Provenance Contract

### Response Fields

| Field | Type | Meaning |
|-------|------|---------|
| `data_status` | `"LIVE"` / `"PARTIAL_FALLBACK"` / `"FALLBACK"` | Aggregate status |
| `verified` | bool | true only when data_status == "LIVE" |
| `live` | bool | alias of verified |
| `fallback_used` | bool | true if any field is hardcoded |
| `fallback_fields` | list[str] | fields using hardcoded values |
| `verified_fields` | list[str] | fields from live sources |
| `field_sources` | dict[str, str] | `{field: source_string}` for frontend |
| `field_provenance` | dict[str, obj] | full per-field metadata |
| `sentinel_available` | bool | whether Sentinel responded |
| `warning` | str or null | human-readable degradation message |

### Allocation Gating

| data_status | allocation_profile | Rebalance language |
|-------------|-------------------|-------------------|
| LIVE | `balanced` | Enabled |
| PARTIAL_FALLBACK | `fallback_illustrative` | Disabled |
| FALLBACK | `fallback_illustrative` | Disabled |

When allocation is `fallback_illustrative`, the dashboard shows illustrative weights only. No approval flow is presented to the user.

---

## Degradation Behavior

### Tier 1 — LIVE (normal)
All 11 fields from live APIs. `verified: true`. Allocation: `balanced`.

### Tier 2 — PARTIAL_FALLBACK
Some fields live, some hardcoded. Triggered by:
- CoinGecko rate limit (free tier, 30 req/min) → btc_d, usdt_d fall back
- Sentinel timeout (4s) → event_risk_score, hours_to_event, regime fall back

During PARTIAL_FALLBACK:
- `source` contains `"partial_plus_fallback"` (frontend `isPartialFallbackSource` check)
- `warning` shows count of fallback fields and list of verified fields
- Dashboard warning banner displayed
- Allocation forced to `fallback_illustrative`

Observed frequency: ≤2 windows per hour, each lasting ≤60s (one cache TTL).

### Tier 3 — FALLBACK (all sources fail)
All 11 fields hardcoded. `source: "all_hardcoded_fallback"`. Allocation: `fallback_illustrative`.  
Dashboard shows: "All macro data is hardcoded fallback — no live market sources available."

---

## Data Sources

### yfinance
- Library: `yfinance>=0.2.40`
- Method: `yf.download()` in `asyncio.to_thread` (non-blocking)
- Data: Last 5 days daily, most recent close price
- Cache TTL: 60 seconds
- Tickers: `DX-Y.NYB`, `^VIX`, `^TNX`, `BZ=F`, `GC=F`, `HG=F`
- Auth: No API key required

### CoinGecko Public API
- Endpoint: `https://api.coingecko.com/api/v3/global`
- Fields: `market_cap_percentage.btc` → btc_d, `market_cap_percentage.usdt` → usdt_d
- Timeout: 8 seconds
- Cache TTL: 60 seconds (shared with yfinance batch)
- Auth: No API key required

### Sentinel AI
- Endpoint: `http://sentinel-api:8004/sentinel/event_risk`
- Params: `symbol=BTC`, `horizon={short|medium|long}`
- Fields: `event_risk_score`, `hours_to_event`
- Regime: derived from `regime_probability_distribution` (max-probability key)
- Timeout: 4 seconds
- Auth: Internal Docker network, no external credentials

---

## Regime Derivation

When Sentinel does not return an explicit `regime` field, system derives it:

```python
rpd = sentinel_data.get("regime_probability_distribution", {})
best = max(rpd.items(), key=lambda kv: float(kv[1]))
# Maps: "risk_on"→"RISK_ON", "normalization"→"NORMALIZATION", etc.
```

Current distribution (2026-05-28 05:54 UTC):
```
normalization : 30.6%  ← selected → NORMALIZATION
risk_on       : 24.7%
risk_off      : 23.2%
accumulation  : 21.5%
```

field_sources entry: `"regime": "sentinel-ai:regime_probability_distribution"`

---

## Allocation Output (Live)

```json
{
  "allocation_target": {
    "gold":      0.2414,
    "btc":       0.1574,
    "bond":      0.2504,
    "commodity": 0.1084,
    "cash":      0.2424
  },
  "allocation_profile": "balanced",
  "allocation_horizon": "medium",
  "hedge": false,
  "warnings": ["Elevated event risk increased cash and gold buffers."]
}
```

event_risk_score = 0.471 triggered cash+gold buffer increase (above 0.4 threshold).

---

## Secret Exposure Note

No API keys or tokens are required for or used by the live data sources (yfinance, CoinGecko public, internal Sentinel). No secrets are stored in `services/market_data.py`, `routes/macro.py`, or any report file. If any service credential was observed in terminal output during this session, it must be treated as potentially exposed and rotated immediately through the relevant service's admin panel.
