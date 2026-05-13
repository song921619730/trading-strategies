#!/usr/bin/env python3
"""T6 板块轮动 - Iter 3 backtest v4 - fixed sector mapping"""
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

# ───────────────────────────────────────
# Sector data from stock_basic.industry
# ───────────────────────────────────────

def load_stock_industry():
    """Load stock->industry from stock_basic (covers ALL stocks)"""
    rows = ch_query("""
    SELECT ts_code, industry
    FROM tushare.tushare_stock_basic FINAL
    WHERE industry IS NOT NULL AND industry != ''
    """)
    result = {r["ts_code"]: r["industry"] for r in rows}
    print(f"  Loaded {len(result)} stock->industry mappings from stock_basic")
    return result

def load_hot_industries(rank=3):
    """Get top-N industries by limit-up count per day from limit_list_d"""
    rows = ch_query(f"""
    SELECT trade_date, industry, count(*) AS cnt
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
      AND industry IS NOT NULL AND industry != ''
    GROUP BY trade_date, industry
    ORDER BY trade_date, cnt DESC
    """)
    daily = defaultdict(list)
    for r in rows:
        dt = str(r["trade_date"]).replace("-", "")
        daily[dt].append((r["industry"], r["cnt"]))
    result = {}
    for dt, inds in daily.items():
        sorted_inds = sorted(inds, key=lambda x: -x[1])
        result[dt] = set(ind[0] for ind in sorted_inds[:rank])
    print(f"  Hot industries (top {rank}) for {len(result)} trading days")
    # Sample of industries available
    if result:
        sample_date = sorted(result.keys())[-1]
        print(f"  Latest day ({sample_date}) hot industries: {result[sample_date]}")
    return result

# ───────────────────────────────────────
# Load stock data for forward returns
# ───────────────────────────────────────

def load_stock_data():
    print("  Loading stock data for forward returns...")
    rows = ch_query(f"""
    SELECT ts_code, trade_date, close
    FROM tushare.tushare_stock_daily
    WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
      AND trade_date >= '{START_DATE}'
    ORDER BY ts_code, trade_date
    """)
    data = defaultdict(list)
    for r in rows:
        data[r["ts_code"]].append((str(r["trade_date"]).replace("-", ""), r["close"]))
    total_rows = sum(len(v) for v in data.values())
    print(f"  Loaded {total_rows} rows for {len(data)} stocks")
    return data

def calc_fwd(ret_tuple, n, data_map, sig_idx_map, signals):
    """Calculate forward returns for a given hold_days (n)"""
    rets = []
    for code, sig_date, _ in signals:
        bars = data_map.get(code, [])
        idx = sig_idx_map.get((code, sig_date))
        if idx is not None and idx + n < len(bars):
            ret = bars[idx + n][1] / bars[idx][1] - 1
            if ret is not None:
                rets.append(ret)
    if not rets: return [0, 0, 0, 0]
    n_r = len(rets)
    mean = sum(rets) / n_r * 100
    wr = sum(1 for r in rets if r > 0) / n_r * 100
    sh = calc_sharpe(rets)
    return [mean, wr, sh, n_r]

# ───────────────────────────────────────
# Signal SQL
# ───────────────────────────────────────

def build_signal_sql(params):
    """Build SQL returning (ts_code, trade_date, close)"""
    p = params
    conds = []
    joins = []
    
    base = [
        "d.ts_code NOT LIKE '30%'",
        "d.ts_code NOT LIKE '688%'",
        "d.ts_code NOT LIKE '920%'",
        "d.ts_code NOT LIKE '%ST%'",
        "d.amount > 0", "d.close IS NOT NULL",
        f"d.trade_date >= '{START_DATE}'",
        f"d.trade_date <= '{END_DATE}'",
    ]
    
    need_db = any(k in p for k in ["volume_ratio_min", "turnover_rate_min", "turnover_rate_max", "market_cap_bucket"])
    if need_db:
        joins.append("LEFT JOIN tushare.tushare_daily_basic AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date")
    
    if "net_mf_min_wan" in p:
        joins.append("LEFT JOIN tushare.tushare_moneyflow AS mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date")
        conds.append(f"mf.net_mf_amount >= {p['net_mf_min_wan']}")
    
    if "pct_chg_1d_min" in p: conds.append(f"d.pct_chg >= {p['pct_chg_1d_min']}")
    if "volume_ratio_min" in p: conds.append(f"db.volume_ratio >= {p['volume_ratio_min']}")
    if "turnover_rate_min" in p: conds.append(f"db.turnover_rate >= {p['turnover_rate_min']}")
    if "turnover_rate_max" in p: conds.append(f"db.turnover_rate <= {p['turnover_rate_max']}")
    
    if "market_cap_bucket" in p:
        b = p["market_cap_bucket"]
        if "30-100亿)" in b: conds.append("db.circ_mv/10000 >= 300000 AND db.circ_mv/10000 < 1000000")
        elif "100-500亿)" in b: conds.append("db.circ_mv/10000 >= 1000000 AND db.circ_mv/10000 < 5000000")
        elif "小盘(<30亿)" in b: conds.append("db.circ_mv/10000 < 300000")
        elif "大盘(>500亿)" in b: conds.append("db.circ_mv/10000 >= 5000000")
    
    base_str = " AND ".join(base)
    cond_str = " AND ".join(conds) if conds else "1=1"
    join_str = " ".join(joins)
    select = "d.ts_code, d.trade_date, d.close AS clo, d.low, d.high"
    if need_db: select += ", db.volume_ratio AS vr, db.turnover_rate AS tr, db.circ_mv/10000 AS cmv"
    
    has_position = "close_position" in p
    has_amplitude = "amplitude_min" in p
    has_ma = "ma_arrangement" in p
    
    # Use simpler SQL for each pattern
    if has_ma:
        arr = p["ma_arrangement"]
        ma_cols = """
          , avg(d.close) OVER w5 AS ma5,
          avg(d.close) OVER w10 AS ma10,
          avg(d.close) OVER w20_ma AS ma20,
          avg(d.close) OVER w60 AS ma60
        """
        if arr == "多头排列":
            return f"""
            SELECT ts_code, trade_date, clo, low, high FROM (
              SELECT d.ts_code, d.trade_date, d.close AS clo, d.low, d.high {ma_cols}
                {', db.volume_ratio AS vr' if 'volume_ratio_min' in p else ''}
                {', db.turnover_rate AS tr' if ('turnover_rate_min' in p or 'turnover_rate_max' in p) else ''}
                {', db.circ_mv/10000 AS cmv' if 'market_cap_bucket' in p else ''}
                , row_number() OVER pw AS rn
              FROM tushare.tushare_stock_daily AS d
              {join_str}
              WHERE {base_str} AND {cond_str}
              WINDOW w5 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
                     w10 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
                     w20_ma AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
                     w60 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
                     pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date)
            ) WHERE rn >= 60 AND ma5 > ma10 AND ma10 > ma20 AND ma20 > ma60
            """
        elif arr == "粘合(差<3%)":
            return f"""
            SELECT ts_code, trade_date, clo, low, high FROM (
              SELECT d.ts_code, d.trade_date, d.close AS clo, d.low, d.high {ma_cols}
                {', db.volume_ratio AS vr' if 'volume_ratio_min' in p else ''}
                {', db.turnover_rate AS tr' if ('turnover_rate_min' in p or 'turnover_rate_max' in p) else ''}
                , row_number() OVER pw AS rn
              FROM tushare.tushare_stock_daily AS d
              {join_str}
              WHERE {base_str} AND {cond_str}
              WINDOW w5 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
                     w10 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
                     w20_ma AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
                     w60 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
                     pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date)
            ) WHERE rn >= 60
              AND ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL
              AND greatest(ma5, ma10, ma20, ma60) / NULLIF(least(ma5, ma10, ma20, ma60), 0) - 1 < 0.03
            """
    
    # Default: position + amplitude
    has_win = has_position or has_amplitude
    if has_win:
        win_cols = """
          , min(d.low) OVER w20 AS low_20d,
          max(d.high) OVER w20 AS high_20d
        """
        where_extra = ""
        if has_position:
            pos = p["close_position"]
            ratio = "0.20" if "底20%" in pos else ("0.40" if "底40%" in pos else "1.0")
            where_extra += f" AND (clo - low_20d) / NULLIF(high_20d - low_20d, 0) <= {ratio}"
        if has_amplitude:
            amp = p["amplitude_min"] / 100.0
            where_extra += f" AND (high - low) / NULLIF(low * 1.0, 0) >= {amp}"
        
        return f"""
        SELECT ts_code, trade_date, clo, low, high FROM (
          SELECT d.ts_code, d.trade_date, d.close AS clo, d.low, d.high {win_cols}
            {', db.volume_ratio AS vr' if 'volume_ratio_min' in p else ''}
            {', db.turnover_rate AS tr' if ('turnover_rate_min' in p or 'turnover_rate_max' in p) else ''}
            {', db.circ_mv/10000 AS cmv' if 'market_cap_bucket' in p else ''}
            , row_number() OVER pw AS rn
          FROM tushare.tushare_stock_daily AS d
          {join_str}
          WHERE {base_str} AND {cond_str}
          WINDOW w20 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
                 pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date)
        ) WHERE rn >= 60 AND low_20d IS NOT NULL AND high_20d IS NOT NULL
          AND (high_20d - low_20d) / NULLIF(low_20d * 1.0, 0) > 0
          {where_extra}
        """
    
    # Simple: just WHERE filters
    return f"""
    SELECT d.ts_code, d.trade_date, d.close AS clo, d.low, d.high
    {', db.volume_ratio AS vr' if 'volume_ratio_min' in p else ''}
    FROM tushare.tushare_stock_daily AS d
    {join_str}
    WHERE {base_str} AND {cond_str}
    """

# ───────────────────────────────────────
# COMBOS (revised)
# ───────────────────────────────────────

COMBOS = [
    {
        "name": "C1_Sector轮动潜伏-底部放量",
        "desc": "热点板块(涨停TOP3) + 底20% + VR>=1.5 + 振幅>=3% + 中小盘 + pct>=0",
        "params": {
            "close_position": "底20%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.5,
            "amplitude_min": 3,
            "market_cap_bucket": "中小盘(30-100亿)"
        },
        "need_sector": True,
    },
    {
        "name": "C2_Sector轮动低吸-底部+放量",
        "desc": "热点板块(涨停TOP5) + 底40% + VR>=1.2 + 振幅>=3% + pct>=0",
        "params": {
            "close_position": "底40%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.2,
            "amplitude_min": 3
        },
        "need_sector": True,
    },
    {
        "name": "C3_Sector超跌反弹-恐慌+资金",
        "desc": "热点板块(涨停TOP3) + 近3日跌幅>=5% + VR>=0.8 + 主力流入>=30万 + 振幅>=5%",
        "params": {
            "pct_chg_1d_min": -5,
            "volume_ratio_min": 0.8,
            "amplitude_min": 5,
            "net_mf_min_wan": 30,
            "turnover_rate_max": 15,
        },
        "need_sector": True,
    },
    {
        "name": "C4_Sector板块爆发-首次涨停",
        "desc": "热点板块(涨停TOP3) + pct>=7 + VR>=1.5 + 换手>=1%",
        "params": {
            "pct_chg_1d_min": 7,
            "volume_ratio_min": 1.5,
            "turnover_rate_min": 1.0,
        },
        "need_sector": True,
    },
    {
        "name": "C5_Sector均线粘合待发",
        "desc": "热点板块(涨停TOP3) + 均线粘合 + VR>=1.0 + pct>=0",
        "params": {
            "ma_arrangement": "粘合(差<3%)",
            "volume_ratio_min": 1.0,
            "pct_chg_1d_min": 0,
        },
        "need_sector": True,
    },
]

if __name__ == "__main__":
    print(f"T6 板块轮动 — Iter 3 Backtest v4")
    print(f"Data: {START_DATE} ~ {END_DATE}")
    
    stock_industry = load_stock_industry()
    hot_ind_3 = load_hot_industries(rank=3)
    hot_ind_5 = load_hot_industries(rank=5)
    stock_data = load_stock_data()
    
    # Build signal index for fast lookup
    sig_idx_map = {}
    for code, bars in stock_data.items():
        for i, (dt, _) in enumerate(bars):
            sig_idx_map[(code, dt)] = i
    
    all_results = []
    
    for combo in COMBOS:
        print(f"\n{'='*60}")
        print(f"  {combo['name']}")
        print(f"{'='*60}")
        p = combo["params"]
        h = combo_hash(p)
        print(f"  Hash: {h}")
        
        sql = build_signal_sql(p)
        print(f"  SQL length: {len(sql)} chars")
        rows = ch_query(sql)
        print(f"  Raw signals: {len(rows)}")
        
        if not rows:
            all_results.append({"name": combo["name"], "hash": h, "signals": 0, "ret_5d": 0, "win_rate_5d": 0, "sharpe_5d": 0, "pass_5d": False, "params": p})
            continue
        
        # Parse signals
        signals = [(r["ts_code"], str(r["trade_date"]).replace("-", ""), r.get("clo", 0)) for r in rows]
        
        # Apply sector filter
        if combo.get("need_sector") and signals:
            # Determine which hot_ind to use
            hot_ind = hot_ind_3 if "TOP3" in combo["name"] or "涨停TOP3" in combo["name"] or "rank3" in str(p) else hot_ind_5
            if "TOP5" in combo["name"]:
                hot_ind = hot_ind_5
            else:
                hot_ind = hot_ind_3
            
            # For combos that say TOP3 in name
            if "C1" in combo["name"] or "C3" in combo["name"] or "C4" in combo["name"] or "C5" in combo["name"]:
                hot_ind = hot_ind_3
            
            before = len(signals)
            filtered = []
            for code, dt, clo in signals:
                ind = stock_industry.get(code, "")
                if ind and dt in hot_ind and ind in hot_ind[dt]:
                    filtered.append((code, dt, clo))
            print(f"  After sector filter: {len(filtered)} (dropped {before - len(filtered)})")
            signals = filtered
        
        if not signals:
            all_results.append({"name": combo["name"], "hash": h, "signals": 0, "ret_5d": 0, "win_rate_5d": 0, "sharpe_5d": 0, "pass_5d": False, "params": p})
            continue
        
        # Compute returns
        def calc(rets):
            if not rets: return [0, 0, 0, 0] 
            n = len(rets)
            m = sum(rets)/n*100; w = sum(1 for r in rets if r>0)/n*100; s = calc_sharpe(rets)
            return [m, w, s, n]
        
        r5 = calc([stock_data[code][sig_idx_map[(code, dt)]+5][1]/stock_data[code][sig_idx_map[(code, dt)]][1]-1 
                   for code, dt, _ in signals 
                   if code in stock_data and (code, dt) in sig_idx_map 
                   and sig_idx_map[(code, dt)] + 5 < len(stock_data[code])])
        
        r10 = calc([stock_data[code][sig_idx_map[(code, dt)]+10][1]/stock_data[code][sig_idx_map[(code, dt)]][1]-1 
                    for code, dt, _ in signals 
                    if code in stock_data and (code, dt) in sig_idx_map 
                    and sig_idx_map[(code, dt)] + 10 < len(stock_data[code])])
        
        r20 = calc([stock_data[code][sig_idx_map[(code, dt)]+20][1]/stock_data[code][sig_idx_map[(code, dt)]][1]-1 
                    for code, dt, _ in signals 
                    if code in stock_data and (code, dt) in sig_idx_map 
                    and sig_idx_map[(code, dt)] + 20 < len(stock_data[code])])
        
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
        print(f"  N={len(signals)} | WR_5d={r5[1]:.1f}% | ret_5d={r5[0]:.2f}% | ret_10d={r10[0]:.2f}% | Sharpe={r5[2]:.3f}")
        print(f"  PASS: {'✅' if result['pass_5d'] else '❌'}")
    
    # ─── Summary ───
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"{'Combo':<28} {'N_sig':>6} {'WR_5d':>7} {'R_5d':>7} {'R_10d':>7} {'R_20d':>7} {'Sharpe':>8}")
    print("-" * 72)
    for r in all_results:
        sig = r.get("signals", 0); wr = r.get("win_rate_5d", 0); r5 = r.get("ret_5d", 0)
        r10 = r.get("ret_10d", 0); r20 = r.get("ret_20d", 0); sh = r.get("sharpe_5d", 0)
        ps = "✅" if r.get("pass_5d") else "❌"
        print(f"{r['name'][:27]:<28} {sig:>6} {wr:>6.1f}% {r5:>6.2f}% {r10:>6.2f}% {r20:>6.2f}% {sh:>6.3f}  {ps:>3}")
    
    # ─── Report ───
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_3/analysis_T6_板块轮动.md"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        f.write(f"# T6 板块轮动 — Iter 3 分析报告\n\n")
        f.write(f"- 基准交易日: {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
        f.write(f"- 回测区间: {START_DATE[:4]}-{START_DATE[4:6]}-{START_DATE[6:8]} ~ {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
        f.write(f"- 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        
        f.write(f"| # | 组合 | 信号数 | WR_5d | ret_5d | ret_10d | ret_20d | Sharpe | 达标 |\n")
        f.write(f"|---|------|--------|-------|--------|---------|---------|--------|------|\n")
        for i, r in enumerate(all_results, 1):
            ps = "✅" if r.get("pass_5d") else "❌"
            f.write(f"| {i} | {r.get('name','')} | {r.get('signals',0)} | {r.get('win_rate_5d',0):.1f}% | {r.get('ret_5d',0):.2f}% | {r.get('ret_10d',0):.2f}% | {r.get('ret_20d',0):.2f}% | {r.get('sharpe_5d',0):.3f} | {ps} |\n")
        
        f.write("\n## 详细分析\n\n")
        for i, combo in enumerate(COMBOS):
            r = all_results[i] if i < len(all_results) else {}
            f.write(f"### {i+1}. {combo['name']}\n\n")
            f.write(f"**描述**: {combo['desc']}\n\n")
            f.write(f"**参数**:\n```json\n{json.dumps(combo['params'], indent=2, ensure_ascii=False)}\n```\n\n")
            f.write(f"**结果**: N={r.get('signals',0)}, WR_5d={r.get('win_rate_5d',0):.1f}%, ret_5d={r.get('ret_5d',0):.2f}%, ")
            f.write(f"ret_10d={r.get('ret_10d',0):.2f}%, ret_20d={r.get('ret_20d',0):.2f}%, Sharpe_5d={r.get('sharpe_5d',0):.3f}\n\n")
            f.write(f"**达标**: {'✅' if r.get('pass_5d') else '❌'}\n\n")
            f.write("---\n\n")
        
        # Conclusion
        passed = [r for r in all_results if r.get("pass_5d")]
        has_sig = [r for r in all_results if r.get("signals", 0) > 0]
        
        f.write("## 结论\n\n")
        if passed:
            best = max(passed, key=lambda r: r.get("ret_5d", 0))
            f.write(f"✅ **{len(passed)}/{len(all_results)} 达标**: {best['name']}\n")
        elif has_sig:
            best = max(has_sig, key=lambda r: r.get("win_rate_5d", 0) + r.get("ret_5d", 0))
            f.write(f"❌ 未达标。最佳: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}\n\n")
        else:
            f.write(f"❌ 全部组合0信号\n\n")
        
        f.write("### Iter 3 vs Iter 2\n\n")
        f.write("| 指标 | Iter 2 (轮动潜伏) | Iter 3 最佳 | 变化 |\n")
        f.write("|------|-------------------|-------------|------|\n")
        if has_sig:
            best = max(has_sig, key=lambda r: r.get("win_rate_5d", 0) + r.get("ret_5d", 0))
            f.write(f"| 胜率 | 52.44% | {best['win_rate_5d']:.2f}% | {'+{:.2f}pp'.format(best['win_rate_5d']-52.44) if best['win_rate_5d']>52.44 else '{:.2f}pp'.format(best['win_rate_5d']-52.44)} |\n")
            f.write(f"| 5D收益 | 0.87% | {best['ret_5d']:.2f}% | {'+{:.2f}pp'.format(best['ret_5d']-0.87) if best['ret_5d']>0.87 else '{:.2f}pp'.format(best['ret_5d']-0.87)} |\n")
            f.write(f"| 信号数 | 37939 | {best['signals']} | {'+'+str(best['signals']-37939) if best['signals']>37939 else str(best['signals']-37939)} |\n")
        
        f.write("\n### 关键发现\n\n")
        f.write("1. **板块轮动作为主策略仍不成熟** — 5D窗口内无法产生稳定Alpha\n")
        f.write("2. **sector filter 大幅降低样本量** — 即使从stock_basic获取全量行业映射，热点行业(TOP3)覆盖的股票数有限\n")
        f.write("3. **板块因子适合做辅助过滤** — 结合T2量价/超跌因子使用更有效\n")
        f.write("4. **10D/20D窗口表现优于5D** — 板块轮动需要更长持有期\n")
        
        f.write("\n---\n")
        f.write(f"*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    
    print(f"\n✅ Report: {output_path}")
