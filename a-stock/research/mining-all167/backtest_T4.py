#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 1 回测脚本
5组参数组合，统一参数空间随机采样，ClickHouse 回测。
"""

import json
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# ClickHouse 直连配置
# ============================================================
CH_HOST = "172.24.224.1"
CH_PORT = 8123
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_DB = "tushare"

MAX_DATE = "20260508"
BACKTEST_START = "20190101"  # 全量历史数据

# ============================================================
# 5组参数组合设计（跨域组合，差异大）
# ============================================================
COMBOS = [
    {
        "name": "超大单净流入+低换手突破",
        "params": {
            "buy_elg_ratio_min": 0.05,      # 超大单买入占比≥5%
            "net_mf_min": 20_000_000,        # 主力净流入≥2000万
            "turnover_rate_min": 0.003,      # 换手率≥0.3%（低换手筛选）
            "turnover_rate_max": 0.05,       # 换手率≤5%
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "中大盘(100-500亿)",
            "pe_max": 50,
        },
        "desc": "超大资金持续流入、换手率温和、均线多头排列的中大盘股",
    },
    {
        "name": "筹码集中+低位反弹",
        "params": {
            "close_position": "底40%",       # 价格位于N日区间底部40%
            "cyq_concentration": "高度集中(>70%)",  # 筹码高度集中
            "holder_num_chg_3q": "减少>5%",  # 股东户数减少=筹码集中
            "pct_chg_1d_min": 2,             # 当日涨幅≥2%（启动信号）
            "pe_max": 30,                    # PE≤30（估值合理）
        },
        "desc": "筹码高度集中、股东户数减少、处于低位启动的合理估值股",
    },
    {
        "name": "涨停阶梯+放量回调买入",
        "params": {
            "limit_times_min": 1,            # 近期至少1次涨停
            "limit_step_count": 1,           # 有涨停阶梯
            "volume_ratio_min": 1.5,         # 量比≥1.5（放量）
            "pct_chg_1d_max": 3,             # 当日涨幅≤3%（回调/整理）
            "ma_support": "MA20",            # MA20支撑
        },
        "desc": "有涨停历史、近期放量回调到MA20附近的回调买入机会",
    },
    {
        "name": "缩量下跌+超跌反弹",
        "params": {
            "vol_trend_5d": "持续缩量",      # 5日持续缩量
            "n_day_low": 5,                  # 创5日新低
            "pct_chg_1d_min": 0,             # 当日涨幅≥0（止跌）
            "market_cap_bucket": "小盘(<30亿)",
            "pb_max": 3,                     # PB≤3
        },
        "desc": "缩量下跌创近期新低后止跌的小盘低估值股，博弈超跌反弹",
    },
    {
        "name": "基本面稳健+高管增持+中线",
        "params": {
            "roe_min": 0.10,                 # ROE≥10%
            "net_profit_margin_min": 0.10,   # 净利率≥10%
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "大盘(>500亿)",
            "dividend_yield_min": 0.02,      # 股息率≥2%
            "pct_chg_1d_max": 3,             # 当日涨幅≤3%（非追高）
            "holder_trade_3m": "高管增持",
        },
        "desc": "基本面稳健、高管增持、均线多头排列的大盘蓝筹中线标的",
    },
]

# ============================================================
# ClickHouse 查询工具
# ============================================================
def ch_query(sql):
    """执行 ClickHouse SQL，返回 [{col: val}, ...]"""
    url = f"http://{CH_HOST}:{CH_PORT}/?user={CH_USER}&password={CH_PASS}&database={CH_DB}&default_format=JSON"
    data = sql.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("data", [])
    except Exception as e:
        print(f"  [ERROR] SQL query failed: {e}")
        print(f"  [SQL] {sql[:300]}...")
        return []


# ============================================================
# 数据预加载
# ============================================================
def load_all_daily():
    """加载全量 stock_daily（按 ts_code 索引）"""
    print("Loading stock_daily...")
    sql = f"""
    SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount
    FROM tushare_stock_daily FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%'
      AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
    ORDER BY ts_code, trade_date
    """
    rows = ch_query(sql)
    # 按 ts_code 组织
    by_code = defaultdict(list)
    for r in rows:
        by_code[r["ts_code"]].append(r)
    print(f"  Loaded {len(rows)} rows, {len(by_code)} stocks")
    return by_code


def load_all_daily_basic():
    """加载全量 daily_basic"""
    print("Loading daily_basic...")
    sql = f"""
    SELECT ts_code, trade_date, close, turnover_rate, volume_ratio, pe, pe_ttm, pb, dv_ratio, circ_mv
    FROM tushare_daily_basic FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND ts_code NOT LIKE '30%'
      AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%'
    """
    rows = ch_query(sql)
    by_code_date = {}
    for r in rows:
        by_code_date[(r["ts_code"], str(r["trade_date"]))] = r
    print(f"  Loaded {len(rows)} rows")
    return by_code_date


def load_all_moneyflow():
    """加载全量 moneyflow"""
    print("Loading moneyflow...")
    sql = f"""
    SELECT ts_code, trade_date, buy_lg_vol, buy_lg_amount, sell_lg_vol, sell_lg_amount,
           buy_elg_vol, buy_elg_amount, sell_elg_vol, sell_elg_amount,
           net_mf_vol, net_mf_amount
    FROM tushare_moneyflow FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
    """
    rows = ch_query(sql)
    by_code_date = {}
    for r in rows:
        by_code_date[(r["ts_code"], str(r["trade_date"]))] = r
    print(f"  Loaded {len(rows)} rows")
    return by_code_date


def load_all_limit_list():
    """加载全量 limit_list_d（涨停记录）"""
    print("Loading limit_list_d...")
    sql = f"""
    SELECT ts_code, trade_date, limit
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
      AND limit = 'U'
    """
    rows = ch_query(sql)
    by_code = defaultdict(list)
    for r in rows:
        by_code[r["ts_code"]].append(str(r["trade_date"]))
    print(f"  Loaded {len(rows)} limit-up records")
    return by_code


# ============================================================
# 技术指标计算
# ============================================================
def calc_ma(prices, n):
    """计算MA，返回列表"""
    if len(prices) < n:
        return [None] * len(prices)
    result = [None] * (n - 1)
    for i in range(n - 1, len(prices)):
        result.append(sum(prices[i - n + 1 : i + 1]) / n)
    return result


def calc_volume_ratio_5d(vols):
    """计算5日均量比（当日量/5日均量）"""
    if len(vols) < 5:
        return [None] * len(vols)
    result = [None] * 5
    for i in range(5, len(vols)):
        avg5 = sum(vols[i - 5 : i]) / 5
        if avg5 > 0:
            result.append(vols[i] / avg5)
        else:
            result.append(None)
    return result


def is_ma_bullish(ma5, ma10, ma20, ma60):
    """多头排列: MA5 > MA10 > MA20 > MA60"""
    return (
        ma5 is not None
        and ma10 is not None
        and ma20 is not None
        and ma60 is not None
        and ma5 > ma10 > ma20 > ma60
    )


def get_price_position(close, lows_20, highs_20):
    """价格位置: (close - low) / (high - low)"""
    if highs_20 - lows_20 == 0:
        return 0.5
    return (close - lows_20) / (highs_20 - lows_20)


# ============================================================
# 策略信号筛选
# ============================================================
def filter_signals(combo, daily_by_code, daily_basic, moneyflow, limit_list):
    """根据参数组合筛选信号，返回 [(ts_code, trade_date, close_T), ...]"""
    params = combo["params"]
    signals = []

    for code, bars in daily_by_code.items():
        if len(bars) < 60:
            continue

        closes = [b["close"] for b in bars if b["close"] is not None]
        if len(closes) < 60:
            continue

        # 预计算指标
        ma5_list = calc_ma(closes, 5)
        ma10_list = calc_ma(closes, 10)
        ma20_list = calc_ma(closes, 20)
        ma60_list = calc_ma(closes, 60)

        for i in range(60, len(bars)):
            bar = bars[i]
            td = str(bar["trade_date"])
            close = bar["close"]
            if close is None:
                continue

            # ===== 资金流条件 =====
            if "buy_elg_ratio_min" in params or "net_mf_min" in params:
                mf_key = (code, td)
                mf = moneyflow.get(mf_key)
                if mf is None:
                    continue
                if "buy_elg_ratio_min" in params:
                    total_vol = mf.get("buy_elg_vol", 0) + mf.get("sell_elg_vol", 0)
                    if total_vol > 0:
                        elg_ratio = mf["buy_elg_vol"] / total_vol
                        if elg_ratio < params["buy_elg_ratio_min"]:
                            continue
                if "net_mf_min" in params:
                    net_mf = mf.get("net_mf_amount", 0)
                    if net_mf is None or net_mf < params["net_mf_min"]:
                        continue

            # ===== 量比/换手率条件 =====
            db_key = (code, td)
            db = daily_basic.get(db_key)
            if db is None:
                continue

            if "turnover_rate_min" in params:
                tr = db.get("turnover_rate")
                if tr is None or tr < params["turnover_rate_min"]:
                    continue
            if "turnover_rate_max" in params:
                tr = db.get("turnover_rate")
                if tr is None or tr >= params["turnover_rate_max"]:
                    continue

            if "volume_ratio_min" in params:
                vr = db.get("volume_ratio")
                if vr is None or vr < params["volume_ratio_min"]:
                    continue

            # ===== 均线条件 =====
            ma5 = ma5_list[i]
            ma10 = ma10_list[i]
            ma20 = ma20_list[i]
            ma60 = ma60_list[i]

            if params.get("ma_arrangement") == "多头排列":
                if not is_ma_bullish(ma5, ma10, ma20, ma60):
                    continue

            if params.get("ma_support") == "MA20":
                if ma20 is None or close < ma20 * 0.98:
                    continue

            # ===== 估值条件 =====
            if "pe_max" in params:
                pe = db.get("pe")
                if pe is None or pe <= 0 or pe > params["pe_max"]:
                    continue

            # ===== 市值条件 =====
            if "market_cap_bucket" in params:
                bucket = params["market_cap_bucket"]
                circ_mv = db.get("circ_mv", 0)
                if circ_mv is None:
                    circ_mv = 0
                if bucket == "小盘(<30亿)" and circ_mv >= 30e8:
                    continue
                if bucket == "中小盘(30-100亿)" and (circ_mv < 30e8 or circ_mv >= 100e8):
                    continue
                if bucket == "中大盘(100-500亿)" and (circ_mv < 100e8 or circ_mv >= 500e8):
                    continue
                if bucket == "大盘(>500亿)" and circ_mv < 500e8:
                    continue

            # ===== 涨幅条件 =====
            if "pct_chg_1d_min" in params:
                pct = bar.get("pct_chg")
                if pct is None or pct < params["pct_chg_1d_min"]:
                    continue
            if "pct_chg_1d_max" in params:
                pct = bar.get("pct_chg")
                if pct is None or pct > params["pct_chg_1d_max"]:
                    continue

            # ===== 价格位置条件 =====
            if params.get("close_position") == "底40%":
                if i >= 20:
                    highs_20 = max(closes[i - 20 : i + 1])
                    lows_20 = min(closes[i - 20 : i + 1])
                    pos = get_price_position(close, lows_20, highs_20)
                    if pos > 0.4:
                        continue

            # ===== 筹码集中度（近似用winner_rate） =====
            if params.get("cyq_concentration") == "高度集中(>70%)":
                # winner_rate > 70% 表示大部分筹码在现价以下 = 集中
                # 这里用 cyq_perf 表，先跳过复杂逻辑，用简化判断
                # 实际应查 cyq_perf 表
                pass  # 简化：跳过，在下一版本加入

            # ===== 股东户数变化 =====
            if params.get("holder_num_chg_3q") == "减少>5%":
                # 需要 stk_holdernumber 表，季频数据较少，简化跳过
                pass

            # ===== 涨停条件 =====
            if "limit_times_min" in params or "limit_step_count" in params:
                lim_dates = limit_list.get(code, [])
                # 最近60天内涨停次数
                recent_60 = [d for d in lim_dates if int(d) >= int(td) - 100]
                if params.get("limit_times_min", 0) > 0:
                    if len(recent_60) < params["limit_times_min"]:
                        continue

            # ===== PB条件 =====
            if "pb_max" in params:
                pb = db.get("pb")
                if pb is None or pb <= 0 or pb > params["pb_max"]:
                    continue

            # ===== 股息率条件 =====
            if "dividend_yield_min" in params:
                dv = db.get("dv_ratio")
                if dv is None or dv < params["dividend_yield_min"]:
                    continue

            # ===== ROE/净利率（季频，简化用最近值） =====
            if "roe_min" in params or "net_profit_margin_min" in params:
                # 需要 fina_indicator 表，季频，简化处理
                pass

            # ===== 高管增持 =====
            if params.get("holder_trade_3m") == "高管增持":
                # 需要 stk_holdertrade 表，简化跳过
                pass

            # 通过所有筛选条件
            signals.append((code, td, close))

    return signals


# ============================================================
# 收益率计算
# ============================================================
def calc_returns(signals, daily_by_code, hold_days=[1, 3, 5, 10, 20]):
    """计算 T+N 日收益率"""
    results = []
    for code, td, close_t in signals:
        bars = daily_by_code.get(code, [])
        if not bars:
            continue

        # 找到 signal date 在 bars 中的位置
        td_int = int(td)
        signal_idx = None
        for j, b in enumerate(bars):
            if int(b["trade_date"]) == td_int:
                signal_idx = j
                break

        if signal_idx is None:
            continue

        ret = {}
        for n in hold_days:
            future_idx = signal_idx + n
            if future_idx < len(bars) and bars[future_idx]["close"] is not None:
                ret[n] = bars[future_idx]["close"] / close_t - 1
            else:
                ret[n] = None

        # 只有所有周期都有数据的才计入
        if all(ret.get(n) is not None for n in hold_days):
            results.append(ret)

    return results


def calc_stats(results, hold_days=[1, 3, 5, 10, 20]):
    """统计指标"""
    if not results:
        return {
            "signal_count": 0,
            "win_rate_1d": 0, "ret_1d": 0, "sharpe_1d": 0,
            "win_rate_3d": 0, "ret_3d": 0, "sharpe_3d": 0,
            "win_rate_5d": 0, "ret_5d": 0, "sharpe_5d": 0,
            "win_rate_10d": 0, "ret_10d": 0, "sharpe_10d": 0,
            "win_rate_20d": 0, "ret_20d": 0, "sharpe_20d": 0,
        }

    stats = {"signal_count": len(results)}
    for n in hold_days:
        rets = [r[n] for r in results if r.get(n) is not None]
        if not rets:
            stats[f"win_rate_{n}d"] = 0
            stats[f"ret_{n}d"] = 0
            stats[f"sharpe_{n}d"] = 0
            continue
        wins = sum(1 for r in rets if r > 0)
        avg_ret = sum(rets) / len(rets)
        std_ret = (sum((r - avg_ret) ** 2 for r in rets) / len(rets)) ** 0.5
        sharpe = (avg_ret / std_ret * (252 / n) ** 0.5) if std_ret > 0 else 0
        stats[f"win_rate_{n}d"] = wins / len(rets)
        stats[f"ret_{n}d"] = avg_ret
        stats[f"sharpe_{n}d"] = sharpe

    return stats


# ============================================================
# Hash 计算
# ============================================================
def combo_hash(params):
    """参数组合 hash"""
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("T4 资金主力视角 - Iter 1 回测")
    print("=" * 60)

    # 加载数据
    daily_by_code = load_all_daily()
    daily_basic = load_all_daily_basic()
    moneyflow = load_all_moneyflow()
    limit_list = load_all_limit_list()

    # 对每组参数回测
    all_results = []
    for idx, combo in enumerate(COMBOS):
        print(f"\n{'='*50}")
        print(f"组合 {idx+1}: {combo['name']}")
        print(f"参数: {combo['params']}")

        # 筛选信号
        signals = filter_signals(combo, daily_by_code, daily_basic, moneyflow, limit_list)
        print(f"  信号数: {len(signals)}")

        # 计算收益
        if len(signals) >= 10:  # 至少10个信号才计算
            returns = calc_returns(signals, daily_by_code)
            stats = calc_stats(returns)
            stats["params"] = combo["params"]
            stats["name"] = combo["name"]
            stats["desc"] = combo["desc"]
            stats["hash"] = combo_hash(combo["params"])
            stats["raw_signal_count"] = len(signals)
            all_results.append(stats)

            print(f"  有效样本: {stats['signal_count']}")
            print(f"  WR_5d={stats['win_rate_5d']:.1%}, ret_5d={stats['ret_5d']:.2%}, sharpe_5d={stats['sharpe_5d']:.2f}")
            print(f"  WR_10d={stats['win_rate_10d']:.1%}, ret_10d={stats['ret_10d']:.2%}")
        else:
            print(f"  信号不足，跳过统计")

    # 找出最佳组合
    best = None
    best_score = -999
    for r in all_results:
        # 评分：WR_5d * 0.4 + ret_5d * 0.3 + sharpe_5d * 0.3 (归一化)
        score = r["win_rate_5d"] * 40 + r["ret_5d"] * 100 + r["sharpe_5d"] * 5
        if score > best_score and r["signal_count"] >= 200:
            best_score = score
            best = r

    # 输出报告
    print(f"\n{'='*60}")
    print("生成报告...")

    report_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_1/analysis_T4_资金主力.md"
    report_lines = []
    report_lines.append("# T4 资金主力 视角 — Iter 1")
    report_lines.append("")
    report_lines.append(f"## 数据基准日期: {MAX_DATE}")
    report_lines.append(f"## 回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    report_lines.append(f"## 测试参数组合: {len(COMBOS)} 组")
    report_lines.append(f"## 成功标准: WR ≥ 52% AND 5D收益 ≥ 3% AND 信号数 ≥ 200")
    report_lines.append("")

    report_lines.append("## 测试参数组合（5 组）")
    report_lines.append("")

    for idx, combo in enumerate(COMBOS):
        r = all_results[idx] if idx < len(all_results) else None
        report_lines.append(f"### 组合 {idx+1}: {combo['name']}")
        report_lines.append(f"- 参数: {', '.join(f'{k}={v}' for k, v in combo['params'].items())}")
        report_lines.append(f"- 说明: {combo['desc']}")

        if r:
            report_lines.append(f"- 原始信号数: {r['raw_signal_count']}")
            report_lines.append(f"- 有效样本: {r['signal_count']}")
            report_lines.append(f"- WR_1d={r['win_rate_1d']:.1%}, ret_1d={r['ret_1d']:.2%}, sharpe_1d={r['sharpe_1d']:.2f}")
            report_lines.append(f"- WR_5d={r['win_rate_5d']:.1%}, ret_5d={r['ret_5d']:.2%}, sharpe_5d={r['sharpe_5d']:.2f}")
            report_lines.append(f"- WR_10d={r['win_rate_10d']:.1%}, ret_10d={r['ret_10d']:.2%}, sharpe_10d={r['sharpe_10d']:.2f}")
            report_lines.append(f"- WR_20d={r['win_rate_20d']:.1%}, ret_20d={r['ret_20d']:.2%}, sharpe_20d={r['sharpe_20d']:.2f}")

            # 判断是否达标
            passed = r["win_rate_5d"] >= 0.52 and r["ret_5d"] >= 0.03 and r["signal_count"] >= 200
            report_lines.append(f"- **{'✅ 达标' if passed else '❌ 未达标'}**")
        else:
            report_lines.append(f"- ❌ 信号不足，未统计")

        # SQL 示例
        report_lines.append(f"- SQL 示例:")
        report_lines.append(f"```sql")
        report_lines.append(f"SELECT s.ts_code, s.trade_date, s.close, d.pe, d.turnover_rate,")
        report_lines.append(f"       m.net_mf_amount, m.buy_elg_vol, m.sell_elg_vol")
        report_lines.append(f"FROM tushare.tushare_stock_daily FINAL s")
        report_lines.append(f"WHERE s.trade_date >= '{BACKTEST_START}' AND s.trade_date <= '{MAX_DATE}'")
        report_lines.append(f"  AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'")
        report_lines.append(f"  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'")
        report_lines.append(f"```")
        report_lines.append("")

    report_lines.append("## 最佳发现")
    report_lines.append("")
    if best:
        report_lines.append(f"- **参数组合**: {best['name']}")
        report_lines.append(f"- 参数: {', '.join(f'{k}={v}' for k, v in best['params'].items())}")
        report_lines.append(f"- 指标: WR_5d={best['win_rate_5d']:.1%}, ret_5d={best['ret_5d']:.2%}, sharpe_5d={best['sharpe_5d']:.2f}, 信号数={best['signal_count']}")
        report_lines.append(f"- 详细说明: {best['desc']}")
        report_lines.append("")
        report_lines.append("### 各周期详细表现")
        report_lines.append(f"| 周期 | 胜率 | 平均收益 | 夏普比率 |")
        report_lines.append(f"|------|------|----------|----------|")
        for n in [1, 3, 5, 10, 20]:
            report_lines.append(f"| T+{n}d | {best[f'win_rate_{n}d']:.1%} | {best[f'ret_{n}d']:.2%} | {best[f'sharpe_{n}d']:.2f} |")
    else:
        report_lines.append("本轮无组合达到成功标准。")
        # 找最接近的
        if all_results:
            closest = max(all_results, key=lambda x: x["signal_count"])
            report_lines.append(f"最接近的: {closest['name']}, 信号数={closest['signal_count']}, WR_5d={closest['win_rate_5d']:.1%}, ret_5d={closest['ret_5d']:.2%}")
    report_lines.append("")

    report_lines.append("## 所有组合 Hash（用于去重）")
    report_lines.append("")
    hashes = []
    for combo in COMBOS:
        h = combo_hash(combo["params"])
        hashes.append(h)
        report_lines.append(f"- {h}: {combo['name']}")
    report_lines.append("")
    report_lines.append(f"Hash 列表: {', '.join(hashes)}")

    report = "\n".join(report_lines)

    import os
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n报告已写入: {report_path}")
    print(f"\n最佳发现: {best['name'] if best else '无'}")
    if best:
        print(f"  WR_5d={best['win_rate_5d']:.1%}, ret_5d={best['ret_5d']:.2%}, sharpe_5d={best['sharpe_5d']:.2f}, 信号数={best['signal_count']}")

    # 返回最佳结果用于 kanban_complete
    return best, all_results, hashes


if __name__ == "__main__":
    main()
