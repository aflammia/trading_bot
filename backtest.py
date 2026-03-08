"""
Runner principal de backtesting para el ICT Trading Bot.

Ejecuta el backtest usando Backtrader con los datos descargados,
la estrategia ICT, y genera las métricas de rendimiento.
"""
import os
import sys
from datetime import datetime

import backtrader as bt
import numpy as np
import pandas as pd

# Path setup
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from config.settings import (
    ACCOUNT_BALANCE, COMMISSION_PER_SIDE, POINT_VALUE,
    SLIPPAGE_TICKS, TICK_VALUE,
    TRAINING_START, TRAINING_END,
    VALIDATION_START, VALIDATION_END,
    OOS_TEST_START, OOS_TEST_END,
)
from data.downloader import download_data, resample_ohlcv, download_multi_timeframe
from strategy.ict_strategy import ICTStrategy, MNQCommInfo
from validation.metrics import compute_metrics, format_metrics_report
from validation.monte_carlo import run_monte_carlo, format_monte_carlo_report
from reporting.consistency import check_consistency, format_consistency_report
from reporting.report_generator import generate_full_report


def run_backtest(
    df: pd.DataFrame,
    period_name: str = "Backtest",
    initial_capital: float = ACCOUNT_BALANCE,
    verbose: bool = True,
    plot: bool = False,
    strategy_params: dict = None,
) -> dict:
    """
    Ejecuta un backtest completo con Backtrader.

    Parameters
    ----------
    df : pd.DataFrame
        Datos OHLCV con DatetimeIndex (1H resolution).
    period_name : str
        Nombre del período para reportes.
    initial_capital : float
        Capital inicial.
    verbose : bool
        Mostrar logs durante el backtest.
    plot : bool
        Generar gráfico de Backtrader.
    strategy_params : dict
        Parámetros adicionales para la estrategia.

    Returns
    -------
    dict con:
        - 'metrics': PerformanceMetrics
        - 'trades_df': DataFrame de trades
        - 'final_value': valor final del portfolio
        - 'strategy': instancia de la estrategia
    """
    print(f"\n{'='*60}")
    print(f"  BACKTESTING: {period_name}")
    print(f"  Datos: {df.index[0]} → {df.index[-1]} ({len(df)} velas)")
    print(f"  Capital: ${initial_capital:,.2f}")
    print(f"{'='*60}\n")

    cerebro = bt.Cerebro()

    # =========================================================================
    # Preparar datos — remover timezone para Backtrader
    # =========================================================================
    df_bt = df.copy()
    if df_bt.index.tz is not None:
        df_bt.index = df_bt.index.tz_localize(None)

    # Data feed base
    data_base = bt.feeds.PandasData(
        dataname=df_bt,
        datetime=None,
        open="Open", high="High", low="Low",
        close="Close", volume="Volume",
        openinterest=-1,
    )
    cerebro.adddata(data_base, name="base")

    # Resample a 4H para análisis multi-TF
    cerebro.resampledata(
        data_base, name="4h",
        timeframe=bt.TimeFrame.Minutes,
        compression=240,
    )

    # =========================================================================
    # Configurar estrategia
    # =========================================================================
    params = {"verbose": verbose}
    if strategy_params:
        params.update(strategy_params)

    cerebro.addstrategy(ICTStrategy, **params)

    # =========================================================================
    # Configurar broker
    # =========================================================================
    cerebro.broker.setcash(initial_capital)

    # Comisión MNQ
    cerebro.broker.addcommissioninfo(MNQCommInfo())

    # Slippage
    cerebro.broker.set_slippage_fixed(
        SLIPPAGE_TICKS * TICK_VALUE,
        slip_open=True,
        slip_match=True,
        slip_limit=True,
    )

    # =========================================================================
    # Analyzers
    # =========================================================================
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, riskfreerate=0.05)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    # =========================================================================
    # Ejecutar
    # =========================================================================
    print("Ejecutando backtest...")
    results = cerebro.run()
    strategy = results[0]

    final_value = cerebro.broker.getvalue()
    print(f"\nValor final del portfolio: ${final_value:,.2f}")
    print(f"Retorno: ${final_value - initial_capital:+,.2f} "
          f"({(final_value - initial_capital) / initial_capital * 100:+.2f}%)")

    # =========================================================================
    # Extraer resultados
    # =========================================================================
    trades_df = strategy.get_trades_df()
    metrics = compute_metrics(trades_df, initial_capital)

    # Plot si se solicita
    if plot and len(trades_df) > 0:
        try:
            cerebro.plot(style="candlestick", volume=True)
        except Exception as e:
            print(f"No se pudo generar gráfico: {e}")

    return {
        "metrics": metrics,
        "trades_df": trades_df,
        "final_value": final_value,
        "strategy": strategy,
    }


def run_full_validation(
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    period_name: str = "Full Validation",
) -> dict:
    """
    Ejecuta la validación completa:
    1. Backtest en datos de entrenamiento
    2. Backtest en datos de test (OOS)
    3. Monte Carlo
    4. Verificación de consistencia
    5. Reporte final

    Returns dict con todos los resultados.
    """
    print("\n" + "█" * 60)
    print(f"  VALIDACIÓN COMPLETA: {period_name}")
    print("█" * 60)

    results = {}

    # =========================================================================
    # 1. Backtest Training
    # =========================================================================
    print("\n" + "─" * 60)
    print("  FASE 1: Backtest en datos de entrenamiento")
    print("─" * 60)
    train_result = run_backtest(
        df_train,
        period_name=f"{period_name} — Training",
        verbose=False,
    )
    results["train"] = train_result
    print(format_metrics_report(train_result["metrics"]))

    # =========================================================================
    # 2. Backtest OOS
    # =========================================================================
    print("\n" + "─" * 60)
    print("  FASE 2: Backtest Out-of-Sample")
    print("─" * 60)
    oos_result = run_backtest(
        df_test,
        period_name=f"{period_name} — OOS Test",
        verbose=False,
    )
    results["oos"] = oos_result
    print(format_metrics_report(oos_result["metrics"]))

    # Comparar degradación
    train_sharpe = train_result["metrics"].sharpe_ratio
    oos_sharpe = oos_result["metrics"].sharpe_ratio
    if train_sharpe != 0:
        degradation = 1.0 - (oos_sharpe / train_sharpe)
        print(f"\n  Degradación IS→OOS del Sharpe: {degradation:.1%}")
        print(f"  {'✓ OK' if degradation <= 0.40 else '✗ POSIBLE OVERFITTING'}")
    results["degradation"] = degradation if train_sharpe != 0 else None

    # =========================================================================
    # 3. Monte Carlo (sobre trades OOS)
    # =========================================================================
    print("\n" + "─" * 60)
    print("  FASE 3: Monte Carlo Simulation")
    print("─" * 60)
    mc_result = None
    if not oos_result["trades_df"].empty:
        trade_pnls = oos_result["trades_df"]["pnl_net"].values
        mc_result = run_monte_carlo(trade_pnls)
        print(format_monte_carlo_report(mc_result))
    else:
        print("  Sin trades para Monte Carlo.")
    results["monte_carlo"] = mc_result

    # =========================================================================
    # 4. Consistencia
    # =========================================================================
    print("\n" + "─" * 60)
    print("  FASE 4: Regla de Consistencia")
    print("─" * 60)
    consistency = None
    if not oos_result["trades_df"].empty and "timestamp" in oos_result["trades_df"].columns:
        df_trades = oos_result["trades_df"].copy()
        df_trades["date"] = pd.to_datetime(df_trades["timestamp"]).dt.date
        daily_pnl = df_trades.groupby("date")["pnl_net"].sum()
        consistency = check_consistency(daily_pnl)
        print(format_consistency_report(consistency))
    else:
        print("  Sin datos para verificación de consistencia.")
    results["consistency"] = consistency

    # =========================================================================
    # 5. Reporte final
    # =========================================================================
    report = generate_full_report(
        metrics=oos_result["metrics"],
        trades_df=oos_result["trades_df"],
        mc_result=mc_result,
        consistency_result=consistency,
        period_name=period_name,
    )
    results["report"] = report

    return results


if __name__ == "__main__":
    # Ejecución directa: backtest simple con datos disponibles
    print("Descargando datos...")
    df_1h = download_data(interval="1h", start=TRAINING_START, end=OOS_TEST_END)

    if df_1h.empty:
        print("ERROR: No se pudieron descargar datos. Verifica tu conexión.")
        sys.exit(1)

    # Split en training y test
    df_train = df_1h[TRAINING_START:TRAINING_END]
    df_val = df_1h[VALIDATION_START:VALIDATION_END]
    df_test = df_1h[OOS_TEST_START:OOS_TEST_END]

    print(f"\nDatos disponibles:")
    print(f"  Training: {len(df_train)} velas ({TRAINING_START} → {TRAINING_END})")
    print(f"  Validation: {len(df_val)} velas ({VALIDATION_START} → {VALIDATION_END})")
    print(f"  OOS Test: {len(df_test)} velas ({OOS_TEST_START} → {OOS_TEST_END})")

    if len(df_train) > 0 and len(df_test) > 0:
        results = run_full_validation(
            df_train=df_train,
            df_test=df_test,
            period_name="Ago 2025 → Feb 2026",
        )
    else:
        print("Datos insuficientes para validación completa. Ejecutando backtest simple...")
        if len(df_1h) > 50:
            result = run_backtest(df_1h, period_name="Backtest Simple")
            print(format_metrics_report(result["metrics"]))
