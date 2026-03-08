"""
Simulaciones de Monte Carlo para validación estadística.

Re-muestrea el orden de los trades (1,000 iteraciones) para generar
distribuciones de Max Drawdown, Sharpe Ratio, y retorno final.
"""
import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import MONTE_CARLO_ITERATIONS, ACCOUNT_BALANCE, TRAILING_DRAWDOWN_MAX


@dataclass
class MonteCarloResult:
    """Resultado de la simulación de Monte Carlo."""
    iterations: int

    # Distribuciones (percentiles)
    max_dd_p50: float      # Mediana del max drawdown
    max_dd_p95: float      # P95 del max drawdown
    max_dd_p99: float      # P99 del max drawdown

    final_pnl_p5: float    # P5 del retorno final
    final_pnl_p50: float   # Mediana del retorno final
    final_pnl_p95: float   # P95 del retorno final

    sharpe_p5: float       # P5 del Sharpe
    sharpe_p50: float      # Mediana del Sharpe
    sharpe_p95: float      # P95 del Sharpe

    # Probabilidades
    prob_profit: float     # Probabilidad de terminar en ganancia
    prob_exceed_dd: float  # Probabilidad de exceder el trailing DD

    # Assessment
    is_viable: bool
    summary: str

    # Datos crudos para plotting
    all_max_dds: Optional[np.ndarray] = None
    all_final_pnls: Optional[np.ndarray] = None
    all_sharpes: Optional[np.ndarray] = None


def run_monte_carlo(
    trade_pnls: np.ndarray,
    iterations: int = MONTE_CARLO_ITERATIONS,
    initial_balance: float = ACCOUNT_BALANCE,
    max_trailing_dd: float = TRAILING_DRAWDOWN_MAX,
    trading_days_per_year: int = 252,
    risk_free_rate: float = 0.05,
) -> MonteCarloResult:
    """
    Ejecuta simulación de Monte Carlo re-muestreando el orden de trades.

    Parameters
    ----------
    trade_pnls : np.ndarray
        Array de P&L por trade (neto de comisiones).
    iterations : int
        Número de iteraciones de Monte Carlo.
    initial_balance : float
        Balance inicial.
    max_trailing_dd : float
        Drawdown trailing máximo (para calcular probabilidad de exceder).
    trading_days_per_year : int
        Días de trading por año para cálculo de Sharpe.
    risk_free_rate : float
        Tasa libre de riesgo anual.

    Returns
    -------
    MonteCarloResult
    """
    n_trades = len(trade_pnls)

    if n_trades < 5:
        return MonteCarloResult(
            iterations=0,
            max_dd_p50=0, max_dd_p95=0, max_dd_p99=0,
            final_pnl_p5=0, final_pnl_p50=0, final_pnl_p95=0,
            sharpe_p5=0, sharpe_p50=0, sharpe_p95=0,
            prob_profit=0, prob_exceed_dd=0,
            is_viable=False,
            summary="Insuficientes trades para Monte Carlo (mín 5).",
        )

    all_max_dds = np.zeros(iterations)
    all_final_pnls = np.zeros(iterations)
    all_sharpes = np.zeros(iterations)
    exceed_dd_count = 0

    rng = np.random.default_rng(seed=42)

    for i in range(iterations):
        # Re-muestrear con reemplazo
        shuffled = rng.choice(trade_pnls, size=n_trades, replace=True)

        # Equity curve
        equity = initial_balance + np.cumsum(shuffled)
        peak = np.maximum.accumulate(equity)
        drawdown = peak - equity

        # Max drawdown
        max_dd = np.max(drawdown)
        all_max_dds[i] = max_dd

        # Final P&L
        final_pnl = equity[-1] - initial_balance
        all_final_pnls[i] = final_pnl

        # ¿Excede el trailing DD?
        if max_dd >= max_trailing_dd:
            exceed_dd_count += 1

        # Sharpe (simplificado: asumimos ~1 trade/día)
        daily_returns = shuffled / initial_balance
        if daily_returns.std() > 0:
            excess = daily_returns.mean() - (risk_free_rate / trading_days_per_year)
            sharpe = excess / daily_returns.std() * np.sqrt(trading_days_per_year)
        else:
            sharpe = 0.0
        all_sharpes[i] = sharpe

    # Calcular percentiles
    result = MonteCarloResult(
        iterations=iterations,
        max_dd_p50=float(np.percentile(all_max_dds, 50)),
        max_dd_p95=float(np.percentile(all_max_dds, 95)),
        max_dd_p99=float(np.percentile(all_max_dds, 99)),
        final_pnl_p5=float(np.percentile(all_final_pnls, 5)),
        final_pnl_p50=float(np.percentile(all_final_pnls, 50)),
        final_pnl_p95=float(np.percentile(all_final_pnls, 95)),
        sharpe_p5=float(np.percentile(all_sharpes, 5)),
        sharpe_p50=float(np.percentile(all_sharpes, 50)),
        sharpe_p95=float(np.percentile(all_sharpes, 95)),
        prob_profit=float(np.mean(all_final_pnls > 0)),
        prob_exceed_dd=exceed_dd_count / iterations,
        is_viable=False,  # Se calcula abajo
        summary="",
        all_max_dds=all_max_dds,
        all_final_pnls=all_final_pnls,
        all_sharpes=all_sharpes,
    )

    # Assessment
    # Viable si: P95 de MDD < trailing DD y probabilidad de profit > 60%
    result.is_viable = (
        result.max_dd_p95 < max_trailing_dd
        and result.prob_profit >= 0.60
        and result.sharpe_p50 > 0
    )

    result.summary = _generate_mc_summary(result, max_trailing_dd)
    return result


def _generate_mc_summary(result: MonteCarloResult, max_dd: float) -> str:
    """Genera el resumen del Monte Carlo."""
    lines = [
        f"Monte Carlo ({result.iterations} iteraciones):",
        f"",
        f"  Max Drawdown:",
        f"    P50 (mediana): ${result.max_dd_p50:,.2f}",
        f"    P95:           ${result.max_dd_p95:,.2f}  {'✓' if result.max_dd_p95 < max_dd else '✗'} (límite ${max_dd:,.2f})",
        f"    P99:           ${result.max_dd_p99:,.2f}",
        f"",
        f"  Retorno Final:",
        f"    P5 (peor):     ${result.final_pnl_p5:+,.2f}",
        f"    P50 (mediana): ${result.final_pnl_p50:+,.2f}",
        f"    P95 (mejor):   ${result.final_pnl_p95:+,.2f}",
        f"",
        f"  Sharpe Ratio:",
        f"    P5:            {result.sharpe_p5:.2f}",
        f"    P50:           {result.sharpe_p50:.2f}",
        f"    P95:           {result.sharpe_p95:.2f}",
        f"",
        f"  Probabilidades:",
        f"    Profit:        {result.prob_profit:.1%}",
        f"    Exceder DD:    {result.prob_exceed_dd:.1%}",
        f"",
        f"  VIABLE: {'✓ SÍ' if result.is_viable else '✗ NO'}",
    ]
    return "\n".join(lines)


def format_monte_carlo_report(result: MonteCarloResult) -> str:
    """Genera un reporte completo formateado."""
    lines = [
        "=" * 65,
        "        MONTE CARLO SIMULATION REPORT",
        "=" * 65,
        "",
        result.summary,
        "",
        "=" * 65,
    ]
    return "\n".join(lines)
