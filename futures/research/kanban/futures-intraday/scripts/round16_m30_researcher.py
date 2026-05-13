#!/usr/bin/env python3
"""
Round 16 — M30 Researcher: load data, compute indicators, output structured JSON summary.

Output: prints the JSON summary to stdout (captured by the calling process).
"""

import json
import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s | %(message)s")

# Path setup
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_loader import load_data, compute_indicators, list_available_symbols

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TIMEFRAME = "M30"
TARGET_SYMBOLS = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
    "USOIL", "UKOIL", "USTEC", "US30", "US500", "JP225", "HK50",
]
LAST_N = 500  # recent candles to summarise

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_round(x, decimals=4):
    """Round a scalar to *decimals* places, handling NaN/None."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), decimals)


def percentile_ranks(series: pd.Series, values: pd.Series) -> pd.Series:
    """Compute percentile rank of each value in *values* relative to *series*."""
    valid = series.dropna()
    if len(valid) == 0:
        return pd.Series(np.nan, index=values.index)
    # ECDF-based
    sorted_vals = np.sort(valid.values)
    ranks = np.searchsorted(sorted_vals, values.values, side="left") / len(sorted_vals)
    return pd.Series(ranks * 100.0, index=values.index)


def compute_session_bias(df: pd.DataFrame) -> dict:
    """
    Compute long (bullish) win rate per session.
    Long win = close > open (candle is bullish).
    Returns dict of {session: win_rate} where win_rate is fraction of bullish candles.
    """
    if df.empty or "session" not in df.columns:
        return {}

    bull = (df["close"] > df["open"]).astype(float)
    session_grp = bull.groupby(df["session"])
    win_rates = session_grp.mean()
    return {
        str(s): safe_round(win_rates.get(s, 0.0), 4)
        for s in ["asia", "europe", "us"]
    }


def compute_candle_stats(df: pd.DataFrame) -> dict:
    """Basic OHLCV statistics for a DataFrame."""
    stats = {
        "total_candles": int(len(df)),
        "date_from": str(df.index[0].strftime("%Y-%m-%d %H:%M")) if len(df) else None,
        "date_to": str(df.index[-1].strftime("%Y-%m-%d %H:%M")) if len(df) else None,
        "open": {
            "mean": safe_round(df["open"].mean()),
            "std": safe_round(df["open"].std()),
            "min": safe_round(df["open"].min()),
            "max": safe_round(df["open"].max()),
        },
        "high": {
            "mean": safe_round(df["high"].mean()),
            "std": safe_round(df["high"].std()),
            "min": safe_round(df["high"].min()),
            "max": safe_round(df["high"].max()),
        },
        "low": {
            "mean": safe_round(df["low"].mean()),
            "std": safe_round(df["low"].std()),
            "min": safe_round(df["low"].min()),
            "max": safe_round(df["low"].max()),
        },
        "close": {
            "mean": safe_round(df["close"].mean()),
            "std": safe_round(df["close"].std()),
            "min": safe_round(df["close"].min()),
            "max": safe_round(df["close"].max()),
        },
        "volume": {
            "tick_volume_mean": safe_round(df["tick_volume"].mean()),
            "tick_volume_sum": int(df["tick_volume"].sum()),
            "real_volume_mean": safe_round(df["real_volume"].mean()),
            "real_volume_sum": int(df["real_volume"].sum()),
        },
        "spread": {
            "mean": safe_round(df["spread"].mean()),
            "min": int(df["spread"].min()),
            "max": int(df["spread"].max()),
        },
    }
    return stats


def compute_rsi_stats(df: pd.DataFrame) -> dict:
    """RSI(14) distribution statistics."""
    rsi = df["rsi14"].dropna()
    if len(rsi) == 0:
        return {"mean": None, "q25": None, "q50": None, "q75": None}
    return {
        "mean": safe_round(rsi.mean()),
        "q25": safe_round(rsi.quantile(0.25)),
        "q50": safe_round(rsi.quantile(0.50)),
        "q75": safe_round(rsi.quantile(0.75)),
    }


def compute_atr_ratio_stats(df: pd.DataFrame) -> dict:
    """ATR(14)/close ratio distribution (volatility as fraction of price)."""
    atr_ratio = (df["atr14"] / df["close"]).dropna()
    if len(atr_ratio) == 0:
        return {"mean": None, "q25": None, "q50": None, "q75": None, "p90": None}
    return {
        "mean": safe_round(atr_ratio.mean(), 6),
        "q25": safe_round(atr_ratio.quantile(0.25), 6),
        "q50": safe_round(atr_ratio.quantile(0.50), 6),
        "q75": safe_round(atr_ratio.quantile(0.75), 6),
        "p90": safe_round(atr_ratio.quantile(0.90), 6),
    }


def compute_volatility_distribution(df: pd.DataFrame) -> dict:
    """
    ATR/close percentiles — describe the volatility regime distribution.
    Returns percentiles of the ATR/close ratio itself (not percentile ranks).
    Also returns decile buckets showing what fraction of time the market
    spends in each volatility regime.
    """
    atr_ratio = (df["atr14"] / df["close"]).dropna()
    if len(atr_ratio) == 0:
        return {}
    percentiles = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
    dist = {f"p{p}": safe_round(atr_ratio.quantile(p / 100.0), 6) for p in percentiles}
    dist["mean"] = safe_round(atr_ratio.mean(), 6)
    dist["std"] = safe_round(atr_ratio.std(), 6)
    dist["count"] = int(len(atr_ratio))
    return dist


def compute_session_distribution(df: pd.DataFrame) -> dict:
    """Count of candles per session."""
    if "session" not in df.columns:
        return {}
    counts = df["session"].value_counts()
    total = len(df)
    return {
        str(s): {
            "count": int(counts.get(s, 0)),
            "pct": safe_round(counts.get(s, 0) / total * 100, 2) if total > 0 else 0,
        }
        for s in ["asia", "europe", "us"]
    }


def compute_recent_stats(df: pd.DataFrame, n: int = LAST_N) -> dict:
    """Summary of the most recent *n* candles."""
    recent = df.tail(n)
    if len(recent) == 0:
        return {}
    stats = {
        "candles_analyzed": int(len(recent)),
        "date_range": {
            "from": str(recent.index[0].strftime("%Y-%m-%d %H:%M")),
            "to": str(recent.index[-1].strftime("%Y-%m-%d %H:%M")),
        },
        "close": {
            "mean": safe_round(recent["close"].mean()),
            "min": safe_round(recent["close"].min()),
            "max": safe_round(recent["close"].max()),
            "volatility_pct": safe_round(recent["close"].pct_change().std() * 100, 4),
        },
        "volume": {
            "tick_volume_mean": safe_round(recent["tick_volume"].mean()),
            "tick_volume_std": safe_round(recent["tick_volume"].std()),
        },
        "bullish_ratio": safe_round((recent["close"] > recent["open"]).mean(), 4),
        "avg_body_pct": safe_round(
            (abs(recent["close"] - recent["open"]) / recent["close"]).mean() * 100, 4
        ),
        "avg_range_pct": safe_round(
            ((recent["high"] - recent["low"]) / recent["close"]).mean() * 100, 4
        ),
    }
    if "rsi14" in recent.columns:
        rsi_recent = recent["rsi14"].dropna()
        if len(rsi_recent) > 0:
            stats["rsi"] = {
                "mean": safe_round(rsi_recent.mean()),
                "last": safe_round(rsi_recent.iloc[-1]),
            }
    if "atr14" in recent.columns:
        atr_recent = recent["atr14"].dropna()
        if len(atr_recent) > 0:
            atr_ratio_recent = (atr_recent / recent.loc[atr_recent.index, "close"]).dropna()
            stats["atr_ratio"] = {
                "mean": safe_round(atr_ratio_recent.mean(), 6),
                "last": safe_round(atr_ratio_recent.iloc[-1], 6) if len(atr_ratio_recent) else None,
            }
    # Session mix in recent data
    if "session" in recent.columns:
        sess_counts = recent["session"].value_counts()
        stats["session_mix"] = {
            str(s): safe_round(sess_counts.get(s, 0) / len(recent), 4)
            for s in ["asia", "europe", "us"]
        }
    return stats


def compute_ma_relationships(df: pd.DataFrame) -> dict:
    """Price position relative to key MAs at last candle."""
    if df.empty:
        return {}
    last = df.iloc[-1]
    result = {}
    for ma in ["ma20", "ma50", "ma200"]:
        if ma in df.columns and not np.isnan(last.get(ma, np.nan)):
            result[ma] = safe_round((last["close"] / last[ma] - 1.0) * 100, 4)
        else:
            result[ma] = None
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Round 16 — M30 Researcher: loading data ...", file=sys.stderr)

    # 1. Load M30 data
    m30_raw = load_data(timeframe="M30")
    if not m30_raw:
        print("ERROR: No M30 data loaded.", file=sys.stderr)
        # Try H1 as fallback
        print("Trying H1 as fallback ...", file=sys.stderr)
        m30_raw = load_data(timeframe="H1")
        if m30_raw:
            print(f"Loaded {len(m30_raw)} symbols from H1 (M30 unavailable).", file=sys.stderr)
        else:
            print("FATAL: No data available at all.", file=sys.stderr)
            sys.exit(1)

    symbols_loaded = sorted(m30_raw.keys())
    print(f"Symbols on disk: {symbols_loaded}", file=sys.stderr)

    # 2. Compute indicators for all symbols
    print("Computing indicators ...", file=sys.stderr)
    m30_enriched = {}
    for sym in symbols_loaded:
        try:
            m30_enriched[sym] = compute_indicators(m30_raw[sym])
        except Exception as e:
            print(f"WARNING: compute_indicators failed for {sym}: {e}", file=sys.stderr)
            m30_enriched[sym] = m30_raw[sym]

    # 3. Determine overall date range
    all_starts = []
    all_ends = []
    for sym, df in m30_enriched.items():
        if len(df) > 0:
            all_starts.append(df.index[0])
            all_ends.append(df.index[-1])
    overall_start = min(all_starts).strftime("%Y-%m-%d %H:%M") if all_starts else None
    overall_end = max(all_ends).strftime("%Y-%m-%d %H:%M") if all_ends else None

    # 4. Build per-symbol indicators
    per_symbol = {}
    for sym in sorted(m30_enriched.keys()):
        df = m30_enriched[sym]
        per_symbol[sym] = {
            "candle_stats": compute_candle_stats(df),
            "rsi_stats": compute_rsi_stats(df),
            "atr_ratio_stats": compute_atr_ratio_stats(df),
            "session_bias": compute_session_bias(df),
            "session_distribution": compute_session_distribution(df),
            "recent_500": compute_recent_stats(df, n=LAST_N),
            "volatility_distribution": compute_volatility_distribution(df),
            "ma_relationships": compute_ma_relationships(df),
        }

    # 5. Build the full output JSON
    output = {
        "round": 16,
        "timeframe": TIMEFRAME,
        "generated_at": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_summary": {
            "symbols_available": symbols_loaded,
            "symbols_count": len(symbols_loaded),
            "symbols_expected": TARGET_SYMBOLS,
            "all_symbols_present": len(set(TARGET_SYMBOLS) - set(symbols_loaded)) == 0,
            "date_range": {
                "overall_start": overall_start,
                "overall_end": overall_end,
            },
        },
        "indicators": {
            "per_symbol": per_symbol,
        },
    }

    # 6. Also add a quick cross-symbol comparison
    cross_symbol = {}
    for sym in sorted(m30_enriched.keys()):
        df = m30_enriched[sym]
        cross_symbol[sym] = {
            "rows": len(df),
            "last_close": safe_round(df["close"].iloc[-1]) if len(df) else None,
            "last_rsi": safe_round(df["rsi14"].dropna().iloc[-1]) if len(df) and "rsi14" in df.columns and len(df["rsi14"].dropna()) else None,
            "atr_ratio_current": safe_round(
                (df["atr14"].dropna().iloc[-1] / df["close"].iloc[-1])
            ) if len(df) and "atr14" in df.columns and len(df["atr14"].dropna()) else None,
            "bullish_ratio_overall": safe_round((df["close"] > df["open"]).mean(), 4),
            "avg_true_range_pct": safe_round(
                ((df["high"] - df["low"]) / df["close"]).mean() * 100, 4
            ),
        }
    output["cross_symbol_comparison"] = cross_symbol

    # 7. Print final JSON
    json_str = json.dumps(output, indent=2, default=str)
    print(json_str)

    # 8. Also print summary table to stderr
    print(f"\n{'='*78}", file=sys.stderr)
    print(f"  RESEARCHER DATA SUMMARY — {TIMEFRAME} (Round 16)", file=sys.stderr)
    print(f"{'='*78}", file=sys.stderr)
    print(f"  {'Symbol':<12} {'Rows':>10} {'From':<20} {'To':<20} {'Bull%':>7}", file=sys.stderr)
    print(f"  {'-'*71}", file=sys.stderr)
    total_rows = 0
    for sym in sorted(m30_enriched.keys()):
        df = m30_enriched[sym]
        rows = len(df)
        total_rows += rows
        start = df.index[0].strftime('%Y-%m-%d %H:%M')
        end = df.index[-1].strftime('%Y-%m-%d %H:%M')
        bull_pct = f"{(df['close'] > df['open']).mean()*100:.1f}%"
        print(f"  {sym:<12} {rows:>10} {start:<20} {end:<20} {bull_pct:>7}", file=sys.stderr)
    print(f"  {'-'*71}", file=sys.stderr)
    print(f"  {'TOTAL':<12} {total_rows:>10}  ({len(m30_enriched)} symbols, {TIMEFRAME})", file=sys.stderr)
    print(f"{'='*78}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
