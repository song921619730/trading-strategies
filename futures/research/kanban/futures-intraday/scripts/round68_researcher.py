#!/usr/bin/env python3
"""
Round 68 — H1/M30 K线形态研究与统计发现

基于各轮发现的整合与扩展：
- R60/R67: M1/M5超卖信号 (已确认)
- R66: H1/M30初始发现方案

本轮重点: K线组合形态的统计预测能力 + 跨TF验证

品种 (13): XAUUSD, XAGUSD, USTEC, US30, US500, JP225, HK50,
            USOIL, UKOIL, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF
时间框架: H1, M30
"""
import json, sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"
STATE_DIR = PROJECT_DIR / "state"

# ── Indicator helpers ──────────────────────────────────────────────

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

# ── Candlestick Pattern Detection ─────────────────────────────────

def detect_candle_patterns(df):
    """Detect candlestick patterns and add columns to dataframe."""
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = np.abs(c - o)
    total_range = h - l
    body_pct = np.divide(body, total_range, out=np.zeros_like(body), where=total_range>0)
    upper_shadow = h - np.maximum(o, c)
    lower_shadow = np.minimum(o, c) - l
    
    # ── Single candle patterns ──
    # Doji: body < 5% of range
    df['doji'] = (body_pct < 0.05).astype(int)
    
    # Hammer: small body, long lower shadow (>2x body), upper shadow < body
    hammer = (lower_shadow > 2 * body) & (upper_shadow < body) & (body_pct < 0.3) & (body_pct > 0.01)
    df['hammer'] = hammer.astype(int)
    
    # Shooting Star: small body, long upper shadow (>2x body), lower shadow < body
    star = (upper_shadow > 2 * body) & (lower_shadow < body) & (body_pct < 0.3) & (body_pct > 0.01)
    df['shooting_star'] = star.astype(int)
    
    # Marubozu: very long body, tiny/no shadows
    marubozu = (body_pct > 0.95) & (upper_shadow < 0.01 * (h - l)) & (lower_shadow < 0.01 * (h - l))
    df['marubozu_bull'] = (marubozu & (c > o)).astype(int)
    df['marubozu_bear'] = (marubozu & (c < o)).astype(int)
    
    # Long body candles (> 70% of range)
    df['long_body_bull'] = ((body_pct > 0.7) & (c > o)).astype(int)
    df['long_body_bear'] = ((body_pct > 0.7) & (c < o)).astype(int)
    
    # Spinning Top: small body (<20%), relatively balanced shadows
    spin_top = (body_pct < 0.2) & (upper_shadow > 0.3 * total_range) & (lower_shadow > 0.3 * total_range)
    df['spinning_top'] = spin_top.astype(int)
    
    # ── Two-candle patterns (shift-based) ──
    prev_body = np.roll(body, 1)
    prev_o, prev_c = np.roll(o, 1), np.roll(c, 1)
    prev_h, prev_l = np.roll(h, 1), np.roll(l, 1)
    prev_upper = np.roll(upper_shadow, 1)
    prev_lower = np.roll(lower_shadow, 1)
    prev_body_pct = np.roll(body_pct, 1)
    
    # Bullish Engulfing: current bull body engulfs prev bear body
    engulf_bull = (c > o) & (prev_c < prev_o) & (c >= prev_h) & (o <= prev_l)
    df['engulfing_bull'] = engulf_bull.astype(int)
    
    # Bearish Engulfing: current bear body engulfs prev bull body
    engulf_bear = (c < o) & (prev_c > prev_o) & (h >= prev_h) & (l <= prev_l)
    df['engulfing_bear'] = engulf_bear.astype(int)
    
    # Harami Bull: prev bear, current bull, current body inside prev body
    harami_bull = (c > o) & (prev_c < prev_o) & (o >= prev_o) & (c <= prev_c) & (body_pct < 0.5)
    df['harami_bull'] = harami_bull.astype(int)
    
    # Harami Bear: prev bull, current bear, current body inside prev body
    harami_bear = (c < o) & (prev_c > prev_o) & (o <= prev_c) & (c >= prev_o) & (body_pct < 0.5)
    df['harami_bear'] = harami_bear.astype(int)
    
    # Piercing Line: prev bear, current bull opens below prev low, closes > 50% of prev body
    piercing = (c > o) & (prev_c < prev_o) & (o < prev_l) & (c > (prev_o + prev_c) / 2)
    df['piercing_line'] = piercing.astype(int)
    
    # Dark Cloud Cover: prev bull, current bear opens above prev high, closes < 50% of prev body
    dcc = (c < o) & (prev_c > prev_o) & (o > prev_h) & (c < (prev_o + prev_c) / 2)
    df['dark_cloud'] = dcc.astype(int)
    
    # ── Three-candle patterns ──
    prev2_body = np.roll(body, 2)
    prev2_o, prev2_c = np.roll(o, 2), np.roll(c, 2)
    prev2_h, prev2_l = np.roll(h, 2), np.roll(l, 2)
    
    # Morning Star: long bear, small body (doji/star), long bull
    ms = (prev2_c < prev2_o) & (prev2_body > 0.7 * (prev2_h - prev2_l)) & \
         (body_pct < 0.1) & (c > o) & (c > (prev2_o + prev2_c) / 2)
    df['morning_star'] = ms.astype(int)
    
    # Evening Star: long bull, small body (doji/star), long bear
    es = (prev2_c > prev2_o) & (prev2_body > 0.7 * (prev2_h - prev2_l)) & \
         (body_pct < 0.1) & (c < o) & (c < (prev2_o + prev2_c) / 2)
    df['evening_star'] = es.astype(int)
    
    # Three White Soldiers: 3 consecutive long bull candles, each close higher
    tws = (prev2_c > prev2_o) & (prev_c > prev_o) & (c > o) & \
          (prev2_body > 0.5 * (prev2_h - prev2_l)) & \
          (body > 0.5 * total_range) & (c > prev_c) & (prev_c > prev2_c)
    df['three_soldiers'] = tws.astype(int)
    
    # Three Black Crows: 3 consecutive long bear candles, each close lower
    tbc = (prev2_c < prev2_o) & (prev_c < prev_o) & (c < o) & \
          (prev2_body > 0.5 * (prev2_h - prev2_l)) & \
          (body > 0.5 * total_range) & (c < prev_c) & (prev_c < prev2_c)
    df['three_crows'] = tbc.astype(int)
    
    # ── Composite pattern strength ──
    # Strong reversal: engulfing + long body + RSI divergence hint
    df['strong_bull_reversal'] = (
        (df['engulfing_bull'] == 1) | (df['piercing_line'] == 1) | (df['morning_star'] == 1)
    ).astype(int)
    df['strong_bear_reversal'] = (
        (df['engulfing_bear'] == 1) | (df['dark_cloud'] == 1) | (df['evening_star'] == 1)
    ).astype(int)
    
    return df


def load_and_compute(timeframe, symbols):
    """Load parquet data and compute all indicators + candle patterns."""
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
        
        # Volume
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
        body = abs(df['close'] - df['open'])
        candle_hi = df['high'] - df['low']
        df['body_pct'] = (body / candle_hi.replace(0, np.nan)).fillna(0)
        df['upper_shadow_ratio'] = (df['high'] - df[['open','close']].max(axis=1)) / df['close']
        df['lower_shadow_ratio'] = (df[['open','close']].min(axis=1) - df['low']) / df['close']
        
        # Volume spike
        df['vol_ma20'] = df['tick_volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['tick_volume'] / df['vol_ma20'].replace(0, np.nan)
        
        # ── Candlestick Pattern Detection ──
        df = detect_candle_patterns(df)
        
        # Drop NaN rows from indicator computation
        df.dropna(inplace=True)
        result[sym] = df
        print(f"  {sym:12s} {len(df):>8} rows  {str(df.index[0])[:22]} -> {str(df.index[-1])[:22]}  | patterns: {sum(1 for c in df.columns if any(p in c for p in ['doji','hammer','star','engulf','harami','piercing','morning','evening','soldier','crow','marubozu','spinning','strong_bull','strong_bear']))}")
    return result


# ── Grid test runner ───────────────────────────────────────────────

def run_grid_test(df, entry_condition, direction='long', hold_periods=None):
    if hold_periods is None:
        hold_periods = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 36, 48]
    
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
    
    # Auto-select periods_per_year based on timeframe
    if len(df) > 1:
        time_diff_sec = (df.index[-1] - df.index[0]).total_seconds() / len(df)
        if time_diff_sec < 90:
            periods_per_year = 360_000
        elif time_diff_sec < 300:
            periods_per_year = 100_000
        elif time_diff_sec < 900:
            periods_per_year = 35_000
        elif time_diff_sec < 1800:
            periods_per_year = 17_500  # M30
        elif time_diff_sec < 3600:
            periods_per_year = 8_760   # H1
        elif time_diff_sec < 14400:
            periods_per_year = 2_190   # H4
        else:
            periods_per_year = 365     # D1
    else:
        periods_per_year = 8_760
    
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
# For H1: holds = hours
H1_HOLDS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 36, 48, 60, 72]
# For M30: holds = 30-min candles
M30_HOLDS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 36, 48, 60, 72, 96]

# Extended holds for longer swings
H1_HOLDS_LONG = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 36, 48, 60, 72, 96, 120]
M30_HOLDS_LONG = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 36, 48, 60, 72, 96, 120, 144, 192]

# Target symbols (13 forex/commodities, no A-stock)
TARGET_SYMBOLS = [
    "XAUUSD", "XAGUSD", "USTEC", "US30", "US500", "JP225", "HK50",
    "USOIL", "UKOIL", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"
]

# ═══════════════════════════════════════════════════════════════════
# TEST DEFINITIONS — Round 68: H1/M30 K线形态研究
# ═══════════════════════════════════════════════════════════════════

TESTS = [

    # ═══════════════════════════════════════════════════════════════
    # SECTION A: H1 K线形态 — 单K与组合K线预测能力
    # ═══════════════════════════════════════════════════════════════

    # A001: Bullish Engulfing — classic reversal pattern
    {
        "id": "R68_H1_A001",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bull == 1",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 看涨吞没 — 经典反转形态，统计各品种预测能力"
    },
    # A002: Bearish Engulfing
    {
        "id": "R68_H1_A002",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bear == 1",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 看跌吞没 — 经典反转形态，统计各品种预测能力"
    },

    # A003: Hammer (in downtrend context — after 2+ bear candles)
    {
        "id": "R68_H1_A003",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "hammer == 1 and consecutive_bear >= 2",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 锤子线(连跌后) — 底部反转形态"
    },
    # A004: Shooting Star (in uptrend context)
    {
        "id": "R68_H1_A004",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "shooting_star == 1 and consecutive_bull >= 2",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 射击之星(连涨后) — 顶部反转形态"
    },

    # A005: Morning Star
    {
        "id": "R68_H1_A005",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "morning_star == 1",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 晨星 — 经典三重反转形态"
    },
    # A006: Evening Star
    {
        "id": "R68_H1_A006",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "evening_star == 1",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 黄昏星 — 经典三重反转形态"
    },

    # A007: Piercing Line
    {
        "id": "R68_H1_A007",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "piercing_line == 1",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 刺透形态 — 看涨反转"
    },
    # A008: Dark Cloud Cover
    {
        "id": "R68_H1_A008",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "dark_cloud == 1",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 乌云盖顶 — 看跌反转"
    },

    # A009: Bullish Harami
    {
        "id": "R68_H1_A009",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "harami_bull == 1",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 看涨孕线 — 温和反转形态"
    },
    # A010: Bearish Harami
    {
        "id": "R68_H1_A010",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "harami_bear == 1",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 看跌孕线 — 温和反转形态"
    },

    # A011: Three White Soldiers
    {
        "id": "R68_H1_A011",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "three_soldiers == 1",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 三白兵 — 强势看涨延续"
    },
    # A012: Three Black Crows
    {
        "id": "R68_H1_A012",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "three_crows == 1",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 三黑鸦 — 强势看跌延续"
    },

    # A013: Doji (after trend) — indecision/reversal
    {
        "id": "R68_H1_A013",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "doji == 1 and consecutive_bear >= 2",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 十字星(连跌后) — 潜在底部反转"
    },
    {
        "id": "R68_H1_A014",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "doji == 1 and consecutive_bull >= 2",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 十字星(连涨后) — 潜在顶部反转"
    },

    # A015: Spinning Top (after trend)
    {
        "id": "R68_H1_A015",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "spinning_top == 1 and consecutive_bear >= 2",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 纺锤线(连跌后) — 犹豫反转信号"
    },
    {
        "id": "R68_H1_A016",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "spinning_top == 1 and consecutive_bull >= 2",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 纺锤线(连涨后) — 犹豫反转信号"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION B: H1 K线形态 + RSI/ATR 增强版
    # ═══════════════════════════════════════════════════════════════

    # B001: Engulfing Bull + oversold RSI
    {
        "id": "R68_H1_B001",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bull == 1 and rsi14 < 30",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 看涨吞没+RSI<30 — 超卖区域吞没增强"
    },
    # B002: Engulfing Bear + overbought RSI
    {
        "id": "R68_H1_B002",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bear == 1 and rsi14 > 70",
        "direction": "short",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 看跌吞没+RSI>70 — 超买区域吞没增强"
    },

    # B003: Hammer + RSI < 30 (oversold hammer)
    {
        "id": "R68_H1_B003",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "hammer == 1 and rsi14 < 30",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 锤子线+RSI<30 — 超卖底部反转增强"
    },
    # B004: Shooting Star + RSI > 70
    {
        "id": "R68_H1_B004",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "shooting_star == 1 and rsi14 > 70",
        "direction": "short",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 射击之星+RSI>70 — 超买顶部反转增强"
    },

    # B005: Strong Bull Reversal (engulfing/piercing/morning star) + RSI<30
    {
        "id": "R68_H1_B005",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "strong_bull_reversal == 1 and rsi14 < 30",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 强看涨反转形态+RSI<30 — 综合反转信号增强"
    },
    # B006: Strong Bear Reversal + RSI>70
    {
        "id": "R68_H1_B006",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "strong_bear_reversal == 1 and rsi14 > 70",
        "direction": "short",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 强看跌反转形态+RSI>70 — 综合反转信号增强"
    },

    # B007: Marubozu Bull (continuation signal)
    {
        "id": "R68_H1_B007",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "marubozu_bull == 1",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 光头光脚大阳线 — 强势延续信号"
    },
    # B008: Marubozu Bear
    {
        "id": "R68_H1_B008",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "marubozu_bear == 1",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 光头光脚大阴线 — 强势延续信号"
    },

    # B009: Long Body Bull + volume spike
    {
        "id": "R68_H1_B009",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "long_body_bull == 1 and vol_ratio > 1.5",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 大阳线+放量>1.5倍 — 量价齐升延续"
    },
    # B010: Long Body Bear + volume spike
    {
        "id": "R68_H1_B010",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "long_body_bear == 1 and vol_ratio > 1.5",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 大阴线+放量>1.5倍 — 量价齐跌延续"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION C: H1 Session + K线形态 + 超卖/超买 (从R66扩展)
    # ═══════════════════════════════════════════════════════════════

    # C001: US session + strong bull reversal
    {
        "id": "R68_H1_C001",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and strong_bull_reversal == 1 and rsi14 < 30",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 美盘+强看涨反转+RSI<30 — 美盘超卖反转"
    },
    # C002: Asia session + strong bull reversal
    {
        "id": "R68_H1_C002",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'asia' and strong_bull_reversal == 1 and rsi14 < 30",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 亚盘+强看涨反转+RSI<30 — 亚盘超卖反转"
    },
    # C003: Europe session + strong bear reversal
    {
        "id": "R68_H1_C003",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'europe' and strong_bear_reversal == 1 and rsi14 > 70",
        "direction": "short",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 欧盘+强看跌反转+RSI>70 — 欧盘超买反转"
    },

    # C004: Consecutive bear 3+ and doji/hammer (exhaustion)
    {
        "id": "R68_H1_C004",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "consecutive_bear >= 3 and (doji == 1 or hammer == 1 or spinning_top == 1)",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 连跌3+且出现十字/锤子/纺锤 — 趋势衰竭反转"
    },
    # C005: Consecutive bull 3+ and doji/shooting star/spinning top
    {
        "id": "R68_H1_C005",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "consecutive_bull >= 3 and (doji == 1 or shooting_star == 1 or spinning_top == 1)",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 连涨3+且出现十字/射击/纺锤 — 趋势衰竭反转"
    },

    # C006: H1 R66复现 — 美盘+RSI<25+ATR>0.10%做多 (从M5上移到H1)
    {
        "id": "R68_H1_C006",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 美盘+RSI<25+ATR>0.10%做多 — R66超卖信号上移H1"
    },
    # C007: H1 亚盘+连跌3+RSI<30+BBL (R66 JP225信号扩展)
    {
        "id": "R68_H1_C007",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 30 and close < bb_lower",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 亚盘+连跌3+RSI<30+BBL — R66 JP225信号多品种扩展"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION D: M30 K线形态 — 单K与组合K线预测能力
    # ═══════════════════════════════════════════════════════════════

    # D001: M30 Bullish Engulfing
    {
        "id": "R68_M30_D001",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bull == 1",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 看涨吞没 — 经典反转形态 M30版"
    },
    # D002: M30 Bearish Engulfing
    {
        "id": "R68_M30_D002",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bear == 1",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 看跌吞没 — 经典反转形态 M30版"
    },

    # D003: M30 Hammer (after downtrend)
    {
        "id": "R68_M30_D003",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "hammer == 1 and consecutive_bear >= 2",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 锤子线(连跌后) — 底部反转 M30版"
    },
    # D004: M30 Shooting Star (after uptrend)
    {
        "id": "R68_M30_D004",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "shooting_star == 1 and consecutive_bull >= 2",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 射击之星(连涨后) — 顶部反转 M30版"
    },

    # D005: M30 Morning Star
    {
        "id": "R68_M30_D005",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "morning_star == 1",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 晨星 — 三重反转 M30版"
    },
    # D006: M30 Evening Star
    {
        "id": "R68_M30_D006",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "evening_star == 1",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 黄昏星 — 三重反转 M30版"
    },

    # D007: M30 Piercing Line
    {
        "id": "R68_M30_D007",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "piercing_line == 1",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 刺透形态 — 看涨反转 M30版"
    },
    # D008: M30 Dark Cloud Cover
    {
        "id": "R68_M30_D008",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "dark_cloud == 1",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 乌云盖顶 — 看跌反转 M30版"
    },

    # D009: M30 Three Soldiers
    {
        "id": "R68_M30_D009",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "three_soldiers == 1",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 三白兵 — 强势看涨延续 M30版"
    },
    # D010: M30 Three Crows
    {
        "id": "R68_M30_D010",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "three_crows == 1",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 三黑鸦 — 强势看跌延续 M30版"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION E: M30 K线形态 + RSI/ATR 增强版
    # ═══════════════════════════════════════════════════════════════

    # E001: M30 Engulfing + RSI<30
    {
        "id": "R68_M30_E001",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bull == 1 and rsi14 < 30",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 看涨吞没+RSI<30 — 超卖吞没增强 M30版"
    },
    # E002: M30 Engulfing Bear + RSI>70
    {
        "id": "R68_M30_E002",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bear == 1 and rsi14 > 70",
        "direction": "short",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 看跌吞没+RSI>70 — 超买吞没增强 M30版"
    },

    # E003: M30 Strong Bull Reversal + RSI<30
    {
        "id": "R68_M30_E003",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "strong_bull_reversal == 1 and rsi14 < 30",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 强看涨反转+RSI<30 — 综合反转增强 M30版"
    },
    # E004: M30 Strong Bear Reversal + RSI>70
    {
        "id": "R68_M30_E004",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "strong_bear_reversal == 1 and rsi14 > 70",
        "direction": "short",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 强看跌反转+RSI>70 — 综合反转增强 M30版"
    },

    # E005: M30 Marubozu continuation
    {
        "id": "R68_M30_E005",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "marubozu_bull == 1",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 光头光脚大阳线 — 强势延续 M30版"
    },
    # E006: M30 Marubozu Bear
    {
        "id": "R68_M30_E006",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "marubozu_bear == 1",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 光头光脚大阴线 — 强势延续 M30版"
    },

    # E007: M30 Doji after bear streak
    {
        "id": "R68_M30_E007",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "doji == 1 and consecutive_bear >= 2",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 十字星(连跌后) — 底部反转 M30版"
    },
    # E008: M30 Doji after bull streak
    {
        "id": "R68_M30_E008",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "doji == 1 and consecutive_bull >= 2",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 十字星(连涨后) — 顶部反转 M30版"
    },

    # E009: M30 Consecutive 3+ bear + doji/hammer/spinning (exhaustion)
    {
        "id": "R68_M30_E009",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "consecutive_bear >= 3 and (doji == 1 or hammer == 1 or spinning_top == 1)",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 连跌3+且出现衰竭形态 — 趋势衰竭反转 M30版"
    },
    # E010: M30 Consecutive 3+ bull + doji/shooting/star/spinning
    {
        "id": "R68_M30_E010",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "consecutive_bull >= 3 and (doji == 1 or shooting_star == 1 or spinning_top == 1)",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 连涨3+且出现衰竭形态 — 趋势衰竭反转 M30版"
    },

    # E011: M30 Long body + volume spike
    {
        "id": "R68_M30_E011",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "long_body_bull == 1 and vol_ratio > 1.5",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 大阳线+放量>1.5倍 — 量价齐升延续 M30版"
    },
    # E012: M30 Long body bear + volume spike
    {
        "id": "R68_M30_E012",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "long_body_bear == 1 and vol_ratio > 1.5",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 大阴线+放量>1.5倍 — 量价齐跌延续 M30版"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION F: M30 Session + 形态 (同C节从H1映射)
    # ═══════════════════════════════════════════════════════════════

    # F001: M30 US Session oversold (R66信号下移M30)
    {
        "id": "R68_M30_F001",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 美盘+RSI<25+ATR>0.10%做多 — R66超卖下移M30"
    },
    # F002: M30 Asia + 连跌3+RSI<30+BBL (R66 JP225信号下移M30)
    {
        "id": "R68_M30_F002",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 30 and close < bb_lower",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 亚盘+连跌3+RSI<30+BBL — R66 JP225下移M30"
    },

    # F003: M30 US session + hammer + RSI<30
    {
        "id": "R68_M30_F003",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and hammer == 1 and consecutive_bear >= 2 and rsi14 < 30",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+锤子线(回调中)+RSI<30 — 美盘超卖锤子反转"
    },
    # F004: M30 Europe + shooting star + RSI>70
    {
        "id": "R68_M30_F004",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'europe' and shooting_star == 1 and consecutive_bull >= 2 and rsi14 > 70",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+射击之星(上涨中)+RSI>70 — 欧盘超买射击反转"
    },

    # F005: M30 US session + engulfing bull + RSI<25
    {
        "id": "R68_M30_F005",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and engulfing_bull == 1 and rsi14 < 25",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 美盘+看涨吞没+RSI<25 — 美盘吞没超卖反转"
    },

    # ═══════════════════════════════════════════════════════════════
    # SECTION G: 跨品种/跨TF对比 — 最强形态赢家
    # ═══════════════════════════════════════════════════════════════

    # G001: Bullish Engulfing + BB lower band (oversold bollinger)
    {
        "id": "R68_H1_G001",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bull == 1 and close < bb_lower",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 看涨吞没+close<BBL — 布林下轨吞没反转"
    },
    # G002: Bearish Engulfing + BB upper band
    {
        "id": "R68_H1_G002",
        "timeframe": "H1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bear == 1 and close > bb_upper",
        "direction": "short",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 看跌吞没+close>BBU — 布林上轨吞没反转"
    },

    # G003: H1 Engulfing + RSI divergence (RSI<30 for bull, >70 for bear) + ATR filter
    {
        "id": "R68_H1_G003",
        "timeframe": "H1",
        "symbols": ["XAUUSD", "XAGUSD", "USTEC", "US30", "JP225", "EURUSD", "GBPUSD"],
        "entry_condition": "engulfing_bull == 1 and rsi14 < 30 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 主要品种 看涨吞没+RSI<30+ATR>0.15% — 强条件高胜率测试"
    },
    # G004: H1 Engulfing bear + RSI>70 + ATR filter
    {
        "id": "R68_H1_G004",
        "timeframe": "H1",
        "symbols": ["XAUUSD", "XAGUSD", "USTEC", "US30", "JP225", "EURUSD", "GBPUSD"],
        "entry_condition": "engulfing_bear == 1 and rsi14 > 70 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": H1_HOLDS_LONG,
        "description": "H1 主要品种 看跌吞没+RSI>70+ATR>0.15% — 强条件高胜率测试"
    },

    # G005: M30 Engulfing + BBL (oversold)
    {
        "id": "R68_M30_G005",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bull == 1 and close < bb_lower",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 看涨吞没+close<BBL — 布林下轨吞没反转 M30版"
    },
    # G006: M30 Engulfing + BBU (overbought)
    {
        "id": "R68_M30_G006",
        "timeframe": "M30",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "engulfing_bear == 1 and close > bb_upper",
        "direction": "short",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 看跌吞没+close>BBU — 布林上轨吞没反转 M30版"
    },
]

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  ROUND 68 — H1/M30 K线形态研究")
    print("=" * 80)
    print(f"  执行时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  品种: {len(TARGET_SYMBOLS)}个")
    print(f"  测试数: {len(TESTS)}个")
    print(f"  时间框架: H1, M30")
    print()
    
    # Group tests by timeframe
    tests_by_tf = {}
    for t in TESTS:
        tf = t["timeframe"]
        if tf not in tests_by_tf:
            tests_by_tf[tf] = []
        tests_by_tf[tf].append(t)
    
    all_results = {}
    
    for tf, tf_tests in sorted(tests_by_tf.items()):
        print(f"\n{'─' * 70}")
        print(f"  加载 {tf} 数据...")
        print()
        
        # Collect unique symbols needed for this timeframe
        tf_symbols = set()
        for t in tf_tests:
            for sym in t["symbols"]:
                tf_symbols.add(sym)
        tf_symbols = sorted(tf_symbols)
        
        data = load_and_compute(tf, tf_symbols)
        
        if not data:
            print(f"  ❌ 没有 {tf} 数据可用，跳过")
            continue
        
        for test in tf_tests:
            tid = test["id"]
            desc = test["description"]
            syms = test["symbols"]
            direction = test["direction"]
            condition = test["entry_condition"]
            holds = test["hold_periods"]
            
            print(f"\n{'─' * 70}")
            print(f"  [{tid}] {desc}")
            print(f"  条件: {condition}")
            print(f"  方向: {direction}")
            print(f"  品种: {len(syms)}个")
            
            all_results[tid] = {}
            
            for sym in syms:
                if sym not in data:
                    continue
                
                df = data[sym]
                results = run_grid_test(df, condition, direction, holds)
                all_results[tid][sym] = results
                
                # Print best result for this symbol
                best_hp = None
                best_wr = 0
                best_n = 0
                for hp, r in results.items():
                    n = r["signal_count"]
                    wr = r["win_rate"] or 0
                    if n >= 30 and wr >= best_wr:
                        best_wr = wr
                        best_hp = hp
                        best_n = n
                
                if best_hp is not None and best_wr >= 0.60:
                    r = results[best_hp]
                    print(f"  ✓ {sym:12s} hold={best_hp:>3} n={best_n:>4} WR={best_wr:.2%} avg_ret={r['avg_return'] or 0:+.4f} Sharpe={r['sharpe_ratio'] or 0:.2f}")
                elif best_hp is not None and best_wr >= 0.50:
                    r = results[best_hp]
                    print(f"  ~ {sym:12s} hold={best_hp:>3} n={best_n:>4} WR={best_wr:.2%} (low)")
    
    # Save results
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    results_path = LOGS_DIR / "round68_researcher_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n{'=' * 70}")
    print(f"  ✅ 结果保存到: {results_path}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
