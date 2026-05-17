#!/usr/bin/env python3
"""
Iter24 T5 Backtest — 基本面估值流 5 组参数组合回测 (v2)
"""
import json
import urllib.parse
import urllib.request
import sys
from collections import defaultdict

HOST = "172.24.224.1"
HTTP_PORT = "8123"
USER = "ai_reader"
PASSWORD = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_query(sql: str, database: str = "tushare") -> list[dict]:
    url = f"http://{HOST}:{HTTP_PORT}/"
    params = {
        "user": USER,
        "password": PASSWORD,
        "database": database,
        "query": sql,
        "default_format": "JSONEachRow",
    }
    qs = urllib.parse.urlencode(params)
    full_url = f"{url}?{qs}"
    try:
        req = urllib.request.Request(full_url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            if not body.strip():
                return []
            return [json.loads(line) for line in body.strip().split("\n") if line.strip()]
    except Exception as e:
        print(f"❌ Query error: {e}", file=sys.stderr)
        return []

def detect_signals(sql_desc: str, signal_sql: str) -> list[dict]:
    print(f"\n{'='*60}")
    print(f"🔍 {sql_desc}")
    print(f"{'='*60}")
    rows = ch_query(signal_sql)
    if not rows:
        print("  ❌ No signals found!")
        return []
    print(f"  ✅ Total signals: {len(rows)}")
    # Show first 3
    for r in rows[:3]:
        print(f"    {r}")
    return rows

def compute_forward_returns(signals: list[dict]) -> dict:
    if not signals:
        return {"signal_count": 0, "ret_5d": None, "ret_10d": None, "ret_20d": None,
                "win_rate_5d": None, "win_rate_10d": None, "win_rate_20d": None,
                "sharpe_5d": None}
    
    # Determine key names (some combos use 'ts_code' others use 's.ts_code' depending on SQL)
    key_map = {}
    for k in signals[0].keys():
        if 'ts_code' in k:
            key_map['ts_code'] = k
        if 'trade_date' in k:
            key_map['trade_date'] = k
        if k == 'close' or 'close' in k:
            key_map['close'] = k
    
    print(f"  📊 Key mapping: {key_map}")
    
    stock_codes = list(set(s[key_map['ts_code']] for s in signals))
    print(f"  📊 Unique stocks: {len(stock_codes)}")
    
    # Get all trade dates for these stocks
    chunk_size = 500
    all_prices = {}
    
    for i in range(0, len(stock_codes), chunk_size):
        chunk = stock_codes[i:i+chunk_size]
        codes_str = ", ".join(f"'{c}'" for c in chunk)
        sql = f"""
            SELECT ts_code, trade_date, close
            FROM tushare.tushare_stock_daily FINAL
            WHERE ts_code IN ({codes_str})
              AND trade_date >= toDate('2020-01-01')
            ORDER BY ts_code, trade_date
        """
        rows = ch_query(sql)
        for r in rows:
            all_prices[(r["ts_code"], r["trade_date"])] = r["close"]
    
    print(f"  📊 Total price records loaded: {len(all_prices)}")
    
    # Get trade calendar
    cal_sql = """
        SELECT cal_date FROM _meta.trade_cal
        WHERE exchange = 'SSE' AND is_open = 1
          AND cal_date >= '2020-01-01' AND cal_date <= '2026-06-30'
        ORDER BY cal_date
    """
    cal_rows = ch_query(cal_sql, database="_meta")
    trade_dates = [r["cal_date"] for r in cal_rows]
    date_to_idx = {d: i for i, d in enumerate(trade_dates)}
    
    print(f"  📅 Trade days in range: {len(trade_dates)}")
    
    rets_5d, rets_10d, rets_20d = [], [], []
    hit_5d, hit_10d, hit_20d = 0, 0, 0
    missed_5d, missed_10d, missed_20d = 0, 0, 0
    
    for sig in signals:
        ts_code = sig[key_map['ts_code']]
        t_date = sig[key_map['trade_date']]
        close_t = float(sig[key_map['close']])
        
        t_idx = date_to_idx.get(t_date)
        if t_idx is None:
            continue
        
        if t_idx + 5 < len(trade_dates):
            d5 = trade_dates[t_idx + 5]
            c5 = all_prices.get((ts_code, d5))
            if c5 and c5 > 0 and close_t > 0:
                r5 = (float(c5) - close_t) / close_t
                rets_5d.append(r5)
                hit_5d += 1
            else:
                missed_5d += 1
        else:
            missed_5d += 1
        
        if t_idx + 10 < len(trade_dates):
            d10 = trade_dates[t_idx + 10]
            c10 = all_prices.get((ts_code, d10))
            if c10 and c10 > 0 and close_t > 0:
                r10 = (float(c10) - close_t) / close_t
                rets_10d.append(r10)
                hit_10d += 1
            else:
                missed_10d += 1
        else:
            missed_10d += 1
        
        if t_idx + 20 < len(trade_dates):
            d20 = trade_dates[t_idx + 20]
            c20 = all_prices.get((ts_code, d20))
            if c20 and c20 > 0 and close_t > 0:
                r20 = (float(c20) - close_t) / close_t
                rets_20d.append(r20)
                hit_20d += 1
            else:
                missed_20d += 1
        else:
            missed_20d += 1
    
    def calc_stats(rets):
        if len(rets) < 5:
            return None, None, None
        avg_ret = sum(rets) / len(rets)
        wins = sum(1 for r in rets if r > 0)
        wr = wins / len(rets) * 100
        if len(rets) > 1:
            variance = sum((r - avg_ret) ** 2 for r in rets) / (len(rets) - 1)
            std = variance ** 0.5
            sharpe = (avg_ret / std) * (252 / 5) ** 0.5 if std > 0 else 0
        else:
            sharpe = 0
        return avg_ret * 100, wr, sharpe
    
    r5_avg, r5_wr, r5_sharpe = calc_stats(rets_5d)
    r10_avg, r10_wr, _ = calc_stats(rets_10d)
    r20_avg, r20_wr, _ = calc_stats(rets_20d)
    
    print(f"  📈 T+5: N={hit_5d}(missed={missed_5d}), R5={r5_avg:.2f}%, WR={r5_wr:.2f}%, Sharpe={r5_sharpe:.3f}")
    print(f"  📈 T+10: N={hit_10d}, R10={r10_avg:.2f}%, WR={r10_wr:.2f}%")
    print(f"  📈 T+20: N={hit_20d}, R20={r20_avg:.2f}%, WR={r20_wr:.2f}%")
    
    return {
        "signal_count": len(signals),
        "ret_5d": r5_avg,
        "ret_10d": r10_avg,
        "ret_20d": r20_avg,
        "win_rate_5d": r5_wr,
        "win_rate_10d": r10_wr,
        "win_rate_20d": r20_wr,
        "sharpe_5d": r5_sharpe,
    }


# ============================================================
# COMBOS - using simpler column aliases to avoid 's.' prefix
# ============================================================
combos = []

# C1: Ultra-deep value relaxed — PE≤10+PB≤1+dv≥2%+netprofit_yoy≥0%+底20%+VR≥1.0+CM≤50亿
# Relaxing: dv 3%→2%, netprofit 10%→0% (just positive), VR 1.2→1.0, CM 30→50亿
combos.append({
    "name": "C1: 超低估值 — PE≤10+PB≤1+dv≥2%+净利增长≥0%+底20%+VR≥1.0+CM≤50亿",
    "sql": """
WITH
signals AS (
    SELECT s.ts_code AS ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pe, pb, dv_ttm, circ_mv, volume_ratio
               FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
    INNER JOIN (SELECT ts_code, end_date, netprofit_yoy
               FROM tushare.tushare_fina_indicator FINAL
               WHERE end_date = toDate('2026-03-31')) f
        ON s.ts_code = f.ts_code
    WHERE s.trade_date >= toDate('2020-01-01') AND s.trade_date <= toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%'
      AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND d.pe > 0 AND d.pe <= 10
      AND d.pb > 0 AND d.pb <= 1
      AND d.dv_ttm >= 2.0
      AND f.netprofit_yoy >= 0
      AND d.circ_mv <= 500000
      AND d.volume_ratio >= 1.0
),
pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL
          WHERE trade_date >= toDate('2019-12-01'))
)
SELECT s.ts_code, s.trade_date, s.close
FROM signals s
INNER JOIN pos p ON s.ts_code = p.ts_code AND s.trade_date = p.trade_date
WHERE p.max_20 > p.min_20
  AND (p.close - p.min_20) / (p.max_20 - p.min_20) <= 0.2
"""
})

# C2: High ROE quality + dv + relaxed VR + SPX — ROE≥10%+PB≤1.5+dv≥2%+底20%+VR≥1.0+CM≤50亿+SPX涨
combos.append({
    "name": "C2: 高ROE质量价值+SPX — ROE≥10%+PB≤1.5+dv≥2%+底20%+VR≥1.0+CM≤50亿+SPX涨",
    "sql": """
WITH
spx AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= toDate('2019-12-01')
),
signals_raw AS (
    SELECT s.ts_code AS ts_code, s.trade_date, s.close, spx.pct_chg AS spx_pct
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pe, pb, dv_ttm, circ_mv, volume_ratio
               FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
    INNER JOIN (SELECT ts_code, end_date, roe
               FROM tushare.tushare_fina_indicator FINAL
               WHERE end_date = toDate('2026-03-31')) f
        ON s.ts_code = f.ts_code
    INNER JOIN spx ON s.trade_date = spx.trade_date
    WHERE s.trade_date >= toDate('2020-01-01') AND s.trade_date <= toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%'
      AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND f.roe >= 10.0
      AND d.pb > 0 AND d.pb <= 1.5
      AND d.dv_ttm >= 2.0
      AND d.circ_mv <= 500000
      AND d.volume_ratio >= 1.0
      AND spx.pct_chg > 0
),
pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL
          WHERE trade_date >= toDate('2019-12-01'))
)
SELECT sr.ts_code, sr.trade_date, sr.close
FROM signals_raw sr
INNER JOIN pos p ON sr.ts_code = p.ts_code AND sr.trade_date = p.trade_date
WHERE p.max_20 > p.min_20
  AND (p.close - p.min_20) / (p.max_20 - p.min_20) <= 0.2
"""
})

# C3: Revenue growing deep value with money flow
# tr_yoy≥10% + PE≤15 + PB≤1 + 底20% + VR≥1.0 + sell_sm>buy_sm + buy_lg>sell_lg + CM≤50亿
combos.append({
    "name": "C3: 营收增长深价值+资金流 — tr_yoy≥10%+PE≤15+PB≤1+底20%+VR≥1.0+sell_sm>buy_sm+buy_lg>sell_lg+CM≤50亿",
    "sql": """
WITH
signals_raw AS (
    SELECT s.ts_code AS ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pe, pb, dv_ttm, circ_mv, volume_ratio
               FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
    INNER JOIN (SELECT ts_code, end_date, tr_yoy
               FROM tushare.tushare_fina_indicator FINAL
               WHERE end_date = toDate('2026-03-31')) f
        ON s.ts_code = f.ts_code
    INNER JOIN (SELECT ts_code, trade_date, buy_sm_vol, sell_sm_vol,
                       buy_lg_vol, sell_lg_vol
               FROM tushare.tushare_moneyflow FINAL) m
        ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    WHERE s.trade_date >= toDate('2020-01-01') AND s.trade_date <= toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%'
      AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND f.tr_yoy >= 10.0
      AND d.pe > 0 AND d.pe <= 15
      AND d.pb > 0 AND d.pb <= 1
      AND d.circ_mv <= 500000
      AND d.volume_ratio >= 1.0
      AND m.sell_sm_vol > m.buy_sm_vol
      AND m.buy_lg_vol > m.sell_lg_vol
),
pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL
          WHERE trade_date >= toDate('2019-12-01'))
)
SELECT s.ts_code, s.trade_date, s.close
FROM signals_raw s
INNER JOIN pos p ON s.ts_code = p.ts_code AND s.trade_date = p.trade_date
WHERE p.max_20 > p.min_20
  AND (p.close - p.min_20) / (p.max_20 - p.min_20) <= 0.2
"""
})

# C4: Ultra-high dividend deep value 60d bottom (no financial indicator needed)
# PB≤1 + dv_ttm≥4% + 底40%(60d) + VR≥1.2 + CM≤30亿
combos.append({
    "name": "C4: 超高股息破净60日底 — PB≤1+dv≥4%+底40%(60d)+VR≥1.2+CM≤30亿",
    "sql": """
WITH
signals_raw AS (
    SELECT s.ts_code AS ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pe, pb, dv_ttm, circ_mv, volume_ratio
               FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
    WHERE s.trade_date >= toDate('2020-01-01') AND s.trade_date <= toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%'
      AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND d.pb > 0 AND d.pb <= 1
      AND d.dv_ttm >= 4.0
      AND d.circ_mv <= 300000
      AND d.volume_ratio >= 1.2
),
pos60 AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_60,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_60
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL
          WHERE trade_date >= toDate('2019-10-01'))
)
SELECT s.ts_code, s.trade_date, s.close
FROM signals_raw s
INNER JOIN pos60 p ON s.ts_code = p.ts_code AND s.trade_date = p.trade_date
WHERE p.max_60 > p.min_60
  AND (p.close - p.min_60) / (p.max_60 - p.min_60) <= 0.4
"""
})

# C5: Earnings momentum value + SPX (wider parameters)
# netprofit_yoy≥10% + PE≤20 + PB≤2 + dv_ttm≥1.5% + 底20% + VR≥1.0 + CM≤50亿 + SPX涨
combos.append({
    "name": "C5: 净利增长合理估值+SPX — netprofit_yoy≥10%+PE≤20+PB≤2+dv≥1.5%+底20%+VR≥1.0+CM≤50亿+SPX涨",
    "sql": """
WITH
spx AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= toDate('2019-12-01')
),
signals_raw AS (
    SELECT s.ts_code AS ts_code, s.trade_date, s.close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
    INNER JOIN (SELECT ts_code, trade_date, pe, pb, dv_ttm, circ_mv, volume_ratio
               FROM tushare.tushare_daily_basic FINAL) d
        ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
    INNER JOIN (SELECT ts_code, end_date, netprofit_yoy
               FROM tushare.tushare_fina_indicator FINAL
               WHERE end_date = toDate('2026-03-31')) f
        ON s.ts_code = f.ts_code
    INNER JOIN spx ON s.trade_date = spx.trade_date
    WHERE s.trade_date >= toDate('2020-01-01') AND s.trade_date <= toDate('2026-05-12')
      AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%'
      AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
      AND f.netprofit_yoy >= 10.0
      AND d.pe > 0 AND d.pe <= 20
      AND d.pb > 0 AND d.pb <= 2
      AND d.dv_ttm >= 1.5
      AND d.circ_mv <= 500000
      AND d.volume_ratio >= 1.0
      AND spx.pct_chg > 0
),
pos AS (
    SELECT ts_code, trade_date, close,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL
          WHERE trade_date >= toDate('2019-12-01'))
)
SELECT s.ts_code, s.trade_date, s.close
FROM signals_raw s
INNER JOIN pos p ON s.ts_code = p.ts_code AND s.trade_date = p.trade_date
WHERE p.max_20 > p.min_20
  AND (p.close - p.min_20) / (p.max_20 - p.min_20) <= 0.2
"""
})

# ============================================================
# RUN BACKTESTS
# ============================================================
results = []
for combo in combos:
    signals = detect_signals(combo["name"], combo["sql"])
    stats = compute_forward_returns(signals)
    results.append({
        "name": combo["name"],
        **stats
    })
    print()

# ============================================================
# REPORT
# ============================================================
from datetime import datetime
now = datetime.now().strftime("%Y-%m-%d %H:%M UTC+8")

report_lines = [f"# Iter24 T5: 基本面估值分析\n"]
report_lines.append(f"**系统执行时间**: {now}\n")
report_lines.append(f"**迭代编号**: 24")
report_lines.append(f"**数据基准日期**: 2026-05-12 (Tushare DB)\n")
report_lines.append("---\n")
report_lines.append("## 参数组合测试结果\n")
report_lines.append("| 组合 | 描述 | 信号数 | 胜率(WR) | 5D收益 | 10D收益 | 20D收益 | Sharpe | 状态 |")
report_lines.append("|------|------|--------|---------|--------|---------|---------|--------|------|")

for r in results:
    name = r["name"]
    sc = r.get("signal_count", 0)
    wr5 = f"{r['win_rate_5d']:.2f}%" if r['win_rate_5d'] is not None else "N/A"
    r5 = f"{r['ret_5d']:.2f}%" if r['ret_5d'] is not None else "N/A"
    r10 = f"{r['ret_10d']:.2f}%" if r['ret_10d'] is not None else "N/A"
    r20 = f"{r['ret_20d']:.2f}%" if r['ret_20d'] is not None else "N/A"
    sh = f"{r['sharpe_5d']:.3f}" if r['sharpe_5d'] is not None else "N/A"
    
    passed = (sc >= 200 and r['win_rate_5d'] is not None and r['win_rate_5d'] >= 52 
              and r['ret_5d'] is not None and r['ret_5d'] >= 3.0)
    status = "✅ PASS" if passed else "❌ FAIL"
    
    short_name = name.split(":")[0]
    report_lines.append(f"| {short_name} | {name} | {sc} | {wr5} | {r5} | {r10} | {r20} | {sh} | {status} |")

report_lines.extend([
    "",
    "## 成功标准",
    "- WR >= 52% AND 5D收益 >= 3% AND 信号数 >= 200",
    "",
])

# Find best
valid_results = [r for r in results if r.get("signal_count", 0) >= 200 
                 and r.get("win_rate_5d") is not None and r["win_rate_5d"] >= 50
                 and r.get("ret_5d") is not None]

if valid_results:
    best = max(valid_results, key=lambda r: (r.get("win_rate_5d", 0) or 0) * (r.get("ret_5d", 0) or 0))
    report_lines.extend([
        "---",
        f"## 🏆 最佳发现",
        f"**{best['name']}**",
        f"- **信号数**: {best['signal_count']}",
        f"- **胜率(WR)**: {best['win_rate_5d']:.2f}%",
        f"- **5D平均收益**: {best['ret_5d']:.2f}%",
        f"- **10D平均收益**: {best['ret_10d']:.2f}%",
        f"- **20D平均收益**: {best['ret_20d']:.2f}%",
        f"- **Sharpe(5D)**: {best['sharpe_5d']:.3f}",
    ])
    
    if best["win_rate_5d"] is not None and best["win_rate_5d"] > 79.43:
        report_lines.append(f"- 🏆 **新T5流派WR纪录!** {best['win_rate_5d']:.2f}% > 79.43% (Iter23 T5-C1)")
    elif best["ret_5d"] is not None and best["ret_5d"] > 7.97:
        report_lines.append(f"- 🏆 **新T5流派R5纪录!** {best['ret_5d']:.2f}% > 7.97% (Iter23 T5-C1)")
    else:
        report_lines.append(f"- 📊 未超越T5流派最佳(WR=79.43%, R5=7.97%, N=319, Iter23 T5-C1)")
else:
    report_lines.append("## ❌ 无组合通过成功标准\n")

report_lines.append("")
report_lines.append("---")
report_lines.append("## 关键SQL查询（可复现）")
report_lines.append("")

# Add SQL for best combo
if valid_results:
    best_idx = results.index(best)
    best_sql = combos[best_idx]["sql"]
    report_lines.append("### 最佳组合SQL")
    report_lines.append("```sql")
    report_lines.append(best_sql)
    report_lines.append("```")

report_lines.append("")
report_lines.append("### 备注")
report_lines.append("- 所有查询使用全量历史数据 (2020-01-01 ~ 2026-05-12)")
report_lines.append("- 主板过滤: ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'")
report_lines.append("- circ_mv单位: 万元 (300000=30亿, 500000=50亿)")
report_lines.append("- 底部位置通过20日/60日滑动窗口计算")

report = "\n".join(report_lines)

# Write report
output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_24/analysis_T5_基本面估值.md"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(report)

print(f"\n{'='*60}")
print(f"📄 Report written to: {output_path}")
print(f"{'='*60}")
print(report)

# Output summary for kanban_complete
if valid_results:
    br = best
    print(f"\n\nBEST_RESULT|{br['name']}|WR={br['win_rate_5d']:.2f}|R5={br['ret_5d']:.2f}|N={br['signal_count']}|Sharpe={br['sharpe_5d']:.3f}")
else:
    print("\n\nNO_PASS")
