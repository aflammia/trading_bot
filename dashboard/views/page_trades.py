"""
Page 4: Trade Explorer — Explorador de Trades
Filterable trade table, P&L histogram, hourly heatmap.
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from dashboard.theme import apply_plotly_theme, PURPLE, NEON_GREEN, HOT_PINK, MID_GRAY, SUCCESS, DANGER
from dashboard.engine import compute_daily_pnl, compute_hourly_performance


def render():
    st.title("Trade Explorer")

    if "backtest_result" not in st.session_state:
        st.info("**Note:** Run a backtest first to explore the trades.")
        return

    trades_df = st.session_state["backtest_result"]["trades_df"]
    if trades_df.empty:
        st.warning("No hay trades para mostrar.")
        return

    pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
    df = trades_df.copy()

    # ── Filters ─────────────────────────────────────────────────
    with st.expander("Filters", expanded=False):
        f1, f2, f3 = st.columns(3, gap="medium")

        with f1:
            if "direction" in df.columns:
                dir_filter = st.multiselect(
                    "Dirección",
                    options=df["direction"].unique().tolist(),
                    default=df["direction"].unique().tolist(),
                )
                df = df[df["direction"].isin(dir_filter)]

        with f2:
            result_filter = st.radio(
                "Resultado",
                ["Todos", "Ganadores", "Perdedores"],
                horizontal=True,
            )
            if result_filter == "Ganadores":
                df = df[df[pnl_col] >= 0]
            elif result_filter == "Perdedores":
                df = df[df[pnl_col] < 0]

        with f3:
            if pnl_col in df.columns and len(df) > 0:
                min_pnl = float(df[pnl_col].min())
                max_pnl = float(df[pnl_col].max())
                pnl_range = st.slider(
                    "Rango P&L ($)",
                    min_value=min_pnl, max_value=max_pnl,
                    value=(min_pnl, max_pnl),
                )
                df = df[(df[pnl_col] >= pnl_range[0]) & (df[pnl_col] <= pnl_range[1])]

    # ── Summary Stats ───────────────────────────────────────────
    s1, s2, s3, s4 = st.columns(4, gap="medium")
    with s1:
        st.metric("Trades Filtrados", len(df))
    with s2:
        wr = (df[pnl_col] >= 0).mean() * 100 if len(df) > 0 else 0
        st.metric("Win Rate", f"{wr:.1f}%")
    with s3:
        total = df[pnl_col].sum() if len(df) > 0 else 0
        st.metric("P&L Total", f"${total:+,.2f}")
    with s4:
        avg = df[pnl_col].mean() if len(df) > 0 else 0
        st.metric("P&L Promedio", f"${avg:+,.2f}")

    st.markdown("---")

    # ── Trade Table ─────────────────────────────────────────────
    st.subheader("Trade Table")

    # Determine columns to display
    available = df.columns.tolist()
    priority_cols = ["timestamp", "direction", "entry_price", "exit_price",
                     "sl_price", "tp_price", pnl_col, "commission",
                     "contracts", "reason", "session"]
    show_cols = [c for c in priority_cols if c in available]
    # Add any remaining columns
    for c in available:
        if c not in show_cols:
            show_cols.append(c)

    display_df = df[show_cols].copy()

    # Color the P&L column
    st.dataframe(
        display_df,
        use_container_width=True,
        height=400,
    )

    # ── Charts Row ──────────────────────────────────────────────
    st.markdown("---")
    col_hist, col_daily = st.columns(2, gap="large")

    with col_hist:
        st.subheader("P&L Distribution")
        fig_hist = go.Figure()
        wins = df[df[pnl_col] >= 0][pnl_col]
        losses = df[df[pnl_col] < 0][pnl_col]

        if len(wins) > 0:
            fig_hist.add_trace(go.Histogram(
                x=wins, name="Ganadores",
                marker_color=NEON_GREEN, opacity=0.7,
                nbinsx=15,
            ))
        if len(losses) > 0:
            fig_hist.add_trace(go.Histogram(
                x=losses, name="Perdedores",
                marker_color=HOT_PINK, opacity=0.7,
                nbinsx=15,
            ))

        fig_hist.add_vline(x=0, line_dash="dash", line_color="white", line_width=1)
        fig_hist = apply_plotly_theme(fig_hist)
        fig_hist.update_layout(
            height=350,
            barmode="overlay",
            xaxis_title="P&L ($)",
            yaxis_title="Frecuencia",
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_daily:
        st.subheader("Daily P&L")
        daily = compute_daily_pnl(df)
        if not daily.empty:
            colors = [NEON_GREEN if v >= 0 else HOT_PINK for v in daily["pnl"]]
            fig_daily = go.Figure(go.Bar(
                x=daily["date"].astype(str),
                y=daily["pnl"],
                marker_color=colors,
                hovertemplate="Fecha: %{x}<br>P&L: $%{y:+,.2f}<br>Trades: %{customdata[0]}<extra></extra>",
                customdata=daily[["trades"]].values,
            ))
            fig_daily = apply_plotly_theme(fig_daily)
            fig_daily.update_layout(height=350, xaxis_title="Fecha", yaxis_title="P&L ($)")
            st.plotly_chart(fig_daily, use_container_width=True)
        else:
            st.info("Sin datos diarios.")

    # ── Hourly Heatmap ──────────────────────────────────────────
    st.markdown("---")
    st.subheader("Hourly Performance")
    hourly = compute_hourly_performance(df)
    if not hourly.empty:
        fig_hourly = go.Figure(go.Bar(
            x=hourly["hour"],
            y=hourly["total_pnl"],
            marker_color=[NEON_GREEN if v >= 0 else HOT_PINK for v in hourly["total_pnl"]],
            hovertemplate="Hora: %{x}:00<br>P&L: $%{y:+,.2f}<br>Trades: %{customdata[0]}<extra></extra>",
            customdata=hourly[["count"]].values,
        ))
        fig_hourly = apply_plotly_theme(fig_hourly)
        fig_hourly.update_layout(
            height=300,
            xaxis_title="Hora del Día (UTC)",
            yaxis_title="P&L ($)",
            xaxis=dict(dtick=1),
        )
        st.plotly_chart(fig_hourly, use_container_width=True)
    else:
        st.info("Sin datos horarios disponibles.")
