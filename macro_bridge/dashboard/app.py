import plotly.graph_objects as go
import streamlit as st

import os
import sys

macro_bridge_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
workspace_root = os.path.dirname(macro_bridge_root)
sys.path.insert(0, workspace_root)
sys.path.insert(0, macro_bridge_root)
from run import run_pipeline


REGIME_COLOR = {
    "liquidity_expansion": "#16a34a",
    "risk_off": "#dc2626",
    "stagflation": "#b45309",
    "normalization": "#2563eb",
}


def _gauge(value_0_to_100: float) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value_0_to_100,
            title={"text": "Macro Score"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#0f172a"},
                "steps": [
                    {"range": [0, 35], "color": "#fee2e2"},
                    {"range": [35, 65], "color": "#fef9c3"},
                    {"range": [65, 100], "color": "#dcfce7"},
                ],
            },
        )
    )
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=20))
    return fig


def main() -> None:
    st.set_page_config(page_title="AEGIS Macro Bridge", layout="wide")
    st.title("AEGIS Macro Bridge")

    symbol = st.sidebar.text_input("Symbol", value="BTCUSDT")
    timeframe = st.sidebar.selectbox("Timeframe", options=["15m", "1h", "4h", "1d"], index=1)
    entry_price = st.sidebar.number_input("Entry Price", value=65000.0, min_value=1.0)
    atr = st.sidebar.number_input("ATR", value=1200.0, min_value=0.1)

    payload = run_pipeline(symbol=symbol, timeframe=timeframe, entry_price=entry_price, atr=atr)
    regime = payload["regime"]
    score = payload["macro_score"]
    score_100 = (score + 1.0) * 50.0

    col1, col2, col3 = st.columns([1.2, 1, 1])
    with col1:
        st.markdown(
            f"""
            <div style='padding:16px;border-radius:12px;background:{REGIME_COLOR.get(regime, "#64748b")};color:white;'>
                <h3 style='margin:0;'>Rejim</h3>
                <p style='font-size:24px;margin:8px 0 0 0;'>{regime}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.plotly_chart(_gauge(score_100), use_container_width=True)

    with col2:
        st.subheader("AEGIS Karari")
        st.write(payload["decision"])
        st.subheader("Birlesik Karar")
        st.write(payload["validated"]["combined_decision"])
        st.caption(payload["validated"]["reason"])

    with col3:
        st.subheader("Trade Parametreleri")
        st.metric("Pozisyon Buyuklugu", f"{payload['position_size']:.4f}")
        st.metric("Stop Loss", f"{payload['stop_loss']:.2f}")
        st.metric("Hedge Uyarisi", "EVET" if payload["hedge"] else "HAYIR")

    st.subheader("Asset Allocation Onerisi")
    allocation_rows = [
        {"Varlik": "Altin", "Yuzde": round(payload["asset_allocation"]["gold"] * 100, 2)},
        {"Varlik": "BTC", "Yuzde": round(payload["asset_allocation"]["btc"] * 100, 2)},
        {"Varlik": "Tahvil", "Yuzde": round(payload["asset_allocation"]["bond"] * 100, 2)},
        {"Varlik": "Emtia", "Yuzde": round(payload["asset_allocation"]["commodity"] * 100, 2)},
        {"Varlik": "Nakit", "Yuzde": round(payload["asset_allocation"]["cash"] * 100, 2)},
    ]
    st.table(allocation_rows)

    st.subheader("Rebalance Sinyali")
    if payload["rebalance_signal"]["rebalance_required"]:
        st.warning(f"Rebalance gerekli. Maksimum sapma: %{payload['rebalance_signal']['max_deviation'] * 100:.2f}")
        st.table(payload["rebalance_signal"]["actions"])
    else:
        st.success("Portfoy hedef dagilima yakin. Rebalance gerekmiyor.")

    st.subheader("Ham Girdiler")
    st.json(payload["inputs"])


if __name__ == "__main__":
    main()
