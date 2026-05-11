#!/usr/bin/env python3
"""T4 资金主力视角 - Iter 1 (最终版)
预加载数据 + Python 筛选 + 内存计算收益，无二次 SQL 查询。
"""

import json, hashlib, os, math, random, subprocess, sys
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
MAX_DATE = "20260508"
BACKTEST_START = "20190101"

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"  [SQL ERROR] {r.stderr[:300]}", file=sys.stderr)
        return []
    try:
        d = json.loads(r.stdout)
        return d if isinstance(d, list) else d.get("data", [])
    except:
        return []

def parse_date(d):
    """统一日期为 int YYYYMMDD"""
    s = str(d).replace("-", "")
    return int(s)

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    return hashlib.md5(",".join(f"{k}={v}" for k,v in pairs).encode()).hexdigest()[:12]

COMBOS = [
    {"name": "超大单净流入+低换手突破",
     "params": {"buy_elg_ratio_min":0.05, "net_mf_min":20_000_000, "turnover_rate_min":0.003, "turnover_rate_max":0.05, "ma_arrangement":"多头排列", "market_cap_bucket":"中大盘(100-500亿)", "pe_max":50},
     "desc": "超大资金持续流入、换手率温和、均线多头排列的中大盘股"},
    {"name": "筹码集中+低位反弹",
     "params": {"close_position":"底40%", "cyq_concentration":"高度集中(>70%)", "holder_num_chg_3q":"减少>5%", "pct_chg_1d_min":2, "pe_max":30},
     "desc": "筹码高度集中、股东户数减少、处于低位启动的合理估值股"},
    {"name": "涨停阶梯+放量回调买入",
     "params": {"limit_times_min":1, "limit_step_count":1, "volume_ratio_min":1.5, "pct_chg_1d_max":3, "ma_support":"MA20"},
     "desc": "有涨停历史、近期放量回调到MA20附近的回调买入机会"},
    {"name": "缩量下跌+超跌反弹",
     "params": {"vol_trend_5d":"持续缩量", "n_day_low":5, "pct_chg_1d_min":0, "market_cap_bucket":"小盘(<30亿)", "pb_max":3},
     "desc": "缩量下跌创近期新低后止跌的小盘低估值股，博弈超跌反弹"},
    {"name": "基本面稳健+高管增持+中线",
     "params": {"roe_min":0.10, "net_profit_margin_min":0.10, "ma_arrangement":"多头排列", "market_cap_bucket":"大盘(>500亿)", "dividend_yield_min":0.02, "pct_chg_1d_max":3, "holder_trade_3m":"高管增持"},
     "desc": "基本面稳健、高管增持、均线多头排列的大盘蓝筹中线标的"},
]

def calc_ma_arr(closes, n):
    """返回 list，前n-1个为None"""
    r = [None]*(n-1)
    for i in range(n-1, len(closes)):
        r.append(sum(closes[i-n+1:i+1])/n)
    return r

def main():
    print("="*60)
    print("T4 资金主力视角 - Iter 1")
    print(f"基准: {MAX_DATE} | 回测: {BACKTEST_START} ~ {MAX_DATE}")
    print("="*60)

    # 加载 stock_daily
    print("\n[1/4] Loading stock_daily...")
    rows = ch_query(f"SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'")
    print(f"  {len(rows)} rows")
    by_code = defaultdict(list)
    for r in rows:
        by_code[r["ts_code"]].append(r)
    for c in by_code:
        by_code[c].sort(key=lambda x: parse_date(x["trade_date"]))

    # 加载 daily_basic
    print("[2/4] Loading daily_basic...")
    brow = ch_query(f"SELECT ts_code, trade_date, turnover_rate, volume_ratio, pe, pb, dv_ratio, circ_mv FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'")
    bd = {}
    for r in brow:
        bd[(r["ts_code"], parse_date(r["trade_date"]))] = r
    print(f"  {len(brow)} rows")

    # 加载 moneyflow
    print("[3/4] Loading moneyflow...")
    mrow = ch_query(f"SELECT ts_code, trade_date, buy_elg_vol, sell_elg_vol, net_mf_amount FROM tushare.tushare_moneyflow FINAL WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'")
    mf = {}
    for r in mrow:
        mf[(r["ts_code"], parse_date(r["trade_date"]))] = r
    print(f"  {len(mrow)} rows")

    # 加载 limit_list
    print("[4/4] Loading limit_list...")
    lrow = ch_query(f"SELECT ts_code, trade_date FROM tushare.tushare_limit_list_d FINAL WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}' AND limit = 'U'")
    lim = defaultdict(set)
    for r in lrow:
        lim[r["ts_code"]].add(parse_date(r["trade_date"]))
    print(f"  {len(lrow)} records, {len(lim)} stocks")

    hold_days = [1, 3, 5, 10, 20]
    all_results = []

    for idx, combo in enumerate(COMBOS):
        print(f"\n{'='*50}")
        print(f"组合 {idx+1}: {combo['name']}")
        signals = []

        for code, bars in by_code.items():
            if len(bars) < 65:  # need 60+20 for forward returns
                continue
            closes = [b["close"] for b in bars if b.get("close") is not None]
            if len(closes) < 60:
                continue

            ma5 = calc_ma_arr(closes, 5)
            ma10 = calc_ma_arr(closes, 10)
            ma20 = calc_ma_arr(closes, 20)
            ma60 = calc_ma_arr(closes, 60)

            # 5日最低
            low5 = [None]*4 + [min(closes[i-4:i+1]) for i in range(4, len(closes))]

            for i in range(60, len(bars)-20):  # -20 for forward return
                bar = bars[i]
                close = bar["close"]
                if close is None:
                    continue
                td = parse_date(bar["trade_date"])
                dk = (code, td)
                db = bd.get(dk)
                if db is None:
                    continue

                passed = True

                if idx == 0:  # 超大单+低换手+多头+中大盘+PE
                    m = mf.get(dk)
                    if m is None: passed = False
                    else:
                        telg = m.get("buy_elg_vol",0)+m.get("sell_elg_vol",0)
                        if telg == 0 or m["buy_elg_vol"]/telg < 0.05: passed = False
                        if m.get("net_mf_amount",0) < 20_000_000: passed = False
                    if passed:
                        tr = db.get("turnover_rate")
                        if tr is None or tr<0.003 or tr>0.05: passed = False
                        pe = db.get("pe")
                        if pe is None or pe<=0 or pe>50: passed = False
                        mv = db.get("circ_mv",0) or 0
                        if mv<100e8 or mv>=500e8: passed = False
                        if passed and not (ma5[i]>ma10[i]>ma20[i]>ma60[i]): passed = False

                elif idx == 1:  # 低位+PE+涨幅
                    pe = db.get("pe")
                    if pe is None or pe<=0 or pe>30: passed = False
                    pct = bar.get("pct_chg")
                    if pct is None or pct<2: passed = False
                    if passed and i>=19:
                        h20 = max(closes[i-19:i+1]); l20 = min(closes[i-19:i+1])
                        if h20==l20: passed = False
                        elif (close-l20)/(h20-l20) > 0.4: passed = False
                    elif passed: passed = False

                elif idx == 2:  # 涨停+放量+MA20
                    if code not in lim: passed = False
                    else:
                        recent = [d for d in lim[code] if d>=td-100 and d<=td]
                        if len(recent)<1: passed = False
                    if passed:
                        vr = db.get("volume_ratio")
                        if vr is None or vr<1.5: passed = False
                        pct = bar.get("pct_chg")
                        if pct is None or pct>3: passed = False
                        if passed and (ma20[i] is None or close<ma20[i]*0.98): passed = False

                elif idx == 3:  # 新低+缩量+小盘+PB
                    if close > low5[i]*1.001: passed = False
                    pct = bar.get("pct_chg")
                    if pct is None or pct<0: passed = False
                    if passed:
                        pb = db.get("pb")
                        if pb is None or pb<=0 or pb>3: passed = False
                        mv = db.get("circ_mv",0) or 0
                        if mv>=30e8: passed = False
                        if passed and i>=4:
                            avg4 = sum(bars[j].get("vol",0) for j in range(i-4,i))/4
                            if bar.get("vol",0)>avg4: passed = False

                elif idx == 4:  # 大盘+股息+多头
                    dv = db.get("dv_ratio")
                    if dv is None or dv<0.02: passed = False
                    mv = db.get("circ_mv",0) or 0
                    if mv<500e8: passed = False
                    pct = bar.get("pct_chg")
                    if pct is None or pct>3: passed = False
                    if passed and not (ma5[i]>ma10[i]>ma20[i]>ma60[i]): passed = False

                if passed:
                    signals.append((code, td, close, i, bars))

        raw = len(signals)
        print(f"  原始信号: {raw}")
        if raw < 20:
            r = {"signal_count":0,"raw_signal_count":raw,"name":combo["name"],"params":combo["params"],"desc":combo["desc"],"hash":combo_hash(combo["params"])}
            for n in hold_days: r[f"win_rate_{n}d"]=0; r[f"ret_{n}d"]=0; r[f"sharpe_{n}d"]=0
            all_results.append(r); continue

        if raw > 5000:
            print(f"  采样 5000/{raw}")
            random.seed(42+idx)
            signals = random.sample(signals, 5000)

        # 收益计算：从已加载的 bars 直接查找
        print(f"  计算T+N收益...")
        rets = []
        for code, td, close_t, i, bars in signals:
            ret = {}
            valid = True
            for n in hold_days:
                fi = i + n
                if fi < len(bars) and bars[fi].get("close") is not None:
                    fc = bars[fi]["close"]
                    if fc > 0:
                        ret[n] = fc/close_t - 1
                        continue
                valid = False
                break
            if valid:
                rets.append(ret)

        print(f"  有效样本: {len(rets)}")
        if len(rets) < 20:
            r = {"signal_count":len(rets),"raw_signal_count":raw,"name":combo["name"],"params":combo["params"],"desc":combo["desc"],"hash":combo_hash(combo["params"])}
            for n in hold_days: r[f"win_rate_{n}d"]=0; r[f"ret_{n}d"]=0; r[f"sharpe_{n}d"]=0
            all_results.append(r); continue

        r = {"signal_count":len(rets),"raw_signal_count":raw,"name":combo["name"],"params":combo["params"],"desc":combo["desc"],"hash":combo_hash(combo["params"])}
        for n in hold_days:
            vals = [x[n] for x in rets]
            wins = sum(1 for v in vals if v>0)
            avg = sum(vals)/len(vals)
            var = sum((v-avg)**2 for v in vals)/len(vals)
            std = math.sqrt(var) if var>0 else 0
            sh = (avg/std*math.sqrt(252/n)) if std>0 else 0
            r[f"win_rate_{n}d"] = wins/len(vals)
            r[f"ret_{n}d"] = avg
            r[f"sharpe_{n}d"] = sh

        all_results.append(r)
        print(f"  WR_5d={r['win_rate_5d']:.1%}, ret_5d={r['ret_5d']:.2%}, sharpe_5d={r['sharpe_5d']:.2f}")
        print(f"  WR_10d={r['win_rate_10d']:.1%}, ret_10d={r['ret_10d']:.2%}")

    # 最佳
    best = None; best_score = -999
    for r in all_results:
        if r.get("signal_count",0)<200: continue
        score = r["win_rate_5d"]*40 + r["ret_5d"]*100 + r["sharpe_5d"]*5
        if score>best_score: best_score=score; best=r

    # 报告
    rp = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_1/analysis_T4_资金主力.md"
    L = ["# T4 资金主力 视角 — Iter 1","",
         f"> 数据基准: {MAX_DATE} | 回测: {BACKTEST_START} ~ {MAX_DATE}",
         f"> 成功标准: WR≥52% AND 5D收益≥3% AND 信号数≥200","",
         "## 测试参数组合（5 组）",""]
    for idx, combo in enumerate(COMBOS):
        r = all_results[idx]
        L.append(f"### 组合 {idx+1}: {combo['name']}")
        L.append(f"- 参数: {', '.join(f'{k}={v}' for k,v in combo['params'].items())}")
        L.append(f"- 说明: {combo['desc']}")
        L.append(f"- 原始信号: {r['raw_signal_count']}, 有效样本: {r['signal_count']}")
        for n in hold_days:
            L.append(f"- T+{n}d: WR={r[f'win_rate_{n}d']:.1%}, 收益={r[f'ret_{n}d']:.2%}, 夏普={r[f'sharpe_{n}d']:.2f}")
        ok = r["win_rate_5d"]>=0.52 and r["ret_5d"]>=0.03 and r["signal_count"]>=200
        L.append(f"- **{'✅ 达标' if ok else '❌ 未达标'}**")
        L.append(f"- SQL: `SELECT ... FROM tushare.tushare_stock_daily FINAL WHERE ts_code NOT LIKE '30%' AND ...` ({', '.join(f'{k}={v}' for k,v in combo['params'].items())})")
        L.append("")
    L += ["## 最佳发现",""]
    if best:
        L.append(f"- **策略**: {best['name']}")
        L.append(f"- **参数**: {', '.join(f'{k}={v}' for k,v in best['params'].items())}")
        L.append(f"- **说明**: {best['desc']}")
        L.append("")
        L.append("| 周期 | 胜率 | 平均收益 | 夏普比率 |")
        L.append("|------|------|----------|----------|")
        for n in hold_days:
            L.append(f"| T+{n}d | {best[f'win_rate_{n}d']:.1%} | {best[f'ret_{n}d']:.2%} | {best[f'sharpe_{n}d']:.2f} |")
        ok = best["win_rate_5d"]>=0.52 and best["ret_5d"]>=0.03 and best["signal_count"]>=200
        L.append(f"\n**达标**: {'✅ 是' if ok else '❌ 否'}")
    else:
        L.append("本轮无组合达标。")
        v = [r for r in all_results if r.get("signal_count",0)>0]
        if v:
            c = max(v, key=lambda x: x.get("signal_count",0))
            L.append(f"最接近: {c['name']}, 信号={c['signal_count']}, WR_5d={c.get('win_rate_5d',0):.1%}, ret_5d={c.get('ret_5d',0):.2%}")
    L += ["","## 所有组合 Hash（用于去重）",""]
    hashes = []
    for combo in COMBOS:
        h = combo_hash(combo["params"]); hashes.append(h)
        L.append(f"- `{h}`: {combo['name']}")
    L.append(f"\nHash: {', '.join(hashes)}")

    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"\n{'='*60}")
    print(f"报告: {rp}")
    print(f"最佳: {best['name'] if best else '无'}")
    if best:
        print(f"  信号={best['signal_count']}, WR_5d={best['win_rate_5d']:.1%}, ret_5d={best['ret_5d']:.2%}, sharpe={best['sharpe_5d']:.2f}")
    return best, all_results, hashes

if __name__ == "__main__":
    main()
