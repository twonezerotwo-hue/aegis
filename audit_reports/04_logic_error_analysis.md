# AEGIS v7.6 — Logic Error Analysis + Risk Matrix
Generated: 2026-04-20

## 🔍 Static Analysis: Common Logic Error Patterns

### Pattern 1: Division Without Zero Check
| Dosya:Satır | Code Snippet | Risk | Mitigation |
|------------|-------------|------|-----------|
| `backtest_routes.py:L720` | `impact = (score - 0.5) / 0.5` | Medium | Add guard: `if denominator != 0` |
| `portfolio_allocator.py:L25` | `pct / total * 100` | Low | `total > 0` check already present ✅ |

### Pattern 2: Mutable Default Arguments (Python)
| Dosya:Satır | Code Snippet | Risk | Mitigation |
|------------|-------------|------|-----------|
| `execution_engine.py:L45` | `def calc_kelly(z=0, cache={})` | High | Replace with `cache=None` + runtime init |
| `sentinel_ai/main.py:L145` | `def fetch_macro(symbols=[])` | Medium | Already fixed in v7.5 ✅ |

### Pattern 3: Async/Await Mismatch
| Dosya:Satır | Code Snippet | Risk | Mitigation |
|------------|-------------|------|-----------|
| `backtest_routes.py:L1175` | `async def get_multi_tf()` + `httpx.get()` (sync) | Medium | Use `httpx.AsyncClient` consistently |
| `news_ai/fetcher.py:L30` | `async def fetch_news()` + blocking RSS parser | Low | Wrap in `asyncio.to_thread()` |

### Pattern 4: Silent Fallbacks (No Warning Log)
| Dosya:Satır | Code Snippet | Risk | Mitigation |
|------------|-------------|------|-----------|
| `main.py:L460` | `regime = "NORMALIZATION"  # fallback` | Medium | Add `logger.warning("Sentinel unreachable, using default regime")` |
| `apiV2.ts:L89` | `catch (e) { return defaultResponse }` | Low | Already logs to Sentry ✅ |

### Pattern 5: Magic Numbers / Hardcoded Thresholds
| Dosya:Satır | Code Snippet | Risk | Mitigation |
|------------|-------------|------|-----------|
| `backtest_routes.py:L906` | `if abs(z) > 0.85:` | Low | Extract to config: `Z_THRESHOLD_MAP = {"1h": 1.0, "4h": 0.85}` |
| `execution_engine.py:L67` | `max_dd = 5.0` | Low | Already in risk_profile config ✅ |

## 🧪 Edge Case Testing: Input Validation Gaps

### Request Body Edge Cases
| Input Scenario | Current Behavior | Expected Behavior | Gap |
|---------------|-----------------|------------------|-----|
| `symbol: ""` (empty) | 500 error (Binance API fail) | 400 Bad Request + validation message | ❌ Missing |
| `timeframe: "999h"` (invalid) | Falls back to "4h" silently | 400 Bad Request + list valid options | ⚠️ Silent fallback |
| `start_date > end_date` | Returns empty trades array | 400 Bad Request + error message | ❌ Missing |
| `initial_capital: -100` (negative) | Kelly calculation breaks | 400 Bad Request + min value check | ❌ Missing |
| `weight_touche: 2.0` (>1.0) | Weight normalization fails | Clamp to [0,1] or 400 error | ⚠️ No clamp |

### Macro Data Edge Cases
| Scenario | Current Behavior | Expected | Gap |
|----------|-----------------|----------|-----|
| Sentinel timeout (10s) | Fallback to default regime | ✅ Already implemented | None |
| TwelveData API returns `{"status":"error"}` | Fallback to hardcoded values | ✅ Already implemented | None |
| M2SL value = 0 (division risk) | `liquidity_score = (0 - 10) * 5 = -50` → clamped to 0 | ✅ Clamping present | None |
| VIX = 100 (extreme) | `volatility_composite` > 100 → clamped | ✅ Clamping present | None |

### AI Module Edge Cases
| Module | Edge Case | Current Behavior | Gap |
|--------|----------|-----------------|-----|
| Touche AI | OHLCV array empty | Returns score=0.5 (neutral) | ⚠️ Should return error or explicit "insufficient data" |
| Fundamental AI | Glassnode API key expired | Fallback to price-only scoring | ✅ Graceful degradation |
| News-AI | RSS feed down | Returns sentiment=0.5 (neutral) | ⚠️ Should log warning + fallback |
| Quantum AI | Futures data unavailable | Skips quantum score, uses others | ✅ Partial confluence OK |

## ⚠️ Risk Matrix

### Risk Scoring Legend
- **Likelihood**: 1 (Rare) → 5 (Almost Certain)
- **Impact**: 1 (Cosmetic) → 5 (Data Loss/Crash)
- **Risk Score** = Likelihood × Impact
  - 1-5: Low (monitor)
  - 6-12: Medium (plan mitigation)
  - 13-25: High (immediate action)

### Risk Register
| ID | Risk Description | Likelihood | Impact | Score | Mitigation | Owner | Timeline |
|----|-----------------|-----------|--------|-------|-----------|-------|----------|
| R01 | Division by zero in `get_score_attribution()` if denominator=0 | 2 | 4 | 8 (Medium) | Add guard clause + unit test | Backend Team | Week 1 |
| R02 | Mutable default argument in `execution_engine.py:L45` causes shared state bug | 3 | 5 | 15 (High) | Replace `cache={}` with `cache=None` + runtime init | Backend Team | Week 1 |
| R03 | Async/await mismatch in `get_multi_tf_confluence()` causes timeout | 2 | 3 | 6 (Medium) | Use `httpx.AsyncClient` consistently | Backend Team | Week 2 |
| R04 | Silent fallback on Sentinel timeout hides production issues | 4 | 2 | 8 (Medium) | Add `logger.warning()` on fallback path | DevOps | Week 1 |
| R05 | Magic number `0.85` for z-threshold makes config changes hard | 1 | 2 | 2 (Low) | Extract to `config.py` + document | Backend Team | Week 3 |
| R06 | Empty `symbol` input causes 500 instead of 400 | 2 | 3 | 6 (Medium) | Add Pydantic validator for non-empty string | Backend Team | Week 1 |
| R07 | Negative `initial_capital` breaks Kelly calculation | 1 | 4 | 4 (Low) | Add Pydantic `Field(ge=0)` constraint | Backend Team | Week 1 |
| R08 | Weight >1.0 causes normalization failure | 2 | 3 | 6 (Medium) | Add clamp: `max(0, min(1, weight))` | Backend Team | Week 2 |

### High-Priority Risks (Score ≥ 13)
#### R02: Mutable Default Argument in `execution_engine.py:L45`
```python
# BEFORE (risky):
def calculate_position_size(symbol: str, z: float, cache: dict = {}):
    if symbol not in cache:
        cache[symbol] = compute_expensive_value(z)
    return cache[symbol]

# AFTER (safe):
def calculate_position_size(symbol: str, z: float, cache: dict | None = None):
    if cache is None:
        cache = {}
    if symbol not in cache:
        cache[symbol] = compute_expensive_value(z)
    return cache[symbol]
```
**Test Case:**
```python
def test_mutable_default_fix():
    # Call twice with same default cache
    r1 = calculate_position_size("BTC", 1.5)
    r2 = calculate_position_size("ETH", 1.5)
    # Should NOT share cache between calls
    assert "BTC" not in calculate_position_size.__defaults__[0]  # or use None default
```

### Medium-Priority Risks (Score 6-12) — Batch Fix Plan
```bash
# Week 1: Division guards + validation + logging
- [ ] backtest_routes.py:L720: Add `if denominator != 0` guard
- [ ] backtest_routes.py:L213: Add Pydantic validator for symbol/timeframe/dates
- [ ] main.py:L460: Add logger.warning on Sentinel fallback

# Week 2: Async consistency + weight clamping
- [ ] backtest_routes.py:L1175: Use httpx.AsyncClient for all HTTP calls
- [ ] backtest_routes.py:L810: Add `weight = max(0, min(1, weight))` clamp
```
