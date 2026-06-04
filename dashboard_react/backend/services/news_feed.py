"""
AEGIS Gerçek Haber Akışı — ücretsiz RSS kaynaklarından canlı kripto haberleri.

Statik news servisinin yerine GERÇEK, TAZE haber çeker:
  • CoinDesk, Cointelegraph, Decrypt, Bitcoin Magazine RSS (key gerektirmez)
  • xml.etree ile parse (yeni bağımlılık yok)
  • Keyword-tabanlı duygu analizi (boğa/ayı sözlüğü)
  • Recency ağırlıklı skor (yeni haber > eski haber)
  • Sembol filtresi (BTC/ETH/SOL/XRP başlıklarına göre)

10 dakika önbellekli (RSS sürekli değişmez, rate-limit dostu).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

# ── Ücretsiz RSS kaynakları (key yok) ──────────────────────────────────────────
_RSS_FEEDS = [
    ("CoinDesk",       "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph",  "https://cointelegraph.com/rss"),
    ("Decrypt",        "https://decrypt.co/feed"),
    ("BitcoinMag",     "https://bitcoinmagazine.com/.rss/full/"),
]

# ── Duygu sözlüğü (kripto-özel) ────────────────────────────────────────────────
_BULLISH = {
    "surge", "surges", "rally", "rallies", "soar", "soars", "gain", "gains", "jump",
    "record", "all-time high", "ath", "adopt", "adoption", "approve", "approval", "etf",
    "institutional", "bullish", "breakout", "boost", "rise", "rises", "rebound", "recovery",
    "inflow", "inflows", "buy", "accumulate", "upgrade", "partnership", "launch", "milestone",
    "soaring", "skyrocket", "green", "pump", "moon", "support",
}
_BEARISH = {
    "crash", "crashes", "plunge", "plunges", "dump", "dumps", "hack", "hacked", "exploit",
    "ban", "banned", "lawsuit", "sue", "sued", "fraud", "scam", "bearish", "selloff", "sell-off",
    "decline", "declines", "drop", "drops", "fall", "falls", "fear", "liquidation", "liquidated",
    "outflow", "outflows", "warning", "investigation", "sec", "regulatory", "crackdown", "delist",
    "collapse", "bankruptcy", "default", "red", "tumble", "slump", "correction", "risk",
    "bleed", "bleeds", "erasing", "erase", "erases", "loss", "losses", "weak", "weakness",
    "sinks", "sink", "down", "lower", "below", "struggle", "struggles", "pressure", "shed",
    "wipeout", "wiped", "panic", "capitulation", "breakdown", "reject", "rejected", "halt",
}

_SYMBOL_KEYWORDS = {
    "BTC": {"bitcoin", "btc", "satoshi"},
    "ETH": {"ethereum", "eth", "ether", "vitalik"},
    "SOL": {"solana", "sol"},
    "XRP": {"ripple", "xrp"},
}

# ── Önbellek ────────────────────────────────────────────────────────────────────
_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL = 600.0  # 10 dakika
_lock = asyncio.Lock()


def _classify(title: str) -> float:
    """Başlık duygusu: -1 (çok ayı) .. +1 (çok boğa)."""
    t = title.lower()
    words = set(re.findall(r"[a-z\-]+", t))
    bull = len(words & _BULLISH) + sum(1 for p in _BULLISH if " " in p and p in t)
    bear = len(words & _BEARISH) + sum(1 for p in _BEARISH if " " in p and p in t)
    if bull == 0 and bear == 0:
        return 0.0
    return (bull - bear) / (bull + bear)


def _detect_symbols(title: str) -> list[str]:
    t = title.lower()
    found = []
    for sym, kws in _SYMBOL_KEYWORDS.items():
        if any(k in t for k in kws):
            found.append(sym)
    return found


async def _fetch_feed(client: httpx.AsyncClient, source: str, url: str) -> list[dict]:
    """Tek RSS feed'i çek ve parse et."""
    try:
        r = await client.get(url, headers={"User-Agent": "AEGIS/1.0"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        items = []
        # RSS 2.0: channel/item ; Atom: entry
        for item in root.iter():
            tag = item.tag.lower().split("}")[-1]
            if tag not in ("item", "entry"):
                continue
            title = None
            pub = None
            link = None
            for child in item:
                ctag = child.tag.lower().split("}")[-1]
                if ctag == "title" and child.text:
                    title = child.text.strip()
                elif ctag in ("pubdate", "published", "updated") and child.text:
                    pub = child.text.strip()
                elif ctag == "link":
                    link = child.text.strip() if child.text else child.get("href")
            if not title:
                continue
            # Tarih parse
            ts = None
            if pub:
                try:
                    dt = parsedate_to_datetime(pub)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts = dt
                except Exception:
                    try:
                        ts = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    except Exception:
                        ts = None
            items.append({
                "title": title, "source": source, "link": link,
                "published": ts.isoformat() if ts else None,
                "_ts": ts,
            })
        return items
    except Exception as exc:
        logger.debug("RSS fetch failed %s: %s", source, exc)
        return []


async def _build_news() -> dict:
    """Tüm feed'leri çek, analiz et, agregat skor üret."""
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch_feed(client, s, u) for s, u in _RSS_FEEDS],
            return_exceptions=True,
        )
    all_items: list[dict] = []
    for res in results:
        if isinstance(res, list):
            all_items.extend(res)

    if not all_items:
        return {"available": False, "count": 0}

    now = datetime.now(timezone.utc)
    enriched = []
    for it in all_items:
        ts = it.get("_ts")
        age_h = (now - ts).total_seconds() / 3600 if ts else 72.0
        if age_h > 96:  # 4 günden eski → atla
            continue
        sentiment = _classify(it["title"])
        symbols = _detect_symbols(it["title"])
        # Recency ağırlığı: 0-24h tam, sonra üstel sönüm
        recency_w = max(0.15, 2.718 ** (-age_h / 36.0))
        enriched.append({
            "title": it["title"], "source": it["source"], "link": it.get("link"),
            "published": it.get("published"), "age_h": round(age_h, 1),
            "sentiment": round(sentiment, 3), "symbols": symbols,
            "recency_w": round(recency_w, 3),
        })

    if not enriched:
        return {"available": False, "count": 0}

    # En yeni önce
    enriched.sort(key=lambda x: x["age_h"])

    # Agregat duygu (recency ağırlıklı)
    tot_w = sum(e["recency_w"] for e in enriched)
    agg_sentiment = sum(e["sentiment"] * e["recency_w"] for e in enriched) / max(tot_w, 1e-6)

    # 24s içindeki haber sayısı (aktivite göstergesi)
    count_24h = sum(1 for e in enriched if e["age_h"] <= 24)
    count_total = len(enriched)

    # Etki skoru: duygu gücü × aktivite (çok haber = yüksek etki)
    activity_factor = min(1.0, count_24h / 20.0)  # 20+ haber/gün = tam aktivite
    impact_score = 50 + agg_sentiment * 40 * (0.5 + 0.5 * activity_factor)

    return {
        "available": True,
        "aggregated_sentiment": round(agg_sentiment, 4),
        "crypto_impact_score": round(min(max(impact_score, 0), 100), 1),
        "count_total": count_total,
        "count_24h": count_24h,
        "sources": sorted(set(e["source"] for e in enriched)),
        "newest_age_h": enriched[0]["age_h"],
        "top_headlines": enriched[:12],
        "fetched_at": now.isoformat(),
    }


async def get_live_news(symbol: str = "BTC") -> dict:
    """
    Sembol için gerçek haber analizi (10dk önbellekli).
    Çıktı: impact_score, sentiment, gerçek başlıklar, kaynak sayısı.
    """
    now = time.time()
    async with _lock:
        if _CACHE["data"] is None or (now - _CACHE["ts"]) > _CACHE_TTL:
            data = await _build_news()
            if data.get("available"):
                _CACHE["data"] = data
                _CACHE["ts"] = now
        data = _CACHE["data"] or {"available": False, "count": 0}

    if not data.get("available"):
        return data

    # Sembol filtresi: ilgili başlıkları öne çıkar
    sym = symbol.replace("/USDT", "").replace("/", "").upper()
    headlines = data.get("top_headlines", [])
    sym_headlines = [h for h in headlines if sym in h.get("symbols", [])]
    # Sembol haberi varsa onlardan duygu hesapla, yoksa genel
    if sym_headlines:
        tot_w = sum(h["recency_w"] for h in sym_headlines)
        sym_sentiment = sum(h["sentiment"] * h["recency_w"] for h in sym_headlines) / max(tot_w, 1e-6)
    else:
        sym_sentiment = data["aggregated_sentiment"]

    return {
        **data,
        "symbol": sym,
        "symbol_sentiment": round(sym_sentiment, 4),
        "symbol_headline_count": len(sym_headlines),
        "display_headlines": (sym_headlines or headlines)[:8],
    }
