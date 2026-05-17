#!/usr/bin/env python3
"""T2 动量趋势挖掘 - Iter28 回测脚本
5组参数组合，统一参数空间随机采样，ClickHouse 全量历史回测。
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
        "name": "C1_底部放量暴涨超大单净买微盘",
        "params": {
            "close_position": "底20%(20日)",
            "pct_chg_min": 4,
            "pct_chg_max": 10,
            "volume_ratio_min": 1.3,
            "amplitude_min": 6,
            "buy_elg_gte_sell_elg": True,
            "circ_mv_max_wan": 300000,
        },
        "desc": "底部放量大阳+超大单净买入+微盘≤30亿。T8 C3e恐慌反转模式的动量版(涨≥4%代替恐慌反转)，测试动量+机构确认的确定性",
    },
    {
        "name": "C2_底部放量持续放量净流入SPX",
        "params": {
            "close_position": "底20%(20日)",
            "pct_chg_min": 3,
            "pct_chg_max": 10,
            "volume_ratio_min": 1.0,
            "amplitude_min": 5,
            "net_mf_positive": True,
            "spx_prev_up": True,
            "持续放量5d": 1.05,
            "circ_mv_max_wan": 500000,
        },
        "desc": "SPX宏观窗口+底部放量+持续放量+净流入，经典T2动量模式的宏观+资金双确认版",
    },
    {
        "name": "C3_60日深底暴涨SPX前日涨微盘",
        "params": {
            "close_position": "底20%(60日)",
            "pct_chg_min": 5,
            "pct_chg_max": 10,
            "volume_ratio_min": 1.3,
            "amplitude_min": 7,
            "spx_prev_up": True,
            "circ_mv_max_wan": 300000,
        },
        "desc": "60日深底(更深的底部安全边际)+暴涨≥5%+高振幅≥7%+SPX前日涨宏观窗口+微盘极致弹性，SPX-NEG的T2动量版(恐慌→动量)",
    },
    {
        "name": "C4_底部放量大单比例高换手持续放量",
        "params": {
            "close_position": "底20%(20日)",
            "pct_chg_min": 3,
            "pct_chg_max": 10,
            "volume_ratio_min": 1.2,
            "amplitude_min": 5,
            "buy_lg_ratio_min": 0.50,
            "持续放量5d": 1.05,
            "circ_mv_max_wan": 500000,
            "turnover_rate_min": 0.01,
        },
        "desc": "迭代24 T2-C4的buy_lg_ratio精炼版(0.50替代原始C4的buy_lg>sell_lg)+持续放量+高换手，验证大单比例>50%是否比原始C4更优",
    },
    {
        "name": "C5_底部散户割肉大单接盘持续放量微盘",
        "params": {
            "close_position": "底20%(20日)",
            "pct_chg_min": 3,
            "pct_chg_max": 10,
            "volume_ratio_min": 1.3,
            "amplitude_min": 5,
            "sell_sm_gt_buy_sm": True,
            "buy_lg_gt_sell_lg": True,
            "持续放量5d": 1.05,
            "circ_mv_max_wan": 300000,
        },
        "desc": "Iter24 T2-C1的最佳参数验证版: 底部放量+散户割肉+大单接盘+持续放量+微盘。之前C1用了多头排列失败，去掉该条件重新测试",
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
    """Load stock daily data."""
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
    """Load daily_basic for volume_ratio, turnover_rate, pe, pb, circ_mv etc."""
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
    """Load moneyflow data."""
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
    """Load SPX index data for macro filter."""
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


def calc_ma(prices, n):
    """Calculate moving average."""
    if len(prices) < n:
        return [None] * len(prices)
    result = [None] * (n - 1)
    for i in range(n - 1, len(prices)):
        result.append(sum(prices[i - n + 1:i + 1]) / n)
    return result


def is_ma_bullish(ma5, ma10, ma20, ma60):
    """Check if MA is bullish (多头排列: 5>10>20>60)."""
    return (ma5 is not None and ma10 is not None and ma20 is not None and ma60 is not None
            and ma5 > ma10 > ma20 > ma60)


def get_vol_sma(vols, n):
    """Calculate volume SMA."""
    if len(vols) < n:
        return [None] * len(vols)
    result = [None] * (n - 1)
    for i in range(n - 1, len(vols)):
        result.append(sum(vols[i - n + 1:i + 1]) / n)
    return result


def filter_signals(combo, daily_by_code, daily_basic, moneyflow, spx_dates):
    """Filter signals based on combo parameters."""
    params = combo["params"]
    need_moneyflow = any(k in params for k in [
        "buy_lg_ratio_min", "buy_elg_gte_sell_elg",
        "sell_sm_gt_buy_sm", "buy_lg_gt_sell_lg",
        "net_mf_positive"
    ])
    need_spx = params.get("spx_prev_up", False)

    signals = []
    skipped_no_data = 0

    for code, bars in daily_by_code.items():
        if len(bars) < 200:
            continue

        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["vol"] for b in bars if b["vol"] is not None]
        pct_chgs = [b["pct_chg"] for b in bars]

        if len(closes) < 200 or None in closes[:200]:
            continue

        # Pre-calc MAs
        ma5_list = calc_ma(closes, 5)
        ma10_list = calc_ma(closes, 10)
        ma20_list = calc_ma(closes, 20)
        ma60_list = calc_ma(closes, 60)
        ma120_list = calc_ma(closes, 120)

        # Volume SMA for 持续放量
        vol_sma5_list = get_vol_sma(vols, 5) if vols else None
        vol_sma15_list = get_vol_sma(vols, 15) if vols else None
        vol_sma20_list = get_vol_sma(vols, 20) if vols else None

        for i in range(200, len(bars)):
            bar = bars[i]
            td = str(bar["trade_date"])
            close = bar["close"]
            if close is None or close == 0:
                continue

            # ===== 价格位置 (close_position) =====
            pos_20d = None
            pos_60d = None
            cp = params.get("close_position", "")

            if i >= 20:
                h20 = max(closes[i - 20:i + 1])
                l20 = min(closes[i - 20:i + 1])
                pos_20d = (close - l20) / (h20 - l20) if h20 - l20 > 0 else 0.5
            if i >= 60:
                h60 = max(closes[i - 60:i + 1])
                l60 = min(closes[i - 60:i + 1])
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
            elif cp == "中位":
                p = pos_20d if pos_20d is not None else pos_60d
                if p is None or p < 0.4 or p > 0.6:
                    continue
            elif cp == "顶40%":
                if pos_20d is None or pos_20d < 0.6:
                    continue

            # ===== N日新高 (n_day_high) =====
            ndh = params.get("n_day_high")
            if ndh is not None:
                if i < ndh:
                    continue
                prev_n = closes[i - ndh:i]
                if max(prev_n) >= close:
                    continue

            # ===== 涨幅 (pct_chg) =====
            pct = bar.get("pct_chg")
            if pct is None:
                continue
            if "pct_chg_min" in params and pct < params["pct_chg_min"]:
                continue
            if "pct_chg_max" in params and pct > params["pct_chg_max"]:
                continue

            # ===== 振幅 (amplitude) =====
            if "amplitude_min" in params:
                h = bar.get("high")
                l = bar.get("low")
                pre_close = bar.get("pre_close")
                if h is None or l is None or pre_close is None or pre_close == 0:
                    continue
                ampl = (h - l) / pre_close * 100
                if ampl < params["amplitude_min"]:
                    continue

            # ===== 量比 (volume_ratio) & 换手率 & circ_mv from daily_basic =====
            db_key = (code, td)
            db = daily_basic.get(db_key)
            if db is None:
                skipped_no_data += 1
                continue

            if "volume_ratio_min" in params:
                vr = db.get("volume_ratio")
                if vr is None or vr < params["volume_ratio_min"]:
                    continue

            if "circ_mv_max_wan" in params:
                cmax = params["circ_mv_max_wan"]
                cmv = db.get("circ_mv", 0)
                if cmv is None or cmv > cmax:
                    continue

            # PE / PB
            if "pe_max" in params:
                pe = db.get("pe")
                if pe is None or pe > params["pe_max"]:
                    continue
            if "pb_max" in params:
                pb = db.get("pb")
                if pb is None or pb > params["pb_max"]:
                    continue

            # ===== MA 多头排列 =====
            if params.get("ma_arrangement") == "多头排列":
                ma5 = ma5_list[i] if i < len(ma5_list) else None
                ma10 = ma10_list[i] if i < len(ma10_list) else None
                ma20 = ma20_list[i] if i < len(ma20_list) else None
                ma60 = ma60_list[i] if i < len(ma60_list) else None
                if not is_ma_bullish(ma5, ma10, ma20, ma60):
                    continue

            # ===== 持续放量 (5日均量 > 15日均量 × threshold) =====
            vol_threshold = params.get("持续放量5d")
            if vol_threshold is not None:
                if vol_sma5_list is None or vol_sma15_list is None:
                    continue
                s5 = vol_sma5_list[i] if i < len(vol_sma5_list) else None
                s15 = vol_sma15_list[i] if i < len(vol_sma15_list) else None
                if s5 is None or s15 is None or s15 == 0:
                    continue
                if s5 / s15 < vol_threshold:
                    continue

            # ===== SPX 前日涨 =====
            if need_spx:
                # Find the most recent SPX trading day before this date
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

                # 大单买入比例 (buy_lg_ratio)
                if "buy_lg_ratio_min" in params:
                    buy_lg = mf.get("buy_lg_vol", 0) or 0
                    sell_lg = mf.get("sell_lg_vol", 0) or 0
                    total_lg = buy_lg + sell_lg
                    if total_lg <= 0 or buy_lg / total_lg < params["buy_lg_ratio_min"]:
                        continue

                # 超大单净买入 (buy_elg > sell_elg)
                if params.get("buy_elg_gte_sell_elg"):
                    buy_elg = mf.get("buy_elg_vol", 0) or 0
                    sell_elg = mf.get("sell_elg_vol", 0) or 0
                    if buy_elg <= sell_elg:
                        continue

                # 散户割肉 (sell_sm > buy_sm)
                if params.get("sell_sm_gt_buy_sm"):
                    buy_sm = mf.get("buy_sm_vol", 0) or 0
                    sell_sm = mf.get("sell_sm_vol", 0) or 0
                    if sell_sm <= buy_sm:
                        continue

                # 大单净买入 (buy_lg > sell_lg)
                if params.get("buy_lg_gt_sell_lg"):
                    buy_lg = mf.get("buy_lg_vol", 0) or 0
                    sell_lg = mf.get("sell_lg_vol", 0) or 0
                    if buy_lg <= sell_lg:
                        continue

                # 净流入 (net_mf_amount > 0)
                if params.get("net_mf_positive"):
                    net_mf = mf.get("net_mf_amount", 0) or 0
                    if net_mf <= 0:
                        continue

            signals.append((code, td, close))

    if skipped_no_data > 0:
        print(f"  [INFO] Skipped {skipped_no_data} rows due to missing daily_basic data")
    return signals


def calc_returns(signals, daily_by_code, hold_days=[1, 3, 5, 10, 20]):
    """Calculate forward returns for each signal."""
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
    """Calculate win rate, avg return, sharpe, P10."""
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
        # P10: worst 10% average
        sorted_rets = sorted(rets)
        p10_count = max(1, len(sorted_rets) // 10)
        p10_avg = sum(sorted_rets[:p10_count]) / p10_count
        stats[f"win_rate_{n}d"] = wins / len(rets)
        stats[f"ret_{n}d"] = avg_ret
        stats[f"sharpe_{n}d"] = sharpe
        stats[f"p10_{n}d"] = p10_avg
    return stats


def combo_hash(params):
    """Generate unique hash for combo dedup."""
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    text = ",".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5(text.encode()).hexdigest()[:12]


def generate_report(all_results, best):
    """Generate markdown report."""
    lines = []
    lines.append("# T2 动量趋势挖掘 — Iter28")
    lines.append("")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"- 执行时间: {now_str} UTC+8")
    lines.append(f"- 数据基准: {MAX_DATE}")
    lines.append(f"- 回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    lines.append(f"- 历史最佳WR: 99.55%, 历史最佳R5: 25.23%")
    lines.append(f"- 疲劳计数: 2 (连续未破纪录轮数)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 测试参数组合（5 组）")
    lines.append("")

    for idx, combo in enumerate(all_results):
        r = combo["results"]
        lines.append(f"### 组合 {idx+1}: {combo['name']}")
        lines.append(f"- 描述: {combo['desc']}")
        lines.append(f"- 逻辑流派: {combo.get('logic', '动量趋势')}")
        params_str = ", ".join(f"{k}={v}" for k, v in sorted(combo["params"].items()))
        lines.append(f"- 参数: {params_str}")
        lines.append(f"- Hash: `{combo['hash']}`")
        lines.append("")
        lines.append("#### 结果")
        lines.append("| 周期 | 信号数(有效) | 胜率(WR) | 平均收益 | 夏普比率 | P10(最差10%) |")
        lines.append("|------|-------------|----------|----------|----------|-------------|")
        total_signals = r["signal_count"]
        for n in [1, 3, 5, 10, 20]:
            wr = r.get(f"win_rate_{n}d", 0) * 100
            ret = r.get(f"ret_{n}d", 0) * 100
            sharpe = r.get(f"sharpe_{n}d", 0)
            p10 = r.get(f"p10_{n}d", 0) * 100
            lines.append(f"| T+{n}d | {total_signals} | {wr:.2f}% | {ret:.2f}% | {sharpe:.3f} | {p10:+.2f}% |")
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
        lines.append("")

        # Check if it breaks records
        if passed:
            if wr5 > 99.55:
                lines.append(f"- **🏆🏆🏆 新全局WR纪录! {wr5:.2f}% > 99.55%**")
            if ret5 > 25.23:
                lines.append(f"- **🏆🏆🏆 新全局R5纪录! {ret5:.2f}% > 25.23%**")
            if sharpe > 20.227:
                lines.append(f"- **🏆🏆🏆 新全局Sharpe纪录! {sharpe:.3f} > 20.227**")

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
    lines.append(f"- Sharpe_10d: {br.get('sharpe_10d', 0):.3f}")
    lines.append(f"- Sharpe_20d: {br.get('sharpe_20d', 0):.3f}")
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

    # Record-breaking check
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
                lines.append(f"- WR差距: {99.55 - wr5b:.2f}pp")
            if ret5b < 25.23:
                lines.append(f"- R5差距: {25.23 - ret5b:.2f}pp")
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
    lines.append("-- 回测全量历史数据，使用Python本地计算MA、位置等")
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
    print("T2 动量趋势挖掘 - Iter28")
    print("=" * 60)
    print(f"数据基准: {MAX_DATE}")
    print(f"回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    print()

    # Load data
    daily_by_code = load_daily_data()
    daily_basic = load_daily_basic()
    moneyflow = load_moneyflow()
    spx_dates = load_spx()

    # # TEMP: For testing with smaller dataset
    # # Filter to stocks with enough data
    # filtered = {}
    # for code, bars in daily_by_code.items():
    #     if len(bars) >= 200:
    #         filtered[code] = bars
    # daily_by_code = filtered

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

    # Also find best by WR
    best_wr = max(all_results, key=lambda c: c["results"].get("win_rate_5d", 0))

    print(f"\n{'='*60}")
    print("最佳发现(Sharpe):")
    print(f"  {best['name']}")
    br = best["results"]
    print(f"  WR_5d={br.get('win_rate_5d', 0)*100:.2f}%")
    print(f"  Ret_5d={br.get('ret_5d', 0)*100:.2f}%")
    print(f"  Sharpe_5d={br.get('sharpe_5d', 0):.3f}")
    print(f"  Signals={br.get('signal_count', 0)}")

    info = f"  WR_5d={br.get('win_rate_5d', 0)*100:.2f}%"
    print(f"  最佳WR: {best_wr['name']} - {best_wr['results'].get('win_rate_5d',0)*100:.2f}%")

    # Generate report
    report_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_28/analysis_T2_动量趋势.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    md = generate_report(all_results, best)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"报告已写入: {report_path}")

    # Print hashes for state.json update
    print(f"\n新组合Hashes:")
    for c in all_results:
        print(f"  iter28_T2_{c['hash']}: {c['name']} → WR={c['results'].get('win_rate_5d',0)*100:.2f}%, R5={c['results'].get('ret_5d',0)*100:.2f}%")

    print("\nDone!")


if __name__ == "__main__":
    main()
