"""
Page 6: Validation — Validación Científica
Walk-Forward Analysis, Monte Carlo, consistency check, GO/NO-GO checklist.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from dashboard.theme import apply_plotly_theme, PURPLE, NEON_GREEN, HOT_PINK, MID_GRAY, SUCCESS, WARNING, DANGER, ELECTRIC
from dashboard.engine import run_monte_carlo_analysis, run_consistency_check


def render():
    st.title("Scientific Validation")

    if "backtest_result" not in st.session_state:
        st.info("**Note:** Run a backtest first to validate the strategy.")
        return

    result = st.session_state["backtest_result"]
    metrics = result["metrics"]
    trades_df = result["trades_df"]

    if trades_df.empty:
        st.warning("No hay trades para validar.")
        return

    pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"

    # ── Run Validation ──────────────────────────────────────────
    tab_mc, tab_consistency, tab_checklist = st.tabs([
        "Monte Carlo", "Consistency", "Checklist GO/NO-GO"
    ])

    # ── Monte Carlo ─────────────────────────────────────────────
    with tab_mc:
        st.subheader("Monte Carlo Simulation")

        if st.button("Run Monte Carlo (1,000 iterations)", type="primary"):
            with st.spinner("Ejecutando 1,000 simulaciones..."):
                mc = run_monte_carlo_analysis(trades_df)
                if mc:
                    st.session_state["mc_result"] = mc
                else:
                    st.error("Insuficientes trades para Monte Carlo (mínimo 3).")

        if "mc_result" in st.session_state:
            mc = st.session_state["mc_result"]

            # KPIs
            m1, m2, m3, m4 = st.columns(4, gap="medium")
            with m1:
                st.metric("Prob. Profit", f"{mc.prob_profit:.1%}",
                           delta="GO" if mc.prob_profit > 0.6 else "NO-GO")
            with m2:
                st.metric("Max DD P95", f"${mc.max_dd_p95:,.0f}",
                           delta="OK" if mc.max_dd_p95 < 2500 else "RIESGO")
            with m3:
                st.metric("P&L Mediano", f"${mc.final_pnl_p50:+,.0f}")
            with m4:
                st.metric("Prob. Exceder DD", f"{mc.prob_exceed_dd:.1%}",
                           delta="OK" if mc.prob_exceed_dd < 0.10 else "ALTO")

            # Fan chart
            if mc.all_final_pnls is not None:
                st.markdown("#### Distribución de Retornos Finales")
                fig_dist = go.Figure()
                fig_dist.add_trace(go.Histogram(
                    x=mc.all_final_pnls,
                    nbinsx=50,
                    marker_color=PURPLE,
                    opacity=0.7,
                    name="P&L Final",
                ))
                fig_dist.add_vline(x=0, line_dash="dash", line_color=HOT_PINK, line_width=2)
                fig_dist.add_vline(x=mc.final_pnl_p50, line_dash="dot", line_color=NEON_GREEN,
                                   annotation_text=f"Mediana: ${mc.final_pnl_p50:+,.0f}")
                fig_dist = apply_plotly_theme(fig_dist)
                fig_dist.update_layout(height=350, xaxis_title="P&L Final ($)", yaxis_title="Frecuencia")
                st.plotly_chart(fig_dist, width="stretch")

            # Max DD distribution
            if mc.all_max_dds is not None:
                st.markdown("#### Distribución de Max Drawdown")
                fig_dd = go.Figure()
                fig_dd.add_trace(go.Histogram(
                    x=mc.all_max_dds,
                    nbinsx=50,
                    marker_color=HOT_PINK,
                    opacity=0.7,
                    name="Max DD",
                ))
                fig_dd.add_vline(x=2500, line_dash="dash", line_color=DANGER,
                                 annotation_text="Límite $2,500")
                fig_dd = apply_plotly_theme(fig_dd)
                fig_dd.update_layout(height=300, xaxis_title="Max Drawdown ($)", yaxis_title="Frecuencia")
                st.plotly_chart(fig_dd, width="stretch")

            # Summary
            st.markdown(
                f"""<div class='chuky-card'>
                <h4>{'PASS' if mc.is_viable else 'FAIL'} -- Monte Carlo Verdict</h4>
                <p>{mc.summary}</p>
                </div>""",
                unsafe_allow_html=True,
            )

    # ── Consistency Check ───────────────────────────────────────
    with tab_consistency:
        st.subheader("OneUpTrader Consistency Rule")

        st.markdown(
            """
            **Regla:** La suma de los 3 mejores días de P&L no debe superar el 80%
            del P&L positivo total. Esto asegura que las ganancias estén distribuidas.
            """
        )

        if st.button("Verify Consistency", type="primary"):
            with st.spinner("Verificando..."):
                cons = run_consistency_check(trades_df)
                if cons:
                    st.session_state["consistency_result"] = cons
                else:
                    st.error("No se pudo calcular la consistencia (faltan datos de fecha).")

        if "consistency_result" in st.session_state:
            cons = st.session_state["consistency_result"]

            # Result
            if cons.passed:
                st.success(f"PASS -- Ratio: {cons.ratio:.1%} (limit: {cons.threshold:.0%})")
            else:
                st.error(f"FAIL -- Ratio: {cons.ratio:.1%} (limit: {cons.threshold:.0%})")

            # Details
            c1, c2, c3 = st.columns(3, gap="medium")
            with c1:
                st.metric("Top 3 Días Sum", f"${cons.top_n_sum:+,.2f}")
            with c2:
                st.metric("PNL Positivo Total", f"${cons.total_positive_pnl:+,.2f}")
            with c3:
                st.metric("Ratio", f"{cons.ratio:.1%}")

            st.metric("Días Positivos / Negativos",
                      f"{cons.positive_days} / {cons.negative_days}")

            # Top days chart
            if cons.top_n_days:
                fig_top = go.Figure(go.Bar(
                    x=[f"Día {i+1}" for i in range(len(cons.top_n_days))],
                    y=cons.top_n_days,
                    marker_color=[NEON_GREEN] * len(cons.top_n_days),
                ))
                fig_top = apply_plotly_theme(fig_top)
                fig_top.update_layout(height=250, yaxis_title="P&L ($)")
                st.plotly_chart(fig_top, width="stretch")

    # ── GO/NO-GO Checklist ──────────────────────────────────────
    with tab_checklist:
        st.subheader("Validation Checklist GO/NO-GO")

        checks = [
            ("Sharpe Ratio > 0.5", metrics.sharpe_ratio > 0.5, f"{metrics.sharpe_ratio:.2f}"),
            ("Profit Factor > 1.0", metrics.profit_factor > 1.0, f"{metrics.profit_factor:.2f}"),
            ("Win Rate > 40%", metrics.win_rate > 0.40, f"{metrics.win_rate:.1%}"),
            ("Max DD < $2,500", metrics.max_drawdown_usd < 2500, f"${metrics.max_drawdown_usd:,.0f}"),
            ("Total Trades >= 10", metrics.total_trades >= 10, f"{metrics.total_trades}"),
            ("Expectancy > 0", metrics.expectancy > 0, f"${metrics.expectancy:+,.2f}"),
        ]

        # Add MC check if available
        if "mc_result" in st.session_state:
            mc = st.session_state["mc_result"]
            checks.append(("MC Prob. Profit > 60%", mc.prob_profit > 0.60, f"{mc.prob_profit:.1%}"))
            checks.append(("MC DD P95 < $2,500", mc.max_dd_p95 < 2500, f"${mc.max_dd_p95:,.0f}"))

        # Add consistency check if available
        if "consistency_result" in st.session_state:
            cons = st.session_state["consistency_result"]
            checks.append(("Consistencia OneUpTrader", cons.passed, f"{cons.ratio:.1%}"))

        passed = sum(1 for _, ok, _ in checks if ok)
        total = len(checks)

        # Summary
        if passed == total:
            st.success(f"**GO** -- {passed}/{total} checks passed")
        elif passed >= total * 0.7:
            st.warning(f"**CAUTION** -- {passed}/{total} checks passed")
        else:
            st.error(f"**NO-GO** -- {passed}/{total} checks passed")

        # Individual checks
        for name, ok, value in checks:
            icon = "[PASS]" if ok else "[FAIL]"
            color = SUCCESS if ok else DANGER
            st.markdown(
                f"""<div style='background:#161B22; border:1px solid #30363D; border-radius:8px;
                padding:10px; margin-bottom:6px; border-left:4px solid {color};
                display:flex; justify-content:space-between; align-items:center;'>
                <span style='color:#E6EDF3;'>{icon} {name}</span>
                <span style='color:{color}; font-weight:600;'>{value}</span>
                </div>""",
                unsafe_allow_html=True,
            )
