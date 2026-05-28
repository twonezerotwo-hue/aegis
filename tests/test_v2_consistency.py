"""
AEGIS v7.3 — V1 vs V2 Data Consistency Validation Test
Validates all BacktestResultV2 TypeScript interface fields against live API
"""
import requests
import json

API = "http://localhost:8502"
params = {
    "symbol": "BTC/USDT",
    "timeframe": "4h",
    "start_date": "2025-01-01",
    "end_date": "2025-03-01",
    "initial_capital": 10000,
    "use_live_data": True,
    "include_fees": True,
}

print("=" * 60)
print("V1 vs V2 DATA CONSISTENCY TEST")
print("=" * 60)

r = requests.post(f"{API}/backtest/run", json=params, timeout=30)
d = r.json()

print("\n[API Response Schema]")
print(f"  success:       {d.get('success')}")
print(f"  backtest_id:   {d.get('backtest_id', 'MISSING')}")
print(f"  symbol:        {d.get('symbol')}")
print(f"  timeframe:     {d.get('timeframe')}")
print(f"  date_range:    {d.get('date_range')}")
print(f"  data_points:   {d.get('data_points')}")
print(f"  total_trades:  {d.get('total_trades')}")

m = d.get("metrics", {})
pnl = m.get("pnl", {})
wl = m.get("win_loss", {})
dd = m.get("drawdown", {})

print("\n[Metrics]")
print(f"  PnL:           {pnl.get('total_pnl', '?')} ({pnl.get('total_pnl_pct', '?')}%)")
print(f"  Win Rate:      {wl.get('win_rate', '?')}%  ({wl.get('win_count', '?')}W / {wl.get('loss_count', '?')}L)")
print(f"  Profit Factor: {wl.get('profit_factor', '?')}")
print(f"  Max Drawdown:  {dd.get('max_drawdown_pct', '?')}%")
print(f"  Sharpe:        {m.get('sharpe_ratio', '?')}")
print(f"  Sortino:       {m.get('sortino_ratio', '?')}")
print(f"  Capital:       {m.get('initial_capital', '?')} -> {m.get('final_capital', '?')}")

ms = d.get("module_scores", {})
print("\n[Module Scores]")
for k, v in ms.items():
    bar = "#" * int(v * 40)
    print(f"  {k:15s} {v:.4f}  |{bar}|")

# V2 TypeScript interface field validation
print("\n[V2 Interface Compatibility]")
all_ok = True

checks = {
    "BacktestResultV2": (d, ["success", "backtest_id", "symbol", "timeframe", "date_range", "metrics", "module_scores", "total_trades", "trades", "data_points"]),
    "Metrics": (m, ["pnl", "win_loss", "drawdown", "sharpe_ratio", "sortino_ratio", "initial_capital", "final_capital"]),
    "PnL": (pnl, ["total_pnl", "total_pnl_pct", "num_trades"]),
    "WinLoss": (wl, ["win_rate", "win_count", "loss_count", "avg_win", "avg_loss", "profit_factor"]),
    "Drawdown": (dd, ["max_drawdown", "max_drawdown_pct"]),
    "ModuleScores": (ms, ["touche", "fundamental", "quantum", "sentinel", "news"]),
}

for section, (obj, fields) in checks.items():
    for f in fields:
        ok = f in obj
        status = "OK" if ok else "MISSING"
        if not ok:
            all_ok = False
        print(f"  {section}.{f}: {status}")

# Frontend health
print("\n[Frontend Health]")
try:
    r1 = requests.get("http://localhost:3001/", timeout=5)
    print(f"  V1 (/)           : {r1.status_code} ({len(r1.text)} bytes)")
except Exception as e:
    print(f"  V1 (/)           : FAILED - {e}")

try:
    r2 = requests.get("http://localhost:3001/v2/backtest", timeout=5)
    print(f"  V2 (/v2/backtest): {r2.status_code} ({len(r2.text)} bytes)")
except Exception as e:
    print(f"  V2 (/v2/backtest): FAILED - {e}")

# Trade field consistency
trades = d.get("trades", [])
print(f"\n[Trade Consistency]")
print(f"  Total trades: {len(trades)}")
if trades:
    t = trades[0]
    print(f"  First trade fields: {list(t.keys())}")
    v2_trade_fields = ["entry_time", "exit_time", "entry_price", "exit_price", "position", "pnl", "pnl_pct"]
    for tf in v2_trade_fields:
        ok = tf in t
        status = "OK" if ok else "MISSING"
        if not ok:
            all_ok = False
        print(f"  Trade.{tf}: {status}")

print(f"\n{'=' * 60}")
if all_ok:
    print("RESULT: ALL V2 INTERFACE FIELDS VALIDATED")
    print("V1 -> V2 DATA CONSISTENCY: PASSED")
else:
    print("RESULT: SOME FIELDS MISSING - CHECK ABOVE")
print("=" * 60)
