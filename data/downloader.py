"""
Módulo de descarga y caché de datos históricos para MNQ/NQ.
Usa yfinance con NQ=F como proxy de MNQ (mismos niveles de precio).
"""
import os
import hashlib
import time
import random
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import (
    SYMBOL, DATA_CACHE_DIR, TIMEZONE_ET,
    TRAINING_START, OOS_TEST_END,
)


# Mapeo de intervalos yfinance → máxima antigüedad disponible
YFINANCE_LIMITS = {
    "1m":  7,      # días
    "2m":  60,
    "5m":  60,
    "15m": 60,
    "30m": 60,
    "1h":  730,
    "1d":  99999,  # sin límite práctico
}


def _cache_path(symbol: str, interval: str, start: str, end: str) -> str:
    """Genera una ruta de caché única basada en los parámetros de descarga."""
    os.makedirs(DATA_CACHE_DIR, exist_ok=True)
    key = f"{symbol}_{interval}_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return os.path.join(DATA_CACHE_DIR, f"{symbol}_{interval}_{h}.parquet")


def _latest_cache_for(symbol: str, interval: str) -> Optional[str]:
    """Retorna el archivo de caché más reciente para símbolo+intervalo."""
    if not os.path.isdir(DATA_CACHE_DIR):
        return None
    safe_symbol = symbol.replace("/", "_")
    prefix = f"{safe_symbol}_{interval}_"
    candidates = [
        os.path.join(DATA_CACHE_DIR, f)
        for f in os.listdir(DATA_CACHE_DIR)
        if f.startswith(prefix) and f.endswith(".parquet")
    ]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def _is_rate_limited_error(err: Exception) -> bool:
    text = str(err).lower()
    return (
        "too many requests" in text
        or "rate limited" in text
        or "429" in text
        or "retry-after" in text
    )


def download_data(
    symbol: str = SYMBOL,
    interval: str = "1h",
    start: Optional[str] = None,
    end: Optional[str] = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Descarga datos OHLCV de yfinance para el símbolo dado.

    Parameters
    ----------
    symbol : str
        Ticker de yfinance (default NQ=F).
    interval : str
        Intervalo de velas: 1m, 2m, 5m, 15m, 30m, 1h, 1d.
    start : str
        Fecha de inicio (YYYY-MM-DD). Si None, calcula según el límite del intervalo.
    end : str
        Fecha de fin (YYYY-MM-DD). Si None, usa hoy.
    use_cache : bool
        Si True, intenta cargar de caché antes de descargar.

    Returns
    -------
    pd.DataFrame
        DataFrame con columnas: Open, High, Low, Close, Volume.
        Índice: DatetimeIndex en timezone ET.
    """
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    if start is None:
        max_days = YFINANCE_LIMITS.get(interval, 730)
        start = (datetime.now() - timedelta(days=max_days - 5)).strftime("%Y-%m-%d")

    # Respetar límites de ventana de yfinance incluso cuando start viene explícito
    max_days = YFINANCE_LIMITS.get(interval)
    if max_days is not None and max_days < 99999:
        requested_start = datetime.strptime(start, "%Y-%m-%d")
        earliest_allowed = datetime.now() - timedelta(days=max_days)
        if requested_start < earliest_allowed:
            adjusted_start = earliest_allowed.strftime("%Y-%m-%d")
            print(
                f"[DATA] Ajustando start para {interval}: {start} → {adjusted_start} "
                f"(límite yfinance: {max_days} días)"
            )
            start = adjusted_start

    # Intentar caché
    cache_file = _cache_path(symbol, interval, start, end)
    if use_cache and os.path.exists(cache_file):
        print(f"[DATA] Cargando de caché: {cache_file}")
        df = pd.read_parquet(cache_file)
        if not df.empty:
            return df

    print(f"[DATA] Descargando {symbol} | {interval} | {start} → {end}")

    df = pd.DataFrame()
    last_error = None
    max_attempts = 4

    for attempt in range(1, max_attempts + 1):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(interval=interval, start=start, end=end)
            if not df.empty:
                break

            # Evitar martillar si Yahoo devolvió vacío temporal por limitación
            if attempt < max_attempts:
                wait_s = (2 ** (attempt - 1)) + random.uniform(0.1, 0.8)
                print(f"[DATA] Respuesta vacía (intento {attempt}/{max_attempts}). Reintentando en {wait_s:.1f}s...")
                time.sleep(wait_s)
        except Exception as e:
            last_error = e
            if attempt >= max_attempts:
                break
            wait_s = (2 ** (attempt - 1)) + random.uniform(0.1, 1.0)
            if _is_rate_limited_error(e):
                wait_s += 1.5
            print(
                f"[DATA] Error en descarga (intento {attempt}/{max_attempts}): {e}. "
                f"Reintentando en {wait_s:.1f}s..."
            )
            time.sleep(wait_s)

    if df.empty and last_error is not None:
        # Fallback a último caché disponible para no romper el backtest
        latest_cache = _latest_cache_for(symbol, interval)
        if use_cache and latest_cache and os.path.exists(latest_cache):
            try:
                cached_df = pd.read_parquet(latest_cache)
                if not cached_df.empty:
                    print(f"[DATA] Fallback a caché reciente por error de red/rate limit: {latest_cache}")
                    return cached_df
            except Exception:
                pass
        raise last_error

    if df.empty:
        print(f"[DATA] WARNING: No se obtuvieron datos para {symbol} {interval}")
        return pd.DataFrame()

    # Limpiar columnas (yfinance puede devolver 'Dividends', 'Stock Splits')
    keep_cols = ["Open", "High", "Low", "Close", "Volume"]
    df = df[[c for c in keep_cols if c in df.columns]].copy()

    # Asegurar timezone
    if df.index.tz is not None:
        df.index = df.index.tz_convert(TIMEZONE_ET)
    else:
        df.index = df.index.tz_localize("UTC").tz_convert(TIMEZONE_ET)

    # Eliminar filas con NaN en OHLC
    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)

    # Guardar caché
    try:
        df.to_parquet(cache_file)
        print(f"[DATA] Guardado en caché: {cache_file}")
    except Exception as e:
        print(f"[DATA] No se pudo guardar caché: {e}")

    print(f"[DATA] {len(df)} velas descargadas ({df.index[0]} → {df.index[-1]})")
    return df


def download_multi_timeframe(
    symbol: str = SYMBOL,
    start_1h: Optional[str] = None,
    end: Optional[str] = None,
    use_cache: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Descarga datos en múltiples timeframes.

    Returns
    -------
    dict
        Diccionario con claves '1d', '4h', '1h', '15m', '5m' → DataFrames.
        Solo incluye timeframes con datos disponibles.
    """
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if start_1h is None:
        start_1h = TRAINING_START

    result = {}

    # 1D — historial largo
    print("\n=== Descargando datos diarios ===")
    df_1d = download_data(symbol, "1d", start="2025-01-01", end=end, use_cache=use_cache)
    if not df_1d.empty:
        result["1d"] = df_1d

    # 1H — hasta 730 días
    print("\n=== Descargando datos 1H ===")
    df_1h = download_data(symbol, "1h", start=start_1h, end=end, use_cache=use_cache)
    if not df_1h.empty:
        result["1h"] = df_1h

        # Derivar 4H desde 1H mediante resample
        print("[DATA] Derivando datos 4H desde 1H...")
        df_4h = resample_ohlcv(df_1h, "4h")
        if not df_4h.empty:
            result["4h"] = df_4h

    # 15m — últimos 60 días
    print("\n=== Descargando datos 15m ===")
    df_15m = download_data(symbol, "15m", end=end, use_cache=use_cache)
    if not df_15m.empty:
        result["15m"] = df_15m

    # 5m — últimos 60 días
    print("\n=== Descargando datos 5m ===")
    df_5m = download_data(symbol, "5m", end=end, use_cache=use_cache)
    if not df_5m.empty:
        result["5m"] = df_5m

    print(f"\n[DATA] Timeframes disponibles: {list(result.keys())}")
    for tf, df in result.items():
        print(f"  {tf}: {len(df)} velas, {df.index[0].date()} → {df.index[-1].date()}")

    return result


def resample_ohlcv(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """
    Resample un DataFrame OHLCV a un timeframe mayor.

    Parameters
    ----------
    df : pd.DataFrame
        Datos originales con columnas Open, High, Low, Close, Volume.
    target_tf : str
        Timeframe destino: '4h', '1h', '1d', etc.

    Returns
    -------
    pd.DataFrame
        Datos resampleados.
    """
    tf_map = {
        "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "1h", "4h": "4h", "1d": "1D",
    }
    rule = tf_map.get(target_tf, target_tf)

    resampled = df.resample(rule).agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()

    return resampled


def filter_trading_hours(
    df: pd.DataFrame,
    start_utc: str = "12:30",
    end_utc: str = "20:00",
) -> pd.DataFrame:
    """
    Filtra datos para solo incluir el horario de trading del bot.
    Convierte a UTC para la comparación.
    """
    df_utc = df.copy()
    if df_utc.index.tz is not None:
        df_utc.index = df_utc.index.tz_convert("UTC")

    mask = (
        (df_utc.index.time >= pd.Timestamp(start_utc).time()) &
        (df_utc.index.time <= pd.Timestamp(end_utc).time()) &
        (df_utc.index.dayofweek < 5)  # Lun-Vie
    )
    return df.loc[mask]


if __name__ == "__main__":
    # Test de descarga
    data = download_multi_timeframe()
    for tf, df in data.items():
        print(f"\n{tf}: {df.shape}")
        print(df.head(3))
