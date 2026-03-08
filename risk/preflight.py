"""
Verificaciones pre-vuelo (preflight checks) antes de ejecutar un trade.

Verifica que el trade propuesto cumple con todas las condiciones de riesgo
y viabilidad económica antes de enviar la orden.
"""
from dataclasses import dataclass
from typing import List, Tuple

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import (
    POINT_VALUE, COMMISSION_PER_SIDE, SLIPPAGE_USD,
    ROUND_TRIP_COST, MIN_RISK_REWARD_RATIO,
    MIN_GAIN_PER_TRADE, MAX_LOSS_PER_TRADE,
    MAX_TRADES_PER_DAY, CLOSE_AT_PCT_OF_TP,
    MIN_CONTRACTS, MAX_CONTRACTS,
)


@dataclass
class PreflightResult:
    """Resultado de la verificación pre-vuelo."""
    passed: bool
    checks: List[Tuple[str, bool, str]]  # (nombre, pasó, detalle)

    @property
    def summary(self) -> str:
        failed = [c for c in self.checks if not c[1]]
        if not failed:
            return "✓ Todas las verificaciones pasadas"
        return "✗ Fallos: " + "; ".join(f"{c[0]}: {c[2]}" for c in failed)


def preflight_check(
    entry_price: float,
    stop_loss_price: float,
    take_profit_price: float,
    num_contracts: int,
    direction: str,  # "long" or "short"
    current_daily_pnl: float = 0.0,
    trades_today: int = 0,
    daily_loss_limit: float = 550.0,
    current_drawdown: float = 0.0,
    max_drawdown: float = 2500.0,
) -> PreflightResult:
    """
    Ejecuta todas las verificaciones pre-vuelo para un trade propuesto.

    Parameters
    ----------
    entry_price : Precio de entrada.
    stop_loss_price : Precio de stop loss.
    take_profit_price : Precio de take profit.
    num_contracts : Número de contratos.
    direction : "long" o "short".
    current_daily_pnl : P&L acumulado del día.
    trades_today : Trades ya ejecutados hoy.
    daily_loss_limit : Pérdida máxima diaria.
    current_drawdown : Drawdown actual de la cuenta.
    max_drawdown : Drawdown máximo permitido.

    Returns
    -------
    PreflightResult con todos los checks y resultado final.
    """
    checks: List[Tuple[str, bool, str]] = []

    # =========================================================================
    # CHECK 1: Dirección coherente con SL/TP
    # =========================================================================
    if direction == "long":
        sl_distance = entry_price - stop_loss_price
        tp_distance = take_profit_price - entry_price
    else:
        sl_distance = stop_loss_price - entry_price
        tp_distance = entry_price - take_profit_price

    valid_direction = sl_distance > 0 and tp_distance > 0
    checks.append((
        "Dirección",
        valid_direction,
        f"SL dist={sl_distance:.1f}pts, TP dist={tp_distance:.1f}pts"
    ))

    if not valid_direction:
        return PreflightResult(passed=False, checks=checks)

    # =========================================================================
    # CHECK 2: Ratio Riesgo/Beneficio mínimo
    # =========================================================================
    rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0
    rr_ok = rr_ratio >= MIN_RISK_REWARD_RATIO
    checks.append((
        "R:R Ratio",
        rr_ok,
        f"{rr_ratio:.2f}:1 (mín {MIN_RISK_REWARD_RATIO:.1f}:1)"
    ))

    # =========================================================================
    # CHECK 3: Costo de comisiones + slippage vs ganancia potencial
    # =========================================================================
    total_cost = ROUND_TRIP_COST * num_contracts
    gross_profit = tp_distance * POINT_VALUE * num_contracts
    net_profit = gross_profit - total_cost
    cost_covered = net_profit > 0
    checks.append((
        "Costos cubiertos",
        cost_covered,
        f"Profit bruto=${gross_profit:.2f}, costos=${total_cost:.2f}, neto=${net_profit:.2f}"
    ))

    # =========================================================================
    # CHECK 4: Pérdida máxima por trade
    # =========================================================================
    potential_loss = sl_distance * POINT_VALUE * num_contracts + total_cost
    loss_ok = potential_loss <= MAX_LOSS_PER_TRADE
    checks.append((
        "Pérdida máxima",
        loss_ok,
        f"Pérdida potencial=${potential_loss:.2f} (máx ${MAX_LOSS_PER_TRADE:.2f})"
    ))

    # =========================================================================
    # CHECK 5: Ganancia mínima viable
    # =========================================================================
    gain_ok = net_profit >= MIN_GAIN_PER_TRADE * 0.5  # Margen de tolerancia
    checks.append((
        "Ganancia mínima",
        gain_ok,
        f"Ganancia neta=${net_profit:.2f} (mín deseable ${MIN_GAIN_PER_TRADE:.2f})"
    ))

    # =========================================================================
    # CHECK 6: Límite de trades diarios
    # =========================================================================
    trades_ok = trades_today < MAX_TRADES_PER_DAY
    checks.append((
        "Trades diarios",
        trades_ok,
        f"{trades_today}/{MAX_TRADES_PER_DAY} trades hoy"
    ))

    # =========================================================================
    # CHECK 7: Pérdida diaria acumulada
    # =========================================================================
    worst_case_daily = current_daily_pnl - potential_loss
    daily_ok = abs(worst_case_daily) <= daily_loss_limit if worst_case_daily < 0 else True
    checks.append((
        "Límite diario",
        daily_ok,
        f"PnL día=${current_daily_pnl:.2f}, peor caso=${worst_case_daily:.2f} "
        f"(límite -${daily_loss_limit:.2f})"
    ))

    # =========================================================================
    # CHECK 8: Drawdown de cuenta
    # =========================================================================
    worst_case_dd = current_drawdown + potential_loss
    dd_ok = worst_case_dd < max_drawdown * 0.95  # 5% de margen de seguridad
    checks.append((
        "Drawdown cuenta",
        dd_ok,
        f"DD actual=${current_drawdown:.2f}, peor caso=${worst_case_dd:.2f} "
        f"(máx ${max_drawdown:.2f})"
    ))

    # =========================================================================
    # CHECK 9: Número de contratos válido
    # =========================================================================
    contracts_ok = MIN_CONTRACTS <= num_contracts <= MAX_CONTRACTS
    checks.append((
        "Contratos",
        contracts_ok,
        f"{num_contracts} contratos (rango {MIN_CONTRACTS}-{MAX_CONTRACTS})"
    ))

    # =========================================================================
    # RESULTADO FINAL
    # =========================================================================
    all_passed = all(c[1] for c in checks)
    return PreflightResult(passed=all_passed, checks=checks)


def format_preflight_report(result: PreflightResult) -> str:
    """Genera un reporte legible del preflight check."""
    lines = ["=" * 60, "PREFLIGHT CHECK REPORT", "=" * 60]

    for name, passed, detail in result.checks:
        icon = "✓" if passed else "✗"
        lines.append(f"  {icon} {name}: {detail}")

    lines.append("-" * 60)
    lines.append(f"  RESULTADO: {'APROBADO ✓' if result.passed else 'RECHAZADO ✗'}")
    lines.append("=" * 60)

    return "\n".join(lines)
