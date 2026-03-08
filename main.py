"""
main.py — Orquestador principal del ICT Trading Bot MVP.

Flujo completo:
  1. Descarga de datos multi-timeframe
  2. Backtest en training (Aug-Nov 2025)
  3. Walk-Forward Analysis (rolling windows)
  4. Backtest Out-of-Sample (Jan-Feb 2026)
  5. Simulación Monte Carlo (1,000 iteraciones)
  6. Verificación de consistencia OneUpTrader
  7. Reporte final con veredicto GO / NO-GO

Uso:
    python main.py                  # Pipeline completo
    python main.py --quick          # Solo backtest rápido
    python main.py --download-only  # Solo descarga de datos
"""
import argparse
import os
import sys
import time
from datetime import datetime

import pandas as pd

# Path setup
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from config.settings import (
    ACCOUNT_BALANCE, TRAILING_DRAWDOWN_MAX,
    TRAINING_START, TRAINING_END,
    VALIDATION_START, VALIDATION_END,
    OOS_TEST_START, OOS_TEST_END,
    WFA_TRAIN_WEEKS, WFA_TEST_WEEKS, WFA_STEP_WEEKS,
)
from data.downloader import download_data, download_multi_timeframe
from backtest import run_backtest, run_full_validation
from strategy.ict_strategy import ICTStrategy, MNQCommInfo
from validation.metrics import compute_metrics, format_metrics_report
from validation.walk_forward import run_walk_forward, format_wfa_report
from validation.monte_carlo import run_monte_carlo, format_monte_carlo_report
from reporting.consistency import check_consistency, format_consistency_report
from reporting.report_generator import generate_full_report


BANNER = r"""
  ╔══════════════════════════════════════════════════════╗
  ║         ICT TRADING BOT — MVP v1.0                  ║
  ║         MNQ Futures | OneUpTrader $50k              ║
  ║         Powered by Backtrader                       ║
  ╚══════════════════════════════════════════════════════╝
"""


def step_download_data() -> dict[str, pd.DataFrame]:
    """Paso 1: Descarga datos multi-timeframe."""
    print("\n" + "=" * 60)
    print("  PASO 1: DESCARGA DE DATOS")
    print("=" * 60)

    data = {}

    # 1H — principal para backtesting (cubre todo el periodo)
    print("\n  Descargando 1H (principal)...")
    df_1h = download_data(interval="1h", start=TRAINING_START, end=OOS_TEST_END)
    if df_1h.empty:
        print("  ✗ ERROR: No se pudieron descargar datos 1H.")
        return data
    data["1h"] = df_1h
    print(f"  ✓ 1H: {len(df_1h)} velas | {df_1h.index[0]} → {df_1h.index[-1]}")

    # 1D — para sesgo diario
    print("\n  Descargando 1D (sesgo diario)...")
    df_1d = download_data(interval="1d", start="2025-01-01", end=OOS_TEST_END)
    if not df_1d.empty:
        data["1d"] = df_1d
        print(f"  ✓ 1D: {len(df_1d)} velas")
    else:
        print("  ⚠ Datos 1D no disponibles, continuando sin sesgo diario.")

    # 15m — para periodos recientes (OOS)
    print("\n  Descargando 15m (detalle OOS)...")
    df_15m = download_data(interval="15m")
    if not df_15m.empty:
        data["15m"] = df_15m
        print(f"  ✓ 15m: {len(df_15m)} velas | {df_15m.index[0]} → {df_15m.index[-1]}")
    else:
        print("  ⚠ Datos 15m no disponibles.")

    # 5m — para entradas precisas
    print("\n  Descargando 5m (entradas precisas)...")
    df_5m = download_data(interval="5m")
    if not df_5m.empty:
        data["5m"] = df_5m
        print(f"  ✓ 5m: {len(df_5m)} velas | {df_5m.index[0]} → {df_5m.index[-1]}")
    else:
        print("  ⚠ Datos 5m no disponibles.")

    # Resumen
    print(f"\n  ─── Resumen de datos ───")
    for tf, df in data.items():
        print(f"  {tf:>4s}: {len(df):>6,} velas")

    return data


def step_training_backtest(df_1h: pd.DataFrame) -> dict:
    """Paso 2: Backtest en periodo de entrenamiento."""
    print("\n" + "=" * 60)
    print("  PASO 2: BACKTEST — ENTRENAMIENTO")
    print("=" * 60)

    df_train = df_1h[TRAINING_START:TRAINING_END]
    if len(df_train) < 50:
        print(f"  ✗ Datos insuficientes para training ({len(df_train)} velas).")
        print("  Nota: Los datos de Aug-Nov 2025 aún no están disponibles en yfinance.")
        print("  Ejecutando backtest con todos los datos disponibles como alternativa...")
        df_train = df_1h
        if len(df_train) < 50:
            return {"error": "Datos insuficientes"}

    result = run_backtest(
        df_train,
        period_name="Training (Aug-Nov 2025)",
        verbose=False,
    )

    print("\n" + format_metrics_report(result["metrics"]))
    return result


def step_walk_forward_analysis(df_1h: pd.DataFrame) -> dict:
    """Paso 3: Walk-Forward Analysis."""
    print("\n" + "=" * 60)
    print("  PASO 3: WALK-FORWARD ANALYSIS")
    print("=" * 60)

    def _setup_cerebro(cerebro):
        """Configura comisiones MNQ para cada ventana WFA."""
        cerebro.broker.addcommissioninfo(MNQCommInfo())

    wfa_result = run_walk_forward(
        df_1h,
        strategy_class=ICTStrategy,
        strategy_params={"verbose": False},
        train_weeks=WFA_TRAIN_WEEKS,
        test_weeks=WFA_TEST_WEEKS,
        step_weeks=WFA_STEP_WEEKS,
        cerebro_setup_fn=_setup_cerebro,
    )

    if wfa_result:
        print(format_wfa_report(wfa_result))
    else:
        print("  ✗ WFA no pudo ejecutarse (datos insuficientes).")

    return wfa_result


def step_oos_backtest(df_1h: pd.DataFrame) -> dict:
    """Paso 4: Backtest Out-of-Sample."""
    print("\n" + "=" * 60)
    print("  PASO 4: BACKTEST — OUT-OF-SAMPLE")
    print("=" * 60)

    df_oos = df_1h[OOS_TEST_START:OOS_TEST_END]
    if len(df_oos) < 20:
        print(f"  ✗ Datos insuficientes para OOS ({len(df_oos)} velas).")
        print("  Nota: Los datos de Jan-Feb 2026 aún no están disponibles.")
        print("  Usando el último 25% de datos disponibles como proxy OOS...")

        split_idx = int(len(df_1h) * 0.75)
        df_oos = df_1h.iloc[split_idx:]
        if len(df_oos) < 20:
            return {"error": "Datos insuficientes"}

    result = run_backtest(
        df_oos,
        period_name="Out-of-Sample (Jan-Feb 2026)",
        verbose=False,
    )

    print("\n" + format_metrics_report(result["metrics"]))
    return result


def step_monte_carlo(trades_df: pd.DataFrame) -> dict:
    """Paso 5: Simulación Monte Carlo."""
    print("\n" + "=" * 60)
    print("  PASO 5: SIMULACIÓN MONTE CARLO")
    print("=" * 60)

    if trades_df is None or trades_df.empty:
        print("  ✗ Sin trades para simulación Monte Carlo.")
        return None

    trade_pnls = trades_df["pnl_net"].values
    mc_result = run_monte_carlo(trade_pnls, n_simulations=1000)
    print(format_monte_carlo_report(mc_result))
    return mc_result


def step_consistency_check(trades_df: pd.DataFrame) -> dict:
    """Paso 6: Verificación de regla de consistencia."""
    print("\n" + "=" * 60)
    print("  PASO 6: REGLA DE CONSISTENCIA ONEUPTRADER")
    print("=" * 60)

    if trades_df is None or trades_df.empty:
        print("  ✗ Sin trades para verificación de consistencia.")
        return None

    # Calcular PnL diario
    df_trades = trades_df.copy()
    if "timestamp" in df_trades.columns:
        df_trades["date"] = pd.to_datetime(df_trades["timestamp"]).dt.date
    elif "entry_time" in df_trades.columns:
        df_trades["date"] = pd.to_datetime(df_trades["entry_time"]).dt.date
    else:
        print("  ✗ No se encontró columna de timestamp.")
        return None

    daily_pnl = df_trades.groupby("date")["pnl_net"].sum()
    consistency = check_consistency(daily_pnl)
    print(format_consistency_report(consistency))
    return consistency


def step_final_verdict(
    train_result: dict,
    oos_result: dict,
    wfa_result: dict,
    mc_result: dict,
    consistency: dict,
) -> str:
    """Paso 7: Veredicto final GO / NO-GO."""
    print("\n" + "█" * 60)
    print("  PASO 7: VEREDICTO FINAL")
    print("█" * 60)

    checks = []

    # 1. Backtest OOS rentable
    if oos_result and "metrics" in oos_result:
        pf = oos_result["metrics"].profit_factor
        is_profitable = pf > 1.0
        checks.append(("OOS Profit Factor > 1.0", is_profitable, f"PF = {pf:.2f}"))
    else:
        checks.append(("OOS Profit Factor > 1.0", False, "Sin datos"))

    # 2. Degradación aceptable
    if train_result and oos_result and "metrics" in train_result and "metrics" in oos_result:
        train_sr = train_result["metrics"].sharpe_ratio
        oos_sr = oos_result["metrics"].sharpe_ratio
        if train_sr != 0:
            degradation = 1.0 - (oos_sr / train_sr)
            ok = degradation <= 0.40
            checks.append(("Degradación IS→OOS ≤ 40%", ok, f"{degradation:.1%}"))
        else:
            checks.append(("Degradación IS→OOS ≤ 40%", True, "N/A"))
    else:
        checks.append(("Degradación IS→OOS ≤ 40%", False, "Sin datos"))

    # 3. WFA aprobado
    if wfa_result and hasattr(wfa_result, "overall_functional"):
        checks.append(("Walk-Forward Aprobado", wfa_result.overall_functional,
                       f"{wfa_result.pct_functional_windows:.0%} funcional"))
    else:
        checks.append(("Walk-Forward Aprobado", False, "No ejecutado"))

    # 4. Monte Carlo viable
    if mc_result and hasattr(mc_result, "is_viable"):
        checks.append(("Monte Carlo Viable", mc_result.is_viable,
                       f"P95 DD=${mc_result.max_dd_p95:,.0f}"))
    else:
        checks.append(("Monte Carlo Viable", False, "No ejecutado"))

    # 5. Consistencia
    if consistency and hasattr(consistency, "passed"):
        checks.append(("Consistencia OneUpTrader", consistency.passed,
                       f"Ratio={consistency.ratio:.1%}"))
    else:
        checks.append(("Consistencia OneUpTrader", False, "No ejecutado"))

    # 6. Max DD < Trailing DD
    if oos_result and "metrics" in oos_result:
        max_dd = oos_result["metrics"].max_drawdown_usd
        ok = max_dd < TRAILING_DRAWDOWN_MAX
        checks.append((f"Max DD < ${TRAILING_DRAWDOWN_MAX:,}", ok,
                       f"DD =${max_dd:,.0f}"))
    else:
        checks.append((f"Max DD < ${TRAILING_DRAWDOWN_MAX:,}", False, "Sin datos"))

    # Imprimir resultados
    print()
    passed = 0
    total = len(checks)
    for name, ok, detail in checks:
        status = "✓" if ok else "✗"
        print(f"  {status} {name}: {detail}")
        if ok:
            passed += 1

    # Veredicto
    print(f"\n  Resultado: {passed}/{total} checks pasados")
    if passed == total:
        verdict = "GO"
        print("\n  ███████████████████████████████████████████")
        print("  ██   VEREDICTO: ✓ GO — LISTO PARA DEMO  ██")
        print("  ███████████████████████████████████████████")
    elif passed >= total - 1:
        verdict = "CONDICIONAL"
        print("\n  ██  VEREDICTO: ⚠ CONDICIONAL — REVISAR  ██")
    else:
        verdict = "NO-GO"
        print("\n  ██  VEREDICTO: ✗ NO-GO — NO PASAR A DEMO ██")

    return verdict


def run_pipeline(quick: bool = False):
    """Ejecuta el pipeline completo de validación."""
    start_time = time.time()

    # ─── Paso 1: Datos ───
    data = step_download_data()
    if "1h" not in data or data["1h"].empty:
        print("\n✗ ERROR FATAL: No se pudieron descargar datos. Abortando.")
        return

    df_1h = data["1h"]

    if quick:
        # Solo backtest rápido con todos los datos
        result = run_backtest(df_1h, period_name="Backtest Rápido", verbose=True)
        print("\n" + format_metrics_report(result["metrics"]))
        elapsed = time.time() - start_time
        print(f"\n  Tiempo total: {elapsed:.1f}s")
        return

    # ─── Paso 2: Training ───
    train_result = step_training_backtest(df_1h)

    # ─── Paso 3: Walk-Forward ───
    wfa_result = step_walk_forward_analysis(df_1h)

    # ─── Paso 4: OOS ───
    oos_result = step_oos_backtest(df_1h)

    # ─── Paso 5: Monte Carlo ───
    mc_result = None
    if isinstance(oos_result, dict) and "trades_df" in oos_result:
        mc_result = step_monte_carlo(oos_result["trades_df"])

    # ─── Paso 6: Consistencia ───
    consistency = None
    if isinstance(oos_result, dict) and "trades_df" in oos_result:
        consistency = step_consistency_check(oos_result["trades_df"])

    # ─── Paso 7: Veredicto ───
    verdict = step_final_verdict(
        train_result=train_result if isinstance(train_result, dict) else None,
        oos_result=oos_result if isinstance(oos_result, dict) else None,
        wfa_result=wfa_result,
        mc_result=mc_result,
        consistency=consistency,
    )

    # ─── Generar reporte en disco ───
    if isinstance(oos_result, dict) and "metrics" in oos_result:
        report = generate_full_report(
            metrics=oos_result["metrics"],
            trades_df=oos_result.get("trades_df"),
            mc_result=mc_result,
            consistency_result=consistency,
            wfa_result=wfa_result,
            period_name="Pipeline Completo",
        )

    # ─── Tiempo total ───
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = elapsed % 60
    print(f"\n  Tiempo total de ejecución: {minutes}m {seconds:.1f}s")
    print(f"  Veredicto final: {verdict}\n")


def main():
    parser = argparse.ArgumentParser(
        description="ICT Trading Bot — MVP Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py                  Pipeline completo de validación
  python main.py --quick          Backtest rápido sin validación
  python main.py --download-only  Solo descarga de datos
        """,
    )
    parser.add_argument("--quick", action="store_true",
                        help="Ejecuta solo un backtest rápido")
    parser.add_argument("--download-only", action="store_true",
                        help="Solo descarga datos sin ejecutar backtest")
    parser.add_argument("--plot", action="store_true",
                        help="Genera gráfico de Backtrader")

    args = parser.parse_args()

    print(BANNER)

    if args.download_only:
        data = step_download_data()
        print("\n  Descarga completada.")
        return

    run_pipeline(quick=args.quick)


if __name__ == "__main__":
    main()
