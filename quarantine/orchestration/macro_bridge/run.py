from typing import Any, Dict, Optional

from macro_bridge.aegis.client import get_cbr_decision, get_consensus
from macro_bridge.aegis.validator import validate_signal
from macro_bridge.data.fetcher import DataFetcher
from macro_bridge.executor.trade_executor import calculate_asset_allocation, calculate_position_size, calculate_stop_loss, check_hedge, generate_rebalance_signal
from macro_bridge.macro.regime import detect_regime
from macro_bridge.macro.scorer import calculate_score
from macro_bridge.utils.logging_config import configure_logging


def run_pipeline(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    entry_price: float = 65000.0,
    atr: float = 1200.0,
    confidence: float = 0.65,
    fingerprint: Optional[str] = None,
    current_allocation: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    fetcher = DataFetcher()

    dxy = fetcher.get_dxy()
    us10y = fetcher.get_us10y()
    vix = fetcher.get_vix()
    brent = fetcher.get_brent()
    xau = fetcher.get_xau()
    btc_d = fetcher.get_btc_dominance()
    usdt_d = fetcher.get_usdt_dominance()
    hg = fetcher.get_hg()

    regime = detect_regime(dxy=dxy, us10y=us10y, vix=vix, brent=brent, xau=xau)
    macro_score = calculate_score(dxy=dxy, us10y=us10y, btc_d=btc_d, usdt_d=usdt_d, hg=hg, vix=vix)

    consensus = get_consensus(symbol=symbol, timeframe=timeframe)
    cbr = get_cbr_decision(fingerprint=fingerprint or f"{symbol}:{timeframe}:{regime}")

    # Prefer consensus decision, fallback to CBR.
    decision = str(consensus.get("decision", cbr.get("decision", "HOLD"))).upper()
    signal_validation = validate_signal(macro_score=macro_score, aegis_decision=decision)

    size = calculate_position_size(
        regime=regime,
        macro_score=macro_score,
        confidence=float(consensus.get("confidence", confidence)),
    ) * signal_validation["position_multiplier"]

    stop_loss = calculate_stop_loss(regime=regime, entry_price=entry_price, atr=atr)
    hedge = check_hedge(vix=vix, dxy=dxy, us10y=us10y)
    asset_allocation = calculate_asset_allocation(regime=regime, macro_score=macro_score, hedge=hedge)
    rebalance_signal = generate_rebalance_signal(asset_allocation, current_allocation=current_allocation, threshold=0.05)

    return {
        "inputs": {
            "dxy": dxy,
            "us10y": us10y,
            "vix": vix,
            "brent": brent,
            "xau": xau,
            "btc_d": btc_d,
            "usdt_d": usdt_d,
            "hg": hg,
        },
        "regime": regime,
        "macro_score": round(macro_score, 4),
        "consensus": consensus,
        "cbr": cbr,
        "decision": decision,
        "validated": signal_validation,
        "position_size": round(size, 4),
        "asset_allocation": asset_allocation,
        "rebalance_signal": rebalance_signal,
        "stop_loss": stop_loss,
        "hedge": hedge,
    }


def main() -> None:
    configure_logging()
    payload = run_pipeline()
    print(payload)


if __name__ == "__main__":
    main()
