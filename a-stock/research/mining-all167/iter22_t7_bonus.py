#!/usr/bin/env python3
"""
Iter22 T7: Bonus tests — Fix C2 Shibor query + C1扩容(C1b) + additional combos
"""
import json
import subprocess
import math
import os
from datetime import datetime, timedelta

CH_QUERY = "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py"
DT_START = "2024-01-01"
DT_END = "2026-05-12"

def sql(query):
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"SQL ERROR: {r.stderr[:200]}")
        return []
    if not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout)
    except:
        return []

def compute_metrics(results, label):
    n = len(results)
    unique_codes = len(set(r.get('code', '') for r in results))
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"  SIGNALS: {n}")
    print(f"  UNIQUE STOCKS: {unique_codes}")

    if n < 10:
        print(f"  Too few signals (< 10)")
        return {
            "label": label, "signal_count": n, "unique_stocks": unique_codes,
            "win_rate_5d": 0, "avg_ret_5d": 0, "avg_ret_10d": 0, "avg_ret_20d": 0,
            "sharpe_5d": 0, "p10_ret_5d": 0, "p90_ret_5d": 0, "max_dd_5d": 0
        }

    ret5 = [r.get("r5", 0) or 0 for r in results]
    ret10 = [r.get("r10", 0) or 0 for r in results]
    ret20 = [r.get("r20", 0) or 0 for r in results]

    a5 = sum(ret5) / n * 100
    a10 = sum(ret10) / n * 100
    a20 = sum(ret20) / n * 100

    w5 = sum(1 for r in ret5 if r > 0) / n * 100
    w10 = sum(1 for r in ret10 if r > 0) / n * 100
    w20 = sum(1 for r in ret20 if r > 0) / n * 100

    std5 = math.sqrt(sum((x - a5/100)**2 for x in ret5) / n) if n > 1 else 1
    sp5 = (a5 / 100) / std5 * math.sqrt(252 / 5) if std5 > 0 else 0

    sorted_ret5 = sorted(ret5)
    p10 = sorted_ret5[max(0, int(n * 0.1))] * 100
    p90 = sorted_ret5[min(n-1, int(n * 0.9))] * 100

    dd5 = min(0, min(ret5)) * 100

    m = {
        "label": label, "signal_count": n, "unique_stocks": unique_codes,
        "win_rate_5d": round(w5, 2), "win_rate_10d": round(w10, 2), "win_rate_20d": round(w20, 2),
        "avg_ret_5d": round(a5, 4), "avg_ret_10d": round(a10, 4), "avg_ret_20d": round(a20, 4),
        "sharpe_5d": round(sp5, 3),
        "p10_ret_5d": round(p10, 2), "p90_ret_5d": round(p90, 2), "max_dd_5d": round(dd5, 2)
    }

    for k, v in m.items():
        if k != "label":
            print(f"  {k}: {v}")
    return m


def get_all_trade_dates():
    q = f"""
    SELECT DISTINCT trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
    WHERE trade_date >= '{DT_START}' AND trade_date <= '{DT_END}'
    ORDER BY trade_date
    """
    return [r['trade_date'] for r in sql(q)]


def get_next_trade_dates(dates, all_dates_set):
    result = []
    for d in dates:
        dt = datetime.strptime(d[:10], '%Y-%m-%d')
        for offset in range(1, 8):
            nd = (dt + timedelta(days=offset)).strftime('%Y-%m-%d')
            if nd in all_dates_set:
                result.append(nd)
                break
    return sorted(set(result))


def run_backtest(label, trade_dates, stock_where, max_signals=10000):
    if not trade_dates:
        print(f"\n{'='*60}\n{label}\n{'='*60}\nNO TRADE DATES")
        return None

    all_signals = []
    batch_size = 100
    for i in range(0, len(trade_dates), batch_size):
        batch = trade_dates[i:i+batch_size]
        dq = ",".join(f"'{d}'" for d in batch)
        q = f"""
        SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
        JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
          ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
        WHERE sd.trade_date IN ({dq})
          AND {stock_where}
          AND sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%'
          AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'
        LIMIT 50000
        """
        r = sql(q)
        all_signals.extend(r)
        if len(all_signals) >= max_signals * 2:
            break

    if not all_signals:
        print(f"\n{'='*60}\n{label}\n{'='*60}\nNO SIGNALS")
        return None

    seen = set()
    unique = []
    for s in all_signals:
        k = (s['ts_code'], s['trade_date'])
        if k not in seen:
            seen.add(k)
            unique.append(s)
    if len(unique) > max_signals:
        unique = unique[:max_signals]

    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print(f"  Raw: {len(all_signals)}, Unique: {len(unique)}")

    codes = list(set(s['ts_code'] for s in unique))
    results = []
    for code_batch in [codes[i:i+200] for i in range(0, len(codes), 200)]:
        cq = ",".join(f"'{c}'" for c in code_batch)
        q_px = f"""
        SELECT ts_code, trade_date, close,
               leadInFrame(close, 5) OVER w AS c5,
               leadInFrame(close, 10) OVER w AS c10,
               leadInFrame(close, 20) OVER w AS c20
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
        WHERE ts_code IN ({cq})
          AND trade_date >= '{DT_START}' AND trade_date <= '2026-07-01'
        WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date
                     ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ORDER BY ts_code, trade_date
        """
        px_rows = sql(q_px)
        px_map = {}
        for r in px_rows:
            px_map[(r['ts_code'], r['trade_date'])] = r
        for s in unique:
            key = (s['ts_code'], s['trade_date'])
            if key in px_map:
                px = px_map[key]
                if px.get('close') and px['close'] > 0:
                    r5 = (px['c5'] / px['close'] - 1) if px.get('c5') else 0
                    r10 = (px['c10'] / px['close'] - 1) if px.get('c10') else 0
                    r20 = (px['c20'] / px['close'] - 1) if px.get('c20') else 0
                    results.append({'code': s['ts_code'], 'date': s['trade_date'],
                                    'r5': r5 or 0, 'r10': r10 or 0, 'r20': r20 or 0})
    return compute_metrics(results, label)


def run_bt_mf(label, trade_dates, stock_where, max_signals=10000):
    """With moneyflow join."""
    if not trade_dates:
        print(f"\n{'='*60}\n{label}\n{'='*60}\nNO TRADE DATES")
        return None
    all_signals = []
    batch_size = 100
    for i in range(0, len(trade_dates), batch_size):
        batch = trade_dates[i:i+batch_size]
        dq = ",".join(f"'{d}'" for d in batch)
        q = f"""
        SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
        JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
          ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
        JOIN (SELECT * FROM tushare.tushare_moneyflow FINAL) AS mf
          ON sd.ts_code = mf.ts_code AND sd.trade_date = mf.trade_date
        WHERE sd.trade_date IN ({dq})
          AND {stock_where}
          AND sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%'
          AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'
        LIMIT 50000
        """
        r = sql(q)
        all_signals.extend(r)
        if len(all_signals) >= max_signals * 2:
            break
    if not all_signals:
        print(f"\n{'='*60}\n{label}\n{'='*60}\nNO SIGNALS")
        return None
    seen = set()
    unique = []
    for s in all_signals:
        k = (s['ts_code'], s['trade_date'])
        if k not in seen:
            seen.add(k)
            unique.append(s)
    if len(unique) > max_signals:
        unique = unique[:max_signals]
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print(f"  Raw: {len(all_signals)}, Unique: {len(unique)}")
    codes = list(set(s['ts_code'] for s in unique))
    results = []
    for code_batch in [codes[i:i+200] for i in range(0, len(codes), 200)]:
        cq = ",".join(f"'{c}'" for c in code_batch)
        q_px = f"""
        SELECT ts_code, trade_date, close,
               leadInFrame(close, 5) OVER w AS c5,
               leadInFrame(close, 10) OVER w AS c10,
               leadInFrame(close, 20) OVER w AS c20
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
        WHERE ts_code IN ({cq})
          AND trade_date >= '{DT_START}' AND trade_date <= '2026-07-01'
        WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date
                     ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ORDER BY ts_code, trade_date
        """
        px_rows = sql(q_px)
        px_map = {}
        for r in px_rows:
            px_map[(r['ts_code'], r['trade_date'])] = r
        for s in unique:
            key = (s['ts_code'], s['trade_date'])
            if key in px_map:
                px = px_map[key]
                if px.get('close') and px['close'] > 0:
                    r5 = (px['c5'] / px['close'] - 1) if px.get('c5') else 0
                    r10 = (px['c10'] / px['close'] - 1) if px.get('c10') else 0
                    r20 = (px['c20'] / px['close'] - 1) if px.get('c20') else 0
                    results.append({'code': s['ts_code'], 'date': s['trade_date'],
                                    'r5': r5 or 0, 'r10': r10 or 0, 'r20': r20 or 0})
    return compute_metrics(results, label)


def main():
    print("=" * 60)
    print("Iter22 T7 — Bonus tests (C2 fix, C1b扩容, additional combos)")
    print(f"Date: {DT_START} ~ {DT_END}")
    print("=" * 60)

    all_dates = get_all_trade_dates()
    all_dates_set = set(all_dates)
    print(f"Total trading days: {len(all_dates)}")

    # C2: Shibor 1W 10-day declining (FIXED)
    print("\n>>> C2: Shibor 10-day declining...")
    shibor_down = [r['date'] for r in sql(f"""
        SELECT date FROM (
            SELECT date, 1w,
                   lagInFrame(1w, 10) OVER (ORDER BY date) AS old_1w
            FROM (SELECT * FROM tushare.tushare_shibor FINAL)
            WHERE date >= '{DT_START}'
        )
        WHERE old_1w IS NOT NULL AND 1w < old_1w
        ORDER BY date
    """)]
    c2_dates = get_next_trade_dates(shibor_down, all_dates_set)
    print(f"  Shibor declining: {len(shibor_down)}, Trade dates: {len(c2_dates)}")

    # C1b: SPX连2跌+恐慌深底+扩容CM≤50亿 (no PE/PB to increase N)
    print("\n>>> C1b: SPX连2跌 SPX dates...")
    spx_down2 = [r['trade_date'] for r in sql(f"""
        SELECT trade_date FROM (
            SELECT trade_date, pct_chg,
                   lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS pp1,
                   lagInFrame(pct_chg, 2) OVER (ORDER BY trade_date) AS pp2
            FROM (SELECT * FROM tushare.tushare_index_global FINAL)
            WHERE ts_code = 'SPX' AND trade_date >= '{DT_START}'
        )
        WHERE pp2 IS NOT NULL AND pp2 < 0 AND pp1 < 0
        ORDER BY trade_date
    """)]
    c1b_dates = get_next_trade_dates(spx_down2, all_dates_set)
    print(f"  SPX NEG: {len(spx_down2)}, Trade dates: {len(c1b_dates)}")

    # C5b: 沪深300连涨3日+恐慌深底微盘(扩容CM≤30亿 stronger)
    csi_up3 = [r['trade_date'] for r in sql(f"""
        SELECT trade_date FROM (
            SELECT trade_date, pct_chg,
                   lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS pp1,
                   lagInFrame(pct_chg, 2) OVER (ORDER BY trade_date) AS pp2
            FROM (SELECT * FROM tushare.tushare_index_daily FINAL)
            WHERE ts_code = '000300.SH' AND trade_date >= '{DT_START}'
        )
        WHERE pp2 IS NOT NULL AND pp2 > 0 AND pp1 > 0 AND pct_chg > 0
        ORDER BY trade_date
    """)]
    c5_dates = [d for d in csi_up3 if d in all_dates_set]
    print(f"  CSI300 up3: {len(csi_up3)}, Trade dates: {len(c5_dates)}")

    combo_results = {}

    # C1b: SPX连2跌 + 恐慌 + CM≤50亿 (no PE/PB, more signals)
    c1b_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -3
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 5000000000
    """
    combo_results['C1b'] = run_backtest(
        "C1b: SPX连2跌+恐慌≤-3%+振幅≥5%+VR≥1.0+CM≤50亿(扩容)",
        c1b_dates, c1b_where
    )

    # C2: Shibor下行 + 恐慌深底微盘
    c2_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 3000000000
    """
    combo_results['C2'] = run_backtest(
        "C2: Shibor下行+恐慌≤-5%+振幅≥5%+VR≥1.0+CM≤30亿",
        c2_dates, c2_where
    )

    # C2b: Shibor下行 + 恐慌深底 + 散户割肉主力承接微盘
    c2b_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 3000000000
        AND mf.sell_sm_amount > mf.buy_sm_amount
        AND mf.buy_elg_amount > mf.sell_elg_amount
    """
    combo_results['C2b'] = run_bt_mf(
        "C2b: Shibor+恐慌≤-5%+振幅≥5%+VR≥1.0+CM≤30亿+sell_sm>buy_sm+buy_elg>sell_elg",
        c2_dates, c2b_where
    )

    # C5b: 沪深300连涨3日+恐慌深底+微盘纯版(CM≤30亿)
    c5b_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 6
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 3000000000
    """
    combo_results['C5b'] = run_backtest(
        "C5b: 沪深300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.0+CM≤30亿(微盘纯版)",
        c5_dates, c5b_where
    )

    # C5c: 沪深300连涨3日+恐慌深底+深价值(PE≤15+PB≤2)+CM≤50亿
    c5c_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 6
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 5000000000
        AND db.pe IS NOT NULL AND db.pe <= 15 AND db.pe > 0
        AND db.pb IS NOT NULL AND db.pb <= 2 AND db.pb > 0
    """
    combo_results['C5c'] = run_backtest(
        "C5c: 沪深300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.0+CM≤50亿+PE≤15+PB≤2",
        c5_dates, c5c_where
    )

    # Print results
    print("\n\n" + "=" * 60)
    print("BONUS RESULTS")
    print("=" * 60)
    for name, res in combo_results.items():
        if res:
            print(f"\n--- {name} ---")
            if isinstance(res, dict):
                for k, v in res.items():
                    if k not in ('label',):
                        print(f"  {k}: {v}")
                    else:
                        print(f"  label: {v}")

    output = {
        "analyst": "T7-bonus",
        "iteration": 22,
        "date": "2026-05-13",
        "data_end_date": DT_END,
        "combos": [{"combo": k, "result": v} for k, v in combo_results.items() if v]
    }

    output_dir = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_22"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "t7_bonus_results.json")
    with open(output_path, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {output_path}")

if __name__ == "__main__":
    main()
