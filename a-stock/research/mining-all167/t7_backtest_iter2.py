#!/usr/bin/env python3
"""
T7: 跨市场联动回测 — Iter 2 (Fixed SQL)
5组参数组合 (C1-C5)
"""
import json
import subprocess
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
DT_START = "2020-01-01"
DT_END = "2026-05-11"

def sql(query):
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return []
    if not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout)
    except:
        return []

def compute_metrics(results, label):
    n = len(results)
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"  SIGNALS: {n}")
    
    if n < 10:
        print(f"  Too few signals (< 10)")
        return {
            "label": label, "signal_count": n,
            "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0,
            "avg_ret_5d": 0, "avg_ret_10d": 0, "avg_ret_20d": 0,
            "sharpe_5d": 0, "sharpe_10d": 0, "max_drawdown_5d": 0,
            "total_return_5d": 0
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
    
    std10 = math.sqrt(sum((x - a10/100)**2 for x in ret10) / n) if n > 1 else 1
    sp10 = (a10 / 100) / std10 * math.sqrt(252 / 10) if std10 > 0 else 0
    
    dd5 = min(0, min(ret5)) * 100
    
    m = {
        "label": label,
        "signal_count": n,
        "win_rate_5d": round(w5, 2),
        "win_rate_10d": round(w10, 2),
        "win_rate_20d": round(w20, 2),
        "avg_ret_5d": round(a5, 4),
        "avg_ret_10d": round(a10, 4),
        "avg_ret_20d": round(a20, 4),
        "sharpe_5d": round(sp5, 3),
        "sharpe_10d": round(sp10, 3),
        "max_drawdown_5d": round(dd5, 2),
        "total_return_5d": round(sum(ret5) * 100, 2)
    }
    
    for k, v in m.items():
        if k != "label":
            print(f"  {k}: {v}")
    
    return m


def get_all_trade_dates():
    """Get all trading dates sorted."""
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
        for offset in range(1, 5):
            nd = (dt + timedelta(days=offset)).strftime('%Y-%m-%d')
            if nd in all_dates_set:
                result.append(nd)
                break
    return sorted(set(result))


def main():
    print("=" * 60)
    print("T7 跨市场联动回测 — Iter 2")
    print(f"时间范围: {DT_START} ~ {DT_END}")
    print("=" * 60)
    
    all_dates = get_all_trade_dates()
    all_dates_set = set(all_dates)
    print(f"Total trading days: {len(all_dates)}")
    
    # ===== Pre-compute macro dates =====
    
    # C1: SPX consecutive 2-day down (前2日)
    print("\n>>> C1: SPX consecutive 2-day down dates...")
    spx_down2_raw = [r['trade_date'] for r in sql(f"""
        SELECT trade_date FROM (
            SELECT trade_date, pct_chg,
                   lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS pp1
            FROM (SELECT * FROM tushare.tushare_index_global FINAL)
            WHERE ts_code = 'SPX' AND trade_date >= '{DT_START}'
        )
        WHERE pp1 < 0 AND pct_chg < 0
        ORDER BY trade_date
    """)]
    print(f"  SPX 2-consecutive-down dates: {len(spx_down2_raw)}")
    
    # "前2日" = SPX dropped on previous 2 days, so we trade on NEXT day
    spx_down2_trade_dates = get_next_trade_dates(spx_down2_raw, all_dates_set)
    print(f"  Trade dates (next day): {len(spx_down2_trade_dates)}")
    
    # C3: SPX前日涨 (SPX up previous day)
    print("\n>>> C3: SPX previous-day-up dates...")
    spx_up_prev_raw = [r['trade_date'] for r in sql(f"""
        SELECT trade_date FROM (
            SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS pp1
            FROM (SELECT * FROM tushare.tushare_index_global FINAL)
            WHERE ts_code = 'SPX' AND trade_date >= '{DT_START}'
        )
        WHERE pp1 > 0
        ORDER BY trade_date
    """)]
    # Trade on the same date (SPX was up on previous day, we trade today)
    # Actually "SPX前日涨" means SPX was up the previous day, and we trade today
    spx_up_prev_trade_dates = sorted(set(spx_up_prev_raw))
    print(f"  SPX prev-up dates (trade same day): {len(spx_up_prev_trade_dates)}")
    
    # C4: Shibor<1.5%
    print("\n>>> C4: Shibor<1.5% dates...")
    shibor_low_raw = [r['date'] for r in sql(f"""
        SELECT date FROM tushare.tushare_shibor FINAL
        WHERE 1w < 1.5 AND date >= '{DT_START}'
        ORDER BY date
    """)]
    # Shibor data is available daily, map to next trading day
    shibor_trade_dates = get_next_trade_dates(shibor_low_raw, all_dates_set)
    print(f"  Shibor<1.5% raw dates: {len(shibor_low_raw)}, trade dates: {len(shibor_trade_dates)}")
    
    # C5: M2_yoy>=8.5%
    print("\n>>> C5: M2_yoy>=8.5% months...")
    m2_high_months = [r['month'] for r in sql(f"""
        SELECT month FROM tushare.tushare_cn_m FINAL
        WHERE m2_yoy IS NOT NULL AND m2_yoy >= 8.5
        ORDER BY month
    """)]
    m2_month_set = set(m2_high_months)
    
    m2_trade_dates = [d for d in all_dates if d[:4] + d[5:7] in m2_month_set]
    print(f"  M2_yoy>=8.5% months: {len(m2_high_months)}, trade dates: {len(m2_trade_dates)}")
    
    print("\n" + "=" * 60)
    print("MACRO DATA SUMMARY")
    print("=" * 60)
    for k, v in [
        ("SPX consecutive down (trade dates)", len(spx_down2_trade_dates)),
        ("SPX prev-up (trade dates)", len(spx_up_prev_trade_dates)),
        ("Shibor<1.5% (trade dates)", len(shibor_trade_dates)),
        ("M2_yoy>=8.5% (trade dates)", len(m2_trade_dates)),
    ]:
        print(f"  {k}: {v}")
    
    # ===== Helper: batch query with forward returns =====
    
    def run_backtest(label, trade_dates, stock_where, max_signals=5000):
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
            SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close,
                   db.volume_ratio, db.circ_mv
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
        print(f"  Signals: {len(unique)}")
        
        # Compute forward returns
        codes = list(set(s['ts_code'] for s in unique))
        results = []
        
        for code_batch in [codes[i:i+100] for i in range(0, len(codes), 100)]:
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
    
    # ===== RUN BACKTESTS =====
    
    combo_results = {}
    
    # --- C1: SPX连2跌 + 恐慌≤-5% + 振幅≥7% + VR≥1.3 + CM≤100亿 ---
    # 恐慌 = pct_chg ≤ -5%
    # 振幅 = (high - low) / pre_close * 100 ≥ 7%
    # VR = volume_ratio ≥ 1.3
    # CM = circ_mv ≤ 100亿 = 10,000,000,000
    c1_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 7
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.3
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 10000000000
    """
    res_c1 = run_backtest("C1: SPX连2跌+恐慌≤-5%+振幅≥7%+VR≥1.3+CM≤100亿",
                          spx_down2_trade_dates, c1_where)
    combo_results['C1'] = res_c1
    
    # --- C2: VOLX>25(跳过) + 恐慌≤-5% + 振幅≥5% + VR≥1.3 + CM≤50亿 ---
    # No VIX data available, run without macro filter
    c2_where = """
        sd.pct_chg IS NOT NULL AND sd.pct_chg <= -5
        AND ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.3
        AND db.circ_mv IS NOT NULL AND db.circ_mv <= 5000000000
    """
    # For C2, since no VOLX, run on ALL dates
    res_c2 = run_backtest("C2: 恐慌≤-5%+振幅≥5%+VR≥1.3+CM≤50亿(无VOLX宏观过滤)",
                          all_dates, c2_where)
    combo_results['C2'] = res_c2
    
    # --- C3: SPX前日涨 + 前日跌 + 今日涨≥2% + 振幅≥5% + VR≥1.3 + CM≤30亿 ---
    # Step 1: Find stocks meeting today's conditions on SPX-prev-up dates
    # Step 2: Filter for "前日跌" (prev day pct_chg < 0)
    
    if spx_up_prev_trade_dates:
        print(f"\n{'='*60}")
        print("C3: SPX前日涨+前日跌+今日涨≥2%+振幅≥5%+VR≥1.3+CM≤30亿")
        print(f"{'='*60}")
        
        # Step 1: Get today's signals
        c3_signals_today = []
        for i in range(0, len(spx_up_prev_trade_dates), 100):
            batch = spx_up_prev_trade_dates[i:i+100]
            dq = ",".join(f"'{d}'" for d in batch)
            
            q = f"""
            SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close,
                   db.volume_ratio, db.circ_mv
            FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
            JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
              ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
            WHERE sd.trade_date IN ({dq})
              AND sd.pct_chg IS NOT NULL AND sd.pct_chg >= 2
              AND ((sd.high - sd.low) / sd.pre_close * 100) >= 5
              AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.3
              AND db.circ_mv IS NOT NULL AND db.circ_mv <= 3000000000
              AND sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%'
              AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'
            LIMIT 50000
            """
            r = sql(q)
            c3_signals_today.extend(r)
            if len(c3_signals_today) >= 10000:
                break
        
        print(f"  Today signals (up≥2%): {len(c3_signals_today)}")
        
        # Step 2: Filter for 前日跌 (previous day down)
        if c3_signals_today:
            signal_codes = list(set(s['ts_code'] for s in c3_signals_today))
            
            filtered_signals = []
            for code_batch in [signal_codes[i:i+100] for i in range(0, len(signal_codes), 100)]:
                cq = ",".join(f"'{c}'" for c in code_batch)
                
                q_prev = f"""
                SELECT ts_code, trade_date, pct_chg,
                       lagInFrame(pct_chg, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS prev_pct_chg
                FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
                WHERE ts_code IN ({cq})
                  AND trade_date >= '{DT_START}' AND trade_date <= '{DT_END}'
                ORDER BY ts_code, trade_date
                """
                prev_rows = sql(q_prev)
                prev_map = {}
                for r in prev_rows:
                    prev_map[(r['ts_code'], r['trade_date'])] = r.get('prev_pct_chg')
                
                for s in c3_signals_today:
                    key = (s['ts_code'], s['trade_date'])
                    if key in prev_map:
                        prev_pct = prev_map[key]
                        if prev_pct is not None and prev_pct < 0:
                            filtered_signals.append(s)
            
            print(f"  After prev-day-down filter: {len(filtered_signals)}")
            
            if filtered_signals:
                unique = []
                seen = set()
                for s in filtered_signals:
                    k = (s['ts_code'], s['trade_date'])
                    if k not in seen:
                        seen.add(k)
                        unique.append(s)
                
                if len(unique) > 5000:
                    unique = unique[:5000]
                
                codes = list(set(s['ts_code'] for s in unique))
                results = []
                
                for code_batch in [codes[i:i+100] for i in range(0, len(codes), 100)]:
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
                
                res_c3 = compute_metrics(results, "C3: SPX前日涨+前日跌+今日涨≥2%+振幅≥5%+VR≥1.3+CM≤30亿")
            else:
                res_c3 = {"label": "C3", "signal_count": 0, "note": "no signals after prev-day-down filter"}
                print("  No C3 signals after prev-day-down filter")
        else:
            res_c3 = {"label": "C3", "signal_count": 0, "note": "no today signals"}
            print("  No C3 today signals")
    else:
        res_c3 = {"label": "C3", "signal_count": 0, "note": "no SPX prev-up dates"}
        print("  No SPX prev-up dates")
    
    combo_results['C3'] = res_c3
    
    # --- C4: Shibor<1.5% + 振幅≥5% + VR≥1.0 + CM 30-100亿 ---
    c4_where = """
        ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv >= 3000000000 AND db.circ_mv <= 10000000000
    """
    res_c4 = run_backtest("C4: Shibor<1.5%+振幅≥5%+VR≥1.0+CM 30-100亿",
                          shibor_trade_dates, c4_where)
    combo_results['C4'] = res_c4
    
    # --- C5: M2_yoy≥8.5% + 振幅≥5% + VR≥1.0 + CM 30-100亿 ---
    c5_where = """
        ((sd.high - sd.low) / sd.pre_close * 100) >= 5
        AND db.volume_ratio IS NOT NULL AND db.volume_ratio >= 1.0
        AND db.circ_mv IS NOT NULL AND db.circ_mv >= 3000000000 AND db.circ_mv <= 10000000000
    """
    res_c5 = run_backtest("C5: M2_yoy≥8.5%+振幅≥5%+VR≥1.0+CM 30-100亿",
                          m2_trade_dates, c5_where)
    combo_results['C5'] = res_c5
    
    # ===== OUTPUT =====
    print("\n\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    
    output = {
        "analyst": "T7",
        "date": "2026-05-12",
        "period": f"{DT_START}~{DT_END}",
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
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/t7_results_iter2.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}")
    
    print("\n\nJSON OUTPUT:")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    
    print("\n" + "=" * 60)
    print("T7 跨市场联动回测 — ALL DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
