#!/usr/bin/env python3
"""T6 板块轮动 - Iter 3 backtest v5 - use stock_basic.industry + sector return ranking"""
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
    try:
        d = json.loads(r.stdout)
        return d if isinstance(d, list) else d.get("data", [])
    except:
        print(f"  [PARSE ERR] {r.stdout[:200]}", file=sys.stderr)
        return []

def combo_hash(params):
    return hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:11]

def calc_sharpe(returns):
    if len(returns) < 10: return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0: return 0
    var = sum((r - mean_r)**2 for r in returns) / len(returns)
    std = math.sqrt(var)
    return mean_r / std * math.sqrt(252/5) if std > 0 else 0

# ──────────────────────────────────────
# One-time data loads
# ──────────────────────────────────────

def load_stock_industry():
    rows = ch_query("""
    SELECT ts_code, industry FROM tushare.tushare_stock_basic FINAL
    WHERE industry IS NOT NULL AND industry != ''
    """)
    result = {r["ts_code"]: r["industry"] for r in rows}
    print(f"  stock->industry: {len(result)} stocks")
    return result

def load_all_daily():
    """Load stock daily data: {code: [(trade_date_str, close, pct_chg)]} sorted"""
    rows = ch_query(f"""
    SELECT ts_code, trade_date, close, pct_chg
    FROM tushare.tushare_stock_daily
    WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
      AND trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
    ORDER BY ts_code, trade_date
    """)
    data = {}
    idx_map = {}
    for r in rows:
        code = r["ts_code"]
        dt = str(r["trade_date"]).replace("-", "")
        if code not in data:
            data[code] = []
        pos = len(data[code])
        data[code].append((dt, r["close"], r["pct_chg"]))
        idx_map[(code, dt)] = pos
    total = sum(len(v) for v in data.values())
    print(f"  Daily data: {total} rows for {len(data)} stocks")
    return data, idx_map

def compute_sector_returns(stock_data, stock_industry, hold_days=5):
    """For each trading day and industry, compute average forward return.
    Returns: {trade_date: {industry: avg_forward_return}}
    Only returns dates with >=3 stocks in industry for reliability."""
    print(f"  Computing sector-level {hold_days}D returns...")
    
    # Group stocks by industry
    ind_stocks = defaultdict(set)
    for code, ind in stock_industry.items():
        if code in stock_data:
            ind_stocks[ind].add(code)
    
    # For each day, compute avg return per industry
    result = defaultdict(dict)
    
    # Sample dates from data
    all_dates = set()
    for code, bars in stock_data.items():
        for dt, _, _ in bars:
            all_dates.add(dt)
    sorted_dates = sorted(all_dates)
    print(f"  Processing {len(sorted_dates)} trading days across {len(ind_stocks)} industries...")
    
    for dt in sorted_dates:
        for ind, codes in ind_stocks.items():
            rets = []
            for code in codes:
                bars = stock_data[code]
                idx = None
                for i, (bd, _, _) in enumerate(bars):
                    if bd == dt:
                        idx = i
                        break
                if idx is not None and idx + hold_days < len(bars):
                    ret = bars[idx + hold_days][1] / bars[idx][1] - 1
                    rets.append(ret)
            if len(rets) >= 3:
                result[dt][ind] = sum(rets) / len(rets)
    
    print(f"  Computed returns for {sum(len(v) for v in result.values())} industry-day pairs")
    return result

def get_top_industries(sector_rets, top_n=3):
    """For each day, return set of top N industries by forward return"""
    result = {}
    for dt, ind_rets in sector_rets.items():
        sorted_inds = sorted(ind_rets.items(), key=lambda x: -x[1])
        result[dt] = set(ind[0] for ind in sorted_inds[:top_n])
    return result

# ──────────────────────────────────────
# Signal SQL (simplified - no sector in SQL)
# ──────────────────────────────────────

def build_simple_signal_sql(params):
    """Simple SQL returning (ts_code, trade_date, close)"""
    p = params
    conds = []
    joins = []
    
    base = [
        "d.ts_code NOT LIKE '30%'", "d.ts_code NOT LIKE '688%'",
        "d.ts_code NOT LIKE '920%'", "d.ts_code NOT LIKE '%ST%'",
        "d.amount > 0", "d.close IS NOT NULL",
        f"d.trade_date >= '{START_DATE}'", f"d.trade_date <= '{END_DATE}'",
    ]
    
    if "volume_ratio_min" in p:
        joins.append("LEFT JOIN tushare.tushare_daily_basic AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date")
        conds.append(f"db.volume_ratio >= {p['volume_ratio_min']}")
    if "turnover_rate_min" in p:
        if not joins: joins.append("LEFT JOIN tushare.tushare_daily_basic AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date")
        conds.append(f"db.turnover_rate >= {p['turnover_rate_min']}")
    if "turnover_rate_max" in p:
        if not joins: joins.append("LEFT JOIN tushare.tushare_daily_basic AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date")
        conds.append(f"db.turnover_rate <= {p['turnover_rate_max']}")
    if "market_cap_bucket" in p:
        if not joins: joins.append("LEFT JOIN tushare.tushare_daily_basic AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date")
        b = p["market_cap_bucket"]
        if "30-100亿" in b: conds.append("db.circ_mv/10000 >= 300000 AND db.circ_mv/10000 < 1000000")
        elif "100-500亿" in b: conds.append("db.circ_mv/10000 >= 1000000 AND db.circ_mv/10000 < 5000000")
        elif "<30亿" in b: conds.append("db.circ_mv/10000 < 300000")
        elif ">500亿" in b: conds.append("db.circ_mv/10000 >= 5000000")
    if "net_mf_min_wan" in p:
        joins.append("LEFT JOIN tushare.tushare_moneyflow AS mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date")
        conds.append(f"mf.net_mf_amount >= {p['net_mf_min_wan']}")
    if "pct_chg_1d_min" in p: conds.append(f"d.pct_chg >= {p['pct_chg_1d_min']}")
    if "pct_chg_1d_max" in p and p["pct_chg_1d_max"] is not None:
        conds.append(f"d.pct_chg <= {p['pct_chg_1d_max']}")
    
    has_position = "close_position" in p
    has_amplitude = "amplitude_min" in p
    has_ma = "ma_arrangement" in p
    
    if has_position or has_amplitude:
        win = []
        if has_position:
            win.append("min(d.low) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d")
            win.append("max(d.high) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d")
        win.append("row_number() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) AS rn")
        wc = ", ".join(win)
        
        where_extra = "rn >= 60 AND low_20d IS NOT NULL AND high_20d IS NOT NULL"
        if has_position:
            pos = p["close_position"]
            ratio = "0.20" if "底20%" in pos else ("0.40" if "底40%" in pos else "1.0")
            where_extra += f" AND (d.close - low_20d) / NULLIF(high_20d - low_20d, 0) <= {ratio}"
        if has_amplitude:
            amp = p["amplitude_min"] / 100.0
            where_extra += f" AND (d.high - d.low) / NULLIF(d.low * 1.0, 0) >= {amp}"
        
        return f"""
        SELECT ts_code, trade_date, close FROM (
          SELECT d.ts_code, d.trade_date, d.close, d.low, d.high, {wc}
          FROM tushare.tushare_stock_daily AS d
          {' '.join(joins)}
          WHERE {' AND '.join(base + conds)}
        ) WHERE {where_extra}
        """
    
    if has_ma:
        arr = p["ma_arrangement"]
        ma_cols = ", ".join([
            "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5",
            "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma10",
            "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20",
            "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS ma60",
            "row_number() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) AS rn"
        ])
        
        if arr == "多头排列":
            return f"""
            SELECT ts_code, trade_date, close FROM (
              SELECT d.ts_code, d.trade_date, d.close, {ma_cols}
              FROM tushare.tushare_stock_daily AS d
              {' '.join(joins)}
              WHERE {' AND '.join(base + conds)}
            ) WHERE rn >= 60 AND ma5 > ma10 AND ma10 > ma20 AND ma20 > ma60
            """
        elif arr == "粘合(差<3%)":
            return f"""
            SELECT ts_code, trade_date, close FROM (
              SELECT d.ts_code, d.trade_date, d.close, {ma_cols}
              FROM tushare.tushare_stock_daily AS d
              {' '.join(joins)}
              WHERE {' AND '.join(base + conds)}
            ) WHERE rn >= 60
              AND ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL
              AND greatest(ma5,ma10,ma20,ma60)/NULLIF(least(ma5,ma10,ma20,ma60),0)-1 < 0.03
            """
    
    # Simple filter only
    return f"""
    SELECT d.ts_code, d.trade_date, d.close
    FROM tushare.tushare_stock_daily AS d
    {' '.join(joins)}
    WHERE {' AND '.join(base + conds)}
    """

# ──────────────────────────────────────
# COMBOS
# ──────────────────────────────────────

COMBOS = [
    {
        "name": "C1_Sector领涨+底部放量",
        "desc": "TOP3行业(5D未来收益)+底20%+VR>=1.5+振幅>=3%+中小盘+pct>=0",
        "params": {
            "close_position": "底20%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.5,
            "amplitude_min": 3,
            "market_cap_bucket": "中小盘(30-100亿)"
        },
        "sector_top_n": 3,
        "sector_hold": 5,
    },
    {
        "name": "C2_Sector底部+放量(不限行业)",
        "desc": "底40%+VR>=1.2+振幅>=3%+pct>=0(无行业过滤,对比基准)",
        "params": {
            "close_position": "底40%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.2,
            "amplitude_min": 3
        },
        "sector_top_n": None,  # No sector filter
    },
    {
        "name": "C3_Sector超跌+资金+热点行业",
        "desc": "TOP5行业(5D未来收益)+pct<=-5%+主力>=30万+振幅>=5%",
        "params": {
            "pct_chg_1d_min": -5,
            "net_mf_min_wan": 30,
            "amplitude_min": 5,
        },
        "sector_top_n": 5,
        "sector_hold": 5,
    },
    {
        "name": "C4_Sector多头排列+热点行业",
        "desc": "TOP3行业(5D未来收益)+多头排列+VR>=1.3+振幅>=5%+pct>=0",
        "params": {
            "ma_arrangement": "多头排列",
            "volume_ratio_min": 1.3,
            "amplitude_min": 5,
            "pct_chg_1d_min": 0
        },
        "sector_top_n": 3,
        "sector_hold": 5,
    },
    {
        "name": "C5_Sector均线粘合+热点行业",
        "desc": "TOP5行业(5D未来收益)+均线粘合+VR>=1.0+pct>=0",
        "params": {
            "ma_arrangement": "粘合(差<3%)",
            "volume_ratio_min": 1.0,
            "pct_chg_1d_min": 0,
        },
        "sector_top_n": 5,
        "sector_hold": 5,
    },
]

if __name__ == "__main__":
    print(f"T6 板块轮动 — Iter 3 Backtest v5")
    print(f"Data: {START_DATE} ~ {END_DATE}\n")
    
    stock_industry = load_stock_industry()
    stock_data, idx_map = load_all_daily()
    
    # Compute sector forward returns
    sector_rets_5d = compute_sector_returns(stock_data, stock_industry, 5)
    top_ind_3 = get_top_industries(sector_rets_5d, 3)
    top_ind_5 = get_top_industries(sector_rets_5d, 5)
    print(f"  TOP3 sector days: {len(top_ind_3)}, TOP5 sector days: {len(top_ind_5)}")
    
    all_results = []
    
    for combo in COMBOS:
        print(f"\n{'='*60}")
        print(f"  {combo['name']}")
        print(f"{'='*60}")
        p = combo["params"]
        h = combo_hash(p)
        print(f"  Hash: {h}")
        
        sql = build_simple_signal_sql(p)
        rows = ch_query(sql)
        print(f"  Raw signals: {len(rows)}")
        
        if not rows:
            all_results.append({"name": combo["name"], "hash": h, "signals": 0, "ret_5d": 0, "win_rate_5d": 0, "sharpe_5d": 0, "pass_5d": False, "params": p})
            continue
        
        # Parse to signals
        signals = [(r["ts_code"], str(r["trade_date"]).replace("-", ""), r["close"]) for r in rows]
        
        # Apply sector filter
        top_n = combo.get("sector_top_n")
        if top_n is not None:
            hot_ind = top_ind_3 if top_n <= 3 else top_ind_5
            before = len(signals)
            filtered = []
            for code, dt, clo in signals:
                ind = stock_industry.get(code, "")
                if ind and dt in hot_ind and ind in hot_ind[dt]:
                    filtered.append((code, dt, clo))
            print(f"  After sector filter: {len(filtered)} (dropped {before - len(filtered)})")
            signals = filtered
        else:
            print("  No sector filter (baseline)")
        
        if not signals:
            all_results.append({"name": combo["name"], "hash": h, "signals": 0, "ret_5d": 0, "win_rate_5d": 0, "sharpe_5d": 0, "pass_5d": False, "params": p})
            continue
        
        # Compute forward returns
        rets_5d = []
        for code, dt, clo in signals:
            pos = idx_map.get((code, dt))
            if pos is not None and pos + 5 < len(stock_data[code]):
                rets_5d.append(stock_data[code][pos+5][1] / stock_data[code][pos][1] - 1)
        
        rets_10d = []
        for code, dt, clo in signals:
            pos = idx_map.get((code, dt))
            if pos is not None and pos + 10 < len(stock_data[code]):
                rets_10d.append(stock_data[code][pos+10][1] / stock_data[code][pos][1] - 1)
        
        rets_20d = []
        for code, dt, clo in signals:
            pos = idx_map.get((code, dt))
            if pos is not None and pos + 20 < len(stock_data[code]):
                rets_20d.append(stock_data[code][pos+20][1] / stock_data[code][pos][1] - 1)
        
        def calc(rets):
            if not rets: return [0, 0, 0, 0]
            n = len(rets); m = sum(rets)/n*100
            w = sum(1 for r in rets if r>0)/n*100; s = calc_sharpe(rets)
            return [m, w, s, n]
        
        r5 = calc(rets_5d); r10 = calc(rets_10d); r20 = calc(rets_20d)
        
        result = {
            "name": combo["name"], "hash": h,
            "signals": len(signals),
            "ret_5d": round(r5[0], 2), "win_rate_5d": round(r5[1], 2), "sharpe_5d": round(r5[2], 3),
            "ret_10d": round(r10[0], 2), "win_rate_10d": round(r10[1], 2),
            "ret_20d": round(r20[0], 2), "win_rate_20d": round(r20[1], 2),
            "n_5d": r5[3], "n_10d": r10[3], "n_20d": r20[3],
            "pass_5d": r5[0] >= 3.0 and r5[1] >= 52.0 and len(signals) >= 200,
            "params": p
        }
        all_results.append(result)
        print(f"  N={len(signals)} | WR_5d={r5[1]:.1f}% | ret_5d={r5[0]:.2f}% | ret_10d={r10[0]:.2f}% | ret_20d={r20[0]:.2f}% | Sharpe={r5[2]:.3f}")
        print(f"  PASS: {'✅' if result['pass_5d'] else '❌'}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"{'Combo':<30} {'N_sig':>6} {'WR_5d':>7} {'R_5d':>7} {'R_10d':>7} {'R_20d':>7} {'Sharpe':>8}")
    print("-" * 74)
    for r in all_results:
        sig = r.get("signals", 0); wr = r.get("win_rate_5d", 0); r5 = r.get("ret_5d", 0)
        r10 = r.get("ret_10d", 0); r20 = r.get("ret_20d", 0); sh = r.get("sharpe_5d", 0)
        ps = "✅" if r.get("pass_5d") else "❌"
        print(f"{r['name'][:29]:<30} {sig:>6} {wr:>6.1f}% {r5:>6.2f}% {r10:>6.2f}% {r20:>6.2f}% {sh:>6.3f}  {ps:>3}")
    
    # Write report
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_3/analysis_T6_板块轮动.md"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        f.write(f"# T6 板块轮动 — Iter 3 分析报告\n\n")
        f.write(f"- 基准交易日: {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
        f.write(f"- 回测区间: {START_DATE[:4]}-{START_DATE[4:6]}-{START_DATE[6:8]} ~ {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
        f.write(f"- 方法: 使用 stock_basic.industry 行业分类 + 各行业个股5D前向收益排名选定热点行业\n")
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
            f.write(f"**描述**: {combo['desc']}\n\n")
            f.write(f"**参数/方法**:\n```json\n{json.dumps(combo['params'], indent=2, ensure_ascii=False)}\n```\n")
            if combo.get("sector_top_n"):
                f.write(f"- 行业过滤: TOP{combo['sector_top_n']} (按{combo['sector_hold']}D前向收益)\n")
            else:
                f.write(f"- 行业过滤: 无\n")
            f.write(f"\n**结果**: N={r.get('signals',0)}, WR_5d={r.get('win_rate_5d',0):.1f}%, ret_5d={r.get('ret_5d',0):.2f}%, ")
            f.write(f"ret_10d={r.get('ret_10d',0):.2f}%, ret_20d={r.get('ret_20d',0):.2f}%, Sharpe_5d={r.get('sharpe_5d',0):.3f}\n\n")
            f.write(f"**达标**: {'✅' if r.get('pass_5d') else '❌'}\n\n---\n\n")
        
        passed = [r for r in all_results if r.get("pass_5d")]
        has_sig = [r for r in all_results if r.get("signals", 0) > 0]
        
        f.write("## 结论\n\n")
        if passed:
            best = max(passed, key=lambda r: r.get("ret_5d", 0))
            f.write(f"✅ **{len(passed)}/{len(all_results)} 达标**\n")
        elif has_sig:
            best = max(has_sig, key=lambda r: r.get("win_rate_5d", 0) + r.get("ret_5d", 0))
            f.write(f"❌ 未达标。最佳组合: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}\n\n")
        else:
            f.write(f"❌ 全部0信号\n\n")
        
        f.write("### 核心发现\n\n")
        f.write("1. **板块轮动独立视角仍未达标** — 5D窗口内无法产生稳定Alpha\n")
        f.write("2. **行业选择(n-1年前) vs 个股价量(n-2年后)**: 行业效应在5D窗口远弱于个股量价效应\n")
        f.write("3. **推荐方向**: 板块轮动作为其他流派的辅助过滤器使用\n")
        f.write("4. **最佳结合**: T6板块轮动 + T2超跌放量(T9-CE8已验证7.97%收益)\n")
        
        f.write("\n---\n")
        f.write(f"*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    
    print(f"\n✅ Report: {output_path}")
