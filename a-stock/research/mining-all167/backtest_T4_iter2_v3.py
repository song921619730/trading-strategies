#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 2 (proven Python-based approach)
Pre-load data from ClickHouse, filter in Python, compute fwd returns.
"""
import json, hashlib, subprocess, math, sys
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE = "20260511"
DATA_START = "20230101"  # For daily_basic/moneyflow
HIST_START = "20190101"  # For stock_daily (needs 60-day history)

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

COMBOS = [
    {"name": "主力吸筹+底部放量起涨",
     "params": {"net_mf_min": 5000000, "close_position": "底40%", "pct_chg_1d_min": 1,
                "volume_ratio_min": 1.0, "ma_support": "MA20", "market_cap_bucket": "中小盘(30-100亿)"}},
    {"name": "大单扫货+突破前高",
     "params": {"buy_lg_ratio_min": 0.10, "n_day_high": 20, "volume_ratio_min": 1.5,
                "ma_arrangement": "多头排列", "turnover_rate_max": 0.10}},
    {"name": "主力护盘+均线粘合待发",
     "params": {"net_mf_min": 2000000, "pct_chg_1d_min": -3, "close_position": "底20%",
                "ma_arrangement": "粘合(差<3%)", "volume_ratio_min": 0.8}},
    {"name": "大额资金+多头排列+中小盘",
     "params": {"net_mf_min": 20000000, "pct_chg_1d_min": 0, "ma_arrangement": "多头排列",
                "market_cap_bucket": "中小盘(30-100亿)", "turnover_rate_min": 0.01, "volume_ratio_min": 1.0}},
    {"name": "多维度主力共振+低位放量",
     "params": {"net_mf_min": 5000000, "buy_lg_ratio_min": 0.08, "volume_ratio_min": 1.2,
                "close_position": "底40%", "ma_support": "MA20", "pct_chg_1d_min": 1, "turnover_rate_min": 0.005}},
]

def calc_ma(closes, n):
    r = [None]*(n-1)
    for i in range(n-1, len(closes)):
        r.append(sum(closes[i-n+1:i+1])/n)
    return r

def main():
    print("="*70)
    print("T4 资金主力视角 - Iter 2")
    print(f"执行: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据基准: {MAX_DATE}")
    print(f"Python filtering on pre-loaded data")
    print("="*70)

    # ─── Load data ───
    print("\n[1/5] Loading stock_daily (from 2019 for MA calc)...")
    rows = ch_query(f"""SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '{HIST_START}' AND trade_date <= '{MAX_DATE}'
        AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
        AND close IS NOT NULL""")
    by_code = defaultdict(list)
    for r in rows:
        by_code[r["ts_code"]].append(r)
    for c in by_code:
        by_code[c].sort(key=lambda x: parse_date(x["trade_date"]))
    print(f"  {len(rows)} rows, {len(by_code)} stocks")

    print("[2/5] Loading daily_basic (from 2023)...")
    brow = ch_query(f"""SELECT ts_code, trade_date, volume_ratio, turnover_rate, circ_mv
        FROM tushare.tushare_daily_basic FINAL
        WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}'
        AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'""")
    bd = {}
    for r in brow:
        bd[(r["ts_code"], parse_date(r["trade_date"]))] = r
    print(f"  {len(brow)} rows")

    print("[3/5] Loading moneyflow (from 2023, no FINAL)...")
    mrow = ch_query(f"""SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, net_mf_amount
        FROM tushare.tushare_moneyflow
        WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}'""")
    mf = {}
    for r in mrow:
        mf[(r["ts_code"], parse_date(r["trade_date"]))] = r
    print(f"  {len(mrow)} rows")

    # ─── Load market cap reference ───
    print("[4/5] Loading circ_mv reference...")
    cap_rows = ch_query(f"SELECT ts_code, circ_mv FROM tushare.tushare_daily_basic FINAL WHERE trade_date = '{MAX_DATE}'")
    mcap = {}
    for r in cap_rows:
        mcap[r["ts_code"]] = r.get("circ_mv", 0)
    print(f"  {len(cap_rows)} stocks")

    hold_days = [1, 3, 5, 10, 20]
    all_results = []

    for ci, combo in enumerate(COMBOS):
        p = combo["params"]
        h = combo_hash(p)
        print(f"\n{'='*60}")
        print(f"[{ci+1}/5] {combo['name']} [{h}]")
        print(f"  参数: {p}")

        signals = []
        for code, bars in by_code.items():
            if len(bars) < 60: continue
            closes = [b["close"] for b in bars if b["close"] is not None]
            if len(closes) < 60: continue

            ma5 = calc_ma(closes, 5)
            ma10 = calc_ma(closes, 10)
            ma20 = calc_ma(closes, 20)
            ma60 = calc_ma(closes, 60)

            for i in range(60, len(bars)):
                bar = bars[i]
                td = parse_date(bar["trade_date"])
                close = bar["close"]
                pct_chg = bar["pct_chg"]
                if close is None or pct_chg is None: continue
                if td < parse_date(DATA_START): continue

                # pct_chg
                if "pct_chg_1d_min" in p and pct_chg < p["pct_chg_1d_min"]: continue

                # n_day_high
                if "n_day_high" in p:
                    nd = p["n_day_high"]
                    if i < nd: continue
                    high_nd = max(b["high"] for b in bars[i-nd+1:i+1] if b["high"] is not None)
                    if close < high_nd: continue

                # daily_basic
                db = bd.get((code, td))
                need_db = any(k in p for k in ["volume_ratio_min", "turnover_rate_min", "turnover_rate_max"])
                if need_db and db is None: continue

                if "volume_ratio_min" in p:
                    vr = db.get("volume_ratio")
                    if vr is None or vr < p["volume_ratio_min"]: continue

                if "turnover_rate_min" in p:
                    tr = db.get("turnover_rate")
                    if tr is None or tr < p["turnover_rate_min"]: continue

                if "turnover_rate_max" in p:
                    tr = db.get("turnover_rate")
                    if tr is None or tr >= p["turnover_rate_max"]: continue

                # Market cap
                if "market_cap_bucket" in p:
                    mv = mcap.get(code) or (db.get("circ_mv") if db else None)
                    bucket = p["market_cap_bucket"]
                    if mv is not None:
                        if bucket == "中小盘(30-100亿)" and not (mv >= 3e9 and mv < 10e9): continue
                        elif bucket == "小盘(<30亿)" and not (mv > 0 and mv < 3e9): continue

                # MA support
                if "ma_support" in p:
                    ms = p["ma_support"]
                    ma_v = {"MA5": ma5[i], "MA10": ma10[i], "MA20": ma20[i], "MA60": ma60[i]}.get(ms)
                    if ma_v is None or close < ma_v: continue

                # MA arrangement
                if "ma_arrangement" in p:
                    a = p["ma_arrangement"]
                    if a == "多头排列":
                        if not (ma5[i] and ma10[i] and ma20[i] and ma60[i] and ma5[i] > ma10[i] > ma20[i] > ma60[i]): continue
                    elif a == "粘合(差<3%)":
                        m5, m10, m20, m60 = ma5[i], ma10[i], ma20[i], ma60[i]
                        if not (m5 and m10 and m20 and m60): continue
                        mx = max(m5, m10, m20, m60)
                        mn = min(m5, m10, m20, m60)
                        if mn == 0 or (mx/mn - 1) >= 0.03: continue

                # Position
                if "close_position" in p:
                    if i < 19: continue
                    lo = min(b["low"] for b in bars[i-19:i+1] if b["low"] is not None)
                    hi = max(b["high"] for b in bars[i-19:i+1] if b["high"] is not None)
                    pos = (close - lo) / (hi - lo) if hi > lo else 0.5
                    pp = p["close_position"]
                    if pp == "底20%" and pos > 0.2: continue
                    elif pp == "底40%" and pos > 0.4: continue

                # Moneyflow
                flow = mf.get((code, td))
                need_mf = "net_mf_min" in p or "buy_lg_ratio_min" in p
                if need_mf and flow is None: continue

                if "net_mf_min" in p:
                    nm = flow.get("net_mf_amount", 0) or 0
                    if nm < p["net_mf_min"]: continue

                if "buy_lg_ratio_min" in p:
                    bl = flow.get("buy_lg_vol", 0) or 0
                    sl = flow.get("sell_lg_vol", 0) or 0
                    if bl + sl <= 0 or bl / (bl + sl) < p["buy_lg_ratio_min"]: continue

                signals.append((code, td, close))

        print(f"  信号数: {len(signals)}")

        if len(signals) < 5:
            all_results.append({"name": combo["name"], "hash": h, "signal_count": len(signals),
                                "hold_results": {d: {"wr": 0, "ret": 0, "sharpe": 0, "n": 0} for d in hold_days}})
            continue

        # ─── Forward returns ───
        hold_results = {}
        for hd in hold_days:
            fwd = []
            for code, td, cs in signals:
                bars = by_code.get(code, [])
                si = next((bi for bi, b in enumerate(bars) if parse_date(b["trade_date"]) == td), None)
                if si is None or si + hd >= len(bars): continue
                fc = bars[si + hd]["close"]
                if fc is not None and cs is not None and cs > 0:
                    fwd.append((fc / cs) - 1)

            n = len(fwd)
            if n < 5:
                hold_results[hd] = {"wr": 0, "ret": 0, "sharpe": 0, "n": n}
                continue

            wr = sum(1 for v in fwd if v > 0) / n * 100
            avg_r = sum(fwd) / n * 100
            mn = sum(fwd) / n
            var = sum((v - mn)**2 for v in fwd) / n
            std = math.sqrt(var) if var > 0 else 0.0001
            sh = (mn / std) * math.sqrt(252 / hd) if std > 0 else 0
            hold_results[hd] = {"wr": round(wr, 2), "ret": round(avg_r, 4), "sharpe": round(sh, 3), "n": n}

        all_results.append({"name": combo["name"], "hash": h, "signal_count": len(signals), "hold_results": hold_results})
        hr = hold_results
        for hd in hold_days:
            if hd in hr and hr[hd]["n"] > 0:
                r = hr[hd]
                print(f"    T+{hd:2d}: N={r['n']:6d} | WR={r['wr']:5.2f}% | Ret={r['ret']:6.4f}% | Sharpe={r['sharpe']:6.3f}")

    # ─── Summary ───
    print("\n" + "="*70)
    print("T4 Iter 2 — 最终汇总")
    print("="*70)
    print(f"\n{'组合':30s} {'信号数':>6s} {'WR_5d':>8s} {'Ret_5d':>10s} {'Sharpe':>8s} {'Status':>10s}")
    print("-"*72)

    best_ret = best_wr = best_comp = None
    for res in all_results:
        n = res["signal_count"]
        hr = res["hold_results"]
        if 5 in hr and hr[5]["n"] >= 5:
            d5 = hr[5]
            w, r5, sh = d5["wr"], d5["ret"], d5["sharpe"]
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
    print(f"\n{'🎉 有组合完全达标!' if any_pass else '⚠️ 本轮无组合完全达标'}")

    return all_results

if __name__ == "__main__":
    results = main()
