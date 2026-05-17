#!/usr/bin/env python3
"""
round70_researcher.py — Round 70 Researcher Phase 1

XAGUSD Asia + AUDUSD Asia Session Pattern Research
Uses grid_engine.run_grid() to test specific entry conditions.

FIX: The parquet data has uppercase columns (Close) with values but lowercase
columns (close) are NaN. This script normalizes column names before computing
indicators so indicators can access the right data.

Tests:
  1. XAGUSD H1/M30 Asia session CB+RSI patterns (long)
  2. AUDUSD H1 Asia session extended scan (long)
  3. XAGUSD M30 Europe session (long)

Saves results to ../logs/round70_xag_aud_results.json
Saves summary to ../logs/round70_xag_aud_summary.txt
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# ── Setup paths ───────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
LOGS_DIR = PROJECT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SCRIPT_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOGS_DIR / "round70_researcher.log")),
    ],
)
log = logging.getLogger("round70_researcher")
log.info("=" * 60)
log.info("Round 70 Researcher Phase 1 — XAGUSD Asia + AUDUSD Asia Patterns")
log.info("=" * 60)

# ── Constants ─────────────────────────────────────────────────────────────
HOLD_PERIODS = [8, 13, 15, 20, 25, 30, 40, 50, 60, 80, 100]

# ── Column normalization ─────────────────────────────────────────────────
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fix parquet files that have both uppercase and lowercase columns.
    The uppercase columns have values, lowercase are NaN.
    Normalize all column names to lowercase, picking the column with
    the most non-NaN values for each lowercased name.
    """
    df = df.copy()
    lowercase_cols = set(c.lower() for c in df.columns)

    for lc in lowercase_cols:
        matching = [c for c in df.columns if c.lower() == lc]
        if len(matching) == 1 and matching[0] == lc:
            continue  # Already lowercase, no duplicates
        # Pick the column with the most non-NaN values
        best_col = max(matching, key=lambda c: df[c].notna().sum())
        df[lc] = df[best_col].values

    # Remove duplicate columns: keep only the lowercase versions
    keep_cols = [c for c in df.columns if c.lower() == c]
    df = df[keep_cols]

    # Drop duplicate column names (keep first occurrence)
    df = df.loc[:, ~df.columns.duplicated(keep='first')]

    return df


def load_and_prepare(timeframe: str, symbols: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Load data from parquet, normalize columns, compute indicators,
    and add consecutive_bear if not already present.
    """
    from data_loader import load_data, compute_indicators

    raw_data = load_data(timeframe, symbols)
    result = {}

    for sym in symbols:
        if sym not in raw_data:
            log.warning("  %s: no data found, skipping", sym)
            continue
        df = raw_data[sym]
        log.info("  %s: %d rows, %s to %s", sym, len(df), df.index.min(), df.index.max())

        # Normalize column case
        df = normalize_columns(df)

        # Compute indicators (RSI, BB, session, hour, etc.)
        df = compute_indicators(df)

        # Ensure consecutive_bear exists
        if 'consecutive_bear' not in df.columns:
            log.info("  Adding consecutive_bear column manually")
            bull = (df["close"] > df["open"]).astype(int)
            bear = (df["close"] < df["open"]).astype(int)
            bull_groups = (bull != bull.shift()).cumsum()
            bear_groups = (bear != bear.shift()).cumsum()
            df["consecutive_bull"] = bull.groupby(bull_groups).cumsum()
            df["consecutive_bear"] = bear.groupby(bear_groups).cumsum()
            doji_mask = (df["close"] == df["open"]).values
            df.loc[doji_mask, "consecutive_bull"] = 0
            df.loc[doji_mask, "consecutive_bear"] = 0

        # Check key columns exist
        for col in ['rsi14', 'session', 'close', 'consecutive_bear', 'hour', 'bb_20_2_lower']:
            if col not in df.columns:
                log.warning("  Column '%s' missing from %s!", col, sym)
            else:
                n_valid = df[col].notna().sum()
                log.debug("  Column '%s': %d valid values", col, n_valid)

        result[sym] = df
        log.info("    -> %d rows × %d cols", len(df), len(df.columns))
    return result


# ── Condition testing using grid_engine-like logic ────────────────────────
def compute_stats(returns: np.ndarray, hold_period: int, periods_per_year: int) -> Dict[str, Any]:
    """Compute aggregate statistics from an array of per-trade returns."""
    n = len(returns)
    if n == 0:
        return {
            "signal_count": 0,
            "avg_return": None,
            "win_rate": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
        }
    avg_ret = float(returns.mean())
    win_rate = float((returns > 0).mean())
    std_ret = float(returns.std())
    if std_ret > 0 and hold_period > 0:
        sharpe = avg_ret / std_ret * np.sqrt(periods_per_year / hold_period)
    else:
        sharpe = 0.0
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    max_dd = float(drawdown.max())
    return {
        "signal_count": n,
        "avg_return": avg_ret,
        "win_rate": win_rate,
        "sharpe_ratio": float(sharpe),
        "max_drawdown": max_dd,
    }


def test_condition(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    entry_condition: str,
    direction: str,
    hold_periods: List[int],
    exit_at_close: bool = True,
) -> Dict[str, Any]:
    """
    Test an entry condition on pre-computed data.
    Uses df.eval() like grid_engine does.
    """
    periods_per_year = {"H1": 6_000, "M30": 12_000, "M5": 72_000, "M1": 360_000}.get(timeframe, 6_000)
    dir_sign = 1.0 if direction == "long" else -1.0

    n_rows = len(df)
    close_arr = df["close"].values
    open_arr = df["open"].values

    # Evaluate entry condition
    try:
        condition_mask = df.eval(entry_condition)
    except Exception as exc:
        log.error("eval('%s') failed for %s: %s", entry_condition, symbol, exc)
        return {hp: compute_stats(np.array([]), hp, periods_per_year) for hp in hold_periods}

    mask_arr = condition_mask.values.astype(bool)
    signal_indices = np.where(mask_arr)[0]

    log.info("  %s: %d signals for '%s'", symbol, len(signal_indices), entry_condition)

    if len(signal_indices) == 0:
        return {hp: compute_stats(np.array([]), hp, periods_per_year) for hp in hold_periods}

    # Compute forward returns
    period_returns: Dict[int, List[float]] = {hp: [] for hp in hold_periods}

    for i in signal_indices:
        entry_price = close_arr[i]
        for hp in hold_periods:
            exit_idx = i + hp
            if exit_idx >= n_rows:
                continue
            if exit_at_close:
                exit_price = close_arr[exit_idx]
            else:
                exit_price = open_arr[exit_idx]
            ret = (exit_price - entry_price) / entry_price * dir_sign
            period_returns[hp].append(ret)

    # Compute stats per hold period
    sym_results: Dict[int, Dict[str, Any]] = {}
    for hp in hold_periods:
        ret_arr = np.array(period_returns[hp], dtype=np.float64)
        sym_results[hp] = compute_stats(ret_arr, hp, periods_per_year)

    return sym_results


# ── Entry condition definitions ──────────────────────────────────────────
CONDITIONS: List[Dict[str, Any]] = [
    # ═══ 1a. XAGUSD H1 Asia session CB+RSI ═══
    {
        "name": "XAGUSD_H1_Asia_CB1_RSI15",
        "timeframe": "H1",
        "symbol": "XAGUSD",
        "entry_condition": "session == 'asia' and consecutive_bear >= 1 and rsi14 < 15",
    },
    {
        "name": "XAGUSD_H1_Asia_CB2_RSI20",
        "timeframe": "H1",
        "symbol": "XAGUSD",
        "entry_condition": "session == 'asia' and consecutive_bear >= 2 and rsi14 < 20",
    },
    {
        "name": "XAGUSD_H1_Asia_RSI18",
        "timeframe": "H1",
        "symbol": "XAGUSD",
        "entry_condition": "session == 'asia' and rsi14 < 18",
    },
    # ═══ 1b. XAGUSD M30 Asia session CB+RSI ═══
    {
        "name": "XAGUSD_M30_Asia_CB1_RSI15",
        "timeframe": "M30",
        "symbol": "XAGUSD",
        "entry_condition": "session == 'asia' and consecutive_bear >= 1 and rsi14 < 15",
    },
    {
        "name": "XAGUSD_M30_Asia_CB2_RSI20",
        "timeframe": "M30",
        "symbol": "XAGUSD",
        "entry_condition": "session == 'asia' and consecutive_bear >= 2 and rsi14 < 20",
    },
    {
        "name": "XAGUSD_M30_Asia_RSI18",
        "timeframe": "M30",
        "symbol": "XAGUSD",
        "entry_condition": "session == 'asia' and rsi14 < 18",
    },
    # ═══ 2a. AUDUSD H1 Asia extended scan ═══
    {
        "name": "AUDUSD_H1_Asia_RSI22_Hour4to6",
        "timeframe": "H1",
        "symbol": "AUDUSD",
        "entry_condition": "session == 'asia' and rsi14 < 22 and hour >= 4 and hour <= 6",
    },
    {
        "name": "AUDUSD_H1_Asia_CB1_RSI25",
        "timeframe": "H1",
        "symbol": "AUDUSD",
        "entry_condition": "session == 'asia' and consecutive_bear >= 1 and rsi14 < 25",
    },
    {
        "name": "AUDUSD_H1_Asia_BBlower_RSI25",
        "timeframe": "H1",
        "symbol": "AUDUSD",
        "entry_condition": "session == 'asia' and bb_20_2_lower > close and rsi14 < 25",
    },
    # ═══ 3. XAGUSD M30 Europe session ═══
    {
        "name": "XAGUSD_M30_Europe_CB1_RSI18",
        "timeframe": "M30",
        "symbol": "XAGUSD",
        "entry_condition": "session == 'europe' and consecutive_bear >= 1 and rsi14 < 18",
    },
    {
        "name": "XAGUSD_M30_Europe_RSI15",
        "timeframe": "M30",
        "symbol": "XAGUSD",
        "entry_condition": "session == 'europe' and rsi14 < 15",
    },
]


def extract_best_hold(
    sym_results: Dict[int, Dict[str, Any]]
) -> Dict[str, Any]:
    """Extract best hold period info from per-hold-period results."""
    best_by_sharpe = None
    best_sharpe = -999
    best_by_wr = None
    best_wr = -1

    for hp, stats in sym_results.items():
        if not isinstance(stats, dict):
            continue
        n = stats.get("signal_count", 0)
        if n < 3:
            continue
        sh = stats.get("sharpe_ratio")
        wr = stats.get("win_rate")
        if sh is not None and sh > best_sharpe:
            best_sharpe = sh
            best_by_sharpe = {"hold_period": int(hp), **stats}
        if wr is not None and wr > best_wr:
            best_wr = wr
            best_by_wr = {"hold_period": int(hp), **stats}

    return {
        "best_by_sharpe": best_by_sharpe,
        "best_by_win_rate": best_by_wr,
    }


def generate_summary_table(
    all_condition_results: List[Dict[str, Any]],
    elapsed: float,
) -> str:
    """Generate human-readable summary."""
    lines = []
    lines.append("=" * 72)
    lines.append("  ROUND 70 RESEARCHER PHASE 1 — XAGUSD Asia + AUDUSD Asia Patterns")
    lines.append("=" * 72)
    lines.append(f"  Generated: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"  Elapsed: {elapsed:.1f}s")
    lines.append(f"  Conditions tested: {len(CONDITIONS)}")
    lines.append(f"  Hold periods: {HOLD_PERIODS}")
    lines.append("")

    # Collect best overall across all conditions
    all_sharpe_rows = []
    all_wr_rows = []

    for cond_result in all_condition_results:
        name = cond_result["name"]
        config = cond_result["config"]
        sym_results = cond_result["results"]
        best = cond_result["best"]

        lines.append("─" * 72)
        lines.append(f"  {name}")
        lines.append(f"    {config['timeframe']} | {config['symbol']} | "
                     f"long | {config['entry_condition']}")
        lines.append("")

        sym = config["symbol"]
        if not sym_results:
            lines.append(f"    {sym}: no signals")
            lines.append("")
            continue

        lines.append(f"    {'Hold':>6} | {'n':>5} | {'WinRate':>8} | "
                     f"{'Sharpe':>7} | {'AvgRet':>10} | {'MaxDD':>8}")
        lines.append(f"    {'-'*6}-+-{'-'*5}-+-{'-'*8}-+-{'-'*7}-+-{'-'*10}-+-{'-'*8}")

        for hp in sorted(sym_results.keys(), key=int):
            s = sym_results[hp]
            n = s.get("signal_count", 0)
            if n == 0:
                continue
            wr = s.get("win_rate", 0) or 0
            sh = s.get("sharpe_ratio", 0) or 0
            avg = s.get("avg_return", 0) or 0
            dd = s.get("max_drawdown", 0) or 0
            lines.append(f"    {int(hp):>6d} | {n:>5d} | {wr:>7.1%} | "
                         f"{sh:>6.2f} | {avg:>+9.4f} | {dd:>7.2%}")

        lines.append("")
        b = best.get("best_by_sharpe")
        if b and b.get("signal_count", 0) >= 3:
            lines.append(f"    Best Sharpe  : hold={b['hold_period']:3d}  "
                         f"n={b['signal_count']:4d}  WR={b['win_rate']:.1%}  "
                         f"Sharpe={b['sharpe_ratio']:.2f}  "
                         f"AvgRet={b['avg_return']:+.4f}")
            all_sharpe_rows.append({
                "name": name,
                "condition": config['entry_condition'],
                **b,
            })
        else:
            lines.append("    Best Sharpe  : (insufficient signals)")

        b = best.get("best_by_win_rate")
        if b and b.get("signal_count", 0) >= 3:
            lines.append(f"    Best WinRate : hold={b['hold_period']:3d}  "
                         f"n={b['signal_count']:4d}  WR={b['win_rate']:.1%}  "
                         f"Sharpe={b['sharpe_ratio']:.2f}  "
                         f"AvgRet={b['avg_return']:+.4f}")
            all_wr_rows.append({
                "name": name,
                "condition": config['entry_condition'],
                **b,
            })
        else:
            lines.append("    Best WinRate : (insufficient signals)")
        lines.append("")

    # ── Overall rankings ──
    lines.append("=" * 72)
    lines.append("  OVERALL RANKINGS")
    lines.append("=" * 72)

    # By Sharpe (n>=5)
    lines.append(f"\n  Top by Sharpe (n >= 5):")
    lines.append(f"  {'Rank':>4} | {'Condition':>45} | {'Hold':>4} | "
                 f"{'n':>5} | {'WR':>7} | {'Sharpe':>7} | {'AvgRet':>9}")
    lines.append(f"  {'-'*4}-+-{'-'*45}-+-{'-'*4}-+-{'-'*5}-+-{'-'*7}-+-{'-'*7}-+-{'-'*9}")
    sorted_sharpe = sorted(all_sharpe_rows, key=lambda r: -r["sharpe_ratio"])
    for i, r in enumerate(sorted_sharpe[:10], 1):
        lines.append(f"  {i:>4d} | {r['name']:>45} | {r['hold_period']:>4d} | "
                     f"{r['signal_count']:>5d} | {r['win_rate']:>6.1%} | "
                     f"{r['sharpe_ratio']:>6.2f} | {r['avg_return']:>+8.4f}")

    # By WR (n>=10)
    lines.append(f"\n  Top by Win Rate (n >= 10):")
    lines.append(f"  {'Rank':>4} | {'Condition':>45} | {'Hold':>4} | "
                 f"{'n':>5} | {'WR':>7} | {'Sharpe':>7} | {'AvgRet':>9}")
    lines.append(f"  {'-'*4}-+-{'-'*45}-+-{'-'*4}-+-{'-'*5}-+-{'-'*7}-+-{'-'*7}-+-{'-'*9}")
    sorted_wr = sorted(all_wr_rows, key=lambda r: -r["win_rate"])
    for i, r in enumerate(sorted_wr[:10], 1):
        lines.append(f"  {i:>4d} | {r['name']:>45} | {r['hold_period']:>4d} | "
                     f"{r['signal_count']:>5d} | {r['win_rate']:>6.1%} | "
                     f"{r['sharpe_ratio']:>6.2f} | {r['avg_return']:>+8.4f}")

    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# Main Pipeline
# ══════════════════════════════════════════════════════════════════════════

def run_pipeline():
    t_start = time.time()

    # ── Step 1: Load data ──
    timeframes_needed = set(c["timeframe"] for c in CONDITIONS)
    symbols_needed = set(c["symbol"] for c in CONDITIONS)

    data_cache: Dict[str, Dict[str, pd.DataFrame]] = {}
    for tf in timeframes_needed:
        syms_for_tf = [c["symbol"] for c in CONDITIONS if c["timeframe"] == tf]
        log.info("Loading %s data for %s ...", tf, syms_for_tf)
        data_cache[tf] = load_and_prepare(tf, syms_for_tf)

    # ── Step 2: Test each condition ──
    all_condition_results: List[Dict[str, Any]] = []

    for config in CONDITIONS:
        name = config["name"]
        tf = config["timeframe"]
        sym = config["symbol"]
        entry_cond = config["entry_condition"]

        log.info("─" * 50)
        log.info("Testing: %s", name)
        log.info("  %s | %s | %s", tf, sym, entry_cond)

        df_dict = data_cache.get(tf, {})
        df = df_dict.get(sym)

        if df is None:
            log.warning("  No data for %s %s, skipping", tf, sym)
            all_condition_results.append({
                "name": name,
                "config": config,
                "results": {},
                "best": {"best_by_sharpe": None, "best_by_win_rate": None},
            })
            continue

        sym_results = test_condition(
            df=df,
            symbol=sym,
            timeframe=tf,
            entry_condition=entry_cond,
            direction="long",
            hold_periods=HOLD_PERIODS,
            exit_at_close=True,
        )

        best = extract_best_hold(sym_results)

        all_condition_results.append({
            "name": name,
            "config": config,
            "results": {str(k): v for k, v in sym_results.items()},
            "best": best,
        })

    elapsed = time.time() - t_start

    # ── Step 3: Save JSON results ──
    json_output = {
        "metadata": {
            "round": 70,
            "phase": 1,
            "name": "round70_xag_aud_researcher",
            "description": "XAGUSD Asia + AUDUSD Asia Session Pattern Research",
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "conditions_tested": len(CONDITIONS),
            "hold_periods": HOLD_PERIODS,
        },
        "conditions": [
            {
                "name": cr["name"],
                "timeframe": cr["config"]["timeframe"],
                "symbol": cr["config"]["symbol"],
                "entry_condition": cr["config"]["entry_condition"],
                "direction": "long",
                "hold_stats": cr["results"],
                "best_by_sharpe": cr["best"]["best_by_sharpe"],
                "best_by_win_rate": cr["best"]["best_by_win_rate"],
            }
            for cr in all_condition_results
        ],
        "raw_results": {
            cr["name"]: {cr["config"]["symbol"]: cr["results"]}
            for cr in all_condition_results
        },
    }

    json_path = LOGS_DIR / "round70_xag_aud_results.json"
    log.info("Saving JSON results to %s ...", json_path)
    with open(json_path, "w") as f:
        json.dump(json_output, f, indent=2, default=str)
    mb = json_path.stat().st_size / (1024 * 1024)
    log.info("✅ JSON saved: %s (%.2f MB)", json_path, mb)

    # ── Step 4: Generate and save human-readable summary ──
    summary_text = generate_summary_table(all_condition_results, elapsed)
    txt_path = LOGS_DIR / "round70_xag_aud_summary.txt"
    with open(txt_path, "w") as f:
        f.write(summary_text)
    log.info("✅ Summary saved: %s", txt_path)

    # ── Step 5: Print summary ──
    print(summary_text)

    log.info("Round 70 Researcher Phase 1 complete! Elapsed: %.1fs", elapsed)
    return json_output


if __name__ == "__main__":
    run_pipeline()
