#!/usr/bin/env python3
"""Round 9 Analyst — Test init_004: Session direction bias (H1)"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/scripts')
from grid_engine import run_grid
from pprint import pprint

# NOTE: files are named without "m" suffix, e.g. "EURUSD.parquet"
ALL_SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
               "USDCHF", "USOIL", "UKOIL", "USTEC", "US30", "US500", "JP225", "HK50"]
FX_SYMBOLS  = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]
HOLD_PERIODS = [1, 3, 5, 10]

def run_and_print(name, config):
    print(f"\n{'='*80}")
    print(f"  TEST: {name}")
    print(f"  entry: {config['entry_condition']}  dir: {config['direction']}")
    print(f"  symbols: {len(config.get('symbols',[]))} total")
    print(f"{'='*80}")
    try:
        results = run_grid(config)
    except Exception as e:
        print(f"  ERROR: {e}")
        return {}, config

    meta = results.pop("_meta", {})
    print(f"  Symbols with signals: {meta.get('symbols_with_signals', 0)} / {meta.get('total_symbols', 0)}")
    
    findings = []
    for sym in sorted(results.keys()):
        sym_res = results[sym]
        if not sym_res:
            continue
        for hp in sorted(sym_res.keys(), key=int):
            s = sym_res[hp]
            cnt = s.get("signal_count", 0)
            if cnt == 0:
                continue
            wr = s.get("win_rate", 0) or 0
            avg = s.get("avg_return", 0) or 0
            sharpe = s.get("sharpe_ratio", 0) or 0
            dd = s.get("max_drawdown", 0) or 0
            flag = ""
            if cnt >= 30:
                if wr > 0.60:
                    flag = " *** STRONG"
                elif wr > 0.55:
                    flag = " ** PROMISING"
                elif wr < 0.45:
                    flag = " ** REVERSE IDEA"
            print(f"  {sym:<12} hold={hp:>2}  n={cnt:>5}  wr={wr:>6.2%}  avg={avg:>+7.4f}  sharpe={sharpe:>6.2f}  dd={dd:>7.4f}{flag}")
            
            if cnt >= 30 and wr > 0.55:
                findings.append({
                    "symbol": sym,
                    "hold": hp,
                    "win_rate": wr,
                    "avg_return": avg,
                    "sharpe_ratio": sharpe,
                    "signal_count": cnt,
                    "max_drawdown": dd,
                })
    
    return findings, config


all_findings = {}

# ===== Series A - Pure Session Direction Tests =====
print(f"\n{'='*80}")
print(f"  SERIES A: PURE SESSION DIRECTION TESTS")
print(f"{'='*80}")

# Test 1: Asia session long
f1, c1 = run_and_print("A1: Asia session long", {
    "timeframe": "H1",
    "symbols": ALL_SYMBOLS,
    "entry_condition": "session == 'asia'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["A1_asia_long"] = {"findings": f1, "config": c1}

# Test 2: Europe session long
f2, c2 = run_and_print("A2: Europe session long", {
    "timeframe": "H1",
    "symbols": ALL_SYMBOLS,
    "entry_condition": "session == 'europe'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["A2_europe_long"] = {"findings": f2, "config": c2}

# Test 3: US session long
f3, c3 = run_and_print("A3: US session long", {
    "timeframe": "H1",
    "symbols": ALL_SYMBOLS,
    "entry_condition": "session == 'us'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["A3_us_long"] = {"findings": f3, "config": c3}

# Test 4: EURUSD Europe session short (bearish bias -1.39%)
f4, c4 = run_and_print("A4: EURUSD Europe short (bearish bias)", {
    "timeframe": "H1",
    "symbols": ["EURUSD"],
    "entry_condition": "session == 'europe'",
    "direction": "short",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["A4_eurusd_europe_short"] = {"findings": f4, "config": c4}

# Test 5: hour == 8 (London open / Europe session start)
f5, c5 = run_and_print("A5: hour==8 London open long", {
    "timeframe": "H1",
    "symbols": ALL_SYMBOLS,
    "entry_condition": "hour == 8",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["A5_hour8_long"] = {"findings": f5, "config": c5}

# Test 6: hour == 13 (US pre-open / late Europe)
f6, c6 = run_and_print("A6: hour==13 US pre-open long", {
    "timeframe": "H1",
    "symbols": ALL_SYMBOLS,
    "entry_condition": "hour == 13",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["A6_hour13_long"] = {"findings": f6, "config": c6}

# ===== Series B - Strongest Deviation Tests =====
print(f"\n{'='*80}")
print(f"  SERIES B: STRONGEST DEVIATION TESTS")
print(f"{'='*80}")

# Test 7: HK50 US session long (+2.63% bias - strongest overall)
f7, c7 = run_and_print("B7: HK50 US session long (+2.63%)", {
    "timeframe": "H1",
    "symbols": ["HK50"],
    "entry_condition": "session == 'us'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B7_hk50_us_long"] = {"findings": f7, "config": c7}

# Test 8: USDJPY US session long (+2.40% bias)
f8, c8 = run_and_print("B8: USDJPY US session long (+2.40%)", {
    "timeframe": "H1",
    "symbols": ["USDJPY"],
    "entry_condition": "session == 'us'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B8_usdjpy_us_long"] = {"findings": f8, "config": c8}

# Test 9: US500 Europe session long (+2.42% bias)
f9, c9 = run_and_print("B9: US500 Europe session long (+2.42%)", {
    "timeframe": "H1",
    "symbols": ["US500"],
    "entry_condition": "session == 'europe'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B9_us500_europe_long"] = {"findings": f9, "config": c9}

# ===== Bonus: Check if reverse direction works for underperforming sessions =====
print(f"\n{'='*80}")
print(f"  BONUS: REVERSE DIRECTION CHECKS")
print(f"{'='*80}")

# Check EURUSD Europe long (should underperform if bearish bias is real)
f10, c10 = run_and_print("B10: EURUSD Europe long (baseline - expect weak)", {
    "timeframe": "H1",
    "symbols": ["EURUSD"],
    "entry_condition": "session == 'europe'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B10_eurusd_europe_long"] = {"findings": f10, "config": c10}

# Check USDJPY Asia long (has +1.87% bias in Asia)
f11, c11 = run_and_print("B11: USDJPY Asia long (+1.87%)", {
    "timeframe": "H1",
    "symbols": ["USDJPY"],
    "entry_condition": "session == 'asia'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B11_usdjpy_asia_long"] = {"findings": f11, "config": c11}

# Check US500 US session (has +2.01% bias in US)
f12, c12 = run_and_print("B12: US500 US session long (+2.01%)", {
    "timeframe": "H1",
    "symbols": ["US500"],
    "entry_condition": "session == 'us'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B12_us500_us_long"] = {"findings": f12, "config": c12}

# Check USTEC Asia session (+2.10% bias)
f13, c13 = run_and_print("B13: USTEC Asia session long (+2.10%)", {
    "timeframe": "H1",
    "symbols": ["USTEC"],
    "entry_condition": "session == 'asia'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B13_ustec_asia_long"] = {"findings": f13, "config": c13}

# Check XAGUSD US session (+1.87% bias)
f14, c14 = run_and_print("B14: XAGUSD US session long (+1.87%)", {
    "timeframe": "H1",
    "symbols": ["XAGUSD"],
    "entry_condition": "session == 'us'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B14_xagusd_us_long"] = {"findings": f14, "config": c14}

# Check XAUUSD US session (+1.76% bias)
f15, c15 = run_and_print("B15: XAUUSD US session long (+1.76%)", {
    "timeframe": "H1",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'us'",
    "direction": "long",
    "hold_periods": HOLD_PERIODS,
    "exit_at_close": True,
})
all_findings["B15_xauusd_us_long"] = {"findings": f15, "config": c15}

# ===== SUMMARY =====
print(f"\n{'='*80}")
print(f"  SUMMARY OF FINDINGS ABOVE 55% THRESHOLD")
print(f"{'='*80}")
promising_count = 0
strong_count = 0
for group_name, group_data in sorted(all_findings.items()):
    if group_data["findings"]:
        for f in group_data["findings"]:
            wr = f['win_rate']
            label = "STRONG" if wr > 0.60 else "PROMISING"
            if wr > 0.60:
                strong_count += 1
            else:
                promising_count += 1
            print(f"  [{label:>10}] {group_name:<25} {f['symbol']:<10} hold={f['hold']:>2}  wr={wr:>6.2%}  n={f['signal_count']:>5}  sharpe={f['sharpe_ratio']:>6.2f}  avg={f['avg_return']:>+7.4f}")

print(f"\n  Total: {promising_count} promising, {strong_count} strong findings")
print(f"  (threshold: >55% = promising, >60% = strong, need >=30 signals)")
