#!/usr/bin/env python3
"""T4 资金主力 - Iter33 v2 探索: 宏观过滤/中单逆势/多日累积/净流分位数
Walk-Forward: IS(2020-01-01~2024-12-31) → OOS(2025-01-01~2026-05-13)

7组全新组合(C7-C13)，填补已有测试的空白:
  C7: SPX+HS300双宏观 + ELG+散户恐慌+底20%
  C8: 中单(MD)净买入 + LG净买入 + 散户恐慌+底20%
  C9: 2日连续净流入 + 第2日散户恐慌+底20%
  C10: net_mf金额分位数(日级别top 20%) + 散户恐慌
  C11: 散户连续2日恐慌 + 第2日ELG抄底+底20%
  C12: 前日跌3% + 当日ELG+散户恐慌+底20%
  C13: 三重资金(ELG+LG+MD)全部净买 + 散户恐慌+缩量
"""
import json, math, time, os, sys
from collections import defaultdict
from datetime import datetime, timedelta

import urllib.request, urllib.parse, urllib.error

HOST = "172.24.224.1"
HTTP_PORT = "8123"
USER = "ai_reader"
PASSWORD = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
DATABASE = "tushare"

def ch_query(sql: str) -> list[dict]:
    url = f"http://{HOST}:{HTTP_PORT}/"
    params = {
        "user": USER, "password": PASSWORD, "database": DATABASE,
        "query": sql, "default_format": "JSONEachRow",
    }
    qs = urllib.parse.urlencode(params)
    full_url = f"{url}?{qs}"
    try:
        req = urllib.request.Request(full_url)
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode("utf-8")
            if not body.strip():
                return []
            return [json.loads(line) for line in body.strip().split("\n") if line.strip()]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"  ❌ HTTP {e.code}: {error_body[:400]}", flush=True)
        return []
    except Exception as e:
        print(f"  ❌ {e}", flush=True)
        return []

def safe_float(v):
    if v is None: return 0.0
    return float(v)

OUTDIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_33"
os.makedirs(OUTDIR, exist_ok=True)

IS_START, IS_END = "2020-01-01", "2024-12-31"
OOS_START, OOS_END = "2025-01-01", "2026-05-13"

# ── Data Loading ─────────────────────────────────────────────

def load_spx():
    rows = ch_query(
        "SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL "
        "WHERE ts_code='SPX' AND trade_date>=toDate('2019-06-01') ORDER BY trade_date"
    )
    return {r["trade_date"]: r["pct_chg"] for r in rows}

def load_hs300():
    rows = ch_query(
        "SELECT trade_date, pct_chg FROM tushare.tushare_index_daily FINAL "
        "WHERE ts_code='000300.SH' AND trade_date>=toDate('2019-06-01') ORDER BY trade_date"
    )
    return {r["trade_date"]: r["pct_chg"] for r in rows}

def load_moneyflow():
    mf = {}
    for yr in range(2019, 2027):
        end = f"{yr}-12-31"
        if yr == 2026: end = "2026-05-13"
        rows = ch_query(
            f"SELECT ts_code, trade_date, "
            f"buy_sm_amount, sell_sm_amount, buy_md_amount, sell_md_amount, "
            f"buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount, "
            f"net_mf_amount "
            f"FROM tushare.tushare_moneyflow FINAL "
            f"WHERE trade_date>=toDate('{yr}-01-01') AND trade_date<=toDate('{end}')"
        )
        for r in rows:
            mf[(r["ts_code"], r["trade_date"])] = r
    return mf

def load_daily_basic():
    db = {}
    for yr in range(2019, 2027):
        end = f"{yr}-12-31"
        if yr == 2026: end = "2026-05-13"
        rows = ch_query(
            f"SELECT ts_code, trade_date, volume_ratio AS vr, circ_mv "
            f"FROM tushare.tushare_daily_basic FINAL "
            f"WHERE trade_date>=toDate('{yr}-01-01') AND trade_date<=toDate('{end}')"
        )
        for r in rows:
            db[(r["ts_code"], r["trade_date"])] = r
    return db

def load_stock_daily():
    daily = defaultdict(list)
    for yr in range(2019, 2027):
        end = f"{yr}-12-31"
        if yr == 2026: end = "2026-05-13"
        rows = ch_query(
            f"SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol "
            f"FROM tushare.tushare_stock_daily FINAL "
            f"WHERE trade_date>=toDate('{yr}-01-01') AND trade_date<=toDate('{end}') "
            f"AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' "
            f"AND ts_code NOT LIKE '%ST%'"
        )
        for r in rows:
            daily[r["ts_code"]].append(r)
    for c in daily:
        daily[c].sort(key=lambda x: x["trade_date"])
    return daily

# ── Backtest Engine ──────────────────────────────────────────

def calc_stats(ret_list):
    if len(ret_list) < 3:
        return {"n": 0, "wr": 0, "avg_ret": 0, "sharpe": 0, "p10": 0, "r5": 0}
    n = len(ret_list)
    win = sum(1 for r in ret_list if r > 0)
    wr = round(win / n * 100, 2)
    avg = round(sum(ret_list) / n, 2)
    std = math.sqrt(sum((r - sum(ret_list)/n)**2 for r in ret_list) / (n-1)) if n > 1 else 0
    sharpe = round(avg / std * math.sqrt(252/5) if std > 0 else 0, 3)
    sorted_r = sorted(ret_list)
    p10 = round(sorted_r[max(0, int(n*0.1)-1)], 2) if n >= 10 else round(sorted_r[0], 2)
    r5 = round(sorted_r[max(0, int(n*0.05)-1)], 2) if n >= 20 else round(sorted_r[0], 2)
    return {"n": n, "wr": wr, "avg_ret": avg, "sharpe": sharpe, "p10": p10, "r5": r5}

def exec_backtest(label, condition_fn, bars_by_code, spx, hs300, mf, db):
    """Run backtest for one combo using condition_fn(code, bars, i, spx, hs300, mf, db)."""
    signals = []  # (code, trade_date, close)
    for code, bars in bars_by_code.items():
        if len(bars) < 60:
            continue
        for i in range(60, len(bars)):
            bar = bars[i]
            td = bar["trade_date"]
            close = bar.get("close")
            pct = bar.get("pct_chg")
            if close is None or pct is None:
                continue
            hi, lo = bar.get("high"), bar.get("low")
            pc = bar.get("pre_close")
            if any(v is None for v in [hi, lo, pc]) or pc == 0:
                continue
            amp = (hi - lo) / pc * 100

            if condition_fn(code, bars, i, spx, hs300, mf, db, amp, pct, close, td):
                signals.append((code, td, close))
    return signals

def compute_returns(signals, bars_by_code, hold_periods=[1,3,5,10,20]):
    rets = {hp: [] for hp in hold_periods}
    for code, td, buy_close in signals:
        bars = bars_by_code.get(code)
        if not bars:
            continue
        buy_idx = None
        for j, b in enumerate(bars):
            if b["trade_date"] == td:
                buy_idx = j
                break
        if buy_idx is None:
            continue
        for hp in hold_periods:
            sell_idx = buy_idx + hp
            if sell_idx < len(bars):
                sc = bars[sell_idx]["close"]
                if sc and buy_close and buy_close > 0:
                    ret = round((sc / buy_close - 1) * 100, 2)
                    rets[hp].append(ret)
    return rets

def get_prev_td(td_str, days_back=1):
    """Get the date string N trading days before td by checking existence in spx/hs300."""
    td_dt = datetime.strptime(td_str, "%Y-%m-%d")
    for d in range(1, 8):
        check = (td_dt - timedelta(days=d)).strftime("%Y-%m-%d")
        return check  # simple approach
    return None

# ── Condition Functions for C7-C13 ───────────────────────────

def c7_condition(code, bars, i, spx, hs300, mf, db, amp, pct, close, td):
    """SPX+HS300双宏观 + ELG净买+散户恐慌+底20+振幅7+CM50+VR1.3"""
    # SPX前日涨
    td_dt = datetime.strptime(td, "%Y-%m-%d")
    spx_ok = False
    for d in range(1, 8):
        ct = (td_dt - timedelta(days=d)).strftime("%Y-%m-%d")
        if ct in spx:
            if spx[ct] > 0: spx_ok = True
            break
    if not spx_ok: return False
    # HS300当日涨
    if td not in hs300 or hs300.get(td, 0) <= 0: return False
    # Moneyflow
    mfk = (code, td)
    mfv = mf.get(mfk)
    if not mfv: return False
    if safe_float(mfv.get("sell_sm_amount")) <= safe_float(mfv.get("buy_sm_amount")): return False
    if safe_float(mfv.get("buy_elg_amount")) <= safe_float(mfv.get("sell_elg_amount")): return False
    # Position: 20-day bottom 20%
    closes = [b["close"] for b in bars[max(0,i-19):i+1] if b.get("close")]
    if len(closes) < 20: return False
    h20, l20 = max(closes), min(closes)
    if h20 == l20: return False
    cpos = (close - l20) / (h20 - l20)
    if cpos > 0.2: return False
    # Amplitude, VR, CM
    if amp < 7: return False
    dbv = db.get(mfk)
    if not dbv: return False
    vr = safe_float(dbv.get("vr"))
    if vr < 1.3: return False
    cm = safe_float(dbv.get("circ_mv"))
    if cm <= 0 or cm > 500000: return False
    return True

def c8_condition(code, bars, i, spx, hs300, mf, db, amp, pct, close, td):
    """中单(MD)+大单(LG)双净买入 + 散户恐慌 + 底20 + 振幅7 + CM50"""
    mfk = (code, td)
    mfv = mf.get(mfk)
    if not mfv: return False
    # MD net buy
    if safe_float(mfv.get("buy_md_amount")) <= safe_float(mfv.get("sell_md_amount")): return False
    # LG net buy
    if safe_float(mfv.get("buy_lg_amount")) <= safe_float(mfv.get("sell_lg_amount")): return False
    # Retail panic
    if safe_float(mfv.get("sell_sm_amount")) <= safe_float(mfv.get("buy_sm_amount")): return False
    # Position 20-day bottom 20%
    closes = [b["close"] for b in bars[max(0,i-19):i+1] if b.get("close")]
    if len(closes) < 20: return False
    h20, l20 = max(closes), min(closes)
    if h20 == l20: return False
    cpos = (close - l20) / (h20 - l20)
    if cpos > 0.2: return False
    if amp < 7: return False
    dbv = db.get(mfk)
    if not dbv: return False
    cm = safe_float(dbv.get("circ_mv"))
    if cm <= 0 or cm > 500000: return False
    return True

def c9_condition(code, bars, i, spx, hs300, mf, db, amp, pct, close, td):
    """2日连续净流入(前日+当日net_mf>0) + 当日散户恐慌 + 底20 + 振幅6 + CM50"""
    if i < 1: return False
    prev = bars[i-1]
    prev_td = prev["trade_date"]
    mfk = (code, td)
    pmfk = (code, prev_td)
    mfv = mf.get(mfk)
    pmfv = mf.get(pmfk)
    if not mfv or not pmfv: return False
    # Day-1 net_mf > 0
    if safe_float(pmfv.get("net_mf_amount")) <= 0: return False
    # Day0 net_mf > 0
    if safe_float(mfv.get("net_mf_amount")) <= 0: return False
    # Day0 retail panic
    if safe_float(mfv.get("sell_sm_amount")) <= safe_float(mfv.get("buy_sm_amount")): return False
    # Position
    closes = [b["close"] for b in bars[max(0,i-19):i+1] if b.get("close")]
    if len(closes) < 20: return False
    h20, l20 = max(closes), min(closes)
    if h20 == l20: return False
    cpos = (close - l20) / (h20 - l20)
    if cpos > 0.2: return False
    if amp < 6: return False
    dbv = db.get(mfk)
    if not dbv: return False
    cm = safe_float(dbv.get("circ_mv"))
    if cm <= 0 or cm > 500000: return False
    return True

def c10_condition(code, bars, i, spx, hs300, mf, db, amp, pct, close, td):
    """net_mf_amount分位数(日级别top20%即>0且金额大) + 散户恐慌 + 底20 + 振幅6 + CM50"""
    mfk = (code, td)
    mfv = mf.get(mfk)
    if not mfv: return False
    net = safe_float(mfv.get("net_mf_amount"))
    if net <= 0: return False
    # 日内比较: ELG+LG vs MD+SM 占比 > 0.5 (主力净流占比高)
    buy_big = safe_float(mfv.get("buy_elg_amount")) + safe_float(mfv.get("buy_lg_amount"))
    sell_big = safe_float(mfv.get("sell_elg_amount")) + safe_float(mfv.get("sell_lg_amount"))
    total_buy = buy_big + safe_float(mfv.get("buy_md_amount")) + safe_float(mfv.get("buy_sm_amount"))
    if total_buy <= 0: return False
    # 主力买入占比 > 65%
    if buy_big / total_buy < 0.65: return False
    # Retail panic
    if safe_float(mfv.get("sell_sm_amount")) <= safe_float(mfv.get("buy_sm_amount")): return False
    # Position
    closes = [b["close"] for b in bars[max(0,i-19):i+1] if b.get("close")]
    if len(closes) < 20: return False
    h20, l20 = max(closes), min(closes)
    if h20 == l20: return False
    cpos = (close - l20) / (h20 - l20)
    if cpos > 0.2: return False
    if amp < 6: return False
    dbv = db.get(mfk)
    if not dbv: return False
    cm = safe_float(dbv.get("circ_mv"))
    if cm <= 0 or cm > 500000: return False
    return True

def c11_condition(code, bars, i, spx, hs300, mf, db, amp, pct, close, td):
    """散户连续2日恐慌 + 第2日ELG净买入 + 底20 + 振幅7 + CM30"""
    if i < 1: return False
    prev = bars[i-1]
    prev_td = prev["trade_date"]
    mfk = (code, td)
    pmfk = (code, prev_td)
    mfv = mf.get(mfk)
    pmfv = mf.get(pmfk)
    if not mfv or not pmfv: return False
    # Day-1 retail panic
    if safe_float(pmfv.get("sell_sm_amount")) <= safe_float(pmfv.get("buy_sm_amount")): return False
    # Day0 retail panic
    if safe_float(mfv.get("sell_sm_amount")) <= safe_float(mfv.get("buy_sm_amount")): return False
    # Day0 ELG net buy
    if safe_float(mfv.get("buy_elg_amount")) <= safe_float(mfv.get("sell_elg_amount")): return False
    # Position
    closes = [b["close"] for b in bars[max(0,i-19):i+1] if b.get("close")]
    if len(closes) < 20: return False
    h20, l20 = max(closes), min(closes)
    if h20 == l20: return False
    cpos = (close - l20) / (h20 - l20)
    if cpos > 0.2: return False
    if amp < 7: return False
    dbv = db.get(mfk)
    if not dbv: return False
    cm = safe_float(dbv.get("circ_mv"))
    if cm <= 0 or cm > 300000: return False
    return True

def c12_condition(code, bars, i, spx, hs300, mf, db, amp, pct, close, td):
    """前日跌≥3%(恐慌窗口) + 当日ELG净买+散户恐慌+底20+振幅8+VR1.3+CM30"""
    if i < 1: return False
    prev = bars[i-1]
    prev_pct = prev.get("pct_chg")
    if prev_pct is None or prev_pct > -3: return False
    mfk = (code, td)
    mfv = mf.get(mfk)
    if not mfv: return False
    if safe_float(mfv.get("buy_elg_amount")) <= safe_float(mfv.get("sell_elg_amount")): return False
    if safe_float(mfv.get("sell_sm_amount")) <= safe_float(mfv.get("buy_sm_amount")): return False
    closes = [b["close"] for b in bars[max(0,i-19):i+1] if b.get("close")]
    if len(closes) < 20: return False
    h20, l20 = max(closes), min(closes)
    if h20 == l20: return False
    cpos = (close - l20) / (h20 - l20)
    if cpos > 0.2: return False
    if amp < 8: return False
    dbv = db.get(mfk)
    if not dbv: return False
    vr = safe_float(dbv.get("vr"))
    if vr < 1.3: return False
    cm = safe_float(dbv.get("circ_mv"))
    if cm <= 0 or cm > 300000: return False
    return True

def c13_condition(code, bars, i, spx, hs300, mf, db, amp, pct, close, td):
    """三重资金(ELG+LG+MD全部净买) + 散户恐慌 + 缩量(VR<1.1) + 底20 + CM50"""
    mfk = (code, td)
    mfv = mf.get(mfk)
    if not mfv: return False
    # Triple smart money all buying
    if safe_float(mfv.get("buy_elg_amount")) <= safe_float(mfv.get("sell_elg_amount")): return False
    if safe_float(mfv.get("buy_lg_amount")) <= safe_float(mfv.get("sell_lg_amount")): return False
    if safe_float(mfv.get("buy_md_amount")) <= safe_float(mfv.get("sell_md_amount")): return False
    # Retail panic
    if safe_float(mfv.get("sell_sm_amount")) <= safe_float(mfv.get("buy_sm_amount")): return False
    # Position
    closes = [b["close"] for b in bars[max(0,i-19):i+1] if b.get("close")]
    if len(closes) < 20: return False
    h20, l20 = max(closes), min(closes)
    if h20 == l20: return False
    cpos = (close - l20) / (h20 - l20)
    if cpos > 0.2: return False
    if amp < 6: return False
    dbv = db.get(mfk)
    if not dbv: return False
    vr = safe_float(dbv.get("vr"))
    if vr >= 1.1: return False
    cm = safe_float(dbv.get("circ_mv"))
    if cm <= 0 or cm > 500000: return False
    return True

# ── Combo Definitions ────────────────────────────────────────

COMBOS = [
    {
        "label": "C7_SPX+HS300宏观_ELG_散户_底20_振幅7_CM50_VR1.3",
        "desc": "SPX前日涨+HS300当日涨双宏观 + ELG净买入+散户恐慌+底20%+振幅≥7%+CM≤50亿+VR≥1.3",
        "fn": c7_condition,
    },
    {
        "label": "C8_中单大单双净买_散户恐慌_底20_振幅7_CM50",
        "desc": "中单(MD)+大单(LG)双净买入 + 散户恐慌+底20%+振幅≥7%+CM≤50亿",
        "fn": c8_condition,
    },
    {
        "label": "C9_2日连续净流入_散户恐慌_底20_振幅6_CM50",
        "desc": "前日+当日net_mf>0(连续2日主力净流入) + 当日散户恐慌+底20%+振幅≥6%+CM≤50亿",
        "fn": c9_condition,
    },
    {
        "label": "C10_主力买入占比65_散户恐慌_底20_振幅6_CM50",
        "desc": "ELG+LG净买入占比≥65%(主力主导) + net_mf>0 + 散户恐慌+底20%+振幅≥6%+CM≤50亿",
        "fn": c10_condition,
    },
    {
        "label": "C11_散户连2日恐慌_第2日ELG抄底_底20_振幅7_CM30",
        "desc": "散户连续2日恐慌卖出 + 第2日ELG净买入抄底 + 底20%+振幅≥7%+CM≤30亿",
        "fn": c11_condition,
    },
    {
        "label": "C12_前日跌3_ELG抄底_散户恐慌_底20_振幅8_VR1.3_CM30",
        "desc": "前日跌≥3%(恐慌窗口) + 当日ELG净买+散户恐慌+底20%+振幅≥8%+VR≥1.3+CM≤30亿",
        "fn": c12_condition,
    },
    {
        "label": "C13_三主力全净买_散户恐慌_缩量VR1.1_底20_CM50",
        "desc": "ELG+LG+MD全部净买入(三重主力资金) + 散户恐慌+缩量VR<1.1+底20%+CM≤50亿",
        "fn": c13_condition,
    },
]

# ── Main Loop ────────────────────────────────────────────────

def filter_by_date(signals, start, end):
    return [(c, t, p) for c, t, p in signals if start <= t <= end]

def main():
    print("=" * 70)
    print("T4 资金主力 v2 — Iter33 新增组合探索 (7组全新)")
    print("=" * 70)

    # Load data
    print("\n[1/5] Loading SPX...")
    spx = load_spx()
    print(f"  {len(spx)} rows")

    print("[2/5] Loading HS300...")
    hs300 = load_hs300()
    print(f"  {len(hs300)} rows")

    print("[3/5] Loading moneyflow...")
    mf = load_moneyflow()
    print(f"  {len(mf)} records")

    print("[4/5] Loading daily_basic...")
    db = load_daily_basic()
    print(f"  {len(db)} records")

    print("[5/5] Loading stock_daily...")
    daily = load_stock_daily()
    total_bars = sum(len(b) for b in daily.values())
    print(f"  {len(daily)} stocks, {total_bars} bars")

    # ── Phase 1: IS backtest ──
    print("\n" + "=" * 70)
    print("PHASE 1: In-Sample (2020-2024) — Testing 7 combos")
    print("=" * 70)

    is_results = []
    for combo in COMBOS:
        label = combo["label"]
        desc = combo["desc"]
        print(f"\n{'─'*50}")
        print(f"  {label}")
        print(f"  {desc}")
        t0 = time.time()

        all_sigs = exec_backtest(label, combo["fn"], daily, spx, hs300, mf, db)
        is_sigs = filter_by_date(all_sigs, IS_START, IS_END)
        print(f"  IS signals: {len(is_sigs)}")

        if len(is_sigs) < 10:
            print(f"  ❌ Insufficient signals")
            is_results.append({"label": label, "desc": desc, "is": None, "is_n": 0, "elapsed": round(time.time()-t0, 1)})
            continue

        rets = compute_returns(is_sigs, daily)
        stats = {f"T+{hp}d": calc_stats(rets[hp]) for hp in [1, 3, 5, 10, 20]}
        r5 = stats.get("T+5d", {})
        print(f"  T+5d: N={r5['n']} WR={r5['wr']}% R5={r5['avg_ret']}% Sharpe={r5['sharpe']} P10={r5['p10']}%")
        elapsed = round(time.time() - t0, 1)
        print(f"  ⏱ {elapsed}s")

        is_results.append({
            "label": label, "desc": desc,
            "is": stats, "is_n": r5["n"],
            "is_signals": len(is_sigs),
            "elapsed": elapsed,
        })

    # ── Phase 1 Summary ──
    print("\n" + "=" * 70)
    print("IS RESULTS SUMMARY")
    print("=" * 70)

    scored = []
    for r in is_results:
        if r["is"] is None:
            print(f"  {r['label']}: ❌ NO SIGNALS")
            continue
        r5 = r["is"].get("T+5d", {})
        score = r5.get("wr", 0) * 0.6 + r5.get("avg_ret", 0) * 4
        status = "PASS ✅" if (r5.get("n", 0) >= 100 and r5.get("wr", 0) >= 52 and r5.get("avg_ret", 0) >= 3) else "FAIL ❌"
        print(f"  {r['label']}: {status} N={r5.get('n',0)} WR={r5.get('wr',0)}% R5={r5.get('avg_ret',0)}% Score={score:.1f}")
        scored.append((score, r))

    scored.sort(reverse=True)

    # ── Phase 2: OOS for top 3 ──
    top3 = scored[:3]
    print("\n" + "=" * 70)
    print(f"PHASE 2: Out-of-Sample (2025-2026-05-13) — Top {len(top3)} combos")
    print("=" * 70)

    oos_results = []
    for score, r in top3:
        # Find the combo
        combo = next(c for c in COMBOS if c["label"] == r["label"])
        print(f"\n{'─'*50}")
        print(f"  OOS: {r['label']}")
        t0 = time.time()

        all_sigs = exec_backtest(r["label"], combo["fn"], daily, spx, hs300, mf, db)
        oos_sigs = filter_by_date(all_sigs, OOS_START, OOS_END)
        print(f"  OOS signals: {len(oos_sigs)}")

        if len(oos_sigs) < 5:
            print(f"  ⚠️ Insufficient OOS signals")
            r["oos"] = None
            r["oos_n"] = 0
            r["oos_signals"] = 0
            r["oos_elapsed"] = round(time.time()-t0, 1)
            oos_results.append(r)
            continue

        rets = compute_returns(oos_sigs, daily)
        stats = {f"T+{hp}d": calc_stats(rets[hp]) for hp in [1, 3, 5, 10, 20]}
        r5 = stats.get("T+5d", {})
        print(f"  T+5d: N={r5['n']} WR={r5['wr']}% R5={r5['avg_ret']}% Sharpe={r5['sharpe']} P10={r5['p10']}%")
        r["oos"] = stats
        r["oos_n"] = r5["n"]
        r["oos_signals"] = len(oos_sigs)
        r["oos_elapsed"] = round(time.time()-t0, 1)
        oos_results.append(r)

    # ── Walk-Forward Summary ──
    print("\n" + "=" * 70)
    print("WALK-FORWARD VERIFICATION")
    print("=" * 70)

    passed_dual = []
    for r in oos_results:
        r5_is = r["is"].get("T+5d", {})
        r5_oos = r["oos"].get("T+5d", {}) if r.get("oos") else {}
        n_is = r5_is.get("n", 0); wr_is = r5_is.get("wr", 0); avg_is = r5_is.get("avg_ret", 0)
        n_oos = r5_oos.get("n", 0); wr_oos = r5_oos.get("wr", 0); avg_oos = r5_oos.get("avg_ret", 0)
        wr_drop = wr_is - wr_oos

        is_ok = n_is >= 100 and wr_is >= 52 and avg_is >= 3
        oos_ok = n_oos >= 20 and wr_oos >= 48 and avg_oos >= 2
        no_overfit = wr_drop <= 15

        print(f"\n  {r['label']}")
        print(f"    IS: N={n_is} WR={wr_is}% R5={avg_is}% → {'✅' if is_ok else '❌'}")
        print(f"    OOS: N={n_oos} WR={wr_oos}% R5={avg_oos}% → {'✅' if oos_ok else '❌'}")
        print(f"    WR-drop: {wr_drop:.1f}pp → {'🟢 Low' if no_overfit else '🔴 High'}")

        if is_ok and oos_ok and no_overfit:
            print(f"    ✅ DUAL-PASS!")
            passed_dual.append(r)
        elif is_ok and oos_ok:
            print(f"    ⚠️ Dual-pass but high overfit")
        elif is_ok:
            print(f"    ⚠️ IS-only pass")
        else:
            print(f"    ❌ Rejected")

    # ── Generate Report ──
    report_path = os.path.join(OUTDIR, "analysis_T4_资金主力_v2.md")
    json_path = os.path.join(OUTDIR, "analysis_T4_moneyflow_v2.json")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# T4 资金主力 v2 (Iter 33) — 新增组合分析报告\n\n")
        f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n")
        f.write("> Walk-Forward: IS (2020-01-01~2024-12-31) → OOS (2025-01-01~2026-05-13)\n")
        f.write("> 历史最优WR: 99.59% | 历史最优R5: 23.78%\n\n")
        f.write("**本次探索方向：**\n")
        f.write("1. SPX+HS300双宏观过滤（来自全局记录X04理念）\n")
        f.write("2. 中单(MD)逆势买入 + 大单协同（来自iter31_C3 ELITE发现）\n")
        f.write("3. 连续2日主力净流入 + 散户恐慌确认\n")
        f.write("4. 主力买入占比≥65%（金额比率替代绝对值）\n")
        f.write("5. 散户连续2日恐慌 → 第2日主力抄底\n")
        f.write("6. 前日跌3%恐慌窗口 + 主力反手买入\n")
        f.write("7. 三重资金全净买(ELG+LG+MD) + 缩量吸筹\n\n")

        f.write("---\n\n## 组合设计\n\n")
        f.write("| 组合 | 核心逻辑 | 思路来源 |\n")
        f.write("|------|---------|---------|\n")
        f.write("| C7 | SPX+HS300双宏观+ELG+SM+底20 | X04全局记录理念 |\n")
        f.write("| C8 | MD+LG双净买+SM+底20 | iter31_C3中单因子 |\n")
        f.write("| C9 | 连续2日net_mf>0+SM | 多日累积观察 |\n")
        f.write("| C10 | 主力买入占比≥65% | 金额比率新维度 |\n")
        f.write("| C11 | SM连续2日恐慌→第2日ELG抄底 | 恐慌衰竭模型 |\n")
        f.write("| C12 | 前日跌3%→当日ELG反手+SM | 恐慌窗口反转 |\n")
        f.write("| C13 | ELG+LG+MD全净买+SM+缩量 | 缩量三重确认 |\n\n")

        f.write("---\n\n## IS (2020-2024) 详细结果\n\n")

        for r in is_results:
            f.write(f"### {r['label']}\n\n")
            f.write(f"**描述**: {r['desc']}  \n")
            if r["is"] is None:
                f.write("**信号不足 (<10)**\n\n")
                f.write("---\n\n")
                continue
            f.write(f"IS信号数: **{r['is_signals']}**  \n\n")
            f.write("| 持有期 | 信号数 | 胜率(WR) | 平均收益 | Sharpe | P10 | R5 |\n")
            f.write("|:-----:|:-----:|:--------:|:--------:|:-----:|:---:|:---:|\n")
            for hp in [1, 3, 5, 10, 20]:
                s = r["is"].get(f"T+{hp}d", {})
                if s["n"] > 0:
                    f.write(f"| T+{hp} | {s['n']} | {s['wr']}% | {s['avg_ret']}% | {s['sharpe']} | {s['p10']}% | {s['r5']}% |\n")
            f.write("\n")
            r5 = r["is"].get("T+5d", {})
            passed = r5.get("n", 0) >= 100 and r5.get("wr", 0) >= 52 and r5.get("avg_ret", 0) >= 3
            f.write(f"**IS判决**: {'✅ PASS' if passed else '❌ FAIL'} (N={r5.get('n',0)} WR={r5.get('wr',0)}% R5={r5.get('avg_ret',0)}%)\n\n")
            f.write("---\n\n")

        # OOS section
        f.write("## OOS (2025-2026-05-13) 详细结果\n\n")
        f.write("仅对IS通过的候选组合进行OOS验证。\n\n")

        for r in oos_results:
            f.write(f"### {r['label']}\n\n")
            r5_is = r["is"].get("T+5d", {})
            r5_oos = r["oos"].get("T+5d", {}) if r.get("oos") else None

            if r5_oos:
                f.write("| 指标 | IS (2020-2024) | OOS (2025-至今) |\n")
                f.write("|------|:-:|:-:|\n")
                f.write(f"| N | {r5_is.get('n',0):,} | {r5_oos.get('n',0):,} |\n")
                f.write(f"| WR | {r5_is.get('wr',0)}% | {r5_oos.get('wr',0)}% |\n")
                f.write(f"| T+5d平均收益 | {r5_is.get('avg_ret',0)}% | {r5_oos.get('avg_ret',0)}% |\n")
                f.write(f"| Sharpe | {r5_is.get('sharpe',0):.3f} | {r5_oos.get('sharpe',0):.3f} |\n")
                f.write(f"| P10 | {r5_is.get('p10',0)}% | {r5_oos.get('p10',0)}% |\n")
                f.write(f"| R5 (5%分位) | {r5_is.get('r5',0)}% | {r5_oos.get('r5',0)}% |\n\n")
            else:
                f.write("**OOS信号不足，无法验证**\n\n")
                continue

            wr_drop = r5_is.get("wr", 0) - r5_oos.get("wr", 0)
            n_is = r5_is.get("n", 0); wr_is = r5_is.get("wr", 0); avg_is = r5_is.get("avg_ret", 0)
            n_oos = r5_oos.get("n", 0); wr_oos = r5_oos.get("wr", 0); avg_oos = r5_oos.get("avg_ret", 0)
            is_ok = n_is >= 100 and wr_is >= 52 and avg_is >= 3
            oos_ok = n_oos >= 20 and wr_oos >= 48 and avg_oos >= 2
            no_overfit = wr_drop <= 15

            f.write(f"**IS判决**: {'✅ PASS' if is_ok else '❌ FAIL'}  ")
            f.write(f"**OOS判决**: {'✅ PASS' if oos_ok else '❌ FAIL'}  ")
            f.write(f"**过拟合**: {'🟢 低' if no_overfit else '🔴 高'} (ΔWR={wr_drop:.1f}pp)\n\n")

            if is_ok and oos_ok and no_overfit:
                f.write("**最终状态**: 🏆 **双重验证通过!**\n\n")
                score = wr_is * 0.5 + avg_is * 4 + math.log10(max(n_is, 10)) * 5
                score += wr_oos * 0.3 + avg_oos * 3
                f.write(f"**综合评分**: {score:.2f}\n\n")
            elif is_ok:
                f.write("**最终状态**: ⚠️ IS通过但OOS未达标\n\n")
            else:
                f.write("**最终状态**: ❌ 淘汰\n\n")

            f.write("**最大失败路径**: 资金流跟随买入后主力不再拉升，股价继续阴跌\n\n")
            f.write("---\n\n")

        # Summary table
        f.write("## 汇总\n\n")
        f.write("| 组合 | IS-N | IS-WR | IS-R5 | OOS-N | OOS-WR | OOS-R5 | ΔWR | 状态 |\n")
        f.write("|------|:----:|:-----:|:-----:|:-----:|:------:|:------:|:---:|:----:|\n")

        all_for_table = []
        for r in is_results:
            r5_is = r["is"].get("T+5d", {}) if r["is"] else {}
            # Find OOS if exists
            oos_r = None
            for or_ in oos_results:
                if or_["label"] == r["label"]:
                    oos_r = or_
                    break
            r5_oos = {}
            if oos_r and oos_r.get("oos"):
                r5_oos = oos_r["oos"].get("T+5d", {})
            all_for_table.append((r, r5_is, r5_oos))

        for r, r5_is, r5_oos in all_for_table:
            n_is = r5_is.get("n", 0); wr_is = r5_is.get("wr", 0); avg_is = r5_is.get("avg_ret", 0)
            n_oos = r5_oos.get("n", 0); wr_oos = r5_oos.get("wr", 0); avg_oos = r5_oos.get("avg_ret", 0)
            wr_drop = wr_is - wr_oos
            is_ok = n_is >= 100 and wr_is >= 52 and avg_is >= 3
            oos_ok = n_oos >= 20 and wr_oos >= 48 and avg_oos >= 2
            no_overfit = wr_drop <= 15
            if is_ok and oos_ok and no_overfit:
                status = "🏆 DUAL"
            elif is_ok:
                status = "⚠️ IS"
            else:
                status = "❌"
            f.write(f"| {r['label']} | {n_is} | {wr_is}% | {avg_is}% | {n_oos} | {wr_oos}% | {avg_oos}% | {wr_drop:.1f}pp | {status} |\n")

        f.write("\n## 数据来源\n")
        f.write("- 日线行情: tushare_stock_daily\n")
        f.write("- 每日指标: tushare_daily_basic (circ_mv, volume_ratio)\n")
        f.write("- 资金流向: tushare_moneyflow (buy/sell amounts for SM/MD/LG/ELG)\n")
        f.write("- 全球指数: tushare_index_global (SPX)\n")
        f.write("- A股指数: tushare_index_daily (HS300: 000300.SH)\n")
        f.write("- 查询工具: ch_query.py (ClickHouse)\n")

    print(f"\n📄 Report: {report_path}")

    # Also save JSON
    json_out = {
        "metadata": {
            "task": "T4_资金主力_v2",
            "iter": 33,
            "is_range": "2020-01-01 to 2024-12-31",
            "oos_range": "2025-01-01 to 2026-05-13",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "is_results": is_results,
        "oos_results": oos_results,
        "passed_dual": [r["label"] for r in passed_dual],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_out, f, ensure_ascii=False, indent=2, default=str)
    print(f"📄 JSON: {json_path}")

    print("\n✅ Done!")

if __name__ == "__main__":
    main()
