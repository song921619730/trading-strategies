#!/usr/bin/env python3
"""Iter18 T6 板块轮动 - v2: 真正新的参数组合"""
import json, subprocess, sys, math
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START = '2020-01-01'
END = '2026-05-12'

def chq(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0: return []
    try:
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else data.get("data", [])
    except: return []

def sharpe(rets):
    if len(rets) < 5: return 0
    m = sum(rets)/len(rets)
    if m <= 0: return 0
    var = sum((r-m)**2 for r in rets)/len(rets)
    std = math.sqrt(var)
    return m/std*math.sqrt(252/5) if std>1e-10 else 0

def p10(rets):
    if not rets: return 0
    sr = sorted(rets)
    return sr[max(0, int(len(sr)*0.1)-1)]

def p90(rets):
    if not rets: return 0
    sr = sorted(rets)
    return sr[min(len(sr)-1, int(len(sr)*0.9))]

def run_combo(cid, name, desc, sql):
    print(f"\n{'='*60}")
    print(f"[{cid}] {name}: {desc}")
    print(f"{'='*60}")
    
    rows = chq(sql)
    if not rows:
        print(f"  ❌ 空结果")
        return {"cid": cid, "name": name, "signals_raw": 0, "error": "empty"}
    
    print(f"  ✅ 原始信号: {len(rows)}")
    
    # Dedup
    sigs = {}
    col_ts = "ts_code" if "ts_code" in rows[0] else "s.ts_code"
    col_dt = "trade_date" if "trade_date" in rows[0] else "s.trade_date"
    col_cl = "close" if "close" in rows[0] else "s.close"
    col_pc = "pct_chg" if "pct_chg" in rows[0] else "s.pct_chg"
    
    for r in rows:
        code = r[col_ts]
        dt = str(r[col_dt]).replace("-", "")
        sigs[(code, dt)] = {"close": r[col_cl], "pct_chg": r[col_pc]}
    
    print(f"  ✅ 唯一信号: {len(sigs)}")
    
    codes = list(set(k[0] for k in sigs.keys()))
    print(f"  [数据] 唯一个股: {len(codes)}")
    
    # Load full historical data for these codes
    stock_data = {}
    for i in range(0, len(codes), 200):
        batch = codes[i:i+200]
        cs = ",".join(f"'{c}'" for c in batch)
        q = f"""
        SELECT ts_code, trade_date, close, high, low
        FROM tushare.tushare_stock_daily FINAL
        WHERE ts_code IN ({cs})
          AND trade_date >= '{START}' AND trade_date <= '{END}'
        ORDER BY ts_code, trade_date
        """
        r2 = chq(q)
        for r in r2:
            c = r["ts_code"]; d = str(r["trade_date"]).replace("-","")
            stock_data.setdefault(c, []).append((d, r["close"], r["high"], r["low"]))
        if (i//200) % 2 == 0:
            print(f"  [进度] {min(i+200,len(codes))}/{len(codes)}")
    
    print(f"  [数据] 总行数: {sum(len(v) for v in stock_data.values())}")
    
    # For MA computation: also load MA5, MA10, MA20
    # We compute MA from close prices
    def compute_ma(bars, pos, period):
        if pos < period-1: return None
        return sum(bars[j][1] for j in range(pos-period+1, pos+1)) / period
    
    # Filter + forward returns
    valid = []
    r5l, r10l, r20l = [], [], []
    
    for (code, dt), sig in sigs.items():
        bars = stock_data.get(code, [])
        if len(bars) < 20: continue
        
        idx = None
        for j, (bd, *_) in enumerate(bars):
            if bd == dt: idx = j; break
        if idx is None or idx < 20: continue
        
        # Bottom 20% check
        window = bars[idx-19:idx+1]
        wc = [w[1] for w in window]
        mn, mx = min(wc), max(wc)
        if mx == mn: continue
        pos = (sig["close"] - mn) / (mx - mn)
        if pos >= 0.20: continue
        
        valid.append((code, dt))
        future = bars[idx:]
        
        def fwd(n):
            return (future[n][1]/sig["close"]-1)*100 if len(future) > n else None
        
        r5 = fwd(5); r10 = fwd(10); r20 = fwd(20)
        if r5 is not None: r5l.append(r5)
        if r10 is not None: r10l.append(r10)
        if r20 is not None: r20l.append(r20)
    
    print(f"  ✅ 底20%过滤后: {len(valid)}, 有5D收益: {len(r5l)}")
    
    if len(r5l) < 50:
        return {"cid": cid, "name": name, "signals": len(valid), "n5": len(r5l), "error": "too_few"}
    
    wr5 = sum(1 for r in r5l if r>0)/len(r5l)*100
    wr10 = sum(1 for r in r10l if r>0)/len(r10l)*100 if r10l else 0
    wr20 = sum(1 for r in r20l if r>0)/len(r20l)*100 if r20l else 0
    avg5 = sum(r5l)/len(r5l)
    avg10 = sum(r10l)/len(r10l) if r10l else 0
    avg20 = sum(r20l)/len(r20l) if r20l else 0
    sh5 = sharpe(r5l)
    p10_5 = p10(r5l)
    p90_5 = p90(r5l)
    
    passed = wr5 >= 55 and avg5 >= 5 and len(r5l) >= 200
    details = {"wr55": wr5>=55, "r5": avg5>=5, "n200": len(r5l)>=200}
    
    print(f"  WR5={wr5:.2f}% WR10={wr10:.2f}%")
    print(f"  R5={avg5:.2f}% R10={avg10:.2f}% R20={avg20:.2f}%")
    print(f"  Sharpe5={sh5:.3f} P10={p10_5:.2f}% P90={p90_5:.2f}%")
    print(f"  {'✅' if passed else '❌'} 达标: WR55={'✅' if details['wr55'] else '❌'} R5={'✅' if details['r5'] else '❌'} N200={'✅' if details['n200'] else '❌'}")
    
    return {
        "cid": cid, "name": name, "desc": desc,
        "signals": len(valid), "n5": len(r5l), "n10": len(r10l), "n20": len(r20l),
        "wr5": round(wr5,2), "wr10": round(wr10,2), "wr20": round(wr20,2),
        "r5": round(avg5,2), "r10": round(avg10,2), "r20": round(avg20,2),
        "sharpe5": round(sh5,3), "p10_5d": round(p10_5,2), "p90_5d": round(p90_5,2),
        "pass": passed, "pass_details": details
    }

# ============================================================
# COMBO 1: 深底均线金叉放量微盘
# ============================================================
# Use window function to compute MA5, MA10 and check golden cross
# SQL: bottom position check + MA5 > MA10 (golden cross) + VR + CM
sql_c1 = f"""  
SELECT ts_code, trade_date, close, pct_chg  
FROM (  
    SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close,  
        AVG(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5,  
        AVG(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma10  
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t  
    WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'  
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'  
      AND close > 0 AND pre_close > 0  
)  
WHERE trade_date >= '{START}' AND trade_date <= '{END}'  
  AND pct_chg >= 2  
  AND (high - low) / pre_close * 100 >= 5  
  AND ma5 > ma10  -- 金叉  
"""

# Join with daily_basic for VR and CM
sql_c1_full = f"""
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close, s.pct_chg AS pct_chg
FROM (
    {sql_c1}
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE b.volume_ratio >= 1.2 AND b.circ_mv <= 300000
"""

# ============================================================
# COMBO 2: 深底均线多头+概念热度+微盘
# ============================================================
# MA5 > MA10 > MA20 (多头排列) + 概念股(kpl) + 底部 + 放量
sql_c2_base = f"""  
SELECT ts_code, trade_date, close, pct_chg  
FROM (  
    SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close,  
        AVG(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5,  
        AVG(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma10,  
        AVG(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20  
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t  
    WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'  
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'  
      AND close > 0 AND pre_close > 0  
)  
WHERE trade_date >= '{START}' AND trade_date <= '{END}'  
  AND pct_chg >= 1  
  AND (high - low) / pre_close * 100 >= 3  
  AND ma5 > ma10 AND ma10 > ma20  -- 多头排列  
"""

sql_c2_full = f"""
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close, s.pct_chg AS pct_chg
FROM (
    {sql_c2_base}
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
INNER JOIN (
    SELECT DISTINCT con_code AS ts_code FROM tushare.tushare_kpl_concept_cons FINAL
) AS c ON s.ts_code = c.ts_code
WHERE b.volume_ratio >= 1.0 AND b.circ_mv <= 300000
"""

# ============================================================
# COMBO 3: 概念热点暴涨微盘 (KPL概念 + 深底 + 暴涨)
# ============================================================
sql_c3_base = f"""  
SELECT ts_code, trade_date, close, pct_chg  
FROM (  
    SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close  
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t  
    WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'  
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'  
      AND close > 0 AND pre_close > 0  
)  
WHERE trade_date >= '{START}' AND trade_date <= '{END}'  
  AND pct_chg >= 4  
  AND (high - low) / pre_close * 100 >= 7  
"""

sql_c3_full = f"""
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close, s.pct_chg AS pct_chg
FROM (
    {sql_c3_base}
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
INNER JOIN (
    SELECT DISTINCT con_code AS ts_code FROM tushare.tushare_kpl_concept_cons FINAL
) AS c ON s.ts_code = c.ts_code
WHERE b.volume_ratio >= 1.3 AND b.circ_mv <= 300000
"""

# ============================================================
# COMBO 4: 深底主力流入跳空微盘
# ============================================================
# gap up (open > pre_close * 1.01 即跳空1%以上) + net_mf > 0
sql_c4_full = f"""  
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close, s.pct_chg AS pct_chg  
FROM (  
    SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close, open  
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t  
    WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'  
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'  
      AND close > 0 AND pre_close > 0  
      AND trade_date >= '{START}' AND trade_date <= '{END}'  
      AND open / pre_close > 1.01  -- 向上跳空>1%  
      AND (high - low) / pre_close * 100 >= 5  
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
INNER JOIN (
    SELECT ts_code, trade_date, net_mf_amount
    FROM tushare.tushare_moneyflow FINAL
) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
WHERE b.volume_ratio >= 1.2 AND b.circ_mv <= 500000
  AND m.net_mf_amount > 0
"""

# ============================================================
# COMBO 5: 深底持续放量爆发微盘
# ============================================================
# pct_chg >= 3 + amplitude >= 6 + VR >= 1.5 + CM <= 30亿 + TR >= 0.5%
sql_c5_full = f"""  
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close, s.pct_chg AS pct_chg  
FROM (  
    SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close  
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t  
    WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'  
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'  
      AND close > 0 AND pre_close > 0  
      AND trade_date >= '{START}' AND trade_date <= '{END}'  
      AND pct_chg >= 3  
      AND (high - low) / pre_close * 100 >= 6  
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv, turnover_rate
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE b.volume_ratio >= 1.5 AND b.circ_mv <= 300000
  AND b.turnover_rate >= 0.005
"""

# Run all 5
combos = [
    ("C1", "深底金叉放量微盘", "底20% + MA5>MA10金叉 + 涨≥2% + 振幅≥5% + VR≥1.2 + CM≤30亿", sql_c1_full),
    ("C2", "多头排列概念微盘", "底20% + MA5>MA10>MA20多头 + KPL概念股 + 振幅≥3% + VR≥1.0 + CM≤30亿", sql_c2_full),
    ("C3", "概念热点暴涨微盘", "底20% + KPL概念股 + 涨≥4% + 振幅≥7% + VR≥1.3 + CM≤30亿", sql_c3_full),
    ("C4", "深底跳空主力流入", "底20% + 向上跳空>1% + 振幅≥5% + VR≥1.2 + 主力净流入>0 + CM≤50亿", sql_c4_full),
    ("C5", "深底放量爆发微盘", "底20% + 涨≥3% + 振幅≥6% + VR≥1.5 + 换手≥0.5% + CM≤30亿", sql_c5_full),
]

results = {}
for cid, name, desc, sql in combos:
    res = run_combo(cid, name, desc, sql)
    results[cid] = res

print("\n\n" + "="*60)
print("最终结果汇总")
print("="*60)
for cid, res in sorted(results.items()):
    if "error" in res:
        print(f"  ❌ {cid}: {res.get('name','')} — {res['error']}")
        continue
    status = "✅" if res["pass"] else "❌"
    print(f"  {status} {cid} {res['name']}: N={res['signals']} WR5={res['wr5']}% R5={res['r5']}% Sharpe={res['sharpe5']}")

# Save
output = {
    "timestamp": datetime.now().isoformat(),
    "combos": {k: {kk:vv for kk,vv in v.items() if kk not in ('name','desc','cid')} for k,v in results.items()},
    "pass_count": sum(1 for v in results.values() if v.get("pass")),
    "total_count": len(combos),
}
with open("/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_18/t6_raw_results.json", "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\n结果已保存到 t6_raw_results.json")
