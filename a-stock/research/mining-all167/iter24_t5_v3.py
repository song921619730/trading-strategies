#!/usr/bin/env python3
"""
Iter24 T5 Backtest v3 — Pure value with SPX and capital flow
"""
import json, urllib.parse, urllib.request, sys

HOST, HTTP_PORT, USER, PASSWORD = "172.24.224.1", "8123", "ai_reader", "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_query(sql, db="tushare"):
    url = f"http://{HOST}:{HTTP_PORT}/?user={USER}&password={PASSWORD}&database={db}&default_format=JSONEachRow&query={urllib.parse.quote(sql)}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode("utf-8")
            if not body.strip(): return []
            return [json.loads(line) for line in body.strip().split("\n") if line.strip()]
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr); return []

def run_combo(name, sql):
    print(f"\n{'='*60}\n🔍 {name}\n{'='*60}")
    rows = ch_query(sql)
    if not rows: print("  ❌ 0 signals"); return None
    print(f"  ✅ {len(rows)} signals, stocks: {len(set(r['ts_code'] for r in rows))}")
    # Show some
    for r in rows[:2]: print(f"    {r['ts_code']} {r['trade_date']} close={r['close']}")
    
    # Get forward prices
    codes = list(set(r['ts_code'] for r in rows))
    prices = {}
    for i in range(0, len(codes), 500):
        cs = ", ".join(f"'{c}'" for c in codes[i:i+500])
        for r in ch_query(f"SELECT ts_code, trade_date, close FROM tushare.tushare_stock_daily FINAL WHERE ts_code IN ({cs}) AND trade_date >= toDate('2020-01-01')"):
            prices[(r['ts_code'], r['trade_date'])] = r['close']
    print(f"  📊 Loaded {len(prices)} price records")
    
    # Trade calendar
    cal = ch_query("SELECT cal_date FROM _meta.trade_cal WHERE exchange='SSE' AND is_open=1 AND cal_date>='2020-01-01' AND cal_date<='2026-06-30' ORDER BY cal_date", "_meta")
    dates = [r['cal_date'] for r in cal]
    d2i = {d:i for i,d in enumerate(dates)}
    
    ret5, ret10, ret20 = [], [], []
    for r in rows:
        t = d2i.get(r['trade_date'])
        if t is None: continue
        c0 = float(r['close'])
        for offset, rets in [(5, ret5), (10, ret10), (20, ret20)]:
            if t + offset < len(dates):
                c = prices.get((r['ts_code'], dates[t+offset]))
                if c and c > 0 and c0 > 0:
                    rets.append((float(c)-c0)/c0)
    
    def stats(rets):
        if len(rets) < 10: return None, None, None
        avg = sum(rets)/len(rets); wins = sum(1 for r in rets if r>0)/len(rets)*100
        if len(rets)>1:
            var = sum((r-avg)**2 for r in rets)/(len(rets)-1)
            sh = (avg/(var**0.5))*(252/5)**0.5 if var>0 else 0
        else: sh = 0
        return avg*100, wins, sh
    
    r5, w5, s5 = stats(ret5)
    r10, w10, _ = stats(ret10)
    r20, w20, _ = stats(ret20)
    print(f"  📈 T+5: N={len(ret5)}, R5={r5:.2f}%, WR={w5:.2f}%, Sharpe={s5:.3f}")
    print(f"  📈 T+10: N={len(ret10)}, R10={r10:.2f}%, WR={w10:.2f}%")
    print(f"  📈 T+20: N={len(ret20)}, R20={r20:.2f}%, WR={w20:.2f}%")
    return {"sig": len(rows), "r5": r5, "w5": w5, "s5": s5, "r10": r10, "w10": w10, "r20": r20, "w20": w20, "passed": (len(ret5)>=200 and w5 is not None and w5>=52 and r5 is not None and r5>=3.0)}

# COMBOS - Pure value focus, no fina_indicator growth filters
combos = []

# C1: PB≤1 + dv≥3% + CM≤30亿 + 底20% + VR≥1.2 (strict value without SPX)
combos.append(("C1: 破净高息微盘 — PB≤1+dv≥3%+底20%+VR≥1.2+CM≤30亿", """
WITH sig AS (
    SELECT s.ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pb, dv_ttm, circ_mv, volume_ratio FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code=d.ts_code AND s.trade_date=d.trade_date
    WHERE s.trade_date>=toDate('2020-01-01') AND s.trade_date<=toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND d.pb>0 AND d.pb<=1 AND d.dv_ttm>=3.0 AND d.circ_mv<=300000 AND d.volume_ratio>=1.2
), pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS mn,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS mx
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL WHERE trade_date>=toDate('2019-12-01'))
)
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close FROM sig s INNER JOIN pos p ON s.ts_code=p.ts_code AND s.trade_date=p.trade_date
WHERE p.mx>p.mn AND (s.close-p.mn)/(p.mx-p.mn)<=0.2
"""))

# C2: PB≤1 + dv≥2% + CM≤50亿 + 底20% + VR≥1.0 + SPX (replicate/follow Iter23 best pattern)
combos.append(("C2: 破净高息SPX — PB≤1+dv≥2%+底20%+VR≥1.0+CM≤50亿+SPX涨", """
WITH spx AS (SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX' AND trade_date>=toDate('2019-12-01')),
sig AS (
    SELECT s.ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pb, dv_ttm, circ_mv, volume_ratio FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code=d.ts_code AND s.trade_date=d.trade_date
    INNER JOIN spx ON s.trade_date=spx.trade_date
    WHERE s.trade_date>=toDate('2020-01-01') AND s.trade_date<=toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND d.pb>0 AND d.pb<=1 AND d.dv_ttm>=2.0 AND d.circ_mv<=500000 AND d.volume_ratio>=1.0 AND spx.pct_chg>0
), pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS mn,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS mx
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL WHERE trade_date>=toDate('2019-12-01'))
)
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close FROM sig s INNER JOIN pos p ON s.ts_code=p.ts_code AND s.trade_date=p.trade_date
WHERE p.mx>p.mn AND (s.close-p.mn)/(p.mx-p.mn)<=0.2
"""))

# C3: PB≤1 + dv≥2% + CM≤30亿 + 底20%(60d) + VR≥1.2 + SPX (deeper bottom position on 60d)
combos.append(("C3: 破净高息60日深底+SPX — PB≤1+dv≥2%+底20%(60d)+VR≥1.2+CM≤30亿+SPX涨", """
WITH spx AS (SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX' AND trade_date>=toDate('2019-12-01')),
sig AS (
    SELECT s.ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pb, dv_ttm, circ_mv, volume_ratio FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code=d.ts_code AND s.trade_date=d.trade_date
    INNER JOIN spx ON s.trade_date=spx.trade_date
    WHERE s.trade_date>=toDate('2020-01-01') AND s.trade_date<=toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND d.pb>0 AND d.pb<=1 AND d.dv_ttm>=2.0 AND d.circ_mv<=300000 AND d.volume_ratio>=1.2 AND spx.pct_chg>0
), pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS mn,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS mx
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL WHERE trade_date>=toDate('2019-10-01'))
)
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close FROM sig s INNER JOIN pos p ON s.ts_code=p.ts_code AND s.trade_date=p.trade_date
WHERE p.mx>p.mn AND (s.close-p.mn)/(p.mx-p.mn)<=0.2
"""))

# C4: PB≤1 + dv≥2% + CM≤100亿 + 底20% + VR≥1.0 + SPX + buy_lg>sell_lg (value + LG flow)
combos.append(("C4: 破净高息大单流入+SPX — PB≤1+dv≥2%+底20%+VR≥1.0+CM≤100亿+SPX涨+buy_lg>sell_lg", """
WITH spx AS (SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX' AND trade_date>=toDate('2019-12-01')),
sig AS (
    SELECT s.ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pb, dv_ttm, circ_mv, volume_ratio FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code=d.ts_code AND s.trade_date=d.trade_date
    INNER JOIN spx ON s.trade_date=spx.trade_date
    INNER JOIN (SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol FROM tushare.tushare_moneyflow FINAL) m
        ON s.ts_code=m.ts_code AND s.trade_date=m.trade_date
    WHERE s.trade_date>=toDate('2020-01-01') AND s.trade_date<=toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND d.pb>0 AND d.pb<=1 AND d.dv_ttm>=2.0 AND d.circ_mv<=1000000 AND d.volume_ratio>=1.0 AND spx.pct_chg>0
      AND m.buy_lg_vol > m.sell_lg_vol
), pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS mn,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS mx
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL WHERE trade_date>=toDate('2019-12-01'))
)
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close FROM sig s INNER JOIN pos p ON s.ts_code=p.ts_code AND s.trade_date=p.trade_date
WHERE p.mx>p.mn AND (s.close-p.mn)/(p.mx-p.mn)<=0.2
"""))

# C5: PE≤15 + PB≤1.5 + dv≥2% + CM≤50亿 + 底20% + VR≥1.2 + SPX + sell_sm>buy_sm + buy_lg>sell_lg
# value + dual money flow + SPX
combos.append(("C5: 深价值双资金流+SPX — PE≤15+PB≤1.5+dv≥2%+底20%+VR≥1.2+CM≤50亿+SPX涨+sell_sm>buy_sm+buy_lg>sell_lg", """
WITH spx AS (SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX' AND trade_date>=toDate('2019-12-01')),
sig AS (
    SELECT s.ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pe, pb, dv_ttm, circ_mv, volume_ratio FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code=d.ts_code AND s.trade_date=d.trade_date
    INNER JOIN spx ON s.trade_date=spx.trade_date
    INNER JOIN (SELECT ts_code, trade_date, buy_sm_vol, sell_sm_vol, buy_lg_vol, sell_lg_vol FROM tushare.tushare_moneyflow FINAL) m
        ON s.ts_code=m.ts_code AND s.trade_date=m.trade_date
    WHERE s.trade_date>=toDate('2020-01-01') AND s.trade_date<=toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND d.pe>0 AND d.pe<=15 AND d.pb>0 AND d.pb<=1.5 AND d.dv_ttm>=2.0 AND d.circ_mv<=500000 AND d.volume_ratio>=1.2
      AND spx.pct_chg>0 AND m.sell_sm_vol>m.buy_sm_vol AND m.buy_lg_vol>m.sell_lg_vol
), pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS mn,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS mx
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL WHERE trade_date>=toDate('2019-12-01'))
)
SELECT s.ts_code AS ts_code, s.trade_date AS trade_date, s.close AS close FROM sig s INNER JOIN pos p ON s.ts_code=p.ts_code AND s.trade_date=p.trade_date
WHERE p.mx>p.mn AND (s.close-p.mn)/(p.mx-p.mn)<=0.2
"""))

# Run
results = []
for name, sql in combos:
    r = run_combo(name, sql)
    if r: results.append((name, r))

# Print summary
print(f"\n\n{'='*60}\n📊 SUMMARY\n{'='*60}")
print(f"{'Combo':<50} {'N':>6} {'WR':>7} {'R5':>7} {'R10':>7} {'R20':>7} {'Sharpe':>8} {'Status':>8}")
print("-"*100)
passed_any = False
for name, r in results:
    st = "✅ PASS" if r['passed'] else "❌ FAIL"
    if r['passed']: passed_any = True
    print(f"{name[:48]:<50} {r['sig']:>6} {r['w5']:>6.1f}% {r['r5']:>6.2f}% {r['r10']:>6.2f}% {r['r20']:>6.2f}% {r['s5']:>7.3f} {st:>8}")

# Write report
lines = ["# Iter24 T5: 基本面估值分析\n", "**系统执行时间**: 2026-05-13 17:55 UTC+8\n", "**迭代编号**: 24\n", "**数据基准日期**: 2026-05-12\n", "---\n",
    "## 参数组合测试结果\n",
    "| 组合 | 信号数 | 胜率(WR) | 5D收益 | 10D收益 | 20D收益 | Sharpe | 状态 |",
    "|------|--------|---------|--------|---------|---------|--------|------|"]
for name, r in results:
    st = "✅ PASS" if r['passed'] else "❌ FAIL"
    sn = name.split("—")[0].strip()[:20]
    lines.append(f"| {sn} | {r['sig']} | {r['w5']:.2f}% | {r['r5']:.2f}% | {r['r10']:.2f}% | {r['r20']:.2f}% | {r['s5']:.3f} | {st} |")

lines.append("\n## 成功标准\n- WR >= 52% AND 5D收益 >= 3% AND 信号数 >= 200\n")

if passed_any:
    best = max(results, key=lambda x: x[1]['r5'])
    lines.append(f"---\n## 🏆 最佳发现\n**{best[0]}**\n")
    lines.append(f"- **信号数**: {best[1]['sig']}\n- **WR**: {best[1]['w5']:.2f}%\n- **R5**: {best[1]['r5']:.2f}%\n- **R10**: {best[1]['r10']:.2f}%\n- **R20**: {best[1]['r20']:.2f}%\n- **Sharpe**: {best[1]['s5']:.3f}\n")
    if best[1]['w5'] > 79.43:
        lines.append(f"- 🏆 **新T5流派WR纪录!** {best[1]['w5']:.2f}% > 79.43%\n")
    elif best[1]['r5'] > 7.97:
        lines.append(f"- 🏆 **新T5流派R5纪录!** {best[1]['r5']:.2f}% > 7.97%\n")
    else:
        lines.append(f"- 📊 未超越T5流派最佳(WR=79.43%, R5=7.97%, N=319, Iter23 T5-C1)\n")
else:
    lines.append("## ❌ 本轮无组合通过成功标准\n")
    # Show nearest
    best = max(results, key=lambda x: x[1]['w5'] if x[1]['w5'] else 0)
    lines.append(f"### 最接近达标\n**{best[0]}** — WR={best[1]['w5']:.2f}%, R5={best[1]['r5']:.2f}%, N={best[1]['sig']}\n")

lines.append("\n---\n## 关键SQL查询（可复现）\n")
lines.append("### C2 (最佳复现基准): 破净高息SPX\n```sql\n")
for name, sql in combos:
    if "C2:" in name:
        lines.append(sql)
        break
lines.append("```\n### 备注\n- 所有查询用全量历史数据 (2020-01-01 ~ 2026-05-12)\n- 主板过滤: NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'\n- circ_mv单位: 万元\n- 底部位置 via 20日/60日滑动窗口 MIN/MAX\n")

path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_24/analysis_T5_基本面估值.md"
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\n📄 Report: {path}")

if passed_any:
    b = best[1]
    print(f"\nBEST|{best[0]}|WR={b['w5']:.2f}|R5={b['r5']:.2f}|N={b['sig']}|Sharpe={b['s5']:.3f}")
else:
    print("\nNO_PASS")
    # Still output nearest
    b = max(results, key=lambda x: x[1]['w5'] if x[1]['w5'] else 0)[1]
    print(f"NEAREST|WR={b['w5']:.2f}|R5={b['r5']:.2f}|N={b['sig']}")
