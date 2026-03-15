"""
Bridge between the existing backtesting engine and the Streamlit dashboard.

Provides cached data loading, backtest execution, multi-TF FVG analysis,
and result formatting for consumption by dashboard pages.
Integrates with MongoDB for persistent storage.
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd

# Ensure project root is importable
ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config.settings import (
    ACCOUNT_BALANCE, TRAILING_DRAWDOWN_MAX,
    TRAINING_START, TRAINING_END,
    VALIDATION_START, VALIDATION_END,
    OOS_TEST_START, OOS_TEST_END,
    SYMBOL, ASSET_NAME, POINT_VALUE, TICK_VALUE,
    DEFAULT_CONTRACTS, MAX_DAILY_LOSS, MAX_TRADES_PER_DAY,
    MAX_BACKTEST_DAYS, MULTI_TF_FVG_TIMEFRAMES, FVG_MULTI_TF_CONFIGS,
)
from data.downloader import download_data, download_multi_timeframe, resample_ohlcv
from backtest import run_backtest
from validation.metrics import compute_metrics, PerformanceMetrics
from validation.monte_carlo import run_monte_carlo, MonteCarloResult
from validation.walk_forward import run_walk_forward, WFAResult
from reporting.consistency import check_consistency, ConsistencyResult
from strategy.ict_strategy import ICTStrategy, MNQCommInfo
from indicators.multi_tf_fvg import MultiTFAnalyzer
from data.database import (
    save_backtest as db_save_backtest,
    list_backtests as db_list_backtests,
    load_backtest as db_load_backtest,
    save_bot_config as db_save_config,
    get_db_status,
)


# ── Configuration Profiles ──────────────────────────────────────
CONFIGS_DIR = os.path.join(ROOT_DIR, "dashboard", "configs")
os.makedirs(CONFIGS_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "name": "Default ICT",
    "initial_capital": ACCOUNT_BALANCE,
    "max_daily_loss": MAX_DAILY_LOSS,
    "max_trades_per_day": MAX_TRADES_PER_DAY,
    "default_contracts": DEFAULT_CONTRACTS,
    # Per-timeframe FVG lookback (bars to scan in each TF)
    "fvg_lookback_1h": 10,
    "fvg_lookback_15m": 16,
    "fvg_lookback_5m": 24,
    "fvg_lookback_1m": 30,
    # Per-timeframe max active FVGs
    "fvg_max_1h": 4,
    "fvg_max_15m": 4,
    "fvg_max_5m": 3,
    "fvg_max_1m": 3,
    "fvg_search_range": 400,
    "structure_lookback": 6,
    "break_even_pct": 0.60,
    "close_at_pct": 0.90,
    "big_loss_threshold": 400.0,
    "big_win_threshold": 800.0,
}

PRESET_CONFIGS = {
    "Conservador": {
        **DEFAULT_CONFIG,
        "name": "Conservador",
        "default_contracts": 2,
        "max_daily_loss": 400.0,
        "max_trades_per_day": 1,
        "big_loss_threshold": 300.0,
    },
    "Moderado": {
        **DEFAULT_CONFIG,
        "name": "Moderado",
    },
    "Agresivo": {
        **DEFAULT_CONFIG,
        "name": "Agresivo",
        "default_contracts": 4,
        "max_daily_loss": 700.0,
        "max_trades_per_day": 3,
        "big_loss_threshold": 500.0,
        "big_win_threshold": 1000.0,
    },
}


def save_config(config: dict, name: str = None) -> str:
    """Save a configuration profile to disk."""
    name = name or config.get("name", "custom")
    fname = name.replace(" ", "_").lower() + ".json"
    path = os.path.join(CONFIGS_DIR, fname)
    config["name"] = name
    config["saved_at"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
    return path


def list_configs() -> List[dict]:
    """List all saved configuration profiles."""
    configs = []
    for f in Path(CONFIGS_DIR).glob("*.json"):
        try:
            with open(f) as fp:
                configs.append(json.load(fp))
        except Exception:
            pass
    return configs


def load_config(name: str) -> dict:
    """Load a configuration by name. Returns DEFAULT_CONFIG if not found."""
    fname = name.replace(" ", "_").lower() + ".json"
    path = os.path.join(CONFIGS_DIR, fname)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    import logging
    logging.getLogger(__name__).warning(
        "Config '%s' not found at %s — using DEFAULT_CONFIG.", name, path
    )
    return DEFAULT_CONFIG.copy()


# ── Data Loading ────────────────────────────────────────────────
def load_data(
    interval: str = "1h",
    start: str = None,
    end: str = None,
) -> pd.DataFrame:
    """Download or load cached data for a single timeframe."""
    start = start or TRAINING_START
    end = end or OOS_TEST_END
    df = download_data(interval=interval, start=start, end=end)
    return df


def load_multi_tf_data(
    start: str = None,
    end: str = None,
) -> Dict[str, pd.DataFrame]:
    """
    Load data for all analysis timeframes: 1H, 15M, 5M, 1M.
    Used for multi-TF FVG analysis and visual backtesting.

    Enforces MAX_BACKTEST_DAYS limit.
    """
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if start is None:
        start = (datetime.now() - timedelta(days=MAX_BACKTEST_DAYS)).strftime("%Y-%m-%d")

    # Enforce 30-day limit
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    if (end_dt - start_dt).days > MAX_BACKTEST_DAYS:
        start_dt = end_dt - timedelta(days=MAX_BACKTEST_DAYS)
        start = start_dt.strftime("%Y-%m-%d")

    data = {}
    for tf in MULTI_TF_FVG_TIMEFRAMES:
        try:
            df = download_data(interval=tf, start=start, end=end)
            if not df.empty:
                data[tf] = df
        except Exception as e:
            print(f"[ENGINE] Warning: Could not load {tf} data: {e}")

    return data


def run_multi_tf_fvg_analysis(
    data_dict: Dict[str, pd.DataFrame],
    current_price: float = None,
    fvg_configs: dict = None,
) -> MultiTFAnalyzer:
    """
    Run multi-timeframe FVG analysis on loaded data.

    Returns the analyzer with all detected FVGs.
    """
    analyzer = MultiTFAnalyzer(fvg_configs=fvg_configs)

    # If no current price, use latest close from highest available TF
    if current_price is None:
        for tf in MULTI_TF_FVG_TIMEFRAMES:
            if tf in data_dict and not data_dict[tf].empty:
                current_price = float(data_dict[tf]["Close"].iloc[-1])
                break

    analyzer.analyze_all_timeframes(data_dict, current_price)
    return analyzer


# ── Backtest Execution ──────────────────────────────────────────
def execute_backtest(
    df: pd.DataFrame,
    config: dict = None,
    period_name: str = "Dashboard Backtest",
    multi_tf_data: Dict[str, pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Execute a backtest with optional custom config.

    Returns dict with: metrics, trades_df, final_value, equity_curve,
                       fvgs (multi-TF FVG data for visualization)
    """
    config = config or DEFAULT_CONFIG

    # Map config to strategy params
    strategy_params = {
        "initial_capital": config.get("initial_capital", ACCOUNT_BALANCE),
        "max_daily_loss": config.get("max_daily_loss", MAX_DAILY_LOSS),
        "max_trades_per_day": config.get("max_trades_per_day", MAX_TRADES_PER_DAY),
        "default_contracts": config.get("default_contracts", DEFAULT_CONTRACTS),
        "fvg_max_1h": config.get("fvg_max_1h", 4),
        "fvg_search_range": config.get("fvg_search_range", 400),
        "structure_lookback": config.get("structure_lookback", 6),
        "break_even_pct": config.get("break_even_pct", 0.60),
        "close_at_pct": config.get("close_at_pct", 0.90),
        "big_loss_threshold": config.get("big_loss_threshold", 400.0),
        "big_win_threshold": config.get("big_win_threshold", 800.0),
        "verbose": False,
    }

    result = run_backtest(
        df=df,
        period_name=period_name,
        initial_capital=config.get("initial_capital", ACCOUNT_BALANCE),
        verbose=False,
        strategy_params=strategy_params,
    )

    # Build equity curve from trades
    trades_df = result["trades_df"]
    equity_curve = build_equity_curve(
        trades_df,
        config.get("initial_capital", ACCOUNT_BALANCE),
    )

    # Run multi-TF FVG analysis if data is available
    fvgs_data = []
    fvg_summary = {}
    if multi_tf_data:
        try:
            current_price = float(df["Close"].iloc[-1]) if not df.empty else None
            # Build per-TF FVG config from user's slider values
            fvg_configs_override = {
                "1h":  {**FVG_MULTI_TF_CONFIGS.get("1h",  {}), "max_fvgs": config.get("fvg_max_1h",  4), "lookback_bars": config.get("fvg_lookback_1h",  10)},
                "15m": {**FVG_MULTI_TF_CONFIGS.get("15m", {}), "max_fvgs": config.get("fvg_max_15m", 4), "lookback_bars": config.get("fvg_lookback_15m", 16)},
                "5m":  {**FVG_MULTI_TF_CONFIGS.get("5m",  {}), "max_fvgs": config.get("fvg_max_5m",  3), "lookback_bars": config.get("fvg_lookback_5m",  24)},
                "1m":  {**FVG_MULTI_TF_CONFIGS.get("1m",  {}), "max_fvgs": config.get("fvg_max_1m",  3), "lookback_bars": config.get("fvg_lookback_1m",  30)},
            }
            analyzer = run_multi_tf_fvg_analysis(multi_tf_data, current_price, fvg_configs=fvg_configs_override)
            fvgs_data = analyzer.get_all_fvgs_for_display()
            fvg_summary = analyzer.get_summary()
        except Exception as e:
            print(f"[ENGINE] Warning: Multi-TF FVG analysis failed: {e}")

    # Convert metrics to dict for MongoDB storage
    metrics = result["metrics"]
    metrics_dict = {}
    if hasattr(metrics, "__dict__"):
        metrics_dict = {k: v for k, v in metrics.__dict__.items()
                       if not k.startswith("_")}

    # Save to MongoDB
    backtest_id = db_save_backtest(
        config=config,
        metrics=metrics_dict,
        trades_df=trades_df,
        equity_df=equity_curve,
        fvgs_data=fvgs_data,
        period_name=period_name,
    )

    return {
        "metrics": metrics,
        "trades_df": trades_df,
        "final_value": result["final_value"],
        "equity_curve": equity_curve,
        "config": config,
        "fvgs": fvgs_data,
        "fvg_summary": fvg_summary,
        "backtest_id": backtest_id,
    }


def build_equity_curve(
    trades_df: pd.DataFrame,
    initial_capital: float = ACCOUNT_BALANCE,
) -> pd.DataFrame:
    """Build equity curve DataFrame from trades."""
    if trades_df.empty:
        return pd.DataFrame({"datetime": [], "equity": [], "drawdown": []})

    df = trades_df.copy()
    if "exit_time" in df.columns:
        df["datetime"] = pd.to_datetime(df["exit_time"])
    elif "timestamp" in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"])
    else:
        df["datetime"] = range(len(df))

    df = df.sort_values("datetime").reset_index(drop=True)

    pnl_col = "pnl_net" if "pnl_net" in df.columns else "pnl"
    cumulative = df[pnl_col].cumsum() + initial_capital
    equity = pd.DataFrame({
        "datetime": df["datetime"],
        "equity": cumulative,
        "pnl": df[pnl_col],
    })

    # Add drawdown
    peak = equity["equity"].cummax()
    equity["drawdown"] = equity["equity"] - peak
    equity["drawdown_pct"] = equity["drawdown"] / peak * 100

    return equity


# ── Validation Helpers ──────────────────────────────────────────
def run_monte_carlo_analysis(
    trades_df: pd.DataFrame,
) -> Optional[MonteCarloResult]:
    """Run Monte Carlo on trade P&Ls."""
    if trades_df.empty:
        return None
    pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
    trade_pnls = trades_df[pnl_col].values
    if len(trade_pnls) < 3:
        return None
    return run_monte_carlo(trade_pnls)


def run_consistency_check(
    trades_df: pd.DataFrame,
) -> Optional[ConsistencyResult]:
    """Run consistency check on trades."""
    if trades_df.empty:
        return None
    pnl_col = "pnl_net" if "pnl_net" in trades_df.columns else "pnl"
    df = trades_df.copy()
    if "exit_time" in df.columns:
        df["date"] = pd.to_datetime(df["exit_time"]).dt.date
    elif "timestamp" in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    else:
        return None
    daily_pnl = df.groupby("date")[pnl_col].sum()
    return check_consistency(daily_pnl)


def compute_daily_pnl(
    trades_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute daily P&L summary."""
    if trades_df.empty:
        return pd.DataFrame(columns=["date", "pnl", "trades", "wins"])

    df = trades_df.copy()
    pnl_col = "pnl_net" if "pnl_net" in df.columns else "pnl"

    if "exit_time" in df.columns:
        df["date"] = pd.to_datetime(df["exit_time"]).dt.date
    elif "timestamp" in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    else:
        df["date"] = range(len(df))

    daily = df.groupby("date").agg(
        pnl=(pnl_col, "sum"),
        trades=(pnl_col, "count"),
        wins=(pnl_col, lambda x: (x > 0).sum()),
    ).reset_index()

    return daily


def compute_hourly_performance(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Compute performance by hour of day."""
    if trades_df.empty:
        return pd.DataFrame()

    df = trades_df.copy()
    pnl_col = "pnl_net" if "pnl_net" in df.columns else "pnl"
    if "entry_time" in df.columns:
        df["hour"] = pd.to_datetime(df["entry_time"]).dt.hour
    elif "timestamp" in df.columns:
        df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    else:
        return pd.DataFrame()

    hourly = df.groupby("hour").agg(
        total_pnl=(pnl_col, "sum"),
        count=(pnl_col, "count"),
        win_rate=(pnl_col, lambda x: (x > 0).mean() * 100),
    ).reset_index()

    return hourly
