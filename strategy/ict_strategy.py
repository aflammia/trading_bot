"""
Estrategia ICT completa integrada con Backtrader.

Implementa el flujo completo del manual:
1. Daily Bias (pre-market) -> determinar dirección
2. Identificar FVGs y liquidez -> encontrar entradas
3. Gestión de posición -> SL/TP/BE/cierre al 90%
4. Kill switches -> protección multinivel
"""
import os
import sys
from datetime import time as dtime, datetime, timedelta
from typing import Optional, List, Dict

import backtrader as bt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import (
    POINT_VALUE, DEFAULT_CONTRACTS,
    BREAK_EVEN_TRIGGER_PCT, CLOSE_AT_PCT_OF_TP,
    MAX_DAILY_LOSS, MAX_TRADES_PER_DAY,
    BIG_LOSS_THRESHOLD, BIG_WIN_THRESHOLD,
    COMMISSION_PER_SIDE, SLIPPAGE_TICKS,
    ACCOUNT_BALANCE, TRAILING_DRAWDOWN_MAX,
    FVG_DUBIOUS_BREAK_PCT, FVG_DUBIOUS_WAIT_BARS,
    DISCOUNT_ZONE_PCT, KILLZONES,
    STRUCTURE_LOOKBACK_4H,
)
from indicators.fvg import (
    FVGType, FVGStatus, FVGTracker, FairValueGap,
    detect_fvgs, filter_significant_fvgs,
)
from indicators.liquidity import (
    LiquidityTracker, LiquidityLevel, LiquidityType, SweepStatus,
    compute_pdh_pdl, find_swing_levels, find_equal_levels,
)
from indicators.market_structure import (
    MarketBias, analyze_4h_trend, detect_swing_points,
    determine_structure, is_move_exhausted, classify_discount_premium,
)
from risk.position_sizing import PositionSizer
from risk.preflight import preflight_check, PreflightResult
from risk.kill_switch import KillSwitchManager


# =============================================================================
# Comisión personalizada para MNQ
# =============================================================================
class MNQCommInfo(bt.CommInfoBase):
    """Comisión para Micro E-mini Nasdaq 100."""
    params = (
        ("commission", COMMISSION_PER_SIDE),
        ("mult", POINT_VALUE),
        ("margin", 1500.0),      # Margen intradía por contrato
        ("stocklike", False),
        ("commtype", bt.CommInfoBase.COMM_FIXED),
    )

    def _getcommission(self, size, price, pseudoexec):
        return abs(size) * self.p.commission

    def getsize(self, price, cash):
        return int(cash / self.p.margin)


# =============================================================================
# Estrategia ICT Principal
# =============================================================================
class ICTStrategy(bt.Strategy):
    """
    Estrategia de trading ICT mimetizada para backtesting con Backtrader.

    Requiere al menos 2 data feeds:
    - datas[0] : TimeFrame base (1H o 15m)
    - datas[1] : TimeFrame superior (4H, resampled)

    Si hay un 3er feed, se usa como diario.
    """

    params = (
        # Risk management
        ("initial_capital", ACCOUNT_BALANCE),
        ("max_daily_loss", MAX_DAILY_LOSS),
        ("max_trades_per_day", MAX_TRADES_PER_DAY),
        ("default_contracts", DEFAULT_CONTRACTS),
        ("break_even_pct", BREAK_EVEN_TRIGGER_PCT),
        ("close_at_pct", CLOSE_AT_PCT_OF_TP),
        ("big_loss_threshold", BIG_LOSS_THRESHOLD),
        ("big_win_threshold", BIG_WIN_THRESHOLD),

        # ICT parameters
        ("fvg_max_1h", 4),
        ("fvg_search_range", 400),
        ("structure_lookback", STRUCTURE_LOOKBACK_4H),
        ("discount_pct", DISCOUNT_ZONE_PCT),

        # Trading hours (UTC) — 8:30-16:00 VET = 12:30-20:00 UTC
        ("trading_start", dtime(12, 30)),
        ("trading_end", dtime(20, 0)),

        # Logging
        ("verbose", True),
    )

    def __init__(self):
        # Data feeds
        self.data_base = self.datas[0]       # Base TF (1H or 15m)
        self.data_4h = self.datas[1] if len(self.datas) > 1 else None
        self.data_daily = self.datas[2] if len(self.datas) > 2 else None

        # ATR indicator
        # FVG and liquidity trackers
        self.fvg_tracker = FVGTracker(
            dubious_break_pct=FVG_DUBIOUS_BREAK_PCT,
            dubious_wait_bars=FVG_DUBIOUS_WAIT_BARS,
        )
        self.liquidity_tracker = LiquidityTracker()

        # Risk managers
        self.position_sizer = PositionSizer(
            initial_equity=self.p.initial_capital
        )
        self.kill_switch = KillSwitchManager(
            initial_balance=self.p.initial_capital,
            max_daily_loss=self.p.max_daily_loss,
        )

        # State tracking
        self._current_date = None
        self._daily_bias: Optional[MarketBias] = None
        self._bias_confidence: float = 0.0
        self._entry_direction: Optional[str] = None  # "long" or "short"
        self._protective_fvg: Optional[FairValueGap] = None
        self._tp_price: Optional[float] = None
        self._sl_price: Optional[float] = None
        self._entry_price: Optional[float] = None
        self._entry_time: Optional[datetime] = None
        self._exit_reason: str = ""
        self._bar_count: int = 0
        self._trades_log: List[Dict] = []
        self._pending_order = None
        self._actual_exit_price: Optional[float] = None
        self._recent_swing_high: Optional[float] = None
        self._recent_swing_low: Optional[float] = None

    def log(self, msg: str, level: str = "INFO"):
        if self.p.verbose:
            dt = self.data_base.datetime.datetime(0)
            print(f"[{dt}] [{level}] {msg}")

    # =========================================================================
    # DAILY BIAS — Ejecutado una vez al inicio de cada día
    # =========================================================================
    def _compute_daily_bias(self):
        """
        Calcula el sesgo diario basado en:
        1. Tendencia 4H
        2. FVGs 1H (cuáles se rompen)
        3. Balance de liquidez
        """
        # Tendencia 4H
        if self.data_4h is not None and len(self.data_4h) >= self.p.structure_lookback:
            # Construir un mini DataFrame de 4H
            df_4h = pd.DataFrame({
                "Open": [self.data_4h.open[-i] for i in range(self.p.structure_lookback - 1, -1, -1)],
                "High": [self.data_4h.high[-i] for i in range(self.p.structure_lookback - 1, -1, -1)],
                "Low": [self.data_4h.low[-i] for i in range(self.p.structure_lookback - 1, -1, -1)],
                "Close": [self.data_4h.close[-i] for i in range(self.p.structure_lookback - 1, -1, -1)],
            })
            trend_4h = analyze_4h_trend(df_4h, lookback=self.p.structure_lookback)
        else:
            trend_4h = MarketBias.NEUTRAL

        # FVGs — analizar qué se rompe
        active_bullish = len(self.fvg_tracker.active_bullish)
        active_bearish = len(self.fvg_tracker.active_bearish)
        broken_bullish = len([f for f in self.fvg_tracker.all_fvgs
                              if f.fvg_type == FVGType.BULLISH and f.status == FVGStatus.BROKEN])
        broken_bearish = len([f for f in self.fvg_tracker.all_fvgs
                              if f.fvg_type == FVGType.BEARISH and f.status == FVGStatus.BROKEN])

        # Score de sesgo
        score = 0
        if trend_4h == MarketBias.BULLISH:
            score += 2
        elif trend_4h == MarketBias.BEARISH:
            score -= 2

        if broken_bullish > broken_bearish:
            score -= 1  # Bullish FVGs rompiendo = bajista
        elif broken_bearish > broken_bullish:
            score += 1

        # Liquidez
        price = self.data_base.close[0]
        buyside = self.liquidity_tracker.get_nearest_buyside(price)
        sellside = self.liquidity_tracker.get_nearest_sellside(price)
        swept_above = self.liquidity_tracker.count_swept_above()
        swept_below = self.liquidity_tracker.count_swept_below()

        if swept_above > swept_below and len(sellside) > 0:
            score -= 1  # Más liquidez tomada arriba -> buscar abajo
        elif swept_below > swept_above and len(buyside) > 0:
            score += 1

        # Determinar sesgo
        self._bias_confidence = min(1.0, abs(score) / 5.0)

        if score >= 2:
            self._daily_bias = MarketBias.BULLISH
            self._entry_direction = "long"
        elif score <= -2:
            self._daily_bias = MarketBias.BEARISH
            self._entry_direction = "short"
        else:
            self._daily_bias = MarketBias.NEUTRAL
            self._entry_direction = None

        self.log(
            f"DAILY BIAS: {self._daily_bias.value} | Score: {score} | "
            f"Conf: {self._bias_confidence:.0%} | 4H: {trend_4h.value} | "
            f"Bull FVG broken: {broken_bullish} | Bear FVG broken: {broken_bearish}"
        )

    # =========================================================================
    # FVG DETECTION AND TRACKING — Cada barra
    # =========================================================================
    def _update_fvgs(self):
        """Detecta nuevos FVGs y actualiza el estado de los existentes."""
        # Solo si tenemos suficientes barras
        if len(self.data_base) < 3:
            return

        high_2 = self.data_base.high[-2]
        high_0 = self.data_base.high[0]
        low_2 = self.data_base.low[-2]
        low_0 = self.data_base.low[0]

        ts = self.data_base.datetime.datetime(0)

        # Bullish FVG
        if high_2 < low_0:
            fvg = FairValueGap(
                fvg_type=FVGType.BULLISH,
                top=low_0,
                bottom=high_2,
                timestamp=pd.Timestamp(ts),
                timeframe="base",
                candle_idx=self._bar_count,
            )
            self.fvg_tracker.add_fvgs([fvg])

        # Bearish FVG
        if low_2 > high_0:
            fvg = FairValueGap(
                fvg_type=FVGType.BEARISH,
                top=low_2,
                bottom=high_0,
                timestamp=pd.Timestamp(ts),
                timeframe="base",
                candle_idx=self._bar_count,
            )
            self.fvg_tracker.add_fvgs([fvg])

        # Actualizar estado de FVGs existentes
        self.fvg_tracker.update(
            self.data_base.high[0],
            self.data_base.low[0],
            self.data_base.close[0],
        )

    # =========================================================================
    # LIQUIDITY TRACKING — Cada barra
    # =========================================================================
    def _update_liquidity(self):
        """Actualiza niveles de liquidez y detecta sweeps."""
        if len(self.data_base) < 10:
            return

        price = self.data_base.close[0]
        ts = pd.Timestamp(self.data_base.datetime.datetime(0))

        # Actualizar sweeps
        self.liquidity_tracker.update(
            self.data_base.high[0],
            self.data_base.low[0],
            self.data_base.close[0],
            ts,
        )

        # Actualizar swing points cada 10 barras
        if self._bar_count % 10 == 0:
            # Construir mini DataFrame de las últimas N barras
            lookback = min(50, len(self.data_base))
            df_mini = pd.DataFrame({
                "High": [self.data_base.high[-i] for i in range(lookback - 1, -1, -1)],
                "Low": [self.data_base.low[-i] for i in range(lookback - 1, -1, -1)],
            })
            swing_highs, swing_lows = find_swing_levels(df_mini, order=3, lookback=lookback)
            self.liquidity_tracker.add_levels(swing_highs + swing_lows)

            # Track recent swings para discount/premium
            if swing_highs:
                self._recent_swing_high = swing_highs[-1].price
            if swing_lows:
                self._recent_swing_low = swing_lows[-1].price

        # PDH/PDL — al inicio de nuevo día
        current_date = self.data_base.datetime.date(0)
        if self._current_date != current_date and len(self.data_base) >= 24:
            # Buscar high/low del día anterior
            prev_high = -np.inf
            prev_low = np.inf
            for i in range(1, min(25, len(self.data_base))):
                bar_date = self.data_base.datetime.date(-i)
                if bar_date != current_date:
                    prev_high = max(prev_high, self.data_base.high[-i])
                    prev_low = min(prev_low, self.data_base.low[-i])
                elif prev_high > -np.inf:
                    break

            if prev_high > -np.inf:
                self.liquidity_tracker.add_levels([
                    LiquidityLevel(LiquidityType.PDH, prev_high, ts,
                                   f"PDH {prev_high:.0f}"),
                    LiquidityLevel(LiquidityType.PDL, prev_low, ts,
                                   f"PDL {prev_low:.0f}"),
                ])

    # =========================================================================
    # ENTRY LOGIC — Buscar oportunidades
    # =========================================================================
    # =========================================================================
    # SESSION / KILLZONE HELPERS
    # =========================================================================
    def _get_current_session(self) -> Optional[str]:
        """
        Return the KILLZONES key matching the current bar's ET time, or None.
        Backtrader feeds from yfinance for NQ=F are in Eastern Time (ET).
        """
        dt = self.data_base.datetime.datetime(0)
        current_time = dt.time()

        for key, zone in KILLZONES.items():
            sh, sm = map(int, zone.start_et.split(":"))
            eh, em = map(int, zone.end_et.split(":"))
            zone_start = dtime(sh, sm)
            zone_end = dtime(eh, em)

            # Standard window: start <= t < end
            if zone_start < zone_end:
                if zone_start <= current_time < zone_end:
                    return key
                continue

            # Overnight window (wrap midnight): t >= start OR t < end
            if current_time >= zone_start or current_time < zone_end:
                return key
        return None

    # =========================================================================
    # ENTRY LOGIC — Buscar oportunidades
    # =========================================================================
    def _check_entry(self):
        """
        Evalúa si hay una oportunidad de entrada según el manual ICT.

        Para LONG:
        1. Bias diario = BULLISH
        2. Un Bearish FVG se rompe (señal alcista)
        3. Existe un Bullish FVG cercano para protección
        4. Entrada "on discount" (no premium)
        5. Preflight check aprobado

        Para SHORT: inverso.
        """
        if self._entry_direction is None:
            return

        if self.position:
            return  # Ya estamos en posición

        if self._pending_order is not None:
            return  # Orden pendiente — evitar doble entrada

        # ── Killzone gate: solo entradas durante NY AM (9:30–11:00 ET) ──────
        if self._get_current_session() != "ny_am":
            return

        price = self.data_base.close[0]

        # Verificar kill switch
        can_trade, reason = self.kill_switch.can_open_trade()
        if not can_trade:
            return

        if self._entry_direction == "long":
            self._check_long_entry(price)
        elif self._entry_direction == "short":
            self._check_short_entry(price)

    def _check_long_entry(self, price: float):
        """Buscar entrada LONG según lógica ICT."""
        # 1. ¿Se rompió un Bearish FVG recientemente?
        recent_bear_breaks = [
            f for f in self.fvg_tracker.all_fvgs
            if f.fvg_type == FVGType.BEARISH
            and f.status == FVGStatus.BROKEN
            and (self._bar_count - f.candle_idx) < 10
        ]
        if not recent_bear_breaks:
            return

        # 2. ¿Hay un Bullish FVG cercano para protección?
        protective = self.fvg_tracker.get_nearest_protective_fvg(price, "long")
        if protective is None:
            return

        # 3. ¿Estamos "on discount"?
        if self._recent_swing_low and self._recent_swing_high:
            zone = classify_discount_premium(
                price, self._recent_swing_low, self._recent_swing_high,
                self.p.discount_pct,
            )
            if zone in ("premium", "extreme_premium"):
                return

        # 4. Calcular SL y TP
        # 4. Calcular SL y TP — SL exactamente en límite del FVG protector (sin buffer)
        sl_price = protective.bottom

        # TP en el siguiente nivel de liquidez arriba (buyside: swings, PDH, equal highs)
        buyside = self.liquidity_tracker.get_nearest_buyside(price)
        if not buyside:
            # Sin nivel de liquidez disponible — skip trade (sin fallback a ATR)
            return
        tp_price = buyside[0].price

        # 5. Preflight check
        sl_points = price - sl_price
        tp_points = tp_price - price

        if sl_points <= 0 or tp_points <= 0:
            return

        num_contracts = self.position_sizer.get_position_size(sl_points)

        # Respetar límite de kill switch
        ks_max = self.kill_switch.get_max_contracts()
        if ks_max is not None:
            num_contracts = min(num_contracts, ks_max)

        if num_contracts <= 0:
            return

        pf = preflight_check(
            entry_price=price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            num_contracts=num_contracts,
            direction="long",
            current_daily_pnl=self.kill_switch.daily_pnl,
            trades_today=self.kill_switch.trades_today,
            current_drawdown=self.kill_switch.current_drawdown,
        )

        if not pf.passed:
            self.log(f"LONG RECHAZADO: {pf.summary}", "WARN")
            return

        # 6. EJECUTAR ENTRADA
        self.log(
            f"-> LONG ENTRY @ {price:.1f} | SL={sl_price:.1f} | TP={tp_price:.1f} | "
            f"Contracts={num_contracts} | R:R={tp_points / sl_points:.2f}:1"
        )

        self._entry_price = price
        self._sl_price = sl_price
        self._tp_price = tp_price
        self._entry_time = self.data_base.datetime.datetime(0)
        self._exit_reason = ""
        self._protective_fvg = protective

        self._pending_order = self.buy(size=num_contracts)

    def _check_short_entry(self, price: float):
        """Buscar entrada SHORT según lógica ICT."""
        # 1. ¿Se rompió un Bullish FVG recientemente?
        recent_bull_breaks = [
            f for f in self.fvg_tracker.all_fvgs
            if f.fvg_type == FVGType.BULLISH
            and f.status == FVGStatus.BROKEN
            and (self._bar_count - f.candle_idx) < 10
        ]
        if not recent_bull_breaks:
            return

        # 2. ¿Hay un Bearish FVG cercano para protección?
        protective = self.fvg_tracker.get_nearest_protective_fvg(price, "short")
        if protective is None:
            return

        # 3. ¿Estamos "on premium"? (para SHORT, evitar zona discount)
        if self._recent_swing_low and self._recent_swing_high:
            zone = classify_discount_premium(
                price, self._recent_swing_low, self._recent_swing_high,
                self.p.discount_pct,
            )
            if zone in ("discount",):
                return

        # 4. Calcular SL y TP
        # 4. Calcular SL y TP — SL exactamente en límite del FVG protector (sin buffer)
        sl_price = protective.top

        # TP en el siguiente nivel de liquidez abajo (sellside: swings, PDL, equal lows)
        sellside = self.liquidity_tracker.get_nearest_sellside(price)
        if not sellside:
            # Sin nivel de liquidez disponible — skip trade (sin fallback a ATR)
            return
        tp_price = sellside[0].price

        # 5. Preflight check
        sl_points = sl_price - price
        tp_points = price - tp_price

        if sl_points <= 0 or tp_points <= 0:
            return

        num_contracts = self.position_sizer.get_position_size(sl_points)

        ks_max = self.kill_switch.get_max_contracts()
        if ks_max is not None:
            num_contracts = min(num_contracts, ks_max)

        if num_contracts <= 0:
            return

        pf = preflight_check(
            entry_price=price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            num_contracts=num_contracts,
            direction="short",
            current_daily_pnl=self.kill_switch.daily_pnl,
            trades_today=self.kill_switch.trades_today,
            current_drawdown=self.kill_switch.current_drawdown,
        )

        if not pf.passed:
            self.log(f"SHORT RECHAZADO: {pf.summary}", "WARN")
            return

        # 6. EJECUTAR ENTRADA
        self.log(
            f"-> SHORT ENTRY @ {price:.1f} | SL={sl_price:.1f} | TP={tp_price:.1f} | "
            f"Contracts={num_contracts} | R:R={tp_points / sl_points:.2f}:1"
        )

        self._entry_price = price
        self._sl_price = sl_price
        self._tp_price = tp_price
        self._entry_time = self.data_base.datetime.datetime(0)
        self._exit_reason = ""
        self._protective_fvg = protective

        self._pending_order = self.sell(size=num_contracts)

    # =========================================================================
    # EXIT / POSITION MANAGEMENT — Cada barra durante un trade abierto
    # =========================================================================
    def _manage_position(self):
        """
        Gestión de posición abierta:
        1. Check SL/TP
        2. Break even al 50% del TP si el precio gira
        3. Cierre al 90% del TP
        4. Ruptura del FVG protector -> salir
        """
        if not self.position or self._entry_price is None:
            return

        price = self.data_base.close[0]
        high = self.data_base.high[0]
        low = self.data_base.low[0]
        size = self.position.size

        is_long = size > 0

        if is_long:
            unrealized_pnl = (price - self._entry_price) * POINT_VALUE * abs(size)
            tp_total = (self._tp_price - self._entry_price) * POINT_VALUE * abs(size)
        else:
            unrealized_pnl = (self._entry_price - price) * POINT_VALUE * abs(size)
            tp_total = (self._entry_price - self._tp_price) * POINT_VALUE * abs(size)

        # --- CHECK 1: Stop Loss ---
        if is_long and low <= self._sl_price:
            self.log(f"X SL HIT (LONG) @ ~{self._sl_price:.1f}", "EXIT")
            self.close()
            return
        elif not is_long and high >= self._sl_price:
            self.log(f"X SL HIT (SHORT) @ ~{self._sl_price:.1f}", "EXIT")
            self.close()
            return

        # --- CHECK 2: Take Profit completo ---
        if is_long and high >= self._tp_price:
            self.log(f"OK TP HIT (LONG) @ ~{self._tp_price:.1f}", "EXIT")
            self.close()
            return
        elif not is_long and low <= self._tp_price:
            self.log(f"OK TP HIT (SHORT) @ ~{self._tp_price:.1f}", "EXIT")
            self.close()
            return

        # --- CHECK 3: Cierre al 90% del TP ---
        if tp_total > 0 and unrealized_pnl >= tp_total * self.p.close_at_pct:
            self.log(
                f"OK 90% TP alcanzado: ${unrealized_pnl:.0f} / ${tp_total:.0f}", "EXIT"
            )
            self.close()
            return

        # --- CHECK 4: Break Even ---
        if tp_total > 0 and unrealized_pnl >= tp_total * self.p.break_even_pct:
            # ¿El precio está girando?  Check si FVGs a favor se están rompiendo
            # Note: fvg_tracker.update() was already called in _update_fvgs() this bar
            if self._protective_fvg is not None:
                if is_long:
                    # Si Bullish FVGs de soporte se rompen -> BE
                    supporting_broken = any(
                        f.fvg_type == FVGType.BULLISH
                        and f.status == FVGStatus.BROKEN
                        and f.candle_idx > self._bar_count - 5
                        for f in self.fvg_tracker.all_fvgs
                    )
                else:
                    supporting_broken = any(
                        f.fvg_type == FVGType.BEARISH
                        and f.status == FVGStatus.BROKEN
                        and f.candle_idx > self._bar_count - 5
                        for f in self.fvg_tracker.all_fvgs
                    )

                if supporting_broken:
                    self.log(
                        f"<> BREAK EVEN @ {unrealized_pnl:.0f} — FVGs de soporte rotos", "EXIT"
                    )
                    self._exit_reason = "Break Even"
                    self.close()
                    return

        # --- CHECK 5: Ruptura del FVG protector ("en seco") ---
        if self._protective_fvg is not None and self._protective_fvg.status == FVGStatus.BROKEN:
            self.log(
                f"X FVG PROTECTOR ROTO ({self._protective_fvg.fvg_type.value}) — salir", "EXIT"
            )
            self._exit_reason = "FVG Protector Roto"
            self.close()
            return

    # =========================================================================
    # TRADING HOURS CHECK — NYSE Open + VET Forced Close
    # =========================================================================
    def _is_trading_hours(self) -> bool:
        """
        Check if current time is within allowed trading hours.

        Rules:
        - Opens: 9:30 AM ET (NYSE market open)
        - Force close: 4:00 PM VET (UTC-4) — fixed, no DST

        Since Backtrader data is in ET timezone:
        - NYSE open = 9:30 AM ET (always)
        - VET close at 4:00 PM VET (UTC-4):
          * During EDT (ET=UTC-4): 4:00 PM VET = 4:00 PM ET
          * During EST (ET=UTC-5): 4:00 PM VET = 3:00 PM ET

        We compute the ET-equivalent of 4:00 PM VET dynamically.
        """
        dt = self.data_base.datetime.datetime(0)
        current_time = dt.time()

        # NYSE opens at 9:30 AM ET regardless of DST
        nyse_open = dtime(9, 30)

        # Calculate forced close time in ET
        # VET is always UTC-4. ET is UTC-5 (EST) or UTC-4 (EDT).
        # Force close = 4:00 PM VET = 20:00 UTC
        # In ET: if EDT (UTC-4) -> 20:00 - 4 = 16:00 ET
        #        if EST (UTC-5) -> 20:00 - 5 = 15:00 ET
        force_close_et = self._get_vet_close_in_et(dt)

        return nyse_open <= current_time <= force_close_et

    def _get_vet_close_in_et(self, dt: datetime) -> dtime:
        """
        Convert 4:00 PM VET (UTC-4) to Eastern Time equivalent.

        VET is always UTC-4 (no DST).
        ET switches between UTC-5 (EST, Nov-Mar) and UTC-4 (EDT, Mar-Nov).

        4:00 PM VET = 20:00 UTC
        - During EDT: 20:00 - 4 = 16:00 ET
        - During EST: 20:00 - 5 = 15:00 ET
        """
        try:
            import pytz
            et_tz = pytz.timezone('US/Eastern')
            # Make dt timezone-aware in ET
            dt_aware = et_tz.localize(dt)
            # Get UTC offset in hours
            utc_offset_hours = dt_aware.utcoffset().total_seconds() / 3600
            # VET close is 20:00 UTC -> convert to ET
            force_close_utc_hour = 20  # 4:00 PM VET = 20:00 UTC
            force_close_et_hour = force_close_utc_hour + int(utc_offset_hours)
            return dtime(force_close_et_hour, 0)
        except ImportError:
            # Fallback: assume EST (conservative, closes earlier)
            return dtime(15, 0)

    def _should_force_close(self) -> bool:
        """
        Check if we must force-close all positions.
        Returns True if current time >= 4:00 PM VET (in ET equivalent).
        Called every bar when position is open.
        """
        dt = self.data_base.datetime.datetime(0)
        current_time = dt.time()
        force_close_et = self._get_vet_close_in_et(dt)

        # Force close 5 minutes before deadline to ensure execution
        close_min = force_close_et.hour * 60 + force_close_et.minute - 5
        close_warning = dtime(close_min // 60, close_min % 60)

        return current_time >= close_warning

    # =========================================================================
    # MAIN LOOP — next() de Backtrader
    # =========================================================================
    def next(self):
        """Método principal ejecutado en cada barra."""
        self._bar_count += 1

        # Solo operar en días de semana
        current_dt = self.data_base.datetime.datetime(0)
        if current_dt.weekday() >= 5:
            return

        # Actualizar FVGs y liquidez
        self._update_fvgs()
        self._update_liquidity()

        # Nuevo día -> recalcular daily bias
        current_date = current_dt.date()
        if self._current_date != current_date:
            self._current_date = current_date
            self.kill_switch.new_day(current_date)
            self._compute_daily_bias()
            self.fvg_tracker.cleanup_old()

        # Forced close check: 4:00 PM VET (UTC-4) — no exceptions
        if self.position and self._should_force_close():
            self.log(
                f"FORCED CLOSE at VET 4:00 PM deadline | "
                f"ET time: {current_dt.time()}",
                "EXIT"
            )
            self._exit_reason = "Forced Close (VET 4PM)"
            self.close()
            return

        # ── Session-based close: force close on NY Lunch entry (12:00 ET) ───
        if self.position:
            _sk = self._get_current_session()
            _kz = KILLZONES.get(_sk) if _sk else None
            if _kz is not None and _kz.close_on_enter:
                self.log(
                    f"FORCED CLOSE: {_kz.name} killzone ({_kz.start_et} ET)",
                    "EXIT",
                )
                self._exit_reason = f"Session Close ({_kz.name})"
                self.close()
                return

        # Check if within NYSE trading hours (9:30 ET - close)
        if not self._is_trading_hours():
            # Outside hours: do not open new positions
            if self.position:
                # Still manage existing position (SL/TP) even outside hours
                self._manage_position()
            return

        # Within trading hours: manage or seek entry
        if self.position:
            self._manage_position()
        else:
            # Do not open new positions if we're in the 5-min forced-close buffer
            if not self._should_force_close():
                self._check_entry()

    # =========================================================================
    # ORDER NOTIFICATIONS
    # =========================================================================
    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"COMPRA EJECUTADA @ {order.executed.price:.1f} | "
                    f"Size={order.executed.size} | Cost=${order.executed.comm:.2f}",
                    "ORDER"
                )
            else:
                self.log(
                    f"VENTA EJECUTADA @ {order.executed.price:.1f} | "
                    f"Size={order.executed.size} | Cost=${order.executed.comm:.2f}",
                    "ORDER"
                )
            # Capture actual fill price for exit trades (position closed after this)
            if self._entry_price is not None and not self.position:
                self._actual_exit_price = order.executed.price
            self._pending_order = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Orden {order.status}: cancelada/rechazada", "WARN")
            self._pending_order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            pnl = trade.pnl
            pnl_net = trade.pnlcomm

            self.log(
                f"{'WIN' if pnl_net > 0 else 'LOSS'}: "
                f"Gross=${pnl:.2f} | Net=${pnl_net:.2f} | "
                f"Comm=${trade.commission:.2f}",
                "TRADE"
            )

            # Registrar en los managers de riesgo
            self.position_sizer.record_trade(pnl_net)
            self.kill_switch.record_trade(pnl_net)

            # Log del trade
            self._trades_log.append({
                "timestamp": self.data_base.datetime.datetime(0),
                "direction": "long" if trade.long else "short",
                "entry_price": self._entry_price,
                "exit_price": self._actual_exit_price if self._actual_exit_price is not None else self.data_base.close[0],
                "sl_price": self._sl_price,
                "tp_price": self._tp_price,
                "pnl_gross": pnl,
                "pnl_net": pnl_net,
                "commission": trade.commission,
                "contracts": abs(trade.size),
                "reason": self._exit_reason or "Manual",
                "entry_time": self._entry_time,
                "exit_time": self.data_base.datetime.datetime(0),
            })

            # Reset state
            self._entry_price = None
            self._sl_price = None
            self._tp_price = None
            self._entry_time = None
            self._exit_reason = ""
            self._protective_fvg = None
            self._actual_exit_price = None

    # =========================================================================
    # STOP — Llamado al finalizar el backtest
    # =========================================================================
    def stop(self):
        """Genera resumen al finalizar."""
        total_trades = len(self._trades_log)
        if total_trades == 0:
            self.log("=" * 50)
            self.log("SIN TRADES EJECUTADOS")
            self.log("=" * 50)
            return

        wins = [t for t in self._trades_log if t["pnl_net"] > 0]
        losses = [t for t in self._trades_log if t["pnl_net"] <= 0]

        total_pnl = sum(t["pnl_net"] for t in self._trades_log)
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        avg_win = np.mean([t["pnl_net"] for t in wins]) if wins else 0
        avg_loss = np.mean([t["pnl_net"] for t in losses]) if losses else 0

        self.log("=" * 60)
        self.log("RESUMEN DE BACKTESTING")
        self.log("=" * 60)
        self.log(f"Total trades:    {total_trades}")
        self.log(f"Wins/Losses:     {len(wins)}/{len(losses)}")
        self.log(f"Win Rate:        {win_rate:.1%}")
        self.log(f"P&L Total:       ${total_pnl:+,.2f}")
        self.log(f"Avg Win:         ${avg_win:+,.2f}")
        self.log(f"Avg Loss:        ${avg_loss:+,.2f}")
        self.log(f"Profit Factor:   {abs(sum(t['pnl_net'] for t in wins)) / abs(sum(t['pnl_net'] for t in losses)):.2f}" if losses and sum(t['pnl_net'] for t in losses) != 0 else "Profit Factor:   N/A")
        self.log(f"Final Balance:   ${self.broker.getvalue():,.2f}")
        self.log(f"Max Drawdown:    ${self.kill_switch.current_drawdown:,.2f}")
        self.log("=" * 60)

    def get_trades_df(self) -> pd.DataFrame:
        """Retorna los trades como DataFrame para análisis posterior."""
        if not self._trades_log:
            return pd.DataFrame()
        return pd.DataFrame(self._trades_log)
