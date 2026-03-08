"""
Detección y seguimiento de niveles de liquidez ICT.

Incluye: PDH/PDL, Session Highs/Lows, Equal Highs/Lows,
ATH/ATL (rolling), Liquidity Pools, Liquidity Sweeps.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd


class LiquidityType(Enum):
    PDH = "previous_day_high"
    PDL = "previous_day_low"
    SESSION_HIGH = "session_high"
    SESSION_LOW = "session_low"
    EQUAL_HIGH = "equal_high"
    EQUAL_LOW = "equal_low"
    ATH = "all_time_high"
    ATL = "all_time_low"
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"


class SweepStatus(Enum):
    UNTOUCHED = "untouched"    # Nivel aún no alcanzado
    SWEPT = "swept"            # Mecha lo tocó pero cierre regresó (fake out)
    TAKEN = "taken"            # Precio cerró a través del nivel


@dataclass
class LiquidityLevel:
    """Representa un nivel de liquidez individual."""
    level_type: LiquidityType
    price: float
    timestamp: pd.Timestamp
    label: str                  # Etiqueta descriptiva (e.g., "PDH 2025-12-01")
    status: SweepStatus = SweepStatus.UNTOUCHED
    sweep_timestamp: Optional[pd.Timestamp] = None

    @property
    def is_above(self) -> bool:
        """Es un nivel de liquidez superior (buyside)."""
        return self.level_type in (
            LiquidityType.PDH, LiquidityType.SESSION_HIGH,
            LiquidityType.EQUAL_HIGH, LiquidityType.ATH,
            LiquidityType.SWING_HIGH,
        )

    @property
    def is_below(self) -> bool:
        """Es un nivel de liquidez inferior (sellside)."""
        return not self.is_above

    @property
    def is_active(self) -> bool:
        return self.status == SweepStatus.UNTOUCHED


def compute_pdh_pdl(df_1h: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula Previous Day High y Previous Day Low a partir de datos intradía.

    Returns DataFrame con columnas 'pdh' y 'pdl' alineadas al mismo índice.
    """
    df = df_1h.copy()
    # Extraer fecha (sin hora)
    df["date"] = df.index.date

    # Calcular high/low diario
    daily_hl = df.groupby("date").agg(
        day_high=("High", "max"),
        day_low=("Low", "min"),
    )

    # Shift para que sea "previous day"
    daily_hl["pdh"] = daily_hl["day_high"].shift(1)
    daily_hl["pdl"] = daily_hl["day_low"].shift(1)

    # Merge de vuelta al DataFrame original
    df["pdh"] = df["date"].map(daily_hl["pdh"])
    df["pdl"] = df["date"].map(daily_hl["pdl"])

    df.drop(columns=["date"], inplace=True)
    return df


def compute_session_levels(
    df: pd.DataFrame,
    session_name: str,
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
) -> pd.DataFrame:
    """
    Calcula los highs/lows de una sesión específica.
    Los horarios se asumen en la timezone del DataFrame.

    Agrega columnas: {session_name}_high, {session_name}_low
    """
    df = df.copy()
    times = df.index.time

    start_time = pd.Timestamp(f"{start_hour:02d}:{start_minute:02d}").time()
    end_time = pd.Timestamp(f"{end_hour:02d}:{end_minute:02d}").time()

    # Manejar sesiones que cruzan medianoche (como Asia: 20:00-00:00)
    if start_time > end_time:
        mask = (times >= start_time) | (times < end_time)
    else:
        mask = (times >= start_time) & (times < end_time)

    df["_in_session"] = mask
    df["_date"] = df.index.date

    # Para sesiones que cruzan medianoche, agrupar por la fecha de inicio
    if start_time > end_time:
        # Asignar la fecha del inicio de sesión
        session_dates = []
        for idx in df.index:
            t = idx.time()
            if t >= start_time:
                session_dates.append(idx.date())
            elif t < end_time:
                # Pertence a la sesión del día anterior
                session_dates.append((idx - pd.Timedelta(days=1)).date())
            else:
                session_dates.append(idx.date())
        df["_session_date"] = session_dates
    else:
        df["_session_date"] = df["_date"]

    # Calcular H/L por sesión
    session_data = df[df["_in_session"]].groupby("_session_date").agg(
        session_high=("High", "max"),
        session_low=("Low", "min"),
    )

    col_high = f"{session_name}_high"
    col_low = f"{session_name}_low"

    # Mapear de vuelta (usar la sesión anterior como referencia)
    session_data[col_high] = session_data["session_high"].shift(1)
    session_data[col_low] = session_data["session_low"].shift(1)

    df[col_high] = df["_session_date"].map(session_data[col_high])
    df[col_low] = df["_session_date"].map(session_data[col_low])

    # Limpiar columnas temporales
    df.drop(columns=["_in_session", "_date", "_session_date"], inplace=True)

    return df


def compute_all_session_levels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula los niveles de todas las sesiones ICT (horarios ET).
    Asume que el DataFrame tiene timestamps en ET.

    Sesiones:
    - Asia: 20:00 - 00:00 ET
    - London: 02:00 - 05:00 ET
    - NY AM: 09:30 - 11:00 ET
    - NY PM: 13:30 - 16:00 ET
    """
    sessions = [
        ("asia", 20, 0, 0, 0),
        ("london", 2, 0, 5, 0),
        ("ny_am", 9, 30, 11, 0),
        ("ny_pm", 13, 30, 16, 0),
    ]

    for name, sh, sm, eh, em in sessions:
        df = compute_session_levels(df, name, sh, sm, eh, em)

    return df


def find_equal_levels(
    df: pd.DataFrame,
    column: str = "High",
    tolerance_pct: float = 0.001,
    min_touches: int = 2,
    lookback: int = 50,
) -> List[LiquidityLevel]:
    """
    Encuentra niveles donde el precio toca repeated el mismo nivel
    (Equal Highs / Equal Lows).

    Parameters
    ----------
    df : DataFrame con OHLCV
    column : 'High' para equal highs, 'Low' para equal lows
    tolerance_pct : Tolerancia porcentual para considerar "igual"
    min_touches : Mínimo de toques para considerar un nivel
    lookback : Velas de lookback

    Returns
    -------
    List[LiquidityLevel] con niveles detectados
    """
    levels: List[LiquidityLevel] = []

    if len(df) < lookback:
        return levels

    data = df[column].values[-lookback:]
    timestamps = df.index[-lookback:]

    # Agrupar valores similares
    used = set()
    for i in range(len(data)):
        if i in used:
            continue

        cluster = [i]
        for j in range(i + 1, len(data)):
            if j in used:
                continue
            if abs(data[j] - data[i]) / data[i] <= tolerance_pct:
                cluster.append(j)
                used.add(j)

        if len(cluster) >= min_touches:
            avg_price = np.mean([data[k] for k in cluster])
            ltype = LiquidityType.EQUAL_HIGH if column == "High" else LiquidityType.EQUAL_LOW
            levels.append(LiquidityLevel(
                level_type=ltype,
                price=avg_price,
                timestamp=timestamps[cluster[-1]],
                label=f"EQ{'H' if column == 'High' else 'L'} {avg_price:.1f} ({len(cluster)} touches)",
            ))

    return levels


def find_swing_levels(
    df: pd.DataFrame,
    order: int = 5,
    lookback: int = 100,
) -> Tuple[List[LiquidityLevel], List[LiquidityLevel]]:
    """
    Encuentra swing highs y swing lows (máximos/mínimos locales).

    Un swing high es un punto donde High[i] > High[i-order:i] y High[i] > High[i+1:i+order+1].
    Análogo para swing lows.

    Returns
    -------
    Tuple[List[swing_highs], List[swing_lows]]
    """
    swing_highs: List[LiquidityLevel] = []
    swing_lows: List[LiquidityLevel] = []

    start = max(0, len(df) - lookback)
    highs = df["High"].values
    lows = df["Low"].values
    timestamps = df.index

    for i in range(start + order, len(df) - order):
        # Swing High
        if highs[i] == max(highs[i - order: i + order + 1]):
            swing_highs.append(LiquidityLevel(
                level_type=LiquidityType.SWING_HIGH,
                price=highs[i],
                timestamp=timestamps[i],
                label=f"SwH {highs[i]:.1f}",
            ))

        # Swing Low
        if lows[i] == min(lows[i - order: i + order + 1]):
            swing_lows.append(LiquidityLevel(
                level_type=LiquidityType.SWING_LOW,
                price=lows[i],
                timestamp=timestamps[i],
                label=f"SwL {lows[i]:.1f}",
            ))

    return swing_highs, swing_lows


class LiquidityTracker:
    """
    Rastreador centralizado de todos los niveles de liquidez.
    Actualiza el estado conforme el precio se mueve.
    """

    def __init__(self, sweep_min_ticks: int = 2, tick_value: float = 0.50):
        self.levels: List[LiquidityLevel] = []
        self.sweep_threshold = sweep_min_ticks * tick_value
        self.recently_swept: List[LiquidityLevel] = []  # Swept en la última actualización

    def add_levels(self, new_levels: List[LiquidityLevel]):
        """Agrega nuevos niveles, evitando duplicados cercanos."""
        for level in new_levels:
            duplicate = any(
                abs(l.price - level.price) < self.sweep_threshold
                and l.level_type == level.level_type
                for l in self.levels
            )
            if not duplicate:
                self.levels.append(level)

    def update(self, candle_high: float, candle_low: float, candle_close: float,
               timestamp: pd.Timestamp):
        """
        Actualiza el estado de todos los niveles basado en la vela actual.

        Lógica ICT:
        - Si la mecha supera el nivel pero el cierre regresa → SWEPT (liquidity sweep/fake out)
        - Si el cierre supera el nivel → TAKEN
        """
        self.recently_swept = []

        for level in self.levels:
            if not level.is_active:
                continue

            if level.is_above:
                # Nivel de liquidez arriba (buyside)
                if candle_high >= level.price + self.sweep_threshold:
                    if candle_close < level.price:
                        # Mecha tomó el nivel pero cierre volvió → SWEEP
                        level.status = SweepStatus.SWEPT
                        level.sweep_timestamp = timestamp
                        self.recently_swept.append(level)
                    else:
                        # Cierre por encima → TAKEN
                        level.status = SweepStatus.TAKEN
                        level.sweep_timestamp = timestamp
            else:
                # Nivel de liquidez abajo (sellside)
                if candle_low <= level.price - self.sweep_threshold:
                    if candle_close > level.price:
                        level.status = SweepStatus.SWEPT
                        level.sweep_timestamp = timestamp
                        self.recently_swept.append(level)
                    else:
                        level.status = SweepStatus.TAKEN
                        level.sweep_timestamp = timestamp

    def get_nearest_buyside(self, price: float, n: int = 3) -> List[LiquidityLevel]:
        """Obtiene los N niveles de liquidez activos más cercanos POR ENCIMA del precio."""
        above = [l for l in self.levels if l.is_above and l.is_active and l.price > price]
        above.sort(key=lambda l: l.price - price)
        return above[:n]

    def get_nearest_sellside(self, price: float, n: int = 3) -> List[LiquidityLevel]:
        """Obtiene los N niveles de liquidez activos más cercanos POR DEBAJO del precio."""
        below = [l for l in self.levels if l.is_below and l.is_active and l.price < price]
        below.sort(key=lambda l: price - l.price)
        return below[:n]

    def count_swept_above(self, since: Optional[pd.Timestamp] = None) -> int:
        """Cuenta niveles de buyside swept recientemente."""
        swept = [l for l in self.levels
                 if l.is_above and l.status in (SweepStatus.SWEPT, SweepStatus.TAKEN)]
        if since:
            swept = [l for l in swept if l.sweep_timestamp and l.sweep_timestamp >= since]
        return len(swept)

    def count_swept_below(self, since: Optional[pd.Timestamp] = None) -> int:
        """Cuenta niveles de sellside swept recientemente."""
        swept = [l for l in self.levels
                 if l.is_below and l.status in (SweepStatus.SWEPT, SweepStatus.TAKEN)]
        if since:
            swept = [l for l in swept if l.sweep_timestamp and l.sweep_timestamp >= since]
        return len(swept)

    def has_liquidity_above(self, price: float) -> bool:
        """¿Quedan niveles de liquidez activos por encima del precio?"""
        return len(self.get_nearest_buyside(price)) > 0

    def has_liquidity_below(self, price: float) -> bool:
        """¿Quedan niveles de liquidez activos por debajo del precio?"""
        return len(self.get_nearest_sellside(price)) > 0
