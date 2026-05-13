#!/usr/bin/env python3
"""Round 9 — All tests using run_grid (baseline) + custom SQL for filters"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from grid_engine import run_grid, ch_query, load_trade_cal, compute_stats


def run_grid_test(label, entry_sql, direction="short", hold_periods=[1,2,3,5], max_signals=10000):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"SQL: {entry_sql[:100]}")
    print('='*60)
    t0 = time.time()
    config = {
        "entry_sql": entry_sql,
        "tables": {"s": "tushare_stock_daily", "d": "tushare_daily_basic"},
        "hold_periods": hold_periods,
        "direction": direction,
        "max_signals": max_signals,
    }
    result = run_grid(config)
    elapsed = time.time() - t0
    print(f"Time: {elapsed:.1f}s")
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        for hp, s in result.items():
            print(f"  {hp}: n={s['signal_count']}, WR={s['win_rate']:.2%}, avg_ret={s['avg_return']:.4f}, CI=[{s['ci_95_lower']:.2%},{s['ci_95_upper']:.2%}]")
    return result


# ====== ROUND 9 TESTS ======
all_results = {}

# ----- TEST 1: gen_009 Replication (baseline) -----
# 放量上涨(量比>3+涨幅>3%) => 做空 — with LIMIT 10000
r1 = run_grid_test(
    "T1: Baseline 量比>3+涨幅>3% => 做空 (n=10000)",
    "s.pct_chg > 3 AND d.volume_ratio > 3",
    direction="short", max_signals=10000
)
all_results["T1_baseline"] = r1

# ----- TEST 2: gen_009 enhanced - only volume_ratio > 3 + pct_chg > 3 (check for consecutive via separate query) -----
# We'll get the full signal set and manually compute consecutive condition
print("\n\n===== TEST 2: 连续2日收阳 (Manual enrichment) =====")
print("Getting base signals with entry prices...")
sql_base = """
SELECT s.ts_code, s.trade_date, s.close AS entry_price, s.pct_chg AS entry_pct
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS d
    ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
WHERE s.pct_chg > 3 AND d.volume_ratio > 3 AND s.close > 0
  AND s.trade_date BETWEEN '2020-01-02' AND '2026-05-11'
  AND s.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
  AND s.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR))
  AND s.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_suspend_d FINAL WHERE trade_date >= DATE_SUB('2026-05-11', INTERVAL 10 DAY))
ORDER BY rand()
LIMIT 3000
"""
signals = ch_query(sql_base)
print(f"Got {len(signals)} base signals")

if signals:
    # Get previous day pct_chg for each signal
    # Build a lookup: for each (ts_code, trade_date) find the previous trading day
    cal = load_trade_cal()
    cal_set = cal["cal_set"] if "cal_set" in cal else set(cal["cal"])
    cal_list = cal["cal"]
    
    enriched = []
    for s in signals:
        # Find previous trading day
        trade_date = s["trade_date"]
        if trade_date in cal_set:
            idx = cal_list.index(trade_date)
            if idx > 0:
                prev_date = cal_list[idx - 1]
                # Query previous day's pct_chg
                prev_rows = ch_query(
                    f"SELECT pct_chg FROM tushare.tushare_stock_daily FINAL "
                    f"WHERE ts_code = '{s['ts_code']}' AND trade_date = '{prev_date}'"
                )
                if prev_rows and prev_rows[0]["pct_chg"] is not None:
                    prev_pct = prev_rows[0]["pct_chg"]
                    s["prev_pct_chg"] = prev_pct
                    if prev_pct > 0:
                        enriched.append(s)
        if len(enriched) >= 1500:
            break
    
    print(f"Signals with consecutive bullish day: {len(enriched)}")
    
    if len(enriched) >= 30:
        # Now compute exit stats for enriched signals
        from grid_engine import load_trade_cal as ltc
        cal_data = ltc()
        cal_list = cal_data["cal"]
        cal_set = cal_data["set"]
        
        date_groups = {}
        for s in enriched:
            date_groups.setdefault(s["trade_date"], []).append((s["ts_code"], s["entry_price"]))
        
        result_009 = {}
        for hp in [1,2,3,5]:
            exit_lookup = {}
            for entry_date, entries in date_groups.items():
                if entry_date in cal_set:
                    idx = cal_list.index(entry_date)
                    target_idx = idx + hp
                    if 0 <= target_idx < len(cal_list):
                        ex_date = cal_list[target_idx]
                        for tc, _ in entries:
                            exit_lookup[(tc, entry_date)] = ex_date
            
            rev_map = {}
            for (tc, en), ex in exit_lookup.items():
                rev_map[(tc, ex)] = en
            
            date_code_groups = {}
            for (tc, en), ex in exit_lookup.items():
                date_code_groups.setdefault(ex, []).append(tc)
            
            exit_price_map = {}
            for ex_date, codes in date_code_groups.items():
                unique = list(set(codes))
                for i in range(0, len(unique), 2000):
                    batch = unique[i:i+2000]
                    cs = ", ".join(f"'{c}'" for c in batch)
                    resp = ch_query(
                        f"SELECT ts_code, close FROM tushare.tushare_stock_daily FINAL "
                        f"WHERE trade_date = '{ex_date}' AND ts_code IN ({cs})"
                    )
                    for r in resp:
                        en = rev_map.get((r["ts_code"], ex_date))
                        if en:
                            exit_price_map[(r["ts_code"], en)] = r["close"]
            
            returns = []
            for s in enriched:
                key = (s["ts_code"], s["trade_date"])
                if s["entry_price"] <= 0:
                    continue
                ep = exit_price_map.get(key)
                if ep and ep > 0:
                    ret = (ep / s["entry_price"]) - 1
                    ret = -ret  # short
                    returns.append(ret)
                else:
                    returns.append(-1.0)
            
            stats = compute_stats(returns, hp)
            result_009[f"hold_{hp}"] = stats
            print(f"  hold={hp}: n={stats['signal_count']}, WR={stats['win_rate']:.2%}, avg_ret={stats['avg_return']:.4f}")
        
        all_results["T2_gen009_consecutive_2day"] = result_009
    
    # Now check: what % of signals have consecutive up days? (to estimate population parameters)
    total_checked = len(signals)
    enriched_count = len(enriched)
    print(f"\nRatio: {enriched_count}/{total_checked} = {enriched_count/total_checked*100:.1f}% of signals have consecutive up day")

# ----- TEST 3: gen_010 - 天量下跌+次日低开确认 => 做空 -----
r3 = run_grid_test(
    "T3: 天量下跌(量比>5+跌幅<-3%)+低开 => 做空",
    "s.pct_chg < -3 AND d.volume_ratio > 5 AND s.open < s.pre_close * 0.99",
    direction="short", max_signals=5000
)
all_results["T3_gen010_gapdown"] = r3

# ----- TEST 4: gen_010 variant - stronger gap down (>2%) -----
r4 = run_grid_test(
    "T4: 天量下跌(量比>5+跌幅<-3%)+大幅低开(>2%) => 做空",
    "s.pct_chg < -3 AND d.volume_ratio > 5 AND s.open < s.pre_close * 0.98",
    direction="short", max_signals=5000
)
all_results["T4_gen010_gapdown_2pct"] = r4

# ----- TEST 5: New angle - 放量上涨 + high RSI (超买) => 做空 -----
# Using stk_factor_pro for RSI, but limited data window (2026-04-24 onward)
# Limited data but worth checking
r5 = run_grid_test(
    "T5: 放量上涨+RSI>70(超买) => 做空 (limited data)",
    "f.rsi_bfq_6 > 70 AND s.pct_chg > 3 AND d.volume_ratio > 2",
    direction="short", max_signals=1000
)
all_results["T5_overbought_short"] = r5

# ----- TEST 6: New - 缩量下跌+RSI<30+布林下轨 => 做多反弹 -----
r6 = run_grid_test(
    "T6: RSI<30+缩量(量比<0.7)+布林下轨 => 做多反弹",
    "f.rsi_bfq_6 < 30 AND d.volume_ratio < 0.7 AND s.close <= f.boll_lower_bfq_6 * 1.01 AND s.pct_chg < 0",
    direction="long", max_signals=500
)
all_results["T6_oversold_bounce"] = r6

# Save all results
print("\n\n===== ALL RESULTS =====")
print(json.dumps(all_results, ensure_ascii=False, indent=2))
with open("/tmp/round9_all_results.json", "w") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
