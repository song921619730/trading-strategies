#!/usr/bin/env python3
"""ClickHouse query helper — sends SQL as POST body (works for large queries)"""
import json, urllib.request, urllib.parse, sys

HOST = "172.24.224.1"
HTTP_PORT = "8123"
USER = "ai_reader"
PASSWORD = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
DATABASE = "tushare"

def ch_query(sql, timeout=300):
    url = f"http://{HOST}:{HTTP_PORT}/?user={USER}&password={PASSWORD}&database={DATABASE}&default_format=JSON"
    data = sql.encode('utf-8')
    req = urllib.request.Request(url, data=data)
    req.add_header('Content-Type', 'text/plain')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode('utf-8')
        result = json.loads(body)
        return result.get("data", [])

if __name__ == "__main__":
    sql = sys.argv[1] if len(sys.argv) > 1 else "SELECT 1 AS test"
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    data = ch_query(sql, timeout)
    print(json.dumps(data))
