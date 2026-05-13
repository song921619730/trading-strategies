#!/usr/bin/env python3
"""
T8: 量价形态 Iter 13 — Round 3: Push near-misses over threshold
Best so far: 缩量回调支撑反弹(精) WR5=88%, R5=4.95%, Sharpe=4.288, N=159

Near-misses to optimize:
- 尾盘拉升+筹码锁定: WR5=59.1%, R5=1.82%, Sharpe=1.756, N=1020 → need R5>=2%
- 放量阳线+低PE小盘: WR5=55.7%, R5=1.17%, Sharpe=1.211, N=309 → need R5>=2%
- 长下影探底(微盘): WR5=71.4%, R5=3.66%, Sharpe=3.414, N=42 → need N>=100
"""
import json
import subprocess
import math
import os
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
        return {"label": label, "signal_count": n, "win_rate_5d": 0, "avg_ret_5d": 0, "sharpe_5d": 0,
                "win_rate_10d": 0, "avg_ret_10d": 0, "sharpe_10d": 0, "win_rate_20d": 0, "avg_ret_20d": 0}
    
    ret5 = [r.get("r5", 0) or 0 for r in results]
    ret10 = [r.get("r10", 0) or 0 for r in results]
    ret20 = [r.get("r20", 0) or 0 for r in results]
    
    a5 = sum(ret5) / n * 100; a10 = sum(ret10) / n * 100; a20 = sum(ret20) / n * 100
    w5 = sum(1 for r in ret5 if r > 0) / n * 100
    w10 = sum(1 for r in ret10 if r > 0) / n * 100
    w20 = sum(1 for r in ret20 if r > 0) / n * 100
    std5 = math.sqrt(sum((x - a5/100)**2 for x in ret5) / n) if n > 1 else 1
    sp5 = (a5 / 100) / std5 * math.sqrt(252 / 5) if std5 > 0 else 0
    std10 = math.sqrt(sum((x - a10/100)**2 for x in ret10) / n) if n > 1 else 1
    sp10 = (a10 / 100) / std10 * math.sqrt(252 / 10) if std10 > 0 else 0
    dd5 = min(0, min(ret5)) * 100
    
    return {
        "label": label, "signal_count": n,
        "win_rate_5d": round(w5, 2), "win_rate_10d": round(w10, 2), "win_rate_20d": round(w20, 2),
        "avg_ret_5d": round(a5, 4), "avg_ret_10d": round(a10, 4), "avg_ret_20d": round(a20, 4),
        "sharpe_5d": round(sp5, 3), "sharpe_10d": round(sp10, 3),
        "max_drawdown_5d": round(dd5, 2), "total_return_5d": round(sum(ret5) * 100, 2)
    }

def get_all_trade_dates():
    q = f"""SELECT DISTINCT trade_date FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
    WHERE trade_date >= '{DT_START}' AND trade_date <= '{DT_END}' ORDER BY trade_date"""
    return [r['trade_date'] for r in sql(q)]

def run_backtest(label, where_clause, trade_dates):
    all_signals = []
    batch_size = 80
    for i in range(0, len(trade_dates), batch_size):
        batch = trade_dates[i:i+batch_size]
        dq = ",".join(f"'{d}'" for d in batch)
        q = f"""SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close, sd.open,
               db.volume_ratio, db.circ_mv, db.turnover_rate, db.pe
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
        JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
          ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
        WHERE sd.trade_date IN ({dq}) AND {where_clause} AND sd.close > 0 AND sd.pre_close > 0"""
        r = sql(q)
        all_signals.extend(r)
        if len(all_signals) >= 20000:
            break
    
    seen = set(); unique = []
    for s in all_signals:
        k = (s['ts_code'], s['trade_date'])
        if k not in seen:
            seen.add(k); unique.append(s)
    
    codes = list(set(s['ts_code'] for s in unique))
    results = []
    for code_batch in [codes[i:i+100] for i in range(0, len(codes), 100)]:
        cq = ",".join(f"'{c}'" for c in code_batch)
        q_px = f"""SELECT ts_code, trade_date, close,
               leadInFrame(close, 5) OVER w AS c5,
               leadInFrame(close, 10) OVER w AS c10,
               leadInFrame(close, 20) OVER w AS c20
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
        WHERE ts_code IN ({cq}) AND trade_date >= '{DT_START}' AND trade_date <= '2026-06-15'
        WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date
                     ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ORDER BY ts_code, trade_date"""
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
                        results.append({'code': s['ts_code'], 'date': s['trade_date'], 'r5': r5, 'r10': r10, 'r20': r20})
    
    return compute_metrics(results, label)


def main():
    print("=" * 60)
    print("T8: 量价形态 Iter 13 — Round 3")
    print("=" * 60)
    
    all_dates = get_all_trade_dates()
    print(f"Trading days: {len(all_dates)}")
    
    EXCLUDE = "sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%' AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'"
    
    # ========================================================================
    # Strategy: Build on the winning formula — 缩量回调支撑反弹
    # Core: low/pre_close<=0.96 + VR>=1.5 + close>open + CM<=30亿 + TR 0.5-5%
    # Try variations to get more signals with high WR
    # ========================================================================
    
    # V1: Original (baseline)
    V1 = f"""sd.pct_chg >= 1.5 AND sd.pct_chg <= 7.0
    AND sd.low / sd.pre_close <= 0.96
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 0.5 AND db.turnover_rate <= 5.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND sd.close > sd.open
    AND {EXCLUDE}"""
    
    # V2: Relax CM to 50亿 (more signals)
    V2 = f"""sd.pct_chg >= 1.5 AND sd.pct_chg <= 7.0
    AND sd.low / sd.pre_close <= 0.96
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 500000
    AND db.turnover_rate >= 0.5 AND db.turnover_rate <= 5.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND sd.close > sd.open
    AND {EXCLUDE}"""
    
    # V3: Deeper drop (low/pre<=0.94) + CM<=30亿
    V3 = f"""sd.pct_chg >= 1.0 AND sd.pct_chg <= 7.0
    AND sd.low / sd.pre_close <= 0.94
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 0.5 AND db.turnover_rate <= 5.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND sd.close > sd.open
    AND {EXCLUDE}"""
    
    # V4: Deeper drop + higher VR
    V4 = f"""sd.pct_chg >= 1.0 AND sd.pct_chg <= 7.0
    AND sd.low / sd.pre_close <= 0.94
    AND db.volume_ratio >= 1.8
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 0.5 AND db.turnover_rate <= 5.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND sd.close > sd.open
    AND {EXCLUDE}"""
    
    # V5: Very deep drop + micro cap (<=20亿)
    V5 = f"""sd.pct_chg >= 0.5 AND sd.pct_chg <= 7.0
    AND sd.low / sd.pre_close <= 0.93
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 200000
    AND db.turnover_rate >= 0.5 AND db.turnover_rate <= 5.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND sd.close > sd.open
    AND {EXCLUDE}"""
    
    # V6: 尾盘拉升+筹码锁定 variations (WR5=59%, R5=1.82%, N=1020)
    # Try: lower turnover (more locked), smaller cap
    V6 = f"""sd.close / sd.high >= 0.97
    AND sd.pct_chg >= 2.0 AND sd.pct_chg <= 6.0
    AND db.volume_ratio >= 1.3
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 0.3 AND db.turnover_rate <= 1.5
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND {EXCLUDE}"""
    
    # V7: 尾盘拉升 + 更低换手 (<1%) + 小盘
    V7 = f"""sd.close / sd.high >= 0.97
    AND sd.pct_chg >= 2.0 AND sd.pct_chg <= 6.0
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 0.3 AND db.turnover_rate <= 1.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND {EXCLUDE}"""
    
    # V8: 放量阳线+低PE小盘 variations (WR5=55.7%, R5=1.17%, N=309)
    # Try: lower PE, smaller cap, higher VR
    V8 = f"""sd.close > sd.open
    AND sd.pct_chg >= 2.0 AND sd.pct_chg <= 7.0
    AND db.volume_ratio >= 1.8
    AND db.pe > 0 AND db.pe <= 20
    AND db.circ_mv <= 300000
    AND db.turnover_rate >= 1.0 AND db.turnover_rate <= 4.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND {EXCLUDE}"""
    
    # V9: New combo — 缩量阴线次日放量阳线（量价背离反转）
    # Requires: previous day was down with low volume, today is up with high volume
    # We can't do "previous day" easily in single-row SQL, so approximate:
    # pct_chg>=2% + VR>=2.0 + close>open + prev_close>open (yesterday was red-ish)
    # Better approach: just look for volume surge after a gap down
    V9 = f"""sd.pct_chg >= 2.0 AND sd.pct_chg <= 7.0
    AND sd.open < sd.pre_close * 0.98
    AND sd.close > sd.open * 1.02
    AND db.volume_ratio >= 2.0
    AND db.circ_mv <= 400000
    AND db.turnover_rate >= 1.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND {EXCLUDE}"""
    
    # V10: 涨停打开回封型 (limit-up opened then closed again)
    # pct_chg >= 9% + high = limit up price + close < high (opened) + VR>=2.0
    # Approximate: pct_chg 8-9.5% + (high-close)/pre_close >= 2% + VR>=2 + CM<=50亿
    V10 = f"""sd.pct_chg >= 8.0 AND sd.pct_chg <= 9.5
    AND (sd.high - sd.close) / sd.pre_close * 100 >= 2.0
    AND db.volume_ratio >= 2.0
    AND db.circ_mv <= 500000
    AND db.turnover_rate >= 2.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND {EXCLUDE}"""
    
    configs = [
        ("V1: 缩量回调(原)", V1),
        ("V2: 缩量回调(CM50亿)", V2),
        ("V3: 缩量回调(深跌94%)", V3),
        ("V4: 缩量回调(深跌+高VR)", V4),
        ("V5: 缩量回调(微盘深跌)", V5),
        ("V6: 尾盘拉升(TR<=1.5%)", V6),
        ("V7: 尾盘拉升(TR<=1%)", V7),
        ("V8: 放量阳线(PE<=20)", V8),
        ("V9: 低开高走放量", V9),
        ("V10: 涨停打开回封", V10),
    ]
    
    all_results = []
    for name, where in configs:
        print(f"\n>>> Testing: {name}")
        r = run_backtest(f"T8-{name}", where, all_dates)
        all_results.append(r)
        n = r.get('signal_count', 0)
        wr5 = r.get('win_rate_5d', 0)
        ret5 = r.get('avg_ret_5d', 0)
        sp5 = r.get('sharpe_5d', 0)
        status = "✅ PASS" if wr5 >= 55 and ret5 >= 2.0 and n >= 100 else "❌"
        print(f"  → {status} N={n}, WR5={wr5}%, R5={ret5}%, Sharpe5={sp5}")
    
    # Summary
    print(f"\n\n{'='*80}")
    print(f"T8 量价形态 Iter 13 Round 3 — SUMMARY")
    print(f"{'='*80}")
    print(f"{'信号':<25} {'N':>6} {'WR5%':>7} {'R5%':>7} {'Sharpe5':>8} {'WR10%':>7} {'R10%':>7}")
    print(f"{'-'*80}")
    
    passed = []
    for r in all_results:
        n = r.get('signal_count', 0)
        wr5 = r.get('win_rate_5d', 0)
        ret5 = r.get('avg_ret_5d', 0)
        sp5 = r.get('sharpe_5d', 0)
        wr10 = r.get('win_rate_10d', 0)
        ret10 = r.get('avg_ret_10d', 0)
        short = r.get('label', '?').replace('T8-', '')
        print(f"{short:<25} {n:>6} {wr5:>6.1f}% {ret5:>6.2f}% {sp5:>8.3f} {wr10:>6.1f}% {ret10:>6.2f}%")
        if wr5 >= 55 and ret5 >= 2.0 and n >= 100:
            passed.append(r['label'])
    
    print(f"\nPASS RATE: {len(passed)}/{len(all_results)}")
    if passed:
        print("PASSED:")
        for p in passed:
            print(f"  ✅ {p}")
    
    # Save combined results
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_13/t8_iter13_round3_results.json"
    with open(output_path, 'w') as f:
        json.dump({
            "iteration": "13_round3", "type": "T8_量价形态_Round3",
            "date_range": {"start": DT_START, "end": DT_END},
            "results": all_results, "passed": passed,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to: {output_path}")

if __name__ == "__main__":
    main()
