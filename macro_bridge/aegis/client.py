from typing import Dict, Iterable

import requests

from macro_bridge.config.settings import Settings


def _try_paths(base_url: str, paths: Iterable[str], params: Dict[str, str]) -> Dict:
    for path in paths:
        try:
            response = requests.get(f"{base_url.rstrip('/')}{path}", params=params, timeout=Settings().timeout_sec)
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            continue
    return {"status": "unavailable", "source": base_url}


def get_consensus(symbol: str, timeframe: str) -> Dict:
    """Calls AEGIS Consensus API and returns normalized payload."""
    params = {"symbol": symbol, "timeframe": timeframe}
    payload = _try_paths(
        Settings().consensus_base_url,
        paths=("/consensus", "/api/consensus", "/signal", "/health"),
        params=params,
    )
    if "decision" not in payload:
        payload.setdefault("decision", "HOLD")
    payload.setdefault("confidence", 0.5)
    return payload


def get_cbr_decision(fingerprint: str) -> Dict:
    """Calls CBR Engine endpoint and returns fallback-safe output."""
    params = {"fingerprint": fingerprint}
    payload = _try_paths(
        Settings().cbr_base_url,
        paths=("/decision", "/api/decision", "/cbr/decision", "/health"),
        params=params,
    )
    if "decision" not in payload:
        payload.setdefault("decision", "HOLD")
    payload.setdefault("confidence", 0.5)
    return payload
