FROM python:3.11-slim

WORKDIR /app

# Copy optimizer service
COPY optimizer_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY optimizer_service/ /app/optimizer_service/
COPY consensus_engine/config/ /app/consensus_engine/config/

WORKDIR /app/optimizer_service

ENV PYTHONUNBUFFERED=1

EXPOSE 8008

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008", "--workers", "1"]
