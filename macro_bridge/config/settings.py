from dataclasses import dataclass
import os

DXY_THRESHOLDS = {"risk_off": 104, "liquidity_expansion": 101}
VIX_THRESHOLDS = {"risk_off": 20, "liquidity_expansion": 16}
US10Y_THRESHOLDS = {"risk_off": 4.5, "liquidity_expansion": 4.0}
BRENT_THRESHOLD = 95

POSITION_SIZE = {"risk_on": 0.25, "risk_off": 0.10, "normal": 0.15}
STOP_LOSS = {"risk_on": 0.12, "risk_off": 0.06, "normal": 0.08}
HEDGE_TRIGGERS = {"vix": 22, "dxy": 103, "us10y": 4.6}


@dataclass(frozen=True)
class Settings:
    consensus_base_url: str = os.getenv("AEGIS_CONSENSUS_URL", "http://localhost:8005")
    cbr_base_url: str = os.getenv("AEGIS_CBR_URL", "http://localhost:8010")
    timeout_sec: float = float(os.getenv("MACRO_BRIDGE_TIMEOUT", "6"))
    redis_url: str = os.getenv("MACRO_BRIDGE_REDIS_URL", "redis://localhost:6379/9")
