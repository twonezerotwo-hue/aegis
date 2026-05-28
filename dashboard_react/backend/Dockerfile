FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only dashboard backend files (not backtest or strategies)
# Context is ./dashboard_react/backend so paths are relative to that
COPY routes ./routes
COPY services ./services
COPY backtest ./backtest
COPY main.py .

# Disable Python bytecode cache to ensure fresh imports
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8502/health || exit 1

CMD ["python", "main.py"]

