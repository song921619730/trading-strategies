#!/usr/bin/env python3
"""
Round 70 — Cross-TF Resonance Analysis (H1 + M30 pattern alignment)

Tests whether H1 buy signals confirmed by M30 signals within the same session
produce better forward returns than H1 signals alone.

Signal combos:
  a) H1: session='asia' AND rsi14<22  +  M30: session='asia' AND rsi14<22
  b) H1: session='europe' AND rsi14<20  +  M30: session='europe' AND rsi14<20
  c) H1: session='asia' AND consecutive_bear>=1  +  M30: session='asia' AND consecutive_bear>=1

Saves: ../logs/round70_resonance_results.json
       ../logs/round70_resonance_summary.txt
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Setup paths ───────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOGS_DIR / "round70_resonance.log")),
    ],
)
log = logging.getLogger("round70_resonance")
log.info("=" * 60)
log.info("Round 70 — Cross-TF Resonance Analysis (H1 + M30)")
log.info("=" * 60)

# ── Constants ─────────────────────────────────────────────────────────────
SYMBOLS = [
    "XAUUSD", "XAGUSD", "USTEC", "US30", "US500", "JP225", "HK50",
    "USOIL", "UKOIL", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
]

HOLD_PERIODS = [5, 10, 15, 20, 30, 40, 60]
PERIODS_PER_YEAR = {"H1": 6_000, "M30": 12_000}

# ── Signal combo definitions ─────────────────────────────────────────────
# Each combo has: an H1 condition, an M30 condition, a name/label.
SIGNAL_COMBOS = [
    {
        "name": "asia_rsi22",
        "h1_condition": "session == 'asia' and rsi14 < 22",
        "m30_condition": "session == 'asia' and rsi14 < 22",
        "session": "asia",
        "direction": "long",
    },
    {
        "name": "europe_rsi20",
        "h1_condition": "session == 'europe' and rsi14 < 20",
        "m30_condition": "session == 'europe' and rsi14 < 20",
        "session": "europe",
        "direction": "long",
    },
    {
        "name": "asia_cbear1",
        "h1_condition": "session == 'asia' and consecutive_bear >= 1",
        "m30_condition": "session == 'asia' and consecutive_bear >= 1",
        "session": "asia",
        "direction": "long",
    },
]


# ══════════════════════════════════════════════════════════════════════════
# 1. Data Loading & Indicator Computation (inline — no data_loader)
# ══════════════════════════════════════════════════════════════════════════

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Fix parquet files with both upper/lowercase columns — uppercase has values."""
    df = df.copy()
    lowercase_cols = set(c.lower() for c in df.columns)

    for lc in lowercase_cols:
        matching = [c for c in df.columns if c.lower() == lc]
        if len(matching) == 1 and matching[0] == lc:
            continue  # Already lowercase, no duplicates
        # Pick the column with the most non-NaN values
        best_col = max(matching, key=lambda c: df[c].notna().sum())
        df[lc] = df[best_col].values

    # Keep only lowercase columns, drop duplicates
    keep_cols = [c for c in df.columns if c.lower() == c]
    df = df[keep_cols]
    df = df.loc[:, ~df.columns.duplicated(keep='first')]
    return df


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def session_label(hour: int) -> str:
    if hour < 8:
        return "asia"
    if hour < 16:
        return "europe"
    return "us"


def load_and_compute(timeframe: str, symbols: List[str]) -> Dict[str, pd.DataFrame]:
    """Load parquet data, normalize columns, compute indicators."""
    tf_dir = DATA_DIR / timeframe
    result: Dict[str, pd.DataFrame] = {}

    for sym in symbols:
        fpath = tf_dir / f"{sym}.parquet"
        if not fpath.is_file():
            log.warning("  File not found: %s", fpath)
            continue

        df = pd.read_parquet(fpath)
        df.index.name = "time"
        df.sort_index(inplace=True)

        # Normalize columns: uppercase -> lowercase (uppercase has values)
        df = normalize_columns(df)

        # Check we have the essential columns
        needed = ["close", "open", "high", "low"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            log.warning("  %s: missing columns %s, skipping", sym, missing)
            continue

        # Time features
        df["hour"] = df.index.hour
        df["session"] = df["hour"].apply(session_label)
        df["dayofweek"] = df.index.dayofweek

        # RSI(14)
        df["rsi14"] = calc_rsi(df["close"])

        # Consecutive bullish/bearish
        bull = (df["close"] > df["open"]).astype(int)
        bear = (df["close"] < df["open"]).astype(int)
        bull_groups = (bull != bull.shift()).cumsum()
        bear_groups = (bear != bear.shift()).cumsum()
        df["consecutive_bull"] = bull.groupby(bull_groups).cumsum()
        df["consecutive_bear"] = bear.groupby(bear_groups).cumsum()
        doji_mask = (df["close"] == df["open"]).values
        df.loc[doji_mask, "consecutive_bull"] = 0
        df.loc[doji_mask, "consecutive_bear"] = 0

        # Drop NaN rows from indicator computation
        df.dropna(subset=["rsi14", "consecutive_bear"], inplace=True)

        result[sym] = df
        log.info("  %s (%s): %d rows, %s to %s",
                 sym, timeframe, len(df), df.index.min(), df.index.max())

    return result


# ══════════════════════════════════════════════════════════════════════════
# 2. Signal Detection & Alignment Logic
# ══════════════════════════════════════════════════════════════════════════

def find_signal_times(df: pd.DataFrame, condition: str) -> pd.DatetimeIndex:
    """Return DatetimeIndex of bars where the eval condition is True."""
    try:
        mask = df.eval(condition).values.astype(bool)
    except Exception as exc:
        log.error("  eval(%s) failed: %s", condition, exc)
        return pd.DatetimeIndex([])
    return df.index[mask]


def align_h1_m30_signals(
    h1_df: pd.DataFrame,
    m30_df: pd.DataFrame,
    h1_condition: str,
    m30_condition: str,
    session_name: str,
) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Return (h1_signal_times, dual_signal_times).

    h1_signal_times: all H1 bars meeting h1_condition.
    dual_signal_times: subset where an M30 bar in the same hour also meets
                       m30_condition.
    """
    h1_times = find_signal_times(h1_df, h1_condition)
    m30_times = find_signal_times(m30_df, m30_condition)

    if len(h1_times) == 0 or len(m30_times) == 0:
        return h1_times, pd.DatetimeIndex([])

    # Build set of (date, hour) for M30 signals
    m30_hours = set()
    for t in m30_times:
        m30_hours.add((t.date(), t.hour))

    # Check which H1 signal times have an M30 signal in the same hour
    dual_times = []
    for t in h1_times:
        if (t.date(), t.hour) in m30_hours:
            dual_times.append(t)

    return h1_times, pd.DatetimeIndex(dual_times)


# ══════════════════════════════════════════════════════════════════════════
# 3. Forward Return Computation
# ══════════════════════════════════════════════════════════════════════════

def compute_forward_returns(
    df: pd.DataFrame,
    signal_times: pd.DatetimeIndex,
    hold_periods: List[int],
    direction: str = "long",
    timeframe: str = "H1",
) -> Dict[int, Dict[str, Any]]:
    """Compute forward returns for signals at given times."""
    dir_sign = 1.0 if direction == "long" else -1.0
    ppy = PERIODS_PER_YEAR.get(timeframe, 6_000)
    close_arr = df["close"].values
    index_arr = df.index.values  # numpy datetime64
    n_rows = len(df)

    # Map DatetimeIndex values to integer positions (fast lookup)
    time_to_pos = {t: i for i, t in enumerate(index_arr)}

    results: Dict[int, Dict[str, Any]] = {}

    for hp in hold_periods:
        returns: List[float] = []

        for sig_time in signal_times:
            sig_time_np = sig_time.to_datetime64()
            i = time_to_pos.get(sig_time_np)
            if i is None:
                continue
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
            results[hp] = {
                "signal_count": 0,
                "avg_return": None,
                "win_rate": None,
                "sharpe_ratio": None,
                "max_drawdown": None,
            }
            continue

        avg_ret = float(ret_arr.mean())
        win_rate = float((ret_arr > 0).mean())
        std_ret = float(ret_arr.std())
        sharpe = 0.0
        if std_ret > 0 and hp > 0:
            sharpe = avg_ret / std_ret * np.sqrt(ppy / hp)

        equity = np.cumprod(1.0 + ret_arr)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_dd = float(drawdown.max())

        results[hp] = {
            "signal_count": n,
            "avg_return": round(avg_ret, 6),
            "win_rate": round(win_rate, 4),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
        }

    return results


# ══════════════════════════════════════════════════════════════════════════
# 4. Main Analysis Pipeline
# ══════════════════════════════════════════════════════════════════════════

def analyze_symbol(
    symbol: str,
    h1_df: pd.DataFrame,
    m30_df: pd.DataFrame,
    combo: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Run resonance analysis for one symbol/strategy combo. Returns results dict."""
    h1_cond = combo["h1_condition"]
    m30_cond = combo["m30_condition"]
    session_name = combo["session"]
    direction = combo["direction"]
    name = combo["name"]

    log.info("  Analyzing %s / %s ...", symbol, name)

    # Find signals
    h1_times, dual_times = align_h1_m30_signals(
        h1_df, m30_df, h1_cond, m30_cond, session_name
    )

    n_h1 = len(h1_times)
    n_dual = len(dual_times)

    log.info("    H1 signals: %d  |  Dual-confirmed: %d", n_h1, n_dual)

    if n_h1 < 5:
        log.info("    -> Insufficient H1 signals (%d < 5), skipping", n_h1)
        return None

    # Compute forward returns for H1-only (baseline) and dual-confirmed
    h1_results = compute_forward_returns(
        h1_df, h1_times, HOLD_PERIODS, direction, "H1"
    )
    dual_results = compute_forward_returns(
        h1_df, dual_times, HOLD_PERIODS, direction, "H1"
    )

    # Compare: does dual confirmation beat single-TF baseline?
    comparison = {}
    for hp in HOLD_PERIODS:
        h1_s = h1_results.get(hp, {})
        dual_s = dual_results.get(hp, {})
        h1_wr = h1_s.get("win_rate")
        dual_wr = dual_s.get("win_rate")
        if h1_wr is not None and dual_wr is not None:
            comparison[str(hp)] = {
                "h1_win_rate": h1_wr,
                "dual_win_rate": dual_wr,
                "dual_outperforms": dual_wr > h1_wr,
                "improvement": round(dual_wr - h1_wr, 4),
            }
        else:
            comparison[str(hp)] = {
                "h1_win_rate": h1_wr,
                "dual_win_rate": dual_wr,
                "dual_outperforms": None,
                "improvement": None,
            }

    # Determine best hold for dual
    best_dual = None
    best_sharpe = -999
    for hp in sorted(dual_results.keys(), key=int):
        s = dual_results[hp]
        n = s.get("signal_count", 0)
        if n >= 5:
            sh = s.get("sharpe_ratio", 0) or 0
            if sh > best_sharpe:
                best_sharpe = sh
                best_dual = {"hold_period": int(hp), **s}

    return {
        "symbol": symbol,
        "combo_name": name,
        "h1_condition": h1_cond,
        "m30_condition": m30_cond,
        "session": session_name,
        "n_h1_signals": n_h1,
        "n_dual_signals": n_dual,
        "h1_hold_stats": {str(k): v for k, v in h1_results.items()},
        "dual_hold_stats": {str(k): v for k, v in dual_results.items()},
        "comparison": comparison,
        "best_dual": best_dual,
    }


def run_pipeline():
    t_start = time.time()

    # ── Step 1: Load all data ──
    log.info("Loading H1 data for %d symbols ...", len(SYMBOLS))
    h1_data = load_and_compute("H1", SYMBOLS)
    log.info("Loaded %d H1 datasets.", len(h1_data))

    log.info("Loading M30 data for %d symbols ...", len(SYMBOLS))
    m30_data = load_and_compute("M30", SYMBOLS)
    log.info("Loaded %d M30 datasets.", len(m30_data))

    # ── Step 2: Analyze each symbol × combo ──
    all_results: List[Dict[str, Any]] = []
    stats_summary: List[Dict[str, Any]] = []

    for combo in SIGNAL_COMBOS:
        combo_name = combo["name"]
        log.info("─" * 55)
        log.info("Combo: %s", combo_name)
        log.info("  H1:  %s", combo["h1_condition"])
        log.info("  M30: %s", combo["m30_condition"])
        log.info("─" * 55)

        for sym in SYMBOLS:
            if sym not in h1_data or sym not in m30_data:
                log.warning("  %s: missing data, skipping", sym)
                continue

            result = analyze_symbol(sym, h1_data[sym], m30_data[sym], combo)
            if result is not None:
                all_results.append(result)

                # Aggregated stats row for text summary
                best = result.get("best_dual")
                if best and best.get("signal_count", 0) >= 5:
                    hp = best["hold_period"]
                    comp = result["comparison"].get(str(hp), {})
                    outperforms = comp.get("dual_outperforms")
                    stats_summary.append({
                        "symbol": sym,
                        "combo": combo_name,
                        "n_h1": result["n_h1_signals"],
                        "n_dual": result["n_dual_signals"],
                        "best_hold": hp,
                        "dual_wr": best["win_rate"],
                        "dual_sharpe": best["sharpe_ratio"],
                        "dual_avg_ret": best["avg_return"],
                        "h1_wr": comp.get("h1_win_rate"),
                        "dual_outperforms": outperforms,
                        "improvement": comp.get("improvement"),
                    })

    elapsed = time.time() - t_start
    log.info("Analysis complete in %.1f seconds.", elapsed)

    # ── Step 3: Build JSON output ──
    json_output = {
        "metadata": {
            "round": 70,
            "name": "round70_cross_tf_resonance",
            "description": "H1 + M30 Cross-Timeframe Resonance Analysis",
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "symbols_tested": len(SYMBOLS),
            "combos_tested": len(SIGNAL_COMBOS),
            "hold_periods": HOLD_PERIODS,
        },
        "combo_definitions": [
            {
                "name": c["name"],
                "h1_condition": c["h1_condition"],
                "m30_condition": c["m30_condition"],
                "session": c["session"],
                "direction": c["direction"],
            }
            for c in SIGNAL_COMBOS
        ],
        "results": all_results,
        "stats_summary": stats_summary,
    }

    json_path = LOGS_DIR / "round70_resonance_results.json"
    with open(json_path, "w") as f:
        json.dump(json_output, f, indent=2, default=str)
    log.info("✅ JSON results saved to %s", json_path)

    # ── Step 4: Generate text summary ──
    summary_text = generate_summary(all_results, stats_summary, elapsed)
    txt_path = LOGS_DIR / "round70_resonance_summary.txt"
    with open(txt_path, "w") as f:
        f.write(summary_text)
    log.info("✅ Summary saved to %s", txt_path)

    # Print the summary
    print(summary_text)

    log.info("Round 70 Cross-TF Resonance complete! Elapsed: %.1fs", elapsed)
    return json_output


def generate_summary(
    all_results: List[Dict[str, Any]],
    stats_summary: List[Dict[str, Any]],
    elapsed: float,
) -> str:
    """Generate human-readable summary text."""
    lines = []
    lines.append("=" * 80)
    lines.append("  ROUND 70 — CROSS-TIMEFRAME RESONANCE ANALYSIS (H1 + M30)")
    lines.append("=" * 80)
    lines.append(f"  Generated: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"  Elapsed: {elapsed:.1f}s")
    lines.append(f"  Symbols: {len(SYMBOLS)}")
    lines.append(f"  Combos: {len(SIGNAL_COMBOS)}")
    lines.append(f"  Hold periods: {HOLD_PERIODS}")
    lines.append("")

    # ── Summary table ──
    if stats_summary:
        lines.append("-" * 80)
        lines.append("  RESULTS SUMMARY (dual-confirmed signals with n >= 5)")
        lines.append("-" * 80)
        lines.append(
            f"  {'Symbol':>8} | {'Combo':>16} | {'H1 Sig':>7} | {'Dual Sig':>8} | "
            f"{'BestH':>5} | {'DualWR':>7} | {'DualShp':>7} | {'H1WR':>7} | {'Better?':>7} | {'Imp':>7}"
        )
        lines.append(
            f"  {'-'*8}-+-{'-'*16}-+-{'-'*7}-+-{'-'*8}-+-{'-'*5}-+-"
            f"{'-'*7}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}"
        )

        for row in sorted(stats_summary, key=lambda r: (-r.get("dual_wr", 0) if r.get("dual_wr") else 0)):
            sym = row["symbol"]
            combo = row["combo"]
            n_h1 = row["n_h1"]
            n_dual = row["n_dual"]
            bhold = row["best_hold"]
            dwr = row["dual_wr"]
            dshp = row["dual_sharpe"]
            h1wr = row["h1_wr"]
            better = "YES" if row.get("dual_outperforms") else ("NO" if row.get("dual_outperforms") is False else "N/A")
            imp = row.get("improvement", 0)
            imp_str = f"{imp:+.1%}" if imp is not None else "N/A"

            dwr_str = f"{dwr:.1%}" if dwr is not None else "N/A"
            h1wr_str = f"{h1wr:.1%}" if h1wr is not None else "N/A"
            dshp_str = f"{dshp:.2f}" if dshp is not None else "N/A"

            lines.append(
                f"  {sym:>8} | {combo:>16} | {n_h1:>7d} | {n_dual:>8d} | "
                f"{bhold:>5d} | {dwr_str:>7} | {dshp_str:>7} | {h1wr_str:>7} | "
                f"{better:>7} | {imp_str:>7}"
            )

        lines.append("")

    # ── Detailed results per symbol/combo ──
    lines.append("=" * 80)
    lines.append("  DETAILED RESULTS")
    lines.append("=" * 80)

    for result in all_results:
        sym = result["symbol"]
        combo_name = result["combo_name"]
        n_h1 = result["n_h1_signals"]
        n_dual = result["n_dual_signals"]

        lines.append("")
        lines.append("-" * 80)
        lines.append(f"  {sym} | {combo_name}")
        lines.append(f"    H1 condition:  {result['h1_condition']}")
        lines.append(f"    M30 condition: {result['m30_condition']}")
        lines.append(f"    H1 signals: {n_h1}  |  Dual-confirmed: {n_dual}")
        lines.append("")

        # Table: hold period stats
        lines.append(
            f"    {'Hold':>6} | {'H1_n':>5} | {'H1_WR':>7} | {'H1_Shp':>7} | "
            f"{'Dual_n':>6} | {'Dual_WR':>7} | {'Dual_Shp':>7} | {'Beat?':>6} | {'ΔWR':>7}"
        )
        lines.append(
            f"    {'-'*6}-+-{'-'*5}-+-{'-'*7}-+-{'-'*7}-+-"
            f"{'-'*6}-+-{'-'*7}-+-{'-'*7}-+-{'-'*6}-+-{'-'*7}"
        )

        for hp in HOLD_PERIODS:
            h1_s = result["h1_hold_stats"].get(str(hp), {})
            dual_s = result["dual_hold_stats"].get(str(hp), {})
            comp = result["comparison"].get(str(hp), {})

            h1_n = h1_s.get("signal_count", 0)
            h1_wr = h1_s.get("win_rate")
            h1_sh = h1_s.get("sharpe_ratio")
            dual_n = dual_s.get("signal_count", 0)
            dual_wr = dual_s.get("win_rate")
            dual_sh = dual_s.get("sharpe_ratio")
            beats = comp.get("dual_outperforms")
            imp = comp.get("improvement")

            h1_wr_s = f"{h1_wr:.1%}" if h1_wr is not None else "N/A"
            h1_sh_s = f"{h1_sh:.2f}" if h1_sh is not None else "N/A"
            dual_wr_s = f"{dual_wr:.1%}" if dual_wr is not None else "N/A"
            dual_sh_s = f"{dual_sh:.2f}" if dual_sh is not None else "N/A"
            beats_s = "YES" if beats else ("NO" if beats is False else "N/A")
            imp_s = f"{imp:+.1%}" if imp is not None else "N/A"

            lines.append(
                f"    {hp:>6d} | {h1_n:>5d} | {h1_wr_s:>7} | {h1_sh_s:>7} | "
                f"{dual_n:>6d} | {dual_wr_s:>7} | {dual_sh_s:>7} | {beats_s:>6} | {imp_s:>7}"
            )

        # Best dual result
        best = result.get("best_dual")
        if best and best.get("signal_count", 0) >= 5:
            lines.append("")
            lines.append(
                f"    ★ Best dual: hold={best['hold_period']:3d}  "
                f"n={best['signal_count']:4d}  "
                f"WR={best['win_rate']:.1%}  "
                f"Sharpe={best['sharpe_ratio']:.2f}  "
                f"AvgRet={best['avg_return']:.4f}"
            )

    lines.append("")
    lines.append("=" * 80)
    lines.append("  END OF REPORT")
    lines.append("=" * 80)

    return "\n".join(lines)


if __name__ == "__main__":
    run_pipeline()
