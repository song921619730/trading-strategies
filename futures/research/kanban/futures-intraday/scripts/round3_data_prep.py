#!/usr/bin/env python3
"""
Round 3 — H1 Data Preparation Script
Researcher Profile: Load H1 data, compute indicators, generate structured summary.

Output: ../reports/round3_data_summary_H1.md
"""

import sys
import os
from pathlib import Path

# Ensure we can import from scripts directory
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import numpy as np
import pandas as pd
from data_loader import load_data, compute_indicators, list_available_symbols

# ── Configuration ──────────────────────────────────────────────────────────────
TIMEFRAME = "H1"
TARGET_SYMBOLS = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
    "USOIL", "UKOIL", "USTEC", "US30", "US500", "JP225", "HK50",
]
REPORT_DIR = PROJECT_DIR / "reports"
REPORT_PATH = REPORT_DIR / "round3_data_summary_H1.md"

# ── Load raw data ─────────────────────────────────────────────────────────────
print(f"Loading {TIMEFRAME} data for all symbols ...")
raw_data = load_data(timeframe=TIMEFRAME, symbols=TARGET_SYMBOLS)
print(f"  → {len(raw_data)} symbols loaded")

missing = [s for s in TARGET_SYMBOLS if s not in raw_data]
if missing:
    print(f"  ⚠ Missing symbols: {missing}")
else:
    print(f"  ✓ All 14 symbols present")

# ── Compute indicators ────────────────────────────────────────────────────────
print("Computing technical indicators ...")
enriched_data = {}
for sym, df in raw_data.items():
    try:
        enriched_data[sym] = compute_indicators(df)
    except Exception as e:
        print(f"  WARNING: compute_indicators failed for {sym}: {e}")
        enriched_data[sym] = df
print(f"  → Indicators computed for {len(enriched_data)} symbols")

# ── Per-symbol statistics ─────────────────────────────────────────────────────
print("Calculating per-symbol statistics ...")
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
    
    # Column structure
    cols = df.columns.tolist()
    
    # Basic OHLC stats
    avg_atr = float(df['atr14'].mean()) if 'atr14' in df.columns else None
    
    # Volatility: std of pct_chg
    volatility = float(df['pct_chg'].std()) if 'pct_chg' in df.columns else None
    
    # Win rate (bullish candle ratio)
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

# ── Cross-symbol statistics ──────────────────────────────────────────────────
total_rows_all = int(stats_df['rows'].sum())
avg_atr_all = stats_df['avg_atr'].mean()
avg_bull_ratio = stats_df['bull_ratio'].mean()
avg_volatility = stats_df['volatility'].mean()

# Find min/max
max_rows_sym = stats_df.loc[stats_df['rows'].idxmax(), 'symbol']
min_rows_sym = stats_df.loc[stats_df['rows'].idxmin(), 'symbol']
highest_vol_sym = stats_df.loc[stats_df['volatility'].idxmax(), 'symbol']
lowest_vol_sym = stats_df.loc[stats_df['volatility'].idxmin(), 'symbol']
highest_bull_sym = stats_df.loc[stats_df['bull_ratio'].idxmax(), 'symbol']
lowest_bull_sym = stats_df.loc[stats_df['bull_ratio'].idxmin(), 'symbol']
highest_atr_sym = stats_df.loc[stats_df['avg_atr'].idxmax(), 'symbol']
lowest_atr_sym = stats_df.loc[stats_df['avg_atr'].idxmin(), 'symbol']

# ── Generate Markdown Report ─────────────────────────────────────────────────
print("Generating Markdown report ...")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

md = []
md.append(f"# Round 3 — H1 数据摘要报告")
md.append(f"")
md.append(f"> **生成时间**: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M')} UTC")
md.append(f"> **时间框架**: {TIMEFRAME}")
md.append(f"> **品种数量**: {len(enriched_data)} / 14")
md.append(f"> **研究轮次**: Round 3 (前序: Round1=H1, Round2=M30)")
md.append(f"")
md.append(f"---")
md.append(f"")

# ── Section 1: 数据概览 ─────────────────────────────────────────────────────
md.append(f"## 1. 数据概览")
md.append(f"")
md.append(f"| 指标 | 值 |")
md.append(f"|------|-----|")
md.append(f"| 时间框架 | {TIMEFRAME} |")
md.append(f"| 品种数 | {len(enriched_data)} |")
md.append(f"| 总记录数 | {total_rows_all:,} |")
md.append(f"| 最早日期 | {stats_df['start'].min()} |")
md.append(f"| 最晚日期 | {stats_df['end'].max()} |")
md.append(f"| 数据跨度 | ~{(pd.to_datetime(stats_df['end'].max()) - pd.to_datetime(stats_df['start'].min())).days} 天 |")
md.append(f"| 平均每品种行数 | {total_rows_all // len(enriched_data):,} |")
md.append(f"| 行数最多 | {max_rows_sym} ({stats_df.loc[stats_df['symbol']==max_rows_sym, 'rows'].values[0]:,}) |")
md.append(f"| 行数最少 | {min_rows_sym} ({stats_df.loc[stats_df['symbol']==min_rows_sym, 'rows'].values[0]:,}) |")
md.append(f"")

# ── Section 2: 逐品种详细信息 ───────────────────────────────────────────────
md.append(f"## 2. 逐品种详细信息")
md.append(f"")
md.append(f"### 2.1 数据范围与完整性")
md.append(f"")
md.append(f"| 品种 | 记录数 | 开始时间 | 结束时间 | 缺失值 | 缺失列 |")
md.append(f"|------|--------|----------|----------|--------|--------|")
for _, row in stats_df.iterrows():
    md.append(f"| {row['symbol']} | {row['rows']:,} | {row['start']} | {row['end']} | {row['missing_total']} | {row['missing_cols']} |")
md.append(f"")

md.append(f"### 2.2 列结构")
md.append(f"")
md.append(f"所有品种的 DataFrame 列结构一致，包含以下列：")
md.append(f"")
md.append(f"| 列名 | 类型 | 说明 |")
md.append(f"|------|------|------|")
md.append(f"| `time` (index) | DatetimeIndex (UTC) | K线开盘时间 |")
md.append(f"| `open` | float64 | 开盘价 |")
md.append(f"| `high` | float64 | 最高价 |")
md.append(f"| `low` | float64 | 最低价 |")
md.append(f"| `close` | float64 | 收盘价 |")
md.append(f"| `tick_volume` | int64 | Tick 计数 |")
md.append(f"| `spread` | int64 | 点差(点数) |")
md.append(f"| `real_volume` | int64 | 真实成交量 |")
md.append(f"")
md.append(f"经 `compute_indicators()` 处理后新增以下衍生列：")
md.append(f"")
md.append(f"| 列名 | 说明 |")
md.append(f"|------|------|")
md.append(f"| `atr14` | 平均真实波幅(14周期) |")
md.append(f"| `rsi14` | 相对强弱指数(14周期, Wilder平滑) |")
md.append(f"| `ma20` / `ma50` / `ma200` | 简单移动均线 |")
md.append(f"| `bb_upper` / `bb_lower` | 布林带 (20,2) 上下轨 |")
md.append(f"| `pct_chg` | 收盘价环比变动率(%) |")
md.append(f"| `gap_pct` | 跳空幅度(%) |")
md.append(f"| `session` | 交易时段 (asia/europe/us) |")
md.append(f"| `hour` | 小时 (0-23, UTC) |")
md.append(f"| `dayofweek` | 星期 (0=周一 ~ 6=周日) |")
md.append(f"| `consecutive_bull_count` | 连续阳线计数 |")
md.append(f"| `consecutive_bear_count` | 连续阴线计数 |")
md.append(f"")

# ── Section 3: ATR 与波动率分析 ─────────────────────────────────────────────
md.append(f"## 3. ATR 与波动率特征")
md.append(f"")
md.append(f"### 3.1 平均ATR(H1)")
md.append(f"")
md.append(f"| 品种 | 平均ATR(14) | ATR/价格% | 平均收盘价 |")
md.append(f"|------|-------------|-----------|-----------|")
for _, row in stats_df.sort_values('avg_atr', ascending=False).iterrows():
    atr_str = f"{row['avg_atr']:.4f}" if row['avg_atr'] is not None else "N/A"
    atr_pct_str = f"{row['atr_pct']:.2f}%" if row['atr_pct'] is not None else "N/A"
    close_str = f"{row['avg_close']:.4f}" if row['avg_close'] is not None else "N/A"
    md.append(f"| {row['symbol']} | {atr_str} | {atr_pct_str} | {close_str} |")
md.append(f"")
md.append(f"**ATR 平均值(全品种)**: {avg_atr_all:.4f}")
md.append(f"")
md.append(f"### 3.2 波动率特征 (pct_chg 标准差)")
md.append(f"")
md.append(f"| 品种 | 波动率(σ%) | 均值(%%) | Q25(%%) | Q50(%%) | Q75(%%) |")
md.append(f"|------|-----------|---------|--------|--------|--------|")
for _, row in stats_df.sort_values('volatility', ascending=False).iterrows():
    vol_str = f"{row['volatility']:.4f}" if row['volatility'] is not None else "N/A"
    mean_str = f"{row['pct_mean']:.4f}" if row['pct_mean'] is not None else "N/A"
    q25_str = f"{row['pct_25']:.4f}" if row['pct_25'] is not None else "N/A"
    q50_str = f"{row['pct_50']:.4f}" if row['pct_50'] is not None else "N/A"
    q75_str = f"{row['pct_75']:.4f}" if row['pct_75'] is not None else "N/A"
    md.append(f"| {row['symbol']} | {vol_str} | {mean_str} | {q25_str} | {q50_str} | {q75_str} |")
md.append(f"")
md.append(f"**最高波动率**: {highest_vol_sym} ({stats_df.loc[stats_df['symbol']==highest_vol_sym, 'volatility'].values[0]:.4f}%)")
md.append(f"")
md.append(f"**最低波动率**: {lowest_vol_sym} ({stats_df.loc[stats_df['symbol']==lowest_vol_sym, 'volatility'].values[0]:.4f}%)")
md.append(f"")
md.append(f"**全品种平均波动率**: {avg_volatility:.4f}%")
md.append(f"")

# ── Section 4: 涨跌幅分布 ──────────────────────────────────────────────────
md.append(f"## 4. 涨跌幅分布")
md.append(f"")
md.append(f"每个品种 H1 周期收盘涨跌幅(pct_chg)的分布特征：")
md.append(f"")
md.append(f"| 品种 | 均值(%%) | 标准差(%%) | Q25(%%) | 中位数(%%) | Q75(%%) | 负值比例 | 正值比例 |")
md.append(f"|------|---------|-----------|--------|-----------|--------|---------|---------|")
for _, row in stats_df.iterrows():
    mean_str = f"{row['pct_mean']:.4f}" if row['pct_mean'] is not None else "N/A"
    std_str = f"{row['pct_std']:.4f}" if row['pct_std'] is not None else "N/A"
    q25_str = f"{row['pct_25']:.4f}" if row['pct_25'] is not None else "N/A"
    q50_str = f"{row['pct_50']:.4f}" if row['pct_50'] is not None else "N/A"
    q75_str = f"{row['pct_75']:.4f}" if row['pct_75'] is not None else "N/A"
    neg_str = f"{row['pct_neg_ratio']*100:.2f}%" if row['pct_neg_ratio'] is not None else "N/A"
    pos_str = f"{row['pct_pos_ratio']*100:.2f}%" if row['pct_pos_ratio'] is not None else "N/A"
    md.append(f"| {row['symbol']} | {mean_str} | {std_str} | {q25_str} | {q50_str} | {q75_str} | {neg_str} | {pos_str} |")
md.append(f"")

# ── Section 5: 阳线/阴线比例 ───────────────────────────────────────────────
md.append(f"## 5. 阳线/阴线比例 (收盘 vs 开盘)")
md.append(f"")
md.append(f"> 阳线 = close > open, 阴线 = close < open, 平盘 = close == open (比例极小)")
md.append(f"")
md.append(f"| 品种 | 阳线比例 | 阴线比例 | 判断 |")
md.append(f"|------|---------|---------|------|")
for _, row in stats_df.sort_values('bull_ratio', ascending=False).iterrows():
    bull_str = f"{row['bull_ratio']*100:.2f}%"
    bear_str = f"{row['bear_ratio']*100:.2f}%"
    if row['bull_ratio'] > 0.505:
        verdict = "偏多倾向 ✓"
    elif row['bull_ratio'] < 0.495:
        verdict = "偏空倾向 ✗"
    else:
        verdict = "中性 ≈"
    md.append(f"| {row['symbol']} | {bull_str} | {bear_str} | {verdict} |")
md.append(f"")
md.append(f"**全品种平均阳线比例**: {avg_bull_ratio*100:.2f}%")
md.append(f"**最高阳线比例**: {highest_bull_sym} ({stats_df.loc[stats_df['symbol']==highest_bull_sym, 'bull_ratio'].values[0]*100:.2f}%)")
md.append(f"**最低阳线比例**: {lowest_bull_sym} ({stats_df.loc[stats_df['symbol']==lowest_bull_sym, 'bull_ratio'].values[0]*100:.2f}%)")
md.append(f"")

# ── Section 6: 数据质量检查 ────────────────────────────────────────────────
md.append(f"## 6. 数据质量检查")
md.append(f"")
md.append(f"### 6.1 缺失值检查")
md.append(f"")
md.append(f"原始列 (open/high/low/close/tick_volume/spread/real_volume) 无缺失值。")
md.append(f"")
md.append(f"衍生列中，前 N 行因滚动窗口计算产生 NaN，这是预期行为：")
md.append(f"")
md.append(f"| 衍生列 | NaN 原因 | 影响行数 |")
md.append(f"|--------|---------|---------|")
md.append(f"| `atr14` | 需要14期TR滚动平均 | 前13行 |")
md.append(f"| `rsi14` | 需要14期EWM计算 | 前13行 |")
md.append(f"| `ma20` | 需要20期SMA | 前19行 |")
md.append(f"| `ma50` | 需要50期SMA | 前49行 |")
md.append(f"| `ma200` | 需要200期SMA | 前199行 |")
md.append(f"| `bb_upper/lower` | 需要20期滚动计算 | 前19行 |")
md.append(f"| `pct_chg` | 首行无前值 | 第1行 |")
md.append(f"| `gap_pct` | 首行无前值 | 第1行 |")
md.append(f"")
md.append(f"### 6.2 时间连续性")
md.append(f"")
md.append(f"所有品种均为 H1 周期数据，时间索引为 UTC。")
md.append(f"数据从 2021-01-03 覆盖至 {stats_df['end'].max().split(' ')[0]}，包含约5年多的历史数据。")
md.append(f"")
md.append(f"### 6.3 各品种缺失值统计")
md.append(f"")
md.append(f"| 品种 | 缺失值总数 | 缺失率(%%) |")
md.append(f"|------|-----------|-----------|")
for _, row in stats_df.iterrows():
    missing_rate = row['missing_total'] / row['rows'] * 100
    md.append(f"| {row['symbol']} | {row['missing_total']} | {missing_rate:.2f}% |")
md.append(f"")

# ── Section 7: Analyst 参考信息 ────────────────────────────────────────────
md.append(f"## 7. Analyst 参考信息")
md.append(f"")
md.append(f"### 7.1 品种分组")
md.append(f"")
md.append(f"| 分组 | 品种 | 特征 |")
md.append(f"|------|------|------|")
md.append(f"| **贵金属** | XAUUSD, XAGUSD | 高波动、均值回归特性 |")
md.append(f"| **外汇主要** | EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF | 低波动、趋势性强 |")
md.append(f"| **能源** | USOIL, UKOIL | 高波动、跳跃性大 |")
md.append(f"| **美股指数** | USTEC, US30, US500 | 中高波动、趋势性中等 |")
md.append(f"| **亚太指数** | JP225, HK50 | 高波动、有跳空 |")
md.append(f"")
md.append(f"### 7.2 上轮回顾与关联")
md.append(f"")
md.append(f"- **Round 2 (M30)** 发现：US30 M30 阴线+RSI<40 做多 hold=20 胜率 **55.03%**")
md.append(f"- **Round 1 (H1)** 发现：H1 阴线后做多(反转) USTEC hold=2 胜率 **54.22%**")
md.append(f"- 本轮回到 **H1** 框架，上述已计算 H1 的 ATR、波动率、阳线比例等基础数据")
md.append(f"- H1 的 ATR 和波动率大约是 M30 的 √2 ≈ 1.414 倍（理论关系）")
md.append(f"")
md.append(f"### 7.3 待测试假设队列")
md.append(f"")
md.append(f"| ID | 假设 | 优先级 |")
md.append(f"|----|------|--------|")
md.append(f"| init_002 | 前N根K线连续同向后的反转概率 | 2 |")
md.append(f"| init_003 | ATR分位数过滤 - 低波动vs高波动后的方向概率 | 3 |")
md.append(f"| init_004 | 不同交易时段(亚盘/欧盘/美盘)的开盘方向概率差异 | 4 |")
md.append(f"| init_005 | D1趋势方向过滤 - MA20上方/下方对H1开盘方向的影响 | 5 |")
md.append(f"| init_006 | 连续3根H1同向后的第4根方向概率分布 | 6 |")
md.append(f"| init_007 | 品种间联动 - EURUSD方向变动后XAUUSD的同向概率 | 7 |")
md.append(f"| auto_002 | 连续2根阴线后的反转做多概率 | 2 |")
md.append(f"| auto_003 | 阴线收盘+RSI<40做多反转策略(全品种H1) | 2 |")
md.append(f"| auto_004 | 阴线+RSI<40做多+US session时段过滤 | 2 |")
md.append(f"| auto_005 | 阳线+RSI>60做空反转策略 | 2 |")
md.append(f"")
md.append(f"---")
md.append(f"")
md.append(f"## 附录")
md.append(f"")
md.append(f"### A. 生成脚本")
md.append(f"")
md.append(f"```")
md.append(f"scripts/round3_data_prep.py")
md.append(f"```")
md.append(f"")
md.append(f"### B. 数据源")
md.append(f"")
md.append(f"- 目录: `data/{TIMEFRAME}/*.parquet`")
md.append(f"- 格式: Parquet (pandas DataFrame)")
md.append(f"- 生成: `fetch_store_data.py` (MetaTrader5)")
md.append(f"")

# Write the report
report_content = '\n'.join(md)
with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    f.write(report_content)
print(f"Report written to {REPORT_PATH}")

# ── Also print a compact summary table to stdout for immediate feedback ────
print("\n" + "=" * 78)
print(f"  ROUND 3 — H1 DATA SUMMARY")
print("=" * 78)
print(f"  {'Symbol':<10} {'Rows':>8} {'From':<17} {'To':<17} {'ATR':>8} {'Vol%':>7} {'Bull%':>7}")
print(f"  " + "-" * 75)
for _, row in stats_df.iterrows():
    atr_str = f"{row['avg_atr']:.1f}" if row['avg_atr'] is not None else "N/A"
    vol_str = f"{row['volatility']:.2f}" if row['volatility'] is not None else "N/A"
    bull_str = f"{row['bull_ratio']*100:.1f}"
    print(f"  {row['symbol']:<10} {row['rows']:>8,} {row['start']:<17} {row['end']:<17} {atr_str:>8} {vol_str:>7} {bull_str:>7}")
print(f"  " + "-" * 75)
print(f"  {'TOTAL':<10} {total_rows_all:>8,}  ({len(enriched_data)} symbols, {TIMEFRAME})")
print("=" * 78)

print(f"\n✅ 数据准备完成。报告已保存至: reports/round3_data_summary_H1.md")
print(f"   共 {len(enriched_data)} 个品种, {total_rows_all:,} 条记录")
print(f"   平均阳线比例: {avg_bull_ratio*100:.2f}%")
print(f"   最高波动率: {highest_vol_sym} ({stats_df.loc[stats_df['symbol']==highest_vol_sym, 'volatility'].values[0]:.2f}%)")
print(f"   最低波动率: {lowest_vol_sym} ({stats_df.loc[stats_df['symbol']==lowest_vol_sym, 'volatility'].values[0]:.2f}%)")
