"""
Prometheus client service for real metrics collection
Queries actual metrics from Prometheus and normalizes them
"""
import logging
import httpx
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Timeframe to Prometheus duration mapping
TIMEFRAME_MAPPING = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "24h",
    "1w": "168h",
    "1month": "720h",
}



class PrometheusClient:
    """Client for Prometheus metrics with real query handling"""

    def __init__(self, url: str = "http://localhost:9090"):
        self.url = url
        self.timeout = 30.0  # Increased from 5.0s for slow Prometheus instances
        self.allow_unlabelled_fallback = os.getenv("ALLOW_UNLABELLED_PROMETHEUS_FALLBACK", "false").lower() == "true"

    async def query(self, query_string: str) -> Optional[Dict[str, Any]]:
        """Execute PromQL query and return normalized results"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.url}/api/v1/query",
                    params={"query": query_string}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "success" and data["data"]["result"]:
                        return self._normalize_result(data["data"]["result"])
            return None
        except Exception as e:
            logger.error(f"Prometheus query error: {e}")
            return None

    async def query_range(self, query_string: str, duration: str = "1h") -> Optional[Dict[str, Any]]:
        """Execute PromQL range query and return normalized results"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.url}/api/v1/query_range",
                    params={
                        "query": query_string,
                        "start": f"now-{duration}",
                        "end": "now",
                        "step": "60s"
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "success" and data["data"]["result"]:
                        return self._normalize_result(data["data"]["result"])
            return None
        except Exception as e:
            logger.error(f"Prometheus range query error: {e}")
            return None

    async def get_metric_average(self, metric_name: str, timeframe: str = "1h", labels: Dict[str, str] = None) -> Optional[float]:
        """Get average metric value over timeframe using avg_over_time - NO FALLBACK"""
        try:
            range_map = {
                "5m": "5m", "15m": "15m", "1h": "1h",
                "4h": "4h", "1d": "1d", "1w": "1w", "1month": "30d"
            }
            duration = range_map.get(timeframe, "1h")

            # Try with labels first (if symbol label exists in Prometheus)
            if labels and "symbol" in labels:
                query = f'avg_over_time({metric_name}{{symbol="{labels["symbol"]}"}}[{duration}])'
                result = await self.query(query)
                if result and "value" in result:
                    return float(result["value"])

            if self.allow_unlabelled_fallback:
                query = f'avg_over_time({metric_name}[{duration}])'
                result = await self.query(query)
                if result and "value" in result:
                    return float(result["value"])

            logger.debug(f"No data for {metric_name} with timeframe {timeframe}")
            return None
        except Exception as e:
            logger.error(f"Error in get_metric_average({metric_name}, {timeframe}): {e}")
            return None

    async def get_metric_value(self, metric_name: str, labels: Dict[str, str] = None) -> Optional[float]:
        """Get single metric value"""
        try:
            # Build PromQL query
            if labels:
                label_str = ",".join([f'{k}="{v}"' for k, v in labels.items()])
                query = f'{metric_name}{{{label_str}}}'
            else:
                query = metric_name

            result = await self.query(query)
            if result and "value" in result:
                return float(result["value"])
            return None
        except Exception as e:
            logger.error(f"Error getting metric value: {e}")
            return None

    async def get_all_metric_instances(self, metric_name: str) -> Dict[str, float]:
        """Get all instances of a metric"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.url}/api/v1/query",
                    params={"query": metric_name}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "success":
                        results = {}
                        for item in data["data"]["result"]:
                            # Extract labels and value
                            labels = item.get("metric", {})
                            value = float(item.get("value", [0, "0"])[1])
                            # Use instance or job as key
                            key = labels.get("instance") or labels.get("job") or str(len(results))
                            results[key] = value
                        return results
            return {}
        except Exception as e:
            logger.error(f"Error getting metric instances: {e}")
            return {}

    async def get_touche_score(self, symbol: str = "BTC/USDT", timeframe: str = "1h") -> Optional[float]:
        """Get Touche EQS score with timeframe averaging"""
        try:
            # Use avg_over_time for proper time-series averaging
            score = await self.get_metric_average(
                "touche_eqs_score",
                timeframe=timeframe,
                labels={"symbol": symbol}
            )
            if score is not None:
                if score > 1:
                    score = score / 100.0
                return min(max(score, 0.0), 1.0)
            return None
        except Exception as e:
            logger.warning(f"Error getting touche score for {symbol} with timeframe {timeframe}: {e}")
            return None

    async def get_fundamental_score(self, symbol: str = "BTC/USDT", timeframe: str = "1h") -> Optional[float]:
        """Get Fundamental score with timeframe averaging"""
        try:
            # Use avg_over_time for proper time-series averaging
            score = await self.get_metric_average(
                "fundamental_score",
                timeframe=timeframe,
                labels={"symbol": symbol}
            )
            if score is not None:
                if score > 1:
                    score = score / 100.0
                return min(max(score, 0.0), 1.0)
            return None
        except Exception as e:
            logger.warning(f"Error getting fundamental score for {symbol} with timeframe {timeframe}: {e}")
            return None

    async def get_quantum_pnl(self, symbol: str = "BTC/USDT", timeframe: str = "1h") -> Optional[float]:
        """Get Quantum PnL (normalized to 0-1 scale) with timeframe averaging"""
        try:
            # Use avg_over_time for proper time-series averaging
            pnl = await self.get_metric_average(
                "quantum_pnl",
                timeframe=timeframe,
                labels={"symbol": symbol}
            )

            if pnl is not None:
                max_pnl = 50000.0
                # Return proportional score, no fallback
                score = min(abs(float(pnl)) / max_pnl, 1.0)
                return score

            return None
        except Exception as e:
            logger.error(f"Error getting quantum pnl for {symbol} with timeframe {timeframe}: {e}", exc_info=True)
            return None

    async def get_sentinel_multiplier(self, symbol: str = "BTC/USDT", timeframe: str = "1h") -> Optional[float]:
        """Get Sentinel multiplier (convert to 0-1 score) with timeframe averaging"""
        try:
            # Use avg_over_time for proper time-series averaging
            multiplier = await self.get_metric_average(
                "sentinel_multiplier",
                timeframe=timeframe,
                labels={"symbol": symbol}
            )
            if multiplier is not None:
                score = min(multiplier / 2.0, 1.0)
                return max(score, 0.0)
            return None
        except Exception as e:
            logger.warning(f"Error getting sentinel multiplier for {symbol} with timeframe {timeframe}: {e}")
            return None

    async def get_news_sentiment_score(self, timeframe: str = "1h") -> Optional[float]:
        """Get News sentiment score with timeframe averaging"""
        try:
            # Use avg_over_time for proper time-series averaging (no symbol label for news)
            score = await self.get_metric_average(
                "news_sentiment_score",
                timeframe=timeframe
            )
            if score is not None:
                if score > 1:
                    score = score / 100.0
                return score
            return None
        except Exception as e:
            logger.warning(f"Error getting news sentiment score with timeframe {timeframe}: {e}")
            return None

    def _normalize_result(self, result_list: list) -> Optional[Dict[str, Any]]:
        """Normalize Prometheus API result"""
        if not result_list:
            return None

        first_result = result_list[0]
        metric = first_result.get("metric", {})
        value_pair = first_result.get("value", [0, "0"])

        return {
            "metric": metric,
            "value": float(value_pair[1]) if len(value_pair) > 1 else 0.0,
            "timestamp": int(value_pair[0]) if value_pair else 0
        }

    async def get_targets_status(self) -> Dict[str, bool]:
        """Get Prometheus targets health status"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.url}/api/v1/targets")
                if response.status_code == 200:
                    data = response.json()
                    targets = data.get("data", {}).get("activeTargets", [])
                    status = {}
                    for target in targets:
                        job = target.get("labels", {}).get("job", "unknown")
                        health = target.get("health", "down") == "up"
                        status[job] = health
                    return status
            return {}
        except Exception as e:
            logger.error(f"Error getting targets status: {e}")
            return {}
