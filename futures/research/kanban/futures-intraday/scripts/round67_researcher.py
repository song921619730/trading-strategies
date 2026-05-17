#!/usr/bin/env python3
"""
Round 67 — M1/M5 Scalping Optimization & Session Window Expansion
基于 Round 60 (M1/M5 初始发现) + Round 66 (H1/M30 发现) 的下一步:

Round 60 核心发现:
  - XAUUSD M5 美盘+RSI<25+ATR>0.15%做多 → n=176 WR=88.07% @hold=60
  - XAGUSD M5 美盘+RSI<25+ATR>0.15%做多 → n=233 WR=78.54% @hold=40
  - JP225 M5 美盘+RSI<25+ATR>0.15%做多 → n=219 WR=72.60% @hold=30
  - XAUUSD M5 美盘+BBL+RSI<30+ATR>0.15%做多 → n=152 WR=75% @hold=48
  - XAUUSD M1 美盘+RSI<20+ATR>0.10%做多 → n=71 WR=73.24% @hold=20
  - JP225 M1 亚盘+RSI<20+ATR>0.10%做多 → n=33 WR=100% @hold=10

Round 66 发现 (下移至M1/M5):
  - USOIL M30 Session窗口(12-14/0-3)超卖 n=263 WR=65.02%
  - JP225 H1 亚盘+连跌3+RSI<30+BBL WR=70.22% n=178
  - US500 M30 亚盘+RSI<25+ATR>0.10%做多 n=182 WR=65.38%

本轮目标:
  1. 复现并优化 R60_M5_001 (XAUUSD M5 美盘超卖) 最佳参数
  2. 降ATR扩样本 — 验证WR能否维持
  3. R66 Session窗口策略下移至M5
  4. R66 JP225/US500信号下移至M5
  5. M1超短线增强 — 验证100% WR信号的稳定性
  6. 新品种专属优化策略

品种 (5): XAUUSD, XAGUSD, JP225, US500, US30
时间框架: M1, M5
"""
import json
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"

# ── Indicators ─────────────────────────────────────────────────────

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))

def calc_atr(df, period=14):
    prev_close = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def session_label(h):
    if h < 8: return 'asia'
    if h < 16: return 'europe'
    return 'us'

def load_and_compute(timeframe, symbols):
    """Load parquet data and compute all technical indicators."""
    tf_dir = DATA_DIR / timeframe
    result = {}
    for sym in symbols:
        fpath = tf_dir / f"{sym}.parquet"
        if not fpath.exists():
            print(f"  SKIP {sym}: file not found ({fpath})")
            continue
        df = pd.read_parquet(fpath)
        df.index.name = "time"
        df.sort_index(inplace=True)

        # Time features
        df['hour'] = df.index.hour
        df['minute'] = df.index.minute
        df['session'] = df['hour'].apply(session_label)
        df['dayofweek'] = df.index.dayofweek

        # Volume features
        df['log_volume'] = np.log1p(df['tick_volume'])

        # RSI
        df['rsi14'] = calc_rsi(df['close'])
        df['rsi7'] = calc_rsi(df['close'], period=7)

        # ATR
        df['atr14'] = calc_atr(df)
        df['atr_pct'] = df['atr14'] / df['close']

        # Moving averages
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()
        df['ma100'] = df['close'].rolling(window=100).mean()
        df['ma200'] = df['close'].rolling(window=200).mean()

        # Bollinger Bands
        std20 = df['close'].rolling(window=20).std(ddof=0)
        df['bb_upper'] = df['ma20'] + 2 * std20
        df['bb_lower'] = df['ma20'] - 2 * std20
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['ma20']
        df['bb_pos'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)

        # Price relative to MA
        df['pct_from_ma20'] = (df['close'] - df['ma20']) / df['ma20']
        df['pct_from_ma50'] = (df['close'] - df['ma50']) / df['ma50']
        df['pct_from_ma200'] = (df['close'] - df['ma200']) / df['ma200']

        # Consecutive candles
        bull = (df['close'] > df['open']).astype(int)
        bear = (df['close'] < df['open']).astype(int)
        bull_groups = (bull != bull.shift()).cumsum()
        bear_groups = (bear != bear.shift()).cumsum()
        df['consecutive_bull'] = bull.groupby(bull_groups).cumsum()
        df['consecutive_bear'] = bear.groupby(bear_groups).cumsum()

        # Candle features
        df['candle_range'] = (df['high'] - df['low']) / df['close']
        df['upper_shadow'] = (df['high'] - df[['open', 'close']].max(axis=1)) / df['close']
        df['lower_shadow'] = (df[['open', 'close']].min(axis=1) - df['low']) / df['close']
        body = abs(df['close'] - df['open'])
        candle_hi = df['high'] - df['low']
        df['body_pct'] = (body / candle_hi.replace(0, np.nan)).fillna(0)

        # Volume spike
        df['vol_ma20'] = df['tick_volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['tick_volume'] / df['vol_ma20'].replace(0, np.nan)

        df.dropna(inplace=True)
        result[sym] = df
        print(f"  {sym:12s} {len(df):>8} rows  {str(df.index[0]):22s} -> {str(df.index[-1]):22s}")
    return result

# ── Grid test runner ───────────────────────────────────────────────

def run_grid_test(df, entry_condition, direction='long', hold_periods=None):
    if hold_periods is None:
        hold_periods = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]

    dir_sign = 1.0 if direction == 'long' else -1.0
    close_arr = df['close'].values
    n_rows = len(df)

    try:
        mask = df.eval(entry_condition).values.astype(bool)
    except Exception as e:
        print(f"  ERROR evaluating condition: {e}")
        return {hp: {"signal_count": 0, "avg_return": None, "win_rate": None,
                     "sharpe_ratio": None, "max_drawdown": None} for hp in hold_periods}

    signal_indices = np.where(mask)[0]
    print(f"  Signals: {len(signal_indices)}")

    # Auto-select periods_per_year
    if len(df) > 1:
        time_diff = (df.index[-1] - df.index[0]).total_seconds() / len(df)
        if time_diff < 90:       # ~1 min
            periods_per_year = 360_000
        elif time_diff < 180:    # ~5 min
            periods_per_year = 72_000
        else:
            periods_per_year = 12_000
    else:
        periods_per_year = 72_000

    results = {}
    for hp in hold_periods:
        returns = []
        for i in signal_indices:
            exit_idx = i + hp
            if exit_idx >= n_rows:
                continue
            entry_price = close_arr[i]
            exit_price = close_arr[exit_idx]
            ret = (exit_price - entry_price) / entry_price * dir_sign
            returns.append(ret)

        ret_arr = np.array(returns, dtype=np.float64)
        n = len(ret_arr)
        if n == 0:
            results[hp] = {"signal_count": 0, "avg_return": None, "win_rate": None,
                           "sharpe_ratio": None, "max_drawdown": None}
            continue

        avg_ret = float(ret_arr.mean())
        win_rate = float((ret_arr > 0).mean())
        std_ret = float(ret_arr.std())
        sharpe = avg_ret / std_ret * np.sqrt(periods_per_year / hp) if std_ret > 0 else 0.0

        equity = np.cumprod(1.0 + ret_arr)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_dd = float(drawdown.max())

        results[hp] = {
            "signal_count": n,
            "avg_return": avg_ret,
            "win_rate": win_rate,
            "sharpe_ratio": float(sharpe),
            "max_drawdown": max_dd,
        }
    return results

def print_results_table(sym, results, label=""):
    print(f"\n### {label} {sym}")
    print(f"| Hold |   n  | avg_ret  |   WR    | Sharpe |  MaxDD  |")
    print(f"|:----:|:----:|:--------:|:-------:|:------:|:-------:|")
    for hp in sorted(results.keys(), key=int):
        r = results[hp]
        n = r['signal_count']
        if n == 0:
            print(f"| {hp:>2}  |  0   |   ---    |   ---   |  ---   |   ---   |")
            continue
        wr = r['win_rate'] or 0
        best = wr >= 0.60 and n >= 30
        wr_str = f"**{wr:>6.2%}**" if best else f"{wr:>6.2%}"
        print(f"| {hp:>2}  | {n:>4} | {r['avg_return'] or 0:>+8.4f} | {wr_str} | {r['sharpe_ratio'] or 0:>6.2f} | {r['max_drawdown'] or 0:>7.4f} |")

# ── Hold periods ──────────────────────────────────────────────────
M1_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]
M5_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]
# Extended holds for M5 to test longer scalps
M5_HOLDS_LONG = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60, 72, 84, 96]

TARGET_SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]

# ═══════════════════════════════════════════════════════════════════
# TEST DEFINITIONS — Round 67: M1/M5 Scalping Optimization
# ═══════════════════════════════════════════════════════════════════

TESTS = [

    # ═══════════════════════════════════════════════════════════════
    # SECTION A: M5 美盘超卖 — R60_M5_001 复现+优化
    # R60_M5_001: XAUUSD n=176 WR=88.07% @hold=60
    #             XAGUSD n=233 WR=78.54% @hold=40
    #             JP225  n=219 WR=72.60% @hold=30
    #             US30   n=134 WR=67.91% @hold=30
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R67_M5_A001",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "M5 美盘+RSI<25+ATR>0.15%做多 — R60_M5_001复现+扩持有期"
    },
    {
        "id": "R67_M5_A002",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "M5 美盘+RSI<20+ATR>0.15%做多 — 严RSI测试"
    },
    {
        "id": "R67_M5_A003",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "M5 美盘+RSI<25+ATR>0.10%做多 — 降ATR扩样本"
    },
    {
        "id": "R67_M5_A004",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "M5 美盘+RSI<20+ATR>0.10%做多 — 严RSI+降ATR"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION B: M5 跨Session超卖 + R66信号下移
    # B003 = JP225 H1 亚盘+连跌3+RSI<30+BBL 下移至M5
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R67_M5_B001",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 亚盘+RSI<25+ATR>0.10%做多 — 亚盘超卖降ATR"
    },
    {
        "id": "R67_M5_B002",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘+RSI<25+ATR>0.10%做多 — 欧盘超卖降ATR"
    },
    {
        "id": "R67_M5_B003",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 30 and close < bb_lower and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "M5 亚盘+连跌3+RSI<30+BBL+ATR>0.10%做多 — JP225 H1信号下移M5"
    },
    {
        "id": "R67_M5_B004",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and consecutive_bear >= 3 and rsi14 < 30 and close < bb_lower and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "M5 美盘+连跌3+RSI<30+BBL+ATR>0.10%做多 — 美盘连跌反转"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION C: M5 Session窗口策略 (R66_G001/G003 下移M5)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R67_M5_C001",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 14 and rsi14 < 25 and atr_pct > 0.0005",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 London-NY(12-14)+RSI<25+ATR>0.05%做多 — R66_G001下移M5"
    },
    {
        "id": "R67_M5_C002",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "hour >= 0 and hour < 3 and rsi14 < 25 and atr_pct > 0.0005",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 东京(0-3)+RSI<25+ATR>0.05%做多 — R66_G003下移M5"
    },
    {
        "id": "R67_M5_C003",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 14 and rsi14 > 70 and atr_pct > 0.0005",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 London-NY(12-14)+RSI>70+ATR>0.05%做空 — R66_G002下移M5"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION D: M5 BB/连跌增强 (R60_M5_006/008 优化)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R67_M5_D001",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and close < bb_lower and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "M5 美盘+close<BBL+RSI<25+ATR>0.15%做多 — R60_M5_006增强严RSI"
    },
    {
        "id": "R67_M5_D002",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and consecutive_bear >= 3 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "M5 美盘+连跌3+RSI<25+ATR>0.10%做多 — R60_M5_008增强严RSI"
    },
    {
        "id": "R67_M5_D003",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and close > bb_upper and rsi14 > 75 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close>BBU+RSI>75+ATR>0.15%做空 — R60_M5_007增强"
    },
    {
        "id": "R67_M5_D004",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and close > bb_upper and rsi14 > 70 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close>BBU+RSI>70+ATR>0.10%做空 — 超买降ATR"

    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION E: M1 超短线增强 (R60_M1系列复现+扩展)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R67_M1_E001",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+RSI<20+ATR>0.10%做多 — R60_M1_001复现+全持有期"
    },
    {
        "id": "R67_M1_E002",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 亚盘+RSI<20+ATR>0.10%做多 — R60_M1_003复现+全持有期"
    },
    {
        "id": "R67_M1_E003",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 15 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+RSI<15+ATR>0.15%做多 — R60_BONUS极限超卖增强"
    },
    {
        "id": "R67_M1_E004",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 80 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+RSI>80+ATR>0.10%做空 — R60_M1_002复现+全持有期"
    },
    {
        "id": "R67_M1_E005",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and consecutive_bear >= 3 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+连跌3+RSI<25+ATR>0.10%做多 — M1连跌反转"
    },
    {
        "id": "R67_M1_E006",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and close < bb_lower and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+close<BBL+RSI<25+ATR>0.10%做多 — M1 BB超卖"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION F: 新品种专属优化 + 做空扫描
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R67_M5_F001",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'us' and rsi14 < 20 and close < bb_lower and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "XAUUSD M5 美盘+RSI<20+BBL+ATR>0.20%做多 — 黄金极限超卖特化"
    },
    {
        "id": "R67_M5_F002",
        "timeframe": "M5",
        "symbols": ["JP225"],
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS_LONG,
        "description": "JP225 M5 亚盘+RSI<20+ATR>0.15%做多 — 日经亚盘超卖特化"
    },
    {
        "id": "R67_M5_F003",
        "timeframe": "M5",
        "symbols": ["US500"],
        "entry_condition": "session == 'europe' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "US500 M5 欧盘+RSI<20+ATR>0.10%做多 — 标普欧盘超卖特化"
    },
    {
        "id": "R67_M5_F004",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 80 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI>80+ATR>0.15%做空 — 全品种超买做空扫描"
    },
    {
        "id": "R67_M5_F005",
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and consecutive_bull >= 3 and rsi14 > 70 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+连涨3+RSI>70+ATR>0.10%做空 — 连续上涨反转做空"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION G: M1 亚盘/欧盘 + 连跌特化
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R67_M1_G001",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 15 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 亚盘+RSI<15+ATR>0.15%做多 — 亚盘极限超卖"
    },
    {
        "id": "R67_M1_G002",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 欧盘+RSI<20+ATR>0.10%做多 — 欧盘超卖"
    },
    {
        "id": "R67_M1_G003",
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 亚盘+连跌3+RSI<25+ATR>0.10%做多 — 亚盘连跌反转"
    },
]

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    print("=" * 90)
    print("  Round 67 — M1/M5 Scalping Optimization & Session Window Expansion")
    print(f"  Start time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Total tests: {len(TESTS)}")
    print("=" * 90)

    all_results = {}

    tests_by_tf = {}
    for t in TESTS:
        tf = t["timeframe"]
        tests_by_tf.setdefault(tf, []).append(t)

    for tf, tf_tests in tests_by_tf.items():
        print(f"\n{'#'*90}")
        print(f"# Loading {tf} data ...")
        print(f"{'#'*90}")

        all_syms = set()
        for t in tf_tests:
            for s in t["symbols"]:
                all_syms.add(s)
        all_syms = sorted(all_syms)

        import time
        start = time.time()
        data = load_and_compute(tf, all_syms)
        load_time = time.time() - start
        print(f"\n  ✅ {tf} data loaded ({load_time:.1f}s) — {len(data)} symbols")

        if not data:
            print(f"  ❌ No {tf} data available, skipping")
            continue

        for t in tf_tests:
            test_id = t["id"]
            print(f"\n{'─'*90}")
            print(f"  🧪 {test_id}: {t['description']}")
            print(f"  Condition: {t['entry_condition']}")
            print(f"  Direction: {t['direction']} | Holds: {t['hold_periods']}")
            print(f"{'─'*90}")

            test_start = time.time()
            test_results = {}

            for sym in t["symbols"]:
                if sym not in data:
                    print(f"  SKIP {sym}: not loaded")
                    continue
                df = data[sym]
                print(f"\n  ▶ {sym} ({len(df)} rows):")

                sym_res = run_grid_test(
                    df,
                    entry_condition=t["entry_condition"],
                    direction=t["direction"],
                    hold_periods=t["hold_periods"],
                )
                test_results[sym] = sym_res
                print_results_table(sym, sym_res, label=tf)

            all_results[test_id] = test_results
            test_elapsed = time.time() - test_start
            print(f"\n  ⏱ {test_id} done ({test_elapsed:.1f}s)")

    # Save results
    LOGS_DIR.mkdir(exist_ok=True)
    results_path = LOGS_DIR / "round67_researcher_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n{'='*90}")
    print(f"  ✅ All tests complete! Results saved to: {results_path}")
    print(f"  Completion time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Tests run: {len(TESTS)}")
    print(f"{'='*90}")

if __name__ == "__main__":
    main()
