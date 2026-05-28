FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY modules/news-ai-limited/requirements.txt .
ENV PIP_DEFAULT_TIMEOUT=180
RUN pip install --no-cache-dir --retries 8 -r requirements.txt

# Copy application code
COPY shared /app/shared
COPY modules/news-ai-limited /app

ENV PYTHONPATH=/app

# Expose port
EXPOSE 8006

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1

# Run application
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8006"]
