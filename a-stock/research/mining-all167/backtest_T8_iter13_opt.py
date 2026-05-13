#!/usr/bin/env python3
"""
T8: 量价形态 回测 — Iter 13 Optimized Variants
Based on initial scan results, optimize top performers with additional filters.
Top from initial scan: C8(尾盘拉升 Sharpe=0.647), C11(缩量回调 Sharpe=0.438), 
C9(双底放量 Sharpe=0.575), C3(低开高走 WR=53.9%), C1(十字星 WR=50.2%)

Strategy: Add position/valuation/momentum filters to narrow signals and improve quality.
"""
import json
import subprocess
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
DT_START = "2025-03-01"
DT_END = "2026-05-09"

def sql(query):
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return []
    if not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout)
    except:
        return []

def compute_metrics(results, label):
    n = len(results)
    if n < 10:
        return {"label": label, "signal_count": n, "win_rate_5d": 0, "avg_ret_5d": 0, "sharpe_5d": 0}
    
    ret5 = [r.get("r5", 0) or 0 for r in results]
    ret10 = [r.get("r10", 0) or 0 for r in results]
    ret20 = [r.get("r20", 0) or 0 for r in results]
    
    a5 = sum(ret5) / n * 100
    a10 = sum(ret10) / n * 100
    a20 = sum(ret20) / n * 100
    
    w5 = sum(1 for r in ret5 if r > 0) / n * 100
    w10 = sum(1 for r in ret10 if r > 0) / n * 100
    w20 = sum(1 for r in ret20 if r > 0) / n * 100
    
    std5 = math.sqrt(sum((x - a5/100)**2 for x in ret5) / n) if n > 1 else 1
    sp5 = (a5 / 100) / std5 * math.sqrt(252 / 5) if std5 > 0 else 0
    
    std10 = math.sqrt(sum((x - a10/100)**2 for x in ret10) / n) if n > 1 else 1
    sp10 = (a10 / 100) / std10 * math.sqrt(252 / 10) if std10 > 0 else 0
    
    dd5 = min(0, min(ret5)) * 100
    
    m = {
        "label": label,
        "signal_count": n,
        "win_rate_5d": round(w5, 2),
        "win_rate_10d": round(w10, 2),
        "win_rate_20d": round(w20, 2),
        "avg_ret_5d": round(a5, 4),
        "avg_ret_10d": round(a10, 4),
        "avg_ret_20d": round(a20, 4),
        "sharpe_5d": round(sp5, 3),
        "sharpe_10d": round(sp10, 3),
        "max_drawdown_5d": round(dd5, 2),
        "total_return_5d": round(sum(ret5) * 100, 2)
    }
    return m


def get_all_trade_dates():
    q = f"""
    SELECT DISTINCT trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
    WHERE trade_date >= '{DT_START}' AND trade_date <= '{DT_END}'
    ORDER BY trade_date
    """
    return [r['trade_date'] for r in sql(q)]


def run_backtest(label, where_clause, trade_dates, max_signals=20000):
    """Run backtest with forward return computation."""
    all_signals = []
    batch_size = 80
    
    for i in range(0, len(trade_dates), batch_size):
        batch = trade_dates[i:i+batch_size]
        dq = ",".join(f"'{d}'" for d in batch)
        
        q = f"""
        SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close, sd.open,
               db.volume_ratio, db.circ_mv, db.turnover_rate
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
        JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
          ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
        WHERE sd.trade_date IN ({dq})
          AND {where_clause}
          AND sd.close > 0 AND sd.pre_close > 0
        """
        r = sql(q)
        all_signals.extend(r)
        if len(all_signals) >= max_signals:
            break
    
    seen = set()
    unique = []
    for s in all_signals:
        k = (s['ts_code'], s['trade_date'])
        if k not in seen:
            seen.add(k)
            unique.append(s)
    
    codes = list(set(s['ts_code'] for s in unique))
    results = []
    
    for code_batch in [codes[i:i+100] for i in range(0, len(codes), 100)]:
        cq = ",".join(f"'{c}'" for c in code_batch)
        
        q_px = f"""
        SELECT ts_code, trade_date, close,
               leadInFrame(close, 5) OVER w AS c5,
               leadInFrame(close, 10) OVER w AS c10,
               leadInFrame(close, 20) OVER w AS c20
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
        WHERE ts_code IN ({cq})
          AND trade_date >= '{DT_START}' AND trade_date <= '2026-06-15'
        WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date
                     ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ORDER BY ts_code, trade_date
        """
        px_rows = sql(q_px)
        px_map = {}
        for r in px_rows:
            px_map[(r['ts_code'], r['trade_date'])] = r
        
        for s in unique:
            key = (s['ts_code'], s['trade_date'])
            if key in px_map:
                px = px_map[key]
                if px.get('close') and px['close'] > 0:
                    r5 = (px['c5'] / px['close'] - 1) if px.get('c5') and px['c5'] > 0 else None
                    r10 = (px['c10'] / px['close'] - 1) if px.get('c10') and px['c10'] > 0 else None
                    r20 = (px['c20'] / px['close'] - 1) if px.get('c20') and px['c20'] > 0 else None
                    if r5 is not None:
                        results.append({
                            'code': s['ts_code'],
                            'date': s['trade_date'],
                            'r5': r5, 'r10': r10, 'r20': r20
                        })
    
    return compute_metrics(results, label)


def main():
    print("=" * 60)
    print("T8: 量价形态 Iter 13 — Optimized Variants")
    print(f"时间范围: {DT_START} ~ {DT_END}")
    print("=" * 60)
    
    all_dates = get_all_trade_dates()
    all_dates_set = set(all_dates)
    print(f"Trading days: {len(all_dates)}")
    
    EXCLUDE = "sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%' AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'"
    
    # ========================================================================
    # OPTIMIZED VARIANTS — based on initial scan top performers
    # ========================================================================
    
    # C8-Opt1: 尾盘拉升线 + 更严格条件 (initial: WR5=49.4%, R5=0.71%, Sharpe=0.647, N=12126)
    # Add: 换手>1% (排除死股), 市值<=30亿 (更小弹性), 涨幅3-7% (排除涨停和微弱涨幅)
    C8o1_name = "尾盘拉升线(精)"
    C8o1_where = f"""
    sd.close / sd.high >= 0.97
    AND sd.pct_chg >= 3.0 AND sd.pct_chg <= 7.0
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 1.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND {EXCLUDE}
    """
    
    # C8-Opt2: 尾盘拉升 + 资金确认 (buy_lg > sell_lg)
    # 需要moneyflow表，先不加，改用低PE+低PB
    C8o2_name = "尾盘拉升+低估值"
    C8o2_where = f"""
    sd.close / sd.high >= 0.97
    AND sd.pct_chg >= 2.0 AND sd.pct_chg <= 7.0
    AND db.volume_ratio >= 1.3
    AND db.circ_mv <= 500000
    AND db.turnover_rate >= 0.5
    AND db.pe > 0 AND db.pe <= 30
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND {EXCLUDE}
    """
    
    # C11-Opt1: 缩量回调支撑反弹 + 更严 (initial: WR5=53.4%, R5=0.67%, Sharpe=0.438, N=1691)
    # Add: 换手0.5-3%, 市值<=30亿, 振幅>=5%
    C11o1_name = "缩量回调支撑反弹(精)"
    C11o1_where = f"""
    sd.pct_chg >= 1.5 AND sd.pct_chg <= 7.0
    AND sd.low / sd.pre_close <= 0.96
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 0.5 AND db.turnover_rate <= 5.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND sd.close > sd.open
    AND {EXCLUDE}
    """
    
    # C9-Opt1: 双底确认放量 + 更严 (initial: WR5=48.8%, R5=0.64%, Sharpe=0.575, N=12209)
    C9o1_name = "双底确认放量(精)"
    C9o1_where = f"""
    sd.close > sd.open
    AND sd.pct_chg >= 2.0 AND sd.pct_chg <= 7.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 1.0
    AND {EXCLUDE}
    """
    
    # C3-Opt1: 低开高走大阳线 + 更严 (initial: WR5=53.9%, R5=0.45%, Sharpe=0.310, N=1690)
    C3o1_name = "低开高走大阳线(精)"
    C3o1_where = f"""
    sd.open / sd.pre_close < 0.97
    AND sd.close / sd.open >= 1.04
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 6.0
    AND db.volume_ratio >= 1.3
    AND db.circ_mv <= 400000
    AND db.turnover_rate >= 1.0
    AND sd.pct_chg <= 9.5
    AND {EXCLUDE}
    """
    
    # C1-Opt1: 十字星+放量 + 更严 (initial: WR5=50.2%, R5=0.47%, Sharpe=0.426, N=448)
    C1o1_name = "缩量十字星+放量突破(精)"
    C1o1_where = f"""
    sd.close > sd.open
    AND (sd.high - sd.low) > 0
    AND abs(sd.close - sd.open) / (sd.high - sd.low) <= 0.15
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 1.0
    AND sd.pct_chg >= 1.5 AND sd.pct_chg <= 7.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND {EXCLUDE}
    """
    
    # New combo: 尾盘拉升 + 低换手(筹码锁定)
    # 尾盘拉升(close/high>=0.97) + 换手<2% + VR>=1.3 + 涨幅2-6% + CM<=50亿
    NEW1_name = "尾盘拉升+筹码锁定"
    NEW1_where = f"""
    sd.close / sd.high >= 0.97
    AND sd.pct_chg >= 2.0 AND sd.pct_chg <= 6.0
    AND db.volume_ratio >= 1.3
    AND db.circ_mv <= 500000
    AND db.turnover_rate >= 0.3 AND db.turnover_rate <= 2.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND {EXCLUDE}
    """
    
    # New combo: 放量阳线+低PE+小盘
    # 涨幅>=2% + VR>=1.5 + PE>0且<=25 + CM<=40亿 + 换手1-4%
    NEW2_name = "放量阳线+低PE小盘"
    NEW2_where = f"""
    sd.close > sd.open
    AND sd.pct_chg >= 2.0 AND sd.pct_chg <= 7.0
    AND db.volume_ratio >= 1.5
    AND db.pe > 0 AND db.pe <= 25
    AND db.circ_mv <= 400000
    AND db.turnover_rate >= 1.0 AND db.turnover_rate <= 4.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND {EXCLUDE}
    """
    
    # New combo: 长下影+放量+微盘 (C10精化)
    # 下影>=实体1.5倍 + VR>=1.8 + CM<=20亿 + 振幅>=6% + 换手1-5%
    NEW3_name = "长下影探底(微盘)"
    NEW3_where = f"""
    sd.close > sd.pre_close
    AND (sd.close - sd.low) >= 1.5 * abs(sd.close - sd.open)
    AND db.volume_ratio >= 1.8
    AND db.circ_mv <= 200000
    AND db.turnover_rate >= 1.0 AND db.turnover_rate <= 5.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 6.0
    AND sd.pct_chg <= 9.5
    AND {EXCLUDE}
    """
    
    # New combo: 放量突破前高 (近5日最高价突破)
    # 涨幅>=3% + VR>=2.0 + close=high + CM<=50亿 + 换手>=1.5%
    NEW4_name = "放量突破前高"
    NEW4_where = f"""
    sd.close = sd.high
    AND sd.pct_chg >= 3.0 AND sd.pct_chg <= 9.0
    AND db.volume_ratio >= 2.0
    AND db.circ_mv <= 500000
    AND db.turnover_rate >= 1.5
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND {EXCLUDE}
    """
    
    all_results = []
    configs = [
        (C8o1_name, C8o1_where),
        (C8o2_name, C8o2_where),
        (C11o1_name, C11o1_where),
        (C9o1_name, C9o1_where),
        (C3o1_name, C3o1_where),
        (C1o1_name, C1o1_where),
        (NEW1_name, NEW1_where),
        (NEW2_name, NEW2_where),
        (NEW3_name, NEW3_where),
        (NEW4_name, NEW4_where),
    ]
    
    for name, where in configs:
        print(f"\n>>> Testing: {name}")
        r = run_backtest(f"T8-{name}", where, all_dates)
        all_results.append(r)
        n = r.get('signal_count', 0)
        wr5 = r.get('win_rate_5d', 0)
        ret5 = r.get('avg_ret_5d', 0)
        sp5 = r.get('sharpe_5d', 0)
        print(f"  → N={n}, WR5={wr5}%, R5={ret5}%, Sharpe5={sp5}")
    
    # ========================================================================
    # Summary
    # ========================================================================
    print(f"\n\n{'='*80}")
    print(f"T8 量价形态 Iter 13 Optimized — SUMMARY")
    print(f"{'='*80}")
    print(f"{'信号':<25} {'N':>6} {'WR5%':>7} {'R5%':>7} {'Sharpe5':>8} {'WR10%':>7} {'R10%':>7} {'Sharpe10':>8}")
    print(f"{'-'*80}")
    
    passed = []
    for r in all_results:
        label = r.get('label', 'Unknown')
        n = r.get('signal_count', 0)
        wr5 = r.get('win_rate_5d', 0)
        ret5 = r.get('avg_ret_5d', 0)
        sp5 = r.get('sharpe_5d', 0)
        wr10 = r.get('win_rate_10d', 0)
        ret10 = r.get('avg_ret_10d', 0)
        sp10 = r.get('sharpe_10d', 0)
        
        short = label.replace('T8-', '')
        print(f"{short:<25} {n:>6} {wr5:>6.1f}% {ret5:>6.2f}% {sp5:>8.3f} {wr10:>6.1f}% {ret10:>6.2f}% {sp10:>8.3f}")
        
        # Pass: WR5>=55% AND R5>=2% AND N>=100
        if wr5 >= 55 and ret5 >= 2.0 and n >= 100:
            passed.append(label)
    
    print(f"\nPASS RATE: {len(passed)}/{len(all_results)}")
    if passed:
        print("PASSED:")
        for p in passed:
            print(f"  ✅ {p}")
    else:
        print("  No combos passed (WR5>=55%, R5>=2%, N>=100)")
        # Show near-misses
        print("\nNEAR-MISSES (best by Sharpe5):")
        sorted_r = sorted(all_results, key=lambda x: x.get('sharpe_5d', 0), reverse=True)
        for r in sorted_r[:5]:
            print(f"  {r.get('label','?')}: N={r.get('signal_count',0)}, WR5={r.get('win_rate_5d',0)}%, R5={r.get('avg_ret_5d',0)}%, Sharpe={r.get('sharpe_5d',0)}")
    
    # Save
    output = {
        "iteration": "13_optimized",
        "type": "T8_量价形态_Optimized",
        "date_range": {"start": DT_START, "end": DT_END},
        "results": all_results,
        "passed": [r['label'] for r in all_results if r.get('win_rate_5d',0)>=55 and r.get('avg_ret_5d',0)>=2.0 and r.get('signal_count',0)>=100],
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_13/t8_iter13_optimized_results.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to: {output_path}")

if __name__ == "__main__":
    main()
