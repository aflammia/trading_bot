"""
Kill Switches multinivel para protección del capital.

Tres niveles de protección:
1. Trade level: ATR-based stops
2. Daily level: Pérdida máxima diaria
3. System level: Trailing drawdown, rachas perdedoras, anomalías
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime, date

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import (
    MAX_DAILY_LOSS, ACCOUNT_BALANCE, TRAILING_DRAWDOWN_MAX,
    KILL_SWITCH_DAILY_DRAWDOWN_PCT, KILL_SWITCH_REDUCE_CONTRACTS_DD,
    KILL_SWITCH_STOP_ALL_DD, MAX_TRADES_PER_DAY,
    BIG_LOSS_THRESHOLD, BIG_WIN_THRESHOLD,
)


class KillSwitchLevel:
    """Niveles de severidad del kill switch."""
    NONE = 0            # Sin restricción
    REDUCE = 1          # Reducir contratos
    STOP_DAY = 2        # Parar por hoy
    STOP_ALL = 3        # Parar todo hasta revisión manual


@dataclass
class KillSwitchState:
    """Estado actual del kill switch."""
    level: int = KillSwitchLevel.NONE
    reason: str = ""
    triggered_at: Optional[datetime] = None
    can_trade: bool = True
    max_contracts: Optional[int] = None  # None = sin límite extra


class KillSwitchManager:
    """
    Gestor centralizado de kill switches.

    Monitorea continuamente:
    1. P&L diario
    2. Drawdown trailing de la cuenta
    3. Número de trades por día
    4. Rachas de pérdidas
    5. Tamaño de trades individuales (big win / big loss)
    """

    def __init__(
        self,
        initial_balance: float = ACCOUNT_BALANCE,
        max_daily_loss: float = MAX_DAILY_LOSS,
        trailing_dd_max: float = TRAILING_DRAWDOWN_MAX,
    ):
        self.initial_balance = initial_balance
        self.max_daily_loss = max_daily_loss
        self.trailing_dd_max = trailing_dd_max

        # Estado del día
        self._daily_pnl: float = 0.0
        self._trades_today: int = 0
        self._current_date: Optional[date] = None
        self._big_events_today: List[str] = []

        # Estado de la cuenta
        self._balance: float = initial_balance
        self._peak_balance: float = initial_balance
        self._trailing_dd_floor: float = initial_balance - trailing_dd_max

        # Historial
        self._daily_pnls: List[float] = []
        self._trade_pnls: List[float] = []

        # Estado del kill switch
        self.state = KillSwitchState()

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def trades_today(self) -> int:
        return self._trades_today

    @property
    def current_drawdown(self) -> float:
        return self._peak_balance - self._balance

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def trailing_dd_floor(self) -> float:
        return self._trailing_dd_floor

    def new_day(self, current_date: date):
        """Resetea los contadores diarios para un nuevo día de trading."""
        if self._current_date != current_date:
            # Guardar P&L del día anterior
            if self._current_date is not None:
                self._daily_pnls.append(self._daily_pnl)

            self._current_date = current_date
            self._daily_pnl = 0.0
            self._trades_today = 0
            self._big_events_today = []

            # Resetear kill switch si solo era diario
            if self.state.level <= KillSwitchLevel.STOP_DAY:
                self.state = KillSwitchState()

    def record_trade(self, pnl: float, timestamp: Optional[datetime] = None):
        """
        Registra un trade completado y evalúa todos los kill switches.

        Parameters
        ----------
        pnl : float
            P&L del trade en USD.
        timestamp : datetime, optional
            Timestamp del cierre del trade.
        """
        self._trades_today += 1
        self._daily_pnl += pnl
        self._balance += pnl
        self._trade_pnls.append(pnl)

        # Actualizar peak y trailing DD floor
        if self._balance > self._peak_balance:
            self._peak_balance = self._balance

            # El trailing DD floor sube, pero se frena en $50,000
            # (según reglas de OneUpTrader, el piso sube hasta que el balance
            # alcanza la marca de $50,000 + $2,500 = $52,500)
            if self._peak_balance <= self.initial_balance + self.trailing_dd_max:
                self._trailing_dd_floor = self._peak_balance - self.trailing_dd_max
            else:
                # Después de $52,500, el piso se queda en $50,000
                self._trailing_dd_floor = max(
                    self._trailing_dd_floor,
                    self.initial_balance
                )

        # Evaluar todos los checks
        self._evaluate_all(timestamp)

    def _evaluate_all(self, timestamp: Optional[datetime] = None):
        """Evalúa todos los kill switches y actualiza el estado."""

        # =====================================================================
        # CHECK 1: Pérdida diaria máxima
        # =====================================================================
        if self._daily_pnl <= -self.max_daily_loss:
            self.state = KillSwitchState(
                level=KillSwitchLevel.STOP_DAY,
                reason=f"Pérdida diaria -${abs(self._daily_pnl):.0f} ≥ límite -${self.max_daily_loss:.0f}",
                triggered_at=timestamp,
                can_trade=False,
            )
            return

        # =====================================================================
        # CHECK 2: Big loss en un solo trade → no más trades hoy
        # =====================================================================
        if self._trade_pnls and self._trade_pnls[-1] <= -BIG_LOSS_THRESHOLD:
            if "big_loss" not in self._big_events_today:
                self._big_events_today.append("big_loss")
                self.state = KillSwitchState(
                    level=KillSwitchLevel.STOP_DAY,
                    reason=f"Gran pérdida en un trade: -${abs(self._trade_pnls[-1]):.0f}",
                    triggered_at=timestamp,
                    can_trade=False,
                )
                return

        # =====================================================================
        # CHECK 3: Big win → no más trades hoy (preservar ganancia)
        # =====================================================================
        if self._trade_pnls and self._trade_pnls[-1] >= BIG_WIN_THRESHOLD:
            if "big_win" not in self._big_events_today:
                self._big_events_today.append("big_win")
                self.state = KillSwitchState(
                    level=KillSwitchLevel.STOP_DAY,
                    reason=f"Gran ganancia: +${self._trade_pnls[-1]:.0f} — preservar capital",
                    triggered_at=timestamp,
                    can_trade=False,
                )
                return

        # =====================================================================
        # CHECK 4: Máximo de trades diarios
        # =====================================================================
        if self._trades_today >= MAX_TRADES_PER_DAY:
            self.state = KillSwitchState(
                level=KillSwitchLevel.STOP_DAY,
                reason=f"Máximo de trades alcanzado: {self._trades_today}/{MAX_TRADES_PER_DAY}",
                triggered_at=timestamp,
                can_trade=False,
            )
            return

        # =====================================================================
        # CHECK 5: Trailing Drawdown — STOP ALL
        # =====================================================================
        if self._balance <= self._trailing_dd_floor:
            self.state = KillSwitchState(
                level=KillSwitchLevel.STOP_ALL,
                reason=f"Balance ${self._balance:.0f} ≤ piso trailing ${self._trailing_dd_floor:.0f}",
                triggered_at=timestamp,
                can_trade=False,
            )
            return

        # =====================================================================
        # CHECK 6: Drawdown acercándose al límite → REDUCIR
        # =====================================================================
        dd = self.current_drawdown
        if dd >= KILL_SWITCH_STOP_ALL_DD:
            self.state = KillSwitchState(
                level=KillSwitchLevel.STOP_ALL,
                reason=f"Drawdown ${dd:.0f} ≥ ${KILL_SWITCH_STOP_ALL_DD}",
                triggered_at=timestamp,
                can_trade=False,
            )
            return
        elif dd >= KILL_SWITCH_REDUCE_CONTRACTS_DD:
            self.state = KillSwitchState(
                level=KillSwitchLevel.REDUCE,
                reason=f"Drawdown ${dd:.0f} ≥ ${KILL_SWITCH_REDUCE_CONTRACTS_DD} — reducir contratos",
                triggered_at=timestamp,
                can_trade=True,
                max_contracts=2,
            )
            return

        # =====================================================================
        # CHECK 7: Daily drawdown porcentual
        # =====================================================================
        daily_dd_pct = abs(self._daily_pnl) / self._balance if self._balance > 0 else 0
        if self._daily_pnl < 0 and daily_dd_pct >= KILL_SWITCH_DAILY_DRAWDOWN_PCT:
            self.state = KillSwitchState(
                level=KillSwitchLevel.STOP_DAY,
                reason=f"DD diario {daily_dd_pct:.1%} ≥ {KILL_SWITCH_DAILY_DRAWDOWN_PCT:.0%}",
                triggered_at=timestamp,
                can_trade=False,
            )
            return

        # =====================================================================
        # Si todo está bien
        # =====================================================================
        self.state = KillSwitchState(
            level=KillSwitchLevel.NONE,
            can_trade=True,
        )

    def can_open_trade(self) -> Tuple[bool, str]:
        """
        Verifica si se puede abrir un nuevo trade.

        Returns
        -------
        Tuple[bool, str] : (puede_operar, razón_si_no)
        """
        if not self.state.can_trade:
            return False, self.state.reason

        return True, ""

    def get_max_contracts(self) -> Optional[int]:
        """Retorna el límite de contratos impuesto por el kill switch, o None."""
        return self.state.max_contracts

    def get_status_report(self) -> str:
        """Genera un reporte de estado del kill switch."""
        lines = [
            "─" * 50,
            "KILL SWITCH STATUS",
            "─" * 50,
            f"  Balance:       ${self._balance:,.2f}",
            f"  Peak:          ${self._peak_balance:,.2f}",
            f"  DD Floor:      ${self._trailing_dd_floor:,.2f}",
            f"  Current DD:    ${self.current_drawdown:,.2f}",
            f"  Daily P&L:     ${self._daily_pnl:+,.2f}",
            f"  Trades hoy:    {self._trades_today}/{MAX_TRADES_PER_DAY}",
            f"  Kill Level:    {self.state.level} ({self.state.reason or 'OK'})",
            f"  Puede operar:  {'SÍ' if self.state.can_trade else 'NO'}",
            "─" * 50,
        ]
        return "\n".join(lines)
