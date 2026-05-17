#!/usr/bin/env python3
"""
T9 Cross-Validation (Iter 32) — v4: argMax dedup + toInt64
Runs 15 cross-discipline combinations using ClickHouse.
"""
import subprocess, json, math, time

END_DATE = "2026-05-13"
START_DATE = "2020-01-01"

CH_CMD = ["docker", "exec", "-i", "tushare_db-clickhouse-1", "clickhouse-client", "--format", "JSONEachRow"]

def ch_query(sql):
    proc = subprocess.run(CH_CMD, input=sql, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        err = proc.stderr.strip()[:400] if proc.stderr else "no stderr"
        raise RuntimeError(f"CH query failed (exit={proc.returncode}): {err}")
    return [json.loads(l) for l in proc.stdout.strip().split('\n') if l.strip()]


BASE_CTE = """WITH
daily_dedup AS (
    SELECT ts_code, trade_date,
           argMax(close, _version) AS c,
           argMax(pct_chg, _version) AS p,
           argMax(open, _version) AS o,
           argMax(pre_close, _version) AS pc,
           argMax(high, _version) AS h,
           argMax(low, _version) AS l
    FROM tushare.tushare_stock_daily
    WHERE trade_date >= '{START}' AND trade_date <= '{END}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
    GROUP BY ts_code, trade_date
),
b AS (
    SELECT ts_code, trade_date,
           argMax(volume_ratio, _version) AS vr,
           argMax(circ_mv, _version) AS cmv,
           argMax(pb, _version) AS pb,
           argMax(dv_ttm, _version) AS dv_ttm
    FROM tushare.tushare_daily_basic
    WHERE trade_date >= '{START}'
    GROUP BY ts_code, trade_date
),
mf AS (
    SELECT ts_code, trade_date,
           argMax(sell_sm_amount, _version) AS sm_s,
           argMax(buy_sm_amount, _version) AS sm_b,
           argMax(buy_lg_amount, _version) AS lg_b,
           argMax(sell_lg_amount, _version) AS lg_s,
           argMax(buy_elg_amount, _version) AS elg_b,
           argMax(sell_elg_amount, _version) AS elg_s,
           argMax(buy_md_amount, _version) AS md_b,
           argMax(sell_md_amount, _version) AS md_s
    FROM tushare.tushare_moneyflow
    WHERE trade_date >= '{START}'
    GROUP BY ts_code, trade_date
),
spx1 AS (SELECT trade_date, argMax(pct_chg, _version) AS pct_chg FROM tushare.tushare_index_global WHERE ts_code='SPX' AND trade_date >= '{START}' GROUP BY trade_date),
spx2 AS (SELECT trade_date, argMax(pct_chg, _version) AS pct_chg FROM tushare.tushare_index_global WHERE ts_code='SPX' AND trade_date >= '{START}' GROUP BY trade_date),
hs300 AS (SELECT trade_date, argMax(pct_chg, _version) AS pct_chg FROM tushare.tushare_index_daily WHERE ts_code='000300.SH' AND trade_date >= '{START}' GROUP BY trade_date),
li AS (
    SELECT trade_date, ts_code, argMax(industry, _version) AS ind,
           COUNT(*) OVER (PARTITION BY trade_date, argMax(industry, _version)) AS ind_cnt
    FROM tushare.tushare_limit_list_d
    WHERE trade_date >= '{START}'
    GROUP BY trade_date, ts_code
),
daily_rn AS (
    SELECT *, toInt64(ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date)) AS rn
    FROM daily_dedup
)
SELECT d.ts_code, d.trade_date, d.c AS close, d.p AS pct_chg,
       round((n5.c / d.c - 1) * 100, 2) AS r5,
       round((n10.c / d.c - 1) * 100, 2) AS r10,
       round((n20.c / d.c - 1) * 100, 2) AS r20,
       pp1.p AS p1_chg, pp2.p AS p2_chg, pp3.p AS p3_chg,
       b.vr, b.cmv, b.pb, b.dv_ttm,
       mf.sm_s, mf.sm_b, mf.lg_b, mf.lg_s, mf.elg_b, mf.elg_s, mf.md_b, mf.md_s,
       spx1.pct_chg AS spx_pp, spx2.pct_chg AS spx_pp2,
       hs300.pct_chg AS hs300_p,
       li.ind_cnt,
       round((d.h - d.l) / d.pc * 100, 2) AS amp
FROM daily_rn d
LEFT JOIN daily_rn pp1 ON d.ts_code = pp1.ts_code AND d.rn = pp1.rn + 1
LEFT JOIN daily_rn pp2 ON d.ts_code = pp2.ts_code AND d.rn = pp2.rn + 2
LEFT JOIN daily_rn pp3 ON d.ts_code = pp3.ts_code AND d.rn = pp3.rn + 3
LEFT JOIN daily_rn n5 ON d.ts_code = n5.ts_code AND d.rn = n5.rn - 5
LEFT JOIN daily_rn n10 ON d.ts_code = n10.ts_code AND d.rn = n10.rn - 10
LEFT JOIN daily_rn n20 ON d.ts_code = n20.ts_code AND d.rn = n20.rn - 20
INNER JOIN b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
INNER JOIN mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date
LEFT JOIN spx1 ON spx1.trade_date = addDays(d.trade_date, -1)
LEFT JOIN spx2 ON spx2.trade_date = addDays(d.trade_date, -2)
LEFT JOIN hs300 ON hs300.trade_date = d.trade_date
LEFT JOIN li ON d.ts_code = li.ts_code AND d.trade_date = li.trade_date
WHERE n5.c IS NOT NULL AND n10.c IS NOT NULL AND n20.c IS NOT NULL
  AND d.c > 0
  AND {WHERE_CLAUSE}
"""

COMBOS = [
    # X01: T3三连跌(-2%) + SPX连续2日涨
    ("X01", "T3三连跌(-2%)+SPX连2涨+散户+大单+CM30亿",
     "d.p >= 1 AND d.p < 11 AND pp1.p <= -2 AND pp2.p <= -2 AND pp3.p <= -2\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND spx1.pct_chg > 0 AND spx2.pct_chg > 0"),
    
    # X02: T3三连跌+中单逆势+T4三重资金+SPX
    ("X02", "T3三连跌+中单逆势+T4三重资金+SPX",
     "d.p >= 1 AND d.p < 11 AND pp1.p <= -2 AND pp2.p <= -2 AND pp3.p <= -2\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s AND mf.md_b > mf.md_s\n"
     " AND spx1.pct_chg > 0"),
    
    # X03: T3三连跌+T5破净高息+SPX
    ("X03", "T3三连跌+T5破净高息+SPX",
     "d.p >= 1 AND d.p < 11 AND pp1.p <= -2 AND pp2.p <= -2 AND pp3.p <= -2\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND b.pb <= 1 AND b.pb > 0 AND b.dv_ttm >= 3\n"
     " AND spx1.pct_chg > 0"),
    
    # X04: T3三连跌-3%+T6行业涨停≥2+双宏观
    ("X04", "T3三连跌-3%+T6行业涨停≥2+双宏观",
     "d.p >= 1 AND d.p < 11 AND pp1.p <= -3 AND pp2.p <= -3 AND pp3.p <= -3\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.md_b > mf.md_s\n"
     " AND li.ind_cnt >= 2\n"
     " AND spx1.pct_chg > 0 AND hs300.pct_chg > 0"),
    
    # X05: T8双日恐慌+T4三重+T6双宏观+行业涨停
    ("X05", "T8双日恐慌+T4三重+T6双宏观+行业涨停",
     "d.p >= 1 AND d.p < 11 AND d.c > d.pc AND pp1.p <= -5 AND pp2.p <= -5\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s\n"
     " AND li.ind_cnt >= 2\n"
     " AND spx1.pct_chg > 0 AND hs300.pct_chg > 0"),
    
    # X06: T8双日恐慌+T5破净高息+SPX
    ("X06", "T8双日恐慌+T5破净高息+SPX",
     "d.p >= 1 AND d.p < 11 AND d.c > d.pc AND pp1.p <= -5 AND pp2.p <= -5\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND b.pb <= 1 AND b.pb > 0 AND b.dv_ttm >= 3\n"
     " AND spx1.pct_chg > 0"),
    
    # X07: T2底部放量+超大单+散户+SPX
    ("X07", "T2底部放量+超大单+散户+振幅6%+CM50亿+SPX",
     "d.p >= 3 AND d.p < 15 AND d.amp >= 6 AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.elg_b > mf.elg_s\n"
     " AND spx1.pct_chg > 0"),
    
    # X08: T3三连跌+T4三重+振幅8%+CM50亿+SPX
    ("X08", "T3三连跌+T4三重+振幅8%+CM50亿+SPX",
     "d.p >= 1 AND d.p < 11 AND pp1.p <= -2 AND pp2.p <= -2 AND pp3.p <= -2\n"
     " AND d.amp >= 8 AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s\n"
     " AND spx1.pct_chg > 0"),
    
    # X09: T8曙光初现≥3%+T4三重+SPX+CM30亿
    ("X09", "T8曙光初现≥3%+T4三重资金+SPX+CM30亿",
     "d.p >= 3 AND d.p < 15 AND d.c > d.pc AND pp1.p <= -5\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s\n"
     " AND spx1.pct_chg > 0"),
    
    # X10: T8双日恐慌+SPX连2涨+T6行业+HS300
    ("X10", "T8双日恐慌+SPX连2涨+T6行业+HS300",
     "d.p >= 1 AND d.p < 11 AND d.c > d.pc AND pp1.p <= -5 AND pp2.p <= -5\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND li.ind_cnt >= 2\n"
     " AND spx1.pct_chg > 0 AND spx2.pct_chg > 0 AND hs300.pct_chg > 0"),
    
    # X11: T3三连跌-3%+沪深300+中单+大单
    ("X11", "T3三连跌-3%+沪深300+中单+大单(纯微观)",
     "d.p >= 1 AND d.p < 11 AND pp1.p <= -3 AND pp2.p <= -3 AND pp3.p <= -3\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.md_b > mf.md_s AND mf.lg_b > mf.lg_s\n"
     " AND hs300.pct_chg > 0"),
    
    # X12: T5破净高息放量+T3三连跌
    ("X12", "T5破净高息放量(VR1.5)+T3三连跌(无SPX)",
     "d.p >= 1 AND d.p < 11 AND pp1.p <= -2 AND pp2.p <= -2 AND pp3.p <= -2\n"
     " AND d.amp >= 7 AND b.vr >= 1.5 AND b.cmv <= 500000\n"
     " AND mf.sm_s > mf.sm_b\n"
     " AND b.pb <= 1 AND b.pb > 0 AND b.dv_ttm >= 3"),
    
    # X13: T2底部放量+超大单+散户+CM100亿+SPX
    ("X13", "T2底部放量+超大单+散户+CM100亿+SPX",
     "d.p >= 3 AND d.p < 15 AND d.amp >= 6 AND b.vr >= 1.3 AND b.cmv <= 1000000\n"
     " AND mf.sm_s > mf.sm_b AND mf.elg_b > mf.elg_s\n"
     " AND spx1.pct_chg > 0"),
    
    # X14: T8双日恐慌+散户+大单(无SPX)+振幅8%+CM30亿
    ("X14", "T8双日恐慌+散户+大单(无SPX)+振幅8%+CM30亿",
     "d.p >= 1 AND d.p < 11 AND d.c > d.pc AND pp1.p <= -5 AND pp2.p <= -5\n"
     " AND d.amp >= 8 AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s"),
    
    # X15: T7 SPX涨+昨恐慌-5%+三连跌(-2%)+散户+大单
    ("X15", "T7 SPX涨+昨恐慌-5%+T3三连跌+散户+大单",
     "d.p >= 2 AND d.p < 11 AND pp1.p <= -5 AND pp2.p <= -2 AND pp3.p <= -2\n"
     " AND d.amp >= 7 AND b.vr >= 1.3 AND b.cmv <= 300000\n"
     " AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s\n"
     " AND spx1.pct_chg > 0"),
]


def run_one(combo_id, desc, wc):
    sql = BASE_CTE.format(START=START_DATE, END=END_DATE, WHERE_CLAUSE=wc)
    try:
        rows = ch_query(sql)
        n = len(rows)
    except Exception as e:
        return {"id": combo_id, "desc": desc, "N": 0, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                "Sharpe": 0, "P10": 0, "P90": 0, "status": f"ERROR: {str(e)[:90]}"}
    if n == 0:
        return {"id": combo_id, "desc": desc, "N": 0, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                "Sharpe": 0, "P10": 0, "P90": 0, "status": "FAIL(N=0)"}
    r5 = [float(r['r5']) for r in rows if r['r5'] is not None]
    r10 = [float(r['r10']) for r in rows if r['r10'] is not None]
    r20 = [float(r['r20']) for r in rows if r['r20'] is not None]
    if not r5:
        return {"id": combo_id, "desc": desc, "N": n, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                "Sharpe": 0, "P10": 0, "P90": 0, "status": "FAIL(no data)"}
    wins = sum(1 for v in r5 if v > 0)
    wr = round(wins/len(r5)*100, 2)
    ar5 = round(sum(r5)/len(r5), 2)
    ar10 = round(sum(r10)/len(r10), 2) if r10 else 0
    ar20 = round(sum(r20)/len(r20), 2) if r20 else 0
    mean_r = sum(r5)/len(r5)
    std_r = math.sqrt(sum((v-mean_r)**2 for v in r5)/len(r5)) if len(r5)>1 else 0
    sharpe = round(mean_r/std_r*math.sqrt(50) if std_r>0 else 0, 3)
    s5 = sorted(r5)
    p10 = round(s5[max(0,int(len(s5)*0.1))], 2)
    p90 = round(s5[min(len(s5)-1,int(len(s5)*0.9))], 2)
    status = "FAIL(N<200)" if n<200 else "PASS" if wr>=52 and ar5>=3 else "FAIL(threshold)"
    if n>=200 and wr>=85 and ar5>=10: status = "🏆ELITE"
    elif n>=200 and wr>=80 and ar5>=7: status = "🏆NEAR-ELITE"
    return {"id": combo_id, "desc": desc, "N": n, "WR": wr, "R5": ar5,
            "R10": ar10, "R20": ar20, "Sharpe": sharpe, "P10": p10, "P90": p90, "status": status}


def main():
    results = []
    for combo_id, desc, wc in COMBOS:
        print(f"\n[{combo_id}] {desc}...", flush=True)
        t0 = time.time()
        r = run_one(combo_id, desc, wc)
        elapsed = time.time()-t0
        print(f"  N={r['N']}, WR={r['WR']}%, R5={r['R5']}%, Sharpe={r['Sharpe']}, {r['status']} ({elapsed:.0f}s)")
        results.append(r)
    
    print("\n\n## Summary")
    hdr = f"{'ID':6s} | {'Desc':40s} | {'N':6s} | {'WR%':6s} | {'R5%':7s} | {'R10%':7s} | {'R20%':7s} | {'Sharpe':9s} | {'P10%':6s} | {'Status'}"
    print(hdr); print("-"*120)
    for r in sorted(results, key=lambda x: (x['WR']+abs(x['R5'])), reverse=True):
        print(f"{r['id']:6s} | {r['desc']:40s} | {r['N']:6d} | {r['WR']:5.2f}% | {r['R5']:6.2f}% | {r['R10']:6.2f}% | {r['R20']:6.2f}% | {r['Sharpe']:8.3f}  | {r['P10']:6.2f}% | {r['status']}")
    
    outpath = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_32/analysis_T9_cross.json'
    with open(outpath,'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {outpath}")
    np = sum(1 for r in results if 'PASS' in r['status'] or 'ELITE' in r['status'] or 'NEAR' in r['status'])
    ne = sum(1 for r in results if 'ELITE' in r['status'])
    nn = sum(1 for r in results if 'NEAR' in r['status'])
    print(f"Total: {len(results)} | PASS/ELITE/NEAR: {np} | ELITE: {ne} | NEAR-ELITE: {nn}")

if __name__ == '__main__':
    main()
