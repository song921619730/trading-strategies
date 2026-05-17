#!/usr/bin/env python3
"""
Round 66 — P0/P1 优先级定向优化 + UKOIL长持有期 + USDJPY扩样本
基于 Round 65 的下一步假设:
  P0: JP225 极限扩样本(ATR↓0.07%) + USDJPY欧盘超买做空扩样本(ATR↓0.10%)
  P1: UKOIL长持有期(72-96) + US30/UKOIL放宽RSI至25 + AUDUSD bb_pos降ATR
  P2: HK50伦敦开盘扩样本 + 极限Session窗口(ATR↓0.05%)

品种 (14): XAUUSD, XAGUSD, USTEC, US30, US500, JP225, HK50,
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

# ── Indicator helpers ─────────────────────────────────────────────

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

        df.dropna(inplace=True)
        result[sym] = df
        print(f"  {sym:12s} {len(df):>8} rows  {str(df.index[0]):22s} -> {str(df.index[-1]):22s}")
    return result

# ── Grid test runner ──────────────────────────────────────────────

H1_HOLDS  = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 24, 30, 40]
M30_HOLDS = [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60]
# Extended holds for UKOIL long-hold testing
M30_HOLDS_LONG = [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60, 72, 84, 96]

PERIODS_PER_YEAR = {"H1": 6000, "M30": 12000}

def run_grid_test(df, entry_condition, direction='long', hold_periods=None, timeframe='H1'):
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

# ── Symbol definitions ────────────────────────────────────────────

ALL_SYMBOLS = ["XAUUSD", "XAGUSD", "USTEC", "US30", "US500", "JP225", "HK50",
               "USOIL", "UKOIL", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]
INDEX_SYMBOLS = ["USTEC", "US30", "US500", "JP225", "HK50"]
FX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]
METAL_SYMBOLS = ["XAUUSD", "XAGUSD"]
OIL_SYMBOLS = ["USOIL", "UKOIL"]

# ═══════════════════════════════════════════════════════════════════════
# TEST DEFINITIONS — Round 66: P0/P1 优先级定向优化
# ═══════════════════════════════════════════════════════════════════════

TESTS = [

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION A: JP225 极限扩样本 — R65发现4个可注入信号，继续降ATR
    # R65_H1_E002: H1 亚盘+连跌3+RSI<30+BBL+ATR>0.15% → n=178 WR=70.22%
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R66_H1_A001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 30 and close < bb_lower and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+连跌3+RSI<30+BBL+ATR>0.10%做多 — JP225极限扩样本(P0)"
    },
    {
        "id": "R66_H1_A002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 3 and rsi14 < 30 and close < bb_lower and atr_pct > 0.0007",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+连跌3+RSI<30+BBL+ATR>0.07%做多 — JP225极限降ATR(P0)"
    },
    {
        "id": "R66_M30_A003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 4 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+连跌4+RSI<25+ATR>0.10%做多 — JP225 M30极限扩样本"
    },
    {
        "id": "R66_M30_A004",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and consecutive_bear >= 4 and rsi14 < 25 and atr_pct > 0.0007",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+连跌4+RSI<25+ATR>0.07%做多 — JP225 M30极限扩样本(P0)"
    },
    {
        "id": "R66_M30_A005",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0008",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<20+ATR>0.08%做多 — JP225 RSI<20极限降ATR(P0)"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION B: USDJPY 欧盘超买做空 扩样本 (R65_H1_D001: n=69 WR=72.46%)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R66_H1_B001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI>70+ATR>0.10%做空 — USDJPY欧盘超买扩样本(P0)"
    },
    {
        "id": "R66_H1_B002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 65 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI>65+ATR>0.10%做空 — 放宽RSI扩样本"
    },
    {
        "id": "R66_M30_B003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI>70+ATR>0.10%做空 — USDJPY欧盘超买M30版"
    },
    {
        "id": "R66_H1_B004",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr_pct > 0.0007",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI>70+ATR>0.07%做空 — USDJPY极限降ATR(P0)"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION C: UKOIL 亚盘极限超卖 长持有期 (R65: WR=76.47% n=68)
    # 假设: UKOIL均值回归需2-3交易日，hold=72-96可进一步提升WR
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R66_M30_C001",
        "timeframe": "M30",
        "symbols": OIL_SYMBOLS + ALL_SYMBOLS,  # 全品种但重点关注UKOIL
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 亚盘+RSI<20+ATR>0.15%做多 — UKOIL长持有期72-96(P1)"
    },
    {
        "id": "R66_M30_C002",
        "timeframe": "M30",
        "symbols": OIL_SYMBOLS + ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 亚盘+RSI<25+ATR>0.10%做多 — UKOIL放宽RSI+长持有(P1)"
    },
    {
        "id": "R66_M30_C003",
        "timeframe": "M30",
        "symbols": OIL_SYMBOLS + ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 22 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 亚盘+RSI<22+ATR>0.15%做多 — UKOIL中间RSI+长持有"
    },
    {
        "id": "R66_M30_C004",
        "timeframe": "M30",
        "symbols": OIL_SYMBOLS + ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M30_HOLDS_LONG,
        "description": "M30 亚盘+RSI<20+ATR>0.10%做多 — UKOIL降ATR+长持有(P1)"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION D: US30/US500/UKOIL 亚盘放宽RSI至25 (R65: n不足)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R66_M30_D001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<25+ATR>0.15%做多 — US30/US500宽RSI扩样本(P1)"
    },
    {
        "id": "R66_M30_D002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<25+ATR>0.10%做多 — US30/US500宽RSI降ATR(P1)"
    },
    {
        "id": "R66_M30_D003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 28 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<28+ATR>0.10%做多 — US30/US500最宽松超卖"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION E: AUDUSD H1 bb_pos 增强 降ATR (R65_G003: n=68 WR=72.06%)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R66_H1_E001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0015 and bb_pos < 0.3",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI<25+ATR>0.15%+bb_pos<0.3做多 — AUDUSD扩样本(P1)"
    },
    {
        "id": "R66_H1_E002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0012 and bb_pos < 0.35",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI<25+ATR>0.12%+bb_pos<0.35做多 — AUDUSD降ATR扩样本(P1)"
    },
    {
        "id": "R66_H1_E003",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0015 and pct_from_ma50 < -0.005",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI<25+ATR>0.15%+低于MA50做多 — MA50替代bb_pos"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION F: HK50 伦敦开盘 扩样本 (R65_B001: n=68 WR=70.59%)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R66_H1_F001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 8 and hour < 10 and rsi14 < 30 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 伦敦开盘(8-10)+RSI<30+ATR>0.10%做多 — HK50扩样本(P2)"
    },
    {
        "id": "R66_H1_F002",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 7 and hour < 9 and rsi14 < 25 and atr_pct > 0.0007",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚→欧转换(7-9)+RSI<25+ATR>0.07%做多 — HK50极限扩样本(P2)"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION G: 极限Session窗口 (ATR降至0.05%)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R66_M30_G001",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 14 and rsi14 < 25 and atr_pct > 0.0005",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 London-NY(12-14)+RSI<25+ATR>0.05%做多 — 极限流动性超卖(P2)"
    },
    {
        "id": "R66_M30_G002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 14 and rsi14 > 70 and atr_pct > 0.0005",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 London-NY(12-14)+RSI>70+ATR>0.05%做空 — 极限流动性超买(P2)"
    },
    {
        "id": "R66_M30_G003",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 0 and hour < 3 and rsi14 < 25 and atr_pct > 0.0005",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 东京开盘(0-3)+RSI<25+ATR>0.05%做多 — 东京极限超卖(P2)"
    },
    {
        "id": "R66_M30_G004",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 0 and hour < 3 and rsi14 > 70 and atr_pct > 0.0005",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 东京开盘(0-3)+RSI>70+ATR>0.05%做空 — 东京极限超买(P2)"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION H: 跨品种谱系对比 — 欧盘做空全面扫描
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "R66_H1_H001",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr_pct > 0.0010",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "H1 欧盘+RSI>70+ATR>0.10%做空 — 跨品种超买做空扫描"
    },
    {
        "id": "R66_M30_H002",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<20+ATR>0.10%做多 — 跨品种极限超卖扫描"
    },
]

# ═══════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 90)
    print("  Round 66 — P0/P1 优先级定向优化 + UKOIL长持有期 + USDJPY扩样本")
    print(f"  开始时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  总测试数: {len(TESTS)}")
    print("=" * 90)

    all_results = {}

    tests_by_tf = {}
    for t in TESTS:
        tf = t["timeframe"]
        tests_by_tf.setdefault(tf, []).append(t)

    for tf, tf_tests in tests_by_tf.items():
        print(f"\n{'#'*90}")
        print(f"# 加载 {tf} 数据 ...")
        print(f"{'#'*90}")

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
    results_path = LOGS_DIR / "round66_researcher_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n{'='*90}")
    print(f"  ✅ 所有测试完成！结果已保存至: {results_path}")
    print(f"  完成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  测试数: {len(TESTS)}")
    print(f"{'='*90}")

if __name__ == "__main__":
    main()
