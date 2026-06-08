# AEGIS Docker Runtime Consistency

Date: 2026-06-08

## Expected Containers

The dashboard runtime should be served by the current project images:

- `aegis_codex-dashboard-backend`
- `aegis_codex-dashboard-frontend`

Expected containers:

- `aegis-dashboard-backend` on port `8502`
- `aegis-dashboard-frontend` on port `3001`

## Known Network Context

`docker-compose.yml` still references the external network:

- `aegis_clean_v71_aegis_network`

Reason: some legacy services were previously attached through that network alias. Removing it abruptly can break service-to-service name resolution for running containers.

## Consistency Rules

- No stale `aegis_clean_v71` image should serve `8502` or `3001`.
- Dashboard backend should expose `/health`, `/api/macro`, `/api/system/modules`, and `/api/system/providers`.
- Dashboard frontend should respond on `/` and `/v2`.
- Optional services should be controlled through compose profiles, not always-on runtime.

## Current Low-Resource Profile

Previously added compose profiles:

- `observe`: Grafana/exporters/Pushgateway/metrics-pusher.
- `research`: optimizer/macro-bridge.

These keep non-core services out of the default startup path.

## Remaining Work

- Current inspected dashboard containers:
  - `aegis-dashboard-backend`: image `aegis_codex-dashboard-backend`, status `running`, health `healthy`, port `8502`.
  - `aegis-dashboard-frontend`: image `aegis_codex-dashboard-frontend`, status `running`, health check not defined, port `3001`.
- Runtime update was applied with `docker cp` and container restart to avoid the previous heavy rebuild/download timeout path.
- Rebuild the images from this branch before treating the container filesystem update as permanent.
- Do not remove the external network until all dependent services are verified without it.
