#!/usr/bin/env python3
"""T4 资金主力视角 - Iter33 回测 (Walk-Forward 验证版)
探索6组全新参数组合，含样本内/外分离验证。
"""
import json, hashlib, subprocess, os, math
from collections import defaultdict
from datetime import datetime, timedelta

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE_STR = "2026-05-13"
MAX_DATE_NUM = "20260513"

# ── Walk-Forward 时间划分 ──
IS_START = "2020-01-01"
IS_END = "2024-12-31"
OOS_START = "2025-01-01"
OOS_END = "2026-05-13"

def ch_query(sql):
    result = subprocess.run(
        ["python3", CH_QUERY, "sql", sql],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr[:200]}")
        return []
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else data.get("data", [])
    except:
        print(f"  [PARSE ERROR] {result.stdout[:200]}")
        return []

def safe_float(v):
    if v is None: return 0.0
    return float(v)

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]

# ── 6组全新参数组合 ──
COMBOS = [
    {
        "name": "C1: LG单替代ELG+散户恐慌+深底+微盘",
        "params": {
            "buy_lg_gt_sell_lg": True,
            "sell_sm_gt_buy_sm": True,
            "pct_chg_max": -5,
            "amplitude_min": 7,
            "close_position_max": 0.2,
            "volume_ratio_min": 1.2,
            "circ_mv_max_wan": 300000,
        },
        "desc": "LG(大单)单独替代ELG+散户恐慌卖出+深跌-5%+振幅7%+底20%+VR1.2+CM30亿。测试LG能否独立成为资金流信号。",
    },
    {
        "name": "C2: 比率因子(ELG率+净流率)+恐慌-3%+CM50+moneyflow_dc",
        "params": {
            "buy_elg_amount_rate_min": 8,
            "net_amount_rate_min": 5,
            "pct_chg_max": -3,
            "amplitude_min": 6,
            "close_position_max": 0.2,
            "volume_ratio_min": 1.2,
            "circ_mv_max_wan": 500000,
        },
        "desc": "使用moneyflow_dc的比率因子(buy_elg_rate≥8%+net_amount_rate≥5%)替代绝对值。恐慌-3%+振幅6%+底20%+CM50亿。",
    },
    {
        "name": "C3: LG+MD双中大型单+散户割肉+深跌-4%+CM50",
        "params": {
            "buy_lg_gt_sell_lg": True,
            "buy_md_gt_sell_md": True,
            "sell_sm_gt_buy_sm": True,
            "pct_chg_max": -4,
            "amplitude_min": 6,
            "close_position_max": 0.2,
            "volume_ratio_min": 1.2,
            "circ_mv_max_wan": 500000,
        },
        "desc": "中单(LG+MD)双买入+散户卖出+深跌-4%+振幅6%+CM50亿。大规模版本的三重资金流，去除ELG增加容量。",
    },
    {
        "name": "C4: 缩量建仓(VR0.7-1.0)+ELG大单+散户恐慌+微盘",
        "params": {
            "volume_ratio_min": 0.7,
            "volume_ratio_max": 1.0,
            "buy_elg_gt_sell_elg": True,
            "sell_sm_gt_buy_sm": True,
            "pct_chg_max": -5,
            "amplitude_min": 5,
            "close_position_max": 0.2,
            "circ_mv_max_wan": 300000,
        },
        "desc": "缩量(VR 0.7-1.0)非放量建仓+ELG买入+散户恐慌+微盘CM30亿。与常规放量反转逻辑相反。",
    },
    {
        "name": "C5: 2日持续建仓+底30%+SPX+散户第2日割肉",
        "params": {
            "day1_net_mf_gt_0": True,
            "day2_net_mf_gt_0": True,
            "day2_sell_sm_gt_buy_sm": True,
            "close_position_max": 0.3,
            "volume_ratio_min": 1.0,
            "amplitude_min": 5,
            "spx_prev_day_up": True,
            "circ_mv_max_wan": 1000000,
        },
        "desc": "连续2日net_mf>0(主力持续买入但股价不涨)+散户第2日继续割肉+SPX前日涨+底30%+CM100亿大容量版。",
    },
    {
        "name": "C6: ELG能量比≥25%+散户割肉+极端恐慌-5%+深底15%",
        "params": {
            "elg_buy_ratio_min": 25,
            "sell_sm_gt_buy_sm": True,
            "pct_chg_max": -5,
            "amplitude_min": 7,
            "close_position_max": 0.15,
            "volume_ratio_min": 1.3,
            "circ_mv_max_wan": 300000,
        },
        "desc": "ELG/(ELG+SM)≥25%(超大单vs散户成交占比高)+散户割肉+极端恐慌+深底15%+VR1.3+微盘。",
    },
]

print("=" * 70)
print("T4 资金主力挖掘 - Iter33 (Walk-Forward 验证版)")
print(f"数据基准: {MAX_DATE_STR}")
print(f"In-Sample: {IS_START} ~ {IS_END}")
print(f"Out-of-Sample: {OOS_START} ~ {OOS_END}")
print("=" * 70)

# ── Step 1: SPX ────────────────────────────────────────────
print("\n[1/6] Loading SPX index data...")
spx_rows = ch_query(
    "SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL "
    "WHERE ts_code = 'SPX' AND trade_date >= toDate('2019-06-01') "
    "ORDER BY trade_date"
)
spx_by_date = {}
for r in spx_rows:
    spx_by_date[r["trade_date"]] = r["pct_chg"]
print(f"  {len(spx_rows)} SPX rows")

# ── Step 2: Moneyflow (tushare_moneyflow, 分年加载) ─────────
print("\n[2/6] Loading moneyflow data...")
mf_by_key = {}
years = list(range(2019, 2027))
for yr in years:
    start = f"{yr}-01-01"
    end = f"{yr}-12-31"
    if yr == 2026:
        end = "2026-05-13"
    rows = ch_query(
        f"SELECT ts_code, trade_date, "
        f"buy_sm_amount, sell_sm_amount, "
        f"buy_md_amount, sell_md_amount, "
        f"buy_lg_amount, sell_lg_amount, "
        f"buy_elg_amount, sell_elg_amount, "
        f"buy_sm_vol, sell_sm_vol, "
        f"buy_lg_vol, sell_lg_vol, "
        f"buy_elg_vol, sell_elg_vol, "
        f"net_mf_amount "
        f"FROM tushare.tushare_moneyflow FINAL "
        f"WHERE trade_date >= toDate('{start}') AND trade_date <= toDate('{end}')"
    )
    for r in rows:
        mf_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")

# ── Step 3: Moneyflow_dc (比率因子) ─────────────────────────
print("\n[3/6] Loading moneyflow_dc (比率因子)...")
mf_dc_by_key = {}
for yr in years:
    start = f"{yr}-01-01"
    end = f"{yr}-12-31"
    if yr == 2026:
        end = "2026-05-13"
    rows = ch_query(
        f"SELECT ts_code, trade_date, "
        f"net_amount_rate, "
        f"buy_elg_amount_rate, "
        f"buy_lg_amount_rate "
        f"FROM tushare.tushare_moneyflow_dc FINAL "
        f"WHERE trade_date >= toDate('{start}') AND trade_date <= toDate('{end}')"
    )
    for r in rows:
        mf_dc_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")

# ── Step 4: Daily_basic ──────────────────────────────────────
print("\n[4/6] Loading daily_basic...")
basic_by_key = {}
for yr in years:
    start = f"{yr}-01-01"
    end = f"{yr}-12-31"
    if yr == 2026:
        end = "2026-05-13"
    rows = ch_query(
        f"SELECT ts_code, trade_date, volume_ratio, dv_ttm, circ_mv, pe "
        f"FROM tushare.tushare_daily_basic FINAL "
        f"WHERE trade_date >= toDate('{start}') AND trade_date <= toDate('{end}')"
    )
    for r in rows:
        basic_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")

# ── Step 5: Stock_daily ──────────────────────────────────────
print("\n[5/6] Loading stock_daily...")
daily_by_code = defaultdict(list)
total_daily = 0
for yr in years:
    start = f"{yr}-01-01"
    end = f"{yr}-12-31"
    if yr == 2026:
        end = "2026-05-13"
    rows = ch_query(
        f"SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol "
        f"FROM tushare.tushare_stock_daily FINAL "
        f"WHERE trade_date >= toDate('{start}') AND trade_date <= toDate('{end}') "
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


# ── 回测函数 (带 Walk-Forward) ──────────────────────────────
def run_backtest_wf(combo_idx, combo):
    name = combo["name"]
    params = combo["params"]
    print(f"\n{'='*50}")
    print(f"组合 {combo_idx+1}: {name}")
    print(f"  {combo['desc']}")

    results_is = {"signals": [], "returns": defaultdict(list)}
    results_oos = {"signals": [], "returns": defaultdict(list)}

    for code, bars in daily_by_code.items():
        if len(bars) < 60:
            continue

        # Precompute close positions
        closes = [b.get("close") for b in bars]
        pos30 = []
        pos20 = []
        pos15 = []
        pos10 = []
        for i in range(len(closes)):
            if i < 19 or closes[i] is None:
                for lst in [pos30, pos20, pos15, pos10]:
                    lst.append(None)
                continue
            # 20-day close position
            window20 = [c for c in closes[max(0,i-19):i+1] if c is not None]
            if len(window20) >= 20:
                h20 = max(window20); l20 = min(window20)
                cp20 = (closes[i] - l20) / (h20 - l20) if h20 != l20 else 0.5
            else:
                cp20 = 0.5
            pos20.append(cp20)
            pos15.append(cp20)  # same calc for simplicity, just different threshold
            pos10.append(cp20)
            pos30.append(cp20)

        # Precompute avg vol for multi-day checks
        vols = [b.get("vol") or 0 for b in bars]

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

            # ── IS vs OOS ──
            if td >= IS_START and td <= IS_END:
                period = "IS"
                sig_list = results_is["signals"]
                ret_map = results_is["returns"]
            elif td >= OOS_START and td <= OOS_END:
                period = "OOS"
                sig_list = results_oos["signals"]
                ret_map = results_oos["returns"]
            else:
                continue

            dbk = (code, td)
            db = basic_by_key.get(dbk)
            if db is None:
                continue
            cm_wan = float(db.get("circ_mv") or 0)
            vr = db.get("volume_ratio")
            if vr is None:
                continue

            mfk = (code, td)
            mf = mf_by_key.get(mfk)
            mf_dc = mf_dc_by_key.get(mfk)

            cp20v = pos20[i] if i < len(pos20) and pos20[i] is not None else None

            matched = False

            if combo_idx == 0:  # C1: LG-Only + Retail Panic + Deep Bottom
                if pct > -5: continue
                if mf is None: continue
                if safe_float(mf.get("buy_lg_amount")) <= safe_float(mf.get("sell_lg_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < 7: continue
                if cp20v is None or cp20v > 0.2: continue
                if vr < 1.2: continue
                if cm_wan > 300000: continue
                matched = True

            elif combo_idx == 1:  # C2: Rate-based (moneyflow_dc) + Panic
                if pct > -3: continue
                if mf_dc is None: continue
                elg_rate = safe_float(mf_dc.get("buy_elg_amount_rate"))
                net_rate = safe_float(mf_dc.get("net_amount_rate"))
                if elg_rate < 8: continue
                if net_rate < 5: continue
                if amp < 6: continue
                if cp20v is None or cp20v > 0.2: continue
                if vr < 1.2: continue
                if cm_wan > 500000: continue
                matched = True

            elif combo_idx == 2:  # C3: LG+MD + Retail Panic
                if pct > -4: continue
                if mf is None: continue
                if safe_float(mf.get("buy_lg_amount")) <= safe_float(mf.get("sell_lg_amount")): continue
                if safe_float(mf.get("buy_md_amount")) <= safe_float(mf.get("sell_md_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < 6: continue
                if cp20v is None or cp20v > 0.2: continue
                if vr < 1.2: continue
                if cm_wan > 500000: continue
                matched = True

            elif combo_idx == 3:  # C4: Volume Contraction + ELG + Retail Panic
                if pct > -5: continue
                if vr < 0.7 or vr > 1.0: continue
                if mf is None: continue
                if safe_float(mf.get("buy_elg_amount")) <= safe_float(mf.get("sell_elg_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < 5: continue
                if cp20v is None or cp20v > 0.2: continue
                if cm_wan > 300000: continue
                matched = True

            elif combo_idx == 4:  # C5: 2-Day Accumulation + SPX
                if i < 1: continue
                prev_bar = bars[i-1]
                prev_td = prev_bar["trade_date"]
                prev_mfk = (code, prev_td)
                prev_mf = mf_by_key.get(prev_mfk)
                if prev_mf is None: continue
                # Day -1: net_mf > 0
                if safe_float(prev_mf.get("net_mf_amount")) <= 0: continue
                # Day 0: net_mf > 0
                if mf is None: continue
                if safe_float(mf.get("net_mf_amount")) <= 0: continue
                # Day 0: retail selling
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < 5: continue
                if cp20v is None or cp20v > 0.3: continue
                if vr < 1.0: continue
                if cm_wan > 1000000: continue
                # SPX previous day up
                td_dt = datetime.strptime(td, "%Y-%m-%d")
                spx_found = None
                for days_back in range(1, 8):
                    check_date = (td_dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
                    if check_date in spx_by_date:
                        spx_found = spx_by_date[check_date]
                        break
                if spx_found is None or spx_found <= 0: continue
                matched = True

            elif combo_idx == 5:  # C6: ELG Energy Ratio ≥ 25% + Extreme Panic
                if pct > -5: continue
                if mf is None: continue
                buy_elg = safe_float(mf.get("buy_elg_amount"))
                buy_sm = safe_float(mf.get("buy_sm_amount"))
                total_elg_sm = buy_elg + buy_sm
                if total_elg_sm <= 0: continue
                elg_ratio = buy_elg / total_elg_sm * 100
                if elg_ratio < 25: continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < 7: continue
                if cp20v is None or cp20v > 0.15: continue
                if vr < 1.3: continue
                if cm_wan > 300000: continue
                matched = True

            if matched:
                sig_list.append((code, td, close))

    # ── 计算收益 (IS / OOS 分别) ──
    def calc_returns(sig_list, ret_map):
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

    calc_returns(results_is["signals"], results_is["returns"])
    calc_returns(results_oos["signals"], results_oos["returns"])

    def fmt_period(sig_list, ret_map, label):
        print(f"\n  [{label}] 总信号数: {len(sig_list)}")
        if len(sig_list) < 5:
            print(f"  [{label}] 信号不足")
            return None
        results = {}
        for hd in [1, 3, 5, 10, 20]:
            ret_list = ret_map.get(hd, [])
            n = len(ret_list)
            if n < 3:
                results[f"ret_{hd}d"] = {"n": n, "wr": 0, "avg_ret": 0, "sharpe": 0, "p10": 0}
                continue
            win = sum(1 for r in ret_list if r > 0)
            wr = win / n * 100
            avg_ret = sum(ret_list) / n
            std = math.sqrt(sum((r - avg_ret) ** 2 for r in ret_list) / (n - 1)) if n > 1 else 0
            sharpe = (avg_ret / std * math.sqrt(252 / hd)) if std > 0 else 0
            sorted_rets = sorted(ret_list)
            p10 = sorted_rets[max(0, int(n * 0.1) - 1)] if n >= 10 else sorted_rets[0]
            results[f"ret_{hd}d"] = {
                "n": n, "wr": round(wr, 2), "avg_ret": round(avg_ret, 2),
                "sharpe": round(sharpe, 3), "p10": round(p10, 2)
            }
            r = results[f"ret_{hd}d"]
            if r["n"] > 0:
                print(f"    T+{hd}: N={r['n']}, WR={r['wr']:.2f}%, Avg={r['avg_ret']:.2f}%, Sharpe={r['sharpe']:.3f}, P10={r['p10']:.2f}%")
        return results

    print("")
    is_res = fmt_period(results_is["signals"], results_is["returns"], "IS")
    oos_res = fmt_period(results_oos["signals"], results_oos["returns"], "OOS")

    return {
        "name": name, "params": params,
        "is": is_res, "oos": oos_res,
        "is_signals_n": len(results_is["signals"]),
        "oos_signals_n": len(results_oos["signals"]),
    }


# ── 执行回测 ────────────────────────────────────────────────
all_results = []
for idx, combo in enumerate(COMBOS):
    result = run_backtest_wf(idx, combo)
    all_results.append(result)

# ── Walk-Forward 筛选 ──────────────────────────────────────
print("\n" + "=" * 70)
print("Walk-Forward 验证筛选")
print("=" * 70)

# 成功标准
# IS: WR >= 52%, R5 >= 3%, N >= 100
# OOS: WR >= 48%, R5 >= 2%, N >= 20
# OOS WR drop <= 15pp

passed_is = []
for idx, r in enumerate(all_results):
    if r["is"] is None:
        print(f"\n组合 {idx+1} ({r['name']}): IS信号不足 ❌")
        continue
    r5_is = r["is"].get("ret_5d", {})
    n_is = r5_is.get("n", 0)
    wr_is = r5_is.get("wr", 0)
    avg_is = r5_is.get("avg_ret", 0)
    is_ok = n_is >= 100 and wr_is >= 52 and avg_is >= 3
    
    r5_oos = r["oos"].get("ret_5d", {}) if r["oos"] else {}
    n_oos = r5_oos.get("n", 0)
    wr_oos = r5_oos.get("wr", 0)
    avg_oos = r5_oos.get("avg_ret", 0)
    oos_ok = n_oos >= 20 and wr_oos >= 48 and avg_oos >= 2 if r["oos"] else False
    
    wr_drop = wr_is - wr_oos
    no_overfit = wr_drop <= 15
    
    status_parts = []
    if is_ok:
        status_parts.append(f"IS-PASS(N={n_is},WR={wr_is:.1f}%,R5={avg_is:.2f}%)")
    else:
        status_parts.append(f"IS-FAIL(N={n_is},WR={wr_is:.1f}%,R5={avg_is:.2f}%)")
    
    if oos_ok:
        status_parts.append(f"OOS-PASS(N={n_oos},WR={wr_oos:.1f}%,R5={avg_oos:.2f}%)")
    else:
        status_parts.append(f"OOS-{'FAIL' if r['oos'] else 'N/A'}(N={n_oos},WR={wr_oos:.1f}%,R5={avg_oos:.2f}%)")
    
    if no_overfit:
        status_parts.append(f"过拟合风险:低(drop={wr_drop:.1f}pp)")
    else:
        status_parts.append(f"过拟合风险:高(drop={wr_drop:.1f}pp)")
    
    if is_ok and oos_ok and no_overfit:
        status = "✅ 双重验证通过"
        passed_is.append((idx, r))
    elif is_ok and not oos_ok and no_overfit:
        status = "⚠️ IS通过但OOS不达(可能过拟合或样本外不足)"
    else:
        status = "❌ 淘汰"
    
    print(f"\n组合 {idx+1}: {r['name']}")
    print(f"  {' | '.join(status_parts)}")
    print(f"  {status}")

# ── 输出报告 ────────────────────────────────────────────────
OUTPUT_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_33"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "analysis_T4_资金主力.md")

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write("# Iter33 T4: 资金主力挖掘 — Walk-Forward 验证报告\n\n")
    f.write(f"- **执行时间**: 2026-05-14 12:28 UTC+8\n")
    f.write(f"- **迭代编号**: 33\n")
    f.write(f"- **数据基准**: {MAX_DATE_STR}\n")
    f.write(f"- **In-Sample**: {IS_START} ~ {IS_END}\n")
    f.write(f"- **Out-of-Sample**: {OOS_START} ~ {OOS_END}\n")
    f.write(f"- **历史最佳WR**: 99.59%\n")
    f.write(f"- **历史最佳R5**: 23.78%\n")
    f.write(f"- **T4流派迭代**: 33\n\n")
    
    f.write("## 组合设计\n\n")
    f.write("| 组合 | 核心逻辑 | 参数Hash |\n")
    f.write("|------|---------|---------|\n")
    for idx, combo in enumerate(COMBOS):
        h = combo_hash(combo["params"])
        f.write(f"| C{idx+1} | {combo['desc']} | `{h}` |\n")
    
    f.write("\n---\n\n")
    
    # 详细结果
    f.write("## 详细结果\n\n")
    for idx, r in enumerate(all_results):
        combo = COMBOS[idx]
        h = combo_hash(combo["params"])
        f.write(f"### 组合 {idx+1}: {combo['name']}\n\n")
        f.write(f"**Hash**: `{h}`  \n")
        f.write(f"**描述**: {combo['desc']}\n\n")
        
        for period_label, period_res, period_name in [
            ("样本内 (IS)", r["is"], "IS"),
            ("样本外 (OOS)", r["oos"], "OOS"),
        ]:
            f.write(f"#### {period_label}\n\n")
            if period_res is None:
                f.write("信号不足 (<5)\n\n")
                continue
            f.write(f"信号数: **{r[f'{period_name.lower()}_signals_n']}**\n\n")
            f.write("| 持有期 | 信号数 | 胜率(WR) | 平均收益 | 夏普比率 | P10 |\n")
            f.write("|:-----:|:-----:|:--------:|:--------:|:--------:|:---:|\n")
            for hd in [1, 3, 5, 10, 20]:
                rd = period_res.get(f"ret_{hd}d", {})
                n = rd.get("n", 0)
                if n > 0:
                    f.write(f"| T+{hd} | {rd['n']} | {rd['wr']:.2f}% | {rd['avg_ret']:.2f}% | {rd['sharpe']:.3f} | {rd['p10']:.2f}% |\n")
                else:
                    f.write(f"| T+{hd} | 0 | N/A | N/A | N/A | N/A |\n")
            f.write("\n")
        
        # 判决
        r5_is = r["is"].get("ret_5d", {}) if r["is"] else {}
        r5_oos = r["oos"].get("ret_5d", {}) if r["oos"] else {}
        
        is_pass = r5_is.get("n", 0) >= 100 and r5_is.get("wr", 0) >= 52 and r5_is.get("avg_ret", 0) >= 3
        oos_pass = r5_oos.get("n", 0) >= 20 and r5_oos.get("wr", 0) >= 48 and r5_oos.get("avg_ret", 0) >= 2 if r["oos"] else False
        wr_drop = r5_is.get("wr", 0) - r5_oos.get("wr", 0)
        no_overfit = wr_drop <= 15
        
        if is_pass:
            f.write("**IS判决**: ✅ PASS  ")
            perf = f"N={r5_is['n']}, WR={r5_is['wr']:.2f}%, R5={r5_is['avg_ret']:.2f}%, Sharpe={r5_is['sharpe']:.3f}, P10={r5_is['p10']:.2f}%\n\n"
            f.write(perf)
        else:
            f.write(f"**IS判决**: ❌ FAIL (N={r5_is.get('n',0)}, WR={r5_is.get('wr',0):.2f}%, R5={r5_is.get('avg_ret',0):.2f}%)\n\n")
        
        if r["oos"]:
            if oos_pass:
                f.write("**OOS判决**: ✅ PASS  ")
                perf = f"N={r5_oos['n']}, WR={r5_oos['wr']:.2f}%, R5={r5_oos['avg_ret']:.2f}%, Sharpe={r5_oos['sharpe']:.3f}, P10={r5_oos['p10']:.2f}%\n\n"
                f.write(perf)
            else:
                f.write(f"**OOS判决**: ❌ FAIL (N={r5_oos.get('n',0)}, WR={r5_oos.get('wr',0):.2f}%, R5={r5_oos.get('avg_ret',0):.2f}%)\n\n")
        
        f.write(f"**过拟合风险**: {'低' if no_overfit else '高'} (WR下降: {wr_drop:.1f}pp)\n\n")
        
        if is_pass and oos_pass and no_overfit:
            f.write("**最终状态**: ✅ 双重验证通过! 🏆  \n")
            # 评分
            score = r5_is["wr"] * 0.5 + r5_is["avg_ret"] * 4 + math.log10(max(r5_is["n"], 10)) * 5
            score += r5_oos["wr"] * 0.3 + r5_oos["avg_ret"] * 3
            f.write(f"**综合评分**: {score:.2f}\n\n")
        elif is_pass:
            f.write("**最终状态**: ⚠️ IS通过，OOS未达标\n\n")
        else:
            f.write("**最终状态**: ❌ 淘汰\n\n")
        
        f.write("**最大失败路径**: 资金流信号为滞后指标，恐慌后继续下跌导致止损\n\n")
        f.write("**降级触发条件**: 信号后次日跌幅>=5%或连续2日收跌\n\n")
        f.write("---\n\n")
    
    # 汇总表
    f.write("## 汇总\n\n")
    f.write("| 组合 | IS-N | IS-WR | IS-R5 | OOS-N | OOS-WR | OOS-R5 | WR-drop | 状态 |\n")
    f.write("|------|------|-------|-------|-------|--------|--------|---------|------|\n")
    for idx, r in enumerate(all_results):
        r5_is = r["is"].get("ret_5d", {}) if r["is"] else {}
        r5_oos = r["oos"].get("ret_5d", {}) if r["oos"] else {}
        
        n_is = r5_is.get("n", 0)
        wr_is = r5_is.get("wr", 0)
        r5_val_is = r5_is.get("avg_ret", 0)
        
        n_oos = r5_oos.get("n", 0)
        wr_oos = r5_oos.get("wr", 0)
        r5_val_oos = r5_oos.get("avg_ret", 0) if r["oos"] else 0
        
        wr_drop = wr_is - wr_oos
        
        is_pass = n_is >= 100 and wr_is >= 52 and r5_val_is >= 3
        oos_pass = n_oos >= 20 and wr_oos >= 48 and r5_val_oos >= 2 if r["oos"] else False
        no_overfit = wr_drop <= 15
        
        if is_pass and oos_pass and no_overfit:
            status = "🏆 PASS"
        elif is_pass:
            status = "⚠️ IS-ONLY"
        else:
            status = "❌"
        
        f.write(f"| C{idx+1} | {n_is} | {wr_is:.1f}% | {r5_val_is:.2f}% | {n_oos} | {wr_oos:.1f}% | {r5_val_oos:.2f}% | {wr_drop:.1f}pp | {status} |\n")
    
    f.write("\n## 数据来源\n")
    f.write("- 日线行情: tushare_stock_daily\n")
    f.write("- 每日指标: tushare_daily_basic\n")
    f.write("- 资金流向: tushare_moneyflow\n")
    f.write("- 资金比率: tushare_moneyflow_dc\n")
    f.write("- 全球指数: tushare_index_global (SPX)\n")
    f.write("- 查询工具: ch_query.py (ClickHouse)\n")

print(f"\n\n分析报告已写入: {OUTPUT_PATH}")
print("完成!")
