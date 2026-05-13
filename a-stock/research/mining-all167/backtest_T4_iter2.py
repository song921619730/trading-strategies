#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 2 回测 (chunked loading, fixed timeout)"""
import json, hashlib, os, math, subprocess, sys
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
# Use shorter date range for daily_basic/moneyflow to avoid timeout
DATA_START = "20230101"  
HISTORY_START = "20190101"  # for MA calculations
MAX_DATE = "20260511"

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
    s = str(d).replace("-", "")
    return int(s)

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    return hashlib.md5(",".join(f"{k}={v}" for k,v in pairs).encode()).hexdigest()[:12]

# ─── 5组参数组合 ───
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
        "desc": "主力温和吸筹+低位放量启动+均线支撑+中小盘"
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
        "desc": "大单扫货+20日新高突破+量能放大+趋势确认"
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
        "desc": "主力护盘+超低位+均线粘合蓄力"
    },
    {
        "name": "大额资金+多头排列",
        "params": {
            "net_mf_min": 20000000,
            "pct_chg_1d_min": 0,
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "中小盘(30-100亿)",
            "turnover_rate_min": 0.01,
            "volume_ratio_min": 1.0,
        },
        "desc": "大额主力扫货+多头排列+中小盘放量"
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
        "desc": "资金主力共振+低位放量+均线支撑"
    },
]

def calc_ma_arr(closes, n):
    r = [None]*(n-1)
    for i in range(n-1, len(closes)):
        r.append(sum(closes[i-n+1:i+1])/n)
    return r

def is_ma_bullish(ma5, ma10, ma20, ma60):
    return all(v is not None for v in [ma5, ma10, ma20, ma60]) and ma5 > ma10 > ma20 > ma60

def is_ma_sticky(closes_60):
    n = len(closes_60)
    if n < 60: return False
    ma5 = sum(closes_60[-5:]) / 5
    ma10 = sum(closes_60[-10:]) / 10
    ma20 = sum(closes_60[-20:]) / 20
    ma60 = sum(closes_60[-60:]) / 60
    min_ma = min(ma5, ma10, ma20, ma60)
    if min_ma == 0: return False
    return (max(ma5, ma10, ma20, ma60) - min_ma) / min_ma < 0.03

def load_data():
    """Load all needed data in chunks"""
    print("\n[1/5] Loading stock_daily (full history)...")
    rows = ch_query(f"""SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount 
        FROM tushare.tushare_stock_daily FINAL 
        WHERE trade_date >= '{HISTORY_START}' AND trade_date <= '{MAX_DATE}' 
        AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'""")
    print(f"  {len(rows)} rows")
    by_code = defaultdict(list)
    for r in rows:
        by_code[r["ts_code"]].append(r)
    for c in by_code:
        by_code[c].sort(key=lambda x: parse_date(x["trade_date"]))
    print(f"  {len(by_code)} stocks")

    print("[2/5] Loading daily_basic (from 2023)...")
    brow = ch_query(f"""SELECT ts_code, trade_date, turnover_rate, volume_ratio, pe, pb, circ_mv 
        FROM tushare.tushare_daily_basic FINAL 
        WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}' 
        AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'""")
    bd = {}
    for r in brow:
        bd[(r["ts_code"], parse_date(r["trade_date"]))] = r
    print(f"  {len(brow)} rows, {len(bd)} unique keys")

    print("[3/5] Loading moneyflow (from 2023)...")
    mrow = ch_query(f"""SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, 
        buy_elg_vol, sell_elg_vol, net_mf_amount 
        FROM tushare.tushare_moneyflow FINAL 
        WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}'""")
    mf = {}
    for r in mrow:
        mf[(r["ts_code"], parse_date(r["trade_date"]))] = r
    print(f"  {len(mrow)} rows")

    print("[4/5] Loading limit_list...")
    lrow = ch_query(f"""SELECT ts_code, trade_date FROM tushare.tushare_limit_list_d FINAL 
        WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}' AND limit = 'U'""")
    lim = defaultdict(set)
    for r in lrow:
        lim[r["ts_code"]].add(parse_date(r["trade_date"]))
    print(f"  {len(lrow)} records")

    print("[5/5] Loading market cap reference (recent)...")
    cap_rows = ch_query(f"SELECT ts_code, trade_date, circ_mv FROM tushare.tushare_daily_basic FINAL WHERE trade_date = '{MAX_DATE}'")
    mcap_ref = {}
    for r in cap_rows:
        mcap_ref[r["ts_code"]] = r.get("circ_mv")
    print(f"  {len(mcap_ref)} stocks")

    return by_code, bd, mf, lim, mcap_ref

def main():
    print("="*70)
    print(f"T4 资金主力视角 - Iter 2")
    print(f"执行: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据基准: {MAX_DATE}")
    print(f"回测周期: {DATA_START} ~ {MAX_DATE} (daily_basic/moneyflow)")
    print(f"行情周期: {HISTORY_START} ~ {MAX_DATE} (stock_daily for MA)")
    print("="*70)

    by_code, bd, mf, lim, mcap_ref = load_data()
    hold_days = [1, 3, 5, 10, 20]
    all_results = []

    for ci, combo in enumerate(COMBOS):
        params = combo["params"]
        name = combo["name"]
        h = combo_hash(params)
        print(f"\n{'='*60}")
        print(f"[{ci+1}/5] {name} [{h}]")
        print(f"  参数: {params}")

        signals = []

        for code, bars in by_code.items():
            if len(bars) < 60:
                continue

            closes = [b["close"] for b in bars if b["close"] is not None]
            if len(closes) < 60:
                continue

            ma5_arr = calc_ma_arr(closes, 5)
            ma10_arr = calc_ma_arr(closes, 10)
            ma20_arr = calc_ma_arr(closes, 20)
            ma60_arr = calc_ma_arr(closes, 60)

            for i in range(60, len(bars)):
                bar = bars[i]
                td = parse_date(bar["trade_date"])
                close = bar["close"]
                pct_chg = bar["pct_chg"]
                if close is None or pct_chg is None:
                    continue

                # Date must be within DATA_START range for daily_basic/moneyflow data
                if td < parse_date(DATA_START):
                    continue

                # ── pct_chg ──
                if "pct_chg_1d_min" in params:
                    if pct_chg < params["pct_chg_1d_min"]:
                        continue

                # ── N-day high ──
                if "n_day_high" in params:
                    nd = params["n_day_high"]
                    if i < nd: continue
                    high_nd = max(b["high"] for b in bars[i-nd+1:i+1] if b["high"] is not None)
                    if close < high_nd: continue

                # ── daily_basic lookups ──
                db = bd.get((code, td))
                if "volume_ratio_min" in params or "turnover_rate_min" in params or "turnover_rate_max" in params or "market_cap_bucket" in params:
                    if db is None: continue

                if "volume_ratio_min" in params:
                    vr = db.get("volume_ratio")
                    if vr is None or vr < params["volume_ratio_min"]: continue

                if "turnover_rate_min" in params:
                    tr = db.get("turnover_rate")
                    if tr is None or tr < params["turnover_rate_min"]: continue

                if "turnover_rate_max" in params:
                    tr = db.get("turnover_rate")
                    if tr is None or tr >= params["turnover_rate_max"]: continue

                # ── Market cap ──
                if "market_cap_bucket" in params:
                    circ_mv = mcap_ref.get(code)
                    if circ_mv is None:
                        circ_mv = db.get("circ_mv") if db else None
                    bucket = params["market_cap_bucket"]
                    if circ_mv is not None:
                        if bucket == "小盘(<30亿)" and not (circ_mv > 0 and circ_mv < 3e9): continue
                        elif bucket == "中小盘(30-100亿)" and not (circ_mv >= 3e9 and circ_mv < 10e9): continue
                        elif bucket == "中大盘(100-500亿)" and not (circ_mv >= 10e9 and circ_mv < 50e9): continue
                        elif bucket == "大盘(>500亿)" and not (circ_mv >= 50e9): continue

                # ── MA support ──
                if "ma_support" in params:
                    ms = params["ma_support"]
                    ma_val = {"MA5": ma5_arr[i], "MA10": ma10_arr[i], "MA20": ma20_arr[i], "MA60": ma60_arr[i]}.get(ms)
                    if ma_val is None or close < ma_val: continue

                # ── MA arrangement ──
                if "ma_arrangement" in params:
                    arr = params["ma_arrangement"]
                    if arr == "多头排列":
                        if not is_ma_bullish(ma5_arr[i], ma10_arr[i], ma20_arr[i], ma60_arr[i]): continue
                    elif arr == "粘合(差<3%)":
                        seg = closes[max(0,i-59):i+1]
                        if not is_ma_sticky(seg): continue

                # ── price position ──
                if "close_position" in params:
                    pos = params["close_position"]
                    if i < 19: continue
                    low_20 = min(b["low"] for b in bars[i-19:i+1] if b["low"] is not None)
                    high_20 = max(b["high"] for b in bars[i-19:i+1] if b["high"] is not None)
                    pos_20d = (close - low_20) / (high_20 - low_20) if high_20 > low_20 else 0.5
                    if pos == "底20%" and pos_20d > 0.2: continue
                    elif pos == "底40%" and pos_20d > 0.4: continue

                # ── moneyflow ──
                flow = mf.get((code, td))
                if "net_mf_min" in params or "buy_lg_ratio_min" in params:
                    if flow is None: continue

                if "net_mf_min" in params:
                    net_mf = flow.get("net_mf_amount", 0) or 0
                    if net_mf < params["net_mf_min"]: continue

                if "buy_lg_ratio_min" in params:
                    buy_lg = flow.get("buy_lg_vol", 0) or 0
                    sell_lg = flow.get("sell_lg_vol", 0) or 0
                    total_lg = buy_lg + sell_lg
                    if total_lg <= 0 or buy_lg / total_lg < params["buy_lg_ratio_min"]: continue

                # ── limit list ──
                signals.append((code, td, close))

        print(f"  原始信号: {len(signals)}")

        if len(signals) == 0:
            hr = {d: {"wr": 0, "ret": 0, "sharpe": 0, "std": 0, "n": 0} for d in hold_days}
            all_results.append({"name": name, "hash": h, "params": params, "signal_count": 0, "hold_results": hr, "desc": combo["desc"]})
            continue

        # Forward returns
        hold_results = {}
        for hd in hold_days:
            fwd_returns = []
            for code, td, close_signal in signals:
                bars_for_code = by_code.get(code, [])
                target_idx = None
                for bi, b in enumerate(bars_for_code):
                    if parse_date(b["trade_date"]) == td:
                        target_idx = bi
                        break
                if target_idx is None or target_idx + hd >= len(bars_for_code):
                    continue
                fwd_close = bars_for_code[target_idx + hd]["close"]
                if fwd_close is not None and close_signal is not None and close_signal > 0:
                    fwd_returns.append((fwd_close / close_signal) - 1)

            n = len(fwd_returns)
            if n < 5:
                hold_results[hd] = {"wr": 0, "ret": 0, "sharpe": 0, "std": 0, "n": n}
                continue

            wr = sum(1 for r_ in fwd_returns if r_ > 0) / n * 100
            avg_ret = sum(fwd_returns) / n * 100
            mean_ret = sum(fwd_returns) / n
            variance = sum((r - mean_ret)**2 for r in fwd_returns) / n
            std = math.sqrt(variance) if variance > 0 else 0.0001
            sharpe = (mean_ret / std) * math.sqrt(252 / hd) if std > 0 else 0

            hold_results[hd] = {"wr": round(wr, 2), "ret": round(avg_ret, 4), "sharpe": round(sharpe, 3), "std": round(std, 6), "n": n}

        all_results.append({"name": name, "hash": h, "params": params, "signal_count": len(signals), "hold_results": hold_results, "desc": combo["desc"]})

        # Print summary
        hr = hold_results
        print(f"  结果:")
        for hd in [1, 3, 5, 10, 20]:
            if hd in hr:
                r = hr[hd]
                print(f"    T+{hd:2d}: N={r['n']:6d} | WR={r['wr']:5.2f}% | Ret={r['ret']:6.4f}% | Sharpe={r['sharpe']:6.3f}")

    # ─── Final summary ───
    print("\n" + "="*70)
    print("T4 Iter 2 — 最终汇总")
    print("="*70)
    print(f"\n{'组合名称':30s} {'N':>8s} {'WR_5d':>8s} {'Ret_5d':>10s} {'Sharpe':>8s} {'Status':>10s}")
    print("-"*74)

    best_ret = None
    best_wr = None
    best_comp = None

    for res in all_results:
        hr = res["hold_results"]
        n = res["signal_count"]
        if 5 in hr:
            d5 = hr[5]
            wr5 = d5["wr"]
            r5 = d5["ret"]
            sh5 = d5["sharpe"]
            n5 = d5["n"]
            passes = wr5 >= 52 and r5 >= 3 and n >= 200
            status = "✅" if passes else "❌"
            print(f"{res['name']:30s} {n:>8d} {wr5:>7.2f}% {r5:>9.4f}% {sh5:>7.3f} {status:>10s}")

            if best_ret is None or r5 > best_ret[0]:
                best_ret = (r5, wr5, n, res)
            if best_wr is None or wr5 > best_wr[0]:
                best_wr = (wr5, r5, n, res)
            score = wr5 * 0.3 + r5 * 4 * 0.4 + min(n / 200, 10) * 10 * 0.3
            if best_comp is None or score > best_comp[0]:
                best_comp = (score, wr5, r5, n, res)
        else:
            print(f"{res['name']:30s} {'0':>8s} {'N/A':>8s} {'N/A':>10s} {'N/A':>8s} {'❌':>10s}")

    print("\n" + "="*70)
    if best_ret:
        print(f"🏆 Best Ret_5d: {best_ret[3]['name']} | Ret={best_ret[0]:.4f}% | WR={best_ret[1]:.2f}% | N={best_ret[2]}")
    if best_wr:
        print(f"🏆 Best WR_5d:  {best_wr[3]['name']} | WR={best_wr[0]:.2f}% | Ret={best_wr[1]:.4f}% | N={best_wr[2]}")
    if best_comp:
        print(f"🏆 Best Comp:   {best_comp[4]['name']} | WR={best_comp[1]:.2f}% | Ret={best_comp[2]:.4f}% | N={best_comp[3]}")

    return all_results

if __name__ == "__main__":
    results = main()
