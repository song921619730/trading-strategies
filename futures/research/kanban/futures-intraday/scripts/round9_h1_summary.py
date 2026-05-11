#!/usr/bin/env python3
"""
Round 9 — H1 Data Summary for Researcher Profile
Computes session-based statistics for 14 futures symbols.
"""

import sys, os, json
from pathlib import Path

sys.path.insert(0, '.')
from data_loader import load_data, compute_indicators, list_available_symbols

import numpy as np
import pandas as pd

# ---- 1. Load all H1 data ----
print("Loading H1 data for all 14 symbols ...")
h1_raw = load_data(timeframe="H1")
print("Loaded %d symbols.\n" % len(h1_raw))

# ---- 2. Compute indicators ----
print("Computing indicators ...")
h1_data = {}
for sym, df in h1_raw.items():
    try:
        h1_data[sym] = compute_indicators(df)
    except Exception as e:
        print("  WARNING: %s indicator computation failed: %s" % (sym, e))
        h1_data[sym] = df

print("Enriched %d DataFrames.\n" % len(h1_data))

# ---- 3. Session label mapping ----
session_names = {'asia': '亚盘', 'europe': '欧盘', 'us': '美盘'}
sessions_ordered = ['asia', 'europe', 'us']

# ---- 4. Compute per-symbol, per-session statistics ----
results = {}

for sym in sorted(h1_data.keys()):
    df = h1_data[sym]
    rows_total = len(df)
    date_start = df.index[0].strftime('%Y-%m-%d %H:%M')
    date_end = df.index[-1].strftime('%Y-%m-%d %H:%M')

    # Determine candle direction
    df['is_bull'] = df['close'] > df['open']
    df['is_bear'] = df['close'] < df['open']

    # Session-level stats
    session_stats = {}
    for sess in sessions_ordered:
        mask = df['session'] == sess
        sub = df[mask]
        n = len(sub)
        if n == 0:
            session_stats[sess] = {'count': 0, 'bull_pct': np.nan, 'bear_pct': np.nan, 'avg_atr14_pct': np.nan}
            continue

        bull_count = sub['is_bull'].sum()
        bear_count = sub['is_bear'].sum()
        bull_pct = bull_count / n * 100
        bear_pct = bear_count / n * 100

        # ATR14 / close as % (average normalized volatility)
        atr_valid = sub['atr14'].dropna()
        close_valid = sub.loc[atr_valid.index, 'close']
        atr_pct = (atr_valid / close_valid * 100).mean() if len(atr_valid) > 0 else np.nan

        session_stats[sess] = {
            'count': n,
            'bull_pct': round(bull_pct, 2),
            'bear_pct': round(bear_pct, 2),
            'avg_atr14_pct': round(atr_pct, 4) if not np.isnan(atr_pct) else None
        }

    results[sym] = {
        'rows': rows_total,
        'date_start': date_start,
        'date_end': date_end,
        'sessions': session_stats
    }

# ---- 5. Print structured output ----

print("=" * 90)
print("  ROUND 9 — H1 DATA SUMMARY (Researcher Profile)")
print("  待测假设: init_004 — 不同交易时段(亚盘/欧盘/美盘)的H1开盘方向概率差异")
print("=" * 90)

# 5a. Data overview table
print()
print("-" * 90)
print("  1. 数据概览")
print("-" * 90)
print("  %-10s %8s %-22s %-22s" % ('品种', '记录数', '起始时间', '结束时间'))
print("  " + "-" * 62)
total_rows = 0
for sym in sorted(results.keys()):
    r = results[sym]
    total_rows += r['rows']
    print("  %-10s %8d %-22s %-22s" % (sym, r['rows'], r['date_start'], r['date_end']))
print("  " + "-" * 62)
print("  %-10s %8d  (共 %d 个品种)" % ('合计', total_rows, len(results)))
print()

# 5b. Bull candle probability matrix
print("-" * 90)
print("  2. 全品种各时段阳线比例矩阵 (阳线比例 %%)")
print("-" * 90)
print("  %-10s %12s %12s %12s %8s" % ('品种', '亚盘(00-08)', '欧盘(08-16)', '美盘(16-24)', '全场'))
print("  " + "-" * 54)

bull_matrix = {}
for sym in sorted(results.keys()):
    r = results[sym]
    asia_bull = r['sessions']['asia']['bull_pct']
    euro_bull = r['sessions']['europe']['bull_pct']
    us_bull = r['sessions']['us']['bull_pct']
    # Overall bull pct
    df = h1_data[sym]
    overall_bull = (df['close'] > df['open']).sum() / len(df) * 100
    bull_matrix[sym] = {
        'asia': asia_bull,
        'europe': euro_bull,
        'us': us_bull,
        'overall': round(overall_bull, 2)
    }
    print("  %-10s %11.2f%% %11.2f%% %11.2f%% %7.2f%%" % (
        sym, asia_bull, euro_bull, us_bull, bull_matrix[sym]['overall']))

print("  " + "-" * 54)
# Average across all symbols
avg_asia = np.nanmean([bull_matrix[s]['asia'] for s in bull_matrix])
avg_euro = np.nanmean([bull_matrix[s]['europe'] for s in bull_matrix])
avg_us = np.nanmean([bull_matrix[s]['us'] for s in bull_matrix])
avg_all = np.nanmean([bull_matrix[s]['overall'] for s in bull_matrix])
print("  %-10s %11.2f%% %11.2f%% %11.2f%% %7.2f%%" % ('均值', avg_asia, avg_euro, avg_us, avg_all))
print()

# 5c. Volatility by session
print("-" * 90)
print("  3. 各时段波动率特征 (ATR14/Close 均值 %%)")
print("-" * 90)
print("  %-10s %10s %10s %10s %10s" % ('品种', '亚盘ATR%', '欧盘ATR%', '美盘ATR%', '全场ATR%'))
print("  " + "-" * 50)

vol_matrix = {}
for sym in sorted(results.keys()):
    r = results[sym]
    asia_atr = r['sessions']['asia']['avg_atr14_pct']
    euro_atr = r['sessions']['europe']['avg_atr14_pct']
    us_atr = r['sessions']['us']['avg_atr14_pct']
    # Overall
    df = h1_data[sym]
    atr_all = (df['atr14'].dropna() / df.loc[df['atr14'].dropna().index, 'close'] * 100).mean()
    vol_matrix[sym] = {
        'asia': asia_atr,
        'europe': euro_atr,
        'us': us_atr,
        'overall': round(atr_all, 4)
    }
    print("  %-10s %9.4f%% %9.4f%% %9.4f%% %9.4f%%" % (
        sym, asia_atr if asia_atr is not None else 0,
        euro_atr if euro_atr is not None else 0,
        us_atr if us_atr is not None else 0,
        atr_all))

print("  " + "-" * 50)
avg_atr_asia = np.nanmean([vol_matrix[s]['asia'] for s in vol_matrix if vol_matrix[s]['asia'] is not None])
avg_atr_euro = np.nanmean([vol_matrix[s]['europe'] for s in vol_matrix if vol_matrix[s]['europe'] is not None])
avg_atr_us = np.nanmean([vol_matrix[s]['us'] for s in vol_matrix if vol_matrix[s]['us'] is not None])
avg_atr_all = np.nanmean([vol_matrix[s]['overall'] for s in vol_matrix])
print("  %-10s %9.4f%% %9.4f%% %9.4f%% %9.4f%%" % ('均值', avg_atr_asia, avg_atr_euro, avg_atr_us, avg_atr_all))
print()

# 5d. Directional bias analysis
print("-" * 90)
print("  4. 方向性偏差分析 (偏差 = |阳线比例 - 50%|)")
print("-" * 90)
print("  %-10s %10s %10s %10s %14s" % ('品种', '亚盘偏差', '欧盘偏差', '美盘偏差', '最大偏差时段'))
print("  " + "-" * 54)

bias_results = []
for sym in sorted(results.keys()):
    bm = bull_matrix[sym]
    asia_bias = abs(bm['asia'] - 50)
    euro_bias = abs(bm['europe'] - 50)
    us_bias = abs(bm['us'] - 50)
    
    max_bias = max(asia_bias, euro_bias, us_bias)
    if max_bias == asia_bias:
        max_sess = '亚盘'
    elif max_bias == euro_bias:
        max_sess = '欧盘'
    else:
        max_sess = '美盘'
    
    bull_val = {'asia': bm['asia'], 'europe': bm['europe'], 'us': bm['us']}
    bias_results.append({
        'symbol': sym,
        'asia_bias': round(asia_bias, 2),
        'europe_bias': round(euro_bias, 2),
        'us_bias': round(us_bias, 2),
        'max_session': max_sess,
        'max_bias': round(max_bias, 2),
        'asia_bull': bm['asia'],
        'europe_bull': bm['europe'],
        'us_bull': bm['us']
    })
    
    print("  %-10s %9.2f%% %9.2f%% %9.2f%%  %8s(%.2f%%)" % (
        sym, asia_bias, euro_bias, us_bias, max_sess, max_bias))

print("  " + "-" * 54)
print()

# 5e. Symbols with significant bias (>1%)
print("-" * 90)
print("  5. 明显方向性偏差品种 (偏差 > 1.0%%)")
print("-" * 90)
threshold = 1.0
found_any = False
for rb in bias_results:
    flagged = []
    for sess_name, sess_key in [('亚盘', 'asia'), ('欧盘', 'europe'), ('美盘', 'us')]:
        bias = abs(rb[sess_key + '_bias'])
        if bias > threshold:
            bull_val = rb[sess_key + '_bull']
            direction = '偏多(阳线多)' if bull_val > 50 else '偏空(阴线多)'
            flagged.append("%s%s(偏差%.2f%%)" % (sess_name, direction, bias))
    if flagged:
        found_any = True
        print("  %-10s → %s" % (rb['symbol'], '; '.join(flagged)))

if not found_any:
    print("  (无品种偏差超过 1.0%%)")
print()

# 5f. Per-session direction summary
print("-" * 90)
print("  6. 各时段方向性汇总 (偏多/偏空品种计数)")
print("-" * 90)
for sess_name, sess_key in [('亚盘', 'asia'), ('欧盘', 'europe'), ('美盘', 'us')]:
    bullish_syms = []
    bearish_syms = []
    for rb in bias_results:
        bull_val = rb[sess_key + '_bull']
        if bull_val > 50:
            bullish_syms.append(rb['symbol'])
        elif bull_val < 50:
            bearish_syms.append(rb['symbol'])
    print("  %s: 偏多 %d 个 %s, 偏空 %d 个 %s" % (sess_name, len(bullish_syms), bullish_syms, len(bearish_syms), bearish_syms))
print()

# ---- 6. Save to file ----
save_path = Path('/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/reports/round9_data_summary_H1.md')
save_path.parent.mkdir(parents=True, exist_ok=True)

lines = []
lines.append("# Round 9 H1 Data Summary — Futures Intraday Pattern Mining\n")
lines.append("**待测假设**: init_004 — 不同交易时段(亚盘/欧盘/美盘)的H1开盘方向概率差异\n")
lines.append("**时间框架**: H1\n")
lines.append("**品种数**: 14\n")
lines.append("**生成时间**: %s UTC\n" % pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'))
lines.append("\n---\n\n")
lines.append("## 1. 数据概览\n\n")
lines.append("| 品种 | 记录数 | 起始时间 | 结束时间 |\n")
lines.append("|------|--------|----------|----------|\n")
for sym in sorted(results.keys()):
    r = results[sym]
    lines.append("| %s | %d | %s | %s |\n" % (sym, r['rows'], r['date_start'], r['date_end']))
lines.append("| **合计** | **%d** | **(14 个品种)** | |\n" % total_rows)
lines.append("\n")

lines.append("## 2. 全品种各时段阳线比例矩阵\n\n")
lines.append("| 品种 | 亚盘(00:00-08:00 UTC) | 欧盘(08:00-16:00 UTC) | 美盘(16:00-24:00 UTC) | 全场 |\n")
lines.append("|------|----------------------|----------------------|----------------------|------|\n")
for sym in sorted(results.keys()):
    bm = bull_matrix[sym]
    lines.append("| %s | %.2f%% | %.2f%% | %.2f%% | %.2f%% |\n" % (
        sym, bm['asia'], bm['europe'], bm['us'], bm['overall']))
lines.append("| **均值** | **%.2f%%** | **%.2f%%** | **%.2f%%** | **%.2f%%** |\n" % (avg_asia, avg_euro, avg_us, avg_all))
lines.append("\n")

lines.append("## 3. 各时段波动率特征 (ATR14/Close 均值 %%)\n\n")
lines.append("| 品种 | 亚盘 ATR%% | 欧盘 ATR%% | 美盘 ATR%% | 全场 ATR%% |\n")
lines.append("|------|-----------|-----------|-----------|-----------|\n")
for sym in sorted(results.keys()):
    vm = vol_matrix[sym]
    asia_v = "%.4f%%" % vm['asia'] if vm['asia'] is not None else "N/A"
    euro_v = "%.4f%%" % vm['europe'] if vm['europe'] is not None else "N/A"
    us_v = "%.4f%%" % vm['us'] if vm['us'] is not None else "N/A"
    lines.append("| %s | %s | %s | %s | %.4f%% |\n" % (sym, asia_v, euro_v, us_v, vm['overall']))
lines.append("| **均值** | **%.4f%%** | **%.4f%%** | **%.4f%%** | **%.4f%%** |\n" % (avg_atr_asia, avg_atr_euro, avg_atr_us, avg_atr_all))
lines.append("\n")

lines.append("## 4. 方向性偏差分析\n\n")
lines.append("### 4.1 各品种各时段偏差统计\n\n")
lines.append("| 品种 | 亚盘偏差 | 欧盘偏差 | 美盘偏差 | 最大偏差时段 | 最大偏差值 |\n")
lines.append("|------|----------|----------|----------|-------------|-----------|\n")
for rb in bias_results:
    lines.append("| %s | %.2f%% | %.2f%% | %.2f%% | %s | %.2f%% |\n" % (
        rb['symbol'], rb['asia_bias'], rb['europe_bias'], rb['us_bias'],
        rb['max_session'], rb['max_bias']))

lines.append("\n### 4.2 明显方向性偏差品种 (偏差 > 1.0%%)\n\n")
lines.append("| 品种 | 显著时段 | 方向 | 偏差值 |\n")
lines.append("|------|----------|------|--------|\n")
for rb in bias_results:
    for sess_name, sess_key in [('亚盘', 'asia'), ('欧盘', 'europe'), ('美盘', 'us')]:
        bias = abs(rb[sess_key + '_bias'])
        if bias > threshold:
            bull_val = rb[sess_key + '_bull']
            direction = '偏多(阳线多)' if bull_val > 50 else '偏空(阴线多)'
            lines.append("| %s | %s | %s | %.2f%% |\n" % (rb['symbol'], sess_name, direction, bias))
lines.append("\n")

lines.append("### 4.3 各时段方向性汇总\n\n")
lines.append("| 时段 | 偏多品种数 | 偏多品种 | 偏空品种数 | 偏空品种 |\n")
lines.append("|------|-----------|----------|-----------|----------|\n")
for sess_name, sess_key in [('亚盘', 'asia'), ('欧盘', 'europe'), ('美盘', 'us')]:
    bullish_syms = []
    bearish_syms = []
    for rb in bias_results:
        bull_val = rb[sess_key + '_bull']
        if bull_val > 50:
            bullish_syms.append(rb['symbol'])
        elif bull_val < 50:
            bearish_syms.append(rb['symbol'])
    lines.append("| %s | %d | %s | %d | %s |\n" % (
        sess_name, len(bullish_syms), '、'.join(bullish_syms),
        len(bearish_syms), '、'.join(bearish_syms)))

lines.append("\n---\n\n")
lines.append("*Report generated by Researcher Profile for Round 9*\n")

with open(save_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Summary saved to: %s" % save_path)
print("Done.")
