from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from datetime import datetime, timezone

try:
    from models.attribution import ExitAttributionResponse
    from services.attribution_engine import ExitAttributionEngine
except ModuleNotFoundError:
    from strategies.analyzer_ai.models.attribution import ExitAttributionResponse
    from strategies.analyzer_ai.services.attribution_engine import ExitAttributionEngine

app = FastAPI(title="AEGIS Analyzer AI", version="2.0")
exit_attribution_engine = ExitAttributionEngine()

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisData(BaseModel):
    touche: float = 50
    fundamental: float = 50
    news: float = 50

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "analyzer-ai"}

@app.post("/analyze")
async def analyze(data: AnalysisData):
    """Analyze AI scores and return recommendation"""
    # Normalize input: handle both 0-1 and 0-100 ranges
    touche = data.touche
    fundamental = data.fundamental
    news = data.news

    # If values are 0-1 range (e.g., 0.6256), convert to 0-100
    if 0 < touche <= 1:
        touche = touche * 100
    if 0 < fundamental <= 1:
        fundamental = fundamental * 100
    if 0 < news <= 1:
        news = news * 100

    # Ensure all values are in 0-100 range
    touche = max(0, min(100, touche))
    fundamental = max(0, min(100, fundamental))
    news = max(0, min(100, news))

    # Calculate weighted consensus score (0-100 range)
    score = (touche * 0.50) + (fundamental * 0.35) + (news * 0.15)
    score = max(0, min(100, score))  # Ensure 0-100

    # Generate recommendation
    if score > 65:
        recommendation = "BUY"
    elif score < 35:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    # Calculate confidence (0-1 range based on distance from neutral 50)
    confidence = min(abs(score - 50) / 50, 1.0)

    return {
        "success": True,
        "recommendation": recommendation,
        "score": round(score, 2),  # 62.56 format
        "confidence": round(confidence, 2),  # 0-1 range
        "modules": {
            "touche": round(max(0, min(100, touche)), 2),
            "fundamental": round(max(0, min(100, fundamental)), 2),
            "news": round(max(0, min(100, news)), 2),
            "recommendation": recommendation
        }
    }

@app.get("/analyze")
async def analyze_get(
    touche: float = 50,
    fundamental: float = 50,
    news: float = 50
):
    """Analyze via GET request - with automatic normalization"""
    # Normalize input: handle both 0-1 and 0-100 ranges
    if 0 < touche <= 1:
        touche = touche * 100
    if 0 < fundamental <= 1:
        fundamental = fundamental * 100
    if 0 < news <= 1:
        news = news * 100

    data = AnalysisData(touche=touche, fundamental=fundamental, news=news)
    return await analyze(data)


@app.get("/dashboard/attribution")
async def dashboard_attribution(
    touche: float = 50,
    fundamental: float = 50,
    news: float = 50,
):
    """Protocol endpoint: Analyzer AI -> Dashboard module attribution."""
    if 0 < touche <= 1:
        touche *= 100
    if 0 < fundamental <= 1:
        fundamental *= 100
    if 0 < news <= 1:
        news *= 100

    weights = {"touche": 0.50, "fundamental": 0.35, "news": 0.15}
    contrib = {
        "touche": round(touche * weights["touche"], 2),
        "fundamental": round(fundamental * weights["fundamental"], 2),
        "news": round(news * weights["news"], 2),
    }
    total = round(contrib["touche"] + contrib["fundamental"] + contrib["news"], 2)
    return {
        "weights": weights,
        "contributions": contrib,
        "total_score": total,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/dashboard/exit_attribution", response_model=ExitAttributionResponse)
async def dashboard_exit_attribution(period: str = "7d"):
    """Exit attribution summary for closed trades (period: 7d, 30d, all)."""
    try:
        # FIX: Engine uses 5-minute Redis/in-memory cache and never logs secrets.
        return exit_attribution_engine.compute(period=period)
    except Exception:
        # Never surface 500 for missing data/schema drift; return empty result.
        return ExitAttributionResponse(period=(period or "7d"), modules={})

if __name__ == "__main__":
    import logging
    logging.info("Starting AEGIS Analyzer AI on 0.0.0.0:8007")
    uvicorn.run(app, host="0.0.0.0", port=8007)
