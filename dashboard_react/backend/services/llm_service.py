"""
AEGIS LLM Service — Groq (birincil) + Ollama (yerel fallback)

Öncelik:
  1. Groq API  (GROQ_API_KEY varsa — hızlı, ücretsiz bulut)
  2. Ollama    (OLLAMA_BASE_URL varsa — yerel, limitsiz)
  3. Kural tabanlı Türkçe gerekçe (her zaman çalışır, LLM gerekmez)

Kullanım:
    from services.llm_service import LLMService
    svc = LLMService()
    text = await svc.signal_rationale(signal_ctx)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "").strip()
_OLLAMA_BASE    = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL   = os.environ.get("OLLAMA_MODEL", "llama3.2")
_GROQ_MODEL     = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
_TIMEOUT        = float(os.environ.get("LLM_TIMEOUT_SEC", "8"))

# ── Prompt ────────────────────────────────────────────────────────────────────

def _build_prompt(ctx: dict[str, Any]) -> str:
    action       = ctx.get("action", "HOLD")
    confidence   = ctx.get("confidence_pct", 50)
    five_mod     = ctx.get("five_module_score", 0.5)
    regime       = ctx.get("regime", "NORMALIZATION")
    event_risk   = ctx.get("event_risk_pct", 30)
    vix          = ctx.get("vix")
    hyg          = ctx.get("hyg")
    funding      = ctx.get("funding_rate_pct")
    scores: dict = ctx.get("module_scores", {})
    symbol       = ctx.get("symbol", "BTC")
    timeframe    = ctx.get("timeframe", "4h")
    warnings     = ctx.get("warnings", [])

    action_tr = {"BUY": "pozitif aday", "SELL": "negatif aday", "HOLD": "notr / aday yok"}.get(action, action)

    mod_lines = "\n".join(
        f"  - {k.capitalize()}: {round(v*100)}%"
        for k, v in scores.items() if isinstance(v, (int, float))
    )
    macro_lines = "\n".join(filter(None, [
        f"  - VIX: {vix:.1f}" if vix is not None else None,
        f"  - HYG ETF: {hyg:.1f}" if hyg is not None else None,
        f"  - BTC Funding Rate: {funding:+.3f}%" if funding is not None else None,
        f"  - Piyasa Rejimi: {regime}",
        f"  - Olay Riski: {event_risk:.0f}%",
    ]))
    warn_line = f"\nUyarılar: {', '.join(warnings[:2])}" if warnings else ""

    return f"""Sen AEGIS algoritmik trading sisteminin sinyal analisti asistanısın.
Aşağıdaki verilere dayanarak {symbol}/{timeframe} için kısa, net ve profesyonel bir
Türkçe gerekçe yaz. Maksimum 3 cümle. Teknik jargon kullan ama anlaşılır ol.
Sayısal verileri kullan. "Sistem" veya "AEGIS" kelimesini kullanma.

== ADAY DURUMU ==
Aday: {action_tr} (Guven: {confidence}%, 5-Modul: {round(five_mod*100, 1)})

== MODÜL SKORLARI ==
{mod_lines}

== MAKRO ORTAM ==
{macro_lines}{warn_line}

Gerekçe:"""


# ── LLM calls ────────────────────────────────────────────────────────────────

async def _call_groq(prompt: str) -> str | None:
    if not _GROQ_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {_GROQ_API_KEY}"},
                json={
                    "model": _GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.4,
                },
            )
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"]["content"].strip()
                logger.info("llm_groq_ok chars=%d", len(text))
                return text
            logger.warning("groq_http_%d", r.status_code)
    except Exception as exc:
        logger.warning("groq_error: %s", exc)
    return None


async def _call_ollama(prompt: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{_OLLAMA_BASE}/api/generate",
                json={
                    "model": _OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 200, "temperature": 0.4},
                },
            )
            if r.status_code == 200:
                text = r.json().get("response", "").strip()
                logger.info("llm_ollama_ok model=%s chars=%d", _OLLAMA_MODEL, len(text))
                return text
            logger.warning("ollama_http_%d", r.status_code)
    except Exception as exc:
        logger.debug("ollama_error: %s", exc)
    return None


def _rule_based_rationale(ctx: dict[str, Any]) -> str:
    """LLM erişilemiyorsa kural tabanlı Türkçe gerekçe üretir."""
    action     = ctx.get("action", "HOLD")
    confidence = ctx.get("confidence_pct", 50)
    regime     = ctx.get("regime", "NORMALIZATION")
    event_risk = ctx.get("event_risk_pct", 30)
    scores: dict = ctx.get("module_scores", {})

    t = scores.get("touche", 0.5)
    f = scores.get("fundamental", 0.5)
    n = scores.get("news", 0.5)
    s = scores.get("sentinel", 0.5)

    action_tr = {"BUY": "Alım", "SELL": "Satım", "HOLD": "Bekle"}.get(action, action)

    if action == "BUY":
        tech   = "güçlü teknik momentum" if t > 0.6 else "nötr teknik görünüm"
        fund   = "olumlu on-chain metrikler" if f > 0.55 else "karışık temel veriler"
        risk   = "düşük makro risk ortamı" if event_risk < 40 else "yüksek olay riski baskısına rağmen"
        return f"%{confidence} güvenle {action_tr} sinyali: {tech}, {fund} ve {risk} eş zamanlı gerçekleşiyor. Rejim: {regime}."

    if action == "SELL":
        tech   = "zayıflayan teknik yapı" if t < 0.4 else "bozulan momentum"
        news   = "olumsuz haber akışı" if n < 0.4 else "nötr haber ortamı"
        risk   = f"Olay riski %{event_risk:.0f} seviyesinde"
        return f"%{confidence} güvenle {action_tr} sinyali: {tech}, {news}. {risk}, makro ortam baskı altında."

    # HOLD
    sent = "riskli ortam beklemeyi" if s < 0.45 else "dengeli makro koşullar beklemeyi"
    return f"Modüller net bir yön gösteremiyor (%{confidence} güven). {sent} öneriyor. Rejim: {regime}."


# ── Ana servis ────────────────────────────────────────────────────────────────

class LLMService:
    """Groq → Ollama → Kural tabanlı öncelik sırasıyla çalışır."""

    def __init__(self) -> None:
        has_groq   = bool(_GROQ_API_KEY)
        has_ollama = bool(_OLLAMA_BASE)
        logger.info(
            "LLMService init: groq=%s ollama=%s model_groq=%s model_ollama=%s",
            "configured" if has_groq else "NO_KEY",
            _OLLAMA_BASE if has_ollama else "disabled",
            _GROQ_MODEL,
            _OLLAMA_MODEL,
        )

    async def signal_rationale(self, ctx: dict[str, Any]) -> dict[str, str]:
        """
        Sinyal için Türkçe gerekçe üretir.

        Returns:
            {"text": "...", "source": "groq" | "ollama" | "rule_based"}
        """
        prompt = _build_prompt(ctx)

        # 1. Groq
        text = await _call_groq(prompt)
        if text:
            return {"text": text, "source": "groq"}

        # 2. Ollama
        text = await _call_ollama(prompt)
        if text:
            return {"text": text, "source": "ollama"}

        # 3. Kural tabanlı
        text = _rule_based_rationale(ctx)
        return {"text": text, "source": "rule_based"}

    @property
    def available_sources(self) -> list[str]:
        sources = []
        if _GROQ_API_KEY:
            sources.append(f"groq({_GROQ_MODEL})")
        sources.append(f"ollama({_OLLAMA_MODEL}@{_OLLAMA_BASE})")
        sources.append("rule_based")
        return sources


# Singleton
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
