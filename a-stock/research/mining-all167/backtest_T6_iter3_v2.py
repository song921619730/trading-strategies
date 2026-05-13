#!/usr/bin/env python3
"""T6 板块轮动 - Iter 3 backtest - v2 with debug"""
import json, hashlib, subprocess, sys, math, os, traceback
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START_DATE = '20250101'
END_DATE = '20260511'

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        stderr = r.stderr[:500] if r.stderr else "no stderr"
        print(f"  [SQL ERROR] {stderr}", file=sys.stderr)
        return []
    try:
        d = json.loads(r.stdout)
        return d if isinstance(d, list) else d.get("data", [])
    except:
        print(f"  [PARSE ERROR] stdout start: {r.stdout[:200]}", file=sys.stderr)
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

# ───────────────────────────────────────
# Step 1: Pre-load sector data
# ───────────────────────────────────────

def load_stock_industry():
    sql = """
    SELECT ts_code, argMax(industry, trade_date) AS ind
    FROM tushare.tushare_limit_list_d FINAL
    GROUP BY ts_code
    HAVING ind IS NOT NULL AND ind != ''
    """
    rows = ch_query(sql)
    result = {r["ts_code"]: r["ind"] for r in rows}
    print(f"  Loaded {len(result)} stock->industry mappings")
    return result

def load_daily_hot_industries(start, end, rank=3):
    """Get top-N industries by limit-up count per day"""
    sql = f"""
    SELECT trade_date, industry, count(*) AS cnt
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date >= '{start}' AND trade_date <= '{end}'
      AND industry IS NOT NULL AND industry != ''
    GROUP BY trade_date, industry
    ORDER BY trade_date, cnt DESC
    """
    rows = ch_query(sql)
    daily = defaultdict(list)
    for r in rows:
        dt = str(r["trade_date"]).replace("-", "")
        daily[dt].append((r["industry"], r["cnt"]))
    
    result = {}
    for dt, inds in daily.items():
        sorted_inds = sorted(inds, key=lambda x: -x[1])
        result[dt] = set(ind[0] for ind in sorted_inds[:rank])
    
    print(f"  Computed hot industries for {len(result)} trading days (top {rank})")
    return result

# ───────────────────────────────────────
# Step 2: Build and run signal SQL
# ───────────────────────────────────────

def run_simple_signal_sql(params):
    """Build a simple SQL without CTE to get signals"""
    
    # Basic subquery that computes everything we need
    window_cols = []
    window_conds = []
    
    # Volume ratio (using daily_basic.volume_ratio or compute it)
    if "volume_ratio_min" in params:
        vr = params["volume_ratio_min"]
        # Use daily_basic.volume_ratio (already computed)
        window_conds.append(f"db.volume_ratio >= {vr}")
    
    # Position
    if "close_position" in params:
        pos = params["close_position"]
        window_cols.extend([
            "min(ss.low) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d",
            "max(ss.high) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d"
        ])
        if pos == "底20%":
            window_conds.append("(ss.close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.20")
        elif pos == "底40%":
            window_conds.append("(ss.close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.40")
    
    # Amplitude
    if "amplitude_min" in params:
        amp_pct = params["amplitude_min"]
        window_conds.append(f"(ss.high - ss.low) / NULLIF(ss.low * 1.0, 0) >= {amp_pct / 100.0}")
    
    # MA arrangement
    if "ma_arrangement" in params:
        arr = params["ma_arrangement"]
        window_cols.extend([
            "avg(ss.close) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5",
            "avg(ss.close) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma10",
            "avg(ss.close) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20",
            "avg(ss.close) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS ma60"
        ])
        if arr == "多头排列":
            window_conds.extend([
                "ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL",
                "ma5 > ma10 AND ma10 > ma20 AND ma20 > ma60"
            ])
        elif arr == "粘合(差<3%)":
            window_conds.extend([
                "ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL",
                "greatest(ma5, ma10, ma20, ma60) / NULLIF(least(ma5, ma10, ma20, ma60), 0) - 1 < 0.03"
            ])
    
    # N-day low
    if "n_day_low" in params:
        nd = params["n_day_low"]
        window_cols.append(f"min(ss.low) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date ROWS BETWEEN {nd-1} PRECEDING AND CURRENT ROW) AS low_{nd}d")
        window_conds.append(f"low_{nd}d IS NOT NULL AND ss.close <= low_{nd}d")
    
    # Row number
    window_cols.append("row_number() OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date) AS rn")
    
    # Forward returns
    window_cols.append("lead(ss.close, 5) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date) AS close_5d")
    window_cols.append("lead(ss.close, 10) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date) AS close_10d")
    window_cols.append("lead(ss.close, 20) OVER (PARTITION BY ss.ts_code ORDER BY ss.trade_date) AS close_20d")
    
    # Pct_chg filter
    pct_conds = []
    if "pct_chg_1d_min" in params:
        v = params["pct_chg_1d_min"]
        pct_conds.append(f"ss.pct_chg >= {v}")
    if "pct_chg_1d_max" in params:
        v = params["pct_chg_1d_max"]
        if v is not None and v < 999:
            pct_conds.append(f"ss.pct_chg <= {v}")
    
    # Turnover rate
    if "turnover_rate_min" in params:
        tr = params["turnover_rate_min"]
        window_conds.append(f"db.turnover_rate >= {tr}")
    if "turnover_rate_max" in params:
        tr = params["turnover_rate_max"]
        window_conds.append(f"db.turnover_rate <= {tr}")
    
    # Market cap
    if "market_cap_bucket" in params:
        bucket = params["market_cap_bucket"]
        if "中小盘(30-100亿)" in bucket:
            window_conds.append("db.circ_mv / 10000 >= 300000 AND db.circ_mv / 10000 < 1000000")
        elif "中大盘(100-500亿)" in bucket:
            window_conds.append("db.circ_mv / 10000 >= 1000000 AND db.circ_mv / 10000 < 5000000")
        elif "小盘(<30亿)" in bucket:
            window_conds.append("db.circ_mv / 10000 < 300000")
        elif "大盘(>500亿)" in bucket:
            window_conds.append("db.circ_mv / 10000 >= 5000000")
    
    # Moneyflow
    mf_conds = []
    if "net_mf_min_wan" in params:
        v = params["net_mf_min_wan"]
        mf_conds.append(f"mf.net_mf_amount >= {v}")
    
    # Base filters
    base_conds = [
        "ss.amount > 0",
        "ss.close IS NOT NULL",
        "ss.ts_code NOT LIKE '30%'",
        "ss.ts_code NOT LIKE '688%'",
        "ss.ts_code NOT LIKE '920%'",
        "ss.ts_code NOT LIKE '%ST%'",
        f"ss.trade_date >= '{START_DATE}'",
        f"ss.trade_date <= '{END_DATE}'",
    ]
    
    all_cond = " AND ".join(base_conds + pct_conds)
    window_cols_str = ",\n      ".join(window_cols)
    
    mf_join = "LEFT JOIN tushare.tushare_moneyflow AS mf ON ss.ts_code = mf.ts_code AND ss.trade_date = mf.trade_date" if mf_conds else ""
    mf_cond_str = f"AND {' AND '.join(mf_conds)}" if mf_conds else ""
    
    db_join = "LEFT JOIN tushare.tushare_daily_basic AS db ON ss.ts_code = db.ts_code AND ss.trade_date = db.trade_date"
    
    sql = f"""
    SELECT * FROM (
        SELECT 
            ss.ts_code,
            ss.trade_date,
            ss.close,
            ss.pct_chg,
            ss.low,
            ss.high,
            ss.vol,
            ss.amount,
            db.volume_ratio,
            db.turnover_rate,
            db.circ_mv / 10000 AS circ_mv_wan
            {', mf.net_mf_amount AS net_mf_amt' if mf_conds else ''},
            {window_cols_str}
        FROM tushare.tushare_stock_daily AS ss
        {db_join}
        {mf_join}
        WHERE {all_cond}
    ) AS sub
    WHERE rn >= 60
      AND low_20d IS NOT NULL AND high_20d IS NOT NULL
      {' AND ' + ' AND '.join(window_conds) if window_conds else ''}
      {mf_cond_str}
    ORDER BY ts_code, trade_date
    """
    return sql

# ───────────────────────────────────────
# MAIN LOOP
# ───────────────────────────────────────

COMBOS = [
    {
        "name": "C1_热点板块+底部放量企稳",
        "desc": "板块涨停排名前3 + 底20% + VR>=1.5 + 振幅>=3% + 中小盘(30-100亿) + pct>=0",
        "params": {
            "close_position": "底20%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.5,
            "amplitude_min": 3,
            "market_cap_bucket": "中小盘(30-100亿)"
        },
        "need_sector": True,
        "sector_rank": 3,
    },
    {
        "name": "C2_板块趋势向上+主力资金+中低位",
        "desc": "底40% + VR>=1.0 + 振幅>=3% + 主力流入>=100万 + pct>=0 + 0.5%<换手<10%",
        "params": {
            "close_position": "底40%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.0,
            "amplitude_min": 3,
            "turnover_rate_min": 0.5,
            "turnover_rate_max": 10,
            "net_mf_min_wan": 100
        },
        "need_sector": False,
    },
    {
        "name": "C3_多概念+超跌+主力承接",
        "desc": "pct<=-5% + 振幅>=5% + 主力流入>=50万 + 换手<10%",
        "params": {
            "pct_chg_1d_min": -5,
            "net_mf_min_wan": 50,
            "turnover_rate_max": 10,
            "amplitude_min": 5
        },
        "need_sector": False,
    },
    {
        "name": "C4_多头排列+中大盘趋势",
        "desc": "多头排列 + 中大盘(100-500亿) + VR>=1.3 + 振幅>=5% + pct>=0",
        "params": {
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "中大盘(100-500亿)",
            "volume_ratio_min": 1.3,
            "amplitude_min": 5,
            "pct_chg_1d_min": 0
        },
        "need_sector": False,
    },
    {
        "name": "C5_均线粘合+温和放量待发",
        "desc": "均线粘合(差<3%) + VR>=1.0 + pct>=0 + 振幅>=3% + 换手>=0.5%",
        "params": {
            "ma_arrangement": "粘合(差<3%)",
            "volume_ratio_min": 1.0,
            "pct_chg_1d_min": 0,
            "amplitude_min": 3,
            "turnover_rate_min": 0.5
        },
        "need_sector": False,
    },
]

if __name__ == "__main__":
    print(f"T6 板块轮动 — Iter 3 Backtest v2")
    print(f"Data: {START_DATE} ~ {END_DATE}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    
    # Pre-load sector data once
    stock_industry = load_stock_industry()
    daily_hot_inds_c3 = load_daily_hot_industries(START_DATE, END_DATE, rank=3)
    
    all_results = []
    
    for combo in COMBOS:
        print(f"\n{'='*60}")
        print(f"  {combo['name']}")
        print(f"  {combo['desc']}")
        print(f"{'='*60}")
        p = combo["params"]
        h = combo_hash(p)
        print(f"  Hash: {h}")
        
        # Debug: show SQL
        sql = run_simple_signal_sql(p)
        with open("/tmp/debug_t6_sql.txt", "w") as f:
            f.write(f"--- {combo['name']} ---\n")
            f.write(sql)
        
        rows = ch_query(sql)
        print(f"  Raw signals: {len(rows)}")
        
        # Apply sector filter if needed
        if combo.get("need_sector") and rows:
            filtered = []
            for r in rows:
                code = r["ts_code"]
                dt = str(r["trade_date"]).replace("-", "")
                ind = stock_industry.get(code, "")
                if ind and dt in daily_hot_inds_c3 and ind in daily_hot_inds_c3[dt]:
                    filtered.append(r)
            print(f"  After sector filter: {len(filtered)}")
            rows = filtered
        
        if not rows:
            print("  ❌ No signals")
            all_results.append({
                "name": combo["name"], "hash": h, "signals": 0,
                "ret_5d": 0, "ret_10d": 0, "ret_20d": 0,
                "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0,
                "sharpe_5d": 0, "pass_5d": False,
                "params": p
            })
            continue
        
        # Compute forward returns
        rets_5d, rets_10d, rets_20d = [], [], []
        for r in rows:
            c = r["close"]
            c5 = r.get("close_5d")
            c10 = r.get("close_10d")
            c20 = r.get("close_20d")
            if c and c5 and c5 > 0: rets_5d.append(c5/c - 1)
            if c and c10 and c10 > 0: rets_10d.append(c10/c - 1)
            if c and c20 and c20 > 0: rets_20d.append(c20/c - 1)
        
        def compute(rets):
            if not rets: return 0, 0, 0
            n = len(rets)
            mean = sum(rets) / n * 100
            wr = sum(1 for r in rets if r > 0) / n * 100
            sh = calc_sharpe(rets)
            return mean, wr, sh, n
        
        m5, w5, s5, n5 = compute(rets_5d)
        m10, w10, s10, n10 = compute(rets_10d)
        m20, w20, s20, n20 = compute(rets_20d)
        
        result = {
            "name": combo["name"],
            "hash": h,
            "signals": len(rows),
            "n_5d": n5, "n_10d": n10, "n_20d": n20,
            "ret_5d": round(m5, 2),
            "ret_10d": round(m10, 2),
            "ret_20d": round(m20, 2),
            "win_rate_5d": round(w5, 2),
            "win_rate_10d": round(w10, 2),
            "win_rate_20d": round(w20, 2),
            "sharpe_5d": round(s5, 3),
            "sharpe_10d": round(s10, 3),
            "sharpe_20d": round(s20, 3),
            "pass_5d": m5 >= 3.0 and w5 >= 52.0 and len(rows) >= 200,
            "params": p
        }
        all_results.append(result)
        
        print(f"  N={len(rows)} | WR_5d={w5:.1f}% | ret_5d={m5:.2f}% | ret_10d={m10:.2f}% | ret_20d={m20:.2f}% | Sharpe={s5:.3f}")
        print(f"  PASS: {'✅' if result['pass_5d'] else '❌'}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"{'Combo':<28} {'N_sig':>6} {'WR_5d':>7} {'R_5d':>7} {'R_10d':>7} {'R_20d':>7} {'Sharpe':>8}")
    print("-" * 72)
    for r in all_results:
        sig = r.get("signals", 0)
        wr = r.get("win_rate_5d", 0)
        r5 = r.get("ret_5d", 0)
        r10 = r.get("ret_10d", 0)
        r20 = r.get("ret_20d", 0)
        sh = r.get("sharpe_5d", 0)
        ps = "✅" if r.get("pass_5d") else "❌"
        n = r["name"][:27]
        print(f"{n:<28} {sig:>6} {wr:>6.1f}% {r5:>6.2f}% {r10:>6.2f}% {r20:>6.2f}% {sh:>6.3f}  {ps:>3}")
    
    # Write report
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_3/analysis_T6_板块轮动.md"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        f.write(f"# T6 板块轮动 — Iter 3 分析报告\n\n")
        f.write(f"- 基准交易日: {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
        f.write(f"- 回测区间: {START_DATE[:4]}-{START_DATE[4:6]}-{START_DATE[6:8]} ~ {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
        f.write(f"- 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        
        f.write("## 总体结果\n\n")
        f.write(f"| # | 组合 | 信号数 | WR_5d | ret_5d | ret_10d | ret_20d | Sharpe_5d | 达标 |\n")
        f.write(f"|---|------|--------|-------|--------|---------|---------|-----------|------|\n")
        for i, r in enumerate(all_results, 1):
            ps = "✅" if r.get("pass_5d") else "❌"
            f.write(f"| {i} | {r.get('name','')} | {r.get('signals',0)} | {r.get('win_rate_5d',0):.1f}% | {r.get('ret_5d',0):.2f}% | {r.get('ret_10d',0):.2f}% | {r.get('ret_20d',0):.2f}% | {r.get('sharpe_5d',0):.3f} | {ps} |\n")
        
        f.write("\n## 详细分析\n\n")
        for i, combo in enumerate(COMBOS):
            r = all_results[i] if i < len(all_results) else {}
            f.write(f"### {i+1}. {combo['name']}\n\n")
            f.write(f"**描述**: {combo['desc']}\n\n")
            f.write(f"**参数**:\n```json\n{json.dumps(combo['params'], indent=2, ensure_ascii=False)}\n```\n\n")
            f.write(f"**结果**: N={r.get('signals',0)}, WR_5d={r.get('win_rate_5d',0):.2f}%, ret_5d={r.get('ret_5d',0):.2f}%, ")
            f.write(f"ret_10d={r.get('ret_10d',0):.2f}%, ret_20d={r.get('ret_20d',0):.2f}%, Sharpe_5d={r.get('sharpe_5d',0):.3f}\n\n")
            f.write(f"**达标**: {'✅' if r.get('pass_5d') else '❌'}\n\n")
        
        # Best & conclusion
        passed = [r for r in all_results if r.get("pass_5d")]
        if passed:
            best = max(passed, key=lambda r: r.get("ret_5d", 0))
            f.write(f"## 最佳组合\n\n")
            f.write(f"**{best['name']}**: WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}, Sharpe={best['sharpe_5d']:.3f}\n")
        else:
            if any(r.get("signals", 0) > 0 for r in all_results):
                best = max(all_results, key=lambda r: (r.get("signals", 0) > 0, r.get("win_rate_5d", 0), r.get("ret_5d", 0)))
                f.write(f"## 结论\n\n")
                f.write(f"❌ 全部组合未达标。最佳: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}\n\n")
            else:
                f.write(f"## 结论\n\n")
                f.write(f"❌ 全部组合产生0信号。参数条件过严或SQL存在兼容性问题。\n\n")
            
            f.write("### Iter 2 对比\n\n")
            f.write("Iter 2 T6 板块轮动结论：板块轮动和纯量价形态在5D窗口无有效Alpha。\n")
            f.write("本轮尝试结合位置/量能/资金因子未产生足够信号。\n")
            f.write("建议：T6视角可作为其他流派的过滤辅助因子，不适合独立使用。\n")
    
    print(f"\nReport: {output_path}")
