"""
Dimensionamiento de posición usando Criterio de Kelly fraccionado.

Kelly Fraction = f * (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win

Donde f es la fracción de Kelly (0.25 - 0.50) para proteger el capital.
"""
import numpy as np
from typing import Optional, Tuple

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import (
    POINT_VALUE, ACCOUNT_BALANCE,
    DEFAULT_CONTRACTS, MIN_CONTRACTS, MAX_CONTRACTS,
    KELLY_FRACTION_DEFAULT, KELLY_FRACTION_MIN, KELLY_FRACTION_MAX,
    MAX_LOSS_PER_TRADE, TRAILING_DRAWDOWN_MAX,
    RECOVERY_CONTRACTS, BAD_STREAK_DAYS, BAD_STREAK_LOSS_PER_DAY,
)


def compute_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_mult: float = KELLY_FRACTION_DEFAULT,
) -> float:
    """
    Calcula el porcentaje de capital a arriesgar usando Kelly fraccionado.

    Parameters
    ----------
    win_rate : float [0, 1]
        Tasa de aciertos histórica.
    avg_win : float
        Ganancia promedio por trade ganador (USD).
    avg_loss : float
        Pérdida promedio por trade perdedor (USD, valor positivo).
    kelly_mult : float [0.25, 0.50]
        Fracción del Kelly completo a usar.

    Returns
    -------
    float : Fracción del capital a arriesgar [0, kelly_mult].
    """
    if avg_win <= 0 or avg_loss <= 0 or win_rate <= 0:
        return 0.0

    # Kelly criterion: f* = (p * b - q) / b
    # donde p = win_rate, q = 1-p, b = avg_win / avg_loss
    b = avg_win / avg_loss
    q = 1.0 - win_rate
    full_kelly = (win_rate * b - q) / b

    if full_kelly <= 0:
        return 0.0

    # Aplicar fracción conservadora
    fractional = full_kelly * kelly_mult
    return max(0.0, min(fractional, kelly_mult))


def calculate_position_size(
    account_equity: float,
    risk_per_trade_pct: float,
    stop_loss_points: float,
    point_value: float = POINT_VALUE,
    max_contracts: int = MAX_CONTRACTS,
    min_contracts: int = MIN_CONTRACTS,
) -> int:
    """
    Calcula el número de contratos basado en el riesgo.

    Parameters
    ----------
    account_equity : float
        Capital actual disponible.
    risk_per_trade_pct : float
        % del capital a arriesgar (calculado por Kelly, e.g., 0.02 = 2%).
    stop_loss_points : float
        Distancia al SL en puntos.
    point_value : float
        Valor por punto por contrato ($2 para MNQ).
    max_contracts : int
        Máximo de contratos permitidos.
    min_contracts : int
        Mínimo de contratos.

    Returns
    -------
    int : Número de contratos a operar.
    """
    if stop_loss_points <= 0:
        return 0

    risk_amount = account_equity * risk_per_trade_pct
    risk_per_contract = stop_loss_points * point_value

    # Verificar que la pérdida por contrato no exceda el máximo
    if risk_per_contract * min_contracts > MAX_LOSS_PER_TRADE:
        # Reducir a lo máximo permitido
        contracts = max(1, int(MAX_LOSS_PER_TRADE / risk_per_contract))
    else:
        contracts = int(risk_amount / risk_per_contract)

    # Aplicar límites
    contracts = max(min_contracts, min(contracts, max_contracts))

    # Verificación final: la pérdida potencial no debe exceder el máximo absoluto
    potential_loss = contracts * risk_per_contract
    if potential_loss > MAX_LOSS_PER_TRADE:
        contracts = max(1, int(MAX_LOSS_PER_TRADE / risk_per_contract))

    return contracts


def adjust_for_drawdown(
    base_contracts: int,
    current_drawdown: float,
    max_drawdown: float = TRAILING_DRAWDOWN_MAX,
    reduce_threshold: float = 0.80,  # 80% del DD máximo → reducir
) -> int:
    """
    Ajusta el número de contratos basado en el drawdown actual.

    Si el drawdown actual es > 80% del máximo → usar contratos de recuperación.
    Si el drawdown actual es > 95% del máximo → parar trading.

    Returns contratos ajustados (puede ser 0 si debe parar).
    """
    dd_pct = current_drawdown / max_drawdown if max_drawdown > 0 else 0

    if dd_pct >= 0.96:
        # Muy cerca del límite → PARAR
        return 0
    elif dd_pct >= reduce_threshold:
        # Reducir contratos
        return min(base_contracts, RECOVERY_CONTRACTS)
    else:
        return base_contracts


def adjust_for_streak(
    base_contracts: int,
    recent_daily_pnls: list,
    bad_days_threshold: int = BAD_STREAK_DAYS,
    bad_loss_threshold: float = BAD_STREAK_LOSS_PER_DAY,
) -> int:
    """
    Ajusta contratos si hay una mala racha.

    Si los últimos N días son todos negativos con pérdidas significativas → reducir.
    """
    if len(recent_daily_pnls) < bad_days_threshold:
        return base_contracts

    recent = recent_daily_pnls[-bad_days_threshold:]
    all_bad = all(pnl < -bad_loss_threshold for pnl in recent)

    if all_bad:
        return min(base_contracts, RECOVERY_CONTRACTS)

    return base_contracts


class PositionSizer:
    """
    Gestor centralizado de dimensionamiento de posición.
    Mantiene estadísticas históricas para el cálculo de Kelly.
    """

    def __init__(
        self,
        initial_equity: float = ACCOUNT_BALANCE,
        kelly_fraction: float = KELLY_FRACTION_DEFAULT,
    ):
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.kelly_fraction = kelly_fraction

        # Historial para cálculo de Kelly
        self.wins: list = []
        self.losses: list = []
        self.daily_pnls: list = []

        # Drawdown tracking
        self.peak_equity = initial_equity
        self.current_drawdown = 0.0

    @property
    def win_rate(self) -> float:
        total = len(self.wins) + len(self.losses)
        return len(self.wins) / total if total > 0 else 0.5

    @property
    def avg_win(self) -> float:
        return np.mean(self.wins) if self.wins else 0.0

    @property
    def avg_loss(self) -> float:
        return np.mean(self.losses) if self.losses else 0.0

    def record_trade(self, pnl: float):
        """Registra un trade completado."""
        if pnl > 0:
            self.wins.append(pnl)
        elif pnl < 0:
            self.losses.append(abs(pnl))

        self.current_equity += pnl
        self.peak_equity = max(self.peak_equity, self.current_equity)
        self.current_drawdown = self.peak_equity - self.current_equity

    def record_daily_pnl(self, pnl: float):
        """Registra P&L diario para tracking de rachas."""
        self.daily_pnls.append(pnl)

    def get_position_size(self, stop_loss_points: float) -> int:
        """
        Calcula el número de contratos óptimo para el próximo trade.

        Combina Kelly criterion con ajustes por drawdown y rachas.
        """
        # Calcular riesgo por Kelly
        if len(self.wins) >= 5 and len(self.losses) >= 3:
            risk_pct = compute_kelly_fraction(
                self.win_rate, self.avg_win, self.avg_loss, self.kelly_fraction
            )
        else:
            # No hay suficiente historial → usar valor fijo conservador
            risk_pct = 0.01  # 1% del capital

        # Calcular contratos base
        base = calculate_position_size(
            self.current_equity, risk_pct, stop_loss_points
        )

        # Ajustar por drawdown
        base = adjust_for_drawdown(base, self.current_drawdown)

        # Ajustar por racha
        base = adjust_for_streak(base, self.daily_pnls)

        # Mínimo de 1 contrato si se permite operar
        return max(1, base) if base > 0 else 0

    def should_stop_trading(self) -> Tuple[bool, str]:
        """
        Verifica si debe dejar de operar por completo.

        Returns
        -------
        Tuple[bool, str] : (debe_parar, razón)
        """
        if self.current_drawdown >= TRAILING_DRAWDOWN_MAX * 0.96:
            return True, f"Drawdown ({self.current_drawdown:.0f}) cercano al límite ({TRAILING_DRAWDOWN_MAX:.0f})"

        if self.current_equity <= self.initial_equity - TRAILING_DRAWDOWN_MAX:
            return True, f"Equity ({self.current_equity:.0f}) por debajo del piso"

        return False, ""
