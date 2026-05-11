#!/usr/bin/env python3
"""
round10_m30_researcher.py — Researcher Profile for Round 10
Loads M30 parquet data for 14 symbols, computes technical indicators,
saves enriched data for the Analyst, and prints a structured summary.
"""

import sys
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure scripts directory is on path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

warnings.filterwarnings("ignore", category=FutureWarning)

from data_loader import list_available_symbols, load_data

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SYMBOLS_14 = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
    "USOIL", "UKOIL", "USTEC", "US30", "US500", "JP225", "HK50",
]

PROJECT_DIR = SCRIPT_DIR.parent  # futures-intraday/
M30_DIR = PROJECT_DIR / "data" / "M30"
INDICATORS_DIR = M30_DIR / "indicators"

# ---------------------------------------------------------------------------
# 1.  Indicator computation (matching Round 10 spec)
# ---------------------------------------------------------------------------


def _session_label(hour: int) -> str:
    """Classify UTC hour per Round 10 spec.

    Asia   00:00 – 07:59 UTC
    Europe 08:00 – 12:59 UTC
    US     13:00 – 21:59 UTC
    (hours outside these ranges → 'other' if needed, but all should be covered)
    """
    if hour < 8:
        return "asia"
    if hour < 13:
        return "europe"
    if hour < 22:
        return "us"
    return "other"  # 22-23 fallback


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Simple moving average of True Range."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period).mean()


def compute_consecutive(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (consecutive_bull, consecutive_bear) counts.

    Bull: close > open (candle is green)
    Bear: close < open (candle is red)
    Doji (close == open): resets both to 0.
    """
    bull = (df["close"] > df["open"]).astype(int)
    bear = (df["close"] < df["open"]).astype(int)

    bull_groups = (bull != bull.shift()).cumsum()
    bear_groups = (bear != bear.shift()).cumsum()

    bull_cnt = bull.groupby(bull_groups).cumsum()
    bear_cnt = bear.groupby(bear_groups).cumsum()

    return bull_cnt, bear_cnt


def enrich_m30(df: pd.DataFrame) -> pd.DataFrame:
    """Add all Round-10-required indicator columns to an M30 DataFrame.

    Returns a new DataFrame with added columns (does not modify input).
    """
    df = df.copy()

    # --- Core indicators (matching Round 10 naming) ---
    df["sma_20"] = df["close"].rolling(window=20).mean()
    df["rsi_14"] = compute_rsi(df["close"], period=14)
    df["atr_14"] = compute_atr(df, period=14)
    df["atr_pct"] = df["atr_14"] / df["close"]

    # --- Temporal / session ---
    df["hour"] = df.index.hour
    df["session"] = df["hour"].apply(_session_label)

    # --- Forward return (return_1: next bar return) ---
    df["return_1"] = df["close"].pct_change().shift(-1)

    # --- Direction (bull / bear) ---
    df["direction"] = np.where(df["close"] > df["open"], "bull", "bear")

    # --- Consecutive counts ---
    bull_cnt, bear_cnt = compute_consecutive(df)
    df["consecutive_bull"] = bull_cnt
    df["consecutive_bear"] = bear_cnt

    return df


# ---------------------------------------------------------------------------
# 2.  Per-symbol statistical summary
# ---------------------------------------------------------------------------


def symbol_summary(sym: str, df: pd.DataFrame) -> dict:
    """Compute a dict of summary statistics for one symbol."""
    total = len(df)
    if total == 0:
        return {"symbol": sym, "error": "empty dataframe"}

    # Time range
    t_start = df.index[0]
    t_end = df.index[-1]

    # Bull ratio
    bull_ratio = (df["close"] > df["open"]).mean()

    # Session distribution
    session_counts = df["session"].value_counts()
    session_bull = df.groupby("session").apply(
        lambda g: (g["close"] > g["open"]).mean()
    )

    # ATR pct stats
    atr_valid = df["atr_pct"].dropna()
    if len(atr_valid) > 0:
        atr_mean = atr_valid.mean()
        atr_median = atr_valid.median()
        atr_q25 = atr_valid.quantile(0.25)
        atr_q75 = atr_valid.quantile(0.75)
    else:
        atr_mean = atr_median = atr_q25 = atr_q75 = np.nan

    # RSI stats
    rsi_valid = df["rsi_14"].dropna()
    rsi_mean = rsi_valid.mean() if len(rsi_valid) > 0 else np.nan
    rsi_median = rsi_valid.median() if len(rsi_valid) > 0 else np.nan

    # Recent 100 bars
    recent = df.tail(100)
    recent_bull = (recent["close"] > recent["open"]).mean()
    recent_rsi_min = recent["rsi_14"].min() if "rsi_14" in recent.columns else np.nan
    recent_rsi_max = recent["rsi_14"].max() if "rsi_14" in recent.columns else np.nan
    recent_atr_min = recent["atr_pct"].min() if "atr_pct" in recent.columns else np.nan
    recent_atr_max = recent["atr_pct"].max() if "atr_pct" in recent.columns else np.nan
    recent_rsi_last = recent["rsi_14"].iloc[-1] if "rsi_14" in recent.columns else np.nan

    return {
        "symbol": sym,
        "rows": total,
        "start": t_start,
        "end": t_end,
        "bull_ratio": bull_ratio,
        # Session distribution
        "session_asia": int(session_counts.get("asia", 0)),
        "session_europe": int(session_counts.get("europe", 0)),
        "session_us": int(session_counts.get("us", 0)),
        "session_other": int(session_counts.get("other", 0)),
        # Session bull ratios
        "bull_asia": session_bull.get("asia", np.nan),
        "bull_europe": session_bull.get("europe", np.nan),
        "bull_us": session_bull.get("us", np.nan),
        # ATR pct
        "atr_pct_mean": atr_mean,
        "atr_pct_median": atr_median,
        "atr_pct_q25": atr_q25,
        "atr_pct_q75": atr_q75,
        # RSI
        "rsi_mean": rsi_mean,
        "rsi_median": rsi_median,
        # Recent 100
        "recent_bull_ratio": recent_bull,
        "recent_rsi_last": recent_rsi_last,
        "recent_rsi_min": recent_rsi_min,
        "recent_rsi_max": recent_rsi_max,
        "recent_atr_pct_min": recent_atr_min,
        "recent_atr_pct_max": recent_atr_max,
    }


# ---------------------------------------------------------------------------
# 3.  Print formatted summary
# ---------------------------------------------------------------------------


def print_header(title: str):
    print()
    print("=" * 90)
    print(f"  {title}")
    print("=" * 90)


def print_section(title: str):
    print()
    print(f"  {'─' * 86}")
    print(f"  {title}")
    print(f"  {'─' * 86}")


def print_summary_table(summaries: list[dict]):
    """Print a compact per-symbol overview table."""
    print(f"\n  {'Symbol':<10} {'Rows':>8} {'Start':<20} {'End':<20} {'Bull%':>7} {'RSI_μ':>7} {'ATR%_μ':>8} {'ATR%_md':>8}")
    print(f"  {'─' * 88}")
    for s in summaries:
        if "error" in s:
            print(f"  {s['symbol']:<10}  ERROR: {s['error']}")
            continue
        start_str = s["start"].strftime("%Y-%m-%d %H:%M")
        end_str = s["end"].strftime("%Y-%m-%d %H:%M")
        print(f"  {s['symbol']:<10} {s['rows']:>8} {start_str:<20} {end_str:<20} "
              f"{s['bull_ratio']:>6.1%} {s['rsi_mean']:>7.2f} "
              f"{s['atr_pct_mean']:>8.4f} {s['atr_pct_median']:>8.4f}")


def print_session_stats(summaries: list[dict]):
    """Print session distribution and bull ratios."""
    print_section("Session Distribution (M30, UTC)")
    print(f"  {'Symbol':<10} {'Asia':>7} {'Eur':>7} {'US':>7} {'Oth':>5} "
          f"{'Bull_A':>7} {'Bull_E':>7} {'Bull_U':>7}")
    print(f"  {'─' * 64}")
    tot_asia = tot_eu = tot_us = tot_oth = 0
    for s in summaries:
        if "error" in s:
            continue
        tot_asia += s["session_asia"]
        tot_eu += s["session_europe"]
        tot_us += s["session_us"]
        tot_oth += s["session_other"]
        print(f"  {s['symbol']:<10} {s['session_asia']:>7} {s['session_europe']:>7} "
              f"{s['session_us']:>7} {s['session_other']:>5} "
              f"{s['bull_asia']:>6.1%} {s['bull_europe']:>6.1%} {s['bull_us']:>6.1%}")
    print(f"  {'─' * 64}")
    print(f"  {'TOTAL':<10} {tot_asia:>7} {tot_eu:>7} {tot_us:>7} {tot_oth:>5}")


def print_atr_stats(summaries: list[dict]):
    """Print ATR% distribution stats."""
    print_section("ATR_pct Statistics (all bars)")
    print(f"  {'Symbol':<10} {'Mean':>8} {'Median':>8} {'Q25':>8} {'Q75':>8}")
    print(f"  {'─' * 46}")
    for s in summaries:
        if "error" in s:
            continue
        print(f"  {s['symbol']:<10} {s['atr_pct_mean']:>8.4f} {s['atr_pct_median']:>8.4f} "
              f"{s['atr_pct_q25']:>8.4f} {s['atr_pct_q75']:>8.4f}")


def print_rsi_stats(summaries: list[dict]):
    """Print RSI stats."""
    print_section("RSI(14) Statistics (all bars)")
    print(f"  {'Symbol':<10} {'Mean':>8} {'Median':>8}")
    print(f"  {'─' * 30}")
    for s in summaries:
        if "error" in s:
            continue
        print(f"  {s['symbol']:<10} {s['rsi_mean']:>8.2f} {s['rsi_median']:>8.2f}")


def print_recent_stats(summaries: list[dict]):
    """Print recent 100-bar snapshot."""
    print_section("Recent 100 Bars — Direction / RSI / ATR% Range")
    print(f"  {'Symbol':<10} {'Bull%':>7} {'RSI_last':>9} {'RSI_min':>8} "
          f"{'RSI_max':>8} {'ATR%_min':>9} {'ATR%_max':>9}")
    print(f"  {'─' * 66}")
    for s in summaries:
        if "error" in s:
            continue
        print(f"  {s['symbol']:<10} {s['recent_bull_ratio']:>6.1%} "
              f"{s['recent_rsi_last']:>9.2f} {s['recent_rsi_min']:>8.2f} "
              f"{s['recent_rsi_max']:>8.2f} "
              f"{s['recent_atr_pct_min']:>9.4f} {s['recent_atr_pct_max']:>9.4f}")


# ---------------------------------------------------------------------------
# 4.  Main
# ---------------------------------------------------------------------------


def main():
    print_header("RESEARCHER PROFILE — Round 10: M30 Data Preparation")

    # ---- Step 1: List & verify symbols ----
    print("\n[1] Checking data availability ...")
    m30_syms = list_available_symbols(timeframe="M30")
    print(f"  M30 symbols found: {len(m30_syms)} — {m30_syms}")

    # Determine which symbols to process (all 14 expected)
    to_process = [s for s in SYMBOLS_14 if s in m30_syms]
    missing = [s for s in SYMBOLS_14 if s not in m30_syms]
    if missing:
        print(f"  WARNING: Missing symbols: {missing}")
    print(f"  Processing {len(to_process)} symbols.")

    # ---- Step 2: Create output directory ----
    INDICATORS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Indicators output: {INDICATORS_DIR}")

    # ---- Step 3: Load data ----
    print("\n[2] Loading M30 data ...")
    raw_data = load_data(timeframe="M30", symbols=to_process)
    print(f"  → {len(raw_data)} symbols loaded successfully.")

    # ---- Step 4: Compute indicators ----
    print("\n[3] Computing indicators ...")
    enriched_data = {}
    for sym in to_process:
        if sym not in raw_data:
            print(f"  WARNING: {sym} not in loaded data, skipping.")
            continue
        try:
            df_enriched = enrich_m30(raw_data[sym])
            enriched_data[sym] = df_enriched
            print(f"  ✓ {sym}: {len(df_enriched)} rows, "
                  f"columns={len(df_enriched.columns)}")
        except Exception as e:
            print(f"  ✗ {sym} FAILED: {e}")
            import traceback
            traceback.print_exc()

    # ---- Step 5: Save enriched data ----
    print("\n[4] Saving enriched data to parquet ...")
    saved_count = 0
    for sym, df in enriched_data.items():
        try:
            out_path = INDICATORS_DIR / f"{sym}_M30_with_indicators.parquet"
            df.to_parquet(out_path, index=True)
            saved_count += 1
        except Exception as e:
            print(f"  ✗ Failed to save {sym}: {e}")
    print(f"  → {saved_count}/{len(enriched_data)} files saved to {INDICATORS_DIR}")

    # ---- Step 6: Compute summaries ----
    print("\n[5] Computing summary statistics ...")
    summaries = []
    for sym in sorted(enriched_data.keys()):
        s = symbol_summary(sym, enriched_data[sym])
        summaries.append(s)
        print(f"  ✓ {sym}: {s['rows']} rows | Bull={s['bull_ratio']:.1%} | "
              f"RSI_μ={s['rsi_mean']:.2f} | ATR%_μ={s['atr_pct_mean']:.4f}")

    # ---- Step 7: Print formatted output ----
    print_header("ROUND 10 — M30 DATA SUMMARY FOR ANALYST")

    # Overview table
    print_summary_table(summaries)

    # Per-section deep dives
    print_session_stats(summaries)
    print_atr_stats(summaries)
    print_rsi_stats(summaries)
    print_recent_stats(summaries)

    # ---- Summary row counts ----
    total_rows = sum(s["rows"] for s in summaries if "error" not in s)
    print()
    print("=" * 90)
    print(f"  TOTAL: {total_rows} rows across {len(summaries)} symbols (M30)")
    print(f"  Enriched columns: sma_20, rsi_14, atr_14, atr_pct, session, hour, "
          f"return_1, direction, consecutive_bull, consecutive_bear")
    print(f"  Data saved to: {INDICATORS_DIR}/")
    print("=" * 90)

    # Print column list for one symbol as reference
    if enriched_data:
        sample_sym = sorted(enriched_data.keys())[0]
        sample_df = enriched_data[sample_sym]
        print(f"\n  Reference columns ({sample_sym}):")
        print(f"  {sample_df.columns.tolist()}")
        print(f"  First 3 rows of indicator columns:")
        ind_cols = [c for c in sample_df.columns if c not in ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']]
        print(f"  {sample_df[ind_cols].head(3).to_string()}")

    print()
    print("  Data preparation complete. Ready for Analyst (Round 10).")
    print("=" * 90)


if __name__ == "__main__":
    main()
