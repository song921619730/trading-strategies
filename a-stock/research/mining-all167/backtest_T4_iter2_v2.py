#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 2 回测 (ClickHouse native SQL with leadInFrame)
Simple SQL: stock_daily + moneyflow + daily_basic JOIN, compute fwd returns with leadInFrame.
No complex subquery scoping issues.
"""
import json, hashlib, subprocess, math, sys
from datetime import datetime

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE = "20260511"
DATA_START = "20230101"

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"  [SQL ERROR] {r.stderr[:300]}", file=sys.stderr)
        return []
    try:
        d = json.loads(r.stdout)
        return d if isinstance(d, list) else d.get("data", [])
    except:
        return []

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    return hashlib.md5(",".join(f"{k}={v}" for k,v in pairs).encode()).hexdigest()[:12]

BASE_SQL = """
SELECT sub.ts_code, sub.trade_date, sub.close,
       sub.fwd_1, sub.fwd_3, sub.fwd_5, sub.fwd_10, sub.fwd_20,
       sub.pos_20d, sub.volume_ratio, sub.turnover_rate,
       sub.net_mf_amount, sub.buy_lg_vol, sub.sell_lg_vol,
       sub.ma5, sub.ma10, sub.ma20, sub.ma60, sub.ma_spread
FROM (
    SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.vol, d.amount,
           m.net_mf_amount, m.buy_lg_vol, m.sell_lg_vol,
           b.volume_ratio, b.turnover_rate,
           leadInFrame(d.close, 1) OVER w AS fwd_1,
           leadInFrame(d.close, 3) OVER w AS fwd_3,
           leadInFrame(d.close, 5) OVER w AS fwd_5,
           leadInFrame(d.close, 10) OVER w AS fwd_10,
           leadInFrame(d.close, 20) OVER w AS fwd_20,
           row_number() OVER pw AS rn,
           min(d.low) OVER w20 AS low_20d,
           max(d.high) OVER w20 AS high_20d,
           avg(d.close) OVER w5 AS ma5,
           avg(d.close) OVER w10 AS ma10,
           avg(d.close) OVER w20_ma AS ma20,
           avg(d.close) OVER w60 AS ma60,
           (d.close - min(d.low) OVER w20) / NULLIF(max(d.high) OVER w20 - min(d.low) OVER w20, 0) AS pos_20d,
           (greatest(avg(d.close) OVER w5, avg(d.close) OVER w10, avg(d.close) OVER w20_ma, avg(d.close) OVER w60) 
            / NULLIF(least(avg(d.close) OVER w5, avg(d.close) OVER w10, avg(d.close) OVER w20_ma, avg(d.close) OVER w60), 0) - 1) AS ma_spread
    FROM tushare.tushare_stock_daily d
    LEFT JOIN tushare.tushare_moneyflow m ON d.ts_code = m.ts_code AND d.trade_date = m.trade_date
    LEFT JOIN tushare.tushare_daily_basic b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
    WHERE d.trade_date >= '{DATA_START}' AND d.trade_date <= '{MAX_DATE}'
      AND d.ts_code NOT LIKE '30%%' AND d.ts_code NOT LIKE '688%%' AND d.ts_code NOT LIKE '920%%'
      AND d.close IS NOT NULL AND d.amount > 0
    WINDOW
        w AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING),
        pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date),
        w5 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
        w10 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
        w20_ma AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
        w60 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
        w20 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
) sub
WHERE sub.rn >= 60
  AND sub.fwd_5 IS NOT NULL
"""

# ─── 5 combos ───
COMBOS = [
    {
        "name": "主力吸筹+底部放量起涨",
        "desc": "净流入≥500万+底40%+涨幅≥1%+量比≥1+MA20支撑+中小盘",
        "sql_filter": """
  AND net_mf_amount >= 5000000
  AND pos_20d <= 0.40
  AND pct_chg >= 1
  AND volume_ratio >= 1.0
  AND ma20 IS NOT NULL AND close >= ma20
  AND circ_mv >= 3e9 AND circ_mv < 10e9
""",
    },
    {
        "name": "大单扫货+突破前高",
        "desc": "大单买入≥10%+20日新高+量比≥1.5+多头排列+换手≤10%",
        "sql_filter": """
  AND buy_lg_vol + sell_lg_vol > 0
  AND buy_lg_vol / (buy_lg_vol + sell_lg_vol) >= 0.10
  AND close >= high_20d
  AND volume_ratio >= 1.5
  AND ma5 > ma10 AND ma10 > ma20 AND ma20 > ma60
  AND turnover_rate <= 0.10
""",
    },
    {
        "name": "主力护盘+均线粘合待发",
        "desc": "净流入≥200万+跌幅≤3%+底20%+均线粘合+量比≥0.8",
        "sql_filter": """
  AND net_mf_amount >= 2000000
  AND pct_chg >= -3
  AND pos_20d <= 0.20
  AND ma_spread < 0.03
  AND volume_ratio >= 0.8
""",
    },
    {
        "name": "大额资金+多头排列+中小盘",
        "desc": "净流入≥2000万+不跌+多头排列+中小盘+换手≥1%+量比≥1",
        "sql_filter": """
  AND net_mf_amount >= 20000000
  AND pct_chg >= 0
  AND ma5 > ma10 AND ma10 > ma20 AND ma20 > ma60
  AND circ_mv >= 3e9 AND circ_mv < 10e9
  AND turnover_rate >= 0.01
  AND volume_ratio >= 1.0
""",
    },
    {
        "name": "多维度主力共振",
        "desc": "净流入≥500万+大单买入≥8%+量比≥1.2+底40%+MA20支撑+涨幅≥1%",
        "sql_filter": """
  AND net_mf_amount >= 5000000
  AND buy_lg_vol + sell_lg_vol > 0
  AND buy_lg_vol / (buy_lg_vol + sell_lg_vol) >= 0.08
  AND volume_ratio >= 1.2
  AND pos_20d <= 0.40
  AND ma20 IS NOT NULL AND close >= ma20
  AND pct_chg >= 1
""",
    },
]

def compute_stats(fwd_vals):
    """Compute win rate, avg return, sharpe from forward return list"""
    n = len(fwd_vals)
    if n < 5:
        return {"wr": 0, "ret": 0, "sharpe": 0, "n": n}
    wr = sum(1 for v in fwd_vals if v > 0) / n * 100
    avg_ret = sum(fwd_vals) / n * 100
    mean = sum(fwd_vals) / n
    var = sum((v - mean)**2 for v in fwd_vals) / n
    std = math.sqrt(var) if var > 0 else 0.0001
    sharpe = (mean / std) * math.sqrt(252 / 5)  # 5-day holding for sharpe
    return {"wr": round(wr, 2), "ret": round(avg_ret, 4), "sharpe": round(sharpe, 3), "n": n}

def main():
    print("="*70)
    print("T4 资金主力视角 - Iter 2")
    print(f"执行: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据基准: {MAX_DATE}")
    print(f"回测: {DATA_START} ~ {MAX_DATE}")
    print("SQL: leadInFrame fwd returns + Python stats")
    print("="*70)
    print(f"\n加载基础数据 (一次查询, 所有条件)...")
    print("这可能需要 1-2 分钟...\n")
    
    # Load base data (with circ_mv)
    base = ch_query(BASE_SQL.replace("{DATA_START}", DATA_START).replace("{MAX_DATE}", MAX_DATE))
    print(f"  基础数据: {len(base)} 条信号候选\n")
    
    if len(base) == 0:
        print("❌ 基础数据为空，退出")
        return []
    
    # Also load circ_mv separately (to avoid complicating the main query)
    print("[补充] Loading circ_mv for market cap filter...")
    mv_rows = ch_query(f"SELECT ts_code, trade_date, circ_mv FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}'")
    mv_idx = {}
    for r in mv_rows:
        mv_idx[(r["ts_code"], str(r["trade_date"]).replace("-",""))] = r.get("circ_mv", 0)
    print(f"  {len(mv_idx)} entries")
    
    # Build index for base data
    base_by_code_td = {}
    for r in base:
        base_by_code_td[(r["ts_code"], str(r["trade_date"]).replace("-",""))] = r
    
    hold_days = [1, 3, 5, 10, 20]
    all_results = []
    
    for ci, combo in enumerate(COMBOS):
        params_desc = combo["desc"]
        h = combo_hash({"name": combo["name"], "filter": combo["sql_filter"]})
        print(f"\n{'='*60}")
        print(f"[{ci+1}/5] {combo['name']} [{h}]")
        print(f"  条件: {params_desc}")
        
        # Apply filter to base data
        # We'll do the filtering in Python on the base data
        matched = []
        for r in base:
            code = r["ts_code"]
            td = str(r["trade_date"]).replace("-","")
            close = r["close"]
            pct_chg = r["pct_chg"]
            pos_20d = r.get("pos_20d")
            net_mf = r.get("net_mf_amount")
            buy_lg = r.get("buy_lg_vol", 0) or 0
            sell_lg = r.get("sell_lg_vol", 0) or 0
            vol_ratio = r.get("volume_ratio")
            turnover = r.get("turnover_rate")
            ma5 = r.get("ma5")
            ma10 = r.get("ma10")
            ma20 = r.get("ma20")
            ma60 = r.get("ma60")
            ma_spread = r.get("ma_spread")
            high_20d = r.get("high_20d")
            fwd_5 = r.get("fwd_5")
            
            p = combo["sql_filter"]  # just use for reference
            
            # Filter logic
            skip = False
            
            # net_mf
            if "net_mf_amount" in p:
                min_mf = 5000000 if "5000000" in p else (2000000 if "2000000" in p else 20000000)
                if net_mf is None or net_mf < min_mf:
                    skip = True
            
            # buy_lg_ratio
            if "buy_lg_vol" in p:
                total_lg = buy_lg + sell_lg
                min_ratio = 0.10 if "0.10" in p else 0.08
                if total_lg <= 0 or buy_lg / total_lg < min_ratio:
                    skip = True
            
            # position
            if "pos_20d" in p:
                max_pos = 0.40 if "0.40" in p else 0.20
                if pos_20d is None or pos_20d > max_pos:
                    skip = True
            
            # pct_chg
            if "pct_chg >=" in p or "pct_chg >" in p:
                min_pct = -3 if "-3" in p else (0 if "0" in p else 1)
                if pct_chg is None or pct_chg < min_pct:
                    skip = True
            
            # volume_ratio
            if "volume_ratio" in p:
                min_vr = 1.2 if "1.2" in p else (1.0 if "1.0" in p else 0.8)
                if vol_ratio is None or vol_ratio < min_vr:
                    skip = True
            
            # turnover
            if "turnover_rate" in p:
                if "turnover_rate <=" in p or "turnover_rate <=" in p:
                    max_tr = 0.10
                    if turnover is None or turnover > max_tr:
                        skip = True
                if "turnover_rate >=" in p:
                    min_tr = 0.01
                    if turnover is None or turnover < min_tr:
                        skip = True
            
            # ma support
            if "close >= ma20" in p:
                if ma20 is None or close < ma20:
                    skip = True
            
            # ma arrangement (bullish)
            if "ma5 > ma10" in p:
                if ma5 is None or ma10 is None or ma20 is None or ma60 is None:
                    skip = True
                elif not (ma5 > ma10 > ma20 > ma60):
                    skip = True
            
            # ma sticky
            if "ma_spread" in p:
                if ma_spread is None or ma_spread >= 0.03:
                    skip = True
            
            # high_20d
            if "high_20d" in p:
                if high_20d is None or close < high_20d:
                    skip = True
            
            # market cap (need separate lookup)
            if "circ_mv" in p:
                mv = mv_idx.get((code, td))
                if mv is None or not (mv >= 3e9 and mv < 10e9):
                    skip = True
            
            if not skip and fwd_5 is not None:
                matched.append(r)
        
        n = len(matched)
        print(f"  信号数: {n}")
        
        if n < 5:
            print(f"  ⚠️ 信号不足")
            all_results.append({"name": combo["name"], "hash": h, "signal_count": n, "hold_results": {d: {"wr": 0, "ret": 0, "sharpe": 0, "n": 0} for d in hold_days}})
            continue
        
        # Compute forward returns
        hold_results = {}
        for hd in hold_days:
            fwd_key = f"fwd_{hd}"
            vals = []
            for r in matched:
                fwd = r.get(fwd_key)
                close_signal = r["close"]
                if fwd is not None and close_signal is not None and close_signal > 0:
                    vals.append((fwd / close_signal) - 1)
            hold_results[hd] = compute_stats(vals)
        
        all_results.append({"name": combo["name"], "hash": h, "signal_count": n, "hold_results": hold_results})
        
        print(f"  结果:")
        for hd in hold_days:
            if hd in hold_results:
                r = hold_results[hd]
                print(f"    T+{hd:2d}: N={r['n']:6d} | WR={r['wr']:5.2f}% | Ret={r['ret']:6.4f}% | Sharpe={r['sharpe']:6.3f}")
    
    # ─── Summary ───
    print("\n" + "="*70)
    print("T4 Iter 2 — 最终汇总")
    print("="*70)
    print(f"\n{'组合':30s} {'信号':>6s} {'WR_5d':>8s} {'Ret_5d':>10s} {'Sharpe':>8s} {'Status':>10s}")
    print("-"*72)
    
    best_ret = best_wr = best_comp = None
    for res in all_results:
        n = res["signal_count"]
        hr = res["hold_results"]
        if 5 in hr:
            d5 = hr[5]
            w, r5, sh, n5 = d5["wr"], d5["ret"], d5["sharpe"], d5["n"]
            ok = w >= 52 and r5 >= 3 and n >= 200
            print(f"{res['name']:30s} {n:>6d} {w:>7.2f}% {r5:>9.4f}% {sh:>7.3f} {'✅' if ok else '❌':>10s}")
            if best_ret is None or r5 > best_ret[0]: best_ret = (r5, w, n, res["name"])
            if best_wr is None or w > best_wr[0]: best_wr = (w, r5, n, res["name"])
            score = w * 0.3 + r5 * 4 * 0.4 + min(n/200, 10)*10*0.3
            if best_comp is None or score > best_comp[0]: best_comp = (score, w, r5, n, res["name"])
        else:
            print(f"{res['name']:30s} {n:>6d} {'N/A':>8s} {'N/A':>10s} {'N/A':>8s} {'❌':>10s}")
    
    print()
    if best_ret: print(f"🏆 Best Ret_5d: {best_ret[3]} | Ret={best_ret[0]:.2f}% | WR={best_ret[1]:.2f}% | N={best_ret[2]}")
    if best_wr: print(f"🏆 Best WR_5d:  {best_wr[3]} | WR={best_wr[0]:.2f}% | Ret={best_wr[1]:.2f}% | N={best_wr[2]}")
    if best_comp: print(f"🏆 Best Comp:   {best_comp[4]} | WR={best_comp[1]:.2f}% | Ret={best_comp[2]:.2f}% | N={best_comp[3]}")
    
    any_pass = any(5 in res["hold_results"] and res["hold_results"][5]["wr"] >= 52 and res["hold_results"][5]["ret"] >= 3 and res["signal_count"] >= 200 for res in all_results)
    print(f"\n{'✅' if any_pass else '⚠️'} 本轮{'有' if any_pass else '无'}组合完全达标")
    
    return all_results

if __name__ == "__main__":
    results = main()
