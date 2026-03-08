"""
Page 1: Overview — Panel Principal
KPIs, equity curve, P&L bars, recent trades, drawdown gauge.
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from dashboard.theme import apply_plotly_theme, PURPLE, NEON_GREEN, HOT_PINK, DANGER, SUCCESS, WARNING, MID_GRAY


def render():
    st.title("Overview Dashboard")

    # Check if backtest results exist in session
    if "backtest_result" not in st.session_state:
        st.info(
            "**Note:** Run a backtest first in the **Backtest Lab** "
            "to see results here."
        )
        _show_demo()
        return

    result = st.session_state["backtest_result"]
    metrics = result["metrics"]
    trades_df = result["trades_df"]
    equity_df = result["equity_curve"]
    config = result.get("config", {})

    # ── Status Bar ──────────────────────────────────────────────
    status_col1, status_col2, status_col3 = st.columns([2, 1, 1])
    with status_col1:
        st.markdown(
            f"**Config activa:** `{config.get('name', 'Default')}`"
        )
    with status_col2:
        st.markdown(f"**Trades:** {metrics.total_trades}")
    with status_col3:
        pnl_color = SUCCESS if metrics.total_pnl >= 0 else DANGER
        st.markdown(f"**P&L:** <span style='color:{pnl_color}'>${metrics.total_pnl:+,.2f}</span>", unsafe_allow_html=True)

    st.markdown("---")

    # ── KPI Cards (Row 1) ──────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        st.metric("Sharpe Ratio", f"{metrics.sharpe_ratio:.2f}",
                   delta="OK" if metrics.sharpe_ratio > 0.5 else "Bajo")
    with k2:
        st.metric("Profit Factor", f"{metrics.profit_factor:.2f}",
                   delta="OK" if metrics.profit_factor > 1.2 else "Bajo")
    with k3:
        st.metric("Win Rate", f"{metrics.win_rate:.1%}",
                   delta=f"{metrics.winning_trades}W / {metrics.losing_trades}L")
    with k4:
        st.metric("Max Drawdown", f"${metrics.max_drawdown_usd:,.0f}",
                   delta=f"{metrics.max_drawdown_pct:.1%}")
    with k5:
        st.metric("Retorno", f"${metrics.total_pnl:+,.0f}",
                   delta=f"{metrics.total_return_pct:+.1f}%")
    with k6:
        st.metric("Total Trades", f"{metrics.total_trades}",
                   delta=f"{metrics.trades_per_day:.1f}/día")

    st.markdown("")

    # ── Equity Curve ────────────────────────────────────────────
    col_eq, col_dd = st.columns([3, 1], gap="large")

    with col_eq:
        st.subheader("Equity Curve")
        if not equity_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=equity_df["datetime"],
                y=equity_df["equity"],
                mode="lines",
                name="Equity",
                line=dict(color=PURPLE, width=2),
                fill="tozeroy",
                fillcolor="rgba(155,89,182,0.1)",
            ))
            # Benchmark line
            fig.add_hline(
                y=metrics.initial_balance,
                line_dash="dash",
                line_color=MID_GRAY,
                annotation_text="Capital Inicial",
            )
            fig = apply_plotly_theme(fig)
            fig.update_layout(
                height=350,
                yaxis_title="Equity ($)",
                xaxis_title="",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Sin datos de equity.")

    with col_dd:
        st.subheader("Drawdown")
        # Gauge
        dd_pct = abs(metrics.max_drawdown_usd) / 2500 * 100  # vs OneUpTrader limit
        dd_pct = min(dd_pct, 100)
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=abs(metrics.max_drawdown_usd),
            number=dict(prefix="$", font=dict(color="#D2B4FF")),
            title=dict(text="vs $2,500 Límite", font=dict(color=MID_GRAY, size=12)),
            gauge=dict(
                axis=dict(range=[0, 2500], tickfont=dict(color=MID_GRAY)),
                bar=dict(color=PURPLE),
                bgcolor="#1A1A2E",
                bordercolor="#2D2D44",
                steps=[
                    dict(range=[0, 1500], color="#1A2E1A"),
                    dict(range=[1500, 2000], color="#2E2E1A"),
                    dict(range=[2000, 2500], color="#2E1A1A"),
                ],
                threshold=dict(
                    line=dict(color=HOT_PINK, width=3),
                    value=2400,
                    thickness=0.75,
                ),
            ),
        ))
        fig_gauge = apply_plotly_theme(fig_gauge)
        fig_gauge.update_layout(height=350)
        st.plotly_chart(fig_gauge, use_container_width=True)

    # ── P&L Bars + Recent Trades ────────────────────────────────
    col_pnl, col_trades = st.columns([1, 1], gap="large")

    with col_pnl:
        st.subheader("P&L por Trade")
        if not trades_df.empty:
            pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
            colors = [NEON_GREEN if v >= 0 else HOT_PINK for v in trades_df[pnl_col]]
            fig_pnl = go.Figure(go.Bar(
                x=list(range(1, len(trades_df) + 1)),
                y=trades_df[pnl_col],
                marker_color=colors,
                hovertemplate="Trade %{x}<br>P&L: $%{y:+,.2f}<extra></extra>",
            ))
            fig_pnl = apply_plotly_theme(fig_pnl)
            fig_pnl.update_layout(
                height=280,
                xaxis_title="Trade #",
                yaxis_title="P&L ($)",
            )
            st.plotly_chart(fig_pnl, use_container_width=True)

    with col_trades:
        st.subheader("Últimos Trades")
        if not trades_df.empty:
            pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
            display_cols = []
            if "timestamp" in trades_df.columns:
                display_cols.append("timestamp")
            if "direction" in trades_df.columns:
                display_cols.append("direction")
            if "entry_price" in trades_df.columns:
                display_cols.append("entry_price")
            if "exit_price" in trades_df.columns:
                display_cols.append("exit_price")
            display_cols.append(pnl_col)

            available_cols = [c for c in display_cols if c in trades_df.columns]
            recent = trades_df[available_cols].tail(10).iloc[::-1]
            st.dataframe(recent, use_container_width=True, height=280)
        else:
            st.info("Sin trades.")

    # ── Extra Metrics ───────────────────────────────────────────
    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4, gap="medium")
    with m1:
        st.metric("Avg Win", f"${metrics.avg_win:+,.2f}")
    with m2:
        st.metric("Avg Loss", f"${metrics.avg_loss:+,.2f}")
    with m3:
        st.metric("Expectancy", f"${metrics.expectancy:+,.2f}")
    with m4:
        st.metric("Mejor Día", f"${metrics.best_day_pnl:+,.2f}")


def _show_demo():
    """Show placeholder with demo metrics."""
    st.markdown("### Preview (sample data)")

    k1, k2, k3, k4, k5, k6 = st.columns(6, gap="medium")
    with k1:
        st.metric("Sharpe Ratio", "—")
    with k2:
        st.metric("Profit Factor", "—")
    with k3:
        st.metric("Win Rate", "—")
    with k4:
        st.metric("Max Drawdown", "—")
    with k5:
        st.metric("Retorno", "—")
    with k6:
        st.metric("Total Trades", "—")

    st.markdown(
        """
        <div class='chuky-card'>
        <h4>Getting Started</h4>
        <p>1. Go to <b>Bot Builder</b> to configure your strategy</p>
        <p>2. Go to <b>Backtest Lab</b> and run a backtest</p>
        <p>3. Results will appear here automatically</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
