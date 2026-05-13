#!/usr/bin/env python3
"""T6 板块轮动 - Iter 3 backtest v3 - two-step approach"""
import json, hashlib, subprocess, sys, math, os, traceback
from datetime import datetime, timedelta
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START_DATE = '20250101'
END_DATE = '20260511'

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        stderr = r.stderr[:500] if r.stderr else "no stderr"
        print(f"  [SQL ERR] {stderr[:200]}", file=sys.stderr)
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
# Sector data
# ───────────────────────────────────────

def load_stock_industry():
    rows = ch_query("""
    SELECT ts_code, argMax(industry, trade_date) AS ind
    FROM tushare.tushare_limit_list_d FINAL
    GROUP BY ts_code
    HAVING ind IS NOT NULL AND ind != ''
    """)
    return {r["ts_code"]: r["ind"] for r in rows}

def load_hot_industries(rank=3):
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
    return result

# ───────────────────────────────────────
# Signal SQL for each combo
# ───────────────────────────────────────

def build_signal_sql(params):
    """Build SQL that returns only (ts_code, trade_date, close) for signals"""
    conds = []
    p = params
    
    # Base filters
    base = [
        "d.ts_code NOT LIKE '30%'",
        "d.ts_code NOT LIKE '688%'",
        "d.ts_code NOT LIKE '920%'",
        "d.ts_code NOT LIKE '%ST%'",
        "d.amount > 0",
        "d.close IS NOT NULL",
        f"d.trade_date >= '{START_DATE}'",
        f"d.trade_date <= '{END_DATE}'",
    ]
    
    joins = []
    
    # DB join for volume ratio / turnover / circ_mv
    need_db = any(k in p for k in ["volume_ratio_min", "turnover_rate_min", "turnover_rate_max", "market_cap_bucket"])
    if need_db:
        joins.append("LEFT JOIN tushare.tushare_daily_basic AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date")
    
    # Moneyflow join
    if "net_mf_min_wan" in p:
        joins.append("LEFT JOIN tushare.tushare_moneyflow AS mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date")
        conds.append(f"mf.net_mf_amount >= {p['net_mf_min_wan']}")
    
    # pct_chg
    if "pct_chg_1d_min" in p:
        conds.append(f"d.pct_chg >= {p['pct_chg_1d_min']}")
    
    # Volume ratio (from daily_basic)
    if "volume_ratio_min" in p:
        conds.append(f"db.volume_ratio >= {p['volume_ratio_min']}")
    
    # Turnover rate
    if "turnover_rate_min" in p:
        conds.append(f"db.turnover_rate >= {p['turnover_rate_min']}")
    if "turnover_rate_max" in p:
        conds.append(f"db.turnover_rate <= {p['turnover_rate_max']}")
    
    # Market cap
    if "market_cap_bucket" in p:
        b = p["market_cap_bucket"]
        if "中小盘(30-100亿)" in b:
            conds.append("db.circ_mv / 10000 >= 300000 AND db.circ_mv / 10000 < 1000000")
        elif "中大盘(100-500亿)" in b:
            conds.append("db.circ_mv / 10000 >= 1000000 AND db.circ_mv / 10000 < 5000000")
        elif "小盘(<30亿)" in b:
            conds.append("db.circ_mv / 10000 < 300000")
        elif "大盘(>500亿)" in b:
            conds.append("db.circ_mv / 10000 >= 5000000")
    
    base_str = " AND ".join(base)
    cond_str = " AND ".join(conds) if conds else "1=1"
    join_str = " ".join(joins)
    
    # We'll use subquery approach: get candidates with window functions, then filter
    # Window functions needed: position, amplitude, MA, etc.
    
    # Just get raw data first for simplicity - filter with positions in outer query
    select_cols = "d.ts_code, d.trade_date, d.close AS clo, d.low, d.high, d.pct_chg"
    if need_db:
        select_cols += ", db.volume_ratio AS vr, db.turnover_rate AS tr, db.circ_mv / 10000 AS cmv"
    
    # For position/amplitude we need 20-day range
    # Use a subquery with window functions, but no lead()
    sql = f"""
    SELECT ts_code, trade_date, clo, low, high From (
      SELECT 
          {select_cols},
          min(d.low) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
          max(d.high) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
          row_number() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) AS rn
      FROM tushare.tushare_stock_daily AS d
      {join_str}
      WHERE {base_str}
    )
    WHERE rn >= 60
      AND low_20d IS NOT NULL AND high_20d IS NOT NULL
      AND (high_20d - low_20d) / NULLIF(low_20d * 1.0, 0) > 0
    """
    
    # Add position filter
    if "close_position" in p:
        pos = p["close_position"]
        if pos == "底20%":
            sql = sql.replace("WHERE rn >= 60", "WHERE rn >= 60 AND (clo - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.20")
        elif pos == "底40%":
            sql = sql.replace("WHERE rn >= 60", "WHERE rn >= 60 AND (clo - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.40")
    
    # Add amplitude filter
    if "amplitude_min" in p:
        amp = p["amplitude_min"] / 100.0
        sql = sql.replace("(high_20d - low_20d) / NULLIF(low_20d * 1.0, 0) > 0",
                          f"(high - low) / NULLIF(low * 1.0, 0) >= {amp}")
    else:
        sql = sql.replace("AND (high_20d - low_20d) / NULLIF(low_20d * 1.0, 0) > 0", "")
    
    # For MA arrangement, we need a more complex query
    if "ma_arrangement" in p:
        arr = p["ma_arrangement"]
        # Rewrite with full window
        if arr == "多头排列":
            select_cols_ma = ", ".join([
                "d.ts_code", "d.trade_date", "d.close AS clo", "d.low", "d.high",
                "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5",
                "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma10",
                "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20",
                "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS ma60",
            ])
            if need_db:
                select_cols_ma += ", db.volume_ratio AS vr, db.turnover_rate AS tr, db.circ_mv / 10000 AS cmv"
            sql = f"""
            SELECT ts_code, trade_date, clo, low, high From (
              SELECT 
                  {select_cols_ma},
                  row_number() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) AS rn
              FROM tushare.tushare_stock_daily AS d
              {join_str}
              WHERE {base_str}
            )
            WHERE rn >= 60
              AND ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL
              AND ma5 > ma10 AND ma10 > ma20 AND ma20 > ma60
            """
        elif arr == "粘合(差<3%)":
            select_cols_ma = ", ".join([
                "d.ts_code", "d.trade_date", "d.close AS clo", "d.low", "d.high",
                "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5",
                "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma10",
                "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20",
                "avg(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS ma60",
            ])
            if need_db:
                select_cols_ma += ", db.volume_ratio AS vr, db.turnover_rate AS tr, db.circ_mv / 10000 AS cmv"
            sql = f"""
            SELECT ts_code, trade_date, clo, low, high From (
              SELECT 
                  {select_cols_ma},
                  row_number() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) AS rn
              FROM tushare.tushare_stock_daily AS d
              {join_str}
              WHERE {base_str}
            )
            WHERE rn >= 60
              AND ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL
              AND greatest(ma5, ma10, ma20, ma60) / NULLIF(least(ma5, ma10, ma20, ma60), 0) - 1 < 0.03
            """
    
    # Add remaining filters (volume_ratio, turnover, mf, volume_ratio_min which wasn't in base)
    # These need to be appended
    if "volume_ratio_min" in p:
        sql = sql.replace("WHERE rn >= 60", f"WHERE rn >= 60 AND vr >= {p['volume_ratio_min']}")
    
    return sql

# ───────────────────────────────────────
# Load all stock data for forward returns
# ───────────────────────────────────────

def load_stock_data():
    """Load all stock daily close data into dict: {code: [(trade_date, close), ...]}"""
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
        code = r["ts_code"]
        dt = str(r["trade_date"]).replace("-", "")
        data[code].append((dt, r["close"]))
    print(f"  Loaded {sum(len(v) for v in data.values())} rows for {len(data)} stocks")
    return data

def get_fwd_returns(stock_data, code, sig_date, hold_days):
    """Compute forward returns given stock data and a signal date"""
    bars = stock_data.get(code, [])
    if not bars:
        return [None] * len(hold_days)
    # Find signal index
    sig_idx = None
    for i, (dt, _) in enumerate(bars):
        if dt == sig_date:
            sig_idx = i
            break
    if sig_idx is None:
        return [None] * len(hold_days)
    sig_close = bars[sig_idx][1]
    results = []
    for hd in hold_days:
        if sig_idx + hd < len(bars):
            results.append(bars[sig_idx + hd][1] / sig_close - 1)
        else:
            results.append(None)
    return results

# ───────────────────────────────────────
# COMBOS
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
    },
    {
        "name": "C2_主力资金+底部反弹",
        "desc": "底40% + VR>=1.0 + 振幅>=3% + 主力流入>=100万 + pct>=0",
        "params": {
            "close_position": "底40%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.0,
            "amplitude_min": 3,
            "net_mf_min_wan": 100,
            "turnover_rate_min": 0.5,
            "turnover_rate_max": 10,
        },
        "need_sector": False,
    },
    {
        "name": "C3_超跌+主力承接",
        "desc": "pct<=-5% + 振幅>=5% + 主力流入>=50万",
        "params": {
            "pct_chg_1d_min": -5,
            "net_mf_min_wan": 50,
            "amplitude_min": 5,
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
        "name": "C5_均线粘合+放量待发",
        "desc": "均线粘合(差<3%) + VR>=1.0 + pct>=0 + 振幅>=3%",
        "params": {
            "ma_arrangement": "粘合(差<3%)",
            "volume_ratio_min": 1.0,
            "pct_chg_1d_min": 0,
            "amplitude_min": 3,
        },
        "need_sector": False,
    },
]

# ───────────────────────────────────────
# MAIN
# ───────────────────────────────────────

if __name__ == "__main__":
    print(f"T6 板块轮动 — Iter 3 Backtest v3")
    print(f"Data: {START_DATE} ~ {END_DATE}")
    
    # Pre-load
    print("\n--- Loading sector data ---")
    stock_industry = load_stock_industry()
    hot_ind_daily = load_hot_industries(rank=3)
    
    print("\n--- Loading stock daily data ---")
    stock_data = load_stock_data()
    
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
        
        with open("/tmp/debug_t6_sql.txt", "w") as f:
            f.write(f"--- {combo['name']} ---\n")
            f.write(sql)
            f.write("\n")
        
        rows = ch_query(sql)
        print(f"  SQL returned {len(rows)} rows")
        
        if not rows:
            print("  ❌ No signals")
            all_results.append({"name": combo["name"], "hash": h, "signals": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0, "sharpe_5d": 0, "pass_5d": False, "params": p})
            continue
        
        # Parse signals
        signals = []
        for r in rows:
            dt = str(r["trade_date"]).replace("-", "")
            code = r["ts_code"]
            signals.append((code, dt, r.get("clo", r.get("close", 0))))
        
        # Apply sector filter
        if combo.get("need_sector") and signals:
            filtered = []
            for code, dt, clo in signals:
                ind = stock_industry.get(code, "")
                if ind and dt in hot_ind_daily and ind in hot_ind_daily[dt]:
                    filtered.append((code, dt, clo))
            print(f"  After sector filter: {len(filtered)} (dropped {len(signals)-len(filtered)})")
            signals = filtered
        
        if not signals:
            print("  ❌ No signals after filter")
            all_results.append({"name": combo["name"], "hash": h, "signals": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0, "sharpe_5d": 0, "pass_5d": False, "params": p})
            continue
        
        # Compute forward returns
        rets_5d, rets_10d, rets_20d = [], [], []
        for code, dt, clo in signals:
            fwd = get_fwd_returns(stock_data, code, dt, [5, 10, 20])
            if fwd[0] is not None: rets_5d.append(fwd[0])
            if fwd[1] is not None: rets_10d.append(fwd[1])
            if fwd[2] is not None: rets_20d.append(fwd[2])
        
        def compute(rets):
            if not rets: return 0, 0, 0, 0
            n = len(rets)
            mean = sum(rets) / n * 100
            wr = sum(1 for r in rets if r > 0) / n * 100
            sh = calc_sharpe(rets)
            return mean, wr, sh, n
        
        m5, w5, s5, n5 = compute(rets_5d)
        m10, w10, s10, n10 = compute(rets_10d)
        m20, w20, s20, n20 = compute(rets_20d)
        
        result = {
            "name": combo["name"], "hash": h,
            "signals": len(signals),
            "n_5d": n5, "n_10d": n10, "n_20d": n20,
            "ret_5d": round(m5, 2), "ret_10d": round(m10, 2), "ret_20d": round(m20, 2),
            "win_rate_5d": round(w5, 2), "win_rate_10d": round(w10, 2), "win_rate_20d": round(w20, 2),
            "sharpe_5d": round(s5, 3), "sharpe_10d": round(s10, 3), "sharpe_20d": round(s20, 3),
            "pass_5d": m5 >= 3.0 and w5 >= 52.0 and len(signals) >= 200,
            "params": p
        }
        all_results.append(result)
        
        print(f"  N={len(signals)} | WR_5d={w5:.1f}% | ret_5d={m5:.2f}% | ret_10d={m10:.2f}% | ret_20d={m20:.2f}% | Sharpe={s5:.3f}")
        print(f"  PASS: {'✅' if result['pass_5d'] else '❌'}")
    
    # Summary
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
            f.write("---\n\n")
        
        # Conclusion
        f.write("## 结论\n\n")
        passed = [r for r in all_results if r.get("pass_5d")]
        if passed:
            best = max(passed, key=lambda r: r.get("ret_5d", 0))
            f.write(f"✅ **{len(passed)}/{len(all_results)} 组合达标**\n\n")
            f.write(f"最佳: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}, Sharpe={best['sharpe_5d']:.3f}\n")
        else:
            has_sig = [r for r in all_results if r.get("signals", 0) > 0]
            if has_sig:
                best = max(has_sig, key=lambda r: (r.get("win_rate_5d", 0) + r.get("ret_5d", 0)))
                f.write(f"❌ 全部组合未达标\n\n")
                f.write(f"最佳接近组合: **{best['name']}** — WR={best['win_rate_5d']:.1f}%, ret_5d={best['ret_5d']:.2f}%, N={best['signals']}, Sharpe={best['sharpe_5d']:.3f}\n\n")
            else:
                f.write(f"❌ 全部组合产生0信号。参数条件可能是过严或SQL兼容性问题。\n\n")
        
        # Comparison with Iter 2
        f.write("### Iter 2 对比\n\n")
        f.write("Iter 2 T6 先例：板块轮动独立视角在5D窗口无有效Alpha(WR=52.44%, ret=0.87%)，\n")
        f.write("建议作辅助过滤器。本轮尝试将板块因子与量价/资金因子组合。\n\n")
        
        f.write("\n---\n")
        f.write(f"*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    
    print(f"\n✅ Report: {output_path}")
