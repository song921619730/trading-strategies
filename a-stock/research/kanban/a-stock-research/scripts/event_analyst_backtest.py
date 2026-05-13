#!/usr/bin/env python3
"""
EventAnalyst 回测脚本 — 涨停首板(非一字) + 封板率>70% → 次日溢价做多

分析:
1. 查询 tushare_limit_list_d 的所有首板数据（limit_times=1）
2. 排除一字板: first_time = last_time
3. 从 tushare_limit_list_ths 获取 limit_up_suc_rate
4. 查询 tushare_stock_daily 获取次日 open/pct_chg
5. 回测: 非一字首板 + 封板率>=70% → 次日开盘买入, 持有1/3/5日

A股限制:
- 不做空，只做多
- 排除 ST、科创(688)、创业板(30)、北交所(920)
- 排除新股（上市<60天）
"""

import json
import math
import subprocess
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

# ─── ClickHouse 查询 ──────────────────────────────────────────

def ch_query(sql: str) -> list[dict]:
    """执行 ClickHouse SQL 查询，返回字典列表"""
    r = subprocess.run(
        ["python3", CH_SCRIPT, "sql", sql],
        capture_output=True, text=True, timeout=120
    )
    idx = r.stdout.find('[')
    if idx >= 0:
        return json.loads(r.stdout[idx:])
    sys.stderr.write(f"CH PARSE ERROR: {r.stderr[:300]}\n")
    sys.stderr.write(f"STDOUT: {r.stdout[:300]}\n")
    return []

# ─── 交易日历 ─────────────────────────────────────────────────

_TRADE_CAL_CACHE: dict = {}

def load_trade_cal() -> dict:
    if "cal" not in _TRADE_CAL_CACHE:
        rows = ch_query(
            "SELECT cal_date FROM tushare.tushare_trade_cal FINAL "
            "WHERE exchange='SSE' AND is_open=1 ORDER BY cal_date"
        )
        dates = [r["cal_date"] for r in rows]
        _TRADE_CAL_CACHE["cal"] = dates
        _TRADE_CAL_CACHE["set"] = set(dates)
    return _TRADE_CAL_CACHE

def next_trade_day(entry_date: str, hold: int) -> str | None:
    """从 entry_date 开始，找第 hold 个交易日"""
    cal = load_trade_cal()
    cal_list = cal["cal"]
    cal_set = cal["set"]
    
    if entry_date not in cal_set:
        for d in cal_list:
            if d >= entry_date:
                entry_date = d
                break
        else:
            return None
    
    idx = cal_list.index(entry_date)
    target_idx = idx + hold
    if 0 <= target_idx < len(cal_list):
        return cal_list[target_idx]
    return None

# ─── 信号查询 ─────────────────────────────────────────────────

def fetch_signals(start_year: int = 2020) -> list[dict]:
    """获取所有符合条件的信号"""
    
    sql = f"""
    SELECT 
        ld.trade_date AS signal_date,
        ld.ts_code,
        ld.close AS limit_close,
        ld.pct_chg AS limit_pct,
        ld.first_time,
        ld.last_time,
        ths.limit_up_suc_rate
    FROM (SELECT * FROM tushare.tushare_limit_list_d FINAL) AS ld
    LEFT JOIN (SELECT * FROM tushare.tushare_limit_list_ths FINAL) AS ths
        ON ld.ts_code = ths.ts_code AND ld.trade_date = ths.trade_date
    WHERE ld.limit_times = 1
      AND ld.first_time IS NOT NULL
      AND ld.first_time != '' 
      AND ld.first_time != '0'
      AND ld.first_time != ld.last_time  -- 非一字板
      AND ths.limit_up_suc_rate >= 0.7   -- 封板率>=70%
      AND ld.ts_code NOT LIKE '688%%'    -- 排除科创板
      AND ld.ts_code NOT LIKE '300%%'    -- 排除创业板
      AND ld.ts_code NOT LIKE '301%%'    -- 排除创业板
      AND ld.ts_code NOT LIKE '920%%'    -- 排除北交所
      AND ld.close > 0
      AND toYear(ld.trade_date) >= {start_year}
    ORDER BY ld.trade_date, ld.ts_code
    """
    
    return ch_query(sql)

# ─── 排除新股 ─────────────────────────────────────────────────

def load_new_stocks(end_date: str) -> set:
    """获取上市<60天的新股列表"""
    rows = ch_query(
        f"SELECT ts_code FROM tushare.tushare_new_share FINAL "
        f"WHERE ipo_date >= DATE_SUB('{end_date}', INTERVAL 60 DAY)"
    )
    return {r["ts_code"] for r in rows}

# ─── 排除 ST ──────────────────────────────────────────────────

def load_st_stocks(end_date: str) -> set:
    """获取ST股票列表"""
    rows = ch_query(
        f"SELECT ts_code FROM tushare.tushare_st FINAL "
        f"WHERE st_type IS NOT NULL AND st_type != '' AND trade_date <= '{end_date}'"
    )
    return {r["ts_code"] for r in rows}

# ─── 查询入场/退出价格 ──────────────────────────────────────

def fetch_entry_prices(signals: list[dict]) -> dict:
    """
    获取入场价格（信号日的下一个交易日的开盘价）。
    返回: {(ts_code, signal_date): {"entry_price": float, "entry_date": str}}
    """
    result = {}
    cal = load_trade_cal()
    
    # Group signals by their signal_date
    date_groups = defaultdict(list)
    for s in signals:
        date_groups[s["signal_date"]].append(s["ts_code"])
    
    # For each signal_date, find next trade date and query open prices
    for signal_date, codes in date_groups.items():
        entry_date = next_trade_day(signal_date, 1)
        if entry_date is None:
            continue
        
        # Query open prices for entry_date
        # Batch query
        batch_size = 2000
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            codes_str = ", ".join(f"'{c}'" for c in batch)
            rows = ch_query(
                f"SELECT ts_code, open, close FROM tushare.tushare_stock_daily FINAL "
                f"WHERE trade_date = '{entry_date}' "
                f"AND ts_code IN ({codes_str})"
            )
            price_map = {r["ts_code"]: r["open"] for r in rows if r["open"] and r["open"] > 0}
            
            for ts_code in batch:
                if ts_code in price_map:
                    result[(ts_code, signal_date)] = {
                        "entry_price": price_map[ts_code],
                        "entry_date": entry_date
                    }
    
    return result

def fetch_exit_prices(entry_map: dict, hold: int) -> dict:
    """
    获取退出价格。
    entry_map: {(ts_code, signal_date): {"entry_price": float, "entry_date": str}}
    返回: {(ts_code, signal_date): exit_price}
    """
    result = {}
    cal = load_trade_cal()
    
    # Group by exit_date
    exit_groups = defaultdict(list)
    for (ts_code, signal_date), info in entry_map.items():
        exit_date = next_trade_day(info["entry_date"], hold)
        if exit_date:
            exit_groups[exit_date].append((ts_code, signal_date))
    
    # Batch query
    for exit_date, items in exit_groups.items():
        codes = [item[0] for item in items]
        batch_size = 2000
        for i in range(0, len(codes), batch_size):
            batch_codes = codes[i:i+batch_size]
            batch_items = items[i:i+batch_size]
            codes_str = ", ".join(f"'{c}'" for c in batch_codes)
            rows = ch_query(
                f"SELECT ts_code, close FROM tushare.tushare_stock_daily FINAL "
                f"WHERE trade_date = '{exit_date}' "
                f"AND ts_code IN ({codes_str})"
            )
            price_map = {r["ts_code"]: r["close"] for r in rows}
            
            for ts_code, signal_date in batch_items:
                if ts_code in price_map and price_map[ts_code] > 0:
                    result[(ts_code, signal_date)] = price_map[ts_code]
                else:
                    result[(ts_code, signal_date)] = 0  # 退市/停牌
    
    return result

# ─── 统计 ─────────────────────────────────────────────────────

def compute_stats(returns: list[float], hp: int) -> dict:
    n = len(returns)
    if n == 0:
        return {"signal_count": 0, "win_rate": 0, "avg_return": 0}
    
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    
    avg_ret = sum(returns) / n
    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    
    # 标准差
    variance = sum((r - avg_ret) ** 2 for r in returns) / n if n > 1 else 0
    std = math.sqrt(variance)
    
    # Sharpe (年化)
    sharpe = (avg_ret / std * math.sqrt(250 / max(hp, 1))) if std > 0 and hp > 0 else 0
    
    # 最大回撤
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= (1 + r)
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    
    # 盈亏比
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    
    return {
        "signal_count": n,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_return": round(avg_ret, 6),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd, 4),
    }

# ─── 市场状态分析 ────────────────────────────────────────────

def get_market_regime(signals: list, returns: list[float], hold: int) -> dict:
    """按市场环境分组分析"""
    # 使用沪深300指数来划分市场状态
    # 获取信号期间的市场数据
    if not signals:
        return {}
    
    # 获取沪深300每日涨跌幅
    start_date = min(s["signal_date"] for s in signals)
    end_date = max(s["signal_date"] for s in signals)
    
    rows = ch_query(
        f"SELECT trade_date, pct_chg FROM tushare.tushare_index_daily FINAL "
        f"WHERE ts_code = '000300.SH' "
        f"AND trade_date BETWEEN '{start_date}' AND '{end_date}' "
        f"ORDER BY trade_date"
    )
    index_data = {r["trade_date"]: r["pct_chg"] for r in rows}
    
    # 按信号日市场涨跌分类
    market_returns = {"bull": [], "bear": [], "neutral": []}
    for s, r in zip(signals, returns):
        if s["signal_date"] in index_data:
            idx_pct = index_data[s["signal_date"]]
            if idx_pct >= 1.0:
                market_returns["bull"].append(r)
            elif idx_pct <= -1.0:
                market_returns["bear"].append(r)
            else:
                market_returns["neutral"].append(r)
    
    result = {}
    for regime, rets in market_returns.items():
        if rets:
            stats = compute_stats(rets, hold)
            result[regime] = stats
    return result

# ─── 主流程 ───────────────────────────────────────────────────

def run_backtest():
    print("=" * 70)
    print("EventAnalyst 回测: 涨停首板(非一字) + 封板率>70% → 次日溢价做多")
    print("=" * 70)
    
    # Step 1: 获取信号
    print("\n[Step 1] 查询信号...")
    signals = fetch_signals(start_year=2020)
    print(f"  原始信号数: {len(signals)}")
    
    if not signals:
        print("  没有信号，退出")
        return
    
    # 显示信号日期范围
    dates = sorted(set(s["signal_date"] for s in signals))
    print(f"  日期范围: {dates[0]} ~ {dates[-1]}")
    print(f"  交易日数: {len(dates)}")
    
    # Step 2: 排除新股和ST
    print("\n[Step 2] 排除新股和ST...")
    end_date = dates[-1]
    new_stocks = load_new_stocks(end_date)
    st_stocks = load_st_stocks(end_date)
    print(f"  新股(上市<60天): {len(new_stocks)}")
    print(f"  ST股票: {len(st_stocks)}")
    
    filtered_signals = [
        s for s in signals 
        if s["ts_code"] not in new_stocks 
        and s["ts_code"] not in st_stocks
    ]
    print(f"  排除后信号数: {len(filtered_signals)}")
    
    # Step 3: 获取入场价格（次日开盘）
    print("\n[Step 3] 获取入场价格（次日开盘价）...")
    entry_map = fetch_entry_prices(filtered_signals)
    print(f"  有入场价: {len(entry_map)}")
    
    # Step 4: 回测各持有期
    print("\n[Step 4] 回测各持有期...")
    hold_periods = [1, 3, 5]
    
    # 过滤：只有能入场的数据
    valid_signals = [s for s in filtered_signals if (s["ts_code"], s["signal_date"]) in entry_map]
    print(f"  有效信号（有入场价）: {len(valid_signals)}")
    
    if not valid_signals:
        print("  没有有效信号，退出")
        return
    
    results = {}
    for hp in hold_periods:
        print(f"\n  --- Hold={hp}日 ---")
        
        # Get exit prices
        exit_map = fetch_exit_prices(entry_map, hp)
        print(f"  有退出价: {len(exit_map)}")
        
        # Compute returns
        returns = []
        valid_for_stats = []
        for s in valid_signals:
            key = (s["ts_code"], s["signal_date"])
            if key in exit_map:
                entry_price = entry_map[key]["entry_price"]
                exit_price = exit_map[key]
                if entry_price > 0 and exit_price > 0:
                    ret = (exit_price / entry_price) - 1
                    returns.append(ret)
                    valid_for_stats.append(s)
        
        stats = compute_stats(returns, hp)
        stats["hold_period"] = hp
        results[f"hold_{hp}"] = stats
        
        print(f"  信号数: {stats['signal_count']}")
        print(f"  胜率: {stats['win_rate']:.2%}")
        print(f"  平均收益: {stats['avg_return']:.4%}")
        print(f"  平均赢: {stats['avg_win']:.4%}, 平均亏: {stats['avg_loss']:.4%}")
        print(f"  盈亏比: {stats['profit_factor']:.2f}")
        print(f"  Sharpe: {stats['sharpe_ratio']:.2f}")
        print(f"  最大回撤: {stats['max_drawdown']:.2%}")
        
        # 市场状态分析
        regime_stats = get_market_regime(valid_for_stats, returns, hp)
        if regime_stats:
            print(f"  市场环境分析:")
            for regime, rst in regime_stats.items():
                print(f"    {regime}: 信号={rst['signal_count']} 胜率={rst['win_rate']:.2%} 平均={rst['avg_return']:.4%}")
            results[f"hold_{hp}_regime"] = regime_stats
    
    return results, valid_signals, entry_map

# ─── 额外特征分析 ────────────────────────────────────────────

def analyze_features(signals, entry_map):
    """额外特征分析"""
    print("\n" + "=" * 70)
    print("特征分析")
    print("=" * 70)
    
    # 按封板率分组
    rate_groups = defaultdict(list)
    for s in signals:
        key = (s["ts_code"], s["signal_date"])
        if key in entry_map:
            rate = s["limit_up_suc_rate"]
            if rate >= 0.9:
                group = "90%+"
            elif rate >= 0.8:
                group = "80-90%"
            elif rate >= 0.7:
                group = "70-80%"
            else:
                continue
            rate_groups[group].append(s)
    
    print("\n按封板率分组（持有1日）:")
    for group in ["70-80%", "80-90%", "90%+"]:
        grp_signals = rate_groups.get(group, [])
        if grp_signals:
            returns = []
            for s in grp_signals:
                key = (s["ts_code"], s["signal_date"])
                if key in entry_map:
                    exit_map = fetch_exit_prices({key: entry_map[key]}, 1)
                    if key in exit_map and exit_map[key] > 0:
                        ret = (exit_map[key] / entry_map[key]["entry_price"]) - 1
                        returns.append(ret)
            
            if returns:
                stats = compute_stats(returns, 1)
                print(f"  {group}: 信号={stats['signal_count']} 胜率={stats['win_rate']:.2%} 平均={stats['avg_return']:.4%}")

if __name__ == "__main__":
    results, signals, entry_map = run_backtest()
    if signals:
        analyze_features(signals, entry_map)
    
    print("\n" + "=" * 70)
    print("回测完成")
    print("=" * 70)
