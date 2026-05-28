import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


# ============ RISK PRESETS (v7.5) ============
_RISK_PRESETS = {
    "conservative": {"kelly_cap": 0.15, "sl_pct": 1.5, "tp_pct": 3.0, "max_dd": 3.0},
    "moderate":     {"kelly_cap": 0.25, "sl_pct": 2.0, "tp_pct": 4.0, "max_dd": 5.0},
    "aggressive":   {"kelly_cap": 0.35, "sl_pct": 3.0, "tp_pct": 6.0, "max_dd": 8.0},
}


def apply_risk_presets(
    profile: str = "moderate",
    kelly_cap: float | None = None,
    sl_pct: float | None = None,
    tp_pct: float | None = None,
    max_dd: float | None = None,
) -> dict:
    """Return risk parameters: preset-based defaults overridden by explicit values."""
    base = _RISK_PRESETS.get(profile, _RISK_PRESETS["moderate"])
    return {
        "kelly_cap": kelly_cap if kelly_cap is not None else base["kelly_cap"],
        "sl_pct": sl_pct if sl_pct is not None else base["sl_pct"],
        "tp_pct": tp_pct if tp_pct is not None else base["tp_pct"],
        "max_dd": max_dd if max_dd is not None else base["max_dd"],
    }


# ============ POSITION TRACKING (v7.4) ============
_active_positions: Dict[str, dict] = {}


def get_position(symbol: str) -> Optional[dict]:
    """Return active position for a symbol, or None."""
    return _active_positions.get(symbol)


def update_position(symbol: str, side: str, qty: float, entry_price: float, pnl: float = 0.0):
    """Update or create tracked position."""
    _active_positions[symbol] = {
        "side": side,
        "quantity": qty,
        "entry_price": entry_price,
        "pnl": pnl,
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }


def close_position(symbol: str):
    """Remove a position from tracking."""
    _active_positions.pop(symbol, None)


class BinanceTestnetExecutor:
    """Thin async Binance Testnet order bridge with optional dry-run mode."""

    def __init__(self, api_key: str, api_secret: str, base_url: str, dry_run: bool = True):
        self.api_key = api_key or ""
        self.api_secret = (api_secret or "").encode()
        self.base_url = (base_url or "https://testnet.binance.vision").rstrip("/")
        self.dry_run = dry_run
        self.session = httpx.AsyncClient(timeout=10)
        self._time_offset_ms: int = 0  # local - server offset

    async def _sync_time(self) -> None:
        """Sync local clock with Binance server to avoid timestamp errors."""
        try:
            resp = await self.session.get(f"{self.base_url}/api/v3/time", timeout=5)
            server_ts = resp.json()["serverTime"]
            local_ts = int(time.time() * 1000)
            self._time_offset_ms = local_ts - server_ts
            logger.info(f"Binance time sync: offset={self._time_offset_ms}ms")
        except Exception as e:
            logger.warning(f"Binance time sync failed, using local clock: {e}")
            self._time_offset_ms = 0

    def _server_timestamp(self) -> int:
        """Return a timestamp adjusted for server clock difference."""
        return int(time.time() * 1000) - self._time_offset_ms

    @staticmethod
    def _qs(params: Dict[str, str]) -> str:
        """Build query-string from an *already string-valued* dict."""
        return "&".join(f"{k}={v}" for k, v in params.items())

    def _sign(self, query_string: str) -> str:
        return hmac.new(self.api_secret, query_string.encode(), hashlib.sha256).hexdigest()

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        order_type: str = "LIMIT",
    ) -> Dict[str, Any]:
        """Place order on Binance test endpoint (or simulated dry-run)."""
        if self.dry_run:
            update_position(symbol, side.upper(), qty, price or 0.0)
            return {
                "success": True,
                "order_id": f"dryrun-{int(time.time() * 1000)}",
                "dry_run": True,
                "position": get_position(symbol),
            }

        # Sync clock on first real call
        if self._time_offset_ms == 0:
            await self._sync_time()

        # All values MUST be strings so the signed QS == the sent QS
        params: Dict[str, str] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(qty),
            "timestamp": str(self._server_timestamp()),
            "recvWindow": "5000",
        }
        if price is not None and order_type.upper() == "LIMIT":
            params["price"] = str(price)
            params["timeInForce"] = "GTC"

        qs = self._qs(params)
        sig = self._sign(qs)
        # Build the full URL ourselves — no httpx param serialization
        url = f"{self.base_url}/api/v3/order/test?{qs}&signature={sig}"
        headers = {"X-MBX-APIKEY": self.api_key}

        logger.debug(f"Binance signed QS: {qs}")

        try:
            resp = await self.session.post(url, headers=headers)
            if resp.status_code != 200:
                body = resp.text
                logger.error(f"Binance order rejected: {resp.status_code} {body}")
                return {"success": False, "error": body, "dry_run": False}
            payload = resp.json() if resp.content else {}
            update_position(symbol, side.upper(), qty, price or 0.0)
            return {
                "success": True,
                "order_id": payload.get("orderId"),
                "dry_run": False,
                "position": get_position(symbol),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "dry_run": False}

    async def close(self) -> None:
        await self.session.aclose()
