from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = ROOT.parent
API_SERVICE = ROOT / "frontend" / "src" / "services" / "apiV2.ts"
MACRO_COMPONENT = ROOT / "frontend" / "src" / "components" / "macro" / "MacroRegimeCommentary.tsx"
ALLOCATION_COMPONENT = ROOT / "frontend" / "src" / "components" / "portfolio" / "AllocationWithTip.tsx"
CHECKLIST_COMPONENT = ROOT / "frontend" / "src" / "components" / "validation" / "CrossAlignmentPanel.tsx"
DOC_PATH = PROJECT_ROOT / "AEGIS_DASHBOARD_V2_MACRO_VIEWMODEL_REWRITE.md"


def test_api_normalization_uses_canonical_macro_view_model():
    content = API_SERVICE.read_text(encoding="utf-8")
    assert "export const normalizeMacroViewModel" in content
    assert 'data_status: viewModelStatus' in content
    assert "fallback_fields: normalizedFallbackFields" in content
    assert "field_sources: forcedFieldSources" in content


def test_fallback_cluster_always_becomes_partial_fallback():
    content = API_SERVICE.read_text(encoding="utf-8")
    assert "const MACRO_FALLBACK_CLUSTER" in content
    assert "dxy: 98.5" in content
    assert "vix: 22.0" in content
    assert "us10y: 4.25" in content
    assert "brent: 92.0" in content
    assert "const fallbackClusterDetected = isHardcodedFallbackCluster(metrics);" in content
    assert 'normalizedFallbackFields.length > 0 ? "PARTIAL_FALLBACK" : dataStatus' in content


def test_macro_view_model_with_fallback_fields_cannot_be_live():
    content = API_SERVICE.read_text(encoding="utf-8")
    assert "if (normalizedFallbackFields.length > 0) {" in content
    assert "verified = false;" in content
    assert "live = false;" in content


def test_macro_commentary_shows_not_fully_verified_and_disables_live_commentary():
    content = MACRO_COMPONENT.read_text(encoding="utf-8")
    assert "NOT FULLY VERIFIED" in content
    assert "live macro commentary is intentionally disabled" in content
    assert 'const liveVerifiedMacro =' in content


def test_partial_fallback_allocation_does_not_render_stable_rebalance_text():
    content = ALLOCATION_COMPONENT.read_text(encoding="utf-8")
    assert "Verified allocation decision unavailable because macro data is not fully verified." in content
    assert 'const tip = liveVerifiedMacro' in content
    assert "Dagilim dengede, rebalance gerekmiyor." in content


def test_final_checklist_marks_fallback_macro_as_unverified():
    content = CHECKLIST_COMPONENT.read_text(encoding="utf-8")
    assert '"UNVERIFIED"' in content
    assert 'const liveVerifiedMacro =' in content
    assert 'label: "Makro rejim uygun"' in content
    assert 'label: "Hedge durumu"' in content
    assert 'label: "VIX normal bolge"' in content
    assert 'status: !liveVerifiedMacro' in content


def test_macro_view_model_rewrite_doc_exists():
    content = DOC_PATH.read_text(encoding="utf-8")
    assert "canonical macro view model" in content.lower()
    assert "macroviewmodel" in content.lower()
