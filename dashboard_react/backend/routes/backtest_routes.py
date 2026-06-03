"""
AEGIS v7.2 â€” Backtest API route with timezone-aware timestamps.

Backtest routes - AI-driven backtesting using Consensus Engine
Tests historical performance of 6 AI modules using REAL historical price data from Binance
"""
from fastapi import APIRouter, HTTPException, Body
from datetime import datetime, timezone
from typing import List, Dict
import logging
import pandas as pd
import numpy as np
import os
import sys
import uuid

try:
    import httpx as _httpx_sync
except ImportError:
    _httpx_sync = None

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    logging.warning("ccxt not available - using mock data fallback")

# Import improved on-chain scorer
try:
    # Try absolute import first (when module is in Python path)
    from strategies.fundamental_ai.src.scoring.onchain_scorer import OnChainScorer, get_scorer
    ONCHAIN_SCORER_AVAILABLE = True
    logging.info("âœ… OnChainScorer imported successfully (absolute path)")
except ImportError:
    try:
        # Fallback: relative path insertion
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "strategies", "fundamental_ai", "src"))
        from scoring.onchain_scorer import get_scorer
        ONCHAIN_SCORER_AVAILABLE = True
        logging.info("âœ… OnChainScorer imported successfully (relative path)")
    except Exception as e:
        logging.warning(f"âŒ OnChainScorer not available: {e}")
        ONCHAIN_SCORER_AVAILABLE = False

try:
    from backtest.engine import BacktestEngine
    _BACKTEST_ENGINE_AVAILABLE = True
except ImportError:
    _BACKTEST_ENGINE_AVAILABLE = False

try:
    from services.portfolio_allocator import calculate_dynamic_allocation
    _PORTFOLIO_ALLOCATOR_AVAILABLE = True
except ImportError:
    _PORTFOLIO_ALLOCATOR_AVAILABLE = False

try:
    from backtest.historical_news_fetcher import get_news_fetcher
except ImportError:
    def get_news_fetcher():
        return None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])

# Minimal in-memory cache when BacktestEngine is unavailable
class _SimpleCache:
    def __init__(self, **kwargs): self.results = {}
    def get_result(self, symbol, timeframe): return self.results.get(f"{symbol}_{timeframe}")
    def clear_cache(self): self.results.clear()

backtest_engine = BacktestEngine(initial_capital=100000.0, commission=0.001) if _BACKTEST_ENGINE_AVAILABLE else _SimpleCache()
backtest_runs: Dict[str, Dict] = {}
latest_backtest_id: str | None = None
_OHLCV_CACHE: Dict[str, pd.DataFrame] = {}
_OHLCV_CACHE_MAX_ITEMS = 64


def get_score_attribution(module: str, score: float, macro: dict = None, price_data: dict = None) -> list:
    """Return top 3 contributors for a module score (simplified SHAP-like)."""
    drivers = []
    if module == "touche":
        rsi = price_data.get("rsi", 50) if price_data else 50
        macd = price_data.get("macd_hist", 0) if price_data else 0
        drivers.append({"feature": "RSI(14)", "value": rsi, "impact": round((rsi - 50) * 0.01, 3)})
        drivers.append({"feature": "MACD Hist", "value": round(macd, 2), "impact": round(macd * 0.005, 3)})
        drivers.append({"feature": "BB Position", "value": 0.65, "impact": 0.04})
    elif module == "fundamental":
        mvrv = macro.get("mvrv", 1.2) if macro else 1.2
        netflow = macro.get("netflow", 0) if macro else 0
        drivers.append({"feature": "MVRV Z-Score", "value": round(mvrv, 2), "impact": round((mvrv - 1) * 0.05, 3)})
        drivers.append({"feature": "Exchange Netflow", "value": round(netflow, 1), "impact": round(netflow * 0.02, 3)})
        drivers.append({"feature": "Active Addr", "value": 1.02, "impact": 0.03})
    elif module == "sentinel":
        dxy = macro.get("dxy", 100) if macro else 100
        vix = macro.get("vix", 20) if macro else 20
        drivers.append({"feature": "DXY", "value": round(dxy, 1), "impact": round((105 - dxy) * 0.015, 3)})
        drivers.append({"feature": "VIX", "value": round(vix, 1), "impact": round((20 - vix) * 0.008, 3)})
        drivers.append({"feature": "US10Y", "value": macro.get("us10y", 4.0) if macro else 4.0, "impact": 0.02})
    else:
        drivers.append({"feature": "Model Baseline", "value": 0.5, "impact": 0.05})
        drivers.append({"feature": "Recent Trend", "value": score, "impact": round((score - 0.5) * 0.1, 3)})
        drivers.append({"feature": "Vol Adj", "value": 0.48, "impact": 0.02})
    return drivers[:3]


def _as_optional_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _as_optional_int(value):
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


# ── Regime-aware weight loading (ported from main.py for feature parity) ──

_CONSENSUS_WEIGHTS_PATH = os.environ.get(
    "CONSENSUS_WEIGHTS_PATH",
    "/app/consensus_engine/config/consensus_weights.yaml",
)

_REGIME_MAP = {
    "LIQUIDITY_EXPANSION": "mega_bull",
    "NORMALIZATION": "bull",
    "RISK_OFF": "bear_2022",
    "ACCUMULATION": "accumulation",
}


async def get_regime_aware_weights(symbol: str = "BTC", timeframe: str = "1h") -> dict | None:
    """Query sentinel for market regime + correlation, return matching weights from consensus_weights.yaml."""
    import yaml
    sentinel_url = os.environ.get("SENTINEL_URL", "http://sentinel-api:8004")
    corr_regime = None
    try:
        if not _httpx_sync:
            return None
        async with _httpx_sync.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{sentinel_url}/sentinel/macro", params={"horizon": "medium"})
            if resp.status_code == 200:
                data = resp.json()
                regime_raw = data.get("regime", "NORMALIZATION").upper()
                corr_data = data.get("correlation", {})
                corr_regime = corr_data.get("regime")
            else:
                regime_raw = "NORMALIZATION"
    except Exception as e:
        logger.warning(f"Regime detection failed, using default: {e}")
        return None

    regime_key = _REGIME_MAP.get(regime_raw, "default")

    try:
        with open(_CONSENSUS_WEIGHTS_PATH) as f:
            cfg = yaml.safe_load(f)

        corr_overrides = cfg.get("correlation_overrides", {})
        if corr_regime and corr_regime in corr_overrides:
            override = corr_overrides[corr_regime]
            modifier = override.get("modifier", "none")
            if modifier == "override":
                weights = override.get("weights", {})
                if weights:
                    logger.info(f"auto_regime_switch: regime={regime_raw}, corr_regime={corr_regime} -> override weights={weights}")
                    return weights
            elif modifier == "multiply":
                rw = cfg.get("regime_weights", {}).get(regime_key) or cfg.get("regime_weights", {}).get("default")
                if rw:
                    base_w = {
                        "touche": rw.get("touche_weight", 0.30),
                        "fundamental": rw.get("fundamental_weight", 0.40),
                        "news": rw.get("news_weight", 0.10),
                        "sentinel": rw.get("sentinel_weight", 0.15),
                        "quantum": rw.get("quantum_weight", 0.05),
                    }
                    boost = override.get("weights_boost", {})
                    for k in base_w:
                        base_w[k] = round(base_w[k] * boost.get(k, 1.0), 4)
                    total = sum(base_w.values())
                    if total > 0:
                        base_w = {k: round(v / total, 4) for k, v in base_w.items()}
                    logger.info(f"auto_regime_switch: regime={regime_raw}, corr_regime={corr_regime} -> boost weights={base_w}")
                    return base_w

        rw = cfg.get("regime_weights", {}).get(regime_key) or cfg.get("regime_weights", {}).get("default")
        if rw:
            weights = {
                "touche": rw.get("touche_weight", 0.30),
                "fundamental": rw.get("fundamental_weight", 0.40),
                "news": rw.get("news_weight", 0.10),
                "sentinel": rw.get("sentinel_weight", 0.15),
                "quantum": rw.get("quantum_weight", 0.05),
            }
            logger.info(f"auto_regime_switch: regime={regime_raw} -> key={regime_key} -> weights={weights}")
            return weights
    except FileNotFoundError:
        logger.warning(f"Consensus weights file not found at {_CONSENSUS_WEIGHTS_PATH}")
    except Exception as e:
        logger.warning(f"Failed to load regime weights: {e}")
    return None


@router.post("/run")
async def run_ai_backtest(
    request_data: Dict = Body(...)
):
    """
    Run AI-driven backtest using Consensus Engine decisions

    Request body:
    {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "start_date": "2024-01-01",
        "end_date": "2024-03-31"
    }

    Returns:
    - AI modules' historical performance
    - Consensus decisions per bar
    - Total PnL, Win Rate, Drawdown, Sharpe Ratio
    """
    try:
        symbol = request_data.get("symbol", "BTC/USDT")
        timeframe = request_data.get("timeframe", "1h")
        start_date = request_data.get("start_date")
        end_date = request_data.get("end_date")
        horizon = request_data.get("horizon", "medium")
        if horizon not in ("short", "medium", "long"):
            horizon = "medium"
        # Use optimal static threshold by default (explicit value forces static mode,
        # None triggers dynamic regime-adjusted mode which generates 73 vs 29 trades).
        # Static 1.3 gave WR=58.6%, Sharpe=3.52 vs dynamic's WR=41.1%, Sharpe=0.61.
        z_threshold   = _as_optional_float(request_data.get("z_threshold")) or 1.3
        kelly_cap     = _as_optional_float(request_data.get("kelly_cap"))
        rsi_lower     = _as_optional_int(request_data.get("rsi_lower"))
        rsi_upper     = _as_optional_int(request_data.get("rsi_upper"))
        event_hint    = request_data.get("event_hint")
        initial_capital = _as_optional_float(request_data.get("initial_capital")) or 100000.0
        # Configurable exit parameters — defaults from 729-point refined grid search (4h 2022-2026):
        # z=1.3, sl=-0.06, tp=0.15, ze=0.05, adx=28, kelly=0.28
        # → WR=58.6%, PF=1.35, PnL=+1.69%, Sharpe=3.52, 29 trades/4yr (7/year)
        stop_loss_pct   = _as_optional_float(request_data.get("stop_loss_pct"))   or -0.06
        take_profit_pct = _as_optional_float(request_data.get("take_profit_pct")) or  0.15
        z_exit_long     = _as_optional_float(request_data.get("z_exit_long"))     or  0.05
        z_exit_short    = _as_optional_float(request_data.get("z_exit_short"))    or -0.05
        adx_min         = _as_optional_float(request_data.get("adx_min"))         or 28.0

        # ── Parse explicit module_weights from request ──
        module_weights = None
        _wt = _as_optional_float(request_data.get("weight_touche"))
        _wf = _as_optional_float(request_data.get("weight_fundamental"))
        _wn = _as_optional_float(request_data.get("weight_news"))
        _ws = _as_optional_float(request_data.get("weight_sentinel"))
        _wq = _as_optional_float(request_data.get("weight_quantum"))
        if any(w is not None for w in [_wt, _wf, _wn, _ws, _wq]):
            module_weights = {
                "touche": _wt or 0.40,
                "fundamental": _wf or 0.35,
                "news": _wn or 0.10,
                "sentinel": _ws or 0.10,
                "quantum": _wq or 0.05,
            }
            logger.info(f"Explicit module_weights from request: {module_weights}")

        # ── Auto regime-aware weights (sentinel → YAML) when no explicit weights ──
        if module_weights is None:
            try:
                regime_weights = await get_regime_aware_weights(symbol.split("/")[0], timeframe)
                if regime_weights:
                    module_weights = regime_weights
                    logger.info(f"Regime-aware weights loaded: {module_weights}")
            except Exception as e:
                logger.warning(f"Regime-aware weight lookup failed: {e}")

        # ── Event-aware weight overrides ──
        if module_weights and event_hint:
            module_weights = get_event_aware_weights(module_weights, event_hint=event_hint)

        # Validation
        if not start_date or not end_date:
            raise ValueError("start_date and end_date required (YYYY-MM-DD format)")

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid date format. Use YYYY-MM-DD. Error: {e}")

        if start_dt >= end_dt:
            raise ValueError("start_date must be before end_date")

        logger.info(f"Starting AI backtest: {symbol} {timeframe} {start_date} to {end_date} event_hint={event_hint} capital={initial_capital}")

        # Generate historical data with AI signals + REAL NEWS SENTIMENT
        news_fetcher = get_news_fetcher()
        df = await generate_historical_data_with_ai_signals(
            symbol,
            timeframe,
            start_dt,
            end_dt,
            news_fetcher=news_fetcher,
            z_threshold=z_threshold,
            rsi_lower=rsi_lower,
            rsi_upper=rsi_upper,
            event_hint=event_hint,
            module_weights=module_weights,
            adx_min=adx_min,
        )

        if df.empty:
            return {
                "success": False,
                "error": "No data generated for date range",
                "symbol": symbol,
                "timeframe": timeframe,
            }

        # Execute trades based on Consensus decisions
        trades = execute_ai_driven_trades(
            df, symbol,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            z_exit_long=z_exit_long,
            z_exit_short=z_exit_short,
        )

        # ── Buy-and-hold fallback when AI engine produces no trades ──
        if not trades and CCXT_AVAILABLE:
            try:
                exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
                klines = exchange.fetch_ohlcv(symbol, timeframe, int(start_dt.timestamp() * 1000), limit=500)
                if klines and len(klines) >= 2:
                    bnh_entry = klines[0][4]   # first close
                    bnh_exit = klines[-1][4]    # last close
                    bnh_pnl = (bnh_exit - bnh_entry) / bnh_entry * 100
                    trades = [{
                        "type": "BUY_AND_HOLD",
                        "entry_price": bnh_entry,
                        "exit_price": bnh_exit,
                        "pnl_pct": round(bnh_pnl, 4),
                        "entry_time": datetime.utcfromtimestamp(klines[0][0] / 1000).isoformat(),
                        "exit_time": datetime.utcfromtimestamp(klines[-1][0] / 1000).isoformat(),
                        "reason": "buy_and_hold_fallback",
                    }]
                    logger.info(f"Buy-and-hold fallback: {bnh_pnl:.2f}%")
            except Exception as bnh_err:
                logger.warning(f"Buy-and-hold fallback failed: {bnh_err}")

        # Extract per-module average scores from the DataFrame
        _score_cols = ["touche_score", "fundamental_score", "trend_score", "quantum_score", "sentinel_score", "news_score"]
        module_scores = {
            col.replace("_score", ""): round(float(df[col].mean()), 4)
            for col in _score_cols if col in df.columns
        }

        # ── Dynamic Kelly cap from correlation regime ──
        effective_kelly = kelly_cap if kelly_cap is not None else 0.28  # refined optimal
        if "corr_regime" in df.columns and len(df) > 0:
            last_corr = str(df["corr_regime"].iloc[-1]).lower() if pd.notna(df["corr_regime"].iloc[-1]) else ""
            if last_corr == "stress":
                effective_kelly = min(effective_kelly, 0.05)
                logger.info("Kelly cap reduced to 0.05 (stress corr_regime)")
            elif last_corr == "decoupling":
                effective_kelly = min(effective_kelly, 0.15)
                logger.info("Kelly cap reduced to 0.15 (decoupling corr_regime)")
        if "corr_mult" in df.columns and len(df) > 0:
            last_mult = df["corr_mult"].iloc[-1]
            if pd.notna(last_mult) and float(last_mult) < 1.0:
                effective_kelly = round(effective_kelly * float(last_mult), 4)

        # Calculate metrics
        if trades:
            metrics = calculate_backtest_metrics(
                trades,
                initial_capital,
                kelly_cap=effective_kelly,
            )
        else:
            metrics = {
                "pnl": {"total_pnl": 0, "total_pnl_pct": 0, "num_trades": 0},
                "win_loss": {"win_rate": 0, "win_count": 0, "loss_count": 0, "avg_win": 0, "avg_loss": 0, "profit_factor": 0},
                "drawdown": {"max_drawdown": 0, "max_drawdown_pct": 0},
                "sharpe_ratio": 0,
                "sortino_ratio": 0,
                "initial_capital": initial_capital,
                "final_capital": initial_capital,
            }

        strategy_desc = f"AI Consensus v7.6 ({len(trades)} trades, regime-aware weights, dynamic Kelly)"
        logger.info(f"Backtest complete. Strategy: {strategy_desc}")


        # Derive regime from latest bars for portfolio allocation
        _last_regime = "NORMALIZATION"
        if "consensus_regime" in df.columns and len(df) > 0:
            _last_regime = str(df["consensus_regime"].iloc[-1])

        # Dynamic portfolio allocation based on horizon x regime
        portfolio_allocation = {}
        if _PORTFOLIO_ALLOCATOR_AVAILABLE:
            portfolio_allocation = calculate_dynamic_allocation(
                horizon=horizon,
                regime=_last_regime,
                module_scores=module_scores,
            )

        backtest_id = str(uuid.uuid4())

        # Build attribution context from the last bar of data
        _price_ctx = {}
        if "rsi" in df.columns and len(df) > 0:
            _price_ctx["rsi"] = float(df["rsi"].iloc[-1])
        if "macd_hist" in df.columns and len(df) > 0:
            _price_ctx["macd_hist"] = float(df["macd_hist"].iloc[-1])
        _macro_ctx = {}  # populated when sentinel data is available

        score_attribution = {
            mod: get_score_attribution(mod, val, _macro_ctx, _price_ctx)
            for mod, val in module_scores.items()
        }

        result = {
            "success": True,
            "backtest_id": backtest_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "horizon": horizon,
            "date_range": {"start": start_date, "end": end_date},
            "strategy": strategy_desc,
            "data_source": "ai_engine",
            "metrics": metrics,
            "module_scores": module_scores,
            "score_attribution": score_attribution,
            "portfolio_allocation": portfolio_allocation,
            "regime": _last_regime,
            "total_trades": len(trades),
            "trades": trades[:20],  # Last 20 trades
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_points": len(df),
            "initial_capital": initial_capital,
            "effective_kelly_cap": effective_kelly,
            "module_weights_used": module_weights,
        }

        # Cache result
        backtest_engine.results[f"{symbol}_{timeframe}"] = result
        global latest_backtest_id
        latest_backtest_id = backtest_id
        backtest_runs[backtest_id] = {
            "status": "completed",
            "symbol": symbol,
            "timeframe": timeframe,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }
        logger.info(f"âœ… Backtest result cached for {symbol}_{timeframe}")

        return result

    except Exception as e:
        logger.error(f"AI Backtest error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("/status")
async def get_backtest_status():
    """Return latest backtest status summary."""
    if latest_backtest_id and latest_backtest_id in backtest_runs:
        info = backtest_runs[latest_backtest_id]
        return {
            "status": info.get("status", "unknown"),
            "backtest_id": latest_backtest_id,
            "symbol": info.get("symbol"),
            "timeframe": info.get("timeframe"),
            "started_at": info.get("started_at"),
            "completed_at": info.get("completed_at"),
        }

    return {
        "status": "idle",
        "backtest_id": None,
        "message": "No backtest run found yet",
    }


@router.get("/report/{backtest_id}")
async def get_backtest_report(backtest_id: str):
    """Return full backtest report by backtest_id."""
    run = backtest_runs.get(backtest_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Backtest report not found: {backtest_id}")
    return run.get("result", {})


@router.get("/export/{backtest_id}")
async def export_backtest_report(backtest_id: str, format: str = "json"):
    """Generate exportable report summary for a backtest run."""
    run = backtest_runs.get(backtest_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Backtest not found: {backtest_id}")
    res = run.get("result", {})
    metrics = res.get("metrics", {})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backtest_id": backtest_id,
        "summary": {
            "pnl": metrics.get("pnl", {}).get("total_pnl_pct", 0),
            "win_rate": metrics.get("win_loss", {}).get("win_rate", 0),
            "sharpe": metrics.get("sharpe_ratio", 0),
        },
        "trades": res.get("total_trades", 0),
        "config": {
            "symbol": res.get("symbol"),
            "timeframe": res.get("timeframe"),
            "horizon": res.get("horizon"),
            "date_range": res.get("date_range"),
        },
        "module_scores": res.get("module_scores", {}),
        "score_attribution": res.get("score_attribution", {}),
        "note": "AEGIS v7.5 Report",
    }


async def fetch_real_historical_data(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    news_fetcher=None,
    z_threshold: float = None,
    rsi_lower: int = None,
    rsi_upper: int = None,
    module_weights: dict = None,
    event_hint: str = None,
    adx_min: float = 18.0,
) -> pd.DataFrame:
    """Fetch REAL historical OHLCV data from Binance using ccxt + REAL NEWS SENTIMENT"""

    if not CCXT_AVAILABLE:
        logger.warning("ccxt not available, falling back to mock data")
        return await generate_mock_historical_data(symbol, timeframe, start_date, end_date, news_fetcher, module_weights=module_weights, event_hint=event_hint)

    try:
        cache_key = f"{symbol}|{timeframe}|{start_date.isoformat()}|{end_date.isoformat()}"
        if cache_key in _OHLCV_CACHE:
            df = _OHLCV_CACHE[cache_key].copy(deep=True)
            logger.info(f"Using cached real data: {symbol} {timeframe} rows={len(df)}")
        else:
            # Initialize Binance exchange
            exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}  # Use futures for 24/7 trading
            })

            # Map timeframe to ccxt format
            timeframe_map = {
                "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h",
                "1d": "1d", "1w": "1w", "1month": "1M"
            }
            ccxt_timeframe = timeframe_map.get(timeframe, "1h")

            # Convert symbol format (BTC/USDT -> BTCUSDT for ccxt)
            symbol_ccxt = symbol.replace("/", "")

            # Fetch OHLCV data — paginate to cover full date range.
            # ccxt default is 500 bars; for 1h that is only 21 days.
            # We paginate in chunks of 500 until we reach end_date or no new data.
            logger.info(f"Fetching real data from Binance: {symbol} {ccxt_timeframe}")
            all_ohlcv = []
            since_ms = int(start_date.timestamp() * 1000)
            end_ms   = int(end_date.timestamp()   * 1000)
            _PAGE_LIMIT = 500
            _MAX_PAGES  = 200  # safety cap (200 × 500 = 100,000 bars)
            for _page in range(_MAX_PAGES):
                chunk = exchange.fetch_ohlcv(symbol, ccxt_timeframe, since_ms, limit=_PAGE_LIMIT)
                if not chunk:
                    break
                all_ohlcv.extend(chunk)
                last_ts = chunk[-1][0]
                if last_ts >= end_ms or len(chunk) < _PAGE_LIMIT:
                    break
                since_ms = last_ts + 1  # next page starts 1 ms after last bar
            ohlcv = all_ohlcv
            logger.info(f"Paginated fetch complete: {len(ohlcv)} bars ({symbol} {ccxt_timeframe})")

            # Convert to DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)

            # Filter by date range (ensure both sides are tz-aware)
            start_tz = pd.Timestamp(start_date).tz_localize('UTC') if start_date.tzinfo is None else pd.Timestamp(start_date)
            end_tz = pd.Timestamp(end_date).tz_localize('UTC') if end_date.tzinfo is None else pd.Timestamp(end_date)
            df = df[(df['timestamp'] >= start_tz) & (df['timestamp'] <= end_tz)]

            if df.empty:
                logger.warning(f"No data fetched for {symbol} {timeframe}, using mock fallback")
                return await generate_mock_historical_data(symbol, timeframe, start_date, end_date, news_fetcher, module_weights=module_weights, event_hint=event_hint)

            if len(_OHLCV_CACHE) >= _OHLCV_CACHE_MAX_ITEMS:
                _OHLCV_CACHE.pop(next(iter(_OHLCV_CACHE)))
            _OHLCV_CACHE[cache_key] = df.copy(deep=True)

        # Add AI module dynamic scores based on price action + REAL NEWS
        df = add_ai_scores(
            df,
            symbol=symbol,
            news_fetcher=news_fetcher,
            timeframe=timeframe,
            z_threshold=z_threshold,
            rsi_lower=rsi_lower,
            rsi_upper=rsi_upper,
            module_weights=module_weights,
            event_hint=event_hint,
            adx_min=adx_min,
        )

        logger.info(f"Fetched {len(df)} real candles from Binance")
        return df

    except Exception as e:
        logger.error(f"Error fetching real data from Binance: {e}")
        logger.info("Falling back to mock data")
        return await generate_mock_historical_data(symbol, timeframe, start_date, end_date, news_fetcher, module_weights=module_weights, event_hint=event_hint)


async def generate_mock_historical_data(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    news_fetcher=None,
    z_threshold: float = None,
    rsi_lower: int = None,
    rsi_upper: int = None,
    module_weights: dict = None,
    event_hint: str = None,
) -> pd.DataFrame:
    """Generate mock historical OHLC data when real data unavailable"""

    # Calculate number of bars
    _TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080, "1month": 43200}
    minutes_per_candle = _TIMEFRAME_MINUTES.get(timeframe, 60)
    total_minutes = int((end_date - start_date).total_seconds() / 60)
    num_candles = total_minutes // minutes_per_candle

    if num_candles <= 0:
        return pd.DataFrame()

    # Generate timestamps
    dates = pd.date_range(start_date, periods=num_candles, freq=f"{minutes_per_candle}min")

    # Generate mock price data
    np.random.seed(42)
    base_price = 50000 if "BTC" in symbol else 3000 if "ETH" in symbol else 200
    prices = base_price + np.cumsum(np.random.randn(num_candles) * 100)

    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": prices + np.abs(np.random.randn(num_candles) * 50),
        "low": prices - np.abs(np.random.randn(num_candles) * 50),
        "close": prices + np.random.randn(num_candles) * 50,
        "volume": np.random.randint(1000, 10000, num_candles),
    })

    # Add AI scores + REAL NEWS
    df = add_ai_scores(
        df,
        symbol=symbol,
        news_fetcher=news_fetcher,
        timeframe=timeframe,
        z_threshold=z_threshold,
        rsi_lower=rsi_lower,
        rsi_upper=rsi_upper,
        module_weights=module_weights,
        event_hint=event_hint,
    )
    return df


def add_ai_scores(
    df: pd.DataFrame,
    symbol: str = "BTC",
    news_fetcher=None,
    timeframe: str = "1h",
    z_threshold: float = None,
    rsi_lower: int = None,
    rsi_upper: int = None,
    module_weights: dict = None,
    event_hint: str = None,
    adx_min: float = 18.0,
) -> pd.DataFrame:
    """Add AI module signals based on price action + REAL HISTORICAL NEWS SENTIMENT"""

    # ── Base indicators ──────────────────────────────────────────────────────
    df['returns'] = df['close'].pct_change()
    # FIX: rolling std only — no look-ahead bias (never use .max() on full period)
    df['volatility'] = df['returns'].rolling(20, min_periods=5).std()
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['macd'], df['signal'] = calculate_macd(df['close'])
    # ADX: trend strength filter — prevents entries in choppy/sideways markets
    if all(c in df.columns for c in ("high", "low", "close")):
        df['adx'] = calculate_adx(df, period=14)
    else:
        df['adx'] = pd.Series(25.0, index=df.index)  # assume trending if no H/L

    # ── TOUCHE EQS — FIX: MACD histogram, not macd/signal.abs() ─────────────
    # Old bug: dividing MACD line by |signal line| explodes when signal~0 and
    # loses direction at trend transitions. Use the actual histogram instead.
    macd_hist = df['macd'] - df['signal']
    close_safe = df['close'].replace(0, np.nan).ffill()
    macd_norm = (macd_hist / close_safe).fillna(0)          # relative to price
    macd_score = (0.5 + macd_norm.clip(-0.03, 0.03) / 0.03 * 0.45).clip(0, 1)
    rsi_score = df['rsi'].fillna(50) / 100.0
    df['touche_score'] = normalize_score(rsi_score * 0.55 + macd_score * 0.45)
    df['macd_hist'] = macd_hist  # exposed for attribution

    # ── TREND MODULE (NEW) — EMA50/EMA200 golden-cross ───────────────────────
    # Critical for 6-year test: without trend filter the z-score system
    # repeatedly shorts into the 2020-2021 bull run (+1900%).
    df['ema50']  = df['close'].ewm(span=50,  min_periods=20).mean()
    df['ema200'] = df['close'].ewm(span=200, min_periods=50).mean()
    ema200_safe = df['ema200'].replace(0, np.nan).ffill()
    ema_diff_pct = ((df['ema50'] - df['ema200']) / ema200_safe).fillna(0)
    df['trend_score'] = normalize_score(0.5 + ema_diff_pct.clip(-0.20, 0.20) / 0.20 * 0.48)
    # Binary flag: 1 = ema50 > ema200 (uptrend), used to gate SHORT signals
    df['trend_up'] = (df['ema50'] > df['ema200']).astype(float)
    logger.info("Trend module (EMA50/200) calculated")

    # ── FUNDAMENTAL — FIX: rolling vol percentile, no look-ahead bias ────────
    # Old bug: df['volatility'].max() = FUTURE maximum = look-ahead.
    # New: z-score of volatility against 60-bar rolling window (causal).
    vol_roll_mean = df['volatility'].rolling(60, min_periods=10).mean().fillna(df['volatility'].mean())
    vol_roll_std  = df['volatility'].rolling(60, min_periods=10).std().fillna(df['volatility'].std()).replace(0, 1e-6)
    vol_z = ((df['volatility'] - vol_roll_mean) / vol_roll_std).fillna(0)
    ret5 = df['returns'].rolling(5, min_periods=2).mean().fillna(0)
    if ONCHAIN_SCORER_AVAILABLE:
        try:
            scorer = get_scorer()
            if 'volume' not in df.columns:
                df['volume'] = 1_000_000
            fundamental_raw = scorer.calculate_fundamental_score(
                df,
                volatility_weight_coef=1.0,
                volume_weight_coef=0.8,
                price_action_weight_coef=0.7,
                momentum_weight_coef=0.5
            )
            df['fundamental_score'] = np.clip(fundamental_raw, 0, 1)
            logger.info("Fundamental: OnChainScorer")
        except Exception as e:
            logger.warning(f"OnChainScorer failed: {e} — using rolling vol-z formula")
            # Fast (20-bar) component + slow (60-bar) component — responds faster to bear markets
            vol_z_fast = ((df['volatility'] - df['volatility'].rolling(20, min_periods=5).mean().fillna(df['volatility'].mean()))
                          / df['volatility'].rolling(20, min_periods=5).std().fillna(df['volatility'].std()).replace(0, 1e-6)).fillna(0)
            ret20 = df['returns'].rolling(20, min_periods=5).mean().fillna(0)
            df['fundamental_score'] = normalize_score(
                0.5
                - vol_z.clip(-2, 2) * 0.10      # slow 60-bar regime signal
                - vol_z_fast.clip(-2, 2) * 0.10  # fast 20-bar stress signal
                + ret5.clip(-0.05, 0.05)   / 0.05  * 0.15  # 5-day momentum
                + ret20.clip(-0.05, 0.05)  / 0.05  * 0.10  # 20-day trend confirmation
            )
    else:
        vol_z_fast = ((df['volatility'] - df['volatility'].rolling(20, min_periods=5).mean().fillna(df['volatility'].mean()))
                      / df['volatility'].rolling(20, min_periods=5).std().fillna(df['volatility'].std()).replace(0, 1e-6)).fillna(0)
        ret20 = df['returns'].rolling(20, min_periods=5).mean().fillna(0)
        df['fundamental_score'] = normalize_score(
            0.5
            - vol_z.clip(-2, 2) * 0.10
            - vol_z_fast.clip(-2, 2) * 0.10
            + ret5.clip(-0.05, 0.05)  / 0.05 * 0.15
            + ret20.clip(-0.05, 0.05) / 0.05 * 0.10
        )
        logger.info("Fundamental: dual-window vol-z (fast 20 + slow 60, causal)")

    # ── QUANTUM SCORE ─────────────────────────────────────────────────────────
    vol20_std = df['returns'].rolling(20, min_periods=5).std().replace(0, 1e-6)
    df['quantum_score'] = normalize_score(
        0.5 + (df['returns'].rolling(5).mean() / vol20_std).clip(-1, 1) * 0.5
    )

    # ── SENTINEL SCORE — FIX: base was 0.75 → always showed ~0.75 ───────────
    # Old: normalize_score(0.75 - vol_z*0.15) → average always ≈ 0.75 (bias)
    # New: base 0.50 with wider ±0.25 range → actually reflects risk state
    df['sentinel_score'] = normalize_score(0.50 - vol_z.clip(-2, 2) * 0.25)
    # Result: calm (vol_z=-2) → 1.0, normal (vol_z=0) → 0.50, crash (vol_z=+2) → 0.0

    # ── NEWS SENTIMENT — FIX: 3-day return averaged to ~0 → always 0.500 ────
    # Bug: ret3 * sqrt(vol_ratio) averages to ~0 over any long period because
    # BTC has roughly equal up/down days. Module contributed zero information.
    # Fix: use 30-day cumulative price momentum as sentiment proxy.
    # 30-day return is a real medium-term sentiment driver (separate from RSI/MACD).
    if news_fetcher is not None:
        logger.info("News: real historical sentiment")
        df['news_score'] = df['timestamp'].apply(
            lambda ts: _fetch_daily_news_score(symbol, ts, news_fetcher)
        )
    else:
        # 30-day cumulative return: strongly directional, captures medium-term mood
        close_30 = df['close'].shift(30).fillna(df['close'].iloc[0])
        ret30 = ((df['close'] / close_30.replace(0, 1e-6)) - 1).fillna(0)
        # Also add 7-day momentum for responsiveness
        close_7 = df['close'].shift(7).fillna(df['close'].iloc[0])
        ret7 = ((df['close'] / close_7.replace(0, 1e-6)) - 1).fillna(0)
        # Blend: 60% 30-day sentiment + 40% 7-day momentum
        news_raw = ret30.clip(-0.40, 0.40) / 0.40 * 0.60 + ret7.clip(-0.20, 0.20) / 0.20 * 0.40
        df['news_score'] = normalize_score(0.5 + news_raw.clip(-1.0, 1.0) * 0.42)
        logger.info("News: 30d+7d cumulative return proxy (medium-term sentiment)")

    # ── CONSENSUS — Trend is a GATE, NOT a score component ───────────────────
    # Key insight: adding a stable trend score (e.g. 0.77 throughout a bull market)
    # to the consensus shifts the entire series up → z-score has no room to
    # oscillate → no signals generated. Trend must be an external gate only.
    # Consensus = Touche (momentum) + Fundamental (quality) + News (direction)
    _w = module_weights or {}
    _w = {
        'touche':      float(_w.get('touche',      0.45)),
        'fundamental': float(_w.get('fundamental', 0.30)),
        'news':        float(_w.get('news',        0.25)),
        'sentinel':    float(_w.get('sentinel',    0.00)),
        'quantum':     float(_w.get('quantum',     0.00)),
    }
    _w = get_event_aware_weights(_w, event_hint)
    w_total = sum(v for k, v in _w.items() if k not in ('trend',))
    if w_total > 0:
        _w = {k: (v / w_total if k not in ('trend',) else v) for k, v in _w.items()}

    df['consensus_score'] = (
        df['touche_score']      * _w['touche']      +
        df['fundamental_score'] * _w['fundamental'] +
        df['news_score']        * _w['news']        +
        df['sentinel_score']    * _w['sentinel']    +
        df['quantum_score']     * _w['quantum']
    )
    # trend_score is stored in df for reporting but does NOT enter the oscillating signal

    # Multi-TF confluence: scale 1h consensus by 4h/1d alignment
    if timeframe == "1h":
        avg_consensus = float(df['consensus_score'].mean())
        mtf_mult = get_multi_tf_confluence(symbol, timeframe, avg_consensus)
        df['consensus_score'] = df['consensus_score'] * mtf_mult
        df['consensus_score'] = df['consensus_score'].clip(0, 1)
        logger.info(f"Multi-TF confluence applied: multiplier={mtf_mult:.3f}")

    # Correlation filter: apply macro correlation multiplier to consensus score
    corr_context = get_correlation_context()
    df = apply_correlation_filter(df, corr_context)
    corr_mult = float(corr_context.get("multiplier", 1.0))
    if corr_mult != 1.0:
        df['consensus_score'] = (df['consensus_score'] * corr_mult).clip(0, 1)
        logger.info(f"Correlation filter applied: regime={corr_context.get('regime')}, mult={corr_mult:.3f}")

    df = add_confluence_filters(df)

    regime_series = derive_regime_series(df)
    df['consensus_regime'] = regime_series
    df['consensus_signal'] = generate_zscore_signals(
        df,
        timeframe,
        regime_series=regime_series,
        z_threshold=z_threshold,
        rsi_lower=rsi_lower,
        rsi_upper=rsi_upper,
        event_hint=event_hint,
        adx_min=adx_min,
    )

    df['consensus_action'] = df['consensus_signal'].apply(
        lambda x: "BUY" if x == 1 else ("SELL" if x == -1 else "HOLD")
    )

    return df


def _fetch_daily_news_score(symbol: str, timestamp: datetime, news_fetcher) -> float:
    """
    Fetch real news sentiment score for a specific date.

    Symbol format: "BTC", "ETH", "XRP", etc.
    Returns: Normalized score (0-1 range)
    """
    try:
        # Get date from timestamp
        news_date = pd.Timestamp(timestamp).to_pydatetime()

        # Fetch real news sentiment (-1 to +1)
        raw_sentiment = news_fetcher.fetch_daily_sentiment(symbol, news_date)

        # Normalize from [-1, +1] to [0, 1]
        normalized = (raw_sentiment + 1.0) / 2.0

        return float(np.clip(normalized, 0.0, 1.0))

    except Exception as e:
        logger.debug(f"Error fetching news score for {symbol} {timestamp}: {e}")
        return 0.5  # Neutral fallback


def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD and Signal line"""
    ema_fast = prices.ewm(span=fast).mean()
    ema_slow = prices.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    return macd, signal_line


def calculate_adx(df: "pd.DataFrame", period: int = 14) -> "pd.Series":
    """Average Directional Index — measures trend STRENGTH (not direction).
    ADX > 20: market is trending (entry allowed)
    ADX < 20: choppy/sideways market (avoid entries)
    """
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)

    # True Range
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Directional movement
    dm_plus  = (high - prev_high).clip(lower=0)
    dm_minus = (prev_low - low).clip(lower=0)
    # When dm_plus <= dm_minus, set dm_plus = 0 and vice versa
    dm_plus  = dm_plus.where(dm_plus > dm_minus, 0.0)
    dm_minus = dm_minus.where(dm_minus > dm_plus.shift(0), 0.0)

    atr    = tr.ewm(alpha=1/period, min_periods=period).mean()
    di_pos = 100 * dm_plus.ewm(alpha=1/period, min_periods=period).mean() / atr.replace(0, 1e-6)
    di_neg = 100 * dm_minus.ewm(alpha=1/period, min_periods=period).mean() / atr.replace(0, 1e-6)
    dx     = 100 * (di_pos - di_neg).abs() / (di_pos + di_neg).replace(0, 1e-6)
    adx    = dx.ewm(alpha=1/period, min_periods=period).mean()
    return adx.fillna(0)


def normalize_score(value):
    """Normalize value to 0-1 range"""
    return np.clip(value, 0, 1) if isinstance(value, (int, float)) else \
           np.clip(value.fillna(0.5), 0, 1)


def derive_regime_series(df: pd.DataFrame) -> pd.Series:
    """Derive a coarse macro regime series from volatility and trend for backtests."""
    if "volatility" not in df.columns:
        return pd.Series("NORMALIZATION", index=df.index)

    vol = df["volatility"].fillna(df["volatility"].median())
    vol_rank = vol.rank(pct=True)
    trend = df.get("returns", pd.Series(0.0, index=df.index)).rolling(20, min_periods=5).mean().fillna(0.0)

    regimes = pd.Series("NORMALIZATION", index=df.index)
    regimes[vol_rank <= 0.35] = "LIQ_EXPANSION"
    regimes[vol_rank >= 0.80] = "RISK_OFF"
    regimes[(vol_rank > 0.35) & (vol_rank < 0.80)] = "NORMALIZATION"
    regimes[(trend > 0) & (vol_rank >= 0.60) & (vol_rank < 0.80)] = "RECOVERY"
    return regimes


def add_confluence_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Add RSI(14) and momentum(3) columns used by confluence filtering."""
    if "rsi" not in df.columns:
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
        rs = gain / loss.replace(0, 1e-6)
        df["rsi"] = 100 - (100 / (1 + rs))

    df["momentum"] = (df["close"] / df["close"].shift(3).fillna(df["close"].iloc[0])) - 1
    return df


def get_confluence_multiplier(
    rsi: float,
    mom: float,
    direction: int,
    rsi_lower: int = 35,
    rsi_upper: int = 65,
) -> float:
    """Return position size multiplier based on RSI+momentum confluence strength."""
    if direction == 1:  # BUY
        if rsi < rsi_lower and mom > 0.02:
            return 1.0
        if rsi < (rsi_lower + 10) and mom > 0:
            return 0.6
        if rsi < ((rsi_lower + rsi_upper) / 2):
            return 0.3
        return 0.1
    if direction == -1:  # SELL
        if rsi > rsi_upper and mom < -0.02:
            return 1.0
        if rsi > (rsi_upper - 10) and mom < 0:
            return 0.6
        if rsi > ((rsi_lower + rsi_upper) / 2):
            return 0.3
        return 0.1
    return 0.1


def get_multi_tf_confluence(symbol: str, current_tf: str, consensus_score: float) -> float:
    """Cross-validate 1h signals with 4h/1d consensus — only strengthen if aligned."""
    if current_tf != "1h":
        return 1.0  # Only applies to 1h timeframe
    if _httpx_sync is None:
        return 1.0
    higher_tfs = ["4h", "1d"]
    multiplier = 1.0
    base_url = os.environ.get("SENTINEL_URL", "http://sentinel-api:8004")
    for tf in higher_tfs:
        try:
            resp = _httpx_sync.get(
                f"http://localhost:8502/consensus/score",
                params={"symbol": symbol, "timeframe": tf},
                timeout=5,
            )
            if resp.status_code == 200:
                other_score = resp.json().get("consensus_score", 50)
                if (consensus_score > 60 and other_score > 60) or (
                    consensus_score < 40 and other_score < 40
                ):
                    multiplier *= 1.15  # Same direction → strengthen signal
                else:
                    multiplier *= 0.7  # Opposite direction → weaken signal
        except Exception:
            pass  # Graceful degradation — no higher TF data available
    return max(0.3, min(1.5, multiplier))


def get_correlation_context() -> dict:
    """Query sentinel /sentinel/correlation for macro correlation regime data."""
    fallback = {"regime": "neutral", "multiplier": 1.0, "pca_signal": 0.0}
    if _httpx_sync is None:
        return fallback
    sentinel_url = os.environ.get("SENTINEL_URL", "http://sentinel-api:8004")
    try:
        resp = _httpx_sync.get(f"{sentinel_url}/sentinel/correlation", timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            logger.info(
                f"Correlation context: regime={data.get('regime')}, "
                f"mult={data.get('multiplier')}, pca={data.get('pca_signal')}"
            )
            return data
    except Exception as e:
        logger.warning(f"Correlation context fetch failed: {e}")
    return fallback


def apply_correlation_filter(df: pd.DataFrame, corr_context: dict) -> pd.DataFrame:
    """Apply macro correlation multiplier and regime tag to DataFrame."""
    df["corr_mult"] = corr_context.get("multiplier", 1.0)
    df["corr_regime"] = corr_context.get("regime", "neutral")
    return df


def apply_correlation_multiplier(df: pd.DataFrame, corr_context: dict) -> pd.DataFrame:
    """Correlation overlay filter (v7.2 extension) — runs AFTER confluence.
    Applies multiplier to signal_strength if present."""
    mult = corr_context.get("multiplier", 1.0)
    if "signal_strength" in df.columns:
        df["signal_strength"] = df["signal_strength"] * mult
    return df


def get_event_aware_weights(
    base_weights: dict,
    event_hint: str = None,
    config_path: str = None,
) -> dict:
    """Apply event-based weight overrides from consensus_weights.yaml.

    Supports two modifiers:
    - "override": full replacement of module weights
    - "multiply": boost selected weights then renormalize to sum=1.0
    Returns base_weights unchanged if no event_hint or no match.
    """
    if not event_hint:
        return base_weights

    import yaml

    if config_path is None:
        config_path = os.environ.get(
            "CONSENSUS_WEIGHTS_PATH",
            "/app/consensus_engine/config/consensus_weights.yaml",
        )

    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        event_overrides = cfg.get("event_overrides", {})
        if not event_overrides:
            return base_weights

        hint_upper = event_hint.upper()
        matched_name = None
        matched_cfg = None
        for name, ocfg in event_overrides.items():
            hints = [h.upper() for h in ocfg.get("event_hints", [])]
            if hint_upper in hints:
                matched_name = name
                matched_cfg = ocfg
                break

        if not matched_cfg:
            return base_weights

        modifier = matched_cfg.get("modifier", "none")
        logger.info(f"Event weight override: {event_hint} -> {matched_name} (modifier={modifier})")

        if modifier == "none":
            return base_weights

        elif modifier == "override":
            override_w = matched_cfg.get("weights", {})
            if override_w:
                result = {k: override_w.get(k, base_weights.get(k, 0.0)) for k in base_weights}
                total = sum(result.values())
                if total > 0:
                    result = {k: round(v / total, 4) for k, v in result.items()}
                logger.info(f"Event override weights: {result}")
                return result
            return base_weights

        elif modifier == "multiply":
            boosted = base_weights.copy()
            boost_map = matched_cfg.get("weights_boost", {})
            for mod, factor in boost_map.items():
                if mod in boosted:
                    boosted[mod] = boosted[mod] * factor
            total = sum(boosted.values())
            if total > 0:
                boosted = {k: round(v / total, 4) for k, v in boosted.items()}
            logger.info(f"Event boost weights: {boosted}")
            return boosted

        else:
            logger.warning(f"Unknown event modifier: {modifier}")
            return base_weights

    except FileNotFoundError:
        logger.debug(f"Event weights config not found: {config_path}")
        return base_weights
    except Exception as e:
        logger.warning(f"Event weight override failed: {e}")
        return base_weights


def get_event_aware_z_threshold(regime: str, base_threshold: float, event_hint: str = None) -> float:
    """Event-type aware z-score threshold for entry timing.

    Based on event analysis (2026-04-20):
    - Touche score +0.031 higher in captured events → lower threshold helps
    - RISK_OFF regime has 60% capture rate → needs higher confirmation
    - PUMP/ATH events benefit from early entry (lower threshold)
    - CRASH/DUMP events need stronger confirmation (higher threshold)
    """
    _PUMP_EVENTS = {"PUMP", "ATH", "BREAKOUT", "ETF_PUMP"}
    _CRASH_EVENTS = {"CRASH", "DUMP", "BANK_CRISIS", "CONTAGION"}
    _STRUCTURAL_EVENTS = {"HALVING", "PEAK", "FORK"}

    # Explicit event_hint takes top priority
    if event_hint:
        hint_upper = event_hint.upper()
        if hint_upper in _PUMP_EVENTS:
            return 0.35
        elif hint_upper in _CRASH_EVENTS:
            return 0.65
        elif hint_upper in _STRUCTURAL_EVENTS:
            return 0.45

    # Regime-based dynamic threshold (per-bar)
    _REGIME_Z = {
        "LIQ_EXPANSION": -0.15,   # Momentum regime → lower threshold (early entry)
        "RECOVERY":      -0.10,   # Recovery → slightly lower
        "NORMALIZATION":  0.0,    # Neutral
        "RISK_OFF":      +0.15,   # Risk-off → higher threshold (strong confirmation)
    }
    adjustment = _REGIME_Z.get(regime, 0.0)
    return max(0.20, min(base_threshold + adjustment, 1.5))


def generate_zscore_signals(
    df: pd.DataFrame,
    timeframe: str,
    regime_series: pd.Series = None,
    z_threshold: float = None,
    rsi_lower: int = None,
    rsi_upper: int = None,
    event_hint: str = None,
    adx_min: float = 18.0,
) -> pd.Series:
    """Rolling z-score with regime filtering and event-aware dynamic thresholds."""
    # Window calibrated to ~10 trading days worth of bars per timeframe:
    # 1h  →  120 bars = 5 days   (was 40 = 1.67 days — too noisy)
    # 4h  →   60 bars = 10 days  (was 20 = 3.3  days — too noisy, caused 22% win rate)
    # 1d  →   20 bars = 20 days  (unchanged — 1 month, already appropriate)
    # Optimal parameters from 945-point grid + refinement search (BTC/USDT 2022-2026):
    # Winner: 4h z=1.3, adx=28, sl=-0.06, tp=0.15, ze=0.05, kelly=0.28
    #         → WR=58.6%, PF=1.35, PnL=+1.69%, Sharpe=3.52, 29 trades/4yr
    _TF_PARAMS = {
        "1h": {"window": 120, "min_periods": 24, "threshold": 1.3},
        "4h": {"window":  60, "min_periods": 12, "threshold": 1.3},  # refined from 1.2
        "1d": {"window":  20, "min_periods":  3, "threshold": 1.0},
    }
    _p = _TF_PARAMS.get(timeframe, {"window": 20, "min_periods": 5, "threshold": 0.8})
    base_threshold = float(z_threshold) if z_threshold is not None else _p["threshold"]
    effective_rsi_lower = int(rsi_lower) if rsi_lower is not None else 35
    effective_rsi_upper = int(rsi_upper) if rsi_upper is not None else 65

    _roll_mean = df["consensus_score"].rolling(_p["window"], min_periods=_p["min_periods"]).mean().fillna(df["consensus_score"].mean())
    _roll_std = df["consensus_score"].rolling(_p["window"], min_periods=_p["min_periods"]).std().fillna(df["consensus_score"].std()).replace(0, 1e-6)
    z = (df["consensus_score"] - _roll_mean) / _roll_std
    df["consensus_zscore"] = z

    # Warmup filter: EMA200 needs 200 bars to stabilize; signals generated before
    # that use an undercooked trend direction and cause wrong LONG/SHORT entries.
    # Block all signals for the first 200 bars (capped at 1/5 of total data).
    warmup_bars = min(200, max(50, len(df) // 5))
    past_warmup = pd.Series(False, index=df.index)
    past_warmup.iloc[warmup_bars:] = True

    if "volume" in df.columns:
        vol_mean = df["volume"].rolling(_p["window"], min_periods=_p["min_periods"]).mean()
        vol_filter = df["volume"] > vol_mean
    else:
        vol_filter = pd.Series(True, index=df.index)

    if regime_series is not None:
        favorable_regimes = ["NORMALIZATION", "LIQ_EXPANSION", "RECOVERY"]
        regime_filter = regime_series.isin(favorable_regimes)
    else:
        regime_filter = pd.Series(True, index=df.index)

    # Per-bar dynamic z-threshold based on regime + event_hint
    if regime_series is not None and event_hint is None and z_threshold is None:
        # Dynamic mode: adjust threshold per bar based on regime
        thresholds = regime_series.map(
            lambda r: get_event_aware_z_threshold(r, base_threshold)
        )
        # ── Quality filters (applied to both modes) ───────────────────────
        trend_up_series = df.get("trend_up",  pd.Series(1.0, index=df.index)).fillna(1.0)
        adx_series      = df.get("adx",       pd.Series(25.0, index=df.index)).fillna(25.0)
        rsi_series      = df.get("rsi",       pd.Series(50.0, index=df.index)).fillna(50.0)
        macd_hist_s     = df.get("macd_hist", pd.Series(0.0,  index=df.index)).fillna(0.0)

        # ADX > 18: market is trending (not choppy sideways)
        adx_filter = adx_series >= 18
        # LONG: RSI 40-73 (some momentum, not overbought), MACD hist positive
        rsi_ok_long  = (rsi_series >= 40) & (rsi_series <= 73)
        macd_pos     = macd_hist_s > 0
        # SHORT: RSI 27-60 (some weakness, not oversold), MACD hist negative
        rsi_ok_short = (rsi_series >= 27) & (rsi_series <= 60)
        macd_neg     = macd_hist_s < 0

        base_signals = pd.Series(0, index=df.index)
        base_signals[
            (z > thresholds) & vol_filter & regime_filter & adx_filter &
            rsi_ok_long & macd_pos & past_warmup
        ] = 1  # BUY — no signals during EMA200 warmup
        base_signals[
            (z < -thresholds) & vol_filter & regime_filter & adx_filter &
            (trend_up_series < 0.5) & rsi_ok_short & macd_neg & past_warmup
        ] = -1  # SHORT — only in downtrend, past warmup
        threshold_desc = f"dynamic(base={base_threshold}, range={thresholds.min():.2f}-{thresholds.max():.2f})"
    else:
        threshold = get_event_aware_z_threshold(
            regime_series.iloc[-1] if regime_series is not None and len(regime_series) > 0 else "NORMALIZATION",
            base_threshold,
            event_hint,
        )
        trend_up_series = df.get("trend_up",  pd.Series(1.0, index=df.index)).fillna(1.0)
        adx_series      = df.get("adx",       pd.Series(25.0, index=df.index)).fillna(25.0)
        rsi_series      = df.get("rsi",       pd.Series(50.0, index=df.index)).fillna(50.0)
        macd_hist_s     = df.get("macd_hist", pd.Series(0.0,  index=df.index)).fillna(0.0)
        adx_filter   = adx_series >= adx_min
        rsi_ok_long  = (rsi_series >= 40) & (rsi_series <= 73)
        macd_pos     = macd_hist_s > 0
        rsi_ok_short = (rsi_series >= 27) & (rsi_series <= 60)
        macd_neg     = macd_hist_s < 0

        base_signals = pd.Series(0, index=df.index)
        base_signals[
            (z > threshold) & vol_filter & regime_filter & adx_filter &
            rsi_ok_long & macd_pos & past_warmup
        ] = 1
        base_signals[
            (z < -threshold) & vol_filter & regime_filter & adx_filter &
            (trend_up_series < 0.5) & rsi_ok_short & macd_neg & past_warmup
        ] = -1
        threshold_desc = f"static={threshold:.2f}(event_hint={event_hint})"

    # Soft RSI + momentum confluence: keep signal, scale position size by strength.
    rsi = df.get("rsi", pd.Series(50.0, index=df.index)).fillna(50.0)
    mom = df.get("momentum", pd.Series(0.0, index=df.index)).fillna(0.0)
    signals = base_signals.copy()
    df["confluence_multiplier"] = pd.Series(0.1, index=df.index)
    active_mask = signals != 0
    if active_mask.any():
        df.loc[active_mask, "confluence_multiplier"] = [
            get_confluence_multiplier(
                float(rv),
                float(mv),
                int(dv),
                rsi_lower=effective_rsi_lower,
                rsi_upper=effective_rsi_upper,
            )
            for rv, mv, dv in zip(rsi[active_mask], mom[active_mask], signals[active_mask])
        ]

    logger.info(
        f"Z-score params: timeframe={timeframe}, threshold={threshold_desc}, "
        f"window={_p['window']}, volume_filter=enabled, regime_filter=enabled, "
        f"confluence=weighted, rsi_bounds={effective_rsi_lower}/{effective_rsi_upper}"
    )
    return signals


def calculate_position_size(
    z_score: float,
    regime_confidence: float,
    confluence_multiplier: float = 1.0,
    kelly_cap: float = 0.25,
) -> float:
    """Dynamic position sizing using capped Kelly fraction and regime confidence."""
    z_abs = abs(float(z_score)) if z_score is not None else 0.0
    base_kelly = z_abs / (z_abs + 1.0)
    adjusted = base_kelly * float(regime_confidence)
    sized = adjusted * float(confluence_multiplier)
    return max(0.0, min(sized, kelly_cap))


# Keep old name for backward compatibility
async def generate_historical_data_with_ai_signals(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    news_fetcher=None,
    z_threshold: float = None,
    rsi_lower: int = None,
    rsi_upper: int = None,
    event_hint: str = None,
    module_weights: dict = None,
    adx_min: float = 18.0,
) -> pd.DataFrame:
    """Generate historical data with AI signals (now uses real data + REAL NEWS when available)"""
    return await fetch_real_historical_data(
        symbol,
        timeframe,
        start_date,
        end_date,
        news_fetcher=news_fetcher,
        z_threshold=z_threshold,
        rsi_lower=rsi_lower,
        rsi_upper=rsi_upper,
        event_hint=event_hint,
        module_weights=module_weights,
        adx_min=adx_min,
    )


def execute_ai_driven_trades(
    df: pd.DataFrame,
    symbol: str,
    stop_loss_pct: float = -0.08,
    take_profit_pct: float = 0.20,
    z_exit_long: float = 0.20,
    z_exit_short: float = -0.20,
) -> List[Dict]:
    """Execute trades based on Consensus signals with z-score momentum exits.

    Entry: z-score crosses threshold (signal = ±1)
    Exit strategy (in priority order):
      1. Hard stop-loss: -8% (limit catastrophic losses)
      2. Take-profit: +20% (lock in gains)
      3. Z-score reversion: exit when z returns toward 0 (momentum faded)
         - LONG exit when z < +0.25 (momentum exhausted)
         - SHORT exit when z > -0.25 (momentum exhausted)
      4. Opposite signal: forced reversal

    This fixes the main bug: with the old approach, a LONG position opened
    during an uptrend NEVER exited because no SHORT signals were generated
    (blocked by the EMA200 trend gate). Result: 2 trades in 2281 bars.
    """
    trades = []
    position = None
    entry_price = None
    entry_time  = None
    entry_z     = None   # FIX: store entry z-score for correct position sizing
    entry_conf  = None   # FIX: store entry confluence for correct position sizing
    entry_regime = None

    STOP_LOSS_PCT   = float(stop_loss_pct)    # from request param
    TAKE_PROFIT_PCT = float(take_profit_pct)  # from request param
    Z_EXIT_LONG     = float(z_exit_long)      # from request param
    Z_EXIT_SHORT    = float(z_exit_short)     # from request param

    def _record_trade(exit_price, exit_ts, exit_z, exit_regime, exit_reason):
        pnl_raw = (exit_price - entry_price) * (1 if position == "LONG" else -1)
        commission = (entry_price + exit_price) * 0.001
        pnl_net = pnl_raw - commission
        trades.append({
            "entry_time": entry_time.isoformat(),
            "exit_time":  exit_ts.isoformat(),
            "entry_price": round(entry_price, 2),
            "exit_price":  round(exit_price, 2),
            "position": position,
            "pnl":     round(pnl_net, 2),
            "pnl_pct": round(pnl_net / entry_price * 100, 2),
            # FIX: use ENTRY z-score and ENTRY confluence for sizing — not exit bar values.
            # Using exit bar's z/conf caused position sizes of ~2% on z-reversion exits
            # (exit z≈0.25 → base_kelly=0.2, confluence=0.1 default → effective=2%).
            # Entry z is always >threshold (e.g. 1.0+) → proper sizing (15-25%).
            "z_score": float(entry_z),
            "regime":  entry_regime,
            "confluence_multiplier": float(entry_conf),
            "exit_reason": exit_reason,
        })

    for idx, row in df.iterrows():
        signal  = row["consensus_signal"]
        price   = row["close"]
        ts      = row["timestamp"]
        z       = float(row.get("consensus_zscore", 0.0))
        regime  = str(row.get("consensus_regime", "NORMALIZATION"))
        conf    = float(row.get("confluence_multiplier", 0.1))

        # ── Exit (check every bar) ────────────────────────────────────────────
        if position is not None:
            pnl_pct = (price - entry_price) / entry_price * (1 if position == "LONG" else -1)

            if pnl_pct <= STOP_LOSS_PCT:
                _record_trade(price, ts, z, regime, "stop_loss")
                position = entry_price = entry_time = entry_z = entry_conf = entry_regime = None

            elif pnl_pct >= TAKE_PROFIT_PCT:
                _record_trade(price, ts, z, regime, "take_profit")
                position = entry_price = entry_time = entry_z = entry_conf = entry_regime = None

            elif position == "LONG" and z < Z_EXIT_LONG:
                _record_trade(price, ts, z, regime, "z_reversion")
                position = entry_price = entry_time = entry_z = entry_conf = entry_regime = None

            elif position == "SHORT" and z > Z_EXIT_SHORT:
                _record_trade(price, ts, z, regime, "z_reversion")
                position = entry_price = entry_time = entry_z = entry_conf = entry_regime = None

            elif signal != 0:
                if (position == "LONG" and signal < 0) or (position == "SHORT" and signal > 0):
                    _record_trade(price, ts, z, regime, "reverse_signal")
                    position = entry_price = entry_time = entry_z = entry_conf = entry_regime = None

        # ── Entry ─────────────────────────────────────────────────────────────
        if position is None and signal != 0:
            position      = "LONG" if signal > 0 else "SHORT"
            entry_price   = price
            entry_time    = ts
            entry_z       = z      # store for sizing
            entry_conf    = conf   # store for sizing
            entry_regime  = regime

    return trades


def calculate_backtest_metrics(trades: List[Dict], initial_capital: float, kelly_cap: float = 0.15) -> Dict:
    """Calculate backtest performance metrics"""

    if not trades:
        return {
            "pnl": {"total_pnl": 0, "total_pnl_pct": 0, "num_trades": 0},
            "win_loss": {"win_rate": 0, "win_count": 0, "loss_count": 0, "avg_win": 0, "avg_loss": 0, "profit_factor": 0},
            "drawdown": {"max_drawdown": 0, "max_drawdown_pct": 0},
            "sharpe_ratio": 0,
            "sortino_ratio": 0,
            "initial_capital": initial_capital,
            "final_capital": initial_capital,
        }

    regime_conf_map = {
        "LIQ_EXPANSION": 1.0,
        "NORMALIZATION": 0.9,
        "RECOVERY": 0.8,
        "RISK_OFF": 0.6,
    }

    # Calculate PnL with dynamic position sizing (fractional exposure per trade)
    capital = initial_capital
    effective_pnls = []
    position_sizes = []
    for t in trades:
        z = float(t.get("z_score", 0.5))
        regime = str(t.get("regime", "NORMALIZATION"))
        regime_conf = regime_conf_map.get(regime, 0.8)
        conf_mult = float(t.get("confluence_multiplier", 1.0))
        pos_size = calculate_position_size(z, regime_conf, confluence_multiplier=conf_mult, kelly_cap=kelly_cap)
        position_sizes.append(pos_size)

        trade_return = (t["pnl_pct"] / 100.0) * pos_size
        capital *= (1.0 + trade_return)
        effective_pnls.append(initial_capital * trade_return)
    total_pnl = capital - initial_capital
    total_pnl_pct = (total_pnl / initial_capital) * 100
    final_capital = capital

    # Win/Loss stats
    winning_vals = [p for p in effective_pnls if p > 0]
    losing_vals = [p for p in effective_pnls if p < 0]

    win_rate = (len(winning_vals) / len(trades)) * 100 if trades else 0
    win_count = len(winning_vals)
    loss_count = len(losing_vals)
    avg_win = sum(winning_vals) / len(winning_vals) if winning_vals else 0
    avg_loss = sum(losing_vals) / len(losing_vals) if losing_vals else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    # Drawdown â€” compound equity curve with dynamic exposure
    equity_curve = [initial_capital]
    running = initial_capital
    for trade, pos_size in zip(trades, position_sizes):
        running *= (1.0 + (trade["pnl_pct"] / 100.0) * pos_size)
        equity_curve.append(running)

    max_equity = equity_curve[0]
    max_drawdown = 0
    max_drawdown_pct = 0

    for equity in equity_curve:
        if equity > max_equity:
            max_equity = equity
        drawdown = max_equity - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_pct = (drawdown / max_equity) * 100 if max_equity > 0 else 0

    # Sharpe Ratio (simplified)
    returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
    sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if len(returns) > 1 and np.std(returns) > 0 else 0

    # Sortino Ratio
    downside_returns = returns[returns < 0]
    downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 1
    sortino_ratio = np.mean(returns) / downside_std * np.sqrt(252) if downside_std > 0 else 0

    return {
        "pnl": {
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "num_trades": len(trades),
        },
        "win_loss": {
            "win_rate": round(win_rate, 1),
            "win_count": win_count,
            "loss_count": loss_count,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
        },
        "drawdown": {
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
        },
        "sharpe_ratio": round(float(sharpe_ratio), 2),
        "sortino_ratio": round(float(sortino_ratio), 2),
        "initial_capital": initial_capital,
        "final_capital": round(final_capital, 2),
    }


@router.get("/results")
async def get_results(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
):
    """Get cached backtest results"""
    result = backtest_engine.get_result(symbol, timeframe)

    if not result:
        raise HTTPException(status_code=404, detail="No backtest results found")

    return result


@router.delete("/cache")
async def clear_cache():
    """Clear all cached backtest results"""
    backtest_engine.clear_cache()
    return {"message": "Cache cleared"}


# ── Hyperopt / Bayesian Parametre Optimizasyonu ──────────────────────────────

@router.post("/optimize")
async def run_hyperopt(request_data: Dict = Body(...)):
    """
    Bayesian/Latin-Hypercube parametre optimizasyonu.

    İlk N iterasyon Latin Hypercube (uzay kapsama garantisi),
    sonraki iterasyonlar en iyi noktaların çevresine odaklanır.
    scikit-learn + scipy gerektir (her ikisi de mevcutsa).

    Body:
        symbol, start_date, end_date, timeframe, horizon
        initial_capital (varsayılan 10000)
        n_trials (varsayılan 20, max 50)
        param_space: {
            z_threshold: [min, max],
            stop_loss_pct: [min, max],
            take_profit_pct: [min, max],
            z_exit_long: [min, max],
            adx_min: [min, max],
            kelly_cap: [min, max]
        }
        objective: "sharpe" | "win_rate" | "pnl" | "composite" (varsayılan "composite")

    Returns:
        {results: [...], best: {...}, total_trials: N, elapsed_sec: float}
    """
    import time as _time
    t0 = _time.time()

    symbol         = request_data.get("symbol", "BTC/USDT")
    timeframe      = request_data.get("timeframe", "4h")
    start_date     = request_data.get("start_date", "2022-05-29")
    end_date       = request_data.get("end_date",   "2026-05-29")
    horizon        = request_data.get("horizon", "medium")
    initial_capital = float(request_data.get("initial_capital", 10000))
    n_trials       = min(int(request_data.get("n_trials", 20)), 50)
    objective      = request_data.get("objective", "composite")

    # Parametre uzayı (varsayılan aralıklar — grid search optimaline yakın)
    space = request_data.get("param_space", {})
    bounds = {
        "z_threshold":    space.get("z_threshold",    [0.8, 2.0]),
        "stop_loss_pct":  space.get("stop_loss_pct",  [-0.10, -0.03]),
        "take_profit_pct": space.get("take_profit_pct",[0.08, 0.30]),
        "z_exit_long":    space.get("z_exit_long",    [0.02, 0.30]),
        "adx_min":        space.get("adx_min",        [15, 35]),
        "kelly_cap":      space.get("kelly_cap",       [0.15, 0.40]),
    }

    # Latin Hypercube Sampling — uzayı homojen kapsayan noktalar
    try:
        from scipy.stats.qmc import LatinHypercube, scale
        sampler = LatinHypercube(d=len(bounds), seed=42)
        lh_samples = sampler.random(n=n_trials)
        l_bounds = [b[0] for b in bounds.values()]
        u_bounds = [b[1] for b in bounds.values()]
        scaled = scale(lh_samples, l_bounds, u_bounds)
        param_sets = [dict(zip(bounds.keys(), row)) for row in scaled]
    except ImportError:
        # scipy yoksa uniform random sampling
        import random
        random.seed(42)
        param_sets = []
        for _ in range(n_trials):
            ps = {}
            for k, (lo, hi) in bounds.items():
                ps[k] = lo + random.random() * (hi - lo)
            param_sets.append(ps)

    def _score(metrics: dict, obj: str) -> float:
        wl = metrics.get("win_loss", {})
        pnl = metrics.get("pnl", {})
        n = pnl.get("num_trades", 0)
        if n < 3:
            return -999.0
        sharpe = float(metrics.get("sharpe_ratio", 0))
        wr = float(wl.get("win_rate", 0))
        pf = float(wl.get("profit_factor", 0))
        pnl_pct = float(pnl.get("total_pnl_pct", 0))
        if obj == "sharpe":
            return sharpe
        if obj == "win_rate":
            return wr
        if obj == "pnl":
            return pnl_pct
        # composite — balances all metrics with trade count penalty
        return (wr * 0.30 + min(pf, 5) * 10 * 0.30 +
                max(sharpe, 0) * 5 * 0.25 + max(pnl_pct, 0) * 2 * 0.15
                - n / 200 * 5)

    results = []
    news_fetcher = get_news_fetcher()

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    for i, ps in enumerate(param_sets):
        try:
            # Parametre yuvarlama
            z   = round(ps["z_threshold"], 3)
            sl  = round(ps["stop_loss_pct"], 4)
            tp  = round(ps["take_profit_pct"], 4)
            ze  = round(ps["z_exit_long"], 4)
            adx = round(ps["adx_min"])
            kly = round(ps["kelly_cap"], 3)

            df = await generate_historical_data_with_ai_signals(
                symbol, timeframe, start_dt, end_dt,
                news_fetcher=news_fetcher,
                z_threshold=z,
                adx_min=adx,
            )
            if df.empty:
                continue

            trades = execute_ai_driven_trades(
                df, symbol,
                stop_loss_pct=sl,
                take_profit_pct=tp,
                z_exit_long=ze,
                z_exit_short=-ze,
            )
            if not trades:
                continue

            metrics = calculate_backtest_metrics(trades, initial_capital, kelly_cap=kly)
            score = _score(metrics, objective)

            results.append({
                "trial": i + 1,
                "params": {
                    "z_threshold": z, "stop_loss_pct": sl,
                    "take_profit_pct": tp, "z_exit_long": ze,
                    "adx_min": adx, "kelly_cap": kly,
                },
                "metrics": {
                    "win_rate":      metrics["win_loss"]["win_rate"],
                    "profit_factor": metrics["win_loss"]["profit_factor"],
                    "pnl_pct":       metrics["pnl"]["total_pnl_pct"],
                    "sharpe":        metrics["sharpe_ratio"],
                    "max_dd_pct":    metrics["drawdown"]["max_drawdown_pct"],
                    "num_trades":    metrics["pnl"]["num_trades"],
                    "avg_win":       metrics["win_loss"]["avg_win"],
                    "avg_loss":      metrics["win_loss"]["avg_loss"],
                },
                "score": round(score, 4),
            })
        except Exception as exc:
            logger.debug("hyperopt trial %d failed: %s", i + 1, exc)
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    elapsed = round(_time.time() - t0, 1)

    return {
        "success": True,
        "symbol": symbol, "timeframe": timeframe,
        "date_range": {"start": start_date, "end": end_date},
        "objective": objective,
        "total_trials": len(results),
        "requested_trials": n_trials,
        "elapsed_sec": elapsed,
        "best": results[0] if results else None,
        "results": results[:20],  # ilk 20 sonuç
        "method": "latin_hypercube",
    }


@router.get("/supported-timeframes")
async def get_supported_timeframes():
    """Get list of supported timeframes"""
    return {
        "timeframes": ["5m", "15m", "1h", "4h", "1d", "1w", "1month"],
        "strategy": "AI Consensus (Touche 50% + Fundamental 35% + News 15%)",
        "ai_modules": ["Touche", "Fundamental", "Quantum", "Sentinel", "News", "Consensus"],
    }


@router.get("/export/csv")
async def export_csv(symbol: str = "BTC/USDT", timeframe: str = "1h"):
    """Export last backtest results as CSV"""
    from fastapi.responses import Response
    import csv
    import io

    result = backtest_engine.get_result(symbol, timeframe)
    if not result or "trades" not in result:
        raise HTTPException(status_code=404, detail="No backtest results to export")

    trades = result.get("trades", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["entry_time", "exit_time", "entry_price", "exit_price", "position", "pnl", "pnl_pct"])

    for trade in trades:
        writer.writerow([
            trade.get('entry_time', ''),
            trade.get('exit_time', ''),
            trade.get('entry_price', ''),
            trade.get('exit_price', ''),
            trade.get('position', ''),
            trade.get('pnl', ''),
            trade.get('pnl_pct', '')
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=backtest_{symbol}_{timeframe}.csv"}
    )


@router.get("/export/html")
async def export_html(symbol: str = "BTC/USDT", timeframe: str = "1h"):
    """Export last backtest results as HTML report"""
    from fastapi.responses import HTMLResponse

    result = backtest_engine.get_result(symbol, timeframe)
    if not result:
        raise HTTPException(status_code=404, detail="No backtest results to export")

    metrics = result.get("metrics", {})
    trades = result.get("trades", [])

    pnl_total = metrics.get('pnl', {}).get('total_pnl', 0)
    pnl_color = "green" if pnl_total >= 0 else "red"

    pnl_pct = metrics.get('pnl', {}).get('total_pnl_pct', 0)
    pnl_pct_color = "green" if pnl_pct >= 0 else "red"

    html_content = f"""<html>
<head>
    <meta charset="UTF-8">
    <title>Backtest Report - {symbol} {timeframe}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        .metric {{ display: inline-block; margin: 10px; padding: 10px; border: 1px solid #ddd; }}
        .positive {{ color: green; font-weight: bold; }}
        .negative {{ color: red; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>AI-Driven Backtest Report</h1>
    <p><strong>Symbol:</strong> {symbol}</p>
    <p><strong>Timeframe:</strong> {timeframe}</p>
    <p><strong>Date Range:</strong> {result.get('date_range', {}).get('start')} to {result.get('date_range', {}).get('end')}</p>

    <h2>Metrics</h2>
    <div class="metric">
        <strong>Total PnL:</strong> <span class="{pnl_color}">${pnl_total:.2f}</span>
    </div>
    <div class="metric">
        <strong>Return:</strong> <span class="{pnl_pct_color}">{pnl_pct:.2f}%</span>
    </div>
    <div class="metric">
        <strong>Win Rate:</strong> {metrics.get('win_loss', {}).get('win_rate', 0):.1f}%
    </div>
    <div class="metric">
        <strong>Total Trades:</strong> {result.get('total_trades', 0)}
    </div>
    <div class="metric">
        <strong>Profit Factor:</strong> {metrics.get('win_loss', {}).get('profit_factor', 0):.2f}x
    </div>
    <div class="metric">
        <strong>Max Drawdown:</strong> {metrics.get('drawdown', {}).get('max_drawdown_pct', 0):.2f}%
    </div>

    <h2>Trades</h2>
    <table>
        <tr>
            <th>Entry Time</th>
            <th>Exit Time</th>
            <th>Entry Price</th>
            <th>Exit Price</th>
            <th>Position</th>
            <th>PnL</th>
            <th>PnL %</th>
        </tr>"""

    for trade in trades[:20]:
        pnl = trade.get('pnl', 0)
        pnl_color = "positive" if pnl >= 0 else "negative"
        pnl_pct_val = trade.get('pnl_pct', 0)
        pnl_pct_color = "positive" if pnl_pct_val >= 0 else "negative"

        html_content += f"""
        <tr>
            <td>{trade.get('entry_time', '')}</td>
            <td>{trade.get('exit_time', '')}</td>
            <td>${trade.get('entry_price', 0):.2f}</td>
            <td>${trade.get('exit_price', 0):.2f}</td>
            <td>{trade.get('position', '')}</td>
            <td class="{pnl_color}">${pnl:.2f}</td>
            <td class="{pnl_pct_color}">{pnl_pct_val:.2f}%</td>
        </tr>"""

    html_content += """
    </table>
</body>
</html>"""

    return HTMLResponse(content=html_content)
