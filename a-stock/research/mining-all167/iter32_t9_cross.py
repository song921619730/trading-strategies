#!/usr/bin/env python3
"""
T9 Cross-Validation (Iter 32) — Multi-factor crossover backtest
Tests 15 cross-discipline combinations extracted from T2-T8 iter 32 best findings.
"""
import json, sys, math, time
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167')
from ch_helper import ch_query

END_DATE = '2026-05-13'
START_DATE = '2020-01-01'

# ── SQL template: backtest one combo ─────────────────────────────────────────
# Pattern:
#   WITH base AS (select all stocks with row_number)
#   SELECT filters on: pct_chg, prev pct_chg, high/low, vol ratio, moneyflow, etc.
#   JOIN daily_basic for VR/circ_mv
#   JOIN moneyflow for buy/sell amounts
#   JOIN SPX/HS300 for macro
#   JOIN forward closes for future returns
#   AGGREGATE WR, avg return, etc.

def run_backtest(combo_id, desc, extra_joins, where_clauses, extra_from=""):
    """Run backtest for one combo and return results dict."""
    
    sql = f"""
    WITH daily_rn AS (
        SELECT ts_code, trade_date, close AS c, pct_chg AS p, open AS o,
               pre_close AS pc, high AS h, low AS l, vol AS v, amount AS amt,
               toInt64(ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date)) AS rn
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= toDate('{START_DATE}') AND trade_date <= toDate('{END_DATE}')
          AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
          AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
    )
    SELECT d.ts_code, d.trade_date, d.c AS close, d.p AS pct_chg,
           round((n5.c / d.c - 1) * 100, 2) AS r5,
           round((n10.c / d.c - 1) * 100, 2) AS r10,
           round((n20.c / d.c - 1) * 100, 2) AS r20
    FROM daily_rn d
    LEFT JOIN daily_rn p1 ON d.ts_code = p1.ts_code AND d.rn = p1.rn + 1
    LEFT JOIN daily_rn p2 ON d.ts_code = p2.ts_code AND d.rn = p2.rn + 2
    LEFT JOIN daily_rn p3 ON d.ts_code = p3.ts_code AND d.rn = p3.rn + 3
    LEFT JOIN daily_rn n5 ON d.ts_code = n5.ts_code AND d.rn = n5.rn - 5
    LEFT JOIN daily_rn n10 ON d.ts_code = n10.ts_code AND d.rn = n10.rn - 10
    LEFT JOIN daily_rn n20 ON d.ts_code = n20.ts_code AND d.rn = n20.rn - 20
    INNER JOIN (SELECT ts_code, trade_date, volume_ratio AS vr, circ_mv AS cmv 
                FROM tushare.tushare_daily_basic FINAL) b
        ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
    INNER JOIN (SELECT ts_code, trade_date, 
                   sell_sm_amount AS sm_s, buy_sm_amount AS sm_b,
                   buy_lg_amount AS lg_b, sell_lg_amount AS lg_s,
                   buy_elg_amount AS elg_b, sell_elg_amount AS elg_s,
                   buy_md_amount AS md_b, sell_md_amount AS md_s
                FROM tushare.tushare_moneyflow FINAL) mf
        ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date
    LEFT JOIN (SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx
        ON spx.trade_date = addDays(d.trade_date, -1)
    LEFT JOIN (SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx_t0
        ON spx_t0.trade_date = d.trade_date
    LEFT JOIN (SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx_t2
        ON spx_t2.trade_date = addDays(d.trade_date, -2)
    LEFT JOIN (SELECT trade_date, pct_chg FROM tushare.tushare_index_daily FINAL WHERE ts_code='000300.SH') hs300
        ON hs300.trade_date = d.trade_date
    {extra_joins}
    WHERE d.p IS NOT NULL AND d.c > 0 AND p1.p IS NOT NULL
      -- Filter: positive forward return requires future data
      AND n5.c IS NOT NULL AND n10.c IS NOT NULL AND n20.c IS NOT NULL
      {where_clauses}
    """
    
    try:
        rows = ch_query(sql, timeout=300)
        n = len(rows)
        if n == 0:
            return {"id": combo_id, "desc": desc, "N": 0, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                    "Sharpe": 0, "P10": 0, "P90": 0, "status": "FAIL(N=0)"}
        
        r5_vals = [r['r5'] for r in rows if r['r5'] is not None]
        r10_vals = [r['r10'] for r in rows if r['r10'] is not None]
        r20_vals = [r['r20'] for r in rows if r['r20'] is not None]
        
        if not r5_vals:
            return {"id": combo_id, "desc": desc, "N": n, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                    "Sharpe": 0, "P10": 0, "P90": 0, "status": "FAIL(no data)"}
        
        wins = sum(1 for v in r5_vals if v > 0)
        wr = round(wins / len(r5_vals) * 100, 2) if r5_vals else 0
        avg_r5 = round(sum(r5_vals) / len(r5_vals), 2)
        avg_r10 = round(sum(r10_vals) / len(r10_vals), 2) if r10_vals else 0
        avg_r20 = round(sum(r20_vals) / len(r20_vals), 2) if r20_vals else 0
        
        # Sharpe (annualized approx): avg_r5 / std * sqrt(250/5)
        mean_r = sum(r5_vals) / len(r5_vals)
        std_r = math.sqrt(sum((v - mean_r)**2 for v in r5_vals) / len(r5_vals)) if len(r5_vals) > 1 else 0
        sharpe = round(mean_r / std_r * math.sqrt(50) if std_r > 0 else 0, 3)
        
        # Percentiles
        sorted_r5 = sorted(r5_vals)
        p10 = round(sorted_r5[max(0, int(len(sorted_r5)*0.1))], 2)
        p90 = round(sorted_r5[min(len(sorted_r5)-1, int(len(sorted_r5)*0.9))], 2)
        
        # Status determination
        status = "FAIL(N<200)" if n < 200 else "PASS" if wr >= 52 and avg_r5 >= 3 else "FAIL(threshold)"
        if n >= 200 and wr >= 85 and avg_r5 >= 10:
            status = "ELITE"
        elif n >= 200 and wr >= 80 and avg_r5 >= 7:
            status = "🏆NEAR-ELITE"
        
        return {"id": combo_id, "desc": desc, "N": n, "WR": wr, "R5": avg_r5, 
                "R10": avg_r10, "R20": avg_r20, "Sharpe": sharpe, "P10": p10, "P90": p90, 
                "status": status}
    except Exception as e:
        return {"id": combo_id, "desc": desc, "N": 0, "WR": 0, "R5": 0, "R10": 0, "R20": 0,
                "Sharpe": 0, "P10": 0, "P90": 0, "status": f"ERROR: {str(e)[:80]}"}


# ── Define 15 cross-combinations ────────────────────────────────────────────
# Each entry: (id, desc, extra_joins, where_clauses)

COMBOS = [
    # X01: T3三连跌(-2%) × T8 SPX连续2日涨 (恐慌+连续宏观)
    ("X01", "T3三连跌(-2%)+T8双日恐慌+SPX连2涨",
     "", """
      AND p3.pct_chg <= -2 AND p2.pct_chg <= -2 AND p1.pct_chg <= -2
      AND d.p >= 1 AND d.p < 11
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 300000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s
      AND spx.pct_chg > 0 AND spx_t2.pct_chg > 0
    """),
    
    # X02: T3 C1三连跌+中单逆势 × T4三重资金 (恐慌+双重资金确认)
    ("X02", "T3三连跌+中单逆势+T4三重资金+SPX",
     "", """
      AND p3.pct_chg <= -2 AND p2.pct_chg <= -2 AND p1.pct_chg <= -2
      AND d.p >= 1 AND d.p < 11
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 300000
      AND mf.sm_s > mf.sm_b
      AND mf.lg_b > mf.lg_s
      AND mf.elg_b > mf.elg_s
      AND mf.md_b > mf.md_s
      AND spx.pct_chg > 0
    """),
    
    # X03: T3三连跌(-2%) × T5 PB≤1+dv≥3% (恐慌+价值)
    ("X03", "T3三连跌+T5破净高息",
     "INNER JOIN (SELECT ts_code, trade_date, pb, dv_ttm FROM tushare.tushare_daily_basic FINAL) val ON d.ts_code = val.ts_code AND d.trade_date = val.trade_date",
     """
      AND p3.pct_chg <= -2 AND p2.pct_chg <= -2 AND p1.pct_chg <= -2
      AND d.p >= 1 AND d.p < 11
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 500000
      AND mf.sm_s > mf.sm_b
      AND mf.lg_b > mf.lg_s
      AND val.pb <= 1 AND val.pb > 0
      AND val.dv_ttm >= 3
      AND spx.pct_chg > 0
    """),
    
    # X04: T3三连跌×T6行业涨停≥2 (恐慌+板块热度)
    ("X04", "T3三连跌-3%+T6行业涨停≥2+双宏观",
     "INNER JOIN (SELECT trade_date, ts_code, COUNT(*) OVER (PARTITION BY trade_date, industry) AS ind_cnt FROM tushare.tushare_limit_list_d FINAL) li ON d.ts_code = li.ts_code AND d.trade_date = li.trade_date",
     """
      AND p3.pct_chg <= -3 AND p2.pct_chg <= -3 AND p1.pct_chg <= -3
      AND d.p >= 1 AND d.p < 11
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 300000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.md_b > mf.md_s
      AND li.ind_cnt >= 2
      AND spx.pct_chg > 0 AND hs300.pct_chg > 0
    """),
    
    # X05: T8双日恐慌(-5%) × T4三重资金 × T6双宏观 (最强恐慌+最强资金+双宏观)
    ("X05", "T8双日恐慌+T4三重+T6双宏观+行业涨停",
     "INNER JOIN (SELECT trade_date, ts_code, COUNT(*) OVER (PARTITION BY trade_date, industry) AS ind_cnt FROM tushare.tushare_limit_list_d FINAL) li ON d.ts_code = li.ts_code AND d.trade_date = li.trade_date",
     """
      AND p2.pct_chg <= -5 AND p1.pct_chg <= -5
      AND d.p >= 1 AND d.p < 11 AND d.c > d.pc
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 300000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s
      AND li.ind_cnt >= 2
      AND spx.pct_chg > 0 AND hs300.pct_chg > 0
    """),
    
    # X06: T8双日恐慌×T5破净高息 (量价+价值)
    ("X06", "T8双日恐慌+T5破净高息+SPX",
     "INNER JOIN (SELECT ts_code, trade_date, pb, dv_ttm FROM tushare.tushare_daily_basic FINAL) val ON d.ts_code = val.ts_code AND d.trade_date = val.trade_date",
     """
      AND p2.pct_chg <= -5 AND p1.pct_chg <= -5
      AND d.p >= 1 AND d.p < 11 AND d.c > d.pc
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 500000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s
      AND val.pb <= 1 AND val.pb > 0 AND val.dv_ttm >= 3
      AND spx.pct_chg > 0
    """),
    
    # X07: T2底部放量+超大单×T4三重资金 (动量+资金)
    ("X07", "T2底部放量+T4三重资金+SPX",
     "", """
      AND d.p >= 3 AND d.p < 15
      AND b.vr >= 1.3 AND b.cmv <= 500000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s
      AND ((d.h - d.l) / d.pc * 100) >= 6
      AND spx.pct_chg > 0
    """),
    
    # X08: T3三连跌×T4 C2-SPX(三重+振幅8%) (恐慌+强资金+SPX)
    ("X08", "T3三连跌+T4三重资金+振幅8%+CM50亿+SPX",
     "", """
      AND p3.pct_chg <= -2 AND p2.pct_chg <= -2 AND p1.pct_chg <= -2
      AND d.p >= 1 AND d.p < 11
      AND ((d.h - d.l) / d.pc * 100) >= 8
      AND b.vr >= 1.3 AND b.cmv <= 500000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s
      AND spx.pct_chg > 0
    """),
    
    # X09: T8 C3_Resurrect(恐慌+曙光初现≥3%) × T4三重资金
    ("X09", "T8曙光初现≥3%+T4三重资金+SPX+CM30亿",
     "", """
      AND p1.pct_chg <= -5
      AND d.p >= 3 AND d.p < 15 AND d.c > d.pc
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 300000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s AND mf.elg_b > mf.elg_s
      AND spx.pct_chg > 0
    """),
    
    # X10: T8双日恐慌×T6双宏观 (量价+双宏观)  
    ("X10", "T8双日恐慌+SPX连2涨+T6行业+HS300",
     "INNER JOIN (SELECT trade_date, ts_code, COUNT(*) OVER (PARTITION BY trade_date, industry) AS ind_cnt FROM tushare.tushare_limit_list_d FINAL) li ON d.ts_code = li.ts_code AND d.trade_date = li.trade_date",
     """
      AND p2.pct_chg <= -5 AND p1.pct_chg <= -5
      AND d.p >= 1 AND d.p < 11 AND d.c > d.pc
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 500000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s
      AND li.ind_cnt >= 2
      AND spx.pct_chg > 0 AND spx_t2.pct_chg > 0
      AND hs300.pct_chg > 0
    """),
    
    # X11: T3 C6(沪深300版+三连跌-3%) × T8双日恐慌
    ("X11", "T3三连跌-3%+沪深300+T8双日恐慌",
     "", """
      AND p3.pct_chg <= -3 AND p2.pct_chg <= -3 AND p1.pct_chg <= -3
      AND d.p >= 1 AND d.p < 11
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 300000
      AND mf.sm_s > mf.sm_b AND mf.md_b > mf.md_s AND mf.lg_b > mf.lg_s
      AND hs300.pct_chg > 0
    """),
    
    # X12: T5 C19(破净高息+恐慌放量) × T3三连跌 (价值+恐慌)
    ("X12", "T5破净高息放量+T3三连跌",
     "INNER JOIN (SELECT ts_code, trade_date, pb, dv_ttm FROM tushare.tushare_daily_basic FINAL) val ON d.ts_code = val.ts_code AND d.trade_date = val.trade_date",
     """
      AND p3.pct_chg <= -2 AND p2.pct_chg <= -2 AND p1.pct_chg <= -2
      AND d.p >= 1 AND d.p < 11
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.5 AND b.cmv <= 500000
      AND mf.sm_s > mf.sm_b
      AND val.pb <= 1 AND val.pb > 0 AND val.dv_ttm >= 3
    """),
    
    # X13: T2 C5(散户+超大单+底部+高振幅) × T4三重(SPX版) — 扩容版
    ("X13", "T2底部放量>超大单+散户割肉+T4三重+CM100亿+SPX",
     "", """
      AND d.p >= 3 AND d.p < 15
      AND ((d.h - d.l) / d.pc * 100) >= 6
      AND b.vr >= 1.3 AND b.cmv <= 1000000
      AND mf.sm_s > mf.sm_b AND mf.elg_b > mf.elg_s
      AND spx.pct_chg > 0
    """),
    
    # X14: T8量价(底20%过滤+双恐慌) × T4资金(散户+大单) × 无SPX
    ("X14", "T8双日恐慌+T4资金(无SPX)+底20%+振幅8%",
     "", """
      AND p2.pct_chg <= -5 AND p1.pct_chg <= -5
      AND d.p >= 1 AND d.p < 11 AND d.c > d.pc
      AND ((d.h - d.l) / d.pc * 100) >= 8
      AND b.vr >= 1.3 AND b.cmv <= 300000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s
    """),
    
    # X15: T7 C7(SPX涨+昨日恐慌-5%) × T3三连跌 (宏观交叉)
    ("X15", "T7 SPX涨+昨恐慌-5%+T3三连跌+散户+大单",
     "", """
      AND p3.pct_chg <= -2 AND p2.pct_chg <= -2 AND p1.pct_chg <= -2
      AND d.p >= 2 AND d.p < 11
      AND ((d.h - d.l) / d.pc * 100) >= 7
      AND b.vr >= 1.3 AND b.cmv <= 300000
      AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s
      AND spx.pct_chg > 0
    """),
]


def main():
    results = []
    for combo_id, desc, extra_joins, where_clauses in COMBOS:
        print(f"\n[{combo_id}] {desc}...", flush=True)
        t0 = time.time()
        r = run_backtest(combo_id, desc, extra_joins, where_clauses)
        elapsed = time.time() - t0
        print(f"  N={r['N']}, WR={r['WR']}%, R5={r['R5']}%, Sharpe={r['Sharpe']}, status={r['status']} ({elapsed:.0f}s)")
        results.append(r)
    
    # Summary table
    print("\n\n## Summary\n")
    print(f"{'ID':6s} | {'Desc':45s} | {'N':6s} | {'WR%':6s} | {'R5%':7s} | {'R10%':7s} | {'R20%':7s} | {'Sharpe':8s} | {'P10%':6s} | {'Status'}")
    print("-"*120)
    for r in sorted(results, key=lambda x: (x['WR'] + x['R5']), reverse=True):
        print(f"{r['id']:6s} | {r['desc']:45s} | {r['N']:6d} | {r['WR']:5.2f}% | {r['R5']:6.2f}% | {r['R10']:6.2f}% | {r['R20']:6.2f}% | {r['Sharpe']:8.3f} | {r['P10']:6.2f}% | {r['status']}")
    
    # Save JSON for report generation
    outpath = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_32/analysis_T9_cross.json'
    with open(outpath, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {outpath}")
    
    # PASS/ELITE stats
    n_pass = sum(1 for r in results if 'PASS' in r['status'] or 'ELITE' in r['status'] or 'NEAR' in r['status'])
    n_elite = sum(1 for r in results if 'ELITE' in r['status'])
    n_near = sum(1 for r in results if 'NEAR' in r['status'])
    print(f"\nTotal: {len(results)} | PASS: {n_pass} | ELITE: {n_elite} | NEAR-ELITE: {n_near}")


if __name__ == '__main__':
    main()
