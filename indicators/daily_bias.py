"""
Determinación del Daily Bias (sesgo diario) multi-timeframe.

Sigue el protocolo del manual ICT:
1. Revisar ForexFactory (maletines rojos) — diferido a Fase 2
2. Marcar ATH/ATL en 1D
3. Marcar PDH/PDL en 1D
4. Tendencia 4H (últimas 6-8 velas)
5. FVGs en 1H (máx 4, rango 400pts)
6. FVGs en 15m (máx 4, rango 300pts)
7. Niveles de liquidez en 15m
8. FVGs en 5m (máx 3, rango 200pts)
→ Generar hipótesis: LONG, SHORT, NO_TRADE
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from indicators.fvg import (
    FVGType, FVGTracker, FairValueGap,
    detect_fvgs, filter_significant_fvgs,
)
from indicators.liquidity import (
    LiquidityTracker, LiquidityLevel, LiquidityType,
    compute_pdh_pdl, find_equal_levels, find_swing_levels,
)
from indicators.market_structure import (
    MarketBias, analyze_4h_trend, detect_swing_points,
    determine_structure, is_move_exhausted,
)


@dataclass
class DailyBiasResult:
    """Resultado del análisis de sesgo diario."""
    bias: MarketBias            # BULLISH, BEARISH, NEUTRAL
    confidence: float           # 0.0 - 1.0
    trend_4h: MarketBias        # Tendencia del timeframe de 4H
    fvg_signal: str             # "bullish_fvgs_breaking", "bearish_fvgs_breaking", "mixed"
    liquidity_imbalance: str    # "more_above", "more_below", "balanced"
    is_exhausted: bool          # ¿El movimiento actual está agotado?
    entry_direction: str        # "long", "short", "no_trade"
    reasoning: List[str]        # Explicación paso a paso

    # Niveles clave identificados
    pdh: Optional[float] = None
    pdl: Optional[float] = None
    nearest_buyside: Optional[float] = None
    nearest_sellside: Optional[float] = None


class DailyBiasEngine:
    """
    Motor de determinación del sesgo diario.
    Integra análisis de múltiples timeframes para generar una hipótesis.
    """

    def __init__(self):
        self.fvg_trackers: Dict[str, FVGTracker] = {
            "1h": FVGTracker(),
            "15m": FVGTracker(),
            "5m": FVGTracker(),
        }
        self.liquidity_tracker = LiquidityTracker()
        self._last_bias: Optional[DailyBiasResult] = None

    def analyze(
        self,
        df_1d: pd.DataFrame,
        df_4h: pd.DataFrame,
        df_1h: pd.DataFrame,
        df_15m: Optional[pd.DataFrame] = None,
        df_5m: Optional[pd.DataFrame] = None,
        current_price: Optional[float] = None,
    ) -> DailyBiasResult:
        """
        Ejecuta el análisis completo de Daily Bias.

        Parameters
        ----------
        df_1d : Datos diarios
        df_4h : Datos de 4 horas
        df_1h : Datos de 1 hora
        df_15m : Datos de 15 minutos (opcional)
        df_5m : Datos de 5 minutos (opcional)
        current_price : Precio actual (si None, usa el último close de 1h)

        Returns
        -------
        DailyBiasResult con el sesgo y todos los detalles.
        """
        if current_price is None:
            current_price = df_1h["Close"].iloc[-1]

        reasoning = []
        score = 0  # Positivo = alcista, negativo = bajista

        # =====================================================================
        # PASO 1: ATH / ATL (1D)
        # =====================================================================
        ath = df_1d["High"].max()
        atl = df_1d["Low"].min()
        dist_to_ath = ath - current_price
        dist_to_atl = current_price - atl

        if dist_to_ath < dist_to_atl * 0.3:
            reasoning.append(f"Precio muy cercano al ATH ({ath:.0f}), cuidado con shorts")
        elif dist_to_atl < dist_to_ath * 0.3:
            reasoning.append(f"Precio muy cercano al ATL ({atl:.0f}), cuidado con longs")

        # =====================================================================
        # PASO 2: PDH / PDL (1D)
        # =====================================================================
        df_1h_pdh = compute_pdh_pdl(df_1h)
        pdh = df_1h_pdh["pdh"].iloc[-1] if "pdh" in df_1h_pdh.columns else None
        pdl = df_1h_pdh["pdl"].iloc[-1] if "pdl" in df_1h_pdh.columns else None

        if pdh is not None and pdl is not None:
            if current_price > pdh:
                reasoning.append(f"Precio por encima de PDH ({pdh:.0f}) — momentum alcista")
                score += 1
            elif current_price < pdl:
                reasoning.append(f"Precio por debajo de PDL ({pdl:.0f}) — momentum bajista")
                score -= 1
            else:
                reasoning.append(f"Precio entre PDH ({pdh:.0f}) y PDL ({pdl:.0f})")

        # =====================================================================
        # PASO 3: Tendencia 4H
        # =====================================================================
        trend_4h = analyze_4h_trend(df_4h)
        if trend_4h == MarketBias.BULLISH:
            score += 2
            reasoning.append("Tendencia 4H: ALCISTA (higher highs + higher lows)")
        elif trend_4h == MarketBias.BEARISH:
            score -= 2
            reasoning.append("Tendencia 4H: BAJISTA (lower highs + lower lows)")
        else:
            reasoning.append("Tendencia 4H: NEUTRAL (sin dirección clara)")

        # =====================================================================
        # PASO 4: FVGs 1H — ¿cuáles se están rompiendo?
        # =====================================================================
        fvgs_1h = detect_fvgs(df_1h, timeframe="1h")
        self.fvg_trackers["1h"].add_fvgs(fvgs_1h)

        # Simular estado de FVGs procesando las últimas velas
        for i in range(max(0, len(df_1h) - 20), len(df_1h)):
            self.fvg_trackers["1h"].update(
                df_1h["High"].iloc[i],
                df_1h["Low"].iloc[i],
                df_1h["Close"].iloc[i],
            )

        recent_broken_bullish = self.fvg_trackers["1h"].count_recently_broken(
            FVGType.BULLISH, max(0, len(df_1h) - 20), len(df_1h) - 1
        )
        recent_broken_bearish = self.fvg_trackers["1h"].count_recently_broken(
            FVGType.BEARISH, max(0, len(df_1h) - 20), len(df_1h) - 1
        )

        if recent_broken_bullish > recent_broken_bearish:
            fvg_signal = "bullish_fvgs_breaking"
            score -= 2  # Bullish FVGs rompiendo = señal bajista
            reasoning.append(
                f"FVGs 1H: {recent_broken_bullish} Bullish FVGs rotos vs "
                f"{recent_broken_bearish} Bearish — precio bajista en corto plazo"
            )
        elif recent_broken_bearish > recent_broken_bullish:
            fvg_signal = "bearish_fvgs_breaking"
            score += 2
            reasoning.append(
                f"FVGs 1H: {recent_broken_bearish} Bearish FVGs rotos vs "
                f"{recent_broken_bullish} Bullish — precio alcista en corto plazo"
            )
        else:
            fvg_signal = "mixed"
            reasoning.append("FVGs 1H: Rompimientos mixtos, sin señal clara")

        # =====================================================================
        # PASO 5: Análisis de liquidez
        # =====================================================================
        # PDH/PDL como niveles
        if pdh is not None:
            self.liquidity_tracker.add_levels([
                LiquidityLevel(LiquidityType.PDH, pdh,
                               df_1h.index[-1], f"PDH {pdh:.0f}"),
            ])
        if pdl is not None:
            self.liquidity_tracker.add_levels([
                LiquidityLevel(LiquidityType.PDL, pdl,
                               df_1h.index[-1], f"PDL {pdl:.0f}"),
            ])

        # Swing levels de 1H
        swing_highs, swing_lows = find_swing_levels(df_1h)
        self.liquidity_tracker.add_levels(swing_highs + swing_lows)

        # Equal levels
        eq_highs = find_equal_levels(df_1h, "High")
        eq_lows = find_equal_levels(df_1h, "Low")
        self.liquidity_tracker.add_levels(eq_highs + eq_lows)

        # Evaluar el balance de liquidez
        buyside = self.liquidity_tracker.get_nearest_buyside(current_price)
        sellside = self.liquidity_tracker.get_nearest_sellside(current_price)
        swept_above = self.liquidity_tracker.count_swept_above()
        swept_below = self.liquidity_tracker.count_swept_below()

        if swept_above > swept_below and len(sellside) > 0:
            liquidity_imbalance = "more_below"
            score -= 1
            reasoning.append(
                f"Liquidez: {swept_above} niveles tomados arriba, "
                f"{len(sellside)} activos abajo — el precio debería buscar abajo"
            )
        elif swept_below > swept_above and len(buyside) > 0:
            liquidity_imbalance = "more_above"
            score += 1
            reasoning.append(
                f"Liquidez: {swept_below} niveles tomados abajo, "
                f"{len(buyside)} activos arriba — el precio debería buscar arriba"
            )
        else:
            liquidity_imbalance = "balanced"
            reasoning.append("Liquidez: Relativamente balanceada en ambos lados")

        # =====================================================================
        # PASO 6: ¿Movimiento agotado?
        # =====================================================================
        if score > 0:
            exhausted = is_move_exhausted(df_1h, "up")
        elif score < 0:
            exhausted = is_move_exhausted(df_1h, "down")
        else:
            exhausted = False

        if exhausted:
            reasoning.append(
                "⚠ El movimiento actual parece AGOTADO — "
                "considerar reversal en vez de unirse a tendencia"
            )

        # =====================================================================
        # DECISIÓN FINAL
        # =====================================================================
        confidence = min(1.0, abs(score) / 6.0)

        if abs(score) < 2:
            bias = MarketBias.NEUTRAL
            entry_direction = "no_trade"
            reasoning.append("DECISIÓN: Score insuficiente → NO TRADE")
        elif score >= 2:
            if exhausted:
                bias = MarketBias.REVERSAL_DOWN
                entry_direction = "no_trade"
                reasoning.append(
                    "DECISIÓN: Sesgo alcista PERO agotado → NO TRADE (esperar reversal)"
                )
            else:
                bias = MarketBias.BULLISH
                entry_direction = "long"
                reasoning.append(f"DECISIÓN: LONG (score={score}, confianza={confidence:.0%})")
        else:
            if exhausted:
                bias = MarketBias.REVERSAL_UP
                entry_direction = "no_trade"
                reasoning.append(
                    "DECISIÓN: Sesgo bajista PERO agotado → NO TRADE (esperar reversal)"
                )
            else:
                bias = MarketBias.BEARISH
                entry_direction = "short"
                reasoning.append(f"DECISIÓN: SHORT (score={score}, confianza={confidence:.0%})")

        result = DailyBiasResult(
            bias=bias,
            confidence=confidence,
            trend_4h=trend_4h,
            fvg_signal=fvg_signal,
            liquidity_imbalance=liquidity_imbalance,
            is_exhausted=exhausted,
            entry_direction=entry_direction,
            reasoning=reasoning,
            pdh=pdh,
            pdl=pdl,
            nearest_buyside=buyside[0].price if buyside else None,
            nearest_sellside=sellside[0].price if sellside else None,
        )

        self._last_bias = result
        return result

    def get_last_bias(self) -> Optional[DailyBiasResult]:
        return self._last_bias
