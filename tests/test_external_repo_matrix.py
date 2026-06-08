from aegis_research.external_repo_matrix import (
    SAFE_MODE,
    repo_feature_table_rows,
    top10_external_repo_matrix,
)
from aegis_research.models import FORBIDDEN_SAFE_FIELDS


def test_top10_external_repo_matrix_is_research_only_catalog():
    matrix = top10_external_repo_matrix()

    assert matrix["status"] == "ok"
    assert matrix["safe_mode"] == SAFE_MODE
    assert matrix["count"] == 10
    assert len(matrix["items"]) == 10
    assert not FORBIDDEN_SAFE_FIELDS.intersection(matrix.keys())


def test_top10_external_repo_matrix_contains_expected_repos():
    repos = {item["repo"] for item in top10_external_repo_matrix()["items"]}

    assert "OpenBB-finance/OpenBB" in repos
    assert "freqtrade/freqtrade" in repos
    assert "microsoft/qlib" in repos
    assert "ccxt/ccxt" in repos
    assert "ProsusAI/finBERT" in repos
    assert "DemonDamon/FinnewsHunter" in repos


def test_repo_feature_table_rows_are_compact_and_safe():
    rows = repo_feature_table_rows()

    assert len(rows) == 10
    for row in rows:
        assert {"repo", "category", "aegis_status", "best_feature", "safe_target", "phase", "license"} <= set(row)
        assert not FORBIDDEN_SAFE_FIELDS.intersection(row.keys())
