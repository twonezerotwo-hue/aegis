"""
AEGIS Bildirim/Uyarı Servisi — sinyal, hata, kill-switch olaylarını duyurur.

İki kanal:
  1. Uygulama-içi akış (her zaman çalışır, dashboard okur) — kalıcı
  2. Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env varsa) — opsiyonel

Kullanım: from services.notifier import notify; notify("signal", "Agent BTC BUY", level="info")
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.getenv("AGENT_DATA_DIR", "/app/data")
_ALERTS_PATH = os.path.join(_DATA_DIR, "alerts.jsonl")
_MAX_MEM = 200

_alerts: deque = deque(maxlen=_MAX_MEM)
_loaded = False

# Telegram (opsiyonel)
_TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "").strip()

_LEVEL_EMOJI = {"info": "ℹ️", "signal": "📊", "success": "✅", "warning": "⚠️", "error": "🔴", "critical": "🚨"}


def _load():
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if os.path.exists(_ALERTS_PATH):
            with open(_ALERTS_PATH, "r", encoding="utf-8") as f:
                for ln in f.readlines()[-_MAX_MEM:]:
                    try:
                        _alerts.append(json.loads(ln))
                    except Exception:
                        pass
    except Exception:
        pass


def _send_telegram(text: str) -> bool:
    if not (_TG_TOKEN and _TG_CHAT):
        return False
    try:
        import httpx
        r = httpx.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json={"chat_id": _TG_CHAT, "text": text, "parse_mode": "HTML"},
            timeout=8.0,
        )
        return r.status_code == 200
    except Exception as exc:
        logger.debug("telegram send failed: %s", exc)
        return False


def notify(category: str, message: str, level: str = "info", meta: Optional[dict] = None) -> dict:
    """
    Uyarı yayınla. category: signal|kill_switch|optimizer|error|system
    level: info|signal|success|warning|error|critical
    """
    _load()
    emoji = _LEVEL_EMOJI.get(level, "•")
    alert = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "level": level,
        "message": message,
        "meta": meta or {},
    }
    _alerts.append(alert)
    # Kalıcı
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_ALERTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Telegram (önemli seviyeler)
    tg_sent = False
    if level in ("signal", "success", "warning", "error", "critical"):
        tg_sent = _send_telegram(f"{emoji} <b>AEGIS {category}</b>\n{message}")
    alert["telegram_sent"] = tg_sent
    if level in ("error", "critical", "warning"):
        logger.warning("ALERT[%s/%s] %s", category, level, message)
    else:
        logger.info("ALERT[%s/%s] %s", category, level, message)
    return alert


def get_alerts(limit: int = 50, category: Optional[str] = None) -> list[dict]:
    _load()
    items = list(_alerts)
    if category:
        items = [a for a in items if a.get("category") == category]
    return items[-limit:][::-1]


def status() -> dict:
    _load()
    return {
        "total": len(_alerts),
        "telegram_configured": bool(_TG_TOKEN and _TG_CHAT),
        "telegram_token_set": bool(_TG_TOKEN),
        "telegram_chat_set": bool(_TG_CHAT),
        "recent": get_alerts(limit=10),
    }
