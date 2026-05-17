#!/usr/bin/env python3
"""Deep analysis of top Round 60 findings - extract full hold period tables."""
import json
from pathlib import Path

with open("logs/round60_m1m5_results.json") as f:
    data = json.load(f)

# Top findings to deep-dive
TOP_TESTS = [
    # (test_id, symbol)
    ("R60_M5_001", "XAUUSD"),       # XAUUSD M5 美盘RSI<25 WR=88.07% n=176
    ("R60_M5_001", "XAGUSD"),       # XAGUSD M5 美盘RSI<25 WR=78.54% n=233
    ("R60_M5_001", "JP225"),        # JP225 M5 美盘RSI<25 WR=72.60% n=219
    ("R60_M5_001", "US30"),         # US30 M5 美盘RSI<25 WR=67.91% n=134
    ("R60_M5_001", "US500"),        # US500 M5 美盘RSI<25 WR=63.37% n=172
    ("R60_M5_005", "XAUUSD"),       # XAUUSD M5 亚盘RSI>75做空 WR=73.88% n=134
    ("R60_M5_002", "XAUUSD"),       # XAUUSD M5 亚盘RSI<25 WR=65.48% n=197
    ("R60_M5_002", "XAGUSD"),       # XAGUSD M5 亚盘RSI<25 WR=65.49% n=368
    ("R60_M5_003", "XAUUSD"),       # XAUUSD M5 欧盘RSI<25 WR=65.85% n=284
    ("R60_M5_003", "XAGUSD"),       # XAGUSD M5 欧盘RSI<25 WR=64.65% n=447
    ("R60_M5_003", "US500"),        # US500 M5 欧盘RSI<25 WR=65.90% n=173
    ("R60_M5_006", "XAUUSD"),       # XAUUSD M5 BB下轨 WR=75.00% n=152
    ("R60_M5_006", "XAGUSD"),       # XAGUSD M5 BB下轨 WR=70.83% n=264
    ("R60_M5_008", "XAUUSD"),       # XAUUSD M5 连跌3 WR=69.73% n=185
    ("R60_M5_008", "XAGUSD"),       # XAGUSD M5 连跌3 WR=69.12% n=272
    ("R60_M1_001", "XAUUSD"),       # XAUUSD M1 RSI<20 WR=73.24% n=71
    ("R60_M1_001", "JP225"),        # JP225 M1 RSI<20 WR=69.52% n=105
    ("R60_M1_001", "XAGUSD"),       # XAGUSD M1 RSI<20 WR=67.15% n=137
    ("R60_M1_003", "JP225"),        # JP225 M1 亚盘RSI<20 WR=100% n=33
    ("R60_BONUS_M5_XAU_002", "XAUUSD"),  # 连跌4 WR=93.62% n=47
    ("R60_BONUS_M5_XAU_001", "XAUUSD"),  # RSI<20+BB WR=91.30% n=23
    ("R60_BONUS_M5_US500_001", "US500"), # 欧盘RSI<20 WR=75.00% n=72
    ("R60_BONUS_M5_US30_001", "US30"),   # 美盘RSI<20 WR=66.10% n=59
]

def print_holds_table(test_id, sym):
    holds = data.get(test_id, {}).get(sym, {})
    if not holds:
        return
    print(f"\n### {test_id} | {sym}")
    print(f"| Hold | n | avg_ret | WR | Sharpe | MaxDD |")
    print(f"|:----:|:-:|:-------:|:--:|:------:|:-----:|")
    for hp in sorted(holds.keys(), key=int):
        r = holds[hp]
        n = r.get('signal_count', 0)
        if n == 0:
            print(f"| {hp:>2} | 0 | -- | -- | -- | -- |")
            continue
        wr = r.get('win_rate') or 0
        avg = r.get('avg_return') or 0
        sh = r.get('sharpe_ratio') or 0
        dd = r.get('max_drawdown') or 0
        best = "**" if wr >= 0.60 else ""
        best2 = "**" if wr >= 0.60 else ""
        marker = " ⭐" if wr >= 0.75 and n >= 30 else (" 💪" if wr >= 0.65 and n >= 100 else "")
        print(f"| {best}{hp:>2}{best2} | {n:>4} | {avg:>+8.4f} | {wr:>6.2%} | {sh:>6.2f} | {dd:>7.4f} |{marker}")

print("=" * 80)
print("  ROUND 60 DEEP ANALYSIS — FULL HOLD PERIOD TABLES")
print("=" * 80)

for test_id, sym in TOP_TESTS:
    print_holds_table(test_id, sym)
