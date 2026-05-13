#!/usr/bin/env python3
"""
T7: 跨市场联动挖掘 (Iter 2) — Clean Backtest Engine
Uses two-step approach: stock_daily (pct_chg) → daily_basic (volume_ratio, circ_mv)
"""
import json
import subprocess
import math
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
DT_START = "2025-01-01"
DT_END = "2026-05-09"

def sql(query):
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return []
    if not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout)
    except:
        return []

def metrics(results, label):
    n = len(results)
    if n < 5:
        print(f"\n{'='*50}\n{label}\n{'='*50}\nSIGNALS={n} (too few)")
        return {"signal_count": n, "win_rate_5d": 0, "avg_ret_5d": 0, "avg_ret_10d": 0, "avg_ret_20d": 0, "sharpe_5d": 0}
    
    ret5 = [r.get("r5",0) or 0 for r in results]
    ret10 = [r.get("r10",0) or 0 for r in results]
    ret20 = [r.get("r20",0) or 0 for r in results]
    
    a5, a10, a20 = sum(ret5)/n*100, sum(ret10)/n*100, sum(ret20)/n*100
    w5 = sum(1 for r in ret5 if r>0)/n*100
    w10 = sum(1 for r in ret10 if r>0)/n*100
    
    std5 = math.sqrt(sum((r - a5/100)**2 for r in ret5)/n) if n>1 else 1
    sp5 = (a5/100)/std5 * math.sqrt(252/5) if std5>0 else 0
    
    std10 = math.sqrt(sum((r - a10/100)**2 for r in ret10)/n) if n>1 and ret10 else 1
    sp10 = (a10/100)/std10 * math.sqrt(252/10) if std10>0 else 0
    
    m = {
        "signal_count": n, "win_rate_5d": round(w5,2), "win_rate_10d": round(w10,2),
        "avg_ret_5d": round(a5,2), "avg_ret_10d": round(a10,2), "avg_ret_20d": round(a20,2),
        "sharpe_5d": round(sp5,3), "sharpe_10d": round(sp10,3)
    }
    print(f"\n{'='*50}\n{label}\n{'='*50}")
    for k,v in m.items():
        print(f"  {k}: {v}")
    return m


def get_macro_dates(query, label):
    """Get date string list from a macro query."""
    results = sql(query)
    dates = []
    for r in results:
        v = list(r.values())[0]  # get first value
        dates.append(str(v)[:10])
    print(f"  {label}: {len(dates)} dates")
    return dates


def backtest(label, macro_dates, pct_chg_cond, daily_cond, max_signals=3000):
    """Two-step backtest.
    
    Step 1: Query stock_daily for ts_code + trade_date matching pct_chg_cond on macro_dates
    Step 2: Filter by daily_basic daily_cond
    Step 3: Compute forward returns using stock_daily leadInFrame
    
    pct_chg_cond: SQL WHERE fragment for stock_daily (e.g. "pct_chg BETWEEN -5 AND 2")
    daily_cond: SQL WHERE fragment for daily_basic (e.g. "volume_ratio > 1.2 AND circ_mv < 20000000000")
    """
    if not macro_dates:
        print(f"\n{'='*50}\n{label}\n{'='*50}\nNO MACRO DATES")
        return None
    
    all_signal_rows = []
    
    for i in range(0, len(macro_dates), 150):
        batch = macro_dates[i:i+150]
        dq = ",".join(f"'{d}'" for d in batch)
        
        # Step 1: Query stock_daily for pct_chg condition
        sql1 = f"""
        SELECT ts_code, trade_date, pct_chg
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date IN ({dq})
          AND {pct_chg_cond}
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
          AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
        LIMIT 10000
        """
        r1 = sql(sql1)
        all_signal_rows.extend(r1)
        if len(all_signal_rows) >= max_signals * 3:
            break
    
    if not all_signal_rows:
        print(f"\n{'='*50}\n{label}\n{'='*50}\nNO SIGNALS (step 1)")
        return None
    
    # Step 2: Filter by daily_basic conditions
    # Get unique codes and dates from step 1
    signal_keys = list(set((r['ts_code'], r['trade_date']) for r in all_signal_rows))
    signal_codes = list(set(k[0] for k in signal_keys))
    signal_dates = list(set(k[1] for k in signal_keys))
    print(f"  Step1 signals: {len(signal_keys)}, codes={len(signal_codes)}, dates={len(signal_dates)}")
    
    filtered_signals = []
    # Batch codes
    for bi in range(0, len(signal_codes), 100):
        code_batch = signal_codes[bi:bi+100]
        cq = ",".join(f"'{c}'" for c in code_batch)
        
        # Batch dates too
        for di in range(0, len(signal_dates), 100):
            date_batch = signal_dates[di:di+100]
            dq = ",".join(f"'{d}'" for d in date_batch)
            
            sql2 = f"""
            SELECT ts_code, trade_date, volume_ratio, circ_mv
            FROM tushare.tushare_daily_basic FINAL
            WHERE ts_code IN ({cq})
              AND trade_date IN ({dq})
              AND {daily_cond}
            """
            r2 = sql(sql2)
            filtered_signals.extend(r2)
    
    if not filtered_signals:
        print(f"\n{'='*50}\n{label}\n{'='*50}\nNO SIGNALS (step 2 - daily_basic filter)")
        return None
    
    # Deduplicate and limit
    seen = set()
    unique_signals = []
    for s in filtered_signals:
        k = (s['ts_code'], s['trade_date'])
        if k not in seen:
            seen.add(k)
            unique_signals.append(s)
    
    if len(unique_signals) > max_signals:
        unique_signals = unique_signals[:max_signals]
    
    print(f"  Filtered signals: {len(unique_signals)}")
    
    # Step 3: Compute forward returns
    codes = list(set(s['ts_code'] for s in unique_signals))
    results = []
    
    for code_batch in [codes[i:i+100] for i in range(0, len(codes), 100)]:
        cq = ",".join(f"'{c}'" for c in code_batch)
        sql_px = f"""
        SELECT ts_code, trade_date, close,
               leadInFrame(close, 5) OVER w AS c5,
               leadInFrame(close, 10) OVER w AS c10,
               leadInFrame(close, 20) OVER w AS c20
        FROM tushare.tushare_stock_daily FINAL
        WHERE ts_code IN ({cq})
          AND trade_date >= '{DT_START}' AND trade_date <= '2026-07-01'
        WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ORDER BY ts_code, trade_date
        """
        px_rows = sql(sql_px)
        
        # Build lookup
        px_map = {}
        for r in px_rows:
            px_map[(r['ts_code'], r['trade_date'])] = r
        
        # Compute returns
        for s in unique_signals:
            key = (s['ts_code'], s['trade_date'])
            if key in px_map:
                px = px_map[key]
                if px.get('close') and px['close'] > 0:
                    r5 = (px['c5']/px['close'] - 1) if px.get('c5') else 0
                    r10 = (px['c10']/px['close'] - 1) if px.get('c10') else 0
                    r20 = (px['c20']/px['close'] - 1) if px.get('c20') else 0
                    results.append({'code': s['ts_code'], 'date': s['trade_date'], 'r5': r5 or 0, 'r10': r10 or 0, 'r20': r20 or 0})
    
    return metrics(results, label)


def main():
    # ===== Get macro dates =====
    print(">>> Fetching macro condition dates...")
    
    md_heavy_north = get_macro_dates(
        "SELECT trade_date FROM tushare.tushare_moneyflow_hsgt FINAL WHERE north_money > 350000 AND trade_date >= '2025-01-01' ORDER BY trade_date",
        "北向大幅流入(>35亿)"
    )
    
    md_north = get_macro_dates(
        "SELECT trade_date FROM tushare.tushare_moneyflow_hsgt FINAL WHERE north_money > 250000 AND trade_date >= '2025-01-01' ORDER BY trade_date",
        "北向流入(>25亿)"
    )
    
    md_shibor = get_macro_dates(
        "SELECT date FROM tushare.tushare_shibor FINAL WHERE 1w < 1.7 AND date >= '2025-01-01' ORDER BY date",
        "Shibor宽松(<1.7%)"
    )
    
    md_hs300 = get_macro_dates(
        "SELECT trade_date FROM tushare.tushare_index_daily FINAL WHERE ts_code='000300.SH' AND pct_chg > 0.5 AND trade_date >= '2025-01-01' ORDER BY trade_date",
        "HS300涨幅>0.5%"
    )
    
    md_hs300_strong = get_macro_dates(
        "SELECT trade_date FROM tushare.tushare_index_daily FINAL WHERE ts_code='000300.SH' AND pct_chg > 1.0 AND trade_date >= '2025-01-01' ORDER BY trade_date",
        "HS300大涨>1%"
    )
    
    # Double resonance
    north_set = set(md_north)
    hs300_set = set(md_hs300)
    md_double = sorted(north_set & hs300_set)
    print(f"  北向+HS300双共振: {len(md_double)} dates")
    
    # ===== Run 5 backtests =====
    
    # C1: 北向资金大举流入(>35亿) + 低位放量反击
    backtest("C1: 北向>35亿 + 低位放量(pct_chg-5~2%, VR>1.2, circ_mv<200亿)",
             md_heavy_north,
             "pct_chg IS NOT NULL AND pct_chg >= -5 AND pct_chg <= 2",
             "volume_ratio > 1.2 AND circ_mv IS NOT NULL AND circ_mv < 20000000000")
    
    # C2: 北向资金流入(>25亿) + 强势突破
    backtest("C2: 北向>25亿 + 强势突破(pct_chg>2%, VR>1.8, circ_mv 30-500亿)",
             md_north,
             "pct_chg IS NOT NULL AND pct_chg > 2",
             "volume_ratio > 1.8 AND circ_mv IS NOT NULL AND circ_mv >= 3000000000 AND circ_mv <= 50000000000")
    
    # C3: Shibor宽松(<1.7) + 超跌小盘
    backtest("C3: Shibor<1.7% + 超跌(pct_chg-7~-2%, VR>0.8, circ_mv<50亿)",
             md_shibor,
             "pct_chg IS NOT NULL AND pct_chg >= -7 AND pct_chg <= -2",
             "volume_ratio > 0.8 AND circ_mv IS NOT NULL AND circ_mv < 5000000000")
    
    # C4: HS300大涨>1% + 放量跟进
    backtest("C4: HS300>1% + 放量跟进(pct_chg>0%, VR>1.3, circ_mv<500亿)",
             md_hs300_strong,
             "pct_chg IS NOT NULL AND pct_chg > 0",
             "volume_ratio > 1.3 AND circ_mv IS NOT NULL AND circ_mv < 50000000000")
    
    # C5: 北向+HS300双共振 + 量价突破
    backtest("C5: 北向>25亿+HS300>0.5%双共振 + 量价突破(pct_chg>3%, VR>2.0, circ_mv 30-500亿)",
             md_double,
             "pct_chg IS NOT NULL AND pct_chg > 3",
             "volume_ratio > 2.0 AND circ_mv IS NOT NULL AND circ_mv >= 3000000000 AND circ_mv <= 50000000000")
    
    print("\n" + "="*60)
    print("T7 跨市场联动挖掘 (Iter 2) — ALL DONE")
    print("="*60)

if __name__ == "__main__":
    main()
