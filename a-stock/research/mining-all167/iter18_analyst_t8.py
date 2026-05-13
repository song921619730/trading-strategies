#!/usr/bin/env python3
"""
Iteration 18 — Analyst: T8 低开尾拉形态深化
Tests 5 hypotheses (H1-H5) for parameter optimization of T8-C5 strategy.

FIX: Use single-query approach for signal extraction to avoid window function
boundary issues with batching.
"""

import json
import math
import sys
import os
import subprocess
from datetime import datetime

CH_QUERY = "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def sql(query):
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr[:300]}")
        return []
    if not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON ERROR: {e}, stdout={r.stdout[:200]}")
        return []


def compute_metrics(results, label):
    n = len(results)
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"  SIGNALS: {n}")

    if n < 5:
        print(f"  Too few signals (< 5)")
        return {"label": label, "signal_count": n, "win_rate_5d": 0,
                "avg_ret_5d": 0, "avg_ret_10d": 0, "avg_ret_20d": 0, "sharpe_5d": 0}

    ret5 = [r.get("r5", 0) or 0 for r in results]
    ret10 = [r.get("r10", 0) or 0 for r in results]
    ret20 = [r.get("r20", 0) or 0 for r in results]

    a5 = sum(ret5) / n * 100
    a10 = sum(ret10) / n * 100
    a20 = sum(ret20) / n * 100

    w5 = sum(1 for r in ret5 if r > 0) / n * 100

    std5 = math.sqrt(sum((x - a5/100)**2 for x in ret5) / n) if n > 1 else 1
    sp5 = (a5 / 100) / std5 * math.sqrt(252 / 5) if std5 > 0 else 0

    m = {"label": label, "signal_count": n, "win_rate_5d": round(w5, 2),
         "avg_ret_5d": round(a5, 4), "avg_ret_10d": round(a10, 4),
         "avg_ret_20d": round(a20, 4), "sharpe_5d": round(sp5, 3)}

    for k, v in m.items():
        if k != "label":
            print(f"  {k}: {v}")
    return m


def main():
    print("=" * 60)
    print("Iteration 18 — Analyst: T8 低开尾拉形态深化")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    latest = sql("SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL")
    dt_end = latest[0]['max(trade_date)'] if latest else "2026-05-12"
    dt_start = "2020-01-01"
    print(f"Range: {dt_start} ~ {dt_end}")

    EXCLUDE = "s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'"

    # ============================================================
    # Define 5 hypotheses as parameter dicts
    # ============================================================
    hypotheses = [
        {
            "name": "H1: 振幅放宽版(≥4%)",
            "params": {
                "amplitude_min": 4.0,  # instead of 5.0
                "circ_mv_max": 500000,
                "turnover_min": None,
                "turnover_max": None,
            }
        },
        {
            "name": "H2: 换手过滤版(0.5-10%)",
            "params": {
                "amplitude_min": 5.0,
                "circ_mv_max": 500000,
                "turnover_min": 0.5,
                "turnover_max": 10.0,
            }
        },
        {
            "name": "H3: 振幅放宽(≥4%)+换手过滤(0.5-10%)",
            "params": {
                "amplitude_min": 4.0,
                "circ_mv_max": 500000,
                "turnover_min": 0.5,
                "turnover_max": 10.0,
            }
        },
        {
            "name": "H4: 极致微盘版(CM≤15亿)",
            "params": {
                "amplitude_min": 5.0,
                "circ_mv_max": 150000,  # 15亿
                "turnover_min": None,
                "turnover_max": None,
            }
        },
        {
            "name": "H5: 极致微盘(CM≤15亿)+振幅放宽(≥4%)",
            "params": {
                "amplitude_min": 4.0,
                "circ_mv_max": 150000,
                "turnover_min": None,
                "turnover_max": None,
            }
        },
    ]

    final_results = []

    for h in hypotheses:
        name = h["name"]
        p = h["params"]
        print(f"\n{'='*60}")
        print(f"Processing: {name}")
        print(f"{'='*60}")

        # ================================================================
        # Step 1: Get signals using a single SQL query with close_position
        # computed via window function (correct across full date range)
        # ================================================================

        # Build filter conditions
        filters = []
        filters.append("s.open / s.pre_close < 1.0")  # 低开
        filters.append("s.close / s.high >= 0.95")    # 收近最高
        filters.append("db.volume_ratio >= 1.3")      # VR≥1.3
        filters.append(f"(s.high - s.low) / s.pre_close * 100 >= {p['amplitude_min']}")
        filters.append(f"db.circ_mv <= {p['circ_mv_max']}")
        filters.append("s.pct_chg >= 2.0")            # 涨≥2%
        if p.get('turnover_min') is not None:
            filters.append(f"db.turnover_rate >= {p['turnover_min']}")
        if p.get('turnover_max') is not None:
            filters.append(f"db.turnover_rate <= {p['turnover_max']}")
        filters.append(EXCLUDE)

        where_str = " AND ".join(filters)

        # Single query: get signals with close_position < 0.20
        q_sig = f"""
        SELECT ts_code, trade_date, close
        FROM (
            SELECT s.ts_code, s.trade_date, s.close,
                   MIN(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min20,
                   MAX(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max20
            FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
            JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv, turnover_rate
                  FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)) AS db
              ON s.ts_code = db.ts_code AND s.trade_date = db.trade_date
            WHERE s.trade_date >= '{dt_start}' AND s.trade_date <= '{dt_end}'
              AND s.close > 0 AND s.pre_close > 0
              AND {where_str}
        )
        WHERE (close - min20) / nullIf((max20 - min20), 0) < 0.20
        ORDER BY trade_date
        """

        signals = sql(q_sig)
        n_sig = len(signals)
        print(f"  Signals found: {n_sig}")

        if n_sig < 10:
            print(f"  Too few signals (< 10), skipping forward returns")
            final_results.append({
                "label": name, "signal_count": n_sig,
                "win_rate_5d": 0, "avg_ret_5d": 0,
                "avg_ret_10d": 0, "avg_ret_20d": 0, "sharpe_5d": 0
            })
            continue

        # ================================================================
        # Step 2: Compute forward returns for all signals
        # ================================================================
        # Deduplicate by (ts_code, trade_date)
        seen = set()
        unique_sigs = []
        for sig in signals:
            k = (sig['ts_code'], sig['trade_date'])
            if k not in seen:
                seen.add(k)
                unique_sigs.append(sig)

        print(f"  Unique signals: {len(unique_sigs)}")

        # Get all unique codes
        codes = list(set(s['ts_code'] for s in unique_sigs))
        results = []
        dt_end_ext = "2026-08-01"

        for cb in [codes[i:i+100] for i in range(0, len(codes), 100)]:
            cq = ",".join(f"'{c}'" for c in cb)

            q_px = f"""
            SELECT ts_code, trade_date, close,
                   leadInFrame(close, 5) OVER w AS c5,
                   leadInFrame(close, 10) OVER w AS c10,
                   leadInFrame(close, 20) OVER w AS c20
            FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
            WHERE ts_code IN ({cq})
              AND trade_date >= '{dt_start}' AND trade_date <= '{dt_end_ext}'
            WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date
                         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            ORDER BY ts_code, trade_date
            """
            px_rows = sql(q_px)
            px_map = {(r['ts_code'], r['trade_date']): r for r in px_rows}

            for s in unique_sigs:
                key = (s['ts_code'], s['trade_date'])
                if key in px_map:
                    px = px_map[key]
                    if px.get('close') and px['close'] > 0:
                        r5 = (px['c5'] / px['close'] - 1) if px.get('c5') and px['c5'] > 0 else None
                        r10 = (px['c10'] / px['close'] - 1) if px.get('c10') and px['c10'] > 0 else None
                        r20 = (px['c20'] / px['close'] - 1) if px.get('c20') and px['c20'] > 0 else None
                        if r5 is not None:
                            results.append({
                                'code': s['ts_code'], 'date': s['trade_date'],
                                'r5': r5, 'r10': r10, 'r20': r20
                            })

        print(f"  Signals with forward returns: {len(results)}")
        m = compute_metrics(results, name)
        final_results.append(m)

    # ============================================================
    # Summary & Output
    # ============================================================
    print(f"\n\n{'='*80}")
    print(f"SUMMARY: Iteration 18 — T8 低开尾拉形态深化")
    print(f"{'='*80}")
    print(f"{'组合':<35} {'N':<8} {'WR5':<8} {'R5%':<10} {'R10%':<10} {'R20%':<10} {'Sharpe5':<10}")
    print(f"{'-'*80}")
    for m in final_results:
        label = m['label'][:35]
        n = m['signal_count']
        wr = f"{m['win_rate_5d']:.1f}%" if m.get('win_rate_5d') else "N/A"
        r5 = f"{m['avg_ret_5d']:.2f}" if m.get('avg_ret_5d') else "N/A"
        r10 = f"{m['avg_ret_10d']:.2f}" if m.get('avg_ret_10d') else "N/A"
        r20 = f"{m['avg_ret_20d']:.2f}" if m.get('avg_ret_20d') else "N/A"
        sp = f"{m['sharpe_5d']:.3f}" if m.get('sharpe_5d') else "N/A"
        print(f"{label:<35} {n:<8} {wr:<8} {r5:<10} {r10:<10} {r20:<10} {sp:<10}")

    # Save to log file
    output_dir = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_18"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "02_analyst_T8_deepening.md")

    with open(output_file, "w") as f:
        f.write(f"# Iteration 18 — Analyst: T8 低开尾拉形态深化\n\n")
        f.write(f"> **执行时间**: {datetime.now().isoformat()}\n")
        f.write(f"> **数据范围**: {dt_start} ~ {dt_end}\n")
        f.write(f"> **基准策略**: T8-C5 (底20% + 低开 + 收近最高 close/high≥0.95 + VR≥1.3 + 振幅≥5% + CM≤50亿 + 涨≥2%)\n\n")

        f.write(f"## 测试结果汇总\n\n")
        f.write(f"| 组合 | N | WR5 | R5% | R10% | R20% | Sharpe5 |\n")
        f.write(f"|------|---:|----:|----:|-----:|-----:|-------:|\n")
        for m in final_results:
            label = m['label']
            n = m['signal_count']
            wr = f"{m['win_rate_5d']:.1f}" if m.get('win_rate_5d') else "N/A"
            r5 = f"{m['avg_ret_5d']:.2f}" if m.get('avg_ret_5d') else "N/A"
            r10 = f"{m['avg_ret_10d']:.2f}" if m.get('avg_ret_10d') else "N/A"
            r20 = f"{m['avg_ret_20d']:.2f}" if m.get('avg_ret_20d') else "N/A"
            sp = f"{m['sharpe_5d']:.3f}" if m.get('sharpe_5d') else "N/A"
            f.write(f"| {label} | {n} | {wr}% | {r5}% | {r10}% | {r20}% | {sp} |\n")

        f.write(f"\n## 各组详细结果\n\n")
        for m in final_results:
            f.write(f"### {m['label']}\n\n")
            f.write(f"| 指标 | 值 |\n")
            f.write(f"|------|---|\n")
            f.write(f"| 信号数 N | {m['signal_count']} |\n")
            f.write(f"| 5日胜率 WR5 | {m.get('win_rate_5d', 'N/A')}% |\n")
            f.write(f"| 5日平均收益 R5 | {m.get('avg_ret_5d', 'N/A')}% |\n")
            f.write(f"| 10日平均收益 R10 | {m.get('avg_ret_10d', 'N/A')}% |\n")
            f.write(f"| 20日平均收益 R20 | {m.get('avg_ret_20d', 'N/A')}% |\n")
            f.write(f"| Sharpe(5d) | {m.get('sharpe_5d', 'N/A')} |\n\n")

        # Find best
        valid = [m for m in final_results if m['signal_count'] >= 10]
        if valid:
            best_sharpe = max(valid, key=lambda x: x.get('sharpe_5d', 0))
            best_r5 = max(valid, key=lambda x: x.get('avg_ret_5d', 0))
            best_wr = max(valid, key=lambda x: x.get('win_rate_5d', 0))

            f.write(f"## 最佳组合与建议\n\n")
            f.write(f"### Sharpe 最优: {best_sharpe['label']}\n")
            f.write(f"- Sharpe5 = {best_sharpe['sharpe_5d']}, R5 = {best_sharpe['avg_ret_5d']}%, WR5 = {best_sharpe['win_rate_5d']}%\n\n")
            f.write(f"### R5 最优: {best_r5['label']}\n")
            f.write(f"- R5 = {best_r5['avg_ret_5d']}%, WR5 = {best_r5['win_rate_5d']}%, Sharpe5 = {best_r5['sharpe_5d']}\n\n")
            f.write(f"### WR5 最优: {best_wr['label']}\n")
            f.write(f"- WR5 = {best_wr['win_rate_5d']}%, R5 = {best_wr['avg_ret_5d']}%, Sharpe5 = {best_wr['sharpe_5d']}\n\n")

        f.write(f"## SQL 查询片段（可复现）\n\n")

        for h in hypotheses:
            p = h['params']
            filters = []
            filters.append("s.open / s.pre_close < 1.0  -- 低开")
            filters.append("s.close / s.high >= 0.95  -- 收近最高")
            filters.append("db.volume_ratio >= 1.3  -- 量比")
            filters.append(f"(s.high - s.low) / s.pre_close * 100 >= {p['amplitude_min']}  -- 振幅")
            filters.append(f"db.circ_mv <= {p['circ_mv_max']}  -- 流通市值(万)")
            filters.append("s.pct_chg >= 2.0  -- 涨幅")
            if p.get('turnover_min') is not None:
                filters.append(f"db.turnover_rate >= {p['turnover_min']}")
            if p.get('turnover_max') is not None:
                filters.append(f"db.turnover_rate <= {p['turnover_max']}")
            filters.append("s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'  -- 主板")

            f.write(f"### {h['name']}\n\n")
            f.write(f"```sql\n")
            f.write(f"SELECT ts_code, trade_date, close\n")
            f.write(f"FROM (\n")
            f.write(f"    SELECT s.ts_code, s.trade_date, s.close,\n")
            f.write(f"           MIN(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min20,\n")
            f.write(f"           MAX(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max20\n")
            f.write(f"    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s\n")
            f.write(f"    JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv, turnover_rate\n")
            f.write(f"          FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)) AS db\n")
            f.write(f"      ON s.ts_code = db.ts_code AND s.trade_date = db.trade_date\n")
            f.write(f"    WHERE s.trade_date >= '2020-01-01' AND s.trade_date <= '2026-05-12'\n")
            f.write(f"      AND s.close > 0 AND s.pre_close > 0\n")
            f.write(f"      AND {' AND '.join(filters)}\n")
            f.write(f")\n")
            f.write(f"WHERE (close - min20) / nullIf((max20 - min20), 0) < 0.20\n")
            f.write(f"ORDER BY trade_date\n")
            f.write(f"```\n\n")

    print(f"\nResults saved to: {output_file}")
    return final_results


if __name__ == "__main__":
    main()
