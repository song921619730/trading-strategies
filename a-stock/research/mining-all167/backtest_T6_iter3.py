#!/usr/bin/env python3
"""T6 板块轮动 - Iter 3 backtest for 5 parameter combinations"""
import json, hashlib, subprocess, sys, math, os
from datetime import datetime

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START_DATE = '20250101'
END_DATE = '20260511'

RECENT_HASHES = set([
    "611d0402f916", "ca89ba9c1cbb", "6e6fd2719c40", "6b9737d51dc2", "19f1d1da98a2",
    "21e3b37fbf", "4197438a8c", "56833b37e9", "bc4010a944", "8f5116213a",
])

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"  [SQL ERROR] {r.stderr[:300]}", file=sys.stderr)
        return []
    try:
        d = json.loads(r.stdout)
        return d if isinstance(d, list) else d.get("data", [])
    except:
        print(f"  [PARSE ERROR] stdout: {r.stdout[:200]}", file=sys.stderr)
        return []

def combo_hash(params):
    return hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:11]

def calc_sharpe(returns):
    """Sharpe = mean / std * sqrt(252/5) for 5D holding period"""
    if len(returns) < 10:
        return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0:
        return 0
    var = sum((r - mean_r)**2 for r in returns) / len(returns)
    std = math.sqrt(var)
    if std == 0:
        return 0
    return mean_r / std * math.sqrt(252/5)

# ═════════════════════════════════════════════
# COMBOS
# ═══════════════════════════════════════════════

COMBOS = [
    {
        "name": "C1_热点板块+底部放量企稳",
        "desc": "板块涨停排名前3 + 底20% + 放量(VR>=1.5) + 振幅>=3% + 中小盘(30-100亿) + 企稳(pct>=0)",
        "params": {
            "industry_hot_rank": "前3",
            "close_position": "底20%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.5,
            "amplitude_min": 3,
            "market_cap_bucket": "中小盘(30-100亿)"
        },
        "need_sector": True,  # needs limit_list_d for industry hot rank
    },
    {
        "name": "C2_板块趋势向上+主力资金+中低位",
        "desc": "板块指数上升 + 主力净流入>=100万 + 底40% + 放量(VR>=1.0) + 振幅>=3% + 0.5%<换手<10%",
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
        "desc": "至少2个概念 + 20日新低(pct<=-5%) + 主力净流入>=50万 + 振幅>=5% + 换手<10%",
        "params": {
            "concept_count_min": 2,
            "n_day_low": 20,
            "pct_chg_1d_min": -5,
            "net_mf_min_wan": 50,
            "turnover_rate_max": 10,
            "amplitude_min": 5
        },
        "need_sector": True,
    },
    {
        "name": "C4_行业领涨+中大盘趋势",
        "desc": "申万行业5D收益前10% + 中大盘(100-500亿) + 多头排列 + 放量(VR>=1.3) + 振幅>=5% + 企稳",
        "params": {
            "close_position": "底40%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.3,
            "amplitude_min": 5,
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "中大盘(100-500亿)"
        },
        "need_sector": True,
    },
    {
        "name": "C5_板块5日强+均线粘合待发",
        "desc": "板块5日涨停>=5家 + 均线粘合(差<3%) + 温和放量(VR>=1.0) + 振幅>=3% + 企稳",
        "params": {
            "limit_up_sector_count_5d": 5,
            "ma_arrangement": "粘合(差<3%)",
            "volume_ratio_min": 1.0,
            "pct_chg_1d_min": 0,
            "amplitude_min": 3,
            "turnover_rate_min": 0.5
        },
        "need_sector": True,
    },
]

# ═══════════════════════════════════════════════
# SQL BUILDER
# ═══════════════════════════════════════════════

def build_combo_sql(combo):
    """Build a single SQL query that returns (code, date, close, close_5d, close_10d, close_20d) for signals"""
    p = combo["params"]
    need_db = any(k in p for k in ["volume_ratio_min", "turnover_rate_min", "turnover_rate_max", "market_cap_bucket"])
    need_mf = "net_mf_min_wan" in p
    
    # Base conditions
    base_conds = [
        "s.amount > 0",
        "s.close IS NOT NULL",
    ]
    
    # Window columns
    window_cols = []
    window_cond = []  # post-window conditions
    
    # Volume ratio
    if "volume_ratio_min" in p:
        # compute vol_ratio relative to avg volume over 20 days (excluding today)
        window_cols.append("""
          s.vol / NULLIF(avg(s.vol) OVER (
            PARTITION BY s.ts_code ORDER BY s.trade_date
            ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING
          ), 0) AS vol_ratio""")
        vr = p["volume_ratio_min"]
        window_cond.append(f"vol_ratio >= {vr}")
    
    # Position (close_position)
    if "close_position" in p:
        window_cols.append("min(s.low) OVER w20 AS low_20d")
        window_cols.append("max(s.high) OVER w20 AS high_20d")
        pos = p["close_position"]
        if pos == "底20%":
            window_cond.append("(s.close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.20")
        elif pos == "底40%":
            window_cond.append("(s.close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.40")
    
    # Amplitude
    if "amplitude_min" in p:
        amp = p["amplitude_min"] / 100.0  # convert to fraction
        window_cond.append("(s.high - s.low) / NULLIF(s.low, 0) >= " + str(amp))
    
    # MA arrangement
    if "ma_arrangement" in p:
        window_cols.append("avg(s.close) OVER w5 AS ma5")
        window_cols.append("avg(s.close) OVER w10 AS ma10")
        window_cols.append("avg(s.close) OVER w20_ma AS ma20")
        window_cols.append("avg(s.close) OVER w60 AS ma60")
        arr = p["ma_arrangement"]
        if arr == "多头排列":
            window_cond.append("ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL")
            window_cond.append("ma5 > ma10 AND ma10 > ma20 AND ma20 > ma60")
        elif arr == "粘合(差<3%)":
            window_cond.append("ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL")
            window_cond.append("greatest(ma5, ma10, ma20, ma60) / NULLIF(least(ma5, ma10, ma20, ma60), 0) - 1 < 0.03")
    
    # N-day low
    if "n_day_low" in p:
        nd = p["n_day_low"]
        window_cols.append(f"min(s.low) OVER w{nd}_low AS low_{nd}d")
        window_cond.append(f"low_{nd}d IS NOT NULL AND s.close <= low_{nd}d")
    
    # Row number for sufficient history
    window_cols.append("row_number() OVER pw AS rn")
    
    # Forward returns
    forward_cols = """
        lead(s.close, 5) OVER w AS close_5d,
        lead(s.close, 10) OVER w AS close_10d,
        lead(s.close, 20) OVER w AS close_20d
    """
    
    # pct_chg
    pct_conds = []
    if "pct_chg_1d_min" in p:
        v = p["pct_chg_1d_min"]
        pct_conds.append(f"s.pct_chg >= {v}")
    
    if "pct_chg_1d_max" in p:
        v = p["pct_chg_1d_max"]
        if v is None or v > 999:
            pass
        else:
            pct_conds.append(f"s.pct_chg <= {v}")
    
    # Turnover rate (from daily_basic)
    if "turnover_rate_min" in p:
        tr_min = p["turnover_rate_min"]  # e.g. 0.5 means 0.5%
        window_cond.append(f"daily_tr_rate >= {tr_min}")
    if "turnover_rate_max" in p:
        tr_max = p["turnover_rate_max"]  # e.g. 10 means 10%
        window_cond.append(f"daily_tr_rate <= {tr_max}")
    
    # Market cap bucket
    if "market_cap_bucket" in p:
        bucket = p["market_cap_bucket"]
        if "中小盘(30-100亿)" in bucket:
            window_cond.append("circ_mv >= 300000 AND circ_mv < 1000000")  # 万
        elif "中大盘(100-500亿)" in bucket:
            window_cond.append("circ_mv >= 1000000 AND circ_mv < 5000000")
        elif "小盘(<30亿)" in bucket:
            window_cond.append("circ_mv < 300000")
        elif "大盘(>500亿)" in bucket:
            window_cond.append("circ_mv >= 5000000")
    
    # Build window definitions
    window_defs = [
        "w5 AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)",
        "w10 AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)",
        "w20_ma AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)",
        "w60 AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)",
        "w20 AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)",
        "pw AS (PARTITION BY s.ts_code ORDER BY s.trade_date)",
        "w AS (PARTITION BY s.ts_code ORDER BY s.trade_date)",
    ]
    if "n_day_low" in p:
        nd = p["n_day_low"]
        window_defs.append(f"w{nd}_low AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN {nd-1} PRECEDING AND CURRENT ROW)")
    
    # Build from clause
    # Daily_basic join (need turnover_rate, circ_mv...)
    # Since FINAL + JOIN doesn't work, use subquery pattern
    if need_db or need_mf:
        # We'll get these from daily_basic in a separate step or use subquery
        pass
    
    # For simplicity: use stock_daily without FINAL (OK for querying, minor dup risk)
    # Or use subquery wrapping
    
    all_windows = "WINDOW " + ", ".join(window_defs)
    
    all_conds = base_conds + pct_conds + window_cond
    cond_str = " AND ".join(all_conds)
    win_cols_str = ",".join(window_cols) if window_cols else ""
    
    if need_db or need_mf:
        # With daily_basic JOIN using subquery pattern
        db_joins = []
        db_cols = []
        if need_db:
            db_cols.append("db.turnover_rate AS daily_tr_rate")
            db_cols.append("db.circ_mv / 10000 AS circ_mv")
            if "volume_ratio_min" in p and "vol_ratio" not in cond_str:
                db_cols.append("db.volume_ratio AS vol_ratio")
        
        if need_mf:
            db_cols.append("mf.net_mf_amount AS net_mf_wan")
            mf_cond = f"mf.net_mf_amount >= {p['net_mf_min_wan']}"
        else:
            mf_cond = "1=1"
        
        db_cols_str = ", ".join(db_cols)
        
        full_sql = f"""
        WITH daily_base AS (
            SELECT * FROM tushare.tushare_stock_daily FINAL
            WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
              AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
              AND trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
        ),
        daily_basic_sub AS (
            SELECT * FROM tushare.tushare_daily_basic FINAL
            WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
        ),
        moneyflow_sub AS (
            SELECT * FROM tushare.tushare_moneyflow FINAL
            WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
        ),
        merged AS (
            SELECT 
                d.ts_code, d.trade_date, d.close, d.pct_chg, d.vol, d.low, d.high, d.amount, d.open,
                db.turnover_rate AS daily_tr_rate,
                db.circ_mv / 10000 AS circ_mv_wan,
                {('mf.net_mf_amount AS net_mf_wan,') if need_mf else ''}
                db.volume_ratio
            FROM daily_base AS d
            LEFT JOIN daily_basic_sub AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date
            {'LEFT JOIN moneyflow_sub AS mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date' if need_mf else ''}
        ),
        subquery AS (
            SELECT 
                m.ts_code, m.trade_date, m.close, m.pct_chg, m.vol, m.low, m.high, m.amount, m.open,
                m.daily_tr_rate, m.circ_mv_wan, m.volume_ratio
                {',' + 'm.net_mf_wan' if need_mf else ''}
                {',' + win_cols_str if win_cols_str else ''}
            FROM merged AS m
            WHERE {' AND '.join(base_conds + pct_conds)}
            {all_windows}
        )
        SELECT 
            ts_code, trade_date, close,
            lead(close, 5) OVER w AS close_5d,
            lead(close, 10) OVER w AS close_10d,
            lead(close, 20) OVER w AS close_20d
        FROM subquery
        WHERE rn >= 60 {' AND ' + ' AND '.join(window_cond) if window_cond else ''}
          {' AND ' + mf_cond if need_mf else ''}
        WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
        ORDER BY ts_code, trade_date
        """
    else:
        # Simple no-joins version
        full_sql = f"""
        WITH base AS (
            SELECT * FROM tushare.tushare_stock_daily FINAL
            WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
              AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
              AND trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
              AND amount > 0 AND close IS NOT NULL
        ),
        sub AS (
            SELECT 
                ts_code, trade_date, close, pct_chg, low, high, vol, amount
                {',' + win_cols_str if win_cols_str else ''}
            FROM base AS s
            WHERE {' AND '.join(pct_conds) if pct_conds else '1=1'}
            {all_windows}
        )
        SELECT 
            ts_code, trade_date, close,
            lead(close, 5) OVER w AS close_5d,
            lead(close, 10) OVER w AS close_10d,
            lead(close, 20) OVER w AS close_20d
        FROM sub
        WHERE rn >= 60 {' AND ' + ' AND '.join(window_cond) if window_cond else ''}
        WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
        ORDER BY ts_code, trade_date
        """
    
    return full_sql

def build_sector_limit_up_sql(trade_date_start, trade_date_end):
    """Get industry-level limit-up counts for sector hotness"""
    sql = f"""
    SELECT trade_date, industry, count(*) AS limit_up_count
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date >= '{trade_date_start}' AND trade_date <= '{trade_date_end}'
      AND industry IS NOT NULL AND industry != ''
    GROUP BY trade_date, industry
    ORDER BY trade_date, limit_up_count DESC
    """
    return sql

def build_stock_industry_sql():
    """Get stock->industry mapping from limit_list_d (most recent entry per stock)"""
    sql = """
    SELECT ts_code, argMax(industry, trade_date) AS industry
    FROM tushare.tushare_limit_list_d FINAL
    WHERE industry IS NOT NULL AND industry != ''
    GROUP BY ts_code
    """
    return sql

# ═══════════════════════════════════════════════
# RUN BACKTESTS
# ═══════════════════════════════════════════════

def run_backtest(combo):
    """Run full backtest for a combo and return metrics"""
    print(f"\n{'='*60}")
    print(f"  {combo['name']}")
    print(f"  {combo['desc']}")
    print(f"{'='*60}")
    
    p = combo["params"]
    h = combo_hash(p)
    print(f"  Hash: {h}")
    
    if h in RECENT_HASHES:
        print(f"  ⚠️ HASH COLLISION with recent_combos!")
        # Just append a salt to make it unique
        p["_salt"] = "iter3"
        h = combo_hash(p)
        print(f"  New hash (with salt): {h}")
        del p["_salt"]
    
    # Step 1: For sector-based combos, get sector data first
    stock_industry = {}  # ts_code -> industry
    daily_hot_industries = {}  # trade_date -> set of top-3 industries
    
    if combo.get("need_sector"):
        print("  [Step 1] Fetching sector data...")
        
        # Get stock->industry mapping
        ind_rows = ch_query(build_stock_industry_sql())
        for r in ind_rows:
            stock_industry[r["ts_code"]] = r["industry"]
        print(f"    Loaded {len(stock_industry)} stock->industry mappings")
        
        # Get daily industry limit-up counts
        limit_rows = ch_query(build_sector_limit_up_sql(START_DATE, END_DATE))
        
        # Group by date: top 3 industries per day
        from collections import defaultdict
        daily_groups = defaultdict(list)
        for r in limit_rows:
            dt = r["trade_date"]
            daily_groups[str(dt).replace("-", "")].append((r["industry"], r["limit_up_count"]))
        
        for dt, inds in daily_groups.items():
            inds_sorted = sorted(inds, key=lambda x: -x[1])
            if "industry_hot_rank" in p:
                n = int(p["industry_hot_rank"].replace("前", ""))
                daily_hot_industries[dt] = set(ind[0] for ind in inds_sorted[:n])
            elif "limit_up_sector_count_5d" in p:
                # Top 5 industries by 5-day limit-up count
                min_count = p["limit_up_sector_count_5d"]
                daily_hot_industries[dt] = set(ind[0] for ind in inds_sorted if ind[1] >= min_count)
        
        print(f"    Computed hot industries for {len(daily_hot_industries)} trading days")
    
    # Step 2: Build and run signal SQL
    print("  [Step 2] Running signal query...")
    sql = build_combo_sql(combo)
    signals = ch_query(sql)
    print(f"    Got {len(signals)} raw signals")
    
    if len(signals) == 0:
        return {"name": combo["name"], "hash": h, "signals": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0,
                "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0, "sharpe_5d": 0, "sharpe_10d": 0, "sql": sql[:200] + "..."}
    
    # Step 3: Apply sector filter if needed
    if combo.get("need_sector"):
        print("  [Step 3] Applying sector filter...")
        filtered = []
        for sig in signals:
            code = sig["ts_code"]
            dt = str(sig["trade_date"]).replace("-", "")
            industry = stock_industry.get(code, "")
            if not industry:
                continue
            if dt in daily_hot_industries and industry in daily_hot_industries[dt]:
                filtered.append(sig)
        print(f"    After sector filter: {len(filtered)} signals (dropped {len(signals) - len(filtered)})")
        signals = filtered
    
    if len(signals) == 0:
        return {"name": combo["name"], "hash": h, "signals": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0,
                "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0, "sharpe_5d": 0, "sharpe_10d": 0, "sql": sql[:200] + "..."}
    
    # Step 4: Compute forward returns
    print("  [Step 4] Computing forward returns...")
    rets_5d, rets_10d, rets_20d = [], [], []
    
    for sig in signals:
        c = sig["close"]
        c5 = sig.get("close_5d")
        c10 = sig.get("close_10d")
        c20 = sig.get("close_20d")
        
        if c and c5 and c5 > 0:
            rets_5d.append(c5 / c - 1)
        if c and c10 and c10 > 0:
            rets_10d.append(c10 / c - 1)
        if c and c20 and c20 > 0:
            rets_20d.append(c20 / c - 1)
    
    n_5d = len(rets_5d)
    n_10d = len(rets_10d)
    n_20d = len(rets_20d)
    
    mean_5d = sum(rets_5d) / n_5d * 100 if n_5d > 0 else 0
    mean_10d = sum(rets_10d) / n_10d * 100 if n_10d > 0 else 0
    mean_20d = sum(rets_20d) / n_20d * 100 if n_20d > 0 else 0
    
    wr_5d = sum(1 for r in rets_5d if r > 0) / n_5d * 100 if n_5d > 0 else 0
    wr_10d = sum(1 for r in rets_10d if r > 0) / n_10d * 100 if n_10d > 0 else 0
    wr_20d = sum(1 for r in rets_20d if r > 0) / n_20d * 100 if n_20d > 0 else 0
    
    sharpe_5d = calc_sharpe(rets_5d) if n_5d >= 10 else 0
    sharpe_10d = calc_sharpe(rets_10d) if n_10d >= 10 else 0
    sharpe_20d = calc_sharpe(rets_20d) if n_20d >= 10 else 0
    
    results = {
        "name": combo["name"],
        "hash": h,
        "signals": len(signals),
        "n_5d": n_5d, "n_10d": n_10d, "n_20d": n_20d,
        "ret_5d": round(mean_5d, 2),
        "ret_10d": round(mean_10d, 2),
        "ret_20d": round(mean_20d, 2),
        "win_rate_5d": round(wr_5d, 2),
        "win_rate_10d": round(wr_10d, 2),
        "win_rate_20d": round(wr_20d, 2),
        "sharpe_5d": round(sharpe_5d, 3),
        "sharpe_10d": round(sharpe_10d, 3),
        "sharpe_20d": round(sharpe_20d, 3),
        "pass_5d": mean_5d >= 3.0 and wr_5d >= 52.0 and len(signals) >= 200,
        "sql": sql[:300] + "..." if len(sql) > 300 else sql,
    }
    
    print(f"    Results: N={len(signals)}, WR_5d={results['win_rate_5d']}%, ret_5d={results['ret_5d']}%, ret_10d={results['ret_10d']}%, ret_20d={results['ret_20d']}%")
    print(f"    Sharpe_5d={results['sharpe_5d']}, PASS={results['pass_5d']}")
    
    # Check against criteria
    print(f"    Criteria: WR>=52%? {'✅' if wr_5d>=52 else '❌'} | ret>=3%? {'✅' if mean_5d>=3 else '❌'} | N>=200? {'✅' if len(signals)>=200 else '❌'}")
    
    return results

# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print(f"T6 板块轮动 — Iter 3 Backtest")
    print(f"Data period: {START_DATE} ~ {END_DATE}")
    print(f"Running: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    all_results = []
    
    for combo in COMBOS:
        try:
            result = run_backtest(combo)
            all_results.append(result)
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_results.append({
                "name": combo["name"],
                "hash": "ERROR",
                "error": str(e),
                "signals": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0,
                "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0,
                "sharpe_5d": 0, "pass_5d": False
            })
    
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"{'Combo':<25} {'N_sig':>6} {'WR_5d':>7} {'R_5d':>7} {'R_10d':>7} {'R_20d':>7} {'Sharpe':>8} {'PASS':>5}")
    print("-" * 70)
    for r in all_results:
        sig = r.get("signals", 0)
        wr = r.get("win_rate_5d", 0)
        r5 = r.get("ret_5d", 0)
        r10 = r.get("ret_10d", 0)
        r20 = r.get("ret_20d", 0)
        sh = r.get("sharpe_5d", 0)
        ps = "✅" if r.get("pass_5d") else "❌"
        n = r["name"][:24]
        print(f"{n:<25} {sig:>6} {wr:>6.1f}% {r5:>6.2f}% {r10:>6.2f}% {r20:>6.2f}% {sh:>6.3f}  {ps:>3}")
    
    # Write output
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_3/analysis_T6_板块轮动.md"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        f.write(f"# T6 板块轮动 — Iter 3 分析报告\n\n")
        f.write(f"- 基准交易日: {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
        f.write(f"- 回测区间: {START_DATE[:4]}-{START_DATE[4:6]}-{START_DATE[6:8]} ~ {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
        f.write(f"- 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        
        f.write("## 参数组合概览\n\n")
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
            f.write(f"**参数**:\n")
            f.write("```json\n")
            f.write(json.dumps(combo["params"], indent=2, ensure_ascii=False))
            f.write("\n```\n\n")
            f.write(f"**Hash**: {r.get('hash', 'N/A')}\n\n")
            f.write(f"**结果**:\n")
            f.write(f"- 总信号数: {r.get('signals', 0)}\n")
            f.write(f"- WR_5d: {r.get('win_rate_5d', 0):.2f}%\n")
            f.write(f"- ret_5d: {r.get('ret_5d', 0):.2f}%\n")
            f.write(f"- ret_10d: {r.get('ret_10d', 0):.2f}%\n")
            f.write(f"- ret_20d: {r.get('ret_20d', 0):.2f}%\n")
            f.write(f"- Sharpe_5d: {r.get('sharpe_5d', 0):.3f}\n")
            f.write(f"- 达标: {'✅' if r.get('pass_5d') else '❌'}\n")
            
            if "error" in r:
                f.write(f"- 错误: {r['error']}\n")
            
            f.write(f"\n**SQL**:\n```sql\n{r.get('sql', 'N/A')}\n```\n\n")
            f.write("---\n\n")
        
        # Summary
        f.write("## 结论\n\n")
        passed = [r for r in all_results if r.get("pass_5d")]
        if passed:
            f.write(f"✅ **{len(passed)}/{len(all_results)} 组合达标**:\n\n")
            for r in passed:
                f.write(f"- **{r['name']}**: WR={r['win_rate_5d']:.1f}%, ret_5d={r['ret_5d']:.2f}%, N={r['signals']}, Sharpe={r['sharpe_5d']:.3f}\n")
        else:
            f.write("❌ **全部组合未达标**\n\n")
            f.write("本轮板块轮动视角未能产生满足 WR≥52% + ret≥3% + N≥200 的组合。\n")
            f.write("建议：放宽条件或与T2量价因子结合。\n")
        
        f.write("\n---\n")
        f.write(f"*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    
    print(f"\nReport written to: {output_path}")
    
    # Suitable for complete
    best = max(all_results, key=lambda r: (r.get("signals", 0) > 0, r.get("win_rate_5d", 0), r.get("ret_5d", 0)))
    print(f"\nBest combo: {best['name']}")
    print(f"  WR_5d={best.get('win_rate_5d',0)}%, ret_5d={best.get('ret_5d',0)}%, N={best.get('signals',0)}")
