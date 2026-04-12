"""
Page 9: Reports & Export -- Professional PDF / CSV generation with Gemini AI analysis.
"""
import streamlit as st
import pandas as pd
import json
import io
import os
from datetime import datetime

from dashboard.theme import PURPLE, NEON_GREEN, HOT_PINK


DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
FALLBACK_GEMINI_MODELS = ("gemini-2.5-pro", "gemini-2.5-flash")


def _resolve_gemini_api_key() -> str:
    """Resolve Gemini API key from env or Streamlit secrets."""
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key

    try:
        root_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        if root_key:
            return root_key
    except Exception:
        pass

    try:
        gemini_cfg = st.secrets.get("gemini", None)
        if gemini_cfg is not None and hasattr(gemini_cfg, "get"):
            nested_key = str(gemini_cfg.get("api_key", "")).strip()
            if nested_key:
                return nested_key
    except Exception:
        pass

    return ""


def _resolve_gemini_model() -> str:
    """Resolve Gemini model id from env or Streamlit secrets."""
    default_model = DEFAULT_GEMINI_MODEL

    env_model = os.environ.get("GEMINI_MODEL", "").strip()
    if env_model:
        return env_model

    try:
        root_model = str(st.secrets.get("GEMINI_MODEL", "")).strip()
        if root_model:
            return root_model
    except Exception:
        pass

    try:
        gemini_cfg = st.secrets.get("gemini", None)
        if gemini_cfg is not None and hasattr(gemini_cfg, "get"):
            nested_model = str(gemini_cfg.get("model", "")).strip()
            if nested_model:
                return nested_model
    except Exception:
        pass

    return default_model


def _build_model_candidates(preferred_model: str) -> list[str]:
    """Build ordered candidate models for robust fallback."""
    candidates = [preferred_model] + list(FALLBACK_GEMINI_MODELS)
    unique = []
    for model in candidates:
        m = (model or "").strip()
        if m and m not in unique:
            unique.append(m)
    return unique


def _is_model_not_found_error(error_text: str) -> bool:
    text = (error_text or "").lower()
    return (
        "404" in text
        and ("is not found" in text or "not supported for generatecontent" in text)
    )


def _find_time_col(df: pd.DataFrame) -> str:
    for col in ("exit_time", "entry_time", "timestamp", "datetime"):
        if col in df.columns:
            return col
    return ""


def _compute_streaks(pnls: list[float]) -> tuple[int, int]:
    max_win, max_loss = 0, 0
    run_win, run_loss = 0, 0
    for pnl in pnls:
        if pnl > 0:
            run_win += 1
            run_loss = 0
            max_win = max(max_win, run_win)
        elif pnl < 0:
            run_loss += 1
            run_win = 0
            max_loss = max(max_loss, run_loss)
        else:
            run_win = 0
            run_loss = 0
    return max_win, max_loss


def _build_report_diagnostics(metrics, trades_df: pd.DataFrame, config: dict) -> dict:
    """Build board-level diagnostics and improvement actions from backtest data."""
    diagnostics = {
        "executive_lines": [],
        "direction_lines": [],
        "reason_lines": [],
        "temporal_lines": [],
        "risk_lines": [],
        "gap_lines": [],
        "actions": [],
    }

    if trades_df is None or trades_df.empty:
        diagnostics["executive_lines"].append("No hay operaciones para diagnostico detallado.")
        return diagnostics

    pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
    if pnl_col not in trades_df.columns:
        diagnostics["executive_lines"].append("No se encontro columna de P&L por operacion.")
        return diagnostics

    work = trades_df.copy()
    work[pnl_col] = pd.to_numeric(work[pnl_col], errors="coerce").fillna(0.0)
    pnls = work[pnl_col].tolist()
    max_win_streak, max_loss_streak = _compute_streaks(pnls)

    diagnostics["executive_lines"] = [
        f"Total de operaciones: {len(work)} | Win rate: {metrics.win_rate:.1%} | Profit factor: {metrics.profit_factor:.2f}.",
        f"Drawdown maximo: ${metrics.max_drawdown_usd:,.0f} ({metrics.max_drawdown_usd / 2500 * 100:.0f}% del limite de la cuenta).",
        f"Expectancy: ${metrics.expectancy:+,.2f} por trade | R:R promedio: {metrics.avg_rr_ratio:.2f}.",
        f"Racha ganadora maxima: {max_win_streak} | Racha perdedora maxima: {max_loss_streak}.",
    ]

    if "direction" in work.columns:
        grouped = work.groupby("direction")[pnl_col].agg(["count", "sum", "mean"])
        for direction, row in grouped.sort_values("sum", ascending=False).iterrows():
            mask = work["direction"] == direction
            wr = (work.loc[mask, pnl_col] > 0).mean() if mask.any() else 0.0
            diagnostics["direction_lines"].append(
                f"{direction}: {int(row['count'])} trades | Win rate {wr:.1%} | P&L ${row['sum']:+,.2f} | Avg ${row['mean']:+,.2f}."
            )

    if "reason" in work.columns:
        reasons = work.groupby("reason")[pnl_col].agg(["count", "sum", "mean"]).sort_values("count", ascending=False).head(8)
        for reason, row in reasons.iterrows():
            diagnostics["reason_lines"].append(
                f"{reason}: {int(row['count'])} salidas | P&L ${row['sum']:+,.2f} | Avg ${row['mean']:+,.2f}."
            )

    time_col = _find_time_col(work)
    if time_col:
        ts = pd.to_datetime(work[time_col], errors="coerce")
        valid = work.loc[ts.notna(), [pnl_col]].copy()
        if not valid.empty:
            valid["_ts"] = ts[ts.notna()]
            valid["_hour"] = valid["_ts"].dt.hour
            by_hour = valid.groupby("_hour")[pnl_col].mean().sort_values(ascending=False)
            if not by_hour.empty:
                best_hour = int(by_hour.index[0])
                worst_hour = int(by_hour.index[-1])
                diagnostics["temporal_lines"].append(
                    f"Mejor hora promedio: {best_hour:02d}:00 (avg ${by_hour.iloc[0]:+,.2f} por trade)."
                )
                diagnostics["temporal_lines"].append(
                    f"Peor hora promedio: {worst_hour:02d}:00 (avg ${by_hour.iloc[-1]:+,.2f} por trade)."
                )

            valid["_date"] = valid["_ts"].dt.date
            by_day = valid.groupby("_date")[pnl_col].sum().sort_values(ascending=False)
            if not by_day.empty and abs(metrics.total_pnl) > 1e-9:
                top3 = float(by_day.head(3).sum())
                concentration = abs(top3 / float(metrics.total_pnl))
                diagnostics["temporal_lines"].append(
                    f"Concentracion de resultados: top-3 dias explican {concentration:.1%} del P&L neto."
                )

    # Gap analysis vs governance targets
    targets = [
        ("Profit Factor", metrics.profit_factor, 1.35, "high"),
        ("Sharpe Ratio", metrics.sharpe_ratio, 1.50, "high"),
        ("Win Rate", metrics.win_rate, 0.50, "high"),
        ("R:R promedio", metrics.avg_rr_ratio, 1.40, "high"),
        ("Max Drawdown USD", metrics.max_drawdown_usd, 1000.0, "low"),
    ]
    for name, actual, target, direction in targets:
        if direction == "high":
            gap = max(0.0, target - float(actual))
            diagnostics["gap_lines"].append(
                f"{name}: actual {actual:.2f} | objetivo >= {target:.2f} | brecha {gap:.2f}."
            )
        else:
            gap = max(0.0, float(actual) - target)
            diagnostics["gap_lines"].append(
                f"{name}: actual {actual:,.2f} | objetivo <= {target:,.2f} | exceso {gap:,.2f}."
            )

    max_daily_loss = float(config.get("max_daily_loss", 550))
    if metrics.max_drawdown_usd > 0.70 * 2500:
        diagnostics["actions"].append({
            "priority": "Alta",
            "title": "Reducir presion de riesgo intradia",
            "evidence": f"Drawdown maximo {metrics.max_drawdown_usd/2500:.0%} del limite de cuenta.",
            "action": "Reducir contratos base en 1 y limitar operaciones a setups con confluencia 1H+15M.",
            "impact": "Menor probabilidad de invalidar la cuenta por cola de perdidas.",
        })
    if metrics.profit_factor < 1.2:
        diagnostics["actions"].append({
            "priority": "Alta",
            "title": "Mejorar calidad de entradas",
            "evidence": f"Profit Factor actual {metrics.profit_factor:.2f}.",
            "action": "Eliminar setups sin confirmacion de estructura y exigir distancia minima a liquidez objetivo.",
            "impact": "Aumenta expectativa por trade y reduce ruido operativo.",
        })
    if metrics.avg_rr_ratio < 1.2:
        diagnostics["actions"].append({
            "priority": "Media",
            "title": "Rebalancear TP/SL",
            "evidence": f"R:R promedio {metrics.avg_rr_ratio:.2f}.",
            "action": "Revisar colocacion de TP para priorizar escenarios >=1.4R cuando la estructura lo permita.",
            "impact": "Mejora rentabilidad sin aumentar frecuencia de trading.",
        })
    if metrics.win_rate < 0.45:
        diagnostics["actions"].append({
            "priority": "Media",
            "title": "Filtrar contexto horario y de volatilidad",
            "evidence": f"Win rate actual {metrics.win_rate:.1%}.",
            "action": "Concentrar ejecucion en ventanas historicamente rentables y pausar en horas de menor edge.",
            "impact": "Mayor consistencia y menor dispersion de resultados.",
        })
    if metrics.largest_loss < -max_daily_loss:
        diagnostics["actions"].append({
            "priority": "Alta",
            "title": "Limitar perdida por operacion",
            "evidence": f"Mayor perdida individual ${metrics.largest_loss:+,.2f} supera el maximo diario configurado (${max_daily_loss:,.0f}).",
            "action": "Imponer hard stop por operacion y validar slippage de ejecucion en escenarios de alta volatilidad.",
            "impact": "Reduce eventos extremos que deterioran el equity.",
        })
    if not bool(getattr(metrics, "consistency_check_passed", True)):
        diagnostics["actions"].append({
            "priority": "Media",
            "title": "Mejorar consistencia de P&L diario",
            "evidence": "Fallo de consistencia en distribucion de ganancias por dia.",
            "action": "Reducir variabilidad de sizing y evitar concentrar resultado en pocos dias excepcionales.",
            "impact": "Perfil de riesgo mas defendible ante comite de inversion.",
        })

    if not diagnostics["actions"]:
        diagnostics["actions"].append({
            "priority": "Media",
            "title": "Programa de mejora continua",
            "evidence": "Metricas principales dentro de rangos saludables.",
            "action": "Mantener configuracion y ejecutar revisiones quincenales de drift en win rate, PF y drawdown.",
            "impact": "Sostener robustez operativa ante cambios de mercado.",
        })

    diagnostics["risk_lines"] = [
        f"Max DD vs limite de cuenta: {metrics.max_drawdown_usd / 2500:.0%}.",
        f"Pico de perdida por trade: ${metrics.largest_loss:+,.2f}.",
        f"Trades por dia: {metrics.trades_per_day:.2f}.",
    ]

    return diagnostics


def render():
    st.title("Reportes & Exportacion")
    st.markdown("*Genera informes profesionales y descarga tus datos.*")

    if "backtest_result" not in st.session_state:
        st.warning("Ejecuta un backtest primero en Backtest Lab.")
        return

    result = st.session_state["backtest_result"]
    metrics = result["metrics"]
    trades_df = result["trades_df"]
    config = result.get("config", {})

    tab_pdf, tab_csv, tab_compare = st.tabs([
        "PDF Report", "CSV Export", "Config Comparison"
    ])

    with tab_pdf:
        _render_pdf_report(metrics, trades_df, config)

    with tab_csv:
        _render_csv_export(metrics, trades_df, config)

    with tab_compare:
        _render_config_comparison(config)


# =====================================================================
#  PDF REPORT
# =====================================================================
def _render_pdf_report(metrics, trades_df: pd.DataFrame, config: dict):
    st.subheader("Informe PDF Profesional")

    gemini_key = _resolve_gemini_api_key()
    model_name = _resolve_gemini_model()
    if not gemini_key:
        gemini_key = st.text_input(
            "Gemini API Key (para analisis AI en el PDF)",
            type="password",
            help="Con API key se agrega un analisis profesional generado por Gemini Pro.",
        )
    else:
        st.caption(f"Gemini API key cargada desde entorno/secrets. Modelo: {model_name}")

    include_ai = st.checkbox("Incluir analisis AI (Gemini)", value=bool(gemini_key))

    if st.button("Generar PDF Profesional", type="primary", width="stretch"):
        with st.spinner("Generando informe profesional..."):
            ai_analysis = ""
            if include_ai and gemini_key:
                with st.spinner("Consultando Gemini para analisis profesional..."):
                    ai_analysis = _get_gemini_pdf_analysis(metrics, trades_df, config, gemini_key, model_name=model_name)

            pdf_bytes = _build_professional_pdf(metrics, trades_df, config, ai_analysis)

            if pdf_bytes:
                st.success("PDF generado exitosamente!")
                st.download_button(
                    "Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"chuky_report_{datetime.now():%Y%m%d_%H%M}.pdf",
                    mime="application/pdf",
                    width="stretch",
                )

    # Preview
    st.markdown("---")
    st.markdown("**Vista previa del contenido:**")
    _render_report_preview(metrics, trades_df, config)


def _get_gemini_pdf_analysis(metrics, trades_df, config, api_key: str, model_name: str = "") -> str:
    """Call Gemini to generate professional trading analysis for the PDF."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
        wins = trades_df[trades_df[pnl_col] > 0] if not trades_df.empty else pd.DataFrame()
        losses = trades_df[trades_df[pnl_col] <= 0] if not trades_df.empty else pd.DataFrame()

        # Build streaks
        streaks = []
        current = 0
        for _, row in trades_df.iterrows():
            if row.get(pnl_col, 0) > 0:
                current = max(0, current) + 1
            else:
                current = min(0, current) - 1
            streaks.append(current)
        max_win_streak = max(streaks) if streaks else 0
        max_loss_streak = abs(min(streaks)) if streaks else 0

        prompt = f"""Eres un analista cuantitativo de trading profesional especializado en futuros NQ/MNQ.
Genera un analisis tecnico profesional de este backtest para incluir en un PDF de reporte.
    El analisis debe ser DIRECTO, TECNICO, UTIL y basado SOLO en los datos provistos.
    No inventes metricas, no asumas hechos no observables y no uses afirmaciones sin respaldo en el contexto.
    Escribe en espanol.

DATOS DEL BACKTEST:
- Instrumento: MNQ (Micro E-mini Nasdaq 100 Futures)
- Metodologia: ICT (Inner Circle Trader) - FVGs, Liquidity Sweeps, Market Structure
- Cuenta: OneUpTrader $50,000 | Trailing DD $2,500
- Capital Inicial: ${metrics.initial_balance:,.0f}
- Capital Final: ${metrics.final_balance:,.0f}
- Total Trades: {metrics.total_trades}
- Trades Ganadores: {metrics.winning_trades} | Trades Perdedores: {metrics.losing_trades}
- Win Rate: {metrics.win_rate:.1%}
- P&L Total (neto): ${metrics.total_pnl:+,.2f}
- P&L Bruto: ${metrics.total_pnl_gross:+,.2f}
- Comisiones Totales: ${metrics.total_commission:,.2f}
- Profit Factor: {metrics.profit_factor:.2f}
- Sharpe Ratio: {metrics.sharpe_ratio:.2f}
- Sortino Ratio: {metrics.sortino_ratio:.2f}
- Expectancy: ${metrics.expectancy:+,.2f}/trade
- Avg Win: ${metrics.avg_win:+,.2f}
- Avg Loss: ${metrics.avg_loss:+,.2f}
- Largest Win: ${metrics.largest_win:+,.2f}
- Largest Loss: ${metrics.largest_loss:+,.2f}
- Max Drawdown: ${metrics.max_drawdown_usd:,.2f} ({metrics.max_drawdown_pct:.1%})
- Max DD Duration: {metrics.max_drawdown_duration_days} dias
- Mejor Dia: ${metrics.best_day_pnl:+,.2f}
- Peor Dia: ${metrics.worst_day_pnl:+,.2f}
- Trades/Dia: {metrics.trades_per_day:.2f}
- Avg Trade Duration: {metrics.avg_trade_duration_hours:.1f}h
- Return: {metrics.total_return_pct:.2f}%
- Racha Ganadora Max: {max_win_streak} trades
- Racha Perdedora Max: {max_loss_streak} trades
- DD vs Limite (${metrics.max_drawdown_usd:,.0f} / $2,500): {metrics.max_drawdown_usd/2500*100:.0f}%

CONFIGURACION:
- Contratos: {config.get('default_contracts', 3)}
- Max Daily Loss: ${config.get('max_daily_loss', 550):,.0f}
- FVG Lookback 1H/15M/5M/1M: {config.get('fvg_lookback_1h', 10)}/{config.get('fvg_lookback_15m', 16)}/{config.get('fvg_lookback_5m', 24)}/{config.get('fvg_lookback_1m', 30)}
- Max FVG 1H/15M/5M/1M: {config.get('fvg_max_1h', 4)}/{config.get('fvg_max_15m', 4)}/{config.get('fvg_max_5m', 3)}/{config.get('fvg_max_1m', 3)}
- Break Even: {config.get('break_even_pct', 0.60):.0%}

Estructura tu respuesta EXACTAMENTE asi (usa estos titulos):

1. RESUMEN EJECUTIVO
(2-4 oraciones con conclusion general para comite de socios)

2. ALCANCE Y CONFIABILIDAD DEL BACKTEST
- Calidad y limites de los datos
- Sesgos potenciales o restricciones del analisis

3. DESEMPENO Y PERFIL DE RIESGO
- Win Rate, Profit Factor, Sharpe, Sortino y Expectancy
- Drawdown absoluto/relativo y riesgo de continuidad

4. COMPORTAMIENTO OPERATIVO DEL BOT
- Patrones de entrada/salida observables
- Rachas, concentracion de resultados y estabilidad diaria

5. FALLAS PRINCIPALES DETECTADAS
(2-5 fallas concretas, cada una con evidencia numerica)

6. PLAN DE MEJORA PRIORIZADO
(3-6 acciones concretas, cada una con impacto esperado y horizonte 30/60/90 dias)

7. VEREDICTO DE GOBERNANZA
(APTO / APTO CON CONDICIONES / NO APTO con justificacion tecnica)

Responde SOLO con el analisis, sin markdown headers (#), usa texto plano."""

        preferred_model = model_name or _resolve_gemini_model()
        last_error = None
        for candidate_model in _build_model_candidates(preferred_model):
            try:
                model = genai.GenerativeModel(
                    candidate_model,
                    generation_config={
                        "temperature": 0.0,
                        "top_p": 0.95,
                    },
                )
                response = model.generate_content(prompt)
                return response.text or ""
            except Exception as model_error:
                last_error = model_error
                if not _is_model_not_found_error(str(model_error)):
                    raise

        if last_error is not None:
            raise last_error

        return ""

    except ImportError:
        return (
            "[Error: google-generativeai no esta instalada en el despliegue. "
            "Agrega 'google-generativeai>=0.8.5' en requirements.txt y vuelve a desplegar.]"
        )
    except Exception as e:
        return f"[Error al generar analisis AI: {str(e)}]"


def _build_professional_pdf(metrics, trades_df, config, ai_analysis: str = "") -> bytes:
    """Build professional trading report PDF using fpdf2."""
    try:
        from fpdf import FPDF

        _CHAR_MAP = {
            '\u2014': '--', '\u2013': '-', '\u2018': "'", '\u2019': "'",
            '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u2022': '*',
            '\u2192': '->', '\u2190': '<-', '\u2264': '<=', '\u2265': '>=',
            '\u00b1': '+/-', '\u2260': '!=', '\u221e': 'inf',
            '\U0001f608': '', '\U0001f4c8': '', '\U0001f4c9': '',
            '\u2705': '[OK]', '\u274c': '[X]', '\u26a0\ufe0f': '[!]', '\u26a0': '[!]',
            '\u00bf': '\u00bf', '\u00a1': '\u00a1',
        }

        def _safe(text: str) -> str:
            for orig, repl in _CHAR_MAP.items():
                text = text.replace(orig, repl)
            return text.encode('latin-1', errors='replace').decode('latin-1')

        # Corporate palette
        C_PURPLE = (22, 55, 97)
        C_DARK = (15, 23, 42)
        C_WHITE = (255, 255, 255)
        C_LIGHT_GRAY = (240, 240, 240)
        C_TEXT = (45, 55, 72)
        C_GREEN = (0, 200, 83)
        C_RED = (244, 67, 54)
        C_HEADER_BG = (22, 55, 97)

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        diagnostics = _build_report_diagnostics(metrics, trades_df, config)

        # ── COVER PAGE ──────────────────────────────────────────
        pdf.add_page()
        pdf.set_fill_color(*C_DARK)
        pdf.rect(0, 0, 210, 297, 'F')

        # Accent bars
        pdf.set_fill_color(*C_PURPLE)
        pdf.rect(0, 100, 210, 4, 'F')
        pdf.rect(0, 180, 210, 2, 'F')

        pdf.set_text_color(*C_PURPLE)
        pdf.set_font("Helvetica", "B", 36)
        pdf.ln(40)
        pdf.cell(0, 16, "CHUKY BOT", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "", 14)
        pdf.set_text_color(200, 200, 200)
        pdf.ln(5)
        pdf.cell(0, 10, "Backtest Governance Report", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(50)
        pdf.set_font("Helvetica", "", 12)
        pdf.set_text_color(180, 180, 180)
        pdf.cell(0, 8, _safe(f"Fecha: {datetime.now():%Y-%m-%d %H:%M}"), align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, "Instrumento: MNQ Futures (Micro E-mini Nasdaq)", align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, "Metodologia: ICT (Inner Circle Trader)", align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, "Cuenta: OneUpTrader $50,000 | Trailing DD $2,500", align="C",
                 new_x="LMARGIN", new_y="NEXT")

        pdf.ln(24)
        pdf.set_text_color(170, 180, 200)
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 10, "Documento tecnico para revision de socios y comite de riesgo.", align="C",
             new_x="LMARGIN", new_y="NEXT")

        # ── PAGE 2: EXECUTIVE SUMMARY ───────────────────────────
        def _usable_width() -> float:
            return max(40.0, pdf.w - pdf.l_margin - pdf.r_margin)

        def _mc(text: str, line_h: float = 5.0):
            # Always reset x and use explicit width to avoid FPDF "Not enough horizontal space".
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(_usable_width(), line_h, _safe(text), new_x="LMARGIN", new_y="NEXT")

        def _section_header(title):
            pdf.set_x(pdf.l_margin)
            pdf.set_fill_color(*C_PURPLE)
            pdf.set_text_color(*C_WHITE)
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, _safe(f"  {title}"), fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
            pdf.set_text_color(*C_TEXT)

        def _kv(label, value, bold_value=False):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(55, 7, _safe(label))
            pdf.set_font("Helvetica", "B" if bold_value else "", 10)
            pdf.cell(0, 7, _safe(str(value)), new_x="LMARGIN", new_y="NEXT")

        def _subheader(title: str):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*C_PURPLE)
            pdf.cell(0, 8, _safe(title), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*C_TEXT)

        pdf.add_page()
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(0, 0, 210, 297, 'F')

        _section_header("RESUMEN EJECUTIVO")
        pdf.set_font("Helvetica", "", 10)

        # Verdict box
        pnl_positive = metrics.total_pnl >= 0
        pdf.set_fill_color(*(C_GREEN if pnl_positive else C_RED))
        pdf.set_text_color(*C_WHITE)
        pdf.set_font("Helvetica", "B", 12)
        verdict = "PROFITABLE" if pnl_positive else "NOT PROFITABLE"
        pdf.cell(0, 10, _safe(f"  RESULTADO: {verdict}"), fill=True,
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_text_color(*C_TEXT)

        # Quick KPIs
        pdf.set_font("Helvetica", "", 10)
        kpis = [
            ("Capital Inicial", f"${metrics.initial_balance:,.0f}"),
            ("Capital Final", f"${metrics.final_balance:,.0f}"),
            ("Retorno", f"{metrics.total_return_pct:+.2f}%"),
            ("P&L Neto", f"${metrics.total_pnl:+,.2f}"),
            ("Total Trades", f"{metrics.total_trades}"),
            ("Win Rate", f"{metrics.win_rate:.1%}"),
            ("Profit Factor", f"{metrics.profit_factor:.2f}"),
            ("Sharpe Ratio", f"{metrics.sharpe_ratio:.2f}"),
            ("Sortino Ratio", f"{metrics.sortino_ratio:.2f}"),
            ("Max Drawdown", f"${metrics.max_drawdown_usd:,.2f} ({metrics.max_drawdown_pct:.1%})"),
        ]
        for label, value in kpis:
            _kv(label, value, bold_value=True)

        # ── DETAILED METRICS ────────────────────────────────────
        pdf.ln(6)
        _section_header("METRICAS DETALLADAS")

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(0, 8, "P&L Analysis", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*C_TEXT)

        pnl_rows = [
            ("P&L Bruto", f"${metrics.total_pnl_gross:+,.2f}"),
            ("Comisiones Totales", f"${metrics.total_commission:,.2f}"),
            ("P&L Neto", f"${metrics.total_pnl:+,.2f}"),
            ("Avg Win", f"${metrics.avg_win:+,.2f}"),
            ("Avg Loss", f"${metrics.avg_loss:+,.2f}"),
            ("Largest Win", f"${metrics.largest_win:+,.2f}"),
            ("Largest Loss", f"${metrics.largest_loss:+,.2f}"),
            ("Expectancy", f"${metrics.expectancy:+,.2f}/trade"),
        ]
        for label, value in pnl_rows:
            _kv(label, value)

        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(0, 8, "Risk Analysis", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*C_TEXT)

        dd_pct_limit = metrics.max_drawdown_usd / 2500 * 100
        risk_rows = [
            ("Max Drawdown", f"${metrics.max_drawdown_usd:,.2f}"),
            ("Max DD % del Capital", f"{metrics.max_drawdown_pct:.1%}"),
            ("DD vs Limite $2,500", f"{dd_pct_limit:.0f}%"),
            ("DD Duration", f"{metrics.max_drawdown_duration_days} dias"),
            ("Avg Drawdown", f"${metrics.avg_drawdown_usd:,.2f}"),
            ("Mejor Dia", f"${metrics.best_day_pnl:+,.2f}"),
            ("Peor Dia", f"${metrics.worst_day_pnl:+,.2f}"),
        ]
        for label, value in risk_rows:
            _kv(label, value)

        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(0, 8, "Trading Activity", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*C_TEXT)

        activity_rows = [
            ("Trades Ganadores", f"{metrics.winning_trades}"),
            ("Trades Perdedores", f"{metrics.losing_trades}"),
            ("R:R Ratio (avg)", f"{metrics.avg_rr_ratio:.2f}"),
            ("Trades/Dia", f"{metrics.trades_per_day:.2f}"),
            ("Avg Duration", f"{metrics.avg_trade_duration_hours:.1f}h"),
            ("Consistency Check", f"{'PASSED' if metrics.consistency_check_passed else 'FAILED'}"),
        ]
        for label, value in activity_rows:
            _kv(label, value)

        pdf.ln(4)
        _subheader("Observaciones ejecutivas")
        pdf.set_font("Helvetica", "", 9)
        for line in diagnostics.get("executive_lines", []):
            _mc(f"- {line}", line_h=5)

        # ── OPERATING DIAGNOSTICS ─────────────────────────────
        pdf.add_page()
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(0, 0, 210, 297, 'F')
        _section_header("DIAGNOSTICO OPERATIVO DEL BOT")
        pdf.set_font("Helvetica", "", 9)

        _subheader("1) Comportamiento por direccion")
        direction_lines = diagnostics.get("direction_lines", [])
        if direction_lines:
            for line in direction_lines:
                _mc(f"- {line}", line_h=5)
        else:
            _mc("- No hay datos suficientes de direccion para analisis.", line_h=5)

        pdf.ln(2)
        _subheader("2) Motivos de salida y calidad de ejecucion")
        reason_lines = diagnostics.get("reason_lines", [])
        if reason_lines:
            for line in reason_lines:
                _mc(f"- {line}", line_h=5)
        else:
            _mc("- No hay datos de motivos de salida para analisis.", line_h=5)

        pdf.ln(2)
        _subheader("3) Patrones temporales")
        temporal_lines = diagnostics.get("temporal_lines", [])
        if temporal_lines:
            for line in temporal_lines:
                _mc(f"- {line}", line_h=5)
        else:
            _mc("- No hay timestamps validos para analisis horario/diario.", line_h=5)

        pdf.ln(2)
        _subheader("4) Exposicion de riesgo")
        for line in diagnostics.get("risk_lines", []):
            _mc(f"- {line}", line_h=5)

        # ── IMPROVEMENT ROADMAP ───────────────────────────────
        pdf.add_page()
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(0, 0, 210, 297, 'F')
        _section_header("MARGENES DE MEJORA Y PLAN DE ACCION")

        _subheader("Gap analysis contra objetivos de gestion")
        pdf.set_font("Helvetica", "", 9)
        for line in diagnostics.get("gap_lines", []):
            _mc(f"- {line}", line_h=5)

        pdf.ln(2)
        _subheader("Plan de mejora priorizado")
        for idx, action in enumerate(diagnostics.get("actions", []), start=1):
            _mc(f"{idx}. [{action['priority']}] {action['title']}", line_h=5)
            _mc(f"   Evidencia: {action['evidence']}", line_h=5)
            _mc(f"   Accion recomendada: {action['action']}", line_h=5)
            _mc(f"   Impacto esperado: {action['impact']}", line_h=5)
            pdf.ln(1)

        # ── TRADES TABLE ────────────────────────────────────────
        if not trades_df.empty:
            pdf.add_page("L")
            pdf.set_fill_color(*C_WHITE)
            pdf.rect(0, 0, 297, 210, 'F')
            _section_header("LISTA DE TRADES")

            pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
            show_cols = ["direction", "entry_price", "exit_price", "sl_price",
                         "tp_price", pnl_col, "contracts", "reason"]
            available = [c for c in show_cols if c in trades_df.columns]
            col_labels = {
                "direction": "Dir", "entry_price": "Entry", "exit_price": "Exit",
                "sl_price": "SL", "tp_price": "TP", pnl_col: "P&L Net",
                "contracts": "Qty", "reason": "Exit Reason",
            }
            col_widths = {
                "direction": 18, "entry_price": 32, "exit_price": 32,
                "sl_price": 32, "tp_price": 32, pnl_col: 32,
                "contracts": 16, "reason": 40,
            }

            # Header row
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_fill_color(*C_HEADER_BG)
            pdf.set_text_color(*C_WHITE)
            for col in available:
                pdf.cell(col_widths.get(col, 30), 7,
                         _safe(col_labels.get(col, col)), border=1, fill=True)
            pdf.ln()

            # Data rows
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*C_TEXT)
            for idx, (_, row) in enumerate(trades_df.iterrows()):
                if idx % 2 == 0:
                    pdf.set_fill_color(*C_LIGHT_GRAY)
                else:
                    pdf.set_fill_color(*C_WHITE)

                for col in available:
                    val = row[col]
                    if isinstance(val, float):
                        text = f"{val:,.2f}"
                    else:
                        text = str(val)[:20]
                    # Color P&L
                    if col == pnl_col and isinstance(val, (int, float)):
                        pdf.set_text_color(*(C_GREEN if val >= 0 else C_RED))
                    else:
                        pdf.set_text_color(*C_TEXT)
                    pdf.cell(col_widths.get(col, 30), 6,
                             _safe(text), border=1, fill=True)
                pdf.ln()

        # ── CONFIGURATION ───────────────────────────────────────
        pdf.add_page()
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(0, 0, 210, 297, 'F')
        _section_header("CONFIGURACION DEL BOT")

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*C_TEXT)

        config_groups = [
            ("Capital & Riesgo", [
                ("Capital Inicial", f"${config.get('initial_capital', 50000):,.0f}"),
                ("Contratos", f"{config.get('default_contracts', 3)}"),
                ("Max Daily Loss", f"${config.get('max_daily_loss', 550):,.0f}"),
                ("Max Trades/Dia", f"{config.get('max_trades_per_day', 2)}"),
            ]),
            ("Entry (ICT)", [
                ("FVG Lookback 1H/15M/5M/1M", f"{config.get('fvg_lookback_1h', 10)}/{config.get('fvg_lookback_15m', 16)}/{config.get('fvg_lookback_5m', 24)}/{config.get('fvg_lookback_1m', 30)}"),
                ("Max FVG 1H/15M/5M/1M", f"{config.get('fvg_max_1h', 4)}/{config.get('fvg_max_15m', 4)}/{config.get('fvg_max_5m', 3)}/{config.get('fvg_max_1m', 3)}"),
                ("FVG Search Range", f"{config.get('fvg_search_range', 400)} pts"),
                ("Structure Lookback", f"{config.get('structure_lookback', 6)}"),
            ]),
            ("Exit Management", [
                ("SL Placement", "FVG boundary (sin buffer)"),
                ("TP Source", "Liquidez (PDH/PDL/Swings)"),
                ("Break Even @", f"{config.get('break_even_pct', 0.60):.0%} + FVG break"),
                ("Close @ TP %", f"{config.get('close_at_pct', 0.90):.0%}"),
            ]),
        ]

        for group_name, items in config_groups:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*C_PURPLE)
            pdf.cell(0, 8, _safe(group_name), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*C_TEXT)
            for label, value in items:
                _kv(label, value)
            pdf.ln(3)

        # ── AI ANALYSIS ─────────────────────────────────────────
        if ai_analysis and not ai_analysis.startswith("[Error"):
            pdf.add_page()
            pdf.set_fill_color(*C_WHITE)
            pdf.rect(0, 0, 210, 297, 'F')
            _section_header("ANALISIS PROFESIONAL (AI)")

            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*C_TEXT)

            for line in ai_analysis.split("\n"):
                line = line.strip()
                if not line:
                    pdf.ln(3)
                    continue

                # Detect section headers (numbered like "1. RESUMEN" etc.)
                if (line and len(line) < 80 and
                    (line[0].isdigit() or line.isupper())):
                    pdf.ln(3)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(*C_PURPLE)
                    _mc(line, line_h=6)
                    pdf.set_font("Helvetica", "", 9)
                    pdf.set_text_color(*C_TEXT)
                elif line.startswith("-") or line.startswith("*"):
                    _mc(f"  {line}", line_h=5)
                else:
                    _mc(line, line_h=5)

        # ── DISCLAIMER ──────────────────────────────────────────
        pdf.add_page()
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(0, 0, 210, 297, 'F')
        _section_header("DISCLAIMER")

        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(120, 120, 120)
        disclaimer = (
            "Este reporte fue generado automaticamente por El Chuky Bot. "
            "Los resultados mostrados corresponden a un backtest historico y NO garantizan "
            "rendimientos futuros. El trading de futuros conlleva riesgo sustancial de perdida. "
            "Resultados pasados no son indicativos de resultados futuros. "
            "Los datos de mercado utilizados provienen de Yahoo Finance (NQ=F como proxy de MNQ) "
            "y pueden diferir de los datos reales del broker. "
            "Use esta informacion bajo su propio riesgo y criterio."
        )
        _mc(disclaimer, line_h=5)

        # Return as bytes (not bytearray) -- fixes StreamlitAPIException
        output = pdf.output()
        if isinstance(output, bytearray):
            return bytes(output)
        return output

    except ImportError:
        st.error("Instala fpdf2: pip install fpdf2")
        return b""
    except Exception as e:
        st.error(f"Error generando PDF: {e}")
        return b""


def _render_report_preview(metrics, trades_df, config):
    """Show in-app preview of report content."""
    with st.expander("Metricas", expanded=True):
        cols = st.columns(4, gap="medium")
        cols[0].metric("Trades", metrics.total_trades)
        cols[1].metric("Win Rate", f"{metrics.win_rate:.1%}")
        cols[2].metric("P&L", f"${metrics.total_pnl:+,.2f}")
        cols[3].metric("Sharpe", f"{metrics.sharpe_ratio:.2f}")

        cols2 = st.columns(4, gap="medium")
        cols2[0].metric("Profit Factor", f"{metrics.profit_factor:.2f}")
        cols2[1].metric("Max DD", f"${metrics.max_drawdown_usd:,.0f}")
        cols2[2].metric("Expectancy", f"${metrics.expectancy:+,.2f}")
        cols2[3].metric("Sortino", f"{metrics.sortino_ratio:.2f}")

    with st.expander("Trades Recientes"):
        if not trades_df.empty:
            pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
            show_cols = [c for c in ["direction", "entry_price", "exit_price",
                                      pnl_col, "contracts", "reason"]
                         if c in trades_df.columns]
            st.dataframe(trades_df[show_cols].tail(10), width="stretch")
        else:
            st.info("Sin trades disponibles.")

    with st.expander("Configuracion"):
        st.json(config)


# =====================================================================
#  CSV EXPORT
# =====================================================================
def _render_csv_export(metrics, trades_df: pd.DataFrame, config: dict):
    st.subheader("Exportar Datos CSV")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("**Trades**")
        st.markdown(f"{len(trades_df)} trades disponibles")
        if not trades_df.empty:
            csv_trades = trades_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Descargar Trades CSV",
                data=csv_trades,
                file_name=f"chuky_trades_{datetime.now():%Y%m%d}.csv",
                mime="text/csv",
                width="stretch",
            )

    with col2:
        st.markdown("**Equity Curve**")
        pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
        if not trades_df.empty and pnl_col in trades_df.columns:
            initial = config.get("initial_capital", 50000)
            equity = trades_df[[pnl_col]].copy()
            equity.columns = ["pnl"]
            equity["cumulative_pnl"] = equity["pnl"].cumsum()
            equity["equity"] = initial + equity["cumulative_pnl"]
            equity["trade_num"] = range(1, len(equity) + 1)

            csv_equity = equity.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Descargar Equity CSV",
                data=csv_equity,
                file_name=f"chuky_equity_{datetime.now():%Y%m%d}.csv",
                mime="text/csv",
                width="stretch",
            )
        else:
            st.info("Sin datos de equity.")

    st.markdown("---")

    # Metrics summary CSV
    st.markdown("**Metricas Resumen**")
    metrics_dict = {
        "total_trades": metrics.total_trades,
        "win_rate": round(metrics.win_rate, 4),
        "total_pnl": round(metrics.total_pnl, 2),
        "profit_factor": round(metrics.profit_factor, 2),
        "sharpe_ratio": round(metrics.sharpe_ratio, 2),
        "sortino_ratio": round(metrics.sortino_ratio, 2),
        "max_drawdown_usd": round(metrics.max_drawdown_usd, 2),
        "max_drawdown_pct": round(metrics.max_drawdown_pct, 4),
        "expectancy": round(metrics.expectancy, 2),
        "avg_win": round(metrics.avg_win, 2),
        "avg_loss": round(metrics.avg_loss, 2),
        "largest_win": round(metrics.largest_win, 2),
        "largest_loss": round(metrics.largest_loss, 2),
    }
    metrics_df = pd.DataFrame([metrics_dict])
    csv_metrics = metrics_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Descargar Metricas CSV",
        data=csv_metrics,
        file_name=f"chuky_metrics_{datetime.now():%Y%m%d}.csv",
        mime="text/csv",
        width="stretch",
    )

    # Config JSON download
    st.markdown("---")
    st.markdown("**Configuracion JSON**")
    config_json = json.dumps(config, indent=2, default=str).encode("utf-8")
    st.download_button(
        "Descargar Config JSON",
        data=config_json,
        file_name=f"chuky_config_{datetime.now():%Y%m%d}.json",
        mime="application/json",
        width="stretch",
    )


# =====================================================================
#  CONFIG COMPARISON
# =====================================================================
def _render_config_comparison(current_config: dict):
    st.subheader("Comparar Configuraciones")
    st.markdown("Compara tu configuracion actual con una guardada.")

    from dashboard.engine import list_configs, load_config, PRESET_CONFIGS

    saved_configs = list_configs()
    saved_names = [c.get("name", "?") for c in saved_configs if isinstance(c, dict)]
    presets = list(PRESET_CONFIGS.keys())
    all_options = presets + saved_names

    if not all_options:
        st.info("No hay otras configuraciones para comparar. "
                "Guarda alguna en el Bot Builder primero.")
        return

    selected = st.selectbox("Comparar con:", all_options)

    if selected in PRESET_CONFIGS:
        compare_config = PRESET_CONFIGS[selected].copy()
    else:
        compare_config = load_config(selected)

    if compare_config is None:
        st.error("No se pudo cargar la configuracion.")
        return

    all_keys = sorted(set(list(current_config.keys()) + list(compare_config.keys())))

    rows = []
    for key in all_keys:
        val_current = current_config.get(key, "--")
        val_compare = compare_config.get(key, "--")
        changed = str(val_current) != str(val_compare)
        rows.append({
            "Parametro": key,
            "Actual": str(val_current),
            selected: str(val_compare),
            "Cambio": "SI" if changed else "",
        })

    df = pd.DataFrame(rows)

    show_only_diff = st.checkbox("Mostrar solo diferencias", value=True)
    if show_only_diff:
        df = df[df["Cambio"] == "SI"]

    if df.empty:
        st.success("Las configuraciones son identicas.")
    else:
        st.dataframe(df, width="stretch", hide_index=True)
        st.caption(f"{len(df)} parametros diferentes.")
