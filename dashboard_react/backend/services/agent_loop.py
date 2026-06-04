"""
AEGIS Agent Orchestrator — otonom karar döngüsü (GÜVENLİ-VARSAYILAN).

Tasarım ilkeleri:
  • GÜVENLİ-VARSAYILAN: AGENT_ENABLED=false → agent kapalı başlar.
  • GERÇEK PARA KORUMASI: agent ASLA otomatik gerçek emir göndermez.
    - DRY_RUN        → sadece karar günlüğüne yazar (emir yok)
    - MANUAL_APPROVAL → sinyali onay kuyruğuna koyar (insan onaylar)
    - AUTO_LIMITED   → "would execute" loglar; gerçek emir ayrı, elle açılan
                       execution endpoint'ini gerektirir (bu modülde YOK)
  • KILL SWITCH: her döngüde kontrol; aktifse hiçbir sinyal üretilmez.
  • ÇÖZÜK (decoupled): consensus/kuyruk/kill-switch fonksiyonları dışarıdan
    enjekte edilir → main.py'yi import etmez (dairesel bağımlılık yok).

Bu modül mevcut sistemi DEĞİŞTİRMEZ; yalnızca üstüne bir orkestrasyon katmanı ekler.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# ── Kalıcı günlük yolu ──────────────────────────────────────────────────────────
_DATA_DIR = os.getenv("AGENT_DATA_DIR", "/app/data")
_JOURNAL_PATH = os.path.join(_DATA_DIR, "agent_journal.jsonl")
_MAX_MEMORY_ENTRIES = 250


# ── Bağımlılık tipleri (main.py enjekte eder) ──────────────────────────────────
ConsensusFn   = Callable[[str, str, str], Awaitable[dict]]      # (symbol, tf, horizon) → consensus dict
EnqueueFn     = Callable[[dict], Optional[str]]                 # signal dict → signal_id | None
KillSwitchFn  = Callable[[], tuple[bool, str]]                  # () → (active, reason)
PriceCheckFn  = Optional[Callable[[str], Awaitable[dict]]]      # (symbol) → validation dict


@dataclass
class AgentConfig:
    enabled: bool          = field(default_factory=lambda: os.getenv("AGENT_ENABLED", "false").lower() == "true")
    interval_sec: int      = field(default_factory=lambda: int(os.getenv("AGENT_INTERVAL_SEC", "300")))
    watch_symbols: list[str] = field(default_factory=lambda: os.getenv("AGENT_SYMBOLS", "BTC/USDT").split(","))
    timeframe: str         = field(default_factory=lambda: os.getenv("AGENT_TIMEFRAME", "4h"))
    horizon: str           = field(default_factory=lambda: os.getenv("AGENT_HORIZON", "medium"))
    min_confidence: float  = field(default_factory=lambda: float(os.getenv("AGENT_MIN_CONFIDENCE", "0.62")))
    min_score_edge: float  = field(default_factory=lambda: float(os.getenv("AGENT_MIN_SCORE_EDGE", "0.08")))  # |score-0.5|
    max_signals_per_day: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_SIGNALS_DAY", "6")))
    execution_mode: str    = field(default_factory=lambda: os.getenv("EXECUTION_MODE", "DRY_RUN").upper())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["watch_symbols"] = [s.strip() for s in self.watch_symbols if s.strip()]
        return d


@dataclass
class AgentDecision:
    ts: str
    symbol: str
    timeframe: str
    action: str            # BUY | SELL | HOLD
    score: float
    confidence: float
    decision: str          # no_action | would_signal | queued_for_approval | blocked_kill_switch | auto_execute_logged | rejected_*
    reason: str
    mode: str
    signal_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class AgentOrchestrator:
    """Otonom analiz → karar → (güvenli) yönlendirme döngüsü."""

    def __init__(self):
        self.config = AgentConfig()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._stop_evt = asyncio.Event()

        # Durum
        self.cycle_count = 0
        self.last_cycle_ts: Optional[str] = None
        self.last_error: Optional[str] = None
        self.started_at: Optional[str] = None
        self._signals_today = 0
        self._today_date = datetime.now(timezone.utc).date().isoformat()

        # Günlük (bellek halkası)
        self.journal: list[AgentDecision] = []

        # Enjekte edilen bağımlılıklar
        self._consensus_fn: Optional[ConsensusFn] = None
        self._enqueue_fn: Optional[EnqueueFn] = None
        self._kill_switch_fn: Optional[KillSwitchFn] = None
        self._price_check_fn: PriceCheckFn = None

        self._load_journal()

    # ── Bağımlılık enjeksiyonu ─────────────────────────────────────────────────
    def wire(
        self,
        *,
        consensus_fn: ConsensusFn,
        enqueue_fn: EnqueueFn,
        kill_switch_fn: KillSwitchFn,
        price_check_fn: PriceCheckFn = None,
    ) -> None:
        self._consensus_fn = consensus_fn
        self._enqueue_fn = enqueue_fn
        self._kill_switch_fn = kill_switch_fn
        self._price_check_fn = price_check_fn
        logger.info("Agent dependencies wired (consensus, enqueue, kill_switch, price_check)")

    # ── Yaşam döngüsü ──────────────────────────────────────────────────────────
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> dict:
        if self._running:
            return {"status": "already_running", **self.status()}
        if self._consensus_fn is None:
            return {"status": "error", "error": "Agent not wired — consensus_fn missing"}
        self._stop_evt.clear()
        self._running = True
        self.started_at = _now_iso()
        self.last_error = None
        self._task = asyncio.get_event_loop().create_task(self._run_loop())
        logger.info("AGENT_STARTED interval=%ds symbols=%s mode=%s",
                    self.config.interval_sec, self.config.watch_symbols, self.config.execution_mode)
        return {"status": "started", **self.status()}

    async def stop(self) -> dict:
        if not self._running:
            return {"status": "already_stopped", **self.status()}
        self._stop_evt.set()
        self._running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        logger.info("AGENT_STOPPED after %d cycles", self.cycle_count)
        return {"status": "stopped", **self.status()}

    async def _run_loop(self) -> None:
        # NOT: config'i burada SIFIRLAMA — çalışma zamanı /config değişiklikleri
        # (timeframe, interval vb.) korunmalı. Env yalnız __init__'te okunur.
        while not self._stop_evt.is_set():
            try:
                await self._decision_cycle()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)[:300]
                logger.error("Agent cycle error: %s", exc, exc_info=True)
            # Kesintiye uğrayabilen uyku
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=self.config.interval_sec)
            except asyncio.TimeoutError:
                pass

    # ── Karar döngüsü ──────────────────────────────────────────────────────────
    async def _decision_cycle(self) -> None:
        self.cycle_count += 1
        self.last_cycle_ts = _now_iso()
        self._roll_day()

        # 1) Kill switch — aktifse hiçbir sinyal üretme
        ks_active, ks_reason = (False, "")
        if self._kill_switch_fn:
            try:
                ks_active, ks_reason = self._kill_switch_fn()
            except Exception:
                ks_active = False

        for symbol in [s.strip() for s in self.config.watch_symbols if s.strip()]:
            if ks_active:
                self._journal_add(AgentDecision(
                    ts=_now_iso(), symbol=symbol, timeframe=self.config.timeframe,
                    action="HOLD", score=0.5, confidence=0.0,
                    decision="blocked_kill_switch",
                    reason=f"Kill switch aktif: {ks_reason}",
                    mode=self.config.execution_mode,
                ))
                continue

            try:
                await self._evaluate_symbol(symbol)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Agent evaluate %s failed: %s", symbol, exc)

    async def _evaluate_symbol(self, symbol: str) -> None:
        consensus = await self._consensus_fn(symbol, self.config.timeframe, self.config.horizon)
        action     = str(consensus.get("action", "HOLD")).upper()
        score      = float(consensus.get("weighted_score", 0.5))
        confidence = float(consensus.get("confidence", 0.5))
        mode       = self.config.execution_mode

        # HOLD veya zayıf kenar → işlem yok
        edge = abs(score - 0.5)
        if action == "HOLD" or action not in ("BUY", "SELL"):
            self._journal_add(AgentDecision(
                ts=_now_iso(), symbol=symbol, timeframe=self.config.timeframe,
                action=action, score=round(score, 4), confidence=round(confidence, 4),
                decision="no_action", reason="Konsensüs HOLD / yön yok", mode=mode,
            ))
            return

        if confidence < self.config.min_confidence or edge < self.config.min_score_edge:
            self._journal_add(AgentDecision(
                ts=_now_iso(), symbol=symbol, timeframe=self.config.timeframe,
                action=action, score=round(score, 4), confidence=round(confidence, 4),
                decision="rejected_low_conviction",
                reason=f"Güven {confidence:.2f}<{self.config.min_confidence} veya kenar {edge:.3f}<{self.config.min_score_edge}",
                mode=mode,
            ))
            return

        # Günlük sinyal limiti
        if self._signals_today >= self.config.max_signals_per_day:
            self._journal_add(AgentDecision(
                ts=_now_iso(), symbol=symbol, timeframe=self.config.timeframe,
                action=action, score=round(score, 4), confidence=round(confidence, 4),
                decision="rejected_daily_limit",
                reason=f"Günlük sinyal limiti doldu ({self.config.max_signals_per_day})",
                mode=mode,
            ))
            return

        # Cross-source fiyat doğrulaması (varsa)
        if self._price_check_fn:
            try:
                vld = await self._price_check_fn(symbol)
                if vld.get("unverified"):
                    self._journal_add(AgentDecision(
                        ts=_now_iso(), symbol=symbol, timeframe=self.config.timeframe,
                        action=action, score=round(score, 4), confidence=round(confidence, 4),
                        decision="rejected_price_unverified",
                        reason=f"Fiyat doğrulanamadı (sapma %{vld.get('deviation_pct', 0)})",
                        mode=mode,
                    ))
                    return
            except Exception:
                pass  # fiyat doğrulama başarısızsa sinyali bloklama, sadece atla

        reason = (f"Konsensüs {action} · skor {score:.2f} · güven {confidence:.2f} · "
                  f"kenar {edge:.3f} (≥{self.config.min_score_edge})")

        # ── GÜVENLİ yönlendirme — moda göre ────────────────────────────────────
        if mode == "DRY_RUN":
            self._journal_add(AgentDecision(
                ts=_now_iso(), symbol=symbol, timeframe=self.config.timeframe,
                action=action, score=round(score, 4), confidence=round(confidence, 4),
                decision="would_signal",
                reason=f"DRY_RUN — emir AÇILMAZ. {reason}", mode=mode,
            ))
            self._signals_today += 1

        elif mode == "MANUAL_APPROVAL":
            sig_id = None
            if self._enqueue_fn:
                sig_payload = {
                    "symbol": symbol, "action": action, "timeframe": self.config.timeframe,
                    "confidence": confidence, "score": score,
                    "reason": reason, "source": "agent_auto",
                }
                try:
                    sig_id = self._enqueue_fn(sig_payload)
                except Exception as exc:
                    logger.warning("enqueue failed: %s", exc)
            self._journal_add(AgentDecision(
                ts=_now_iso(), symbol=symbol, timeframe=self.config.timeframe,
                action=action, score=round(score, 4), confidence=round(confidence, 4),
                decision="queued_for_approval",
                reason=f"İnsan onayı bekliyor. {reason}", mode=mode, signal_id=sig_id,
            ))
            self._signals_today += 1

        else:  # AUTO_LIMITED — gerçek emir GÖNDERİLMEZ (güvenlik)
            self._journal_add(AgentDecision(
                ts=_now_iso(), symbol=symbol, timeframe=self.config.timeframe,
                action=action, score=round(score, 4), confidence=round(confidence, 4),
                decision="auto_execute_logged",
                reason=(f"AUTO_LIMITED — gerçek emir bu katmanda AÇILMAZ; "
                        f"elle açılan execution endpoint gerekir. {reason}"),
                mode=mode,
            ))
            self._signals_today += 1

    # ── Günlük yönetimi ────────────────────────────────────────────────────────
    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self._today_date:
            self._today_date = today
            self._signals_today = 0

    def _journal_add(self, d: AgentDecision) -> None:
        self.journal.append(d)
        if len(self.journal) > _MAX_MEMORY_ENTRIES:
            self.journal = self.journal[-_MAX_MEMORY_ENTRIES:]
        # Kalıcı (append-only JSONL)
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_JOURNAL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.debug("journal persist failed: %s", exc)
        # Önemli kararları logla + uyarı yayınla
        if d.decision not in ("no_action",):
            logger.info("AGENT_DECISION %s %s → %s | %s",
                        d.symbol, d.action, d.decision, d.reason[:80])
            try:
                from services.notifier import notify
                if d.decision in ("would_signal", "queued_for_approval", "auto_execute_logged"):
                    notify("signal", f"{d.symbol} {d.action} ({d.timeframe}) · skor {d.score:.2f} · {d.decision}",
                           level="signal", meta={"symbol": d.symbol, "action": d.action})
                elif d.decision == "blocked_kill_switch":
                    notify("kill_switch", f"Kill switch aktif — {d.symbol} sinyali bloklandı", level="critical")
            except Exception:
                pass

    def _load_journal(self) -> None:
        try:
            if os.path.exists(_JOURNAL_PATH):
                with open(_JOURNAL_PATH, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-_MAX_MEMORY_ENTRIES:]
                for ln in lines:
                    try:
                        self.journal.append(AgentDecision(**json.loads(ln)))
                    except Exception:
                        continue
                logger.info("Agent journal loaded: %d entries", len(self.journal))
        except Exception as exc:
            logger.debug("journal load failed: %s", exc)

    # ── Durum & sorgular ───────────────────────────────────────────────────────
    def status(self) -> dict:
        return {
            "running": self._running,
            "config": self.config.to_dict(),
            "cycle_count": self.cycle_count,
            "last_cycle_ts": self.last_cycle_ts,
            "started_at": self.started_at,
            "last_error": self.last_error,
            "signals_today": self._signals_today,
            "journal_size": len(self.journal),
            "heartbeat_age_sec": _age_sec(self.last_cycle_ts),
        }

    def recent_journal(self, limit: int = 50) -> list[dict]:
        return [d.to_dict() for d in self.journal[-limit:]][::-1]

    async def run_once(self) -> dict:
        """Tek döngü çalıştır (test/manuel tetikleme) — agent kapalıyken bile."""
        if self._consensus_fn is None:
            return {"status": "error", "error": "Agent not wired"}
        before = len(self.journal)
        await self._decision_cycle()
        new = self.recent_journal(limit=len(self.journal) - before) if len(self.journal) > before else []
        return {"status": "ok", "cycle": self.cycle_count, "new_decisions": new}


# ── Yardımcılar ─────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _age_sec(ts: Optional[str]) -> Optional[float]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return round((datetime.now(timezone.utc) - dt).total_seconds(), 1)
    except Exception:
        return None


# Singleton
_agent: Optional[AgentOrchestrator] = None

def get_agent() -> AgentOrchestrator:
    global _agent
    if _agent is None:
        _agent = AgentOrchestrator()
    return _agent
