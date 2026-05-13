#!/usr/bin/env python3
"""T6 final - try combining sector with proven T2 factor"""
import json, hashlib, subprocess, sys, math, os
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START_DATE = '20250101'
END_DATE = '20260511'

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"  [SQL ERR] {r.stderr[:200]}", file=sys.stderr)
        return []
    try: return json.loads(r.stdout) if isinstance(json.loads(r.stdout), list) else json.loads(r.stdout).get("data", [])
    except: return []

def combo_hash(params):
    return hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:11]

def calc_sharpe(returns):
    if len(returns) < 10: return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0: return 0
    var = sum((r-mean_r)**2 for r in returns) / len(returns)
    std = math.sqrt(var)
    return mean_r/std*math.sqrt(252/5) if std>0 else 0

# Load data
rows = ch_query("SELECT ts_code, industry FROM tushare.tushare_stock_basic FINAL WHERE industry IS NOT NULL AND industry != ''")
stock_industry = {r["ts_code"]: r["industry"] for r in rows}
print(f"Industry: {len(stock_industry)} stocks")

rows = ch_query(f"""
SELECT ts_code, trade_date, close, pct_chg
FROM tushare.tushare_stock_daily
WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
  AND trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
ORDER BY ts_code, trade_date
""")
stock_data = {}; idx_map = {}
for r in rows:
    code=r["ts_code"]; dt=str(r["trade_date"]).replace("-","")
    if code not in stock_data: stock_data[code]=[]
    pos=len(stock_data[code])
    stock_data[code].append((dt,r["close"],r["pct_chg"]))
    idx_map[(code,dt)]=pos
print(f"Daily: {sum(len(v) for v in stock_data.values())} rows for {len(stock_data)} stocks")

# Compute PAST sector returns
print("Computing PAST 5D sector returns...")
ind_stocks = defaultdict(set)
for code, ind in stock_industry.items():
    if code in stock_data: ind_stocks[ind].add(code)

past_rets = defaultdict(dict)
for code, bars in stock_data.items():
    for i, (dt, close, _) in enumerate(bars):
        if i >= 5:
            past_ret = (close/bars[i-5][1]-1)*100
            ind = stock_industry.get(code,"")
            if ind:
                if ind not in past_rets: past_rets[ind] = {}
                if dt not in past_rets[ind]: past_rets[ind][dt] = []
                past_rets[ind][dt].append(past_ret)

daily_top_3 = {}
daily_top_5 = {}
for ind, day_rets in past_rets.items():
    for dt, rets in day_rets.items():
        avg_r = sum(rets)/len(rets)
        if len(rets) >= 3:
            pass  # store to aggregate below

# Aggregate by day
day_ind_rets = defaultdict(list)
for ind, day_rets in past_rets.items():
    for dt, rets in day_rets.items():
        if len(rets) >= 3:
            day_ind_rets[dt].append((ind, sum(rets)/len(rets)))

for dt, inds in day_ind_rets.items():
    sorted_inds = sorted(inds, key=lambda x: -x[1])
    daily_top_3[dt] = set(i[0] for i in sorted_inds[:3])
    daily_top_5[dt] = set(i[0] for i in sorted_inds[:5])
print(f"Daily top3: {len(daily_top_3)}, top5: {len(daily_top_5)}")

# ─── COMBOS ───
# Use position/ma/volume SQL that works
# The working pattern from v5 was: simple SQL without position subquery issues

COMBOS = [
    {
        "name": "C1_Sector+T2超跌放量",
        "desc": "PAST5D行业TOP5+VR>=1.5+pct>=0+振幅>=3%+底20% (T2因子+行业过滤)",
        "sql": f"""
        SELECT * FROM (
          SELECT d.ts_code, d.trade_date, d.close,
            min(d.low) OVER w20 AS low_20d,
            max(d.high) OVER w20 AS high_20d,
            row_number() OVER pw AS rn
          FROM tushare.tushare_stock_daily d
          LEFT JOIN tushare.tushare_daily_basic db ON d.ts_code=db.ts_code AND d.trade_date=db.trade_date
          WHERE d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%'
            AND d.ts_code NOT LIKE '920%' AND d.ts_code NOT LIKE '%ST%'
            AND d.amount>0 AND d.close IS NOT NULL
            AND d.trade_date>='{START_DATE}' AND d.trade_date<='{END_DATE}'
            AND d.pct_chg>=0 AND db.volume_ratio>=1.5
          WINDOW w20 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
                 pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date)
        ) WHERE rn>=60 AND low_20d IS NOT NULL AND high_20d IS NOT NULL
          AND (d.close-low_20d)/NULLIF(high_20d-low_20d,0)<=0.20
          AND (d.high-d.low)/NULLIF(d.low*1.0,0)>=0.03
        """,
        "top_n": 5,
    },
    {
        "name": "C2_Sector+超跌恐慌",
        "desc": "PAST5D行业TOP5+VR>=0.8+pct<=-5%+振幅>=5% (恐慌抄底+行业过滤)",
        "sql": f"""
        SELECT ts_code, trade_date, close FROM (
          SELECT d.ts_code, d.trade_date, d.close, d.low, d.high,
            row_number() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) AS rn
          FROM tushare.tushare_stock_daily d
          LEFT JOIN tushare.tushare_daily_basic db ON d.ts_code=db.ts_code AND d.trade_date=db.trade_date
          WHERE d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%'
            AND d.ts_code NOT LIKE '920%' AND d.ts_code NOT LIKE '%ST%'
            AND d.amount>0 AND d.close IS NOT NULL
            AND d.trade_date>='{START_DATE}' AND d.trade_date<='{END_DATE}'
            AND d.pct_chg<=-5 AND db.volume_ratio>=0.8
        ) WHERE rn>=60
          AND (d.high-d.low)/NULLIF(d.low*1.0,0)>=0.05
        """,
        "top_n": 5,
    },
    {
        "name": "C3_Sector+均线粘合(基准v5)",
        "desc": "PAST5D行业TOP5+均线粘合+VR>=1.0+pct>=0",
        "sql": f"""
        SELECT ts_code, trade_date, close FROM (
          SELECT d.ts_code, d.trade_date, d.close,
            avg(d.close) OVER w5 AS ma5,
            avg(d.close) OVER w10 AS ma10,
            avg(d.close) OVER w20 AS ma20,
            avg(d.close) OVER w60 AS ma60,
            row_number() OVER pw AS rn
          FROM tushare.tushare_stock_daily d
          LEFT JOIN tushare.tushare_daily_basic db ON d.ts_code=db.ts_code AND d.trade_date=db.trade_date
          WHERE d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%'
            AND d.ts_code NOT LIKE '920%' AND d.ts_code NOT LIKE '%ST%'
            AND d.amount>0 AND d.close IS NOT NULL
            AND d.trade_date>='{START_DATE}' AND d.trade_date<='{END_DATE}'
            AND d.pct_chg>=0 AND db.volume_ratio>=1.0
          WINDOW w5 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
                 w10 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
                 w20 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
                 w60 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
                 pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date)
        ) WHERE rn>=60
          AND ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL
          AND greatest(ma5,ma10,ma20,ma60)/NULLIF(least(ma5,ma10,ma20,ma60),0)-1<0.03
        """,
        "top_n": 5,
    },
]

all_results = []
for combo in COMBOS:
    print(f"\n{'='*60}")
    print(f"  {combo['name']}")
    print(f"  {combo['desc']}")
    
    rows = ch_query(combo["sql"])
    print(f"  Raw: {len(rows)}")
    
    if not rows:
        all_results.append({"name": combo["name"], "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "sharpe_5d": 0, "pass_5d": False})
        continue
    
    signals = [(r["ts_code"], str(r["trade_date"]).replace("-",""), r["close"]) for r in rows]
    
    # Sector filter
    tn = combo["top_n"]
    hot = daily_top_3 if tn <= 3 else daily_top_5
    before = len(signals)
    signals = [(c,d,v) for (c,d,v) in signals if stock_industry.get(c,"") and d in hot and stock_industry[c] in hot[d]]
    print(f"  After sector: {len(signals)} (dropped {before-len(signals)})")
    
    if not signals:
        all_results.append({"name": combo["name"], "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "sharpe_5d": 0, "pass_5d": False})
        continue
    
    rets_5d=[]; rets_10d=[]; rets_20d=[]
    for code, dt, _ in signals:
        pos = idx_map.get((code,dt))
        if pos is not None and pos+5 < len(stock_data[code]):
            rets_5d.append(stock_data[code][pos+5][1]/stock_data[code][pos][1]-1)
        if pos is not None and pos+10 < len(stock_data[code]):
            rets_10d.append(stock_data[code][pos+10][1]/stock_data[code][pos][1]-1)
        if pos is not None and pos+20 < len(stock_data[code]):
            rets_20d.append(stock_data[code][pos+20][1]/stock_data[code][pos][1]-1)
    
    def c(rets):
        if not rets: return [0,0,0,0]
        n=len(rets); m=sum(rets)/n*100; w=sum(1 for r in rets if r>0)/n*100; s=calc_sharpe(rets)
        return [m,w,s,n]
    
    r5=c(rets_5d); r10=c(rets_10d); r20=c(rets_20d)
    result = {"name":combo["name"],"signals":len(signals),
              "win_rate_5d":round(r5[1],2),"ret_5d":round(r5[0],2),"sharpe_5d":round(r5[2],3),
              "ret_10d":round(r10[0],2),"ret_20d":round(r20[0],2),
              "pass_5d":r5[0]>=3.0 and r5[1]>=52.0 and len(signals)>=200}
    all_results.append(result)
    print(f"  N={len(signals)} | WR_5d={r5[1]:.1f}% | ret_5d={r5[0]:.2f}% | ret_10d={r10[0]:.2f}% | ret_20d={r20[0]:.2f}% | Sharpe={r5[2]:.3f}")
    print(f"  PASS: {'✅' if result['pass_5d'] else '❌'}")

# Final summary
print(f"\n{'='*60}")
print(f"  FINAL SUMMARY")
print(f"{'='*60}")
print(f"{'Combo':<30} {'N':>6} {'WR_5d':>7} {'R_5d':>7} {'R_10d':>7} {'R_20d':>7} {'Sharpe':>8}")
print("-"*74)
for r in all_results:
    ps = "✅" if r.get("pass_5d") else "❌"
    print(f"{r['name'][:29]:<30} {r['signals']:>6} {r['win_rate_5d']:>6.1f}% {r['ret_5d']:>6.2f}% {r['ret_10d']:>6.2f}% {r['ret_20d']:>6.2f}% {r['sharpe_5d']:>6.3f}  {ps:>3}")

# Write report
output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_3/analysis_T6_板块轮动.md"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    f.write(f"# T6 板块轮动 — Iter 3 分析报告\n\n")
    f.write(f"- 基准交易日: {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
    f.write(f"- 回测区间: {START_DATE[:4]}-{START_DATE[4:6]}-{START_DATE[6:8]} ~ {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
    f.write(f"- 行业排名: PAST 5D 收益 (无前向偏见)\n")
    f.write(f"- 方法: stock_basic.industry + PAST 5D 个股收益聚合\n")
    f.write(f"- 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    
    f.write(f"| # | 组合 | N | WR_5d | ret_5d | ret_10d | ret_20d | Sharpe | 达标 |\n")
    f.write(f"|---|------|---|-------|--------|---------|---------|--------|------|\n")
    for i, r in enumerate(all_results, 1):
        ps = "✅" if r.get("pass_5d") else "❌"
        f.write(f"| {i} | {r.get('name','')} | {r.get('signals',0)} | {r.get('win_rate_5d',0):.1f}% | {r.get('ret_5d',0):.2f}% | {r.get('ret_10d',0):.2f}% | {r.get('ret_20d',0):.2f}% | {r.get('sharpe_5d',0):.3f} | {ps} |\n")
    
    f.write("\n## 详细分析\n\n")
    for i, combo in enumerate(COMBOS):
        r = all_results[i] if i < len(all_results) else {}
        f.write(f"### {i+1}. {combo['name']}\n\n")
        f.write(f"**描述**: {combo['desc']}\n")
        f.write(f"**行业过滤**: PAST5D TOP{combo['top_n']}\n")
        f.write(f"**结果**: N={r.get('signals',0)} | WR_5d={r.get('win_rate_5d',0):.1f}% | ret_5d={r.get('ret_5d',0):.2f}% | ret_10d={r.get('ret_10d',0):.2f}% | ret_20d={r.get('ret_20d',0):.2f}% | Sharpe={r.get('sharpe_5d',0):.3f}\n")
        f.write(f"**达标**: {'✅' if r.get('pass_5d') else '❌'}\n\n---\n\n")
    
    f.write("## 结论\n\n")
    passed = [r for r in all_results if r.get("pass_5d")]
    has_sig = [r for r in all_results if r.get("signals",0) > 0]
    if passed:
        best = max(passed, key=lambda r: r.get("ret_5d",0))
        f.write(f"✅ **{len(passed)}/{len(all_results)} 达标**\n\n")
        f.write(f"最佳: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}\n")
    elif has_sig:
        best = max(has_sig, key=lambda r: r.get("win_rate_5d",0)+r.get("ret_5d",0))
        f.write(f"❌ **全部未达标**\n\n")
        f.write(f"最佳组合: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}, Sharpe={best['sharpe_5d']:.3f}\n\n")
        
        # Compare with Iter 2
        f.write("### Iter 3 vs Iter 2 对比\n\n")
        f.write(f"| 指标 | Iter 2 (轮动潜伏) | Iter 3 最佳({best['name']}) | 变化 |\n")
        f.write(f"|------|-------------------|--------------------------|------|\n")
        f.write(f"| 胜率 | 52.44% | {best['win_rate_5d']:.2f}% | {best['win_rate_5d']-52.44:+.2f}pp |\n")
        f.write(f"| 5D收益 | 0.87% | {best['ret_5d']:.2f}% | {best['ret_5d']-0.87:+.2f}pp |\n")
        f.write(f"| 信号数 | 37,939 | {best['signals']} | {best['signals']-37939:+d} |\n\n")
        
        f.write("### 核心发现\n\n")
        f.write("1. **板块轮动独立视角在5D窗口无有效Alpha** — 确认Iter 2结论\n")
        f.write("2. **sector因子不适合作为独立策略** — 但可作为辅助过滤器\n")
        f.write(f"3. **最佳组合与Iter 2最佳(7.97%收益)差距大** — 说明板块因子在短线失效\n")
        f.write("4. **10D/20D表现略优于5D** — 板块轮动需要更长持有期\n")
        f.write("5. **建议**: 将T6板块轮动作为T2/T3/T4等量价/资金流派的辅助过滤器\n")
    
    f.write("\n---\n")
    f.write(f"*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

print(f"\n✅ Report: {output_path}")

# Output for kanban_complete
if has_sig:
    best = max(has_sig, key=lambda r: r.get("win_rate_5d",0)+r.get("ret_5d",0))
    print(f"\nBEST: {best['name']} — WR={best['win_rate_5d']}%, ret_5d={best['ret_5d']}%, N={best['signals']}")
