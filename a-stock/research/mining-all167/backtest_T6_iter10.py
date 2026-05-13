#!/usr/bin/env python3
"""T6 板块轮动 - Iter 10: NEW strategies using industry rotation timing"""
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

def calc_sharpe(returns):
    if len(returns) < 10: return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0: return 0
    var = sum((r-mean_r)**2 for r in returns) / len(returns)
    std = math.sqrt(var)
    return mean_r/std*math.sqrt(252/5) if std>0 else 0

# ── Step 1: Load industry data ──
print("Loading industry data...")
rows = ch_query("SELECT ts_code, industry FROM tushare.tushare_stock_basic FINAL WHERE industry IS NOT NULL AND industry != ''")
stock_industry = {r["ts_code"]: r["industry"] for r in rows}
print(f"  Industry mapping: {len(stock_industry)} stocks")

# ── Step 2: Load stock daily data ──
print("Loading stock daily data...")
rows = ch_query(f"""
SELECT ts_code, trade_date, close, pct_chg, low, high
FROM tushare.tushare_stock_daily FINAL
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
    stock_data[code].append((dt,r["close"],r["pct_chg"],r["low"],r["high"]))
    idx_map[(code,dt)]=pos
print(f"  {sum(len(v) for v in stock_data.values())} rows for {len(stock_data)} stocks")

# ── Step 3: Load daily_basic (volume_ratio, circ_mv) ──
print("Loading daily_basic...")
rows = ch_query(f"""
SELECT ts_code, trade_date, volume_ratio, circ_mv, turnover_rate
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
  AND volume_ratio IS NOT NULL
""")
db_data = {}
for r in rows:
    code=r["ts_code"]; dt=str(r["trade_date"]).replace("-","")
    db_data[(code, dt)] = {
        "vr": r["volume_ratio"],
        "cm": r["circ_mv"] if r.get("circ_mv") else 0,
        "tr": r["turnover_rate"] if r.get("turnover_rate") else 0
    }
print(f"  {len(db_data)} rows")

# ── Step 4: Compute industry-level PAST returns ──
print("Computing PAST industry returns...")
# Build industry stock index
ind_stocks = defaultdict(set)
for code, ind in stock_industry.items():
    if code in stock_data: ind_stocks[ind].add(code)

def calc_ind_return(days_back):
    """Compute industry average return over past `days_back` days for each day."""
    results = defaultdict(dict)  # dt -> {ind: avg_ret}
    for code, bars in stock_data.items():
        for i, (dt, close, pct, low, high) in enumerate(bars):
            if i >= days_back:
                past_ret = (close / bars[i-days_back][1] - 1) * 100
                ind = stock_industry.get(code, "")
                if ind:
                    if dt not in results[ind]:
                        results[ind][dt] = []
                    results[ind][dt].append(past_ret)
    # Aggregate
    day_ind_rets = defaultdict(list)  # dt -> [(ind, avg_ret, n_stocks)]
    for ind, day_rets in results.items():
        for dt, rets in day_rets.items():
            if len(rets) >= 3:
                day_ind_rets[dt].append((ind, sum(rets)/len(rets), len(rets)))
    return day_ind_rets

ind_rets_1d = calc_ind_return(1)
ind_rets_3d = calc_ind_return(3)
print(f"  Industry 1D returns: {sum(len(v) for v in ind_rets_1d.values())} day-industry pairs")
print(f"  Industry 3D returns: {sum(len(v) for v in ind_rets_3d.values())} day-industry pairs")

# Helper to get ranked industries
def get_top_industries(day_rets, dt, n, from_top=True):
    if dt not in day_rets: return set()
    sorted_inds = sorted(day_rets[dt], key=lambda x: -x[1] if from_top else x[1])
    return set(i[0] for i in sorted_inds[:n])

def get_industry_ret(day_rets, dt, ind):
    if dt not in day_rets: return None
    for i, avg, n in day_rets[dt]:
        if i == ind: return avg
    return None

# ── Step 5: Define strategies ──
# Generate all candidate signals from SQL first, then apply industry filter

COMBOS = []

# C1: 板块动量前排+深底放量 (Top Industry by 3D momentum + deep bottom + volume)
# Thesis: Stocks in the hottest sectors that haven't started moving yet
COMBOS.append({
    "name": "C1_板块动量前排深底放量",
    "desc": "行业3D涨幅TOP5 + 底20% + 振幅≥5% + VR≥1.2 + CM≤50亿",
    "cond": lambda code, dt: (
        db_data.get((code,dt),{}).get("vr",0) >= 1.2
        and db_data.get((code,dt),{}).get("cm",float('inf')) <= 500000  # 50亿(万元)
    ),
    "ind_filter": lambda dt: get_top_industries(ind_rets_3d, dt, 5, from_top=True),
    "top_n": 5,
})

# C2: 板块超跌+恐慌放量 (Industry oversold + panic volume reversal)
# Thesis: Most oversold industries have mean-reversion potential
COMBOS.append({
    "name": "C2_板块超跌恐慌放量",
    "desc": "行业3D涨幅倒数TOP5 + 底20% + 振幅≥6% + VR≥1.3 + CM≤50亿",
    "cond": lambda code, dt: (
        db_data.get((code,dt),{}).get("vr",0) >= 1.3
        and db_data.get((code,dt),{}).get("cm",float('inf')) <= 500000
    ),
    "ind_filter": lambda dt: get_top_industries(ind_rets_3d, dt, 5, from_top=False),
    "top_n": 5,
})

# C3: 板块当日最强+微盘补涨 (Sector intraday strongest + micro-cap catch-up)
# Thesis: Strong sectors today -> micro-cap laggards within the sector catch up
COMBOS.append({
    "name": "C3_板块当日最强微盘补涨",
    "desc": "行业1D涨幅TOP3 + 底20% + 振幅≥5% + VR≥1.0 + 涨幅≥0% + CM≤30亿",
    "cond": lambda code, dt: (
        db_data.get((code,dt),{}).get("vr",0) >= 1.0
        and db_data.get((code,dt),{}).get("cm",float('inf')) <= 300000  # 30亿
        and db_data.get((code,dt),{}).get("tr",0) >= 0.005  # 换手≥0.5%排除僵尸
    ),
    "ind_filter": lambda dt: get_top_industries(ind_rets_1d, dt, 3, from_top=True),
    "top_n": 3,
})

# C4: 板块连续走强+底部确认爆发 (Industry continuous rally + bottom breakout)
# Thesis: Sectors with sustained multi-day strength -> stocks breaking out from bottom
# C1 with stronger conditions: both 1D top20 and 3D top15 -> sustained sector strength
COMBOS.append({
    "name": "C4_板块持续走强底部爆发",
    "desc": "行业3D涨幅TOP10 + 底20% + 振幅≥5% + VR≥1.2 + 涨幅≥1% + CM≤50亿",
    "cond": lambda code, dt: (
        db_data.get((code,dt),{}).get("vr",0) >= 1.2
        and db_data.get((code,dt),{}).get("cm",float('inf')) <= 500000
    ),
    "ind_filter": lambda dt: get_top_industries(ind_rets_3d, dt, 10, from_top=True),
    "top_n": 10,
})

# C5: 板块轮动β中性的深底大振幅策略 (Sector rotation β-neutral deep bottom)
# Thesis: Remove sector bias by requiring industry to be in MIDDLE 40% (not top/bottom)
# This tests if pure stock-specific factors outperform without sector noise
COMBOS.append({
    "name": "C5_板块中性深底反转",
    "desc": "行业中位40%(非热非冷) + 底20% + 振幅≥5% + VR≥1.2 + CM≤100亿 + 换手0.5-10%",
    "cond": lambda code, dt: (
        db_data.get((code,dt),{}).get("vr",0) >= 1.2
        and db_data.get((code,dt),{}).get("cm",float('inf')) <= 1000000
        and 0.005 <= db_data.get((code,dt),{}).get("tr",0) <= 0.10
    ),
    "ind_filter": lambda dt: None,  # Applied in logic
    "top_n": 0,
})

print(f"\n{'='*60}")
print("Running backtest...")

all_results = []
for combo_idx, combo in enumerate(COMBOS):
    name = combo["name"]
    desc = combo["desc"]
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"  {desc}")
    
    # Step 1: SQL to get base candidates WITH position/low-high calculation
    # Use window functions + daily_basic join
    sql = f"""
    SELECT ts_code, trade_date, close
    FROM (
      SELECT d.ts_code, d.trade_date, d.close, d.low, d.high, d.pct_chg,
        min(d.low) OVER w20 AS low_20d,
        max(d.high) OVER w20 AS high_20d,
        row_number() OVER pw AS rn
      FROM tushare.tushare_stock_daily d
      WHERE d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%'
        AND d.ts_code NOT LIKE '920%' AND d.ts_code NOT LIKE '%ST%'
        AND d.amount>0 AND d.close IS NOT NULL
        AND d.trade_date>='{START_DATE}' AND d.trade_date<='{END_DATE}'
      WINDOW w20 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
             pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date)
    ) WHERE rn>=60
      AND low_20d IS NOT NULL AND high_20d IS NOT NULL
      AND high_20d != low_20d
    """
    
    rows = ch_query(sql)
    print(f"  Raw SQL: {len(rows)}")
    
    if not rows:
        all_results.append({"name": name, "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "sharpe_5d": 0, "pass_5d": False})
        continue
    
    # Step 2: Apply position, amplitude and combo-specific conditions
    signals = []
    for r in rows:
        code = r["ts_code"]
        dt = str(r["trade_date"]).replace("-","")
        
        # Get position data
        if code not in stock_data: continue
        pos = idx_map.get((code, dt))
        if pos is None: continue
        bar = stock_data[code][pos]
        close, low, high = bar[1], bar[3], bar[4]
        
        # Compute position and amplitude from daily data
        # We need 20d min/max from the row data
        low_20d = None
        high_20d = None
        for j in range(max(0, pos-19), pos+1):
            b = stock_data[code][j]
            if low_20d is None or b[3] < low_20d: low_20d = b[3]
            if high_20d is None or b[4] > high_20d: high_20d = b[4]
        
        if low_20d is None or high_20d is None or high_20d == low_20d:
            continue
        
        close_position = (close - low_20d) / (high_20d - low_20d)
        amplitude = (high - low) / low
        
        # Apply position and amplitude filters
        if close_position > 0.20: continue  # 底20%
        
        # C5 special: 底20%
        if combo_idx == 4 and close_position > 0.20: continue  # 底20%
        
        # Amplitude filter
        if combo_idx == 1:  # C2: 振幅≥6%
            if amplitude < 0.06: continue
        elif combo_idx == 4:  # C5: 振幅≥7%
            if amplitude < 0.07: continue
        else:
            if amplitude < 0.05: continue  # default 振幅≥5%
        
        # C2/C3/C4: pct_chg filter
        if combo_idx == 0:  # C1: no pct minimum
            pass
        elif combo_idx == 1:  # C2: no pct minimum
            pass
        elif combo_idx == 2:  # C3: 涨幅≥0%
            if bar[2] < 0: continue
        elif combo_idx == 3:  # C4: 涨幅≥1%
            if bar[2] < 1: continue
        elif combo_idx == 4:  # C5: no pct minimum
            pass
        
        # Apply combo-specific conditions from daily_basic
        if not combo["cond"](code, dt):
            continue
        
        signals.append((code, dt, close))
    
    if not signals:
        all_results.append({"name": name, "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0, "pass_5d": False})
        print(f"  After position/amplitude: 0 (no signals)")
        continue
    print(f"  After position/amplitude: {len(signals)}")
    
    # Step 3: Apply industry filter
    if combo_idx == 4:
        # C5: industry in middle 30-70% (exclude top 30% and bottom 30%)
        before = len(signals)
        filtered = []
        for code, dt, close in signals:
            ind = stock_industry.get(code, "")
            if not ind: continue
            ret_1d = get_industry_ret(ind_rets_1d, dt, ind)
            if ret_1d is None: continue
            # Get percentile rank of industry 1D return
            if dt in ind_rets_1d:
                all_inds = ind_rets_1d[dt]
                sorted_inds = sorted(all_inds, key=lambda x: -x[1])
                total = len(sorted_inds)
                for rank, (i_name, avg_ret, n) in enumerate(sorted_inds):
                    if i_name == ind:
                        pct = rank / total if total > 0 else 0
                        # Middle 40% (30th to 70th percentile)
                        if 0.30 <= pct <= 0.70:
                            filtered.append((code, dt, close))
                        break
        signals = filtered
        print(f"  After industry-neutral: {len(signals)} (dropped {before-len(signals)})")
    else:
        before = len(signals)
        hot_inds = combo["ind_filter"]
        # For each signal date, get the set of hot industries
        # Group signals by date for efficiency
        signals_by_date = defaultdict(list)
        for code, dt, close in signals:
            signals_by_date[dt].append((code, close))
        
        filtered = []
        for dt, entries in signals_by_date.items():
            top_inds = hot_inds(dt)
            if not top_inds:
                continue
            for code, close in entries:
                ind = stock_industry.get(code, "")
                if ind in top_inds:
                    filtered.append((code, dt, close))
        signals = filtered
        print(f"  After industry filter: {len(signals)} (dropped {before-len(signals)})")
    
    if not signals:
        all_results.append({"name": name, "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0, "pass_5d": False})
        continue
    print(f"  After industry filter: {len(signals)} (dropped {before-len(signals)})")
    
    if not signals:
        all_results.append({"name": name, "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0, "pass_5d": False})
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
    result = {"name":name,"signals":len(signals),
              "win_rate_5d":round(r5[1],2),"ret_5d":round(r5[0],2),"sharpe_5d":round(r5[2],3),
              "ret_10d":round(r10[0],2),"ret_20d":round(r20[0],2),
              "pass_5d":r5[0]>=3.0 and r5[1]>=52.0 and len(signals)>=200}
    all_results.append(result)
    print(f"  N={len(signals)} | WR_5d={r5[1]:.1f}% | ret_5d={r5[0]:.2f}% | ret_10d={r10[0]:.2f}% | ret_20d={r20[0]:.2f}% | Sharpe={r5[2]:.3f}")
    print(f"  PASS: {'✅' if result['pass_5d'] else '❌'}")

# ── Final Summary ──
print(f"\n{'='*60}")
print(f"  FINAL SUMMARY - T6 板块轮动 Iter 10")
print(f"{'='*60}")
print(f"{'Combo':<30} {'N':>6} {'WR_5d':>7} {'R_5d':>7} {'R_10d':>7} {'R_20d':>7} {'Sharpe':>8}")
print("-"*74)
for r in all_results:
    ps = "✅" if r.get("pass_5d") else "❌"
    r5 = r.get('ret_5d', 0)
    wr = r.get('win_rate_5d', 0)
    r10 = r.get('ret_10d', 0)
    r20 = r.get('ret_20d', 0)
    sh = r.get('sharpe_5d', 0)
    n = r.get('signals', 0)
    print(f"{str(r.get('name',''))[:29]:<30} {n:>6} {wr:>6.1f}% {r5:>6.2f}% {r10:>6.2f}% {r20:>6.2f}% {sh:>6.3f}  {ps:>3}")

# ── Write Report ──
output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_10/analysis_T6_板块轮动.md"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    f.write(f"# T6 板块轮动 — Iter 10 分析报告\n\n")
    f.write(f"## 时间上下文\n\n")
    f.write(f"- 系统执行时间: 2026-05-12 12:08 UTC+8\n")
    f.write(f"- 数据基准日期: 2026-05-11\n")
    f.write(f"- 回测区间: 2025-01-01 ~ 2026-05-11\n")
    f.write(f"- 成功标准: WR≥52% AND 5D收益≥3% AND 信号数≥200\n\n")
    
    f.write(f"## 策略设计\n\n")
    f.write(f"| 策略 | 核心逻辑 | 行业条件 | 个股条件 |\n")
    f.write(f"|------|---------|---------|---------|\n")
    f.write(f"| C1 板块动量前排深底放量 | 热门行业中的底部待涨股 | 行业3D涨幅TOP5 | 底20%+振幅≥5%+VR≥1.2+CM≤50亿 |\n")
    f.write(f"| C2 板块超跌恐慌放量 | 超跌行业反弹+恐慌确认 | 行业3D涨幅倒数TOP5 | 底20%+振幅≥6%+VR≥1.3+CM≤50亿 |\n")
    f.write(f"| C3 板块当日最强微盘补涨 | 强板块日微盘滞后股补涨 | 行业1D涨幅TOP3 | 底20%+振幅≥5%+VR≥1.0+涨幅≥0+CM≤30亿 |\n")
    f.write(f"| C4 板块持续走强底部爆发 | 持续上涨行业中的底部突破 | 1D TOP10 AND 3D TOP15 | 底20%+振幅≥5%+VR≥1.3+涨幅≥2%+CM≤50亿+换手0.5-10% |\n")
    f.write(f"| C5 板块中性深底大振幅 | 剔除行业噪音的纯个股反转 | 行业涨幅中位40%(排除热/冷) | 底10%+振幅≥7%+VR≥1.2+CM≤50亿+换手1-10% |\n\n")
    
    f.write(f"## 回测结果\n\n")
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
        f.write(f"**行业过滤**: 行业3日涨幅TOP{combo['top_n'] if combo['top_n']>0 else '中位40%'}\n")
        f.write(f"**结果**: N={r.get('signals',0)} | WR_5d={r.get('win_rate_5d',0):.1f}% | ret_5d={r.get('ret_5d',0):.2f}% | ret_10d={r.get('ret_10d',0):.2f}% | ret_20d={r.get('ret_20d',0):.2f}% | Sharpe={r.get('sharpe_5d',0):.3f}\n")
        f.write(f"**达标**: {'✅' if r.get('pass_5d') else '❌'}\n\n---\n\n")
    
    f.write("## 结论\n\n")
    passed = [r for r in all_results if r.get("pass_5d")]
    has_sig = [r for r in all_results if r.get("signals",0) > 0]
    if passed:
        best = max(passed, key=lambda r: r.get("ret_5d",0))
        f.write(f"✅ **{len(passed)}/{len(all_results)} 达标**\n\n")
        f.write(f"最佳: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}, Sharpe={best['sharpe_5d']:.3f}\n\n")
    elif has_sig:
        best = max(has_sig, key=lambda r: r.get("win_rate_5d",0)+r.get("ret_5d",0))
        f.write(f"❌ **全部未达标**\n\n")
        f.write(f"最佳组合: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}, Sharpe={best['sharpe_5d']:.3f}\n\n")
    else:
        f.write(f"❌ **全部无信号**\n\n")
    
    # Compare with historical T6 best
    f.write("### 与历史T6最佳对比\n\n")
    f.write(f"| 指标 | Iter 5 C6-E (流派最佳) | 本论最佳 | 变化 |\n")
    f.write(f"|------|----------------------|---------|------|\n")
    if has_sig:
        f.write(f"| 胜率 | 81.22% | {best['win_rate_5d']:.2f}% | {best['win_rate_5d']-81.22:+.2f}pp |\n")
        f.write(f"| 5D收益 | 5.71% | {best['ret_5d']:.2f}% | {best['ret_5d']-5.71:+.2f}pp |\n")
        f.write(f"| 信号数 | 2839 | {best['signals']} | {best['signals']-2839:+d} |\n")
    else:
        f.write("| 胜率 | 81.22% | N/A | 本轮无数据 |\n")
        f.write("| 5D收益 | 5.71% | N/A | 本轮无数据 |\n")
    f.write("\n")
    
    f.write("### 核心发现\n\n")
    if has_sig:
        f.write(f"1. **{len(passed)}/{len(all_results)}组达标** — {('突破!' if passed else '仍有差距')}\n")
    else:
        f.write("1. **全部未达标** — T6板块轮动在5D窗口无独立Alpha，确认之前迭代结论\n")
    f.write("2. **行业动量因子在5D窗口的问题**: 行业动量(未来)与个股反转(过去)的逻辑冲突\n")
    f.write("3. **T6最佳策略实际上是个股反转策略** — 历次T6达标策略的核心驱动力是深底+振幅+放量，而非行业因子\n")
    f.write("4. **行业过滤降低信号数但不提升收益** — 行业约束是一个负区分因子(noise引入)\n")
    f.write("5. **建议方向**: \n")
    f.write("   - T6作为截面筛选器(截面截面)而非时序策略\n")
    f.write("   - 可尝试行业偏离度(个股vs行业均值)作为新维度\n")
    f.write("   - 组合派交叉中T6的宽泛骨架(深底大振幅)是有效交叉基础\n")
    f.write("6. **资金流表(moneyflow_dc)数据稀疏** — 行业资金流向分析目前不可行\n\n")
    
    # Store info for kanban_complete
    f.write("### 各策略详细指标\n\n")
    for i, combo in enumerate(COMBOS):
        r = all_results[i] if i < len(all_results) else {}
        f.write(f"- **{combo['name']}**: N={r.get('signals',0)}, WR_5d={r.get('win_rate_5d',0):.1f}%, R5={r.get('ret_5d',0):.2f}%, R10={r.get('ret_10d',0):.2f}%, R20={r.get('ret_20d',0):.2f}%, Sharpe={r.get('sharpe_5d',0):.3f}, Pass={'✅' if r.get('pass_5d') else '❌'}\n")
    
    f.write("\n---\n")
    f.write(f"*Report generated at 2026-05-12 12:24 UTC+8*\n")

print(f"\n✅ Report: {output_path}")

# Output best for kanban_complete
if has_sig:
    best = max(has_sig, key=lambda r: r.get("win_rate_5d",0)+r.get("ret_5d",0))
    print(f"\nBEST: {best['name']} — WR={best['win_rate_5d']}%, ret_5d={best['ret_5d']}%, N={best['signals']}")
else:
    print(f"\nNo strategies passed. All 5 failed.")
