"""
AEGIS v7.2 — Macro Correlation Engine

Rolling correlation, lead-lag analysis, and PCA-based regime detection
between BTC and 23 macro/crypto instruments.
"""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# 23 instrument universe — extensible
MACRO_SYMBOLS = [
    "BTCUSD", "BTC.D", "TOTAL", "TOTAL2",
    "DXY", "XAUUSD", "XAGUSD", "XAUXAG",
    "BRENT", "US02Y", "US10Y", "US20Y",
    "USCPI", "USPPI", "M2SL",
    "SP500", "NASDAQ", "QQQ", "FXI",
    "HYG", "JNK", "000001", "BTCXAU",
]

RISK_ASSETS = ["SP500", "NASDAQ", "QQQ", "HYG", "JNK", "FXI"]
DEFENSIVE_ASSETS = ["DXY", "US10Y", "US02Y", "XAUUSD", "XAGUSD"]


class CorrelationEngine:
    """Rolling correlation + lead-lag + PCA regime detection for BTC macro overlay"""

    def __init__(self, window: int = 30, min_periods: int = 20):
        self.window = window
        self.min_periods = min_periods

    def analyze(self, price_df: pd.DataFrame) -> dict:
        """Rolling correlation, lead-lag & PCA regime detection.

        Input: DataFrame with columns ⊆ MACRO_SYMBOLS, index=datetime, values=daily close
        Output: regime, multiplier, lead_lag, pca_signal for consensus overlay
        """
        fallback = {
            "regime": "unknown",
            "multiplier": 1.0,
            "lead_lag": {},
            "pca_signal": 0.0,
            "btc_risk_corr": 0.0,
            "btc_def_corr": 0.0,
            "variance_explained": [],
        }

        available = [s for s in MACRO_SYMBOLS if s in price_df.columns]
        if price_df.empty or len(price_df) < self.min_periods or "BTCUSD" not in available:
            return fallback

        returns = price_df[available].pct_change().dropna()
        if len(returns) < self.min_periods:
            return fallback

        # BTC vs Risk / Defensive averages (latest window)
        risk_in_df = [s for s in RISK_ASSETS if s in returns.columns]
        def_in_df = [s for s in DEFENSIVE_ASSETS if s in returns.columns]

        tail = returns.iloc[-self.window:]
        btc_risk = float(np.mean([tail["BTCUSD"].corr(tail[s]) for s in risk_in_df])) if risk_in_df else 0.0
        btc_def = float(np.mean([tail["BTCUSD"].corr(tail[s]) for s in def_in_df])) if def_in_df else 0.0

        # Lead-Lag (-5 to +5 days)
        lead_lag = {}
        for s in risk_in_df + def_in_df:
            lags = list(range(-5, 6))
            corrs = [returns[s].shift(l).corr(returns["BTCUSD"]) for l in lags]
            safe_corrs = [c if not np.isnan(c) else 0.0 for c in corrs]
            best_idx = int(np.argmax(np.abs(safe_corrs)))
            best_lag = lags[best_idx]
            lead_lag[s] = {
                "corr": round(float(max(safe_corrs, key=abs)), 3),
                "lag_days": best_lag,
                "leads": best_lag < 0,
            }

        # PCA Regime Signal
        pca_signal = 0.0
        variance_explained = []
        clean = returns.dropna(axis=1, how="all").dropna()
        if clean.shape[1] >= 2 and len(clean) >= self.window:
            try:
                from sklearn.decomposition import PCA
                pca_data = clean.iloc[-self.window:]
                n_comp = min(2, pca_data.shape[1])
                pca = PCA(n_components=n_comp)
                components = pca.fit_transform(pca_data)
                pca_signal = float(components[-1, 0])
                variance_explained = [round(float(v), 3) for v in pca.explained_variance_ratio_]
            except Exception as e:
                logger.warning(f"PCA failed: {e}")

        # Regime & Multiplier Logic (overlay on top of existing Sentinel regime)
        if btc_risk > 0.7 and btc_def < -0.4:
            regime, mult = "risk_on", 1.0
        elif btc_risk < 0.3 and btc_def > 0.2:
            regime, mult = "decoupling", 0.65
        elif pca_signal < -1.5:
            regime, mult = "stress", 0.45
        else:
            regime, mult = "neutral", 0.85

        logger.info(
            f"CorrelationEngine: regime={regime}, btc_risk={btc_risk:.2f}, "
            f"btc_def={btc_def:.2f}, pca={pca_signal:.2f}, mult={mult}"
        )
        return {
            "regime": regime,
            "multiplier": round(mult, 3),
            "lead_lag": lead_lag,
            "pca_signal": round(pca_signal, 4),
            "btc_risk_corr": round(btc_risk, 4),
            "btc_def_corr": round(btc_def, 4),
            "variance_explained": variance_explained,
        }
