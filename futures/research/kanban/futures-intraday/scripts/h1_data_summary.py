#!/usr/bin/env python3
"""
H1 Data Summary — Load all 14 symbols, compute indicators, output structured summary.
"""
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np

pd.set_option('display.max_columns', 30)
pd.set_option('display.width', 300)

# ── All 14 symbols ──
SYMBOLS = [
    'XAUUSD', 'XAGUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCHF',
    'USOIL', 'UKOIL', 'USTEC', 'US30', 'US500', 'JP225', 'HK50'
]

print("=" * 120)
print("H1 期货数据加载与技术指标计算 — 结构化摘要")
print("=" * 120)
print()

# ── 1. Load raw data ──
raw = load_data(timeframe='H1', symbols=SYMBOLS)
print(f"成功加载 {len(raw)} / {len(SYMBOLS)} 个品种的 H1 parquet 数据\n")

# ── 2. Compute indicators ──
indicator_dfs = {}
for sym in SYMBOLS:
    if sym not in raw:
        print(f"⚠  {sym}: 文件未找到，跳过")
        continue
    df = compute_indicators(raw[sym])
    indicator_dfs[sym] = df

print(f"\n指标计算完成: {len(indicator_dfs)} 个品种\n")

# ── 3. Build summary table ──
INDICATOR_COLS = [
    'atr14', 'rsi14', 'ma20', 'ma50', 'ma200',
    'bb_upper', 'bb_lower', 'pct_chg', 'gap_pct',
    'session', 'hour', 'dayofweek',
    'consecutive_bull_count', 'consecutive_bear_count'
]
BASE_COLS = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']

print("## 结构化数据摘要\n")
print("| 品种 | 行数 | 日期范围 | 可用列 | 缺失值 | 备注 |")
print("|------|------|----------|--------|--------|------|")

total_rows = 0
for sym in SYMBOLS:
    if sym not in indicator_dfs:
        # Symbol not found
        print(f"| {sym} | — | — | — | — | ⚠ 文件缺失，未加载 |")
        continue

    df = indicator_dfs[sym]
    n = len(df)
    total_rows += n

    # Date range
    start = df.index.min().strftime('%Y-%m-%d')
    end = df.index.max().strftime('%Y-%m-%d')
    date_range = f"{start} ~ {end}"

    # Available columns count
    all_cols = BASE_COLS + INDICATOR_COLS
    avail = [c for c in all_cols if c in df.columns]
    avail_str = f"{len(avail)} 列"

    # Missing values (NaN count in indicator columns)
    missing_vals = 0
    for c in INDICATOR_COLS:
        if c in df.columns:
            missing_vals += int(df[c].isna().sum())
    if missing_vals == 0:
        miss_str = "0"
    else:
        miss_str = f"{missing_vals}（指标列NaN总数）"

    # Notes / data quality
    notes = []
    # Check if expected indicator columns exist
    expected_indicators = ['atr14', 'rsi14', 'ma20', 'session', 'consecutive_bull_count', 'consecutive_bear_count']
    missing_indicators = [c for c in expected_indicators if c not in df.columns]
    if missing_indicators:
        notes.append(f"缺: {','.join(missing_indicators)}")
    else:
        notes.append("指标完整")

    # Check for any NaN ratio in RSI (proxy for indicator usability)
    if 'rsi14' in df.columns:
        nan_ratio = df['rsi14'].isna().mean()
        if nan_ratio > 0.5:
            notes.append(f"RSI NaN率 {nan_ratio:.0%}")
        elif nan_ratio > 0:
            notes.append(f"RSI预热期 {df['rsi14'].isna().sum()}行")
        else:
            notes.append("RSI就绪")

    # Check session distribution
    if 'session' in df.columns:
        sess_counts = df['session'].value_counts()
        sess_str = '/'.join([f"{sess_counts.get(s,0):,}" for s in ['asia','europe','us']])
        notes.append(f"Session: {sess_str}")

    note_str = "; ".join(notes)

    print(f"| {sym} | {n:,} | {date_range} | {avail_str} | {miss_str} | {note_str} |")

print()

# ── 4. Summary statistics ──
print("## 数据总览与质量总结\n")
print(f"**总计**: {total_rows:,} 行数据，{len(indicator_dfs)} 个品种\n")

# Data completeness
print("### 各品种数据完整性\n")
print("| 品种 | 行数 | 最早日期 | 最晚日期 | 覆盖年数 | 缺失值比例 |")
print("|------|------|----------|----------|----------|------------|")
for sym in SYMBOLS:
    if sym not in indicator_dfs:
        continue
    df = indicator_dfs[sym]
    n = len(df)
    years = (df.index.max() - df.index.min()).days / 365.25
    missing_ratio = 0.0
    for c in INDICATOR_COLS:
        if c in df.columns:
            missing_ratio += df[c].isna().mean()
    missing_ratio /= len([c for c in INDICATOR_COLS if c in df.columns])
    print(f"| {sym} | {n:,} | {df.index.min().strftime('%Y-%m-%d')} | {df.index.max().strftime('%Y-%m-%d')} | {years:.1f}年 | {missing_ratio:.2%} |")

print()

# Indicator availability confirmation
print("### 指标可用性确认\n")
ind_header = ['指标'] + SYMBOLS
print("| " + " | ".join(ind_header) + " |")
print("|" + "|".join(["---"] * len(ind_header)) + "|")

# Check specific indicators
check_indicators = ['rsi14', 'atr14', 'ma20', 'ma50', 'ma200', 'session', 'consecutive_bull_count', 'consecutive_bear_count', 'bb_upper', 'pct_chg']
for ind in check_indicators:
    row = [ind]
    for sym in SYMBOLS:
        if sym not in indicator_dfs:
            row.append("—")
        elif ind in indicator_dfs[sym].columns:
            non_null = indicator_dfs[sym][ind].notna().sum()
            row.append(f"✓ ({non_null:,})")
        else:
            row.append("✗")
    print("| " + " | ".join(row) + " |")

print()

# ── 5. Per-symbol RSI/ATR stats ──
print("### RSI14 描述性统计\n")
print("| 品种 | 有效数 | 最小值 | 25% | 中位数 | 75% | 最大值 | 均值 |")
print("|------|--------|--------|-----|--------|-----|--------|------|")
for sym in SYMBOLS:
    if sym not in indicator_dfs or 'rsi14' not in indicator_dfs[sym].columns:
        continue
    rsi = indicator_dfs[sym]['rsi14'].dropna()
    if len(rsi) == 0:
        continue
    desc = rsi.describe(percentiles=[0.25, 0.5, 0.75])
    print(f"| {sym} | {len(rsi):,} | {desc['min']:.2f} | {desc['25%']:.2f} | {desc['50%']:.2f} | {desc['75%']:.2f} | {desc['max']:.2f} | {desc['mean']:.2f} |")

print()

print("### ATR14 描述性统计\n")
print("| 品种 | 有效数 | 最小值 | 25% | 中位数 | 75% | 最大值 | 均值 |")
print("|------|--------|--------|-----|--------|-----|--------|------|")
for sym in SYMBOLS:
    if sym not in indicator_dfs or 'atr14' not in indicator_dfs[sym].columns:
        continue
    atr = indicator_dfs[sym]['atr14'].dropna()
    if len(atr) == 0:
        continue
    desc = atr.describe(percentiles=[0.25, 0.5, 0.75])
    print(f"| {sym} | {len(atr):,} | {desc['min']:.4f} | {desc['25%']:.4f} | {desc['50%']:.4f} | {desc['75%']:.4f} | {desc['max']:.4f} | {desc['mean']:.4f} |")

print()

# ── 6. Session distribution ──
print("### Session 分布 (asia / europe / us)\n")
print("| 品种 | Total | asia | europe | us |")
print("|------|-------|------|--------|----|")
for sym in SYMBOLS:
    if sym not in indicator_dfs or 'session' not in indicator_dfs[sym].columns:
        continue
    df = indicator_dfs[sym]
    counts = df['session'].value_counts()
    total = len(df)
    print(f"| {sym} | {total:,} | {counts.get('asia',0):,} | {counts.get('europe',0):,} | {counts.get('us',0):,} |")

print()
print("=" * 120)
print("摘要完成 — 数据已准备就绪，可供 Analyst 使用")
print("=" * 120)
