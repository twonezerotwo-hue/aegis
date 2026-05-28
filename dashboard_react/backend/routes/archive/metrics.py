"""
Metrics routes for dashboard
"""
from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/touche")
async def get_touche():
    """Touche EQS Score"""
    return {
        "name": "Touche EQS",
        "score": 0.75,
        "health": "healthy",
        "color": "#3B82F6",
    }


@router.get("/fundamental")
async def get_fundamental():
    """Fundamental Score"""
    return {
        "name": "Fundamental Score",
        "score": 0.68,
        "health": "healthy",
        "color": "#10B981",
    }


@router.get("/quantum")
async def get_quantum():
    """Quantum Score"""
    return {
        "name": "Quantum Score",
        "score": 0.72,
        "health": "healthy",
        "color": "#F59E0B",
    }


@router.get("/sentinel")
async def get_sentinel():
    """Sentinel Score"""
    return {
        "name": "Sentinel Score",
        "score": 0.65,
        "health": "healthy",
        "color": "#8B5CF6",
    }


@router.get("/news")
async def get_news():
    """News Sentiment Score"""
    return {
        "name": "News Sentiment",
        "score": 0.80,
        "health": "healthy",
        "color": "#EC4899",
    }
