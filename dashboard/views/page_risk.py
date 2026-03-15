"""
Page 5: Risk Center — Centro de Control de Riesgo
Drawdown tracking, kill switch status, position history, streak analysis.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from dashboard.theme import apply_plotly_theme, PURPLE, NEON_GREEN, HOT_PINK, MID_GRAY, SUCCESS, WARNING, DANGER
from dashboard.engine import build_equity_curve


def render():
    st.title("Risk Control Center")

    if "backtest_result" not in st.session_state:
        st.info("**Note:** Run a backtest first to see the risk analysis.")
        return

    result = st.session_state["backtest_result"]
    metrics = result["metrics"]
    trades_df = result["trades_df"]
    equity_df = result["equity_curve"]
    config = result.get("config", {})

    if trades_df.empty:
        st.warning("No hay trades para analizar riesgo.")
        return

    pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"

    # ── Drawdown Gauge + Kill Switch Status ─────────────────────
    col_gauge, col_ks = st.columns([1, 1], gap="large")

    with col_gauge:
        st.subheader("Trailing Drawdown")
        dd_limit = 2500
        dd_actual = abs(metrics.max_drawdown_usd)

        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=dd_actual,
            number=dict(prefix="$", font=dict(color="#E6EDF3", size=36)),
            delta=dict(reference=dd_limit, valueformat=".0f", prefix="$"),
            title=dict(text="Max Drawdown vs Límite $2,500", font=dict(color=MID_GRAY, size=14)),
            gauge=dict(
                axis=dict(range=[0, dd_limit], tickfont=dict(color=MID_GRAY)),
                bar=dict(color=PURPLE),
                bgcolor="#161B22",
                bordercolor="#30363D",
                steps=[
                    dict(range=[0, dd_limit * 0.6], color="rgba(0,200,83,0.2)"),
                    dict(range=[dd_limit * 0.6, dd_limit * 0.8], color="rgba(255,152,0,0.2)"),
                    dict(range=[dd_limit * 0.8, dd_limit], color="rgba(244,67,54,0.2)"),
                ],
                threshold=dict(
                    line=dict(color=HOT_PINK, width=3),
                    value=2400,
                    thickness=0.75,
                ),
            ),
        ))
        fig_gauge = apply_plotly_theme(fig_gauge)
        fig_gauge.update_layout(height=300)
        st.plotly_chart(fig_gauge, width="stretch")

    with col_ks:
        st.subheader("Kill Switches")
        max_daily = config.get("max_daily_loss", 550)

        # Level 1: Reduce contracts
        _ks_card("Nivel 1: Reducir Contratos",
                 f"Drawdown > $2,000 → operar con 2 contratos",
                 dd_actual >= 2000, dd_actual >= 2000)

        # Level 2: Stop day
        _ks_card("Nivel 2: Stop del Día",
                 f"Pérdida diaria > ${max_daily:,.0f} → no más trades hoy",
                 abs(metrics.worst_day_pnl) >= max_daily,
                 abs(metrics.worst_day_pnl) >= max_daily)

        # Level 3: Stop all
        _ks_card("Nivel 3: Stop Total",
                 f"Drawdown > $2,400 → parar todo el trading",
                 dd_actual >= 2400, dd_actual >= 2400)

    st.markdown("---")

    # ── Underwater Drawdown Chart ───────────────────────────────
    st.subheader("Drawdown Underwater")
    if not equity_df.empty and "drawdown" in equity_df.columns:
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=equity_df["datetime"],
            y=equity_df["drawdown"],
            mode="lines",
            fill="tozeroy",
            line=dict(color=HOT_PINK, width=1.5),
            fillcolor="rgba(255,0,110,0.2)",
            name="Drawdown",
        ))
        fig_dd.add_hline(y=-2500, line_dash="dash", line_color=DANGER,
                         annotation_text="Límite DD $2,500")
        fig_dd = apply_plotly_theme(fig_dd)
        fig_dd.update_layout(height=300, yaxis_title="Drawdown ($)")
        st.plotly_chart(fig_dd, width="stretch")

    # ── Position History + Streak Analysis ──────────────────────
    col_pos, col_streak = st.columns(2, gap="large")

    with col_pos:
        st.subheader("P&L per Trade (sequential)")
        pnls = trades_df[pnl_col].values
        colors = [NEON_GREEN if p >= 0 else HOT_PINK for p in pnls]
        fig_pos = go.Figure(go.Bar(
            x=list(range(1, len(pnls) + 1)),
            y=pnls,
            marker_color=colors,
        ))
        fig_pos = apply_plotly_theme(fig_pos)
        fig_pos.update_layout(height=300, xaxis_title="Trade #", yaxis_title="P&L ($)")
        st.plotly_chart(fig_pos, width="stretch")

    with col_streak:
        st.subheader("Streak Analysis")
        streaks = _compute_streaks(trades_df[pnl_col].values)

        s1, s2 = st.columns(2, gap="medium")
        with s1:
            st.metric("Racha Ganadora Más Larga", f"{streaks['max_win_streak']} trades")
            st.metric("P&L Racha Ganadora", f"${streaks['max_win_streak_pnl']:+,.2f}")
        with s2:
            st.metric("Racha Perdedora Más Larga", f"{streaks['max_loss_streak']} trades")
            st.metric("P&L Racha Perdedora", f"${streaks['max_loss_streak_pnl']:+,.2f}")

        st.markdown("---")
        st.markdown("**Simulación: ¿Qué pasa si pierdo N trades seguidos?**")
        n_losses = st.slider("Trades perdedores consecutivos", 1, 10, 3)
        avg_loss = abs(metrics.avg_loss) if metrics.avg_loss != 0 else 300
        simulated_dd = n_losses * avg_loss
        st.warning(
            f"Con {n_losses} pérdidas consecutivas (avg ${avg_loss:,.0f}): "
            f"**-${simulated_dd:,.2f}** drawdown "
            f"({'DANGEROUS' if simulated_dd > 2000 else 'Manageable'})"
        )


def _ks_card(title: str, description: str, is_triggered: bool, active: bool):
    """Render a kill switch status card."""
    if is_triggered:
        icon = "[!]"
        badge = "ACTIVATED"
        color = DANGER
    else:
        icon = "[OK]"
        badge = "OK"
        color = SUCCESS

    st.markdown(
        f"""<div style='background:#161B22; border:1px solid #30363D; border-radius:8px;
        padding:12px; margin-bottom:8px; border-left:4px solid {color};'>
        <span style='font-size:16px;'>{icon}</span>
        <span style='color:#E6EDF3; font-weight:600;'> {title}</span>
        <span style='float:right; background:{color}; color:white; padding:2px 8px;
        border-radius:4px; font-size:11px;'>{badge}</span>
        <br><span style='color:#8B949E; font-size:12px;'>{description}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def _compute_streaks(pnls: np.ndarray) -> dict:
    """Compute winning/losing streaks."""
    if len(pnls) == 0:
        return {"max_win_streak": 0, "max_loss_streak": 0,
                "max_win_streak_pnl": 0, "max_loss_streak_pnl": 0}

    max_win = max_loss = current_win = current_loss = 0
    win_pnl = loss_pnl = current_win_pnl = current_loss_pnl = 0

    for pnl in pnls:
        if pnl >= 0:
            current_win += 1
            current_win_pnl += pnl
            if current_win > max_win:
                max_win = current_win
                win_pnl = current_win_pnl
            current_loss = 0
            current_loss_pnl = 0
        else:
            current_loss += 1
            current_loss_pnl += pnl
            if current_loss > max_loss:
                max_loss = current_loss
                loss_pnl = current_loss_pnl
            current_win = 0
            current_win_pnl = 0

    return {
        "max_win_streak": max_win,
        "max_loss_streak": max_loss,
        "max_win_streak_pnl": win_pnl,
        "max_loss_streak_pnl": loss_pnl,
    }
