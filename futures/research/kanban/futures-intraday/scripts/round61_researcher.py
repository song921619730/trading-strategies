#!/usr/bin/env python3
"""
Round 61 — Researcher Runner
Focus: European/Asian session patterns on H1 and M30
Runs ~40 hypothesis tests across all 14 symbols
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

# ── Indicator computation helpers (fast, local, no heavy deps) ──────────────

def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))

def _atr(df, period=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def _bollinger_bands(series, period=20, n_std=2.0):
    ma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std(ddof=0)
    return ma + n_std * std, ma - n_std * std

def _session_label(hour):
    if hour < 8:
        return "asia"
    if hour < 16:
        return "europe"
    return "us"

def _consecutive_counts(df):
    bull = (df["close"] > df["open"]).astype(int)
    bear = (df["close"] < df["open"]).astype(int)
    bull_groups = (bull != bull.shift()).cumsum()
    bear_groups = (bear != bear.shift()).cumsum()
    return bull.groupby(bull_groups).cumsum(), bear.groupby(bear_groups).cumsum()

def load_and_compute(timeframe, symbols, progress_label=""):
    """Load parquet data and compute indicators. Returns {symbol: df}."""
    tf_dir = DATA_DIR / timeframe
    result = {}
    for sym in symbols:
        fpath = tf_dir / f"{sym}.parquet"
        if not fpath.exists():
            print(f"  [{progress_label}] SKIP {sym}: file not found")
            continue
        df = pd.read_parquet(fpath)
        df.index.name = "time"
        df.sort_index(inplace=True)

        # Session / time features
        df["hour"] = df.index.hour
        df["session"] = df["hour"].apply(_session_label)
        df["dayofweek"] = df.index.dayofweek

        # Indicators
        df["rsi14"] = _rsi(df["close"])
        df["atr14"] = _atr(df)
        df["ma20"] = df["close"].rolling(window=20).mean()
        df["ma50"] = df["close"].rolling(window=50).mean()
        df["ma200"] = df["close"].rolling(window=200).mean()

        std20 = df["close"].rolling(window=20).std(ddof=0)
        df["bb_upper"] = df["ma20"] + 2 * std20
        df["bb_lower"] = df["ma20"] - 2 * std20

        bull_cnt, bear_cnt = _consecutive_counts(df)
        df["consecutive_bull_count"] = bull_cnt
        df["consecutive_bear_count"] = bear_cnt

        df.dropna(inplace=True)
        result[sym] = df
        print(f"  [{progress_label}] {sym:10s} {len(df):>6} rows  {str(df.index[0])[:19]} -> {str(df.index[-1])[:19]}")
    return result

# ── Grid test runner (standalone, no grid_engine dependency) ────────────────

H1_HOLDS = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 30, 40, 48]
M30_HOLDS = [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 40, 45, 50, 60]

PERIODS_PER_YEAR = {"H1": 6000, "M30": 12000}

def run_grid_test(df, entry_condition, direction="long", hold_periods=None, timeframe="H1"):
    """Run a single hypothesis test on a single symbol's DataFrame."""
    if hold_periods is None:
        hold_periods = H1_HOLDS if timeframe == "H1" else M30_HOLDS

    dir_sign = 1.0 if direction == "long" else -1.0
    close_arr = df["close"].values
    open_arr = df["open"].values
    n_rows = len(df)
    ppy = PERIODS_PER_YEAR.get(timeframe, 6000)

    try:
        mask = df.eval(entry_condition).values.astype(bool)
    except Exception as e:
        print(f"    ERROR evaluating condition: {e}")
        return {hp: {"signal_count": 0, "avg_return": None, "win_rate": None,
                     "sharpe_ratio": None, "max_drawdown": None}
                for hp in hold_periods}

    signal_indices = np.where(mask)[0]
    n_signals = len(signal_indices)
    print(f"    Signals: {n_signals}")

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
    """Pretty-print results for a symbol."""
    print(f"\n### {label} {sym}")
    print(f"| Hold |   n  | avg_ret  |   WR    | Sharpe |  MaxDD  |")
    print(f"|:----:|:----:|:--------:|:-------:|:------:|:-------:|")
    for hp in sorted(results.keys(), key=int):
        r = results[hp]
        n = r["signal_count"]
        if n == 0:
            print(f"| {hp:>2}  |  0   |   ---    |   ---   |  ---   |   ---   |")
            continue
        best = r["win_rate"] and r["win_rate"] >= 0.60 and n >= 30
        wr_str = f"{r['win_rate']:>6.2%}"
        if best:
            wr_str = f"**{r['win_rate']:>6.2%}**"
        print(f"| {hp:>2}  | {n:>4} | {r['avg_return']:>+8.4f} | {wr_str} | {r['sharpe_ratio']:>6.2f} | {r['max_drawdown']:>7.4f} |")

# ── Define all hypothesis tests ─────────────────────────────────────────────

ALL_SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
               "USDCHF", "USOIL", "UKOIL", "USTEC", "US30", "US500", "JP225", "HK50"]
INDEX_SYMBOLS = ["USTEC", "US30", "US500", "JP225", "HK50"]
FX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]
METAL_SYMBOLS = ["XAUUSD", "XAGUSD"]
OIL_SYMBOLS = ["USOIL", "UKOIL"]

TESTS = [
    # ═══════════════════════════════════════════════════════════════════════
    # H1 TESTS (1-20)
    # ═══════════════════════════════════════════════════════════════════════

    # 1. XAUUSD ATR reduction — asia RSI<30 ATR>0.30%
    {
        "id": "h1_xau_asia_rsi30_atr030",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'asia' and rsi14 < 30 and atr14 / close > 0.0030",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "XAUUSD H1 亚盘+RSI<30+ATR>0.30%做多 - 降ATR扩样本至150+目标注入"
    },
    # 2. XAUUSD ATR reduction — asia RSI<40 ATR>0.15%
    {
        "id": "h1_xau_asia_rsi40_atr015",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'asia' and rsi14 < 40 and atr14 / close > 0.0015",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "XAUUSD H1 亚盘+RSI<40+ATR>0.15%做多 - 极宽松ATR验证广谱信号"
    },
    # 3. XAUUSD ATR reduction — us RSI<30 ATR>0.35%
    {
        "id": "h1_xau_us_rsi30_atr035",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0035",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "XAUUSD H1 美盘+RSI<30+ATR>0.35%做多 - 降ATR验证美盘72.73%信号"
    },
    # 4. XAGUSD H1 europe RSI<25 ATR>0.35%
    {
        "id": "h1_xag_europe_rsi25_atr035",
        "timeframe": "H1",
        "symbols": ["XAGUSD"],
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr14 / close > 0.0035",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "XAGUSD H1 欧盘+RSI<25+ATR>0.35%做多 - 白银欧盘超卖"
    },
    # 5. XAGUSD H1 asia RSI<30 ATR>0.30%
    {
        "id": "h1_xag_asia_rsi30_atr030",
        "timeframe": "H1",
        "symbols": ["XAGUSD"],
        "entry_condition": "session == 'asia' and rsi14 < 30 and atr14 / close > 0.0030",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "XAGUSD H1 亚盘+RSI<30+ATR>0.30%做多 - 白银亚盘超卖"
    },
    # 6. EURUSD H1 europe short RSI>65 ATR>0.12%
    {
        "id": "h1_eur_europe_rsi65_atr012_short",
        "timeframe": "H1",
        "symbols": ["EURUSD"],
        "entry_condition": "session == 'europe' and rsi14 > 65 and atr14 / close > 0.0012",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "EURUSD H1 欧盘+RSI>65+ATR>0.12%做空 - 欧元欧盘超买"
    },
    # 7. EURUSD H1 europe short RSI>70 ATR>0.12% (stricter)
    {
        "id": "h1_eur_europe_rsi70_atr012_short",
        "timeframe": "H1",
        "symbols": ["EURUSD"],
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr14 / close > 0.0012",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "EURUSD H1 欧盘+RSI>70+ATR>0.12%做空 - 欧元欧盘严重超买"
    },
    # 8. GBPUSD H1 europe short RSI>70 ATR>0.18%
    {
        "id": "h1_gbp_europe_rsi70_atr018_short",
        "timeframe": "H1",
        "symbols": ["GBPUSD"],
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr14 / close > 0.0018",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "GBPUSD H1 欧盘+RSI>70+ATR>0.18%做空 - 英镑欧盘超买"
    },
    # 9. GBPUSD H1 europe short RSI>70 ATR>0.20%
    {
        "id": "h1_gbp_europe_rsi70_atr020_short",
        "timeframe": "H1",
        "symbols": ["GBPUSD"],
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr14 / close > 0.0020",
        "direction": "short",
        "hold_periods": H1_HOLDS,
        "description": "GBPUSD H1 欧盘+RSI>70+ATR>0.20%做空 - 英镑严格ATR验证"
    },
    # 10. USDJPY H1 europe long RSI<30 ATR>0.40%
    {
        "id": "h1_jpy_europe_rsi30_atr040",
        "timeframe": "H1",
        "symbols": ["USDJPY"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0040",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "USDJPY H1 欧盘+RSI<30+ATR>0.40%做多 - 美日欧盘超卖"
    },
    # 11. USDJPY H1 europe long RSI<30 ATR>0.35%
    {
        "id": "h1_jpy_europe_rsi30_atr035",
        "timeframe": "H1",
        "symbols": ["USDJPY"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0035",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "USDJPY H1 欧盘+RSI<30+ATR>0.35%做多 - 美日低ATR扩样本"
    },
    # 12. JP225 H1 europe RSI<25 ATR>0.40%
    {
        "id": "h1_jp225_europe_rsi25_atr040",
        "timeframe": "H1",
        "symbols": ["JP225"],
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr14 / close > 0.0040",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "JP225 H1 欧盘+RSI<25+ATR>0.40%做多 - 日经欧盘超卖"
    },
    # 13. JP225 H1 europe RSI<30 ATR>0.35%
    {
        "id": "h1_jp225_europe_rsi30_atr035",
        "timeframe": "H1",
        "symbols": ["JP225"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0035",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "JP225 H1 欧盘+RSI<30+ATR>0.35%做多 - 日经宽松版扩样本"
    },
    # 14. US500 H1 europe RSI<30 ATR>0.20%
    {
        "id": "h1_us500_europe_rsi30_atr020",
        "timeframe": "H1",
        "symbols": ["US500"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "US500 H1 欧盘+RSI<30+ATR>0.20%做多 - 标普欧盘超卖"
    },
    # 15. US500 H1 europe RSI<35 ATR>0.20%
    {
        "id": "h1_us500_europe_rsi35_atr020",
        "timeframe": "H1",
        "symbols": ["US500"],
        "entry_condition": "session == 'europe' and rsi14 < 35 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "US500 H1 欧盘+RSI<35+ATR>0.20%做多 - 标普宽松版扩样本"
    },
    # 16. US30 H1 europe RSI<30 ATR>0.20%
    {
        "id": "h1_us30_europe_rsi30_atr020",
        "timeframe": "H1",
        "symbols": ["US30"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "US30 H1 欧盘+RSI<30+ATR>0.20%做多 - 道指欧盘超卖"
    },
    # 17. US30 H1 europe RSI<35 ATR>0.20%
    {
        "id": "h1_us30_europe_rsi35_atr020",
        "timeframe": "H1",
        "symbols": ["US30"],
        "entry_condition": "session == 'europe' and rsi14 < 35 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "US30 H1 欧盘+RSI<35+ATR>0.20%做多 - 道指宽松版"
    },
    # 18. H1 BB lower + RSI<30 cross-symbol (HK50, UKOIL, USTEC)
    {
        "id": "h1_bb_lower_cross",
        "timeframe": "H1",
        "symbols": ["HK50", "UKOIL", "USTEC"],
        "entry_condition": "close < bb_lower and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 BB下轨+RSI<30+ATR>0.20%做多 (HK50/UKOIL/USTEC) - BB增强跨品种"
    },
    # 19. H1 XAUUSD BB lower + asia session
    {
        "id": "h1_xau_asia_bb_lower_rsi40_atr020",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'asia' and close < bb_lower and rsi14 < 40 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "XAUUSD H1 亚盘+BB下轨+RSI<40+ATR>0.20%做多 - BB+亚盘组合"
    },
    # 20. H1 asia broad RSI<30 + ATR test on all symbols
    {
        "id": "h1_asia_broad_rsi30_atr020",
        "timeframe": "H1",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": H1_HOLDS,
        "description": "H1 亚盘+RSI<30+ATR>0.20%做多 - 全品种亚盘超卖扫描"
    },

    # ═══════════════════════════════════════════════════════════════════════
    # M30 TESTS (21-40)
    # ═══════════════════════════════════════════════════════════════════════

    # 21. M30 European RSI<25 ALL symbols
    {
        "id": "m30_europe_rsi25_all",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI<25+ATR>0.20%做多 - 全品种欧盘超卖扫描"
    },
    # 22. M30 European RSI<30 ALL symbols
    {
        "id": "m30_europe_rsi30_all",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘+RSI<30+ATR>0.20%做多 - 全品种欧盘超卖宽松版"
    },
    # 23. M30 Asian RSI<25 + ATR broad
    {
        "id": "m30_asia_rsi25_all",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<25+ATR>0.20%做多 - 全品种亚盘超卖扫描"
    },
    # 24. M30 Asian RSI<30 + ATR broad
    {
        "id": "m30_asia_rsi30_all",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "session == 'asia' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘+RSI<30+ATR>0.20%做多 - 全品种亚盘超卖宽松版"
    },
    # 25. M30 Session transition (7-10 UTC) + RSI<25 long
    {
        "id": "m30_transition_7_10_rsi25_long",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 7 and hour < 10 and rsi14 < 25 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚→欧转换(7-10UTC)+RSI<25+ATR>0.20%做多 - 全品种晨盘超卖"
    },
    # 26. M30 Session transition (7-10 UTC) + RSI>70 short
    {
        "id": "m30_transition_7_10_rsi70_short",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 7 and hour < 10 and rsi14 > 70 and atr14 / close > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚→欧转换(7-10UTC)+RSI>70+ATR>0.20%做空 - 全品种晨盘超买"
    },
    # 27. M30 Consecutive bear >=3 + RSI<30 + europe
    {
        "id": "m30_bear3_europe_rsi30",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "consecutive_bear_count >= 3 and rsi14 < 30 and session == 'europe' and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘连续3阴+RSI<30+ATR>0.20%做多 - 欧盘超卖衰竭"
    },
    # 28. M30 Consecutive bear >=3 + RSI<30 + asia
    {
        "id": "m30_bear3_asia_rsi30",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "consecutive_bear_count >= 3 and rsi14 < 30 and session == 'asia' and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 亚盘连续3阴+RSI<30+ATR>0.20%做多 - 亚盘超卖衰竭"
    },
    # 29. M30 BB lower + RSI<30 (new symbols: HK50, UKOIL, XAGUSD)
    {
        "id": "m30_bb_lower_rsi30_new",
        "timeframe": "M30",
        "symbols": ["HK50", "UKOIL", "XAGUSD", "USTEC"],
        "entry_condition": "close < bb_lower and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 BB下轨+RSI<30+ATR>0.20%做多 (HK50/UKOIL/XAGUSD/USTEC) - BB信号验证"
    },
    # 30. M30 Hour-specific 8-12UTC (European open) + RSI<25
    {
        "id": "m30_hour_8_12_rsi25",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 8 and hour < 12 and rsi14 < 25 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘开盘(8-12UTC)+RSI<25+ATR>0.20%做多 - 全品种欧盘开盘超卖"
    },
    # 31. M30 Hour-specific 12-16UTC (European afternoon) + RSI>70 short
    {
        "id": "m30_hour_12_16_rsi70_short",
        "timeframe": "M30",
        "symbols": ALL_SYMBOLS,
        "entry_condition": "hour >= 12 and hour < 16 and rsi14 > 70 and atr14 / close > 0.0020",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "M30 欧盘下午(12-16UTC)+RSI>70+ATR>0.20%做空 - 全品种午后超买修正"
    },
    # 32. M30 XAUUSD europe RSI<25 ATR>0.30%
    {
        "id": "m30_xau_europe_rsi25_atr030",
        "timeframe": "M30",
        "symbols": ["XAUUSD"],
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr14 / close > 0.0030",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "XAUUSD M30 欧盘+RSI<25+ATR>0.30%做多 - 黄金M30欧盘超卖"
    },
    # 33. M30 JP225 europe RSI<25 ATR>0.35%
    {
        "id": "m30_jp225_europe_rsi25_atr035",
        "timeframe": "M30",
        "symbols": ["JP225"],
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr14 / close > 0.0035",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "JP225 M30 欧盘+RSI<25+ATR>0.35%做多 - 日经M30欧盘超卖验证"
    },
    # 34. M30 US500 europe RSI<30 ATR>0.20%
    {
        "id": "m30_us500_europe_rsi30_atr020",
        "timeframe": "M30",
        "symbols": ["US500"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "US500 M30 欧盘+RSI<30+ATR>0.20%做多 - 标普M30欧盘验证纯欧盘信号"
    },
    # 35. M30 XAGUSD asia RSI<30 ATR>0.30%
    {
        "id": "m30_xag_asia_rsi30_atr030",
        "timeframe": "M30",
        "symbols": ["XAGUSD"],
        "entry_condition": "session == 'asia' and rsi14 < 30 and atr14 / close > 0.0030",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "XAGUSD M30 亚盘+RSI<30+ATR>0.30%做多 - 白银M30亚盘超卖"
    },
    # 36. M30 GBPUSD europe RSI>70 ATR>0.15% short
    {
        "id": "m30_gbp_europe_rsi70_atr015_short",
        "timeframe": "M30",
        "symbols": ["GBPUSD"],
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr14 / close > 0.0015",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "GBPUSD M30 欧盘+RSI>70+ATR>0.15%做空 - 英镑M30欧盘超买"
    },
    # 37. M30 EURUSD europe RSI>70 ATR>0.10% short
    {
        "id": "m30_eur_europe_rsi70_atr010_short",
        "timeframe": "M30",
        "symbols": ["EURUSD"],
        "entry_condition": "session == 'europe' and rsi14 > 70 and atr14 / close > 0.0010",
        "direction": "short",
        "hold_periods": M30_HOLDS,
        "description": "EURUSD M30 欧盘+RSI>70+ATR>0.10%做空 - 欧元M30欧盘超买"
    },
    # 38. M30 US30 europe RSI<30 ATR>0.20%
    {
        "id": "m30_us30_europe_rsi30_atr020",
        "timeframe": "M30",
        "symbols": ["US30"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "US30 M30 欧盘+RSI<30+ATR>0.20%做多 - 道指M30欧盘超卖验证"
    },
    # 39. M30 USTEC europe RSI<30 ATR>0.20%
    {
        "id": "m30_ustec_europe_rsi30_atr020",
        "timeframe": "M30",
        "symbols": ["USTEC"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "USTEC M30 欧盘+RSI<30+ATR>0.20%做多 - 纳指M30欧盘超卖验证"
    },
    # 40. M30 HK50 europe RSI<30 ATR>0.20%
    {
        "id": "m30_hk50_europe_rsi30_atr020",
        "timeframe": "M30",
        "symbols": ["HK50"],
        "entry_condition": "session == 'europe' and rsi14 < 30 and atr14 / close > 0.0020",
        "direction": "long",
        "hold_periods": M30_HOLDS,
        "description": "HK50 M30 欧盘+RSI<30+ATR>0.20%做多 - 恒指M30欧盘超卖验证"
    },
]

# ── Main execution ──────────────────────────────────────────────────────────

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
    print("=" * 75)
    print("  Round 61 — European/Asian Session Pattern Mining")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Total tests: {len(TESTS)}")
    print("=" * 75)

    all_results = {}
    test_seq = 0

    for test in TESTS:
        test_seq += 1
        print(f"\n{'─' * 75}")
        print(f"\n[{test_seq:>2}/{len(TESTS)}] {test['id']}: {test['description']}")
        print(f"  Timeframe: {test['timeframe']}  Direction: {test['direction']}")
        print(f"  Condition: {test['entry_condition']}")
        print(f"  Symbols: {test['symbols']}")

        t0 = time.time()
        data = load_and_compute(test["timeframe"], test["symbols"],
                                progress_label=test["id"])
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
    out_path = LOGS_DIR / "round61_researcher_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n{'=' * 75}")
    print(f"Raw results saved to {out_path}")

    # ── Summary of top findings ──
    findings = extract_top_findings(all_results)
    print(f"\n{'=' * 75}")
    print(f"  TOP FINDINGS (WR >= 60%, n >= 30)")
    print(f"  Total: {len(findings)} signals")
    print(f"{'=' * 75}")

    if findings:
        # Group by test for readability
        from collections import defaultdict
        by_test = defaultdict(list)
        for f in findings:
            by_test[f["test_id"]].append(f)

        for test_id, sigs in sorted(by_test.items()):
            print(f"\n  [{test_id}]")
            for s in sigs[:5]:  # top 5 per test
                wr_pct = s["win_rate"] * 100
                avg_ret_pct = (s["avg_return"] or 0) * 100
                sharpe = s["sharpe_ratio"] or 0
                print(f"    {s['symbol']:10s} hold={s['hold_period']:>2}  "
                      f"n={s['signal_count']:>4}  WR={wr_pct:>5.1f}%  "
                      f"avg_ret={avg_ret_pct:>+6.2f}%  Sharpe={sharpe:>5.2f}")

        # Top 10 overall
        print(f"\n  {'─' * 60}")
        print(f"  TOP 10 SIGNALS OVERALL")
        print(f"  {'─' * 60}")
        for i, s in enumerate(findings[:10]):
            wr_pct = s["win_rate"] * 100
            avg_ret_pct = (s["avg_return"] or 0) * 100
            sharpe = s["sharpe_ratio"] or 0
            print(f"  #{i+1:>2}. {s['symbol']:10s} | {s['test_id']:35s} | "
                  f"hold={s['hold_period']:>2} | n={s['signal_count']:>4} | "
                  f"WR={wr_pct:>5.1f}% | avg={avg_ret_pct:>+5.2f}% | "
                  f"Sharpe={sharpe:>4.2f}")

        # Recommendation
        print(f"\n  {'=' * 60}")
        print(f"  RECOMMENDATIONS")
        print(f"  {'=' * 60}")

        # Best injectable (n>=150)
        injectable = [s for s in findings if s["signal_count"] >= 150]
        if injectable:
            print(f"\n  ★ Injectable signals (n >= 150):")
            for s in injectable[:5]:
                wr_pct = s["win_rate"] * 100
                print(f"    {s['symbol']:10s} | {s['test_id']:35s} | "
                      f"hold={s['hold_period']:>2} | n={s['signal_count']:>4} | WR={wr_pct:>5.1f}%")

        # Strongest signals (WR>=70%, n>=50)
        strong = [s for s in findings if s["win_rate"] >= 0.70 and s["signal_count"] >= 50]
        if strong:
            print(f"\n  ★ Strong signals (WR >= 70%, n >= 50):")
            for s in strong[:10]:
                wr_pct = s["win_rate"] * 100
                print(f"    {s['symbol']:10s} | {s['test_id']:35s} | "
                      f"hold={s['hold_period']:>2} | n={s['signal_count']:>4} | WR={wr_pct:>5.1f}%")

    else:
        print("\n  No findings meeting WR>=60% and n>=30 criteria.")

    print(f"\n{'=' * 75}")
    print(f"  Round 61 completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 75}")

if __name__ == "__main__":
    main()
