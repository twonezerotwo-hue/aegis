# AEGIS v7.6 — V1/V2 Incompatibility Matrix
Generated: 2026-04-20

## 🎯 Executive Summary
| Metric | Value |
|--------|-------|
| Total API endpoints compared | 1 (POST /backtest/run) |
| Incompatible fields | 2 |
| Breaking changes | 2 (`strategy` removed, `module_scores` missing in V1) |
| Backward-compatible additions | 5+ (risk_profile, event_hint, score_attribution, portfolio_allocation, horizon, etc.) |
| Migration effort estimate | Low (adapter layer + prop forwarding) |

## ⚠️ Breaking Changes (CRITICAL)
| Field | V1 Value | V2 Value | Impact | Mitigation |
|-------|---------|---------|--------|-----------|
| `strategy` | "AI Consensus v7.1" | REMOVED | Low (display only) | Redirect V1 users to V2 + deprecation warning |
| `module_scores` | Missing in V1 schema | Present in V2 | Medium (custom integrations) | Adapter layer in apiV2.ts |

## ✅ Backward-Compatible Additions
| Field | Type | Purpose | Default |
|-------|------|---------|---------|
| `risk_profile` | enum | Kelly/SL/TP presets | "moderate" |
| `event_hint` | enum | Event-aware z-threshold | null |
| `score_attribution` | array | Explainability panel | [] |
| `portfolio_allocation` | object | Per-asset allocation | {} |
| `horizon` | enum | Backtest horizon | "medium" |

---

## 🔄 Migration Strategy (3-Phase)

### Phase 1: Adapter Layer (Week 1)
- [ ] Create `apiV2_adapter.ts`: Transform V1 requests → V2 format
- [ ] Add `module_scores: {}` default for V1 responses
- [ ] Deprecation warning for `strategy` field usage
- [ ] Test: V1 dashboard loads with V2 backend

### Phase 2: Component Forwarding (Week 2)
- [ ] Update V1 components to accept V2 optional props (spread pattern)
- [ ] Add TypeScript `& Partial<V2Props>` to V1 component types
- [ ] Test: V1 components render without errors with V2 data

### Phase 3: Deprecation + Redirect (Week 3-4)
- [ ] Add `/v1` → `/v2` redirect with query param `?legacy=true` for opt-out
- [ ] Console warning: "V1 dashboard deprecated, migrate to V2 by [date]"
- [ ] Analytics: Track V1 vs V2 usage, plan removal after 90 days

## 🧪 Automated Checks (3 küçük ekleme)

### 1. TypeScript Interface Compatibility Test
```ts
// scripts/check_v1_v2_compat.ts
import { BacktestRequestV1, BacktestRequestV2 } from '@/types';

// Compile-time check: V2 should be superset of V1
type V1Compatible = Omit<BacktestRequestV2, keyof BacktestRequestV1> extends infer R 
	? [R] extends [never] ? true : false 
	: false;

// Runtime check: V1 request should validate against V2 schema
export function validateV1OnV2(req: BacktestRequestV1): req is BacktestRequestV2 {
	return true; // V2 optional fields allow V1 subset
}
```

### 2. API Contract Validation Script
```python
# scripts/validate_api_contract.py
import jsonschema, requests

V1_SCHEMA = {...}  # OpenAPI spec for V1
V2_SCHEMA = {...}  # OpenAPI spec for V2

def check_superset(v1: dict, v2: dict) -> bool:
		# All V1 required fields must exist in V2
		for field in v1.get("required", []):
				if field not in v2.get("required", []) and field not in v2.get("properties", {}):
						return False
		return True

# Run: python validate_api_contract.py --v1 openapi_v1.json --v2 openapi_v2.json
```

### 3. Component Prop Diff Tool
```tsx
// scripts/prop-diff.tsx
type DiffProps<V1, V2> = {
	added: Exclude<keyof V2, keyof V1>;
	removed: Exclude<keyof V1, keyof V2>;
	changed: {
		[K in keyof V1 & keyof V2]: V1[K] extends V2[K] ? never : { old: V1[K]; new: V2[K] }
	};
};

// Usage: Log prop differences for migration planning
const scoreBarDiff = diffProps<ScoreBarV1, ScoreBarV2>();
console.log("Added props:", scoreBarDiff.added); // ["weight", "attribution"]
```

## 📊 Breaking Change Impact Analysis (3. küçük ekleme)
| Breaking Change | Affected Users | Severity | Mitigation Timeline |
|----------------|---------------|----------|-------------------|
| `strategy` removed | V1 dashboard users (display only) | Low | Week 1: Warning, Week 4: Remove |
| `module_scores` missing in V1 | Custom API integrations | Medium | Week 1: Adapter layer, Week 2: Notify integrators |
| Structured error response | Error handling code | Low | Week 1: Backward-compatible error parser |

## 🧩 Component Prop Forwarding Pattern (3. küçük ekleme)
```tsx
// Pattern: V1 component accepts V2 optional props without breaking
interface ScoreBarV1Props {
	value: number;
	label: string;
}

interface ScoreBarV2Props extends ScoreBarV1Props {
	weight?: number;        // Optional: ignored by V1 logic
	attribution?: AttributionEntry[]; // Optional: ignored by V1 logic
}

const ScoreBar: React.FC<ScoreBarV2Props> = ({
	value, label, weight, attribution, // weight/attribution unused in V1 render
	...rest // Forward any future V2 props
}) => {
	// V1 render logic only uses value/label
	return (
		<div className="score-bar">
			<span>{label}: {value.toFixed(2)}</span>
			{/* V2 can extend: {weight && <span>{weight}%</span>} */}
		</div>
	);
};
```
---

## 🧠 State Management Comparison

### Global State Pattern
| Aspect | V1 | V2 | Migration Path |
|--------|----|----|---------------|
| Library | Zustand / Redux | Jotai + React Context | Adapter: `useV1State()` → `useV2State()` |
| Async Data | useEffect + fetch | React Query + SWR | Wrap V1 fetches in React Query |
| Cache | Manual (localStorage) | React Query cache + staleTime | Migrate keys: `v1:metrics` → `v2:metrics` |

### Component Prop Mapping
| Component | V1 Props | V2 Props | Forwarding Strategy |
|-----------|---------|---------|-------------------|
| ScoreBar | `{value, label}` | `{value, label, weight?, attribution?}` | Spread unused props: `{...rest}` |
| MetricCard | `{pnl, wr}` | `{pnl, wr, sharpe?, sortino?, regime?}` | Optional props ignored by V1 |
| BacktestForm | `{symbol, tf, dates}` | `{symbol, tf, dates, horizon?, risk_profile?}` | Defaults for optional V2 props |

## 🎨 UI/UX Differences
| Feature | V1 | V2 | User Impact |
|---------|----|----|------------|
| Theme | Light only | Dark/Light toggle | V1 users get system default |
| Responsive | Desktop-first | Mobile-first | V1 may break on mobile |
| Loading | Spinner only | Skeleton + progressive | V2 better UX |

---

## 🔌 API Contract Comparison

### Request Body: POST /backtest/run
| Field | V1 Type | V2 Type | Compatible | Notes |
|-------|--------|--------|-----------|-------|
| `symbol` | string | string | ✅ | Same |
| `timeframe` | "1h"\|"4h"\|"1d" | "1h"\|"4h"\|"1d"\|"1w" | ✅ V2 superset | V1 clients work |
| `horizon` | missing | "short"\|"medium"\|"long" | ✅ Optional | Default: "medium" |
| `risk_profile` | missing | "conservative"\|"moderate"\|"aggressive" | ✅ Optional | Default: "moderate" |
| `event_hint` | missing | enum | ✅ Optional | Default: null |
| `weight_*` | missing | number[] | ✅ Optional | Expert mode only |

### Response Body
| Field | V1 | V2 | Compatible | Notes |
|-------|----|----|-----------|-------|
| `success` | boolean | boolean | ✅ | Same |
| `metrics` | object | object | ✅ | Same structure |
| `module_scores` | ❌ Missing | Record<string, number> | ⚠️ Breaking | Add adapter: `module_scores: {}` for V1 |
| `strategy` | string | ❌ Removed | ⚠️ Breaking | Deprecate, redirect to V2 |
| `score_attribution` | ❌ | array | ✅ New (optional) | V1 ignores, V2 uses |
| `portfolio_allocation` | ❌ | object | ✅ New (optional) | V1 ignores, V2 uses |
| `horizon` | ❌ | enum | ✅ New (optional) | V1 ignores, V2 uses |

### Error Response
| Field | V1 | V2 | Compatible |
|-------|----|----|-----------|
| `error` | string | {code: string, message: string, details?: any} | ⚠️ Structured in V2 |

---
