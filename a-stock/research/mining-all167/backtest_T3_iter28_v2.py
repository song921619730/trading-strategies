#!/usr/bin/env python3
"""T3 反转低吸挖掘 - Iter28 回测脚本 (fixed)
- Load moneyflow in yearly batches to avoid timeout
- Fixed PMI query
- Fixed C2 parameter name
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
        "name": "C1_双日恐慌-4%新阈值SPX散户割肉大单CM50",
        "params": {
            "close_position": "底20%(60日)",
            "prev1_pct_chg_max": -4,
            "prev2_pct_chg_max": -4,
            "volume_ratio_min": 1.0,
            "amplitude_min": 7,
            "sell_sm_gt_buy_sm": True,
            "buy_lg_gt_sell_lg": True,
            "spx_prev_up": True,
            "circ_mv_max_wan": 500000,
        },
        "desc": "双日恐慌-4%新阈值(介于已验证的-5%和-3%之间)+SPX前日涨+散户割肉+大单接盘+60日深底+振幅≥7%+CM≤50亿。测试温和阈值扩容+双资金流确认的确定性维持能力。",
        "logic": "反转低吸",
    },
    {
        "name": "C2_极端恐慌-7%振幅10%散户ELG深价值微盘",
        "params": {
            "close_position": "底20%(20日)",
            "prev1_pct_chg_max": -7,
            "volume_ratio_min": 1.3,
            "amplitude_min": 10,
            "sell_sm_gt_buy_sm": True,
            "buy_elg_gte_sell_elg": True,
            "circ_mv_max_wan": 300000,
            "pe_max": 20,
        },
        "desc": "单日极端恐慌≤-7%+振幅≥10%(极端振幅清洗筹码)+散户割肉+超大单净买入+深价值(PE≤20)+微盘≤30亿。纯微观深价值版，测试是否无需SPX达到高质量。",
        "logic": "反转低吸",
    },
    {
        "name": "C3_双日恐慌-5%VR放宽散户大单比例底30%CM100亿",
        "params": {
            "close_position": "底30%",
            "prev2_pct_chg_max": -5,
            "prev1_pct_chg_max": -5,
            "volume_ratio_min": 0.8,
            "amplitude_min": 6,
            "sell_sm_gt_buy_sm": True,
            "buy_lg_ratio_min": 0.60,
            "circ_mv_max_wan": 1000000,
        },
        "desc": "双日恐慌(-5%)+振幅≥6%+VR≥0.8(大幅放宽)+散户割肉+大单比例≥60%+底30%(放宽)+CM≤100亿(大幅扩容)。测试最大容量版的质量维持。",
        "logic": "反转低吸",
    },
    {
        "name": "C4_单日恐慌5%SPX双涨散户大单60日底CM30",
        "params": {
            "close_position": "底20%(60日)",
            "prev1_pct_chg_max": -5,
            "now_pct_chg_min": 2,
            "volume_ratio_min": 1.3,
            "amplitude_min": 6,
            "sell_sm_gt_buy_sm": True,
            "buy_lg_gt_sell_lg": True,
            "spx_double_up": True,
            "circ_mv_max_wan": 300000,
        },
        "desc": "昨跌≤-5%+今涨≥2%恐慌反转+SPX双涨(连续2日前日上涨)+散户割肉+大单+60日底20%+CM≤30亿。CROSS-6的'单日恐慌替代双日'版本，测试单日恐慌+SPX双涨是否能接近全局纪录。",
        "logic": "反转低吸",
    },
    {
        "name": "C5_双日温和-3%散户ELG振幅7%CM30无宏观",
        "params": {
            "close_position": "底20%(20日)",
            "prev2_pct_chg_max": -3,
            "prev1_pct_chg_max": -3,
            "volume_ratio_min": 1.2,
            "amplitude_min": 7,
            "sell_sm_gt_buy_sm": True,
            "buy_elg_gte_sell_elg": True,
            "circ_mv_max_wan": 300000,
        },
        "desc": "双日温和恐慌(-3%)+散户割肉+超大单净买入+振幅≥7%+VR≥1.2+微盘≤30亿。纯微观多方版，无任何宏观过滤。测试双日温和恐慌+三重资金流在无宏观窗口下的极限表现。修正版(去掉PMI)。",
        "logic": "反转低吸",
    },
]


def ch_query(sql, timeout=300):
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
    """Load daily_basic in yearly batches to avoid timeout."""
    print("Loading daily_basic (yearly batches)...")
    idx = {}
    years = list(range(2019, 2027))
    for y in years:
        sql = f"""
        SELECT ts_code, trade_date, turnover_rate, volume_ratio, pe, pe_ttm, pb, dv_ratio, circ_mv
        FROM tushare_daily_basic FINAL
        WHERE trade_date >= '{y}0101' AND trade_date <= '{min(y, 2026)}1231'
          AND trade_date <= '{MAX_DATE}'
          AND ts_code NOT LIKE '30%'
          AND ts_code NOT LIKE '688%'
          AND ts_code NOT LIKE '920%'
        """
        try:
            rows = ch_query(sql, timeout=120)
            for r in rows:
                idx[(r["ts_code"], str(r["trade_date"]))] = r
            print(f"  {y}: {len(rows)} rows")
        except Exception as e:
            print(f"  {y}: ERROR - {e}")
    print(f"  Total loaded: {len(idx)} unique stock-date pairs")
    return idx


def load_moneyflow_by_year():
    """Load moneyflow in yearly batches to avoid timeout."""
    print("Loading moneyflow (yearly batches)...")
    idx = {}
    years = list(range(2019, 2027))
    for y in years:
        sql = f"""
        SELECT ts_code, trade_date, net_mf_amount,
               buy_lg_vol, sell_lg_vol,
               buy_elg_vol, sell_elg_vol,
               buy_sm_vol, sell_sm_vol
        FROM tushare_moneyflow FINAL
        WHERE trade_date >= '{y}0101' AND trade_date <= '{min(y, 2026)}1231'
          AND trade_date <= '{MAX_DATE}'
        """
        try:
            rows = ch_query(sql, timeout=120)
            for r in rows:
                idx[(r["ts_code"], str(r["trade_date"]))] = r
            print(f"  {y}: {len(rows)} rows")
        except Exception as e:
            print(f"  {y}: ERROR - {e}")
    print(f"  Total loaded: {len(idx)} unique stock-date pairs")
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


def load_pmi():
    """Load PMI data. Table has MONTH (YYYYMM) and PMI010000 (manufacturing PMI)."""
    print("Loading PMI data...")
    sql = f"""
    SELECT MONTH, PMI010000
    FROM tushare_cn_pmi FINAL
    WHERE MONTH >= '201901' AND MONTH <= '202612'
    ORDER BY MONTH
    """
    rows = ch_query(sql, timeout=60)
    pmi_map = {}
    for r in rows:
        month_str = r["MONTH"]
        pmi_val = r["PMI010000"]
        if pmi_val is not None and pmi_val > 0:
            pmi_map[month_str] = pmi_val
    print(f"  Loaded {len(rows)} PMI entries, {len(pmi_map)} valid")
    return pmi_map


def calc_ma(prices, n):
    if len(prices) < n:
        return [None] * len(prices)
    result = [None] * (n - 1)
    for i in range(n - 1, len(prices)):
        result.append(sum(prices[i - n + 1:i + 1]) / n)
    return result


def filter_signals(combo, daily_by_code, daily_basic, moneyflow, spx_dates, pmi_dates):
    params = combo["params"]
    need_moneyflow = any(k in params for k in [
        "buy_lg_ratio_min", "buy_elg_gte_sell_elg",
        "sell_sm_gt_buy_sm", "buy_lg_gt_sell_lg",
        "net_mf_positive"
    ])
    need_spx = params.get("spx_prev_up", False)
    need_spx_double = params.get("spx_double_up", False)

    signals = []
    skipped_no_data = 0

    for code, bars in daily_by_code.items():
        if len(bars) < 200:
            continue

        closes = [b["close"] for b in bars]
        pct_chgs = [b.get("pct_chg") for b in bars]

        if len(closes) < 200 or None in closes[:200]:
            continue

        for i in range(200, len(bars)):
            bar = bars[i]
            td = str(bar["trade_date"])
            close = bar["close"]
            if close is None or close == 0:
                continue

            # === 价格位置 ===
            cp = params.get("close_position", "")
            pos_20d = None
            pos_60d = None
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
            elif cp == "底30%":
                p = pos_20d if pos_20d is not None else pos_60d
                if p is None or p > 0.3:
                    continue

            # === 前日/前前日跌幅 ===
            if "prev1_pct_chg_max" in params:
                if i < 1:
                    continue
                prev1 = bars[i - 1].get("pct_chg")
                if prev1 is None or prev1 > params["prev1_pct_chg_max"]:
                    continue

            if "prev2_pct_chg_max" in params:
                if i < 2:
                    continue
                prev2 = bars[i - 2].get("pct_chg")
                if prev2 is None or prev2 > params["prev2_pct_chg_max"]:
                    continue

            # === 今日涨幅 ===
            if "now_pct_chg_min" in params:
                pct = bar.get("pct_chg")
                if pct is None or pct < params["now_pct_chg_min"]:
                    continue

            # 限制今日涨幅上限（防垃圾票）
            pct = bar.get("pct_chg")
            if pct is None or pct > 10:
                continue

            # === 振幅 ===
            if "amplitude_min" in params:
                h = bar.get("high")
                l = bar.get("low")
                pc = bar.get("pre_close")
                if h is None or l is None or pc is None or pc == 0:
                    continue
                ampl = (h - l) / pc * 100
                if ampl < params["amplitude_min"]:
                    continue

            # === daily_basic ===
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

            if "pe_max" in params:
                pe = db.get("pe")
                if pe is None or pe > params["pe_max"]:
                    continue

            # === SPX ===
            if need_spx:
                td_int = int(td.replace("-", ""))
                prev_spx_pct = None
                for spx_td in sorted(spx_dates.keys(), reverse=True):
                    spx_td_int = int(spx_td.replace("-", ""))
                    if spx_td_int < td_int:
                        prev_spx_pct = spx_dates[spx_td]
                        break
                if prev_spx_pct is None or prev_spx_pct <= 0:
                    continue

            # === SPX双涨 ===
            if need_spx_double:
                td_int = int(td.replace("-", ""))
                spx_vals = []
                for spx_td in sorted(spx_dates.keys(), reverse=True):
                    spx_td_int = int(spx_td.replace("-", ""))
                    if spx_td_int < td_int:
                        spx_vals.append(spx_dates[spx_td])
                        if len(spx_vals) >= 2:
                            break
                if len(spx_vals) < 2 or spx_vals[0] <= 0 or spx_vals[1] <= 0:
                    continue

            # === 资金流 ===
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

                if params.get("net_mf_positive"):
                    net_mf = mf.get("net_mf_amount", 0) or 0
                    if net_mf <= 0:
                        continue

            signals.append((code, td, close))

    if skipped_no_data > 0:
        print(f"  [INFO] Skipped {skipped_no_data} rows due to missing daily_basic")
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
    lines.append("# T3 反转低吸挖掘 — Iter28")
    lines.append("")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"- 执行时间: {now_str} UTC+8")
    lines.append(f"- 数据基准: {MAX_DATE}")
    lines.append(f"- 回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    lines.append(f"- 历史最佳WR: 99.55%, 历史最佳R5: 25.23%")
    lines.append(f"- 疲劳计数: 2")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 测试参数组合（5 组）")
    lines.append("")

    for idx, combo in enumerate(all_results):
        r = combo["results"]
        lines.append(f"### 组合 {idx+1}: {combo['name']}")
        lines.append(f"- 描述: {combo['desc']}")
        lines.append(f"- 逻辑流派: {combo.get('logic', '反转低吸')}")
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

        if passed:
            improvements = []
            if wr5 > 99.55:
                improvements.append(f"🏆 新全局WR纪录: {wr5:.2f}% > 99.55% (+{wr5-99.55:.2f}pp)")
            if ret5 > 25.23:
                improvements.append(f"🏆 新全局R5纪录: {ret5:.2f}% > 25.23% (+{ret5-25.23:.2f}pp)")
            if improvements:
                lines.append("🏆🏆🏆 全局纪录突破!")
                for imp in improvements:
                    lines.append(f"- {imp}")
            else:
                lines.append("ℹ️ PASS但未破全局纪录")
                if wr5 < 99.55:
                    lines.append(f"- WR差距: {99.55 - wr5:.2f}pp")
                if ret5 < 25.23:
                    lines.append(f"- R5差距: {25.23 - ret5:.2f}pp")

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
    lines.append(f"- 参数: {best['params']}")
    lines.append(f"- Hash: `{best['hash']}`")
    lines.append("")

    wr5b = br.get("win_rate_5d", 0) * 100
    ret5b = br.get("ret_5d", 0) * 100
    cntb = br.get("signal_count", 0)
    passed_best = wr5b >= 52 and ret5b >= 3 and cntb >= 200
    lines.append(f"- **成功标准: {'✅ PASS' if passed_best else '❌ FAIL'}**")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 所有组合 Hash")
    lines.append("")
    for c in all_results:
        lines.append(f"- `{c['hash']}` → {c['name']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## SQL 查询骨架")
    lines.append("")
    lines.append("```sql")
    lines.append("SELECT d.ts_code, d.trade_date, d.open, d.high, d.low, d.close, d.pre_close, d.pct_chg, d.vol, d.amount,")
    lines.append("       b.volume_ratio, b.circ_mv, b.pe, b.pb, b.dv_ratio, b.turnover_rate,")
    lines.append("       m.buy_lg_vol, m.sell_lg_vol, m.buy_elg_vol, m.sell_elg_vol, m.buy_sm_vol, m.sell_sm_vol")
    lines.append("FROM tushare_stock_daily FINAL d")
    lines.append("LEFT JOIN tushare_daily_basic FINAL b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date")
    lines.append("LEFT JOIN tushare_moneyflow FINAL m ON d.ts_code = m.ts_code AND d.trade_date = m.trade_date")
    lines.append(f"WHERE d.trade_date >= '{BACKTEST_START}' AND d.trade_date <= '{MAX_DATE}'")
    lines.append("  AND d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%'")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("T3 反转低吸挖掘 - Iter28 (Fixed)")
    print("=" * 60)
    print(f"数据基准: {MAX_DATE}")
    print(f"回测区间: {BACKTEST_START} ~ {MAX_DATE}")
    print()

    # Check recent_combos
    state_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/state/state.json"
    state = json.load(open(state_path))
    recent_combos = state.get("recent_combos", [])
    combo_names_in_state = set()
    for entry in recent_combos:
        if "iter28_" in entry:
            name_part = entry.split(":")[0].strip()
            combo_names_in_state.add(name_part)

    fresh_combos = []
    for combo in COMBOS:
        h = combo_hash(combo["params"])
        iter_key = f"iter28_T3_{h}"
        if iter_key in combo_names_in_state:
            print(f"⏭️ 跳过已测试组合: {combo['name']} (hash={h})")
        else:
            fresh_combos.append(combo)
    print(f"待测试: {len(fresh_combos)} 组 (共定义{len(COMBOS)}组)")

    if not fresh_combos:
        print("所有组合已在recent_combos中")
        return

    # Load data
    daily_by_code = load_daily_data()
    daily_basic = load_daily_basic()
    moneyflow = load_moneyflow_by_year()
    spx_dates = load_spx()

    all_results = []
    for idx, combo in enumerate(fresh_combos):
        print(f"\n{'='*50}")
        print(f"组合 {idx+1}: {combo['name']}")
        print(f"参数: {combo['params']}")

        t0 = datetime.now()
        signals = filter_signals(combo, daily_by_code, daily_basic, moneyflow, spx_dates, None)
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

    if all_results:
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

        report_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_28/analysis_T3_反转低吸.md"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        md = generate_report(all_results, best)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\n报告已写入: {report_path}")

        print(f"\n新组合Hashes:")
        for c in all_results:
            wr5 = c["results"].get("win_rate_5d", 0) * 100
            ret5 = c["results"].get("ret_5d", 0) * 100
            cnt = c["results"].get("signal_count", 0)
            sharpe = c["results"].get("sharpe_5d", 0)
            passed = wr5 >= 52 and ret5 >= 3 and cnt >= 200
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  iter28_T3_{c['hash']}: {c['name']} → N={cnt}, WR={wr5:.2f}%, R5={ret5:.2f}%, Sharpe={sharpe:.3f} {status}")
    else:
        print("\n⚠️ 无可用结果")

    print("\nDone!")


if __name__ == "__main__":
    main()
