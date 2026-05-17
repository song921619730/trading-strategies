#!/usr/bin/env python3
"""
H1/M30 欧盘/亚盘研究循环 — Round 3: 精化验证与策略优化

P1: M30 欧盘连阴+超卖精细hold优化 (hold扩展1-48 + 分品种对比)
P1: H1 欧盘超卖信号多品种组合策略 (GBPUSD/EURUSD/XAUUSD/USOIL/JP225)
P2: H1 欧盘超买做空hold优化 (高WR品种做ATR倍数出场分析)
P2: H1 亚盘+欧盘过渡volatility filter (ATR扩张过滤)

数据: 最新重采样至 2026-05-13 13:30 UTC
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
log = logging.getLogger("h1_m30_r3")

BASE = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
STATE_DIR = BASE / "state"
STATE_DIR.mkdir(exist_ok=True)

ROUND = 3


def rich_results(df, sym, cond_entries, label, direction, hold_range, tf, pppy):
    """Evaluate with richer output."""
    mask = df.eval(cond_entries)
    n_signals = int(mask.sum())
    if n_signals < 5:
        return None
    results = run_test(df, mask, label, direction, hold_range, pppy)
    print_results(results, label, n_signals, sym)
    if not results:
        return None
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
    }


def atr_exit_analysis(df, sym, cond_entries, label, direction, tf, pppy, atr_multipliers=[1.0, 1.5, 2.0, 3.0], max_hold=48):
    """
    Analyze ATR-based trailing exit vs fixed hold.
    Entry is same as cond_entries. Exit is when price moves against by atr_mult * ATR.
    """
    mask = df.eval(cond_entries)
    entries = df[mask].copy()
    n_signals = len(entries)
    if n_signals < 5:
        return None

    results = {}
    for mult in atr_multipliers:
        returns = []
        for idx in entries.index:
            pos = df.index.get_loc(idx)
            entry_price = df.loc[idx, 'close']
            entry_atr = df.loc[idx, 'atr14']
            entry_idx = idx

            exit_idx = None
            # Scan forward up to max_hold bars
            for lookahead in range(1, min(max_hold + 1, len(df) - pos)):
                current_bar = df.iloc[pos + lookahead]
                if direction == 'long':
                    # Trail: exit if price drops below entry - atr_mult * ATR
                    stop_loss = entry_price - mult * entry_atr
                    if current_bar['low'] <= stop_loss:
                        # Exit at stop (use stop price for estimate)
                        exit_idx = current_bar.name
                        break
                else:  # short
                    stop_loss = entry_price + mult * entry_atr
                    if current_bar['high'] >= stop_loss:
                        exit_idx = current_bar.name
                        break

            if exit_idx is None:
                # Use final bar of max_hold as exit
                final_pos = min(pos + max_hold, len(df) - 1)
                exit_price = df.iloc[final_pos]['close']
            else:
                exit_pos = df.index.get_loc(exit_idx)
                exit_price = df.loc[exit_idx, 'close']

            if direction == 'long':
                ret = (exit_price - entry_price) / entry_price
            else:
                ret = (entry_price - exit_price) / entry_price
            returns.append(ret)

        if len(returns) < 5:
            continue
        ret_arr = np.array(returns, dtype=float)
        n = len(ret_arr)
        wr = float((ret_arr > 0).mean())
        avg_ret = float(ret_arr.mean())
        std = float(ret_arr.std()) if ret_arr.std() > 0 else 1e-10
        sharpe = (avg_ret / std) * np.sqrt(pppy / max_hold) if max_hold > 0 else 0.0
        results[f"ATR×{mult}"] = {
            "n": n, "win_rate": wr, "avg_return": avg_ret, "sharpe": sharpe,
        }

    return results


print("=" * 70)
print("📈 H1/M30 欧盘/亚盘研究循环 — Round 3 (精化验证与策略优化)")
print(f"   日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"   品种: {len(SYMBOLS_ALL)} symbols")
print(f"   数据: 最新至 2026-05-13 13:30 UTC")
print("=" * 70)

# Load all data
h1_data = load_data("H1", symbols=SYMBOLS_ALL)
m30_data = load_data("M30", symbols=SYMBOLS_ALL)

all_findings = []

# ══════════════════════════════════════════════════════════════════
# R3-M1: M30 欧盘连阴+超卖精细hold优化 (P1)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R3-M1: M30 欧盘连阴+超卖 — hold扩展1-48 精细优化")
print("=" * 70)

r3m1_results = []

# Focus on strong findings from R2: EURUSD, GBPUSD, UKOIL, USOIL, JP225, XAGUSD
focus_m30_symbols = ["EURUSD", "GBPUSD", "UKOIL", "USOIL", "JP225", "XAGUSD", "AUDUSD", "HK50"]

# Extended hold range for fine optimization
extended_hold = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 36, 42, 48]

for sym in sorted(m30_data.keys()):
    if sym not in focus_m30_symbols:
        continue
    df = compute_indicators(m30_data[sym])

    # Best CB+RSI combos from R2
    combos = [
        (3, 25, "CB>=3+RSI<25"),
        (3, 30, "CB>=3+RSI<30"),
        (4, 25, "CB>=4+RSI<25"),
        (4, 30, "CB>=4+RSI<30"),
        (5, 25, "CB>=5+RSI<25"),
        (5, 30, "CB>=5+RSI<30"),
    ]
    for cb, rsi_t, combo_label in combos:
        cond = f"session == 'europe' and consecutive_bear >= {cb} and rsi14 < {rsi_t}"
        label = f"M30欧盘连阴>={cb}+超卖 RSI<{rsi_t}"
        res = rich_results(df, sym, cond, label, direction="long",
                          hold_range=extended_hold, tf="M30",
                          pppy=PERIODS_PER_YEAR["M30"])
        if res and res['best_wr'] >= 0.65 and res['best_n'] >= 15:
            r3m1_results.append(res)

print(f"\n✅ R3-M1 完成: {len(r3m1_results)} 个强信号")
all_findings.extend(r3m1_results)


# ══════════════════════════════════════════════════════════════════
# R3-M2: H1 欧盘超卖信号多品种组合策略 (P1)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R3-M2: H1 欧盘超卖多品种组合 — GBPUSD/EURUSD/XAUUSD/USOIL/JP225")
print("=" * 70)

r3m2_results = []
focus_h1_symbols = ["GBPUSD", "EURUSD", "XAUUSD", "USOIL", "JP225", "AUDUSD", "XAGUSD"]

for sym in sorted(h1_data.keys()):
    if sym not in focus_h1_symbols:
        continue
    df = compute_indicators(h1_data[sym])

    # Multi-threshold RSI scan on H1
    for rsi_t in [22, 25, 28, 30]:
        cond = f"session == 'europe' and rsi14 < {rsi_t}"
        label = f"H1欧盘超卖做多 RSI<{rsi_t}"
        res = rich_results(df, sym, cond, label, direction="long",
                          hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.65 and res['best_n'] >= 15:
            r3m2_results.append(res)

    # Also check RSI<20 extreme (usually very high WR but low n)
    cond = f"session == 'europe' and rsi14 < 20"
    label = "H1欧盘极端超卖做多 RSI<20"
    res = rich_results(df, sym, cond, label, direction="long",
                      hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24], tf="H1",
                      pppy=PERIODS_PER_YEAR["H1"])
    if res and res['best_wr'] >= 0.70 and res['best_n'] >= 10:
        r3m2_results.append(res)

print(f"\n✅ R3-M2 完成: {len(r3m2_results)} 个强信号")
all_findings.extend(r3m2_results)


# ══════════════════════════════════════════════════════════════════
# R3-M3: H1 欧盘超买做空hold优化 + ATR退出分析 (P2)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R3-M3: H1 欧盘超买做空 — ATR倍数退出分析 (P2)")
print("=" * 70)

r3m3_results = []

for sym in sorted(h1_data.keys()):
    if sym not in focus_h1_symbols:
        continue
    df = compute_indicators(h1_data[sym])

    # Focus on high-WR short patterns
    short_combos = [
        (3, 72, "CBull>=3+RSI>72"),
        (3, 75, "CBull>=3+RSI>75"),
        (4, 72, "CBull>=4+RSI>72"),
        (4, 75, "CBull>=4+RSI>75"),
    ]
    for cb, rsi_t, combo_label in short_combos:
        cond = f"session == 'europe' and consecutive_bull >= {cb} and rsi14 > {rsi_t}"
        label = f"H1欧盘做空 {combo_label}"

        # First: fixed hold analysis
        res = rich_results(df, sym, cond, label, direction="short",
                          hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.60 and res['best_n'] >= 10:
            r3m3_results.append(res)

            # Also do ATR exit analysis on best patterns
            atr_res = atr_exit_analysis(df, sym, cond, label + " [ATR退出]",
                                       direction="short", tf="H1",
                                       pppy=PERIODS_PER_YEAR["H1"],
                                       atr_multipliers=[1.0, 1.5, 2.0, 3.0],
                                       max_hold=48)
            if atr_res:
                best_atr = max(atr_res.items(), key=lambda x: x[1]['win_rate'])
                if best_atr[1]['win_rate'] >= 0.55 and best_atr[1]['n'] >= 8:
                    res_copy = res.copy()
                    res_copy['label'] = label + f" [ATR×{best_atr[0].replace('ATR×', '')} WR={best_atr[1]['win_rate']*100:.1f}%]"
                    r3m3_results.append(res_copy)

print(f"\n✅ R3-M3 完成: {len(r3m3_results)} 个有效模式")
all_findings.extend(r3m3_results)


# ══════════════════════════════════════════════════════════════════
# R3-M4: H1 亚盘+欧盘过渡 volatility filter (P2)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R3-M4: H1 亚盘+欧盘过渡 — ATR扩张过滤扫描")
print("=" * 70)

r3m4_results = []

for sym in sorted(h1_data.keys()):
    if sym not in focus_h1_symbols:
        continue
    df = compute_indicators(h1_data[sym])

    # Calculate ATR expansion: compare current ATR to 50-bar median
    df['atr_median50'] = df['atr14'].rolling(50, min_periods=20).median()
    df['atr_expansion'] = (df['atr14'] > df['atr_median50'] * 1.2).astype(int)  # 20% above median

    # Session transition strategy: Asian session range + European open with volatility
    # Compute Asia daily range
    asia_mask = df['session'] == 'asia'
    df['asia_day'] = None
    asia_days = df[asia_mask].index.date
    df.loc[asia_mask, 'asia_day'] = asia_days

    euro_open_mask = (df['session'] == 'europe') & (df['hour'] == 8)
    for idx in df[euro_open_mask].index[:200]:
        current_date = idx.date()
        asia_today = df[(df.index.date == current_date) & (df['session'] == 'asia')]
        if len(asia_today) < 2:
            continue
        asia_high = asia_today['high'].max()
        asia_low = asia_today['low'].min()
        entry_price = df.loc[idx, 'close']

        df.loc[idx, 'asia_high'] = asia_high
        df.loc[idx, 'asia_low'] = asia_low
        df.loc[idx, 'asia_range_pct'] = (asia_high - asia_low) / entry_price * 100
        df.loc[idx, 'asia_breakout_high'] = 1 if entry_price > asia_high else 0
        df.loc[idx, 'asia_breakdown_low'] = 1 if entry_price < asia_low else 0

    # Test: Asia breakout + ATR expansion -> long
    if 'asia_breakout_high' in df.columns and 'atr_expansion' in df.columns:
        cond_breakout_atr = ("session == 'europe' and hour == 8 and asia_breakout_high == 1"
                            " and atr_expansion == 1")
        res = rich_results(df, sym, cond_breakout_atr, "亚盘高突破+ATR扩张做多", direction="long",
                          hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.60 and res['best_n'] >= 8:
            r3m4_results.append(res)

    # Test: Asia breakdown + ATR expansion -> short
    if 'asia_breakdown_low' in df.columns and 'atr_expansion' in df.columns:
        cond_breakdown_atr = ("session == 'europe' and hour == 8 and asia_breakdown_low == 1"
                            " and atr_expansion == 1")
        res = rich_results(df, sym, cond_breakdown_atr, "亚盘低突破+ATR扩张做空", direction="short",
                          hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.60 and res['best_n'] >= 8:
            r3m4_results.append(res)

    # Test: ATR expansion + Europe oversold -> filtered long
    if 'atr_expansion' in df.columns:
        cond_oversold_atr = "session == 'europe' and rsi14 < 25 and atr_expansion == 1"
        res = rich_results(df, sym, cond_oversold_atr, "欧盘超卖+ATR扩张做多", direction="long",
                          hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12], tf="H1",
                          pppy=PERIODS_PER_YEAR["H1"])
        if res and res['best_wr'] >= 0.65 and res['best_n'] >= 8:
            r3m4_results.append(res)

print(f"\n✅ R3-M4 完成: {len(r3m4_results)} 个有效模式")
all_findings.extend(r3m4_results)


# ══════════════════════════════════════════════════════════════════
# SUMMARY & BEST FINDINGS
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🏆 H1/M30 Round 3 — 发现汇总")
print("=" * 70)

# Tiered filtering
strong = [r for r in all_findings if r['best_wr'] >= 0.65 and r['best_n'] >= 15]
promising = [r for r in all_findings if 0.60 <= r['best_wr'] < 0.65 and r['best_n'] >= 15]
weak = [r for r in all_findings if r['best_wr'] >= 0.58 and r['best_n'] >= 10 and r not in strong and r not in promising]

print(f"\n📈 强信号 (WR>=65% n>=15): {len(strong)}")
print(f"📊 有潜力 (60%<=WR<65% n>=15): {len(promising)}")
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

# ──────────────────────────────────────────────────────────────────
# 更新 state 文件
# ──────────────────────────────────────────────────────────────────
state_path = STATE_DIR / "research_state_h1_m30.json"

with open(state_path) as f:
    state = json.load(f)

# Mark pending hypotheses from round3 as completed
hypothesis_verdicts = {
    "h1r3_001": {  # M30 CB hold optimization
        "status": "completed",
        "verdict": "confirmed" if any(r['best_wr'] >= 0.65 and r['best_n'] >= 15 for r in r3m1_results) else "partial",
        "n_findings": len(r3m1_results),
    },
    "h1r3_002": {  # H1 multi-symbol combo
        "status": "completed",
        "verdict": "confirmed" if any(r['best_wr'] >= 0.65 and r['best_n'] >= 15 for r in r3m2_results) else "partial",
        "n_findings": len(r3m2_results),
    },
    "h1r3_003": {  # H1 short hold optimization
        "status": "completed",
        "verdict": "confirmed" if any(r['best_wr'] >= 0.65 and r['best_n'] >= 15 for r in r3m3_results) else "partial",
        "n_findings": len(r3m3_results),
    },
    "h1r3_004": {  # Volatility filter transition
        "status": "completed",
        "verdict": "confirmed" if any(r['best_wr'] >= 0.65 and r['best_n'] >= 15 for r in r3m4_results) else "partial",
        "n_findings": len(r3m4_results),
    },
}

for h in state["hypothesis_queue"]:
    hid = h["id"]
    if hid in hypothesis_verdicts:
        h.update(hypothesis_verdicts[hid])

# Generate new hypotheses for Round 4
new_hypotheses = []

if strong:
    # Build on best findings
    best_sym = strong_sorted[0]['symbol']
    best_label = strong_sorted[0]['label']

    new_hypotheses.append({
        "id": "h1r4_001",
        "description": f"M30 最强信号的跨品种协同验证 — {best_sym} {best_label[:30]}，扩展到关联品种的同步入场",
        "direction": "long",
        "timeframe": "M30",
        "priority": 1,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r4_002",
        "description": "H1 欧盘超卖信号bootstrap稳健性验证 — 对WR>70% n>=20的策略做bootstrap CI和跨周期分割",
        "direction": "long",
        "timeframe": "H1",
        "priority": 1,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r4_003",
        "description": "M30 亚盘/欧盘过渡的窄幅挤压+波动扩张策略 — 结合ATR收缩→扩张的squeeze play",
        "direction": "both",
        "timeframe": "M30",
        "priority": 2,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r4_004",
        "description": "H1/M30 整体胜率衰减监控 — 对best_findings做rolling WR跟踪，检测策略退化",
        "direction": "both",
        "timeframe": "H1/M30",
        "priority": 2,
        "status": "pending"
    })

# Add new findings to best_findings (avoid duplicates)
existing_desc = {bf['description'] for bf in state['best_findings']}
for r in strong:
    desc = f"{r['symbol']} {r['label']}, hold={r['best_hold']}, WR={r['best_wr']*100:.1f}%, n={r['best_n']}"
    if desc not in existing_desc:
        finding = {
            "id": f"h1bf_{len(state['best_findings'])+1:03d}",
            "description": desc,
            "timeframe": "H1" if "H1" in r['label'] else "M30",
            "direction": r['direction'],
            "best_hold": r['best_hold'],
            "win_rate": round(r['best_wr']*100, 1),
            "n": r['best_n'],
            "avg_return_pct": round(r['best_avg_ret']*100, 3),
            "sharpe": round(r['best_sharpe'], 2),
            "source": f"round3_{r['symbol']}"
        }
        state['best_findings'].append(finding)
        existing_desc.add(desc)

# Update round state
state["current_round"] = ROUND
state["round"] = ROUND
state["last_completed_round"] = ROUND

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
**研究重点**: 精化验证 — hold优化、多品种组合、ATR退出、波动过滤
**数据**: M1重采样H1/M30，最新至2026-05-13 13:30 UTC

---

## 研究模块结果

### R3-M1: M30 欧盘连阴+超卖 — hold扩展1-48 精细优化 (P1)
- 聚焦品种: {focus_m30_symbols}
- CB阈值: 3,4,5 | RSI阈值: 25,30
- hold范围: 1-48 (扩展)
- 有效信号: {len(r3m1_results)}
""")
    if r3m1_results:
        f.write(f"| {'品种':<8} | {'模式':<35} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':35}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r3m1_results, key=lambda x: x['best_wr'], reverse=True)[:25]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:33]:<35} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R3-M2: H1 欧盘超卖多品种组合 — 阈值扫描 (P1)
- 聚焦品种: {focus_h1_symbols}
- RSI阈值: 22,25,28,30 + 极端20
- 有效信号: {len(r3m2_results)}
""")
    if r3m2_results:
        f.write(f"| {'品种':<8} | {'模式':<35} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':35}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r3m2_results, key=lambda x: x['best_wr'], reverse=True)[:25]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:33]:<35} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R3-M3: H1 欧盘超买做空 — 固定hold + ATR退出分析 (P2)
- 测试: CBull>=3/4 + RSI>72/75
- ATR倍数: 1.0×, 1.5×, 2.0×, 3.0×
- 有效信号: {len(r3m3_results)}
""")
    if r3m3_results:
        f.write(f"| {'品种':<8} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r3m3_results, key=lambda x: x['best_wr'], reverse=True)[:30]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:38]:<40} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R3-M4: H1 亚盘+欧盘过渡 — ATR扩张过滤 (P2)
- 条件: 亚盘突破/超卖 + ATR扩张(>中位数1.2×)
- 有效信号: {len(r3m4_results)}
""")
    if r3m4_results:
        f.write(f"| {'品种':<8} | {'模式':<35} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':35}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r3m4_results, key=lambda x: x['best_wr'], reverse=True)[:20]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:33]:<35} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    # Best findings
    f.write("## 最佳发现 (WR>=65% n>=15)\n\n")
    f.write("| # | 品种 | 模式 | 方向 | WR | n | Hold | Sharpe |\n")
    f.write("|:-:|:----|:----|:---:|:--:|:-:|:----:|:------:|\n")
    if strong:
        for i, r in enumerate(sorted(strong, key=lambda x: x['best_wr'], reverse=True)):
            f.write(f"| {i+1} | {r['symbol']} | {r['label'][:38]} | {r['direction']} | {r['best_wr']*100:.1f}% | {r['best_n']} | {r['best_hold']} | {r['best_sharpe']:.2f} |\n")
    else:
        f.write("| — | — | 本轮未发现WR>=65% n>=15的强信号 | — | — | — | — | — |\n")
    f.write("\n")

    # Promising
    f.write("## 有潜力信号 (60%<=WR<65% n>=15)\n\n")
    f.write("| # | 品种 | 模式 | 方向 | WR | n | Hold | Sharpe |\n")
    f.write("|:-:|:----|:----|:---:|:--:|:-:|:----:|:------:|\n")
    if promising:
        for i, r in enumerate(sorted(promising, key=lambda x: x['best_wr'], reverse=True)):
            f.write(f"| {i+1} | {r['symbol']} | {r['label'][:38]} | {r['direction']} | {r['best_wr']*100:.1f}% | {r['best_n']} | {r['best_hold']} | {r['best_sharpe']:.2f} |\n")
    else:
        f.write("| — | — | 无 | — | — | — | — | — |\n")
    f.write("\n")

    # Hypothesis verdicts
    f.write("## 假设验证结果\n\n")
    f.write("| 假设ID | 描述 | 结果 | 发现数 |\n")
    f.write("|:-------|:----|:----:|:------:|\n")
    for h in state["hypothesis_queue"]:
        if h.get("status") in ["completed"] and h.get("verdict"):
            verdict_symbol = "✅" if h.get("verdict") == "confirmed" else "⚠️" if h.get("verdict") == "partial" else "❌"
            f.write(f"| {h['id']} | {h['description'][:50]} | {verdict_symbol} {h['verdict']} | {h.get('n_findings', '—')} |\n")
    f.write("\n")

    # Next round hypotheses
    f.write("## 下一轮假设\n\n")
    for h in new_hypotheses:
        f.write(f"- **P{h['priority']}** [{h['timeframe']}] {h['description']}\n")
    f.write("\n")

    # Market summary section
    f.write("## 最新行情快照\n\n")
    f.write(f"数据更新至: 2026-05-13 13:30 UTC\n\n")
    f.write("| 品种 | H1收盘 | H1 RSI | H1 ATR% | M30 RSI | 信号摘要 |\n")
    f.write("|:----|:------:|:------:|:-------:|:-------:|:--------|\n")
    for sym in sorted(h1_data.keys()):
        h1_df = compute_indicators(h1_data[sym])
        m30_sym = m30_data.get(sym)
        m30_df = compute_indicators(m30_sym) if m30_sym is not None else None

        h1_close = h1_df['close'].iloc[-1] if len(h1_df) > 0 else 0
        h1_rsi = h1_df['rsi14'].iloc[-1] if 'rsi14' in h1_df.columns and len(h1_df) > 0 else 0
        h1_atr = h1_df['atr14_pct'].iloc[-1] if 'atr14_pct' in h1_df.columns and len(h1_df) > 0 else 0
        m30_rsi = m30_df['rsi14'].iloc[-1] if m30_df is not None and 'rsi14' in m30_df.columns and len(m30_df) > 0 else 0

        # Generate signal summary
        signals = []
        if h1_rsi < 25:
            signals.append("🔴超卖")
        elif h1_rsi > 75:
            signals.append("🟢超买")
        if h1_rsi < 30:
            signals.append("⚪偏低")
        elif h1_rsi > 70:
            signals.append("⚪偏高")
        if len(signals) == 0:
            signals.append("—")

        f.write(f"| {sym} | {h1_close:.4f} | {h1_rsi:.1f} | {h1_atr:.3f}% | {m30_rsi:.1f} | {' '.join(signals)} |\n")

    f.write("\n")
    f.write("---\n")
    f.write(f"*报告由 Candlestick Pattern Researcher 于 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC 生成*\n")

print(f"\n✅ 报告已保存到: {report_path}")
print("✅ H1/M30 研究循环 Round 3 完成")

# Output summary for delivery
if strong:
    best = sorted(strong, key=lambda x: x['best_wr'], reverse=True)[0]
    print(f"\n📣 发现 {len(strong)} 个强信号! 最佳: {best['symbol']} {best['label']} WR={best['best_wr']*100:.1f}% n={best['best_n']}")
    # Top 3
    print(f"🏆 Top 3:")
    for i, r in enumerate(sorted(strong, key=lambda x: x['best_wr'], reverse=True)[:3]):
        print(f"   {i+1}. {r['symbol']} {r['label']} — WR={r['best_wr']*100:.1f}% n={r['best_n']} hold={r['best_hold']} Sharpe={r['best_sharpe']:.2f}")
else:
    print(f"\n📣 本轮未发现强信号 (WR>=65% n>=15), 已有 {len(promising)} 个有潜力信号")
