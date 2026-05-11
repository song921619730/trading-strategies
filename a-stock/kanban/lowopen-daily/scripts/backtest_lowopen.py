#!/usr/bin/env python3
"""LowOpen 策略 5 年回测脚本"""

import sys
import json
import subprocess
import numpy as np

def ch_query(sql):
    cmd = ["python3", "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py", "sql", sql]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"SQL Error: {result.stderr}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except:
        return []

def main():
    print("[INFO] 开始回测 (2021-01-01 至 2026-05-08)...")
    
    # 1. 获取信号 + 未来收盘价
    # 逻辑：T 日收盘买入，T+1, T+3, T+5 收盘卖出计算收益
    # 使用 ClickHouse join + window function
    # 注意：moneyflow 可能比 daily 晚几天才出全，但我们用 Final 去重，尽量用已有数据
    # 为了准确性，我们假设信号日和资金流日是匹配的。
    
    sql = """
    SELECT 
        s.ts_code, 
        s.trade_date, 
        s.entry_close,
        s.rr,
        s.buy_lg_amount,
        s.net_amount_wan,
        f.close as close_t1,
        f3.close as close_t3,
        f5.close as close_t5
    FROM (
        SELECT 
            d.ts_code, 
            d.trade_date, 
            d.close as entry_close,
            round(d.close/d.open, 4) as rr,
            round(m.buy_lg_amount / 1e4, 2) as buy_lg_amount,
            round(m.net_mf_amount / 1e4, 2) as net_amount_wan
        FROM tushare.tushare_stock_daily d FINAL
        INNER JOIN tushare.tushare_moneyflow m FINAL 
            ON d.ts_code = m.ts_code AND d.trade_date = m.trade_date
        WHERE d.trade_date >= '20210101' 
          AND d.trade_date <= '20260425'
          AND d.open > 0
          AND d.close/d.open >= 1.05
          AND d.ts_code NOT LIKE '%%ST'
          AND d.ts_code NOT LIKE '688%%'
          AND d.ts_code NOT LIKE '30%%'
          AND d.ts_code NOT LIKE '920%%'
          AND m.net_mf_amount > 0
          AND m.buy_lg_amount > 5000000  -- 大单买入 > 500万
    ) s
    ANY LEFT JOIN tushare.tushare_stock_daily f FINAL ON s.ts_code = f.ts_code AND f.trade_date > s.trade_date
    ANY LEFT JOIN tushare.tushare_stock_daily f3 FINAL ON s.ts_code = f3.ts_code AND f3.trade_date > dateAdd(day, 2, s.trade_date)
    ANY LEFT JOIN tushare.tushare_stock_daily f5 FINAL ON s.ts_code = f5.ts_code AND f5.trade_date > dateAdd(day, 4, s.trade_date)
    ORDER BY s.trade_date
    SETTINGS allow_experimental_join_condition = 1
    """
    
    rows = ch_query(sql)
    print(f"[INFO] 找到 {len(rows)} 个信号。")
    
    # 检查数据时间跨度
    if rows:
        # 找出 trade_date 键（可能是 s.trade_date 或 trade_date）
        key = 'trade_date' if 'trade_date' in rows[0] else (list(rows[0].keys())[1] if len(rows[0]) > 1 else 'trade_date')
        dates = [r.get(key, r.get('s.trade_date')) for r in rows]
        dates = [d for d in dates if d]
        if dates:
            print(f"[INFO] 信号时间跨度: {min(dates)} 至 {max(dates)}")
        else:
            print(f"[INFO] 样本数: {len(rows)}, 第一行 keys: {list(rows[0].keys())}")

    if not rows:
        print("[ERROR] 无数据")
        return

    # 2. 计算指标
    ret_1d = []
    ret_3d = []
    ret_5d = []
    win_1d = 0
    win_3d = 0
    win_5d = 0
    count_1d = 0
    count_3d = 0
    count_5d = 0

    for r in rows:
        base = float(r['entry_close'])
        
        # 1 Day
        if r.get('close_t1'):
            c1 = float(r['close_t1'])
            ret = (c1 - base) / base
            ret_1d.append(ret)
            count_1d += 1
            if ret > 0: win_1d += 1
            
        # 3 Days
        if r.get('close_t3'):
            c3 = float(r['close_t3'])
            ret = (c3 - base) / base
            ret_3d.append(ret)
            count_3d += 1
            if ret > 0: win_3d += 1
            
        # 5 Days
        if r.get('close_t5'):
            c5 = float(r['close_t5'])
            ret = (c5 - base) / base
            ret_5d.append(ret)
            count_5d += 1
            if ret > 0: win_5d += 1

    # 3. 统计
    def stats(name, returns, wins, count):
        if count == 0: return
        rets = np.array(returns)
        avg_ret = float(np.mean(rets))
        std = float(np.std(rets))
        win_rate = float(wins) / count
        
        print(f"\n--- {name} ---")
        print(f"样本数: {count}")
        print(f"胜率:   {win_rate:.2%}")
        print(f"平均收益: {avg_ret:.2%}")
        print(f"波动率:   {std:.2%}")
        
        # 简单夏普 (假设无风险利率 0)
        if std > 0:
            sharpe = float(avg_ret / std)
            print(f"夏普:   {sharpe:.2f}")
        else:
            print(f"夏普:   N/A")

    stats("T+1 Day", ret_1d, win_1d, count_1d)
    stats("T+3 Days", ret_3d, win_3d, count_3d)
    stats("T+5 Days", ret_5d, win_5d, count_5d)

if __name__ == "__main__":
    main()
