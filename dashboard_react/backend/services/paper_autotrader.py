"""
AEGIS Otonom Paper Trader — agent'ın UYGULADIĞI config'i gerçek zamanlı,
parasız test eder. Backtest'in TAM sinyal mantığını canlı veride kullanır.

Akış (her cycle):
  1. applied_strategy_config.json'u oku (agent'ın seçtiği 1d momentum vb.)
  2. Şimdiye kadarki OHLCV + consensus sinyallerini üret (backtest fonksiyonları)
  3. Son barın sinyali = ŞU ANKİ sinyal
  4. Pozisyon yönetimi: giriş/çıkış (sl/tp/z_exit/ters sinyal) — config paramlarıyla
  5. Sanal P&L + equity güncelle, kalıcı kaydet

GÜVENLİ: gerçek emir YOK, yalnız sanal. Gerçek forward-test = backtest'in
canlıda doğrulanması.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.getenv("AGENT_DATA_DIR", "/app/data")
_APPLIED_CONFIG_PATH = os.path.join(_DATA_DIR, "applied_strategy_config.json")
_PAPER_STATE_PATH = os.path.join(_DATA_DIR, "paper_autotrader_state.json")

# TF → cycle aralığı (sn). 1d için saatlik kontrol yeterli (bar günlük kapanır).
_TF_INTERVAL = {
    "5m": 60, "15m": 120, "1h": 300, "4h": 900, "1d": 3600, "1w": 7200,
}
# TF → lookback bar (z-score penceresi + warmup için yeterli)
_TF_LOOKBACK_DAYS = {
    "5m": 5, "15m": 10, "1h": 30, "4h": 90, "1d": 400, "1w": 900,
}


@dataclass
class PaperState:
    running: bool = False
    symbol: str = "BTC/USDT"
    timeframe: str = "1d"
    initial_capital: float = 100000.0
    balance: float = 100000.0            # nakit + pozisyon kapanınca güncellenir
    equity: float = 100000.0             # nakit + açık pozisyon değeri
    position: Optional[str] = None       # LONG | SHORT | None
    entry_price: Optional[float] = None
    entry_time: Optional[str] = None
    entry_z: Optional[float] = None
    position_size_pct: float = 0.0       # sermayenin %'si
    last_price: Optional[float] = None
    last_signal: Optional[int] = None
    last_z: Optional[float] = None
    cycle_count: int = 0
    last_cycle_ts: Optional[str] = None
    started_at: Optional[str] = None
    config_summary: str = ""
    trades: list = field(default_factory=list)        # kapanan işlemler
    equity_curve: list = field(default_factory=list)  # {ts, equity}
    open_pnl_pct: float = 0.0
    last_error: Optional[str] = None
    message: str = ""


class PaperAutoTrader:
    def __init__(self):
        self.state = PaperState()
        self._task: Optional[asyncio.Task] = None
        self._stop = False
        self._load()

    # ── Applied config ─────────────────────────────────────────────────────────
    @staticmethod
    def _applied() -> Optional[dict]:
        try:
            if os.path.exists(_APPLIED_CONFIG_PATH):
                with open(_APPLIED_CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    # ── Yaşam döngüsü ──────────────────────────────────────────────────────────
    async def start(self, reset: bool = False) -> dict:
        if self.state.running:
            return {"status": "already_running", **self.status()}
        cfg = self._applied()
        if not cfg:
            return {"status": "error", "error": "Uygulanan agent config yok — önce optimizer çalıştır"}

        if reset or self.state.cycle_count == 0:
            p = cfg["params"]
            self.state = PaperState(
                running=True,
                symbol=cfg.get("symbol", "BTC/USDT"),
                timeframe=cfg.get("timeframe", "1d"),
                started_at=_now(),
                config_summary=(f"Agent sinyali (canlı consensus) · "
                                f"sl={p.get('stop_loss_pct')} tp={p.get('take_profit_pct')} "
                                f"kelly={p.get('kelly_cap')}"),
                equity_curve=[{"ts": _now(), "equity": 100000.0}],
            )
        else:
            self.state.running = True

        self._stop = False
        self._task = asyncio.get_event_loop().create_task(self._loop())
        logger.info("PAPER_AUTO_START %s %s", self.state.symbol, self.state.timeframe)
        return {"status": "started", **self.status()}

    async def stop(self) -> dict:
        self._stop = True
        self.state.running = False
        self._save()
        return {"status": "stopped", **self.status()}

    async def _loop(self):
        # Açılışta hemen bir değerlendirme
        while not self._stop:
            try:
                await self._cycle()
            except Exception as exc:
                self.state.last_error = str(exc)[:300]
                logger.warning("paper cycle error: %s", exc)
            # Agent'la aynı tempoda kontrol et (sinyali kaçırma)
            try:
                from services.agent_loop import get_agent
                interval = max(120, int(get_agent().config.interval_sec))
            except Exception:
                interval = 300
            slept = 0
            while not self._stop and slept < interval:
                await asyncio.sleep(5); slept += 5

    async def _get_price(self, symbol: str) -> Optional[float]:
        """Binance public ticker'dan anlık fiyat."""
        try:
            import httpx
            bsym = symbol.replace("/", "")
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": bsym})
            if r.status_code == 200:
                return float(r.json().get("price", 0)) or None
        except Exception:
            pass
        return None

    # ── Tek cycle: AGENT'in sinyaline göre (canlı consensus action) ────────────
    async def _cycle(self):
        cfg = self._applied()
        if not cfg:
            self.state.message = "Uygulanan config kayboldu"
            return
        p = cfg["params"]
        sym = cfg.get("symbol", "BTC/USDT")
        sl = float(p.get("stop_loss_pct", -0.08))
        tp = float(p.get("take_profit_pct", 0.15))

        # Trading Agent'ın config'i — paper AYNI TF + AYNI kapılarla sinyal alsın
        try:
            from services.agent_loop import get_agent
            acfg = get_agent().config
            tf = acfg.timeframe
            horizon = acfg.horizon
            min_conf = float(acfg.min_confidence)
            min_edge = float(acfg.min_score_edge)
        except Exception:
            tf, horizon, min_conf, min_edge = cfg.get("timeframe", "1d"), "medium", 0.60, 0.05

        # ── CANLI CONSENSUS (agent ile AYNI kaynak) ───────────────────────────
        from routes import dashboard
        consensus = await dashboard.get_consensus(
            symbol=sym, timeframe=tf, horizon=horizon,
            prometheus_url=os.getenv("PROMETHEUS_URL", "http://prometheus:9090"),
        )
        action = str(consensus.get("action", "HOLD")).upper()
        score = float(consensus.get("weighted_score", 0.5))
        confidence = float(consensus.get("confidence", 0.5))
        edge = abs(score - 0.5)

        # Sinyal: AGENT ile birebir — consensus action BUY/SELL ise aç.
        # (action zaten eşik içeriyor; ekstra güven kapısı hafif tutuldu)
        signal = 0
        if action == "BUY" and confidence >= min_conf:
            signal = 1
        elif action == "SELL" and confidence >= min_conf:
            signal = -1

        price = await self._get_price(sym)
        if not price:
            self.state.message = "Fiyat alınamadı"
            return

        self.state.cycle_count += 1
        self.state.last_cycle_ts = _now()
        self.state.last_price = round(price, 2)
        self.state.last_signal = signal
        self.state.last_z = round(score, 3)   # artık consensus skoru (z değil)
        self.state.symbol = sym
        self.state.timeframe = tf

        st = self.state

        # ── Açık pozisyon yönetimi ─────────────────────────────────────────────
        if st.position is not None:
            pnl_pct = (price - st.entry_price) / st.entry_price * (1 if st.position == "LONG" else -1)
            st.open_pnl_pct = round(pnl_pct * 100, 2)
            exit_reason = None
            if pnl_pct <= sl:
                exit_reason = "stop_loss"
            elif pnl_pct >= tp:
                exit_reason = "take_profit"
            elif signal != 0 and ((st.position == "LONG" and signal < 0) or (st.position == "SHORT" and signal > 0)):
                exit_reason = "reverse_signal"
            # Consensus nötre döndü ve pozisyon kârda → kârı koru
            elif action == "HOLD" and pnl_pct > 0.01:
                exit_reason = "signal_neutral"

            if exit_reason:
                self._close_position(price, pnl_pct, exit_reason)

        # ── Yeni giriş (agent sinyali) ──────────────────────────────────────────
        if st.position is None and signal != 0:
            self._open_position("LONG" if signal > 0 else "SHORT", price, score, confidence)

        # ── Equity güncelle ────────────────────────────────────────────────────
        if st.position is not None:
            pnl_pct = (price - st.entry_price) / st.entry_price * (1 if st.position == "LONG" else -1)
            st.equity = round(st.balance * (1 + pnl_pct * st.position_size_pct), 2)
            st.open_pnl_pct = round(pnl_pct * 100, 2)
        else:
            st.equity = st.balance
            st.open_pnl_pct = 0.0

        st.equity_curve.append({"ts": _now(), "equity": st.equity})
        st.equity_curve = st.equity_curve[-500:]
        st.message = self._status_msg()
        self._save()

    def _open_position(self, side, price, score, confidence):
        st = self.state
        # Pozisyon boyutu: güven × kelly_cap (yüksek güven = büyük pozisyon)
        cfg = self._applied(); kelly = float(cfg["params"].get("kelly_cap", 0.25)) if cfg else 0.25
        edge = abs(score - 0.5) * 2          # 0-1
        size = max(0.02, min(kelly, kelly * (0.4 + 0.6 * confidence) * (0.5 + edge)))
        st.position = side
        st.entry_price = round(price, 2)
        st.entry_time = _now()
        st.entry_z = round(score, 3)
        st.position_size_pct = round(size, 4)
        logger.info("PAPER_OPEN %s %s @ %.2f size=%.1f%% (conf=%.2f)", side, st.symbol, price, size * 100, confidence)
        try:
            from services.notifier import notify
            notify("signal", f"Paper {side} açıldı · {st.symbol} @ ${round(price,2)} · "
                   f"boyut %{round(size*100)} · güven {round(confidence,2)}", level="signal")
        except Exception:
            pass

    def _close_position(self, price, pnl_pct, reason):
        st = self.state
        realized = st.balance * pnl_pct * st.position_size_pct
        st.balance = round(st.balance + realized, 2)
        st.trades.append({
            "side": st.position, "entry_price": st.entry_price, "exit_price": round(price, 2),
            "entry_time": st.entry_time, "exit_time": _now(),
            "pnl_pct": round(pnl_pct * 100, 2), "pnl_usd": round(realized, 2),
            "size_pct": st.position_size_pct, "reason": reason,
        })
        st.trades = st.trades[-100:]
        logger.info("PAPER_CLOSE %s @ %.2f pnl=%.2f%% (%s)", st.position, price, pnl_pct * 100, reason)
        try:
            from services.notifier import notify
            lvl = "success" if realized > 0 else "warning"
            notify("signal", f"Paper {st.position} kapandı @ ${round(price,2)} · "
                   f"{round(pnl_pct*100,2):+.2f}% (${round(realized,2)}) · {reason}", level=lvl)
        except Exception:
            pass
        st.position = st.entry_price = st.entry_time = st.entry_z = None
        st.position_size_pct = 0.0
        st.open_pnl_pct = 0.0

    def _status_msg(self) -> str:
        st = self.state
        if st.position:
            return (f"{st.position} açık @ ${st.entry_price} · anlık {st.open_pnl_pct:+.2f}% · "
                    f"fiyat ${st.last_price}")
        wins = sum(1 for t in st.trades if t["pnl_usd"] > 0)
        return (f"Pozisyon yok · {len(st.trades)} işlem ({wins} kâr) · "
                f"sinyal={'pozitif' if st.last_signal==1 else 'negatif' if st.last_signal==-1 else 'notr'} · z={st.last_z}")

    # ── Durum + kalıcılık ──────────────────────────────────────────────────────
    def status(self) -> dict:
        s = asdict(self.state)
        total_pnl = s["balance"] - s["initial_capital"]
        s["total_pnl_usd"] = round(total_pnl, 2)
        s["total_pnl_pct"] = round(total_pnl / s["initial_capital"] * 100, 3)
        wins = sum(1 for t in s["trades"] if t["pnl_usd"] > 0)
        s["trade_count"] = len(s["trades"])
        s["win_count"] = wins
        s["win_rate"] = round(wins / len(s["trades"]) * 100, 1) if s["trades"] else 0.0
        s["recent_trades"] = s["trades"][-10:][::-1]
        s["equity_curve_compact"] = s["equity_curve"][-120:]
        # Büyük listeleri yanıttan çıkar
        s.pop("trades", None); s.pop("equity_curve", None)
        return s

    def _save(self):
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_PAPER_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(asdict(self.state), f)
        except Exception as exc:
            logger.debug("paper save failed: %s", exc)

    def _load(self):
        try:
            if os.path.exists(_PAPER_STATE_PATH):
                with open(_PAPER_STATE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["running"] = False  # restart sonrası durmuş kabul
                self.state = PaperState(**{k: v for k, v in data.items() if k in PaperState.__dataclass_fields__})
        except Exception as exc:
            logger.debug("paper load failed: %s", exc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_trader: Optional[PaperAutoTrader] = None

def get_paper_trader() -> PaperAutoTrader:
    global _trader
    if _trader is None:
        _trader = PaperAutoTrader()
    return _trader
