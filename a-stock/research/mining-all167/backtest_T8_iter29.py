#!/usr/bin/env python3
"""T8 量价形态挖掘 - Iter29 回测脚本
5组全新K线形态+量价配合参数组合，全量历史回测。
"""
import json, hashlib, math, os, sys
import urllib.request
from collections import defaultdict
from datetime import datetime

CH_HOST = "172.24.224.1"
CH_PORT = 8123
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_DB = "tushare"

MAX_DATE = "20260513"
BACKTEST_START = "20190101"

COMBOS = [
    {
        "name": "C1_长阳反包恐慌放量散户大单",
        "params": {
            "close_position": "底20%(20日)",
            "昨跌_max": -4,
            "今涨_min": 4,
            "阳线反包": True,        # 今日收阳 > 昨日最高 AND 昨收阴
            "amplitude_min": 7,
            "volume_ratio_min": 1.3,
            "sell_sm_gt_buy_sm": True,
            "buy_lg_gt_sell_lg": True,
            "circ_mv_max_wan": 500000,
        },
        "desc": "长阳反包昨日阴线(今收阳且close>prev_high)+恐慌昨跌≤-4%+今涨≥4%+振幅≥7%+VR≥1.3+散户割肉+大单接盘+底20%+CM≤50亿。经典阳包阴强反转形态+资金确认。",
    },
    {
        "name": "C2_温和恐慌振幅12PE持续放量无资金流",
        "params": {
            "close_position": "底20%(60日)",
            "昨跌_max": -3,
            "今涨_min": 3,
            "amplitude_min": 12,
            "volume_ratio_min": 1.3,
            "pe_max": 20,
            "持续放量": True,         # 5日均量>15日均量×1.1
            "circ_mv_max_wan": 1000000,
        },
        "desc": "温和恐慌(昨跌≤-3%)+今涨≥3%+极端振幅≥12%+VR≥1.3+PE≤20+60日底20%+CM≤100亿+持续放量。无任何资金流依赖，纯量价+估值+极端振幅模式。振幅≥12%是全新极端阈值测试。",
    },
    {
        "name": "C3_双日恐慌振幅8VR08ELG散户SPX",
        "params": {
            "close_position": "底20%(20日)",
            "双日恐慌_5_5": True,     # 前日跌≤-5% AND 前前日跌≤-5%
            "今涨_min": 1,
            "amplitude_min": 8,
            "volume_ratio_min": 0.8,
            "buy_elg_gte_sell_elg": True,
            "sell_sm_gt_buy_sm": True,
            "spx_prev_up": True,
            "circ_mv_max_wan": 300000,
        },
        "desc": "双日恐慌(连2日各跌≤-5%)+今涨≥1%+振幅≥8%+VR≥0.8+ELG+散户割肉+SPX前日涨+底20%+CM≤30亿。CROSS-6的VR放宽版(0.8替代1.3)+振幅≥8%替代具体VR阈值。测试VR放宽后信号扩容效果。",
    },
    {
        "name": "C4_连跌5日放量反弹大单底20",
        "params": {
            "close_position": "底20%(60日)",
            "连跌5日": True,          # 连续5日中至少4日下跌
            "今涨_min": 3,
            "amplitude_min": 6,
            "volume_ratio_min": 1.3,
            "buy_lg_gt_sell_lg": True,
            "circ_mv_max_wan": 300000,
        },
        "desc": "连续5日中至少4日下跌+今日涨≥3%+振幅≥6%+VR≥1.3+大单净买入+60日底20%+CM≤30亿。超长洗盘(5日)后放量反弹，比三连阴更彻底的清洗。无SPX无ELG，纯微观模式。",
    },
    {
        "name": "C5_曙光初现SPX大单比例55CM100大容量",
        "params": {
            "close_position": "底20%(20日)",
            "曙光初现": True,         # 昨收阴+今收阳 AND 今close > (昨open+昨close)/2
            "今涨_min": 2,
            "amplitude_min": 5,
            "volume_ratio_min": 1.0,
            "spx_prev_up": True,
            "buy_lg_ratio_min": 0.55,
            "circ_mv_max_wan": 1000000,
        },
        "desc": "曙光初现K线形态(经典反转)+SPX前日涨+大单买入比例≥55%+振幅≥5%+VR≥1.0+底20%+CM≤100亿。大容量版：CM放宽至100亿+buy_lg_ratio替代buy_lg>sell_lg简单过滤。",
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


def load_daily_data():
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


def load_daily_basic():
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
    idx = {}
    for r in rows:
        idx[(r["ts_code"], str(r["trade_date"]))] = r
    print(f"  Loaded {len(rows)} rows")
    return idx


def load_moneyflow():
    print("Loading moneyflow...")
    sql = f"""
    SELECT ts_code, trade_date, net_mf_amount,
           buy_lg_vol, sell_lg_vol,
           buy_elg_vol, sell_elg_vol,
           buy_sm_vol, sell_sm_vol
    FROM tushare_moneyflow FINAL
    WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
    """
    rows = ch_query(sql)
    idx = {}
    for r in rows:
        idx[(r["ts_code"], str(r["trade_date"]))] = r
    print(f"  Loaded {len(rows)} rows")
    return idx


def load_spx():
    print("Loading SPX index...")
    sql = f"""
    SELECT trade_date, pct_chg
    FROM tushare_index_global FINAL
    WHERE ts_code = 'SPX'
      AND trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
    ORDER BY trade_date
    """
    rows = ch_query(sql)
    spx_map = {}
    for r in rows:
        spx_map[str(r["trade_date"])] = r["pct_chg"]
    print(f"  Loaded {len(rows)} SPX dates")
    return spx_map


def get_vol_sma(vols, n):
    if len(vols) < n:
        return [None] * len(vols)
    result = [None] * (n - 1)
    for i in range(n - 1, len(vols)):
        result.append(sum(vols[i - n + 1:i + 1]) / n)
    return result


def check_candle_patterns(params, bars, i, pct, close, high, low, open_p, pre_close, pct_chgs):
    # ---- 昨跌约束 ----
    if params.get("昨跌_max") is not None:
        if i < 1: return False
        prev_pct = pct_chgs[i - 1]
        if prev_pct is None or prev_pct > params["昨跌_max"]:
            return False

    # ---- 今涨约束 ----
    if params.get("今涨_min") is not None:
        if pct < params["今涨_min"]:
            return False

    # ---- C1: 阳线反包 (今日阳线完全包裹昨日阴线) ----
    if params.get("阳线反包"):
        if i < 1: return False
        prev = bars[i - 1]
        prev_close = prev["close"]
        prev_open = prev["open"]
        # 昨收阴
        if prev_close >= prev_open:
            return False
        # 今收阳
        if close <= open_p:
            return False
        # 今close > 昨high (反包)
        if close <= prev["high"]:
            return False

    # ---- C2: 持续放量 ----
    if params.get("持续放量"):
        if i < 15: return False
        # 5日均量
        vol_list = []
        for j in range(i-4, i+1):
            v = bars[j].get("vol")
            if v is None: return False
            vol_list.append(v)
        ma5 = sum(vol_list) / 5
        # 15日均量
        vol_list_15 = []
        for j in range(i-14, i+1):
            v = bars[j].get("vol")
            if v is None: return False
            vol_list_15.append(v)
        ma15 = sum(vol_list_15) / 15
        if ma15 <= 0 or ma5 / ma15 < 1.1:
            return False

    # ---- C3: 双日恐慌(连2日跌≤-5%) ----
    if params.get("双日恐慌_5_5"):
        if i < 2: return False
        prev1 = pct_chgs[i - 1]
        prev2 = pct_chgs[i - 2]
        if prev1 is None or prev2 is None: return False
        if prev1 > -5 or prev2 > -5:
            return False

    # ---- C4: 连跌5日(连续5日中至少4日下跌) ----
    if params.get("连跌5日"):
        if i < 5: return False
        down_days = 0
        for k in range(1, 6):
            pp = pct_chgs[i - k]
            if pp is None: return False
            if pp < 0:
                down_days += 1
        if down_days < 4:
            return False

    # ---- C5: 曙光初现 ----
    if params.get("曙光初现"):
        if i < 1: return False
        prev = bars[i - 1]
        prev_close = prev["close"]
        prev_open = prev["open"]
        # 昨收阴
        if prev_close >= prev_open:
            return False
        # 今收阳
        if close <= open_p:
            return False
        # 今close > (昨open+昨close)/2
        mid_point = (prev_open + prev_close) / 2
        if close <= mid_point:
            return False

    return True


def filter_signals(combo, daily_by_code, daily_basic, moneyflow, spx_dates):
    params = combo["params"]
    need_moneyflow = any(k in params for k in [
        "buy_lg_ratio_min", "buy_elg_gte_sell_elg",
        "sell_sm_gt_buy_sm", "buy_lg_gt_sell_lg",
    ])
    need_spx = params.get("spx_prev_up", False)

    # For C3, also prepare 前2日 SPX
    signals = []
    skipped_no_data = 0

    for code, bars in daily_by_code.items():
        if len(bars) < 250:
            continue

        pct_chgs = [b["pct_chg"] for b in bars]

        for i in range(200, len(bars)):
            bar = bars[i]
            td = str(bar["trade_date"])
            close = bar["close"]
            high = bar["high"]
            low = bar["low"]
            open_p = bar["open"]
            pre_close = bar["pre_close"]
            pct = bar["pct_chg"]

            if close is None or close == 0 or high is None or low is None:
                continue
            if open_p is None or pre_close is None or pre_close == 0:
                continue
            if pct is None:
                continue

            # ===== 价格位置 (close_position) =====
            pos_20d = None
            pos_60d = None
            cp = params.get("close_position", "")

            if i >= 20:
                h20 = max(bars[j]["close"] for j in range(i-20, i+1))
                l20 = min(bars[j]["close"] for j in range(i-20, i+1))
                pos_20d = (close - l20) / (h20 - l20) if h20 - l20 > 0 else 0.5
            if i >= 60:
                h60 = max(bars[j]["close"] for j in range(i-60, i+1))
                l60 = min(bars[j]["close"] for j in range(i-60, i+1))
                pos_60d = (close - l60) / (h60 - l60) if h60 - l60 > 0 else 0.5

            if cp == "底20%(20日)":
                if pos_20d is None or pos_20d > 0.2:
                    continue
            elif cp == "底20%(60日)":
                if pos_60d is None or pos_60d > 0.2:
                    continue
            elif cp == "底40%":
                p = pos_20d if pos_20d is not None else pos_60d
                if p is None or p > 0.4:
                    continue

            # ===== 振幅约束 =====
            if "amplitude_min" in params:
                ampl = (high - low) / pre_close * 100
                if ampl < params["amplitude_min"]:
                    continue

            # ===== K线形态检查 =====
            if not check_candle_patterns(params, bars, i, pct, close, high, low, open_p, pre_close, pct_chgs):
                continue

            # ===== daily_basic fields =====
            db_key = (code, td)
            db = daily_basic.get(db_key)
            if db is None:
                skipped_no_data += 1
                continue

            if "volume_ratio_min" in params:
                vr = db.get("volume_ratio")
                if vr is None or vr < params["volume_ratio_min"]:
                    continue

            if "pe_max" in params:
                pe = db.get("pe", 0) or 0
                if pe <= 0 or pe > params["pe_max"]:
                    continue

            if "circ_mv_max_wan" in params:
                cmax = params["circ_mv_max_wan"]
                cmv = db.get("circ_mv", 0)
                if cmv is None or cmv > cmax:
                    continue

            # ===== SPX 前日涨 =====
            if need_spx:
                td_int = int(td.replace("-", ""))
                prev_spx_pct = None
                for spx_td_str in sorted(spx_dates.keys(), reverse=True):
                    spx_td_int = int(spx_td_str.replace("-", ""))
                    if spx_td_int < td_int:
                        prev_spx_pct = spx_dates[spx_td_str]
                        break
                if prev_spx_pct is None or prev_spx_pct <= 0:
                    continue

            # ===== 资金流 =====
            if need_moneyflow:
                mf = moneyflow.get((code, td))
                if mf is None:
                    continue

                if "buy_lg_ratio_min" in params:
                    buy_lg = mf.get("buy_lg_vol", 0) or 0
                    sell_lg = mf.get("sell_lg_vol", 0) or 0
                    total_lg = buy_lg + sell_lg
                    if total_lg <= 0 or buy_lg / total_lg < params["buy_lg_ratio_min"]:
                        continue

                if params.get("buy_elg_gte_sell_elg"):
                    buy_elg = mf.get("buy_elg_vol", 0) or 0
                    sell_elg = mf.get("sell_elg_vol", 0) or 0
                    if buy_elg <= sell_elg:
                        continue

                if params.get("sell_sm_gt_buy_sm"):
                    buy_sm = mf.get("buy_sm_vol", 0) or 0
                    sell_sm = mf.get("sell_sm_vol", 0) or 0
                    if sell_sm <= buy_sm:
                        continue

                if params.get("buy_lg_gt_sell_lg"):
                    buy_lg = mf.get("buy_lg_vol", 0) or 0
                    sell_lg = mf.get("sell_lg_vol", 0) or 0
                    if buy_lg <= sell_lg:
                        continue

            signals.append((code, td, close))

    if skipped_no_data > 0:
        print(f"  [INFO] Skipped {skipped_no_data} rows due to missing daily_basic data")
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
            stats[f"p10_{n}d"] = 0
        return stats
    stats = {"signal_count": signals_count}
    for n in hold_days:
        rets = [r[n] for r in results if r.get(n) is not None]
        if not rets:
            stats[f"win_rate_{n}d"] = 0
            stats[f"ret_{n}d"] = 0
            stats[f"sharpe_{n}d"] = 0
            stats[f"p10_{n}d"] = 0
            continue
        wins = sum(1 for r in rets if r > 0)
        avg_ret = sum(rets) / len(rets)
        std_ret = (sum((r - avg_ret) ** 2 for r in rets) / len(rets)) ** 0.5
        sharpe = (avg_ret / std_ret * math.sqrt(252 / n)) if std_ret > 0 else 0
        sorted_rets = sorted(rets)
        p10_count = max(1, len(sorted_rets) // 10)
        p10_avg = sum(sorted_rets[:p10_count]) / p10_count
        stats[f"win_rate_{n}d"] = wins / len(rets)
        stats[f"ret_{n}d"] = avg_ret
        stats[f"sharpe_{n}d"] = sharpe
        stats[f"p10_{n}d"] = p10_avg
    return stats


def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]


def generate_report(all_results, best):
    lines = []
    lines.append("# T8 量价形态挖掘 — Iter29")
    lines.append("")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"- 执行时间: {now_str} UTC+8")
    lines.append(f"- 数据基准: {MAX_DATE}")
    lines.append(f"- 回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    lines.append(f"- 历史最佳WR: 99.55%, 历史最佳R5: 25.23%")
    lines.append(f"- 历史最佳Sharpe: 20.227")
    lines.append(f"- 疲劳计数: 3 (连续未破纪录轮数)")
    lines.append("")
    lines.append("---")
    lines.append("")

    all_passed = []
    for idx, combo in enumerate(all_results):
        r = combo["results"]
        lines.append(f"### 组合 {idx+1}: {combo['name']}")
        lines.append(f"- 描述: {combo['desc']}")
        params_str = ", ".join(f"{k}={v}" for k, v in sorted(combo["params"].items()))
        lines.append(f"- 参数: {params_str}")
        lines.append(f"- Hash: `{combo['hash']}`")
        lines.append("")
        lines.append("#### 结果")
        lines.append("| 周期 | 信号数(原始) | 有效信号 | 胜率(WR) | 平均收益 | 夏普比率 | P10(最差10%) |")
        lines.append("|------|-------------|---------|----------|----------|----------|-------------|")
        total_signals = r["signal_count"]
        for n in [1, 3, 5, 10, 20]:
            wr = r.get(f"win_rate_{n}d", 0) * 100
            ret = r.get(f"ret_{n}d", 0) * 100
            sharpe = r.get(f"sharpe_{n}d", 0)
            p10 = r.get(f"p10_{n}d", 0) * 100
            effective = r.get(f"effective_{n}d", total_signals)
            lines.append(f"| T+{n}d | {total_signals} | | {wr:.2f}% | {ret:.2f}% | {sharpe:.3f} | {p10:+.2f}% |")
        lines.append("")

        wr5 = r.get("win_rate_5d", 0) * 100
        ret5 = r.get("ret_5d", 0) * 100
        cnt = r.get("signal_count", 0)
        passed = wr5 >= 52 and ret5 >= 3 and cnt >= 200
        lines.append(f"- **成功标准(WR>=52% AND Ret5d>=3% AND N>=200): {'✅ PASS' if passed else '❌ FAIL'}**")
        if not passed:
            reasons = []
            if wr5 < 52: reasons.append(f"WR_5d={wr5:.2f}%<52%")
            if ret5 < 3: reasons.append(f"Ret_5d={ret5:.2f}%<3%")
            if cnt < 200: reasons.append(f"信号数={cnt}<200")
            lines.append(f"- 未达标原因: {', '.join(reasons)}")
        if passed:
            all_passed.append(combo)
        lines.append("")

        # Record checking
        if passed:
            if wr5 > 99.55:
                lines.append(f"- **🏆🏆🏆 新全局WR纪录! {wr5:.2f}% > 99.55%**")
            if ret5 > 25.23:
                lines.append(f"- **🏆🏆🏆 新全局R5纪录! {ret5:.2f}% > 25.23%**")
            if r.get("sharpe_5d", 0) > 20.227:
                lines.append(f"- **🏆🏆🏆 新全局Sharpe纪录! {r['sharpe_5d']:.3f} > 20.227**")

        lines.append("---")
        lines.append("")

    lines.append("## 🏆 最佳发现")
    lines.append("")
    lines.append(f"### 最佳组合: {best['name']}")
    br = best["results"]
    lines.append(f"- 信号数: {br['signal_count']}")
    lines.append(f"- WR_5d: {br.get('win_rate_5d', 0)*100:.2f}%")
    lines.append(f"- Ret_5d: {br.get('ret_5d', 0)*100:.2f}%")
    lines.append(f"- Ret_10d: {br.get('ret_10d', 0)*100:.2f}%")
    lines.append(f"- Ret_20d: {br.get('ret_20d', 0)*100:.2f}%")
    lines.append(f"- Sharpe_5d: {br.get('sharpe_5d', 0):.3f}")
    lines.append(f"- P10_5d: {br.get('p10_5d', 0)*100:.2f}%")
    lines.append(f"- 参数: {best['params']}")
    lines.append(f"- 描述: {best['desc']}")
    lines.append(f"- Hash: `{best['hash']}`")
    lines.append("")

    wr5b = br.get("win_rate_5d", 0) * 100
    ret5b = br.get("ret_5d", 0) * 100
    cntb = br.get("signal_count", 0)
    passed_best = wr5b >= 52 and ret5b >= 3 and cntb >= 200
    lines.append(f"- **成功标准(WR>=52% AND Ret5d>=3% AND N>=200): {'✅ PASS' if passed_best else '❌ FAIL'}**")
    lines.append("")

    if passed_best:
        improvements = []
        if wr5b > 99.55:
            improvements.append(f"🏆 新全局WR纪录: {wr5b:.2f}% > 99.55% (+{wr5b-99.55:.2f}pp)")
        if ret5b > 25.23:
            improvements.append(f"🏆 新全局R5纪录: {ret5b:.2f}% > 25.23% (+{ret5b-25.23:.2f}pp)")
        if improvements:
            lines.append("### 🏆🏆🏆 全局纪录突破!")
            for imp in improvements:
                lines.append(f"- {imp}")
        else:
            lines.append("### ℹ️ PASS但未破全局纪录")
            if wr5b < 99.55:
                lines.append(f"- WR差距: {99.55-wr5b:.2f}pp")
            if ret5b < 25.23:
                lines.append(f"- R5差距: {25.23-ret5b:.2f}pp")
            lines.append(f"- Sharpe差距: {20.227-br.get('sharpe_5d', 0):.3f}")

    if len(all_passed) > 0:
        lines.append(f"\n### 📊 本轮统计")
        lines.append(f"- 测试组合: {len(all_results)}")
        lines.append(f"- PASS: {len(all_passed)}/{len(all_results)}")
        lines.append(f"- FAIL: {len(all_results)-len(all_passed)}/{len(all_results)}")
        lines.append(f"- fatigue_count: 3 (若无全局纪录突破则→ 4)")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 所有组合 Hash（用于去重）")
    lines.append("")
    for c in all_results:
        lines.append(f"- `{c['hash']}` → {c['name']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## SQL 查询骨架 (C1 示例)")
    lines.append("")
    lines.append("```sql")
    lines.append("-- 回测全量历史数据，使用Python本地计算K线形态、位置、MA等")
    lines.append("SELECT d.ts_code, d.trade_date, d.open, d.high, d.low, d.close, d.pre_close, d.pct_chg, d.vol, d.amount,")
    lines.append("       b.volume_ratio, b.circ_mv, b.pe, b.pb, b.dv_ratio, b.turnover_rate,")
    lines.append("       m.buy_lg_vol, m.sell_lg_vol, m.buy_elg_vol, m.sell_elg_vol, m.buy_sm_vol, m.sell_sm_vol")
    lines.append("FROM tushare_stock_daily FINAL d")
    lines.append("LEFT JOIN tushare_daily_basic FINAL b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date")
    lines.append("LEFT JOIN tushare_moneyflow FINAL m ON d.ts_code = m.ts_code AND d.trade_date = m.trade_date")
    lines.append("WHERE d.trade_date >= '20190101' AND d.trade_date <= '20260513'")
    lines.append("  AND d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%'")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("T8 量价形态挖掘 - Iter29")
    print("=" * 60)
    print(f"数据基准: {MAX_DATE}")
    print(f"回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    print()

    # Load data
    daily_by_code = load_daily_data()
    daily_basic = load_daily_basic()
    moneyflow = load_moneyflow()
    spx_dates = load_spx()

    all_results = []
    for idx, combo in enumerate(COMBOS):
        print(f"\n{'='*50}")
        print(f"组合 {idx+1}: {combo['name']}")
        print(f"参数: {combo['params']}")

        t0 = datetime.now()
        signals = filter_signals(combo, daily_by_code, daily_basic, moneyflow, spx_dates)
        t1 = datetime.now()
        print(f"  原始信号数: {len(signals)}, 耗时: {(t1-t0).total_seconds():.1f}s")

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
        print(f"  成功标准(WR>=52%, Ret5d>=3%, N>=200): {'✅ PASS' if passed else '❌ FAIL'}")

    # Find best by Sharpe_5d
    best = max(all_results, key=lambda c: c["results"].get("sharpe_5d", 0))
    best_wr = max(all_results, key=lambda c: c["results"].get("win_rate_5d", 0))

    print(f"\n{'='*60}")
    print("最佳发现(Sharpe):")
    print(f"  {best['name']}")
    br = best["results"]
    print(f"  WR_5d={br.get('win_rate_5d', 0)*100:.2f}%")
    print(f"  Ret_5d={br.get('ret_5d', 0)*100:.2f}%")
    print(f"  Sharpe_5d={br.get('sharpe_5d', 0):.3f}")
    print(f"  Signals={br.get('signal_count', 0)}")
    print(f"  最佳WR: {best_wr['name']} - {best_wr['results'].get('win_rate_5d',0)*100:.2f}%")

    # Generate report
    report_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_29/analysis_T8_量价形态.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    md = generate_report(all_results, best)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"报告已写入: {report_path}")

    # Print hashes for state.json update
    print(f"\n新组合Hashes:")
    for c in all_results:
        r = c["results"]
        wr5 = r.get("win_rate_5d", 0) * 100
        ret5 = r.get("ret_5d", 0) * 100
        print(f"  iter29_T8_{c['hash']}: {c['name']} → WR={wr5:.2f}%, R5={ret5:.2f}%")

    print("\nDone!")


if __name__ == "__main__":
    main()
