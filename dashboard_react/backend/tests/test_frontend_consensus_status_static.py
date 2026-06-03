from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_SERVICE = ROOT / "frontend" / "src" / "services" / "apiV2.ts"
V2_PAGE = ROOT / "frontend" / "src" / "pages" / "DashboardV2.tsx"


def test_missing_module_provenance_is_not_forced_to_fallback():
    content = API_SERVICE.read_text(encoding="utf-8")
    assert '(missingSource || missingLikeSource ? "MISSING" : fallbackUsed ? "FALLBACK" : timestamp ? "LIVE" : "UNKNOWN")' in content


def test_partial_fallback_has_higher_priority_than_unknown():
    content = API_SERVICE.read_text(encoding="utf-8")
    partial_idx = content.index('"PARTIAL_FALLBACK"')
    unknown_idx = content.index('"UNKNOWN"')
    assert partial_idx < unknown_idx


def test_macro_assets_use_gateway_only_consensus_path():
    content = API_SERVICE.read_text(encoding="utf-8")
    assert 'const MACRO_ASSET_SYMBOLS = new Set(["XAU/USDT", "XAG/USDT", "BOND/USDT", "CASH/USDT"]);' in content
    assert 'const gatewayOnly = MACRO_ASSET_SYMBOLS.has(symbol);' in content
    assert '? Promise.resolve(null)' in content


def test_btc_sse_override_does_not_downgrade_better_gateway_data():
    content = V2_PAGE.read_text(encoding="utf-8")
    assert "incomingStrength > currentStrength" in content
    assert "if (!shouldReplace) {" in content
