from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ALLOCATION_COMPONENT = ROOT / "frontend" / "src" / "components" / "portfolio" / "AllocationWithTip.tsx"


def _read_component() -> str:
    return ALLOCATION_COMPONENT.read_text(encoding="utf-8")


def test_allocation_horizon_label_exists():
    content = _read_component()
    assert "Allocation horizon:" in content
    assert "Allocation profile:" in content


def test_fallback_illustrative_text_still_exists():
    content = _read_component()
    assert "Illustrative allocation based on incomplete/fallback macro data." in content


def test_verified_rebalance_language_is_gated_behind_live_verified_macro():
    content = _read_component()
    assert 'const liveVerifiedMacro =' in content
    assert 'macro.data_status === "LIVE"' in content
    assert 'macro.verified === true' in content
    assert 'macro.live === true' in content
    assert re.search(r'const tip = liveVerifiedMacro\s*\?', content)
    assert "Verified allocation decision unavailable because macro data is not fully verified." in content
