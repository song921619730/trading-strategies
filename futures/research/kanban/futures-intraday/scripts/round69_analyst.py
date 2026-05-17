#!/usr/bin/env python3
"""
Round 69 Analyst — H1/M30 European & Asian Session Pattern Analysis
Loads researcher results, computes deep-dive analytics, and saves JSON.
"""

import json
import sys
from collections import defaultdict, Counter
from datetime import datetime

RESULTS_PATH = "logs/round69_researcher_results.json"
OUTPUT_PATH = "logs/round69_analyst_results.json"

def load_results(path):
    print(f"Loading {path}...")
    with open(path, "r") as f:
        data = json.load(f)
    all_results = data["all_results"]
    print(f"Loaded {len(all_results)} condition results")
    return all_results, data

def analyze_european_session(results, top_n=20):
    """European Session Deep Dive"""
    print("\n=== EUROPEAN SESSION DEEP DIVE ===")
    eu_results = [r for r in results if r["session"] == "europe"]
    print(f"European session conditions: {len(eu_results)}")
    
    # Sort by win_rate descending, then by signal_count descending
    eu_sorted = sorted(eu_results, key=lambda r: (-r["win_rate"], -r.get("signal_count", 0)))
    
    top_eu = eu_sorted[:top_n]
    print(f"Top {top_n} European patterns:")
    for r in top_eu:
        print(f"  {r['symbol']:8s} {r['timeframe']:4s} {r['condition_type']:20s} "
              f"WR={r['win_rate']:.1%}  cnt={r['signal_count']:3d}  "
              f"ret={r['avg_return']:.3f}  hold={r['hold_period']:3d}  {r['direction']:6s}")
    
    # Find WR >= 80% EU patterns
    wr80_eu = [r for r in eu_results if r["win_rate"] >= 0.80]
    print(f"\nEU patterns with WR >= 80%: {len(wr80_eu)}")
    
    # Best per symbol
    best_per_symbol = {}
    for r in eu_results:
        sym = r["symbol"]
        if sym not in best_per_symbol or r["win_rate"] > best_per_symbol[sym]["win_rate"]:
            best_per_symbol[sym] = r
    
    print("Best EU pattern per symbol:")
    for sym, r in sorted(best_per_symbol.items()):
        print(f"  {sym:8s} WR={r['win_rate']:.1%}  {r['condition_type']:20s}  tf={r['timeframe']:4s}  hold={r['hold_period']:3d}")
    
    return top_eu, wr80_eu, best_per_symbol

def analyze_asian_session(results, top_n=20):
    """Asian Session Deep Dive"""
    print("\n=== ASIAN SESSION DEEP DIVE ===")
    asia_results = [r for r in results if r["session"] == "asia"]
    print(f"Asian session conditions: {len(asia_results)}")
    
    asia_sorted = sorted(asia_results, key=lambda r: (-r["win_rate"], -r.get("signal_count", 0)))
    
    top_asia = asia_sorted[:top_n]
    print(f"Top {top_n} Asian patterns:")
    for r in top_asia:
        print(f"  {r['symbol']:8s} {r['timeframe']:4s} {r['condition_type']:20s} "
              f"WR={r['win_rate']:.1%}  cnt={r['signal_count']:3d}  "
              f"ret={r['avg_return']:.3f}  hold={r['hold_period']:3d}  {r['direction']:6s}")
    
    # Find WR >= 80% ASIA patterns
    wr80_asia = [r for r in asia_results if r["win_rate"] >= 0.80]
    print(f"\nASIA patterns with WR >= 80%: {len(wr80_asia)}")
    
    # Compare with known previous finding (XAGUSD asia WR=96.2%)
    xagusd_asia = [r for r in asia_results if r["symbol"] == "XAGUSD"]
    if xagusd_asia:
        best_xag = max(xagusd_asia, key=lambda r: r["win_rate"])
        print(f"\nXAGUSD Asia best: WR={best_xag['win_rate']:.1%}  "
              f"{best_xag['condition_type']}  hold={best_xag['hold_period']}  "
              f"tf={best_xag['timeframe']}")
    
    return top_asia, wr80_asia

def analyze_us_session(results, top_n=20):
    """US Session Summary"""
    print("\n=== US SESSION SUMMARY ===")
    us_results = [r for r in results if r["session"] == "us"]
    print(f"US session conditions: {len(us_results)}")
    us_sorted = sorted(us_results, key=lambda r: (-r["win_rate"], -r.get("signal_count", 0)))
    top_us = us_sorted[:top_n]
    print(f"Top {top_n} US patterns:")
    for r in top_us:
        print(f"  {r['symbol']:8s} {r['timeframe']:4s} {r['condition_type']:20s} "
              f"WR={r['win_rate']:.1%}  cnt={r['signal_count']:3d}  "
              f"hold={r['hold_period']:3d}  {r['direction']:6s}")
    return top_us

def analyze_cross_timeframe(results):
    """Cross-Timeframe Analysis: Symbols where both H1 and M30 have WR>=80% for same/similar condition"""
    print("\n=== CROSS-TIMEFRAME ANALYSIS ===")
    
    # Group by (symbol, session, condition_type, direction) 
    # Find pairs where both H1 and M30 have WR >= 80%
    groups = defaultdict(list)
    for r in results:
        key = (r["symbol"], r["session"], r["condition_type"], r["direction"])
        groups[key].append(r)
    
    cross_tf = []
    for key, items in groups.items():
        symbol, session, ctype, direction = key
        h1_items = [i for i in items if i["timeframe"] == "H1"]
        m30_items = [i for i in items if i["timeframe"] == "M30"]
        
        for h1 in h1_items:
            for m30 in m30_items:
                if h1["win_rate"] >= 0.80 and m30["win_rate"] >= 0.80:
                    cross_tf.append({
                        "symbol": symbol,
                        "session": session,
                        "condition_type": ctype,
                        "direction": direction,
                        "h1": {
                            "hold_period": h1["hold_period"],
                            "win_rate": h1["win_rate"],
                            "signal_count": h1["signal_count"],
                            "avg_return": h1["avg_return"],
                            "sharpe_ratio": h1["sharpe_ratio"]
                        },
                        "m30": {
                            "hold_period": m30["hold_period"],
                            "win_rate": m30["win_rate"],
                            "signal_count": m30["signal_count"],
                            "avg_return": m30["avg_return"],
                            "sharpe_ratio": m30["sharpe_ratio"]
                        }
                    })
    
    # Deduplicate: keep best pair per group
    deduped = {}
    for item in cross_tf:
        key = (item["symbol"], item["session"], item["condition_type"], item["direction"])
        avg_wr = (item["h1"]["win_rate"] + item["m30"]["win_rate"]) / 2
        if key not in deduped or avg_wr > (deduped[key]["h1"]["win_rate"] + deduped[key]["m30"]["win_rate"]) / 2:
            deduped[key] = item
    
    cross_tf_unique = list(deduped.values())
    print(f"Cross-timeframe winners (H1+M30 both WR>=80%): {len(cross_tf_unique)}")
    for item in sorted(cross_tf_unique, key=lambda x: -x["h1"]["win_rate"]):
        print(f"  {item['symbol']:8s} sess={item['session']:6s} {item['condition_type']:20s} {item['direction']:6s} "
              f"H1: WR={item['h1']['win_rate']:.1%} cnt={item['h1']['signal_count']:3d} "
              f"M30: WR={item['m30']['win_rate']:.1%} cnt={item['m30']['signal_count']:3d}")
    
    return cross_tf_unique

def analyze_cb_vs_pure(results):
    """CB+RSI Combo Effectiveness: Compare pure RSI vs CB+RSI combo conditions"""
    print("\n=== CB+RSI COMBO EFFECTIVENESS ===")
    
    # Pure RSI (long): pure_rsi_oversold
    pure_rsi_long = [r for r in results if r["condition_type"] == "pure_rsi_oversold"]
    # Pure RSI (short): we don't have pure_rsi_overbought in this data based on Counter
    
    # CB+RSI Combo (long): cb_rsi_combo
    cb_rsi_long = [r for r in results if r["condition_type"] == "cb_rsi_combo"]
    # CB+RSI Combo (short): short_cb_rsi
    cb_rsi_short = [r for r in results if r["condition_type"] == "short_cb_rsi"]
    
    # Pure CB (long): pure_cb
    pure_cb = [r for r in results if r["condition_type"] == "pure_cb"]
    
    print(f"Pure RSI (long): {len(pure_rsi_long)} conditions")
    print(f"CB+RSI Combo (long): {len(cb_rsi_long)} conditions")
    print(f"CB+RSI Combo (short): {len(cb_rsi_short)} conditions")
    print(f"Pure CB: {len(pure_cb)} conditions")
    
    def avg_stats(cond_list):
        if not cond_list:
            return {"avg_wr": 0, "avg_ret": 0, "avg_sharpe": 0, "total_signals": 0, "count": 0}
        return {
            "avg_wr": sum(c["win_rate"] for c in cond_list) / len(cond_list),
            "avg_ret": sum(c["avg_return"] for c in cond_list) / len(cond_list),
            "avg_sharpe": sum(c["sharpe_ratio"] for c in cond_list) / len(cond_list),
            "total_signals": sum(c["signal_count"] for c in cond_list),
            "count": len(cond_list)
        }
    
    stats = {
        "pure_rsi_long": avg_stats(pure_rsi_long),
        "cb_rsi_long": avg_stats(cb_rsi_long),
        "cb_rsi_short": avg_stats(cb_rsi_short),
        "pure_cb_long": avg_stats(pure_cb),
    }
    
    print("\nAverage stats comparison:")
    for name, s in stats.items():
        print(f"  {name:20s} avg_WR={s['avg_wr']:.1%}  avg_ret={s['avg_ret']:.3f}  "
              f"avg_sharpe={s['avg_sharpe']:.3f}  signals={s['total_signals']}")
    
    # Compare best of each type
    def best_conditions(cond_list, top_n=10):
        sorted_list = sorted(cond_list, key=lambda r: (-r["win_rate"], -r["signal_count"]))
        return sorted_list[:top_n]
    
    best_pure_rsi = best_conditions(pure_rsi_long)
    best_cb_rsi = best_conditions(cb_rsi_long)
    best_short_cb_rsi = best_conditions(cb_rsi_short)
    best_pure_cb_list = best_conditions(pure_cb)
    
    print("\nTop 5 Pure RSI (long):")
    for r in best_pure_rsi[:5]:
        print(f"  {r['symbol']:8s} {r['timeframe']:4s} {r['session']:6s} WR={r['win_rate']:.1%} cnt={r['signal_count']:3d}")
    
    print("\nTop 5 CB+RSI Combo (long):")
    for r in best_cb_rsi[:5]:
        print(f"  {r['symbol']:8s} {r['timeframe']:4s} {r['session']:6s} WR={r['win_rate']:.1%} cnt={r['signal_count']:3d} hold={r['hold_period']:3d}")
    
    print("\nTop 5 Short CB+RSI Combo:")
    for r in best_short_cb_rsi[:5]:
        print(f"  {r['symbol']:8s} {r['timeframe']:4s} {r['session']:6s} WR={r['win_rate']:.1%} cnt={r['signal_count']:3d} hold={r['hold_period']:3d}")
    
    print("\nTop 5 Pure CB:")
    for r in best_pure_cb_list[:5]:
        print(f"  {r['symbol']:8s} {r['timeframe']:4s} {r['session']:6s} WR={r['win_rate']:.1%} cnt={r['signal_count']:3d} hold={r['hold_period']:3d}")
    
    # Compare CB+RSI vs pure RSI for same (symbol, timeframe, session, hold_period, direction) where possible
    print("\nDirect comparison (CB+RSI vs Pure RSI for matching conditions):")
    
    # Build lookup for pure_rsi
    pure_lookup = {}
    for r in pure_rsi_long:
        key = (r["symbol"], r["timeframe"], r["session"], r["hold_period"], r["direction"],
               r["rsi_column"], r["rsi_threshold"])
        pure_lookup[key] = r
    
    comparisons = []
    for r in cb_rsi_long:
        key = (r["symbol"], r["timeframe"], r["session"], r["hold_period"], r["direction"],
               r["rsi_column"], r["rsi_threshold"])
        if key in pure_lookup:
            pure = pure_lookup[key]
            comparisons.append({
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "session": r["session"],
                "hold_period": r["hold_period"],
                "direction": r["direction"],
                "rsi_column": r["rsi_column"],
                "rsi_threshold": r["rsi_threshold"],
                "pure_rsi_wr": pure["win_rate"],
                "cb_rsi_wr": r["win_rate"],
                "wr_diff": r["win_rate"] - pure["win_rate"],
                "pure_rsi_count": pure["signal_count"],
                "cb_rsi_count": r["signal_count"],
                "pure_rsi_ret": pure["avg_return"],
                "cb_rsi_ret": r["avg_return"]
            })
    
    print(f"Direct comparisons found: {len(comparisons)}")
    if comparisons:
        avg_diff = sum(c["wr_diff"] for c in comparisons) / len(comparisons)
        print(f"Average WR improvement from adding CB: {avg_diff:.1%}")
        
        improved = [c for c in comparisons if c["wr_diff"] > 0]
        worsened = [c for c in comparisons if c["wr_diff"] < 0]
        same = [c for c in comparisons if c["wr_diff"] == 0]
        print(f"Improved: {len(improved)} / Worsened: {len(worsened)} / Same: {len(same)}")
        
        if improved:
            best_improvement = max(improved, key=lambda c: c["wr_diff"])
            print(f"Best improvement: {best_improvement['symbol']} {best_improvement['timeframe']} "
                  f"{best_improvement['session']} diff={best_improvement['wr_diff']:.1%}")
    
    return stats, comparisons, best_pure_rsi, best_cb_rsi, best_short_cb_rsi, best_pure_cb_list

def analyze_hold_periods(results):
    """Best Hold Period Analysis"""
    print("\n=== BEST HOLD PERIOD ANALYSIS ===")
    
    # Filter to top conditions only (WR >= 80%)
    top_conditions = [r for r in results if r["win_rate"] >= 0.80]
    print(f"Top conditions (WR>=80%): {len(top_conditions)}")
    
    # Group by hold_period
    hold_groups = defaultdict(list)
    for r in top_conditions:
        hold_groups[r["hold_period"]].append(r)
    
    print("\nHold period distribution for top conditions:")
    for hp in sorted(hold_groups.keys()):
        items = hold_groups[hp]
        avg_wr = sum(i["win_rate"] for i in items) / len(items)
        print(f"  Hold={hp:3d}: count={len(items):3d}  avg_WR={avg_wr:.1%}")
    
    # Categorize hold periods
    short_hp = [r for r in top_conditions if r["hold_period"] <= 5]
    medium_hp = [r for r in top_conditions if 8 <= r["hold_period"] <= 20]
    long_hp = [r for r in top_conditions if r["hold_period"] >= 25]
    
    categories = {
        "short (1-5)": short_hp,
        "medium (8-20)": medium_hp,
        "long (25+)": long_hp
    }
    
    print("\nHold period category analysis for WR>=80% conditions:")
    for cat_name, cat_list in categories.items():
        if cat_list:
            avg_wr = sum(r["win_rate"] for r in cat_list) / len(cat_list)
            avg_ret = sum(r["avg_return"] for r in cat_list) / len(cat_list)
            print(f"  {cat_name:15s}: {len(cat_list):3d} conditions  avg_WR={avg_wr:.1%}  avg_ret={avg_ret:.3f}")
    
    # Best hold period by (symbol, timeframe, condition_type, session)
    best_hold_by_group = {}
    for r in top_conditions:
        key = (r["symbol"], r["timeframe"], r["condition_type"], r["session"], r["direction"])
        if key not in best_hold_by_group or r["win_rate"] > best_hold_by_group[key]["win_rate"]:
            best_hold_by_group[key] = r
    
    # Hold period distribution of best per group
    hp_counter = Counter(best_hold_by_group[key]["hold_period"] for key in best_hold_by_group)
    print(f"\nBest hold period distribution (per group):")
    for hp in sorted(hp_counter.keys()):
        print(f"  Hold={hp:3d}: {hp_counter[hp]:3d} groups")
    
    return hold_groups, categories, best_hold_by_group

def analyze_direction(results):
    """Direction Analysis: Long vs Short"""
    print("\n=== DIRECTION ANALYSIS ===")
    
    long_results = [r for r in results if r["direction"] == "long"]
    short_results = [r for r in results if r["direction"] == "short"]
    
    print(f"Long conditions: {len(long_results)}")
    print(f"Short conditions: {len(short_results)}")
    
    def direction_stats(cond_list):
        if not cond_list:
            return {"avg_wr": 0, "avg_ret": 0, "avg_sharpe": 0, "wr80_count": 0}
        wr80 = sum(1 for r in cond_list if r["win_rate"] >= 0.80)
        return {
            "avg_wr": sum(r["win_rate"] for r in cond_list) / len(cond_list),
            "avg_ret": sum(r["avg_return"] for r in cond_list) / len(cond_list),
            "avg_sharpe": sum(r["sharpe_ratio"] for r in cond_list) / len(cond_list),
            "wr80_count": wr80,
            "count": len(cond_list)
        }
    
    long_stats = direction_stats(long_results)
    short_stats = direction_stats(short_results)
    
    print(f"Long:  avg_WR={long_stats['avg_wr']:.1%}  avg_ret={long_stats['avg_ret']:.3f}  WR>=80: {long_stats['wr80_count']}")
    print(f"Short: avg_WR={short_stats['avg_wr']:.1%}  avg_ret={short_stats['avg_ret']:.3f}  WR>=80: {short_stats['wr80_count']}")
    
    return long_stats, short_stats

def analyze_session_quality(results):
    """Session Quality Ranking"""
    print("\n=== SESSION QUALITY RANKING ===")
    
    sessions_of_interest = ["asia", "europe", "us"]
    
    ranking = {}
    for session in sessions_of_interest:
        sess_results = [r for r in results if r["session"] == session]
        if not sess_results:
            continue
        
        # Filter qualified signals (signal_count >= 10)
        qualified = [r for r in sess_results if r["signal_count"] >= 10]
        
        if qualified:
            avg_wr = sum(r["win_rate"] for r in qualified) / len(qualified)
            avg_ret = sum(r["avg_return"] for r in qualified) / len(qualified)
            avg_sharpe = sum(r["sharpe_ratio"] for r in qualified) / len(qualified)
            wr80_count = sum(1 for r in qualified if r["win_rate"] >= 0.80)
            wr70_count = sum(1 for r in qualified if r["win_rate"] >= 0.70)
        else:
            avg_wr = avg_ret = avg_sharpe = wr80_count = wr70_count = 0
        
        ranking[session] = {
            "total_conditions": len(sess_results),
            "qualified_conditions": len(qualified),
            "avg_win_rate": avg_wr,
            "avg_return": avg_ret,
            "avg_sharpe": avg_sharpe,
            "wr80_count": wr80_count,
            "wr70_count": wr70_count
        }
        print(f"  {session:8s}: total={len(sess_results):5d}  qualified={len(qualified):5d}  "
              f"avg_WR={avg_wr:.1%}  avg_ret={avg_ret:.3f}  WR>=80={wr80_count:3d}  "
              f"WR>=70={wr70_count:3d}")
    
    # Rank by avg WR of qualified signals
    ranked = sorted(ranking.items(), key=lambda x: -x[1]["avg_win_rate"])
    print("\nSession ranking (by avg WR of qualified signals):")
    for i, (session, stats) in enumerate(ranked, 1):
        print(f"  #{i}: {session:8s}  avg_WR={stats['avg_win_rate']:.1%}")
    
    return ranking, ranked

def main():
    start = datetime.now()
    print(f"Round 69 Analyst — started at {start}")
    print("=" * 60)
    
    all_results, full_data = load_results(RESULTS_PATH)
    
    # ---- All analyses ----
    # a. European Session Deep Dive
    top_eu, wr80_eu, best_eu_per_symbol = analyze_european_session(all_results)
    
    # b. Asian Session Deep Dive
    top_asia, wr80_asia = analyze_asian_session(all_results)
    
    # c. US Session Summary
    top_us = analyze_us_session(all_results)
    
    # d. Cross-Timeframe Analysis
    cross_tf_winners = analyze_cross_timeframe(all_results)
    
    # e. CB+RSI Combo Effectiveness
    cb_vs_pure_stats, cb_comparisons, best_pure_rsi, best_cb_rsi, best_short_cb_rsi, best_pure_cb_list = \
        analyze_cb_vs_pure(all_results)
    
    # f. Best Hold Period Analysis
    hold_groups, hold_categories, best_hold_by_group = analyze_hold_periods(all_results)
    
    # g. Direction Analysis
    long_stats, short_stats = analyze_direction(all_results)
    
    # h. Session Quality Ranking
    session_ranking, ranked_sessions = analyze_session_quality(all_results)
    
    # ---- Compile key findings ----
    key_findings = []
    
    # Session ranking
    if ranked_sessions:
        ranking_str = " > ".join(f"{s}({st['avg_win_rate']:.1%})" for s, st in ranked_sessions)
        key_findings.append(f"Session ranking: {ranking_str}")
    
    # Best EU patterns
    if top_eu:
        top_eu_s = f"Top EU pattern: {top_eu[0]['symbol']} {top_eu[0]['condition_type']} WR={top_eu[0]['win_rate']:.1%}"
        key_findings.append(top_eu_s)
        # Count WR>=80 EU
        key_findings.append(f"EU patterns with WR>=80%: {len(wr80_eu)}")
    
    # Best Asia patterns
    if top_asia:
        top_asia_s = f"Top Asia pattern: {top_asia[0]['symbol']} {top_asia[0]['condition_type']} WR={top_asia[0]['win_rate']:.1%}"
        key_findings.append(top_asia_s)
        key_findings.append(f"Asia patterns with WR>=80%: {len(wr80_asia)}")
    
    # Cross-TF
    if cross_tf_winners:
        key_findings.append(f"Cross-TF winners (H1+M30 both WR>=80%): {len(cross_tf_winners)}")
        top_ctf = sorted(cross_tf_winners, key=lambda x: -x['h1']['win_rate'])[:3]
        for ct in top_ctf:
            key_findings.append(f"  {ct['symbol']} {ct['session']} {ct['condition_type']}: H1 WR={ct['h1']['win_rate']:.1%} / M30 WR={ct['m30']['win_rate']:.1%}")
    
    # CB vs Pure
    if cb_comparisons:
        avg_diff = sum(c["wr_diff"] for c in cb_comparisons) / len(cb_comparisons)
        improved = sum(1 for c in cb_comparisons if c["wr_diff"] > 0)
        key_findings.append(f"CB+RSI vs Pure RSI: avg WR improvement={avg_diff:.1%} ({improved}/{len(cb_comparisons)} improved)")
    
    # Direction
    key_findings.append(f"Direction: Long avg_WR={long_stats['avg_wr']:.1%} vs Short avg_WR={short_stats['avg_wr']:.1%}")
    
    # Hold period
    for cat_name, cat_list in hold_categories.items():
        if cat_list:
            avg_wr = sum(r["win_rate"] for r in cat_list) / len(cat_list)
            key_findings.append(f"Hold {cat_name}: {len(cat_list)} conditions, avg_WR={avg_wr:.1%}")
    
    print("\n\n=== KEY FINDINGS ===")
    for f in key_findings:
        print(f"  • {f}")
    
    # ---- Build output JSON ----
    output = {
        "metadata": {
            "round": 69,
            "name": "round69_analyst",
            "description": "H1/M30 European & Asian Session Pattern Analysis — Round 69",
            "generated_at": datetime.now().isoformat(),
            "source": "logs/round69_researcher_results.json",
        },
        "key_findings": key_findings,
        "top_europe_patterns": [
            {
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "condition_type": r["condition_type"],
                "rsi_column": r.get("rsi_column"),
                "rsi_threshold": r.get("rsi_threshold"),
                "hold_period": r["hold_period"],
                "direction": r["direction"],
                "signal_count": r["signal_count"],
                "win_rate": r["win_rate"],
                "avg_return": r["avg_return"],
                "sharpe_ratio": r["sharpe_ratio"]
            }
            for r in top_eu
        ],
        "top_asia_patterns": [
            {
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "condition_type": r["condition_type"],
                "rsi_column": r.get("rsi_column"),
                "rsi_threshold": r.get("rsi_threshold"),
                "hold_period": r["hold_period"],
                "direction": r["direction"],
                "signal_count": r["signal_count"],
                "win_rate": r["win_rate"],
                "avg_return": r["avg_return"],
                "sharpe_ratio": r["sharpe_ratio"]
            }
            for r in top_asia
        ],
        "top_us_patterns": [
            {
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "condition_type": r["condition_type"],
                "hold_period": r["hold_period"],
                "direction": r["direction"],
                "signal_count": r["signal_count"],
                "win_rate": r["win_rate"],
                "avg_return": r["avg_return"],
                "sharpe_ratio": r["sharpe_ratio"]
            }
            for r in top_us
        ],
        "europe_wr80_patterns": [
            {
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "condition_type": r["condition_type"],
                "hold_period": r["hold_period"],
                "direction": r["direction"],
                "signal_count": r["signal_count"],
                "win_rate": r["win_rate"],
                "avg_return": r["avg_return"],
                "sharpe_ratio": r["sharpe_ratio"]
            }
            for r in wr80_eu
        ],
        "asia_wr80_patterns": [
            {
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "condition_type": r["condition_type"],
                "hold_period": r["hold_period"],
                "direction": r["direction"],
                "signal_count": r["signal_count"],
                "win_rate": r["win_rate"],
                "avg_return": r["avg_return"],
                "sharpe_ratio": r["sharpe_ratio"]
            }
            for r in wr80_asia[:50]  # limit size
        ],
        "cross_tf_summary": {
            "total_dual_80_winners": len(cross_tf_winners),
            "winners": sorted(cross_tf_winners, key=lambda x: -x["h1"]["win_rate"])
        },
        "cb_vs_pure_comparison": {
            "pure_rsi_long_avg": cb_vs_pure_stats["pure_rsi_long"],
            "cb_rsi_long_avg": cb_vs_pure_stats["cb_rsi_long"],
            "cb_rsi_short_avg": cb_vs_pure_stats["cb_rsi_short"],
            "pure_cb_long_avg": cb_vs_pure_stats["pure_cb_long"],
            "direct_comparisons": {
                "total_pairs": len(cb_comparisons),
                "avg_wr_improvement": sum(c["wr_diff"] for c in cb_comparisons) / len(cb_comparisons) if cb_comparisons else 0,
                "improved_count": sum(1 for c in cb_comparisons if c["wr_diff"] > 0),
                "worsened_count": sum(1 for c in cb_comparisons if c["wr_diff"] < 0),
                "same_count": sum(1 for c in cb_comparisons if c["wr_diff"] == 0),
                "examples": sorted(cb_comparisons, key=lambda c: -c["wr_diff"])[:10]
            },
            "top_pure_rsi": [
                {"symbol": r["symbol"], "timeframe": r["timeframe"], "session": r["session"],
                 "hold_period": r["hold_period"], "win_rate": r["win_rate"], "signal_count": r["signal_count"]}
                for r in best_pure_rsi[:10]
            ],
            "top_cb_rsi_combo": [
                {"symbol": r["symbol"], "timeframe": r["timeframe"], "session": r["session"],
                 "hold_period": r["hold_period"], "win_rate": r["win_rate"], "signal_count": r["signal_count"]}
                for r in best_cb_rsi[:10]
            ],
            "top_short_cb_rsi": [
                {"symbol": r["symbol"], "timeframe": r["timeframe"], "session": r["session"],
                 "hold_period": r["hold_period"], "win_rate": r["win_rate"], "signal_count": r["signal_count"]}
                for r in best_short_cb_rsi[:10]
            ],
            "top_pure_cb": [
                {"symbol": r["symbol"], "timeframe": r["timeframe"], "session": r["session"],
                 "hold_period": r["hold_period"], "win_rate": r["win_rate"], "signal_count": r["signal_count"]}
                for r in best_pure_cb_list[:10]
            ]
        },
        "session_rankings": session_ranking,
        "direction_analysis": {
            "long": long_stats,
            "short": short_stats
        },
        "hold_period_analysis": {
            "short_1_5": {
                "count": len(hold_categories.get("short (1-5)", [])),
                "avg_wr": sum(r["win_rate"] for r in hold_categories.get("short (1-5)", [])) / len(hold_categories.get("short (1-5)", [])) if hold_categories.get("short (1-5)") else 0,
                "avg_ret": sum(r["avg_return"] for r in hold_categories.get("short (1-5)", [])) / len(hold_categories.get("short (1-5)", [])) if hold_categories.get("short (1-5)") else 0
            },
            "medium_8_20": {
                "count": len(hold_categories.get("medium (8-20)", [])),
                "avg_wr": sum(r["win_rate"] for r in hold_categories.get("medium (8-20)", [])) / len(hold_categories.get("medium (8-20)", [])) if hold_categories.get("medium (8-20)") else 0,
                "avg_ret": sum(r["avg_return"] for r in hold_categories.get("medium (8-20)", [])) / len(hold_categories.get("medium (8-20)", [])) if hold_categories.get("medium (8-20)") else 0
            },
            "long_25_plus": {
                "count": len(hold_categories.get("long (25+)", [])),
                "avg_wr": sum(r["win_rate"] for r in hold_categories.get("long (25+)", [])) / len(hold_categories.get("long (25+)", [])) if hold_categories.get("long (25+)") else 0,
                "avg_ret": sum(r["avg_return"] for r in hold_categories.get("long (25+)", [])) / len(hold_categories.get("long (25+)", [])) if hold_categories.get("long (25+)") else 0
            },
            "best_hold_distribution": dict(sorted(Counter(best_hold_by_group[key]["hold_period"] for key in best_hold_by_group).items()))
        }
    }
    
    # Write output
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n\nAnalysis complete in {elapsed:.1f}s")
    print(f"Results saved to {OUTPUT_PATH}")
    
    return output

if __name__ == "__main__":
    main()
