#!/usr/bin/env python3
"""
Round 5 — H1 Data Summary (Researcher Profile)
Loads H1 data, computes indicators, generates structured summary.
"""

import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import numpy as np
import pandas as pd

from data_loader import load_data, compute_indicators

# ── Configuration ──────────────────────────────────────────────────────────
TIMEFRAME = "H1"
TARGET_SYMBOLS = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
    "USOIL", "UKOIL", "USTEC", "US30", "US500", "JP225", "HK50",
]

# ── Load raw data ─────────────────────────────────────────────────────────
print(f"Loading {TIMEFRAME} data for all symbols ...")
raw_data = load_data(timeframe=TIMEFRAME, symbols=TARGET_SYMBOLS)
print(f"  → {len(raw_data)} symbols loaded")

missing = [s for s in TARGET_SYMBOLS if s not in raw_data]
if missing:
    print(f"  ⚠ Missing symbols: {missing}")
else:
    print(f"  ✓ All {len(TARGET_SYMBOLS)} symbols present")

# ── Compute indicators ────────────────────────────────────────────────────
print("Computing technical indicators ...")
enriched_data = {}
for sym, df in raw_data.items():
    try:
        enriched_data[sym] = compute_indicators(df)
    except Exception as e:
        print(f"  WARNING: compute_indicators failed for {sym}: {e}")
        enriched_data[sym] = df
print(f"  → Indicators computed for {len(enriched_data)} symbols")

# ── Verify required columns exist ─────────────────────────────────────────
REQUIRED_COLS = [
    "atr14", "rsi14", "ma20", "ma50", "ma200",
    "bb_upper", "bb_lower", "pct_chg", "session",
    "hour", "dayofweek", "consecutive_bull_count", "consecutive_bear_count"
]
print("\n── Column Integrity Check ──")
all_ok = True
for sym, df in enriched_data.items():
    missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        print(f"  ✗ {sym}: MISSING {missing_cols}")
        all_ok = False
if all_ok:
    print(f"  ✓ All {len(REQUIRED_COLS)} required columns present in all {len(enriched_data)} symbols")

# ── Per-symbol statistics ────────────────────────────────────────────────
print("\n── Calculating per-symbol statistics ──")
stats_rows = []
for sym in sorted(enriched_data.keys()):
    df = enriched_data[sym]
    n_rows = len(df)
    start_date = df.index[0].strftime('%Y-%m-%d %H:%M')
    end_date = df.index[-1].strftime('%Y-%m-%d %H:%M')

    # Missing values
    missing_counts = df.isnull().sum()
    missing_total = int(missing_counts.sum())
    missing_cols = missing_counts[missing_counts > 0].index.tolist()

    # Basic OHLC stats
    avg_atr = float(df['atr14'].mean()) if 'atr14' in df.columns else None
    volatility = float(df['pct_chg'].std()) if 'pct_chg' in df.columns else None

    # Bull/bear ratio
    bull_mask = df['close'] > df['open']
    bear_mask = df['close'] < df['open']
    bull_ratio = float(bull_mask.mean())
    bear_ratio = float(bear_mask.mean())

    # ATR relative to price
    avg_close = float(df['close'].mean())
    atr_pct = (avg_atr / avg_close * 100) if avg_atr and avg_close else None

    # Pct_chg distribution
    if 'pct_chg' in df.columns:
        pct = df['pct_chg'].dropna()
        pct_25 = float(pct.quantile(0.25))
        pct_50 = float(pct.median())
        pct_75 = float(pct.quantile(0.75))
        pct_mean = float(pct.mean())
        pct_std = float(pct.std())
        pct_neg_ratio = float((pct < 0).mean())
        pct_pos_ratio = float((pct > 0).mean())
    else:
        pct_25 = pct_50 = pct_75 = pct_mean = pct_std = pct_neg_ratio = pct_pos_ratio = None

    stats_rows.append({
        'symbol': sym,
        'rows': n_rows,
        'start': start_date,
        'end': end_date,
        'missing_total': missing_total,
        'missing_cols': ', '.join(missing_cols) if missing_cols else 'none',
        'avg_atr': avg_atr,
        'atr_pct': atr_pct,
        'volatility': volatility,
        'bull_ratio': bull_ratio,
        'bear_ratio': bear_ratio,
        'pct_mean': pct_mean,
        'pct_std': pct_std,
        'pct_25': pct_25,
        'pct_50': pct_50,
        'pct_75': pct_75,
        'pct_neg_ratio': pct_neg_ratio,
        'pct_pos_ratio': pct_pos_ratio,
        'avg_close': avg_close,
    })

stats_df = pd.DataFrame(stats_rows)

# ── Cross-symbol statistics ──────────────────────────────────────────────
total_rows_all = int(stats_df['rows'].sum())
avg_atr_all = stats_df['avg_atr'].mean()
avg_bull_ratio = stats_df['bull_ratio'].mean()
avg_volatility = stats_df['volatility'].mean()

highest_vol_sym = stats_df.loc[stats_df['volatility'].idxmax(), 'symbol']
lowest_vol_sym = stats_df.loc[stats_df['volatility'].idxmin(), 'symbol']
highest_bull_sym = stats_df.loc[stats_df['bull_ratio'].idxmax(), 'symbol']
lowest_bull_sym = stats_df.loc[stats_df['bull_ratio'].idxmin(), 'symbol']
highest_atr_sym = stats_df.loc[stats_df['avg_atr'].idxmax(), 'symbol']
lowest_atr_sym = stats_df.loc[stats_df['avg_atr'].idxmin(), 'symbol']

# ── Session distribution analysis ────────────────────────────────────────
print("\n── Session Distribution Analysis ──")
session_stats = []
for sym in sorted(enriched_data.keys()):
    df = enriched_data[sym]
    if 'session' in df.columns:
        session_counts = df['session'].value_counts()
        session_pcts = df['session'].value_counts(normalize=True) * 100
        for sess in ['asia', 'europe', 'us']:
            cnt = int(session_counts.get(sess, 0))
            pct = float(session_pcts.get(sess, 0))
            session_stats.append({
                'symbol': sym,
                'session': sess,
                'count': cnt,
                'pct': pct
            })

session_df = pd.DataFrame(session_stats)

# Session bull ratio per session
session_bull_stats = []
for sym in sorted(enriched_data.keys()):
    df = enriched_data[sym]
    if 'session' in df.columns:
        for sess in ['asia', 'europe', 'us']:
            sub = df[df['session'] == sess]
            if len(sub) > 0:
                bull = (sub['close'] > sub['open']).mean()
            else:
                bull = None
            session_bull_stats.append({
                'symbol': sym,
                'session': sess,
                'count': len(sub),
                'bull_ratio': float(bull) if bull is not None else None
            })

session_bull_df = pd.DataFrame(session_bull_stats)

# ── Print Summary ────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("  ROUND 5 — H1 DATA SUMMARY (Researcher Profile)")
print("=" * 90)

print("\n── 1. 数据概览 ──")
print(f"  {'指标':<20} {'值'}")
print(f"  {'-'*60}")
print(f"  {'时间框架':<20} {TIMEFRAME}")
print(f"  {'品种数':<20} {len(enriched_data)} / {len(TARGET_SYMBOLS)}")
print(f"  {'总记录数':<20} {total_rows_all:,}")
print(f"  {'最早日期':<20} {stats_df['start'].min()}")
print(f"  {'最晚日期':<20} {stats_df['end'].max()}")
print(f"  {'平均每品种行数':<20} {total_rows_all // len(enriched_data):,}")
max_rows_sym = stats_df.loc[stats_df['rows'].idxmax(), 'symbol']
max_rows_val = stats_df.loc[stats_df['rows'].idxmax(), 'rows']
min_rows_sym = stats_df.loc[stats_df['rows'].idxmin(), 'symbol']
min_rows_val = stats_df.loc[stats_df['rows'].idxmin(), 'rows']
print(f"  {'行数最多':<20} {max_rows_sym} ({max_rows_val:,})")
print(f"  {'行数最少':<20} {min_rows_sym} ({min_rows_val:,})")

print("\n── 2. 逐品种详细信息 ──")

print("\n── 2. 逐品种详细信息 ──")
print(f"  {'品种':<10} {'记录数':>8} {'开始时间':<17} {'结束时间':<17} {'缺失值':>6}")
print(f"  {'-'*60}")
for _, row in stats_df.iterrows():
    print(f"  {row['symbol']:<10} {row['rows']:>8,} {row['start']:<17} {row['end']:<17} {row['missing_total']:>6}")

print("\n── 3. 阳线比例与波动率 ──")
print(f"  {'品种':<10} {'阳线比例':>8} {'阴线比例':>8} {'平均ATR':>10} {'波动率%':>8} {'ATR/价格%':>8}")
print(f"  {'-'*55}")
for _, row in stats_df.sort_values('bull_ratio', ascending=False).iterrows():
    bull_str = f"{row['bull_ratio']*100:.2f}%"
    bear_str = f"{row['bear_ratio']*100:.2f}%"
    atr_str = f"{row['avg_atr']:.4f}" if row['avg_atr'] is not None else "N/A"
    vol_str = f"{row['volatility']:.4f}" if row['volatility'] is not None else "N/A"
    atrp_str = f"{row['atr_pct']:.2f}%" if row['atr_pct'] is not None else "N/A"
    print(f"  {row['symbol']:<10} {bull_str:>8} {bear_str:>8} {atr_str:>10} {vol_str:>8} {atrp_str:>8}")

print(f"\n  全品种平均阳线比例: {avg_bull_ratio*100:.2f}%")
print(f"  全品种平均波动率: {avg_volatility:.4f}%")
print(f"  最高波动率: {highest_vol_sym} ({stats_df.loc[stats_df['symbol']==highest_vol_sym, 'volatility'].values[0]:.4f}%)")
print(f"  最低波动率: {lowest_vol_sym} ({stats_df.loc[stats_df['symbol']==lowest_vol_sym, 'volatility'].values[0]:.4f}%)")
print(f"  最高平均ATR: {highest_atr_sym} ({stats_df.loc[stats_df['symbol']==highest_atr_sym, 'avg_atr'].values[0]:.4f})")
print(f"  最低平均ATR: {lowest_atr_sym} ({stats_df.loc[stats_df['symbol']==lowest_atr_sym, 'avg_atr'].values[0]:.4f})")

print("\n── 4. 各时段信号分布 ──")
# Pivot for display
pivot_bull = session_bull_df.pivot_table(
    index='symbol', columns='session', values='bull_ratio', aggfunc='first'
)
pivot_count = session_bull_df.pivot_table(
    index='symbol', columns='session', values='count', aggfunc='first'
)
print(f"  {'品种':<10} {'亚洲K线':>8} {'亚洲阳率':>10} {'欧洲K线':>8} {'欧洲阳率':>10} {'美盘K线':>8} {'美盘阳率':>10}")
print(f"  {'-'*70}")
for sym in sorted(enriched_data.keys()):
    asia_c = int(pivot_count.loc[sym, 'asia']) if 'asia' in pivot_count.columns and sym in pivot_count.index else 0
    eu_c = int(pivot_count.loc[sym, 'europe']) if 'europe' in pivot_count.columns and sym in pivot_count.index else 0
    us_c = int(pivot_count.loc[sym, 'us']) if 'us' in pivot_count.columns and sym in pivot_count.index else 0
    asia_b = f"{pivot_bull.loc[sym, 'asia']*100:.1f}%" if 'asia' in pivot_bull.columns and sym in pivot_bull.index else "N/A"
    eu_b = f"{pivot_bull.loc[sym, 'europe']*100:.1f}%" if 'europe' in pivot_bull.columns and sym in pivot_bull.index else "N/A"
    us_b = f"{pivot_bull.loc[sym, 'us']*100:.1f}%" if 'us' in pivot_bull.columns and sym in pivot_bull.index else "N/A"
    print(f"  {sym:<10} {asia_c:>8,} {asia_b:>10} {eu_c:>8,} {eu_b:>10} {us_c:>8,} {us_b:>10}")

# Session bull ratio averages across all symbols
print(f"\n  全品种各时段平均阳线比例:")
for sess in ['asia', 'europe', 'us']:
    avg_b = session_bull_df[session_bull_df['session'] == sess]['bull_ratio'].mean()
    total_k = session_bull_df[session_bull_df['session'] == sess]['count'].sum()
    print(f"    {sess:<8}: {avg_b*100:.2f}% (共 {total_k:,} 根K线)")

# ── Session distribution detail table ──
print("\n── 5. 各品种时段K线分布 ──")
print(f"  {'品种':<10} {'亚洲%':>8} {'欧洲%':>8} {'美盘%':>8}")
print(f"  {'-'*38}")
for sym in sorted(enriched_data.keys()):
    sym_sessions = session_df[session_df['symbol'] == sym]
    asia_p = next((r['pct'] for _, r in sym_sessions.iterrows() if r['session'] == 'asia'), 0)
    eu_p = next((r['pct'] for _, r in sym_sessions.iterrows() if r['session'] == 'europe'), 0)
    us_p = next((r['pct'] for _, r in sym_sessions.iterrows() if r['session'] == 'us'), 0)
    print(f"  {sym:<10} {asia_p:>7.1f}% {eu_p:>7.1f}% {us_p:>7.1f}%")

# ── Column integrity summary ──
print("\n── 6. 数据列完整性检查 ──")
print(f"  检查的列: {', '.join(REQUIRED_COLS)}")
if all_ok:
    print(f"  状态: ✓ 所有 {len(REQUIRED_COLS)} 列均存在且完整")

# ── Save to report ──
REPORT_DIR = PROJECT_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = REPORT_DIR / "round5_h1_data_summary.md"

md = []
md.append(f"# Round 5 — H1 数据摘要报告 (Researcher Profile)")
md.append(f"")
md.append(f"> **生成时间**: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M')} UTC")
md.append(f"> **时间框架**: {TIMEFRAME}")
md.append(f"> **品种数量**: {len(enriched_data)} / {len(TARGET_SYMBOLS)}")
md.append(f"> **研究轮次**: Round 5")
md.append(f"")
md.append(f"---")
md.append(f"")

# Section 1: Overview
md.append(f"## 1. 数据概览")
md.append(f"")
md.append(f"| 指标 | 值 |")
md.append(f"|------|-----|")
md.append(f"| 时间框架 | {TIMEFRAME} |")
md.append(f"| 品种数 | {len(enriched_data)} |")
md.append(f"| 总记录数 | {total_rows_all:,} |")
md.append(f"| 最早日期 | {stats_df['start'].min()} |")
md.append(f"| 最晚日期 | {stats_df['end'].max()} |")
md.append(f"| 平均每品种行数 | {total_rows_all // len(enriched_data):,} |")
md.append(f"| 行数最多 | {max_rows_sym} ({stats_df.loc[stats_df['symbol']==max_rows_sym, 'rows'].values[0]:,}) |")
md.append(f"| 行数最少 | {min_rows_sym} ({stats_df.loc[stats_df['symbol']==min_rows_sym, 'rows'].values[0]:,}) |")
md.append(f"")

# Section 2: Per-symbol detail
md.append(f"## 2. 逐品种详细信息")
md.append(f"")
md.append(f"### 2.1 数据范围与完整性")
md.append(f"")
md.append(f"| 品种 | 记录数 | 开始时间 | 结束时间 | 缺失值 | 缺失列 |")
md.append(f"|------|--------|----------|----------|--------|--------|")
for _, row in stats_df.iterrows():
    md.append(f"| {row['symbol']} | {row['rows']:,} | {row['start']} | {row['end']} | {row['missing_total']} | {row['missing_cols']} |")
md.append(f"")

# Section 3: Bull ratio & volatility
md.append(f"### 2.2 阳线比例与波动率")
md.append(f"")
md.append(f"| 品种 | 阳线比例 | 阴线比例 | 平均ATR(14) | 波动率(σ%) | ATR/价格% | 平均收盘价 |")
md.append(f"|------|---------|---------|-------------|-----------|-----------|-----------|")
for _, row in stats_df.sort_values('bull_ratio', ascending=False).iterrows():
    bull_str = f"{row['bull_ratio']*100:.2f}%"
    bear_str = f"{row['bear_ratio']*100:.2f}%"
    atr_str = f"{row['avg_atr']:.4f}" if row['avg_atr'] is not None else "N/A"
    vol_str = f"{row['volatility']:.4f}" if row['volatility'] is not None else "N/A"
    atrp_str = f"{row['atr_pct']:.2f}%" if row['atr_pct'] is not None else "N/A"
    close_str = f"{row['avg_close']:.4f}" if row['avg_close'] is not None else "N/A"
    md.append(f"| {row['symbol']} | {bull_str} | {bear_str} | {atr_str} | {vol_str} | {atrp_str} | {close_str} |")
md.append(f"")
md.append(f"**全品种平均阳线比例**: {avg_bull_ratio*100:.2f}%")
md.append(f"**全品种平均波动率**: {avg_volatility:.4f}%")
md.append(f"**最高波动率**: {highest_vol_sym} ({stats_df.loc[stats_df['symbol']==highest_vol_sym, 'volatility'].values[0]:.4f}%)")
md.append(f"**最低波动率**: {lowest_vol_sym} ({stats_df.loc[stats_df['symbol']==lowest_vol_sym, 'volatility'].values[0]:.4f}%)")
md.append(f"**最高平均ATR**: {highest_atr_sym} ({stats_df.loc[stats_df['symbol']==highest_atr_sym, 'avg_atr'].values[0]:.4f})")
md.append(f"**最低平均ATR**: {lowest_atr_sym} ({stats_df.loc[stats_df['symbol']==lowest_atr_sym, 'avg_atr'].values[0]:.4f})")
md.append(f"")

# Section 4: Session distribution
md.append(f"## 3. 各时段信号分布")
md.append(f"")
md.append(f"### 3.1 各品种各时段K线分布及阳线比例")
md.append(f"")
md.append(f"| 品种 | 亚洲K线数 | 亚洲阳率 | 欧洲K线数 | 欧洲阳率 | 美盘K线数 | 美盘阳率 |")
md.append(f"|------|----------|---------|----------|---------|----------|---------|")
for sym in sorted(enriched_data.keys()):
    asia_c = int(pivot_count.loc[sym, 'asia']) if 'asia' in pivot_count.columns and sym in pivot_count.index else 0
    eu_c = int(pivot_count.loc[sym, 'europe']) if 'europe' in pivot_count.columns and sym in pivot_count.index else 0
    us_c = int(pivot_count.loc[sym, 'us']) if 'us' in pivot_count.columns and sym in pivot_count.index else 0
    asia_b = f"{pivot_bull.loc[sym, 'asia']*100:.1f}%" if 'asia' in pivot_bull.columns and sym in pivot_bull.index else "N/A"
    eu_b = f"{pivot_bull.loc[sym, 'europe']*100:.1f}%" if 'europe' in pivot_bull.columns and sym in pivot_bull.index else "N/A"
    us_b = f"{pivot_bull.loc[sym, 'us']*100:.1f}%" if 'us' in pivot_bull.columns and sym in pivot_bull.index else "N/A"
    md.append(f"| {sym} | {asia_c:,} | {asia_b} | {eu_c:,} | {eu_b} | {us_c:,} | {us_b} |")
md.append(f"")

md.append(f"### 3.2 全品种各时段平均阳线比例")
md.append(f"")
md.append(f"| 时段 | 平均阳线比例 | 总K线数 |")
md.append(f"|------|-------------|--------|")
for sess in ['asia', 'europe', 'us']:
    avg_b = session_bull_df[session_bull_df['session'] == sess]['bull_ratio'].mean()
    total_k = session_bull_df[session_bull_df['session'] == sess]['count'].sum()
    md.append(f"| {sess} | {avg_b*100:.2f}% | {total_k:,} |")
md.append(f"")

# Section 5: Column completeness
md.append(f"## 4. 数据列完整性检查")
md.append(f"")
md.append(f"| 列名 | 状态 |")
md.append(f"|------|------|")
for col in REQUIRED_COLS:
    present = all(col in df.columns for df in enriched_data.values())
    md.append(f"| `{col}` | {'✓ 存在' if present else '✗ 缺失'} |")
md.append(f"")
md.append(f"**结论**: {'所有列完整 ✓' if all_ok else '存在缺失列 ⚠'}")
md.append(f"")

# Section 6: Cross-symbol stats
md.append(f"## 5. 全品种统计")
md.append(f"")
md.append(f"| 统计项 | 值 |")
md.append(f"|--------|-----|")
md.append(f"| 总记录数 | {total_rows_all:,} |")
md.append(f"| 最高波动品种 | {highest_vol_sym} ({stats_df.loc[stats_df['symbol']==highest_vol_sym, 'volatility'].values[0]:.4f}%) |")
md.append(f"| 最低波动品种 | {lowest_vol_sym} ({stats_df.loc[stats_df['symbol']==lowest_vol_sym, 'volatility'].values[0]:.4f}%) |")
md.append(f"| 最高阳线比例品种 | {highest_bull_sym} ({stats_df.loc[stats_df['symbol']==highest_bull_sym, 'bull_ratio'].values[0]*100:.2f}%) |")
md.append(f"| 最低阳线比例品种 | {lowest_bull_sym} ({stats_df.loc[stats_df['symbol']==lowest_bull_sym, 'bull_ratio'].values[0]*100:.2f}%) |")
md.append(f"")

report_content = '\n'.join(md)
with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    f.write(report_content)
print(f"\n✅ 报告已保存至: {REPORT_PATH}")

# ── Final stats for parent agent ──
print("\n" + "=" * 90)
print("  STRUCTURED DATA SUMMARY FOR PARENT AGENT")
print("=" * 90)
print(f"  Total records: {total_rows_all:,}")
print(f"  Symbols: {len(enriched_data)}")
print(f"  Date range: {stats_df['start'].min()} → {stats_df['end'].max()}")
print(f"  Highest volatility: {highest_vol_sym}")
print(f"  Lowest volatility: {lowest_vol_sym}")
print(f"  Avg bull ratio: {avg_bull_ratio*100:.2f}%")
print(f"  Columns check: {'ALL OK' if all_ok else 'ISSUES'}")
print("=" * 90)
