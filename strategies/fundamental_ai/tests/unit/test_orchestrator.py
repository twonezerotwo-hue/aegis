import pytest
import asyncio
from engine.orchestrator import MetricOrchestrator

class MockClient:
    async def fetch_metric(self, symbol, metric_name=None):
        return {"value": 85.0}

class SlowMockClient:
    async def fetch_metric(self, symbol, metric_name=None):
        # Bilinçli olarak timeout süresinden (2.0s) fazla bekletir
        await asyncio.sleep(2.5)
        return {"value": 0.0}

@pytest.mark.asyncio
async def test_orchestrator_successful_gather():
    fast_client = MockClient()
    
    config = [
        {"name": "mvrv", "client": fast_client, "method": "fetch_metric"},
        {"name": "puell", "client": fast_client, "method": "fetch_metric"}
    ]
    orchestrator = MetricOrchestrator(config)
    results = await orchestrator.fetch_all_metrics("BTCUSDT")
    
    assert results["mvrv"] == {"value": 85.0}
    assert results["puell"] == {"value": 85.0}

@pytest.mark.asyncio
async def test_orchestrator_timeout_fallback():
    slow_client = SlowMockClient()
    fast_client = MockClient()
    
    config = [
        {"name": "slow_metric", "client": slow_client, "method": "fetch_metric"},
        {"name": "fast_metric", "client": fast_client, "method": "fetch_metric"}
    ]
    orchestrator = MetricOrchestrator(config)
    # Hızlı test olması için timeoutu daralttık
    orchestrator.timeout_seconds = 0.5 
    
    results = await orchestrator.fetch_all_metrics("BTCUSDT")
    
    # Timeout'a takılanın None, diğerinin başarılı devam etmesi gerekir
    assert results["slow_metric"] is None
    assert results["fast_metric"] == {"value": 85.0}
