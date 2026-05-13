#!/usr/bin/env python3
"""
grid_engine.py — A 股全表多因子回测引擎

用法:
    python3 grid_engine.py --config '{"entry_sql":"factor.rsi_bfq_6<30","tables":{"factor":"tushare_stk_factor_pro"},"hold_periods":[1,3,5]}'

导入使用:
    from grid_engine import run_grid, get_research_range
"""

import json
import math
import subprocess
import sys
from datetime import datetime, timedelta, date
from functools import lru_cache
from typing import Any

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

# ─── 数据可用范围（按表）──────────────────────────────────────
DATA_RANGES = {
    "stock_daily":      ("2019-12-30", date.today().isoformat()),
    "stk_factor_pro":   ("2020-01-02", date.today().isoformat()),
    "daily_basic":      ("2020-01-02", date.today().isoformat()),
    "moneyflow":        ("2020-01-02", date.today().isoformat()),
    "limit_list_d":     ("2020-01-02", date.today().isoformat()),
    "index_daily":      ("1993-06-02", date.today().isoformat()),
    "moneyflow_dc":     ("2026-04-24", date.today().isoformat()),
    "stock_basic":      ("1990-01-01", date.today().isoformat()),
}

TABLE_MAP = {
    "stock_daily":      "tushare_stock_daily",
    "stk_factor_pro":   "tushare_stk_factor_pro",
    "daily_basic":      "tushare_daily_basic",
    "moneyflow":        "tushare_moneyflow",
    "moneyflow_dc":     "tushare_moneyflow_dc",
    "limit_list_d":     "tushare_limit_list_d",
    "fina_indicator":   "tushare_fina_indicator",
    "stock_basic":      "tushare_stock_basic",
    "st":               "tushare_st",
    "suspend_d":        "tushare_suspend_d",
    "new_share":        "tushare_new_share",
    "trade_cal":        "tushare_trade_cal",
    "index_daily":      "tushare_index_daily",
}


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
    """缓存加载交易日历"""
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
    """
    从 entry_date 开始，找第 hold 个交易日。
    支持正负 hold。
    """
    cal = load_trade_cal()
    cal_list = cal["cal"]
    cal_set = cal["set"]

    # 找到 entry_date 在交易日历中的位置
    if entry_date not in cal_set:
        # 如果 entry_date 不是交易日，取下一个最近交易日
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
    # 超出范围（可能已退市）
    return None


# ─── 研究范围计算 ─────────────────────────────────────────────

def get_research_range(tables: list[str]) -> tuple[str, str]:
    """
    根据使用的表，自动计算可用的研究时间范围。
    返回 (start_date, end_date)，字符串 YYYY-MM-DD。
    如果跨度 < 365 天，返回 None。
    """
    # 从 table_name 或 short_name 获取范围
    start_dates = []
    end_dates = []
    for t in tables:
        tbl = TABLE_MAP.get(t, t)
        # 尝试从 DATA_RANGES 的 short name 找
        short = None
        for k, v in TABLE_MAP.items():
            if v == tbl:
                short = k
                break
        if short and short in DATA_RANGES:
            s, e = DATA_RANGES[short]
            start_dates.append(s)
            end_dates.append(e)
        else:
            # 没在预置表里，放宽
            pass

    if not start_dates:
        return ("2020-01-02", date.today().isoformat())

    start = max(start_dates)
    end = min(end_dates)

    # 检查跨度
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    if (e - s).days < 365:
        return None  # 数据不够

    return (start, end)


# ─── Entry SQL 生成 ───────────────────────────────────────────

def build_entry_sql(config: dict) -> str:
    """
    根据 config 组装 Entry SQL。
    自动添加排除逻辑（ST、新股、停牌）。
    ClickHouse 在 3+ 表 JOIN 时会保留列名前缀，所以必须用 AS 别名。
    """
    entry_cond = config["entry_sql"]
    tables = config["tables"]  # {alias: table_name, ...}
    max_signals = config.get("max_signals", 50000) or 50000
    start_date, end_date = get_research_range(list(tables.keys()))

    # 组装 FROM + LEFT JOIN
    aliases = list(tables.keys())
    main_alias = aliases[0]
    main_table = tables[main_alias]

    joins_str = ""
    if len(aliases) > 1:
        join_lines = []
        for alias in aliases[1:]:
            tbl = tables[alias]
            # ClickHouse 24.8 不支持 FINAL AS alias，用子查询包装
            join_lines.append(
                f"LEFT JOIN (SELECT * FROM tushare.{tbl} FINAL) AS {alias}\n"
                f"    ON {main_alias}.ts_code = {alias}.ts_code "
                f"AND {main_alias}.trade_date = {alias}.trade_date"
            )
        joins_str = "\n".join(join_lines)

    # 排除逻辑 - 直接用 NOT IN 子查询，不用 WITH UNION（ClickHouse 24.8 兼容性）
    exclude_st = f"{main_alias}.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')"
    exclude_new = f"{main_alias}.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('{end_date}', INTERVAL 1 YEAR))"
    exclude_suspend = f"{main_alias}.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_suspend_d FINAL WHERE trade_date >= DATE_SUB('{end_date}', INTERVAL 10 DAY))"

    sql = f"""
    SELECT DISTINCT
        {main_alias}.ts_code AS ts_code,
        {main_alias}.trade_date AS trade_date,
        {main_alias}.close AS entry_price,
        {main_alias}.pct_chg AS entry_pct
    FROM (SELECT * FROM tushare.{main_table} FINAL) AS {main_alias}
    {joins_str}
    WHERE ({entry_cond})
      AND {main_alias}.close > 0
      AND {main_alias}.trade_date BETWEEN '{start_date}' AND '{end_date}'
      AND {exclude_st}
      AND {exclude_new}
      AND {exclude_suspend}
    LIMIT {max_signals or 50000}
    """
    return sql


# ─── 退出价格查询 ─────────────────────────────────────────────

def fetch_exit_prices(exit_dates: dict[int, dict]) -> dict[int, dict]:
    """
    批量查询所有退出日的价格。
    exit_dates = {hold: {(ts_code, entry_date): exit_date, ...}}
    返回: {hold: {(ts_code, entry_date): {"price": float}, ...}}
    如果找不到退出价格（退市），price = 0
    """
    result = {}
    for hp, entries in exit_dates.items():
        result[hp] = {}
        # 按 exit_date 分组批量查询
        date_groups: dict[str, list] = {}
        for key, exit_dt in entries.items():
            if exit_dt is None:
                result[hp][key] = {"price": 0}  # 退市全损
                continue
            date_groups.setdefault(exit_dt, []).append(key[0])

        for exit_dt, codes in date_groups.items():
            codes_str = ", ".join(f"'{c}'" for c in codes)
            rows = ch_query(
                f"SELECT ts_code, close FROM tushare.tushare_stock_daily FINAL "
                f"WHERE trade_date = '{exit_dt}' "
                f"AND ts_code IN ({codes_str})"
            )
            price_map = {r["ts_code"]: r["close"] for r in rows}
            for key in date_groups[exit_dt]:
                ts_code = key[0]
                if ts_code in price_map and price_map[ts_code] > 0:
                    result[hp][key] = {"price": price_map[ts_code]}
                else:
                    result[hp][key] = {"price": 0}  # 停牌或退市

    return result


# ─── 统计计算 ─────────────────────────────────────────────────

def compute_stats(returns: list[float], hp: int) -> dict:
    """计算一组 forward_return 的统计量"""
    n = len(returns)
    if n == 0:
        return {"signal_count": 0, "win_rate": 0, "win_count": 0, "avg_return": 0,
                "avg_win": 0, "avg_loss": 0, "sharpe_ratio": 0,
                "ci_95_lower": 0, "ci_95_upper": 0}

    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    nz = [r for r in returns if r != 0]

    avg_ret = sum(returns) / n if n > 0 else 0
    win_rate = len(wins) / n if n > 0 else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0

    # 标准差
    variance = sum((r - avg_ret) ** 2 for r in returns) / n if n > 1 else 0
    std = math.sqrt(variance)

    # Sharpe (年化, 日线约250个交易日)
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

    # 95% 威尔逊置信区间
    z = 1.96
    p = win_rate
    denominator = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    ci_lower = max(0, (center - margin) / denominator)
    ci_upper = min(1, (center + margin) / denominator)

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
        "ci_95_lower": round(ci_lower, 4),
        "ci_95_upper": round(ci_upper, 4),
    }

# ─── 入口：run_grid ───────────────────────────────────────────

def run_grid(config: dict) -> dict:
    """
    运行全表多因子回测。
    
    Python 层处理: 交易日历查找（避免 ClickHouse 24.8 不支持的相关子查询）
    ClickHouse 层处理: entry 信号查询 + exit 价格批量查询

    config:
        entry_sql: SQL WHERE 条件
        tables: { alias: table_name, ... }
        hold_periods: [1, 3, 5, 10, 20]
        direction: "long" / "short"
        max_signals: 最大采样数（默认 50000，None=不限）
    """
    entry_sql = build_entry_sql(config)
    sys.stderr.write(f"[grid] Entry SQL ({len(entry_sql)} chars)\n")

    # Step 1: 查询 entry 信号（SQL 层已 LIMIT）
    signals = ch_query(entry_sql)
    if not signals:
        return {"error": "no_signals"}
    sys.stderr.write(f"[grid] Entry signals: {len(signals)}\n")

    hold_periods = config.get("hold_periods", [1, 3, 5, 10, 20])
    direction = config.get("direction", "long")

    # Step 2: 计算退出日期（Python 层，使用交易日历缓存）
    import random as _rnd
    trade_cal = load_trade_cal()
    cal_list = trade_cal["cal"]

    # 按日期分组：{entry_date: [(ts_code, entry_price), ...]}
    date_groups: dict[str, list[tuple[str, float]]] = {}
    for s in signals:
        date_groups.setdefault(s["trade_date"], []).append((s["ts_code"], s["entry_price"]))

    results = {}
    for hp in hold_periods:
        sys.stderr.write(f"[grid] hold={hp}: finding exit dates...\n")

        # 对每个 entry_date 找退出日
        exit_lookup: dict[tuple[str, str], str] = {}  # (ts_code, entry_date) → exit_date
        for entry_date in date_groups:
            if entry_date in trade_cal["set"]:
                idx = cal_list.index(entry_date)
                target_idx = idx + hp
                if 0 <= target_idx < len(cal_list):
                    exit_date = cal_list[target_idx]
                    for ts_code, _ in date_groups[entry_date]:
                        exit_lookup[(ts_code, entry_date)] = exit_date

        # Step 3: 按 exit_date 分组批量查询退出价
        date_code_groups: dict[str, list[str]] = {}
        code_entry_map: dict[tuple[str, str], tuple[str, float]] = {}
        for (ts_code, entry_date), exit_date in exit_lookup.items():
            date_code_groups.setdefault(exit_date, []).append(ts_code)
            code_entry_map[(ts_code, entry_date)] = (exit_date, [ep for _, ep in date_groups[entry_date] if _ == ts_code][0])

        # 批量查 exit 价格
        exit_price_map: dict[tuple[str, str], float] = {}
        # 构建反向映射: (ts_code, exit_date) → entry_date
        rev_map: dict[tuple[str, str], str] = {}
        for (ts_code, entry_date), exit_date in exit_lookup.items():
            rev_map[(ts_code, exit_date)] = entry_date

        for exit_date, codes in date_code_groups.items():
            unique_codes = list(set(codes))
            # 分批次，防止 URL 过长
            for i in range(0, len(unique_codes), 2000):
                batch = unique_codes[i:i + 2000]
                codes_str = ", ".join(f"'{c}'" for c in batch)
                rows = ch_query(
                    f"SELECT ts_code, close FROM tushare.tushare_stock_daily FINAL "
                    f"WHERE trade_date = '{exit_date}' "
                    f"AND ts_code IN ({codes_str})"
                )
                for r in rows:
                    entry_dt = rev_map.get((r["ts_code"], exit_date))
                    if entry_dt:
                        exit_price_map[(r["ts_code"], entry_dt)] = r["close"]

        # Step 4: 计算统计
        returns = []
        for s in signals:
            key = (s["ts_code"], s["trade_date"])
            if s["entry_price"] <= 0:
                continue  # 跳过异常价格
            exit_price = exit_price_map.get(key)
            if exit_price and exit_price > 0:
                ret = (exit_price / s["entry_price"]) - 1
                if direction == "short":
                    ret = -ret
                returns.append(ret)
            else:
                returns.append(-1.0)  # 退市全损

        stats = compute_stats(returns, hp)
        results[f"hold_{hp}"] = stats
        sys.stderr.write(f"[grid] hold={hp}: {stats['signal_count']} signals, WR={stats['win_rate']:.2%}\n")

    return results


# ─── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="JSON config")
    args = parser.parse_args()
    config = json.loads(args.config)
    result = run_grid(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
