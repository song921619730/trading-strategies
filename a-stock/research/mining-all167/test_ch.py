#!/usr/bin/env python3
"""Docker exec-based ClickHouse query tool (HTTP port is down after restart)"""
import json, subprocess, sys, hashlib, math
from collections import defaultdict

def ch_query(sql):
    """Execute ClickHouse query via docker exec"""
    # Escape SQL for shell
    sql_escaped = sql.replace('"', '\\"').replace("'", "'\\''")
    cmd = f'docker exec tushare_db-clickhouse-1 clickhouse-client --user ai_reader --password "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ" -q "{sql_escaped}" --format JSONEachRow 2>/dev/null'
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, shell=True)
    if r.returncode != 0:
        print(f"  [SQL ERROR] rc={r.returncode}: {r.stderr[:200]}", file=sys.stderr)
        return []
    try:
        lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
        return [json.loads(l) for l in lines]
    except:
        return []

def parse_date(d):
    s = str(d).replace("-", "")
    return int(s)

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    return hashlib.md5(",".join(f"{k}={v}" for k,v in pairs).encode()).hexdigest()[:12]

COMBOS = [
    {
        "name": "主力吸筹+底部放量起涨",
        "params": {
            "net_mf_min": 5000000,
            "close_position": "底40%",
            "pct_chg_1d_min": 1,
            "volume_ratio_min": 1.0,
            "ma_support": "MA20",
            "market_cap_bucket": "中小盘(30-100亿)",
        },
        "desc": "主力温和吸筹+低位放量启动+均线支撑+中小盘"
    },
    {
        "name": "大单扫货+突破前高",
        "params": {
            "buy_lg_ratio_min": 0.10,
            "n_day_high": 20,
            "volume_ratio_min": 1.5,
            "ma_arrangement": "多头排列",
            "turnover_rate_max": 0.10,
        },
        "desc": "大单扫货+20日新高突破+量能放大+趋势确认"
    },
    {
        "name": "主力护盘+均线粘合待发",
        "params": {
            "net_mf_min": 2000000,
            "pct_chg_1d_min": -3,
            "close_position": "底20%",
            "ma_arrangement": "粘合(差<3%)",
            "volume_ratio_min": 0.8,
        },
        "desc": "主力护盘+超低位+均线粘合蓄力"
    },
    {
        "name": "大额资金+多头排列+中小盘",
        "params": {
            "net_mf_min": 20000000,
            "pct_chg_1d_min": 0,
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "中小盘(30-100亿)",
            "turnover_rate_min": 0.01,
            "volume_ratio_min": 1.0,
        },
        "desc": "大额主力扫货+多头排列+中小盘放量"
    },
    {
        "name": "多维度主力共振+低位放量",
        "params": {
            "net_mf_min": 5000000,
            "buy_lg_ratio_min": 0.08,
            "volume_ratio_min": 1.2,
            "close_position": "底40%",
            "ma_support": "MA20",
            "pct_chg_1d_min": 1,
            "turnover_rate_min": 0.005,
        },
        "desc": "资金主力共振+低位放量+均线支撑"
    },
]

# Test connection
print("="*60)
print("T4 Iter 2 — ClickHouse Backtest (docker-exec mode)")
print("="*60)
print("\nTesting ClickHouse connection...")
r = ch_query("SELECT 1 AS x")
print(f"  Connection: {'OK' if r else 'FAIL'}")
if r:
    print(f"  Max trade_date...")
    d = ch_query("SELECT max(trade_date) AS md FROM tushare.tushare_stock_daily FINAL")
    print(f"  -> {d}")

    print(f"  daily_basic count...")
    d = ch_query("SELECT count() AS n FROM tushare.tushare_daily_basic FINAL")
    print(f"  -> {d}")

    print(f"  moneyflow count...")
    d = ch_query("SELECT count() AS n FROM tushare.tushare_moneyflow FINAL")
    print(f"  -> {d}")
