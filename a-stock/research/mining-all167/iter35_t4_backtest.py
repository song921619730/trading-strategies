#!/usr/bin/env python3
"""T4 资金主力 - Iter35 Walk-Forward 验证
6组全新组合：高股息强化、中单逆势、大宗交易、换手率保护、多日积累、极端恐慌
"""
import json, hashlib, os, sys, math
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167')
from ch_helper import ch_query

MAX_DATE_STR = "2026-05-13"
MAX_DATE_NUM = "20260513"

IS_START = "2020-01-01"
IS_END = "2024-12-31"
OOS_START = "2025-01-01"
OOS_END = "2026-05-13"

def safe_float(v):
    if v is None: return 0.0
    try: return float(v)
    except: return 0.0

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]

# ── 6组全新参数组合 ──
COMBOS = [
    {
        "name": "C1: 高股息强化版(DV≥2.5%+DUAL+恐慌)",
        "params": {
            "buy_elg_gt_sell_elg": True,
            "buy_lg_gt_sell_lg": True,
            "sell_sm_gt_buy_sm": True,
            "pct_chg_max": -3,
            "amplitude_min": 5,
            "close_position_max": 0.2,
            "volume_ratio_min": 1.0,
            "circ_mv_max_wan": 500000,
            "dv_ttm_min": 2.5,
        },
        "desc": "Iter34 C4高股息版强化：dv≥2.5%替代隐含dv≥2%。DUAL双资金确认+散户恐慌+底20%+CM50亿。测试高股息保护力是否随阈值提升而增强。",
    },
    {
        "name": "C2: 中单逆势+ELG双重确认+深底+微盘",
        "params": {
            "buy_md_gt_sell_md": True,
            "buy_elg_gt_sell_elg": True,
            "sell_sm_gt_buy_sm": True,
            "pct_chg_max": -4,
            "amplitude_min": 6,
            "close_position_max": 0.2,
            "volume_ratio_min": 1.2,
            "circ_mv_max_wan": 300000,
        },
        "desc": "Iter34 C6中单逆势改进版：增加ELG买入确认(原版无ELG)。中单独立有效但加ELG双确认是否提升稳定性？CM30亿微盘+底20%+跌幅-4%。",
    },
    {
        "name": "C3: 大宗交易机构买入+资金流确认+底",
        "params": {
            "block_trade_inst_buy": True,
            "buy_elg_gt_sell_elg": True,
            "sell_sm_gt_buy_sm": True,
            "pct_chg_max": -2,
            "close_position_max": 0.3,
            "volume_ratio_min": 0.8,
            "circ_mv_max_wan": 1000000,
        },
        "desc": "【全新维度】当日有大宗交易(机构专用买方)+同日资金流ELG买入+散户恐慌。因大宗交易相对稀疏，放宽至底30%+CM100亿+跌幅-2%。",
    },
    {
        "name": "C4: 换手率保护版(TR≥2%+DUAL+恐慌+底)",
        "params": {
            "buy_elg_gt_sell_elg": True,
            "buy_lg_gt_sell_lg": True,
            "sell_sm_gt_buy_sm": True,
            "pct_chg_max": -3,
            "amplitude_min": 5,
            "close_position_max": 0.2,
            "volume_ratio_min": 1.0,
            "circ_mv_max_wan": 500000,
            "turnover_rate_min": 2.0,
        },
        "desc": "【全新维度】加入换手率≥2%(tr from daily_info)过滤僵尸股。测试换手率是否提升资金流信号稳定性。其余同C1基线。",
    },
    {
        "name": "C5: 连续3日资金净流入+高股息+底30%",
        "params": {
            "day1_net_mf_gt_0": True,
            "day2_net_mf_gt_0": True,
            "day3_net_mf_gt_0": True,
            "day3_sell_sm_gt_buy_sm": True,
            "dv_ttm_min": 2.0,
            "close_position_max": 0.3,
            "volume_ratio_min": 0.8,
            "amplitude_min": 4,
            "circ_mv_max_wan": 1000000,
        },
        "desc": "【全新维度】连续3日净流入(主力持续建仓但股价不涨)+第3日散户割肉+高股息dv≥2%+底30%。测试持续性资金积累模式。",
    },
    {
        "name": "C6: 极端恐慌(≤-5%)+DUAL+高股息+微盘",
        "params": {
            "buy_elg_gt_sell_elg": True,
            "buy_lg_gt_sell_lg": True,
            "sell_sm_gt_buy_sm_ratio": 1.5,
            "pct_chg_max": -5,
            "amplitude_min": 7,
            "close_position_max": 0.15,
            "volume_ratio_min": 1.3,
            "circ_mv_max_wan": 300000,
            "dv_ttm_min": 2.0,
        },
        "desc": "极端恐慌-5%+散户卖/买比≥1.5(更强割肉确认)+DUAL双资金+高股息dv≥2%+深底15%+VR1.3+微盘CM30亿。最强约束版。",
    },
]

print("=" * 70)
print("T4 资金主力挖掘 - Iter35 (Walk-Forward 验证版)")
print(f"数据基准: {MAX_DATE_STR}")
print(f"In-Sample: {IS_START} ~ {IS_END}")
print(f"Out-of-Sample: {OOS_START} ~ {OOS_END}")
print("=" * 70)

# ── Step 1: SPX ────────────────────────────────
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

# ── Step 2: Moneyflow ────────────────────────────
print("\n[2/6] Loading moneyflow data (分年加载)...")
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
        f"net_mf_amount "
        f"FROM tushare.tushare_moneyflow FINAL "
        f"WHERE trade_date >= toDate('{start}') AND trade_date <= toDate('{end}')"
    )
    for r in rows:
        mf_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")

# ── Step 3: Daily_basic ──────────────────────────
print("\n[3/6] Loading daily_basic...")
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

# ── Step 4: Daily_info (for turnover rate) ───────
print("\n[4/6] Loading daily_info (换手率)...")
info_by_key = {}
for yr in years:
    start = f"{yr}-01-01"
    end = f"{yr}-12-31"
    if yr == 2026:
        end = "2026-05-13"
    rows = ch_query(
        f"SELECT ts_code, trade_date, tr "
        f"FROM tushare.tushare_daily_info FINAL "
        f"WHERE trade_date >= toDate('{start}') AND trade_date <= toDate('{end}')"
    )
    for r in rows:
        info_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")

# ── Step 5: Block_trade (大宗交易) ────────────────
print("\n[5/6] Loading block_trade (大宗交易机构买入)...")
block_trade_dates = set()
block_rows = ch_query(
    f"SELECT ts_code, trade_date, amount, buyer "
    f"FROM tushare.tushare_block_trade FINAL "
    f"WHERE buyer LIKE '%机构%' "
    f"AND trade_date >= toDate('{IS_START}') AND trade_date <= toDate('{OOS_END}')"
)
block_by_stock_date = {}
for r in block_rows:
    key = (r["ts_code"], r["trade_date"])
    if key not in block_by_stock_date:
        block_by_stock_date[key] = []
    block_by_stock_date[key].append(r)
    block_trade_dates.add(r["trade_date"])
print(f"   {len(block_rows)} 机构大宗交易行, {len(block_trade_dates)} 个交易日")

# ── Step 6: Stock_daily ───────────────────────────
print("\n[6/6] Loading stock_daily (主力行情)...")
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

# ── 回测函数 ────────────────────────────────────
def run_backtest(combo_idx, combo):
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

            # IS vs OOS
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
            cm_wan = safe_float(db.get("circ_mv"))
            vr = db.get("volume_ratio")
            if vr is None:
                continue
            dv_ttm = safe_float(db.get("dv_ttm"))

            mfk = (code, td)
            mf = mf_by_key.get(mfk)
            cp20v = pos20[i] if i < len(pos20) and pos20[i] is not None else None

            # Daily info for turnover rate
            infok = (code, td)
            info = info_by_key.get(infok)
            tr = safe_float(info.get("tr")) if info else 0

            # Block trade
            blk_key = (code, td)
            has_block_inst = blk_key in block_by_stock_date

            matched = False

            if combo_idx == 0:  # C1: 高股息强化版
                if pct > -3: continue
                if mf is None: continue
                if safe_float(mf.get("buy_elg_amount")) <= safe_float(mf.get("sell_elg_amount")): continue
                if safe_float(mf.get("buy_lg_amount")) <= safe_float(mf.get("sell_lg_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < 5: continue
                if cp20v is None or cp20v > 0.2: continue
                if vr < 1.0: continue
                if cm_wan > 500000: continue
                if dv_ttm < 2.5: continue
                matched = True

            elif combo_idx == 1:  # C2: 中单逆势+ELG双确认
                if pct > -4: continue
                if mf is None: continue
                if safe_float(mf.get("buy_md_amount")) <= safe_float(mf.get("sell_md_amount")): continue
                if safe_float(mf.get("buy_elg_amount")) <= safe_float(mf.get("sell_elg_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < 6: continue
                if cp20v is None or cp20v > 0.2: continue
                if vr < 1.2: continue
                if cm_wan > 300000: continue
                matched = True

            elif combo_idx == 2:  # C3: 大宗交易机构买入
                if not has_block_inst: continue
                if pct > -2: continue
                if mf is None: continue
                if safe_float(mf.get("buy_elg_amount")) <= safe_float(mf.get("sell_elg_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if cp20v is None or cp20v > 0.3: continue
                if vr < 0.8: continue
                if cm_wan > 1000000: continue
                matched = True

            elif combo_idx == 3:  # C4: 换手率保护版
                if tr < 2.0: continue
                if pct > -3: continue
                if mf is None: continue
                if safe_float(mf.get("buy_elg_amount")) <= safe_float(mf.get("sell_elg_amount")): continue
                if safe_float(mf.get("buy_lg_amount")) <= safe_float(mf.get("sell_lg_amount")): continue
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if amp < 5: continue
                if cp20v is None or cp20v > 0.2: continue
                if vr < 1.0: continue
                if cm_wan > 500000: continue
                matched = True

            elif combo_idx == 4:  # C5: 连续3日净流入
                if i < 2: continue
                d1_bar = bars[i-2]; d2_bar = bars[i-1]
                d1_mfk = (code, d1_bar["trade_date"])
                d2_mfk = (code, d2_bar["trade_date"])
                d1_mf = mf_by_key.get(d1_mfk)
                d2_mf = mf_by_key.get(d2_mfk)
                if d1_mf is None or d2_mf is None or mf is None: continue
                # 第1日净流入
                if safe_float(d1_mf.get("net_mf_amount")) <= 0: continue
                # 第2日净流入
                if safe_float(d2_mf.get("net_mf_amount")) <= 0: continue
                # 第3日净流入
                if safe_float(mf.get("net_mf_amount")) <= 0: continue
                # 第3日散户割肉
                if safe_float(mf.get("sell_sm_amount")) <= safe_float(mf.get("buy_sm_amount")): continue
                if dv_ttm < 2.0: continue
                if cp20v is None or cp20v > 0.3: continue
                if vr < 0.8: continue
                if amp < 4: continue
                if cm_wan > 1000000: continue
                matched = True

            elif combo_idx == 5:  # C6: 极端恐慌+DUAL+高股息+微盘
                if pct > -5: continue
                if mf is None: continue
                if safe_float(mf.get("buy_elg_amount")) <= safe_float(mf.get("sell_elg_amount")): continue
                if safe_float(mf.get("buy_lg_amount")) <= safe_float(mf.get("sell_lg_amount")): continue
                # Stronger retail panic ratio ≥ 1.5
                sell_sm = safe_float(mf.get("sell_sm_amount"))
                buy_sm = safe_float(mf.get("buy_sm_amount"))
                if buy_sm <= 0 or sell_sm / buy_sm < 1.5: continue
                if amp < 7: continue
                if cp20v is None or cp20v > 0.15: continue
                if vr < 1.3: continue
                if cm_wan > 300000: continue
                if dv_ttm < 2.0: continue
                matched = True

            if matched:
                sig_list.append((code, td, close))

    # ── 计算收益 ──
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
        if not sig_list:
            print(f"  [{label}] 无信号")
            return None
        results = {}
        for hd in [1, 3, 5, 10, 20]:
            ret_list = ret_map.get(hd, [])
            n = len(ret_list)
            if n < 3:
                results[f"ret_{hd}d"] = {"n": n, "wr": 0, "avg_ret": 0, "sharpe": 0}
                continue
            win = sum(1 for r in ret_list if r > 0)
            wr = win / n * 100
            avg_ret = sum(ret_list) / n
            std = math.sqrt(sum((r - avg_ret) ** 2 for r in ret_list) / (n - 1)) if n > 1 else 0
            sharpe = (avg_ret / std * math.sqrt(252 / hd)) if std > 0 else 0
            sorted_rets = sorted(ret_list)
            p10 = sorted_rets[max(0, int(n * 0.1) - 1)] if n >= 10 else sorted_rets[0] if sorted_rets else 0
            results[f"ret_{hd}d"] = {
                "n": n, "wr": round(wr, 2), "avg_ret": round(avg_ret, 2),
                "sharpe": round(sharpe, 3), "p10": round(p10, 2)
            }
            r = results[f"ret_{hd}d"]
            print(f"    T+{hd}: N={r['n']}, WR={r['wr']:.2f}%, Avg={r['avg_ret']:.2f}%, Sharpe={r['sharpe']:.3f}, P10={r['p10']:.2f}%")
        return results

    print("")
    is_res = fmt_period(results_is["signals"], results_is["returns"], "IS")
    oos_res = fmt_period(results_oos["signals"], results_oos["returns"], "OOS")

    return {
        "name": name,
        "params": params,
        "is": is_res,
        "oos": oos_res,
        "is_signals_n": len(results_is["signals"]),
        "oos_signals_n": len(results_oos["signals"]),
    }

# ── 执行回测 ───────────────────────────────────
all_results = []
for idx, combo in enumerate(COMBOS):
    result = run_backtest(idx, combo)
    all_results.append(result)

# ── Walk-Forward 筛选 ─────────────────────────
print("\n" + "=" * 70)
print("Walk-Forward 验证筛选")
print("=" * 70)

# 成功标准
# IS: WR >= 52%, R5 >= 3%, N >= 100
# OOS: WR >= 48%, R5 >= 2%, N >= 20
# OOS WR drop <= 15pp (compared to IS)

passed = []
for idx, r in enumerate(all_results):
    print(f"\n组合 {idx+1}: {r['name']}")

    if r["is"] is None:
        print(f"  IS: 无信号 ❌")
        continue

    r5_is = r["is"].get("ret_5d", {})
    r5_oos = r["oos"].get("ret_5d", {}) if r["oos"] else {}

    n_is = r5_is.get("n", 0)
    wr_is = r5_is.get("wr", 0)
    avg_is = r5_is.get("avg_ret", 0)
    n_oos = r5_oos.get("n", 0)
    wr_oos = r5_oos.get("wr", 0)
    avg_oos = r5_oos.get("avg_ret", 0)

    checks = []
    # IS criteria
    c1 = wr_is >= 52; checks.append(f"IS WR={wr_is:.1f}% {'✅' if c1 else '❌'} (≥52%)")
    c2 = avg_is >= 3; checks.append(f"IS R5={avg_is:.2f}% {'✅' if c2 else '❌'} (≥3%)")
    c3 = n_is >= 100; checks.append(f"IS N={n_is} {'✅' if c3 else '❌'} (≥100)")
    # OOS criteria
    c4 = wr_oos >= 48; checks.append(f"OOS WR={wr_oos:.1f}% {'✅' if c4 else '❌'} (≥48%)")
    c5 = avg_oos >= 2; checks.append(f"OOS R5={avg_oos:.2f}% {'✅' if c5 else '❌'} (≥2%)")
    c6 = n_oos >= 20; checks.append(f"OOS N={n_oos} {'✅' if c6 else '❌'} (≥20)")
    # Overfitting check
    wr_drop = wr_is - wr_oos
    c7 = wr_drop <= 15; checks.append(f"WR下降={wr_drop:.1f}pp {'✅' if c7 else '❌'} (≤15pp)")

    for chk in checks:
        print(f"  {chk}")

    if all([c1, c2, c3, c4, c5, c6, c7]):
        # Bonus check: avg_oos must be positive
        if avg_oos > 0:
            print(f"  → DUAL-PASS ✅")
            passed.append(r)
        else:
            print(f"  → OOS R5为负，经济失效 ❌")
    else:
        print(f"  → FAIL ❌")

# ── 汇总输出 ───────────────────────────────────
print("\n" + "=" * 70)
print("最终结果汇总")
print("=" * 70)
print(f"\n共测试 {len(COMBOS)} 组，通过 {len(passed)} 组")

for idx, r in enumerate(all_results):
    r5_is = r["is"].get("ret_5d", {}) if r["is"] else {"n": 0, "wr": 0, "avg_ret": 0}
    r5_oos = r["oos"].get("ret_5d", {}) if r["oos"] else {"n": 0, "wr": 0, "avg_ret": 0}
    n_is = r5_is.get("n", 0)
    wr_is = r5_is.get("wr", 0)
    avg_is = r5_is.get("avg_ret", 0)
    n_oos = r5_oos.get("n", 0)
    wr_oos = r5_oos.get("wr", 0)
    avg_oos = r5_oos.get("avg_ret", 0)
    sharpe_is = r5_is.get("sharpe", 0)
    sharpe_oos = r5_oos.get("sharpe", 0)
    
    is_pass = all([wr_is >= 52, avg_is >= 3, n_is >= 100,
                   wr_oos >= 48, avg_oos >= 2, n_oos >= 20,
                   (wr_is - wr_oos) <= 15])
    status = "✅ DUAL-PASS" if is_pass else "❌ FAIL"

    print(f"\n组合 {idx+1} | {r['name'][:40]:40s}")
    print(f"  IS: N={n_is:6d} | WR={wr_is:5.1f}% | R5={avg_is:5.2f}% | Sharpe={sharpe_is:.3f}")
    print(f"  OOS: N={n_oos:5d} | WR={wr_oos:5.1f}% | R5={avg_oos:5.2f}% | Sharpe={sharpe_oos:.3f}")
    print(f"  {status}")

# Save results
output = {
    "metadata": {
        "task": "T4_资金主力",
        "iter": 35,
        "is_range": f"{IS_START} to {IS_END}",
        "oos_range": f"{OOS_START} to {OOS_END}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "combos_tested": len(COMBOS),
        "combos_passed": len(passed),
    },
    "combinations": []
}

for idx, r in enumerate(all_results):
    r5_is = r["is"].get("ret_5d", {}) if r["is"] else {"n": 0}
    r5_oos = r["oos"].get("ret_5d", {}) if r["oos"] else {"n": 0}
    is_pass = (r["is"] is not None and 
               r5_is.get("wr", 0) >= 52 and r5_is.get("avg_ret", 0) >= 3 and r5_is.get("n", 0) >= 100 and
               r5_oos.get("wr", 0) >= 48 and r5_oos.get("avg_ret", 0) >= 2 and r5_oos.get("n", 0) >= 20 and
               (r5_is.get("wr", 0) - r5_oos.get("wr", 0)) <= 15)
    
    combo_out = {
        "label": r["name"],
        "is": r["is"],
        "oos": r["oos"],
        "is_signals_n": r["is_signals_n"],
        "oos_signals_n": r["oos_signals_n"],
        "status": "PASS" if is_pass else "FAIL",
    }
    output["combinations"].append(combo_out)

# Write outputs
out_md = os.path.join(os.path.dirname(__file__), "logs", "iter_35", "analysis_T4_资金主力：聪明资金流入.md")
out_json = os.path.join(os.path.dirname(__file__), "logs", "iter_35", "analysis_T4_资金主力：聪明资金流入.json")

with open(out_md, "w") as f:
    f.write("# T4 资金主力 (Iter 35) — 分析报告\n\n")
    f.write(f"> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("---\n\n")
    f.write("| 组合 | IS WR | IS R5 | IS N | OOS WR | OOS R5 | OOS N | 状态 |\n")
    f.write("|------|:----:|:-----:|:----:|:------:|:------:|:-----:|------|\n")
    for idx, r in enumerate(all_results):
        r5_is = r["is"].get("ret_5d", {}) if r["is"] else {"n": 0, "wr": 0, "avg_ret": 0}
        r5_oos = r["oos"].get("ret_5d", {}) if r["oos"] else {"n": 0, "wr": 0, "avg_ret": 0}
        is_pass = (r["is"] is not None and 
                   r5_is.get("wr", 0) >= 52 and r5_is.get("avg_ret", 0) >= 3 and r5_is.get("n", 0) >= 100 and
                   r5_oos.get("wr", 0) >= 48 and r5_oos.get("avg_ret", 0) >= 2 and r5_oos.get("n", 0) >= 20 and
                   (r5_is.get("wr", 0) - r5_oos.get("wr", 0)) <= 15)
        status = "✅" if is_pass else "❌"
        f.write(f"| {idx+1}_{r['name'][:35]} | {r5_is.get('wr', 0):.1f}% | {r5_is.get('avg_ret', 0):.2f}% | {r5_is.get('n', 0)} | {r5_oos.get('wr', 0):.1f}% | {r5_oos.get('avg_ret', 0):.2f}% | {r5_oos.get('n', 0)} | {status} |\n")

with open(out_json, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n\n结果已保存至:\n  {out_md}\n  {out_json}")
