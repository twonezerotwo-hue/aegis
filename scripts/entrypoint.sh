#!/bin/bash

set -e

SERVICE_NAME=$1

echo "Starting AEGIS Holding - ${SERVICE_NAME} Service"
echo "=================================================="

# Wait for dependencies
echo "Waiting for PostgreSQL..."
until python -c "import psycopg2; psycopg2.connect('${DATABASE_URL}')" 2>/dev/null; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 2
done
echo "PostgreSQL is up!"

echo "Waiting for Redis (optional - will retry in service)..."
python -c "import redis; redis.from_url('${REDIS_URL}').ping()" 2>/dev/null && echo "Redis is up!" || echo "Redis unavailable - service will retry"

# Service-specific startup
case ${SERVICE_NAME} in
    touche-ai)
        echo "Starting Touche AI Module..."
        cd /app/touche_ai
        python -m uvicorn main:app --host 0.0.0.0 --port 8001
        ;;
    fundamental-ai)
        echo "Starting Fundamental AI Module..."
        cd /app/fundamental_ai
        python -m uvicorn main:app --host 0.0.0.0 --port 8002
        ;;
    quantum-ai)
        echo "Starting Quantum AI Module..."
        cd /app/quantum_ai
        python -m uvicorn main:app --host 0.0.0.0 --port 8003
        ;;
    sentinel-ai)
        echo "Starting Sentinel AI Module..."
        cd /app/sentinel_ai
        python -m uvicorn main:app --host 0.0.0.0 --port 8004
        ;;
    consensus-engine)
        echo "Starting Consensus Engine..."
        cd /app/consensus_engine
        python -m uvicorn main:app --host 0.0.0.0 --port 8005
        ;;
    *)
        echo "Unknown service: ${SERVICE_NAME}"
        exit 1
        ;;
esac
