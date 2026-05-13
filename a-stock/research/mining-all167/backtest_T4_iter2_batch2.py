#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 2 BATCH 2 (relaxed params for more signals)
"""
import json, hashlib, subprocess, math, sys
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE = "20260511"
DATA_START = "20230101"
HIST_START = "20190101"

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"  [SQL ERROR] {r.stderr[:300]}", file=sys.stderr)
        return []
    try: return json.loads(r.stdout) if isinstance(json.loads(r.stdout), list) else json.loads(r.stdout).get("data", [])
    except: return []

def parse_date(d): return int(str(d).replace("-", ""))

def combo_hash(params):
    return hashlib.md5(",".join(f"{k}={v}" for k,v in sorted(params.items())).encode()).hexdigest()[:12]

# ═══ MUCH MORE RELAXED COMBOS ═══
COMBOS = [
    {
        "name": C[0],
        "params": C[1]
    }
    for C in [
        # Combo 1: Copy of iter 1's best "底部放量+主力吸筹" with slight tuning
        ("底部放量+主力吸筹(放宽)",
         {"net_mf_min": 3000000, "close_position": "底40%", "pct_chg_1d_min": -2,
          "volume_ratio_min": 0.8, "ma_support": "MA20"}),

        # Combo 2: Pure capital flow + any price action
        ("主力净流入+温和放量",
         {"net_mf_min": 1000000, "volume_ratio_min": 0.8, "pct_chg_1d_min": -1,
          "turnover_rate_min": 0.003, "turnover_rate_max": 0.20}),

        # Combo 3: Ultra-broad capital flow filter
        ("大资金净流入(极宽)",
         {"net_mf_min": 500000, "pct_chg_1d_min": -5, "volume_ratio_min": 0.5}),  

        # Combo 4: Large order ratio + moderate volume
        ("大单买入占比高+放量",
         {"buy_lg_ratio_min": 0.08, "volume_ratio_min": 1.0, "pct_chg_1d_min": 0,
          "turnover_rate_max": 0.15}),

        # Combo 5: Multi-factor but very relaxed
        ("主力+大单+低位(综合)",
         {"net_mf_min": 1000000, "buy_lg_ratio_min": 0.06, "volume_ratio_min": 0.8,
          "pct_chg_1d_min": -3, "close_position": "底40%"}),
    ]
]

def calc_ma(closes, n):
    r = [None]*(n-1)
    for i in range(n-1, len(closes)): r.append(sum(closes[i-n+1:i+1])/n)
    return r

def main():
    print("="*70)
    print("T4 资金主力视角 - Iter 2 BATCH 2")
    print(f"执行: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据基准: {MAX_DATE}")
    print("="*70)

    # ─── Load data ───
    print("\n[1/4] Loading stock_daily...")
    rows = ch_query(f"SELECT ts_code, trade_date, open, high, low, close, pct_chg FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '{HIST_START}' AND trade_date <= '{MAX_DATE}' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND close IS NOT NULL")
    by_code = defaultdict(list)
    for r in rows:
        by_code[r["ts_code"]].append(r)
    for c in by_code:
        by_code[c].sort(key=lambda x: parse_date(x["trade_date"]))
    print(f"  {len(rows)} rows, {len(by_code)} stocks")

    print("[2/4] Loading daily_basic (from 2023)...")
    brow = ch_query(f"SELECT ts_code, trade_date, volume_ratio, turnover_rate FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'")
    bd = {}
    for r in brow:
        bd[(r["ts_code"], parse_date(r["trade_date"]))] = r
    print(f"  {len(brow)} rows")

    print("[3/4] Loading moneyflow (no FINAL)...")
    mrow = ch_query(f"SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, net_mf_amount FROM tushare.tushare_moneyflow WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}'")
    mf = {}
    for r in mrow:
        mf[(r["ts_code"], parse_date(r["trade_date"]))] = r
    print(f"  {len(mrow)} rows")

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

                if "pct_chg_1d_min" in p and pct_chg < p["pct_chg_1d_min"]: continue

                db = bd.get((code, td))
                need_db = any(k in p for k in ["volume_ratio_min", "turnover_rate_min", "turnover_rate_max"])
                if need_db and db is None: continue

                if "volume_ratio_min" in p:
                    if db.get("volume_ratio") is None or db["volume_ratio"] < p["volume_ratio_min"]: continue
                if "turnover_rate_min" in p:
                    if db.get("turnover_rate") is None or db["turnover_rate"] < p["turnover_rate_min"]: continue
                if "turnover_rate_max" in p:
                    if db.get("turnover_rate") is None or db["turnover_rate"] >= p["turnover_rate_max"]: continue

                if "ma_support" in p:
                    ms = p["ma_support"]
                    mv = {"MA5": ma5[i], "MA10": ma10[i], "MA20": ma20[i], "MA60": ma60[i]}.get(ms)
                    if mv is None or close < mv: continue

                if "close_position" in p:
                    if i < 19: continue
                    lo = min(b["low"] for b in bars[i-19:i+1] if b["low"] is not None)
                    hi = max(b["high"] for b in bars[i-19:i+1] if b["high"] is not None)
                    pos = (close - lo) / (hi - lo) if hi > lo else 0.5
                    pp = p["close_position"]
                    if pp == "底20%" and pos > 0.2: continue
                    elif pp == "底40%" and pos > 0.4: continue

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

        n = len(signals)
        print(f"  信号数: {n}")
        if n < 5:
            all_results.append({"name": combo["name"], "hash": h, "signal_count": n, "hold_results": {d: {"wr":0,"ret":0,"sharpe":0,"n":0} for d in hold_days}})
            continue

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
            nf = len(fwd)
            if nf < 5:
                hold_results[hd] = {"wr": 0, "ret": 0, "sharpe": 0, "n": nf}
                continue
            wr = sum(1 for v in fwd if v > 0) / nf * 100
            ar = sum(fwd) / nf * 100
            mn = sum(fwd) / nf
            var = sum((v - mn)**2 for v in fwd) / nf
            std = math.sqrt(var) if var > 0 else 0.0001
            sh = (mn / std) * math.sqrt(252 / hd) if std > 0 else 0
            hold_results[hd] = {"wr": round(wr, 2), "ret": round(ar, 4), "sharpe": round(sh, 3), "n": nf}

        all_results.append({"name": combo["name"], "hash": h, "signal_count": n, "hold_results": hold_results})
        for hd in hold_days:
            if hd in hold_results and hold_results[hd]["n"] > 0:
                r = hold_results[hd]
                print(f"    T+{hd:2d}: N={r['n']:6d} | WR={r['wr']:5.2f}% | Ret={r['ret']:6.4f}% | Sharpe={r['sharpe']:6.3f}")

    # ─── Summary ───
    print("\n" + "="*70)
    print("T4 Iter 2 — BATCH 2 最终汇总")
    print("="*70)
    print(f"\n{'组合':35s} {'信号数':>6s} {'WR_5d':>8s} {'Ret_5d':>10s} {'Sharpe':>8s} {'Status':>10s}")
    print("-"*77)

    best_r5 = best_w5 = best_c = None
    for res in all_results:
        n = res["signal_count"]
        hr = res["hold_results"]
        if 5 in hr and hr[5]["n"] >= 5:
            d5 = hr[5]
            ok = d5["wr"] >= 52 and d5["ret"] >= 3 and n >= 200
            print(f"{res['name']:35s} {n:>6d} {d5['wr']:>7.2f}% {d5['ret']:>9.4f}% {d5['sharpe']:>7.3f} {'✅' if ok else '❌':>10s}")
            if best_r5 is None or d5["ret"] > best_r5[0]: best_r5 = (d5["ret"], d5["wr"], n, res["name"])
            if best_w5 is None or d5["wr"] > best_w5[0]: best_w5 = (d5["wr"], d5["ret"], n, res["name"])
            sc = d5["wr"]*0.3 + d5["ret"]*4*0.4 + min(n/200,10)*10*0.3
            if best_c is None or sc > best_c[0]: best_c = (sc, d5["wr"], d5["ret"], n, res["name"])
        else:
            print(f"{res['name']:35s} {n:>6d} {'N/A':>8s} {'N/A':>10s} {'N/A':>8s} {'❌':>10s}")

    print()
    if best_r5: print(f"🏆 Best Ret_5d: {best_r5[3]} | Ret={best_r5[0]:.2f}% | WR={best_r5[1]:.2f}% | N={best_r5[2]}")
    if best_w5: print(f"🏆 Best WR_5d:  {best_w5[3]} | WR={best_w5[0]:.2f}% | Ret={best_w5[1]:.2f}% | N={best_w5[2]}")
    if best_c: print(f"🏆 Best Comp:   {best_c[4]} | WR={best_c[1]:.2f}% | Ret={best_c[2]:.2f}% | N={best_c[3]}")

    ap = any(5 in res["hold_results"] and res["hold_results"][5]["wr"] >= 52 and res["hold_results"][5]["ret"] >= 3 and res["signal_count"] >= 200 for res in all_results)
    print(f"\n{'🎉 有组合完全达标!' if ap else '⚠️ 本轮无组合完全达标'}")
    return all_results

if __name__ == "__main__":
    results = main()
