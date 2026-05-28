# AEGIS v7.2 — ClickHouse write-path smoke test.
import os

import httpx


def _query_url() -> str:
    # Host-side pytest icin localhost, container icinde clickhouse kullanilabilir.
    return os.getenv("CLICKHOUSE_HTTP_URL", "http://localhost:8123")


def _auth_params() -> dict[str, str]:
    return {
        "user": os.getenv("CLICKHOUSE_USER", "default"),
        "password": os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass"),
        "database": os.getenv("CLICKHOUSE_DB", "aegis"),
    }


def test_clickhouse_write_smoke() -> None:
    base = _query_url()
    params = _auth_params()

    create_db = "CREATE DATABASE IF NOT EXISTS aegis"
    create_db_resp = httpx.post(base, params=params, data=create_db, timeout=10.0)
    assert create_db_resp.status_code == 200, create_db_resp.text

    create_table = (
        "CREATE TABLE IF NOT EXISTS trades ("
        "symbol String, action String, timestamp DateTime"
        ") ENGINE=MergeTree ORDER BY timestamp"
    )
    create_resp = httpx.post(base, params=params, data=create_table, timeout=10.0)
    assert create_resp.status_code == 200, create_resp.text

    insert_sql = "INSERT INTO trades (symbol, action, timestamp) VALUES ('TEST', 'BUY', now())"
    response = httpx.post(base, params=params, data=insert_sql, timeout=10.0)
    assert response.status_code == 200, response.text

    verify_sql = "SELECT count() FROM trades WHERE symbol='TEST' FORMAT TabSeparated"
    verify = httpx.post(base, params=params, data=verify_sql, timeout=10.0)
    assert verify.status_code == 200, verify.text
    assert int(verify.text.strip() or "0") >= 1
