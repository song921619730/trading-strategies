#!/usr/bin/env python3
"""
Round 63 — H1/M30 US Session & Candle Pattern Deep Dive
Focus: Building on Round 62's M5 US session successes extended to H1/M30,
plus new candle pattern and overbought pattern mining across all 14 symbols.

Key goals:
1. H1/M30 US session oversold patterns (extend M5 success to higher TF)
2. H1/M30 overbought short patterns (under-explored in Round 61)
3. H1/M30 candle patterns (engulfing, hammer, shooting star, doji)
4. Cross-symbol validation on all 14 forex/futures symbols
5. Session transition and specific hour windows

Target symbols (14): XAUUSD, XAGUSD, USTEC, US30, US500, JP225, HK50,
                    USOIL, UKOIL, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF
Timeframes: H1, M30
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

# ── TEST DEFINITIONS — Round 63: H1/M30 US Session & Candle Pattern Deep Dive ──

TESTS = [
    # ═══════════════════════════════════════════════════════════════════════
    # SECTION A: H1 US Session Oversold (extend M5 success → H1)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_H1_A001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 30 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘+RSI<30+ATR>0.25%做多 — 全品种美盘超卖均值回归(宽基版)"
    },
    {
        "id": "R63_H1_A002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0030",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘+RSI<25+ATR>0.30%做多 — 全品种美盘严格超卖"
    },
    {
        "id": "R63_H1_A003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0035",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘+RSI<20+ATR>0.35%做多 — 全品种美盘极限超卖"
    },
    {
        "id": "R63_H1_A004",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 30 and close < bb_lower and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘+RSI<30+close<BBL+ATR>0.25%做多 — BB增强超卖"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION B: H1 US Session Overbought Short (under-explored)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_H1_B001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 70 and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘+RSI>70+ATR>0.25%做空 — 全品种美盘超买均值回归"
    },
    {
        "id": "R63_H1_B002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 75 and atr_pct > 0.0030",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘+RSI>75+ATR>0.30%做空 — 全品种美盘严重超买做空"
    },
    {
        "id": "R63_H1_B003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 70 and close > bb_upper and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘+RSI>70+close>BBU+ATR>0.25%做空 — BB增强超买做空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION C: H1 Specific Hour Windows (session transitions)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_H1_C001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 13 and hour < 15 and rsi14 < 25 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘开盘(13-15UTC)+RSI<25+ATR>0.25%做多 — NY开盘超卖"
    },
    {
        "id": "R63_H1_C002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 13 and hour < 15 and rsi14 > 70 and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘开盘(13-15UTC)+RSI>70+ATR>0.25%做空 — NY开盘超买做空"
    },
    {
        "id": "R63_H1_C003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 7 and hour < 9 and rsi14 < 25 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘开盘(7-9UTC)+RSI<25+ATR>0.25%做多 — 伦敦开盘超卖"
    },
    {
        "id": "R63_H1_C004",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 20 and hour < 22 and rsi14 < 25 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘收盘(20-22UTC)+RSI<25+ATR>0.25%做多 — NY尾盘超卖"
    },
    {
        "id": "R63_H1_C005",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 0 and hour < 3 and rsi14 < 25 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘开盘(0-3UTC)+RSI<25+ATR>0.25%做多 — 东京开盘超卖"
    },
    {
        "id": "R63_H1_C006",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 16 and rsi14 > 70 and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 伦敦-NY重叠(12-16UTC)+RSI>70+ATR>0.25%做空 — 双盘重叠超买做空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION D: H1 Candle Patterns
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_H1_D001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "bullish_engulf and rsi14 < 40 and session == 'us' and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘看涨吞没+RSI<40+ATR>0.25%做多 — 美盘反转吞没"
    },
    {
        "id": "R63_H1_D002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "bearish_engulf and rsi14 > 60 and session == 'us' and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 美盘看跌吞没+RSI>60+ATR>0.25%做空 — 美盘反转吞没空"
    },
    {
        "id": "R63_H1_D003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "consecutive_bear >= 3 and body_pct < 0.3 and rsi14 < 30 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 连跌3+十字星(体<30%)+RSI<30+ATR>0.25%做多 — 衰竭十字星反转"
    },
    {
        "id": "R63_H1_D004",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "consecutive_bull >= 3 and body_pct < 0.3 and rsi14 > 70 and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 连涨3+十字星(体<30%)+RSI>70+ATR>0.25%做空 — 衰竭十字星反转空"
    },
    {
        "id": "R63_H1_D005",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "lower_shadow > 0.6 and body_pct < 0.5 and rsi14 < 30 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 长下影(>60%)+体<50%+RSI<30+ATR>0.25%做多 — 锤子线反转"
    },
    {
        "id": "R63_H1_D006",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "upper_shadow > 0.6 and body_pct < 0.5 and rsi14 > 70 and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 长上影(>60%)+体<50%+RSI>70+ATR>0.25%做空 — 射击之星反转空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION E: M30 US Session Oversold
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_M30_E001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+RSI<25+ATR>0.20%做多 — 全品种美盘超卖(宽基版)"
    },
    {
        "id": "R63_M30_E002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+RSI<20+ATR>0.25%做多 — 全品种美盘严格超卖"
    },
    {
        "id": "R63_M30_E003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 30 and close < bb_lower and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+RSI<30+close<BBL+ATR>0.20%做多 — BB增强超卖"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION F: M30 Overbought Short
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_M30_F001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 70 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+RSI>70+ATR>0.20%做空 — 全品种美盘超买均值回归"
    },
    {
        "id": "R63_M30_F002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 75 and atr_pct > 0.0025",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+RSI>75+ATR>0.25%做空 — 全品种美盘严重超买"
    },
    {
        "id": "R63_M30_F003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 70 and close > bb_upper and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+RSI>70+close>BBU+ATR>0.20%做空 — BB增强超买做空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION G: M30 Session Windows & Transitions
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_M30_G001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 13 and hour < 16 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘时段(13-16UTC)+RSI<25+ATR>0.20%做多 — NY下午超卖"
    },
    {
        "id": "R63_M30_G002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 19 and hour < 22 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘尾盘(19-22UTC)+RSI<25+ATR>0.20%做多 — NY收盘前超卖"
    },
    {
        "id": "R63_M30_G003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 7 and hour < 10 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘开盘(7-10UTC)+RSI<25+ATR>0.20%做多 — 伦敦晨盘超卖"
    },
    {
        "id": "R63_M30_G004",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 16 and rsi14 > 70 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 双盘重叠(12-16UTC)+RSI>70+ATR>0.20%做空 — 重叠窗口超买做空"
    },
    {
        "id": "R63_M30_G005",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 0 and hour < 7 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘(0-7UTC)+RSI<25+ATR>0.20%做多 — 全品种亚盘超卖"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION H: M30 Candle & Consecutive Patterns
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_M30_H001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "consecutive_bear >= 3 and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 连跌3+RSI<25+ATR>0.20%做多 — 连续阴线超卖衰竭"
    },
    {
        "id": "R63_M30_H002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "consecutive_bull >= 3 and rsi14 > 70 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 连涨3+RSI>70+ATR>0.20%做空 — 连续阳线超买衰竭"
    },
    {
        "id": "R63_M30_H003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "bullish_engulf and rsi14 < 35 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 看涨吞没+RSI<35+ATR>0.20%做多 — 全盘吞没反转多"
    },
    {
        "id": "R63_M30_H004",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "bearish_engulf and rsi14 > 65 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 看跌吞没+RSI>65+ATR>0.20%做空 — 全盘吞没反转空"
    },
    {
        "id": "R63_M30_H005",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "lower_shadow > 0.6 and body_pct < 0.4 and rsi14 < 30 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 长下影锤子线+RSI<30+ATR>0.20%做多 — 锤子线反转多"
    },
    {
        "id": "R63_M30_H006",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "upper_shadow > 0.6 and body_pct < 0.4 and rsi14 > 70 and atr_pct > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 长上影射击之星+RSI>70+ATR>0.20%做空 — 射击之星反转空"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION I: Cross-Symbol Deep Dive (session comparison)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R63_H1_I001",
        "timeframe": "H1",
        "symbols": METAL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI<25+ATR>0.25%做多 — 贵金属欧盘超卖验证"
    },
    {
        "id": "R63_H1_I002",
        "timeframe": "H1",
        "symbols": FX_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI>70+ATR>0.15%做空 — 外汇欧盘超买做空"
    },
    {
        "id": "R63_M30_I003",
        "timeframe": "M30",
        "symbols": INDEX_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+RSI<25+ATR>0.20%做多 — 指数美盘超卖集中验证"
    },
    {
        "id": "R63_M30_I004",
        "timeframe": "M30",
        "symbols": OIL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 30 and atr_pct > 0.0025",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+RSI<30+ATR>0.25%做多 — 原油美盘超卖验证"
    },
]

# ── Main execution ────────────────────────────────────────────────────────

def extract_top_findings(all_results):
    """Scan all results and return signals with WR>=60%, n>=30 sorted by WR."""
    findings = []
    for test_id, test_results in all_results.items():
        if not isinstance(test_results, dict):
            continue
        for sym, sym_res in test_results.items():
            if not isinstance(sym_res, dict):
                continue
            for hp, stats in sym_res.items():
                if not isinstance(stats, dict):
                    continue
                n = stats.get("signal_count", 0)
                wr = stats.get("win_rate")
                avg_ret = stats.get("avg_return")
                sharpe = stats.get("sharpe_ratio")
                if wr is not None and n >= 30 and wr >= 0.60:
                    findings.append({
                        "test_id": test_id,
                        "symbol": sym,
                        "hold_period": hp,
                        "signal_count": n,
                        "win_rate": wr,
                        "avg_return": avg_ret,
                        "sharpe_ratio": sharpe,
                    })
    findings.sort(key=lambda x: (x["win_rate"], x["signal_count"]), reverse=True)
    return findings

def main():
    print("=" * 80)
    print("  Round 63 — H1/M30 US Session & Candle Pattern Deep Dive")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Total tests: {len(TESTS)}")
    print(f"  Target: All 14 symbols on H1/M30")
    print("=" * 80)

    all_results = {}
    test_seq = 0

    for test in TESTS:
        test_seq += 1
        print(f"\n{'─' * 80}")
        print(f"\n[{test_seq:>2}/{len(TESTS)}] {test['id']}: {test['description']}")
        print(f"  Timeframe: {test['timeframe']}  Direction: {test['direction']}")
        print(f"  Condition: {test['entry_condition']}")
        print(f"  Symbols: {test['symbols']}")

        t0 = time.time()
        data = load_and_compute(test["timeframe"], test["symbols"])
        elapsed_load = time.time() - t0

        test_results = {}
        for sym, df in data.items():
            print(f"\n  --- Testing {sym} ---")
            results = run_grid_test(df, test["entry_condition"],
                                    test["direction"],
                                    test["hold_periods"],
                                    test["timeframe"])
            test_results[sym] = results
            print_results_table(sym, results, label=test["id"])

        all_results[test["id"]] = test_results
        print(f"\n  [{test['id']}] Completed in {time.time()-t0:.1f}s")

    # ── Save raw results ──
    LOGS_DIR.mkdir(exist_ok=True)
    out_path = LOGS_DIR / "round63_researcher_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n{'=' * 80}")
    print(f"Raw results saved to {out_path}")

    # ── Summary of top findings ──
    findings = extract_top_findings(all_results)
    print(f"\n{'=' * 80}")
    print(f"  TOP FINDINGS (WR >= 60%, n >= 30)")
    print(f"  Total: {len(findings)} signals")
    print(f"{'=' * 80}")

    if findings:
        from collections import defaultdict
        by_test = defaultdict(list)
        for f in findings:
            by_test[f["test_id"]].append(f)

        for test_id, sigs in sorted(by_test.items()):
            print(f"\n  [{test_id}]")
            for s in sigs[:5]:
                wr_pct = s["win_rate"] * 100
                avg_ret_pct = (s["avg_return"] or 0) * 100
                sharpe = s["sharpe_ratio"] or 0
                print(f"    {s['symbol']:10s} hold={s['hold_period']:>2}  "
                      f"n={s['signal_count']:>4}  WR={wr_pct:>5.1f}%  "
                      f"avg_ret={avg_ret_pct:>+6.2f}%  Sharpe={sharpe:>5.2f}")

        # Top 20 overall
        print(f"\n  {'─' * 70}")
        print(f"  TOP 20 SIGNALS OVERALL")
        print(f"  {'─' * 70}")
        for i, s in enumerate(findings[:20]):
            wr_pct = s["win_rate"] * 100
            avg_ret_pct = (s["avg_return"] or 0) * 100
            sharpe = s["sharpe_ratio"] or 0
            print(f"  #{i+1:>2}. {s['symbol']:10s} | {s['test_id']:35s} | "
                  f"hold={s['hold_period']:>2} | n={s['signal_count']:>4} | "
                  f"WR={wr_pct:>5.1f}% | avg={avg_ret_pct:>+5.2f}% | "
                  f"Sharpe={sharpe:>4.2f}")

        # Injectable signals (n >= 150)
        injectable = [s for s in findings if s["signal_count"] >= 150]
        if injectable:
            print(f"\n\n  ★ INJECTABLE SIGNALS (n >= 150):")
            print(f"  {'─' * 70}")
            for i, s in enumerate(injectable[:15]):
                wr_pct = s["win_rate"] * 100
                avg_ret_pct = (s["avg_return"] or 0) * 100
                sharpe = s["sharpe_ratio"] or 0
                status = "⭐ INJECT" if wr_pct >= 65 else "▸ WATCH"
                print(f"  #{i+1:>2}. {status} | {s['symbol']:10s} | {s['test_id']:35s} | "
                      f"hold={s['hold_period']:>2} | n={s['signal_count']:>4} | WR={wr_pct:>5.1f}% | "
                      f"avg={avg_ret_pct:>+5.2f}% | Sharpe={sharpe:>4.2f}")

        # Strong signals (WR >= 70%, n >= 50)
        strong = [s for s in findings if s["win_rate"] >= 0.70 and s["signal_count"] >= 50]
        if strong:
            print(f"\n\n  ★ STRONG SIGNALS (WR >= 70%, n >= 50):")
            print(f"  {'─' * 70}")
            for i, s in enumerate(strong[:15]):
                wr_pct = s["win_rate"] * 100
                avg_ret_pct = (s["avg_return"] or 0) * 100
                print(f"  #{i+1:>2}. {s['symbol']:10s} | {s['test_id']:35s} | "
                      f"hold={s['hold_period']:>2} | n={s['signal_count']:>4} | WR={wr_pct:>5.1f}% | "
                      f"avg={avg_ret_pct:>+5.2f}%")

        # Candidates for injection
        inject_candidates = [s for s in findings if s["win_rate"] >= 0.65 and s["signal_count"] >= 150]
        if inject_candidates:
            print(f"\n\n  ★★ CANDIDATES FOR IMMEDIATE INJECTION (WR>=65%, n>=150):")
            print(f"  {'─' * 70}")
            for i, s in enumerate(inject_candidates[:10]):
                wr_pct = s["win_rate"] * 100
                print(f"  #{i+1:>2}. {s['symbol']:10s} | {s['test_id']:35s} | "
                      f"hold={s['hold_period']:>2} | n={s['signal_count']:>4} | WR={wr_pct:>5.1f}%")

    else:
        print("\n  No findings meeting WR>=60% and n>=30 criteria.")

    print(f"\n{'=' * 80}")
    print(f"  Round 63 completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    main()
