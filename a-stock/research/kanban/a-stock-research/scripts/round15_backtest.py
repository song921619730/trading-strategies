#!/usr/bin/env python3
"""
Round 15 Backtest: long_004 — RSI<30 + 收阳线 + close>5元 → 超跌反弹1日

Two approaches:
  A) Using stk_factor_pro single table (grid_engine, limited to 2026-04-24+)
  B) Computing RSI(6) from stock_daily for full 2020-2026 range
"""
import sys, os, json, math, subprocess
from datetime import datetime, date

sys.path.insert(0, 'scripts')
from grid_engine import run_grid, compute_stats, ch_query, load_trade_cal, next_trade_day

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def compute_rsi_6_sql():
    """Compute RSI(6) from stock_daily close prices.
    
    RSI = 100 - 100 / (1 + RS)
    RS = avg_gain / avg_loss over 6 periods
    """
    return """
    WITH price_chg AS (
        SELECT 
            ts_code, trade_date, close, pct_chg,
            -- Calculate initial RSI(6) entry condition
            CASE 
                WHEN row_number() OVER (PARTITION BY ts_code ORDER BY trade_date) < 7 THEN NULL
                ELSE 100 - 100 / (
                    1 + (
                        -- avg gain (absolute pct_chg when positive)
                        avg(CASE WHEN pct_chg > 0 THEN pct_chg ELSE 0 END) 
                            OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING)
                        /
                        nullIf(
                            avg(CASE WHEN pct_chg < 0 THEN -pct_chg ELSE 0 END) 
                                OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING),
                            0
                        )
                    )
                )
            END AS rsi_6
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date BETWEEN '2020-01-02' AND '2026-05-11'
    )
    SELECT ts_code, trade_date, close AS entry_price, pct_chg AS entry_pct, rsi_6
    FROM price_chg
    WHERE rsi_6 < 30 AND close > 5 AND pct_chg > 0
    """
def run_full_backtest():
    """Run backtest using stock_daily with computed RSI(6)"""
    print("=" * 60)
    print("Approach B: stock_daily with computed RSI(6)")
    print("=" * 60)
    
    # Compute RSI and get entry signals
    sql = compute_rsi_6_sql()
    print(f"[backtest] Executing RSI computation query...")
    r = subprocess.run(
        ["python3", CH_SCRIPT, "sql", sql],
        capture_output=True, text=True, timeout=300
    )
    idx = r.stdout.find('[')
    if idx < 0:
        print(f"ERROR: {r.stderr[:500]}")
        print(f"STDOUT: {r.stdout[:500]}")
        return None
    
    signals = json.loads(r.stdout[idx:])
    print(f"[backtest] Entry signals: {len(signals)}")
    
    if not signals:
        return {"error": "no_signals"}
    
    # Load trade calendar
    trade_cal = load_trade_cal()
    cal_list = trade_cal["cal"]
    cal_set = trade_cal["set"]
    
    # Group signals by entry date
    date_groups = {}
    for s in signals:
        date_groups.setdefault(s["trade_date"], []).append((s["ts_code"], s["entry_price"]))
    
    hold_periods = [1, 3, 5, 10, 20]
    results = {}
    
    for hp in hold_periods:
        print(f"[backtest] hold={hp}: finding exit dates...")
        
        # Build exit date lookup
        exit_lookup = {}
        for entry_date in date_groups:
            if entry_date in cal_set:
                idx = cal_list.index(entry_date)
                target_idx = idx + hp
                if 0 <= target_idx < len(cal_list):
                    exit_date = cal_list[target_idx]
                    for ts_code, _ in date_groups[entry_date]:
                        exit_lookup[(ts_code, entry_date)] = exit_date
        
        # Batch query exit prices
        exit_price_map = {}
        date_code_groups = {}
        for (ts_code, entry_date), exit_date in exit_lookup.items():
            date_code_groups.setdefault(exit_date, []).append(ts_code)
        
        rev_map = {}
        for (ts_code, entry_date), exit_date in exit_lookup.items():
            rev_map[(ts_code, exit_date)] = entry_date
        
        for exit_date, codes in date_code_groups.items():
            unique_codes = list(set(codes))
            for i in range(0, len(unique_codes), 2000):
                batch = unique_codes[i:i+2000]
                codes_str = ", ".join(f"'{c}'" for c in batch)
                rows = ch_query(
                    f"SELECT ts_code, close FROM tushare.tushare_stock_daily FINAL "
                    f"WHERE trade_date = '{exit_date}' AND ts_code IN ({codes_str})"
                )
                for r in rows:
                    entry_dt = rev_map.get((r["ts_code"], exit_date))
                    if entry_dt:
                        exit_price_map[(r["ts_code"], entry_dt)] = r["close"]
        
        # Calculate returns
        returns = []
        for s in signals:
            key = (s["ts_code"], s["trade_date"])
            if s["entry_price"] <= 0:
                continue
            exit_price = exit_price_map.get(key)
            if exit_price and exit_price > 0:
                ret = (exit_price / s["entry_price"]) - 1
                returns.append(ret)
            else:
                returns.append(-1.0)  # delisted
        
        stats = compute_stats(returns, hp)
        results[f"hold_{hp}"] = stats
        print(f"[backtest] hold={hp}: {stats['signal_count']} signals, WR={stats['win_rate']:.2%}, avg_ret={stats['avg_return']:.4f}")
    
    return results

def run_grid_backtest():
    """Run grid_engine with factor table only"""
    print("=" * 60)
    print("Approach A: grid_engine with stk_factor_pro single table")
    print("=" * 60)
    
    config = {
        'entry_sql': 'factor.rsi_bfq_6 < 30 AND factor.pct_chg > 0 AND factor.close > 5',
        'tables': {'factor': 'tushare_stk_factor_pro'},
        'hold_periods': [1, 3, 5, 10, 20],
        'direction': 'long',
        'max_signals': None
    }
    
    result = run_grid(config)
    return result

if __name__ == "__main__":
    print("Round 15 Backtest — long_004: RSI<30 + 收阳线 + close>5 → 超跌反弹")
    print(f"Date: {datetime.now().isoformat()}")
    print()
    
    # Approach A: grid_engine with factor table
    result_a = run_grid_backtest()
    print()
    print("=" * 60)
    print("Result A (stk_factor_pro, limited range)")
    print("=" * 60)
    print(json.dumps(result_a, ensure_ascii=False, indent=2))
    
    print()
    
    # Approach B: stock_daily with computed RSI
    result_b = run_full_backtest()
    print()
    print("=" * 60)
    print("Result B (stock_daily with computed RSI, full range)")
    print("=" * 60)
    print(json.dumps(result_b, ensure_ascii=False, indent=2))
    
    # Save to file
    output = {
        "approach_a": result_a,
        "approach_b": result_b,
        "generated_at": datetime.now().isoformat()
    }
    with open("logs/round_015/backtest_results.json", "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print()
    print("Results saved to logs/round_015/backtest_results.json")
