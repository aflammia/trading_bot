"""
Métricas de rendimiento para evaluación del bot.

Incluye: Sharpe Ratio, Profit Factor, Max Drawdown,
Win Rate, R:R promedio, y métricas específicas del manual.
"""
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """Conjunto completo de métricas de rendimiento."""
    # Básicas
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # P&L
    total_pnl: float = 0.0
    total_pnl_gross: float = 0.0
    total_commission: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    # Ratios
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    avg_rr_ratio: float = 0.0
    expectancy: float = 0.0      # Expected $ per trade

    # Drawdown
    max_drawdown_usd: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    avg_drawdown_usd: float = 0.0

    # Account
    initial_balance: float = 50000.0
    final_balance: float = 50000.0
    total_return_pct: float = 0.0

    # Consistency (OneUpTrader)
    consistency_check_passed: bool = False
    top_3_days_sum: float = 0.0
    total_positive_pnl: float = 0.0

    # Time-based
    avg_trade_duration_hours: float = 0.0
    trades_per_day: float = 0.0
    best_day_pnl: float = 0.0
    worst_day_pnl: float = 0.0


def compute_metrics(
    trades_df: pd.DataFrame,
    initial_balance: float = 50000.0,
    risk_free_rate: float = 0.05,  # 5% anual
    trading_days_per_year: int = 252,
) -> PerformanceMetrics:
    """
    Calcula todas las métricas de rendimiento a partir del DataFrame de trades.

    Parameters
    ----------
    trades_df : pd.DataFrame
        Debe contener: timestamp, pnl_net, pnl_gross, commission, direction
    initial_balance : float
        Balance inicial de la cuenta.
    risk_free_rate : float
        Tasa libre de riesgo anual para Sharpe (0.05 = 5%).
    trading_days_per_year : int
        Días de trading por año para anualizaciones.

    Returns
    -------
    PerformanceMetrics
    """
    m = PerformanceMetrics()
    m.initial_balance = initial_balance

    if trades_df.empty:
        m.final_balance = initial_balance
        return m

    pnl_col = "pnl_net"
    if pnl_col not in trades_df.columns:
        pnl_col = "pnl_gross"

    pnl = trades_df[pnl_col].values

    # Básicas
    m.total_trades = len(pnl)
    m.winning_trades = int(np.sum(pnl > 0))
    m.losing_trades = int(np.sum(pnl <= 0))
    m.win_rate = m.winning_trades / m.total_trades if m.total_trades > 0 else 0.0

    # P&L
    m.total_pnl = float(np.sum(pnl))
    if "pnl_gross" in trades_df.columns:
        m.total_pnl_gross = float(trades_df["pnl_gross"].sum())
    if "commission" in trades_df.columns:
        m.total_commission = float(trades_df["commission"].sum())

    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]

    m.avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    m.avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    m.largest_win = float(np.max(wins)) if len(wins) > 0 else 0.0
    m.largest_loss = float(np.min(losses)) if len(losses) > 0 else 0.0

    # Profit Factor
    total_wins = float(np.sum(wins)) if len(wins) > 0 else 0.0
    total_losses = abs(float(np.sum(losses))) if len(losses) > 0 else 0.0
    m.profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

    # Expectancy (expected $ per trade)
    m.expectancy = m.total_pnl / m.total_trades if m.total_trades > 0 else 0.0

    # Average R:R
    if m.avg_loss != 0:
        m.avg_rr_ratio = abs(m.avg_win / m.avg_loss)
    else:
        m.avg_rr_ratio = float("inf") if m.avg_win > 0 else 0.0

    # Account
    m.final_balance = initial_balance + m.total_pnl
    m.total_return_pct = (m.total_pnl / initial_balance) * 100

    # =========================================================================
    # Drawdown (curve-based)
    # =========================================================================
    equity_curve = initial_balance + np.cumsum(pnl)
    peak = np.maximum.accumulate(equity_curve)
    drawdown = peak - equity_curve

    m.max_drawdown_usd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
    m.max_drawdown_pct = (m.max_drawdown_usd / initial_balance) * 100
    m.avg_drawdown_usd = float(np.mean(drawdown)) if len(drawdown) > 0 else 0.0

    # Drawdown duration
    if len(drawdown) > 0 and m.max_drawdown_usd > 0:
        in_dd = drawdown > 0
        dd_lengths = []
        current_len = 0
        for is_dd in in_dd:
            if is_dd:
                current_len += 1
            else:
                if current_len > 0:
                    dd_lengths.append(current_len)
                current_len = 0
        if current_len > 0:
            dd_lengths.append(current_len)
        m.max_drawdown_duration_days = max(dd_lengths) if dd_lengths else 0

    # =========================================================================
    # Sharpe Ratio (anualizado)
    # =========================================================================
    if "timestamp" in trades_df.columns:
        trades_df_copy = trades_df.copy()
        trades_df_copy["date"] = pd.to_datetime(trades_df_copy["timestamp"]).dt.date
        daily_pnl = trades_df_copy.groupby("date")[pnl_col].sum()
    else:
        # Sin timestamps, tratar cada trade como un día
        daily_pnl = pd.Series(pnl)

    if len(daily_pnl) > 1:
        daily_returns = daily_pnl / initial_balance
        excess_return = daily_returns.mean() - (risk_free_rate / trading_days_per_year)
        std_return = daily_returns.std()

        if std_return > 0:
            m.sharpe_ratio = float(excess_return / std_return * np.sqrt(trading_days_per_year))
        else:
            m.sharpe_ratio = 0.0

        # Sortino Ratio (solo downside deviation)
        downside = daily_returns[daily_returns < 0]
        if len(downside) > 0:
            downside_std = downside.std()
            if downside_std > 0:
                m.sortino_ratio = float(excess_return / downside_std * np.sqrt(trading_days_per_year))

        # Best/worst day
        m.best_day_pnl = float(daily_pnl.max())
        m.worst_day_pnl = float(daily_pnl.min())

        # Trades per day
        m.trades_per_day = m.total_trades / len(daily_pnl)
    else:
        m.sharpe_ratio = 0.0

    # =========================================================================
    # Consistency Rule (OneUpTrader)
    # sum(top_3_days) <= 80% * total_positive_pnl
    # =========================================================================
    if "timestamp" in trades_df.columns and len(daily_pnl) >= 3:
        positive_days = daily_pnl[daily_pnl > 0].sort_values(ascending=False)
        if len(positive_days) >= 3:
            m.top_3_days_sum = float(positive_days.iloc[:3].sum())
            m.total_positive_pnl = float(positive_days.sum())
            if m.total_positive_pnl > 0:
                m.consistency_check_passed = (
                    m.top_3_days_sum <= 0.80 * m.total_positive_pnl
                )
            else:
                m.consistency_check_passed = True
        else:
            m.consistency_check_passed = True  # No hay suficientes días

    return m


def format_metrics_report(m: PerformanceMetrics) -> str:
    """Genera un reporte formateado de las métricas."""
    lines = [
        "=" * 65,
        "        REPORTE DE RENDIMIENTO — ICT Trading Bot",
        "=" * 65,
        "",
        "── TRADES ──────────────────────────────────────────────",
        f"  Total Trades:       {m.total_trades}",
        f"  Wins / Losses:      {m.winning_trades} / {m.losing_trades}",
        f"  Win Rate:           {m.win_rate:.1%}",
        f"  Trades/Day (avg):   {m.trades_per_day:.1f}",
        "",
        "── P&L ─────────────────────────────────────────────────",
        f"  P&L Total (net):    ${m.total_pnl:+,.2f}",
        f"  P&L Bruto:          ${m.total_pnl_gross:+,.2f}",
        f"  Comisiones:         ${m.total_commission:,.2f}",
        f"  Avg Win:            ${m.avg_win:+,.2f}",
        f"  Avg Loss:           ${m.avg_loss:+,.2f}",
        f"  Largest Win:        ${m.largest_win:+,.2f}",
        f"  Largest Loss:       ${m.largest_loss:+,.2f}",
        f"  Expectancy/trade:   ${m.expectancy:+,.2f}",
        "",
        "── RATIOS ──────────────────────────────────────────────",
        f"  Profit Factor:      {m.profit_factor:.2f}",
        f"  Sharpe Ratio:       {m.sharpe_ratio:.2f}",
        f"  Sortino Ratio:      {m.sortino_ratio:.2f}",
        f"  Avg R:R:            {m.avg_rr_ratio:.2f}:1",
        "",
        "── DRAWDOWN ────────────────────────────────────────────",
        f"  Max Drawdown:       ${m.max_drawdown_usd:,.2f} ({m.max_drawdown_pct:.2f}%)",
        f"  Max DD Duration:    {m.max_drawdown_duration_days} trades",
        f"  Avg Drawdown:       ${m.avg_drawdown_usd:,.2f}",
        "",
        "── CUENTA ──────────────────────────────────────────────",
        f"  Balance Inicial:    ${m.initial_balance:,.2f}",
        f"  Balance Final:      ${m.final_balance:,.2f}",
        f"  Retorno Total:      {m.total_return_pct:+.2f}%",
        f"  Best Day:           ${m.best_day_pnl:+,.2f}",
        f"  Worst Day:          ${m.worst_day_pnl:+,.2f}",
        "",
        "── CONSISTENCIA (OneUpTrader) ─────────────────────────",
        f"  Top 3 Days Sum:     ${m.top_3_days_sum:,.2f}",
        f"  Total Positive PnL: ${m.total_positive_pnl:,.2f}",
        f"  Rule Passed:        {'✓ SÍ' if m.consistency_check_passed else '✗ NO'}",
        "",
        "── METAS DE PRODUCCIÓN ────────────────────────────────",
        f"  Sharpe > 1.5:       {'✓' if m.sharpe_ratio > 1.5 else '✗'} ({m.sharpe_ratio:.2f})",
        f"  MDD < 3% diario:    {'✓' if m.max_drawdown_pct < 3.0 else '✗'} ({m.max_drawdown_pct:.2f}%)",
        f"  Profit Factor >1.2: {'✓' if m.profit_factor > 1.2 else '✗'} ({m.profit_factor:.2f})",
        f"  Win Rate > 50%:     {'✓' if m.win_rate > 0.5 else '✗'} ({m.win_rate:.1%})",
        "=" * 65,
    ]
    return "\n".join(lines)
