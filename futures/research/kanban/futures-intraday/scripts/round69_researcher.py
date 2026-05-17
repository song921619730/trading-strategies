#!/usr/bin/env python3
"""
round69_researcher.py — Round 69 H1/M30 CB+RSI Pattern Researcher

Loads H1 and M30 parquet data for 14 core symbols, computes technical indicators,
and scans for CB (Consecutive Bear/Bull) + RSI combo patterns across multiple
thresholds and hold periods. Focuses on European and Asian sessions.

Saves results to ../logs/round69_researcher_results.json
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd

# ── Setup ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"
STATE_DIR = PROJECT_DIR / "state"
REPORTS_DIR = PROJECT_DIR / "reports"

sys.path.insert(0, str(SCRIPT_DIR))
from data_loader import load_data, compute_indicators

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(str(LOGS_DIR / "round69_researcher.log"))],
)
log = logging.getLogger("round69_researcher")
log.info("=" * 60)
log.info("Round 69 H1/M30 CB+RSI Pattern Researcher")
log.info("=" * 60)

# ── Constants ────────────────────────────────────────────────────────────
CORE_SYMBOLS = [
    "XAUUSD", "XAGUSD", "USTEC", "US30", "US500",
    "JP225", "HK50", "USOIL", "UKOIL",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
]

H1_HOLD_PERIODS = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50, 60, 80]
M30_HOLD_PERIODS = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50, 60, 80, 100]

# Session definitions (UTC hour ranges)
SESSION_RANGES = {
    "asia": (0, 7),
    "europe": (8, 15),
    "us": (16, 23),
}

# Condition configurations
RSI_OVERSOLD_THRESHOLDS = {"rsi14": [15, 18, 20, 22, 25, 28, 30],
                            "rsi9": [15, 18, 20, 25, 30],
                            "rsi7": [15, 18, 20, 25, 30]}

CB_MIN_THRESHOLDS = [1, 2, 3, 4, 5]

PURE_CB_THRESHOLDS = [2, 3, 4, 5, 6, 7]

SHORT_CB_THRESHOLDS = [2, 3, 4, 5]
SHORT_RSI_OVERBOUGHT = {"rsi14": [70, 75, 80], "rsi9": [70, 75, 80]}

EU_OPEN_HOURS = [8, 9]
EU_RSI_THRESHOLDS = {"rsi14": [20, 25, 30, 35, 40]}


# ══════════════════════════════════════════════════════════════════════════
# 1. Data Loading & Indicator Computation
# ══════════════════════════════════════════════════════════════════════════

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lowercase for indicator engine."""
    df = df.copy()
    rename_map = {c: c.lower() for c in df.columns}
    df.rename(columns=rename_map, inplace=True)
    return df


def add_custom_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add consecutive bull/bear counts, session labels, forward returns."""
    df = df.copy()

    # Consecutive bull/bear counts
    bull = (df["close"] > df["open"]).astype(int)
    bear = (df["close"] < df["open"]).astype(int)

    bull_groups = (bull != bull.shift()).cumsum()
    bear_groups = (bear != bear.shift()).cumsum()

    df["consecutive_bull"] = bull.groupby(bull_groups).cumsum()
    df["consecutive_bear"] = bear.groupby(bear_groups).cumsum()

    # Reset both to 0 on doji (close == open)
    doji_mask = (df["close"] == df["open"]).values
    df.loc[doji_mask, "consecutive_bull"] = 0
    df.loc[doji_mask, "consecutive_bear"] = 0

    # Session labels (overriding the internal one to match spec)
    hour = df.index.hour if isinstance(df.index, pd.DatetimeIndex) else df["hour"]
    df["session_label"] = "us"  # default
    df.loc[hour < 8, "session_label"] = "asia"
    df.loc[(hour >= 8) & (hour < 16), "session_label"] = "europe"
    df.loc[hour >= 16, "session_label"] = "us"

    return df


def compute_forward_returns(df: pd.DataFrame, hold_periods: List[int]) -> pd.DataFrame:
    """Compute forward returns for multiple hold periods (in bars)."""
    df = df.copy()
    for h in hold_periods:
        df[f"fwd_return_{h}"] = df["close"].pct_change(h).shift(-h) * 100
    return df


def load_and_prepare(timeframe: str, symbols: List[str], hold_periods: List[int]) -> Dict[str, pd.DataFrame]:
    """Load data, compute indicators, add custom features for given timeframe."""
    log.info(f"Loading {timeframe} data for {len(symbols)} symbols...")
    raw_data = load_data(timeframe, symbols)
    result = {}
    for sym in symbols:
        if sym not in raw_data:
            log.warning(f"  {sym}: no data found, skipping")
            continue
        df = raw_data[sym]
        log.info(f"  {sym}: {len(df)} rows, {df.index.min()} to {df.index.max()}")

        # Normalize columns
        df = normalize_columns(df)

        # Compute indicators (RSI, ATR, BB, etc.) + time features
        df = compute_indicators(df)

        # Add custom indicators
        df = add_custom_indicators(df)

        # Compute forward returns
        df = compute_forward_returns(df, hold_periods)

        result[sym] = df
        log.info(f"    -> {len(df)} rows × {len(df.columns)} cols after prep")
    return result


# ══════════════════════════════════════════════════════════════════════════
# 2. Pattern Condition Testing
# ══════════════════════════════════════════════════════════════════════════

def test_pure_rsi_oversold(
    df: pd.DataFrame, sym: str, tf: str, hold_periods: List[int]
) -> List[dict]:
    """Test pure RSI oversold conditions (long signals)."""
    results = []
    sessions = ["asia", "europe", "us", "all"]

    for session in sessions:
        if session == "all":
            mask = pd.Series(True, index=df.index)
        else:
            mask = df["session_label"] == session

        for rsi_col, thresholds in RSI_OVERSOLD_THRESHOLDS.items():
            if rsi_col not in df.columns:
                continue
            for thr in thresholds:
                cond_mask = mask & (df[rsi_col] < thr) & (df[rsi_col].notna())
                signal_idx = cond_mask[cond_mask].index
                n_signals = len(signal_idx)

                if n_signals < 5:
                    continue

                for h in hold_periods:
                    fwd_col = f"fwd_return_{h}"
                    if fwd_col not in df.columns:
                        continue
                    fwd_vals = df.loc[signal_idx, fwd_col].dropna()
                    if len(fwd_vals) < 5:
                        continue

                    wins = (fwd_vals > 0).sum()
                    total = len(fwd_vals)
                    wr = wins / total
                    avg_ret = fwd_vals.mean()
                    std_ret = fwd_vals.std()
                    sharpe = avg_ret / std_ret if std_ret > 1e-10 else 0.0

                    results.append({
                        "condition_type": "pure_rsi_oversold",
                        "symbol": sym,
                        "timeframe": tf,
                        "session": session,
                        "rsi_column": rsi_col,
                        "rsi_threshold": thr,
                        "hold_period": h,
                        "direction": "long",
                        "signal_count": total,
                        "win_rate": round(wr, 4),
                        "avg_return": round(avg_ret, 6),
                        "sharpe_ratio": round(sharpe, 4),
                        "wins": int(wins),
                    })
    return results


def test_cb_rsi_combo(
    df: pd.DataFrame, sym: str, tf: str, hold_periods: List[int]
) -> List[dict]:
    """Test CB + RSI combo conditions (long signals)."""
    results = []
    sessions = ["asia", "europe", "us", "all"]

    for session in sessions:
        if session == "all":
            mask = pd.Series(True, index=df.index)
        else:
            mask = df["session_label"] == session

        for cb_min in CB_MIN_THRESHOLDS:
            cb_col = "consecutive_bear"
            for rsi_col, thresholds in RSI_OVERSOLD_THRESHOLDS.items():
                if rsi_col not in df.columns:
                    continue
                for thr in thresholds:
                    cond_mask = (
                        mask
                        & (df[cb_col] >= cb_min)
                        & (df[rsi_col] < thr)
                        & (df[rsi_col].notna())
                        & (df[cb_col].notna())
                    )
                    signal_idx = cond_mask[cond_mask].index
                    n_signals = len(signal_idx)

                    if n_signals < 5:
                        continue

                    for h in hold_periods:
                        fwd_col = f"fwd_return_{h}"
                        if fwd_col not in df.columns:
                            continue
                        fwd_vals = df.loc[signal_idx, fwd_col].dropna()
                        if len(fwd_vals) < 5:
                            continue

                        wins = (fwd_vals > 0).sum()
                        total = len(fwd_vals)
                        wr = wins / total
                        avg_ret = fwd_vals.mean()
                        std_ret = fwd_vals.std()
                        sharpe = avg_ret / std_ret if std_ret > 1e-10 else 0.0

                        results.append({
                            "condition_type": "cb_rsi_combo",
                            "symbol": sym,
                            "timeframe": tf,
                            "session": session,
                            "rsi_column": rsi_col,
                            "rsi_threshold": thr,
                            "consecutive_bear_min": cb_min,
                            "hold_period": h,
                            "direction": "long",
                            "signal_count": total,
                            "win_rate": round(wr, 4),
                            "avg_return": round(avg_ret, 6),
                            "sharpe_ratio": round(sharpe, 4),
                            "wins": int(wins),
                        })
    return results


def test_pure_cb(
    df: pd.DataFrame, sym: str, tf: str, hold_periods: List[int]
) -> List[dict]:
    """Test pure consecutive bear conditions (long signals)."""
    results = []
    sessions = ["asia", "europe", "us", "all"]

    for session in sessions:
        if session == "all":
            mask = pd.Series(True, index=df.index)
        else:
            mask = df["session_label"] == session

        for cb_min in PURE_CB_THRESHOLDS:
            cb_col = "consecutive_bear"
            cond_mask = (
                mask
                & (df[cb_col] >= cb_min)
                & (df[cb_col].notna())
            )
            signal_idx = cond_mask[cond_mask].index
            n_signals = len(signal_idx)

            if n_signals < 5:
                continue

            for h in hold_periods:
                fwd_col = f"fwd_return_{h}"
                if fwd_col not in df.columns:
                    continue
                fwd_vals = df.loc[signal_idx, fwd_col].dropna()
                if len(fwd_vals) < 5:
                    continue

                wins = (fwd_vals > 0).sum()
                total = len(fwd_vals)
                wr = wins / total
                avg_ret = fwd_vals.mean()
                std_ret = fwd_vals.std()
                sharpe = avg_ret / std_ret if std_ret > 1e-10 else 0.0

                results.append({
                    "condition_type": "pure_cb",
                    "symbol": sym,
                    "timeframe": tf,
                    "session": session,
                    "consecutive_bear_min": cb_min,
                    "hold_period": h,
                    "direction": "long",
                    "signal_count": total,
                    "win_rate": round(wr, 4),
                    "avg_return": round(avg_ret, 6),
                    "sharpe_ratio": round(sharpe, 4),
                    "wins": int(wins),
                })
    return results


def test_short_conditions(
    df: pd.DataFrame, sym: str, tf: str, hold_periods: List[int]
) -> List[dict]:
    """Test short conditions: consecutive_bull + RSI overbought."""
    results = []
    sessions = ["asia", "europe", "us", "all"]

    for session in sessions:
        if session == "all":
            mask = pd.Series(True, index=df.index)
        else:
            mask = df["session_label"] == session

        for cb_min in SHORT_CB_THRESHOLDS:
            cb_col = "consecutive_bull"
            for rsi_col, thresholds in SHORT_RSI_OVERBOUGHT.items():
                if rsi_col not in df.columns:
                    continue
                for thr in thresholds:
                    cond_mask = (
                        mask
                        & (df[cb_col] >= cb_min)
                        & (df[rsi_col] > thr)
                        & (df[rsi_col].notna())
                        & (df[cb_col].notna())
                    )
                    signal_idx = cond_mask[cond_mask].index
                    n_signals = len(signal_idx)

                    if n_signals < 5:
                        continue

                    for h in hold_periods:
                        fwd_col = f"fwd_return_{h}"
                        if fwd_col not in df.columns:
                            continue
                        fwd_vals = df.loc[signal_idx, fwd_col].dropna()
                        if len(fwd_vals) < 5:
                            continue

                        # For short: negative forward return = win
                        wins = (fwd_vals < 0).sum()
                        total = len(fwd_vals)
                        wr = wins / total
                        avg_ret = -fwd_vals.mean()  # positive = good for short
                        std_ret = fwd_vals.std()
                        sharpe = (-fwd_vals.mean()) / std_ret if std_ret > 1e-10 else 0.0

                        results.append({
                            "condition_type": "short_cb_rsi",
                            "symbol": sym,
                            "timeframe": tf,
                            "session": session,
                            "rsi_column": rsi_col,
                            "rsi_threshold": thr,
                            "consecutive_bull_min": cb_min,
                            "hold_period": h,
                            "direction": "short",
                            "signal_count": total,
                            "win_rate": round(wr, 4),
                            "avg_return": round(-fwd_vals.mean(), 6),
                            "sharpe_ratio": round(sharpe, 4),
                            "wins": int(wins),
                        })
    return results


def test_eu_open_focus(
    df: pd.DataFrame, sym: str, tf: str, hold_periods: List[int]
) -> List[dict]:
    """Test EU open hour focus (hour 8, 9) with RSI oversold."""
    results = []

    if "hour" not in df.columns:
        return results

    for hour in EU_OPEN_HOURS:
        hour_mask = df["hour"] == hour

        for rsi_col, thresholds in EU_RSI_THRESHOLDS.items():
            if rsi_col not in df.columns:
                continue
            for thr in thresholds:
                cond_mask = (
                    hour_mask
                    & (df[rsi_col] < thr)
                    & (df[rsi_col].notna())
                )
                signal_idx = cond_mask[cond_mask].index
                n_signals = len(signal_idx)

                if n_signals < 5:
                    continue

                for h in hold_periods:
                    fwd_col = f"fwd_return_{h}"
                    if fwd_col not in df.columns:
                        continue
                    fwd_vals = df.loc[signal_idx, fwd_col].dropna()
                    if len(fwd_vals) < 5:
                        continue

                    wins = (fwd_vals > 0).sum()
                    total = len(fwd_vals)
                    wr = wins / total
                    avg_ret = fwd_vals.mean()
                    std_ret = fwd_vals.std()
                    sharpe = avg_ret / std_ret if std_ret > 1e-10 else 0.0

                    results.append({
                        "condition_type": "eu_open_rsi",
                        "symbol": sym,
                        "timeframe": tf,
                        "session": f"eu_open_h{hour}",
                        "rsi_column": rsi_col,
                        "rsi_threshold": thr,
                        "hour": hour,
                        "hold_period": h,
                        "direction": "long",
                        "signal_count": total,
                        "win_rate": round(wr, 4),
                        "avg_return": round(avg_ret, 6),
                        "sharpe_ratio": round(sharpe, 4),
                        "wins": int(wins),
                    })
    return results


def test_all_conditions(df: pd.DataFrame, sym: str, tf: str, hold_periods: List[int]) -> List[dict]:
    """Run all condition tests for a symbol/timeframe."""
    results = []
    results.extend(test_pure_rsi_oversold(df, sym, tf, hold_periods))
    results.extend(test_cb_rsi_combo(df, sym, tf, hold_periods))
    results.extend(test_pure_cb(df, sym, tf, hold_periods))
    results.extend(test_short_conditions(df, sym, tf, hold_periods))
    results.extend(test_eu_open_focus(df, sym, tf, hold_periods))
    return results


# ══════════════════════════════════════════════════════════════════════════
# 3. Cross-TF Focus: Identify symbols where both H1 and M30 have WR >= 80%
# ══════════════════════════════════════════════════════════════════════════

def find_cross_tf_winners(
    h1_results: List[dict], m30_results: List[dict]
) -> List[dict]:
    """Find conditions where both H1 and M30 have WR >= 80% for same symbol/session/condition."""
    # Index H1 results by (symbol, session, condition_type)
    h1_index = {}
    for r in h1_results:
        if r["win_rate"] >= 0.80 and r["signal_count"] >= 5:
            key = (r["symbol"], r["session"], r["condition_type"])
            if key not in h1_index or r["win_rate"] > h1_index[key]["win_rate"]:
                h1_index[key] = r

    m30_index = {}
    for r in m30_results:
        if r["win_rate"] >= 0.80 and r["signal_count"] >= 5:
            key = (r["symbol"], r["session"], r["condition_type"])
            if key not in m30_index or r["win_rate"] > m30_index[key]["win_rate"]:
                m30_index[key] = r

    # Find common keys
    cross_tf = []
    common_keys = set(h1_index.keys()) & set(m30_index.keys())
    for key in common_keys:
        cross_tf.append({
            "symbol": key[0],
            "session": key[1],
            "condition_type": key[2],
            "h1": h1_index[key],
            "m30": m30_index[key],
        })
    return cross_tf


# ══════════════════════════════════════════════════════════════════════════
# 4. Main Pipeline
# ══════════════════════════════════════════════════════════════════════════

def run_pipeline():
    t_start = time.time()

    # ── Step 1: Load & Prepare Data ──
    log.info("Step 1: Loading H1 data...")
    h1_data = load_and_prepare("H1", CORE_SYMBOLS, H1_HOLD_PERIODS)
    log.info(f"  H1 data loaded: {len(h1_data)} symbols")

    log.info("Step 2: Loading M30 data...")
    m30_data = load_and_prepare("M30", CORE_SYMBOLS, M30_HOLD_PERIODS)
    log.info(f"  M30 data loaded: {len(m30_data)} symbols")

    # ── Step 2: Test Conditions ──
    log.info("Step 3: Testing conditions on H1...")
    all_h1_results = []
    for sym, df in h1_data.items():
        results = test_all_conditions(df, sym, "H1", H1_HOLD_PERIODS)
        all_h1_results.extend(results)
        log.info(f"  H1 {sym}: {len(results)} conditions tested")

    log.info("Step 4: Testing conditions on M30...")
    all_m30_results = []
    for sym, df in m30_data.items():
        results = test_all_conditions(df, sym, "M30", M30_HOLD_PERIODS)
        all_m30_results.extend(results)
        log.info(f"  M30 {sym}: {len(results)} conditions tested")

    all_results = all_h1_results + all_m30_results
    log.info(f"Total raw conditions tested: {len(all_results)}")

    # ── Step 3: Find Cross-TF Winners ──
    log.info("Step 5: Finding cross-TF winners...")
    cross_tf_winners = find_cross_tf_winners(all_h1_results, all_m30_results)
    log.info(f"  Cross-TF winners found: {len(cross_tf_winners)}")

    # ── Step 4: Filter and compute summaries ──
    log.info("Step 6: Computing summaries...")

    # Filter: keep only conditions with n >= 5 signals
    filtered = [r for r in all_results if r["signal_count"] >= 5]

    # Qualified: WR >= 70% AND n >= 10
    qualified = [r for r in filtered if r["win_rate"] >= 0.70 and r["signal_count"] >= 10]

    # Elite: WR >= 85% AND n >= 10
    elite = [r for r in filtered if r["win_rate"] >= 0.85 and r["signal_count"] >= 10]

    # Top 20 patterns per TF
    h1_qualified = [r for r in qualified if r["timeframe"] == "H1"]
    m30_qualified = [r for r in qualified if r["timeframe"] == "M30"]

    h1_top20 = sorted(h1_qualified, key=lambda x: (-x["win_rate"], -x["signal_count"]))[:20]
    m30_top20 = sorted(m30_qualified, key=lambda x: (-x["win_rate"], -x["signal_count"]))[:20]

    # Session distribution
    session_dist = {}
    for r in filtered:
        sess = r["session"]
        session_dist[sess] = session_dist.get(sess, 0) + 1

    qualified_session_dist = {}
    for r in qualified:
        sess = r["session"]
        qualified_session_dist[sess] = qualified_session_dist.get(sess, 0) + 1

    # ── Step 5: Build output ──
    log.info("Step 7: Building output...")

    output = {
        "metadata": {
            "round": 69,
            "name": "round69_researcher",
            "description": "H1/M30 CB+RSI Pattern Scan — Round 69",
            "symbols_tested": CORE_SYMBOLS,
            "timeframes": ["H1", "M30"],
            "h1_hold_periods": H1_HOLD_PERIODS,
            "m30_hold_periods": M30_HOLD_PERIODS,
            "data_symbols_h1": list(h1_data.keys()),
            "data_symbols_m30": list(m30_data.keys()),
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "elapsed_seconds": round(time.time() - t_start, 2),
        },
        "summary": {
            "total_conditions_tested": len(all_results),
            "filtered_n5": len(filtered),
            "qualified_wr70_n10": len(qualified),
            "elite_wr85_n10": len(elite),
            "session_distribution_all": session_dist,
            "session_distribution_qualified": qualified_session_dist,
            "cross_tf_winners_count": len(cross_tf_winners),
        },
        "top20_h1": h1_top20,
        "top20_m30": m30_top20,
        "cross_tf_winners": cross_tf_winners,
        "all_results": all_results,
    }

    # ── Save ──
    output_path = LOGS_DIR / "round69_researcher_results.json"
    log.info(f"Saving results to {output_path}...")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    log.info(f"✅ Results saved: {output_path} ({file_size_mb:.2f} MB)")

    # ── Print Summary ──
    print("\n" + "=" * 60)
    print("ROUND 69 RESEARCHER — SUMMARY")
    print("=" * 60)
    print(f"  Total conditions tested:    {len(all_results)}")
    print(f"  Filtered (n≥5):             {len(filtered)}")
    print(f"  Qualified (WR≥70%, n≥10):   {len(qualified)}")
    print(f"  Elite (WR≥85%, n≥10):       {len(elite)}")
    print(f"  Cross-TF winners:           {len(cross_tf_winners)}")
    print(f"  Elapsed:                    {output['metadata']['elapsed_seconds']:.1f}s")
    print()
    print("─" * 60)
    print("Top 20 H1 Patterns:")
    print("─" * 60)
    for i, p in enumerate(h1_top20, 1):
        print(f"  {i:2d}. [{p['symbol']:6s}] {p['condition_type']:18s} sess={p['session']:8s} "
              f"hold={p['hold_period']:3d} WR={p['win_rate']:.1%} n={p['signal_count']:4d} "
              f"avg_ret={p['avg_return']:.4f} sharpe={p['sharpe_ratio']:.2f}")

    print()
    print("─" * 60)
    print("Top 20 M30 Patterns:")
    print("─" * 60)
    for i, p in enumerate(m30_top20, 1):
        print(f"  {i:2d}. [{p['symbol']:6s}] {p['condition_type']:18s} sess={p['session']:8s} "
              f"hold={p['hold_period']:3d} WR={p['win_rate']:.1%} n={p['signal_count']:4d} "
              f"avg_ret={p['avg_return']:.4f} sharpe={p['sharpe_ratio']:.2f}")

    print()
    print("─" * 60)
    print("Session Distribution (Qualified):")
    print("─" * 60)
    for sess, count in sorted(qualified_session_dist.items()):
        print(f"  {sess:10s}: {count} conditions")

    print()
    print("─" * 60)
    print("Cross-TF Winners (both H1 & M30 WR≥80%):")
    print("─" * 60)
    for cw in cross_tf_winners:
        print(f"  [{cw['symbol']:6s}] {cw['condition_type']:18s} sess={cw['session']:8s} "
              f"H1: WR={cw['h1']['win_rate']:.1%} n={cw['h1']['signal_count']} "
              f"M30: WR={cw['m30']['win_rate']:.1%} n={cw['m30']['signal_count']}")

    print()
    print("=" * 60)
    print(f"DONE — {output_path}")
    print("=" * 60)

    return output


# ══════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_pipeline()
