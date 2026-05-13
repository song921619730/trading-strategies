#!/usr/bin/env python3
"""
Researcher Task — M30 Data Summary
Loads M30 data for all 14 symbols, computes indicators,
and prints a structured summary table.
"""

import sys
import pandas as pd

# Ensure scripts dir is on path
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/scripts')

from data_loader import list_available_symbols, load_data, compute_indicators

def print_summary_table(data, tf):
    """Print a structured data summary table with fixed-width columns."""
    sep = "  " + "-" * 70
    header_line = "  " + "=" * 70

    print()
    print(header_line)
    print(f"  RESEARCHER DATA SUMMARY — {tf}")
    print(header_line)
    print(f"  {'Symbol':<12} {'Rows':>10} {'From':<22} {'To':<22} {'Sessions':>8}")
    print(sep)

    total_rows = 0
    symbol_count = 0

    for sym in sorted(data.keys()):
        df = data[sym]
        rows = len(df)
        total_rows += rows
        symbol_count += 1

        start = df.index[0].strftime('%Y-%m-%d %H:%M')
        end = df.index[-1].strftime('%Y-%m-%d %H:%M')

        if 'session' in df.columns:
            sessions = df['session'].nunique()
        else:
            sessions = '?'

        print(f"  {sym:<12} {rows:>10,} {start:<22} {end:<22} {sessions:>8}")

    print(sep)
    print(f"  {'TOTAL':<12} {total_rows:>10,}  ({symbol_count} symbols, {tf})")
    print(header_line)
    print()

def main():
    tf = "M30"

    # Step 1: List available symbols
    syms = list_available_symbols(timeframe=tf)
    print(f"\n{'='*70}")
    print(f"  [Researcher] M30 数据加载开始")
    print(f"  [Researcher] 发现 {len(syms)} 个品种: {', '.join(syms)}")
    print(f"{'='*70}\n")

    # Step 2: Load data for all symbols
    print("  Loading parquet data...")
    data = load_data(timeframe=tf)
    print(f"  Loaded {len(data)} symbols successfully.")

    # Step 3: Compute indicators
    print("  Computing technical indicators (ATR, RSI, MA, Bollinger, session, etc.)...")
    enriched = {}
    for sym, df in data.items():
        enriched[sym] = compute_indicators(df)
    print(f"  Indicators computed for {len(enriched)} symbols.\n")

    # Step 4: Print summary table
    print_summary_table(enriched, tf)

    # Step 5: Print available indicator columns
    sample_sym = list(enriched.keys())[0]
    sample_df = enriched[sample_sym]

    # Show original + indicator columns
    base_cols = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
    indicator_cols = [c for c in sample_df.columns if c not in base_cols]

    print(f"  {'='*70}")
    print(f"  可用指标列列表 ({len(indicator_cols)} columns)")
    print(f"  {'='*70}")
    print(f"  Base OHLCV columns: {base_cols}")
    print(f"  Indicator columns:  {indicator_cols}")
    print()
    print(f"  Sample from {sample_sym}:")
    print(f"  {sample_df[indicator_cols].tail(3).to_string(index=True)}")
    print()

    # Step 6: Ready status
    print(f"  {'='*70}")
    print(f"  ✅ 就绪状态声明")
    print(f"  {'='*70}")
    print(f"  Researcher 任务完成。")
    print(f"  - 时间框架: {tf}")
    print(f"  - 品种数量: {len(enriched)}")
    print(f"  - 数据总行数: {sum(len(v) for v in enriched.values()):,}")
    print(f"  - 指标数量: {len(indicator_cols)}")
    print(f"  - 状态: 数据已加载并增强，可供 Analyst 进行假设测试。")
    print(f"  {'='*70}\n")

if __name__ == "__main__":
    main()
