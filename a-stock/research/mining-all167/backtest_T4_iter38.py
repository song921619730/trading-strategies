#!/usr/bin/env python3
"""T4 资金主力视角 - Iter38 回测 (Walk-Forward 验证版)
基于 iter37 发现：ELG主导(2x)最强，散户卖出基石，中单逆势大规模验证，高股息稳定器。
iter38 探索：ELG强度阶梯、持续ELG流入、恐慌-3%温和版、CM分层(50/100亿)、dv_ttm分层、SPX过滤、VR3天放量。
"""
import json, hashlib, subprocess, os, math, sys
from collections import defaultdict
from datetime import datetime, timedelta

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE = "2026-05-14"

# Walk-Forward 时间划分
IS_START = "2020-01-01"
IS_END   = "2024-12-31"
OOS_START = "2025-01-01"
OOS_END   = "2026-05-14"

OUTPUT_PATH = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_38/analysis_T4_资金主力.md"

def ch_query(sql):
    result = subprocess.run(
        ["python3", CH_QUERY, "sql", sql],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr[:300]}", file=sys.stderr)
        return []
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else data.get("data", [])
    except Exception:
        print(f"  [PARSE ERROR] {result.stdout[:300]}", file=sys.stderr)
        return []

def safe_float(v):
    if v is None: return 0.0
    return float(v)

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]

# ── 8组参数组合 (iter38 全新/改进) ──
COMBOS = [
    {
        "name": "C1: ELG主导1.5x+散户割肉+恐慌-4%+CM30亿",
        "params": {"elg_ratio_min": 1.5, "sell_sm_gt_buy_sm": True, "pct_max": -4, "amp_min": 5, "cp20_max": 0.3, "vr_min": 1.0, "cm_max": 300000},
        "desc": "iter37 C6的1.5x宽松版。测试ELG主导强度从2x降到1.5x是否提升信号量且保持WR。",
    },
    {
        "name": "C2: ELG主导3x+高股息+恐慌-4%+CM30亿",
        "params": {"elg_ratio_min": 3.0, "sell_sm_gt_buy_sm": True, "pct_max": -4, "amp_min": 5, "cp20_max": 0.3, "dv_min": 1.5, "vr_min": 1.0, "cm_max": 300000},
        "desc": "iter37 C6的加强版(3x)。测试极端ELG主导是否进一步提升WR但减少信号量。",
    },
    {
        "name": "C3: LG+MD双流入+散户卖出+恐慌-3%+CM50亿+dv>=1.0%",
        "params": {"buy_lg_gt_sell_lg": True, "buy_md_gt_sell_md": True, "sell_sm_gt_buy_sm": True, "pct_max": -3, "amp_min": 4, "cp20_max": 0.3, "dv_min": 1.0, "vr_min": 1.0, "cm_max": 500000},
        "desc": "iter37 C7的中盘版(50亿)+温和恐慌-3%+低股息保护。中盘容量更大。",
    },
    {
        "name": "C4: ELG连续2日净流入+散户卖出+恐慌-4%+CM30亿",
        "params": {"elg_2day_net_in": True, "sell_sm_gt_buy_sm": True, "pct_max": -4, "amp_min": 4, "cp20_max": 0.3, "vr_min": 1.0, "cm_max": 300000},
        "desc": "ELG连续2日净流入(持续建仓)+当日散户割肉。测试持续性的增量价值。",
    },
    {
        "name": "C5: ELG主导2x+dv>=3%+恐慌-4%+CM30亿",
        "params": {"elg_ratio_min": 2.0, "sell_sm_gt_buy_sm": True, "pct_max": -4, "amp_min": 5, "cp20_max": 0.3, "dv_min": 3.0, "vr_min": 1.0, "cm_max": 300000},
        "desc": "iter37 C6的高股息加强版(dv>=3%替代1.5%)。测试高股息极端保护是否提升WR。",
    },
    {
        "name": "C6: ELG主导2x+SPX前日<=-1%+恐慌-4%+CM50亿",
        "params": {"elg_ratio_min": 2.0, "sell_sm_gt_buy_sm": True, "pct_max": -4, "amp_min": 5, "cp20_max": 0.3, "vr_min": 1.0, "cm_max": 500000, "spx_panic": True},
        "desc": "iter37 C6加SPX恐慌过滤。测试外部恐慌是否创造更好买点。",
    },
    {
        "name": "C7: 3天放量(VR>=1.3连续3日)+ELG流入+恐慌-4%+CM50亿",
        "params": {"vr_3day_min": 1.3, "buy_elg_gt_sell_elg": True, "sell_sm_gt_buy_sm": True, "pct_max": -4, "amp_min": 4, "cp20_max": 0.3, "cm_max": 500000},
        "desc": "持续3天放量+ELG流入+散户割肉。测试持续放量的增量价值(参考T2 iter37发现)。",
    },
    {
        "name": "C8: ELG主导2x+无恐慌(温和回调-2%)+CM100亿大容量",
        "params": {"elg_ratio_min": 2.0, "sell_sm_gt_buy_sm": True, "pct_max": -2, "amp_min": 3, "cp20_max": 0.25, "dv_min": 1.5, "vr_min": 1.0, "cm_max": 1000000},
        "desc": "非恐慌建仓：ELG主导+温和回调-2%+高股息+CM100亿。测试大容量温和建仓策略。",
    },
]

print("=" * 70)
print("T4 资金主力挖掘 - Iter38 (Walk-Forward 验证版)")
print(f"数据基准: {MAX_DATE}")
print(f"In-Sample:  {IS_START} ~ {IS_END}")
print(f"Out-of-Sample: {OOS_START} ~ {OOS_END}")
print(f"组合数: {len(COMBOS)}")
print("=" * 70)

# ── Step 1: SPX ──
print("\n[1/8] Loading SPX index data...")
spx_rows = ch_query(
    "SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL "
    "WHERE ts_code = 'SPX' AND trade_date >= toDate('2019-06-01') "
    "ORDER BY trade_date"
)
spx_by_date = {}
for r in spx_rows:
    spx_by_date[r["trade_date"]] = r["pct_chg"]
print(f"  {len(spx_rows)} SPX rows")

# ── Step 2: Moneyflow ──
print("\n[2/8] Loading moneyflow data...")
mf_by_key = {}
for yr in range(2019, 2027):
    end_yr = "2026-05-14" if yr == 2026 else f"{yr}-12-31"
    rows = ch_query(
        f"SELECT ts_code, trade_date, "
        f"buy_sm_amount, sell_sm_amount, "
        f"buy_md_amount, sell_md_amount, "
        f"buy_lg_amount, sell_lg_amount, "
        f"buy_elg_amount, sell_elg_amount, "
        f"net_mf_amount "
        f"FROM tushare.tushare_moneyflow FINAL "
        f"WHERE trade_date >= toDate('{yr}-01-01') AND trade_date <= toDate('{end_yr}')"
    )
    for r in rows:
        mf_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")

# ── Step 3: Daily basic ──
print("\n[3/8] Loading daily_basic...")
basic_by_key = {}
for yr in range(2019, 2027):
    end_yr = "2026-05-14" if yr == 2026 else f"{yr}-12-31"
    rows = ch_query(
        f"SELECT ts_code, trade_date, volume_ratio, dv_ttm, circ_mv, pe "
        f"FROM tushare.tushare_daily_basic FINAL "
        f"WHERE trade_date >= toDate('{yr}-01-01') AND trade_date <= toDate('{end_yr}')"
    )
    for r in rows:
        basic_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")

# ── Step 4: Stock daily ──
print("\n[4/8] Loading stock_daily...")
daily_by_code = defaultdict(list)
total_daily = 0
for yr in range(2019, 2027):
    end_yr = "2026-05-14" if yr == 2026 else f"{yr}-12-31"
    rows = ch_query(
        f"SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol "
        f"FROM tushare.tushare_stock_daily FINAL "
        f"WHERE trade_date >= toDate('{yr}-01-01') AND trade_date <= toDate('{end_yr}') "
        f"AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' "
        f"AND ts_code NOT LIKE '%ST%'"
    )
    for r in rows:
        daily_by_code[r["ts_code"]].append(r)
    total_daily += len(rows)
    print(f"   {yr}: {len(rows)} rows")

print(f"  Total: {total_daily} rows, {len(daily_by_code)} stocks")
for c in daily_by_code:
    daily_by_code[c].sort(key=lambda x: x["trade_date"])

# ── 回测函数 ──
def run_backtest_wf(combo_idx, combo):
    name = combo["name"]
    params = combo["params"]
    h = combo_hash(params)
    print(f"\n{'='*50}")
    print(f"组合 {combo_idx+1}: {name}  (hash={h})")
    print(f"  {combo['desc']}")

    is_signals = []
    oos_signals = []

    for code, bars in daily_by_code.items():
        if len(bars) < 60:
            continue

        closes = [b.get("close") for b in bars]
        pos20 = []
        for i in range(len(closes)):
            if i < 19 or closes[i] is None:
                pos20.append(None)
                continue
            window20 = [c for c in closes[max(0,i-19):i+1] if c is not None]
            if len(window20) >= 20:
                h20 = max(window20); l20 = min(window20)
                cp20 = (closes[i] - l20) / (h20 - l20) if h20 != l20 else 0.5
            else:
                cp20 = 0.5
            pos20.append(cp20)

        for i in range(60, len(bars)):
            bar = bars[i]
            td = bar["trade_date"]
            close = bar["close"]
            pct = bar.get("pct_chg")
            if close is None or pct is None:
                continue

            pc_val = bar.get("pre_close")
            h_val = bar.get("high")
            l_val = bar.get("low")
            if any(v is None for v in [pc_val, h_val, l_val]) or pc_val == 0:
                continue
            amp = (h_val - l_val) / pc_val * 100

            if td >= IS_START and td <= IS_END:
                period = "IS"
            elif td >= OOS_START and td <= OOS_END:
                period = "OOS"
            else:
                continue

            dbk = (code, td)
            db = basic_by_key.get(dbk)
            if db is None:
                continue
            cm_wan = float(db.get("circ_mv") or 0)
            vr = db.get("volume_ratio")
            dv = db.get("dv_ttm")
            if vr is None:
                continue

            mfk = (code, td)
            mf = mf_by_key.get(mfk)

            cp20v = pos20[i] if i < len(pos20) and pos20[i] is not None else None

            matched = False

            # ── C1: ELG 1.5x (宽松版) ──
            if combo_idx == 0:
                if pct > params["pct_max"]: continue
                if mf is None: continue
                elg_buy = safe_float(mf.get("buy_elg_amount"))
                elg_sell = safe_float(mf.get("sell_elg_amount"))
                if elg_sell <= 0 or elg_buy / elg_sell < params["elg_ratio_min"]: continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < params["amp_min"]: continue
                if cp20v is None or cp20v > params["cp20_max"]: continue
                if vr < params["vr_min"]: continue
                if cm_wan > params["cm_max"]: continue
                matched = True

            # ── C2: ELG 3x (加强版) ──
            elif combo_idx == 1:
                if pct > params["pct_max"]: continue
                if mf is None: continue
                elg_buy = safe_float(mf.get("buy_elg_amount"))
                elg_sell = safe_float(mf.get("sell_elg_amount"))
                if elg_sell <= 0 or elg_buy / elg_sell < params["elg_ratio_min"]: continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < params["amp_min"]: continue
                if cp20v is None or cp20v > params["cp20_max"]: continue
                if dv is None or safe_float(dv) < params["dv_min"]: continue
                if cm_wan > params["cm_max"]: continue
                matched = True

            # ── C3: LG+MD+散户卖出+温和恐慌-3%+CM50亿+dv ──
            elif combo_idx == 2:
                if pct > params["pct_max"]: continue
                if mf is None: continue
                if safe_float(mf.get("buy_lg_amount")) <= safe_float(mf.get("sell_lg_amount")): continue
                if safe_float(mf.get("buy_md_amount")) <= safe_float(mf.get("sell_md_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < params["amp_min"]: continue
                if cp20v is None or cp20v > params["cp20_max"]: continue
                if dv is None or safe_float(dv) < params["dv_min"]: continue
                if vr < params["vr_min"]: continue
                if cm_wan > params["cm_max"]: continue
                matched = True

            # ── C4: ELG连续2日净流入 ──
            elif combo_idx == 3:
                if pct > params["pct_max"]: continue
                if mf is None: continue
                if safe_float(mf.get("buy_elg_amount")) <= safe_float(mf.get("sell_elg_amount")): continue
                # 前一日ELG也净流入
                if i < 1: continue
                prev_bar = bars[i-1]
                prev_td = prev_bar["trade_date"]
                prev_mf = mf_by_key.get((code, prev_td))
                if prev_mf is None: continue
                if safe_float(prev_mf.get("buy_elg_amount")) <= safe_float(prev_mf.get("sell_elg_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < params["amp_min"]: continue
                if cp20v is None or cp20v > params["cp20_max"]: continue
                if vr < params["vr_min"]: continue
                if cm_wan > params["cm_max"]: continue
                matched = True

            # ── C5: ELG 2x + dv>=3% ──
            elif combo_idx == 4:
                if pct > params["pct_max"]: continue
                if mf is None: continue
                elg_buy = safe_float(mf.get("buy_elg_amount"))
                elg_sell = safe_float(mf.get("sell_elg_amount"))
                if elg_sell <= 0 or elg_buy / elg_sell < params["elg_ratio_min"]: continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < params["amp_min"]: continue
                if cp20v is None or cp20v > params["cp20_max"]: continue
                if dv is None or safe_float(dv) < params["dv_min"]: continue
                if cm_wan > params["cm_max"]: continue
                matched = True

            # ── C6: ELG 2x + SPX恐慌 ──
            elif combo_idx == 5:
                if pct > params["pct_max"]: continue
                if mf is None: continue
                elg_buy = safe_float(mf.get("buy_elg_amount"))
                elg_sell = safe_float(mf.get("sell_elg_amount"))
                if elg_sell <= 0 or elg_buy / elg_sell < params["elg_ratio_min"]: continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < params["amp_min"]: continue
                if cp20v is None or cp20v > params["cp20_max"]: continue
                if vr < params["vr_min"]: continue
                if cm_wan > params["cm_max"]: continue
                # SPX前日恐慌
                td_dt = datetime.strptime(td, "%Y-%m-%d")
                spx_found = None
                for days_back in range(1, 8):
                    check_date = (td_dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
                    if check_date in spx_by_date:
                        spx_found = spx_by_date[check_date]
                        break
                if spx_found is None or spx_found > -1.0: continue
                matched = True

            # ── C7: 3天放量 + ELG流入 ──
            elif combo_idx == 6:
                if pct > params["pct_max"]: continue
                if mf is None: continue
                if safe_float(mf.get("buy_elg_amount")) <= safe_float(mf.get("sell_elg_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < params["amp_min"]: continue
                if cp20v is None or cp20v > params["cp20_max"]: continue
                if cm_wan > params["cm_max"]: continue
                # 3天持续放量
                vr_ok = True
                for dd in range(0, 3):
                    if i - dd < 0:
                        vr_ok = False
                        break
                    dbk_dd = (code, bars[i-dd]["trade_date"])
                    db_dd = basic_by_key.get(dbk_dd)
                    if db_dd is None or safe_float(db_dd.get("volume_ratio")) < params["vr_3day_min"]:
                        vr_ok = False
                        break
                if not vr_ok: continue
                matched = True

            # ── C8: ELG 2x + 温和回调-2% + CM100亿 ──
            elif combo_idx == 7:
                if pct > params["pct_max"]: continue
                if mf is None: continue
                elg_buy = safe_float(mf.get("buy_elg_amount"))
                elg_sell = safe_float(mf.get("sell_elg_amount"))
                if elg_sell <= 0 or elg_buy / elg_sell < params["elg_ratio_min"]: continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < params["amp_min"]: continue
                if cp20v is None or cp20v > params["cp20_max"]: continue
                if dv is None or safe_float(dv) < params["dv_min"]: continue
                if cm_wan > params["cm_max"]: continue
                matched = True

            if matched:
                if period == "IS":
                    is_signals.append((code, td, close))
                else:
                    oos_signals.append((code, td, close))

    # 计算收益
    def calc_returns(sig_list):
        ret_map = defaultdict(list)
        for code, td, buy_close in sig_list:
            stocks_bars = daily_by_code[code]
            buy_idx = None
            for j, b in enumerate(stocks_bars):
                if b["trade_date"] == td:
                    buy_idx = j
                    break
            if buy_idx is None:
                continue
            for hd in [1, 3, 5, 10, 20]:
                sell_idx = buy_idx + hd
                if sell_idx < len(stocks_bars):
                    sc = stocks_bars[sell_idx]["close"]
                    if sc and buy_close and buy_close > 0:
                        ret = (sc / buy_close - 1) * 100
                        ret_map[hd].append(ret)
        return ret_map

    is_ret = calc_returns(is_signals)
    oos_ret = calc_returns(oos_signals)

    def fmt_period(sig_list, ret_map, label):
        print(f"\n  [{label}] 总信号数: {len(sig_list)}")
        if len(sig_list) < 5:
            print(f"  [{label}] 信号不足 (<5)")
            return None
        results = {}
        for hd in [1, 3, 5, 10, 20]:
            ret_list = ret_map.get(hd, [])
            n = len(ret_list)
            if n < 3:
                results[f"ret_{hd}d"] = {"n": n, "wr": 0, "avg_ret": 0}
                continue
            win = sum(1 for r in ret_list if r > 0)
            wr = win / n * 100
            avg_ret = sum(ret_list) / n
            results[f"ret_{hd}d"] = {"n": n, "wr": round(wr, 2), "avg_ret": round(avg_ret, 2)}
            r = results[f"ret_{hd}d"]
            if r["n"] > 0:
                print(f"    T+{hd}: N={r['n']}, WR={r['wr']:.2f}%, Avg={r['avg_ret']:.2f}%")
        return results

    is_res = fmt_period(is_signals, is_ret, "IS")
    oos_res = fmt_period(oos_signals, oos_ret, "OOS")

    return {
        "name": name, "params": params, "hash": h,
        "is": is_res, "oos": oos_res,
        "is_signals_n": len(is_signals),
        "oos_signals_n": len(oos_signals),
        "is_ret": {k: v for k, v in is_ret.items()},
        "oos_ret": {k: v for k, v in oos_ret.items()},
    }


# ── 执行回测 ──
all_results = []
for idx, combo in enumerate(COMBOS):
    try:
        result = run_backtest_wf(idx, combo)
        all_results.append(result)
    except Exception as e:
        print(f"\n  [ERROR] Combo {idx+1} failed: {e}", file=sys.stderr)
        all_results.append({
            "name": combo["name"], "params": combo["params"], "hash": combo_hash(combo["params"]),
            "is": None, "oos": None, "is_signals_n": 0, "oos_signals_n": 0, "error": str(e),
        })

# ── Walk-Forward 筛选 ──
print("\n" + "=" * 70)
print("Walk-Forward 验证筛选")
print("=" * 70)

passed_is = []
for idx, r in enumerate(all_results):
    if r.get("is") is None:
        print(f"\n组合 {idx+1} ({r['name']}): IS信号不足 ❌")
        continue
    r5_is = r["is"].get("ret_5d", {})
    n_is = r5_is.get("n", 0)
    wr_is = r5_is.get("wr", 0)
    r5_is_val = r5_is.get("avg_ret", 0)
    if wr_is >= 52 and r5_is_val >= 3 and n_is >= 100:
        passed_is.append(idx)
        print(f"组合 {idx+1} ({r['name']}): IS PASS ✅ (WR={wr_is:.2f}%, R5={r5_is_val:.2f}%, N={n_is})")
    else:
        print(f"组合 {idx+1} ({r['name']}): IS FAIL ❌ (WR={wr_is:.2f}%, R5={r5_is_val:.2f}%, N={n_is})")

dual_pass = []
for idx in passed_is:
    r = all_results[idx]
    if r.get("oos") is None:
        print(f"  -> OOS 信号不足 ❌")
        continue
    r5_oos = r["oos"].get("ret_5d", {})
    n_oos = r5_oos.get("n", 0)
    wr_oos = r5_oos.get("wr", 0)
    r5_oos_val = r5_oos.get("avg_ret", 0)
    wr_drop = r5_oos.get("wr", 0) - r["is"].get("ret_5d", {}).get("wr", 0)

    if wr_oos >= 48 and r5_oos_val >= 2 and n_oos >= 20 and abs(wr_drop) <= 15:
        dual_pass.append(idx)
        print(f"  -> OOS PASS ✅ (WR={wr_oos:.2f}%, R5={r5_oos_val:.2f}%, N={n_oos}, ΔWR={wr_drop:+.2f}pp)")
    else:
        print(f"  -> OOS FAIL ❌ (WR={wr_oos:.2f}%, R5={r5_oos_val:.2f}%, N={n_oos}, ΔWR={wr_drop:+.2f}pp)")

print(f"\n{'='*70}")
print(f"DUAL-PASS: {len(dual_pass)}/{len(COMBOS)}")
if dual_pass:
    for idx in dual_pass:
        r = all_results[idx]
        wr_is_val = r["is"]["ret_5d"]["wr"]
        wr_oos_val = r["oos"]["ret_5d"]["wr"]
        print(f"  🏆 {r['name']} | IS WR={wr_is_val:.2f}% → OOS WR={wr_oos:.2f}% | N_is={r['is_signals_n']}, N_oos={r['oos_signals_n']} | hash={r['hash']}")
print(f"{'='*70}")

# ── 生成 Markdown 报告 ──
report_lines = []
report_lines.append(f"# T4: 资金主力 (iter 38) — Walk-Forward 验证报告")
report_lines.append(f"")
report_lines.append(f"> 生成时间：2026-05-15 03:xx UTC+8")
report_lines.append(f"> 数据基准：2026-05-14（最新交易日）")
report_lines.append(f"> 执行机制：ClickHouse 直连（Python批量加载 + 本地回测）")
report_lines.append(f"")
report_lines.append(f"---")
report_lines.append(f"")
report_lines.append(f"## 1. 验证框架")
report_lines.append(f"")
report_lines.append(f"| 项目 | 内容 |")
report_lines.append(f"|------|------|")
report_lines.append(f"| 训练集 (IS) | 2020-01-01 至 2024-12-31 |")
report_lines.append(f"| 测试集 (OOS) | 2025-01-01 至 2026-05-14 |")
report_lines.append(f"| 通过标准（IS） | WR>=52%, R5>=3%, N>=100 |")
report_lines.append(f"| 通过标准（OOS） | WR>=48%, R5>=2%, N>=20, WR降幅<=15pp |")
report_lines.append(f"| 因子维度 | ELG强度阶梯(1.5x/2x/3x)、持续ELG流入、恐慌-3%/-4%、市值分层(30/50/100亿)、高股息(1.5%/3%)、SPX恐慌过滤、3天持续放量 |")
report_lines.append(f"| iter37基线 | C6: ELG主导2x+高股息+微盘30亿, OOS WR=63.62%, N=448 |")
report_lines.append(f"")
report_lines.append(f"### 组合矩阵")
report_lines.append(f"")
report_lines.append(f"| 编号 | 名称 | 核心因子 | hash |")
report_lines.append(f"|------|------|---------|------|")
for idx, r in enumerate(all_results):
    report_lines.append(f"| C{idx+1} | {r['name'].split(': ')[-1] if ': ' in r['name'] else r['name']} | {COMBOS[idx]['desc'][:60]} | {r['hash']} |")
report_lines.append(f"")

# IS results
report_lines.append(f"## 2. 训练集结果 (IS)")
report_lines.append(f"")
report_lines.append(f"| 组合 | N | WR(T+5) | R5 | avg_ret% | PASS |")
report_lines.append(f"|------|---|---------|----|----------|------|")
for idx, r in enumerate(all_results):
    if r.get("is") is None:
        report_lines.append(f"| C{idx+1} | {r.get('is_signals_n', 0)} | - | - | - | ❌ 信号不足 |")
        continue
    r5 = r["is"].get("ret_5d", {})
    n = r5.get("n", 0)
    wr = r5.get("wr", 0)
    avg = r5.get("avg_ret", 0)
    passed = n >= 100 and wr >= 52 and avg >= 3
    emoji = "✅" if passed else "❌"
    report_lines.append(f"| C{idx+1} | {r['is_signals_n']} | {wr:.2f}% | {avg:.2f}% | {avg:.2f} | {emoji} |")
report_lines.append(f"")

# OOS results
report_lines.append(f"## 3. OOS 测试集结果")
report_lines.append(f"")
report_lines.append(f"| 组合 | N | WR(T+5) | R5 | avg_ret% | IS->OOS | WR_drop | DUAL |")
report_lines.append(f"|------|---|---------|----|----------|---------|---------|------|")
for idx, r in enumerate(all_results):
    if r.get("oos") is None or r.get("is") is None:
        wr_drop = "N/A"
        dual = "❌"
        wr_oos = "-"
        r5_oos = "-"
        n_oos = r.get("oos_signals_n", 0)
    else:
        r5_is = r["is"].get("ret_5d", {})
        r5_oos_d = r["oos"].get("ret_5d", {})
        wr_is = r5_is.get("wr", 0)
        wr_oos = f"{r5_oos_d.get('wr', 0):.2f}%"
        r5_oos = f"{r5_oos_d.get('avg_ret', 0):.2f}%"
        n_oos = r5_oos_d.get("n", 0)
        wr_drop_v = r5_oos_d.get("wr", 0) - wr_is
        wr_drop = f"{wr_drop_v:+.2f}pp"
        dual = "✅" if idx in dual_pass else "❌"
    report_lines.append(f"| C{idx+1} | {n_oos} | {wr_oos} | {r5_oos} | {r.get('oos_signals_n', 0)} | {r5_is.get('wr', 0):.2f}%->{wr_oos} | {wr_drop} | {dual} |")
report_lines.append(f"")
report_lines.append(f"**DUAL-PASS：{len(dual_pass)}/{len(COMBOS)}**")
report_lines.append(f"")

report_lines2 = []
report_lines2.append(f"# T4: 资金主力 (iter 38) — Walk-Forward 验证报告")
report_lines2.append(f"")
report_lines2.append(f"> 生成时间：2026-05-15 03:xx UTC+8")
report_lines2.append(f"> 数据基准：2026-05-14（最新交易日）")
report_lines2.append(f"> 执行机制：ClickHouse 直连（Python批量加载 + 本地回测）")
report_lines2.append(f"")
report_lines2.append(f"---")
report_lines2.append(f"")
report_lines2.append(f"## 1. 验证框架")
report_lines2.append(f"")
report_lines2.append(f"| 项目 | 内容 |")
report_lines2.append(f"|------|------|")
report_lines2.append(f"| 训练集 (IS) | 2020-01-01 至 2024-12-31 |")
report_lines2.append(f"| 测试集 (OOS) | 2025-01-01 至 2026-05-14 |")
report_lines2.append(f"| 通过标准（IS） | WR>=52%, R5>=3%, N>=100 |")
report_lines2.append(f"| 通过标准（OOS） | WR>=48%, R5>=2%, N>=20, WR降幅<=15pp |")
report_lines2.append(f"| 因子维度 | ELG强度阶梯、持续ELG流入、恐慌分层、市值分层、高股息分层、SPX过滤、3天放量 |")
report_lines2.append(f"| iter37基线 | C6: ELG主导2x+高股息+微盘30亿, OOS WR=63.62%, N=448 |")
report_lines2.append(f"")
report_lines2.append(f"### 组合矩阵")
report_lines2.append(f"")
report_lines2.append(f"| 编号 | 名称 | 核心因子 | hash |")
report_lines2.append(f"|------|------|---------|------|")
for idx, r in enumerate(all_results):
    short_name = r['name'].split(': ', 1)[-1] if ': ' in r['name'] else r['name']
    desc_short = COMBOS[idx]['desc'][:60]
    report_lines2.append(f"| C{idx+1} | {short_name} | {desc_short} | {r['hash']} |")
report_lines2.append(f"")
report_lines2.append(f"## 2. 训练集结果 (IS)")
report_lines2.append(f"")
report_lines2.append(f"| 组合 | N | WR(T+5) | R5 | avg_ret% | PASS |")
report_lines2.append(f"|------|---|---------|----|----------|------|")
for idx, r in enumerate(all_results):
    if r.get("is") is None:
        report_lines2.append(f"| C{idx+1} | {r.get('is_signals_n', 0)} | - | - | - | ❌ 信号不足 |")
        continue
    r5 = r["is"].get("ret_5d", {})
    n = r5.get("n", 0)
    wr = r5.get("wr", 0)
    avg = r5.get("avg_ret", 0)
    passed = n >= 100 and wr >= 52 and avg >= 3
    emoji = "✅" if passed else "❌"
    report_lines2.append(f"| C{idx+1} | {r['is_signals_n']} | {wr:.2f}% | {avg:.2f}% | {avg:.2f} | {emoji} |")
report_lines2.append(f"")
report_lines2.append(f"## 3. OOS 测试集结果")
report_lines2.append(f"")
report_lines2.append(f"| 组合 | N_oos | WR(T+5) | R5 | IS_WR | WR_drop | DUAL |")
report_lines2.append(f"|------|-------|---------|----|-------|---------|------|")
for idx, r in enumerate(all_results):
    if r.get("oos") is None or r.get("is") is None:
        wr_oos_s = "-"
        r5_oos_s = "-"
        n_oos = r.get("oos_signals_n", 0)
        wr_drop_s = "N/A"
        dual = "❌"
        wr_is_s = "-"
    else:
        r5_is = r["is"].get("ret_5d", {})
        r5_oos_d = r["oos"].get("ret_5d", {})
        wr_is_v = r5_is.get("wr", 0)
        wr_is_s = f"{wr_is_v:.2f}%"
        wr_oos_v = r5_oos_d.get("wr", 0)
        wr_oos_s = f"{wr_oos_v:.2f}%"
        r5_oos_s = f"{r5_oos_d.get('avg_ret', 0):.2f}%"
        n_oos = r5_oos_d.get("n", 0)
        wr_drop_v = wr_oos_v - wr_is_v
        wr_drop_s = f"{wr_drop_v:+.2f}pp"
        dual = "✅" if idx in dual_pass else "❌"
    report_lines2.append(f"| C{idx+1} | {n_oos} | {wr_oos_s} | {r5_oos_s} | {wr_is_s} | {wr_drop_s} | {dual} |")
report_lines2.append(f"")
report_lines2.append(f"**DUAL-PASS：{len(dual_pass)}/{len(COMBOS)}**")
report_lines2.append(f"")

if dual_pass:
    report_lines2.append(f"## 4. DUAL-PASS 组合详细拆解")
    report_lines2.append(f"")
    for rank, idx in enumerate(dual_pass):
        r = all_results[idx]
        r5_is = r["is"]["ret_5d"]
        r5_oos = r["oos"]["ret_5d"]
        medal = ["🏆", "🥈", "🥉"][rank] if rank < 3 else f"C{idx+1}"
        wr_drop_v = r5_oos.get("wr", 0) - r5_is.get("wr", 0)
        report_lines2.append(f"### {medal} C{idx+1}: {r['name']}")
        report_lines2.append(f"")
        report_lines2.append(f"**描述：** {COMBOS[idx]['desc']}")
        report_lines2.append(f"**IS：** WR={r5_is['wr']:.2f}%, R5={r5_is['avg_ret']:.2f}%, N={r['is_signals_n']}")
        report_lines2.append(f"**OOS：** WR={r5_oos['wr']:.2f}%, R5={r5_oos['avg_ret']:.2f}%, N={r['oos_signals_n']}")
        report_lines2.append(f"**WR_drop：** {wr_drop_v:+.2f}pp {'(反过拟合)' if wr_drop_v < 0 else ''}")
        report_lines2.append(f"**Hash：** {r['hash']}")
        report_lines2.append(f"")

report_lines2.append(f"## 5. 因子有效性总结 (iter38)")
report_lines2.append(f"")
report_lines2.append(f"| 因子 | 有效性 | 说明 |")
report_lines2.append(f"|------|--------|------|")
# Analyze based on results
for idx in range(len(COMBOS)):
    r = all_results[idx]
    if idx in dual_pass:
        status = "✅ 有效"
    elif r.get("is") and r["is"].get("ret_5d", {}).get("wr", 0) >= 48:
        status = "⚠️ IS有效/OOS待验证"
    else:
        status = "❌ 未通过"
    report_lines2.append(f"| C{idx+1} | {status} | {COMBOS[idx]['desc'][:50]} |")
report_lines2.append(f"")
report_lines2.append(f"## 6. 与 iter37 冠军对比")
report_lines2.append(f"")
report_lines2.append(f"| 指标 | iter37 C6 | iter38 最佳 |")
report_lines2.append(f"|------|-----------|-------------|")
if dual_pass:
    best_idx = dual_pass[0]
    best = all_results[best_idx]
    report_lines2.append(f"| OOS WR | 63.62% | {best['oos']['ret_5d']['wr']:.2f}% |")
    report_lines2.append(f"| OOS N | 448 | {best['oos_signals_n']} |")
    report_lines2.append(f"| OOS R5 | 7.30% | {best['oos']['ret_5d']['avg_ret']:.2f}% |")
else:
    report_lines2.append(f"| 结果 | iter37 C6为基线 | 本iter无DUAL-PASS |")
report_lines2.append(f"")
report_lines2.append(f"## 7. 已测组合 Hash 记录")
report_lines2.append(f"")
report_lines2.append(f"| 组合 | hash |")
report_lines2.append(f"|------|------|")
for r in all_results:
    short_name = r['name'][:40]
    report_lines2.append(f"| {short_name} | {r['hash']} |")
report_lines2.append(f"")
report_lines2.append(f"---")
report_lines2.append(f"*报告结束*")

report_content = "\n".join(report_lines2)

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(report_content)

print(f"\n✅ 报告已写入: {OUTPUT_PATH}")
print(f"  文件大小: {len(report_content)} bytes")
print("Done.")
