"""
Generador de reportes finales del bot de trading.

Genera un reporte consolidado con todas las métricas,
Walk-Forward Analysis, Monte Carlo, y regla de consistencia.
"""
import os
import sys
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import REPORT_OUTPUT_DIR, ACCOUNT_BALANCE, TRAILING_DRAWDOWN_MAX
from validation.metrics import PerformanceMetrics, format_metrics_report
from validation.monte_carlo import MonteCarloResult, format_monte_carlo_report
from validation.walk_forward import WFAResult, format_wfa_report
from reporting.consistency import ConsistencyResult, format_consistency_report


def generate_full_report(
    metrics: PerformanceMetrics,
    trades_df: pd.DataFrame,
    wfa_result: Optional[WFAResult] = None,
    mc_result: Optional[MonteCarloResult] = None,
    consistency_result: Optional[ConsistencyResult] = None,
    period_name: str = "Backtest",
    save_to_file: bool = True,
) -> str:
    """
    Genera un reporte completo y consolidado.

    Parameters
    ----------
    metrics : PerformanceMetrics del período principal.
    trades_df : DataFrame de trades.
    wfa_result : Resultado del Walk-Forward (opcional).
    mc_result : Resultado de Monte Carlo (opcional).
    consistency_result : Resultado de consistencia (opcional).
    period_name : Nombre del período (para el título).
    save_to_file : Si True, guarda en un archivo .txt.

    Returns
    -------
    str : Reporte completo como texto.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sections = [
        "╔" + "═" * 68 + "╗",
        "║" + f"  ICT TRADING BOT — REPORTE DE SIMULACIÓN".center(68) + "║",
        "║" + f"  Período: {period_name}".center(68) + "║",
        "║" + f"  Generado: {now}".center(68) + "║",
        "╚" + "═" * 68 + "╝",
        "",
    ]

    # Sección 1: Métricas de rendimiento
    sections.append(format_metrics_report(metrics))
    sections.append("")

    # Sección 2: Consistencia
    if consistency_result:
        sections.append(format_consistency_report(consistency_result))
        sections.append("")

    # Sección 3: Walk-Forward Analysis
    if wfa_result:
        sections.append(format_wfa_report(wfa_result))
        sections.append("")

    # Sección 4: Monte Carlo
    if mc_result:
        sections.append(format_monte_carlo_report(mc_result))
        sections.append("")

    # Sección 5: Resumen de trades individuales
    if not trades_df.empty:
        sections.append(_trades_summary(trades_df))
        sections.append("")

    # Sección 6: Veredicto final
    sections.append(_final_verdict(metrics, wfa_result, mc_result, consistency_result))

    report = "\n".join(sections)

    # Guardar en archivo
    if save_to_file:
        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
        safe_name = period_name.replace(" ", "_").replace("/", "-")
        filepath = os.path.join(
            REPORT_OUTPUT_DIR,
            f"report_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n[REPORT] Guardado en: {filepath}")

    return report


def _trades_summary(trades_df: pd.DataFrame) -> str:
    """Resumen tabular de los últimos 20 trades."""
    lines = [
        "=" * 65,
        "        DETALLE DE TRADES (últimos 20)",
        "=" * 65,
    ]

    df = trades_df.tail(20).copy()

    for _, row in df.iterrows():
        ts = row.get("timestamp", "N/A")
        if isinstance(ts, datetime):
            ts = ts.strftime("%Y-%m-%d %H:%M")

        direction = row.get("direction", "?")
        entry = row.get("entry_price", 0)
        exit_p = row.get("exit_price", 0)
        pnl = row.get("pnl_net", row.get("pnl_gross", 0))
        contracts = row.get("contracts", 0)

        icon = "✓" if pnl > 0 else "✗"
        lines.append(
            f"  {icon} {ts} | {direction:5s} | "
            f"Entry={entry:>9.1f} | Exit={exit_p:>9.1f} | "
            f"PnL=${pnl:>+8.2f} | x{contracts}"
        )

    lines.append("=" * 65)
    return "\n".join(lines)


def _final_verdict(
    metrics: PerformanceMetrics,
    wfa: Optional[WFAResult],
    mc: Optional[MonteCarloResult],
    consistency: Optional[ConsistencyResult],
) -> str:
    """Genera el veredicto final sobre si el bot es funcional."""
    checks = []

    # Metric checks
    checks.append(("Sharpe Ratio > 1.5", metrics.sharpe_ratio > 1.5))
    checks.append(("Profit Factor > 1.2", metrics.profit_factor > 1.2))
    checks.append(("Max DD < $2,500", metrics.max_drawdown_usd < TRAILING_DRAWDOWN_MAX))
    checks.append(("Win Rate > 45%", metrics.win_rate > 0.45))

    # WFA check
    if wfa:
        checks.append(("WFA: Funcional", wfa.overall_functional))

    # Monte Carlo check
    if mc:
        checks.append(("MC: Viable (P95 DD < límite)", mc.is_viable))

    # Consistency check
    if consistency:
        checks.append(("Consistencia: Cumple", consistency.passed))

    passed = sum(1 for _, p in checks if p)
    total = len(checks)
    all_passed = passed == total

    lines = [
        "╔" + "═" * 68 + "╗",
        "║" + "  VEREDICTO FINAL".center(68) + "║",
        "╚" + "═" * 68 + "╝",
        "",
    ]

    for name, p in checks:
        icon = "✓" if p else "✗"
        lines.append(f"  {icon} {name}")

    lines.extend([
        "",
        f"  Score: {passed}/{total} checks pasados",
        "",
    ])

    if all_passed:
        lines.append(
            "  ★ BOT FUNCIONAL — Listo para Fase Shadow Trading (Mes 1)"
        )
    elif passed >= total * 0.7:
        lines.append(
            "  △ BOT PARCIALMENTE FUNCIONAL — Requiere ajustes antes de Shadow Trading"
        )
    else:
        lines.append(
            "  ✗ BOT NO FUNCIONAL — Requiere revisión significativa de la estrategia"
        )

    lines.append("")
    return "\n".join(lines)
