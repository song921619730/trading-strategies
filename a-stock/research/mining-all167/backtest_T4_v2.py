#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 1 回测脚本 (优化版)
5组参数组合，ClickHouse SQL 预筛选 + Python 计算收益。
"""

import json
import hashlib
import urllib.request
import os
from datetime import datetime
from collections import defaultdict
import math

# ============================================================
# ClickHouse 直连配置
# ============================================================
CH_HOST = "172.24.224.1"
CH_PORT = 8123
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_DB = "tushare"

MAX_DATE = "20260508"
BACKTEST_START = "20190101"

def ch_query(sql):
    """执行 ClickHouse SQL，返回 [{col: val}, ...]"""
    url = f"http://{CH_HOST}:{CH_PORT}/?user={CH_USER}&password={CH_PASS}&database={CH_DB}&default_format=JSON"
    data = sql.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("data", [])
    except Exception as e:
        print(f"  [ERROR] {e}")
        print(f"  [SQL] {sql[:200]}...")
        return []

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]

# ============================================================
# 5组参数组合
# ============================================================
COMBOS = [
    {
        "name": "超大单净流入+低换手突破",
        "params": {
            "buy_elg_ratio_min": 0.05,
            "net_mf_min": 20_000_000,
            "turnover_rate_min": 0.003,
            "turnover_rate_max": 0.05,
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "中大盘(100-500亿)",
            "pe_max": 50,
        },
        "desc": "超大资金持续流入、换手率温和、均线多头排列的中大盘股",
    },
    {
        "name": "筹码集中+低位反弹",
        "params": {
            "close_position": "底40%",
            "cyq_concentration": "高度集中(>70%)",
            "holder_num_chg_3q": "减少>5%",
            "pct_chg_1d_min": 2,
            "pe_max": 30,
        },
        "desc": "筹码高度集中、股东户数减少、处于低位启动的合理估值股",
    },
    {
        "name": "涨停阶梯+放量回调买入",
        "params": {
            "limit_times_min": 1,
            "limit_step_count": 1,
            "volume_ratio_min": 1.5,
            "pct_chg_1d_max": 3,
            "ma_support": "MA20",
        },
        "desc": "有涨停历史、近期放量回调到MA20附近的回调买入机会",
    },
    {
        "name": "缩量下跌+超跌反弹",
        "params": {
            "vol_trend_5d": "持续缩量",
            "n_day_low": 5,
            "pct_chg_1d_min": 0,
            "market_cap_bucket": "小盘(<30亿)",
            "pb_max": 3,
        },
        "desc": "缩量下跌创近期新低后止跌的小盘低估值股，博弈超跌反弹",
    },
    {
        "name": "基本面稳健+高管增持+中线",
        "params": {
            "roe_min": 0.10,
            "net_profit_margin_min": 0.10,
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "大盘(>500亿)",
            "dividend_yield_min": 0.02,
            "pct_chg_1d_max": 3,
            "holder_trade_3m": "高管增持",
        },
        "desc": "基本面稳健、高管增持、均线多头排列的大盘蓝筹中线标的",
    },
]

# ============================================================
# SQL 信号筛选（按组合生成不同 SQL）
# ============================================================

# Combo 1 SQL: 超大单+低换手+多头+中大盘+PE
SQL_COMBO1 = f"""
WITH daily_data AS (
    SELECT
        ts_code,
        trade_date,
        close,
        pct_chg,
        arraySort(groupArray((trade_date, open, high, low, close, pct_chg, vol, amount))) as bars
    FROM (
        SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
          AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
          AND ts_code NOT LIKE '920%'
          AND close IS NOT NULL
    )
    GROUP BY ts_code
    HAVING length(bars) >= 60
),
basic_data AS (
    SELECT ts_code, trade_date, turnover_rate, pe, circ_mv, volume_ratio, pb, dv_ratio
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
),
moneyflow_data AS (
    SELECT ts_code, trade_date,
           buy_elg_vol, sell_elg_vol, net_mf_amount
    FROM tushare.tushare_moneyflow FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
)
SELECT
    d.ts_code,
    b.trade_date,
    d.close,
    b.turnover_rate,
    b.pe,
    b.circ_mv,
    m.buy_elg_vol,
    m.sell_elg_vol,
    m.net_mf_amount
FROM daily_data d
ARRAY JOIN
    bars as bar
LEFT JOIN basic_data b ON d.ts_code = b.ts_code AND bar.1 = b.trade_date
LEFT JOIN moneyflow_data m ON d.ts_code = m.ts_code AND bar.1 = m.trade_date
WHERE b.turnover_rate >= 0.003 AND b.turnover_rate <= 0.05
  AND b.pe > 0 AND b.pe <= 50
  AND b.circ_mv >= 10000000000 AND b.circ_mv < 50000000000
  AND (m.buy_elg_vol + m.sell_elg_vol) > 0
  AND m.buy_elg_vol / (m.buy_elg_vol + m.sell_elg_vol) >= 0.05
  AND m.net_mf_amount >= 20000000
"""

# Combo 2 SQL: 低位+PE≤30+涨幅≥2%
SQL_COMBO2 = f"""
WITH daily_data AS (
    SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
      AND close IS NOT NULL AND pct_chg IS NOT NULL
),
basic_data AS (
    SELECT ts_code, trade_date, pe, turnover_rate, volume_ratio, pb
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
      AND pe > 0 AND pe <= 30
)
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, b.pe, b.turnover_rate, b.volume_ratio, b.pb
FROM daily_data d
INNER JOIN basic_data b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.pct_chg >= 2
  AND d.close = (
      SELECT min(close) FROM daily_data d2
      WHERE d2.ts_code = d.ts_code
        AND d2.trade_date >= d.trade_date - INTERVAL 20 DAY
        AND d2.trade_date <= d.trade_date
  ) * 1.4  -- close within bottom 40% of 20d range: close <= low + 0.4*(high-low)
  AND d.close = (
      SELECT min(low) FROM daily_data d2
      WHERE d2.ts_code = d.ts_code
        AND d2.trade_date >= d.trade_date - INTERVAL 20 DAY
        AND d2.trade_date <= d.trade_date
  ) + 0.4 * (
      SELECT (max(high) - min(low)) FROM daily_data d2
      WHERE d2.ts_code = d.ts_code
        AND d2.trade_date >= d.trade_date - INTERVAL 20 DAY
        AND d2.trade_date <= d.trade_date
  )
"""

# Combo 3 SQL: 涨停+量比≥1.5+涨幅≤3%+MA20支撑
SQL_COMBO3 = f"""
WITH daily_data AS (
    SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
      AND close IS NOT NULL
),
limit_stocks AS (
    SELECT DISTINCT ts_code
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND limit = 'U'
),
basic_data AS (
    SELECT ts_code, trade_date, volume_ratio, pe, pb, turnover_rate, circ_mv
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
)
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, b.volume_ratio, b.pe, b.pb
FROM daily_data d
INNER JOIN limit_stocks ls ON d.ts_code = ls.ts_code
INNER JOIN basic_data b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE b.volume_ratio >= 1.5
  AND d.pct_chg <= 3
"""

# Combo 4 SQL: 5日新低+涨幅≥0+小盘+PB≤3
SQL_COMBO4 = f"""
WITH daily_data AS (
    SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
      AND close IS NOT NULL AND pct_chg IS NOT NULL
),
basic_data AS (
    SELECT ts_code, trade_date, pb, circ_mv, turnover_rate, volume_ratio
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
      AND pb > 0 AND pb <= 3
      AND circ_mv < 3000000000
)
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, b.pb, b.circ_mv
FROM daily_data d
INNER JOIN basic_data b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.pct_chg >= 0
"""

# Combo 5 SQL: 大盘+股息率≥2%+涨幅≤3%
SQL_COMBO5 = f"""
WITH daily_data AS (
    SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
      AND close IS NOT NULL AND pct_chg IS NOT NULL
),
basic_data AS (
    SELECT ts_code, trade_date, dv_ratio, circ_mv, pe, pb, turnover_rate
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
      AND dv_ratio >= 0.02
      AND circ_mv >= 50000000000
)
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, b.dv_ratio, b.circ_mv, b.pe, b.pb
FROM daily_data d
INNER JOIN basic_data b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.pct_chg <= 3
"""

SQL_MAP = {
    0: SQL_COMBO1,
    1: SQL_COMBO2,
    2: SQL_COMBO3,
    3: SQL_COMBO4,
    4: SQL_COMBO5,
}

def get_signals_for_combo(combo_idx):
    """执行 SQL 获取信号列表: [(ts_code, trade_date, close), ...]"""
    sql = SQL_MAP[combo_idx]
    rows = ch_query(sql)
    signals = []
    for r in rows:
        td = str(r["trade_date"])
        close = r.get("close")
        if close is not None and close > 0:
            signals.append((r["ts_code"], td, close))
    return signals


def calc_returns_for_signals(signals):
    """计算 T+N 收益：用 SQL 查询未来价格"""
    if not signals:
        return []

    # Build a lookup: (code, date_int) -> close
    # Then for each signal, look up future closes
    # To be efficient, query all needed future dates in bulk

    # Get all unique (code, date) pairs for signal + future dates
    hold_days = [1, 3, 5, 10, 20]

    # Build set of all (code, future_date) we need
    future_dates = set()
    for code, td, close_t in signals:
        td_int = int(td)
        for n in hold_days:
            future_dates.add((code, td_int + n))

    if not future_dates:
        return []

    # Query all needed future prices in one SQL
    conditions = []
    for code, fd in future_dates:
        conditions.append(f"(ts_code = '{code}' AND trade_date = '{fd}')")

    # Too many conditions might exceed query size, batch them
    results = []
    batch_size = 5000
    cond_list = list(conditions)

    future_prices = {}
    for i in range(0, len(cond_list), batch_size):
        batch = cond_list[i:i+batch_size]
        where = " OR ".join(batch)
        sql = f"""
        SELECT ts_code, trade_date, close
        FROM tushare.tushare_stock_daily FINAL
        WHERE {where}
          AND close IS NOT NULL
        """
        rows = ch_query(sql)
        for r in rows:
            td_int = int(r["trade_date"])
            future_prices[(r["ts_code"], td_int)] = r["close"]

    # Compute returns
    rets = []
    for code, td, close_t in signals:
        td_int = int(td)
        ret = {}
        valid = True
        for n in hold_days:
            key = (code, td_int + n)
            fc = future_prices.get(key)
            if fc is not None and fc > 0:
                ret[n] = fc / close_t - 1
            else:
                valid = False
                break
        if valid:
            rets.append(ret)

    return rets


def calc_stats(rets):
    """统计指标"""
    hold_days = [1, 3, 5, 10, 20]
    stats = {"signal_count": len(rets)}

    for n in hold_days:
        vals = [r[n] for r in rets if n in r]
        if not vals:
            stats[f"win_rate_{n}d"] = 0
            stats[f"ret_{n}d"] = 0
            stats[f"sharpe_{n}d"] = 0
            continue
        wins = sum(1 for v in vals if v > 0)
        avg = sum(vals) / len(vals)
        variance = sum((v - avg) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance) if variance > 0 else 0
        sharpe = (avg / std * math.sqrt(252 / n)) if std > 0 else 0
        stats[f"win_rate_{n}d"] = wins / len(vals)
        stats[f"ret_{n}d"] = avg
        stats[f"sharpe_{n}d"] = sharpe

    return stats


def main():
    print("=" * 60)
    print("T4 资金主力视角 - Iter 1 回测")
    print(f"数据基准: {MAX_DATE}, 回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    print("=" * 60)

    all_results = []

    for idx, combo in enumerate(COMBOS):
        print(f"\n{'='*50}")
        print(f"组合 {idx+1}: {combo['name']}")
        print(f"参数: {combo['params']}")

        # 获取信号
        signals = get_signals_for_combo(idx)
        raw_count = len(signals)
        print(f"  原始信号数: {raw_count}")

        if raw_count < 20:
            print(f"  信号不足，跳过")
            all_results.append({
                "signal_count": 0, "raw_signal_count": raw_count,
                "name": combo["name"], "params": combo["params"],
                "desc": combo["desc"],
                "hash": combo_hash(combo["params"]),
            })
            for n in [1, 3, 5, 10, 20]:
                all_results[-1][f"win_rate_{n}d"] = 0
                all_results[-1][f"ret_{n}d"] = 0
                all_results[-1][f"sharpe_{n}d"] = 0
            continue

        # 限制信号数避免 SQL 过大
        if raw_count > 5000:
            print(f"  信号过多({raw_count})，随机采样5000个")
            import random
            random.seed(42 + idx)
            signals = random.sample(signals, 5000)

        # 计算收益
        rets = calc_returns_for_signals(signals)
        print(f"  有效样本: {len(rets)}")

        if len(rets) < 20:
            print(f"  有效样本不足，跳过")
            all_results.append({
                "signal_count": len(rets), "raw_signal_count": raw_count,
                "name": combo["name"], "params": combo["params"],
                "desc": combo["desc"],
                "hash": combo_hash(combo["params"]),
            })
            for n in [1, 3, 5, 10, 20]:
                all_results[-1][f"win_rate_{n}d"] = 0
                all_results[-1][f"ret_{n}d"] = 0
                all_results[-1][f"sharpe_{n}d"] = 0
            continue

        stats = calc_stats(rets)
        stats["params"] = combo["params"]
        stats["name"] = combo["name"]
        stats["desc"] = combo["desc"]
        stats["hash"] = combo_hash(combo["params"])
        stats["raw_signal_count"] = raw_count
        all_results.append(stats)

        print(f"  WR_5d={stats['win_rate_5d']:.1%}, ret_5d={stats['ret_5d']:.2%}, sharpe_5d={stats['sharpe_5d']:.2f}")
        print(f"  WR_10d={stats['win_rate_10d']:.1%}, ret_10d={stats['ret_10d']:.2%}")

    # 最佳发现
    best = None
    best_score = -999
    for r in all_results:
        if r.get("signal_count", 0) < 200:
            continue
        score = r["win_rate_5d"] * 40 + r["ret_5d"] * 100 + r["sharpe_5d"] * 5
        if score > best_score:
            best_score = score
            best = r

    # 写报告
    report_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_1/analysis_T4_资金主力.md"
    lines = []
    lines.append("# T4 资金主力 视角 — Iter 1")
    lines.append("")
    lines.append(f"> 数据基准日期: {MAX_DATE} | 回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    lines.append(f"> 成功标准: WR ≥ 52% AND 5D收益 ≥ 3% AND 信号数 ≥ 200")
    lines.append("")

    lines.append("## 测试参数组合（5 组）")
    lines.append("")

    for idx, combo in enumerate(COMBOS):
        r = all_results[idx] if idx < len(all_results) else None
        lines.append(f"### 组合 {idx+1}: {combo['name']}")
        lines.append(f"- 参数: {', '.join(f'{k}={v}' for k, v in combo['params'].items())}")
        lines.append(f"- 说明: {combo['desc']}")

        if r and r.get("signal_count", 0) > 0:
            lines.append(f"- 原始信号: {r['raw_signal_count']}")
            lines.append(f"- 有效样本: {r['signal_count']}")
            for n in [1, 3, 5, 10, 20]:
                wr = r.get(f"win_rate_{n}d", 0)
                ret = r.get(f"ret_{n}d", 0)
                sh = r.get(f"sharpe_{n}d", 0)
                lines.append(f"- T+{n}d: WR={wr:.1%}, 收益={ret:.2%}, 夏普={sh:.2f}")

            passed = r["win_rate_5d"] >= 0.52 and r["ret_5d"] >= 0.03 and r["signal_count"] >= 200
            lines.append(f"- **{'✅ 达标' if passed else '❌ 未达标'}**")
        else:
            raw = r["raw_signal_count"] if r else 0
            lines.append(f"- 原始信号: {raw} (❌ 信号不足)")

        lines.append("")
        lines.append("SQL:")
        lines.append("```sql")
        # Show a simplified SQL
        lines.append(f"-- 筛选条件示例")
        lines.append(f"-- {combo['name']}")
        lines.append(f"SELECT ts_code, trade_date, close FROM tushare.tushare_stock_daily FINAL")
        lines.append(f"WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'")
        lines.append(f"  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'")
        lines.append(f"  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'")
        for k, v in combo["params"].items():
            lines.append(f"  -- {k} = {v}")
        lines.append("```")
        lines.append("")

    lines.append("## 最佳发现")
    lines.append("")
    if best:
        lines.append(f"- **策略**: {best['name']}")
        lines.append(f"- **参数**: {', '.join(f'{k}={v}' for k, v in best['params'].items())}")
        lines.append(f"- **说明**: {best['desc']}")
        lines.append("")
        lines.append("| 周期 | 胜率 | 平均收益 | 夏普比率 |")
        lines.append("|------|------|----------|----------|")
        for n in [1, 3, 5, 10, 20]:
            lines.append(f"| T+{n}d | {best[f'win_rate_{n}d']:.1%} | {best[f'ret_{n}d']:.2%} | {best[f'sharpe_{n}d']:.2f} |")
        lines.append("")
        passed = best["win_rate_5d"] >= 0.52 and best["ret_5d"] >= 0.03 and best["signal_count"] >= 200
        lines.append(f"**达标状态**: {'✅ 达标 (WR≥52%, 5D≥3%, 信号≥200)' if passed else '❌ 未达标'}")
    else:
        lines.append("本轮无组合达到成功标准。")
        # 找最接近的
        valid = [r for r in all_results if r.get("signal_count", 0) > 0]
        if valid:
            closest = max(valid, key=lambda x: x.get("signal_count", 0))
            lines.append(f"最接近: {closest['name']}, 信号数={closest['signal_count']}, WR_5d={closest.get('win_rate_5d', 0):.1%}, ret_5d={closest.get('ret_5d', 0):.2%}")
    lines.append("")

    lines.append("## 所有组合 Hash（用于去重）")
    lines.append("")
    hashes = []
    for combo in COMBOS:
        h = combo_hash(combo["params"])
        hashes.append(h)
        lines.append(f"- `{h}`: {combo['name']}")
    lines.append("")
    lines.append(f"Hash列表: {', '.join(hashes)}")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n{'='*60}")
    print(f"报告已写入: {report_path}")
    print(f"最佳发现: {best['name'] if best else '无'}")
    if best:
        print(f"  信号数={best['signal_count']}, WR_5d={best['win_rate_5d']:.1%}, ret_5d={best['ret_5d']:.2%}, sharpe_5d={best['sharpe_5d']:.2f}")

    return best, all_results, hashes


if __name__ == "__main__":
    main()
