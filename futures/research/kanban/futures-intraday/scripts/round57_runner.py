#!/usr/bin/env python3
"""
Round 57 — Researcher Runner
Runs grid tests on pending hypotheses and outputs structured results.
"""
import json, sys
from pathlib import Path

import pandas as pd
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))

def load_and_compute(timeframe, symbols):
    """Load parquet files and compute indicators."""
    tf_dir = DATA_DIR / timeframe
    result = {}
    for sym in symbols:
        fpath = tf_dir / f"{sym}.parquet"
        if not fpath.exists():
            print(f"  SKIP {sym}: file not found")
            continue
        df = pd.read_parquet(fpath)
        df.index.name = "time"
        df.sort_index(inplace=True)
        
        # Session & time
        df['hour'] = df.index.hour
        def session_label(h):
            if h < 8: return 'asia'
            if h < 16: return 'europe'
            return 'us'
        df['session'] = df['hour'].apply(session_label)
        df['dayofweek'] = df.index.dayofweek
        
        # RSI
        df['rsi14'] = calc_rsi(df['close'])
        
        # ATR
        prev_close = df['close'].shift(1)
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - prev_close).abs(),
            (df['low'] - prev_close).abs()
        ], axis=1).max(axis=1)
        df['atr14'] = tr.rolling(window=14).mean()
        
        # MA
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()
        df['ma200'] = df['close'].rolling(window=200).mean()
        
        # Bollinger
        std20 = df['close'].rolling(window=20).std(ddof=0)
        df['bb_upper'] = df['ma20'] + 2 * std20
        df['bb_lower'] = df['ma20'] - 2 * std20
        
        # Consecutive counts
        bull = (df['close'] > df['open']).astype(int)
        bear = (df['close'] < df['open']).astype(int)
        bull_groups = (bull != bull.shift()).cumsum()
        bear_groups = (bear != bear.shift()).cumsum()
        df['consecutive_bull_count'] = bull.groupby(bull_groups).cumsum()
        df['consecutive_bear_count'] = bear.groupby(bear_groups).cumsum()
        
        # Drop rows with NaN from indicator computation
        df.dropna(inplace=True)
        result[sym] = df
        print(f"  {sym:12s} {len(df):>6} rows  {str(df.index[0]):22s} → {str(df.index[-1]):22s}")
    return result

def run_grid_test(df, entry_condition, direction='long', hold_periods=None):
    """Run a grid test on a single DataFrame."""
    if hold_periods is None:
        hold_periods = [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60]
    
    dir_sign = 1.0 if direction == 'long' else -1.0
    close_arr = df['close'].values
    n_rows = len(df)
    
    try:
        mask = df.eval(entry_condition).values.astype(bool)
    except Exception as e:
        print(f"  ERROR evaluating condition: {e}")
        return {hp: {"signal_count": 0, "avg_return": None, "win_rate": None, "sharpe_ratio": None, "max_drawdown": None} for hp in hold_periods}
    
    signal_indices = np.where(mask)[0]
    print(f"  Signals: {len(signal_indices)}")
    
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
            results[hp] = {"signal_count": 0, "avg_return": None, "win_rate": None, "sharpe_ratio": None, "max_drawdown": None}
            continue
        
        avg_ret = float(ret_arr.mean())
        win_rate = float((ret_arr > 0).mean())
        std_ret = float(ret_arr.std())
        
        # Annualized Sharpe (M30: ~12000 bars/year)
        periods_per_year = 12000
        sharpe = avg_ret / std_ret * np.sqrt(periods_per_year / hp) if std_ret > 0 else 0.0
        
        # Max drawdown
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
    """Pretty print results as markdown table."""
    print(f"\n### {sym}")
    print(f"| Hold | n | avg_ret | WR | Sharpe | MaxDD |")
    print(f"|:----:|:-:|:-------:|:--:|:------:|:-----:|")
    for hp in sorted(results.keys(), key=int):
        r = results[hp]
        n = r['signal_count']
        if n == 0:
            print(f"| {hp:>2} | 0 | — | — | — | — |")
            continue
        print(f"| **{hp}** | {n:>4} | {r['avg_return']:>+8.4f} | {r['win_rate']:>6.2%} | {r['sharpe_ratio']:>6.2f} | {r['max_drawdown']:>7.4f} |")

# ── Test Configurations ──

TESTS = [
    {
        "id": "round56_new_01",
        "timeframe": "M30",
        "symbols": ["JP225"],
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0030",
        "direction": "long",
        "hold_periods": [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60],
        "description": "JP225 M30 美盘+RSI<30+ATR>0.30%做多 — 降低ATR阈值扩大样本"
    },
    {
        "id": "round56_new_02",
        "timeframe": "M30",
        "symbols": ["JP225"],
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0035 and close < bb_lower",
        "direction": "long",
        "hold_periods": [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60],
        "description": "JP225 M30 美盘+RSI<30+ATR>0.35%+close<bb_lower做多 — BB下轨过滤"
    },
    {
        "id": "round56_new_03",
        "timeframe": "M30",
        "symbols": ["US30"],
        "entry_condition": "session == 'us' and rsi14 < 20 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60],
        "description": "US30 M30 美盘+RSI<20+ATR>0.20%做多 — 严格RSI+低ATR扩样本"
    },
    {
        "id": "round56_new_04",
        "timeframe": "M30",
        "symbols": ["JP225"],
        "entry_condition": "session == 'us' and rsi14 < 25 and atr14 / close > 0.0030",
        "direction": "long",
        "hold_periods": [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60],
        "description": "JP225 M30 美盘+RSI<25+ATR>0.30%做多 — 降低ATR扩RSI<25版样本"
    }
]

if __name__ == "__main__":
    print("=" * 70)
    print("  Round 57 — Researcher Pipeline")
    print("=" * 70)
    
    all_results = {}
    
    for test in TESTS:
        print(f"\n{'─' * 70}")
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
    out_path = SCRIPT_DIR.parent / "logs" / "round57_researcher_results.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n{'─' * 70}")
    print(f"\nResults saved to {out_path}")
    print("Done.")
