#!/usr/bin/env python3
"""
T2 (动量趋势) A股日线模式挖掘回测 v2
从统一参数空间中选5组参数组合（C1-C5），运行ClickHouse SQL回测
"""
import json
import subprocess
import sys
import re
from datetime import datetime

CH_QUERY = "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def run_sql(sql):
    """Run SQL via ch_query.py and return parsed JSON results."""
    # Clean up SQL
    sql_clean = re.sub(r'\n\s*', ' ', sql).strip()
    # Remove extra spaces
    sql_clean = re.sub(r'\s+', ' ', sql_clean)
    
    cmd = ["python3", CH_QUERY, "sql", sql_clean]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  [ERROR] rc={result.returncode}, stderr={result.stderr[:300]}", file=sys.stderr)
        return None
    try:
        data = json.loads(result.stdout)
        return data
    except json.JSONDecodeError as e:
        print(f"  [ERROR] JSON parse: {e}", file=sys.stderr)
        print(f"  Raw: {result.stdout[:200]}", file=sys.stderr)
        return None


def compute_metrics(rows):
    """Compute metrics from query results."""
    if not rows:
        return {"signal_count": 0, "wr_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}

    sig_count = len(rows)

    ret_1d_list, ret_3d_list, ret_5d_list = [], [], []
    ret_10d_list, ret_20d_list = [], []

    for r in rows:
        sig_close = r.get("sig_close")
        if not sig_close or sig_close == 0:
            continue

        c1d = r.get("c1d")
        c3d = r.get("c3d")
        c5d = r.get("c5d")
        c10d = r.get("c10d")
        c20d = r.get("c20d")

        if c1d and c1d != 0:
            ret_1d_list.append((c1d - sig_close) / sig_close)
        if c3d and c3d != 0:
            ret_3d_list.append((c3d - sig_close) / sig_close)
        if c5d and c5d != 0:
            ret_5d_list.append((c5d - sig_close) / sig_close)
        if c10d and c10d != 0:
            ret_10d_list.append((c10d - sig_close) / sig_close)
        if c20d and c20d != 0:
            ret_20d_list.append((c20d - sig_close) / sig_close)

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    def win_rate(lst):
        return sum(1 for v in lst if v > 0) / len(lst) * 100 if lst else 0

    def sharpe(lst):
        if len(lst) < 5:
            return 0
        mean_ret = sum(lst) / len(lst)
        var_ret = sum((v - mean_ret) ** 2 for v in lst) / (len(lst) - 1)
        std_ret = var_ret ** 0.5
        if std_ret == 0:
            return 0
        return (mean_ret / std_ret) * (50 ** 0.5)

    results = {
        "signal_count": sig_count,
        "wr_5d": round(win_rate(ret_5d_list), 2),
        "ret_5d": round(avg(ret_5d_list) * 100, 2),
        "ret_10d": round(avg(ret_10d_list) * 100, 2),
        "ret_20d": round(avg(ret_20d_list) * 100, 2),
        "sharpe_5d": round(sharpe(ret_5d_list), 4),
        "_detail": {
            "count_1d": len(ret_1d_list), "ret_1d": round(avg(ret_1d_list)*100, 2), "wr_1d": round(win_rate(ret_1d_list), 2),
            "count_3d": len(ret_3d_list), "ret_3d": round(avg(ret_3d_list)*100, 2), "wr_3d": round(win_rate(ret_3d_list), 2),
            "count_5d": len(ret_5d_list), "wr_5d_detail": round(win_rate(ret_5d_list), 2),
            "count_10d": len(ret_10d_list), "ret_10d_detail": round(avg(ret_10d_list)*100, 2), "wr_10d": round(win_rate(ret_10d_list), 2),
            "count_20d": len(ret_20d_list), "wr_20d": round(win_rate(ret_20d_list), 2),
        }
    }
    return results


# ========== Base SQL template ==========
BASE_INNER = """
SELECT ts_code, trade_date, close, pct_chg, vol, high, low, pre_close, open
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20200101' AND trade_date <= '20260511'
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_stock_basic FINAL WHERE name LIKE '%ST%')
""".strip()

def make_sql_simple(where_clauses, extra_cols="", limit=50000):
    """Build SQL for simple combos (C1, C2, C5)."""
    sql = f"""
    SELECT ts_code, trade_date, close AS sig_close,
           fc[1] AS c1d, fc[3] AS c3d, fc[5] AS c5d, fc[10] AS c10d, fc[20] AS c20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, vol,
            (close - min60) / nullIf(max60 - min60, 0) AS position_ratio,
            vol / nullIf(ma5_vol, 0) AS vol_ratio,
            (high - low) / nullIf(pre_close, 0) * 100 AS amplitude,
            groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc
            {extra_cols}
        FROM (
            SELECT ts_code, trade_date, close, pct_chg, vol, high, low, pre_close, open,
                min(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min60,
                max(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max60,
                avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5_vol
            FROM ({BASE_INNER}) AS a0
        ) AS a1
    ) AS a2
    INNER JOIN (SELECT ts_code, trade_date, volume_ratio, turnover_rate, circ_mv FROM tushare.tushare_daily_basic FINAL) AS b USING (ts_code, trade_date)
    WHERE position_ratio IS NOT NULL
      AND {where_clauses}
    LIMIT {limit}
    """
    return sql


# ========== Define Combos ==========

# C1: X04扩容
C1_SQL = make_sql_simple("""
    position_ratio <= 0.20
    AND pct_chg >= 3
    AND amplitude >= 5
    AND volume_ratio >= 1.3
    AND circ_mv <= 500000
    AND turnover_rate >= 1.0 AND turnover_rate <= 10.0
""")

# C2: 振幅测试  
C2_SQL = make_sql_simple("""
    position_ratio <= 0.10
    AND pct_chg >= 5
    AND amplitude >= 7
    AND volume_ratio >= 1.2
    AND circ_mv <= 300000
""")

# C3: 缩量后放量 (uses lagInFrame for prev vol check)
C3_SQL = """
SELECT ts_code, trade_date, close AS sig_close,
       fc[1] AS c1d, fc[3] AS c3d, fc[5] AS c5d, fc[10] AS c10d, fc[20] AS c20d
FROM (
    SELECT ts_code, trade_date, close, pct_chg, vol,
        (close - min60) / nullIf(max60 - min60, 0) AS position_ratio,
        vol / nullIf(ma5_vol, 0) AS vol_ratio,
        (high - low) / nullIf(pre_close, 0) * 100 AS amplitude,
        groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc,
        -- Previous 3 days vol and ma3_vol for shrink check
        lagInFrame(vol, 1) OVER w AS prev1_vol,
        lagInFrame(vol, 2) OVER w AS prev2_vol,
        lagInFrame(vol, 3) OVER w AS prev3_vol,
        lagInFrame(avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) OVER w AS prev1_ma3,
        lagInFrame(avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) OVER w AS prev2_ma3,
        lagInFrame(avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 3) OVER w AS prev3_ma3
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, vol, high, low, pre_close, open,
            min(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min60,
            max(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max60,
            avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5_vol
        FROM (""" + BASE_INNER + """) AS a0
    ) AS a1
    WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
) AS a2
INNER JOIN (SELECT ts_code, trade_date, volume_ratio, turnover_rate, circ_mv FROM tushare.tushare_daily_basic FINAL) AS b USING (ts_code, trade_date)
WHERE position_ratio IS NOT NULL
  AND position_ratio <= 0.20
  AND pct_chg >= 3
  AND amplitude >= 5
  AND volume_ratio >= 1.5
  AND circ_mv <= 500000
  AND prev1_vol IS NOT NULL AND prev2_vol IS NOT NULL AND prev3_vol IS NOT NULL
  AND prev1_vol < 0.8 * prev1_ma3
  AND prev2_vol < 0.8 * prev2_ma3
  AND prev3_vol < 0.8 * prev3_ma3
LIMIT 50000
"""

# C4: 趋势加速 (volume increasing 5 days)
C4_SQL = """
SELECT ts_code, trade_date, close AS sig_close,
       fc[1] AS c1d, fc[3] AS c3d, fc[5] AS c5d, fc[10] AS c10d, fc[20] AS c20d
FROM (
    SELECT ts_code, trade_date, close, pct_chg, vol,
        (close - min60) / nullIf(max60 - min60, 0) AS position_ratio,
        vol / nullIf(ma5_vol, 0) AS vol_ratio,
        (high - low) / nullIf(pre_close, 0) * 100 AS amplitude,
        groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc,
        -- Previous vol values for increasing check
        lagInFrame(vol, 1) OVER w AS prev1_vol,
        lagInFrame(vol, 2) OVER w AS prev2_vol,
        lagInFrame(vol, 3) OVER w AS prev3_vol,
        lagInFrame(vol, 4) OVER w AS prev4_vol
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, vol, high, low, pre_close, open,
            min(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min60,
            max(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max60,
            avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5_vol
        FROM (""" + BASE_INNER + """) AS a0
    ) AS a1
    WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
) AS a2
INNER JOIN (SELECT ts_code, trade_date, volume_ratio, turnover_rate, circ_mv FROM tushare.tushare_daily_basic FINAL) AS b USING (ts_code, trade_date)
WHERE position_ratio IS NOT NULL
  AND position_ratio <= 0.20
  AND pct_chg >= 2
  AND amplitude >= 5
  AND volume_ratio >= 1.0
  AND circ_mv >= 300000 AND circ_mv <= 1000000
  AND prev4_vol IS NOT NULL AND prev3_vol IS NOT NULL AND prev2_vol IS NOT NULL AND prev1_vol IS NOT NULL
  AND prev4_vol < prev3_vol AND prev3_vol < prev2_vol AND prev2_vol < prev1_vol AND prev1_vol < vol
LIMIT 50000
"""

# C5: 跳空支撑 (gap up)
C5_SQL = make_sql_simple("""
    position_ratio <= 0.15
    AND open > pre_close
    AND pct_chg >= 2
    AND amplitude >= 5
    AND volume_ratio >= 1.2
    AND circ_mv <= 500000
""")


combos = [
    {
        "name": "C1: X04扩容",
        "params": {
            "close_position": "底20%",
            "pct_chg_1d_min": 3,
            "amplitude_min": 5,
            "volume_ratio_min": 1.3,
            "market_cap_bucket": "CM≤50亿",
            "turnover": "1-10%"
        },
        "sql": C1_SQL,
        "expected": "WR≥52%, 5D≥3%, count≥200"
    },
    {
        "name": "C2: 振幅测试",
        "params": {
            "close_position": "底10%",
            "pct_chg_1d_min": 5,
            "amplitude_min": 7,
            "volume_ratio_min": 1.2,
            "market_cap_bucket": "CM≤30亿"
        },
        "sql": C2_SQL,
        "expected": "高振幅+强动量测试"
    },
    {
        "name": "C3: 缩量后放量",
        "params": {
            "close_position": "底20%",
            "pct_chg_1d_min": 3,
            "amplitude_min": 5,
            "volume_ratio_min": 1.5,
            "market_cap_bucket": "CM≤50亿",
            "condition": "前3日缩量(vol<ma3_vol*0.8)"
        },
        "sql": C3_SQL,
        "expected": "缩量整理后放量突破"
    },
    {
        "name": "C4: 趋势加速",
        "params": {
            "close_position": "底20%",
            "pct_chg_1d_min": 2,
            "amplitude_min": 5,
            "volume_ratio_min": 1.0,
            "market_cap_bucket": "CM 30-100亿",
            "condition": "持续放量5日"
        },
        "sql": C4_SQL,
        "expected": "持续放量趋势加速"
    },
    {
        "name": "C5: 跳空支撑",
        "params": {
            "close_position": "底15%",
            "pct_chg_1d_min": 2,
            "amplitude_min": 5,
            "volume_ratio_min": 1.2,
            "market_cap_bucket": "CM≤50亿",
            "condition": "向上跳空"
        },
        "sql": C5_SQL,
        "expected": "跳空缺口+放量上攻"
    }
]


def run_combo(combo):
    """Run a single combo: execute SQL, compute metrics, return results."""
    print(f"\n{'='*70}")
    print(f"  {combo['name']}")
    print(f"  Params: {json.dumps(combo['params'], ensure_ascii=False)}")
    print(f"{'='*70}")
    
    sql_raw = combo['sql']
    # Clean up
    sql_clean = re.sub(r'\n\s*', ' ', sql_raw).strip()
    sql_clean = re.sub(r'\s+', ' ', sql_clean)
    
    print(f"  SQL: {len(sql_clean)} chars")
    
    rows = run_sql(sql_clean)
    if rows is None:
        print(f"  [FAILED] SQL execution error")
        return {
            "name": combo["name"],
            "params": combo["params"],
            "sql": sql_clean[:400],
            "results": {"signal_count": 0, "wr_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
        }
    
    results = compute_metrics(rows)
    
    print(f"  [OK] Signals: {results['signal_count']}")
    print(f"       5D WR: {results['wr_5d']}%  |  Ret: {results['ret_5d']}%")
    print(f"       10D Ret: {results['ret_10d']}%  |  20D Ret: {results['ret_20d']}%")
    print(f"       5D Sharpe: {results['sharpe_5d']}")
    if results.get('_detail'):
        d = results['_detail']
        print(f"       Detail: 1D(wr={d['wr_1d']}%, r={d['ret_1d']}%) 3D(wr={d['wr_3d']}%, r={d['ret_3d']}%) "
              f"5D(wr={d['wr_5d_detail']}%, n={d['count_5d']}) 10D(wr={d['wr_10d']}%, r={d['ret_10d_detail']}%)")
    
    # Check success criteria
    crit = results['signal_count'] >= 200 and results['wr_5d'] >= 52 and results['ret_5d'] >= 3
    print(f"  [{'PASS' if crit else 'FAIL'}] Success criteria: count≥200({results['signal_count']≥200}) "
          f"WR≥52%({results['wr_5d']≥52}) 5D≥3%({results['ret_5d']≥3})")
    
    return {
        "name": combo["name"],
        "params": combo["params"],
        "sql": sql_clean[:400],
        "results": {k: v for k, v in results.items() if not k.startswith('_')}
    }


def main():
    print("=" * 70)
    print("  T2 动量趋势流派回测")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  数据基准: 2026-05-11 (最新交易日)")
    print("=" * 70)
    
    all_results = []
    for combo in combos:
        result = run_combo(combo)
        all_results.append(result)
        
    output = {
        "analyst": "T2",
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "data_benchmark": "2026-05-11",
        "combos": all_results
    }
    
    print("\n" + "=" * 70)
    print("  FINAL RESULTS SUMMARY")
    print("=" * 70)
    for r in all_results:
        res = r['results']
        print(f"  {r['name']:25s} | sig={res['signal_count']:5d} | WR5d={res['wr_5d']:6.2f}% | R5d={res['ret_5d']:6.2f}% | R10d={res['ret_10d']:7.2f}% | SR5d={res['sharpe_5d']:8.4f}")
    
    print("\n" + "=" * 70)
    print("  JSON OUTPUT")
    print("=" * 70)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    
    # Save
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/t2_backtest_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {output_path}")
    
    summary_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/kanban/a-stock-research/t2_backtest_summary.json"
    with open(summary_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
