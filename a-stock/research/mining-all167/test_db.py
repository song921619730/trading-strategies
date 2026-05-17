#!/usr/bin/env python3
"""Test moneyflow and PMI queries."""
import urllib.request, json

CH_HOST = "172.24.224.1"
CH_PORT = 8123
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def q(sql, t=120):
    url = f"http://{CH_HOST}:{CH_PORT}/?user={CH_USER}&password={CH_PASS}&database=tushare&default_format=JSON"
    req = urllib.request.Request(url, data=sql.encode())
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read())["data"]

# Test moneyflow count by year
for y in [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]:
    try:
        r = q(f"SELECT count() AS cnt FROM tushare_moneyflow FINAL WHERE trade_date>='{y}0101' AND trade_date<='{y}1231'")
        print(f"{y}: {r[0]['cnt']} rows")
    except Exception as e:
        print(f"{y}: ERROR {e}")

# Test PMI structure
print("\nPMI columns:")
r = q("SELECT name, type FROM system.columns WHERE table='tushare_cn_pmi' AND database='tushare'")
for c in r[:10]:
    print(f"  {c['name']}: {c['type']}")
print(f"  ... ({len(r)} columns total)")

# Test PMI with MONTH
print("\nPMI monthly data (latest 5):")
r = q("SELECT MONTH, PMI010000 FROM tushare_cn_pmi FINAL ORDER BY MONTH DESC LIMIT 5")
for row in r:
    print(f"  {row['MONTH']}: PMI={row['PMI010000']}")
