"""Test long GET query with SPX IN clause."""
import json, urllib.request, urllib.parse

HOST, PORT, USER, PWD = '172.24.224.1', '8123', 'ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'

def ch_q(sql):
    params = {"user": USER, "password": PWD, "database": "tushare",
              "query": sql, "default_format": "JSONEachRow"}
    url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=300) as resp:
        body = resp.read().decode("utf-8")
        if not body.strip():
            return []
        return [json.loads(line) for line in body.strip().split("\n") if line.strip()]

# First get SPX dates
spx_sql = """
SELECT trade_date, pct_chg,
       lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS prev_pct_chg
FROM (SELECT * FROM tushare.tushare_index_global FINAL)
WHERE ts_code = 'SPX' AND trade_date >= '2020-01-01' AND trade_date <= '2026-05-12'
ORDER BY trade_date
"""
spx = ch_q(spx_sql)
up_dates = [r['trade_date'] for r in spx if r.get('prev_pct_chg') and float(r['prev_pct_chg']) > 0]
spx_up_str = "','".join(sorted(up_dates))
spx_up_str = f"'{spx_up_str}'"
print(f"SPX dates string length: {len(spx_up_str)} chars")

# Build a compact test query with SPX
test_sql = f"""
SELECT count() AS cnt FROM (
    SELECT ts_code, trade_date FROM (
        SELECT ts_code, trade_date, MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
        MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
        WHERE trade_date >= '2025-01-01' AND trade_date <= '2026-05-12'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    )
    WHERE trade_date IN ({spx_up_str})
)
"""
print(f"Query length: {len(test_sql)} chars")
print(f"Estimated URL length: {len(test_sql) + 200} chars")

try:
    r = ch_q(test_sql)
    print(f"Result: {r}")
except Exception as e:
    print(f"Error: {e}")
