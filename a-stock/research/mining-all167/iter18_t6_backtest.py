#!/usr/bin/env python3
"""Iter18 T6 板块轮动 (Sector Rotation) - 5组合并行回测"""
import json, subprocess, sys, math, os
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START = '2020-01-01'
END = '2026-05-12'

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
        if isinstance(data, list): return data
        if isinstance(data, dict): return data.get("data", [])
        return []
    except:
        return []

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
    idx = max(0, int(len(sr)*0.1)-1)
    return sr[idx]

# Load basic data
print("="*60)
print(f"Iter18 T6 板块轮动回测 | {START} ~ {END}")
print("="*60)

# Cache daily data for signal stocks
# We'll use a 2-step approach: get signal codes first, then fetch their full history

# Step 1: Load concept membership from kpl_concept_cons
print("\n[LOAD] 概念成分股...")
conc_rows = ch_query("SELECT DISTINCT con_code FROM tushare.tushare_kpl_concept_cons FINAL")
concept_codes = set(r["con_code"] for r in conc_rows if r.get("con_code"))
print(f"  概念股: {len(concept_codes)} 只")

# Step 2: Define 5 combos
combos = []

# C1: 深底均线支撑微盘 (Bottom + MA20 Support + Micro Cap)
combos.append({
    "id": "C1",
    "name": "深底均线支撑微盘",
    "desc": "底20% + 站上MA20 + 涨≥2% + 振幅≥5% + VR≥1.2 + CM≤30亿",
    "sql": f"""
SELECT s.ts_code, s.trade_date, s.close, s.pct_chg
FROM (
    SELECT ts_code, trade_date, close, high, low, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START}' AND trade_date <= '{END}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
      AND close > 0 AND pre_close > 0
      AND pct_chg >= 2
      AND (high - low) / pre_close * 100 >= 5
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE b.volume_ratio >= 1.2 AND b.circ_mv <= 300000
"""
})

# C2: 概念热点深底放量 (KPL Concept Hot + Bottom Volume)
combos.append({
    "id": "C2",
    "name": "概念热点深底放量",
    "desc": "概念股 + 底20% + 涨≥3% + 振幅≥5% + VR≥1.2 + CM≤30亿",
    "sql": f"""
SELECT s.ts_code, s.trade_date, s.close, s.pct_chg
FROM (
    SELECT ts_code, trade_date, close, high, low, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START}' AND trade_date <= '{END}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
      AND close > 0 AND pre_close > 0
      AND pct_chg >= 3
      AND (high - low) / pre_close * 100 >= 5
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE b.volume_ratio >= 1.2 AND b.circ_mv <= 300000
"""
})

# C3: 深底暴涨大盘 (Bottom + Big Gain + Large Cap)
combos.append({
    "id": "C3",
    "name": "深底暴涨大盘",
    "desc": "底20% + 涨≥5% + 振幅≥7% + VR≥1.5 + CM100-500亿",
    "sql": f"""
SELECT s.ts_code, s.trade_date, s.close, s.pct_chg
FROM (
    SELECT ts_code, trade_date, close, high, low, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START}' AND trade_date <= '{END}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
      AND close > 0 AND pre_close > 0
      AND pct_chg >= 5
      AND (high - low) / pre_close * 100 >= 7
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE b.volume_ratio >= 1.5 AND b.circ_mv >= 1000000 AND b.circ_mv <= 5000000
"""
})

# C4: 均线多头深底微盘 (MA Bullish + Bottom + Micro Cap)
combos.append({
    "id": "C4",
    "name": "均线多头深底微盘",
    "desc": "底20% + MA多头排列 + 涨≥1% + 振幅≥3% + VR≥1.0 + CM≤50亿",
    "sql": f"""
SELECT s.ts_code, s.trade_date, s.close, s.pct_chg
FROM (
    SELECT ts_code, trade_date, close, high, low, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START}' AND trade_date <= '{END}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
      AND close > 0 AND pre_close > 0
      AND pct_chg >= 1
      AND (high - low) / pre_close * 100 >= 3
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE b.volume_ratio >= 1.0 AND b.circ_mv <= 500000
"""
})

# C5: 主力流入中盘放量 (Fund Flow + Mid Cap + Volume)
combos.append({
    "id": "C5",
    "name": "主力流入中盘放量",
    "desc": "底20% + 振幅≥5% + VR≥1.2 + 主力净流入>0 + CM30-100亿 + 特大单买入>0",
    "sql": f"""
SELECT s.ts_code, s.trade_date, s.close, s.pct_chg
FROM (
    SELECT ts_code, trade_date, close, high, low, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START}' AND trade_date <= '{END}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
      AND close > 0 AND pre_close > 0
      AND (high - low) / pre_close * 100 >= 5
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
INNER JOIN (
    SELECT ts_code, trade_date, net_mf_amount, buy_elg_amount
    FROM tushare.tushare_moneyflow FINAL
) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
WHERE b.volume_ratio >= 1.2
  AND b.circ_mv >= 300000 AND b.circ_mv <= 1000000
  AND m.net_mf_amount > 0
  AND m.buy_elg_amount > 0
"""
})

# Step 3: Run each combo
all_results = {}
for combo in combos:
    cid = combo["id"]
    print(f"\n{'='*60}")
    print(f"[{cid}] {combo['name']}: {combo['desc']}")
    print(f"{'='*60}")

    rows = ch_query(combo["sql"])
    if not rows:
        print(f"  ❌ 查询返回空或错误")
        all_results[cid] = {"signals": 0, "error": "empty"}
        continue

    print(f"  ✅ 原始信号: {len(rows)}")

    # Build (code, date) lookup for dedup
    signal_map = {}
    for r in rows:
        code = r["ts_code"]
        dt = str(r["trade_date"]).replace("-", "")
        key = (code, dt)
        if key not in signal_map:
            signal_map[key] = {"close": r["close"], "pct_chg": r["pct_chg"]}

    print(f"  ✅ 唯一信号: {len(signal_map)}")

    # Step 4: 底20% position filtering in Python (since ClickHouse complex subquery is tricky)
    # For each signal stock, get last 20 days, compute bottom 20% threshold
    # We'll batch query by stock

    # Get all unique stock codes
    codes = list(set(k[0] for k in signal_map.keys()))
    signal_items = list(signal_map.items())

    # For each signal, we need to check if close is in bottom 20% of last 20 days
    # Batch: fetch close data for all signal stocks
    batch_size = 200
    stock_data = {}
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        q = f"""
        SELECT ts_code, trade_date, close
        FROM tushare.tushare_stock_daily FINAL
        WHERE ts_code IN ({codes_str})
          AND trade_date >= '{START}' AND trade_date <= '{END}'
        ORDER BY ts_code, trade_date
        """
        rows2 = ch_query(q)
        for r in rows2:
            code = r["ts_code"]
            dt = str(r["trade_date"]).replace("-", "")
            if code not in stock_data:
                stock_data[code] = []
            stock_data[code].append((dt, r["close"]))

        if (i // batch_size) % 2 == 0:
            print(f"  [进度] 加载数据: {min(i+batch_size, len(codes))}/{len(codes)}")

    print(f"  [进度] 数据加载完成: {sum(len(v) for v in stock_data.values())} 行")

    # Step 5: Filter and compute forward returns
    # For each signal, compute bottom20 check and forward returns
    valid_signals = []
    forward_rets_5d = []
    forward_rets_10d = []
    forward_rets_20d = []

    for (code, dt), sig in signal_items:
        bars = stock_data.get(code, [])
        if len(bars) < 20:
            continue

        # Find index of signal date
        idx = None
        for j, (bd, _) in enumerate(bars):
            if bd == dt:
                idx = j
                break
        if idx is None or idx < 20:
            continue

        # Bottom 20% check: last 20 days (including signal day)
        window = bars[idx-19:idx+1]
        window_closes = [w[1] for w in window]
        # Also check today's close is < 20% percentile of the 20-day range
        # Using max/min approach: close_position = (close - min20) / (max20 - min20)
        min20 = min(window_closes)
        max20 = max(window_closes)
        if max20 == min20:
            continue  # flat line, skip
        
        close_pos = (sig["close"] - min20) / (max20 - min20)
        if close_pos >= 0.20:
            continue  # not in bottom 20%
        
        valid_signals.append((code, dt))

        # Forward returns
        future = bars[idx:]
        # 5 trading days later
        idx5 = min(5, len(future)-1)
        idx10 = min(10, len(future)-1)
        idx20 = min(20, len(future)-1)
        
        r5 = (future[idx5][1] / sig["close"] - 1) * 100 if len(future) > 5 else None
        r10 = (future[idx10][1] / sig["close"] - 1) * 100 if len(future) > 10 else None
        r20 = (future[idx20][1] / sig["close"] - 1) * 100 if len(future) > 20 else None
        
        if r5 is not None:
            forward_rets_5d.append(r5)
            if r10 is not None:
                forward_rets_10d.append(r10)
            if r20 is not None:
                forward_rets_20d.append(r20)

    print(f"  ✅ 底20%过滤后: {len(valid_signals)} 信号")
    print(f"  ✅ 有5D收益: {len(forward_rets_5d)}")

    if len(forward_rets_5d) < 50:
        print(f"  ⚠️ 信号不足({len(forward_rets_5d)}<50), 跳过统计")
        all_results[cid] = {"signals": len(valid_signals), "n5": len(forward_rets_5d), "error": "too_few"}
        continue

    wr5 = sum(1 for r in forward_rets_5d if r > 0) / len(forward_rets_5d) * 100
    wr10 = sum(1 for r in forward_rets_10d if r > 0) / len(forward_rets_10d) * 100 if forward_rets_10d else 0
    wr20 = sum(1 for r in forward_rets_20d if r > 0) / len(forward_rets_20d) * 100 if forward_rets_20d else 0

    avg5 = sum(forward_rets_5d) / len(forward_rets_5d)
    avg10 = sum(forward_rets_10d) / len(forward_rets_10d) if forward_rets_10d else 0
    avg20 = sum(forward_rets_20d) / len(forward_rets_20d) if forward_rets_20d else 0

    sh5 = sharpe(forward_rets_5d)
    p10_5 = p10(forward_rets_5d)

    # Also compute C1 without bottom20 for comparison
    # (optional)

    result = {
        "signals_raw": len(rows),
        "signals_unique": len(signal_map),
        "signals_after_bottom": len(valid_signals),
        "n5": len(forward_rets_5d),
        "n10": len(forward_rets_10d),
        "n20": len(forward_rets_20d),
        "wr5": round(wr5, 2),
        "wr10": round(wr10, 2),
        "wr20": round(wr20, 2),
        "r5": round(avg5, 2),
        "r10": round(avg10, 2),
        "r20": round(avg20, 2),
        "sharpe5": round(sh5, 3),
        "p10_5d": round(p10_5, 2),
        "pass": wr5 >= 55 and avg5 >= 5 and len(forward_rets_5d) >= 200,
    }

    result["pass_wr"] = wr5 >= 55
    result["pass_r5"] = avg5 >= 5
    result["pass_n"] = len(forward_rets_5d) >= 200

    all_results[cid] = result

    print(f"\n  {'✅' if result['pass'] else '❌'} 达标: {'是' if result['pass'] else '否'}")
    print(f"  信号数: {result['signals_after_bottom']}")
    print(f"  5D胜率: {result['wr5']}%")
    print(f"  5D收益: {result['r5']}%")
    print(f"  10D收益: {result['r10']}%")
    print(f"  20D收益: {result['r20']}%")
    print(f"  Sharpe5: {result['sharpe5']}")
    print(f"  P10: {result['p10_5d']}%")

# Step 6: Summary
print("\n\n" + "="*60)
print("最终结果汇总")
print("="*60)
for cid, res in sorted(all_results.items()):
    status = "✅" if res.get("pass") else ("⚠️" if res.get("signals_after_bottom", 0) >= 50 else "❌")
    print(f"  {status} {cid}: N={res.get('signals_after_bottom',0)} WR5={res.get('wr5','N/A')}% R5={res.get('r5','N/A')}% Sharpe={res.get('sharpe5','N/A')}")

# Save results
output = {
    "timestamp": datetime.now().isoformat(),
    "combos": all_results,
    "pass_count": sum(1 for v in all_results.values() if v.get("pass")),
    "total_count": len(combos),
}
with open("/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_18/t6_raw_results.json", "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n结果已保存到 t6_raw_results.json")
