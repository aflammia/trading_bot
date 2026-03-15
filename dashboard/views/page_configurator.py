"""
Page 7: Bot Builder / Configurator — Configurador de Estrategia
Full parameter configuration with tabs, presets, save/load, impact preview.
"""
import streamlit as st
import json

from dashboard.engine import (
    DEFAULT_CONFIG, PRESET_CONFIGS,
    save_config, list_configs, load_config,
)
from dashboard.theme import PURPLE, NEON_GREEN, SUCCESS, WARNING


def render():
    st.title("Bot Builder")
    st.markdown("*Diseña tu propio bot personalizado. Configura cada parámetro a tu estilo.*")

    # ── Load current config ─────────────────────────────────────
    if "active_config" not in st.session_state:
        st.session_state["active_config"] = DEFAULT_CONFIG.copy()

    config = st.session_state["active_config"].copy()

    # ── Preset Selector ─────────────────────────────────────────
    st.markdown(
        "<div class='chuky-section'>",
        unsafe_allow_html=True,
    )

    col_preset, col_load, col_save = st.columns([1, 1, 1], gap="large")

    with col_preset:
        st.markdown("**Quick Presets**")
        # Use separate rows for better spacing
        for name, preset in PRESET_CONFIGS.items():
            if st.button(f"{name}", key=f"preset_{name}", width="stretch"):
                config = preset.copy()
                st.session_state["active_config"] = config
                st.success(f"Preset '{name}' cargado")
                st.rerun()

    with col_load:
        st.markdown("**Saved Configs**")
        saved = list_configs()
        if saved:
            saved_names = [c.get("name", "?") for c in saved]
            sel = st.selectbox("Seleccionar", ["—"] + saved_names, label_visibility="collapsed")
            if sel != "—":
                config = load_config(sel)
                st.session_state["active_config"] = config
                st.rerun()
        else:
            st.caption("No hay configs guardadas aún.")

    with col_save:
        st.markdown("**Save Config**")
        save_name = st.text_input("Nombre", value=config.get("name", "Mi Bot"), label_visibility="collapsed")
        if st.button("Save", width="stretch"):
            config["name"] = save_name
            save_config(config, save_name)
            st.success(f"Config '{save_name}' guardada!")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ── Parameter Tabs ──────────────────────────────────────────
    tab_risk, tab_fvg, tab_structure, tab_sessions, tab_exit, tab_advanced = st.tabs([
        "Risk", "FVG", "Structure", "Sessions", "Exit Rules", "Advanced"
    ])

    with tab_risk:
        st.subheader("Gestión de Riesgo")
        c1, c2 = st.columns(2, gap="large")

        with c1:
            config["initial_capital"] = float(st.number_input(
                "Capital Inicial ($)",
                value=int(config.get("initial_capital", 50000)),
                min_value=10000, max_value=200000, step=5000,
            ))
            config["max_daily_loss"] = float(st.slider(
                "Max Pérdida Diaria ($)",
                min_value=200, max_value=1500,
                value=int(config.get("max_daily_loss", 550)),
                step=50,
                help="Kill switch: si pierdes esto en un día, Chuky para de operar.",
            ))
            config["max_trades_per_day"] = st.slider(
                "Max Trades por Día",
                min_value=1, max_value=5,
                value=int(config.get("max_trades_per_day", 2)),
                help="Máximo de operaciones por sesión.",
            )

        with c2:
            config["default_contracts"] = st.slider(
                "Contratos Default",
                min_value=1, max_value=6,
                value=int(config.get("default_contracts", 3)),
                help="Número de contratos MNQ por trade.",
            )
            config["big_loss_threshold"] = float(st.slider(
                "Big Loss Threshold ($)",
                min_value=200, max_value=1000,
                value=int(config.get("big_loss_threshold", 400)),
                step=50,
                help="Si pierdes esto en 1 trade → no más trades hoy.",
            ))
            config["big_win_threshold"] = float(st.slider(
                "Big Win Threshold ($)",
                min_value=400, max_value=2000,
                value=int(config.get("big_win_threshold", 800)),
                step=100,
                help="Si ganas esto en 1 trade → asegurar y parar.",
            ))

    with tab_fvg:
        st.subheader("Fair Value Gaps (FVG)")
        st.markdown("**Lookback por Timeframe** (velas a escanear en cada TF)")
        c1, c2 = st.columns(2, gap="large")

        with c1:
            config["fvg_lookback_1h"] = st.slider(
                "Lookback 1H (barras)",
                min_value=5, max_value=50,
                value=int(config.get("fvg_lookback_1h", 10)),
                help="Velas de 1H a revisar. ~10 barras = ~10 horas de historia.",
            )
            config["fvg_lookback_5m"] = st.slider(
                "Lookback 5M (barras)",
                min_value=5, max_value=50,
                value=int(config.get("fvg_lookback_5m", 24)),
                help="Velas de 5M a revisar. ~24 barras = ~2 horas de historia.",
            )

        with c2:
            config["fvg_lookback_15m"] = st.slider(
                "Lookback 15M (barras)",
                min_value=5, max_value=50,
                value=int(config.get("fvg_lookback_15m", 16)),
                help="Velas de 15M a revisar. ~16 barras = ~4 horas de historia.",
            )
            config["fvg_lookback_1m"] = st.slider(
                "Lookback 1M (barras)",
                min_value=5, max_value=50,
                value=int(config.get("fvg_lookback_1m", 30)),
                help="Velas de 1M a revisar. ~30 barras = ~30 minutos de historia.",
            )

        st.markdown("**Max FVGs Activos por Timeframe**")
        c1, c2, c3, c4 = st.columns(4, gap="medium")
        with c1:
            config["fvg_max_1h"] = st.slider(
                "Max 1H", min_value=1, max_value=10,
                value=int(config.get("fvg_max_1h", 4)),
                help="Máximo de FVGs activos rastreados en 1H.",
            )
        with c2:
            config["fvg_max_15m"] = st.slider(
                "Max 15M", min_value=1, max_value=10,
                value=int(config.get("fvg_max_15m", 4)),
                help="Máximo de FVGs activos rastreados en 15M.",
            )
        with c3:
            config["fvg_max_5m"] = st.slider(
                "Max 5M", min_value=1, max_value=10,
                value=int(config.get("fvg_max_5m", 3)),
                help="Máximo de FVGs activos rastreados en 5M.",
            )
        with c4:
            config["fvg_max_1m"] = st.slider(
                "Max 1M", min_value=1, max_value=10,
                value=int(config.get("fvg_max_1m", 3)),
                help="Máximo de FVGs activos rastreados en 1M.",
            )

        st.markdown("**Rango de Búsqueda**")
        config["fvg_search_range"] = st.slider(
            "Rango Búsqueda FVG (puntos)",
            min_value=100, max_value=800,
            value=int(config.get("fvg_search_range", 400)),
            step=50,
            help="Distancia máxima desde precio actual para buscar FVGs relevantes.",
        )

    with tab_structure:
        st.subheader("Estructura de Mercado")

        config["structure_lookback"] = st.slider(
            "Lookback Tendencia 4H (velas)",
            min_value=3, max_value=12,
            value=int(config.get("structure_lookback", 6)),
            help="Velas de 4H para determinar tendencia.",
        )
        st.info("El sesgo se calcula desde tendencia 4H + FVG breaks + liquidez — **sin ATR**.")

    with tab_sessions:
        st.subheader("Horarios de Trading")
        st.markdown(
            """
            **Sessiones ICT (Killzones):**
            | Sesión | Horario ET | Notas |
            |--------|-----------|-------|
            | Asia | 20:00 - 00:00 | Solo observar |
            | London | 02:00 - 05:00 | Setup early |
            | NY AM | 09:30 - 11:00 | **Mejor ventana** |
            | NY Lunch | 12:00 - 13:00 | Evitar |
            | NY PM | 13:30 - 16:00 | Segunda oportunidad |
            """
        )
        st.info("The bot operates in the window 08:30 - 16:00 VET (12:30 - 20:00 UTC)")

    with tab_exit:
        st.subheader("Reglas de Salida")
        c1, c2 = st.columns(2, gap="large")

        with c1:
            config["break_even_pct"] = st.slider(
                "Break-Even Trigger (%)",
                min_value=0.20, max_value=0.80,
                value=float(config.get("break_even_pct", 0.60)),
                step=0.05,
                help="Cierra al break-even cuando profit ≥ este % del TP Y un FVG de soporte se rompe.",
            )

        with c2:
            config["close_at_pct"] = st.slider(
                "Cerrar al % del TP",
                min_value=0.70, max_value=1.00,
                value=float(config.get("close_at_pct", 0.90)),
                step=0.05,
                help="Cerrar trade si alcanza este % del take profit.",
            )

        # Validate that break_even fires before close_at
        if config["break_even_pct"] >= config["close_at_pct"]:
            st.warning(
                f"⚠️ Break-Even ({config['break_even_pct']:.0%}) ≥ Cerrar al TP "
                f"({config['close_at_pct']:.0%}): el break-even nunca se activará. "
                "Reduce el Break-Even o sube el Cerrar al %."
            )

    with tab_advanced:
        st.subheader("Configuración Avanzada")
        st.markdown("**JSON completo de la configuración actual:**")
        config_json = json.dumps(config, indent=2, default=str)
        edited_json = st.text_area(
            "Editar JSON",
            value=config_json,
            height=400,
            label_visibility="collapsed",
        )
        if st.button("Apply JSON"):
            try:
                config = json.loads(edited_json)
                st.session_state["active_config"] = config
                st.success("Configuración actualizada desde JSON.")
            except json.JSONDecodeError as e:
                st.error(f"JSON inválido: {e}")

        # Import/Export
        st.markdown("---")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.download_button(
                "Export Config",
                data=json.dumps(config, indent=2, default=str),
                file_name=f"{config.get('name', 'config').replace(' ', '_')}.json",
                mime="application/json",
                width="stretch",
            )
        with c2:
            uploaded = st.file_uploader("Import Config", type=["json"])
            if uploaded:
                try:
                    imported = json.load(uploaded)
                    config = imported
                    st.session_state["active_config"] = config
                    st.success(f"Config '{config.get('name', '?')}' importada!")
                except Exception as e:
                    st.error(f"Error importando: {e}")

    # ── Save back to session ────────────────────────────────────
    st.session_state["active_config"] = config

    # ── Config Summary ──────────────────────────────────────────
    st.markdown("---")
    st.subheader("Current Configuration Summary")
    summary_cols = st.columns(4, gap="medium")
    with summary_cols[0]:
        st.metric("Capital", f"${config.get('initial_capital', 50000):,.0f}")
    with summary_cols[1]:
        st.metric("Contratos", config.get("default_contracts", 3))
    with summary_cols[2]:
        st.metric("Max DD Diario", f"${config.get('max_daily_loss', 550):,.0f}")
    with summary_cols[3]:
        st.metric("Config", config.get("name", "Custom"))

    st.markdown(
        """
        <div class='chuky-card'>
        <h4>Next Step</h4>
        <p>Go to <b>Backtest Lab</b> to run a backtest with this configuration.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
