#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 2 (SQL-based signal detection, much faster)
Strategy: for each combo, run pure SQL to find signals, only return signal tuples.
"""
import json, hashlib, subprocess, math, sys
from datetime import datetime

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE = "20260511"
DATA_START = "20230101"

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"  [SQL ERROR] {r.stderr[:300]}", file=sys.stderr)
        return []
    try:
        d = json.loads(r.stdout)
        return d if isinstance(d, list) else d.get("data", [])
    except:
        return []

def parse_date(d):
    return int(str(d).replace("-", ""))

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    return hashlib.md5(",".join(f"{k}={v}" for k,v in pairs).encode()).hexdigest()[:12]

# ─── COMBOS (same 5) ───
COMBOS = [
    {
        "name": "主力吸筹+底部放量起涨",
        "params": {
            "net_mf_min": 5000000,
            "close_position": "底40%",
            "pct_chg_1d_min": 1,
            "volume_ratio_min": 1.0,
            "ma_support": "MA20",
            "market_cap_bucket": "中小盘(30-100亿)",
        },
    },
    {
        "name": "大单扫货+突破前高",
        "params": {
            "buy_lg_ratio_min": 0.10,
            "n_day_high": 20,
            "volume_ratio_min": 1.5,
            "ma_arrangement": "多头排列",
            "turnover_rate_max": 0.10,
        },
    },
    {
        "name": "主力护盘+均线粘合待发",
        "params": {
            "net_mf_min": 2000000,
            "pct_chg_1d_min": -3,
            "close_position": "底20%",
            "ma_arrangement": "粘合(差<3%)",
            "volume_ratio_min": 0.8,
        },
    },
    {
        "name": "大额资金+多头排列+中小盘",
        "params": {
            "net_mf_min": 20000000,
            "pct_chg_1d_min": 0,
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "中小盘(30-100亿)",
            "turnover_rate_min": 0.01,
            "volume_ratio_min": 1.0,
        },
    },
    {
        "name": "多维度主力共振+低位放量",
        "params": {
            "net_mf_min": 5000000,
            "buy_lg_ratio_min": 0.08,
            "volume_ratio_min": 1.2,
            "close_position": "底40%",
            "ma_support": "MA20",
            "pct_chg_1d_min": 1,
            "turnover_rate_min": 0.005,
        },
    },
]

def build_signal_sql(combo):
    """Build a ClickHouse SQL that returns signals (ts_code, trade_date, close)"""
    p = combo["params"]
    conditions = []
    joins = []
    data_cols = ["d.ts_code", "d.trade_date", "d.close", "d.pct_chg", "d.vol", "d.amount"]
    
    # Base from stock_daily
    from_clause = "FROM tushare.tushare_stock_daily d"
    
    # Basic filters
    base_filters = [
        "d.trade_date >= '20230101'",
        "d.trade_date <= '20260511'",
        "d.ts_code NOT LIKE '30%'",
        "d.ts_code NOT LIKE '688%'",
        "d.ts_code NOT LIKE '920%'",
        "d.amount > 0",
        "d.close IS NOT NULL",
        "d.pct_chg IS NOT NULL",
    ]
    
    # Moneyflow JOIN
    need_mf = "net_mf_min" in p or "buy_lg_ratio_min" in p
    if need_mf:
        joins.append("LEFT JOIN tushare.tushare_moneyflow m ON d.ts_code=m.ts_code AND d.trade_date=m.trade_date")
        data_cols.append("m.net_mf_amount")
        data_cols.append("m.buy_lg_vol")
        data_cols.append("m.sell_lg_vol")
        if "net_mf_min" in p:
            conditions.append(f"m.net_mf_amount >= {p['net_mf_min']}")
        if "buy_lg_ratio_min" in p:
            conditions.append(f"m.buy_lg_vol + m.sell_lg_vol > 0")
            conditions.append(f"m.buy_lg_vol / (m.buy_lg_vol + m.sell_lg_vol) >= {p['buy_lg_ratio_min']}")
    
    # Daily basic JOIN
    need_db = any(k in p for k in ["volume_ratio_min", "turnover_rate_min", "turnover_rate_max"])
    if need_db:
        joins.append("LEFT JOIN tushare.tushare_daily_basic b ON d.ts_code=b.ts_code AND d.trade_date=b.trade_date")
        data_cols.extend(["b.volume_ratio", "b.turnover_rate"])
        if "volume_ratio_min" in p:
            conditions.append(f"b.volume_ratio >= {p['volume_ratio_min']}")
        if "turnover_rate_min" in p:
            conditions.append(f"b.turnover_rate >= {p['turnover_rate_min']}")
        if "turnover_rate_max" in p:
            conditions.append(f"b.turnover_rate <= {p['turnover_rate_max']}")
    
    # pct_chg
    if "pct_chg_1d_min" in p:
        conditions.append(f"d.pct_chg >= {p['pct_chg_1d_min']}")
    
    # Window functions for position, MA support, N-day high, MA arrangement
    windows_cols = ""
    windows_having = ""
    
    if "close_position" in p or "ma_support" in p:
        windows_cols += ", min(d.low) OVER w20 AS low_20d, max(d.high) OVER w20 AS high_20d"
    
    if "ma_support" in p or "ma_arrangement" in p:
        windows_cols += ", avg(d.close) OVER w5 AS ma5"
        windows_cols += ", avg(d.close) OVER w10 AS ma10"
        windows_cols += ", avg(d.close) OVER w20_ma AS ma20"
        windows_cols += ", avg(d.close) OVER w60 AS ma60"
    
    if "n_day_high" in p:
        nd = p["n_day_high"]
        windows_cols += f", max(d.high) OVER w{nd} AS high_{nd}d"
    
    # Row number for sufficient history
    windows_cols += ", row_number() OVER pw AS rn"
    
    # Build subquery
    window_defs = [
        "w5 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)",
        "w10 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)",
        "w20_ma AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)",
        "w60 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)",
        "w20 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)",
        "pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date)",
    ]
    
    if "n_day_high" in p:
        nd = p["n_day_high"]
        window_defs.append(f"w{nd} AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN {nd-1} PRECEDING AND CURRENT ROW)")
    
    all_windows = ", ".join(window_defs)
    
    # Build the full subquery
    data_cols_str = ", ".join(data_cols)
    join_str = " ".join(joins)
    cond_str = " AND ".join(base_filters + conditions)
    window_cols_str = windows_cols
    
    subquery = f"""
    SELECT {data_cols_str} {window_cols_str}
    {from_clause}
    {join_str}
    WHERE {cond_str}
    WINDOW {all_windows}
    """
    
    # Outer query with post-filter conditions
    outer_conds = ["rn >= 60"]  # need 60 days of history
    
    if "close_position" in p:
        pos = p["close_position"]
        if pos == "底20%":
            outer_conds.append("(d.close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.20")
        elif pos == "底40%":
            outer_conds.append("(d.close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.40")
    
    if "ma_support" in p:
        ms = p["ma_support"]
        ma_map = {"MA5": "ma5", "MA10": "ma10", "MA20": "ma20", "MA60": "ma60"}
        ma_col = ma_map.get(ms)
        if ma_col:
            outer_conds.append(f"{ma_col} IS NOT NULL AND d.close >= {ma_col}")
    
    if "ma_arrangement" in p:
        arr = p["ma_arrangement"]
        if arr == "多头排列":
            outer_conds.append("ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL")
            outer_conds.append("ma5 > ma10 AND ma10 > ma20 AND ma20 > ma60")
        elif arr == "粘合(差<3%)":
            outer_conds.append("ma5 IS NOT NULL AND ma10 IS NOT NULL AND ma20 IS NOT NULL AND ma60 IS NOT NULL")
            outer_conds.append("greatest(ma5, ma10, ma20, ma60) / NULLIF(least(ma5, ma10, ma20, ma60), 0) - 1 < 0.03")
    
    if "n_day_high" in p:
        nd = p["n_day_high"]
        outer_conds.append(f"high_{nd}d IS NOT NULL AND d.close >= high_{nd}d")
    
    outer_cond_str = " AND ".join(outer_conds)
    
    full_sql = f"""
    SELECT ts_code, trade_date, close
    FROM ({subquery})
    WHERE {outer_cond_str}
    ORDER BY ts_code, trade_date
    """
    
    return full_sql

def calc_fwd_returns(signals, stock_data, hold_days):
    """Calculate forward returns for signal list"""
    # Build index: code -> {trade_date -> close}
    idx = {}
    for code, bars in stock_data.items():
        idx[code] = {}
        for b in bars:
            idx[code][parse_date(b["trade_date"])] = b["close"]
    
    results = {}
    for hd in hold_days:
        fwd = []
        for code, td, close_signal in signals:
            code_bars = stock_data.get(code, [])
            # Find index of signal
            sig_idx = None
            for bi, b in enumerate(code_bars):
                if parse_date(b["trade_date"]) == td:
                    sig_idx = bi
                    break
            if sig_idx is None or sig_idx + hd >= len(code_bars):
                continue
            fwd_close = code_bars[sig_idx + hd]["close"]
            if fwd_close is not None and close_signal is not None and close_signal > 0:
                ret = (fwd_close / close_signal) - 1
                fwd.append(ret)
        
        n = len(fwd)
        if n < 5:
            results[hd] = {"wr": 0, "ret": 0, "sharpe": 0, "n": n}
            continue
        
        wr = sum(1 for r_ in fwd if r_ > 0) / n * 100
        avg_ret = sum(fwd) / n * 100
        mean_ret = sum(fwd) / n
        var = sum((r_ - mean_ret)**2 for r_ in fwd) / n
        std = math.sqrt(var) if var > 0 else 0.0001
        sharpe = (mean_ret / std) * math.sqrt(252 / hd) if std > 0 else 0
        
        results[hd] = {"wr": round(wr, 2), "ret": round(avg_ret, 4), "sharpe": round(sharpe, 3), "n": n}
    
    return results

def load_stock_data():
    """Load stock_daily for forward return calculation"""
    print("[Load] Loading stock_daily (for fwd returns)...")
    rows = ch_query(f"""SELECT ts_code, trade_date, close 
        FROM tushare.tushare_stock_daily FINAL 
        WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}' 
        AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' 
        AND close IS NOT NULL
        ORDER BY ts_code, trade_date""")
    by_code = {}
    for r in rows:
        code = r["ts_code"]
        if code not in by_code:
            by_code[code] = []
        by_code[code].append(r)
    print(f"  {len(rows)} rows, {len(by_code)} stocks")
    return by_code

def main():
    print("="*70)
    print("T4 资金主力视角 - Iter 2")
    print(f"执行: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据基准: {MAX_DATE}")
    print(f"SQL-based signal detection + Python fwd return calculation")
    print("="*70)
    
    # Load stock data (stripped down - no need for full hist in SQL approach)
    stock_data = load_stock_data()
    hold_days = [1, 3, 5, 10, 20]
    all_results = []
    
    for ci, combo in enumerate(COMBOS):
        p = combo["params"]
        h = combo_hash(p)
        print(f"\n{'='*60}")
        print(f"[{ci+1}/5] {combo['name']} [{h}]")
        print(f"  参数: {p}")
        
        # Build and run signal SQL
        sql = build_signal_sql(combo)
        signals_raw = ch_query(sql)
        
        # Parse signals
        signals = []
        for r in signals_raw:
            try:
                td = parse_date(r["trade_date"])
                close = float(r["close"])
                signals.append((r["ts_code"], td, close))
            except:
                continue
        
        print(f"  SQL signals: {len(signals_raw)} raw, {len(signals)} valid")
        
        if len(signals) < 5:
            print(f"  ⚠️ Too few signals ({len(signals)}), skipping")
            all_results.append({
                "name": combo["name"], "hash": h, "params": p,
                "signal_count": len(signals),
                "hold_results": {d: {"wr": 0, "ret": 0, "sharpe": 0, "n": 0} for d in hold_days}
            })
            continue
        
        # Calculate forward returns
        hr = calc_fwd_returns(signals, stock_data, hold_days)
        
        all_results.append({
            "name": combo["name"], "hash": h, "params": p,
            "signal_count": len(signals),
            "hold_results": hr
        })
        
        # Print
        print(f"  Results:")
        for hd in hold_days:
            if hd in hr:
                r = hr[hd]
                print(f"    T+{hd:2d}: N={r['n']:6d} | WR={r['wr']:5.2f}% | Ret={r['ret']:6.4f}% | Sharpe={r['sharpe']:6.3f}")
    
    # ─── Summary ───
    print("\n" + "="*70)
    print("T4 Iter 2 — 最终汇总")
    print("="*70)
    print(f"\n{'组合':30s} {'信号数':>8s} {'WR_5d':>8s} {'Ret_5d':>10s} {'Sharpe':>8s} {'Status':>10s}")
    print("-"*74)
    
    best_ret = best_wr = best_comp = None
    
    for res in all_results:
        hr = res["hold_results"]
        n = res["signal_count"]
        if 5 in hr:
            d5 = hr[5]
            w, r5, sh, n5 = d5["wr"], d5["ret"], d5["sharpe"], d5["n"]
            ok = w >= 52 and r5 >= 3 and n >= 200
            print(f"{res['name']:30s} {n:>8d} {w:>7.2f}% {r5:>9.4f}% {sh:>7.3f} {'✅' if ok else '❌':>10s}")
            if best_ret is None or r5 > best_ret[0]:
                best_ret = (r5, w, n, res["name"])
            if best_wr is None or w > best_wr[0]:
                best_wr = (w, r5, n, res["name"])
            score = w * 0.3 + r5 * 4 * 0.4 + min(n / 200, 10) * 10 * 0.3
            if best_comp is None or score > best_comp[0]:
                best_comp = (score, w, r5, n, res["name"])
        else:
            print(f"{res['name']:30s} {n:>8d} {'N/A':>8s} {'N/A':>10s} {'N/A':>8s} {'❌':>10s}")
    
    print()
    if best_ret: print(f"🏆 Best Ret_5d: {best_ret[3]} | Ret={best_ret[0]:.2f}% | WR={best_ret[1]:.2f}% | N={best_ret[2]}")
    if best_wr: print(f"🏆 Best WR_5d:  {best_wr[3]} | WR={best_wr[0]:.2f}% | Ret={best_wr[1]:.2f}% | N={best_wr[2]}")
    if best_comp: print(f"🏆 Best Comp:   {best_comp[4]} | WR={best_comp[1]:.2f}% | Ret={best_comp[2]:.2f}% | N={best_comp[3]}")
    
    # Check success criteria
    print(f"\n{'='*70}")
    print("✅ 达标判定: WR>=52% AND Ret_5d>=3% AND N>=200")
    any_pass = any(
        5 in res["hold_results"] and res["hold_results"][5]["wr"] >= 52 
        and res["hold_results"][5]["ret"] >= 3 and res["signal_count"] >= 200
        for res in all_results
    )
    if any_pass:
        print("🎉 有组合完全达标!")
    else:
        print("⚠️ 本轮无组合完全达标")
    
    return all_results

if __name__ == "__main__":
    results = main()
