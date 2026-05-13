
import json, subprocess, sys, math
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START = '2020-01-01'
END = '2026-05-12'

def ch_query(sql):
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

# C5: 主力流入中盘放量 (with fixed column aliases)
print("C5: 主力流入中盘放量")
sql = f"""
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close, s.pct_chg AS pct_chg
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
rows = ch_query(sql)
print(f"原始信号: {len(rows)}")

# Dedup
signal_map = {}
for r in rows:
    code = r["ts_code"]
    dt = str(r["trade_date"]).replace("-", "")
    signal_map[(code, dt)] = {"close": r["close"], "pct_chg": r["pct_chg"]}

print(f"唯一信号: {len(signal_map)}")

# Load daily data for these codes
codes = list(set(k[0] for k in signal_map.keys()))
print(f"唯一个股: {len(codes)}")

stock_data = {}
for i in range(0, len(codes), 200):
    batch = codes[i:i+200]
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
        if code not in stock_data: stock_data[code] = []
        stock_data[code].append((dt, r["close"]))

print(f"数据加载: {sum(len(v) for v in stock_data.values())} 行")

# Filter bottom20% + forward returns
valid = []
r5_list, r10_list, r20_list = [], [], []

for (code, dt), sig in signal_map.items():
    bars = stock_data.get(code, [])
    if len(bars) < 20: continue
    idx = None
    for j, (bd, _) in enumerate(bars):
        if bd == dt: idx = j; break
    if idx is None or idx < 20: continue
    
    window = bars[idx-19:idx+1]
    wc = [w[1] for w in window]
    mn, mx = min(wc), max(wc)
    if mx == mn: continue
    
    pos = (sig["close"] - mn) / (mx - mn)
    if pos >= 0.20: continue
    
    valid.append((code, dt))
    future = bars[idx:]
    
    if len(future) > 5:
        r5 = (future[5][1]/sig["close"]-1)*100
        r5_list.append(r5)
    if len(future) > 10:
        r10 = (future[10][1]/sig["close"]-1)*100
        r10_list.append(r10)
    if len(future) > 20:
        r20 = (future[20][1]/sig["close"]-1)*100
        r20_list.append(r20)

print(f"底20%过滤后: {len(valid)}")
print(f"5D收益数: {len(r5_list)}")

if len(r5_list) >= 50:
    wr5 = sum(1 for r in r5_list if r>0)/len(r5_list)*100
    wr10 = sum(1 for r in r10_list if r>0)/len(r10_list)*100 if r10_list else 0
    wr20 = sum(1 for r in r20_list if r>0)/len(r20_list)*100 if r20_list else 0
    avg5 = sum(r5_list)/len(r5_list)
    avg10 = sum(r10_list)/len(r10_list) if r10_list else 0
    avg20 = sum(r20_list)/len(r20_list) if r20_list else 0
    sh5 = sharpe(r5_list)
    p10_5 = p10(r5_list)
    
    print(f"WR5={wr5:.2f}% WR10={wr10:.2f}% WR20={wr20:.2f}%")
    print(f"R5={avg5:.2f}% R10={avg10:.2f}% R20={avg20:.2f}%")
    print(f"Sharpe5={sh5:.3f} P10={p10_5:.2f}%")
    
    passed = wr5 >= 55 and avg5 >= 5 and len(r5_list) >= 200
    print(f"达标: {'✅' if passed else '❌'}")
    print(f"WR达标: {wr5>=55}, R5达标: {avg5>=5}, N达标: {len(r5_list)>=200}")
else:
    print("信号不足")
