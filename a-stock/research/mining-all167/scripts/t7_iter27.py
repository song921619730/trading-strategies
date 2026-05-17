#!/usr/bin/env python3
"""T7 跨市场联动 — Iter 27 策略挖掘脚本
运行5组参数组合的 ClickHouse 回测
"""
import json, sys, os
from urllib.request import Request, urlopen
from urllib.parse import urlencode

CH_URL = "http://172.24.224.1:8123"
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_query(sql):
    """Execute ClickHouse SQL via HTTP interface - returns list of dicts"""
    url = f"{CH_URL}/?default_format=JSONCompact"
    req = Request(url, data=sql.encode('utf-8'))
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    import base64
    auth = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', f'Basic {auth}')
    try:
        resp = urlopen(req, timeout=300)
        raw = json.loads(resp.read().decode('utf-8'))
        if 'data' not in raw or not raw['data']:
            return []
        # Convert from JSONCompact array-of-arrays to list of dicts
        cols = [m['name'] for m in raw['meta']]
        rows = []
        for row in raw['data']:
            d = {}
            for i, col in enumerate(cols):
                d[col] = row[i] if i < len(row) else None
            rows.append(d)
        return rows
    except Exception as e:
        return [{"error": str(e)}]

# ─── 定义5组参数 ───

combos = [
    {
        "id": "C1",
        "name": "T7-C3-CM50扩容",
        "desc": "迭代26最佳(C3)的CM扩容版: 30亿→50亿",
        "params": {
            "SPX前日涨>0": True,
            "恐慌≤-5%": True,
            "振幅≥7%": True,
            "VR≥1.0": True,
            "散户割肉(sell_sm>buy_sm)": True,
            "大单(buy_lg>sell_lg)": True,
            "底20%(20日)": True,
            "CM≤50亿": True
        },
        "end_date": "2026-05-06",
    },
    {
        "id": "C2",
        "name": "T7-SPX双涨+双日恐慌-5%+三重资金流+微盘",
        "desc": "SPX连续2日前日上涨 + 双日极端恐慌(-5%) + 三重资金流确认",
        "params": {
            "SPX连续2日前日涨>0": True,
            "双日恐慌(昨≤-5%+今≤-5%)": True,
            "VR≥1.0": True,
            "散户割肉(sell_sm>buy_sm)": True,
            "大单(buy_lg>sell_lg)": True,
            "底20%(20日)": True,
            "CM≤30亿": True
        },
        "end_date": "2026-05-06",
    },
    {
        "id": "C3",
        "name": "T7-HSI恐慌+SPX+个股恐慌+微盘",
        "desc": "HSI暴跌(-2%)+SPX偏暖+个股恐慌三重跨市场确认",
        "params": {
            "HSI恐慌≤-2%": True,
            "SPX前日涨>0": True,
            "个股恐慌≤-5%": True,
            "振幅≥6%": True,
            "VR≥1.0": True,
            "散户割肉(sell_sm>buy_sm)": True,
            "底20%(20日)": True,
            "CM≤30亿": True
        },
        "end_date": "2026-05-06",
    },
    {
        "id": "C4",
        "name": "T7-SPX+恐慌+振幅7%+大单比例≥50%+散户割肉+底20%+CM≤50亿",
        "desc": "用大单买入比例≥50%替代原始大单净买入, 更强的大单确认信号",
        "params": {
            "SPX前日涨>0": True,
            "恐慌≤-5%": True,
            "振幅≥7%": True,
            "VR≥1.0": True,
            "大单比例≥50%": True,
            "散户割肉(sell_sm>buy_sm)": True,
            "底20%(20日)": True,
            "CM≤50亿": True
        },
        "end_date": "2026-05-06",
    },
    {
        "id": "C5",
        "name": "T7-三重资金流+底40%+CM100亿(最大容量版)",
        "desc": "三重资金流确认 + 放宽底位至40% + CM≤100亿, 最大信号量测试",
        "params": {
            "SPX前日涨>0": True,
            "恐慌≤-5%": True,
            "振幅≥7%": True,
            "VR≥1.0": True,
            "散户割肉(sell_sm>buy_sm)": True,
            "大单(buy_lg>sell_lg)": True,
            "ELG(buy_elg>sell_elg)": True,
            "底40%(20日)": True,
            "CM≤100亿": True
        },
        "end_date": "2026-05-06",
    },
]

# ─── 构建SQL ───

def build_sql_c1(end_date="2026-05-06"):
    """C1: T7-C3-CM50扩容 - SPX前日涨+恐慌-5%+振幅7%+VR+散户割肉+大单+底20%+CM≤50亿"""
    return f"""
WITH prices AS (
    SELECT ts_code, trade_date, close, pct_chg, pre_close, high, low,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS close_t5,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS close_t10,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_t20,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
    FROM tushare.tushare_stock_daily FINAL
)
SELECT count() AS signal_count, countIf((close_t5/close-1)>0) AS win_5d,
    round(avgOrNull((close_t5/close-1)*100), 2) AS avg_ret_5d,
    round(avgOrNull((close_t10/close-1)*100), 2) AS avg_ret_10d,
    round(avgOrNull((close_t20/close-1)*100), 2) AS avg_ret_20d,
    round(avgOrNull((close_t5/close-1)*100)/NULLIF(stddevSampOrNull((close_t5/close-1)*100),0)*sqrt(252.0/5), 2) AS sharpe_5d
FROM prices p
INNER JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv FROM tushare.tushare_daily_basic FINAL) d 
    ON p.ts_code=d.ts_code AND p.trade_date=d.trade_date
INNER JOIN (SELECT ts_code, trade_date, sell_sm_amount, buy_sm_amount, buy_lg_amount, sell_lg_amount 
            FROM tushare.tushare_moneyflow FINAL) m 
    ON p.ts_code=m.ts_code AND p.trade_date=m.trade_date
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS spx_1d 
           FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx 
    ON p.trade_date=spx.trade_date
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{end_date}')
    AND spx.spx_1d > 0 AND p.pct_chg <= -5 AND (p.high-p.low)/p.pre_close*100 >= 7
    AND d.volume_ratio >= 1.0
    AND m.sell_sm_amount > m.buy_sm_amount AND m.buy_lg_amount > m.sell_lg_amount
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 500000
"""

def build_sql_c2(end_date="2026-05-06"):
    """C2: SPX连续2日前日涨+双日恐慌(-5%)+VR+散户割肉+大单+底20%+CM≤30亿"""
    return f"""
WITH spx AS (
    SELECT trade_date, pct_chg,
        any(pct_chg) OVER (ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS spx_prev
    FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX'
),
prices AS (
    SELECT ts_code, trade_date, close, pct_chg, pre_close, high, low,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS close_t5,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS close_t10,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_t20,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d,
        any(pct_chg) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS prev_pct_chg
    FROM tushare.tushare_stock_daily FINAL
)
SELECT count() AS signal_count, countIf((close_t5/close-1)>0) AS win_5d,
    round(avgOrNull((close_t5/close-1)*100), 2) AS avg_ret_5d,
    round(avgOrNull((close_t10/close-1)*100), 2) AS avg_ret_10d,
    round(avgOrNull((close_t20/close-1)*100), 2) AS avg_ret_20d,
    round(avgOrNull((close_t5/close-1)*100)/NULLIF(stddevSampOrNull((close_t5/close-1)*100),0)*sqrt(252.0/5), 2) AS sharpe_5d
FROM prices p
INNER JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv FROM tushare.tushare_daily_basic FINAL) d 
    ON p.ts_code=d.ts_code AND p.trade_date=d.trade_date
INNER JOIN (SELECT ts_code, trade_date, sell_sm_amount, buy_sm_amount, buy_lg_amount, sell_lg_amount 
            FROM tushare.tushare_moneyflow FINAL) m 
    ON p.ts_code=m.ts_code AND p.trade_date=m.trade_date
LEFT JOIN spx ON p.trade_date = spx.trade_date + INTERVAL 1 DAY
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{end_date}')
    AND spx.pct_chg > 0 AND spx.spx_prev > 0   -- SPX连续2日前日上涨
    AND p.prev_pct_chg <= -5 AND p.pct_chg <= -5  -- 双日恐慌
    AND d.volume_ratio >= 1.0
    AND m.sell_sm_amount > m.buy_sm_amount AND m.buy_lg_amount > m.sell_lg_amount
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 300000
"""

def build_sql_c3(end_date="2026-05-06"):
    """C3: HSI恐慌+SPX+个股恐慌+振幅+VR+散户割肉+底20%+CM≤30亿"""
    return f"""
WITH prices AS (
    SELECT ts_code, trade_date, close, pct_chg, pre_close, high, low,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS close_t5,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS close_t10,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_t20,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
    FROM tushare.tushare_stock_daily FINAL
)
SELECT count() AS signal_count, countIf((close_t5/close-1)>0) AS win_5d,
    round(avgOrNull((close_t5/close-1)*100), 2) AS avg_ret_5d,
    round(avgOrNull((close_t10/close-1)*100), 2) AS avg_ret_10d,
    round(avgOrNull((close_t20/close-1)*100), 2) AS avg_ret_20d,
    round(avgOrNull((close_t5/close-1)*100)/NULLIF(stddevSampOrNull((close_t5/close-1)*100),0)*sqrt(252.0/5), 2) AS sharpe_5d
FROM prices p
INNER JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv FROM tushare.tushare_daily_basic FINAL) d 
    ON p.ts_code=d.ts_code AND p.trade_date=d.trade_date
INNER JOIN (SELECT ts_code, trade_date, sell_sm_amount, buy_sm_amount FROM tushare.tushare_moneyflow FINAL) m 
    ON p.ts_code=m.ts_code AND p.trade_date=m.trade_date
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS spx_1d 
           FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx 
    ON p.trade_date=spx.trade_date
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS hsi_1d
           FROM tushare.tushare_index_global FINAL WHERE ts_code='HSI') hsi
    ON p.trade_date=hsi.trade_date
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{end_date}')
    AND spx.spx_1d > 0 AND hsi.hsi_1d <= -2  -- HSI恐慌
    AND p.pct_chg <= -5 AND (p.high-p.low)/p.pre_close*100 >= 6
    AND d.volume_ratio >= 1.0
    AND m.sell_sm_amount > m.buy_sm_amount
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 300000
"""

def build_sql_c4(end_date="2026-05-06"):
    """C4: SPX+恐慌+振幅7%+VR+大单比例≥50%+散户割肉+底20%+CM≤50亿"""
    return f"""
WITH prices AS (
    SELECT ts_code, trade_date, close, pct_chg, pre_close, high, low,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS close_t5,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS close_t10,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_t20,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
    FROM tushare.tushare_stock_daily FINAL
)
SELECT count() AS signal_count, countIf((close_t5/close-1)>0) AS win_5d,
    round(avgOrNull((close_t5/close-1)*100), 2) AS avg_ret_5d,
    round(avgOrNull((close_t10/close-1)*100), 2) AS avg_ret_10d,
    round(avgOrNull((close_t20/close-1)*100), 2) AS avg_ret_20d,
    round(avgOrNull((close_t5/close-1)*100)/NULLIF(stddevSampOrNull((close_t5/close-1)*100),0)*sqrt(252.0/5), 2) AS sharpe_5d
FROM prices p
INNER JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv FROM tushare.tushare_daily_basic FINAL) d 
    ON p.ts_code=d.ts_code AND p.trade_date=d.trade_date
INNER JOIN (SELECT ts_code, trade_date, sell_sm_amount, buy_sm_amount, 
                   buy_lg_amount, sell_lg_amount, buy_md_amount, buy_elg_amount, sell_elg_amount
            FROM tushare.tushare_moneyflow FINAL) m 
    ON p.ts_code=m.ts_code AND p.trade_date=m.trade_date
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS spx_1d 
           FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx 
    ON p.trade_date=spx.trade_date
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{end_date}')
    AND spx.spx_1d > 0 AND p.pct_chg <= -5 AND (p.high-p.low)/p.pre_close*100 >= 7
    AND d.volume_ratio >= 1.0
    AND m.sell_sm_amount > m.buy_sm_amount
    AND (m.buy_lg_amount / (m.buy_sm_amount + m.buy_md_amount + m.buy_lg_amount + m.buy_elg_amount)) * 100 >= 50
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 500000
"""

def build_sql_c5(end_date="2026-05-06"):
    """C5: 三重资金流 + 底40% + CM100亿(最大容量版)"""
    return f"""
WITH prices AS (
    SELECT ts_code, trade_date, close, pct_chg, pre_close, high, low,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS close_t5,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS close_t10,
        any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_t20,
        MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
        MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
    FROM tushare.tushare_stock_daily FINAL
)
SELECT count() AS signal_count, countIf((close_t5/close-1)>0) AS win_5d,
    round(avgOrNull((close_t5/close-1)*100), 2) AS avg_ret_5d,
    round(avgOrNull((close_t10/close-1)*100), 2) AS avg_ret_10d,
    round(avgOrNull((close_t20/close-1)*100), 2) AS avg_ret_20d,
    round(avgOrNull((close_t5/close-1)*100)/NULLIF(stddevSampOrNull((close_t5/close-1)*100),0)*sqrt(252.0/5), 2) AS sharpe_5d
FROM prices p
INNER JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv FROM tushare.tushare_daily_basic FINAL) d 
    ON p.ts_code=d.ts_code AND p.trade_date=d.trade_date
INNER JOIN (SELECT ts_code, trade_date, sell_sm_amount, buy_sm_amount, 
                   buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount
            FROM tushare.tushare_moneyflow FINAL) m 
    ON p.ts_code=m.ts_code AND p.trade_date=m.trade_date
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS spx_1d 
           FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx 
    ON p.trade_date=spx.trade_date
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{end_date}')
    AND spx.spx_1d > 0 AND p.pct_chg <= -5 AND (p.high-p.low)/p.pre_close*100 >= 7
    AND d.volume_ratio >= 1.0
    AND m.sell_sm_amount > m.buy_sm_amount  -- 散户割肉
    AND m.buy_lg_amount > m.sell_lg_amount  -- 大单抄底
    AND m.buy_elg_amount > m.sell_elg_amount  -- 超大单抄底(三重确认)
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.4 AND d.circ_mv <= 1000000
"""

# ─── 运行回测 ───

builders = [build_sql_c1, build_sql_c2, build_sql_c3, build_sql_c4, build_sql_c5]

results = []
for i, combo in enumerate(combos):
    print(f"\n{'='*60}")
    print(f"🏃 {combo['id']}: {combo['name']}")
    print(f"📝 {combo['desc']}")
    print(f"{'='*60}")
    
    sql = builders[i](combo.get("end_date", "2026-05-06"))
    
    # Print SQL summary (first 200 chars)
    print(f"SQL ({len(sql)} chars): {sql[:200]}...")
    
    result = ch_query(sql)
    
    if not result or len(result) == 0:
        print(f"❌ No results returned")
        results.append({"id": combo['id'], "name": combo['name'], "error": "no results"})
        continue
    
    row = result[0]
    if 'error' in row:
        print(f"❌ ERROR: {row['error']}")
        results.append({"id": combo['id'], "name": combo['name'], "error": row['error']})
        continue
    signal_count = int(row['signal_count']) if row['signal_count'] is not None else 0
    win_5d = int(row['win_5d']) if row['win_5d'] is not None else 0
    avg_ret_5d = float(row['avg_ret_5d']) if row['avg_ret_5d'] is not None else 0.0
    avg_ret_10d = float(row['avg_ret_10d']) if row['avg_ret_10d'] is not None else 0.0
    avg_ret_20d = float(row['avg_ret_20d']) if row['avg_ret_20d'] is not None else 0.0
    sharpe_5d = float(row['sharpe_5d']) if row['sharpe_5d'] is not None else 0.0
    
    wr_5d = (win_5d / signal_count * 100) if signal_count > 0 else 0.0
    
    is_pass = "✅" if (signal_count >= 200 and wr_5d >= 52 and avg_ret_5d >= 3) else "❌"
    is_excellent = "🏆" if (signal_count >= 200 and wr_5d >= 58 and avg_ret_5d >= 7) else ""
    
    print(f"\n📊 Results for {combo['id']}:")
    print(f"   Signal Count: {signal_count:,}")
    print(f"   5D Win Rate:  {wr_5d:.2f}% ({win_5d}/{signal_count})")
    print(f"   5D Avg Ret:   {avg_ret_5d:.2f}%")
    print(f"   10D Avg Ret:  {avg_ret_10d:.2f}%")
    print(f"   20D Avg Ret:  {avg_ret_20d:.2f}%")
    print(f"   Sharpe(5D):   {sharpe_5d:.2f}")
    print(f"   Status:       {is_pass} {is_excellent}")
    
    results.append({
        "id": combo['id'],
        "name": combo['name'],
        "desc": combo['desc'],
        "params": combo['params'],
        "signal_count": signal_count,
        "win_5d": win_5d,
        "wr_5d": round(wr_5d, 2),
        "avg_ret_5d": avg_ret_5d,
        "avg_ret_10d": avg_ret_10d,
        "avg_ret_20d": avg_ret_20d,
        "sharpe_5d": sharpe_5d,
        "is_pass": is_pass.strip(),
        "sql": sql[:500],
    })

# Save full results to JSON
output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_27/t7_results.json"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n\n{'='*60}")
print(f"📊 SUMMARY")
print(f"{'='*60}")
print(f"{'ID':<6} {'Signal':>8} {'WR%':>7} {'R5%':>7} {'R10%':>7} {'R20%':>7} {'Sharpe':>7} {'Status':>8}")
print(f"{'-'*60}")
for r in results:
    if 'error' in r:
        print(f"{r['id']:<6} {'ERROR':>8} {r.get('error',''):>30}")
    else:
        status = "✅" if r['is_pass'] else "❌"
        print(f"{r['id']:<6} {r['signal_count']:>8,} {r['wr_5d']:>6.1f}% {r['avg_ret_5d']:>6.2f}% {r['avg_ret_10d']:>6.2f}% {r['avg_ret_20d']:>6.2f}% {r['sharpe_5d']:>6.2f} {status:>8}")

print(f"\n✅ Results saved to {output_path}")
