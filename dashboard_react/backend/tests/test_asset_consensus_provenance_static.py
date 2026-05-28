from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = ROOT.parent
CARD_COMPONENT = ROOT / "frontend" / "src" / "components" / "assets" / "AssetConsensusCard.tsx"
API_SERVICE = ROOT / "frontend" / "src" / "services" / "apiV2.ts"
STREAM_ROUTE = ROOT / "backend" / "routes" / "stream.py"
GATEWAY_ROUTE = ROOT / "backend" / "routes" / "dashboard.py"
PROCESS_SERVICE = PROJECT_ROOT / "consensus_engine" / "main.py"
AUDIT_DOC = PROJECT_ROOT / "AEGIS_ASSET_CONSENSUS_PROVENANCE_AUDIT.md"


def test_asset_card_shows_visible_provenance_fields():
    content = CARD_COMPONENT.read_text(encoding="utf-8")
    assert "Data Status:" in content
    assert "Source:" in content
    assert "Updated:" in content
    assert "Verified:" in content
    assert "Fallback used:" in content


def test_asset_card_warns_for_unverified_and_shared_scores():
    content = CARD_COMPONENT.read_text(encoding="utf-8")
    assert "Signal is not verified because source data is stale/fallback/mock." in content
    assert "Shared module score, not asset-specific." in content


def test_consensus_paths_propagate_module_provenance():
    api_content = API_SERVICE.read_text(encoding="utf-8")
    stream_content = STREAM_ROUTE.read_text(encoding="utf-8")
    gateway_content = GATEWAY_ROUTE.read_text(encoding="utf-8")
    process_content = PROCESS_SERVICE.read_text(encoding="utf-8")

    assert "module_sources" in api_content
    assert "module_sources" in stream_content
    assert "module_sources" in gateway_content
    assert "module_sources" in process_content
    assert "verified" in process_content
    assert "warnings" in process_content


def test_asset_consensus_audit_doc_exists():
    content = AUDIT_DOC.read_text(encoding="utf-8")
    assert "Exact data path" in content
    assert "Remaining limitations" in content
