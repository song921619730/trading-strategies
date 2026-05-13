#!/usr/bin/env python3
"""
Round 17 Backtest — long_001b: 跳空高开1.5-3% + 微盘股(circ_mv<20亿) → 持有做多
"""
import json, math, subprocess, sys

CH = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def q(sql):
    r = subprocess.run(["python3", CH, "sql", sql], capture_output=True, text=True, timeout=180)
    idx = r.stdout.find('[')
    if idx >= 0: return json.loads(r.stdout[idx:])
    print(f"ERR: {r.stderr[:300]}", file=sys.stderr); return []

def ci95(n, wr):
    if n==0: return (0,0)
    z=1.96; p=wr; d=1+z*z/n; c=p+z*z/(2*n); m=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return (max(0,(c-m)/d), min(1,(c+m)/d))

def stats(sigs, ek, lb):
    r=[(s.get(ek)-s["ec"])/s["ec"] for s in sigs if s.get(ek) and s.get(ek)>0 and s["ec"]>0]
    n=len(r)
    if n==0: return {"h":lb,"n":0}
    w=sum(1 for x in r if x>0); wr=w/n; ar=sum(r)/n; cl,cu=ci95(n,wr)
    aw=sum(x for x in r if x>0)/w if w>0 else 0
    al=sum(x for x in r if x<0)/(n-w) if n-w>0 else 0
    pf=abs(aw/al) if al!=0 else float('inf')
    return {"h":lb,"n":n,"wr":round(wr*100,2),"ar":round(ar*100,4),"cl":round(cl*100,2),"cu":round(cu*100,2),"pf":round(pf,2)}

def run(label, cond, sd="2020-01-02", ed="2026-05-12", nh=5):
    print(f"[{label}]")
    sql=f"""
    SELECT ts_code, trade_date, close AS ec,
           any(close) OVER w1 AS exit_1d,
           any(close) OVER w3 AS exit_3d,
           any(close) OVER w5 AS exit_5d,
           any(close) OVER w10 AS exit_10d,
           any(close) OVER w20 AS exit_20d
    FROM (
        SELECT ts_code, trade_date, open, pre_close, close
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '{sd}' AND trade_date <= '{ed}'
    )
    WHERE {cond}
      AND close > 0
      AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '920%'
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
      AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('{ed}', INTERVAL 1 YEAR))
    WINDOW w1 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING),
           w3 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 3 FOLLOWING AND 3 FOLLOWING),
           w5 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING),
           w10 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING),
           w20 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING)
    ORDER BY ts_code, trade_date
    """
    sigs = q(sql)
    print(f"  Signals: {len(sigs)}")
    if not sigs: return None
    for ek,lb in [("exit_1d",1),("exit_3d",3),("exit_5d",5),("exit_10d",10),("exit_20d",20)][:nh]:
        s=stats(sigs,ek,lb)
        if s["n"]>0: print(f"  h{lb:>2}: n={s['n']:>8}  WR={s['wr']:>5.2f}%  avg={s['ar']:+.4f}%  CI=[{s['cl']:.2f},{s['cu']:.2f}]  PF={s['pf']:.2f}")
    return sigs

print("="*70)
print("Round 17 — long_001b 回测: 跳空高开1.5-3% + 微盘股")
print("="*70)

# 1. 全市场2024+
print("\n"+"─"*40)
print("1. 全市场 跳空1.5-3% (2024+ 验证)")
print("─"*40)
run("全市场2024+", "open / pre_close BETWEEN 1.015 AND 1.03", sd="2024-01-01", ed="2026-05-12")

# 2. 全市场2020-2026
print("\n"+"─"*40)
print("2. 全市场 跳空1.5-3% (2020-2026)")
print("─"*40)
run("全市场2020-2026", "open / pre_close BETWEEN 1.015 AND 1.03", nh=2)

# 3. 两步法测试微盘
print("\n"+"─"*40)
print("3. 跳空1.5-3% + 各市值门槛 (2024+)")
print("─"*40)
sql_g=f"""
SELECT ts_code, trade_date, close AS ec,
       any(close) OVER w1 AS exit_1d,
       any(close) OVER w5 AS exit_5d
FROM (
    SELECT ts_code, trade_date, open, pre_close, close
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2024-01-01' AND trade_date <= '2026-05-12'
)
WHERE open / pre_close BETWEEN 1.015 AND 1.03
  AND close > 0
  AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '920%'
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-12', INTERVAL 1 YEAR))
WINDOW w1 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING),
       w5 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING)
ORDER BY ts_code, trade_date
"""
print("  Fetching all gap-up signals (2024+)...")
gs = q(sql_g)
print(f"  Got {len(gs)} signals")

if gs:
    print("  Fetching circ_mv...")
    dg = {}
    for s in gs: dg.setdefault(s["trade_date"], set()).add(s["ts_code"])
    cm = {}
    for d in sorted(dg.keys()):
        codes = list(dg[d])
        for i in range(0, len(codes), 5000):
            b = codes[i:i+5000]
            cs = ", ".join(f"'{c}'" for c in b)
            rows = q(f"SELECT ts_code, circ_mv FROM tushare.tushare_daily_basic FINAL WHERE trade_date = '{d}' AND ts_code IN ({cs})")
            for r in rows: cm[(r["ts_code"], d)] = r["circ_mv"]
    print(f"  Got {len(cm)} values")
    
    tests = [
        ("circ_mv < 10亿", lambda v: v is not None and v < 100000),
        ("circ_mv < 20亿 (long_001b)", lambda v: v is not None and v < 200000),
        ("circ_mv < 30亿", lambda v: v is not None and v < 300000),
        ("circ_mv < 50亿", lambda v: v is not None and v < 500000),
        ("circ_mv < 100亿", lambda v: v is not None and v < 1000000),
        ("circ_mv >= 100亿", lambda v: v is not None and v >= 1000000),
        ("circ_mv >= 200亿", lambda v: v is not None and v >= 2000000),
    ]
    for lb, flt in tests:
        fd = [s for s in gs if flt(cm.get((s["ts_code"], s["trade_date"]), None))]
        if fd:
            s1 = stats(fd, "exit_1d", 1)
            s5 = stats(fd, "exit_5d", 5)
            print(f"  [{lb:25s}] n={s1['n']:>6}  H1 WR={s1['wr']:.2f}%  avg={s1['ar']:+.4f}%  CI_l={s1['cl']:.2f}%  PF={s1['pf']:.2f}  | H5 WR={s5['wr']:.2f}%  avg={s5['ar']:+.4f}%")
        else:
            print(f"  [{lb:25s}] 无信号")

print("\n"+"="*70)
print("DONE")
