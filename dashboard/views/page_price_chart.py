"""
Page 3: Price Chart — Gráfico de Precio Interactivo
Candlestick with ICT overlays, trade markers, FVGs.
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

from dashboard.theme import apply_plotly_theme, PURPLE, NEON_GREEN, HOT_PINK, MID_GRAY, PURPLE_LIGHT


def render():
    st.title("Interactive Price Chart")

    if "price_data" not in st.session_state:
        st.info("**Note:** Run a backtest first to see the chart with trades.")
        return

    df = st.session_state["price_data"].copy()
    trades_df = st.session_state.get("backtest_result", {}).get("trades_df", pd.DataFrame())

    # Ensure timezone-naive index for Plotly
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # ── Controls ────────────────────────────────────────────────
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 1, 2], gap="medium")

    with col_ctrl1:
        show_volume = st.checkbox("Volume", value=True)
    with col_ctrl2:
        show_trades = st.checkbox("Trades", value=True)
    with col_ctrl3:
        # Date range selector
        if len(df) > 200:
            window = st.slider(
                "Ventana (últimas N velas)",
                min_value=50, max_value=len(df),
                value=min(200, len(df)),
                step=50,
            )
            df = df.tail(window)

    # ── Build Chart ─────────────────────────────────────────────
    rows = 2 if show_volume else 1
    row_heights = [0.8, 0.2] if show_volume else [1.0]
    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        increasing_line_color=NEON_GREEN,
        decreasing_line_color=HOT_PINK,
        increasing_fillcolor=NEON_GREEN,
        decreasing_fillcolor=HOT_PINK,
        name="Price",
    ), row=1, col=1)

    # Volume
    if show_volume and "Volume" in df.columns:
        vol_colors = [NEON_GREEN if c >= o else HOT_PINK
                      for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(go.Bar(
            x=df.index,
            y=df["Volume"],
            marker_color=vol_colors,
            opacity=0.5,
            name="Volume",
            showlegend=False,
        ), row=2, col=1)

    # Trade markers
    if show_trades and not trades_df.empty:
        _add_trade_markers(fig, trades_df, df)

    # Apply theme
    fig = apply_plotly_theme(fig)
    fig.update_layout(
        height=600,
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="Precio ($)", row=1, col=1)
    if show_volume:
        fig.update_yaxes(title_text="Vol", row=2, col=1)

    st.plotly_chart(fig, width="stretch")

    # ── Trade Context Panel ─────────────────────────────────────
    if not trades_df.empty:
        st.markdown("---")
        st.subheader("Trade Context")

        pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
        display_df = trades_df.copy()
        cols_to_show = [c for c in ["timestamp", "direction", "entry_price", "exit_price",
                                      "sl_price", "tp_price", pnl_col, "reason"] if c in display_df.columns]
        if cols_to_show:
            st.dataframe(display_df[cols_to_show], width="stretch")


def _add_trade_markers(fig, trades_df, price_df):
    """Add entry/exit markers to the chart."""
    pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"

    # Entry markers
    if "entry_price" in trades_df.columns:
        entries = trades_df.copy()
        # Use entry_time if available, else timestamp
        if "entry_time" in entries.columns:
            entries["dt"] = pd.to_datetime(entries["entry_time"])
        elif "timestamp" in entries.columns:
            entries["dt"] = pd.to_datetime(entries["timestamp"])
        else:
            return

        # Remove timezone if present (match price_df index)
        if entries["dt"].dt.tz is not None:
            entries["dt"] = entries["dt"].dt.tz_localize(None)

        # Longs (green triangles up)
        if "direction" in entries.columns:
            longs = entries[entries["direction"] == "long"]
            shorts = entries[entries["direction"] == "short"]
        else:
            longs = pd.DataFrame()
            shorts = pd.DataFrame()

        if not longs.empty:
            fig.add_trace(go.Scatter(
                x=longs["dt"],
                y=longs["entry_price"],
                mode="markers",
                marker=dict(symbol="triangle-up", size=12, color=NEON_GREEN, line=dict(width=1, color="white")),
                name="Long Entry",
                hovertemplate="LONG @ $%{y:.2f}<extra></extra>",
            ), row=1, col=1)

        if not shorts.empty:
            fig.add_trace(go.Scatter(
                x=shorts["dt"],
                y=shorts["entry_price"],
                mode="markers",
                marker=dict(symbol="triangle-down", size=12, color=HOT_PINK, line=dict(width=1, color="white")),
                name="Short Entry",
                hovertemplate="SHORT @ $%{y:.2f}<extra></extra>",
            ), row=1, col=1)

    # Exit markers
    if "exit_price" in trades_df.columns:
        exits = trades_df.copy()
        if "exit_time" in exits.columns:
            exits["dt"] = pd.to_datetime(exits["exit_time"])
        elif "timestamp" in exits.columns:
            exits["dt"] = pd.to_datetime(exits["timestamp"])
        else:
            return

        if exits["dt"].dt.tz is not None:
            exits["dt"] = exits["dt"].dt.tz_localize(None)

        if pnl_col in exits.columns:
            wins = exits[exits[pnl_col] >= 0]
            losses = exits[exits[pnl_col] < 0]
        else:
            wins = pd.DataFrame()
            losses = pd.DataFrame()

        if not wins.empty:
            fig.add_trace(go.Scatter(
                x=wins["dt"],
                y=wins["exit_price"],
                mode="markers",
                marker=dict(symbol="star", size=10, color=NEON_GREEN),
                name="Win Exit",
                hovertemplate="WIN @ $%{y:.2f}<extra></extra>",
            ), row=1, col=1)

        if not losses.empty:
            fig.add_trace(go.Scatter(
                x=losses["dt"],
                y=losses["exit_price"],
                mode="markers",
                marker=dict(symbol="x", size=10, color=HOT_PINK),
                name="Loss Exit",
                hovertemplate="LOSS @ $%{y:.2f}<extra></extra>",
            ), row=1, col=1)
