#!/usr/bin/env python3
"""
Round 60 — M1/M5 Scalping Researcher Runner
First round focusing on M1/M5 ultra-short-term patterns.

Target symbols: XAUUSD, XAGUSD, JP225, US500, US30
Timeframes: M1, M5

Scalping holds (bars): [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48]
For M1: 1-48 minutes
For M5: 5-240 minutes (4h max)
"""
import json, sys
from pathlib import Path

import pandas as pd
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

# ──────────────────────────────────────────────────────────────────
# Indicator helpers
# ──────────────────────────────────────────────────────────────────

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

        # Time-based features
        df['hour'] = df.index.hour
        df['minute'] = df.index.minute
        def session_label(h):
            if h < 8: return 'asia'
            if h < 16: return 'europe'
            return 'us'
        df['session'] = df['hour'].apply(session_label)
        df['dayofweek'] = df.index.dayofweek

        # Volume features
        df['log_volume'] = np.log1p(df['tick_volume'])

        # RSI
        df['rsi14'] = calc_rsi(df['close'])
        df['rsi7'] = calc_rsi(df['close'], period=7)

        # ATR (absolute and relative)
        df['atr14'] = calc_atr(df)
        df['atr_pct'] = df['atr14'] / df['close']  # ATR as % of price

        # Moving averages
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()
        df['ma100'] = df['close'].rolling(window=100).mean()
        df['ma200'] = df['close'].rolling(window=200).mean()

        # Bollinger Bands (20,2)
        std20 = df['close'].rolling(window=20).std(ddof=0)
        df['bb_upper'] = df['ma20'] + 2 * std20
        df['bb_lower'] = df['ma20'] - 2 * std20
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['ma20']
        df['bb_pos'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # Price relative to MA
        df['pct_from_ma20'] = (df['close'] - df['ma20']) / df['ma20']
        df['pct_from_ma50'] = (df['close'] - df['ma50']) / df['ma50']
        df['pct_from_ma200'] = (df['close'] - df['ma200']) / df['ma200']

        # Consecutive bullish/bearish candles
        bull = (df['close'] > df['open']).astype(int)
        bear = (df['close'] < df['open']).astype(int)
        bull_groups = (bull != bull.shift()).cumsum()
        bear_groups = (bear != bear.shift()).cumsum()
        df['consecutive_bull'] = bull.groupby(bull_groups).cumsum()
        df['consecutive_bear'] = bear.groupby(bear_groups).cumsum()

        # Price range features
        df['candle_range'] = (df['high'] - df['low']) / df['close']
        df['upper_shadow'] = (df['high'] - df[['open', 'close']].max(axis=1)) / df['close']
        df['lower_shadow'] = (df[['open', 'close']].min(axis=1) - df['low']) / df['close']
        df['body_pct'] = abs(df['close'] - df['open']) / (df['high'] - df['low'])
        df['body_pct'] = df['body_pct'].replace([np.inf, -np.inf], 0).fillna(0)

        # Volume spike (compared to 20-bar average)
        df['vol_ma20'] = df['tick_volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['tick_volume'] / df['vol_ma20'].replace(0, np.nan)

        df.dropna(inplace=True)
        result[sym] = df
        print(f"  {sym:12s} {len(df):>8} rows  {str(df.index[0]):22s} -> {str(df.index[-1]):22s}")
    return result

# ──────────────────────────────────────────────────────────────────
# Grid test runner
# ──────────────────────────────────────────────────────────────────

def run_grid_test(df, entry_condition, direction='long', hold_periods=None):
    """Run a hypothesis test on a single DataFrame."""
    if hold_periods is None:
        hold_periods = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48]

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

    # Auto-select periods_per_year based on data frequency
    # Estimate from typical bar spacing
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

def print_results_table(sym, results):
    """Pretty-print results table with bold for WR >= 60%."""
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

# ──────────────────────────────────────────────────────────────────
# M1 HOLD PERIODS  — 1 to 60 minutes
# M5 HOLD PERIODS  — 1 to 60 bars = 5 to 300 minutes
# ──────────────────────────────────────────────────────────────────

M1_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]
M5_HOLDS  = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 24, 30, 40, 48, 60]

# ──────────────────────────────────────────────────────────────────
# TEST DEFINITIONS  —  Round 60: M1/M5 Scalping Discovery
# ──────────────────────────────────────────────────────────────────

TESTS = [
    # ═══════════════════════════════════════════════════════════════
    # Category 1: M5 — RSI Oversold Mean Reversion (Session-based)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R60_M5_001",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI<25+ATR>0.15%做多 — 美盘超卖均值回归（5种期货）"
    },
    {
        "id": "R60_M5_002",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 亚盘+RSI<25+ATR>0.15%做多 — 亚盘超卖均值回归"
    },
    {
        "id": "R60_M5_003",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘+RSI<25+ATR>0.15%做多 — 欧盘超卖均值回归"
    },

    # ═══════════════════════════════════════════════════════════════
    # Category 2: M5 — RSI Overbought Mean Reversion (Short)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R60_M5_004",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and rsi14 > 75 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+RSI>75+ATR>0.15%做空 — 美盘超买做空"
    },
    {
        "id": "R60_M5_005",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'asia' and rsi14 > 75 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 亚盘+RSI>75+ATR>0.15%做空 — 亚盘超买做空"
    },

    # ═══════════════════════════════════════════════════════════════
    # Category 3: M5 — Bollinger Band mean reversion
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R60_M5_006",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and close < bb_lower and rsi14 < 30 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close<bb_lower+RSI<30+ATR>0.15%做多 — BB下轨增强超卖"
    },
    {
        "id": "R60_M5_007",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and close > bb_upper and rsi14 > 70 and atr_pct > 0.0015",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close>bb_upper+RSI>70+ATR>0.15%做空 — BB上轨增强超买"
    },

    # ═══════════════════════════════════════════════════════════════
    # Category 4: M5 — Momentum / Consecutive candles
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R60_M5_008",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and consecutive_bear >= 3 and rsi14 < 30 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+连跌3+RSI<30+ATR>0.10%做多 — 连续下跌反转"
    },
    {
        "id": "R60_M5_009",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and consecutive_bull >= 3 and rsi14 > 70 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+连涨3+RSI>70+ATR>0.10%做空 — 连续上涨反转"
    },

    # ═══════════════════════════════════════════════════════════════
    # Category 5: M5 — Session Open / Close patterns
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R60_M5_010",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "hour == 8 and minute == 0 and rsi14 < 40 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 欧盘开盘(8:00)+RSI<40 做多 — 欧盘开盘做多策略"
    },
    {
        "id": "R60_M5_011",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "hour == 13 and minute == 30 and rsi14 < 40 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘开盘(13:30)+RSI<40 做多 — 美盘开盘做多策略"
    },

    # ═══════════════════════════════════════════════════════════════
    # Category 6: M1 — RSI Oversold (ultra-short scalping)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R60_M1_001",
        "timeframe": "M1",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS[:20],  # 1-20 holds for M1
        "description": "M1 美盘+RSI<20+ATR>0.10%做多 — 1分钟超卖极短持仓"
    },
    {
        "id": "R60_M1_002",
        "timeframe": "M1",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and rsi14 > 80 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M1_HOLDS[:20],
        "description": "M1 美盘+RSI>80+ATR>0.10%做空 — 1分钟超买极短持仓"
    },
    {
        "id": "R60_M1_003",
        "timeframe": "M1",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M1_HOLDS[:20],
        "description": "M1 亚盘+RSI<20+ATR>0.10%做多 — 亚盘1分钟超卖"
    },

    # ═══════════════════════════════════════════════════════════════
    # Category 7: M5 — Volume spike breakouts
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R60_M5_012",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and vol_ratio > 2.0 and close > ma20 and rsi14 > 50",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+vol>2xMA+close>MA20+RSI>50做多 — 放量突破做多"
    },
    {
        "id": "R60_M5_013",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and vol_ratio > 2.0 and close < ma20 and rsi14 < 50",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+vol>2xMA+close<MA20+RSI<50做空 — 放量下跌做空"
    },

    # ═══════════════════════════════════════════════════════════════
    # Category 8: M5 — Price relative to MA (trend following)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "R60_M5_014",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and close > ma50 and rsi14 > 60 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close>MA50+RSI>60做多 — MA50上方强势延续"
    },
    {
        "id": "R60_M5_015",
        "timeframe": "M5",
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "entry_condition": "session == 'us' and close < ma50 and rsi14 < 40 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M5_HOLDS,
        "description": "M5 美盘+close<MA50+RSI<40做空 — MA50下方弱势延续"
    },
]

# ──────────────────────────────────────────────────────────────────
# BONUS TESTS — XAUUSD specific deep dive
# ──────────────────────────────────────────────────────────────────

BONUS_TESTS = [
    {
        "id": "R60_BONUS_M5_XAU_001",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0020 and close < bb_lower",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "XAUUSD M5 美盘+RSI<20+ATR>0.20%+close<BBL做多 — 黄金极致超卖"
    },
    {
        "id": "R60_BONUS_M5_XAU_002",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'us' and consecutive_bear >= 4 and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "XAUUSD M5 美盘+连跌4+RSI<25+ATR>0.15%做多 — 黄金连续暴跌反转"
    },
    {
        "id": "R60_BONUS_M5_JP225_001",
        "timeframe": "M5",
        "symbols": ["JP225"],
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0020",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "JP225 M5 亚盘+RSI<20+ATR>0.20%做多 — 日经亚盘超卖拖网"
    },
    {
        "id": "R60_BONUS_M5_US500_001",
        "timeframe": "M5",
        "symbols": ["US500"],
        "entry_condition": "session == 'europe' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "US500 M5 欧盘+RSI<20+ATR>0.15%做多 — 标普欧盘超卖"
    },
    {
        "id": "R60_BONUS_M1_XAU_001",
        "timeframe": "M1",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'us' and rsi14 < 15 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M1_HOLDS[:20],
        "description": "XAUUSD M1 美盘+RSI<15+ATR>0.15%做多 — 黄金1分钟极限超卖"
    },
    {
        "id": "R60_BONUS_M5_US30_001",
        "timeframe": "M5",
        "symbols": ["US30"],
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M5_HOLDS,
        "description": "US30 M5 美盘+RSI<20+ATR>0.15%做多 — 道指美盘超卖"
    },
]

# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 80)
    print("  Round 60 — M1/M5 Scalping Researcher Pipeline")
    print("  First ultra-short-term pattern discovery round!")
    print("=" * 80)

    all_tests = TESTS + BONUS_TESTS
    all_results = {}

    for test in all_tests:
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

    # Save results
    out_path = SCRIPT_DIR.parent / "logs" / "round60_m1m5_results.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n{'─' * 80}")
    print(f"\nResults saved to {out_path}")
    print("Done.")
