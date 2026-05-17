#!/usr/bin/env python3
"""
Round 64 — 欧盘/亚盘 Session 专注挖掘：H1/M30 Asia & London 时段模式
转向: 之前63轮已穷尽美盘(US session)，本轮全面转向亚盘(Asia)和欧盘(London)时段

研究方向重点:
1. 亚盘方向偏差（JP225/USDJPY等亚系品种）
2. 亚盘低波动后的均值回归
3. 亚盘/欧盘开盘方向性延续
4. 伦敦开盘（08:00 UTC）方向性突破
5. 欧盘回调买入 / 伦敦突破
6. Session 转换（亚→欧 07-09 UTC, 欧→美 15-17 UTC）

目标品种 (14): XAUUSD, XAGUSD, USTEC, US30, US500, JP225, HK50,
              USOIL, UKOIL, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF
时间框架: H1, M30
"""
import json, sys, time
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"

# ── Indicator helpers ─────────────────────────────────────────────────────

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
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
    """Load parquet data and compute all indicators needed."""
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
        df['session'] = df['hour'].apply(session_label)
        df['dayofweek'] = df.index.dayofweek

        # RSI
        df['rsi14'] = calc_rsi(df['close'])

        # ATR
        df['atr14'] = calc_atr(df)
        df['atr_pct'] = df['atr14'] / df['close']

        # Moving Averages
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()
        df['ma100'] = df['close'].rolling(window=100).mean()
        df['ma200'] = df['close'].rolling(window=200).mean()

        # Price relative to MA
        df['pct_from_ma20'] = (df['close'] - df['ma20']) / df['ma20']
        df['pct_from_ma50'] = (df['close'] - df['ma50']) / df['ma50']
        df['pct_from_ma200'] = (df['close'] - df['ma200']) / df['ma200']

        # Bollinger Bands (20,2)
        std20 = df['close'].rolling(window=20).std(ddof=0)
        df['bb_upper'] = df['ma20'] + 2 * std20
        df['bb_lower'] = df['ma20'] - 2 * std20
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['ma20']
        df['bb_pos'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)

        # Consecutive bullish/bearish
        bull = (df['close'] > df['open']).astype(int)
        bear = (df['close'] < df['open']).astype(int)
        bull_groups = (bull != bull.shift()).cumsum()
        bear_groups = (bear != bear.shift()).cumsum()
        df['consecutive_bull'] = bull.groupby(bull_groups).cumsum()
        df['consecutive_bear'] = bear.groupby(bear_groups).cumsum()

        # Candle body / range features
        df['candle_range'] = (df['high'] - df['low']) / df['close']
        df['body_pct'] = abs(df['close'] - df['open']) / (df['high'] - df['low'] + 1e-10)
        df['upper_shadow'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['high'] - df['low'] + 1e-10)
        df['lower_shadow'] = (df[['open', 'close']].min(axis=1) - df['low']) / (df['high'] - df['low'] + 1e-10)

        # Engulfing patterns
        df['bullish_engulf'] = (df['close'] > df['open']) & (df['close'].shift(1) < df['open'].shift(1)) & \
                               (df['close'] > df['open'].shift(1)) & (df['open'] < df['close'].shift(1))
        df['bearish_engulf'] = (df['close'] < df['open']) & (df['close'].shift(1) > df['open'].shift(1)) & \
                               (df['close'] < df['open'].shift(1)) & (df['open'] > df['close'].shift(1))

        # Volume
        df['vol_ma20'] = df['tick_volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['tick_volume'] / df['vol_ma20'].replace(0, np.nan)

        df.dropna(inplace=True)
        result[sym] = df
        print(f"  {sym:12s} {len(df):>8} rows  {str(df.index[0]):22s} -> {str(df.index[-1]):22s}")
    return result

# ── Grid test runner ──────────────────────────────────────────────────────

H1_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48]
M30_HOLDS = [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60]

PERIODS_PER_YEAR = {"H1": 6000, "M30": 12000}

def run_grid_test(df, entry_condition, direction='long', hold_periods=None, timeframe='H1'):
    """Run a hypothesis test on a single DataFrame."""
    if hold_periods is None:
        hold_periods = H1_HOLDS if timeframe == 'H1' else M30_HOLDS

    dir_sign = 1.0 if direction == 'long' else -1.0
    close_arr = df['close'].values
    n_rows = len(df)
    ppy = PERIODS_PER_YEAR.get(timeframe, 6000)

    try:
        mask = df.eval(entry_condition).values.astype(bool)
    except Exception as e:
        print(f"  ERROR evaluating condition: {e}")
        return {hp: {"signal_count": 0, "avg_return": None, "win_rate": None,
                     "sharpe_ratio": None, "max_drawdown": None} for hp in hold_periods}

    signal_indices = np.where(mask)[0]
    n_signals = len(signal_indices)
    print(f"  Signals: {n_signals}")

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
        sharpe = avg_ret / std_ret * np.sqrt(ppy / hp) if std_ret > 0 and hp > 0 else 0.0

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
    """Pretty-print results table."""
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
        wr_str = f"{wr:>6.2%}"
        if best:
            wr_str = f"**{wr:>6.2%}**"
        print(f"| {hp:>2}  | {n:>4} | {r['avg_return'] or 0:>+8.4f} | {wr_str} | {r['sharpe_ratio'] or 0:>6.2f} | {r['max_drawdown'] or 0:>7.4f} |")

# ── Symbol definitions ────────────────────────────────────────────────────

ALL_SYMBOLS = ["XAUUSD", "XAGUSD", "USTEC", "US30", "US500", "JP225", "HK50",
               "USOIL", "UKOIL", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]
INDEX_SYMBOLS = ["USTEC", "US30", "US500", "JP225", "HK50"]
FX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]
METAL_SYMBOLS = ["XAUUSD", "XAGUSD"]
OIL_SYMBOLS = ["USOIL", "UKOIL"]

# ── TEST DEFINITIONS — Round 64: Asia & London Session Deep Dive ──

TESTS = [
    # ═══════════════════════════════════════════════════════════════════════
    # SECTION A: H1 Asia Session — Oversold Mean Reversion (Long)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_H1_A001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 30 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI<30+ATR>0.20%做多 — 全品种亚盘超卖均值回归(宽基版)"
    },
    {
        "id": "R64_H1_A002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI<25+ATR>0.25%做多 — 亚盘严格超卖"
    },
    {
        "id": "R64_H1_A003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 30 and close < bb_lower and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI<30+close<BBL+ATR>0.20%做多 — 亚盘BB增强超卖"
    },
    {
        "id": "R64_H1_A004",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 35 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+连跌3+RSI<35+ATR>0.20%做多 — 亚盘连续阴线衰竭"
    },
    {
        "id": "R64_H1_A005",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and close < ma50 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI<25+close<MA50+ATR>0.20%做多 — 亚盘趋势线支撑超卖"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION B: H1 Asia Session — Overbought (Short)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_H1_B001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 > 70 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI>70+ATR>0.20%做空 — 亚盘超买做空"
    },
    {
        "id": "R64_H1_B002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 > 75 and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI>75+ATR>0.25%做空 — 亚盘严重超买做空"
    },
    {
        "id": "R64_H1_B003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 > 70 and close > bb_upper and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI>70+close>BBU+ATR>0.20%做空 — 亚盘BB增强超买做空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION C: H1 London/Europe Session — Oversold (Long)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_H1_C001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI<30+ATR>0.20%做多 — 全品种欧盘超卖均值回归"
    },
    {
        "id": "R64_H1_C002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI<25+ATR>0.25%做多 — 欧盘严格超卖"
    },
    {
        "id": "R64_H1_C003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 30 and close < bb_lower and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI<30+close<BBL+ATR>0.20%做多 — 欧盘BB增强超卖"
    },
    {
        "id": "R64_H1_C004",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and consecutive_bear >= 3 and rsi14 < 35 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+连跌3+RSI<35+ATR>0.20%做多 — 欧盘连续阴线衰竭"
    },
    {
        "id": "R64_H1_C005",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and close < ma50 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI<25+close<MA50+ATR>0.20%做多 — 欧盘趋势线支撑超卖"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION D: H1 London/Europe Session — Overbought (Short)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_H1_D001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI>70+ATR>0.20%做空 — 欧盘超买做空"
    },
    {
        "id": "R64_H1_D002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 75 and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI>75+ATR>0.25%做空 — 欧盘严重超买做空"
    },
    {
        "id": "R64_H1_D003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and close > bb_upper and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI>70+close>BBU+ATR>0.20%做空 — 欧盘BB增强超买做空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION E: H1 Session Transition Windows
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_H1_E001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 7 and hour < 9 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚→欧转换(7-9UTC)+RSI<25+ATR>0.20%做多 — 伦敦开盘超卖"
    },
    {
        "id": "R64_H1_E002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 15 and hour < 17 and rsi14 > 70 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧→美转换(15-17UTC)+RSI>70+ATR>0.20%做空 — 美开盘超买做空"
    },
    {
        "id": "R64_H1_E003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 14 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 伦敦-NY重叠(12-14UTC)+RSI<25+ATR>0.20%做多 — 最大流动性超卖"
    },
    {
        "id": "R64_H1_E004",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 14 and rsi14 > 70 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 伦敦-NY重叠(12-14UTC)+RSI>70+ATR>0.20%做空 — 最大流动性超买做空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION F: H1 London Open / Asia Open Specific Hour Windows
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_H1_F001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 8 and hour < 10 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 伦敦开盘(8-10UTC)+RSI<25+ATR>0.20%做多 — 伦敦晨盘超卖"
    },
    {
        "id": "R64_H1_F002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 0 and hour < 3 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 东京开盘(0-3UTC)+RSI<25+ATR>0.20%做多 — 东京晨盘超卖"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION G: M30 Asia Session — Oversold (Long)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_M30_G001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<25+ATR>0.15%做多 — 亚盘超卖均值回归(M30宽基)"
    },
    {
        "id": "R64_M30_G002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<20+ATR>0.20%做多 — 亚盘极限超卖"
    },
    {
        "id": "R64_M30_G003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and close < bb_lower and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<25+close<BBL+ATR>0.15%做多 — 亚盘BB增强超卖"
    },
    {
        "id": "R64_M30_G004",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 30 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+连跌3+RSI<30+ATR>0.15%做多 — 亚盘阴线衰竭"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION H: M30 Asia Session — Overbought (Short)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_M30_H001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 > 70 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI>70+ATR>0.15%做空 — 亚盘超买做空"
    },
    {
        "id": "R64_M30_H002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 > 75 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI>75+ATR>0.20%做空 — 亚盘严重超买做空"
    },
    {
        "id": "R64_M30_H003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 > 70 and close > bb_upper and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI>70+close>BBU+ATR>0.15%做空 — 亚盘BB增强超买做空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION I: M30 London/Europe Session — Oversold (Long)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_M30_I001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI<25+ATR>0.15%做多 — 欧盘超卖均值回归"
    },
    {
        "id": "R64_M30_I002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 20 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI<20+ATR>0.20%做多 — 欧盘极限超卖"
    },
    {
        "id": "R64_M30_I003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and close < bb_lower and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI<25+close<BBL+ATR>0.15%做多 — 欧盘BB增强超卖"
    },
    {
        "id": "R64_M30_I004",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and consecutive_bear >= 3 and rsi14 < 30 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+连跌3+RSI<30+ATR>0.15%做多 — 欧盘阴线衰竭"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION J: M30 London/Europe Session — Overbought (Short)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_M30_J001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI>70+ATR>0.15%做空 — 欧盘超买做空"
    },
    {
        "id": "R64_M30_J002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 75 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI>75+ATR>0.20%做空 — 欧盘严重超买做空"
    },
    {
        "id": "R64_M30_J003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and close > bb_upper and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI>70+close>BBU+ATR>0.15%做空 — 欧盘BB增强超买做空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION K: M30 Session Transition Windows
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_M30_K001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 7 and hour < 9 and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚→欧转换(7-9UTC)+RSI<25+ATR>0.15%做多 — 伦敦开盘超卖"
    },
    {
        "id": "R64_M30_K002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 15 and hour < 17 and rsi14 > 70 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧→美转换(15-17UTC)+RSI>70+ATR>0.15%做空 — 美开盘超买做空"
    },
    {
        "id": "R64_M30_K003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 14 and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 伦敦-NY重叠(12-14UTC)+RSI<25+ATR>0.15%做多 — 最大流动性超卖"
    },
    {
        "id": "R64_M30_K004",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 14 and rsi14 > 70 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 伦敦-NY重叠(12-14UTC)+RSI>70+ATR>0.15%做空 — 最大流动性超买做空"
    },
    {
        "id": "R64_M30_K005",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 8 and hour < 10 and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 伦敦开盘(8-10UTC)+RSI<25+ATR>0.15%做多 — 伦敦晨盘超卖"
    },
    {
        "id": "R64_M30_K006",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 0 and hour < 3 and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 东京开盘(0-3UTC)+RSI<25+ATR>0.15%做多 — 东京晨盘超卖"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION L: H1 Candle Patterns in Asia/London Sessions
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R64_H1_L001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "bullish_engulf and rsi14 < 40 and session == 'asia' and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘看涨吞没+RSI<40+ATR>0.20%做多 — 亚盘反转吞没"
    },
    {
        "id": "R64_H1_L002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "bearish_engulf and rsi14 > 60 and session == 'asia' and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘看跌吞没+RSI>60+ATR>0.20%做空 — 亚盘反转吞没空"
    },
    {
        "id": "R64_H1_L003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "bullish_engulf and rsi14 < 40 and session == 'europe' and atr_pct > 0.0020",
        "description": "H1 欧盘看涨吞没+RSI<40+ATR>0.20%做多 — 欧盘反转吞没",
        "direction": "long",
        "hold_periods": H1_HOLDS,
    },
    {
        "id": "R64_H1_L004",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "bearish_engulf and rsi14 > 60 and session == 'europe' and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘看跌吞没+RSI>60+ATR>0.20%做空 — 欧盘反转吞没空"
    },
]

# ═══════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 90)
    print("  Round 64 — 欧盘/亚盘 Session 专注挖掘")
    print(f"  开始时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 90)

    all_results = {}

    # Group tests by timeframe so we load data once per timeframe
    tests_by_tf = {}
    for t in TESTS:
        tf = t["timeframe"]
        tests_by_tf.setdefault(tf, []).append(t)

    for tf, tf_tests in tests_by_tf.items():
        print(f"\n{'#'*90}")
        print(f"# 加载 {tf} 数据 ...")
        print(f"{'#'*90}")

        # Collect all unique symbols needed
        all_syms = set()
        for t in tf_tests:
            for s in t["symbols"]:
                all_syms.add(s)
        all_syms = sorted(all_syms)

        start = time.time()
        data = load_and_compute(tf, all_syms)
        load_time = time.time() - start
        print(f"\n  ✅ {tf} 数据加载完成 ({load_time:.1f}s) — {len(data)} 个品种")

        if not data:
            print(f"  ❌ 无 {tf} 数据可用，跳过")
            continue

        # Run each test
        for t in tf_tests:
            test_id = t["id"]
            print(f"\n{'─'*90}")
            print(f"  🧪 {test_id}: {t['description']}")
            print(f"  条件: {t['entry_condition']}")
            print(f"  方向: {t['direction']} | 持有期: {t['hold_periods']}")
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
                    timeframe=tf,
                )
                test_results[sym] = sym_res
                print_results_table(sym, sym_res, label=tf)

            all_results[test_id] = test_results
            test_elapsed = time.time() - test_start
            print(f"\n  ⏱ {test_id} 完成 ({test_elapsed:.1f}s)")

    # ── Save results ──
    LOGS_DIR.mkdir(exist_ok=True)
    results_path = LOGS_DIR / "round64_researcher_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n{'='*90}")
    print(f"  ✅ 所有测试完成！结果已保存至: {results_path}")
    print(f"  完成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*90}")

if __name__ == "__main__":
    main()
