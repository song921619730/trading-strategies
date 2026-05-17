#!/usr/bin/env python3
"""T4 资金主力视角 - Iter28 回测 (分块加载版)
将大表按年份分块加载，避免单次查询超时
"""
import json, hashlib, subprocess, os, math
from collections import defaultdict
from datetime import datetime, timedelta

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE = "20260513"
BACKTEST_START = "20190101"

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

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]

def safe_float(v):
    if v is None: return 0.0
    return float(v)

# ── 5组参数组合 ──────────────────────────────────────────
COMBOS = [
    {
        "name": "C1: 恐慌+大单比例≥60%+散户割肉+振幅7%+底20%+CM30",
        "params": {
            "pct_chg_max": -5,
            "buy_lg_ratio_min": 60,
            "sell_sm_gt_buy_sm": True,
            "amplitude_min": 7,
            "close_position": "底20%",
            "circ_mv_max_wan": 300000,
            "volume_ratio_min": 1.0,
        },
        "desc": "恐慌下跌中，大单买入占比≥60%(机构坚定接盘)+散户割肉+极端振幅7%+底部微盘",
    },
    {
        "name": "C2: 双日温和恐慌(-3%)+散户割肉+大单+底20%+CM50",
        "params": {
            "prev1_pct_chg_max": -3,
            "sell_sm_gt_buy_sm": True,
            "buy_lg_gt_sell_lg": True,
            "close_position": "底20%",
            "circ_mv_max_wan": 500000,
            "amplitude_min": 5,
            "volume_ratio_min": 1.0,
        },
        "desc": "双日温和恐慌(-3%替代-5%，信号量+158%)+散户割肉+大单接盘+CM50扩容",
    },
    {
        "name": "C3: 恐慌+三重资金流(ELG+LG+散户)+振幅≥10%+CM50+底20%",
        "params": {
            "pct_chg_max": -5,
            "buy_elg_gt_sell_elg": True,
            "sell_sm_gt_buy_sm": True,
            "buy_lg_gt_sell_lg": True,
            "amplitude_min": 10,
            "circ_mv_max_wan": 500000,
            "close_position": "底20%",
        },
        "desc": "三重资金流确认(ELG+LG+散户割肉)+极端振幅10%(T3已验证)，无VR依赖",
    },
    {
        "name": "C4: SPX前日涨+恐慌+净流入+持续放量+底20%+CM100(大容量)",
        "params": {
            "spx_prev_day_up": True,
            "pct_chg_max": -5,
            "net_mf_gt_0": True,
            "vol_trend_5d": "持续放量",
            "close_position": "底20%",
            "circ_mv_max_wan": 1000000,
            "volume_ratio_min": 1.0,
            "amplitude_min": 5,
        },
        "desc": "SPX宏观窗口+恐慌+净流入+持续放量+CM100亿大容量版",
    },
    {
        "name": "C5: 恐慌+散户割肉+大单+PE≤15+振幅≥5%+底20%+CM30",
        "params": {
            "pct_chg_max": -5,
            "sell_sm_gt_buy_sm": True,
            "buy_lg_gt_sell_lg": True,
            "pe_max": 15,
            "amplitude_min": 5,
            "close_position": "底20%",
            "circ_mv_max_wan": 300000,
            "volume_ratio_min": 1.0,
        },
        "desc": "恐慌+散户割肉+大单+PE≤15深价值过滤，提升尾部风险控制",
    },
]

print("=" * 60)
print("T4 资金主力挖掘 - Iter28 (分块加载版)")
print(f"数据基准: {MAX_DATE}, 回测: {BACKTEST_START} ~ {MAX_DATE}")
print("=" * 60)

# ── Step 1: SPX ─────────────────────────────────────────────
print("\n[1/5] Loading SPX index data...")
spx_rows = ch_query(
    f"SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL "
    f"WHERE ts_code = 'SPX' AND trade_date >= toDate('{BACKTEST_START[:4]}-{BACKTEST_START[4:6]}-{BACKTEST_START[6:8]}') "
    f"ORDER BY trade_date"
)
spx_by_date = {}
for r in spx_rows:
    spx_by_date[r["trade_date"]] = r["pct_chg"]
print(f"  {len(spx_rows)} SPX rows")

# ── Step 2: Moneyflow (分年加载) ────────────────────────────
print("\n[2/5] Loading moneyflow data (分年加载)...")
mf_by_key = {}
years = list(range(2019, 2027))
for yr in years:
    start = f"{yr}-01-01"
    end = f"{yr}-12-31"
    if yr == 2026:
        end = "2026-05-13"
    rows = ch_query(
        f"SELECT ts_code, trade_date, "
        f"buy_lg_amount, sell_lg_amount, "
        f"buy_elg_vol, sell_elg_vol, "
        f"buy_lg_vol, sell_lg_vol, "
        f"buy_sm_vol, sell_sm_vol, "
        f"net_mf_amount "
        f"FROM tushare.tushare_moneyflow FINAL "
        f"WHERE trade_date >= toDate('{start}') AND trade_date <= toDate('{end}')"
    )
    for r in rows:
        mf_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")
print(f"  Total: {len(mf_by_key)} rows")

# ── Step 3: Daily_basic (分年加载) ──────────────────────────
print("\n[3/5] Loading daily_basic (分年加载)...")
basic_by_key = {}
for yr in years:
    start = f"{yr}-01-01"
    end = f"{yr}-12-31"
    if yr == 2026:
        end = "2026-05-13"
    rows = ch_query(
        f"SELECT ts_code, trade_date, volume_ratio, pe, circ_mv "
        f"FROM tushare.tushare_daily_basic FINAL "
        f"WHERE trade_date >= toDate('{start}') AND trade_date <= toDate('{end}')"
    )
    for r in rows:
        basic_by_key[(r["ts_code"], r["trade_date"])] = r
    print(f"   {yr}: {len(rows)} rows")
print(f"  Total: {len(basic_by_key)} rows")

# ── Step 4: Stock_daily (分年加载) ──────────────────────────
print("\n[4/5] Loading stock_daily (分年加载)...")
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
        f"AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'"
    )
    for r in rows:
        daily_by_code[r["ts_code"]].append(r)
    total_daily += len(rows)
    print(f"   {yr}: {len(rows)} rows")
print(f"  Total: {total_daily} rows, {len(daily_by_code)} stocks")

# Sort each stock's bars by date
print("Sorting by date...")
for c in daily_by_code:
    daily_by_code[c].sort(key=lambda x: x["trade_date"])

# ── 回测函数 ────────────────────────────────────────────────
def run_backtest(combo_idx, combo):
    name = combo["name"]
    params = combo["params"]
    print(f"\n{'='*50}")
    print(f"组合 {combo_idx+1}: {name}")
    print(f"  {combo['desc']}")
    
    signals = []
    
    for code, bars in daily_by_code.items():
        if len(bars) < 60:
            continue
        
        closes = [b.get("close") for b in bars]
        pos20 = []
        for i in range(len(closes)):
            if i < 19 or closes[i] is None:
                pos20.append(None)
            else:
                window = [c for c in closes[i-19:i+1] if c is not None]
                if len(window) < 20:
                    pos20.append(None)
                    continue
                h20 = max(window)
                l20 = min(window)
                pos20.append((closes[i] - l20) / (h20 - l20) if h20 != l20 else 0.5)
        
        vols = [b.get("vol") or 0 for b in bars]
        avg_vol_5 = []
        avg_vol_15 = []
        for i in range(len(vols)):
            avg_vol_5.append(sum(vols[i-4:i+1]) / 5.0 if i >= 4 else None)
            avg_vol_15.append(sum(vols[i-14:i+1]) / 15.0 if i >= 14 else None)
        
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
            
            dbk = (code, td)
            db = basic_by_key.get(dbk)
            if db is None:
                continue
            cm_wan = float(db.get("circ_mv") or 0)
            vr = db.get("volume_ratio")
            
            mfk = (code, td)
            mf = mf_by_key.get(mfk)
            
            cp = pos20[i] if pos20[i] is not None else None
            if cp is None:
                continue
            
            matched = False
            
            if combo_idx == 0:  # C1
                if pct > -5: continue
                if mf is None: continue
                total_lg = safe_float(mf.get("buy_lg_amount")) + safe_float(mf.get("sell_lg_amount"))
                if total_lg <= 0: continue
                lg_ratio = safe_float(mf.get("buy_lg_amount")) / total_lg * 100
                if lg_ratio < 60: continue
                if safe_float(mf.get("sell_sm_vol")) <= safe_float(mf.get("buy_sm_vol")): continue
                if amp < 7: continue
                if cp > 0.2: continue
                if cm_wan > 300000: continue
                if vr is None or vr < 1.0: continue
                matched = True
            
            elif combo_idx == 1:  # C2
                if pct > -3: continue
                if i < 1: continue
                prev_pct = bars[i-1].get("pct_chg")
                if prev_pct is None or prev_pct > -3: continue
                if mf is None: continue
                if safe_float(mf.get("sell_sm_vol")) <= safe_float(mf.get("buy_sm_vol")): continue
                if safe_float(mf.get("buy_lg_vol")) <= safe_float(mf.get("sell_lg_vol")): continue
                if cp > 0.2: continue
                if cm_wan > 500000: continue
                if amp < 5: continue
                if vr is None or vr < 1.0: continue
                matched = True
            
            elif combo_idx == 2:  # C3
                if pct > -5: continue
                if mf is None: continue
                if safe_float(mf.get("buy_elg_vol")) <= safe_float(mf.get("sell_elg_vol")): continue
                if safe_float(mf.get("sell_sm_vol")) <= safe_float(mf.get("buy_sm_vol")): continue
                if safe_float(mf.get("buy_lg_vol")) <= safe_float(mf.get("sell_lg_vol")): continue
                if amp < 10: continue
                if cm_wan > 500000: continue
                if cp > 0.2: continue
                matched = True
            
            elif combo_idx == 3:  # C4
                if pct > -5: continue
                td_dt = datetime.strptime(td, "%Y-%m-%d")
                spx_found = None
                for days_back in range(1, 8):
                    check_date = (td_dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
                    if check_date in spx_by_date:
                        spx_found = spx_by_date[check_date]
                        break
                if spx_found is None or spx_found <= 0: continue
                if mf is None: continue
                if safe_float(mf.get("net_mf_amount")) <= 0: continue
                if avg_vol_5[i] is None or avg_vol_15[i] is None: continue
                if avg_vol_5[i] <= avg_vol_15[i] * 1.05: continue
                if cp > 0.2: continue
                if cm_wan > 1000000: continue
                if vr is None or vr < 1.0: continue
                if amp < 5: continue
                matched = True
            
            elif combo_idx == 4:  # C5
                if pct > -5: continue
                if mf is None: continue
                if safe_float(mf.get("sell_sm_vol")) <= safe_float(mf.get("buy_sm_vol")): continue
                if safe_float(mf.get("buy_lg_vol")) <= safe_float(mf.get("sell_lg_vol")): continue
                pe = db.get("pe")
                if pe is None or pe <= 0 or pe > 15: continue
                if amp < 5: continue
                if cp > 0.2: continue
                if cm_wan > 300000: continue
                if vr is None or vr < 1.0: continue
                matched = True
            
            if matched:
                signals.append((code, td, close))
    
    print(f"  总信号数: {len(signals)}")
    if len(signals) < 10:
        return {"name": name, "signals": 0, "error": f"信号不足({len(signals)})"}
    
    # ── 计算收益 ──
    hold_days = [1, 3, 5, 10, 20]
    returns = {hd: [] for hd in hold_days}
    
    for code, td, buy_close in signals:
        stocks_bars = daily_by_code[code]
        buy_idx = None
        for j, b in enumerate(stocks_bars):
            if b["trade_date"] == td:
                buy_idx = j
                break
        if buy_idx is None:
            continue
        
        for hd in hold_days:
            sell_idx = buy_idx + hd
            if sell_idx < len(stocks_bars):
                sc = stocks_bars[sell_idx]["close"]
                if sc and buy_close and buy_close > 0:
                    ret = (sc / buy_close - 1) * 100
                    returns[hd].append(ret)
    
    # ── 计算指标 ──
    results = {}
    for hd in hold_days:
        ret_list = returns[hd]
        n = len(ret_list)
        if n < 5:
            results[f"ret_{hd}d"] = {"n": n, "wr": 0, "avg_ret": 0, "sharpe": 0, "p10": 0}
            continue
        win = sum(1 for r in ret_list if r > 0)
        wr = win / n * 100
        avg_ret = sum(ret_list) / n
        std = math.sqrt(sum((r - avg_ret) ** 2 for r in ret_list) / (n - 1)) if n > 1 else 0
        sharpe = (avg_ret / std * math.sqrt(252 / hd)) if std > 0 else 0
        sorted_rets = sorted(ret_list)
        p10 = sorted_rets[max(0, int(n * 0.1) - 1)] if n >= 10 else sorted_rets[0]
        results[f"ret_{hd}d"] = {"n": n, "wr": round(wr, 2), "avg_ret": round(avg_ret, 2),
                                  "sharpe": round(sharpe, 3), "p10": round(p10, 2)}
    
    for hd in [1, 3, 5, 10, 20]:
        r = results[f"ret_{hd}d"]
        if r["n"] > 0:
            print(f"  T+{hd}: N={r['n']}, WR={r['wr']:.2f}%, Avg={r['avg_ret']:.2f}%, Sharpe={r['sharpe']:.3f}, P10={r['p10']:.2f}%")
        else:
            print(f"  T+{hd}: N=0")
    
    return {"name": name, "params": params, "signals": len(signals), "results": results}

# ── 执行回测 ────────────────────────────────────────────────
all_results = []
for idx, combo in enumerate(COMBOS):
    result = run_backtest(idx, combo)
    all_results.append(result)

# ── 写入分析报告 ─────────────────────────────────────────────
OUTPUT_PATH = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_28/analysis_资金主力.md"
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(f"# Iter28 T4: 资金主力挖掘 — 分析报告\n\n")
    f.write(f"- **执行时间**: 2026-05-14 02:23 UTC+8\n")
    f.write(f"- **数据基准**: {MAX_DATE[:4]}-{MAX_DATE[4:6]}-{MAX_DATE[6:8]}\n")
    f.write(f"- **回测区间**: {BACKTEST_START[:4]}-{BACKTEST_START[4:6]}-{BACKTEST_START[6:8]} ~ {MAX_DATE[:4]}-{MAX_DATE[4:6]}-{MAX_DATE[6:8]}\n")
    f.write(f"- **历史最佳WR**: 99.55%（CROSS-6, Iter25）\n")
    f.write(f"- **历史最佳R5**: 25.23%（CROSS-6, Iter25）\n")
    f.write(f"- **T4流派最佳R5**: 13.48%（T4-C5-MIX, Iter25）\n")
    f.write(f"- **疲劳计数**: 2\n\n")
    f.write(f"---\n\n")
    
    best_combo = None
    best_score = -999
    
    for idx, result in enumerate(all_results):
        combo = COMBOS[idx]
        h = combo_hash(combo["params"])
        
        f.write(f"## 组合 {idx+1}: {combo['name']}\n\n")
        f.write(f"**描述**: {combo['desc']}\n\n")
        f.write(f"**Hash**: {h}\n\n")
        f.write(f"**信号数**: {result['signals']}\n\n")
        
        if "error" in result:
            f.write(f"**状态**: ❌ {result['error']}\n\n")
        else:
            f.write(f"| 持有期 | 信号数 | 胜率(WR) | 平均收益 | 夏普比率 | P10 |\n")
            f.write(f"|:-----:|:-----:|:--------:|:--------:|:--------:|:---:|\n")
            for hd in [1, 3, 5, 10, 20]:
                r = result["results"].get(f"ret_{hd}d", {})
                if r.get("n", 0) > 0:
                    f.write(f"| T+{hd} | {r['n']} | {r['wr']:.2f}% | {r['avg_ret']:.2f}% | {r['sharpe']:.3f} | {r['p10']:.2f}% |\n")
                else:
                    f.write(f"| T+{hd} | 0 | N/A | N/A | N/A | N/A |\n")
            
            r5 = result["results"].get("ret_5d", {})
            n5 = r5.get("n", 0)
            wr5 = r5.get("wr", 0)
            avg5 = r5.get("avg_ret", 0)
            passes = n5 >= 200 and wr5 >= 52 and avg5 >= 3
            status = "✅ PASS" if passes else "❌ FAIL"
            
            perf_line = f"N={n5}, WR={wr5:.2f}%, R5={avg5:.2f}%"
            if r5.get("sharpe"):
                perf_line += f", Sharpe={r5['sharpe']:.3f}"
            if r5.get("p10"):
                perf_line += f", P10={r5['p10']:.2f}%"
            
            f.write(f"\n**状态**: {status} — {perf_line}\n\n")
            
            if passes:
                score = wr5 * 0.6 + avg5 * 3 + math.log10(max(n5, 10)) * 5
                f.write(f"**综合评分**: {score:.2f}\n\n")
                if score > best_score:
                    best_score = score
                    best_combo = {"combo_idx": idx + 1, **result, "score": score}
        
        f.write(f"**最大失败路径**: 恐慌反转失败，股价继续下跌，散户割肉是滞后指标\n\n")
        f.write("---\n\n")
    
    f.write(f"## 🏆 最佳策略\n\n")
    if best_combo:
        idx = best_combo["combo_idx"]
        combo = COMBOS[idx - 1]
        f.write(f"**组合 {idx}: {combo['name']}**\n\n")
        f.write(f"**参数**:\n")
        for k, v in combo["params"].items():
            f.write(f"- {k}: {v}\n")
        f.write(f"\n**指标**:\n")
        for hd in [1, 3, 5, 10, 20]:
            r = best_combo["results"].get(f"ret_{hd}d", {})
            if r.get("n", 0) > 0:
                f.write(f"- T+{hd}: N={r['n']}, WR={r['wr']:.2f}%, Avg={r['avg_ret']:.2f}%, Sharpe={r['sharpe']:.3f}, P10={r['p10']:.2f}%\n")
        f.write(f"\n**综合评分**: {best_combo['score']:.2f}\n")
    else:
        f.write("无策略通过成功标准\n")
    
    f.write(f"\n## 数据来源\n")
    f.write(f"- 日线行情: tushare_stock_daily\n")
    f.write(f"- 每日指标: tushare_daily_basic\n")
    f.write(f"- 资金流向: tushare_moneyflow\n")
    f.write(f"- 全球指数: tushare_index_global (SPX)\n")
    f.write(f"- 查询工具: ch_query.py (ClickHouse)\n")

print(f"\n\n分析报告已写入: {OUTPUT_PATH}")
print("完成!")
