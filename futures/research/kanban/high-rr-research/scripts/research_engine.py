#!/usr/bin/env python3
"""research_engine.py — High-RR 回测引擎

支持多组 SL/TP 配置 + H1 趋势方向 + M5 入场时机。
评估指标: WR, avg_return, Sharpe, Profit Factor, Max Drawdown。
"""

from __future__ import annotations

import logging
import math
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from data_loader import load_data
from data_loader import detect_pullback_to_ma

log = logging.getLogger("high_rr_engine")

# ─── 全部 19 个 MT5 品种 ───
_HS = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts")
if _HS not in sys.path:
    sys.path.insert(0, _HS)
from mt5_symbols import MT5_SYMBOLS_19
SYMBOLS = MT5_SYMBOLS_19

# ─── 可搜索的参数空间 ───
PARAM_SPACE = {
    "pattern_type": ["trend_pullback", "structure_breakout", "fakeout_reversal"],
    "timeframe_entry": ["M5", "M15"],
    "h1_trend": ["up", "down", "any"],
    "session": ["asia", "europe", "us", "any"],
    "sl_multiple": [0.5, 0.8, 1.0, 1.2, 1.5],
    "tp_multiple": [3.0, 4.0, 5.0, 6.0, 8.0, 10.0],
    "rsi14_max": [30, 35, 40, 45, 50],
    "rsi14_min": [50, 55, 60, 65, 70],
    "consecutive_bear": [1, 2, 3],
    "consecutive_bull": [1, 2, 3],
    "pullback_to_ma50": [True, False],
}


@dataclass
class TradeRecord:
    """单笔交易记录"""
    entry_time: pd.Timestamp = None
    exit_time: pd.Timestamp = None
    direction: str = ""          # long/short
    entry_price: float = 0.0
    exit_price: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    return_pct: float = 0.0     # 盈亏百分比（含SL/TP）
    hold_bars: int = 0           # 持仓bar数
    exit_reason: str = ""        # sl/tp/timeout
    atr_at_entry: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    symbol: str = ""
    params: dict = field(default_factory=dict)
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0       # 累计收益率
    avg_return_pct: float = 0.0          # 平均每笔收益率
    sharpe: float = 0.0                  # 夏普比率（年化）
    profit_factor: float = 0.0           # 总盈利/总亏损
    max_drawdown_pct: float = 0.0        # 最大回撤%
    avg_hold_bars: float = 0.0
    trades: List[TradeRecord] = field(default_factory=list)
    error: str = ""


def _calc_sharp(returns: List[float], periods_per_year: int = 72000) -> float:
    """计算年化夏普比率（M5 = 72000, M15 = 24000）"""
    if len(returns) < 5:
        return 0.0
    arr = np.array(returns)
    if arr.std() == 0:
        return 0.0
    return float(np.mean(arr) / np.std(arr) * math.sqrt(periods_per_year))


def _calc_profit_factor(gross_profit: float, gross_loss: float) -> float:
    if abs(gross_loss) < 0.0001:
        return gross_profit / 0.0001 if gross_profit > 0 else 0.0
    return abs(gross_profit / gross_loss)


def _calc_max_dd(equity_curve: List[float]) -> float:
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100


def backtest_strategy(
    symbol: str,
    entry_tf: str,           # "M5" or "M15"
    h1_data: pd.DataFrame,
    entry_data: pd.DataFrame,
    params: dict,
) -> BacktestResult:
    """对单个策略配置运行回测

    params 支持:
      - pattern_type: 形态类型（目前用于分组，逻辑统一走条件判断）
      - h1_trend: up/down/any
      - session: asia/europe/us/any
      - sl_multiple, tp_multiple
      - rsi14_max, rsi14_min (M5/M15 RSI门槛)
      - consecutive_bear, consecutive_bull
      - pullback_to_ma50: bool
      - max_hold_bars: int (默认 48 M5 bars ≈ 4h)
    """
    result = BacktestResult(symbol=symbol, params=params)
    sl_mult = params.get("sl_multiple", 1.0)
    tp_mult = params.get("tp_multiple", 5.0)
    req_h1_trend = params.get("h1_trend", "any")
    req_session = params.get("session", "any")
    rsi14_max = params.get("rsi14_max", None)
    rsi14_min = params.get("rsi14_min", None)
    req_cb = params.get("consecutive_bear", 0)
    req_cbull = params.get("consecutive_bull", 0)
    req_pb50 = params.get("pullback_to_ma50", False)
    direction = params.get("direction", "long")  # 由外面传方向，或自动判断

    max_hold = params.get("max_hold_bars", 48)

    if entry_data.empty or h1_data.empty:
        result.error = "No data"
        return result

    # 预计算数据已包含全部指标，无需额外计算
    # 只需要检查必要的列是否存在
    required_cols = ["rsi14", "atr14", "hh_20", "ll_20", "ma50",
                     "ema12_above_ema26", "market_regime", "session"]
    missing = [c for c in required_cols if c not in entry_data.columns]
    if missing:
        result.error = f"Missing pre-computed columns: {missing}"
        return result

    # 对齐 H1 数据到每个 entry bar（向前填充 H1 指标）
    h1_cols = [c for c in ["ma50", "hh_20", "ll_20", "ema12_above_ema26", "market_regime"]
               if c in h1_data.columns]
    if not h1_cols:
        result.error = "H1 data missing required trend columns"
        return result
    h1_align = h1_data[h1_cols].copy()
    h1_align.columns = [f"h1_{c}" for c in h1_cols]
    entry_aligned = entry_data.join(h1_align, how="left")
    entry_aligned = entry_aligned.ffill()

    trades = []
    equity_curve = [10000.0]
    gross_profit = 0.0
    gross_loss = 0.0
    all_returns = []

    i = 50  # 跳过 warmup
    while i < len(entry_aligned) - 5:
        bar = entry_aligned.iloc[i]

        # ── Session 过滤 ──
        if req_session != "any" and bar.get("session", "") != req_session:
            i += 1
            continue

        # ── H1 趋势过滤（使用预计算列） ──
        if req_h1_trend != "any":
            h1_ema = bar.get("h1_ema12_above_ema26", 0)
            h1_regime = bar.get("h1_market_regime", "sideways")
            is_up = (h1_ema == 1) and h1_regime == "bull"
            is_down = (h1_ema == 0) and h1_regime == "bear"
            current_trend = "up" if is_up else ("down" if is_down else "sideways")
            if current_trend != req_h1_trend:
                i += 1
                continue

        # ── 入场条件 ──
        entry_hit = False
        entry_reason = []

        if direction == "long":
            # 超卖/回调买入
            if rsi14_max is not None and bar.get("rsi14", 100) > rsi14_max:
                pass  # not triggered
            elif req_cb > 0 and bar.get("consecutive_bear", 0) < req_cb:
                pass
            elif req_pb50 and not detect_pullback_to_ma(
                    entry_data.loc[:bar.name], bar.get("h1_ma50", 0)):
                pass
            else:
                entry_hit = True
                if rsi14_max is not None:
                    entry_reason.append(f"rsi<{rsi14_max}")
                if req_cb > 0:
                    entry_reason.append(f"cb>={req_cb}")
                if req_pb50:
                    entry_reason.append("pb50")

        else:  # short
            if rsi14_min is not None and bar.get("rsi14", 0) < rsi14_min:
                pass
            elif req_cbull > 0 and bar.get("consecutive_bull", 0) < req_cbull:
                pass
            else:
                entry_hit = True
                if rsi14_min is not None:
                    entry_reason.append(f"rsi>{rsi14_min}")
                if req_cbull > 0:
                    entry_reason.append(f"cbull>={req_cbull}")

        if not entry_hit:
            i += 1
            continue

        # ── 入场执行 ──
        entry_price = bar["close"]
        atr = bar.get("atr14", 0)
        if atr <= 0:
            i += 1
            continue

        trade = TradeRecord()
        trade.entry_time = bar.name
        trade.entry_price = entry_price
        trade.direction = direction
        trade.atr_at_entry = atr

        if direction == "long":
            trade.sl_price = entry_price - atr * sl_mult
            trade.tp_price = entry_price + atr * tp_mult
        else:
            trade.sl_price = entry_price + atr * sl_mult
            trade.tp_price = entry_price - atr * tp_mult

        # ── Walk forward ──
        closed = False
        for j in range(i + 1, min(i + max_hold, len(entry_aligned))):
            future = entry_aligned.iloc[j]
            trade.hold_bars = j - i

            if direction == "long":
                if future["low"] <= trade.sl_price:
                    trade.exit_time = future.name
                    trade.exit_price = trade.sl_price
                    trade.exit_reason = "sl"
                    closed = True
                    break
                if future["high"] >= trade.tp_price:
                    trade.exit_time = future.name
                    trade.exit_price = trade.tp_price
                    trade.exit_reason = "tp"
                    closed = True
                    break
            else:
                if future["high"] >= trade.sl_price:
                    trade.exit_time = future.name
                    trade.exit_price = trade.sl_price
                    trade.exit_reason = "sl"
                    closed = True
                    break
                if future["low"] <= trade.tp_price:
                    trade.exit_time = future.name
                    trade.exit_price = trade.tp_price
                    trade.exit_reason = "tp"
                    closed = True
                    break

        if not closed:
            # Timeout: 以最后一根 close 平仓
            trade.exit_time = entry_aligned.iloc[min(i + max_hold - 1, len(entry_aligned) - 1)].name
            trade.exit_price = entry_aligned.iloc[min(i + max_hold - 1, len(entry_aligned) - 1)]["close"]
            trade.exit_reason = "timeout"

        # ── 盈亏计算 ──
        if direction == "long":
            trade.return_pct = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            trade.return_pct = (trade.entry_price - trade.exit_price) / trade.entry_price * 100

        if trade.return_pct > 0:
            trade.exit_reason = "tp"
        elif trade.return_pct < 0:
            trade.exit_reason = "sl"
        # else: timeout flat -> still count as loss for win_rate

        trades.append(trade)
        all_returns.append(trade.return_pct)
        equity_curve.append(equity_curve[-1] * (1 + trade.return_pct / 100))

        if trade.return_pct > 0:
            gross_profit += trade.return_pct
        else:
            gross_loss += abs(trade.return_pct)

        # 跳过持仓期内的所有 bar
        i = entry_aligned.index.get_loc(trade.exit_time) + 1

    # ── 汇总 ──
    result.trades = trades
    result.total_trades = len(trades)
    result.wins = sum(1 for t in trades if t.return_pct > 0)
    result.losses = result.total_trades - result.wins
    result.win_rate = (result.wins / result.total_trades * 100) if result.total_trades > 0 else 0
    result.avg_return_pct = np.mean(all_returns) if all_returns else 0
    result.total_return_pct = ((equity_curve[-1] - 10000) / 10000 * 100) if len(equity_curve) > 1 else 0
    result.sharpe = _calc_sharp(all_returns, 72000 if entry_tf == "M5" else 24000)
    result.profit_factor = _calc_profit_factor(gross_profit, gross_loss)
    result.max_drawdown_pct = _calc_max_dd(equity_curve)
    result.avg_hold_bars = float(np.mean([t.hold_bars for t in trades])) if trades else 0

    return result


def random_params() -> dict:
    """随机采样一组参数"""
    params = {}
    for key, values in PARAM_SPACE.items():
        params[key] = random.choice(values)

    # 根据 pattern_type 调整个别默认值
    if params["pattern_type"] == "structure_breakout":
        params["sl_multiple"] = random.choice([0.5, 0.8])
        params["tp_multiple"] = random.choice([6.0, 8.0, 10.0])
        params["pullback_to_ma50"] = False
    elif params["pattern_type"] == "fakeout_reversal":
        params["sl_multiple"] = random.choice([0.8, 1.0, 1.2])
        params["tp_multiple"] = random.choice([5.0, 6.0, 8.0])
    else:  # trend_pullback
        params["sl_multiple"] = random.choice([0.8, 1.0, 1.2])
        params["tp_multiple"] = random.choice([3.0, 4.0, 5.0])

    # 方向: 根据 h1_trend 自动决定
    if params["h1_trend"] == "up":
        params["direction"] = "long"
    elif params["h1_trend"] == "down":
        params["direction"] = "short"
    else:
        params["direction"] = random.choice(["long", "short"])

    return params


def run_research_round(symbols: Optional[List[str]] = None,
                       samples_per_symbol: int = 5) -> List[BacktestResult]:
    """一轮研究: 对每个品种随机采样参数并回测"""
    if symbols is None:
        symbols = SYMBOLS

    results = []

    for sym in symbols:
        log.info("Loading data for %s...", sym)
        h1_raw = load_data("H1", [sym])
        entry_raw = load_data("M5", [sym])

        h1_df = h1_raw.get(sym, pd.DataFrame())
        entry_df = entry_raw.get(sym, pd.DataFrame())

        if h1_df.empty or entry_df.empty:
            log.warning("No data for %s, skipping", sym)
            continue

        # 对齐时间范围
        start = max(h1_df.index[0], entry_df.index[0])
        end = min(h1_df.index[-1], entry_df.index[-1])
        h1_df = h1_df[start:end]
        entry_df = entry_df[start:end]

        if len(h1_df) < 100 or len(entry_df) < 500:
            log.warning("Insufficient data for %s", sym)
            continue

        # 预计算数据已包含全部指标，直接使用
        for _ in range(samples_per_symbol):
            params = random_params()
            try:
                bt = backtest_strategy(sym, "M5", h1_df, entry_df, params)
                if bt.total_trades > 0:
                    results.append(bt)
                    log.info("  %s %s: %d trades WR=%.1f%% Sharpe=%.2f PF=%.2f",
                             sym, params.get("pattern_type","?"),
                             bt.total_trades, bt.win_rate, bt.sharpe, bt.profit_factor)
            except Exception as e:
                log.warning("  %s error: %s", sym, e)

    # 排序: Sharpe 优先
    results.sort(key=lambda r: r.sharpe, reverse=True)
    return results
