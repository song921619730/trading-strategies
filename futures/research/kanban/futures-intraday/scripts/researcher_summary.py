#!/usr/bin/env python3
"""
Researcher: M30 Data Validation & Structured Summary

Loads all 14 symbols' M30 data, computes indicators, and outputs a
formatted summary table for the Analyst role.  Runs as a standalone script.
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure we can import from the scripts directory
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_loader import load_data, compute_indicators

# ---------------------------------------------------------------------------
# 1.  Load data
# ---------------------------------------------------------------------------
SYMBOLS = [
    "AUDUSD", "EURUSD", "GBPUSD", "HK50", "JP225", "UKOIL",
    "US30", "US500", "USDCHF", "USDJPY", "USOIL", "USTEC",
    "XAGUSD", "XAUUSD",
]

print("=" * 90)
print("  Researcher — M30 数据加载与验证报告")
print("=" * 90)

print("\n▶ 加载 M30 数据中 ...")
data = load_data(timeframe="M30", symbols=SYMBOLS)

loaded_symbols = sorted(data.keys())
print(f"  成功加载 {len(loaded_symbols)} 个品种: {', '.join(loaded_symbols)}")

# ---------------------------------------------------------------------------
# 2.  Compute indicators
# ---------------------------------------------------------------------------
print("\n▶ 计算技术指标中 ...")
indicator_data = {}
for sym in loaded_symbols:
    df = data[sym]
    df_ind = compute_indicators(df)
    indicator_data[sym] = df_ind
    print(f"  {sym:8s} → {len(df_ind):>8,} 行, 指标已添加")

# ---------------------------------------------------------------------------
# 3.  Per-symbol summary
# ---------------------------------------------------------------------------
print("\n" + "─" * 90)
print("  【品种概览】")
print("─" * 90)

rows = []
for sym in loaded_symbols:
    df = indicator_data[sym]
    n_rows = len(df)
    start_date = df.index.min().strftime("%Y-%m-%d")
    end_date = df.index.max().strftime("%Y-%m-%d")
    latest_date = df.index.max().strftime("%Y-%m-%d %H:%M")
    rows.append((sym, n_rows, start_date, end_date, latest_date))

sum_table = pd.DataFrame(
    rows,
    columns=["品种", "行数", "起始日期", "截止日期", "最新数据时间"],
)
print(sum_table.to_string(index=False))

# ---------------------------------------------------------------------------
# 4.  XAUUSD — column validation (first 5 rows)
# ---------------------------------------------------------------------------
print("\n" + "─" * 90)
print("  【XAUUSD — 指标列名前 5 行验证】")
print("─" * 90)

xau = indicator_data["XAUUSD"]
# Pick a meaningful set of columns: original + added indicators
indicator_cols = [
    "open", "high", "low", "close", "tick_volume",
    "atr14", "rsi14", "ma20", "ma50", "ma200",
    "bb_upper", "bb_lower", "pct_chg", "gap_pct",
    "hour", "dayofweek", "session",
    "consecutive_bull_count", "consecutive_bear_count",
]
# Only include columns that exist
indicator_cols = [c for c in indicator_cols if c in xau.columns]

print(f"  列数: {len(indicator_cols)}")
print(f"  列名: {', '.join(indicator_cols)}")
print()
print(xau[indicator_cols].head(5).to_string())

# ---------------------------------------------------------------------------
# 5.  Cross-symbol statistics (ATR/RSI means and volatility)
# ---------------------------------------------------------------------------
print("\n" + "─" * 90)
print("  【全品种统计摘要】")
print("─" * 90)

stat_rows = []
for sym in loaded_symbols:
    df = indicator_data[sym]
    close = df["close"]
    atr = df["atr14"].dropna()
    rsi = df["rsi14"].dropna()

    # ATR relative to close (ATR / close ratio)
    # Use the close price at the same index as atr values
    atr_close_ratio = (atr / close.loc[atr.index]).mean() * 100
    atr_mean = atr.mean()
    atr_std = atr.std()
    rsi_mean = rsi.mean()
    rsi_std = rsi.std()

    stat_rows.append({
        "品种": sym,
        "总行数": len(df),
        "ATR均值": round(atr_mean, 4),
        "ATR波动率(std)": round(atr_std, 4),
        "ATR/Close(%)": round(atr_close_ratio, 4),
        "RSI均值": round(rsi_mean, 2),
        "RSI波动率(std)": round(rsi_std, 2),
    })

stat_df = pd.DataFrame(stat_rows)

# Add a total row
total_records = int(stat_df["总行数"].sum())
stat_df.loc["合计"] = [
    "合计",
    total_records,
    stat_df["ATR均值"].mean(),
    stat_df["ATR波动率(std)"].mean(),
    stat_df["ATR/Close(%)"].mean(),
    stat_df["RSI均值"].mean(),
    stat_df["RSI波动率(std)"].mean(),
]
# Format the total row nicely
stat_df = stat_df.round(4)

print(stat_df.to_string())

# ---------------------------------------------------------------------------
# 6.  Summary statistics as JSON (for downstream use)
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
        "atr_mean": round(float(atr.mean()), 4),
        "atr_std": round(float(atr.std()), 4),
        "atr_close_ratio_pct": round(float(atr_close_ratio), 4),
        "rsi_mean": round(float(rsi.mean()), 2),
        "rsi_std": round(float(rsi.std()), 2),
    }

summary_stats["_meta"] = {
    "total_symbols": int(len(loaded_symbols)),
    "total_records": int(total_records),
    "timeframe": "M30",
    "generated_at": str(pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC")),
}

# Save to state directory
state_dir = Path(__file__).resolve().parent.parent / "state"
state_dir.mkdir(parents=True, exist_ok=True)
state_path = state_dir / "m30_summary.json"
with open(state_path, "w") as f:
    json.dump(summary_stats, f, indent=2, ensure_ascii=False)
print(f"\n▶ JSON 摘要已保存至: {state_path}")

print("\n" + "=" * 90)
print("  Researcher 任务完成。摘要数据已准备，可供 Analyst 使用。")
print("=" * 90)
