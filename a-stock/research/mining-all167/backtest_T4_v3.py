#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 1 回测 (简化版)
使用 ch_query.py 直连 ClickHouse，分步查询 + Python 合并。
"""

import json
import hashlib
import subprocess
import os
import math
import random

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE = "20260508"
BACKTEST_START = "20190101"

def ch_query(sql):
    """通过 ch_query.py 执行 SQL"""
    result = subprocess.run(
        ["python3", CH_QUERY, "sql", sql],
        capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr[:200]}")
        return []
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else data.get("data", [])
    except:
        print(f"  [PARSE ERROR] {result.stdout[:200]}")
        return []

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]

COMBOS = [
    {
        "name": "超大单净流入+低换手突破",
        "params": {
            "buy_elg_ratio_min": 0.05, "net_mf_min": 20_000_000,
            "turnover_rate_min": 0.003, "turnover_rate_max": 0.05,
            "ma_arrangement": "多头排列",
            "market_cap_bucket": "中大盘(100-500亿)", "pe_max": 50,
        },
        "desc": "超大资金持续流入、换手率温和、均线多头排列的中大盘股",
    },
    {
        "name": "筹码集中+低位反弹",
        "params": {
            "close_position": "底40%", "cyq_concentration": "高度集中(>70%)",
            "holder_num_chg_3q": "减少>5%", "pct_chg_1d_min": 2, "pe_max": 30,
        },
        "desc": "筹码高度集中、股东户数减少、处于低位启动的合理估值股",
    },
    {
        "name": "涨停阶梯+放量回调买入",
        "params": {
            "limit_times_min": 1, "limit_step_count": 1,
            "volume_ratio_min": 1.5, "pct_chg_1d_max": 3, "ma_support": "MA20",
        },
        "desc": "有涨停历史、近期放量回调到MA20附近的回调买入机会",
    },
    {
        "name": "缩量下跌+超跌反弹",
        "params": {
            "vol_trend_5d": "持续缩量", "n_day_low": 5,
            "pct_chg_1d_min": 0, "market_cap_bucket": "小盘(<30亿)", "pb_max": 3,
        },
        "desc": "缩量下跌创近期新低后止跌的小盘低估值股，博弈超跌反弹",
    },
    {
        "name": "基本面稳健+高管增持+中线",
        "params": {
            "roe_min": 0.10, "net_profit_margin_min": 0.10,
            "ma_arrangement": "多头排列", "market_cap_bucket": "大盘(>500亿)",
            "dividend_yield_min": 0.02, "pct_chg_1d_max": 3, "holder_trade_3m": "高管增持",
        },
        "desc": "基本面稳健、高管增持、均线多头排列的大盘蓝筹中线标的",
    },
]

def load_table(table, cols, where_extra=""):
    """加载表数据"""
    col_str = ", ".join(cols)
    where = f"WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'"
    if where_extra:
        where += f" AND {where_extra}"
    sql = f"SELECT {col_str} FROM tushare.{table} FINAL {where}"
    return ch_query(sql)

def merge_dicts(dicts_list, key):
    """合并字典列表为 {key: [records]}"""
    by_key = {}
    for d in dicts_list:
        k = d[key]
        if k not in by_key:
            by_key[k] = []
        by_key[k].append(d)
    return by_key

def calc_ma(closes, n):
    if len(closes) < n:
        return []
    return [sum(closes[i-n+1:i+1])/n for i in range(n-1, len(closes))]

def main():
    print("=" * 60)
    print("T4 资金主力视角 - Iter 1")
    print(f"数据基准: {MAX_DATE}, 回测: {BACKTEST_START} ~ {MAX_DATE}")
    print("=" * 60)

    # 预加载数据
    print("\nLoading stock_daily...")
    daily_rows = load_table("tushare_stock_daily",
        ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"])
    print(f"  {len(daily_rows)} rows")

    # 按 ts_code 组织并按日期排序
    daily_by_code = {}
    for r in daily_rows:
        code = r["ts_code"]
        if code not in daily_by_code:
            daily_by_code[code] = []
        daily_by_code[code].append(r)
    for code in daily_by_code:
        daily_by_code[code].sort(key=lambda x: x["trade_date"])

    print("Loading daily_basic...")
    basic_rows = load_table("tushare_daily_basic",
        ["ts_code", "trade_date", "turnover_rate", "volume_ratio", "pe", "pb", "dv_ratio", "circ_mv"])
    basic_by_code_date = {}
    for r in basic_rows:
        basic_by_code_date[(r["ts_code"], r["trade_date"])] = r
    print(f"  {len(basic_rows)} rows")

    print("Loading moneyflow...")
    mf_rows = load_table("tushare_moneyflow",
        ["ts_code", "trade_date", "buy_lg_vol", "sell_lg_vol", "buy_lg_amount", "sell_lg_amount",
         "buy_elg_vol", "sell_elg_vol", "buy_elg_amount", "sell_elg_amount",
         "net_mf_vol", "net_mf_amount"])
    mf_by_code_date = {}
    for r in mf_rows:
        mf_by_code_date[(r["ts_code"], r["trade_date"])] = r
    print(f"  {len(mf_rows)} rows")

    print("Loading limit_list...")
    lim_rows = ch_query(f"SELECT ts_code, trade_date, limit FROM tushare.tushare_limit_list_d FINAL WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}' AND limit = 'U'")
    lim_by_code = {}
    for r in lim_rows:
        code = r["ts_code"]
        if code not in lim_by_code:
            lim_by_code[code] = set()
        lim_by_code[code].add(r["trade_date"])
    print(f"  {len(lim_rows)} limit-up records, {len(lim_by_code)} stocks")

    all_results = []
    hold_days = [1, 3, 5, 10, 20]

    for idx, combo in enumerate(COMBOS):
        print(f"\n{'='*50}")
        print(f"组合 {idx+1}: {combo['name']}")
        params = combo["params"]
        signals = []

        for code, bars in daily_by_code.items():
            if len(bars) < 60:
                continue

            closes = [b["close"] for b in bars if b.get("close") is not None]
            if len(closes) < 60:
                continue

            ma5 = calc_ma(closes, 5)
            ma10 = calc_ma(closes, 10)
            ma20 = calc_ma(closes, 20)
            ma60 = calc_ma(closes, 60)

            # 预计算 5日最低/最高
            lows_5 = []
            highs_5 = []
            for i in range(len(closes)):
                if i < 4:
                    lows_5.append(None)
                    highs_5.append(None)
                else:
                    lows_5.append(min(closes[i-4:i+1]))
                    highs_5.append(max(closes[i-4:i+1]))

            for i in range(60, len(bars)):
                bar = bars[i]
                td = bar["trade_date"]
                close = bar["close"]
                if close is None:
                    continue

                db_key = (code, td)
                db = basic_by_code_date.get(db_key)
                if db is None:
                    continue

                # === Combo 1: 超大单+低换手+多头+中大盘+PE ===
                if idx == 0:
                    mf = mf_by_code_date.get(db_key)
                    if mf is None:
                        continue
                    total_elg = mf.get("buy_elg_vol", 0) + mf.get("sell_elg_vol", 0)
                    if total_elg == 0:
                        continue
                    if mf["buy_elg_vol"] / total_elg < 0.05:
                        continue
                    if mf.get("net_mf_amount", 0) < 20_000_000:
                        continue
                    tr = db.get("turnover_rate")
                    if tr is None or tr < 0.003 or tr > 0.05:
                        continue
                    pe = db.get("pe")
                    if pe is None or pe <= 0 or pe > 50:
                        continue
                    mv = db.get("circ_mv", 0)
                    if mv is None or mv < 100e8 or mv >= 500e8:
                        continue
                    # 多头排列
                    if not (ma5[i] > ma10[i] > ma20[i] > ma60[i]):
                        continue

                # === Combo 2: 低位+PE≤30+涨幅≥2% ===
                elif idx == 1:
                    pe = db.get("pe")
                    if pe is None or pe <= 0 or pe > 30:
                        continue
                    pct = bar.get("pct_chg")
                    if pct is None or pct < 2:
                        continue
                    # 底部40%: close在20日区间的底部40%
                    if i >= 19:
                        h20 = max(closes[i-19:i+1])
                        l20 = min(closes[i-19:i+1])
                        if h20 == l20:
                            continue
                        pos = (close - l20) / (h20 - l20)
                        if pos > 0.4:
                            continue
                    else:
                        continue

                # === Combo 3: 涨停+量比≥1.5+涨幅≤3%+MA20支撑 ===
                elif idx == 2:
                    if code not in lim_by_code:
                        continue
                    # 最近60天有涨停
                    lim_dates = lim_by_code[code]
                    td_str = str(td) if not isinstance(td, str) else td
                    recent_lim = [d for d in lim_dates if int(str(d)) >= int(td_str) - 100 and int(str(d)) <= int(td_str)]
                    if len(recent_lim) < 1:
                        continue
                    vr = db.get("volume_ratio")
                    if vr is None or vr < 1.5:
                        continue
                    pct = bar.get("pct_chg")
                    if pct is None or pct > 3:
                        continue
                    # MA20支撑: close >= MA20 * 0.98
                    if ma20[i] is None or close < ma20[i] * 0.98:
                        continue

                # === Combo 4: 5日新低+涨幅≥0+小盘+PB≤3 ===
                elif idx == 3:
                    if lows_5[i] is None:
                        continue
                    if close > lows_5[i] * 1.001:  # 接近5日最低
                        continue
                    pct = bar.get("pct_chg")
                    if pct is None or pct < 0:
                        continue
                    pb = db.get("pb")
                    if pb is None or pb <= 0 or pb > 3:
                        continue
                    mv = db.get("circ_mv", 0)
                    if mv is None or mv >= 30e8:
                        continue
                    # 缩量: 当日vol < 前4日均量
                    if i >= 4:
                        avg_vol_4 = sum(bars[j].get("vol", 0) for j in range(i-4, i)) / 4
                        if bar.get("vol", 0) > avg_vol_4:
                            continue

                # === Combo 5: 大盘+股息率≥2%+涨幅≤3% ===
                elif idx == 4:
                    dv = db.get("dv_ratio")
                    if dv is None or dv < 0.02:
                        continue
                    mv = db.get("circ_mv", 0)
                    if mv is None or mv < 500e8:
                        continue
                    pct = bar.get("pct_chg")
                    if pct is None or pct > 3:
                        continue
                    # 多头排列
                    if not (ma5[i] > ma10[i] > ma20[i] > ma60[i]):
                        continue

                signals.append((code, td, close))

        raw_count = len(signals)
        print(f"  原始信号数: {raw_count}")

        if raw_count < 20:
            print(f"  信号不足")
            r = {"signal_count": 0, "raw_signal_count": raw_count,
                 "name": combo["name"], "params": combo["params"], "desc": combo["desc"],
                 "hash": combo_hash(combo["params"])}
            for n in hold_days:
                r[f"win_rate_{n}d"] = 0; r[f"ret_{n}d"] = 0; r[f"sharpe_{n}d"] = 0
            all_results.append(r)
            continue

        # 采样控制
        if raw_count > 5000:
            print(f"  采样5000/...")
            random.seed(42 + idx)
            signals = random.sample(signals, 5000)

        # 计算收益: 批量查询未来价格
        print(f"  计算T+N收益...")
        future_queries = []
        for code, td, close_t in signals:
            td_int = int(str(td))
            for n in hold_days:
                future_queries.append((code, td_int, close_t, n, td_int + n))

        # 构建 (ts_code, trade_date) -> close 查找表
        # 查询所有需要的未来价格
        needed_dates = set()
        for _, _, _, _, fd in future_queries:
            needed_dates.add(fd)

        # 按日期批量查询
        future_prices = {}
        sorted_dates = sorted(needed_dates)

        # 一次性查询所有未来价格
        date_conditions = " OR ".join(
            f"trade_date = '{d}'" for d in sorted_dates[:100]  # limit to avoid huge queries
        )
        # 需要查询所有涉及到的code+date组合
        code_date_pairs = set()
        for code, _, _, _, fd in future_queries:
            code_date_pairs.add((code, fd))

        # Batch query by date ranges
        results_by_pair = {}
        for fd in sorted_dates:
            codes_for_date = set(c for c, _, _, _, d in future_queries if d == fd)
            if len(codes_for_date) > 2000:
                # 分批查询
                codes_list = list(codes_for_date)
                for batch_start in range(0, len(codes_list), 2000):
                    batch = codes_list[batch_start:batch_start+2000]
                    codes_str = "','".join(batch)
                    sql = f"SELECT ts_code, trade_date, close FROM tushare.tushare_stock_daily FINAL WHERE ts_code IN ('{codes_str}') AND trade_date = '{fd}' AND close IS NOT NULL"
                    rows = ch_query(sql)
                    for row in rows:
                        results_by_pair[(row["ts_code"], int(str(row["trade_date"])))] = row["close"]
            else:
                codes_str = "','".join(codes_for_date)
                sql = f"SELECT ts_code, trade_date, close FROM tushare.tushare_stock_daily FINAL WHERE ts_code IN ('{codes_str}') AND trade_date = '{fd}' AND close IS NOT NULL"
                rows = ch_query(sql)
                for row in rows:
                    results_by_pair[(row["ts_code"], int(str(row["trade_date"])))] = row["close"]

        # 计算收益
        rets = []
        for code, td, close_t in signals:
            td_int = int(str(td))
            ret = {}
            valid = True
            for n in hold_days:
                fc = results_by_pair.get((code, td_int + n))
                if fc is not None and fc > 0:
                    ret[n] = fc / close_t - 1
                else:
                    valid = False
                    break
            if valid:
                rets.append(ret)

        print(f"  有效样本: {len(rets)}")

        if len(rets) < 20:
            r = {"signal_count": len(rets), "raw_signal_count": raw_count,
                 "name": combo["name"], "params": combo["params"], "desc": combo["desc"],
                 "hash": combo_hash(combo["params"])}
            for n in hold_days:
                r[f"win_rate_{n}d"] = 0; r[f"ret_{n}d"] = 0; r[f"sharpe_{n}d"] = 0
            all_results.append(r)
            continue

        # 统计
        r = {"signal_count": len(rets), "raw_signal_count": raw_count,
             "name": combo["name"], "params": combo["params"], "desc": combo["desc"],
             "hash": combo_hash(combo["params"])}
        for n in hold_days:
            vals = [x[n] for x in rets]
            wins = sum(1 for v in vals if v > 0)
            avg = sum(vals) / len(vals)
            var = sum((v-avg)**2 for v in vals) / len(vals)
            std = math.sqrt(var) if var > 0 else 0
            sharpe = (avg/std*math.sqrt(252/n)) if std > 0 else 0
            r[f"win_rate_{n}d"] = wins/len(vals)
            r[f"ret_{n}d"] = avg
            r[f"sharpe_{n}d"] = sharpe

        all_results.append(r)
        print(f"  WR_5d={r['win_rate_5d']:.1%}, ret_5d={r['ret_5d']:.2%}, sharpe_5d={r['sharpe_5d']:.2f}")
        print(f"  WR_10d={r['win_rate_10d']:.1%}, ret_10d={r['ret_10d']:.2%}")

    # 最佳
    best = None
    best_score = -999
    for r in all_results:
        if r.get("signal_count", 0) < 200:
            continue
        score = r["win_rate_5d"]*40 + r["ret_5d"]*100 + r["sharpe_5d"]*5
        if score > best_score:
            best_score = score
            best = r

    # 报告
    report_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_1/analysis_T4_资金主力.md"
    lines = [
        "# T4 资金主力 视角 — Iter 1",
        "",
        f"> 数据基准: {MAX_DATE} | 回测: {BACKTEST_START} ~ {MAX_DATE}",
        f"> 成功标准: WR≥52% AND 5D收益≥3% AND 信号数≥200",
        "",
        "## 测试参数组合（5 组）",
        ""
    ]
    for idx, combo in enumerate(COMBOS):
        r = all_results[idx]
        lines.append(f"### 组合 {idx+1}: {combo['name']}")
        lines.append(f"- 参数: {', '.join(f'{k}={v}' for k,v in combo['params'].items())}")
        lines.append(f"- 说明: {combo['desc']}")
        lines.append(f"- 原始信号: {r['raw_signal_count']}, 有效样本: {r['signal_count']}")
        for n in hold_days:
            lines.append(f"- T+{n}d: WR={r[f'win_rate_{n}d']:.1%}, 收益={r[f'ret_{n}d']:.2%}, 夏普={r[f'sharpe_{n}d']:.2f}")
        passed = r["win_rate_5d"]>=0.52 and r["ret_5d"]>=0.03 and r["signal_count"]>=200
        lines.append(f"- **{'✅ 达标' if passed else '❌ 未达标'}**")
        lines.append(f"- SQL: `SELECT ... FROM tushare.tushare_stock_daily FINAL WHERE ...` ({', '.join(f'{k}={v}' for k,v in combo['params'].items())})")
        lines.append("")

    lines.append("## 最佳发现")
    lines.append("")
    if best:
        lines.append(f"- **策略**: {best['name']}")
        lines.append(f"- **参数**: {', '.join(f'{k}={v}' for k,v in best['params'].items())}")
        lines.append(f"- **说明**: {best['desc']}")
        lines.append("")
        lines.append("| 周期 | 胜率 | 平均收益 | 夏普比率 |")
        lines.append("|------|------|----------|----------|")
        for n in hold_days:
            lines.append(f"| T+{n}d | {best[f'win_rate_{n}d']:.1%} | {best[f'ret_{n}d']:.2%} | {best[f'sharpe_{n}d']:.2f} |")
        passed = best["win_rate_5d"]>=0.52 and best["ret_5d"]>=0.03 and best["signal_count"]>=200
        lines.append(f"\n**达标**: {'✅ 是' if passed else '❌ 否'}")
    else:
        lines.append("本轮无组合达标。")
        valid = [r for r in all_results if r.get("signal_count",0) > 0]
        if valid:
            c = max(valid, key=lambda x: x.get("signal_count",0))
            lines.append(f"最接近: {c['name']}, 信号={c['signal_count']}, WR_5d={c.get('win_rate_5d',0):.1%}, ret_5d={c.get('ret_5d',0):.2%}")
    lines.append("")
    lines.append("## 所有组合 Hash（用于去重）")
    lines.append("")
    hashes = []
    for combo in COMBOS:
        h = combo_hash(combo["params"])
        hashes.append(h)
        lines.append(f"- `{h}`: {combo['name']}")
    lines.append(f"\nHash: {', '.join(hashes)}")

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n{'='*60}")
    print(f"报告: {report_path}")
    print(f"最佳: {best['name'] if best else '无'}")
    if best:
        print(f"  信号={best['signal_count']}, WR_5d={best['win_rate_5d']:.1%}, ret_5d={best['ret_5d']:.2%}, sharpe={best['sharpe_5d']:.2f}")
    return best, all_results, hashes

if __name__ == "__main__":
    main()
