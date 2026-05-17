#!/usr/bin/env python3
"""
Round 62 — M1/M5 Scalping Deep Dive Researcher
Focus: Building on Round 60's M1/M5 discoveries with deeper pattern mining.

Key goals:
1. Expand sample counts for Round 60's strongest signals via ATR reduction
2. Test new M5 pattern categories (session transitions, MA alignment, hour windows)
3. M1 ultra-short momentum and reversal patterns
4. Cross-symbol pattern consistency testing

Target symbols: XAUUSD, XAGUSD, JP225, US500, US30
Timeframes: M1, M5
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

# ─────────────────────────────────────────────────────────────────────────────
# Indicator helpers (fast, local, no heavy deps)
# ─────────────────────────────────────────────────────────────────────────────

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
        df['minute'] = df.index.minute
        df['session'] = df['hour'].apply(session_label)
        df['dayofweek'] = df.index.dayofweek

        # RSI (multiple periods)
        df['rsi14'] = calc_rsi(df['close'])
        df['rsi7'] = calc_rsi(df['close'], period=7)
        df['rsi5'] = calc_rsi(df['close'], period=5)

        # ATR
        df['atr14'] = calc_atr(df)
        df['atr_pct'] = df['atr14'] / df['close']

        # Moving Averages
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()
        df['ma100'] = df['close'].rolling(window=100).mean()
        df['ma200'] = df['close'].rolling(window=200).mean()

        # MA slope (rate of change of MA)
        df['ma20_slope'] = df['ma20'].diff(5) / df['ma20'].shift(5)
        df['ma50_slope'] = df['ma50'].diff(10) / df['ma50'].shift(10)

        # Price relative to MA
        df['pct_from_ma20'] = (df['close'] - df['ma20']) / df['ma20']
        df['pct_from_ma50'] = (df['close'] - df['ma50']) / df['ma50']
        df['pct_from_ma200'] = (df['close'] - df['ma200']) / df['ma200']

        # Bollinger Bands (20,2)
        std20 = df['close'].rolling(window=20).std(ddof=0)
        df['bb_upper'] = df['ma20'] + 2 * std20
        df['bb_lower'] = df['ma20'] - 2 * std20
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['ma20']
        df['bb_pos'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

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

        # Volume features
        df['vol_ma20'] = df['tick_volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['tick_volume'] / df['vol_ma20'].replace(0, np.nan)

        # Spread features (only on M1 where spread data exists)
        if 'spread' in df.columns:
            df['spread_pct'] = df['spread'] / df['close']

        df.dropna(inplace=True)
        result[sym] = df
        print(f"  {sym:12s} {len(df):>8} rows  {str(df.index[0]):22s} -> {str(df.index[-1]):22s}")
    return result

# ─────────────────────────────────────────────────────────────────────────────
# Grid test runner
# ─────────────────────────────────────────────────────────────────────────────

def run_grid_test(df, entry_condition, direction='long', hold_periods=None):
    """Run a hypothesis test on a single DataFrame."""
    if hold_periods is None:
        hold_periods = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]

    dir_sign = 1.0 if direction == 'long' else -1.0
    close_arr = df['close'].values
    open_arr = df['open'].values
    n_rows = len(df)

    try:
        mask = df.eval(entry_condition).values.astype(bool)
    except Exception as e:
        print(f"  ERROR evaluating condition: {e}")
        return {hp: {"signal_count": 0, "avg_return": None, "win_rate": None,
                     "sharpe_ratio": None, "max_drawdown": None} for hp in hold_periods}

    signal_indices = np.where(mask)[0]
    n_signals = len(signal_indices)
    print(f"  Signals: {n_signals}")

    # Auto-select periods_per_year based on data frequency
    if len(df) > 1:
        time_diff = (df.index[-1] - df.index[0]).total_seconds() / len(df)
        if time_diff < 90:  # ~1 min bars
            periods_per_year = 360_000
        elif time_diff < 180:  # ~5 min bars
            periods_per_year = 72_000
        elif time_diff < 900:  # ~30 min bars
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

def print_results_table(sym, results, label=""):
    """Pretty-print results table with bold for WR >= 60%."""
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
        best = wr >= 0.60
        wr_str = f"{wr:>6.2%}"
        if best:
            wr_str = f"**{wr:>6.2%}**"
        print(f"| {hp:>2}  | {n:>4} | {r['avg_return'] or 0:>+8.4f} | {wr_str} | {r['sharpe_ratio'] or 0:>6.2f} | {r['max_drawdown'] or 0:>7.4f} |")

# ─────────────────────────────────────────────────────────────────────────────
# Holding periods
# ─────────────────────────────────────────────────────────────────────────────

M1_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]
M5_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]

ALL_SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]

# ─────────────────────────────────────────────────────────────────────────────
# TEST DEFINITIONS — Round 62: M1/M5 Deep Dive
# ─────────────────────────────────────────────────────────────────────────────

TESTS = [
    # ═════════════════════════════════════════════════════════════════════
    # SECTION A: M5 — Round 60 Pattern Extension (ATR reduction to expand n)
    # ═════════════════════════════════════════════════════════════════════

    # A1: M5 US RSI<25 — reduce ATR to 0.10% to expand n (was 0.15%)
    {
        "id": "R62_M5_A001",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<25+ATR>0.10%做多 — 降ATR扩样本(R60原0.15%)"
    },
    # A2: M5 US RSI<25 — reduce ATR further to 0.08%
    {
        "id": "R62_M5_A002",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0008",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<25+ATR>0.08%做多 — 极低ATR扩样本至极限"
    },
    # A3: M5 US RSI<20 — reduce ATR to 0.10%
    {
        "id": "R62_M5_A003",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<20+ATR>0.10%做多 — 更严格RSI降ATR"
    },
    # A4: M5 US RSI<25 + BB lower — reduce ATR to 0.10%
    {
        "id": "R62_M5_A004",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25 and close < bb_lower and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<25+close<BBL+ATR>0.10%做多 — BB加强超卖降ATR"
    },

    # ═════════════════════════════════════════════════════════════════════
    # SECTION B: M5 — New Session & Hour Window Patterns
    # ═════════════════════════════════════════════════════════════════════

    # B1: M5 Session transition (asia→europe 7:00-8:00 UTC) RSI<25
    {
        "id": "R62_M5_B001",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour == 7 and minute >= 55 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 亚→欧转换(7:55-7:59)+RSI<25+ATR>0.10%做多 — 晨盘过渡超卖"
    },
    # B2: M5 Session transition (europe→us 15:00-16:00 UTC) RSI<25
    {
        "id": "R62_M5_B002",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour == 15 and minute >= 55 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧→美转换(15:55-15:59)+RSI<25+ATR>0.10%做多 — 美盘前超卖"
    },
    # B3: M5 European morning (8:00-10:00 UTC) RSI<25
    {
        "id": "R62_M5_B003",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 8 and hour < 10 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘早盘(8-10UTC)+RSI<25+ATR>0.10%做多 — 欧盘晨盘超卖"
    },
    # B4: M5 US afternoon (18:00-21:00 UTC) RSI<25
    {
        "id": "R62_M5_B004",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 18 and hour < 21 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘下午(18-21UTC)+RSI<25+ATR>0.10%做多 — 尾盘超卖"
    },
    # B5: M5 Asian session RSI<25 ATR>0.10%
    {
        "id": "R62_M5_B005",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 亚盘+RSI<25+ATR>0.10%做多 — 亚盘超卖均值回归(扩样本版)"
    },
    # B6: M5 European session RSI<25 ATR>0.10%
    {
        "id": "R62_M5_B006",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘+RSI<25+ATR>0.10%做多 — 欧盘超卖均值回归(扩样本版)"
    },

    # ═════════════════════════════════════════════════════════════════════
    # SECTION C: M5 — Trend / Momentum Patterns
    # ═════════════════════════════════════════════════════════════════════

    # C1: M5 Price above MA50 + RSI > 60 (trend continuation)
    {
        "id": "R62_M5_C001",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "close > ma50 and rsi14 > 60 and atr_pct > 0.0010 and session == 'us'",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close>MA50+RSI>60+ATR>0.10%做多 — MA50上方强势延续(扩样本)"
    },
    # C2: M5 Price below MA50 + RSI < 40 (trend continuation short)
    {
        "id": "R62_M5_C002",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "close < ma50 and rsi14 < 40 and atr_pct > 0.0010 and session == 'us'",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close<MA50+RSI<40+ATR>0.10%做空 — MA50下方弱势延续(扩样本)"
    },
    # C3: M5 Bullish MA alignment (MA20 > MA50 > MA100) + pullback to MA20
    {
        "id": "R62_M5_C003",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "ma20 > ma50 and ma50 > ma100 and close < ma20 and close > ma50 and rsi14 > 40 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 MA多头排列(20>50>100)+价格回踩MA20与MA50之间+RSI>40做多 — 趋势回调买入"
    },
    # C4: M5 Bearish MA alignment (MA20 < MA50 < MA100) + pullback to MA20 short
    {
        "id": "R62_M5_C004",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "ma20 < ma50 and ma50 < ma100 and close > ma20 and close < ma50 and rsi14 < 60 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 MA空头排列(20<50<100)+价格反弹至MA20与MA50之间+RSI<60做空 — 趋势反弹卖出"
    },

    # ═════════════════════════════════════════════════════════════════════
    # SECTION D: M1 — Ultra Scalping Patterns
    # ═════════════════════════════════════════════════════════════════════

    # D1: M1 US session RSI<20 ultra oversold
    {
        "id": "R62_M1_D001",
        "timeframe": "M1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0008",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+RSI<20+ATR>0.08%做多 — 1分钟极限超卖均值回归"
    },
    # D2: M1 US session RSI>80 ultra overbought short
    {
        "id": "R62_M1_D002",
        "timeframe": "M1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 > 80 and atr_pct > 0.0008",
        "direction": "short",
        "hold_periods": M1_HOLDS,
        "description": "M1 美盘+RSI>80+ATR>0.08%做空 — 1分钟极限超买做空"
    },
    # D3: M1 European session RSI<20
    {
        "id": "R62_M1_D003",
        "timeframe": "M1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 20 and atr_pct > 0.0008",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 欧盘+RSI<20+ATR>0.08%做多 — 欧盘1分钟超卖"
    },
    # D4: M1 European session RSI>80 short
    {
        "id": "R62_M1_D004",
        "timeframe": "M1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 80 and atr_pct > 0.0008",
        "direction": "short",
        "hold_periods": M1_HOLDS,
        "description": "M1 欧盘+RSI>80+ATR>0.08%做空 — 欧盘1分钟超买"
    },
    # D5: M1 Asian session RSI<20
    {
        "id": "R62_M1_D005",
        "timeframe": "M1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0008",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 亚盘+RSI<20+ATR>0.08%做多 — 亚盘1分钟超卖"
    },
    # D6: M1 RSI<15 extreme oversold (all sessions)
    {
        "id": "R62_M1_D006",
        "timeframe": "M1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "rsi14 < 15 and atr_pct > 0.0008",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "M1 RSI<15+ATR>0.08%做多 — 全盘极端超卖1分钟"
    },

    # ═════════════════════════════════════════════════════════════════════
    # SECTION E: M5 — RSI7 (faster RSI) Patterns
    # ═════════════════════════════════════════════════════════════════════

    # E1: M5 US RSI7 < 15 (ultra short-term oversold)
    {
        "id": "R62_M5_E001",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi7 < 15 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI7<15+ATR>0.10%做多 — 快速RSI超短线超卖"
    },
    # E2: M5 US RSI7 > 85 (ultra short-term overbought short)
    {
        "id": "R62_M5_E002",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'us' and rsi7 > 85 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI7>85+ATR>0.10%做空 — 快速RSI超短线超买"
    },

    # ═════════════════════════════════════════════════════════════════════
    # SECTION F: M5 — Volume-based Patterns
    # ═════════════════════════════════════════════════════════════════════

    # F1: M5 Volume spike + price at BB lower (climactic selling)
    {
        "id": "R62_M5_F001",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "vol_ratio > 2.0 and close < bb_lower and rsi14 < 30 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 vol>2xMA+close<BBL+RSI<30+ATR>0.10%做多 — 放量触及BB下轨反转"
    },
    # F2: M5 Volume spike + price at BB upper (climactic buying short)
    {
        "id": "R62_M5_F002",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "vol_ratio > 2.0 and close > bb_upper and rsi14 > 70 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 vol>2xMA+close>BBU+RSI>70+ATR>0.10%做空 — 放量触及BB上轨反转"
    },
    # F3: M5 Low volume + price inside BB (consolidation breakout long)
    {
        "id": "R62_M5_F003",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "vol_ratio < 0.5 and bb_width < 0.01 and rsi14 > 50 and rsi14 < 70 and close > ma20",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 vol<0.5xMA+BB窄幅+RSI(50-70)+close>MA20做多 — 缩量盘整突破做多"
    },

    # ═════════════════════════════════════════════════════════════════════
    # SECTION G: M5 — Candle Pattern-based
    # ═════════════════════════════════════════════════════════════════════

    # G1: M5 Doji after 3+ bear candles (reversal signal)
    {
        "id": "R62_M5_G001",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "consecutive_bear >= 3 and body_pct < 0.3 and rsi14 < 40 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 连跌3+十字星(体<30%)+RSI<40做多 — 衰竭十字星反转"
    },
    # G2: M5 Doji after 3+ bull candles (reversal short)
    {
        "id": "R62_M5_G002",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "consecutive_bull >= 3 and body_pct < 0.3 and rsi14 > 60 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 连涨3+十字星(体<30%)+RSI>60做空 — 衰竭十字星反转空"
    },

    # ═════════════════════════════════════════════════════════════════════
    # SECTION H: M5 — RSI Divergence from MA (price extreme vs mean)
    # ═════════════════════════════════════════════════════════════════════

    # H1: M5 Price far below MA20 (% distance) + RSI<30 — extreme mean reversion
    {
        "id": "R62_M5_H001",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "pct_from_ma20 < -0.005 and rsi14 < 30 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 price比MA20低0.5%以上+RSI<30+ATR>0.10%做多 — 极端均值回归"
    },
    # H2: M5 Price far above MA20 + RSI>70 — extreme overextension short
    {
        "id": "R62_M5_H002",
        "timeframe": "M5",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "pct_from_ma20 > 0.005 and rsi14 > 70 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 price比MA20高0.5%以上+RSI>70+ATR>0.10%做空 — 极端延伸做空"
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# BONUS: XAUUSD-specific deep dive (most important symbol)
# ─────────────────────────────────────────────────────────────────────────────

BONUS_TESTS = [
    # XAUUSD M5: US session + RSI<15 + ATR>0.15% (extreme oversold)
    {
        "id": "R62_BONUS_XAU_M5_001",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'us' and rsi14 < 15 and atr_pct > 0.0015 and close < bb_lower",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "XAUUSD M5 美盘+RSI<15+ATR>0.15%+close<BBL做多 — 黄金极致超卖(扩n版)"
    },
    # XAUUSD M5: US session consecutive bear 4+ RSI<30
    {
        "id": "R62_BONUS_XAU_M5_002",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'us' and consecutive_bear >= 4 and rsi14 < 30 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "XAUUSD M5 美盘+连跌4+RSI<30+ATR>0.10%做多 — 黄金连续暴跌(扩样本)"
    },
    # XAUUSD M5: Asian session RSI<25
    {
        "id": "R62_BONUS_XAU_M5_003",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0012",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "XAUUSD M5 亚盘+RSI<25+ATR>0.12%做多 — 黄金亚盘超卖(首次测试)"
    },

    # JP225 M5: Asia session RSI<20
    {
        "id": "R62_BONUS_JP225_M5_001",
        "timeframe": "M5",
        "symbols": ["JP225"],
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "JP225 M5 亚盘+RSI<20+ATR>0.15%做多 — 日经亚盘超卖(扩样本)"
    },
    # JP225 M5: US session RSI<20 ATR>0.10%
    {
        "id": "R62_BONUS_JP225_M5_002",
        "timeframe": "M5",
        "symbols": ["JP225"],
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "JP225 M5 美盘+RSI<20+ATR>0.10%做多 — 日经美盘超卖(扩样本至极限)"
    },

    # XAGUSD M5: US session RSI<20 ATR>0.12%
    {
        "id": "R62_BONUS_XAG_M5_001",
        "timeframe": "M5",
        "symbols": ["XAGUSD"],
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0012",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "XAGUSD M5 美盘+RSI<20+ATR>0.12%做多 — 白银美盘超卖(严格RSI)"
    },
    # XAGUSD M5: European session RSI<25 ATR>0.12%
    {
        "id": "R62_BONUS_XAG_M5_002",
        "timeframe": "M5",
        "symbols": ["XAGUSD"],
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0012",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "XAGUSD M5 欧盘+RSI<25+ATR>0.12%做多 — 白银欧盘超卖(扩样本)"
    },

    # US500 M5: European session RSI<25
    {
        "id": "R62_BONUS_US500_M5_001",
        "timeframe": "M5",
        "symbols": ["US500"],
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "US500 M5 欧盘+RSI<25+ATR>0.10%做多 — 标普欧盘超卖(降ATR扩样本)"
    },
    # US500 M5: US session RSI<20 ATR>0.10%
    {
        "id": "R62_BONUS_US500_M5_002",
        "timeframe": "M5",
        "symbols": ["US500"],
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "US500 M5 美盘+RSI<20+ATR>0.10%做多 — 标普美盘超卖(严格RSI扩样本)"
    },

    # US30 M5: US session RSI<25 ATR>0.10%
    {
        "id": "R62_BONUS_US30_M5_001",
        "timeframe": "M5",
        "symbols": ["US30"],
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "US30 M5 美盘+RSI<25+ATR>0.10%做多 — 道指美盘超卖(降ATR扩样本)"
    },

    # M1 BONUS: XAUUSD RSI<15 US session
    {
        "id": "R62_BONUS_XAU_M1_001",
        "timeframe": "M1",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'us' and rsi14 < 15 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "XAUUSD M1 美盘+RSI<15+ATR>0.10%做多 — 黄金1分钟极限超卖"
    },
    # M1 BONUS: JP225 US session RSI<20
    {
        "id": "R62_BONUS_JP225_M1_001",
        "timeframe": "M1",
        "symbols": ["JP225"],
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS,
        "description": "JP225 M1 美盘+RSI<20+ATR>0.10%做多 — 日经1分钟超卖"
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Main execution
# ─────────────────────────────────────────────────────────────────────────────

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
    print("  Round 62 — M1/M5 Scalping Deep Dive Researcher")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Total tests: {len(TESTS) + len(BONUS_TESTS)} ({len(TESTS)} main + {len(BONUS_TESTS)} bonus)")
    print("  Target: XAUUSD, XAGUSD, JP225, US500, US30 on M1/M5")
    print("=" * 80)

    all_tests = TESTS + BONUS_TESTS
    all_results = {}
    test_seq = 0

    for test in all_tests:
        test_seq += 1
        print(f"\n{'─' * 80}")
        print(f"\n[{test_seq:>2}/{len(all_tests)}] {test['id']}: {test['description']}")
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
                                    test["hold_periods"])
            test_results[sym] = results
            print_results_table(sym, results, label=test["id"])

        all_results[test["id"]] = test_results
        print(f"\n  [{test['id']}] Completed in {time.time()-t0:.1f}s")

    # ── Save raw results ──
    LOGS_DIR.mkdir(exist_ok=True)
    out_path = LOGS_DIR / "round62_researcher_results.json"
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

        # Candidate for injection (WR>=65%, n>=150)
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
    print(f"  Round 62 completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    main()
