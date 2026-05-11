#!/usr/bin/env python3
"""
Researcher: H1 Data Loading, Indicator Computation & Structured Summary

Loads all 14 symbols' H1 parquet data, computes technical indicators,
and outputs a formatted summary report for the Analyst role.
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_loader import load_data, compute_indicators

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SYMBOLS = [
    "AUDUSD", "EURUSD", "GBPUSD", "HK50", "JP225", "UKOIL",
    "US30", "US500", "USDCHF", "USDJPY", "USOIL", "USTEC",
    "XAGUSD", "XAUUSD",
]

TIMEFRAME = "H1"

print("=" * 100)
print(f"  Researcher — {TIMEFRAME} 数据加载与验证报告  (Round 15)")
print("=" * 100)

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------
print(f"\n▶ 加载 {TIMEFRAME} 数据中 ...")
data = load_data(timeframe=TIMEFRAME, symbols=SYMBOLS)

loaded_symbols = sorted(data.keys())
print(f"  成功加载 {len(loaded_symbols)}/{len(SYMBOLS)} 个品种: {', '.join(loaded_symbols)}")

missing = set(SYMBOLS) - set(loaded_symbols)
if missing:
    print(f"  ⚠ 缺失品种: {', '.join(sorted(missing))}")

# ---------------------------------------------------------------------------
# 2. Compute indicators
# ---------------------------------------------------------------------------
print(f"\n▶ 计算技术指标中 ...")
indicator_data = {}
for sym in loaded_symbols:
    df = data[sym]
    df_ind = compute_indicators(df)
    indicator_data[sym] = df_ind
    print(f"  {sym:8s} → {len(df_ind):>8,} 行, 指标已添加")

# ---------------------------------------------------------------------------
# 3. Per-symbol overview
# ---------------------------------------------------------------------------
print("\n" + "─" * 100)
print("  【品种概览 — 数据范围与行数】")
print("─" * 100)

rows = []
for sym in loaded_symbols:
    df = indicator_data[sym]
    n_rows = len(df)
    start_date = df.index.min().strftime("%Y-%m-%d")
    end_date = df.index.max().strftime("%Y-%m-%d")
    latest_time = df.index.max().strftime("%Y-%m-%d %H:%M")
    rows.append((sym, n_rows, start_date, end_date, latest_time))

sum_table = pd.DataFrame(
    rows,
    columns=["品种", "行数", "起始日期", "截止日期", "最新数据时间"],
)
print(sum_table.to_string(index=False))

# ---------------------------------------------------------------------------
# 4. NaN analysis — indicator completeness
# ---------------------------------------------------------------------------
print("\n" + "─" * 100)
print("  【指标完整性检查 — NaN 统计】")
print("─" * 100)

indicator_cols_check = [
    "atr14", "rsi14", "ma20", "ma50", "ma200",
    "bb_upper", "bb_lower", "pct_chg", "gap_pct",
    "hour", "dayofweek", "session",
    "consecutive_bull_count", "consecutive_bear_count",
]

nan_rows = []
for sym in loaded_symbols:
    df = indicator_data[sym]
    n_total = len(df)
    details = {}
    has_any_nan = False
    for col in indicator_cols_check:
        if col in df.columns:
            n_nan = int(df[col].isna().sum())
            pct = round(n_nan / n_total * 100, 2)
            details[col] = f"{n_nan}/{n_total} ({pct}%)"
            if n_nan > 0:
                has_any_nan = True
        else:
            details[col] = "MISSING"
            has_any_nan = True

    # Summary: how many indicator columns have NaN
    nan_cols = sum(1 for col in indicator_cols_check if col in df.columns and df[col].isna().any())
    pct_nan_cols = round(nan_cols / len(indicator_cols_check) * 100, 1)

    nan_rows.append({
        "品种": sym,
        "总行数": n_total,
        "含NaN指标列数": nan_cols,
        "占比(%)": pct_nan_cols,
        "atr14_NaN": details.get("atr14", "N/A"),
        "rsi14_NaN": details.get("rsi14", "N/A"),
        "ma200_NaN": details.get("ma200", "N/A"),
    })

nan_df = pd.DataFrame(nan_rows)
print(nan_df.to_string(index=False))

# Show percentage of NaN rows for first few rows (warm-up period)
print("\n  ▶ 详细说明: NaN 主要来自指标计算所需的 warm-up 窗口")
print(f"     - ATR14/RSI14: 前 13 行 NaN (需 14 根 K 线)")
print(f"     - MA20: 前 19 行 NaN")
print(f"     - MA50: 前 49 行 NaN")
print(f"     - MA200: 前 199 行 NaN")
print(f"     - 其他列 (pct_chg, gap_pct): 首行 NaN")
print(f"     - 非滚动列 (session, hour, dayofweek, consecutive counts): 无 NaN")

# ---------------------------------------------------------------------------
# 5. XAUUSD — column validation (first 5 rows)
# ---------------------------------------------------------------------------
print("\n" + "─" * 100)
print("  【XAUUSD — 指标列名前 5 行验证】")
print("─" * 100)

xau = indicator_data["XAUUSD"]
indicator_cols = [
    "open", "high", "low", "close", "tick_volume",
    "atr14", "rsi14", "ma20", "ma50", "ma200",
    "bb_upper", "bb_lower", "pct_chg", "gap_pct",
    "hour", "dayofweek", "session",
    "consecutive_bull_count", "consecutive_bear_count",
]
indicator_cols = [c for c in indicator_cols if c in xau.columns]

print(f"  列数: {len(indicator_cols)}")
print(f"  列名: {', '.join(indicator_cols)}")
print()
print(xau[indicator_cols].head(5).to_string())

# ---------------------------------------------------------------------------
# 6. Cross-symbol statistics (ATR/RSI/price means and volatility)
# ---------------------------------------------------------------------------
print("\n" + "─" * 100)
print("  【全品种统计摘要】")
print("─" * 100)

stat_rows = []
for sym in loaded_symbols:
    df = indicator_data[sym]
    close = df["close"]
    atr = df["atr14"].dropna()
    rsi = df["rsi14"].dropna()

    # ATR relative to close
    atr_close_ratio = (atr / close.loc[atr.index]).mean() * 100
    atr_mean = atr.mean()
    atr_std = atr.std()
    rsi_mean = rsi.mean()
    rsi_std = rsi.std()
    close_mean = close.mean()
    close_std = close.std()
    close_min = close.min()
    close_max = close.max()

    stat_rows.append({
        "品种": sym,
        "总行数": len(df),
        "收盘均价": round(close_mean, 2),
        "收盘σ": round(close_std, 2),
        "最低价": round(close_min, 2),
        "最高价": round(close_max, 2),
        "ATR均值": round(atr_mean, 4),
        "ATRσ": round(atr_std, 4),
        "ATR/Close(%)": round(atr_close_ratio, 4),
        "RSI均值": round(rsi_mean, 2),
        "RSIσ": round(rsi_std, 2),
    })

stat_df = pd.DataFrame(stat_rows)

# Add totals row
total_records = int(stat_df["总行数"].sum())
stat_df.loc["合计"] = [
    "合计",
    total_records,
    stat_df["收盘均价"].mean(),
    stat_df["收盘σ"].mean(),
    stat_df["最低价"].mean(),
    stat_df["最高价"].mean(),
    stat_df["ATR均值"].mean(),
    stat_df["ATRσ"].mean(),
    stat_df["ATR/Close(%)"].mean(),
    stat_df["RSI均值"].mean(),
    stat_df["RSIσ"].mean(),
]
stat_df = stat_df.round(4)

print(stat_df.to_string())

# ---------------------------------------------------------------------------
# 7. Save structured JSON summary for downstream use
# ---------------------------------------------------------------------------
summary_stats = {}
for sym in loaded_symbols:
    df = indicator_data[sym]
    atr = df["atr14"].dropna()
    rsi = df["rsi14"].dropna()
    close = df["close"]
    atr_close_ratio = (atr / close.loc[atr.index]).mean() * 100

    summary_stats[sym] = {
        "rows": int(len(df)),
        "date_start": str(df.index.min().strftime("%Y-%m-%d")),
        "date_end": str(df.index.max().strftime("%Y-%m-%d")),
        "latest": str(df.index.max().strftime("%Y-%m-%d %H:%M")),
        "close_mean": round(float(close.mean()), 2),
        "close_std": round(float(close.std()), 2),
        "atr_mean": round(float(atr.mean()), 4),
        "atr_std": round(float(atr.std()), 4),
        "atr_close_ratio_pct": round(float(atr_close_ratio), 4),
        "rsi_mean": round(float(rsi.mean()), 2),
        "rsi_std": round(float(rsi.std()), 2),
        "nan_pct": {
            "atr14": round(float(df["atr14"].isna().mean() * 100), 2),
            "rsi14": round(float(df["rsi14"].isna().mean() * 100), 2),
            "ma20": round(float(df["ma20"].isna().mean() * 100), 2),
            "ma50": round(float(df["ma50"].isna().mean() * 100), 2),
            "ma200": round(float(df["ma200"].isna().mean() * 100), 2),
        },
    }

summary_stats["_meta"] = {
    "total_symbols": int(len(loaded_symbols)),
    "total_records": int(total_records),
    "timeframe": TIMEFRAME,
    "round": 15,
    "generated_at": str(pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC")),
    "hypothesis_focus": "auto_023 — EURUSD H1 high ATR + RSI < 40 long, optimal holding period deep scan",
}

# Save to state directory
state_dir = Path(__file__).resolve().parent.parent / "state"
state_dir.mkdir(parents=True, exist_ok=True)
state_path = state_dir / "h1_summary.json"
with open(state_path, "w") as f:
    json.dump(summary_stats, f, indent=2, ensure_ascii=False)
print(f"\n▶ JSON 摘要已保存至: {state_path}")

# ---------------------------------------------------------------------------
# 8. EURUSD specific focus (for auto_023 hypothesis)
# ---------------------------------------------------------------------------
print("\n" + "─" * 100)
print("  【EURUSD 专题 — 针对 auto_023 假设】")
print("─" * 100)

eur = indicator_data["EURUSD"]
atr = eur["atr14"].dropna()
rsi = eur["rsi14"].dropna()

# High ATR periods (top quartile)
atr_threshold = atr.quantile(0.75)
high_atr_mask = eur["atr14"] >= atr_threshold
rsi_under_40 = eur["rsi14"] < 40
combined = (high_atr_mask & rsi_under_40).sum()

print(f"  EURUSD 总行数: {len(eur):,}")
print(f"  ATR14 均值: {atr.mean():.4f}  |  中位数: {atr.median():.4f}  |  Q3(阈值): {atr_threshold:.4f}")
print(f"  RSI14 均值: {rsi.mean():.2f}  |  中位数: {rsi.median():.2f}")
print(f"  ATR ≥ Q3 且 RSI < 40 的 K 线数: {int(combined)} (占 {combined/len(eur)*100:.2f}%)")
print()
print(f"  ▶ 假设 auto_023 信号频率较低 ({combined} 次), 适合深入扫描最优持有期")

# ---------------------------------------------------------------------------
# 9. Session distribution summary
# ---------------------------------------------------------------------------
print("\n" + "─" * 100)
print("  【交易时段分布 (全品种平均)】")
print("─" * 100)

session_data = []
for sym in loaded_symbols:
    df = indicator_data[sym]
    session_counts = df["session"].value_counts()
    total = len(df)
    session_data.append({
        "品种": sym,
        "asia_%": round(session_counts.get("asia", 0) / total * 100, 1),
        "europe_%": round(session_counts.get("europe", 0) / total * 100, 1),
        "us_%": round(session_counts.get("us", 0) / total * 100, 1),
    })

session_df = pd.DataFrame(session_data)
print(session_df.to_string(index=False))

print("\n" + "=" * 100)
print(f"  Researcher 任务完成。{TIMEFRAME} 数据摘要已准备，可供 Analyst 使用。")
print("  焦点假设: auto_023 — EURUSD H1 高 ATR + RSI < 40 做多")
print("=" * 100)
