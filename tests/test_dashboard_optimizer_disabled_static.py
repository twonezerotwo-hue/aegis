from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKTEST_V2 = REPO_ROOT / "dashboard_react" / "frontend" / "src" / "pages" / "BacktestV2.tsx"


def test_backtest_v2_does_not_render_optimizer_panel():
    content = BACKTEST_V2.read_text(encoding="utf-8")

    assert "OptimizerAgentPanel" not in content
    assert "/api/optimizer" not in content
    assert "Light Optimize" not in content
    assert "Apply to Consensus" not in content
    assert "Rollback" not in content

