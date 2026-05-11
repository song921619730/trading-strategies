#!/usr/bin/env python3
"""T2 动力趋势视角 - Iter 1 回测脚本 (v2)
5组参数组合，统一参数空间随机采样，ClickHouse 回测。
"""

import json
import hashlib
import math
import urllib.request
from collections import defaultdict
from datetime import datetime

CH_HOST = "172.24.224.1"
CH_PORT = 8123
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_DB = "tushare"

MAX_DATE = "20260508"
BACKTEST_START = "20190101"

COMBOS = [
    {
        "name": "中大盘趋势+放量突破",
        "params": {
            "close_position": "顶40%",
            "ma_arrangement": "多头排列",
            "volume_ratio_min": 1.2,
            "pct_chg_1d_min": 2,
            "pct_chg_1d_max": 10,
            "market_cap_bucket": "中大盘(100-500亿)",
            "amplitude_min": 3,
            "turnover_rate_min": 0.01,
        },
        "desc": "中大盘趋势票放量突破，日涨幅2-10%确认动能的延续",
    },
    {
        "name": "小盘强势+放量上攻",
        "params": {
            "close_position": "顶40%",
            "pct_chg_1d_min": 3,
            "pct_chg_1d_max": 10,
            "volume_ratio_min": 1.5,
            "market_cap_bucket": "小盘(<30亿)",
            "turnover_rate_min": 0.02,
            "turnover_rate_max": 0.30,
            "amplitude_min": 3,
        },
        "desc": "小盘动量强势股，放量上攻，高换手确认活跃度",
    },
    {
        "name": "多头趋势+放量加速",
        "params": {
            "ma_arrangement": "多头排列",
            "volume_ratio_min": 1.5,
            "pct_chg_1d_min": 2,
            "pct_chg_1d_max": 10,
            "turnover_rate_min": 0.01,
            "ma_support": "MA10",
            "amplitude_min": 3,
        },
        "desc": "均线多头排列中放量加速的纯趋势信号，无市值限制",
    },
    {
        "name": "低位首阳放量反弹",
        "params": {
            "close_position": "底40%",
            "pct_chg_1d_min": 3,
            "pct_chg_1d_max": 10,
            "volume_ratio_min": 2.0,
            "turnover_rate_min": 0.01,
            "amplitude_min": 4,
        },
        "desc": "低位放量首阳，超跌反弹的动量反转模式",
    },
    {
        "name": "涨停后高开+换手接力",
        "params": {
            "ma_arrangement": "多头排列",
            "pct_chg_1d_min": 0,
            "pct_chg_1d_max": 6,
            "volume_ratio_min": 1.0,
            "amplitude_min": 5,
            "turnover_rate_min": 0.05,
            "turnover_rate_max": 0.40,
            "gap_direction": "向上跳空",
        },
        "desc": "涨停后接力（简化：高换手+高振幅+多头+跳空确认）",
    },
]


def ch_query(sql, timeout=180):
    url = f"http://{CH_HOST}:{CH_PORT}/?user={CH_USER}&password={CH_PASS}&database={CH_DB}&default_format=JSON"
    data = sql.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("data", [])
    except Exception as e:
        print(f"  [ERROR] {e}")
        return []


def load_all_daily():
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
    by_code = defaultdict(list)
    for r in rows:
        by_code[r["ts_code"]].append(r)
    print(f"  Loaded {len(rows)} rows, {len(by_code)} stocks")
    return by_code


def load_all_daily_basic():
    print("Loading daily_basic...")
    sql = f"""
    SELECT ts_code, trade_date, turnover_rate, volume_ratio, pe, pe_ttm, pb, dv_ratio, circ_mv
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
    print("Loading moneyflow...")
    sql = f"""
    SELECT ts_code, trade_date, net_mf_amount, buy_lg_vol, sell_lg_vol, buy_elg_vol, sell_elg_vol
    FROM tushare_moneyflow FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
    """
    rows = ch_query(sql)
    by_code_date = {}
    for r in rows:
        by_code_date[(r["ts_code"], str(r["trade_date"]))] = r
    print(f"  Loaded {len(rows)} rows")
    return by_code_date


def calc_ma(prices, n):
    if len(prices) < n:
        return [None] * len(prices)
    result = [None] * (n - 1)
    for i in range(n - 1, len(prices)):
        result.append(sum(prices[i - n + 1 : i + 1]) / n)
    return result


def is_ma_bullish(ma5, ma10, ma20, ma60):
    return (ma5 is not None and ma10 is not None and ma20 is not None and ma60 is not None
            and ma5 > ma10 > ma20 > ma60)


def get_price_position_20d(close, lows_20, highs_20):
    if highs_20 - lows_20 == 0:
        return 0.5
    return (close - lows_20) / (highs_20 - lows_20)


def filter_signals(combo, daily_by_code, daily_basic, moneyflow):
    params = combo["params"]
    signals = []

    need_moneyflow = any(k in params for k in ["net_mf_min", "buy_lg_ratio_min"])

    for code, bars in daily_by_code.items():
        if len(bars) < 120:
            continue

        closes = [b["close"] for b in bars if b["close"] is not None]
        if len(closes) < 120:
            continue

        highs = [b["high"] for b in bars if b["high"] is not None]
        lows = [b["low"] for b in bars if b["low"] is not None]

        ma5_list = calc_ma(closes, 5)
        ma10_list = calc_ma(closes, 10)
        ma20_list = calc_ma(closes, 20)
        ma60_list = calc_ma(closes, 60)
        ma120_list = calc_ma(closes, 120)

        for i in range(120, len(bars)):
            bar = bars[i]
            td = str(bar["trade_date"])
            close = bar["close"]
            if close is None or close == 0:
                continue

            # 价格位置
            pos_20d = None
            if "close_position" in params:
                if i >= 20:
                    h20 = max(closes[i - 20:i + 1])
                    l20 = min(closes[i - 20:i + 1])
                    pos_20d = get_price_position_20d(close, l20, h20)

            if params.get("close_position") == "顶40%":
                if pos_20d is None or pos_20d < 0.6:
                    continue
            elif params.get("close_position") == "底40%":
                if pos_20d is None or pos_20d > 0.4:
                    continue

            # 跳空
            if "gap_direction" in params:
                gap_dir = params["gap_direction"]
                pre_close = bar.get("pre_close")
                open_p = bar.get("open")
                if pre_close is None or open_p is None or pre_close == 0:
                    continue
                gap_pct = (open_p - pre_close) / pre_close * 100
                if gap_dir == "向上跳空" and gap_pct < 0.5:
                    continue
                if gap_dir == "向下跳空" and gap_pct > -0.5:
                    continue

            # 涨幅
            pct = bar.get("pct_chg")
            if pct is None:
                continue
            if "pct_chg_1d_min" in params and pct < params["pct_chg_1d_min"]:
                continue
            if "pct_chg_1d_max" in params and pct > params["pct_chg_1d_max"]:
                continue

            # 振幅
            if "amplitude_min" in params:
                high_pr = bar.get("high")
                low_pr = bar.get("low")
                pre_close = bar.get("pre_close")
                if high_pr is None or low_pr is None or pre_close is None or pre_close == 0:
                    continue
                ampl = (high_pr - low_pr) / pre_close * 100
                if ampl < params["amplitude_min"]:
                    continue

            # 量能
            db_key = (code, td)
            db = daily_basic.get(db_key)
            if db is None:
                continue

            if "volume_ratio_min" in params:
                vr = db.get("volume_ratio")
                if vr is None or vr < params["volume_ratio_min"]:
                    continue

            if "turnover_rate_min" in params:
                tr = db.get("turnover_rate")
                if tr is None or tr < params["turnover_rate_min"]:
                    continue
            if "turnover_rate_max" in params:
                tr = db.get("turnover_rate")
                if tr is None or tr >= params["turnover_rate_max"]:
                    continue

            # 均线
            ma5 = ma5_list[i]
            ma10 = ma10_list[i]
            ma20 = ma20_list[i]
            ma60 = ma60_list[i]

            if params.get("ma_arrangement") == "多头排列":
                if not is_ma_bullish(ma5, ma10, ma20, ma60):
                    continue

            if params.get("ma_support") == "MA10":
                if ma10 is None or close < ma10 * 0.97:
                    continue
            elif params.get("ma_support") == "MA20":
                if ma20 is None or close < ma20 * 0.97:
                    continue

            # 市值
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

            # 资金流（部分组合需要）
            if need_moneyflow:
                mf_key = (code, td)
                mf = moneyflow.get(mf_key)
                if mf is None:
                    continue
                if "net_mf_min" in params:
                    net_mf = mf.get("net_mf_amount", 0)
                    if net_mf is None or net_mf < params["net_mf_min"]:
                        continue
                if "buy_lg_ratio_min" in params:
                    total_lg = (mf.get("buy_lg_vol", 0) or 0) + (mf.get("sell_lg_vol", 0) or 0)
                    buy_lg = mf.get("buy_lg_vol", 0) or 0
                    if total_lg > 0 and buy_lg / total_lg < params["buy_lg_ratio_min"]:
                        continue

            signals.append((code, td, close))

    return signals


def calc_returns(signals, daily_by_code, hold_days=[1, 3, 5, 10, 20]):
    results = []
    for code, td, close_t in signals:
        bars = daily_by_code.get(code, [])
        if not bars:
            continue
        td_clean = td.replace("-", "")
        td_int = int(td_clean)
        signal_idx = None
        for j, b in enumerate(bars):
            b_td = str(b["trade_date"]).replace("-", "")
            if int(b_td) == td_int:
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
        if any(ret.get(n) is not None for n in hold_days):
            results.append(ret)
    return results


def calc_stats(results, signals_count, hold_days=[1, 3, 5, 10, 20]):
    if not results:
        stats = {"signal_count": signals_count}
        for n in hold_days:
            stats[f"win_rate_{n}d"] = 0
            stats[f"ret_{n}d"] = 0
            stats[f"sharpe_{n}d"] = 0
        return stats

    stats = {"signal_count": signals_count}
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
        sharpe = (avg_ret / std_ret * math.sqrt(252 / n)) if std_ret > 0 else 0
        stats[f"win_rate_{n}d"] = wins / len(rets)
        stats[f"ret_{n}d"] = avg_ret
        stats[f"sharpe_{n}d"] = sharpe
    return stats


def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]


def main():
    print("=" * 60)
    print("T2 动力趋势视角 - Iter 1 回测 (v2)")
    print("=" * 60)
    print(f"数据基准: {MAX_DATE}")
    print(f"回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    print()

    daily_by_code = load_all_daily()
    daily_basic = load_all_daily_basic()
    moneyflow = load_all_moneyflow()

    all_results = []
    for idx, combo in enumerate(COMBOS):
        print(f"\n{'='*50}")
        print(f"组合 {idx+1}: {combo['name']}")
        print(f"参数: {combo['params']}")

        t0 = datetime.now()
        signals = filter_signals(combo, daily_by_code, daily_basic, moneyflow)
        t1 = datetime.now()
        print(f"  信号数: {len(signals)}, 耗时: {(t1-t0).total_seconds():.1f}s")

        if len(signals) > 0:
            ret_data = calc_returns(signals, daily_by_code)
            stats = calc_stats(ret_data, len(signals))
        else:
            stats = calc_stats([], 0)

        combo["results"] = stats
        combo["hash"] = combo_hash(combo["params"])
        all_results.append(combo)

        for n in [1, 3, 5, 10, 20]:
            wr = stats.get(f"win_rate_{n}d", 0) * 100
            ret = stats.get(f"ret_{n}d", 0) * 100
            sharpe = stats.get(f"sharpe_{n}d", 0)
            print(f"  T+{n}d: WR={wr:.2f}%, Ret={ret:.2f}%, Sharpe={sharpe:.3f}")

        wr5 = stats.get("win_rate_5d", 0) * 100
        ret5 = stats.get("ret_5d", 0) * 100
        cnt = stats.get("signal_count", 0)
        passed = wr5 >= 52 and ret5 >= 3 and cnt >= 200
        print(f"  成功标准(WR>=52%, Ret5d>=3%, N>=200): {'PASS' if passed else 'FAIL'}")

    best = max(all_results, key=lambda c: c["results"].get("sharpe_5d", 0))

    report_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_1/analysis_T2_动力趋势.md"
    print(f"\n生成报告: {report_path}")

    md = generate_report(all_results, best)

    import os
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)

    print("Done!")
    print(f"\n最佳发现: {best['name']}")
    print(f"  WR_5d={best['results'].get('win_rate_5d', 0)*100:.2f}%")
    print(f"  Ret_5d={best['results'].get('ret_5d', 0)*100:.2f}%")
    print(f"  Sharpe_5d={best['results'].get('sharpe_5d', 0):.3f}")
    print(f"  Signals={best['results'].get('signal_count', 0)}")


def generate_report(all_results, best):
    lines = []
    lines.append("# T2 动力趋势视角 — Iter 1")
    lines.append("")
    lines.append(f"- 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8")
    lines.append(f"- 数据基准: {MAX_DATE}")
    lines.append(f"- 回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 测试参数组合（5 组）")
    lines.append("")

    for idx, combo in enumerate(all_results):
        r = combo["results"]
        lines.append(f"### 组合 {idx+1}: {combo['name']}")
        lines.append(f"- 描述: {combo['desc']}")
        params_str = ", ".join(f"{k}={v}" for k, v in sorted(combo["params"].items()))
        lines.append(f"- 参数: {params_str}")
        lines.append(f"- Hash: `{combo['hash']}`")
        lines.append("")
        lines.append("#### 结果")
        lines.append(f"| 周期 | 信号数 | 胜率(WR) | 平均收益 | 夏普比率 |")
        lines.append(f"|------|--------|----------|----------|----------|")
        for n in [1, 3, 5, 10, 20]:
            wr = r.get(f"win_rate_{n}d", 0) * 100
            ret = r.get(f"ret_{n}d", 0) * 100
            sharpe = r.get(f"sharpe_{n}d", 0)
            lines.append(f"| T+{n}d | {r['signal_count']} | {wr:.2f}% | {ret:.2f}% | {sharpe:.3f} |")
        lines.append("")

        lines.append("#### SQL 查询骨架")
        lines.append("```sql")
        lines.append("SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.open, d.pre_close")
        lines.append("FROM tushare_stock_daily FINAL d")
        lines.append("LEFT JOIN tushare_daily_basic FINAL b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date")
        lines.append("WHERE d.trade_date >= '20190101' AND d.trade_date <= '20260508'")
        lines.append("  AND d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%'")
        for k, v in sorted(combo["params"].items()):
            lines.append(f"  -- {k}={v}")
        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 最佳发现")
    lines.append("")
    lines.append(f"- 参数组合: {best['name']}")
    br = best["results"]
    lines.append(f"- 指标:")
    lines.append(f"  - 信号数: {br['signal_count']}")
    lines.append(f"  - WR_5d: {br.get('win_rate_5d', 0)*100:.2f}%")
    lines.append(f"  - Ret_5d: {br.get('ret_5d', 0)*100:.2f}%")
    lines.append(f"  - Ret_10d: {br.get('ret_10d', 0)*100:.2f}%")
    lines.append(f"  - Ret_20d: {br.get('ret_20d', 0)*100:.2f}%")
    lines.append(f"  - Sharpe_5d: {br.get('sharpe_5d', 0):.3f}")
    lines.append(f"  - Sharpe_10d: {br.get('sharpe_10d', 0):.3f}")
    lines.append(f"  - Sharpe_20d: {br.get('sharpe_20d', 0):.3f}")
    lines.append(f"- 描述: {best['desc']}")
    lines.append(f"- Hash: `{best['hash']}`")
    lines.append("")

    wr5 = br.get('win_rate_5d', 0) * 100
    ret5 = br.get('ret_5d', 0) * 100
    cnt = br.get('signal_count', 0)
    passed = wr5 >= 52 and ret5 >= 3 and cnt >= 200
    lines.append(f"- 成功标准(WR>=52% AND Ret5d>=3% AND N>=200): {'PASS' if passed else 'FAIL'}")
    if not passed:
        reasons = []
        if wr5 < 52: reasons.append(f"WR_5d={wr5:.2f}%<52%")
        if ret5 < 3: reasons.append(f"Ret_5d={ret5:.2f}%<3%")
        if cnt < 200: reasons.append(f"信号数={cnt}<200")
        lines.append(f"- 未达标原因: {', '.join(reasons)}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 所有组合 Hash（用于去重）")
    lines.append("")
    hashes = [c["hash"] for c in all_results]
    lines.append(", ".join(f"`{h}`" for h in hashes))
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
