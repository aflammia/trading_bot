"""
Detección y seguimiento de Fair Value Gaps (FVG) — concepto central ICT.

Un FVG es un desequilibrio en el precio representado por un gap entre velas:
- Bullish FVG: candle[i-2].high < candle[i].low  (gap alcista)
- Bearish FVG: candle[i-2].low  > candle[i].high (gap bajista)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd


class FVGType(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class FVGStatus(Enum):
    ACTIVE = "active"         # FVG aún no ha sido tocado/roto
    TESTED = "tested"         # Precio entró parcialmente pero no lo rompió
    BROKEN = "broken"         # Precio cerró completamente a través del FVG
    DUBIOUS = "dubious"       # Penetración < 30%, esperando confirmación


@dataclass
class FairValueGap:
    """Representa un Fair Value Gap individual."""
    fvg_type: FVGType
    top: float               # Borde superior del gap
    bottom: float             # Borde inferior del gap
    timestamp: pd.Timestamp   # Momento de formación (vela [i])
    timeframe: str            # '1h', '15m', '5m'
    candle_idx: int           # Índice en el DataFrame original

    # Calculados
    midpoint: float = 0.0
    size: float = 0.0         # Tamaño en puntos

    # Estado dinámico (se actualiza en tiempo real)
    status: FVGStatus = FVGStatus.ACTIVE
    max_penetration_pct: float = 0.0  # Máxima penetración observada (0-1)
    bars_since_dubious: int = 0       # Velas desde que entró en estado "dubious"

    def __post_init__(self):
        self.midpoint = (self.top + self.bottom) / 2.0
        self.size = self.top - self.bottom

    @property
    def is_active(self) -> bool:
        return self.status in (FVGStatus.ACTIVE, FVGStatus.TESTED, FVGStatus.DUBIOUS)

    def distance_from(self, price: float) -> float:
        """Distancia en puntos desde el precio actual al centro del FVG."""
        return abs(price - self.midpoint)


def detect_fvgs(
    df: pd.DataFrame,
    timeframe: str = "1h",
    min_size: Optional[float] = None,
) -> List[FairValueGap]:
    """
    Detecta todos los Fair Value Gaps en un DataFrame OHLCV.

    Parameters
    ----------
    df : pd.DataFrame
        Datos OHLCV con índice DatetimeIndex.
    timeframe : str
        Identificador del timeframe para etiquetar los FVGs.
    min_size : float, optional
        Tamaño mínimo (en puntos) para considerar un FVG. Si None, acepta todos.

    Returns
    -------
    List[FairValueGap]
        Lista de FVGs detectados, ordenados cronológicamente.
    """
    fvgs: List[FairValueGap] = []

    highs = df["High"].values
    lows = df["Low"].values
    timestamps = df.index

    for i in range(2, len(df)):
        # Bullish FVG: gap up (candle i-2 high < candle i low)
        if highs[i - 2] < lows[i]:
            gap_bottom = highs[i - 2]
            gap_top = lows[i]
            size = gap_top - gap_bottom

            if min_size is not None and size < min_size:
                continue

            fvgs.append(FairValueGap(
                fvg_type=FVGType.BULLISH,
                top=gap_top,
                bottom=gap_bottom,
                timestamp=timestamps[i],
                timeframe=timeframe,
                candle_idx=i,
            ))

        # Bearish FVG: gap down (candle i-2 low > candle i high)
        if lows[i - 2] > highs[i]:
            gap_top = lows[i - 2]
            gap_bottom = highs[i]
            size = gap_top - gap_bottom

            if min_size is not None and size < min_size:
                continue

            fvgs.append(FairValueGap(
                fvg_type=FVGType.BEARISH,
                top=gap_top,
                bottom=gap_bottom,
                timestamp=timestamps[i],
                timeframe=timeframe,
                candle_idx=i,
            ))

    return fvgs


def compute_fvg_size_percentile(fvgs: List[FairValueGap], percentile: float = 0.60) -> float:
    """
    Calcula el percentil de tamaño de una lista de FVGs.
    Usado para filtrar FVGs "significativos".
    """
    if not fvgs:
        return 0.0
    sizes = [f.size for f in fvgs]
    return float(np.percentile(sizes, percentile * 100))


def filter_significant_fvgs(
    fvgs: List[FairValueGap],
    current_price: float,
    max_fvgs: int = 4,
    search_range_points: float = 400.0,
    min_size_percentile: float = 0.40,
) -> List[FairValueGap]:
    """
    Filtra los FVGs más relevantes según el manual ICT:
    - Solo activos (no rotos)
    - Dentro del rango de búsqueda del precio actual
    - Tamaño >= percentil configurado
    - Limitados al máximo configurado

    Returns FVGs ordenados por cercanía al precio actual.
    """
    # Solo FVGs activos
    active = [f for f in fvgs if f.is_active]

    if not active:
        return []

    # Filtrar por rango de búsqueda
    in_range = [
        f for f in active
        if f.distance_from(current_price) <= search_range_points
    ]

    if not in_range:
        return []

    # Filtrar por tamaño mínimo (percentil)
    size_threshold = compute_fvg_size_percentile(fvgs, min_size_percentile)
    significant = [f for f in in_range if f.size >= size_threshold]

    # Si no hay suficientes significativos, relajar el filtro
    if len(significant) < 2:
        significant = in_range

    # Ordenar por cercanía al precio actual
    significant.sort(key=lambda f: f.distance_from(current_price))

    return significant[:max_fvgs]


class FVGTracker:
    """
    Rastreador de estado de FVGs en tiempo real.
    Actualiza el estado de cada FVG conforme el precio avanza vela a vela.
    """

    def __init__(self, dubious_break_pct: float = 0.30, dubious_wait_bars: int = 2):
        self.all_fvgs: List[FairValueGap] = []
        self.dubious_break_pct = dubious_break_pct
        self.dubious_wait_bars = dubious_wait_bars

    @property
    def active_bullish(self) -> List[FairValueGap]:
        """FVGs alcistas activos."""
        return [f for f in self.all_fvgs
                if f.fvg_type == FVGType.BULLISH and f.is_active]

    @property
    def active_bearish(self) -> List[FairValueGap]:
        """FVGs bajistas activos."""
        return [f for f in self.all_fvgs
                if f.fvg_type == FVGType.BEARISH and f.is_active]

    @property
    def broken_fvgs(self) -> List[FairValueGap]:
        """FVGs recientemente rotos."""
        return [f for f in self.all_fvgs if f.status == FVGStatus.BROKEN]

    def add_fvgs(self, new_fvgs: List[FairValueGap]):
        """Agrega nuevos FVGs detectados al tracker."""
        for fvg in new_fvgs:
            # Evitar duplicados (mismo timestamp y tipo)
            duplicate = any(
                f.timestamp == fvg.timestamp and f.fvg_type == fvg.fvg_type
                and abs(f.top - fvg.top) < 0.01
                for f in self.all_fvgs
            )
            if not duplicate:
                self.all_fvgs.append(fvg)

    def update(self, candle_high: float, candle_low: float, candle_close: float):
        """
        Actualiza el estado de todos los FVGs activos basado en la vela actual.

        Lógica del manual:
        - Si el precio cierra completamente a través del FVG → BROKEN
        - Si la penetración es < 30% del tamaño → DUBIOUS (esperar 2 velas)
        - Si DUBIOUS y pasan 2 velas sin break completo → volver a ACTIVE
        """
        for fvg in self.all_fvgs:
            if not fvg.is_active:
                continue

            if fvg.fvg_type == FVGType.BULLISH:
                self._update_bullish(fvg, candle_high, candle_low, candle_close)
            else:
                self._update_bearish(fvg, candle_high, candle_low, candle_close)

    def _update_bullish(self, fvg: FairValueGap, high: float, low: float, close: float):
        """
        Actualiza un Bullish FVG.
        Se rompe si el precio cierra POR DEBAJO del bottom del FVG.
        """
        if close < fvg.bottom:
            # Calcular penetración
            penetration = (fvg.bottom - close) / fvg.size if fvg.size > 0 else 1.0
            fvg.max_penetration_pct = max(fvg.max_penetration_pct, penetration)

            if penetration < self.dubious_break_pct:
                # Ruptura dudosa — esperar
                if fvg.status != FVGStatus.DUBIOUS:
                    fvg.status = FVGStatus.DUBIOUS
                    fvg.bars_since_dubious = 0
            else:
                # Ruptura sólida ("en seco")
                fvg.status = FVGStatus.BROKEN
        elif low < fvg.top and close >= fvg.bottom:
            # Precio entró en el gap pero no lo rompió → TESTED
            if fvg.status == FVGStatus.ACTIVE:
                fvg.status = FVGStatus.TESTED

        # Manejar estado DUBIOUS
        if fvg.status == FVGStatus.DUBIOUS:
            fvg.bars_since_dubious += 1
            if fvg.bars_since_dubious >= self.dubious_wait_bars:
                if close >= fvg.bottom:
                    # No se confirmó la ruptura → volver a activo
                    fvg.status = FVGStatus.TESTED
                    fvg.bars_since_dubious = 0
                else:
                    # Se confirmó después de la espera
                    fvg.status = FVGStatus.BROKEN

    def _update_bearish(self, fvg: FairValueGap, high: float, low: float, close: float):
        """
        Actualiza un Bearish FVG.
        Se rompe si el precio cierra POR ENCIMA del top del FVG.
        """
        if close > fvg.top:
            penetration = (close - fvg.top) / fvg.size if fvg.size > 0 else 1.0
            fvg.max_penetration_pct = max(fvg.max_penetration_pct, penetration)

            if penetration < self.dubious_break_pct:
                if fvg.status != FVGStatus.DUBIOUS:
                    fvg.status = FVGStatus.DUBIOUS
                    fvg.bars_since_dubious = 0
            else:
                fvg.status = FVGStatus.BROKEN
        elif high > fvg.bottom and close <= fvg.top:
            if fvg.status == FVGStatus.ACTIVE:
                fvg.status = FVGStatus.TESTED

        if fvg.status == FVGStatus.DUBIOUS:
            fvg.bars_since_dubious += 1
            if fvg.bars_since_dubious >= self.dubious_wait_bars:
                if close <= fvg.top:
                    fvg.status = FVGStatus.TESTED
                    fvg.bars_since_dubious = 0
                else:
                    fvg.status = FVGStatus.BROKEN

    def get_nearest_protective_fvg(
        self,
        price: float,
        trade_direction: str,  # "long" or "short"
    ) -> Optional[FairValueGap]:
        """
        Encuentra el FVG protector más cercano para una entrada.

        Para LONG: necesitamos un Bullish FVG cercano (SL debajo de él)
        Para SHORT: necesitamos un Bearish FVG cercano (SL encima de él)
        """
        if trade_direction == "long":
            candidates = [f for f in self.active_bullish if f.top <= price]
            if not candidates:
                return None
            # El más cercano por arriba del precio
            candidates.sort(key=lambda f: price - f.top)
            return candidates[0]
        else:
            candidates = [f for f in self.active_bearish if f.bottom >= price]
            if not candidates:
                return None
            candidates.sort(key=lambda f: f.bottom - price)
            return candidates[0]

    def count_recently_broken(
        self,
        fvg_type: FVGType,
        since_idx: int,
        current_idx: int,
    ) -> int:
        """
        Cuenta cuántos FVGs de un tipo se han roto recientemente.
        Usado para confirmar tendencia y reversiones.
        """
        count = 0
        for fvg in self.all_fvgs:
            if (fvg.fvg_type == fvg_type
                    and fvg.status == FVGStatus.BROKEN
                    and since_idx <= fvg.candle_idx <= current_idx):
                count += 1
        return count

    def cleanup_old(self, max_age_bars: int = 200):
        """Elimina FVGs muy antiguos para mantener la memoria limpia."""
        if not self.all_fvgs:
            return
        max_idx = max(f.candle_idx for f in self.all_fvgs)
        self.all_fvgs = [
            f for f in self.all_fvgs
            if f.is_active or (max_idx - f.candle_idx) < max_age_bars
        ]


def precompute_fvg_columns(df: pd.DataFrame, timeframe: str = "1h") -> pd.DataFrame:
    """
    Pre-computa columnas de FVG en el DataFrame para uso con Backtrader.
    Agrega columnas: fvg_bullish_top, fvg_bullish_bottom, fvg_bearish_top, fvg_bearish_bottom,
                     fvg_new_bullish, fvg_new_bearish

    IMPORTANTE: Sin look-ahead bias. Cada fila solo usa datos de filas anteriores.
    """
    n = len(df)
    # Columnas para el FVG más reciente activo de cada tipo
    df = df.copy()
    df["fvg_new_bullish"] = False
    df["fvg_new_bearish"] = False
    df["fvg_bull_top"] = np.nan
    df["fvg_bull_bottom"] = np.nan
    df["fvg_bear_top"] = np.nan
    df["fvg_bear_bottom"] = np.nan

    highs = df["High"].values
    lows = df["Low"].values

    for i in range(2, n):
        # Bullish FVG
        if highs[i - 2] < lows[i]:
            df.iloc[i, df.columns.get_loc("fvg_new_bullish")] = True
            df.iloc[i, df.columns.get_loc("fvg_bull_top")] = lows[i]
            df.iloc[i, df.columns.get_loc("fvg_bull_bottom")] = highs[i - 2]

        # Bearish FVG
        if lows[i - 2] > highs[i]:
            df.iloc[i, df.columns.get_loc("fvg_new_bearish")] = True
            df.iloc[i, df.columns.get_loc("fvg_bear_top")] = lows[i - 2]
            df.iloc[i, df.columns.get_loc("fvg_bear_bottom")] = highs[i]

    return df
