#!/usr/bin/env python3
"""
直接 SQL 回测 — 测试所有 6 个变体
使用 clickhouse_driver 直接执行查询，绕过 grid_engine 的 FINAL 和子查询性能问题。
"""
from clickhouse_driver import Client
from datetime import datetime, date, timedelta
import json
import math
import sys

client = Client(host='172.24.224.1', port=9000, user='ai_reader', password='OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

# ─── 交易日历 ────────────────────────────────────────────────
rows = client.execute("""
    SELECT cal_date FROM tushare.tushare_trade_cal FINAL
    WHERE exchange='SSE' AND is_open=1 ORDER BY cal_date
""")
CAL_LIST = [r[0] for r in rows]
CAL_SET = set(CAL_LIST)

# ─── 排除列表 ────────────────────────────────────────────────
# 获取 ST 股票
st_rows = client.execute("SELECT DISTINCT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != ''")
ST_SET = set(r[0] for r in st_rows)

# 新股（近1年内上市）
new_rows = client.execute("""
    SELECT ts_code FROM tushare.tushare_new_share FINAL
    WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR)
""")
NEW_SET = set(r[0] for r in new_rows)

# 停牌股票（近10日）
suspend_rows = client.execute("""
    SELECT DISTINCT ts_code FROM tushare.tushare_suspend_d FINAL
    WHERE trade_date >= DATE_SUB('2026-05-11', INTERVAL 10 DAY)
""")
SUSPEND_SET = set(r[0] for r in suspend_rows)

print(f"交易日: {len(CAL_LIST)}, ST排除: {len(ST_SET)}, 新股排除: {len(NEW_SET)}, 停牌排除: {len(SUSPEND_SET)}")

# ─── 获取所有限价板数据 ──────────────────────────────────
print("加载 limit_list_d 数据...")
limit_rows = client.execute("""
    SELECT ts_code, trade_date, close, pct_chg,
           first_time, last_time, open_times, fd_amount
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date BETWEEN '2020-01-02' AND '2026-05-11'
      AND close > 0
""")
print(f"  共 {len(limit_rows)} 条记录")

# 过滤：排除 ST、新股、停牌
def should_exclude(ts_code, trade_date):
    if ts_code in ST_SET:
        return True
    if ts_code in NEW_SET:
        return True
    if ts_code in SUSPEND_SET:
        return True
    # 排除科创板(688)、创业板(300/301/30)、北交所(920)
    if ts_code.startswith('688'):
        return True
    if ts_code.startswith('300') or ts_code.startswith('301') or ts_code.startswith('30'):
        return True
    if ts_code.startswith('920'):
        return True
    return False

# 解析数据
data = []
for r in limit_rows:
    ts_code, trade_date, close, pct_chg, first_time, last_time, open_times, fd_amount = r
    if should_exclude(ts_code, trade_date):
        continue
    # 确保非空
    ft = first_time if first_time else ''
    lt = last_time if last_time else ''
    fd = fd_amount if fd_amount else 0
    data.append({
        'ts_code': ts_code,
        'trade_date': trade_date,
        'close': close,
        'pct_chg': pct_chg,
        'first_time': ft,
        'last_time': lt,
        'open_times': open_times,
        'fd_amount': fd
    })
print(f"  排除后: {len(data)} 条记录")

# ─── 获取退出价格 ──────────────────────────────────────────
# 收集所有需要的退出日期
def next_trade_day(entry_date, hold):
    if entry_date not in CAL_SET:
        # 找下一个交易日
        for d in CAL_LIST:
            if d >= entry_date:
                entry_date = d
                break
        else:
            return None
    idx = CAL_LIST.index(entry_date)
    target = idx + hold
    if 0 <= target < len(CAL_LIST):
        return CAL_LIST[target]
    return None

# 预计算所有退出日期
exit_needed = set()  # { (exit_date, ts_code) }
signal_info = {}  # { (ts_code, entry_date): {entry_close, ...} }

for d in data:
    ed = d['trade_date']
    for hp in [1, 3, 5]:
        ex_dt = next_trade_day(ed, hp)
        if ex_dt:
            exit_needed.add((ex_dt, d['ts_code']))
    signal_info[(d['ts_code'], ed)] = {
        'close': d['close'],
        'open_times': d['open_times'],
        'first_time': d['first_time'],
        'last_time': d['last_time'],
        'fd_amount': d['fd_amount'],
    }

print(f"需要查询的退出价格数: {len(exit_needed)}")

# 批量查询退出价格（按日期分批）
exit_prices = {}  # {(ts_code, exit_date): close}
exit_dates_group = {}
for ex_dt, ts_code in exit_needed:
    exit_dates_group.setdefault(ex_dt, []).append(ts_code)

batch_size = 5000
for ex_dt in sorted(exit_dates_group.keys()):
    codes = list(set(exit_dates_group[ex_dt]))
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        codes_str = ', '.join(f"'{c}'" for c in batch)
        rows = client.execute(f"""
            SELECT ts_code, close FROM tushare.tushare_stock_daily FINAL
            WHERE trade_date = '{ex_dt}' AND ts_code IN ({codes_str})
        """)
        for r in rows:
            exit_prices[(r[0], ex_dt)] = r[1]

print(f"查询到 {len(exit_prices)} 个退出价格")

# ─── 定义变体 ──────────────────────────────────────────────
def is_non_yizi(d):
    """非一字板：first_time != last_time"""
    ft = d['first_time']
    lt = d['last_time']
    return ft != '' and lt != '' and ft != lt

def variant_v1(d):
    """非一字+未开板"""
    return is_non_yizi(d) and d['open_times'] == 0

def variant_v2(d):
    """非一字+早封<10点"""
    return is_non_yizi(d) and d['first_time'] < '10:00'

def variant_v3(d):
    """非一字+午前<11:30"""
    return is_non_yizi(d) and d['first_time'] < '11:30'

def variant_v4(d):
    """非一字+有封单"""
    return is_non_yizi(d) and d['fd_amount'] > 0

def variant_v5(d):
    """纯非一字首板"""
    return is_non_yizi(d)

def variant_v6(d):
    """非一字+未开板+早封"""
    return is_non_yizi(d) and d['open_times'] == 0 and d['first_time'] < '10:00'

VARIANTS = {
    "V1_非一字+未开板": variant_v1,
    "V2_非一字+早封<10点": variant_v2,
    "V3_非一字+午前<11:30": variant_v3,
    "V4_非一字+有封单": variant_v4,
    "V5_纯非一字首板": variant_v5,
    "V6_非一字+未开板+早封": variant_v6,
}

# ─── 统计函数 ──────────────────────────────────────────────
def compute_stats(returns):
    n = len(returns)
    if n == 0:
        return {"signal_count": 0, "win_rate": 0, "win_count": 0, "avg_return": 0,
                "avg_win": 0, "avg_loss": 0, "ci_95_lower": 0, "ci_95_upper": 0}
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    nz = [r for r in returns if r != 0]
    avg_ret = sum(returns) / n
    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    # 标准差
    variance = sum((r - avg_ret) ** 2 for r in returns) / n if n > 1 else 0
    std = math.sqrt(variance)
    # 95% 威尔逊置信区间
    z = 1.96
    p = win_rate
    denominator = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    ci_lower = max(0, (center - margin) / denominator)
    ci_upper = min(1, (center + margin) / denominator)
    return {
        "signal_count": n,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_return": round(avg_ret, 6),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "ci_95_lower": round(ci_lower, 4),
        "ci_95_upper": round(ci_upper, 4),
    }

# ─── 回测每个变体 ──────────────────────────────────────────
all_results = {}
for vname, vfunc in VARIANTS.items():
    print(f"\n{'='*70}")
    print(f"回测: {vname}")
    print(f"{'='*70}")
    
    # 筛选信号
    signals = [d for d in data if vfunc(d)]
    print(f"  信号总数: {len(signals)}")
    
    if len(signals) == 0:
        all_results[vname] = {"error": "no_signals"}
        continue
    
    for hp in [1, 3, 5]:
        returns_list = []
        count_valid = 0
        count_missing = 0
        for d in signals:
            ed = d['trade_date']
            ex_dt = next_trade_day(ed, hp)
            if ex_dt is None:
                count_missing += 1
                continue
            ep = exit_prices.get((d['ts_code'], ex_dt))
            if ep and ep > 0 and d['close'] > 0:
                ret = (ep / d['close']) - 1
                returns_list.append(ret)
                count_valid += 1
            else:
                count_missing += 1
        
        stats = compute_stats(returns_list)
        print(f"  hold={hp}: n={stats['signal_count']}, WR={stats['win_rate']*100:.2f}%, "
              f"avg_ret={stats['avg_return']*100:.4f}%, CI_low={stats['ci_95_lower']*100:.2f}%"
              f" (缺失={count_missing})")
        all_results[f"{vname}_h{hp}"] = stats
    
    all_results[vname] = {"signal_count": len(signals)}

# ─── 汇总 ──────────────────────────────────────────────────
print("\n\n" + "="*70)
print("最终汇总（Close-to-Close 回测，入场=涨停日收盘价，退出=持有期收盘价）")
print("="*70)
print(f"{'变体':<30} {'n_1d':<8} {'WR_1d':<9} {'avg_1d':<12} {'CI_low_1d':<10} {'n_3d':<8} {'WR_3d':<9} {'avg_3d':<12} {'CI_low_3d':<10} {'n_5d':<8} {'WR_5d':<9} {'avg_5d':<12} {'CI_low_5d':<10}")
print("-"*130)
for vname in VARIANTS:
    h1 = all_results.get(f"{vname}_h1", {})
    h3 = all_results.get(f"{vname}_h3", {})
    h5 = all_results.get(f"{vname}_h5", {})
    print(f"{vname:<30} "
          f"{h1.get('signal_count', 0):<8} {h1.get('win_rate', 0)*100:<9.2f} {h1.get('avg_return', 0)*100:<12.4f} {h1.get('ci_95_lower', 0)*100:<10.2f} "
          f"{h3.get('signal_count', 0):<8} {h3.get('win_rate', 0)*100:<9.2f} {h3.get('avg_return', 0)*100:<12.4f} {h3.get('ci_95_lower', 0)*100:<10.2f} "
          f"{h5.get('signal_count', 0):<8} {h5.get('win_rate', 0)*100:<9.2f} {h5.get('avg_return', 0)*100:<12.4f} {h5.get('ci_95_lower', 0)*100:<10.2f}")

print("-"*130)
print("注: WR=胜率(收盘价入场→收盘价退出), avg_ret=平均收益率(%), CI_low=Wilson CI下限(%)")

# ─── 额外：次日开盘价回测（更贴近实战）───────────────────
print("\n\n" + "="*70)
print("补充回测：次日开盘价入场（更贴近实战）")
print("="*70)

# 获取次日开盘价
open_needed = set()
for d in data:
    ed = d['trade_date']
    next_dt = next_trade_day(ed, 1)
    if next_dt:
        open_needed.add((next_dt, d['ts_code']))

open_prices = {}
open_dates_group = {}
for ex_dt, ts_code in open_needed:
    open_dates_group.setdefault(ex_dt, []).append(ts_code)

for ex_dt in sorted(open_dates_group.keys()):
    codes = list(set(open_dates_group[ex_dt]))
    for i in range(0, len(codes), 5000):
        batch = codes[i:i+5000]
        codes_str = ', '.join(f"'{c}'" for c in batch)
        rows = client.execute(f"""
            SELECT ts_code, open FROM tushare.tushare_stock_daily FINAL
            WHERE trade_date = '{ex_dt}' AND ts_code IN ({codes_str})
        """)
        for r in rows:
            open_prices[(r[0], ex_dt)] = r[1]

print(f"  查询到 {len(open_prices)} 个开盘价")

# 回测：次日开盘买入，持有1/3/5日出
for vname, vfunc in VARIANTS.items():
    print(f"\n--- {vname} ---")
    signals = [d for d in data if vfunc(d)]
    print(f"  信号总数: {len(signals)}")
    
    for hp in [1, 3, 5]:
        returns_list = []
        for d in signals:
            ed = d['trade_date']
            entry_dt = next_trade_day(ed, 1)  # 次日开盘
            if entry_dt is None:
                continue
            entry_open = open_prices.get((d['ts_code'], entry_dt))
            if entry_open is None or entry_open <= 0:
                continue
            exit_dt = next_trade_day(entry_dt, hp-1)  # 从entry_dt后持hp天
            if exit_dt is None:
                continue
            exit_close = exit_prices.get((d['ts_code'], exit_dt))
            if exit_close is None or exit_close <= 0:
                continue
            ret = (exit_close / entry_open) - 1
            returns_list.append(ret)
        
        stats = compute_stats(returns_list)
        print(f"  hold={hp}d(次日开→收盘): n={stats['signal_count']}, WR={stats['win_rate']*100:.2f}%, "
              f"avg_ret={stats['avg_return']*100:.4f}%, CI_low={stats['ci_95_lower']*100:.2f}%")

# 保存结果
print("\n\n完成！结果已打印如上。")
