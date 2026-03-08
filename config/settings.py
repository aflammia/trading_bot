"""
Configuración global del bot de trading ICT.
Todos los parámetros de la cuenta, activo, riesgo y sesiones.
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple


# =============================================================================
# ACTIVO Y CUENTA
# =============================================================================
SYMBOL = "NQ=F"               # Proxy de MNQ en yfinance (mismos precios)
ASSET_NAME = "MNQ"
TICK_VALUE = 0.50              # USD por tick
TICKS_PER_POINT = 4
POINT_VALUE = TICK_VALUE * TICKS_PER_POINT  # $2.00 por punto

ACCOUNT_BALANCE = 50_000.0
TRAILING_DRAWDOWN_MAX = 2_500.0
DRAWDOWN_FLOOR = 50_000.0     # El piso del trailing DD no sube hasta 52,501

# Contratos
DEFAULT_CONTRACTS = 3
MIN_CONTRACTS = 2
MAX_CONTRACTS = 4
ABSOLUTE_MAX_CONTRACTS = 6    # Límite duro de OneUpTrader para 50k

# Comisiones y slippage (por contrato, por lado)
COMMISSION_PER_SIDE = 0.62    # USD por contrato por lado (Rithmic/OneUpTrader)
SLIPPAGE_TICKS = 1            # Ticks de slippage estimado por ejecución
SLIPPAGE_USD = SLIPPAGE_TICKS * TICK_VALUE  # $0.50

# Costo total por round-trip por contrato
ROUND_TRIP_COST = (COMMISSION_PER_SIDE * 2) + (SLIPPAGE_USD * 2)  # ~$2.24


# =============================================================================
# GESTIÓN DE RIESGO
# =============================================================================
MAX_DAILY_LOSS = 550.0         # USD — kill switch diario
MAX_LOSS_PER_TRADE = 600.0     # USD — stop loss máximo por trade
MIN_GAIN_PER_TRADE = 200.0     # USD — TP mínimo para que un trade valga la pena
MAX_TRADES_PER_DAY = 2

# Thresholds de comportamiento post-trade
BIG_LOSS_THRESHOLD = 400.0     # Si pierdes esto en 1 trade → no más trades hoy
BIG_WIN_THRESHOLD = 800.0      # Si ganas esto en 1 trade → no más trades hoy

# Kelly criterion
KELLY_FRACTION_MIN = 0.25
KELLY_FRACTION_MAX = 0.50
KELLY_FRACTION_DEFAULT = 0.35  # Fracción conservadora del Kelly

# Kill switches
KILL_SWITCH_DAILY_DRAWDOWN_PCT = 0.03   # 3% del balance
KILL_SWITCH_REDUCE_CONTRACTS_DD = 2000  # Reducir contratos si DD > $2,000
KILL_SWITCH_STOP_ALL_DD = 2400          # Parar todo si DD > $2,400

# Trailing drawdown del examen (primeros $2,500 de buffer)
EXAM_THRESHOLD_PROFIT = 2_500.0         # Después de +$2,500, el piso sube

# =============================================================================
# R:R y GESTIÓN DE POSICIÓN
# =============================================================================
MIN_RISK_REWARD_RATIO = 1.0    # Mínimo 1:1
BREAK_EVEN_TRIGGER_PCT = 0.50  # Activar BE cuando profit >= 50% de TP
CLOSE_AT_PCT_OF_TP = 0.90      # Cerrar si se alcanza 90% del TP
SL_BUFFER_TICKS = 4            # Ticks de buffer sobre/bajo el FVG protector

# Reducción de contratos tras malas rachas
BAD_STREAK_DAYS = 3            # Si pierdes X días seguidos
BAD_STREAK_LOSS_PER_DAY = 300  # Con pérdidas de al menos esto → reducir
RECOVERY_CONTRACTS = 2          # Operar con 2 contratos mientras recuperas


# =============================================================================
# HORARIOS DE TRADING (VET = UTC-4, todo el año)
# =============================================================================
TIMEZONE_VET = "America/Caracas"      # UTC-4
TIMEZONE_ET = "US/Eastern"            # UTC-5 / UTC-4

# Horario de operación del bot (VET)
TRADING_START_VET = "08:30"
TRADING_END_VET = "16:00"

# En UTC para cálculos internos
TRADING_START_UTC = "12:30"
TRADING_END_UTC = "20:00"

# Pre-market analysis (VET)
PREMARKET_START_VET = "08:00"

# =============================================================================
# ICT KILLZONES (Hora Eastern Time — como están en TradingView)
# =============================================================================
@dataclass
class KillZone:
    """Definición de una sesión/killzone ICT."""
    name: str
    start_et: str   # HH:MM en ET
    end_et: str     # HH:MM en ET

KILLZONES = {
    "asia":     KillZone("Asia",       "20:00", "00:00"),
    "london":   KillZone("London",     "02:00", "05:00"),
    "ny_am":    KillZone("NY AM",      "09:30", "11:00"),
    "ny_lunch": KillZone("NY Lunch",   "12:00", "13:00"),
    "ny_pm":    KillZone("NY PM",      "13:30", "16:00"),
}


# =============================================================================
# INDICADORES — PARÁMETROS DE DETECCIÓN
# =============================================================================
@dataclass
class FVGConfig:
    """Configuración de detección de FVGs por timeframe."""
    timeframe: str
    max_fvgs: int           # Máximo de FVGs a rastrear activos
    search_range_points: int  # Rango de búsqueda en puntos desde precio actual
    min_size_percentile: float  # Percentil mínimo de tamaño para considerar "significativo"

FVG_CONFIGS: Dict[str, FVGConfig] = {
    "1h":  FVGConfig("1h",  max_fvgs=4, search_range_points=400, min_size_percentile=0.40),
    "15m": FVGConfig("15m", max_fvgs=4, search_range_points=300, min_size_percentile=0.30),
    "5m":  FVGConfig("5m",  max_fvgs=3, search_range_points=200, min_size_percentile=0.20),
    "1m":  FVGConfig("1m",  max_fvgs=3, search_range_points=100, min_size_percentile=0.15),
}

# Estructura de mercado
SWING_POINT_ORDER = 5         # Velas a cada lado para confirmar swing high/low
STRUCTURE_LOOKBACK_4H = 6     # Velas de 4H para determinar tendencia
STRUCTURE_MIN_CANDLES_TREND = 4  # Mínimo de velas en la misma dirección

# FVG break thresholds
FVG_DUBIOUS_BREAK_PCT = 0.30  # Penetración < 30% = ruptura dudosa
FVG_DUBIOUS_WAIT_BARS = 2     # Velas a esperar tras ruptura dudosa

# On Discount vs Premium
DISCOUNT_ZONE_PCT = 0.40      # Primer 40% de un movimiento = Discount
PREMIUM_ZONE_PCT = 0.60       # Último 60% = Premium (no entrar)

# Liquidez
EQUAL_LEVELS_TOLERANCE_PCT = 0.001  # 0.1% de tolerancia para equal H/L
EQUAL_LEVELS_MIN_TOUCHES = 2
LIQUIDITY_SWEEP_MIN_TICKS = 2       # Mínimo de ticks que debe superar el nivel


# =============================================================================
# DATOS Y BACKTESTING
# =============================================================================
DATA_CACHE_DIR = "data/cache"

# Períodos de datos
TRAINING_START = "2025-08-01"
TRAINING_END = "2025-11-30"
VALIDATION_START = "2025-12-01"
VALIDATION_END = "2025-12-31"
OOS_TEST_START = "2026-01-01"
OOS_TEST_END = "2026-02-28"

# Walk-forward
WFA_TRAIN_WEEKS = 4
WFA_TEST_WEEKS = 1
WFA_STEP_WEEKS = 1
WFA_MAX_DEGRADATION = 0.40    # 40% de degradación máxima permitida

# Monte Carlo
MONTE_CARLO_ITERATIONS = 1_000

# ATR para cálculos de volatilidad
ATR_PERIOD = 14


# =============================================================================
# FUNDED ACCOUNT (post-examen)
# =============================================================================
FUNDED_THRESHOLD = 2_500.0
FUNDED_MIN_WITHDRAWAL = 1_000.0
FUNDED_FIRST_10K_SPLIT = 1.0    # 100% para el trader
FUNDED_AFTER_10K_SPLIT = 0.90   # 90% para el trader
MIN_TRADE_DURATION_SEC = 10     # Mínimo 10 segundos por trade (regla funded)


# =============================================================================
# REPORTING
# =============================================================================
REPORT_OUTPUT_DIR = "reports"

# Regla de consistencia OneUpTrader
# Interpretación: sum(top_3_days_pnl) <= 0.80 * total_pnl
CONSISTENCY_TOP_N_DAYS = 3
CONSISTENCY_MAX_PCT = 0.80


# =============================================================================
# MONGODB ATLAS
# =============================================================================
# NEVER hardcode credentials here — use one of these methods:
#   1. Streamlit Cloud: paste secrets in Advanced Settings > Secrets
#   2. Local dev: create .streamlit/secrets.toml (excluded by .gitignore)
#   3. Environment variable: set MONGODB_URI in your shell
import os as _os

MONGODB_DB_NAME = "chuky_bot"

try:
    import streamlit as _st
    MONGODB_URI = _st.secrets["mongodb"]["uri"]
    MONGODB_DB_NAME = _st.secrets["mongodb"].get("db_name", MONGODB_DB_NAME)
except Exception:
    MONGODB_URI = _os.environ.get("MONGODB_URI", "")
    if not MONGODB_URI:
        print("[SETTINGS] WARNING: No MongoDB URI found. Set MONGODB_URI env var or configure .streamlit/secrets.toml")


# =============================================================================
# MULTI-TIMEFRAME FVG ANALYSIS
# =============================================================================
# Timeframes for hierarchical FVG analysis (ordered by weight, descending).
# FVGs are only searched in timeframes < 4H (1H, 15M, 5M, 1M).
# Higher timeframes carry more weight for confluence scoring.
MULTI_TF_FVG_TIMEFRAMES = ["1h", "15m", "5m", "1m"]

# Weight assigned to each timeframe for FVG scoring (higher = more important)
MULTI_TF_FVG_WEIGHTS = {
    "1h": 4.0,
    "15m": 3.0,
    "5m": 2.0,
    "1m": 1.0,
}

# FVG detection configs per timeframe for multi-TF analysis
FVG_MULTI_TF_CONFIGS = {
    "1h":  {"max_fvgs": 4, "search_range_points": 400, "min_size_percentile": 0.40},
    "15m": {"max_fvgs": 4, "search_range_points": 300, "min_size_percentile": 0.30},
    "5m":  {"max_fvgs": 3, "search_range_points": 200, "min_size_percentile": 0.20},
    "1m":  {"max_fvgs": 3, "search_range_points": 100, "min_size_percentile": 0.15},
}

# Entry is only allowed on these timeframes (15M and below)
ENTRY_TIMEFRAMES = ["15m", "5m", "1m"]

# Maximum backtest period (days)
MAX_BACKTEST_DAYS = 30


# =============================================================================
# TRADING HOURS — STRICT NYSE + VET CLOSE
# =============================================================================
# Bot opens: 9:30 AM ET (NYSE open)
# Bot force-closes: 4:00 PM VET (UTC-4) — always, no DST adjustment for VET
MARKET_OPEN_ET = "09:30"       # Eastern Time (adjusts for DST)
FORCE_CLOSE_VET = "16:00"      # Venezuela Time (UTC-4, no DST)
FORCE_CLOSE_UTC = "20:00"      # 4:00 PM VET = 8:00 PM UTC (fixed)
