#!/usr/bin/env python3
"""T9 跨流派交叉验证 — Iteration 4
从 T2-T8 最佳发现中提取因子，做 12 组交叉组合 + 回测。
数据基准: 2026-05-11
回测范围: 2020-01-01 ~ 2026-05-11
"""
import json, math, subprocess, sys, hashlib, os
from datetime import datetime
from collections import defaultdict

CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_HOST = "172.24.224.1"
CH_PORT = "8123"
CH_DB = "tushare"
MAX_DATE = "2026-05-11"
BT_START = "2020-01-01"

def ch_query_rows(sql, timeout=300):
    import urllib.request, urllib.parse
    url = f"http://{CH_HOST}:{CH_PORT}/"
    params = {
        "user": CH_USER,
        "password": CH_PASS,
        "database": CH_DB,
        "query": sql,
        "default_format": "JSONEachRow",
        "max_execution_time": str(timeout),
    }
    qs = urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(f"{url}?{qs}")
        with urllib.request.urlopen(req, timeout=timeout+10) as resp:
            body = resp.read().decode("utf-8")
            if not body.strip():
                return []
            return [json.loads(line) for line in body.strip().split("\n") if line.strip()]
    except Exception as e:
        print(f"  [ERROR] {e}", file=sys.stderr)
        return []

ST_FILTER = "AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_stock_basic FINAL WHERE name LIKE '%ST%')"
def parse_date(d):
    s = str(d).replace("-", "")
    return int(s)

def compute_stats(results):
    n = len(results)
    if n == 0:
        return {"signal_count": 0, "wr_1d": 0, "wr_3d": 0, "wr_5d": 0, "wr_10d": 0, "wr_20d": 0,
                "ret_1d": 0, "ret_3d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
    def avg(lst): return sum(lst)/len(lst) if lst else 0
    def std(lst):
        if len(lst) < 2: return 0
        m = avg(lst)
        return math.sqrt(sum((x-m)**2 for x in lst)/len(lst))
    stats = {"signal_count": n}
    for k in ["ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d"]:
        vals = [r[k] for r in results if r[k] is not None]
        wins = sum(1 for v in vals if v > 0)
        stats[f"wr_{k.split('_')[1]}"] = round(wins/len(vals)*100, 2) if vals else 0
        stats[k] = round(avg(vals)*100, 4) if vals else 0
    ret5 = [r["ret_5d"] for r in results if r["ret_5d"] is not None]
    if len(ret5) > 1:
        m5, s5 = avg(ret5), std(ret5)
        stats["sharpe_5d"] = round(m5/s5*math.sqrt(252/5), 4) if s5 > 0 else 0
    else:
        stats["sharpe_5d"] = 0
    # 中位数
    ret5_sorted = sorted(ret5)
    if ret5_sorted:
        stats["median_ret_5d"] = round(ret5_sorted[len(ret5_sorted)//2]*100, 4)
    return stats

# ═══════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════
print("="*60)
print(f"T9 跨流派交叉验证 - Iter 4")
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"回测: {BT_START} ~ {MAX_DATE}")
print("="*60)

print("\n[1/5] Loading stock_daily...")
rows = ch_query_rows(f"""SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '{BT_START}' AND trade_date <= '{MAX_DATE}'
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_stock_basic FINAL WHERE name LIKE '%ST%')
ORDER BY ts_code, trade_date""")
print(f"  {len(rows)} rows")
by_code = defaultdict(list)
for r in rows:
    by_code[r["ts_code"]].append(r)
for c in by_code:
    by_code[c].sort(key=lambda x: parse_date(x["trade_date"]))
print(f"  {len(by_code)} stocks")

print("[2/5] Loading daily_basic...")
brow = ch_query_rows(f"""SELECT ts_code, trade_date, turnover_rate, volume_ratio, pe, pb, dv_ratio, circ_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '{BT_START}' AND trade_date <= '{MAX_DATE}'""")
bd = {}
for r in brow:
    bd[(r["ts_code"], parse_date(r["trade_date"]))] = r
print(f"  {len(brow)} rows")

print("[3/5] Loading moneyflow...")
mrow = ch_query_rows(f"""SELECT ts_code, trade_date, net_mf_amount, buy_lg_amount, sell_lg_amount
FROM tushare.tushare_moneyflow FINAL
WHERE trade_date >= '{BT_START}' AND trade_date <= '{MAX_DATE}'""")
mf = {}
for r in mrow:
    mf[(r["ts_code"], parse_date(r["trade_date"]))] = r
print(f"  {len(mrow)} rows")

print("[4/5] Loading shibor...")
srow = ch_query_rows(f"""SELECT date, 1w FROM tushare.tushare_shibor FINAL
WHERE date >= '{BT_START}' AND date <= '{MAX_DATE}'""")
shibor = {}
for r in srow:
    d = parse_date(r["date"])
    one_w = r.get("1w")
    if one_w is not None:
        shibor[d] = float(one_w)
print(f"  {len(srow)} records")

print("[5/5] Loading forecast...")
frow = ch_query_rows(f"""SELECT ts_code, end_date, type FROM (
  SELECT ts_code, end_date, type, row_number() OVER (PARTITION BY ts_code ORDER BY end_date DESC) AS rn
  FROM tushare.tushare_forecast FINAL
) WHERE rn = 1""")
forecast = {}
for r in frow:
    forecast[r["ts_code"]] = r.get("type")
print(f"  {len(frow)} records")

# ═══════════════════════════════════════════════
# 回测函数
# ═══════════════════════════════════════════════
def combo_hash(name, params):
    return hashlib.md5(f"{name}:{json.dumps(params, sort_keys=True)}".encode()).hexdigest()[:12]

def run_backtest(name, params, t9_only=True):
    """
    params dict:
    必选: {pos_max, amp_min, tr_min, tr_max, vr_min, cm_max}
    可选: {pct_chg_max, net_mf_min, buy_lg_ratio_min, shibor_1w_max,
           dv_ratio_min, pe_max, pb_max, forecast_type, pct_min,
           vol_trend_5d, vol_trend_type}
    注: net_mf_min单位万元
    """
    h = combo_hash(name, params)
    results = []
    total_stocks = len(by_code)
    for idx, (code, days) in enumerate(by_code.items()):
        if (idx+1) % 500 == 0:
            print(f"  {name}: {idx+1}/{total_stocks} stocks, {len(results)} signals", end="\r")
        n = len(days)
        for i in range(20, n-20):
            d = days[i]
            dt = parse_date(d["trade_date"])

            # --- 位置计算 ---
            window = [days[j]["close"] for j in range(i-19, i+1)]
            low_20d = min(window)
            high_20d = max(window)
            if low_20d == high_20d:
                continue
            pos = (d["close"] - low_20d) / (high_20d - low_20d)
            if pos > params.get("pos_max", 0.20):
                continue

            # --- 振幅 ---
            pre_close = d.get("pre_close")
            if not pre_close or pre_close == 0:
                continue
            amp = (d["high"] - d["low"]) / pre_close * 100
            if amp < params.get("amp_min", 0):
                continue

            # --- pct_chg ---
            pct = d.get("pct_chg", 0)
            if pct is None:
                continue
            if "pct_chg_max" in params and pct > params["pct_chg_max"]:
                continue
            if "pct_chg_min" in params and pct < params["pct_chg_min"]:
                continue
            # pct_chg ≤ X 用于恐慌
            if "pct_chg_leq" in params and pct > params["pct_chg_leq"]:
                continue

            # --- pct_min (含pct≥) ---
            if "pct_min" in params and pct < params["pct_min"]:
                continue

            # --- 换手率 ---
            bk = bd.get((code, dt))
            if bk is None:
                continue
            tr = bk.get("turnover_rate")
            if tr is None:
                continue
            if "tr_min" in params and tr < params["tr_min"]:
                continue
            if "tr_max" in params and tr > params["tr_max"]:
                continue

            # --- 量比 ---
            vr = bk.get("volume_ratio")
            if vr is None or vr < params.get("vr_min", 0):
                continue

            # --- 市值 ---
            cm = bk.get("circ_mv")
            if cm is None or cm == 0:
                continue
            cm_wan = float(cm)
            if "cm_max" in params and cm_wan > params["cm_max"]:
                continue

            # --- 成交量趋势 持续放量5日 ---
            if params.get("vol_trend_5d"):
                if i < 4:
                    continue
                vols = [days[i-j]["vol"] for j in range(0, 5)]
                if not all(v > 0 for v in vols):
                    continue
                if not (vols[0] > vols[1] > vols[2] > vols[3] > vols[4]):
                    # vol_trend_5d: vol[0]=today > vol[1]=yesterday > ...
                    # Actually "持续放量" means vol is increasing each day
                    # Let's check today > yesterday > day_before... for 5 days
                    pass  # we need to check ascending order
                # Check ascending: each day volume > previous day
                ok = True
                for j in range(4):
                    if vols[j] <= vols[j+1]:
                        ok = False
                        break
                if not ok:
                    continue

            # --- 资金流 ---
            mk = mf.get((code, dt))
            if params.get("net_mf_min") is not None or params.get("buy_lg_ratio_min") is not None:
                if mk is None:
                    continue
                net = mk.get("net_mf_amount")
                if net is None:
                    continue
                if "net_mf_min" in params and net < params["net_mf_min"]:
                    continue
                bl = mk.get("buy_lg_amount")
                sl = mk.get("sell_lg_amount")
                if bl is not None and sl is not None and (bl + sl) > 0:
                    bl_ratio = bl / (bl + sl)
                    if "buy_lg_ratio_min" in params and bl_ratio < params["buy_lg_ratio_min"]:
                        continue
                elif params.get("buy_lg_ratio_min") is not None and params["buy_lg_ratio_min"] > 0:
                    continue

            # --- 基本面 ---
            if params.get("dv_ratio_min") is not None:
                dv = bk.get("dv_ratio")
                if dv is None or float(dv) < params["dv_ratio_min"]:
                    continue
            if params.get("pe_max") is not None:
                pe = bk.get("pe")
                if pe is None or float(pe) <= 0 or float(pe) > params["pe_max"]:
                    continue
            if params.get("pb_max") is not None:
                pb = bk.get("pb")
                if pb is None or float(pb) <= 0 or float(pb) > params["pb_max"]:
                    continue
            if params.get("forecast_type"):
                ft = forecast.get(code)
                if ft != params["forecast_type"]:
                    continue

            # --- Shibor ---
            if params.get("shibor_1w_max") is not None:
                sw = shibor.get(dt)
                if sw is None or sw >= params["shibor_1w_max"]:
                    continue

            # --- 计算未来收益 ---
            if i+20 >= n:
                continue
            c1 = days[i+1]["close"] if i+1 < n else None
            c3 = days[i+3]["close"] if i+3 < n else None
            c5 = days[i+5]["close"] if i+5 < n else None
            c10 = days[i+10]["close"] if i+10 < n else None
            c20 = days[i+20]["close"] if i+20 < n else None
            close = d["close"]
            results.append({
                "ts_code": code, "trade_date": d["trade_date"],
                "ret_1d": (c1/close-1) if c1 else None,
                "ret_3d": (c3/close-1) if c3 else None,
                "ret_5d": (c5/close-1) if c5 else None,
                "ret_10d": (c10/close-1) if c10 else None,
                "ret_20d": (c20/close-1) if c20 else None,
            })
    print(f"  {name}: {len(results)} signals    ")
    return results

# ═══════════════════════════════════════════════
# 12 组交叉组合定义 + 回测
# ═══════════════════════════════════════════════
COMBOS = [
    # XC1: T2持续放量 × T7 Shibor宽松 (动量+宏观)
    {
        "id": "XC1",
        "name": "T2持续放量+T7_Shibor",
        "desc": "{T2-C1深底持续放量} × {T7-C6 Shibor宽松}",
        "parents": ["T2-C1", "T7-C6"],
        "params": {
            "pos_max": 0.10, "amp_min": 5,
            "tr_min": 1.0, "tr_max": 8.0, "vr_min": 1.0,
            "cm_max": 1000000,
            "vol_trend_5d": True,
            "shibor_1w_max": 1.5,
        }
    },
    # XC2: T2持续放量 × T4恐慌逆势资金 (动量+资金)
    {
        "id": "XC2",
        "name": "T2持续放量+T4恐慌逆势",
        "desc": "{T2-C1深底持续放量} × {T4-C2恐慌逆势资金}",
        "parents": ["T2-C1", "T4-C2"],
        "params": {
            "pos_max": 0.10, "amp_min": 5,
            "tr_min": 0.5, "tr_max": 15.0, "vr_min": 1.0,
            "cm_max": 500000,
            "vol_trend_5d": True,
            "pct_chg_leq": -4.0,
            "net_mf_min": 200,
            "buy_lg_ratio_min": 0.08,
        }
    },
    # XC3: T7 Shibor × T5高股息预增 (宏观+基本面)
    {
        "id": "XC3",
        "name": "T7_Shibor+T5高股息预增",
        "desc": "{T7-C6 Shibor宽松深底} × {T5-C10高股息预增}",
        "parents": ["T7-C6", "T5-C10"],
        "params": {
            "pos_max": 0.10, "amp_min": 7,
            "tr_min": 1.0, "tr_max": 10.0, "vr_min": 1.0,
            "cm_max": 1000000,
            "shibor_1w_max": 1.5,
            "dv_ratio_min": 2.0,
            "pe_max": 15,
            "pb_max": 2,
            "forecast_type": "预增",
        }
    },
    # XC4: T4恐慌逆势 × T7 Shibor (资金+宏观)
    {
        "id": "XC4",
        "name": "T4恐慌逆势+T7_Shibor",
        "desc": "{T4-C2恐慌逆势资金} × {T7-C7 Shibor宽松恐慌}",
        "parents": ["T4-C2", "T7-C7"],
        "params": {
            "pos_max": 0.20, "amp_min": 5,
            "tr_min": 0.5, "tr_max": 15.0, "vr_min": 1.0,
            "cm_max": 500000,
            "pct_chg_leq": -4.0,
            "net_mf_min": 200,
            "buy_lg_ratio_min": 0.08,
            "shibor_1w_max": 1.5,
        }
    },
    # XC5: T4恐慌逆势 × T5高股息预增 (资金+基本面)
    {
        "id": "XC5",
        "name": "T4恐慌逆势+T5高股息预增",
        "desc": "{T4-C2恐慌逆势资金} × {T5-C10高股息预增}",
        "parents": ["T4-C2", "T5-C10"],
        "params": {
            "pos_max": 0.20, "amp_min": 5,
            "tr_min": 0.5, "tr_max": 15.0, "vr_min": 1.0,
            "cm_max": 500000,
            "pct_chg_leq": -4.0,
            "net_mf_min": 200,
            "buy_lg_ratio_min": 0.08,
            "dv_ratio_min": 2.0,
            "pe_max": 15,
            "pb_max": 2,
            "forecast_type": "预增",
        }
    },
    # XC6: T8量价大振幅 × T7 Shibor (形态+宏观)
    {
        "id": "XC6",
        "name": "T8量价深底+T7_Shibor",
        "desc": "{T8-C13深底大振幅} × {T7-C6 Shibor宽松}",
        "parents": ["T8-C13", "T7-C6"],
        "params": {
            "pos_max": 0.15, "amp_min": 6,
            "tr_min": 0.5, "tr_max": 10.0, "vr_min": 1.3,
            "cm_max": 500000,
            "pct_min": 2.0,
            "shibor_1w_max": 1.5,
        }
    },
    # XC7: T8量价大振幅 × T4恐慌逆势 (形态+资金)
    {
        "id": "XC7",
        "name": "T8量价深底+T4恐慌逆势",
        "desc": "{T8-C13深底大振幅} × {T4-C2恐慌逆势资金}",
        "parents": ["T8-C13", "T4-C2"],
        "params": {
            "pos_max": 0.15, "amp_min": 6,
            "tr_min": 0.5, "tr_max": 10.0, "vr_min": 1.3,
            "cm_max": 500000,
            "pct_min": 2.0,
            "pct_chg_leq": -4.0,
            "net_mf_min": 200,
            "buy_lg_ratio_min": 0.08,
        }
    },
    # XC8: T2持续放量 × T5高股息预增 (动量+基本面)
    {
        "id": "XC8",
        "name": "T2持续放量+T5高股息预增",
        "desc": "{T2-C1深底持续放量} × {T5-C10高股息预增}",
        "parents": ["T2-C1", "T5-C10"],
        "params": {
            "pos_max": 0.10, "amp_min": 5,
            "tr_min": 1.0, "tr_max": 8.0,
            "cm_max": 1000000,
            "vol_trend_5d": True,
            "dv_ratio_min": 2.0,
            "pe_max": 15,
            "pb_max": 2,
            "forecast_type": "预增",
        }
    },
    # XC9: T4恐慌逆势 × T2持续放量 × T7 Shibor (三因子融合)
    {
        "id": "XC9",
        "name": "T4恐慌+T2放量+T7_Shibor(三因子)",
        "desc": "{T4-C2恐慌逆势} × {T2-C1持续放量} × {T7-C6 Shibor宽松}",
        "parents": ["T4-C2", "T2-C1", "T7-C6"],
        "params": {
            "pos_max": 0.10, "amp_min": 5,
            "tr_min": 0.5, "tr_max": 10.0, "vr_min": 1.0,
            "cm_max": 500000,
            "vol_trend_5d": True,
            "pct_chg_leq": -4.0,
            "net_mf_min": 200,
            "buy_lg_ratio_min": 0.08,
            "shibor_1w_max": 1.5,
        }
    },
    # XC10: T5高股息预增 × T7 Shibor (基本面+宏观)
    {
        "id": "XC10",
        "name": "T5高股息+T7_Shibor(放松)",
        "desc": "{T5-C10高股息预增} × {T7-C6 Shibor宽松 (位置40%)}",
        "parents": ["T5-C10", "T7-C6"],
        "params": {
            "pos_max": 0.40, "amp_min": 3,
            "vr_min": 1.0,
            "shibor_1w_max": 1.5,
            "dv_ratio_min": 2.0,
            "pe_max": 15,
            "pb_max": 2,
            "forecast_type": "预增",
        }
    },
    # XC11: T8量价大振幅 × T2持续放量 (形态+动量)
    {
        "id": "XC11",
        "name": "T8量价大振幅+T2持续放量",
        "desc": "{T8-C13深底大振幅} × {T2-C1持续放量}",
        "parents": ["T8-C13", "T2-C1"],
        "params": {
            "pos_max": 0.15, "amp_min": 6,
            "tr_min": 0.5, "tr_max": 10.0,
            "cm_max": 500000,
            "pct_min": 2.0,
            "vol_trend_5d": True,
        }
    },
    # XC12: T6深底大振幅 × T4恐慌逆势 (板块+资金)
    {
        "id": "XC12",
        "name": "T6深底大振幅+T4恐慌逆势",
        "desc": "{T6-C5深底大振幅} × {T4-C2恐慌逆势资金}",
        "parents": ["T6-C5", "T4-C2"],
        "params": {
            "pos_max": 0.10, "amp_min": 7,
            "tr_min": 1.0, "tr_max": 10.0, "vr_min": 1.0,
            "pct_chg_leq": -4.0,
            "net_mf_min": 200,
            "buy_lg_ratio_min": 0.08,
            # no cm_max — T6无市值限制
        }
    },
]

all_results = {}
print("\n" + "="*60)
print("开始回测 12 组交叉组合...")
print("="*60)

for combo in COMBOS:
    print(f"\n▸ {combo['id']}: {combo['name']}")
    print(f"  描述: {combo['desc']}")
    results = run_backtest(combo["id"], combo["params"])
    stats = compute_stats(results)
    all_results[combo["id"]] = {"stats": stats, "combo": combo}
    
    print(f"  ── 结果 ──")
    print(f"  N={stats['signal_count']}, WR5={stats['wr_5d']}%, R5={stats['ret_5d']}%")
    print(f"  R10={stats['ret_10d']}%, R20={stats['ret_20d']}%")
    print(f"  Sharpe5={stats['sharpe_5d']}, Median5={stats.get('median_ret_5d', 'N/A')}%")
    passed = (
        stats['signal_count'] >= 200 and
        stats['wr_5d'] >= 52.0 and
        stats['ret_5d'] >= 3.0
    )
    print(f"  达标: {'✅' if passed else '❌'}")

# ═══════════════════════════════════════════════
# 汇总输出
# ═══════════════════════════════════════════════
print("\n" + "="*60)
print("T9 跨流派交叉验证 — 最终汇总")
print("="*60)

results_summary = []
for cid, data in sorted(all_results.items()):
    s = data["stats"]
    results_summary.append({
        "id": cid,
        "name": data["combo"]["name"],
        "desc": data["combo"]["desc"],
        "n": s["signal_count"],
        "wr_5d": s["wr_5d"],
        "ret_5d": s["ret_5d"],
        "ret_10d": s["ret_10d"],
        "ret_20d": s["ret_20d"],
        "sharpe_5d": s["sharpe_5d"],
        "median_5d": s.get("median_ret_5d", 0),
        "pass": (s['signal_count'] >= 200 and s['wr_5d'] >= 52.0 and s['ret_5d'] >= 3.0)
    })

# 排序
results_summary.sort(key=lambda x: (-x["pass"], -x["ret_5d"]))
print(f"\n{'ID':<8} {'名称':<30} {'N':<6} {'WR5':<8} {'R5':<8} {'R10':<8} {'R20':<8} {'Sharpe':<8} {'中位R5':<8} {'达标'}")
print("-"*110)
for r in results_summary:
    pf = "✅" if r["pass"] else "❌"
    print(f"{r['id']:<8} {r['name']:<30} {r['n']:<6} {r['wr_5d']:<8.2f} {r['ret_5d']:<8.4f} {r['ret_10d']:<8.4f} {r['ret_20d']:<8.4f} {r['sharpe_5d']:<8.4f} {r['median_5d']:<8.4f} {pf}")

# 导出JSON供报告使用
out = {"results": results_summary, "generated_at": datetime.now().isoformat()}
with open("/tmp/t9_cross_results.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n详细结果写入 /tmp/t9_cross_results.json")
