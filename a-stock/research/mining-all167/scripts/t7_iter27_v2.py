#!/usr/bin/env python3
"""T7 跨市场联动 — Iter 27 补充回测
改进C2/C3/C4的失败组合, 放松约束条件
"""
import json, sys, os, base64
from urllib.request import Request, urlopen

CH_URL = "http://172.24.224.1:8123"
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_query(sql):
    url = f"{CH_URL}/?default_format=JSONCompact"
    req = Request(url, data=sql.encode('utf-8'))
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    auth = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', f'Basic {auth}')
    try:
        resp = urlopen(req, timeout=300)
        raw = json.loads(resp.read().decode('utf-8'))
        if 'data' not in raw or not raw['data']:
            return []
        cols = [m['name'] for m in raw['meta']]
        rows = []
        for r in raw['data']:
            d = {}
            for i, col in enumerate(cols):
                d[col] = r[i] if i < len(r) else None
            rows.append(d)
        return rows
    except Exception as e:
        return [{"error": str(e)}]

END_DATE = "2026-05-06"

combos = [
    {
        "id": "C2v2",
        "name": "T7-SPX双涨+恐慌-5%+大单+底20%+微盘",
        "desc": "SPX连续2日涨+恐慌-5%+VR+大单+微盘(无散户割肉,无双日恐慌)",
        "sql": f"""
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
INNER JOIN (SELECT ts_code, trade_date, buy_lg_amount, sell_lg_amount FROM tushare.tushare_moneyflow FINAL) m 
    ON p.ts_code=m.ts_code AND p.trade_date=m.trade_date
LEFT JOIN spx ON p.trade_date = spx.trade_date + INTERVAL 1 DAY
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{END_DATE}')
    AND spx.pct_chg > 0 AND spx.spx_prev > 0
    AND p.pct_chg <= -5 AND d.volume_ratio >= 1.0
    AND m.buy_lg_amount > m.sell_lg_amount
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 300000
"""
    },
    {
        "id": "C3v2",
        "name": "T7-HSI恐慌+SPX+恐慌+底20%+CM50亿",
        "desc": "HSI≤-2%+SPX前日涨+个股-5%+振幅5%+VR+底20%+CM≤50亿(无散户割肉)",
        "sql": f"""
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
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS spx_1d 
           FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx 
    ON p.trade_date=spx.trade_date
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS hsi_1d
           FROM tushare.tushare_index_global FINAL WHERE ts_code='HSI') hsi
    ON p.trade_date=hsi.trade_date
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{END_DATE}')
    AND spx.spx_1d > 0 AND hsi.hsi_1d <= -2
    AND p.pct_chg <= -5 AND (p.high-p.low)/p.pre_close*100 >= 5
    AND d.volume_ratio >= 1.0
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 500000
"""
    },
    {
        "id": "C4v2",
        "name": "T7-恐慌+振幅7%+大单比例≥40%+底20%+CM≤30亿",
        "desc": "大单比例放宽至≥40%, 并去除散户割肉约束",
        "sql": f"""
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
                   buy_lg_amount, sell_lg_amount, buy_md_amount, buy_elg_amount
            FROM tushare.tushare_moneyflow FINAL) m 
    ON p.ts_code=m.ts_code AND p.trade_date=m.trade_date
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS spx_1d 
           FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx 
    ON p.trade_date=spx.trade_date
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{END_DATE}')
    AND spx.spx_1d > 0 AND p.pct_chg <= -5 AND (p.high-p.low)/p.pre_close*100 >= 7
    AND d.volume_ratio >= 1.0
    AND m.sell_sm_amount > m.buy_sm_amount  -- 散户割肉保留
    AND (m.buy_lg_amount / (m.buy_sm_amount + m.buy_md_amount + m.buy_lg_amount + m.buy_elg_amount)) * 100 >= 40
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 300000
"""
    },
    {
        "id": "C6",
        "name": "T7-SPX+恐慌+振幅7%+CM30亿(无资金流对照)",
        "desc": "无任何资金流约束的纯参数恐慌反转, 评估资金流因子的边际价值",
        "sql": f"""
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
LEFT JOIN (SELECT trade_date+INTERVAL 1 DAY AS trade_date, pct_chg AS spx_1d 
           FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX') spx 
    ON p.trade_date=spx.trade_date
WHERE p.ts_code NOT LIKE '30%' AND p.ts_code NOT LIKE '688%' AND p.ts_code NOT LIKE '920%' AND p.ts_code NOT LIKE '%ST%'
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{END_DATE}')
    AND spx.spx_1d > 0 AND p.pct_chg <= -5 AND (p.high-p.low)/p.pre_close*100 >= 7
    AND d.volume_ratio >= 1.0
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 300000
"""
    },
    {
        "id": "C7",
        "name": "T7-C1-CM100大规模扩容",
        "desc": "C1进一步扩容: CM≤100亿测试极限容量下的质量表现",
        "sql": f"""
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
    AND p.trade_date >= toDate('2024-01-01') AND p.trade_date <= toDate('{END_DATE}')
    AND spx.spx_1d > 0 AND p.pct_chg <= -5 AND (p.high-p.low)/p.pre_close*100 >= 7
    AND d.volume_ratio >= 1.0
    AND m.sell_sm_amount > m.buy_sm_amount AND m.buy_lg_amount > m.sell_lg_amount
    AND (p.close-p.min_20d) <= (p.max_20d-p.min_20d)*0.2 AND d.circ_mv <= 1000000
"""
    },
]

results = []
for combo in combos:
    print(f"\n{'='*60}")
    print(f"🏃 {combo['id']}: {combo['name']}")
    print(f"📝 {combo['desc']}")
    print(f"{'='*60}")
    
    result = ch_query(combo['sql'])
    
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
    is_excellent = " 🏆" if (signal_count >= 200 and wr_5d >= 58 and avg_ret_5d >= 7) else ""
    
    print(f"   Signal Count: {signal_count:,}")
    print(f"   5D Win Rate:  {wr_5d:.2f}% ({win_5d}/{signal_count})")
    print(f"   5D Avg Ret:   {avg_ret_5d:.2f}%")
    print(f"   10D Avg Ret:  {avg_ret_10d:.2f}%")
    print(f"   20D Avg Ret:  {avg_ret_20d:.2f}%")
    print(f"   Sharpe(5D):   {sharpe_5d:.2f}")
    print(f"   Status:       {is_pass}{is_excellent}")
    
    results.append({
        "id": combo['id'],
        "name": combo['name'],
        "desc": combo['desc'],
        "signal_count": signal_count,
        "win_5d": win_5d,
        "wr_5d": round(wr_5d, 2),
        "avg_ret_5d": avg_ret_5d,
        "avg_ret_10d": avg_ret_10d,
        "avg_ret_20d": avg_ret_20d,
        "sharpe_5d": sharpe_5d,
        "is_pass": is_pass.strip(),
    })

# Also load earlier results
earlier_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_27/t7_results.json"
all_results = []
if os.path.exists(earlier_path):
    with open(earlier_path) as f:
        all_results = json.load(f)
    print(f"\n📎 Loaded {len(all_results)} earlier results")

all_results.extend(results)

# Print summary
print(f"\n\n{'='*60}")
print(f"📊 ALL RESULTS SUMMARY")
print(f"{'='*60}")
print(f"{'ID':<8} {'Signal':>8} {'WR%':>7} {'R5%':>7} {'R10%':>7} {'R20%':>7} {'Sharpe':>7} {'Status':>8}")
print(f"{'-'*60}")
for r in all_results:
    if 'error' in r:
        print(f"{r['id']:<8} {'ERROR':>8} {r.get('error','')[:30]:>30}")
    else:
        status = "✅" if r['is_pass'] else "❌"
        print(f"{r['id']:<8} {r['signal_count']:>8,} {r['wr_5d']:>6.1f}% {r['avg_ret_5d']:>6.2f}% {r['avg_ret_10d']:>6.2f}% {r['avg_ret_20d']:>6.2f}% {r['sharpe_5d']:>6.2f} {status:>8}")

# Save combined
combined_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_27/t7_results_combined.json"
with open(combined_path, 'w') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f"\n✅ Results saved to {combined_path}")
