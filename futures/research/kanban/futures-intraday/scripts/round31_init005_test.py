#!/usr/bin/env python3
"""
Round 31 — Hypothesis init_005 Test
D1 MA20上下方对H1开盘方向的影响

Strategy:
  - Long: When D1 close is above D1 MA20 (d1_close_above_ma20 == 1)
  - Short: When D1 close is below D1 MA20 (d1_close_above_ma20 == 0)
  - Entry at close of H1 candle when condition is true
  - Hold periods: [1, 3, 5, 8, 10, 15, 20]
  
Fix: Drop NaN weekend rows from daily data before computing MA20.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_loader import compute_indicators, load_data, resample_to_daily

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TIMEFRAME = "H1"
SYMBOLS = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCHF", "USOIL", "UKOIL", "USTEC",
    "US30", "US500", "JP225", "HK50",
]
HOLD_PERIODS = [1, 3, 5, 8, 10, 15, 20]
PERIODS_PER_YEAR = 6_000  # H1

# ---------------------------------------------------------------------------
# Stats helper
# ---------------------------------------------------------------------------
def compute_stats(returns):
    n = len(returns)
    if n == 0:
        return {"signal_count": 0, "avg_return": None, "win_rate": None,
                "sharpe_ratio": None, "max_drawdown": None}
    avg_ret = float(np.mean(returns))
    win_rate = float(np.mean(returns > 0))
    std_ret = float(np.std(returns, ddof=0))
    sharpe = (avg_ret / std_ret * np.sqrt(PERIODS_PER_YEAR)) if std_ret > 0 else 0.0
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    max_dd = float(np.max(drawdown))
    return {"signal_count": n, "avg_return": avg_ret, "win_rate": win_rate,
            "sharpe_ratio": sharpe, "max_drawdown": max_dd}

# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
def run_backtest(df, direction, hold_periods):
    n = len(df)
    close_arr = df["close"].values
    open_arr = df["open"].values

    if direction == "long":
        mask = df["d1_close_above_ma20"].values.astype(bool)
    else:
        mask = (~df["d1_close_above_ma20"].values).astype(bool)

    dir_sign = 1.0 if direction == "long" else -1.0
    signal_indices = np.where(mask)[0]

    if len(signal_indices) == 0:
        return {hp: compute_stats(np.array([])) for hp in hold_periods}

    results = {}
    for hp in hold_periods:
        ret_list = []
        for i in signal_indices:
            entry_price = close_arr[i]
            exit_idx = i + hp
            if exit_idx >= n:
                continue
            exit_price = close_arr[exit_idx]
            ret = (exit_price - entry_price) / entry_price * dir_sign
            ret_list.append(ret)
        results[hp] = compute_stats(np.array(ret_list, dtype=np.float64))
    return results


# ---------------------------------------------------------------------------
# Prepare D1 context
# ---------------------------------------------------------------------------
def add_d1_context(df_h1):
    """
    Add a 'd1_close_above_ma20' column to the H1 DataFrame.
    
    1. Resample H1 → daily
    2. Drop weekend NaN rows
    3. Compute D1 MA20
    4. Shift by 1 (use yesterday's signal for today's H1 bars)
    5. Map back to H1 by date
    """
    # Resample to daily
    df_daily = resample_to_daily(df_h1)
    
    # Drop rows where close is NaN (weekends / non-trading days)
    df_daily = df_daily.dropna(subset=["close"]).copy()
    
    # Compute D1 MA20 (20-day simple moving average)
    df_daily["d1_ma20"] = df_daily["close"].rolling(window=20, min_periods=20).mean()
    
    # Close above MA20?
    df_daily["d1_close_above_ma20"] = (df_daily["close"] > df_daily["d1_ma20"]).astype(int)
    
    # Shift by 1: yesterday's close-vs-MA20 status → today's H1 bars
    df_daily["d1_close_above_ma20_shifted"] = df_daily["d1_close_above_ma20"].shift(1)
    
    # Drop NaN from shift (first row) and from missing MA20 (first 20 days)
    df_daily = df_daily.dropna(subset=["d1_close_above_ma20_shifted"])
    
    # Map to H1 by date
    df_h1 = df_h1.copy()
    df_h1["d1_close_above_ma20"] = np.nan
    
    h1_dates = df_h1.index.normalize()
    for date_val, row in df_daily.iterrows():
        # date_val has time component, h1_dates has same
        mask = h1_dates == date_val
        df_h1.loc[mask, "d1_close_above_ma20"] = row["d1_close_above_ma20_shifted"]
    
    # Drop rows without D1 context
    df_h1 = df_h1.dropna(subset=["d1_close_above_ma20"])
    df_h1["d1_close_above_ma20"] = df_h1["d1_close_above_ma20"].astype(int)
    
    return df_h1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 100)
    print("  ROUND 31 — HYPOTHESIS init_005: D1 MA20上下方对H1开盘方向的影响")
    print("=" * 100)

    # --- 1. Load H1 data ---
    print("\n[1/4] Loading H1 data for all 14 symbols …")
    raw_data = load_data(timeframe=TIMEFRAME, symbols=SYMBOLS)
    print(f"  Loaded {len(raw_data)} symbols")

    # --- 2. Compute indicators & D1 MA20 context ---
    print("\n[2/4] Computing indicators & D1 MA20 context …")
    processed_data = {}
    for sym, df in raw_data.items():
        df_h1 = compute_indicators(df)
        df_h1 = add_d1_context(df_h1)
        processed_data[sym] = df_h1
        # Count how many Long vs Short signals
        n_above = (df_h1["d1_close_above_ma20"] == 1).sum()
        n_below = (df_h1["d1_close_above_ma20"] == 0).sum()
        pct_above = n_above / (n_above + n_below) * 100
        print(f"  {sym:<8} → {len(df_h1):>6} rows  |  D1>MA20: {n_above:>5} ({pct_above:.1f}%)  D1<MA20: {n_below:>5} ({100-pct_above:.1f}%)")

    # --- 3. Run backtests ---
    print("\n[3/4] Running backtests …")
    long_results = {}
    short_results = {}
    for sym, df in processed_data.items():
        long_results[sym] = run_backtest(df, "long", HOLD_PERIODS)
        short_results[sym] = run_backtest(df, "short", HOLD_PERIODS)

    # --- 4. Print results ---
    print("\n[4/4] Results\n")

    # ── Long: D1 above MA20 ──
    print("=" * 100)
    print("  TABLE A: D1 CLOSE ABOVE MA20 → LONG")
    print("=" * 100)
    header = f"  {'Symbol':<8}" + "".join(f"  wr(h{hp:<2})" for hp in HOLD_PERIODS)
    print(header)
    print("  " + "-" * (8 + 11 * len(HOLD_PERIODS)))

    all_long_findings = []
    for sym in SYMBOLS:
        res = long_results.get(sym, {})
        parts = [f"{sym:<8}"]
        for hp in HOLD_PERIODS:
            s = res.get(hp, {})
            cnt = s.get("signal_count", 0) or 0
            wr = s.get("win_rate", 0) or 0
            avg = s.get("avg_return", 0) or 0
            if cnt >= 30:
                parts.append(f"  {wr:.1%}({cnt:<4})")
                if wr > 0.55:
                    all_long_findings.append((sym, hp, wr, cnt, avg, s.get("sharpe_ratio", 0)))
            else:
                parts.append(f"  {'—':>9}")
        print("".join(parts))

    # ── Short: D1 below MA20 ──
    print()
    print("=" * 100)
    print("  TABLE B: D1 CLOSE BELOW MA20 → SHORT")
    print("=" * 100)
    print(header)
    print("  " + "-" * (8 + 11 * len(HOLD_PERIODS)))

    all_short_findings = []
    for sym in SYMBOLS:
        res = short_results.get(sym, {})
        parts = [f"{sym:<8}"]
        for hp in HOLD_PERIODS:
            s = res.get(hp, {})
            cnt = s.get("signal_count", 0) or 0
            wr = s.get("win_rate", 0) or 0
            avg = s.get("avg_return", 0) or 0
            if cnt >= 30:
                parts.append(f"  {wr:.1%}({cnt:<4})")
                if wr > 0.55:
                    all_short_findings.append((sym, hp, wr, cnt, avg, s.get("sharpe_ratio", 0)))
            else:
                parts.append(f"  {'—':>9}")
        print("".join(parts))

    # ── Summary statistics ──
    print("\n" + "=" * 100)
    print("  FINDINGS ANALYSIS")
    print("=" * 100)

    all_findings = [("LONG", *f) for f in all_long_findings] + [("SHORT", *f) for f in all_short_findings]
    all_findings.sort(key=lambda x: x[3], reverse=True)

    if all_findings:
        print(f"\n  {len(all_findings)} findings with win_rate > 55%:\n")
        print(f"  {'Dir':<6} {'Symbol':<8} {'Hold':<6} {'WinRate':<9} {'Sigs':<7} {'AvgRet':<10} {'Sharpe':<8}")
        print("  " + "-" * 54)
        for dir_, sym, hp, wr, cnt, avg_ret, sharpe in all_findings:
            avg_str = f"{avg_ret:.4f}" if avg_ret is not None else "N/A"
            sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"
            print(f"  {dir_:<6} {sym:<8} {hp:<6} {wr:.2%}   {cnt:<7} {avg_str:<10} {sharpe_str:<8}")
    else:
        print("\n  No findings with win_rate > 55%.")

    # Check near-threshold
    print("\n  Near-threshold (wr 52-55%) signals:")
    borderline = []
    for dir_, results_dict in [("LONG", long_results), ("SHORT", short_results)]:
        for sym in SYMBOLS:
            res = results_dict.get(sym, {})
            for hp in HOLD_PERIODS:
                s = res.get(hp, {})
                cnt = s.get("signal_count", 0) or 0
                wr = s.get("win_rate", 0) or 0
                if cnt >= 30 and 0.52 <= wr <= 0.55:
                    borderline.append((dir_, sym, hp, wr, cnt))
    if borderline:
        for dir_, sym, hp, wr, cnt in sorted(borderline, key=lambda x: x[3], reverse=True):
            print(f"    {dir_:<6} {sym:<8} hold={hp:<2}  wr={wr:.2%}  n={cnt}")
    else:
        print("    (none)")

    print("\n" + "=" * 100)
    print("  ANALYSIS SUMMARY")
    print("=" * 100)

    # Best win rates
    print(f"\n  Total long findings (wr>55%): {len(all_long_findings)}")
    print(f"  Total short findings (wr>55%): {len(all_short_findings)}")
    print(f"  Total strong signals (wr>60%): {sum(1 for f in all_findings if f[3] > 0.60)}")

    if all_findings:
        print(f"\n  ✅ {len(all_findings)} promising/borderline findings identified.")
        print("  Fatigue recommendation: maintain (0, new findings exist)")
        return {"finding": True, "strong_signals": [f for f in all_findings if f[3] > 0.60]}
    else:
        print("\n  ⚠ No promising signals found (wr <= 55%).")
        print("  Fatigue recommendation: +1 (no new finding)")
        return {"finding": False, "strong_signals": []}


if __name__ == "__main__":
    result = main()
    print("\nDone.")
