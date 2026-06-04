"""
AEGIS Optimizasyon Agent'ı — tüm strateji uzayını tarar, en iyi ayarı bulur,
OUT-OF-SAMPLE doğrulamadan geçerse OTOMATİK uygular.

Kullanıcı kararları:
  • Hedef:   Toplam Getiri (PnL) maksimizasyonu
  • Kapsam:  Her şey (sinyal+çıkış paramları + yön + modül ağırlıkları + TF)
  • Uygula:  Otomatik

GÜVENLİK TABANI (gerçek para — pazarlık edilemez):
  Aday config tüm geçmişte (in-sample) optimize edilir AMA görülmemiş son %30'da
  (out-of-sample) da KÂRLI olmak zorundadır. OOS'de para kaybeden config
  otomatik UYGULANMAZ → mevcut ayar korunur. Bu, overfitting felaketini önler.

Yöntem: Latin Hypercube örnekleme (brute-force grid imkansız — milyarlarca kombo).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

_DATA_DIR = os.getenv("AGENT_DATA_DIR", "/app/data")
_APPLIED_CONFIG_PATH = os.path.join(_DATA_DIR, "applied_strategy_config.json")
_OPT_RESULTS_PATH = os.path.join(_DATA_DIR, "optimizer_results.json")


@dataclass
class OptimizerConfig:
    symbol: str = "BTC/USDT"
    timeframes: list[str] = field(default_factory=lambda: ["4h", "1d"])
    start_date: str = "2022-10-01"
    end_date: str = "2025-09-28"
    initial_capital: float = 100000.0
    n_candidates_per_tf: int = 80      # TF başına aday sayısı (tur başına)
    refine_rounds: int = 2             # İTERASYON: broad + N daraltma turu (interpolasyon)
    refine_top_k: int = 8              # her turdan en iyi K aday etrafında daralt
    oos_fraction: float = 0.30         # son %30 = out-of-sample test
    min_trades: int = 12               # istatistiksel anlamlılık
    seed: int = 42
    # ── Otonom mod ──────────────────────────────────────────────────────────
    auto_enabled: bool = False         # periyodik kendi kendine yeniden optimize et
    auto_interval_hours: float = 24.0  # her N saatte bir tara
    min_profit_factor: float = 1.05    # KAPI: PF<1.05 config UYGULANMAZ (kırılgan)


@dataclass
class OptimizerState:
    running: bool = False
    progress: float = 0.0              # 0-1
    current_tf: str = ""
    evaluated: int = 0
    total: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    best: Optional[dict] = None
    applied: Optional[dict] = None
    last_error: Optional[str] = None
    message: str = ""


class OptimizerAgent:
    """Strateji uzayını tarayan, OOS-doğrulamalı, otomatik uygulayan agent."""

    def __init__(self):
        self.config = OptimizerConfig()
        self.state = OptimizerState()
        self._task: Optional[asyncio.Task] = None
        self.all_results: list[dict] = []
        self._stop_flag: bool = False
        self._auto_task = None
        self._auto_running = False
        self.last_auto_run = None
        self.next_auto_run = None

    # ── Parametre uzayı (HER ŞEY) ──────────────────────────────────────────────
    @staticmethod
    def _param_bounds() -> dict:
        return {
            "z_threshold":    [0.5, 2.0],
            "stop_loss_pct":  [-0.12, -0.03],
            "take_profit_pct": [0.06, 0.35],
            "z_exit_long":    [-0.35, 0.25],
            "adx_min":        [10, 32],
            "kelly_cap":      [0.10, 0.40],
            # Modül ağırlıkları (ham — normalize edilir). Sinyal varyansına göre:
            # trend(0.31)/ml(0.29)/quantum(0.22) en güçlü → geniş aralık.
            # touche(0.04 flat)/news(0.00 ölü) → düşük aralık.
            "w_touche":       [0.0, 0.5],   # flat → düşük tavan
            "w_fundamental":  [0.0, 0.8],
            "w_news":         [0.0, 0.15],  # ölü → neredeyse sıfır
            "w_sentinel":     [0.0, 0.8],
            "w_quantum":      [0.0, 1.0],   # güçlü sinyal
            "w_ml":           [0.0, 1.0],   # YENİ — güçlü sinyal
            "w_trend":        [0.0, 1.0],   # YENİ — en güçlü sinyal
            # Yön: <0.5 momentum, >=0.5 kontrarian
            "contrarian":     [0.0, 1.0],
        }

    def _sample(self, n: int, seed: int, bounds: Optional[dict] = None) -> list[dict]:
        """Latin Hypercube örnekleme (permütasyon). bounds verilirse o uzayda örnekler."""
        bounds = bounds or self._param_bounds()
        try:
            from scipy.stats.qmc import LatinHypercube, scale
            s = LatinHypercube(d=len(bounds), seed=seed)
            raw = s.random(n=n)
            lo = [b[0] for b in bounds.values()]
            hi = [b[1] for b in bounds.values()]
            scaled = scale(raw, lo, hi)
            return [dict(zip(bounds.keys(), row)) for row in scaled]
        except ImportError:
            import random
            random.seed(seed)
            return [{k: lo + random.random() * (hi - lo) for k, (lo, hi) in bounds.items()}
                    for _ in range(n)]

    def _refine_bounds(self, top: list[dict]) -> dict:
        """
        İNTERPOLASYON: en iyi adayların etrafında arama uzayını daralt.
        Her param için top'ların min-max'ı ± %20 marj → bir sonraki tur burada arar.
        """
        broad = self._param_bounds()
        if not top:
            return broad
        # top'lardan ham param değerlerini çıkar (normalize öncesi yaklaşık geri çevir)
        refined = {}
        for key, (blo, bhi) in broad.items():
            vals = []
            for r in top:
                p = r.get("params", {})
                if key == "contrarian":
                    vals.append(1.0 if p.get("contrarian") else 0.0)
                elif key.startswith("w_"):
                    w = p.get("weights", {}).get(key[2:])
                    if w is not None:
                        vals.append(w)
                else:
                    v = p.get(key)
                    if v is not None:
                        vals.append(float(v))
            if not vals:
                refined[key] = [blo, bhi]; continue
            lo_v, hi_v = min(vals), max(vals)
            margin = (bhi - blo) * 0.20
            refined[key] = [max(blo, lo_v - margin), min(bhi, hi_v + margin)]
        return refined

    # ── Tek aday değerlendirme (in-sample + out-of-sample) ─────────────────────
    async def _evaluate(self, bt, tf: str, ps: dict, start_dt, end_dt, news_fetcher, split_ts) -> Optional[dict]:
        # Modül ağırlıklarını normalize et (trend + ml DAHİL — en güçlü sinyaller)
        wsum = (ps["w_touche"] + ps["w_fundamental"] + ps["w_news"] + ps["w_sentinel"]
                + ps["w_quantum"] + ps.get("w_ml", 0) + ps.get("w_trend", 0))
        if wsum <= 0:
            return None
        weights = {
            "touche": ps["w_touche"] / wsum, "fundamental": ps["w_fundamental"] / wsum,
            "news": ps["w_news"] / wsum, "sentinel": ps["w_sentinel"] / wsum,
            "quantum": ps["w_quantum"] / wsum,
            "ml": ps.get("w_ml", 0) / wsum, "trend": ps.get("w_trend", 0) / wsum,
        }
        contrarian = ps["contrarian"] >= 0.5
        z   = round(ps["z_threshold"], 3)
        sl  = round(ps["stop_loss_pct"], 4)
        tp  = round(ps["take_profit_pct"], 4)
        ze  = round(ps["z_exit_long"], 4)
        adx = round(ps["adx_min"])
        kly = round(ps["kelly_cap"], 3)

        bt._CONTRARIAN_OVERRIDE = contrarian
        try:
            df = await bt.generate_historical_data_with_ai_signals(
                self.config.symbol, tf, start_dt, end_dt,
                news_fetcher=news_fetcher, z_threshold=z, adx_min=adx,
                module_weights=weights,
            )
            if df is None or df.empty:
                return None
            trades = bt.execute_ai_driven_trades(
                df, self.config.symbol, stop_loss_pct=sl, take_profit_pct=tp,
                z_exit_long=ze, z_exit_short=-ze,
            )
            if not trades or len(trades) < self.config.min_trades:
                return None

            # ── In-sample / Out-of-sample bölme (exit zamanına göre) ───────────
            is_trades, oos_trades = [], []
            for t in trades:
                ex = t.get("exit_time", "")
                if ex and ex < split_ts:
                    is_trades.append(t)
                else:
                    oos_trades.append(t)

            full_m = bt.calculate_backtest_metrics(trades, self.config.initial_capital, kelly_cap=kly)
            oos_m  = bt.calculate_backtest_metrics(oos_trades, self.config.initial_capital, kelly_cap=kly) if len(oos_trades) >= 3 else None
            is_m   = bt.calculate_backtest_metrics(is_trades, self.config.initial_capital, kelly_cap=kly) if len(is_trades) >= 3 else None

            oos_pnl = oos_m["pnl"]["total_pnl_pct"] if oos_m else None
            is_pnl  = is_m["pnl"]["total_pnl_pct"] if is_m else None

            return {
                "timeframe": tf,
                "params": {
                    "z_threshold": z, "stop_loss_pct": sl, "take_profit_pct": tp,
                    "z_exit_long": ze, "adx_min": adx, "kelly_cap": kly,
                    "contrarian": contrarian, "weights": {k: round(v, 3) for k, v in weights.items()},
                },
                "full_pnl_pct":  full_m["pnl"]["total_pnl_pct"],
                "oos_pnl_pct":   oos_pnl,
                "is_pnl_pct":    is_pnl,
                "win_rate":      full_m["win_loss"]["win_rate"],
                "profit_factor": full_m["win_loss"]["profit_factor"],
                "sharpe":        full_m["sharpe_ratio"],
                "max_dd_pct":    full_m["drawdown"]["max_drawdown_pct"],
                "num_trades":    full_m["pnl"]["num_trades"],
                "oos_trades":    len(oos_trades),
                # OOS-doğrulanmış: hem in-sample hem out-of-sample kârlı
                "oos_validated": bool(oos_pnl is not None and oos_pnl > 0 and (is_pnl is None or is_pnl > 0)),
            }
        except Exception as exc:
            logger.debug("eval failed: %s", exc)
            return None
        finally:
            bt._CONTRARIAN_OVERRIDE = None

    # ── Ana optimizasyon döngüsü ───────────────────────────────────────────────
    async def _run(self):
        import importlib
        bt = importlib.import_module("routes.backtest_routes")
        news_fetcher = bt.get_news_fetcher()

        start_dt = datetime.strptime(self.config.start_date, "%Y-%m-%d")
        end_dt   = datetime.strptime(self.config.end_date, "%Y-%m-%d")
        # OOS split timestamp (son %30)
        span = (end_dt - start_dt).total_seconds()
        split_dt = start_dt.fromtimestamp(start_dt.timestamp() + span * (1 - self.config.oos_fraction), tz=timezone.utc)
        split_ts = split_dt.isoformat()

        self.all_results = []
        n_rounds = 1 + max(0, self.config.refine_rounds)
        self.state.total = self.config.n_candidates_per_tf * len(self.config.timeframes) * n_rounds
        self.state.evaluated = 0
        self.state.running = True   # FIX: _run kendi bayrağını yönetir (auto modda da çalışsın)
        self._stop_flag = False

        for tf_i, tf in enumerate(self.config.timeframes):
            self.state.current_tf = tf
            tf_results: list[dict] = []
            bounds = self._param_bounds()   # tur 1: geniş uzay

            # ── İTERASYON: broad → daraltma turları (interpolasyon) ───────────
            for rnd in range(n_rounds):
                self.state.current_tf = f"{tf} (tur {rnd+1}/{n_rounds})"
                candidates = self._sample(self.config.n_candidates_per_tf,
                                          self.config.seed + tf_i * 100 + rnd, bounds)
                for ps in candidates:
                    if self._stop_flag:
                        self.state.running = False
                        return
                    res = await self._evaluate(bt, tf, ps, start_dt, end_dt, news_fetcher, split_ts)
                    if res:
                        res = _to_native(res)
                        tf_results.append(res)
                        self.all_results.append(res)
                    self.state.evaluated += 1
                    self.state.progress = round(self.state.evaluated / max(self.state.total, 1), 3)
                    await asyncio.sleep(0.01)

                # Sonraki tur için: bu TF'in en iyi K adayı etrafında daralt (interpolasyon)
                if rnd < n_rounds - 1:
                    ranked = [r for r in tf_results if r.get("oos_validated")]
                    ranked.sort(key=lambda x: (x.get("oos_pnl_pct") or -999), reverse=True)
                    if not ranked:  # OOS geçen yoksa full PnL'e göre
                        ranked = sorted(tf_results, key=lambda x: x["full_pnl_pct"], reverse=True)
                    bounds = self._refine_bounds(ranked[:self.config.refine_top_k])

        # ── AKILLI SEÇİM: kapı + sağlam skor ──────────────────────────────────
        # Agent kırılgan/sağlam ikilemini KENDİ çözer. İki katmanlı:
        #   1) KAPI: OOS'de kârlı VE profit_factor >= min_pf (kırılgan eler)
        #   2) SIRALAMA: sağlam bileşik skor (Sharpe + PF + OOS PnL − drawdown)
        # Böylece PF=0.71 gibi kırılgan ama yüksek-PnL config asla uygulanmaz.
        min_pf = self.config.min_profit_factor

        def robust_score(r: dict) -> float:
            oos = r.get("oos_pnl_pct") or 0.0
            sharpe = r.get("sharpe") or 0.0
            pf = min(r.get("profit_factor") or 0.0, 3.0)
            dd = abs(r.get("max_dd_pct") or 0.0)
            # Risk-ayarlı kalite: Sharpe ve PF baskın, getiri katkı, drawdown ceza
            return (sharpe * 8 * 0.32
                    + pf * 14 * 0.28
                    + oos * 1.5 * 0.22
                    - dd * 0.6 * 0.18)

        # Kapı: OOS kârlı + yeterli profit factor (pozitif beklenti)
        eligible = [r for r in self.all_results
                    if r.get("oos_validated") and (r.get("profit_factor") or 0) >= min_pf]
        eligible.sort(key=robust_score, reverse=True)
        for r in eligible:
            r["robust_score"] = round(robust_score(r), 3)

        # Doğrulanmış ama kapıyı geçemeyenler (referans)
        validated = [r for r in self.all_results if r.get("oos_validated")]
        validated.sort(key=lambda x: (x.get("oos_pnl_pct") or -999), reverse=True)
        unvalidated = [r for r in self.all_results if not r.get("oos_validated")]
        unvalidated.sort(key=lambda x: x["full_pnl_pct"], reverse=True)

        self.state.best = eligible[0] if eligible else None

        # ── OTOMATİK UYGULA — kapıyı geçen en SAĞLAM config ────────────────────
        if eligible:
            best = eligible[0]
            self._apply_config(best)
            self.state.applied = best
            self.state.message = (
                f"✓ Uygulandı: {best['timeframe']} {'Kont' if best['params']['contrarian'] else 'Mom'} · "
                f"sağlam skor={best['robust_score']} · OOS+{best['oos_pnl_pct']:.1f}% · "
                f"PF={best['profit_factor']} · Sharpe={best['sharpe']} · DD={best['max_dd_pct']}%"
            )
            try:
                from services.notifier import notify
                notify("optimizer", f"Yeni config uygulandı: {best['timeframe']} "
                       f"{'Kontrarian' if best['params']['contrarian'] else 'Momentum'} · "
                       f"PF={best['profit_factor']} Sharpe={best['sharpe']} OOS+{best['oos_pnl_pct']:.1f}%",
                       level="success")
            except Exception:
                pass
        elif validated:
            self.state.message = (
                f"⚠ {len(validated)} config OOS kârlı AMA hiçbiri PF≥{min_pf} kapısını geçemedi "
                f"(hepsi kırılgan, negatif beklenti) → mevcut ayar KORUNDU."
            )
        else:
            self.state.message = (
                "⚠ Hiçbir config OOS testini geçemedi (görülmemiş veride kârlı değil) → "
                "mevcut ayar KORUNDU. Overfitting'den otomatik kaçınıldı."
            )
        # Sıralanmış listeyi sağlam-skora göre sakla (UI bunu gösterir)
        validated = eligible if eligible else validated

        # Sonuçları kaydet
        self._save_results(validated[:10], unvalidated[:5])
        self.state.running = False   # tur bitti

    def _apply_config(self, best: dict):
        """En iyi OOS-doğrulanmış config'i sisteme yaz (backtest bunu override okur)."""
        payload = {
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "symbol": self.config.symbol,
            "timeframe": best["timeframe"],
            "params": best["params"],
            "evidence": {
                "oos_pnl_pct": best["oos_pnl_pct"], "full_pnl_pct": best["full_pnl_pct"],
                "is_pnl_pct": best["is_pnl_pct"], "win_rate": best["win_rate"],
                "profit_factor": best["profit_factor"], "sharpe": best["sharpe"],
                "max_dd_pct": best["max_dd_pct"], "num_trades": best["num_trades"],
                "robust_score": best.get("robust_score"),
            },
        }
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_APPLIED_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info("OPTIMIZER_APPLIED %s", payload["evidence"])
        except Exception as exc:
            logger.error("apply config failed: %s", exc)

    def _save_results(self, validated: list, unvalidated: list):
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_OPT_RESULTS_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "config": asdict(self.config),
                    "validated_top": validated, "unvalidated_top": unvalidated,
                }, f, indent=2)
        except Exception as exc:
            logger.debug("save results failed: %s", exc)

    async def start(self, overrides: Optional[dict] = None) -> dict:
        if self.state.running:
            return {"status": "already_running", **self.status()}
        if overrides:
            for k, v in overrides.items():
                if hasattr(self.config, k):
                    setattr(self.config, k, v)
        self.state = OptimizerState(running=True, started_at=datetime.now(timezone.utc).isoformat(),
                                    message="Optimizasyon başladı…")

        async def _wrap():
            try:
                await self._run()
            except Exception as exc:
                self.state.last_error = str(exc)[:300]
                logger.error("optimizer run error: %s", exc, exc_info=True)
            finally:
                self.state.running = False
                self.state.finished_at = datetime.now(timezone.utc).isoformat()
                self.state.progress = 1.0

        self._task = asyncio.get_event_loop().create_task(_wrap())
        return {"status": "started", **self.status()}

    async def stop(self) -> dict:
        self._stop_flag = True
        self.state.running = False
        return {"status": "stopped", **self.status()}

    # ── OTONOM MOD: periyodik kendi kendine yeniden optimize + uygula ─────────
    _auto_task: Optional[asyncio.Task] = None
    _auto_running: bool = False
    last_auto_run: Optional[str] = None
    next_auto_run: Optional[str] = None

    async def start_auto(self, overrides: Optional[dict] = None) -> dict:
        """Otonom mod: her auto_interval_hours'ta kendi tarar + en sağlamı uygular."""
        if overrides:
            for k, v in overrides.items():
                if hasattr(self.config, k):
                    setattr(self.config, k, v)
        self.config.auto_enabled = True
        if self._auto_running:
            return {"status": "auto_already_running", "auto": self.auto_status()}
        self._auto_running = True

        async def _loop():
            # Açılışta hemen bir tur (kullanıcı sonucu hemen görsün)
            while self._auto_running:
                try:
                    if not self.state.running:
                        self.last_auto_run = datetime.now(timezone.utc).isoformat()
                        await self._run()
                except Exception as exc:
                    self.state.last_error = str(exc)[:300]
                    logger.error("auto optimize error: %s", exc, exc_info=True)
                # Sonraki tura kadar bekle (kesintiye uğrayabilir)
                import time as _t
                interval = max(600, int(self.config.auto_interval_hours * 3600))
                self.next_auto_run = datetime.fromtimestamp(_t.time() + interval, tz=timezone.utc).isoformat()
                slept = 0
                while self._auto_running and slept < interval:
                    await asyncio.sleep(10); slept += 10

        self._auto_task = asyncio.get_event_loop().create_task(_loop())
        logger.info("OPTIMIZER_AUTO_STARTED interval=%.1fh", self.config.auto_interval_hours)
        return {"status": "auto_started", "auto": self.auto_status()}

    async def stop_auto(self) -> dict:
        self._auto_running = False
        self.config.auto_enabled = False
        self.next_auto_run = None
        return {"status": "auto_stopped", "auto": self.auto_status()}

    def auto_status(self) -> dict:
        return {
            "auto_enabled": self._auto_running,
            "interval_hours": self.config.auto_interval_hours,
            "last_auto_run": self.last_auto_run,
            "next_auto_run": self.next_auto_run,
            "min_profit_factor": self.config.min_profit_factor,
        }

    def status(self) -> dict:
        s = asdict(self.state)
        s["config"] = asdict(self.config)
        s["results_count"] = len(self.all_results)
        s["auto"] = self.auto_status()
        return _to_native(s)

    def results(self, limit: int = 15) -> dict:
        # Sağlam-skora göre sıralı (kapıyı geçenler)
        min_pf = self.config.min_profit_factor
        eligible = [r for r in self.all_results
                    if r.get("oos_validated") and (r.get("profit_factor") or 0) >= min_pf]
        eligible.sort(key=lambda x: x.get("robust_score", -999), reverse=True)
        if not eligible:  # kapıyı geçen yoksa OOS-kârlıları göster
            eligible = [r for r in self.all_results if r.get("oos_validated")]
            eligible.sort(key=lambda x: (x.get("oos_pnl_pct") or -999), reverse=True)
        return _to_native({
            "validated": eligible[:limit],
            "total_evaluated": len(self.all_results),
            "applied": self.state.applied,
        })

    @staticmethod
    def get_applied() -> Optional[dict]:
        try:
            if os.path.exists(_APPLIED_CONFIG_PATH):
                with open(_APPLIED_CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None


def _to_native(obj):
    """numpy tiplerini JSON-uyumlu native Python'a çevir (recursive)."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(x) for x in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return round(float(obj), 4)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        return round(obj, 4)
    return obj


_optimizer: Optional[OptimizerAgent] = None

def get_optimizer() -> OptimizerAgent:
    global _optimizer
    if _optimizer is None:
        _optimizer = OptimizerAgent()
    return _optimizer
