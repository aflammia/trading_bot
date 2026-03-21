"""
Page 2: Backtest Lab - Visual Interactive Backtesting

Features:
- Multi-timeframe data loading (1H, 15M, 5M, 1M)
- Interactive candlestick chart with FVG zones
- Entry/exit markers with detailed tooltips
- Multi-timeframe FVG panel showing all detected FVGs
- Date range selector with 30-day limit
- Equity curve and performance metrics
- MongoDB persistence for all results
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from dashboard.theme import (
    apply_plotly_theme, BRAND_PRIMARY, LONG_GREEN, SHORT_RED,
    TEXT_SECONDARY, SUCCESS, DANGER, NEUTRAL_BLUE, ACCENT_GOLD,
    BG_SECONDARY, BORDER_COLOR, TEXT_PRIMARY, ACCENT_CYAN,
    fmt_currency, fmt_pnl_color,
)
from dashboard.engine import (
    load_data, load_multi_tf_data, execute_backtest, build_equity_curve,
    DEFAULT_CONFIG, PRESET_CONFIGS,
    save_config, list_configs, load_config,
    run_multi_tf_fvg_analysis,
)
from config.settings import MAX_BACKTEST_DAYS, MULTI_TF_FVG_TIMEFRAMES
from indicators.liquidity import compute_all_session_levels


# FVG color mapping by timeframe
# FVG color mapping by timeframe (opacity decreases with lower TFs for visual hierarchy)
FVG_COLORS = {
    "1h":  {"bullish": "rgba(0,200,83,0.22)",  "bearish": "rgba(239,83,80,0.22)",
             "bullish_border": "#00C853", "bearish_border": "#EF5350"},
    "15m": {"bullish": "rgba(0,200,83,0.13)",  "bearish": "rgba(239,83,80,0.13)",
             "bullish_border": "#66BB6A", "bearish_border": "#E57373"},
    "5m":  {"bullish": "rgba(0,200,83,0.07)",  "bearish": "rgba(239,83,80,0.07)",
             "bullish_border": "#A5D6A7", "bearish_border": "#EF9A9A"},
    "1m":  {"bullish": "rgba(0,200,83,0.04)",  "bearish": "rgba(239,83,80,0.04)",
             "bullish_border": "#C8E6C9", "bearish_border": "#FFCDD2"},
}


def render():
    st.title("Backtest Laboratory")

    # Load active config from Bot Builder (or default)
    if "active_config" not in st.session_state:
        st.session_state["active_config"] = DEFAULT_CONFIG.copy()

    base_config = st.session_state["active_config"].copy()

    # -- Configuration Panel --
    with st.expander("Backtest Configuration", expanded=True):
        c1, c2, c3 = st.columns(3, gap="large")

        with c1:
            st.markdown("**Period**")
            default_end = datetime.now().date()
            default_start = default_end - timedelta(days=14)
            start_date = st.date_input(
                "Start Date",
                value=default_start,
                key="bt_start",
            )
            end_date = st.date_input(
                "End Date",
                value=default_end,
                key="bt_end",
            )
            # Enforce 30-day limit
            date_diff = (end_date - start_date).days
            if date_diff > MAX_BACKTEST_DAYS:
                st.warning(f"Maximum backtest period is {MAX_BACKTEST_DAYS} days. Range will be adjusted.")
                start_date = end_date - timedelta(days=MAX_BACKTEST_DAYS)

            interval = st.selectbox(
                "Chart Timeframe",
                ["1m", "5m", "15m", "1h"],
                index=2,
                help="Primary chart display timeframe. FVGs are analyzed on all timeframes.",
            )

        with c2:
            st.markdown("**Capital & Risk**")
            capital = st.number_input(
                "Initial Capital ($)",
                value=int(base_config.get("initial_capital", 50000)),
                min_value=10000, max_value=200000, step=5000,
            )
            max_daily = st.slider(
                "Max Daily Loss ($)",
                min_value=200, max_value=1500,
                value=int(base_config.get("max_daily_loss", 550)),
                step=50,
            )
            contracts = st.slider(
                "Default Contracts",
                min_value=1, max_value=6,
                value=int(base_config.get("default_contracts", 3)),
            )

        with c3:
            st.markdown("**Preset / Config**")
            preset = st.selectbox(
                "Load Preset",
                ["-- Custom --"] + list(PRESET_CONFIGS.keys()),
            )
            if preset != "-- Custom --":
                base_config = PRESET_CONFIGS[preset].copy()
                st.success(f"Preset: {preset}")

            max_trades = st.slider(
                "Max Trades/Day",
                min_value=1, max_value=5,
                value=int(base_config.get("max_trades_per_day", 2)),
            )

            saved = list_configs()
            if saved:
                saved_names = [c.get("name", "?") for c in saved]
                load_from = st.selectbox("Load Saved", ["--"] + saved_names)
                if load_from != "--":
                    loaded = load_config(load_from)
                    if loaded:
                        base_config = loaded
                        st.success(f"Config loaded: {load_from}")

    # Build final config
    config = base_config.copy()
    config["initial_capital"] = float(capital)
    config["max_daily_loss"] = float(max_daily)
    config["default_contracts"] = contracts
    config["max_trades_per_day"] = max_trades

    # ICT Parameters panel
    with st.expander("Active ICT Parameters (from Bot Builder)"):
        ic1, ic2, ic3 = st.columns(3, gap="large")
        with ic1:
            st.caption("FVG Lookback / Max")
            st.write(f"- 1H: {config.get('fvg_lookback_1h', 10)} bars / max {config.get('fvg_max_1h', 4)}")
            st.write(f"- 15M: {config.get('fvg_lookback_15m', 16)} bars / max {config.get('fvg_max_15m', 4)}")
            st.write(f"- 5M: {config.get('fvg_lookback_5m', 24)} bars / max {config.get('fvg_max_5m', 3)}")
            st.write(f"- 1M: {config.get('fvg_lookback_1m', 30)} bars / max {config.get('fvg_max_1m', 3)}")
        with ic2:
            st.caption("Structure")
            st.write(f"- Lookback 4H: {config.get('structure_lookback', 6)}")
            st.write(f"- TP: Liquidez / PDH-PDL / Swings")
            st.write(f"- SL: FVG boundary (sin buffer)")
        with ic3:
            st.caption("Exits")
            st.write(f"- Break Even: {config.get('break_even_pct', 0.60):.0%} + FVG break")
            st.write(f"- Close at TP: {config.get('close_at_pct', 0.90):.0%}")
            st.write("- Sessions: NY AM only (9:30–11:00 ET)")
        st.info("To change these parameters, go to **Bot Builder**.")

    # -- Action Buttons --
    col_run, col_save, col_status = st.columns([1, 1, 2])

    with col_run:
        run_clicked = st.button(
            "Run Backtest", type="primary", width="stretch"
        )

    with col_save:
        save_name = st.text_input(
            "Config name",
            value=config.get("name", "My Config"),
            label_visibility="collapsed",
        )
        if st.button("Save Config", width="stretch"):
            save_config(config, save_name)
            st.success(f"Config '{save_name}' saved.")

    # -- Execute Backtest --
    if run_clicked:
        with col_status:
            st.info("Executing backtest analysis...")

        with st.spinner("Downloading data and running backtest..."):
            try:
                # Load primary timeframe data
                df = load_data(
                    interval=interval,
                    start=str(start_date),
                    end=str(end_date),
                )

                if df.empty:
                    st.error("Could not download data. Check your connection.")
                    return

                # Load multi-TF data for FVG analysis
                multi_tf_data = load_multi_tf_data(
                    start=str(start_date),
                    end=str(end_date),
                    primary_interval=interval,
                    primary_df=df,
                )

                st.success(
                    f"Data loaded: {len(df)} candles | "
                    f"{df.index[0]} to {df.index[-1]}"
                )

                result = execute_backtest(
                    df=df,
                    config=config,
                    period_name=f"Backtest {start_date} to {end_date}",
                    multi_tf_data=multi_tf_data,
                )

                # Store results in session state
                st.session_state["backtest_result"] = result
                st.session_state["price_data"] = df
                st.session_state["multi_tf_data"] = multi_tf_data
                st.session_state["active_config"] = config

                st.success(
                    f"Backtest complete: "
                    f"{result['metrics'].total_trades} trades | "
                    f"P&L: {fmt_currency(result['metrics'].total_pnl)}"
                )

            except Exception as e:
                st.error(f"Backtest error: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
                return

    # -- Display Results --
    if "backtest_result" in st.session_state:
        st.markdown("---")
        _show_results(st.session_state["backtest_result"])


def _show_results(result: dict):
    """Display backtest results with interactive charts."""
    metrics = result["metrics"]
    trades_df = result["trades_df"]
    equity_df = result["equity_curve"]
    fvgs = result.get("fvgs", [])
    fvg_summary = result.get("fvg_summary", {})

    # -- KPIs --
    st.subheader("Performance Summary")
    k1, k2, k3, k4, k5, k6 = st.columns(6, gap="medium")
    with k1:
        st.metric("P&L Total", fmt_currency(metrics.total_pnl),
                   delta=f"{metrics.total_return_pct:+.2f}%")
    with k2:
        st.metric("Sharpe", f"{metrics.sharpe_ratio:.2f}")
    with k3:
        st.metric("Win Rate", f"{metrics.win_rate:.1%}",
                   delta=f"{metrics.winning_trades}W / {metrics.losing_trades}L")
    with k4:
        st.metric("Profit Factor", f"{metrics.profit_factor:.2f}")
    with k5:
        st.metric("Max DD", fmt_currency(metrics.max_drawdown_usd))
    with k6:
        st.metric("Trades", f"{metrics.total_trades}",
                   delta=f"{metrics.trades_per_day:.1f}/day")

    c_ai1, c_ai2 = st.columns([1, 3], gap="large")
    with c_ai1:
        if st.button("Analizar con AI", width="stretch"):
            st.session_state["ai_prefill_prompt"] = (
                "Analiza este backtest y dame: resumen ejecutivo, fortalezas, debilidades, "
                "riesgo para prop firm y 5 acciones concretas para mejorar resultados."
            )
            st.success("Resumen enviado al AI Analyst. Abre la pagina AI Analyst para continuar.")
    with c_ai2:
        st.caption("Pasa el contexto del backtest actual al chat AI con un click.")

    # -- Visual Backtest Chart --
    if "price_data" in st.session_state:
        st.markdown("---")
        st.subheader("Interactive Backtest Chart")

        # Chart timeframe selector
        chart_tf = st.radio(
            "Chart Resolution",
            ["1m", "5m", "15m", "1h"],
            index=3,
            horizontal=True,
            help="Select the chart candle resolution. FVGs from all timeframes are overlaid.",
        )

        # FVG display toggles
        fvg_col1, fvg_col2 = st.columns(2, gap="large")
        with fvg_col1:
            show_fvgs = st.multiselect(
                "Show FVGs from timeframes",
                MULTI_TF_FVG_TIMEFRAMES,
                default=["1h", "15m"],
                help="Select which timeframe FVGs to display on the chart.",
            )
        with fvg_col2:
            show_decisions = st.checkbox(
                "Highlight decision FVGs only",
                value=False,
                help="Show only FVGs that influenced trade decisions.",
            )
            show_session_levels = st.checkbox(
                "Show previous session H/L",
                value=True,
                help="Muestra niveles previos de Asia, London, NY AM y NY PM.",
            )

        # Load chart data for selected resolution
        chart_df = st.session_state["price_data"]
        if "multi_tf_data" in st.session_state:
            mtf = st.session_state["multi_tf_data"]
            tf_df = mtf.get(chart_tf)
            if tf_df is not None and not tf_df.empty:
                chart_df = tf_df

        # Build the interactive chart
        fig = _build_backtest_chart(
            chart_df,
            trades_df,
            fvgs,
            show_fvgs,
            show_decisions,
            show_session_levels,
        )
        st.plotly_chart(fig, width="stretch", config={
            "scrollZoom": True,
            "displayModeBar": True,
            "editable": True,
            "modeBarButtonsToAdd": [
                "drawline", "drawopenpath", "drawclosedpath",
                "drawrect", "drawcircle", "eraseshape",
            ],
        })

    # -- Multi-TF FVG Summary Panel --
    if fvg_summary:
        st.markdown("---")
        st.subheader("Multi-Timeframe FVG Analysis")

        by_tf = fvg_summary.get("by_timeframe", {})
        tf_cols = st.columns(len(MULTI_TF_FVG_TIMEFRAMES))
        for i, tf in enumerate(MULTI_TF_FVG_TIMEFRAMES):
            with tf_cols[i]:
                data = by_tf.get(tf, {})
                st.markdown(f"**{tf.upper()}**")
                st.metric("Active", data.get("active", 0))
                bull = data.get("bullish_active", 0)
                bear = data.get("bearish_active", 0)
                st.caption(f"Bullish: {bull} | Bearish: {bear}")

        # FVG detail table
        if fvgs:
            with st.expander(f"FVG Detail Table ({len(fvgs)} total)"):
                fvg_df = pd.DataFrame(fvgs)
                display_cols = [c for c in ["timeframe", "fvg_type", "top", "bottom",
                                            "size", "status", "confluence_score",
                                            "decision_fvg", "timestamp"] if c in fvg_df.columns]
                if display_cols:
                    st.dataframe(
                        fvg_df[display_cols].sort_values(
                            ["timeframe", "timestamp"], ascending=[True, False]
                        ),
                        width="stretch",
                        hide_index=True,
                    )

    # -- Equity Curve --
    if not equity_df.empty:
        st.markdown("---")
        col_eq, col_dist = st.columns(2, gap="large")

        with col_eq:
            st.subheader("Equity Curve")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=equity_df["datetime"],
                y=equity_df["equity"],
                mode="lines",
                name="Equity",
                line=dict(color=BRAND_PRIMARY, width=2.5),
                fill="tozeroy",
                fillcolor="rgba(88,166,255,0.08)",
            ))
            fig.add_hline(
                y=metrics.initial_balance,
                line_dash="dash",
                line_color=TEXT_SECONDARY,
                annotation_text="Initial Capital",
            )
            fig = apply_plotly_theme(fig)
            fig.update_layout(height=350, yaxis_title="Equity ($)")
            st.plotly_chart(fig, width="stretch")

        with col_dist:
            st.subheader("P&L Distribution")
            if not trades_df.empty:
                pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
                fig_hist = go.Figure(go.Histogram(
                    x=trades_df[pnl_col],
                    nbinsx=20,
                    marker_color=BRAND_PRIMARY,
                    opacity=0.8,
                ))
                fig_hist.add_vline(x=0, line_dash="dash", line_color=SHORT_RED)
                fig_hist = apply_plotly_theme(fig_hist)
                fig_hist.update_layout(
                    height=350, xaxis_title="P&L ($)", yaxis_title="Count"
                )
                st.plotly_chart(fig_hist, width="stretch")

    # -- Detailed Metrics --
    with st.expander("Detailed Metrics"):
        m1, m2 = st.columns(2, gap="large")
        with m1:
            st.markdown("**Performance**")
            st.write(f"- Total P&L: {fmt_currency(metrics.total_pnl)}")
            st.write(f"- Total Trades: {metrics.total_trades}")
            st.write(f"- Win Rate: {metrics.win_rate:.1%}")
            st.write(f"- Profit Factor: {metrics.profit_factor:.2f}")
            st.write(f"- Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
            st.write(f"- Sortino Ratio: {metrics.sortino_ratio:.2f}")
            st.write(f"- Expectancy: {fmt_currency(metrics.expectancy)}")
        with m2:
            st.markdown("**Risk**")
            st.write(
                f"- Max Drawdown: {fmt_currency(metrics.max_drawdown_usd)} "
                f"({metrics.max_drawdown_pct:.1%})"
            )
            st.write(f"- Avg Win: {fmt_currency(metrics.avg_win)}")
            st.write(f"- Avg Loss: {fmt_currency(metrics.avg_loss)}")
            st.write(f"- Largest Win: {fmt_currency(metrics.largest_win)}")
            st.write(f"- Largest Loss: {fmt_currency(metrics.largest_loss)}")
            st.write(f"- Trades/Day: {metrics.trades_per_day:.2f}")
            st.write(f"- Best Day: {fmt_currency(metrics.best_day_pnl)}")
            st.write(f"- Worst Day: {fmt_currency(metrics.worst_day_pnl)}")

    # -- Trade list --
    if not trades_df.empty:
        with st.expander("Trade List"):
            pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
            show_cols = [c for c in [
                "timestamp", "direction", "entry_price", "exit_price",
                "sl_price", "tp_price", pnl_col, "commission",
                "contracts", "reason",
            ] if c in trades_df.columns]
            st.dataframe(
                trades_df[show_cols], width="stretch", hide_index=True,
            )


def _build_backtest_chart(
    df: pd.DataFrame,
    trades_df: pd.DataFrame,
    fvgs: list,
    show_fvg_tfs: list,
    show_decisions_only: bool,
    show_session_levels: bool = True,
) -> go.Figure:
    """
    Build the interactive candlestick chart with FVG zones and trade markers.

    Features:
    - Candlestick OHLC chart
    - Volume subplot
    - FVG zones as colored rectangles
    - Trade entry markers (green up arrow for long, red down arrow for short)
    - Trade exit markers (blue circle)
    - Hover tooltips with trade details
    """
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.8, 0.2],
    )

    # -- Candlestick Chart --
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            increasing_line_color=LONG_GREEN,
            decreasing_line_color=SHORT_RED,
            increasing_fillcolor=LONG_GREEN,
            decreasing_fillcolor=SHORT_RED,
            name="Price",
            showlegend=False,
        ),
        row=1, col=1,
    )

    # -- Previous Session High/Low Levels --
    if show_session_levels and not df.empty:
        try:
            session_df = compute_all_session_levels(df)
            if session_df.empty:
                raise ValueError("No session levels computed")
            last = session_df.iloc[-1]
            x0, x1 = df.index[0], df.index[-1]

            session_specs = [
                ("asia", "#7E57C2"),
                ("london", "#42A5F5"),
                ("ny_am", "#26A69A"),
                ("ny_pm", "#FFA726"),
            ]

            for sname, scolor in session_specs:
                high_col = f"{sname}_high"
                low_col = f"{sname}_low"
                sval_high = last.get(high_col)
                sval_low = last.get(low_col)

                if pd.notna(sval_high):
                    fig.add_shape(
                        type="line",
                        x0=x0, x1=x1,
                        y0=float(sval_high), y1=float(sval_high),
                        line=dict(color=scolor, width=1, dash="dot"),
                        opacity=0.7,
                        row=1, col=1,
                    )
                if pd.notna(sval_low):
                    fig.add_shape(
                        type="line",
                        x0=x0, x1=x1,
                        y0=float(sval_low), y1=float(sval_low),
                        line=dict(color=scolor, width=1, dash="dot"),
                        opacity=0.7,
                        row=1, col=1,
                    )
        except Exception:
            pass

    # -- Volume Bars --
    if "Volume" in df.columns:
        colors = [LONG_GREEN if c >= o else SHORT_RED
                  for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["Volume"],
                marker_color=colors,
                opacity=0.4,
                name="Volume",
                showlegend=False,
            ),
            row=2, col=1,
        )

    # -- FVG Zones as Rectangles --
    if fvgs:
        for fvg in fvgs:
            tf = fvg.get("timeframe", "1h")
            if tf not in show_fvg_tfs:
                continue
            if show_decisions_only and not fvg.get("decision_fvg", False):
                continue

            fvg_type = fvg.get("fvg_type", "bullish")
            colors = FVG_COLORS.get(tf, FVG_COLORS["1h"])
            fill = colors.get(f"{fvg_type}", colors["bullish"])
            border = colors.get(f"{fvg_type}_border", "#888888")

            # Make decision FVGs more prominent
            line_width = 2 if fvg.get("decision_fvg") else 1
            opacity = 1.0 if fvg.get("decision_fvg") else 0.6

            top_val = fvg.get("top", 0)
            bottom_val = fvg.get("bottom", 0)
            ts = fvg.get("timestamp", "")

            # Determine x range for the rectangle
            try:
                fvg_time = pd.to_datetime(ts)
                # Extend FVG zone to the right (show active zone)
                if fvg.get("status") == "active":
                    x_end = df.index[-1] if len(df) > 0 else fvg_time
                else:
                    # Broken FVGs: show for a limited range
                    x_end = fvg_time + pd.Timedelta(hours=24)
            except Exception:
                continue

            fig.add_shape(
                type="rect",
                x0=fvg_time, x1=x_end,
                y0=bottom_val, y1=top_val,
                fillcolor=fill,
                line=dict(color=border, width=line_width),
                opacity=opacity,
                layer="below",
                row=1, col=1,
            )

            # Add FVG label
            label = f"{tf.upper()} {'Bull' if fvg_type == 'bullish' else 'Bear'} FVG"
            if fvg.get("decision_fvg"):
                label += " [DECISION]"
            fig.add_annotation(
                x=fvg_time,
                y=top_val,
                text=label,
                showarrow=False,
                font=dict(size=9, color=border),
                bgcolor="rgba(13,17,23,0.7)",
                bordercolor=border,
                borderwidth=1,
                opacity=opacity,
                row=1, col=1,
            )

    # -- Trade Entry Markers --
    if not trades_df.empty:
        for _, trade in trades_df.iterrows():
            entry_time = trade.get("entry_time") or trade.get("timestamp")
            exit_time = trade.get("exit_time") or trade.get("timestamp")
            entry_price = trade.get("entry_price", 0)
            exit_price = trade.get("exit_price", 0)
            direction = trade.get("direction", "long")
            pnl = trade.get("pnl_net", trade.get("pnl", 0))

            # Entry marker
            entry_color = LONG_GREEN if direction == "long" else SHORT_RED
            entry_symbol = "triangle-up" if direction == "long" else "triangle-down"

            if entry_time is not None and not pd.isna(entry_price):
                fig.add_trace(
                    go.Scatter(
                        x=[pd.to_datetime(entry_time)],
                        y=[entry_price],
                        mode="markers",
                        marker=dict(
                            symbol=entry_symbol,
                            size=14,
                            color=entry_color,
                            line=dict(width=2, color="#FFFFFF"),
                        ),
                        name=f"Entry ({direction.upper()})",
                        showlegend=False,
                        hovertemplate=(
                            f"<b>ENTRY ({direction.upper()})</b><br>"
                            f"Price: {entry_price:.2f}<br>"
                            f"Time: %{{x}}<br>"
                            f"SL: {trade.get('sl_price', 0):.2f}<br>"
                            f"TP: {trade.get('tp_price', 0):.2f}<br>"
                            f"Contracts: {trade.get('contracts', 0)}"
                            "<extra></extra>"
                        ),
                    ),
                    row=1, col=1,
                )

            # Exit marker
            if exit_time is not None and not pd.isna(exit_price):
                exit_color = LONG_GREEN if pnl >= 0 else SHORT_RED
                fig.add_trace(
                    go.Scatter(
                        x=[pd.to_datetime(exit_time)],
                        y=[exit_price],
                        mode="markers",
                        marker=dict(
                            symbol="circle",
                            size=10,
                            color=exit_color,
                            line=dict(width=2, color="#FFFFFF"),
                        ),
                        name="Exit",
                        showlegend=False,
                        hovertemplate=(
                            f"<b>EXIT</b><br>"
                            f"Price: {exit_price:.2f}<br>"
                            f"Time: %{{x}}<br>"
                            f"P&L: ${pnl:.2f}<br>"
                            f"Reason: {trade.get('reason', 'N/A')}"
                            "<extra></extra>"
                        ),
                    ),
                    row=1, col=1,
                )

            # Connect entry to exit with a line
            if entry_time is not None and exit_time is not None:
                line_color = LONG_GREEN if pnl >= 0 else SHORT_RED
                fig.add_trace(
                    go.Scatter(
                        x=[pd.to_datetime(entry_time), pd.to_datetime(exit_time)],
                        y=[entry_price, exit_price],
                        mode="lines",
                        line=dict(color=line_color, width=1, dash="dot"),
                        showlegend=False,
                        hoverinfo="skip",
                    ),
                    row=1, col=1,
                )

    # -- Layout --
    fig = apply_plotly_theme(fig)
    fig.update_layout(
        height=650,
        xaxis_rangeslider_visible=False,
        xaxis2_title="Time",
        yaxis_title="Price",
        yaxis2_title="Volume",
        hovermode="x unified",
        dragmode="zoom",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )

    # Remove range slider
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)

    return fig
