"""
Análisis de estructura de mercado ICT.

Determina si el mercado está en estructura alcista, bajista,
lateral/acumulación, o en posible reversión.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd


class MarketBias(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"       # Sin tendencia clara / acumulación
    REVERSAL_UP = "reversal_up"    # Posible giro alcista
    REVERSAL_DOWN = "reversal_down"  # Posible giro bajista


@dataclass
class SwingPoint:
    """Un punto de swing (máximo o mínimo local)."""
    price: float
    timestamp: pd.Timestamp
    idx: int
    is_high: bool     # True = swing high, False = swing low


def detect_swing_points(
    df: pd.DataFrame,
    order: int = 5,
) -> List[SwingPoint]:
    """
    Detecta swing highs y swing lows usando comparación de ventana.

    Un swing high en i requiere:
        High[i] >= max(High[i-order:i]) AND High[i] >= max(High[i+1:i+order+1])
    Análogo para swing lows.

    Parameters
    ----------
    df : DataFrame OHLCV
    order : int
        Número de velas a cada lado para confirmar el swing.

    Returns
    -------
    List[SwingPoint] ordenados cronológicamente.
    """
    swings: List[SwingPoint] = []
    highs = df["High"].values
    lows = df["Low"].values
    timestamps = df.index

    for i in range(order, len(df) - order):
        # Swing High
        window_highs = highs[i - order: i + order + 1]
        if highs[i] == np.max(window_highs):
            swings.append(SwingPoint(
                price=highs[i],
                timestamp=timestamps[i],
                idx=i,
                is_high=True,
            ))

        # Swing Low
        window_lows = lows[i - order: i + order + 1]
        if lows[i] == np.min(window_lows):
            swings.append(SwingPoint(
                price=lows[i],
                timestamp=timestamps[i],
                idx=i,
                is_high=False,
            ))

    # Ordenar cronológicamente
    swings.sort(key=lambda s: s.idx)
    return swings


def determine_structure(
    swing_points: List[SwingPoint],
    min_points: int = 4,
) -> MarketBias:
    """
    Determina la estructura de mercado basándose en los swing points.

    Estructura Alcista: Higher Highs + Higher Lows
    Estructura Bajista: Lower Highs + Lower Lows
    Neutral: Ningún patrón claro

    Parameters
    ----------
    swing_points : Lista de swing points recientes.
    min_points : Mínimo de puntos necesarios para determinar estructura.

    Returns
    -------
    MarketBias
    """
    if len(swing_points) < min_points:
        return MarketBias.NEUTRAL

    # Separar swing highs y swing lows
    s_highs = [s for s in swing_points if s.is_high]
    s_lows = [s for s in swing_points if not s.is_high]

    if len(s_highs) < 2 or len(s_lows) < 2:
        return MarketBias.NEUTRAL

    # Verificar Higher Highs
    higher_highs = all(
        s_highs[i].price > s_highs[i - 1].price
        for i in range(1, len(s_highs))
    )

    # Verificar Higher Lows
    higher_lows = all(
        s_lows[i].price > s_lows[i - 1].price
        for i in range(1, len(s_lows))
    )

    # Verificar Lower Highs
    lower_highs = all(
        s_highs[i].price < s_highs[i - 1].price
        for i in range(1, len(s_highs))
    )

    # Verificar Lower Lows
    lower_lows = all(
        s_lows[i].price < s_lows[i - 1].price
        for i in range(1, len(s_lows))
    )

    if higher_highs and higher_lows:
        return MarketBias.BULLISH
    elif lower_highs and lower_lows:
        return MarketBias.BEARISH
    elif lower_highs and higher_lows:
        # Convergencia → acumulación/lateral
        return MarketBias.NEUTRAL
    else:
        return MarketBias.NEUTRAL


def detect_structure_break(
    swing_points: List[SwingPoint],
    current_price: float,
) -> Optional[MarketBias]:
    """
    Detecta un cambio/giro de estructura (Break of Structure - BOS).

    Un BOS alcista ocurre cuando el precio rompe el último swing high
    en una estructura bajista.

    Un BOS bajista ocurre cuando el precio rompe el último swing low
    en una estructura alcista.

    Returns
    -------
    MarketBias si se detecta un BOS, None si no hay cambio.
    """
    if len(swing_points) < 4:
        return None

    s_highs = [s for s in swing_points if s.is_high]
    s_lows = [s for s in swing_points if not s.is_high]

    if len(s_highs) < 2 or len(s_lows) < 2:
        return None

    last_high = s_highs[-1]
    last_low = s_lows[-1]

    # BOS alcista: precio rompe el último swing high
    # en un contexto de estructura bajista previa
    if current_price > last_high.price:
        prev_structure = determine_structure(swing_points[:-2])
        if prev_structure == MarketBias.BEARISH:
            return MarketBias.REVERSAL_UP

    # BOS bajista: precio rompe el último swing low
    if current_price < last_low.price:
        prev_structure = determine_structure(swing_points[:-2])
        if prev_structure == MarketBias.BULLISH:
            return MarketBias.REVERSAL_DOWN

    return None


def analyze_4h_trend(df_4h: pd.DataFrame, lookback: int = 6) -> MarketBias:
    """
    Analiza la tendencia en el timeframe de 4H.
    Según el manual: "ver la dirección / estructura a la cual está apuntando
    el mercado desde la última secuencia de velas de 4h".

    Parameters
    ----------
    df_4h : DataFrame con datos de 4H.
    lookback : Número de velas a analizar (default 6 como en el manual).

    Returns
    -------
    MarketBias
    """
    if len(df_4h) < lookback:
        return MarketBias.NEUTRAL

    recent = df_4h.iloc[-lookback:]
    closes = recent["Close"].values
    highs = recent["High"].values
    lows = recent["Low"].values

    # Contar velas alcistas vs bajistas
    bullish_candles = sum(1 for i in range(len(closes)) if closes[i] > recent["Open"].values[i])
    bearish_candles = lookback - bullish_candles

    # Verificar tendencia por higher highs/lows
    hh_count = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i - 1])
    hl_count = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i - 1])
    lh_count = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i - 1])
    ll_count = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i - 1])

    # Score de tendencia
    bull_score = hh_count + hl_count + bullish_candles
    bear_score = lh_count + ll_count + bearish_candles

    threshold = lookback * 0.6  # 60% de las señales en una dirección

    if bull_score >= threshold * 1.5 and bull_score > bear_score * 1.3:
        return MarketBias.BULLISH
    elif bear_score >= threshold * 1.5 and bear_score > bull_score * 1.3:
        return MarketBias.BEARISH
    else:
        return MarketBias.NEUTRAL


def is_move_exhausted(
    df: pd.DataFrame,
    direction: str,  # "up" or "down"
    lookback: int = 12,
    exhaustion_candles: int = 3,
) -> bool:
    """
    Determina si un movimiento se está "agotando" (desgastando).
    Según el manual: "Si ya la tendencia se está desgastando o lleva mucho rato,
    entonces no se entra, a menos que sea para buscar un reversal."

    Criterios de agotamiento:
    1. Las últimas N velas muestran rango decreciente (momentum fading)
    2. El precio no está haciendo nuevos extremos
    3. Velas contrarias aparecen

    Returns True si el movimiento parece agotado.
    """
    if len(df) < lookback:
        return False

    recent = df.iloc[-lookback:]
    closes = recent["Close"].values
    opens = recent["Open"].values
    ranges = (recent["High"] - recent["Low"]).values

    # Rango decreciente en las últimas velas
    recent_ranges = ranges[-exhaustion_candles:]
    earlier_ranges = ranges[:exhaustion_candles]
    range_decreasing = np.mean(recent_ranges) < np.mean(earlier_ranges) * 0.7

    if direction == "up":
        # Contar velas bajistas recientes
        bearish_recent = sum(1 for i in range(-exhaustion_candles, 0)
                             if closes[i] < opens[i])
        # ¿No más higher highs?
        highs = recent["High"].values
        no_new_highs = highs[-1] < max(highs[-exhaustion_candles - 2:-1])
        is_exhausted = (bearish_recent >= 2) or (range_decreasing and no_new_highs)
    else:
        bullish_recent = sum(1 for i in range(-exhaustion_candles, 0)
                             if closes[i] > opens[i])
        lows = recent["Low"].values
        no_new_lows = lows[-1] > min(lows[-exhaustion_candles - 2:-1])
        is_exhausted = (bullish_recent >= 2) or (range_decreasing and no_new_lows)

    return is_exhausted


def classify_discount_premium(
    entry_price: float,
    swing_start: float,
    swing_end: float,
    discount_pct: float = 0.40,
) -> str:
    """
    Clasifica si una entrada es "On Discount" o "Premium".

    El manual dice: entrar en el 40% inicial de un nuevo movimiento = Discount.
    Entrar en el 60%+ = Premium → NO ENTRAR (salvo excepciones con buen R:R).

    Parameters
    ----------
    entry_price : Precio de entrada propuesto.
    swing_start : Precio donde comenzó el movimiento.
    swing_end : Precio del extremo actual del movimiento.
    discount_pct : Porcentaje del movimiento considerado "discount".

    Returns
    -------
    str: "discount", "premium", or "extreme_premium"
    """
    total_move = abs(swing_end - swing_start)
    if total_move == 0:
        return "discount"

    # Calcular qué porcentaje del movimiento se ha cubierto al entry_price
    if swing_end > swing_start:
        # Movimiento alcista
        progress = (entry_price - swing_start) / total_move
    else:
        # Movimiento bajista
        progress = (swing_start - entry_price) / total_move

    progress = max(0.0, min(1.0, progress))

    if progress <= discount_pct:
        return "discount"
    elif progress <= 0.75:
        return "premium"
    else:
        return "extreme_premium"


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calcula el Average True Range (ATR)."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=1).mean()

    return atr
