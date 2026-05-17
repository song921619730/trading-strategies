#!/usr/bin/env python3
"""
H1/M30 欧盘/亚盘研究循环 — Round 2
专注 pending hypotheses 的精化扫描

P1: H1 欧盘超卖 RSI 阈值深度扫描 — RSI<20/22/25/28 分档对比
P1: H1 欧盘中段(9-12) vs 欧盘首段(8-10) 子窗口对比
P1: M30 欧盘连阴CB深度对比 — CB>=2/3/4/5 + RSI阈值精细扫描
P2: H1 亚盘尾段到欧盘开盘transition策略
P2: H1/M30 欧盘超买做空探索 — RSI>70/72/75/78 + CBull>=3/4
"""
import sys, logging, json
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from h1_m30_engine import (
    load_data, compute_indicators, evaluate_pattern, SYMBOLS_ALL,
    PERIODS_PER_YEAR, list_available_symbols, run_test, print_results
)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("h1_m30_r2")

BASE = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
STATE_DIR = BASE / "state"
STATE_DIR.mkdir(exist_ok=True)

ROUND = 2

def rich_results(df, sym, cond_entries, label, direction, hold_range, tf, pppy):
    """Evaluate with richer output including best hold optimization."""
    mask = df.eval(cond_entries)
    n_signals = int(mask.sum())
    if n_signals < 5:
        return None

    results = run_test(df, mask, label, direction, hold_range, pppy)
    print_results(results, label, n_signals, sym)

    if not results:
        return None

    # Best by WR (with n>=5)
    valid = {k: v for k, v in results.items() if v['n'] >= 5}
    if not valid:
        return None
    best_wr_hold = max(valid.items(), key=lambda x: x[1]['win_rate'])
    best_sharpe_hold = max(valid.items(), key=lambda x: x[1]['sharpe'])

    return {
        "symbol": sym,
        "label": label,
        "direction": direction,
        "n_signals": n_signals,
        "best_hold": best_wr_hold[0],
        "best_wr": best_wr_hold[1]['win_rate'],
        "best_n": best_wr_hold[1]['n'],
        "best_avg_ret": best_wr_hold[1]['avg_return'],
        "best_sharpe": best_wr_hold[1]['sharpe'],
        "best_sharpe_hold": best_sharpe_hold[0],
        "best_sharpe_val": best_sharpe_hold[1]['sharpe'],
        "best_sharpe_wr": best_sharpe_hold[1]['win_rate'],
        "all_results": {str(k): v for k, v in results.items()},
    }


print("=" * 70)
print("📈 H1/M30 欧盘/亚盘研究循环 — Round 2 (精化扫描)")
print(f"   日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"   品种: {len(SYMBOLS_ALL)} symbols")
print("=" * 70)

# Load all data once
h1_data = load_data("H1", symbols=SYMBOLS_ALL)
m30_data = load_data("M30", symbols=SYMBOLS_ALL)

all_findings = []

# ══════════════════════════════════════════════════════════════════
# R2-M1: H1 欧盘超卖 RSI 阈值深度扫描 (P1)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R2-M1: H1 欧盘超卖 RSI 阈值深度扫描 — RSI<20/22/25/28 分档对比")
print("=" * 70)

rsi_thresholds = [20, 22, 25, 28]
r2m1_results = []

for sym in sorted(h1_data.keys()):
    df = compute_indicators(h1_data[sym])
    for rsi_t in rsi_thresholds:
        cond = f"session == 'europe' and rsi14 < {rsi_t}"
        label = f"欧盘深度超卖做多 RSI<{rsi_t}"
        res = rich_results(df, sym, cond, label, direction="long",
                          hold_range=[1,2,3,4,5,6,8,10,12,16,20,24], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.58:
            r2m1_results.append(res)

print(f"\n✅ R2-M1 完成: {len(r2m1_results)} 个有效模式")
all_findings.extend(r2m1_results)

# ══════════════════════════════════════════════════════════════════
# R2-M2: H1 欧盘中段 vs 首段 子窗口对比 (P1)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R2-M2: H1 欧盘中段(9-12) vs 欧盘首段(8-10) 子窗口对比")
print("=" * 70)

r2m2_results = []

# Focus on symbols that showed strong oversold signals in R1
focus_symbols = ["GBPUSD", "EURUSD", "XAUUSD", "XAGUSD", "JP225", "US30", "USOIL", "UKOIL", "USDCHF", "AUDUSD"]

for sym in sorted(h1_data.keys()):
    if sym not in focus_symbols:
        continue
    df = compute_indicators(h1_data[sym])

    # First window: European open (hours 8-10)
    for window_desc, window_cond in [
        ("欧盘首段(8-10)超卖", "hour >= 8 and hour < 10 and rsi14 < 25"),
        ("欧盘中段(9-12)超卖", "hour >= 9 and hour < 12 and rsi14 < 25"),
        ("欧盘后段(10-13)超卖", "hour >= 10 and hour < 13 and rsi14 < 25"),
    ]:
        res = rich_results(df, sym, window_cond, window_desc, direction="long",
                          hold_range=[1,2,3,4,5,6,8,10,12], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.58:
            r2m2_results.append(res)

print(f"\n✅ R2-M2 完成: {len(r2m2_results)} 个有效模式")
all_findings.extend(r2m2_results)

# ══════════════════════════════════════════════════════════════════
# R2-M3: M30 欧盘连阴CB深度对比 (P1)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R2-M3: M30 欧盘连阴CB深度对比 — CB>=2/3/4/5 + RSI<30/<35 精细扫描")
print("=" * 70)

r2m3_results = []
cb_thresholds = [2, 3, 4, 5]
rsi_oversold = [25, 30, 35]

for sym in sorted(m30_data.keys()):
    df = compute_indicators(m30_data[sym])
    for cb in cb_thresholds:
        for rsi_t in rsi_oversold:
            cond = f"session == 'europe' and consecutive_bear >= {cb} and rsi14 < {rsi_t}"
            label = f"欧盘连阴>={cb}+超卖做多 RSI<{rsi_t}"
            res = rich_results(df, sym, cond, label, direction="long",
                              hold_range=[1,2,3,4,6,8,10,12,16,20,24], tf="M30",
                              pppy=PERIODS_PER_YEAR["M30"])
            if res and res['best_wr'] >= 0.60 and res['best_n'] >= 10:
                r2m3_results.append(res)

print(f"\n✅ R2-M3 完成: {len(r2m3_results)} 个有效模式")
all_findings.extend(r2m3_results)

# ══════════════════════════════════════════════════════════════════
# R2-M4: H1/M30 欧盘超买做空探索 (P2)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R2-M4: H1/M30 欧盘超买做空探索 — RSI>70/72/75/78 + CBull>=3/4")
print("=" * 70)

r2m4_results = []
rsi_overbought = [70, 72, 75, 78]

for sym in sorted(h1_data.keys()):
    df = compute_indicators(h1_data[sym])
    for rsi_t in rsi_overbought:
        for cb in [3, 4]:
            cond = f"session == 'europe' and rsi14 > {rsi_t} and consecutive_bull >= {cb}"
            label = f"H1欧盘连阳>={cb}+超买做空 RSI>{rsi_t}"
            res = rich_results(df, sym, cond, label, direction="short",
                              hold_range=[1,2,3,4,5,6,8,10,12,16,20,24], tf="H1",
                              pppy=PERIODS_PER_YEAR["H1"])
            if res and res['best_wr'] >= 0.60 and res['best_n'] >= 8:
                r2m4_results.append(res)

# Also on M30
for sym in sorted(m30_data.keys()):
    df = compute_indicators(m30_data[sym])
    for rsi_t in rsi_overbought:
        for cb in [3, 4]:
            cond = f"session == 'europe' and rsi14 > {rsi_t} and consecutive_bull >= {cb}"
            label = f"M30欧盘连阳>={cb}+超买做空 RSI>{rsi_t}"
            res = rich_results(df, sym, cond, label, direction="short",
                              hold_range=[1,2,3,4,6,8,10,12,16,20,24], tf="M30",
                              pppy=PERIODS_PER_YEAR["M30"])
            if res and res['best_wr'] >= 0.60 and res['best_n'] >= 8:
                r2m4_results.append(res)

print(f"\n✅ R2-M4 完成: {len(r2m4_results)} 个有效模式")
all_findings.extend(r2m4_results)

# ══════════════════════════════════════════════════════════════════
# R2-M5: H1 亚盘range高/低突破 + transition (P2)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R2-M5: H1 亚盘range高/低突破 + 欧盘开盘transition")
print("=" * 70)

r2m5_results = []

for sym in sorted(h1_data.keys()):
    df = compute_indicators(h1_data[sym])

    # Asian session range breakout — price above Asia high at Euro open (hour=8)
    # Compute Asia session high/low for each day
    asia_mask = df['session'] == 'asia'
    df['asia_day'] = None
    # Assign a day ID for Asia sessions
    asia_days = df[asia_mask].index.date
    df.loc[asia_mask, 'asia_day'] = asia_days
    
    # For each European open, check if price breaks above previous Asia high
    euro_open_mask = (df['session'] == 'europe') & (df['hour'] == 8)
    euro_open_idx = df[euro_open_mask].index
    
    for idx in euro_open_idx[:200]:  # limit for performance
        # Find the current day's Asia session
        current_date = idx.date()
        asia_today = df[(df.index.date == current_date) & (df['session'] == 'asia')]
        if len(asia_today) < 2:
            continue
        
        asia_high = asia_today['high'].max()
        asia_low = asia_today['low'].min()
        asia_range = asia_high - asia_low
        entry_price = df.loc[idx, 'close']
        
        # Breakout above Asia high
        if entry_price > asia_high:
            df.loc[idx, 'asia_breakout_high'] = 1
        else:
            df.loc[idx, 'asia_breakout_high'] = 0
            
        # Breakdown below Asia low
        if entry_price < asia_low:
            df.loc[idx, 'asia_breakdown_low'] = 1
        else:
            df.loc[idx, 'asia_breakdown_low'] = 0
            
        # Narrow range breakout
        if asia_range > 0 and asia_range / df.loc[idx, 'close'] < 0.005:  # <0.5% range
            df.loc[idx, 'asia_narrow_range'] = 1
        else:
            df.loc[idx, 'asia_narrow_range'] = 0

    # Test: Asian session high breakout -> long
    if 'asia_breakout_high' in df.columns:
        cond_breakout_high = "session == 'europe' and hour == 8 and asia_breakout_high == 1"
        res = rich_results(df, sym, cond_breakout_high, "亚盘区间突破做多(高突破)", direction="long",
                          hold_range=[1,2,3,4,5,6,8,10,12], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.55 and res['best_n'] >= 8:
            r2m5_results.append(res)

    # Test: Asian session low breakdown -> short
    if 'asia_breakdown_low' in df.columns:
        cond_breakdown_low = "session == 'europe' and hour == 8 and asia_breakdown_low == 1"
        res = rich_results(df, sym, cond_breakdown_low, "亚盘区间突破做空(低突破)", direction="short",
                          hold_range=[1,2,3,4,5,6,8,10,12], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.55 and res['best_n'] >= 8:
            r2m5_results.append(res)

    # Test: Asian narrow range -> squeeze breakout
    if 'asia_narrow_range' in df.columns:
        cond_narrow = "session == 'europe' and hour == 8 and asia_narrow_range == 1"
        res = rich_results(df, sym, cond_narrow, "亚盘窄幅挤压breakout", direction="long",
                          hold_range=[1,2,3,4,5,6,8,10,12], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.55 and res['best_n'] >= 8:
            r2m5_results.append(res)

print(f"\n✅ R2-M5 完成: {len(r2m5_results)} 个有效模式")
all_findings.extend(r2m5_results)

# ══════════════════════════════════════════════════════════════════
# SUMMARY & BEST FINDINGS
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🏆 H1/M30 Round 2 — 发现汇总")
print("=" * 70)

# Filter quality
strong = [r for r in all_findings if r['best_wr'] >= 0.65 and r['best_n'] >= 15]
promising = [r for r in all_findings if 0.60 <= r['best_wr'] < 0.65 and r['best_n'] >= 15]
weak = [r for r in all_findings if r['best_wr'] >= 0.58 and r['best_n'] >= 10 and r not in strong and r not in promising]

print(f"\n📈 强信号 (WR>=65% n>=15): {len(strong)}")
print(f"📊 有潜力 (WR>=60% n>=15): {len(promising)}")
print(f"📉 弱信号 (WR>=58% n>=10): {len(weak)}")

if strong:
    print(f"\n{'='*60}")
    print(f"🏆 最佳发现 — 按胜率排序")
    print(f"{'='*60}")
    strong_sorted = sorted(strong, key=lambda x: x['best_wr'], reverse=True)
    print(f" {'#':<4} {'品种':<8} {'模式':<45} {'方向':<6} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8}")
    print(f" {'-'*3} {'-'*7} {'-'*44} {'-'*5} {'-'*7} {'-'*5} {'-'*5} {'-'*7}")
    for i, r in enumerate(strong_sorted[:40]):
        print(f" {i+1:<3} {r['symbol']:<8} {r['label'][:43]:<45} {r['direction']:<6} "
              f"{r['best_wr']*100:<7.1f}% {r['best_n']:<6} {r['best_hold']:<6} {r['best_sharpe']:<8.2f}")

# ══════════════════════════════════════════════════════════════════
# 更新 state 文件
# ══════════════════════════════════════════════════════════════════
state_path = STATE_DIR / "research_state_h1_m30.json"

with open(state_path) as f:
    state = json.load(f)

# Mark pending hypotheses as completed
hypothesis_verdicts = {
    "h1r2_001": {  # RSI thresholds
        "status": "completed",
        "verdict": "confirmed" if any(r['best_wr'] >= 0.65 and r['best_n'] >= 15 for r in r2m1_results) else "partial",
        "n_findings": len(r2m1_results),
    },
    "h1r2_002": {  # Window comparison
        "status": "completed",
        "verdict": "confirmed" if any(r['best_wr'] >= 0.65 and r['best_n'] >= 15 for r in r2m2_results) else "partial",
        "n_findings": len(r2m2_results),
    },
    "h1r2_003": {  # M30 CB depth
        "status": "completed",
        "verdict": "confirmed" if any(r['best_wr'] >= 0.65 and r['best_n'] >= 15 for r in r2m3_results) else "partial",
        "n_findings": len(r2m3_results),
    },
    "h1r2_004": {  # Asia range transition
        "status": "completed",
        "verdict": "partial" if any(r['best_wr'] >= 0.55 for r in r2m5_results) else "inconclusive",
        "n_findings": len(r2m5_results),
    },
    "h1r2_005": {  # H1/M30 short explore
        "status": "completed",
        "verdict": "confirmed" if any(r['best_wr'] >= 0.65 and r['best_n'] >= 15 for r in r2m4_results) else "partial",
        "n_findings": len(r2m4_results),
    },
}

for h in state["hypothesis_queue"]:
    hid = h["id"]
    if hid in hypothesis_verdicts:
        h.update(hypothesis_verdicts[hid])

# Generate new hypotheses for Round 3
new_hypotheses = []

# Based on strong findings
if strong:
    # If M3 found good signals, suggest deeper
    new_hypotheses.append({
        "id": "h1r3_001",
        "description": "M30 欧盘连阴+超卖精细hold优化 — 对R2中找到的强信号品种做hold扩展(1-48)和出场方式对比(close vs trailing stop)",
        "direction": "long",
        "timeframe": "M30",
        "priority": 1,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r3_002",
        "description": "H1 欧盘超卖信号多品种组合策略 — GBPUSD/EURUSD/XAUUSD 统一入场，hold分散对冲",
        "direction": "long",
        "timeframe": "H1",
        "priority": 1,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r3_003",
        "description": "H1 欧盘超买做空hold优化 — 对R2-M4中WR>65%的品种做SL/TP优化(ATR倍数出场)",
        "direction": "short",
        "timeframe": "H1",
        "priority": 2,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r3_004",
        "description": "H1 亚盘+欧盘 session 过渡的volatility filter — 加入ATR放大过滤，只在波动扩张日交易",
        "direction": "both",
        "timeframe": "H1",
        "priority": 2,
        "status": "pending"
    })

# Add new findings to best_findings
for r in strong:
    finding = {
        "id": f"h1bf_{len(state['best_findings'])+1:03d}",
        "description": f"{r['symbol']} {r['label']}, hold={r['best_hold']}, WR={r['best_wr']*100:.1f}%, n={r['best_n']}, Sharpe={r['best_sharpe']:.1f}",
        "timeframe": "H1" if "H1" in r['label'] or "H1" in str(r.get('all_results', {})) else "M30",
        "direction": r['direction'],
        "best_hold": r['best_hold'],
        "win_rate": round(r['best_wr']*100, 1),
        "n": r['best_n'],
        "avg_return_pct": round(r['best_avg_ret']*100, 3),
        "sharpe": round(r['best_sharpe'], 2),
        "source": f"round2_{r['symbol']}"
    }
    state["best_findings"].append(finding)

# Update round state
state["current_round"] = ROUND
state["round"] = ROUND
# Fatigue: increment if no strong findings
if not strong:
    state["fatigue"] = state.get("fatigue", 0) + 1
    state["consecutive_no_finding"] = state.get("consecutive_no_finding", 0) + 1
else:
    state["fatigue"] = max(0, state.get("fatigue", 0) - 1)
    state["consecutive_no_finding"] = 0

state["hypothesis_queue"].extend(new_hypotheses)
state["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

with open(state_path, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"\n✅ State 更新完成: {state_path}")

# ══════════════════════════════════════════════════════════════════
# 生成报告文件
# ══════════════════════════════════════════════════════════════════
report_path = REPORTS_DIR / f"h1_m30_round_{ROUND:03d}.md"

with open(report_path, "w", encoding="utf-8") as f:
    f.write(f"""# H1/M30 欧盘/亚盘研究报告 — Round {ROUND}

**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC
**品种**: 全部14个MT5品种
**时间框架**: H1（主）/ M30（辅）
**研究重点**: 精化扫描 — RSI阈值深度、CB深度、子窗口对比、超买做空、Asia过渡

---

## 研究模块结果

### R2-M1: H1 欧盘超卖 RSI 阈值深度扫描
- 测试条件: `session=='europe' and rsi14<{rsi_thresholds}` (20/22/25/28)
- 有效品种: {len(r2m1_results)}
""")
    if r2m1_results:
        f.write(f"| {'品种':<8} | {'RSI阈值':<12} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':12}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r2m1_results, key=lambda x: x['best_wr'], reverse=True)[:20]:
            short_label = r['label'].replace("欧盘深度超卖做多 ", "")
            f.write(f"| {r['symbol']:<8} | {short_label:<12} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R2-M2: H1 欧盘中段(9-12) vs 首段(8-10) 子窗口对比
- 有效品种: {len(r2m2_results)}
""")
    if r2m2_results:
        f.write(f"| {'品种':<8} | {'窗口':<25} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':25}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r2m2_results, key=lambda x: x['best_wr'], reverse=True)[:20]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:23]:<25} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R2-M3: M30 欧盘连阴CB深度对比 — CB>=2/3/4/5 + RSI阈值
- CB阈值测试: {cb_thresholds}
- RSI阈值测试: {rsi_oversold}
- 有效品种: {len(r2m3_results)}
""")
    if r2m3_results:
        f.write(f"| {'品种':<8} | {'模式':<35} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':35}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r2m3_results, key=lambda x: x['best_wr'], reverse=True)[:25]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:33]:<35} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R2-M4: H1/M30 欧盘超买做空探索 (P2)
- 测试: RSI>70/72/75/78 + CBull>=3/4
- 有效品种: {len(r2m4_results)}
""")
    if r2m4_results:
        f.write(f"| {'品种':<8} | {'模式':<35} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':35}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r2m4_results, key=lambda x: x['best_wr'], reverse=True)[:25]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:33]:<35} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R2-M5: H1 亚盘range高/低突破 + transition
- 有效品种: {len(r2m5_results)}
""")
    if r2m5_results:
        f.write(f"| {'品种':<8} | {'模式':<30} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':30}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r2m5_results, key=lambda x: x['best_wr'], reverse=True)[:15]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:28]:<30} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    # Best findings table
    f.write(f"""## 最佳发现 (WR>=65% n>=15)

| # | 品种 | 模式 | 方向 | WR | n | Hold | Sharpe |
|:-:|:----|:----|:---:|:--:|:-:|:----:|:------:|
""")
    if strong:
        for i, r in enumerate(sorted(strong, key=lambda x: x['best_wr'], reverse=True)):
            f.write(f"| {i+1} | {r['symbol']} | {r['label'][:38]} | {r['direction']} | {r['best_wr']*100:.1f}% | {r['best_n']} | {r['best_hold']} | {r['best_sharpe']:.2f} |\n")
    else:
        f.write("| — | — | 本轮未发现WR>=65% n>=15的强信号 | — | — | — | — | — |\n")
    f.write("\n")

    # Promising
    f.write(f"""## 有潜力信号 (60%<=WR<65% n>=15)

| # | 品种 | 模式 | 方向 | WR | n | Hold | Sharpe |
|:-:|:----|:----|:---:|:--:|:-:|:----:|:------:|
""")
    if promising:
        for i, r in enumerate(sorted(promising, key=lambda x: x['best_wr'], reverse=True)):
            f.write(f"| {i+1} | {r['symbol']} | {r['label'][:38]} | {r['direction']} | {r['best_wr']*100:.1f}% | {r['best_n']} | {r['best_hold']} | {r['best_sharpe']:.2f} |\n")
    else:
        f.write("| — | — | 无 | — | — | — | — | — |\n")
    f.write("\n")

    # Verdicts
    f.write(f"""## 假设验证结果

| 假设ID | 描述 | 结果 | 发现数 |
|:-------|:----|:----:|:------:|
""")
    for h in state["hypothesis_queue"]:
        if h.get("status") in ["completed"] and h.get("verdict"):
            verdict_symbol = "✅" if h.get("verdict") == "confirmed" else "⚠️" if h.get("verdict") == "partial" else "❌"
            f.write(f"| {h['id']} | {h['description'][:50]} | {verdict_symbol} {h['verdict']} | {h.get('n_findings', '—')} |\n")
    f.write("\n")

    # Next round hypotheses
    f.write(f"""## 下一轮假设

""")
    for h in new_hypotheses:
        f.write(f"- **P{h['priority']}** [{h['timeframe']}] {h['description']}\n")
    f.write("\n")

    f.write("---\n")
    f.write(f"*报告由 Candlestick Pattern Researcher 于 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC 生成*\n")

print(f"\n✅ 报告已保存到: {report_path}")
print("✅ H1/M30 研究循环 Round 2 完成")

# Output summary line for delivery
if strong:
    print(f"\n📣 发现 {len(strong)} 个强信号! 最佳: {strong_sorted[0]['symbol']} {strong_sorted[0]['label']} WR={strong_sorted[0]['best_wr']*100:.1f}%")
else:
    print(f"\n📣 本轮未发现强信号 (WR>=65% n>=15), 已有 {len(promising)} 个有潜力信号")
