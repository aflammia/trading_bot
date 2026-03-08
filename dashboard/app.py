"""
Chuky Bot — Algorithmic Trading Platform
Main Streamlit Application

Run: streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

import streamlit as st

# Ensure project root is importable
ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Page config MUST be first Streamlit command
st.set_page_config(
    page_title="Chuky Bot | Trading Platform",
    page_icon=":material/monitoring:",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.theme import inject_css
from dashboard.views import (
    page_overview,
    page_backtest,
    page_price_chart,
    page_trades,
    page_risk,
    page_validation,
    page_configurator,
    page_ai_chat,
    page_reports,
)

inject_css()

# ── Navigation — Professional layout with Material icons ────────
pages = [
    st.Page(page_overview.render, title="Overview", icon=":material/monitoring:", url_path="overview"),
    st.Page(page_backtest.render, title="Backtest Lab", icon=":material/science:", url_path="backtest"),
    st.Page(page_price_chart.render, title="Price Chart", icon=":material/candlestick_chart:", url_path="precio"),
    st.Page(page_trades.render, title="Trades", icon=":material/receipt_long:", url_path="trades"),
    st.Page(page_risk.render, title="Risk", icon=":material/shield:", url_path="riesgo"),
    st.Page(page_validation.render, title="Validation", icon=":material/verified:", url_path="validacion"),
    st.Page(page_configurator.render, title="Bot Builder", icon=":material/tune:", url_path="builder"),
    st.Page(page_ai_chat.render, title="AI Analyst", icon=":material/psychology:", url_path="ai-chat"),
    st.Page(page_reports.render, title="Reports", icon=":material/description:", url_path="reportes"),
]

with st.sidebar:
    st.markdown("# CHUKY BOT")
    st.markdown(
        "<p style='text-align:center; color:#FFFFFF; font-size:0.8rem; margin-top:-8px; opacity:0.7;'>"
        "Algorithmic Trading Platform</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

pg = st.navigation(pages)

with st.sidebar:
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; color:#FFFFFF; font-size:11px; line-height:1.6;'>"
        "MNQ Futures &middot; OneUpTrader $50k<br>"
        "ICT Methodology<br>"
        "<span style='color:#58A6FF;'>v2.0</span>"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Render Selected Page ────────────────────────────────────────
pg.run()
