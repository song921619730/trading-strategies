#!/usr/bin/env python3
"""
Iter22 T7: 跨市场联动回测
5组参数组合 (C1-C5) — 聚焦未充分挖掘的跨市场维度
"""
import json
import subprocess
import math
import sys
import os
from collections import defaultdict
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

    # Win rates for 10D, 20D
    w10 = sum(1 for r in ret10 if r > 0) / n * 100 if n > 0 else 0
    w20 = sum(1 for r in ret20 if r > 0) / n * 100 if n > 0 else 0

    std5 = math.sqrt(sum((x - a5/100)**2 for x in ret5) / n) if n > 1 else 1
    sp5 = (a5 / 100) / std5 * math.sqrt(252 / 5) if std5 > 0 else 0

    # Percentiles
    sorted_ret5 = sorted(ret5)
    p10 = sorted_ret5[max(0, int(n * 0.1))] * 100
    p90 = sorted_ret5[min(n-1, int(n * 0.9))] * 100

    dd5 = min(0, min(ret5)) * 100

    m = {
        "label": label,
        "signal_count": n,
        "unique_stocks": unique_codes,
        "win_rate_5d": round(w5, 2),
        "win_rate_10d": round(w10, 2),
        "win_rate_20d": round(w20, 2),
        "avg_ret_5d": round(a5, 4),
        "avg_ret_10d": round(a10, 4),
        "avg_ret_20d": round(a20, 4),
        "sharpe_5d": round(sp5, 3),
        "p10_ret_5d": round(p10, 2),
        "p90_ret_5d": round(p90, 2),
        "max_dd_5d": round(dd5, 2)
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
    """Get the next trading day after each date."""
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
    """Run backtest on given trade dates with stock conditions."""
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

    # Deduplicate
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
    print(f"  Raw signals: {len(all_signals)}, Unique: {len(unique)}")

    # Compute forward returns
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
                    results.append({
                        'code': s['ts_code'],
                        'date': s['trade_date'],
                        'r5': r5 or 0,
                        'r10': r10 or 0,
                        'r20': r20 or 0
                    })

    return compute_metrics(results, label)


def run_backtest_with_moneyflow(label, trade_dates, stock_where, max_signals=10000):
    """Run backtest with moneyflow join (needed for sell_sm>buy_sm, buy_elg>sell_elg)."""
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
    print(f"  Raw signals: {len(all_signals)}, Unique: {len(unique)}")

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
                    results.append({
                        'code': s['ts_code'],
                        'date': s['trade_date'],
                        'r5': r5 or 0,
                        'r10': r10 or 0,
                        'r20': r20 or 0
                    })

    return compute_metrics(results, label)


def main():
    print("=" * 60)
    print("Iter22 T7 跨市场联动回测")
    print(f"时间范围: {DT_START} ~ {DT_END}")
    print(f"数据基准: {DT_END}")
    print("=" * 60)

    all_dates = get_all_trade_dates()
    all_dates_set = set(all_dates)
    print(f"Total trading days: {len(all_dates)}")

    # ===== Pre-compute macro dates =====

    # C1: SPX连续2日下跌 (SPX_NEG)
    print("\n>>> C1: SPX consecutive 2-day down dates...")
    spx_down2_raw = [r['trade_date'] for r in sql(f"""
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
    # SPX连续2日下跌后的下一个交易日交易
    spx_down2_trade_dates = get_next_trade_dates(spx_down2_raw, all_dates_set)
    print(f"  SPX consecutive 2-day down events: {len(spx_down2_raw)}, Trade dates: {len(spx_down2_trade_dates)}")

    # C2: Shibor 1W 10日下行
    print("\n>>> C2: Shibor 1W 10-day declining dates...")
    shibor_down_raw = [r['date'] for r in sql(f"""
        SELECT date, 1w, lagInFrame(1w, 10) OVER (ORDER BY date) AS old_1w
        FROM (SELECT * FROM tushare.tushare_shibor FINAL)
        WHERE date >= '{DT_START}'
        HAVING old_1w IS NOT NULL AND 1w < old_1w
        ORDER BY date
    """)]
    shibor_down_trade_dates = get_next_trade_dates(shibor_down_raw, all_dates_set)
    print(f"  Shibor declining events: {len(shibor_down_raw)}, Trade dates: {len(shibor_down_trade_dates)}")

    # C3: 北向资金净流入 + 沪深300当日跌≥1.5%
    print("\n>>> C3: 北向净流入+CSI300大跌 dates...")
    north_flow_dates = [r['trade_date'] for r in sql(f"""
        SELECT hsgt.trade_date
        FROM (
            SELECT trade_date, hgt, ggt_ss, ggt_sz,
                   (COALESCE(hgt,0) + COALESCE(ggt_ss,0) + COALESCE(ggt_sz,0)) AS north_total
            FROM (SELECT * FROM tushare.tushare_moneyflow_hsgt FINAL)
            WHERE trade_date >= '{DT_START}'
        ) AS hsgt
        JOIN (
            SELECT trade_date, pct_chg
            FROM (SELECT * FROM tushare.tushare_index_daily FINAL)
            WHERE ts_code = '000300.SH' AND trade_date >= '{DT_START}'
        ) AS csi
        ON hsgt.trade_date = csi.trade_date
        WHERE hsgt.north_total > 0 AND csi.pct_chg <= -1.5
        ORDER BY hsgt.trade_date
    """)]
    # 北向+沪深300数据日期与A股交易日期一致
    c3_trade_dates = [d for d in north_flow_dates if d in all_dates_set]
    print(f"  北向净流入+CSI300大跌 dates: {len(c3_trade_dates)}")

    # C4: HSI前日跌≥-2%
    print("\n>>> C4: HSI prev-day down ≥2% dates...")
    hsi_panic_raw = [r['trade_date'] for r in sql(f"""
        SELECT trade_date FROM (
            SELECT trade_date, pct_chg,
                   lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS pp1
            FROM (SELECT * FROM tushare.tushare_index_global FINAL)
            WHERE ts_code = 'HSI' AND trade_date >= '{DT_START}'
        )
        WHERE pp1 IS NOT NULL AND pp1 <= -2
        ORDER BY trade_date
    """)]
    # HSI前日跌≥-2%, 今日交易A股
    hsi_panic_trade_dates = get_next_trade_dates(hsi_panic_raw, all_dates_set)
    print(f"  HSI panic events: {len(hsi_panic_raw)}, Trade dates: {len(hsi_panic_trade_dates)}")

    # C5: 沪深300连续3日上涨
    print("\n>>> C5: CSI300 consecutive 3-day up dates...")
    csi_up3_raw = [r['trade_date'] for r in sql(f"""
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
    c5_trade_dates = [d for d in csi_up3_raw if d in all_dates_set]
    print(f"  CSI300 consecutive 3-up events: {len(csi_up3_raw)}, Trade dates: {len(c5_trade_dates)}")

    print("\n" + "=" * 60)
    print("MACRO DATA SUMMARY")
    print("=" * 60)
    for k, v in [
        ("C1: SPX连2跌", len(spx_down2_trade_dates)),
        ("C2: Shibor 1W 10日下行", len(shibor_down_trade_dates)),
        ("C3: 北向净流入+沪深300跌≥1.5%", len(c3_trade_dates)),
        ("C4: HSI前日跌≥2%", len(hsi_panic_trade_dates)),
        ("C5: 沪深300连涨3日", len(c5_trade_dates)),
    ]:
        print(f"  {k}: {v} trade dates")

    # ===== RUN BACKTESTS =====
    combo_results = {}

    # --- C1: SPX连2跌 + 恐慌深底深价值微盘 ---
    c1_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 6
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.2
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 3000000000
        AND db.pe IS NOT NULL AND db.pe <= 15
        AND db.pb IS NOT NULL AND db.pb <= 2
        AND db.pe > 0 AND db.pb > 0
    """
    res_c1 = run_backtest(
        "C1: SPX连2跌+恐慌≤-5%+振幅≥6%+VR≥1.2+CM≤30亿+PE≤15+PB≤2",
        spx_down2_trade_dates, c1_where
    )
    combo_results['C1'] = res_c1

    # --- C2: Shibor宽松 + 恐慌深底 + 散户割肉 + 主力承接 + 微盘 ---
    c2_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 3000000000
        AND mf.sell_sm_amount > mf.buy_sm_amount
        AND mf.buy_elg_amount > mf.sell_elg_amount
    """
    res_c2 = run_backtest_with_moneyflow(
        "C2: Shibor宽松+恐慌≤-5%+振幅≥5%+VR≥1.0+CM≤30亿+sell_sm>buy_sm+buy_elg>sell_elg",
        shibor_down_trade_dates, c2_where
    )
    combo_results['C2'] = res_c2

    # --- C3: 北向净流入+沪深300大跌+逆势抗跌放量微盘 ---
    c3_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg >= 0
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.2
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 5000000000
    """
    res_c3 = run_backtest(
        "C3: 北向净流入+CSI300大跌≥1.5%+逆势涨≥0%+振幅≥5%+VR≥1.2+CM≤50亿",
        c3_trade_dates, c3_where
    )
    combo_results['C3'] = res_c3

    # --- C4: HSI前日恐慌≥-2% + A股恐慌深底放量微盘 ---
    c4_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.3
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 3000000000
    """
    res_c4 = run_backtest(
        "C4: HSI前日跌≥2%+恐慌≤-5%+振幅≥5%+VR≥1.3+CM≤30亿",
        hsi_panic_trade_dates, c4_where
    )
    combo_results['C4'] = res_c4

    # --- C5: 沪深300连涨3日 + 个股恐慌深底放量 ---
    c5_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 6
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 5000000000
    """
    res_c5 = run_backtest(
        "C5: 沪深300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.0+CM≤50亿",
        c5_trade_dates, c5_where
    )
    combo_results['C5'] = res_c5

    # ===== OUTPUT =====
    print("\n\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    output = {
        "analyst": "T7",
        "iteration": 22,
        "date": "2026-05-13",
        "period": f"{DT_START}~{DT_END}",
        "data_end_date": DT_END,
        "combos": []
    }

    for combo_name in ['C1', 'C2', 'C3', 'C4', 'C5']:
        result = combo_results.get(combo_name)
        if result:
            entry = {"combo": combo_name, "result": result}
            output["combos"].append(entry)
            print(f"\n--- {combo_name} ---")
            if isinstance(result, dict):
                for k, v in result.items():
                    if k != 'label':
                        print(f"  {k}: {v}")
                    else:
                        print(f"  label: {v}")

    # Save
    output_dir = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_22"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "t7_results.json")
    with open(output_path, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}")

    print("\n\nJSON OUTPUT:")
    print(json.dumps(output, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
