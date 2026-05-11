#!/usr/bin/env python3
"""LowOpen 每日候选股筛选脚本"""

import sys
import json
import subprocess
import os
from datetime import datetime

def ch_query(args):
    cmd = ["python3", "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout, r.stderr

def parse_lines(output):
    """解析 tab 分隔的文本输出"""
    lines = [l.strip() for l in output.strip().split('\n') if l.strip()]
    if not lines or lines[0].startswith('['):
        return []  # 可能是 JSON
    headers = lines[0].split('\t')
    rows = []
    for line in lines[1:]:
        cols = line.split('\t')
        rows.append(dict(zip(headers, cols)))
    return rows

def parse_json(output):
    """JSON 格式解析"""
    try:
        return json.loads(output)
    except:
        return []

def main():
    # 获取最新数据日期
    out, err = ch_query(["sql", "SELECT max(trade_date) as md FROM tushare.tushare_stock_daily FINAL"])
    data = json.loads(out)
    date = data[0]['md']
    print(f"[INFO] 数据日期: {date}")

    # Step 1: 从 stock_daily 筛选日内反转 >= 5% 的票
    sql1 = f"""
    SELECT ts_code, open, close, round(close/open,2) as rr
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date = '{date}'
      AND close/open >= 1.05
      AND open > 0
      AND ts_code NOT LIKE '%ST'
      AND ts_code NOT LIKE '688%'  -- 排除科创板
      AND ts_code NOT LIKE '30%'   -- 排除创业板
      AND ts_code NOT LIKE '920%'  -- 排除北交所
    ORDER BY close/open DESC
    LIMIT 100
    """
    out1, err1 = ch_query(["sql", sql1])
    candidates = json.loads(out1)
    print(f"[INFO] 日线初筛: {len(candidates)} 只")

    if not candidates:
        print('[WARN] 日线无候选')
        print(json.dumps({"date": date, "count": 0, "list": []}))
        return

    # Step 2: 批量查资金流
    codes = [c['ts_code'] for c in candidates]
    codes_str = ','.join([f"'{c}'" for c in codes])
    sql2 = f"""
    SELECT ts_code, trade_date, close, net_amount,
           round(buy_lg_amount_rate, 2) as buy_lg_rate,
           round(buy_elg_amount_rate, 2) as buy_elg_rate,
           round(net_amount_rate, 2) as net_rate
    FROM tushare.tushare_moneyflow_dc FINAL
    WHERE trade_date = '{date}'
      AND ts_code IN ({codes_str})
      AND net_amount > 0
    ORDER BY net_amount DESC
    """
    out2, err2 = ch_query(["sql", sql2])
    moneyflow_data = json.loads(out2)

    # 建立资金流索引
    mf_index = {r['ts_code']: r for r in moneyflow_data}

    # Step 3: 合并
    results = []
    for c in candidates:
        code = c['ts_code']
        mf = mf_index.get(code, {})
        
        # 排除资金流不达标的
        buy_lg = float(mf.get('buy_lg_rate', 0) or 0)
        if buy_lg < 5:
            continue

        row = {
            "ts_code": code,
            "open": float(c['open']),
            "close": float(c['close']),
            "reversal_ratio": float(c['rr']),
            "buy_lg_rate": buy_lg,
            "net_amount_wan": round(float(mf.get('net_amount', 0) or 0) / 1e4, 0),
            "net_rate": float(mf.get('net_rate', 0) or 0),
            "score": round(buy_lg * 0.4 + float(c['rr']) * 20 * 0.6, 1)
        }
        results.append(row)

    # 按评分排序
    results.sort(key=lambda x: x['score'], reverse=True)

    output = {
        "date": date,
        "count": len(results),
        "list": results
    }

    # 保存到脚本同级目录的 ../candidates.json，但 orchestrator 会在工作目录运行
    # 所以写入工作目录下的 candidates.json
    out_path = "candidates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 也输出一份到标准输出
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
