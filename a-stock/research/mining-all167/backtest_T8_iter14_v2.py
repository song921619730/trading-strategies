#!/usr/bin/env python3
"""
T8: 量价形态 回测 — Iter 14 v2
5组E-series信号组合，确保与Iter13和Iter14 D-series不重复
使用ClickHouse直连 + leadInFrame窗口函数高效计算前向收益
"""
import json
import subprocess
import math
import sys

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
DT_START = "2024-01-01"
DT_END = "2026-05-11"
OUTPUT_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_14"

EXCLUDE = "ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'"

def sql(query):
    """Execute SQL via ClickHouse direct query."""
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr[:300]}", file=sys.stderr)
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
        return {
            "combo": label, "signal_count": n,
            "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0,
            "avg_ret_5d": 0, "avg_ret_10d": 0, "avg_ret_20d": 0,
            "sharpe_5d": 0, "sharpe_10d": 0, "passed": False,
            "status": f"SKIP(<{n} signals)"
        }
    
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
    
    passed = w5 >= 52 and a5 >= 3 and n >= 200 and sp5 >= 0.5
    
    return {
        "combo": label,
        "signal_count": n,
        "win_rate_5d": round(w5, 2),
        "win_rate_10d": round(w10, 2),
        "win_rate_20d": round(w20, 2),
        "avg_ret_5d": round(a5, 4),
        "avg_ret_10d": round(a10, 4),
        "avg_ret_20d": round(a20, 4),
        "sharpe_5d": round(sp5, 3),
        "sharpe_10d": round(sp10, 3),
        "passed": passed,
        "status": "PASS" if passed else "FAIL"
    }

def run_backtest(combo_name, where_clause, desc):
    """Run backtest using ClickHouse leadInFrame for efficient forward return calculation."""
    print(f"\n{'='*60}")
    print(f"Running: {combo_name}")
    print(f"Desc: {desc}")
    print(f"{'='*60}")
    
    # Step 1: Get all signals in one query using the full date range
    # Use subquery wrapper for FINAL to be safe with JOIN
    q = f"""
    SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close, sd.open
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '{DT_START}' AND trade_date <= '{DT_END}') AS sd
    JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv, turnover_rate FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '{DT_START}' AND trade_date <= '{DT_END}') AS db
      ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
    WHERE {where_clause}
      AND {EXCLUDE}
      AND sd.close > 0 AND sd.pre_close > 0
    ORDER BY sd.trade_date, sd.ts_code
    """
    
    print("  Querying signals...")
    signals = sql(q)
    print(f"  Raw signals found: {len(signals)}")
    
    if len(signals) < 10:
        print(f"  Too few signals, skipping forward return calc")
        return compute_metrics([], combo_name)
    
    # Deduplicate
    seen = set()
    unique = []
    for s in signals:
        k = (s['ts_code'], s['trade_date'])
        if k not in seen:
            seen.add(k)
            unique.append(s)
    
    print(f"  Unique signals: {len(unique)}")
    
    # Step 2: Get forward prices using leadInFrame window function
    # Only query codes that appear in signals
    codes = list(set(s['ts_code'] for s in unique))
    print(f"  Unique codes: {len(codes)}")
    
    # Batch the code queries to avoid query length limits
    results = []
    batch_size = 200
    
    for i in range(0, len(codes), batch_size):
        batch_codes = codes[i:i+batch_size]
        cq = ",".join(f"'{c}'" for c in batch_codes)
        
        q_px = f"""
        SELECT ts_code, trade_date, close,
               leadInFrame(close, 5) OVER w AS c5,
               leadInFrame(close, 10) OVER w AS c10,
               leadInFrame(close, 20) OVER w AS c20
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL
              WHERE ts_code IN ({cq})
                AND trade_date >= '{DT_START}'
                AND trade_date <= '2026-06-30')
        WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date
                     ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ORDER BY ts_code, trade_date
        """
        
        px_rows = sql(q_px)
        px_map = {}
        for r in px_rows:
            px_map[(r['ts_code'], r['trade_date'])] = r
        
        # Match signals to forward returns
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
                            'r5': r5,
                            'r10': r10,
                            'r20': r20
                        })
        
        print(f"  Batch {i//batch_size + 1}/{(len(codes)+batch_size-1)//batch_size}: {len(results)} results so far")
    
    print(f"  Total results with forward returns: {len(results)}")
    return compute_metrics(results, combo_name)

def main():
    print("=" * 60)
    print("T8: 量价形态 回测 — Iter 14 v2 (E-series)")
    print(f"时间范围: {DT_START} ~ {DT_END}")
    print("=" * 60)
    
    # 5 new E-series combos designed to avoid recent_combos and D-series
    combos = [
        {
            "name": "T8-E1: 底部放量十字星+微盘",
            "desc": "底30%(20日)+十字星(实体<=振幅15%)+VR>=1.3+振幅>=5%+CM<=30亿+收阳",
            "where": """
                sd.close > sd.open
                AND (sd.high - sd.low) > 0
                AND abs(sd.close - sd.open) / (sd.high - sd.low) <= 0.15
                AND db.volume_ratio >= 1.3
                AND db.circ_mv <= 300000
                AND sd.pct_chg >= 0.5 AND sd.pct_chg <= 9.5
            """
        },
        {
            "name": "T8-E2: 波动挤压突破+放量",
            "desc": "前3日振幅<3%的挤压+当日振幅>=4%+VR>=2.0+涨幅>=2%+CM<=50亿+收阳",
            "where": """
                sd.pct_chg >= 2.0
                AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
                AND db.volume_ratio >= 2.0
                AND db.circ_mv <= 500000
                AND sd.close > sd.open
                AND sd.pct_chg <= 9.5
            """
        },
        {
            "name": "T8-E3: 长下影探底+中位反转",
            "desc": "中位+下影>=实体2倍+VR>=1.2+振幅>=6%+CM<=40亿+收阳",
            "where": """
                sd.close > sd.open
                AND (sd.close - sd.low) >= 2.0 * abs(sd.close - sd.open)
                AND (sd.high - sd.low) / sd.pre_close * 100 >= 6.0
                AND db.volume_ratio >= 1.2
                AND db.circ_mv <= 400000
                AND sd.pct_chg >= 1.0 AND sd.pct_chg <= 9.5
            """
        },
        {
            "name": "T8-E4: 跳空缺口+放量不回补",
            "desc": "向上跳空(open>前日high)+VR>=1.5+振幅>=5%+CM<=50亿+涨幅>=1%+收阳",
            "where": """
                sd.open > sd.pre_close * 1.01
                AND sd.pct_chg >= 1.0
                AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
                AND db.volume_ratio >= 1.5
                AND db.circ_mv <= 500000
                AND sd.close > sd.open
                AND sd.pct_chg <= 9.5
            """
        },
        {
            "name": "T8-E5: 尾盘抢筹线+低换手",
            "desc": "收盘/最高>=0.98(尾盘强势)+涨幅>=1.5%+VR>=1.0+换手0.5-3%+CM<=50亿",
            "where": """
                sd.close / sd.high >= 0.98
                AND sd.pct_chg >= 1.5
                AND db.volume_ratio >= 1.0
                AND db.turnover_rate >= 0.5 AND db.turnover_rate <= 3.0
                AND db.circ_mv <= 500000
                AND sd.pct_chg <= 9.5
            """
        },
    ]
    
    all_results = []
    for combo in combos:
        result = run_backtest(combo["name"], combo["where"].strip(), combo["desc"])
        result["params"] = combo["desc"]
        all_results.append(result)
    
    # Write results
    # JSON results
    json_path = f"{OUTPUT_DIR}/iter14_T8_E_results.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nJSON results written to: {json_path}")
    
    # Markdown report
    md_lines = [
        "# Iter14 T8: 量价形态流派挖掘 (E-series)",
        f"# Date: 2026-05-12",
        f"# Base date: 2026-05-11",
        f"# Combos tested: {len(combos)}",
        "",
    ]
    
    passed_count = 0
    best = None
    best_r5 = -999
    
    for r in all_results:
        md_lines.append(f"## {r['combo']}")
        md_lines.append(f"- 参数: {r.get('params', 'N/A')}")
        md_lines.append(f"- 信号数: {r['signal_count']}")
        md_lines.append(f"- 5D: WR={r['win_rate_5d']}%, R5={r['avg_ret_5d']}%, Sharpe={r['sharpe_5d']}")
        md_lines.append(f"- 10D: WR={r['win_rate_10d']}%, R10={r['avg_ret_10d']}%, Sharpe={r['sharpe_10d']}")
        md_lines.append(f"- 20D: WR={r['win_rate_20d']}%, R20={r['avg_ret_20d']}%")
        md_lines.append(f"- 状态: {'PASS' if r['passed'] else 'FAIL'}")
        md_lines.append("")
        
        if r['avg_ret_5d'] > best_r5:
            best_r5 = r['avg_ret_5d']
            best = r
        if r['passed']:
            passed_count += 1
    
    md_lines.append(f"## 汇总")
    md_lines.append(f"- 通过/总数: {passed_count}/{len(combos)}")
    if best:
        md_lines.append(f"- 最优: {best['combo']} (R5={best['avg_ret_5d']}%, WR={best['win_rate_5d']}%, N={best['signal_count']})")
    
    md_path = f"{OUTPUT_DIR}/iter14_T8_E_量价形态.md"
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))
    print(f"Markdown report written to: {md_path}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in all_results:
        status = "PASS" if r['passed'] else "FAIL"
        print(f"  {r['combo']}: N={r['signal_count']}, WR={r['win_rate_5d']}%, R5={r['avg_ret_5d']}%, Sharpe={r['sharpe_5d']} [{status}]")
    print(f"\nPassed: {passed_count}/{len(combos)}")
    if best:
        print(f"Best: {best['combo']} with R5={best['avg_ret_5d']}%")

if __name__ == "__main__":
    main()
