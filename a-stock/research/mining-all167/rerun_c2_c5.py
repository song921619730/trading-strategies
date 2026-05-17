#!/usr/bin/env python3
"""Re-run C2 and C5 with SPX data loaded properly."""
import json, hashlib, math, os
import urllib.request
from collections import defaultdict
from datetime import datetime

CH_HOST = "172.24.224.1"
CH_PORT = 8123
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
MAX_DATE = "20260513"
BACKTEST_START = "20190101"

def ch_query(sql, timeout=180):
    url = f"http://{CH_HOST}:{CH_PORT}/?user={CH_USER}&password={CH_PASS}&database=tushare&default_format=JSON"
    data = sql.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("data", [])
    except Exception as e:
        print(f"  [ERROR] {e}")
        return []

print("Loading stock_daily...")
sql_d = f"""
SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount
FROM tushare_stock_daily FINAL
WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
ORDER BY ts_code, trade_date
"""
rows_d = ch_query(sql_d)
daily_by_code = defaultdict(list)
for r in rows_d:
    daily_by_code[r["ts_code"]].append(r)
print(f"  {len(rows_d)} rows, {len(daily_by_code)} stocks")

print("Loading daily_basic...")
sql_b = f"""
SELECT ts_code, trade_date, turnover_rate, volume_ratio, pe, pe_ttm, pb, dv_ratio, circ_mv
FROM tushare_daily_basic FINAL
WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
"""
rows_b = ch_query(sql_b)
daily_basic = {}
for r in rows_b:
    daily_basic[(r["ts_code"], str(r["trade_date"]))] = r
print(f"  {len(rows_b)} rows")

print("Loading moneyflow...")
sql_m = f"""
SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, buy_elg_vol, sell_elg_vol, buy_sm_vol, sell_sm_vol
FROM tushare_moneyflow FINAL
WHERE trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
"""
rows_m = ch_query(sql_m)
moneyflow = {}
for r in rows_m:
    moneyflow[(r["ts_code"], str(r["trade_date"]))] = r
print(f"  {len(rows_m)} rows")

print("Loading SPX...")
sql_spx = f"""
SELECT trade_date, pct_chg
FROM tushare_index_global FINAL
WHERE ts_code='SPX' AND trade_date >= '{BACKTEST_START}' AND trade_date <= '{MAX_DATE}'
ORDER BY trade_date
"""
rows_spx = ch_query(sql_spx)
spx_dates = {}
for r in rows_spx:
    spx_dates[str(r["trade_date"])] = r["pct_chg"]
print(f"  {len(rows_spx)} SPX dates")

# ============== C2: 曙光初现SPX双涨散户割肉 ==============
print("\n" + "="*50)
print("C2_曙光初现SPX双涨散户割肉")
c2_signals = []
for code, bars in daily_by_code.items():
    if len(bars) < 250:
        continue
    pct_chgs = [b["pct_chg"] for b in bars]
    closes = [b["close"] for b in bars]
    for i in range(200, len(bars)):
        bar = bars[i]
        td = str(bar["trade_date"])
        close = bar["close"]
        pre_close = bar["pre_close"]
        pct = bar["pct_chg"]

        if close is None or close == 0 or pct is None:
            continue

        # 底20%(20日)
        if i < 20:
            continue
        h20 = max(closes[i-20:i+1])
        l20 = min(closes[i-20:i+1])
        pos20 = (close - l20) / (h20 - l20) if h20-l20 > 0 else 0.5
        if pos20 > 0.2:
            continue

        # 昨跌≤-3%
        if i < 1:
            continue
        prev_pct = pct_chgs[i-1]
        if prev_pct is None or prev_pct > -3:
            continue

        # 今涨≥2%
        if pct < 2:
            continue

        # 曙光初现: 昨收阴 + 今收阳 + 今close > (昨open+昨close)/2
        prev = bars[i-1]
        prev_open = prev["open"]
        prev_close = prev["close"]
        if prev_close is None or prev_open is None:
            continue
        if prev_close >= prev_open:  # 昨未收阴
            continue
        if bar["close"] <= bar["open"]:  # 今未收阳
            continue
        mid = (prev_open + prev_close) / 2
        if close <= mid:
            continue

        # 振幅≥5%
        ampl = (bar["high"] - bar["low"]) / pre_close * 100
        if ampl < 5:
            continue

        # VR
        db = daily_basic.get((code, td))
        if db is None:
            continue
        vr = db.get("volume_ratio")
        if vr is None or vr < 1.0:
            continue

        # CM≤30亿
        cmv = db.get("circ_mv", 0)
        if cmv is None or cmv > 300000:
            continue

        # SPX连续2日前日涨
        td_int = int(td.replace("-", ""))
        spx_keys_sorted = sorted(spx_dates.keys(), reverse=True)
        prev_spx = None
        prev2_spx = None
        count = 0
        for sk in spx_keys_sorted:
            sk_int = int(sk.replace("-", ""))
            if sk_int < td_int:
                if count == 0:
                    prev_spx = spx_dates[sk]
                    count += 1
                elif count == 1:
                    prev2_spx = spx_dates[sk]
                    break
        if prev_spx is None or prev2_spx is None or prev_spx <= 0 or prev2_spx <= 0:
            continue

        # 散户割肉
        mf = moneyflow.get((code, td))
        if mf is None:
            continue
        buy_sm = mf.get("buy_sm_vol", 0) or 0
        sell_sm = mf.get("sell_sm_vol", 0) or 0
        if sell_sm <= buy_sm:
            continue

        c2_signals.append((code, td, close))

print(f"  Signals: {len(c2_signals)}")

# ============== C5: 三连阴后放量反弹SPX散户割肉大单 ==============
print("\n" + "="*50)
print("C5_三连阴后放量反弹SPX散户割肉大单")
c5_signals = []
for code, bars in daily_by_code.items():
    if len(bars) < 250:
        continue
    pct_chgs = [b["pct_chg"] for b in bars]
    closes = [b["close"] for b in bars]
    for i in range(200, len(bars)):
        bar = bars[i]
        td = str(bar["trade_date"])
        close = bar["close"]
        pre_close = bar["pre_close"]
        pct = bar["pct_chg"]

        if close is None or close == 0 or pct is None:
            continue

        # 底20%(20日)
        if i < 20:
            continue
        h20 = max(closes[i-20:i+1])
        l20 = min(closes[i-20:i+1])
        pos20 = (close - l20) / (h20 - l20) if h20-l20 > 0 else 0.5
        if pos20 > 0.2:
            continue

        # 涨幅2-10%
        if pct < 2 or pct > 10:
            continue

        # 三连阴(前3日连跌)
        if i < 3:
            continue
        for k in range(1, 4):
            pp = pct_chgs[i-k]
            if pp is None or pp >= 0:
                continue

        # 振幅≥5%
        ampl = (bar["high"] - bar["low"]) / pre_close * 100
        if ampl < 5:
            continue

        # VR≥1.3
        db = daily_basic.get((code, td))
        if db is None:
            continue
        vr = db.get("volume_ratio")
        if vr is None or vr < 1.3:
            continue

        # CM≤30亿
        cmv = db.get("circ_mv", 0)
        if cmv is None or cmv > 300000:
            continue

        # SPX前日涨
        td_int = int(td.replace("-", ""))
        prev_spx = None
        for sk in sorted(spx_dates.keys(), reverse=True):
            sk_int = int(sk.replace("-", ""))
            if sk_int < td_int:
                prev_spx = spx_dates[sk]
                break
        if prev_spx is None or prev_spx <= 0:
            continue

        # 资金流
        mf = moneyflow.get((code, td))
        if mf is None:
            continue
        buy_sm = mf.get("buy_sm_vol", 0) or 0
        sell_sm = mf.get("sell_sm_vol", 0) or 0
        if sell_sm <= buy_sm:
            continue
        buy_lg = mf.get("buy_lg_vol", 0) or 0
        sell_lg = mf.get("sell_lg_vol", 0) or 0
        if buy_lg <= sell_lg:
            continue

        c5_signals.append((code, td, close))

print(f"  Signals: {len(c5_signals)}")


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


for name, signals in [("C2_曙光初现SPX双涨散户割肉", c2_signals), ("C5_三连阴后放量反弹SPX散户割肉大单", c5_signals)]:
    print(f"\n--- {name} ---")
    if len(signals) > 0:
        ret_data = calc_returns(signals, daily_by_code)
        stats = calc_stats(ret_data, len(signals))
    else:
        stats = calc_stats([], 0)
    for n in [1, 3, 5, 10, 20]:
        wr = stats.get(f"win_rate_{n}d", 0) * 100
        ret = stats.get(f"ret_{n}d", 0) * 100
        sharpe = stats.get(f"sharpe_{n}d", 0)
        print(f"  T+{n}d: N={stats['signal_count']}, WR={wr:.2f}%, Ret={ret:.2f}%, Sharpe={sharpe:.3f}")
    wr5 = stats.get("win_rate_5d", 0) * 100
    ret5 = stats.get("ret_5d", 0) * 100
    cnt = stats.get("signal_count", 0)
    passed = wr5 >= 52 and ret5 >= 3 and cnt >= 200
    print(f"  PASS: {'✅' if passed else '❌'}")
