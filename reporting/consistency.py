"""
Verificación de la regla de consistencia de OneUpTrader.

Regla: La suma de los 3 mejores días de PNL no debe superar el 80%
del PNL positivo total (ganancias totales).

Esto asegura que las ganancias estén distribuidas y no concentradas
en pocos días excepcionales.
"""
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import CONSISTENCY_TOP_N_DAYS, CONSISTENCY_MAX_PCT


@dataclass
class ConsistencyResult:
    """Resultado de la verificación de consistencia."""
    passed: bool
    top_n_days: List[float]       # PNL de los mejores N días
    top_n_sum: float              # Suma de los mejores N días
    total_positive_pnl: float     # Total de ganancias (solo días positivos)
    ratio: float                  # top_n_sum / total_positive_pnl
    threshold: float              # Umbral (0.80)
    best_day: float               # Mejor día individual
    total_trading_days: int
    positive_days: int
    negative_days: int
    detail: str


def check_consistency(
    daily_pnls: pd.Series,
    top_n: int = CONSISTENCY_TOP_N_DAYS,
    max_pct: float = CONSISTENCY_MAX_PCT,
) -> ConsistencyResult:
    """
    Verifica la regla de consistencia.

    Parameters
    ----------
    daily_pnls : pd.Series
        Serie con el PNL diario (indexada por fecha).
    top_n : int
        Número de mejores días a sumar (default 3).
    max_pct : float
        Porcentaje máximo permitido (default 0.80 = 80%).

    Returns
    -------
    ConsistencyResult
    """
    if len(daily_pnls) == 0:
        return ConsistencyResult(
            passed=True, top_n_days=[], top_n_sum=0,
            total_positive_pnl=0, ratio=0, threshold=max_pct,
            best_day=0, total_trading_days=0,
            positive_days=0, negative_days=0,
            detail="Sin datos de trading.",
        )

    # Días positivos y negativos
    positive = daily_pnls[daily_pnls > 0].sort_values(ascending=False)
    negative = daily_pnls[daily_pnls <= 0]

    total_positive_pnl = float(positive.sum())
    total_trading_days = len(daily_pnls)
    positive_days = len(positive)
    negative_days = len(negative)

    if positive_days < top_n:
        # No hay suficientes días positivos — automáticamente pasa
        return ConsistencyResult(
            passed=True,
            top_n_days=positive.tolist(),
            top_n_sum=float(positive.sum()),
            total_positive_pnl=total_positive_pnl,
            ratio=0.0,
            threshold=max_pct,
            best_day=float(positive.iloc[0]) if len(positive) > 0 else 0.0,
            total_trading_days=total_trading_days,
            positive_days=positive_days,
            negative_days=negative_days,
            detail=f"Solo {positive_days} días positivos (se necesitan {top_n} para evaluar).",
        )

    top_n_days = positive.iloc[:top_n].tolist()
    top_n_sum = sum(top_n_days)
    best_day = top_n_days[0]

    ratio = top_n_sum / total_positive_pnl if total_positive_pnl > 0 else 0.0
    passed = ratio <= max_pct

    detail = (
        f"Top {top_n} días: {', '.join(f'${d:+,.0f}' for d in top_n_days)} "
        f"= ${top_n_sum:,.0f} "
        f"({ratio:.1%} del total positivo ${total_positive_pnl:,.0f}). "
        f"Umbral: {max_pct:.0%}. "
        f"{'✓ CUMPLE' if passed else '✗ NO CUMPLE'}"
    )

    return ConsistencyResult(
        passed=passed,
        top_n_days=top_n_days,
        top_n_sum=top_n_sum,
        total_positive_pnl=total_positive_pnl,
        ratio=ratio,
        threshold=max_pct,
        best_day=best_day,
        total_trading_days=total_trading_days,
        positive_days=positive_days,
        negative_days=negative_days,
        detail=detail,
    )


def format_consistency_report(result: ConsistencyResult) -> str:
    """Genera un reporte formateado de la regla de consistencia."""
    lines = [
        "=" * 60,
        "  REGLA DE CONSISTENCIA — OneUpTrader",
        "=" * 60,
        f"",
        f"  Trading Days:       {result.total_trading_days}",
        f"  Positive Days:      {result.positive_days}",
        f"  Negative Days:      {result.negative_days}",
        f"  Best Day:           ${result.best_day:+,.2f}",
        f"",
        f"  Top {len(result.top_n_days)} Days:",
    ]

    for i, d in enumerate(result.top_n_days):
        lines.append(f"    #{i + 1}: ${d:+,.2f}")

    lines.extend([
        f"",
        f"  Sum Top Days:       ${result.top_n_sum:,.2f}",
        f"  Total Positive:     ${result.total_positive_pnl:,.2f}",
        f"  Ratio:              {result.ratio:.1%} (máx {result.threshold:.0%})",
        f"",
        f"  RESULTADO:          {'✓ CUMPLE' if result.passed else '✗ NO CUMPLE'}",
        f"",
        f"  {result.detail}",
        "=" * 60,
    ])

    return "\n".join(lines)
