#!/usr/bin/env python3
"""
Iter16 Analyst: 量价形态 + 宏观过滤交叉（R5 全局纪录突破冲刺）
数据基准: 2026-05-12 | 回测范围: 2020-01-01 ~ 2026-05-12
"""
import json, subprocess, math, sys, os
from datetime import datetime

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
DT_START = "2020-01-01"
DT_END = "2026-05-12"
OUTPUT_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_16"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sql(query):
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr[:300]}", file=sys.stderr)
        return []
    if not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout)
    except Exception as e:
        print(f"  PARSE ERROR: {e}", file=sys.stderr)
        return []

def compute_metrics(results, label):
    n = len(results)
    if n < 10:
        return {"combo": label, "N": n, "WR_5d": 0, "R5": 0, "R10": 0, "R20": 0,
                "Sharpe": 0, "P10": 0, "pass": False, "status": "SKIP"}
    ret5 = [(r.get("r5", 0) or 0) for r in results]
    ret10 = [(r.get("r10", 0) or 0) for r in results]
    ret20 = [(r.get("r20", 0) or 0) for r in results]
    a5 = sum(ret5) / n
    a10 = sum(ret10) / n
    a20 = sum(ret20) / n
    w5 = sum(1 for r in ret5 if r > 0) / n * 100
    std5 = math.sqrt(sum((x/100 - a5/100)**2 for x in ret5) / n) if n > 1 else 1
    sp5 = (a5 / 100) / std5 * math.sqrt(252 / 5) if std5 > 0 else 0
    sorted_ret5 = sorted(ret5)
    p10_idx = max(0, int(n * 0.1) - 1)
    p10 = sorted_ret5[p10_idx] if n > 0 else 0
    passed = w5 >= 55 and a5 >= 5 and n >= 200
    return {
        "combo": label, "N": n,
        "WR_5d": round(w5, 2), "R5": round(a5, 2),
        "R10": round(a10, 2), "R20": round(a20, 2),
        "Sharpe": round(sp5, 3), "P10": round(p10, 2),
        "pass": passed, "status": "PASS" if passed else "FAIL"
    }

def get_spx_date_groups():
    q = """
    SELECT s.trade_date AS trade_date, spx_prev_ret, spx_prev2_ret
    FROM (
        SELECT trade_date,
               any(pct_chg) OVER (ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS spx_prev_ret,
               any(pct_chg) OVER (ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND 2 PRECEDING) AS spx_prev2_ret
        FROM tushare.tushare_index_global FINAL
        WHERE ts_code='SPX' AND trade_date IS NOT NULL
    ) spx
    INNER JOIN (
        SELECT DISTINCT trade_date FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-05-12' AND trade_date IS NOT NULL
    ) s ON spx.trade_date = s.trade_date
    WHERE spx_prev_ret IS NOT NULL AND s.trade_date IS NOT NULL
    ORDER BY s.trade_date
    """
    rows = sql(q)
    groups = {"none": None, "up": [], "neg": [], "up05": []}
    for r in rows:
        d = r.get("trade_date")
        if d is None:
            continue
        prev = r.get("spx_prev_ret") or 0
        prev2 = r.get("spx_prev2_ret") or 0
        if prev > 0: groups["up"].append(d)
        if prev > 0 and prev2 > 0: groups["neg"].append(d)
        if prev > 0.5: groups["up05"].append(d)
    print(f"  SPX前日上涨(>0%): {len(groups['up'])} 个交易日")
    print(f"  SPX连续2日上涨(NEG): {len(groups['neg'])} 个交易日")
    print(f"  SPX前日上涨(>0.5%): {len(groups['up05'])} 个交易日")
    # Debug: print first few dates
    if groups['up']:
        print(f"  Sample SPX>0 dates: {groups['up'][:3]}")
    return groups

def run_combo(combo_id, desc, where_conditions, spx_dates=None, label_suffix=""):
    """Run a single combo with the correct ClickHouse SQL pattern."""
    full_label = f"{combo_id}{label_suffix}"
    print(f"\n{'='*60}")
    print(f"Running: {full_label} — {desc}")
    print(f"{'='*60}")
    
    spx_filter = ""
    if spx_dates is not None:
        formatted_dates = ",".join(f"'{d}'" for d in spx_dates)
        # Use tuple syntax for ClickHouse - works with large constant lists
        spx_filter = f" AND trade_date IN ({formatted_dates})"
    
    # Use the pattern from successful t9_cross_combos.py:
    # 1. Subquery from FINAL table with s. alias for window functions
    # 2. Columns keep their original names (no re-alias)
    # 3. Use s. prefix in window functions
    # 4. Join daily_basic 
    # 5. Outer query filters on the nicely named CTE columns
    query = f"""
    WITH base_all AS (
        SELECT
            s.ts_code, s.trade_date,
            s.close, s.pct_chg, s.open, s.high, s.low, s.vol, s.pre_close,
            (s.high - s.low) / s.pre_close * 100 AS amplitude,
            b.volume_ratio, b.circ_mv, b.pe, b.pb, b.dv_ratio, b.turnover_rate,
            MIN(s.close) OVER w20 AS min_20d,
            MAX(s.close) OVER w20 AS max_20d,
            any(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS close_f5,
            any(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS close_f10,
            any(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_f20,
            lagInFrame(s.pct_chg) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev_pct,
            lagInFrame(s.open) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev_open,
            lagInFrame(s.high) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev_high
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '{DT_START}' AND trade_date <= '{DT_END}') AS s
        INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
            ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
        WHERE s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
          AND s.close > 0 AND s.pre_close > 0
        WINDOW w20 AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
    )
    SELECT
        round((close_f5 / close - 1) * 100, 2) AS r5,
        round((close_f10 / close - 1) * 100, 2) AS r10,
        round((close_f20 / close - 1) * 100, 2) AS r20
    FROM base_all
    WHERE close_f5 IS NOT NULL AND close_f5 > 0
      AND min_20d > 0 AND max_20d > min_20d
      AND (close - min_20d) / (max_20d - min_20d) <= 0.20
      {where_conditions}
      {spx_filter}
    """
    
    results = sql(query)
    metrics = compute_metrics(results, full_label)
    metrics["desc"] = desc
    metrics["spx_filter"] = label_suffix if label_suffix else "无SPX过滤"
    
    status = "✅ PASS" if metrics["pass"] else "❌ FAIL"
    print(f"  N={metrics['N']}, WR={metrics['WR_5d']:.1f}%, R5={metrics['R5']:.2f}%, "
          f"R10={metrics['R10']:.2f}%, R20={metrics['R20']:.2f}%, "
          f"Sharpe={metrics['Sharpe']:.3f}, P10={metrics['P10']:.2f}%  {status}")
    return metrics

def run_combo_all_spx(combo_id, desc, where_clause):
    """Run combo with 4 SPX variants."""
    results = []
    spx_variants = [
        (None, ""),
        ("up", " [SPX>0]"),
        ("neg", " [SPX-NEG]"),
        ("up05", " [SPX>0.5]"),
    ]
    for key, suffix in spx_variants:
        r = run_combo(combo_id, desc, where_clause, spx_dates=spx_groups.get(key), label_suffix=suffix)
        results.append(r)
    return results

def fmt_row(r):
    sl = r.get("spx_filter", "")
    if sl == "无SPX过滤": sl = "无"
    elif sl == " [SPX>0]": sl = ">0%"
    elif sl == " [SPX-NEG]": sl = "NEG(连续2日↑)"
    elif sl == " [SPX>0.5]": sl = ">0.5%"
    return (f"| {r['combo']:16s} | {r['desc'][:35]:35s} | {r['N']:4d} | "
            f"{r['WR_5d']:5.1f}% | {r['R5']:5.2f}% | {r['R10']:5.2f}% | "
            f"{r['Sharpe']:6.3f} | {r['P10']:6.2f}% | {sl:16s} |")

# =========================================================================
# MAIN
# =========================================================================
print("="*70)
print("Iter16 Analyst: 量价形态 + 宏观过滤交叉 (R5全局纪录突破冲刺)")
print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"数据范围: {DT_START} ~ {DT_END}")
print("="*70)

print("\n--- 获取 SPX 宏观过滤器数据 ---")
spx_groups = get_spx_date_groups()
all_results = []

# =========================================================================
# DIRECTION A: 锤子线 × SPX
# =========================================================================
print("\n" + "="*70)
print("方向 A: 锤子线 × SPX 重现与优化")
print("="*70)

# X17a: 锤子线原始版 - 下影≥实体+振幅≥5%+VR≥1.3+CM≤50亿
X17a_where = """
    AND amplitude >= 5
    AND volume_ratio >= 1.3
    AND circ_mv <= 500000 AND circ_mv > 0
    AND close > open
    AND (close - low) >= abs(close - open)
    AND low < open
    AND pct_chg >= 0.5 AND pct_chg <= 9.5
"""
all_results.extend(run_combo_all_spx("X17a", "锤子线(下影≥实体+振幅≥5%+VR≥1.3+CM≤50亿)", X17a_where))

# X17d: 锤子线放宽版
X17d_where = """
    AND amplitude >= 4
    AND volume_ratio >= 1.0
    AND circ_mv <= 300000 AND circ_mv > 0
    AND close > open
    AND (close - low) >= abs(close - open)
    AND low < open
    AND pct_chg >= 0.5 AND pct_chg <= 9.5
"""
all_results.extend(run_combo_all_spx("X17d", "锤子线放宽(振幅≥4%+VR≥1.0+CM≤30亿)", X17d_where))

# =========================================================================
# DIRECTION B: SPX × 极端振幅
# =========================================================================
print("\n" + "="*70)
print("方向 B: SPX × 极端振幅组合")
print("="*70)

# X03b: 极端振幅
X03b_where = """
    AND amplitude >= 8
    AND volume_ratio >= 1.0
    AND circ_mv <= 300000 AND circ_mv > 0
    AND pct_chg >= 2.0 AND pct_chg <= 9.5
"""
all_results.extend(run_combo_all_spx("X03b", "极端振幅(涨≥2%+振幅≥8%+VR≥1.0+CM≤30亿)", X03b_where))

# X16b: 极端振幅+高股息
X16b_where = """
    AND amplitude >= 8
    AND volume_ratio >= 1.0
    AND circ_mv <= 500000 AND circ_mv > 0
    AND dv_ratio IS NOT NULL AND dv_ratio >= 2
    AND pe > 0 AND pe <= 20
    AND pct_chg >= 2.0 AND pct_chg <= 9.5
"""
all_results.extend(run_combo_all_spx("X16b", "极端振幅+高股息(dv≥2%+PE≤20+CM≤50亿)", X16b_where))

# X03c: 极端振幅收紧
X03c_where = """
    AND amplitude >= 8
    AND volume_ratio >= 1.5
    AND circ_mv <= 300000 AND circ_mv > 0
    AND pct_chg >= 3.0 AND pct_chg <= 9.5
"""
all_results.extend(run_combo_all_spx("X03c", "极端振幅收紧(涨≥3%+振幅≥8%+VR≥1.5+CM≤30亿)", X03c_where))

# =========================================================================
# DIRECTION C: 多 K 线形态
# =========================================================================
print("\n" + "="*70)
print("方向 C: 多 K 线形态交叉")
print("="*70)

# K01: 启明星
K01_where = """
    AND amplitude >= 5
    AND volume_ratio >= 1.2
    AND open < pre_close
    AND close > open
    AND pct_chg >= 3.0 AND pct_chg <= 9.5
    AND prev_pct IS NOT NULL AND prev_pct <= -1.0
"""
all_results.extend(run_combo_all_spx("K01", "启明星(前日跌≥1%+低开高走+涨≥3%+VR≥1.2+振幅≥5%)", K01_where))

# K02: 看涨吞没
K02_where = """
    AND volume_ratio >= 1.5
    AND circ_mv <= 300000 AND circ_mv > 0
    AND close > pre_close
    AND pct_chg >= 0.5 AND pct_chg <= 9.5
    AND close > prev_high
"""
all_results.extend(run_combo_all_spx("K02", "看涨吞没(收盘>前日最高+VR≥1.5+CM≤30亿)", K02_where))

# K03: 长阳突破
K03_where = """
    AND amplitude >= 8
    AND volume_ratio >= 2.0
    AND circ_mv <= 300000 AND circ_mv > 0
    AND pct_chg >= 7.0 AND pct_chg <= 10.0
"""
all_results.extend(run_combo_all_spx("K03", "长阳突破(涨≥7%+VR≥2.0+振幅≥8%+CM≤30亿)", K03_where))

# K04: 双日反转
K04_where = """
    AND amplitude >= 5
    AND volume_ratio >= 1.2
    AND pct_chg >= 3.0 AND pct_chg <= 9.5
    AND prev_pct IS NOT NULL AND prev_pct <= -3.0
"""
all_results.extend(run_combo_all_spx("K04", "双日反转(前日跌≥3%+今日涨≥3%+振幅≥5%+VR≥1.2)", K04_where))

# K05: 缩量止跌
K05_where = """
    AND amplitude >= 3
    AND volume_ratio <= 0.8
    AND circ_mv <= 300000 AND circ_mv > 0
    AND prev_pct IS NOT NULL AND prev_pct < 0
    AND pct_chg <= 1.0 AND pct_chg >= -3.0
"""
all_results.extend(run_combo_all_spx("K05", "缩量止跌(前日跌+VR≤0.8+振幅≥3%+CM≤30亿)", K05_where))

# K06: 跳空不补
K06_where = """
    AND volume_ratio >= 1.0
    AND open < pre_close
    AND close > prev_open
    AND pct_chg >= 0.5 AND pct_chg <= 9.5
    AND close > open
"""
all_results.extend(run_combo_all_spx("K06", "跳空不补(低开+收盘>前日开盘+VR≥1.0)", K06_where))

# =========================================================================
# RESULTS
# =========================================================================
print(f"\n{'='*60}")
print(f"RESULTS SUMMARY")
print(f"{'='*60}")

all_results.sort(key=lambda r: r["R5"], reverse=True)

md_lines = [
    f"# Iter16 Analyst: 量价形态 + 宏观过滤交叉报告",
    f"",
    f"**执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC+8",
    f"**数据范围**: {DT_START} ~ {DT_END}",
    f"**SPX前日上涨日(>0%)**: {len(spx_groups['up'])} 个",
    f"**SPX连续2日上涨(NEG)**: {len(spx_groups['neg'])} 个",
    f"**SPX前日上涨(>0.5%)**: {len(spx_groups['up05'])} 个",
    f"**全局R5纪录**: 25.76% (Iter7 T9-X17: 锤子线×SPX上涨)",
    f"**全局WR纪录**: 94.93% (Iter15 SPX-NEG)",
    f"",
    f"## 全量结果表",
    f"",
    f"| 编号 | 名称 | N | WR_5d | R5% | R10% | Sharpe | P10% | SPX过滤 |",
    f"|:----:|------|:-:|:-----:|:---:|:----:|:------:|:----:|:-------:|",
]

passed_count = 0
best_r5 = {"combo": "", "R5": -999, "WR_5d": 0, "N": 0, "Sharpe": 0, "P10": 0}
best_wr = {"combo": "", "WR_5d": 0, "R5": 0, "N": 0, "Sharpe": 0, "P10": 0}

for r in all_results:
    md_lines.append(fmt_row(r))
    if r["pass"]: passed_count += 1
    if r["R5"] > best_r5["R5"]: best_r5 = r
    if r["WR_5d"] > best_wr["WR_5d"] and r["N"] >= 50: best_wr = r

md_lines += [
    f"",
    f"## 汇总",
    f"- 通过(合格线: WR≥55%+R5≥5%+N≥200): {passed_count}/{len(all_results)}",
    f"- 全量组合: {len(all_results)}",
    f"",
    f"## 对标全局纪录",
    f"",
    f"| 纪录 | 保持者 | 值 | 本轮最佳 | 胜负 |",
    f"|------|--------|------|----------|------|",
    f"| 全局R5 | Iter7 T9-X17 | 25.76% | {best_r5['R5']:.2f}% ({best_r5['combo']}) | {'🏆 **超越!**' if best_r5['R5'] >= 25.76 else '❌ 未超越'} |",
    f"| 全局WR | Iter15 SPX-NEG | 94.93% | {best_wr['WR_5d']:.1f}% ({best_wr['combo']}) | {'🏆 **超越!**' if best_wr['WR_5d'] >= 94.93 else '❌ 未超越'} |",
    f"",
    f"## 最佳发现",
    f"",
]

# Top 5 by R5
md_lines.append("### R5 最高 TOP 5\n")
for i, r in enumerate(sorted(all_results, key=lambda x: x["R5"], reverse=True)[:5], 1):
    md_lines.append(f"**{i}. {r['combo']}** — R5={r['R5']:.2f}%, WR={r['WR_5d']:.1f}%, N={r['N']}, Sharpe={r['Sharpe']:.3f}")
    md_lines.append(f"   - SPX过滤: {r.get('spx_filter','无')} | P10={r['P10']:.2f}% | {'✅ PASS' if r['pass'] else '❌ FAIL'}\n")

# Top 5 by WR
top5_wr = sorted([r for r in all_results if r['N'] >= 200], key=lambda x: x["WR_5d"], reverse=True)[:5]
if top5_wr:
    md_lines.append("### WR 最高 TOP 5 (N≥200)\n")
    for i, r in enumerate(top5_wr, 1):
        md_lines.append(f"**{i}. {r['combo']}** — WR={r['WR_5d']:.1f}%, R5={r['R5']:.2f}%, N={r['N']}, Sharpe={r['Sharpe']:.3f}")
        md_lines.append(f"   - SPX过滤: {r.get('spx_filter','无')} | P10={r['P10']:.2f}%\n")

# Direction analysis
for label, prefix in [("方向A: 锤子线 × SPX", "X17"), ("方向B: SPX × 极端振幅", "X03b,X16,X03c"), ("方向C: 多K线形态", "K")]:
    md_lines.append(f"### {label}\n")
    if prefix == "X03b,X16,X03c":
        dir_results = [r for r in all_results if r['combo'].startswith('X03') or r['combo'].startswith('X16')]
    else:
        dir_results = [r for r in all_results if r['combo'].startswith(prefix)]
    for r in sorted(dir_results, key=lambda x: x["R5"], reverse=True):
        md_lines.append(f"- **{r['combo']}**: R5={r['R5']:.2f}%, WR={r['WR_5d']:.1f}%, N={r['N']} ({'✅' if r['pass'] else '❌'})")
    md_lines.append(f"")

# SPX filter comparison
md_lines.append(f"## SPX 过滤效果对比\n")
md_lines.append(f"| 策略 | 无SPX | SPX>0% | SPX-NEG | SPX>0.5% |\n")
md_lines.append(f"|------|:-----:|:------:|:-------:|:--------:|\n")

base_combos = {}
for r in all_results:
    base_name = r['combo'].rsplit(" [", 1)[0] if " [" in r['combo'] else r['combo']
    st = r.get('spx_filter', '无')
    if base_name not in base_combos: base_combos[base_name] = {}
    base_combos[base_name][st] = r

for bname, variants in sorted(base_combos.items()):
    def vfmt(k):
        r = variants.get(k, {})
        return f"{r.get('R5',0):.1f}%" if r.get('N', 0) >= 10 else "-"
    md_lines.append(f"| {bname[:20]:20s} | {vfmt('无'):7s} | {vfmt('>0%'):7s} | {vfmt('NEG(连续2日↑)'):8s} | {vfmt('>0.5%'):7s} |\n")

md_lines += [
    f"",
    f"## 核心发现",
    f"",
    f"### 1. R5 最高组合",
    f"- **{best_r5['combo']}**: R5={best_r5['R5']:.2f}%, WR={best_r5['WR_5d']:.1f}%, N={best_r5['N']}, Sharpe={best_r5['Sharpe']:.3f}",
    f"- {'🏆 超越全局R5纪录(25.76%)!' if best_r5['R5'] >= 25.76 else '距全局R5纪录(25.76%)差 ' + str(round(25.76-best_r5['R5'], 2)) + 'pp'}",
    f"",
    f"### 2. WR 最高组合 (N≥50)",
    f"- **{best_wr['combo']}**: WR={best_wr['WR_5d']:.1f}%, R5={best_wr['R5']:.2f}%, N={best_wr['N']}",
    f"- {'🏆 超越全局WR纪录(94.93%)!' if best_wr['WR_5d'] >= 94.93 else '距全局WR纪录(94.93%)差 ' + str(round(94.93-best_wr['WR_5d'], 1)) + 'pp'}",
    f"",
    f"---",
    f"*报告由 Iter16 Analyst 自动生成*",
]

md_path = os.path.join(OUTPUT_DIR, "02_analyst_kline_spx.md")
with open(md_path, "w") as f:
    f.write("\n".join(md_lines))
print(f"\nMarkdown report written to: {md_path}")

json_path = os.path.join(OUTPUT_DIR, "iter16_kline_spx_results.json")
with open(json_path, "w") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f"JSON results written to: {json_path}")

print(f"\n{'='*60}")
print(f"SUMMARY")
print(f"{'='*60}")
print(f"Total combos: {len(all_results)}")
print(f"Passed: {passed_count}")
print(f"Best R5: {best_r5['combo']} = {best_r5['R5']:.2f}%")
print(f"Best WR: {best_wr['combo']} = {best_wr['WR_5d']:.1f}%")
print(f"{'='*60}")
