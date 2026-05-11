#!/usr/bin/env python3
"""T8 量价形态视角 - 5组参数组合回测 (Iter 1)
数据基准: 2026-05-08 | 执行时间: 2026-05-11 15:02 UTC+8
策略域: 纯量价形态 (price + volume pattern)
成功标准: WR>=52% AND 5D收益>=3% AND 信号数>=200

ClickHouse 注意事项:
- leadInFrame + 显式 frame 语法
- WINDOW 必须在 WHERE 之后
- 不支持 CTE 套子查询
"""

import json
import hashlib
import subprocess
import sys
import math

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def ch_query(sql):
    cmd = ["python3", CH_QUERY, "sql", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"  ERROR (rc={r.returncode}): {r.stderr[:500]}", file=sys.stderr)
        return None
    out = r.stdout.strip()
    if not out or out == "[]":
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        print(f"  JSON parse error: {out[:300]}", file=sys.stderr)
        return None

def compute_stats(rows, label=""):
    if not rows:
        return {"signal_count": 0}
    n = len(rows)
    periods = [1, 3, 5, 10, 20]
    ret_data = {p: [] for p in periods}
    for row in rows:
        close = row.get("close")
        if not close or close <= 0:
            continue
        for p in periods:
            fwd = row.get(f"fwd_{p}")
            if fwd and fwd > 0:
                ret_data[p].append((fwd / close - 1) * 100)
    stats = {"signal_count": n}
    for p in periods:
        lst = ret_data[p]
        cnt = len(lst)
        if cnt == 0:
            stats[f"wr_{p}d"] = 0
            stats[f"ret_{p}d"] = 0
            stats[f"sharpe_{p}d"] = 0
            continue
        wins = sum(1 for x in lst if x > 0)
        avg = sum(lst) / cnt
        stats[f"wr_{p}d"] = round(wins / cnt * 100, 2)
        stats[f"ret_{p}d"] = round(avg, 2)
        if cnt > 1:
            var = sum((x - avg) ** 2 for x in lst) / (cnt - 1)
            std = math.sqrt(var) if var > 0 else 0
            if std > 0:
                stats[f"sharpe_{p}d"] = round(avg / std * math.sqrt(252 / p), 3)
            else:
                stats[f"sharpe_{p}d"] = 0
        else:
            stats[f"sharpe_{p}d"] = 0
    wr5 = stats.get("wr_5d", 0)
    ret5 = stats.get("ret_5d", 0)
    stats["pass"] = (wr5 >= 52 and ret5 >= 3 and n >= 200)
    return stats

def combo_hash(params):
    pairs = sorted(f"{k}={v}" for k, v in params.items())
    return hashlib.md5("|".join(pairs).encode()).hexdigest()[:10]

# ═══════════════════════════════════════════════
# ClickHouse SQL: 全量查询 (注意 WINDOW 在 WHERE 之后, leadInFrame)
# ═══════════════════════════════════════════════

FULL_SQL = """
SELECT
    ts_code, trade_date, close, open, high, low, pre_close, pct_chg, vol, amount,
    avg(close) OVER w5 AS ma5,
    avg(close) OVER w10 AS ma10,
    avg(close) OVER w20 AS ma20,
    vol / NULLIF(avg(vol) OVER w5, 0) AS vol_ratio,
    max(high) OVER w20r AS high_20d,
    min(low) OVER w20r AS low_20d,
    (close - min(low) OVER w20r) / NULLIF(max(high) OVER w20r - min(low) OVER w20r, 0) AS pos_20d,
    open / NULLIF(pre_close, 0) - 1 AS gap_pct,
    (high - low) / NULLIF(pre_close, 0) AS amplitude,
    leadInFrame(close, 1) OVER wfwd AS fwd_1,
    leadInFrame(close, 3) OVER wfwd AS fwd_3,
    leadInFrame(close, 5) OVER wfwd AS fwd_5,
    leadInFrame(close, 10) OVER wfwd AS fwd_10,
    leadInFrame(close, 20) OVER wfwd AS fwd_20
FROM tushare.tushare_stock_daily FINAL
WHERE ts_code NOT LIKE '30%'
  AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%'
  AND ts_code NOT LIKE '%ST%'
  AND amount >= 1e5
  AND trade_date >= '2023-01-01'
WINDOW
    w5 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
    w10 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
    w20 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
    w20r AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
    wfwd AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)
ORDER BY trade_date DESC
LIMIT 1500000
"""

# Python 过滤函数
def f1(r):
    """放量突破20日新高: pos>=0.8, vol_ratio>=2, pct_chg>=2"""
    p = r.get("pos_20d"); v = r.get("vol_ratio"); c = r.get("pct_chg")
    return p is not None and p >= 0.8 and v is not None and v >= 2.0 and c is not None and c >= 2.0

def f2(r):
    """均线多头+温和放量: ma5>ma10>ma20, vol_ratio>=1.5, pct_chg>=0"""
    m5=r.get("ma5"); m10=r.get("ma10"); m20=r.get("ma20"); v=r.get("vol_ratio"); c=r.get("pct_chg")
    return m5 and m10 and m20 and m5>m10 and m10>m20 and v and v>=1.5 and c is not None and c>=0

def f3(r):
    """大阳线放量: pct_chg>=7, vol_ratio>=1, amplitude>=5%"""
    c=r.get("pct_chg"); v=r.get("vol_ratio"); a=r.get("amplitude")
    return c is not None and c>=7.0 and v and v>=1.0 and a is not None and a>=0.05

def f4(r):
    """跳空+温和涨: gap>=1%, 1%<=pct<=5%, vol_ratio>=1.2"""
    g=r.get("gap_pct"); c=r.get("pct_chg"); v=r.get("vol_ratio")
    return g is not None and g>=0.01 and c is not None and 1.0<=c<=5.0 and v and v>=1.2

def f5(r):
    """底部放量: pos<=0.2, vol_ratio>=1.5, pct_chg>=0"""
    p=r.get("pos_20d"); v=r.get("vol_ratio"); c=r.get("pct_chg")
    return p is not None and p<=0.2 and v and v>=1.5 and c is not None and c>=0

combos = [
    {
        "name": "放量突破20日新高",
        "params": {"n_day_high": 20, "volume_ratio_min": 2.0, "close_position": "顶20%", "pct_chg_1d_min": 2},
        "domain": "价格行为+量能",
        "fn": f1,
        "where": "pos_20d>=0.80 AND vol_ratio>=2.0 AND pct_chg>=2.0",
        "desc": "股价位于20日区间顶部80%+, 量比>=2, 当日涨幅>=2%",
    },
    {
        "name": "均线多头排列+温和放量",
        "params": {"ma_arrangement": "多头排列", "volume_ratio_min": 1.5, "pct_chg_1d_min": 0},
        "domain": "均线系统+量能",
        "fn": f2,
        "where": "ma5>ma10>ma20 AND vol_ratio>=1.5 AND pct_chg>=0",
        "desc": "MA5>MA10>MA20多头排列, 量比>=1.5温和放量, 非下跌日",
    },
    {
        "name": "大阳线放量(涨停附近)",
        "params": {"pct_chg_1d_min": 7, "volume_ratio_min": 1.0, "amplitude_min": 5},
        "domain": "价格行为+量能+涨停",
        "fn": f3,
        "where": "pct_chg>=7.0 AND vol_ratio>=1.0 AND amplitude>=5%",
        "desc": "当日涨幅>=7%, 振幅>=5%, 量比>=1 — 大阳线强势形态",
    },
    {
        "name": "向上跳空+中小幅上涨",
        "params": {"gap_direction": "向上跳空", "pct_chg_1d_min": 1, "pct_chg_1d_max": 5, "volume_ratio_min": 1.2},
        "domain": "价格行为+量能",
        "fn": f4,
        "where": "gap_pct>=0.01 AND 1.0<=pct_chg<=5.0 AND vol_ratio>=1.2",
        "desc": "跳空高开>=1%, 涨幅1-5%温和, 量比>=1.2",
    },
    {
        "name": "底部放量(超跌反弹)",
        "params": {"close_position": "底20%", "volume_ratio_min": 1.5, "pct_chg_1d_min": 0},
        "domain": "价格位置+量能",
        "fn": f5,
        "where": "pos_20d<=0.20 AND vol_ratio>=1.5 AND pct_chg>=0",
        "desc": "股价位于20日底部20%以内, 量比>=1.5放量, 当日不跌",
    },
]

# Step 1: 全量查询
print("Step 1: 查询全量基础数据(近3年, 20万条上限)...")
rows = ch_query(FULL_SQL)
if rows is None:
    print("FAIL: 全量查询失败")
    sys.exit(1)
print(f"  获取 {len(rows)} 条基础数据")

# Step 2: Python 过滤 + 统计
results = []
for i, combo in enumerate(combos, 1):
    print(f"\n{'='*60}")
    print(f"组合 {i}: {combo['name']}")
    print(f"域: {combo['domain']} | 条件: {combo['where']}")

    filtered = [r for r in rows if combo["fn"](r)]
    print(f"  筛选信号数: {len(filtered)}")

    if not filtered:
        results.append({"combo": combo, "stats": {"signal_count": 0}, "error": "no_signals"})
        continue

    stats = compute_stats(filtered, combo["name"])
    wr5 = stats.get("wr_5d", 0)
    ret5 = stats.get("ret_5d", 0)
    sc = stats.get("signal_count", 0)
    print(f"  WR_5d={wr5}%, ret_5d={ret5}%, sharpe_5d={stats.get('sharpe_5d', 0)}")
    if stats.get("pass"):
        print(f"  通过成功标准!")
    results.append({"combo": combo, "stats": stats, "error": None})

# ═══════════════════════════════════════════════
# 生成 Markdown 报告
# ═══════════════════════════════════════════════

rpt = []
rpt.append("# T8 量价形态 视角 — Iter 1")
rpt.append("")
rpt.append("> 数据基准: 2026-05-08 | 执行时间: 2026-05-11 15:02 UTC+8")
rpt.append("> 角色: 策略挖掘分析师 (量价形态视角)")
rpt.append("> 回测范围: 2023-01-01 ~ 2026-05-08 (近3年, 采样20万条)")
rpt.append("> 基础过滤: 排除30/688/920/ST, amount>=1亿")
rpt.append("> 成功标准: WR>=52% AND 5D收益>=3% AND 信号数>=200")
rpt.append("")

rpt.append("## 测试参数组合 (5 组)")
rpt.append("")

for i, r in enumerate(results, 1):
    c = r["combo"]
    s = r["stats"]
    rpt.append(f"### 组合 {i}: {c['name']}")
    rpt.append(f"- **域**: {c['domain']}")
    rpt.append(f"- **参数**: {', '.join(f'{k}={v}' for k, v in c['params'].items())}")
    rpt.append(f"- **逻辑**: {c['desc']}")
    rpt.append(f"- **条件**: `{c['where']}`")
    if s.get("signal_count", 0) == 0:
        rpt.append(f"- **结果**: 信号数=0")
    else:
        sc = s["signal_count"]
        rpt.append(f"- **结果**: 信号数={sc}")
        for pd in [1,3,5,10,20]:
            rpt.append(f"  - {pd}D: WR={s.get(f'wr_{pd}d',0)}%, ret={s.get(f'ret_{pd}d',0)}%, sharpe={s.get(f'sharpe_{pd}d',0)}")
        if s.get("pass"):
            rpt.append(f"- **判定**: 通过成功标准 (WR_5d={s['wr_5d']}%>=52%, ret_5d={s['ret_5d']}%>=3%, N={sc}>=200)")
        else:
            fails = []
            if s.get("wr_5d", 0) < 52: fails.append(f"WR_5d={s['wr_5d']}%<52%")
            if s.get("ret_5d", 0) < 3: fails.append(f"ret_5d={s['ret_5d']}%<3%")
            if sc < 200: fails.append(f"信号数={sc}<200")
            rpt.append(f"- **判定**: 未达标准 — {', '.join(fails)}")
    rpt.append("")

rpt.append("## 最佳发现")
rpt.append("")
valid = [(i, r) for i, r in enumerate(results) if r["stats"] and r["stats"].get("signal_count", 0) > 0]
if valid:
    def score(r):
        s = r["stats"]
        return (s.get("wr_5d",0) or 0) * (s.get("ret_5d",0) or 0) * min(s.get("signal_count",0) or 0 / 200, 5)
    bi, br = max(valid, key=lambda x: score(x[1]))
    c, s = br["combo"], br["stats"]
    sc = s.get("signal_count")
    rpt.append(f"- **最佳参数**: {c['name']}")
    rpt.append(f"- **参数组合**: {', '.join(f'{k}={v}' for k, v in c['params'].items())}")
    rpt.append(f"- **核心指标**: 信号数={sc}, WR_5d={s.get('wr_5d')}%, ret_5d={s.get('ret_5d')}%, ret_10d={s.get('ret_10d')}%, sharpe_5d={s.get('sharpe_5d')}")
    rpt.append(f"- **详细分析**: {c['domain']}域, {c['desc']}。{sc}个信号中, "
               f"5日胜率{s.get('wr_5d')}%, 5日收益{s.get('ret_5d')}%, 10日收益{s.get('ret_10d')}%, 20日收益{s.get('ret_20d')}%。"
               f"5日夏普{s.get('sharpe_5d')}, 10日夏普{s.get('sharpe_10d')}。")
    rpt.append(f"- **结论**: {'通过成功标准, 可进入交叉验证' if s.get('pass') else '未完全达标, 作首轮参考基线'}")
else:
    rpt.append("- 无有效信号")

rpt.append("")
rpt.append("## 所有组合 Hash (用于去重)")
rpt.append("")
hashes = []
for r in results:
    h = combo_hash(r["combo"]["params"])
    hashes.append(h)
    rpt.append(f"- `{h}` — {r['combo']['name']}")
rpt.append(f"\nHash列表: {', '.join(hashes)}")

rpt.append("\n## 完整 SQL 查询")
rpt.append("```sql")
rpt.append(FULL_SQL)
rpt.append("```")

out_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_1/analysis_T8_量价形态.md"
with open(out_path, "w") as f:
    f.write("\n".join(rpt))

print(f"\n报告已写入: {out_path}")
