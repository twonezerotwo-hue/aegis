"""
EVENT-DRIVEN PARAMETER OPTIMIZATION
Tarihsel Ani Fiyat Hareketlerini Analiz Et — AEGIS v7.1
"""
import json
import time
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import urllib.request
import urllib.error

BASE = "http://localhost:8502"
SYMBOL = "BTC/USDT"

# Önemli BTC fiyat olayları
EVENTS = [
    {"date": "2019-04-02", "type": "PUMP",        "change": +22,  "desc": "BTC 4k→5k breakout"},
    {"date": "2019-06-26", "type": "PEAK",        "change": +300, "desc": "13.8k local top"},
    {"date": "2020-03-12", "type": "CRASH",       "change": -50,  "desc": "Black Thursday COVID crash"},
    {"date": "2020-05-11", "type": "HALVING",     "change": +15,  "desc": "3rd halving event"},
    {"date": "2020-12-16", "type": "BREAKOUT",    "change": +40,  "desc": "20k ATH breach"},
    {"date": "2021-05-19", "type": "DUMP",        "change": -30,  "desc": "China mining ban"},
    {"date": "2021-11-10", "type": "ATH",         "change": +69,  "desc": "69k all-time high"},
    {"date": "2022-06-18", "type": "CRASH",       "change": -70,  "desc": "Celsius/3AC contagion"},
    {"date": "2023-03-10", "type": "BANK_CRISIS", "change": +25,  "desc": "SVB collapse → flight to BTC"},
    {"date": "2024-03-14", "type": "ETF_PUMP",    "change": +73,  "desc": "Spot ETF approval rally"},
]

TIMEFRAMES = ["4h", "1d"]
RESULTS = []


def fetch_json(url, method="GET", body=None, timeout=180):
    """Simple HTTP request without external dependencies."""
    headers = {"Content-Type": "application/json"}
    if body:
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err_body[:300]}")


def fetch_binance_candles(start_date, end_date):
    """Fetch daily candles from Binance public API."""
    start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    url = (
        f"https://api.binance.com/api/v3/klines?"
        f"symbol=BTCUSDT&interval=1d&startTime={start_ms}&endTime={end_ms}"
    )
    raw = fetch_json(url, timeout=30)
    candles = []
    for k in raw:
        candles.append({
            "ts": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return candles


def run_backtest(start, end, tf):
    """Run a backtest via AEGIS API."""
    body = {
        "symbol": SYMBOL,
        "timeframe": tf,
        "start_date": start,
        "end_date": end,
        "initial_capital": 10000,
        "use_live_data": True,
        "include_fees": True,
        "z_threshold": 0.5,
        "kelly_cap": 0.25,
        "rsi_lower": 35,
        "rsi_upper": 65,
    }
    return fetch_json(f"{BASE}/backtest/run", method="POST", body=body, timeout=180)


def main():
    print("\n" + "=" * 70)
    print(" EVENT-DRIVEN PARAMETER OPTIMIZATION — AEGIS v7.1")
    print("=" * 70)
    print(f"\n[STEP 1] Tarihsel Ani Fiyat Hareketlerini Tespit Et ({len(EVENTS)} event)")

    for evt in EVENTS:
        event_date = datetime.strptime(evt["date"], "%Y-%m-%d")
        start = (event_date - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (event_date + timedelta(days=7)).strftime("%Y-%m-%d")

        print(f"\n{'─'*60}")
        print(f"[EVENT] {evt['date']} — {evt['desc']} ({evt['change']:+d}%)")
        print(f"{'─'*60}")

        # 1. Binance fiyat verisi
        try:
            candles = fetch_binance_candles(start, end)
            event_candle = [c for c in candles if c["ts"] == evt["date"]]
            if event_candle:
                ec = event_candle[0]
                daily_chg = round((ec["close"] - ec["open"]) / ec["open"] * 100, 2)
                avg_vol = sum(c["volume"] for c in candles) / len(candles) if candles else 1
                vol_ratio = round(ec["volume"] / avg_vol, 2) if avg_vol else 0
                print(f"  Fiyat: {ec['open']:.1f} → {ec['close']:.1f} ({daily_chg:+.2f}%), Hacim: {vol_ratio}x ort.")
            else:
                print(f"  ⚠ Event günü mumu bulunamadı")
        except Exception as e:
            print(f"  ⚠ Fiyat verisi alınamadı: {e}")

        # 2. Backtest per timeframe
        for tf in TIMEFRAMES:
            print(f"  TF={tf}:", end=" ")
            try:
                report = run_backtest(start, end, tf)

                if not report.get("success"):
                    print(f"❌ Backtest failed: {report.get('detail', 'unknown')}")
                    continue

                ms = report.get("module_scores", {})
                metrics = report.get("metrics", {})
                trades = report.get("trades", [])

                pnl = metrics.get("pnl", {}).get("total_pnl_pct", 0)
                wr = metrics.get("win_loss", {}).get("win_rate", 0)
                num_trades = metrics.get("pnl", {}).get("num_trades", 0)

                # Event gününe yakın trade'ler (±1 gün)
                event_trades = []
                for t in trades:
                    try:
                        entry = datetime.fromisoformat(t["entry_time"].replace("Z", "+00:00"))
                        if abs((entry.replace(tzinfo=None) - event_date).days) <= 1:
                            event_trades.append(t)
                    except (ValueError, KeyError):
                        pass

                # Event yakalandı mı?
                captured = False
                if event_trades:
                    positions = [t.get("position", "") for t in event_trades]
                    if evt["change"] > 0 and "LONG" in positions:
                        captured = True
                    elif evt["change"] < 0 and "SHORT" in positions:
                        captured = True

                marker = "✅" if captured else ("⚠" if event_trades else "❌")
                print(
                    f"T={ms.get('touche',0):.3f} F={ms.get('fundamental',0):.3f} "
                    f"N={ms.get('news',0):.3f} S={ms.get('sentinel',0):.3f} "
                    f"Q={ms.get('quantum',0):.3f} | "
                    f"EventTrades={len(event_trades)} | PnL={pnl:+.2f}% WR={wr:.1f}% "
                    f"Trades={num_trades} {marker}"
                )

                RESULTS.append({
                    "event": evt["desc"],
                    "date": evt["date"],
                    "type": evt["type"],
                    "change": evt["change"],
                    "tf": tf,
                    "touche": ms.get("touche", 0),
                    "fundamental": ms.get("fundamental", 0),
                    "news": ms.get("news", 0),
                    "sentinel": ms.get("sentinel", 0),
                    "quantum": ms.get("quantum", 0),
                    "event_trades": len(event_trades),
                    "pnl": pnl,
                    "wr": wr,
                    "num_trades": num_trades,
                    "captured": captured,
                    "regime": report.get("regime", ""),
                    "trades_detail": [
                        {
                            "entry": t.get("entry_time"),
                            "exit": t.get("exit_time"),
                            "position": t.get("position"),
                            "pnl_pct": t.get("pnl_pct"),
                        }
                        for t in event_trades
                    ],
                })

            except Exception as e:
                print(f"❌ API Error: {e}")
                RESULTS.append({
                    "event": evt["desc"],
                    "date": evt["date"],
                    "type": evt["type"],
                    "change": evt["change"],
                    "tf": tf,
                    "error": str(e),
                    "captured": False,
                })

        # Small delay between events to avoid rate limiting
        time.sleep(0.5)

    # ═══════════════════════════════════════════════════════════════
    # ANALİZ
    # ═══════════════════════════════════════════════════════════════
    valid = [r for r in RESULTS if "error" not in r]
    if not valid:
        print("\n❌ Hiç geçerli sonuç yok!")
        sys.exit(1)

    print("\n" + "=" * 70)
    print(" EVENT CAPTURE ANALYSIS")
    print("=" * 70)

    # By event type
    from collections import defaultdict
    by_type = defaultdict(lambda: {"total": 0, "captured": 0})
    for r in valid:
        by_type[r["type"]]["total"] += 1
        if r["captured"]:
            by_type[r["type"]]["captured"] += 1

    print(f"\n{'EventType':<14} {'Total':>5} {'Captured':>8} {'Rate':>6}")
    print("─" * 36)
    for t, v in sorted(by_type.items()):
        rate = v["captured"] / v["total"] * 100 if v["total"] else 0
        print(f"{t:<14} {v['total']:>5} {v['captured']:>8} {rate:>5.1f}%")

    total_valid = len(valid)
    total_captured = sum(1 for r in valid if r["captured"])
    print(f"{'TOTAL':<14} {total_valid:>5} {total_captured:>8} {total_captured/total_valid*100:>5.1f}%")

    # By timeframe
    print(f"\n{'Timeframe':<10} {'Total':>5} {'Captured':>8} {'Rate':>6} {'AvgPnL':>8}")
    print("─" * 40)
    for tf in TIMEFRAMES:
        tf_results = [r for r in valid if r.get("tf") == tf]
        tf_cap = sum(1 for r in tf_results if r["captured"])
        avg_pnl = sum(r.get("pnl", 0) for r in tf_results) / len(tf_results) if tf_results else 0
        rate = tf_cap / len(tf_results) * 100 if tf_results else 0
        print(f"{tf:<10} {len(tf_results):>5} {tf_cap:>8} {rate:>5.1f}% {avg_pnl:>+7.2f}%")

    # ═══════════════════════════════════════════════════════════════
    # PARAMETER PATTERNS
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print(" PARAMETER PATTERNS — Event Yakalayanlar vs Kaçıranlar")
    print("=" * 70)

    captured_list = [r for r in valid if r["captured"]]
    missed_list = [r for r in valid if not r["captured"]]

    def avg_score(lst, key):
        vals = [r.get(key, 0) for r in lst if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0

    if captured_list:
        print(f"\n✅ Event Yakalayanlar ({len(captured_list)} adet) — Ort. Modül Skorları:")
        print(f"  Touche:      {avg_score(captured_list, 'touche'):.4f}")
        print(f"  Fundamental: {avg_score(captured_list, 'fundamental'):.4f}")
        print(f"  News:        {avg_score(captured_list, 'news'):.4f}")
        print(f"  Sentinel:    {avg_score(captured_list, 'sentinel'):.4f}")
        print(f"  Quantum:     {avg_score(captured_list, 'quantum'):.4f}")
        print(f"  Ort. PnL:    {avg_score(captured_list, 'pnl'):+.2f}%")
        print(f"  Ort. WR:     {avg_score(captured_list, 'wr'):.1f}%")

    if missed_list:
        print(f"\n❌ Event Kaçıranlar ({len(missed_list)} adet) — Ort. Modül Skorları:")
        print(f"  Touche:      {avg_score(missed_list, 'touche'):.4f}")
        print(f"  Fundamental: {avg_score(missed_list, 'fundamental'):.4f}")
        print(f"  News:        {avg_score(missed_list, 'news'):.4f}")
        print(f"  Sentinel:    {avg_score(missed_list, 'sentinel'):.4f}")
        print(f"  Quantum:     {avg_score(missed_list, 'quantum'):.4f}")
        print(f"  Ort. PnL:    {avg_score(missed_list, 'pnl'):+.2f}%")
        print(f"  Ort. WR:     {avg_score(missed_list, 'wr'):.1f}%")

    # Score delta
    if captured_list and missed_list:
        print(f"\n📊 Skor Farkları (Yakalayan - Kaçıran):")
        for key in ["touche", "fundamental", "news", "sentinel", "quantum"]:
            delta = avg_score(captured_list, key) - avg_score(missed_list, key)
            marker = "↑" if delta > 0 else "↓"
            print(f"  {key:14s}: {delta:+.4f} {marker}")

    # Regime analysis
    print(f"\n📊 Regime Dağılımı:")
    regime_counts = defaultdict(lambda: {"total": 0, "captured": 0})
    for r in valid:
        regime = r.get("regime", "UNKNOWN")
        regime_counts[regime]["total"] += 1
        if r["captured"]:
            regime_counts[regime]["captured"] += 1
    for reg, v in sorted(regime_counts.items()):
        rate = v["captured"] / v["total"] * 100 if v["total"] else 0
        print(f"  {reg:<22s}: {v['captured']}/{v['total']} ({rate:.0f}%)")

    # ═══════════════════════════════════════════════════════════════
    # REVİZE ÖNERİLERİ
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print(" PARAMETER REVISION PROPOSALS")
    print("=" * 70)

    proposals = """
🔧 Öneri 1: Event-Type Bazlı Z-Threshold
  • PUMP/ATH event'leri: z_threshold = 0.35 (daha erken giriş)
  • CRASH/DUMP event'leri: z_threshold = 0.65 (daha güçlü teyit)
  • NORMAL: z_threshold = 0.50 (mevcut)

🔧 Öneri 2: Sentinel Ağırlığını Event Türüne Göre Dinamik Yap
  • CRASH/BANK_CRISIS: sentinel_weight = 0.30 (makro risk öncelikli)
  • ETF_PUMP/HALVING: news_weight = 0.25 (haber akışı öncelikli)
  • BREAKOUT: touche_weight = 0.40 (teknik kırılım öncelikli)

🔧 Öneri 3: Event Window'da Kelly Cap Esnetme
  • Event öncesi 48 saat: kelly_cap = 0.35 (fırsatı kaçırma)
  • Event sonrası 48 saat: kelly_cap = 0.15 (kar realizasyonu)
  • Normal: kelly_cap = 0.25

🔧 Öneri 4: Multi-Module Confluence for Events
  • Event yakalamak için en az 3 modülün aynı yönde sinyal vermesi şartı
  • Mevcut: 2 modül yeterli → false positive artıyor
  • Öneri: event_type == "CRASH" ise 4 modül teyit iste
"""
    print(proposals)

    # ═══════════════════════════════════════════════════════════════
    # RAPOR KAYDET
    # ═══════════════════════════════════════════════════════════════
    report_dir = Path("backtest_reports")
    report_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"EVENT_ANALYSIS_{ts}.json"

    report_data = {
        "generated_at": datetime.now().isoformat(),
        "total_events": len(EVENTS),
        "total_results": len(RESULTS),
        "capture_rate": total_captured / total_valid * 100 if total_valid else 0,
        "by_type": {t: v for t, v in by_type.items()},
        "by_regime": {r: v for r, v in regime_counts.items()},
        "captured_avg_scores": {k: avg_score(captured_list, k) for k in ["touche", "fundamental", "news", "sentinel", "quantum"]} if captured_list else {},
        "missed_avg_scores": {k: avg_score(missed_list, k) for k in ["touche", "fundamental", "news", "sentinel", "quantum"]} if missed_list else {},
        "results": RESULTS,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)

    print(f"💾 Detaylı rapor: {report_file}")

    print("\n[SONRAKİ ADIM]")
    print("Bu analiz sonucunda hangi öneriyi uygulamak istersin?")
    print("A) Z-threshold'ı event-type bazlı dinamik yap")
    print("B) Sentinel/News ağırlıklarını haber tipi göre ayarla")
    print("C) Kelly cap'i event window'da esnet")
    print("D) Multi-module confluence şartını sıkılaştır")


if __name__ == "__main__":
    main()
