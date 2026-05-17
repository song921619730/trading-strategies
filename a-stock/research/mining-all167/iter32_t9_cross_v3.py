#!/usr/bin/env python3
"""
T9 Cross-Validation (Iter 32) — uses docker exec clickhouse-client
V3: Fixed type issues with ROW_NUMBER() and JOINs
"""
import subprocess, json, sys, math, time, os

END_DATE = "2026-05-13"
START_DATE = "2020-01-01"

def ch_query(sql):
    """Execute SQL via docker exec clickhouse-client"""
    proc = subprocess.run(
        ["docker", "exec", "-i", "tushare_db-clickhouse-1", "clickhouse-client", "--format", "JSONEachRow"],
        input=sql, capture_output=True, text=True, timeout=600
    )
    if proc.returncode != 0:
        err = proc.stderr.strip()[:300] if proc.stderr else "no stderr"
        raise RuntimeError(f"CH query failed (exit={proc.returncode}): {err}")
    if not proc.stdout.strip():
        return []
    return [json.loads(line) for line in proc.stdout.strip().split('\n') if line.strip()]


# Base SQL: all factor fields pre-computed. WHERE_CLAUSE placeholder.
BASE_SQL = """
WITH daily_rn AS (
    SELECT ts_code, trade_date, close, pct_chg, open, pre_close, high, low,
           toInt64(ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date)) AS rn
    FROM tushare.tushare_stock_daily
    WHERE trade_date >= '{START}' AND trade_date <= '{END}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
)
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg,
       round((n5.close / d.close - 1) * 100, 2) AS r5,
       round((n10.close / d.close - 1) * 100, 2) AS r10,
       round((n20.close / d.close - 1) * 100, 2) AS r20,
       pp1.pct_chg AS p1_chg,
       pp2.pct_chg AS p2_chg,
       pp3.pct_chg AS p3_chg,
       b.vr, b.cmv, b.pb, b.dv_ttm,
       mf.sm_s, mf.sm_b, mf.lg_b, mf.lg_s, mf.elg_b, mf.elg_s, mf.md_b, mf.md_s,
       spx.pct_chg AS spx_pp,
       spx_t2.pct_chg AS spx_pp2,
       hs300.pct_chg AS hs300_p,
       li.ind_cnt,
       round((d.high - d.low) / d.pre_close * 100, 2) AS amp
FROM daily_rn d
LEFT JOIN daily_rn pp1 ON d.ts_code = pp1.ts_code AND d.rn = pp1.rn + 1
LEFT JOIN daily_rn pp2 ON d.ts_code = pp2.ts_code AND d.rn = pp2.rn + 2
LEFT JOIN daily_rn pp3 ON d.ts_code = pp3.ts_code AND d.rn = pp3.rn + 3
LEFT JOIN daily_rn n5 ON d.ts_code = n5.ts_code AND d.rn = n5.rn - 5
LEFT JOIN daily_rn n10 ON d.ts_code = n10.ts_code AND d.rn = n10.rn - 10
LEFT JOIN daily_rn n20 ON d.ts_code = n20.ts_code AND d.rn = n20.rn - 20
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio AS vr, circ_mv AS cmv, pb, dv_ttm
    FROM tushare.tushare_daily_basic
) b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
INNER JOIN (
    SELECT ts_code, trade_date,
           sell_sm_amount AS sm_s, buy_sm_amount AS sm_b,
           buy_lg_amount AS lg_b, sell_lg_amount AS lg_s,
           buy_elg_amount AS elg_b, sell_elg_amount AS elg_s,
           buy_md_amount AS md_b, sell_md_amount AS md_s
    FROM tushare.tushare_moneyflow
) mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date
LEFT JOIN (SELECT trade_date, pct_chg FROM tushare.tushare_index_global WHERE ts_code='SPX') spx
    ON spx.trade_date = addDays(d.trade_date, -1)
LEFT JOIN (SELECT trade_date, pct_chg FROM tushare.tushare_index_global WHERE ts_code='SPX') spx_t2
    ON spx_t2.trade_date = addDays(d.trade_date, -2)
LEFT JOIN (SELECT trade_date, pct_chg FROM tushare.tushare_index_daily WHERE ts_code='000300.SH') hs300
    ON hs300.trade_date = d.trade_date
LEFT JOIN (
    SELECT trade_date, ts_code, COUNT(*) OVER (PARTITION BY trade_date, industry) AS ind_cnt
    FROM tushare.tushare_limit_list_d
) li ON d.ts_code = li.ts_code AND d.trade_date = li.trade_date
WHERE n5.close IS NOT NULL AND n10.close IS NOT NULL AND n20.close IS NOT NULL
  AND d.close > 0 AND d.pct_chg IS NOT NULL
  AND {WHERE_CLAUSE}
"""


COMBOS = [
    # X01: T3三连跌(-2%) + SPX连续2日涨 (T3×T8×T7)
    ("X01", "T3三连跌(-2%)+SPX连2涨+散户+大单+CM30亿",
     "d.pct_chg >= 1 AND d.pct_chg < 11\n"
     " AND pp1.pct_chg <= -2 AND pp2.pct_chg <= -2 AND pp3.pct_chg <= -2\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND spx.pct_chg > 0 AND spx_t2.pct_chg > 0"),
    
    # X02: T3三连跌+中单逆势+T4三重资金+SPX
    ("X02", "T3三连跌+中单逆势+T4三重资金+SPX",
     "d.pct_chg >= 1 AND d.pct_chg < 11\n"
     " AND pp1.pct_chg <= -2 AND pp2.pct_chg <= -2 AND pp3.pct_chg <= -2\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s AND mf.md_b > mf.md_s\n"
     " AND spx.pct_chg > 0"),
    
    # X03: T3三连跌+T5破净高息+SPX
    ("X03", "T3三连跌+T5破净高息+SPX",
     "d.pct_chg >= 1 AND d.pct_chg < 11\n"
     " AND pp1.pct_chg <= -2 AND pp2.pct_chg <= -2 AND pp3.pct_chg <= -2\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND b.pb <= 1 AND b.pb > 0 AND b.dv_ttm >= 3\n"
     " AND spx.pct_chg > 0"),
    
    # X04: T3三连跌-3%+T6行业涨停≥2+双宏观
    ("X04", "T3三连跌-3%+T6行业涨停≥2+双宏观",
     "d.pct_chg >= 1 AND d.pct_chg < 11\n"
     " AND pp1.pct_chg <= -3 AND pp2.pct_chg <= -3 AND pp3.pct_chg <= -3\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.md_b > mf.md_s\n"
     " AND li.ind_cnt >= 2\n"
     " AND spx.pct_chg > 0 AND hs300.pct_chg > 0"),
    
    # X05: T8双日恐慌+T4三重+T6双宏观+行业涨停
    ("X05", "T8双日恐慌+T4三重+T6双宏观+行业涨停",
     "d.pct_chg >= 1 AND d.pct_chg < 11 AND d.close > d.pre_close\n"
     " AND pp1.pct_chg <= -5 AND pp2.pct_chg <= -5\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s\n"
     " AND li.ind_cnt >= 2\n"
     " AND spx.pct_chg > 0 AND hs300.pct_chg > 0"),
    
    # X06: T8双日恐慌+T5破净高息+SPX
    ("X06", "T8双日恐慌+T5破净高息+SPX",
     "d.pct_chg >= 1 AND d.pct_chg < 11 AND d.close > d.pre_close\n"
     " AND pp1.pct_chg <= -5 AND pp2.pct_chg <= -5\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND b.pb <= 1 AND b.pb > 0 AND b.dv_ttm >= 3\n"
     " AND spx.pct_chg > 0"),
    
    # X07: T2底部放量+超大单+散户+SPX
    ("X07", "T2底部放量+超大单+散户+振幅6%+CM50亿+SPX",
     "d.pct_chg >= 3 AND d.pct_chg < 15\n"
     " AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.elg_b > mf.elg_s\n"
     " AND d.amp >= 6\n"
     " AND spx.pct_chg > 0"),
    
    # X08: T3三连跌+T4三重+振幅8%+CM50亿+SPX
    ("X08", "T3三连跌+T4三重+振幅8%+CM50亿+SPX",
     "d.pct_chg >= 1 AND d.pct_chg < 11\n"
     " AND pp1.pct_chg <= -2 AND pp2.pct_chg <= -2 AND pp3.pct_chg <= -2\n"
     " AND d.amp >= 8\n"
     " AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s\n"
     " AND spx.pct_chg > 0"),
    
    # X09: T8曙光初现≥3%+T4三重+SPX+CM30亿
    ("X09", "T8曙光初现≥3%+T4三重资金+SPX+CM30亿",
     "d.pct_chg >= 3 AND d.pct_chg < 15 AND d.close > d.pre_close\n"
     " AND pp1.pct_chg <= -5\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s\n"
     " AND spx.pct_chg > 0"),
    
    # X10: T8双日恐慌+SPX连2涨+T6行业+HS300
    ("X10", "T8双日恐慌+SPX连2涨+T6行业+HS300",
     "d.pct_chg >= 1 AND d.pct_chg < 11 AND d.close > d.pre_close\n"
     " AND pp1.pct_chg <= -5 AND pp2.pct_chg <= -5\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND li.ind_cnt >= 2\n"
     " AND spx.pct_chg > 0 AND spx_t2.pct_chg > 0\n"
     " AND hs300.pct_chg > 0"),
    
    # X11: T3三连跌-3%+沪深300+中单+大单 (纯微观本土版)
    ("X11", "T3三连跌-3%+沪深300+中单+大单(纯微观)",
     "d.pct_chg >= 1 AND d.pct_chg < 11\n"
     " AND pp1.pct_chg <= -3 AND pp2.pct_chg <= -3 AND pp3.pct_chg <= -3\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.md_b > mf.md_s AND mf.lg_b > mf.lg_s\n"
     " AND hs300.pct_chg > 0"),
    
    # X12: T5破净高息放量+T3三连跌 (无SPX纯微观)
    ("X12", "T5破净高息放量(VR1.5)+T3三连跌(无SPX)",
     "d.pct_chg >= 1 AND d.pct_chg < 11\n"
     " AND pp1.pct_chg <= -2 AND pp2.pct_chg <= -2 AND pp3.pct_chg <= -2\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.5 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b\n"
     " AND b.pb <= 1 AND b.pb > 0 AND b.dv_ttm >= 3"),
    
    # X13: T2底部放量+超大单+散户+CM100亿+SPX (扩容版)
    ("X13", "T2底部放量+超大单+散户+CM100亿+SPX",
     "d.pct_chg >= 3 AND d.pct_chg < 15\n"
     " AND d.amp >= 6\n"
     " AND b.vr >= 1.3 AND b.cmv <= 1000000\n"
     " AND mf.sm_s > mf.sm_b AND mf.elg_b > mf.elg_s\n"
     " AND spx.pct_chg > 0"),
    
    # X14: T8双日恐慌+散户+大单(无SPX)+振幅8%+CM30亿
    ("X14", "T8双日恐慌+散户+大单(无SPX)+振幅8%+CM30亿",
     "d.pct_chg >= 1 AND d.pct_chg < 11 AND d.close > d.pre_close\n"
     " AND pp1.pct_chg <= -5 AND pp2.pct_chg <= -5\n"
     " AND d.amp >= 8\n"
     " AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s"),
    
    # X15: T7 SPX涨+昨恐慌-5%+T3三连跌(-2%)+散户+大单
    ("X15", "T7 SPX涨+昨恐慌-5%+T3三连跌+散户+大单",
     "d.pct_chg >= 2 AND d.pct_chg < 11\n"
     " AND pp1.pct_chg <= -5 AND pp2.pct_chg <= -2 AND pp3.pct_chg <= -2\n"
     " AND d.amp >= 7\n"
     " AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND spx.pct_chg > 0"),
]


def run_backtest(combo_id, desc, where_clause):
    sql = BASE_SQL.format(START=START_DATE, END=END_DATE, WHERE_CLAUSE=where_clause)
    try:
        rows = ch_query(sql)
        n = len(rows)
    except Exception as e:
        return {"id": combo_id, "desc": desc, "N": 0, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                "Sharpe": 0, "P10": 0, "P90": 0, "status": f"ERROR: {str(e)[:80]}"}
    
    if n == 0:
        return {"id": combo_id, "desc": desc, "N": 0, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                "Sharpe": 0, "P10": 0, "P90": 0, "status": "FAIL(N=0)"}
    
    r5_vals = [float(r['r5']) for r in rows if r['r5'] is not None]
    r10_vals = [float(r['r10']) for r in rows if r['r10'] is not None]
    r20_vals = [float(r['r20']) for r in rows if r['r20'] is not None]
    
    if not r5_vals:
        return {"id": combo_id, "desc": desc, "N": n, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                "Sharpe": 0, "P10": 0, "P90": 0, "status": "FAIL(no data)"}
    
    wins = sum(1 for v in r5_vals if v > 0)
    wr = round(wins / len(r5_vals) * 100, 2)
    avg_r5 = round(sum(r5_vals) / len(r5_vals), 2)
    avg_r10 = round(sum(r10_vals) / len(r10_vals), 2) if r10_vals else 0
    avg_r20 = round(sum(r20_vals) / len(r20_vals), 2) if r20_vals else 0
    
    mean_r = sum(r5_vals) / len(r5_vals)
    std_r = math.sqrt(sum((v - mean_r)**2 for v in r5_vals) / len(r5_vals)) if len(r5_vals) > 1 else 0
    sharpe = round(mean_r / std_r * math.sqrt(50) if std_r > 0 else 0, 3)
    
    sorted_r5 = sorted(r5_vals)
    p10 = round(sorted_r5[max(0, int(len(sorted_r5)*0.1))], 2)
    p90 = round(sorted_r5[min(len(sorted_r5)-1, int(len(sorted_r5)*0.9))], 2)
    
    status = "FAIL(N<200)" if n < 200 else "PASS" if wr >= 52 and avg_r5 >= 3 else "FAIL(threshold)"
    if n >= 200 and wr >= 85 and avg_r5 >= 10:
        status = "🏆ELITE"
    elif n >= 200 and wr >= 80 and avg_r5 >= 7:
        status = "🏆NEAR-ELITE"
    
    return {"id": combo_id, "desc": desc, "N": n, "WR": wr, "R5": avg_r5,
            "R10": avg_r10, "R20": avg_r20, "Sharpe": sharpe, "P10": p10, "P90": p90, "status": status}


def main():
    results = []
    for combo_id, desc, where_clause in COMBOS:
        print(f"\n[{combo_id}] {desc}...", flush=True)
        t0 = time.time()
        r = run_backtest(combo_id, desc, where_clause)
        elapsed = time.time() - t0
        print(f"  N={r['N']}, WR={r['WR']}%, R5={r['R5']}%, Sharpe={r['Sharpe']}, status={r['status']} ({elapsed:.0f}s)")
        results.append(r)
    
    print("\n\n## Summary")
    print(f"{'ID':6s} | {'Desc':42s} | {'N':6s} | {'WR%':6s} | {'R5%':7s} | {'R10%':7s} | {'R20%':7s} | {'Sharpe':9s} | {'P10%':6s} | {'Status'}")
    print("-"*125)
    for r in sorted(results, key=lambda x: (x['WR'] + abs(x['R5'])), reverse=True):
        print(f"{r['id']:6s} | {r['desc']:42s} | {r['N']:6d} | {r['WR']:5.2f}% | {r['R5']:6.2f}% | {r['R10']:6.2f}% | {r['R20']:6.2f}% | {r['Sharpe']:8.3f}  | {r['P10']:6.2f}% | {r['status']}")
    
    outpath = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_32/analysis_T9_cross.json'
    with open(outpath, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {outpath}")
    
    n_pass = sum(1 for r in results if 'PASS' in r['status'] or 'ELITE' in r['status'] or 'NEAR' in r['status'])
    n_elite = sum(1 for r in results if 'ELITE' in r['status'])
    n_near = sum(1 for r in results if 'NEAR' in r['status'])
    print(f"\nTotal: {len(results)} | PASS/ELITE/NEAR: {n_pass} | ELITE: {n_elite} | NEAR-ELITE: {n_near}")

if __name__ == '__main__':
    main()
