#!/usr/bin/env python3
"""
gen_009: 放量上涨(量比>3+涨幅>3%)+连续2日收阳 → 做空持有5日
Optimized version with smaller samples
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from grid_engine import run_grid, compute_stats, ch_query, load_trade_cal

def run_custom_test(sql, label, hold_periods=[1,2,3,5], direction="short"):
    """Run a full test on custom SQL signals"""
    print(f"\n{'='*60}")
    print(f"Test: {label}")
    print('='*60)
    
    rows = ch_query(sql)
    print(f"Signals: {len(rows)}")
    if not rows:
        print("NO SIGNALS")
        return {"error": "no_signals"}
    
    trade_cal = load_trade_cal()
    cal_list = trade_cal["cal"]
    
    date_groups = {}
    for s in rows:
        date_groups.setdefault(s["trade_date"], []).append((s["ts_code"], s["entry_price"]))
    
    results = {}
    for hp in hold_periods:
        exit_lookup = {}
        for entry_date in date_groups:
            if entry_date in trade_cal["set"]:
                idx = cal_list.index(entry_date)
                target_idx = idx + hp
                if 0 <= target_idx < len(cal_list):
                    exit_date = cal_list[target_idx]
                    for ts_code, _ in date_groups[entry_date]:
                        exit_lookup[(ts_code, entry_date)] = exit_date
        
        exit_price_map = {}
        rev_map = {}
        for (ts_code, entry_date), exit_date in exit_lookup.items():
            rev_map[(ts_code, exit_date)] = entry_date
        
        date_code_groups = {}
        for (ts_code, entry_date), exit_date in exit_lookup.items():
            date_code_groups.setdefault(exit_date, []).append(ts_code)
        
        for exit_date, codes in date_code_groups.items():
            unique_codes = list(set(codes))
            for i in range(0, len(unique_codes), 2000):
                batch = unique_codes[i:i+2000]
                codes_str = ", ".join(f"'{c}'" for c in batch)
                resp = ch_query(
                    f"SELECT ts_code, close FROM tushare.tushare_stock_daily FINAL "
                    f"WHERE trade_date = '{exit_date}' AND ts_code IN ({codes_str})"
                )
                for r in resp:
                    entry_dt = rev_map.get((r["ts_code"], exit_date))
                    if entry_dt:
                        exit_price_map[(r["ts_code"], entry_dt)] = r["close"]
        
        returns = []
        for s in rows:
            key = (s["ts_code"], s["trade_date"])
            if s["entry_price"] <= 0:
                continue
            exit_price = exit_price_map.get(key)
            if exit_price and exit_price > 0:
                ret = (exit_price / s["entry_price"]) - 1
                if direction == "short":
                    ret = -ret
                returns.append(ret)
            else:
                returns.append(-1.0)
        
        stats = compute_stats(returns, hp)
        results[f"hold_{hp}"] = stats
        print(f"  hold={hp}: n={stats['signal_count']}, WR={stats['win_rate']:.2%}, avg_ret={stats['avg_return']:.4f}, CI=[{stats['ci_95_lower']:.2%},{stats['ci_95_upper']:.2%}], Sharpe={stats['sharpe_ratio']:.2f}")
    
    return results


if __name__ == "__main__":
    # === Test B: 连续2日收阳 + 量比>3 + 涨幅>3% ===
    sql_b = """
    WITH base AS (
        SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
               d.volume_ratio,
               LAG(s.pct_chg, 1) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev1_pct,
               LAG(s.pct_chg, 2) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev2_pct
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
        LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS d
            ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
        WHERE s.close > 0
    )
    SELECT ts_code, trade_date, close AS entry_price, pct_chg AS entry_pct
    FROM base
    WHERE volume_ratio > 3 
      AND pct_chg > 3
      AND prev1_pct > 0  -- previous day also bullish
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR))
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_suspend_d FINAL WHERE trade_date >= DATE_SUB('2026-05-11', INTERVAL 10 DAY))
    ORDER BY rand()
    LIMIT 10000
    """
    result_b = run_custom_test(sql_b, "量比>3+涨幅>3%+连续2日收阳 → 做空")
    
    # === Test C: 连续3日收阳 (更严格) ===
    sql_c = """
    WITH base AS (
        SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
               d.volume_ratio,
               LAG(s.pct_chg, 1) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev1_pct,
               LAG(s.pct_chg, 2) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev2_pct
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
        LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS d
            ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
        WHERE s.close > 0
    )
    SELECT ts_code, trade_date, close AS entry_price, pct_chg AS entry_pct
    FROM base
    WHERE volume_ratio > 3 
      AND pct_chg > 3
      AND prev1_pct > 0
      AND prev2_pct > 0
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR))
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_suspend_d FINAL WHERE trade_date >= DATE_SUB('2026-05-11', INTERVAL 10 DAY))
    ORDER BY rand()
    LIMIT 10000
    """
    result_c = run_custom_test(sql_c, "量比>3+涨幅>3%+连续3日收阳 → 做空")
    
    # === Test D: 量比>3+涨幅>3% but check if PREVIOUS DAY also had volume_ratio>2 (连续放量) ===
    sql_d = """
    WITH base AS (
        SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
               d.volume_ratio,
               LAG(d.volume_ratio, 1) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev_vol_ratio
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
        LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS d
            ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
        WHERE s.close > 0
    )
    SELECT ts_code, trade_date, close AS entry_price, pct_chg AS entry_pct
    FROM base
    WHERE volume_ratio > 3 
      AND pct_chg > 3
      AND prev_vol_ratio > 2
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR))
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_suspend_d FINAL WHERE trade_date >= DATE_SUB('2026-05-11', INTERVAL 10 DAY))
    ORDER BY rand()
    LIMIT 10000
    """
    result_d = run_custom_test(sql_d, "量比>3+涨幅>3%+前日也放量(量比>2) → 做空")
    
    # === Save results for report ===
    output = {
        "test_B_consecutive_2day_bull": result_b,
        "test_C_consecutive_3day_bull": result_c,
        "test_D_consecutive_volume": result_d,
    }
    print("\n\n=== FINAL RESULTS ===")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    
    with open("/tmp/gen_009_results.json", "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
