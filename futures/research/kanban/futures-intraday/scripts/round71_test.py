#!/usr/bin/env python3
"""
round71_test.py — Round 71 M1/M5 Scalping Researcher
基于 Round 60 (初始发现) + Round 67 (复现优化) 的进阶研究:

Round 60 核心发现:
  - XAUUSD M5 美盘+RSI<25+ATR>0.15%做多 → n=176 WR=88.07% @hold=60
  - XAGUSD M5 美盘+RSI<25+ATR>0.15%做多 → n=233 WR=78.54% @hold=40
  - JP225 M5 美盘+RSI<25+ATR>0.15%做多 → n=219 WR=72.60% @hold=30
  - XAUUSD M1 美盘+RSI<20+ATR>0.10%做多 → n=71 WR=73.24% @hold=20
  - JP225 M1 亚盘+RSI<20+ATR>0.10%做多 → n=33 WR=100% @hold=10

Round 67 核心发现:
  - R60_M5_001 完全复现 (XAUUSD M5 WR=88.07% n=176)
  - XAGUSD RSI<20增强版 WR=84.69%(n=98) @hold=30
  - JP225 RSI<20增强版 WR=78.70%(n=108) @hold=30
  - XAUUSD M1 欧盘超卖 WR=89.66%(n=58) @hold=40
  - JP225 M1 亚盘完美信号 WR=93.94%(n=33) @hold=10

本轮目标 (Round 71):
  1. RSI阈值精细化: 15/18/20/22/25 分层扫描寻找最优WR峰值
  2. M5欧盘超卖扩展: 基于R67 M1欧盘发现上移至M5
  3. M1美盘深超卖: RSI<15极限信号 + 不同ATR阈值
  4. BB增强 + 连跌反转组合: 多条件筛选高胜率入口
  5. Session小时窗口: 特定小时区间(欧盘8-10, 美盘13-15等)
  6. ATR参数分层: 0.10%/0.15%/0.20%对比
  7. US30/US500精细化: 之前WR偏低, 调整参数看能否提升
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
REPORTS_DIR = PROJECT_DIR / "reports"

SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]

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

        # RSI
        df['rsi14'] = calc_rsi(df['close'])
        df['rsi7'] = calc_rsi(df['close'], period=7)

        # ATR
        df['atr14'] = calc_atr(df)
        df['atr_pct'] = df['atr14'] / df['close']

        # Moving averages
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()

        # Bollinger Bands (20,2)
        std20 = df['close'].rolling(window=20).std(ddof=0)
        df['bb_upper'] = df['ma20'] + 2 * std20
        df['bb_lower'] = df['ma20'] - 2 * std20

        # Consecutive candles
        bull = (df['close'] > df['open']).astype(int)
        bear = (df['close'] < df['open']).astype(int)
        bull_groups = (bull != bull.shift()).cumsum()
        bear_groups = (bear != bear.shift()).cumsum()
        df['consecutive_bull'] = bull.groupby(bull_groups).cumsum()
        df['consecutive_bear'] = bear.groupby(bear_groups).cumsum()
        doji_mask = (df['close'] == df['open']).values
        df.loc[doji_mask, 'consecutive_bull'] = 0
        df.loc[doji_mask, 'consecutive_bear'] = 0

        # Candle body ratio
        df['candle_range'] = (df['high'] - df['low']) / df['close']
        df['body_ratio'] = abs(df['close'] - df['open']) / (df['high'] - df['low']).replace(0, np.nan)
        df['body_ratio'] = df['body_ratio'].fillna(0)

        # Volume features
        df['vol_ma20'] = df['tick_volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['tick_volume'] / df['vol_ma20'].replace(0, np.nan)

        df.dropna(inplace=True)
        result[sym] = df
        print(f"  {sym:12s} {len(df):>8} rows  {str(df.index[0]):22s} -> {str(df.index[-1]):22s}")
    return result

# ── Grid test runner ───────────────────────────────────────────────

def run_grid_test(df, entry_condition, direction='long', hold_periods=None):
    """Run a hypothesis test on a single DataFrame."""
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
        if time_diff < 90:
            periods_per_year = 360_000
        elif time_diff < 180:
            periods_per_year = 72_000
        elif time_diff < 900:
            periods_per_year = 12_000
        else:
            periods_per_year = 6_000
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

def print_results_table(sym, results):
    """Pretty-print results table."""
    print(f"\n### {sym}")
    print(f"| Hold | n | avg_ret | WR | Sharpe | MaxDD |")
    print(f"|:----:|:-:|:-------:|:--:|:------:|:-----:|")
    for hp in sorted(results.keys(), key=int):
        r = results[hp]
        n = r['signal_count']
        if n == 0:
            print(f"| {hp:>2} | 0 | -- | -- | -- | -- |")
            continue
        wr = r['win_rate'] or 0
        best_str = "**" if wr >= 0.60 else ""
        best_end = "**" if wr >= 0.60 else ""
        print(f"| {best_str}{hp:>2}{best_end} | {n:>4} | {r['avg_return'] or 0:>+8.4f} | {wr:>6.2%} | {r['sharpe_ratio'] or 0:>6.2f} | {r['max_drawdown'] or 0:>7.4f} |")

# ── Hold periods ───────────────────────────────────────────────────

M1_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]
M5_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60, 72, 84, 96]

# ── Test Definitions ───────────────────────────────────────────────
# Category structure:
#   A = US Session (美盘)
#   B = Asia Session (亚盘)
#   C = Europe Session (欧盘)
#   D = Cross-session / Hour windows
#   E = Multi-condition combos

TESTS = [
    # ═══════════════════════════════════════════════════════════════
    # A: M5 US Session — RSI Threshold Refinement (美盘RSI阈值精细化)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M5_A001",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 15 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<15+ATR>0.15%做多 — 极限超卖高胜率"
    },
    {
        "id": "R71_M5_A002",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 18 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<18+ATR>0.15%做多 — RSI<18超卖扫描"
    },
    {
        "id": "R71_M5_A003",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<20+ATR>0.15%做多 — R60 RSI<20增强版(对照R67)"
    },
    {
        "id": "R71_M5_A004",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 22 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<22+ATR>0.15%做多 — RSI<22中等超卖"
    },
    {
        "id": "R71_M5_A005",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<25+ATR>0.15%做多 — R60基准复现对照"
    },

    # ═══════════════════════════════════════════════════════════════
    # B: M5 US Session — ATR Parameter Scan (ATR参数扫描)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M5_B001",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<20+ATR>0.10%做多 — 降ATR扩样本"
    },
    {
        "id": "R71_M5_B002",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<20+ATR>0.20%做多 — 升ATR提质量"
    },
    {
        "id": "R71_M5_B003",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<25+ATR>0.10%做多 — R60降ATR复现"
    },

    # ═══════════════════════════════════════════════════════════════
    # C: M5 Europe Session — 欧盘超卖扩展
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M5_C001",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘+RSI<20+ATR>0.10%做多 — 欧盘超卖初探(基于R67 M1发现)"
    },
    {
        "id": "R71_M5_C002",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘+RSI<25+ATR>0.10%做多 — 欧盘宽松超卖"
    },
    {
        "id": "R71_M5_C003",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 18 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘+RSI<18+ATR>0.15%做多 — 欧盘深超卖高质"
    },

    # ═══════════════════════════════════════════════════════════════
    # D: M5 Asia Session — 亚盘超卖扩展
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M5_D001",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 亚盘+RSI<20+ATR>0.10%做多 — 亚盘超卖扩展"
    },
    {
        "id": "R71_M5_D002",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 亚盘+RSI<25+ATR>0.10%做多 — 亚盘宽松超卖"
    },

    # ═══════════════════════════════════════════════════════════════
    # E: M5 BB Enhanced + Consecutive Bear (BB增强+连跌反转)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M5_E001",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and close < bb_lower and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close<BBL+RSI<25+ATR>0.15%做多 — BB下轨超卖(R67对照)"
    },
    {
        "id": "R71_M5_E002",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and consecutive_bear >= 3 and rsi14 < 30 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+连跌3+RSI<30+ATR>0.15%做多 — 连续下跌反转"
    },
    {
        "id": "R71_M5_E003",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and consecutive_bear >= 2 and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+连跌2+RSI<20+ATR>0.15%做多 — 轻连跌深超卖"
    },
    {
        "id": "R71_M5_E004",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and consecutive_bear >= 4 and rsi14 < 30 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+连跌4+RSI<30+ATR>0.10%做多 — 深连跌宽松ATR"
    },

    # ═══════════════════════════════════════════════════════════════
    # F: M1 US Session — 深超卖信号
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M1_F001",
        "timeframe": "M1",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 15 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+RSI<15+ATR>0.15%做多 — 极限超卖M1"
    },
    {
        "id": "R71_M1_F002",
        "timeframe": "M1",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 18 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+RSI<18+ATR>0.10%做多 — M1深超卖中等ATR"
    },
    {
        "id": "R71_M1_F003",
        "timeframe": "M1",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+RSI<20+ATR>0.10%做多 — R60_M1_001复现对照"
    },

    # ═══════════════════════════════════════════════════════════════
    # G: M1 Europe Session — 欧盘超短线(基于R67发现)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M1_G001",
        "timeframe": "M1",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 18 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 欧盘+RSI<18+ATR>0.10%做多 — R67 M1欧盘重新验证"
    },
    {
        "id": "R71_M1_G002",
        "timeframe": "M1",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 欧盘+RSI<20+ATR>0.10%做多 — R67 M1欧盘宽松版"
    },
    {
        "id": "R71_M1_G003",
        "timeframe": "M1",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 15 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 欧盘+RSI<15+ATR>0.15%做多 — M1欧盘极限信号"
    },

    # ═══════════════════════════════════════════════════════════════
    # H: M1 Asia Session — 亚盘M1(基于R67 JP225完美信号)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M1_H001",
        "timeframe": "M1",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 18 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 亚盘+RSI<18+ATR>0.10%做多 — 亚盘深超卖"
    },
    {
        "id": "R71_M1_H002",
        "timeframe": "M1",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 亚盘+连跌3+RSI<25+ATR>0.10%做多 — 亚盘连跌反转"
    },

    # ═══════════════════════════════════════════════════════════════
    # I: Hour Windows — 交易时段小时窗口
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M5_I001",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "hour >= 13 and hour <= 15 and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘午盘(13-15)+RSI<20+ATR>0.15%做多 — 美盘活跃窗口"
    },
    {
        "id": "R71_M5_I002",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "hour >= 8 and hour <= 10 and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘早盘(8-10)+RSI<20+ATR>0.15%做多 — 欧盘开盘窗口"
    },
    {
        "id": "R71_M5_I003",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "hour >= 0 and hour <= 3 and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 亚盘凌晨(0-3)+RSI<20+ATR>0.15%做多 — 亚盘平静窗口"
    },

    # ═══════════════════════════════════════════════════════════════
    # J: RSI7 (fast RSI) — 快速RSI短线信号
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R71_M5_J001",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi7 < 15 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI7<15+ATR>0.15%做多 — 快速RSI短线超卖(持仓更短)"
    },
    {
        "id": "R71_M5_J002",
        "timeframe": "M5",
        "symbols": SYMBOLS,
        "entry_condition": "session == 'us' and rsi7 < 10 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI7<10+ATR>0.20%做多 — RSI7极限反转信号"
    },
]


# ── Main ───────────────────────────────────────────────────────────

def analyze_results(all_results):
    """Extract best findings from all test results."""
    findings = []
    for test_id, sym_results in all_results.items():
        test_info = next((t for t in TESTS if t['id'] == test_id), None)
        if not test_info:
            continue
        for sym, hp_results in sym_results.items():
            for hp, stats in hp_results.items():
                n = stats.get('signal_count', 0)
                wr = stats.get('win_rate', 0) or 0
                sharp = stats.get('sharpe_ratio', 0) or 0
                avg_ret = stats.get('avg_return', 0) or 0
                if n >= 30 and wr >= 0.60:
                    findings.append({
                        'test_id': test_id,
                        'symbol': sym,
                        'timeframe': test_info['timeframe'],
                        'description': test_info['description'],
                        'entry_condition': test_info['entry_condition'],
                        'direction': test_info['direction'],
                        'hold_period': hp,
                        'signal_count': n,
                        'win_rate': wr,
                        'sharpe_ratio': sharp,
                        'avg_return': avg_ret,
                    })
    # Sort by win_rate descending
    findings.sort(key=lambda f: (-f['win_rate'], -f['signal_count']))
    return findings

if __name__ == "__main__":
    print("=" * 80)
    print("  Round 71 — M1/M5 Scalping Researcher Pipeline")
    print("  Building on R60+R67: RSI阈值精细化, Session扩展, 参数优化")
    print(f"  执行时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)

    all_results = {}

    for test in TESTS:
        print(f"\n{'─' * 80}")
        print(f"\n### {test['id']}: {test['description']}")
        print(f"  Condition: {test['entry_condition']}")
        print(f"  Timeframe: {test['timeframe']}  Direction: {test['direction']}")

        print(f"\n  Loading data...")
        data = load_and_compute(test['timeframe'], test['symbols'])

        for sym, df in data.items():
            results = run_grid_test(df, test['entry_condition'], test['direction'], test['hold_periods'])
            all_results.setdefault(test['id'], {})[sym] = results
            print_results_table(sym, results)

    # Save full results
    out_path = LOGS_DIR / "round71_results.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n{'─' * 80}")
    print(f"\nResults saved to {out_path}")

    # Analyze and save findings
    findings = analyze_results(all_results)
    findings_path = LOGS_DIR / "round71_findings.json"
    with open(findings_path, 'w') as f:
        json.dump(findings, f, indent=2, default=str)
    print(f"Findings saved to {findings_path}")
    print(f"\nTotal qualified findings (n>=30, WR>=60%): {len(findings)}")

    # Print top findings
    print(f"\n{'=' * 80}")
    print(f"  TOP FINDINGS (n>=30, WR>=60%)")
    print(f"{'=' * 80}")
    print(f"{'Rank':>4} | {'TestID':>14} | {'Symbol':>8} | {'Hold':>4} | {'n':>5} | {'WR':>8} | {'Sharpe':>7} | {'AvgRet':>9} | {'Description'}")
    print(f"{'-'*4}-+-{'-'*14}-+-{'-'*8}-+-{'-'*4}-+-{'-'*5}-+-{'-'*8}-+-{'-'*7}-+-{'-'*9}-+-{'-'*40}")
    for i, f in enumerate(findings[:30], 1):
        desc = f['description'][:38]
        print(f"{i:>4d} | {f['test_id']:>14} | {f['symbol']:>8} | {f['hold_period']:>4d} | {f['signal_count']:>5d} | {f['win_rate']:>7.1%} | {f['sharpe_ratio']:>6.2f} | {f['avg_return']:>+8.4f} | {desc}")

    print("\nDone.")
