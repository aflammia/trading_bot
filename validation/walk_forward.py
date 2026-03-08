"""
Walk-Forward Analysis (WFA) para validación del bot.

Protocolo:
1. Ventana de entrenamiento: N semanas (optimización de parámetros)
2. Ventana de prueba: M semanas (out-of-sample)
3. Paso: 1 semana
4. Criterio: Si el Sharpe OOS se degrada >40% vs IS → overfitting
"""
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import backtrader as bt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import (
    WFA_TRAIN_WEEKS, WFA_TEST_WEEKS, WFA_STEP_WEEKS,
    WFA_MAX_DEGRADATION, ACCOUNT_BALANCE,
)
from validation.metrics import compute_metrics, PerformanceMetrics


@dataclass
class WFAWindowResult:
    """Resultado de una ventana del WFA."""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    is_sharpe: float       # Sharpe in-sample
    oos_sharpe: float      # Sharpe out-of-sample
    is_pf: float           # Profit Factor in-sample
    oos_pf: float          # Profit Factor out-of-sample
    is_trades: int
    oos_trades: int
    degradation: float     # % de degradación del Sharpe (IS → OOS)
    is_functional: bool    # ¿Pasa el criterio?


@dataclass
class WFAResult:
    """Resultado agregado del Walk-Forward Analysis."""
    windows: List[WFAWindowResult]
    avg_oos_sharpe: float
    avg_degradation: float
    pct_functional_windows: float
    overall_functional: bool
    summary: str


def run_walk_forward(
    data_df: pd.DataFrame,
    strategy_class,
    strategy_params: dict = None,
    train_weeks: int = WFA_TRAIN_WEEKS,
    test_weeks: int = WFA_TEST_WEEKS,
    step_weeks: int = WFA_STEP_WEEKS,
    max_degradation: float = WFA_MAX_DEGRADATION,
    initial_capital: float = ACCOUNT_BALANCE,
    cerebro_setup_fn=None,
) -> WFAResult:
    """
    Ejecuta Walk-Forward Analysis completo.

    Parameters
    ----------
    data_df : pd.DataFrame
        DataFrame OHLCV con DatetimeIndex para el período completo.
    strategy_class : bt.Strategy class
        La clase de estrategia a evaluar.
    strategy_params : dict, optional
        Parámetros para la estrategia.
    train_weeks : int
        Semanas de entrenamiento por ventana.
    test_weeks : int
        Semanas de prueba por ventana.
    step_weeks : int
        Semanas de avance entre ventanas.
    max_degradation : float
        Degradación máxima permitida (0.40 = 40%).
    initial_capital : float
        Capital inicial.
    cerebro_setup_fn : callable, optional
        Función para configurar Cerebro adicional (comisiones, etc.).

    Returns
    -------
    WFAResult con resultados agregados.
    """
    if strategy_params is None:
        strategy_params = {}

    windows: List[WFAWindowResult] = []

    # Calcular fechas de ventanas
    data_start = data_df.index[0]
    data_end = data_df.index[-1]

    train_delta = timedelta(weeks=train_weeks)
    test_delta = timedelta(weeks=test_weeks)
    step_delta = timedelta(weeks=step_weeks)

    window_start = data_start
    window_id = 0

    while window_start + train_delta + test_delta <= data_end:
        train_end = window_start + train_delta
        test_start = train_end
        test_end = test_start + test_delta

        # Extraer datos para cada ventana
        train_data = data_df[window_start:train_end]
        test_data = data_df[test_start:test_end]

        if len(train_data) < 20 or len(test_data) < 5:
            window_start += step_delta
            continue

        # Run backtests
        is_metrics = _run_single_backtest(
            train_data, strategy_class, strategy_params,
            initial_capital, cerebro_setup_fn
        )
        oos_metrics = _run_single_backtest(
            test_data, strategy_class, strategy_params,
            initial_capital, cerebro_setup_fn
        )

        # Calcular degradación
        if is_metrics.sharpe_ratio != 0:
            degradation = 1.0 - (oos_metrics.sharpe_ratio / is_metrics.sharpe_ratio)
        else:
            degradation = 1.0 if oos_metrics.sharpe_ratio <= 0 else 0.0

        is_functional = degradation <= max_degradation and oos_metrics.profit_factor > 1.0

        result = WFAWindowResult(
            window_id=window_id,
            train_start=str(window_start.date()),
            train_end=str(train_end.date()),
            test_start=str(test_start.date()),
            test_end=str(test_end.date()),
            is_sharpe=is_metrics.sharpe_ratio,
            oos_sharpe=oos_metrics.sharpe_ratio,
            is_pf=is_metrics.profit_factor,
            oos_pf=oos_metrics.profit_factor,
            is_trades=is_metrics.total_trades,
            oos_trades=oos_metrics.total_trades,
            degradation=degradation,
            is_functional=is_functional,
        )

        windows.append(result)
        print(
            f"  WFA Window {window_id}: "
            f"IS Sharpe={is_metrics.sharpe_ratio:.2f} → "
            f"OOS Sharpe={oos_metrics.sharpe_ratio:.2f} "
            f"(deg={degradation:.1%}) "
            f"{'✓' if is_functional else '✗'}"
        )

        window_id += 1
        window_start += step_delta

    # Agregar resultados
    if not windows:
        return WFAResult(
            windows=[],
            avg_oos_sharpe=0.0,
            avg_degradation=0.0,
            pct_functional_windows=0.0,
            overall_functional=False,
            summary="No se pudieron crear ventanas de WFA con los datos disponibles.",
        )

    avg_oos_sharpe = np.mean([w.oos_sharpe for w in windows])
    avg_degradation = np.mean([w.degradation for w in windows])
    pct_functional = sum(1 for w in windows if w.is_functional) / len(windows)
    overall = pct_functional >= 0.70 and avg_oos_sharpe > 0

    summary_lines = [
        f"Walk-Forward Analysis: {len(windows)} ventanas",
        f"  Avg OOS Sharpe:        {avg_oos_sharpe:.2f}",
        f"  Avg Degradation:       {avg_degradation:.1%}",
        f"  Functional Windows:    {pct_functional:.0%}",
        f"  Overall Functional:    {'✓ SÍ' if overall else '✗ NO'}",
    ]

    return WFAResult(
        windows=windows,
        avg_oos_sharpe=avg_oos_sharpe,
        avg_degradation=avg_degradation,
        pct_functional_windows=pct_functional,
        overall_functional=overall,
        summary="\n".join(summary_lines),
    )


def _run_single_backtest(
    data_df: pd.DataFrame,
    strategy_class,
    strategy_params: dict,
    initial_capital: float,
    cerebro_setup_fn=None,
) -> PerformanceMetrics:
    """Ejecuta un backtest individual y retorna las métricas."""
    from strategy.ict_strategy import MNQCommInfo

    cerebro = bt.Cerebro()

    # Configurar datos
    data_feed = bt.feeds.PandasData(
        dataname=data_df,
        datetime=None,
        open="Open", high="High", low="Low", close="Close",
        volume="Volume",
    )
    cerebro.adddata(data_feed, name="base")

    # Resample a 4H
    cerebro.resampledata(data_feed, name="4h",
                         timeframe=bt.TimeFrame.Minutes, compression=240)

    # Estrategia
    params = {**strategy_params, "verbose": False}
    cerebro.addstrategy(strategy_class, **params)

    # Broker
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.addcommissioninfo(MNQCommInfo())

    if cerebro_setup_fn:
        cerebro_setup_fn(cerebro)

    # Ejecutar
    try:
        results = cerebro.run()
        strategy_instance = results[0]
        trades_df = strategy_instance.get_trades_df()
        return compute_metrics(trades_df, initial_capital)
    except Exception as e:
        print(f"  [WFA] Error en backtest: {e}")
        return PerformanceMetrics(initial_balance=initial_capital,
                                  final_balance=initial_capital)


def format_wfa_report(result: WFAResult) -> str:
    """Genera un reporte formateado del WFA."""
    lines = [
        "=" * 70,
        "        WALK-FORWARD ANALYSIS REPORT",
        "=" * 70,
        "",
    ]

    for w in result.windows:
        lines.append(
            f"  Window {w.window_id:2d} | "
            f"Train: {w.train_start}→{w.train_end} | "
            f"Test: {w.test_start}→{w.test_end} | "
            f"IS Sharpe: {w.is_sharpe:+.2f} | "
            f"OOS Sharpe: {w.oos_sharpe:+.2f} | "
            f"Deg: {w.degradation:+.1%} | "
            f"{'✓' if w.is_functional else '✗'}"
        )

    lines.extend([
        "",
        "─" * 70,
        result.summary,
        "=" * 70,
    ])

    return "\n".join(lines)
