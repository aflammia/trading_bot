"""
Page 8: AI Analyst -- Chat with Gemini AI Trading Expert.
Uses Google Gemini API for professional trading analysis.
"""
import streamlit as st
import os
import pandas as pd
from datetime import datetime

from dashboard.theme import PURPLE, NEON_GREEN, HOT_PINK


def render():
    st.title("AI Analyst -- Chuky AI")
    st.markdown("*Preguntale al Chuky sobre tu estrategia, trades y rendimiento.*")

    # ── API Key Setup ───────────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "Gemini API Key",
            type="password",
            help="Ingresa tu API key de Google Gemini para activar el AI Analyst. "
                 "Sin API key, el chat funciona con respuestas pre-programadas.",
        )

    # ── Chat History ────────────────────────────────────────────
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # ── Backtest handoff from Backtest Lab ─────────────────────
    prefill_prompt = st.session_state.get("ai_prefill_prompt")
    if prefill_prompt:
        _handle_message(prefill_prompt, api_key)
        st.session_state.pop("ai_prefill_prompt", None)
        st.success("Contexto del ultimo backtest cargado en el chat.")

    # ── Quick Questions ─────────────────────────────────────────
    st.markdown("**Preguntas Rapidas:**")
    quick_qs = st.columns(4, gap="medium")
    quick_questions = [
        "Analiza mi rendimiento general",
        "Cual es mi peor patron de trading?",
        "Como puedo mejorar mi win rate?",
        "Evalua mi nivel de riesgo",
    ]
    for i, q in enumerate(quick_questions):
        with quick_qs[i]:
            if st.button(q, width="stretch", key=f"quick_{i}"):
                _handle_message(q, api_key)
                st.rerun()

    st.markdown("---")

    # ── Chat Display ────────────────────────────────────────────
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state["chat_history"]:
            if msg["role"] == "user":
                st.chat_message("user").markdown(msg["content"])
            else:
                st.chat_message("assistant").markdown(msg["content"])

    # ── Chat Input ──────────────────────────────────────────────
    user_input = st.chat_input("Preguntale al Chuky...")
    if user_input:
        _handle_message(user_input, api_key)
        st.rerun()

    # ── Clear Chat ──────────────────────────────────────────────
    if st.session_state["chat_history"]:
        if st.button("Limpiar Chat"):
            st.session_state["chat_history"] = []
            st.rerun()


def _handle_message(user_msg: str, api_key: str = ""):
    """Process a user message and generate AI response."""
    st.session_state["chat_history"].append({
        "role": "user",
        "content": user_msg,
    })

    context = _build_context()

    if api_key:
        response = _call_gemini(user_msg, context, api_key)
    else:
        response = _generate_local_response(user_msg, context)

    st.session_state["chat_history"].append({
        "role": "assistant",
        "content": response,
    })


def _build_context() -> str:
    """Build context string from current backtest results."""
    if "backtest_result" not in st.session_state:
        return "No hay resultados de backtest disponibles. El trader aun no ha ejecutado ningun backtest."

    result = st.session_state["backtest_result"]
    metrics = result["metrics"]
    trades_df = result["trades_df"]
    config = result.get("config", {})
    fvgs = result.get("fvgs", [])
    fvg_summary = result.get("fvg_summary", {})
    equity_df = result.get("equity_curve", pd.DataFrame())

    pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
    decision_fvgs = len([f for f in fvgs if f.get("decision_fvg")])
    equity_points = len(equity_df) if isinstance(equity_df, pd.DataFrame) else 0
    equity_last = (
        float(equity_df["equity"].iloc[-1])
        if isinstance(equity_df, pd.DataFrame)
        and not equity_df.empty
        and "equity" in equity_df.columns
        else metrics.final_balance
    )

    ctx = f"""CONTEXTO DEL BACKTEST:
- Config: {config.get('name', 'Default')}
- Capital Inicial: ${metrics.initial_balance:,.0f}
- Capital Final: ${metrics.final_balance:,.0f}
- Total Trades: {metrics.total_trades}
- Trades Ganadores: {metrics.winning_trades} | Perdedores: {metrics.losing_trades}
- Win Rate: {metrics.win_rate:.1%}
- P&L Total (neto): ${metrics.total_pnl:+,.2f}
- P&L Bruto: ${metrics.total_pnl_gross:+,.2f}
- Comisiones: ${metrics.total_commission:,.2f}
- Profit Factor: {metrics.profit_factor:.2f}
- Sharpe Ratio: {metrics.sharpe_ratio:.2f}
- Sortino Ratio: {metrics.sortino_ratio:.2f}
- Max Drawdown: ${metrics.max_drawdown_usd:,.2f} ({metrics.max_drawdown_pct:.1%})
- Avg Win: ${metrics.avg_win:+,.2f}
- Avg Loss: ${metrics.avg_loss:+,.2f}
- Largest Win: ${metrics.largest_win:+,.2f}
- Largest Loss: ${metrics.largest_loss:+,.2f}
- Expectancy: ${metrics.expectancy:+,.2f} por trade
- Trades/Dia: {metrics.trades_per_day:.2f}
- Return: {metrics.total_return_pct:.2f}%
- Mejor Dia: ${metrics.best_day_pnl:+,.2f}
- Peor Dia: ${metrics.worst_day_pnl:+,.2f}
- Avg R:R: {metrics.avg_rr_ratio:.2f}
- DD Duration: {metrics.max_drawdown_duration_days} dias

CONTEXTO FVG MULTI-TF:
- Total FVGs detectados: {len(fvgs)}
- Decision FVGs: {decision_fvgs}
- Resumen por timeframe: {fvg_summary.get('by_timeframe', {})}

EQUITY CURVE:
- Puntos de equity: {equity_points}
- Equity final registrada: ${equity_last:,.2f}

CONFIGURACION:
- Contratos: {config.get('default_contracts', 3)}
- Max Daily Loss: ${config.get('max_daily_loss', 550):,.0f}
- Max Trades/Dia: {config.get('max_trades_per_day', 2)}
- FVG Lookback 1H/15M/5M/1M: {config.get('fvg_lookback_1h', 10)}/{config.get('fvg_lookback_15m', 16)}/{config.get('fvg_lookback_5m', 24)}/{config.get('fvg_lookback_1m', 30)}
- Max FVG 1H/15M/5M/1M: {config.get('fvg_max_1h', 4)}/{config.get('fvg_max_15m', 4)}/{config.get('fvg_max_5m', 3)}/{config.get('fvg_max_1m', 3)}
- Break Even: {config.get('break_even_pct', 0.60):.0%}
- Close at TP: {config.get('close_at_pct', 0.90):.0%}

CUENTA: OneUpTrader $50,000 | MNQ Futures | Trailing DD $2,500
METODOLOGIA: ICT (Fair Value Gaps, Liquidity Sweeps, Market Structure)"""

    # Add trade details
    if not trades_df.empty and len(trades_df) <= 50:
        ctx += "\n\nULTIMOS TRADES:"
        for _, row in trades_df.tail(20).iterrows():
            direction = row.get("direction", "?")
            pnl = row.get(pnl_col, 0)
            reason = row.get("reason", "?")
            ctx += f"\n  Trade: {direction} | P&L: ${pnl:+,.2f} | Exit: {reason}"

    return ctx


def _call_gemini(user_msg: str, context: str, api_key: str) -> str:
    """Call Google Gemini 3.1 Pro for response."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        system_instruction = f"""Eres "Chuky AI", el asistente de trading del bot "El Chuky Bot".
Tu personalidad: directo, tecnico, un poco malandro pero profesional. Hablas en espanol con toque venezolano.
Eres experto en:
- Metodologia ICT (Inner Circle Trader): FVGs, Liquidity Sweeps, Market Structure, Killzones
- Analisis cuantitativo: Sharpe, Profit Factor, Monte Carlo, Walk-Forward
- Gestion de riesgo para prop firms (OneUpTrader)
- Backtesting y optimizacion de estrategias

Reglas:
1. Responde de forma concisa pero informativa. Usa datos concretos del contexto.
2. Si el rendimiento es malo, se honesto pero constructivo.
3. Usa numeros y porcentajes concretos, no generalidades.
4. Si te preguntan algo que no sabes, di que necesitas mas datos.
5. Responde en espanol siempre.

{context}"""

        model = genai.GenerativeModel(
            'gemini-2.0-flash',
            system_instruction=system_instruction,
        )

        # Build multi-turn chat history
        history = []
        for m in st.session_state["chat_history"][-10:]:
            role = "user" if m["role"] == "user" else "model"
            history.append({"role": role, "parts": [m["content"]]})

        chat = model.start_chat(history=history)
        response = chat.send_message(user_msg)
        return response.text or "Sin respuesta de Gemini."

    except ImportError:
        return ("La libreria google-generativeai no esta instalada. "
                "Ejecuta: pip install google-generativeai")
    except Exception as e:
        error_str = str(e)
        if "API_KEY" in error_str.upper() or "401" in error_str or "403" in error_str:
            return "API key invalida o sin permisos. Verifica tu Gemini API key."
        return f"Error al consultar Gemini: {error_str}"


def _generate_local_response(user_msg: str, context: str) -> str:
    """Generate a response without LLM (rule-based fallback)."""
    msg_lower = user_msg.lower()

    if "backtest_result" not in st.session_state:
        return ("**Chuky dice:** Pana, primero ejecuta un backtest en el Backtest Lab. "
                "Sin datos, no puedo analizar nada.")

    metrics = st.session_state["backtest_result"]["metrics"]

    if any(w in msg_lower for w in ["rendimiento", "performance", "general", "resumen"]):
        pnl_emoji = "+" if metrics.total_pnl >= 0 else ""
        verdict = "bueno" if metrics.profit_factor > 1.2 else "necesita trabajo"
        return (
            f"**Analisis General de Chuky:**\n\n"
            f"P&L Total: **${metrics.total_pnl:+,.2f}** ({metrics.total_return_pct:+.1f}%)\n"
            f"- Win Rate: **{metrics.win_rate:.1%}** | Profit Factor: **{metrics.profit_factor:.2f}**\n"
            f"- Sharpe: **{metrics.sharpe_ratio:.2f}** | Sortino: **{metrics.sortino_ratio:.2f}**\n"
            f"- Max DD: **${metrics.max_drawdown_usd:,.0f}** ({metrics.max_drawdown_pct:.1%})\n"
            f"- Avg Win: ${metrics.avg_win:+,.2f} | Avg Loss: ${metrics.avg_loss:+,.2f}\n"
            f"- Expectancy: ${metrics.expectancy:+,.2f}/trade\n\n"
            f"**Veredicto:** El rendimiento {verdict}. "
            f"{'Sigue asi, pana!' if metrics.total_pnl > 0 else 'Hay que ajustar parametros. Ve al Bot Builder.'}"
        )

    if any(w in msg_lower for w in ["riesgo", "risk", "drawdown"]):
        dd_pct = metrics.max_drawdown_usd / 2500 * 100
        return (
            f"**Analisis de Riesgo:**\n\n"
            f"- Max Drawdown: **${metrics.max_drawdown_usd:,.0f}** "
            f"({dd_pct:.0f}% del limite $2,500)\n"
            f"- DD Duration: {metrics.max_drawdown_duration_days} dias\n"
            f"- Peor Dia: ${metrics.worst_day_pnl:+,.2f}\n"
            f"- Mejor Dia: ${metrics.best_day_pnl:+,.2f}\n\n"
            f"{'ALERTA: Drawdown alto! Considera reducir contratos.' if dd_pct > 80 else 'Drawdown bajo control.'}"
        )

    if any(w in msg_lower for w in ["win rate", "mejorar", "improve"]):
        return (
            f"**Tips para mejorar el Win Rate ({metrics.win_rate:.1%}):**\n\n"
            f"1. **FVG Quality:** Filtra FVGs mas grandes (min size percentile mas alto)\n"
            f"2. **Sesiones:** Enfocate en NY AM (9:30-11:00 ET) -- mejor liquidez\n"
            f"3. **Confirmacion:** Espera que el precio respete la estructura en 4H\n"
            f"4. **Objetivo claro:** Prioriza entries con liquidez objetivo bien definida (PDH/PDL/swing)\n"
            f"5. **Paciencia:** Menos trades de mejor calidad > muchos trades mediocres"
        )

    if any(w in msg_lower for w in ["patron", "pattern", "peor"]):
        return (
            f"**Patrones detectados:**\n\n"
            f"- Largest Loss: ${metrics.largest_loss:+,.2f} -- "
            f"{'Perdida grande, revisa tu SL' if abs(metrics.largest_loss) > 500 else 'Bajo control'}\n"
            f"- Avg Loss vs Avg Win: ${abs(metrics.avg_loss):,.2f} vs ${metrics.avg_win:,.2f} -- "
            f"{'R:R favorable' if metrics.avg_win > abs(metrics.avg_loss) else 'R:R desfavorable, ajusta TP/SL'}\n"
            f"- Trades/dia: {metrics.trades_per_day:.1f} -- "
            f"{'Buen ritmo' if metrics.trades_per_day <= 2 else 'Tal vez overtrading'}\n\n"
            f"**Consejo:** Revisa los trades perdedores en el Trade Explorer para encontrar el patron."
        )

    # Default response
    return (
        f"**Chuky dice:** Buena pregunta, pana. Con los datos actuales:\n\n"
        f"- {metrics.total_trades} trades | Win Rate: {metrics.win_rate:.1%}\n"
        f"- P&L: ${metrics.total_pnl:+,.2f} | Sharpe: {metrics.sharpe_ratio:.2f}\n"
        f"- Profit Factor: {metrics.profit_factor:.2f} | Expectancy: ${metrics.expectancy:+,.2f}\n\n"
        f"Para un analisis mas profundo con IA, configura tu Gemini API key "
        f"al inicio de esta pagina."
    )
