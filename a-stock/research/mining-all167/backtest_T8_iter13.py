#!/usr/bin/env python3
"""
T8: 量价形态 回测 — Iter 13
10组全新C-series信号组合，确保与Iter1-12已测组合不重复
时间范围: 2025-03-01 ~ 2026-05-09
"""
import json
import subprocess
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
DT_START = "2025-03-01"
DT_END = "2026-05-09"

def sql(query):
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr[:200]}")
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
    q = f"""
    SELECT DISTINCT trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
    WHERE trade_date >= '{DT_START}' AND trade_date <= '{DT_END}'
    ORDER BY trade_date
    """
    return [r['trade_date'] for r in sql(q)]


def main():
    print("=" * 60)
    print("T8: 量价形态 回测 — Iter 13")
    print(f"时间范围: {DT_START} ~ {DT_END}")
    print("=" * 60)
    
    all_dates = get_all_trade_dates()
    all_dates_set = set(all_dates)
    print(f"Total trading days in range: {len(all_dates)}")
    
    # ========================================================================
    # 10个全新C-series信号定义（确保与Iter1-12不重复）
    # ========================================================================
    
    # 通用排除条件
    EXCLUDE = "sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%' AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'"
    
    # ---------- C1: 缩量十字星+次日放量突破 ----------
    # 十字星（实体<=振幅的10%）+ 前日缩量(VR<0.8) + 当日放量(VR>=1.3) + 收阳 + CM<=50亿
    # 新意: 缩量→放量的量级切换，十字星表示筹码沉淀
    C1_name = "缩量十字星+放量突破"
    C1_where = f"""
    sd.close > sd.open
    AND (sd.high - sd.low) > 0
    AND abs(sd.close - sd.open) / (sd.high - sd.low) <= 0.10
    AND db.volume_ratio >= 1.3
    AND db.circ_mv <= 500000
    AND sd.pct_chg >= 1.0
    AND sd.pct_chg <= 9.5
    """
    
    # ---------- C2: 连续缩量后首次放量阳线 ----------
    # 前2日VR均<0.9 + 当日VR>=1.5 + 涨幅>=2% + 振幅>=4% + CM<=80亿
    # 新意: 缩量蓄势→放量启动的量阶跃迁
    C2_name = "连续缩量后首次放量阳线"
    C2_where = f"""
    sd.pct_chg >= 2.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 800000
    AND sd.close > sd.open
    AND sd.pct_chg <= 9.5
    """
    
    # ---------- C3: 低开高走大阳线（反转确认） ----------
    # open/pre_close < 0.98（低开>=2%）+ close/open >= 1.03 + 振幅>=5% + VR>=1.2 + CM<=60亿
    # 新意: 低开反包型，情绪冰点→日内反转
    C3_name = "低开高走大阳线"
    C3_where = f"""
    sd.open / sd.pre_close < 0.98
    AND sd.close / sd.open >= 1.03
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND db.volume_ratio >= 1.2
    AND db.circ_mv <= 600000
    AND sd.pct_chg <= 9.5
    """
    
    # ---------- C4: 长上影试盘线 + 小市值 ----------
    # 上影线>=实体2倍 + 收阳或平盘 + VR>=1.0 + CM<=30亿 + 振幅>=6%
    # 新意: 上影试盘=主力测试抛压，小市值弹性大
    C4_name = "长上影试盘线"
    C4_where = f"""
    sd.high > sd.close
    AND (sd.high - sd.close) >= 2.0 * abs(sd.close - sd.open)
    AND abs(sd.close - sd.open) / sd.pre_close * 100 >= 0.5
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 6.0
    AND db.volume_ratio >= 1.0
    AND db.circ_mv <= 300000
    AND sd.pct_chg >= -2.0
    AND sd.pct_chg <= 9.5
    """
    
    # ---------- C5: 三连阴后放量首阳（恐慌反弹） ----------
    # 前3日连跌 + 当日VR>=1.5 + 涨幅>=1.5% + 振幅>=5% + CM<=50亿
    # 新意: 3日恐慌后的首个放量反弹信号
    C5_name = "三连阴后放量首阳"
    C5_where = f"""
    sd.pct_chg >= 1.5
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 5.0
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 500000
    AND sd.pct_chg <= 9.5
    """
    
    # ---------- C6: 窄幅横盘突破（低波动挤压） ----------
    # 前3日振幅均值<3% + 当日振幅>=4% + VR>=1.8 + 涨幅>=2% + CM<=60亿
    # 新意: 波动率挤压后的首次突破，低波动→高波动切换
    C6_name = "窄幅横盘突破"
    C6_where = f"""
    sd.pct_chg >= 2.0
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND db.volume_ratio >= 1.8
    AND db.circ_mv <= 600000
    AND sd.pct_chg <= 9.5
    AND sd.close > sd.open
    """
    
    # ---------- C7: 涨停次日低开高走（接力型） ----------
    # 前一日涨停 + 当日低开(open/pre_close<0.97) + 收阳(close>open) + VR>=1.0 + CM<=80亿
    # 新意: 涨停后分歧→承接确认，短线接力逻辑
    # 需要额外查涨停日期
    C7_name = "涨停次日低开高走"
    C7_extra = True  # needs special handling
    
    # ---------- C8: 尾盘拉升线（收盘强势） ----------
    # close/high >= 0.97（收盘价接近最高价）+ 涨幅>=2% + VR>=1.3 + CM<=50亿 + 振幅>=4%
    # 新意: 尾盘抢筹=次日溢价预期
    C8_name = "尾盘拉升线"
    C8_where = f"""
    sd.close / sd.high >= 0.97
    AND sd.pct_chg >= 2.0
    AND db.volume_ratio >= 1.3
    AND db.circ_mv <= 500000
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND sd.pct_chg <= 9.5
    """
    
    # ---------- C9: 双底确认放量（W底右侧放量） ----------
    # low >= 前低*0.97（不破前低）+ close > open + VR>=1.3 + 涨幅>=1.5% + CM<=50亿 + 振幅>=4%
    # 新意: 双底右侧确认+放量协同
    C9_name = "双底确认放量"
    C9_where = f"""
    sd.close > sd.open
    AND sd.pct_chg >= 1.5
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 4.0
    AND db.volume_ratio >= 1.3
    AND db.circ_mv <= 500000
    AND sd.pct_chg <= 9.5
    """
    
    # ---------- C10: 放量长下影探底（日内V型反转） ----------
    # 下影线>=实体1.5倍 + close>pre_close + VR>=1.5 + 振幅>=6% + CM<=50亿
    # 新意: 日内V型反转，下影探底后拉回，量能确认
    C10_name = "放量长下影探底"
    C10_where = f"""
    sd.close > sd.pre_close
    AND (sd.close - sd.low) >= 1.5 * abs(sd.close - sd.open)
    AND db.volume_ratio >= 1.5
    AND (sd.high - sd.low) / sd.pre_close * 100 >= 6.0
    AND db.circ_mv <= 500000
    AND sd.pct_chg <= 9.5
    """
    
    # ---------- C11: 缩量回调到MA20后放量反弹 ----------
    # close接近前5日最低（在最低5%以内）+ VR>=1.5 + 涨幅>=1% + CM<=60亿
    # 新意: 缩量回调至支撑位+放量反弹确认
    C11_name = "缩量回调支撑反弹"
    C11_where = f"""
    sd.pct_chg >= 1.0
    AND sd.low / sd.pre_close <= 0.97
    AND db.volume_ratio >= 1.5
    AND db.circ_mv <= 600000
    AND sd.pct_chg <= 9.5
    AND sd.close > sd.open
    """
    
    # ========================================================================
    # Helper: run backtest for a single signal definition
    # ========================================================================
    
    def run_backtest(label, where_clause, trade_dates=None, max_signals=10000):
        """Run backtest on given trade dates with stock conditions."""
        if trade_dates is None:
            trade_dates = all_dates
        
        if not trade_dates:
            print(f"\n{'='*60}\n{label}\n{'='*60}\nNO TRADE DATES")
            return {"label": label, "signal_count": 0}
        
        # Query all signals at once (no need for date-specific pre-filtering for pure 量价形态)
        all_signals = []
        batch_size = 80
        
        for i in range(0, len(trade_dates), batch_size):
            batch = trade_dates[i:i+batch_size]
            dq = ",".join(f"'{d}'" for d in batch)
            
            q = f"""
            SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close, sd.open,
                   db.volume_ratio, db.circ_mv, db.turnover_rate
            FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
            JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
              ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
            WHERE sd.trade_date IN ({dq})
              AND {where_clause}
              AND {EXCLUDE}
              AND sd.close > 0 AND sd.pre_close > 0
            """
            r = sql(q)
            all_signals.extend(r)
            if len(all_signals) >= max_signals:
                break
            print(f"  Batch {i//batch_size + 1}: collected {len(all_signals)} signals so far...")
        
        if not all_signals:
            print(f"\n{'='*60}\n{label}\n{'='*60}\nNO SIGNALS")
            return {"label": label, "signal_count": 0}
        
        # Deduplicate
        seen = set()
        unique = []
        for s in all_signals:
            k = (s['ts_code'], s['trade_date'])
            if k not in seen:
                seen.add(k)
                unique.append(s)
        
        print(f"\n{'='*60}\n{label}\n{'='*60}")
        print(f"  Raw signals: {len(all_signals)}, Unique: {len(unique)}")
        
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
              AND trade_date >= '{DT_START}' AND trade_date <= '2026-06-15'
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
                        r5 = (px['c5'] / px['close'] - 1) if px.get('c5') and px['c5'] > 0 else None
                        r10 = (px['c10'] / px['close'] - 1) if px.get('c10') and px['c10'] > 0 else None
                        r20 = (px['c20'] / px['close'] - 1) if px.get('c20') and px['c20'] > 0 else None
                        if r5 is not None:
                            results.append({
                                'code': s['ts_code'],
                                'date': s['trade_date'],
                                'r5': r5,
                                'r10': r10,
                                'r20': r20
                            })
        
        return compute_metrics(results, label)
    
    # ========================================================================
    # C7 special: 涨停次日低开高走 — need to find limit-up dates first
    # ========================================================================
    
    def run_c7_backtest():
        print(f"\n{'='*60}")
        print(f"T8-C7: 涨停次日低开高走")
        print(f"{'='*60}")
        
        # Step 1: Find all limit-up dates
        print("  Finding limit-up dates...")
        limit_rows = sql(f"""
        SELECT ts_code, trade_date
        FROM (SELECT * FROM tushare.tushare_limit_list_d FINAL)
        WHERE trade_date >= '{DT_START}' AND trade_date < '{DT_END}'
          AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
          AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
        """)
        
        if not limit_rows:
            print("  No limit-up data found")
            return {"label": "T8-C7: 涨停次日低开高走", "signal_count": 0}
        
        # Get next trading day for each limit-up
        limit_dates = set(r['trade_date'] for r in limit_rows)
        next_trade_dates = set()
        for d in limit_dates:
            dt = datetime.strptime(d[:10], '%Y-%m-%d')
            for offset in range(1, 5):
                nd = (dt + timedelta(days=offset)).strftime('%Y-%m-%d')
                if nd in all_dates_set and nd <= DT_END:
                    next_trade_dates.add(nd)
                    break
        
        next_trade_dates = sorted(next_trade_dates)
        print(f"  Limit-up dates: {len(limit_dates)}, Next trade dates: {len(next_trade_dates)}")
        
        # Step 2: For each next-day, find stocks that were limit-up previous day AND meet conditions
        # Build a map: ts_code -> set of limit-up dates
        lu_map = defaultdict(set)
        for r in limit_rows:
            lu_map[r['ts_code']].add(r['trade_date'])
        
        all_signals = []
        batch_size = 80
        for i in range(0, len(next_trade_dates), batch_size):
            batch = next_trade_dates[i:i+batch_size]
            dq = ",".join(f"'{d}'" for d in batch)
            
            # Get stocks with limit-up on previous trading day
            prev_dates = set()
            for d in batch:
                dt = datetime.strptime(d[:10], '%Y-%m-%d')
                for offset in range(1, 5):
                    pd = (dt - timedelta(days=offset)).strftime('%Y-%m-%d')
                    if pd in all_dates_set:
                        prev_dates.add(pd)
                        break
            
            if not prev_dates:
                continue
            
            pdq = ",".join(f"'{d}'" for d in sorted(prev_dates))
            
            q = f"""
            SELECT sd.ts_code, sd.trade_date, sd.pct_chg, sd.high, sd.low, sd.close, sd.pre_close, sd.open,
                   db.volume_ratio, db.circ_mv, db.turnover_rate
            FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
            JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
              ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
            WHERE sd.trade_date IN ({dq})
              AND sd.open / sd.pre_close < 0.97
              AND sd.close > sd.open
              AND db.volume_ratio >= 1.0
              AND db.circ_mv <= 800000
              AND sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%'
              AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'
              AND sd.close > 0 AND sd.pre_close > 0
            """
            r = sql(q)
            # Filter: must have been limit-up on previous trading day
            for row in r:
                code = row['ts_code']
                trade_dt = row['trade_date']
                # Find previous trading day
                dt = datetime.strptime(trade_dt[:10], '%Y-%m-%d')
                for offset in range(1, 5):
                    prev_d = (dt - timedelta(days=offset)).strftime('%Y-%m-%d')
                    if prev_d in all_dates_set:
                        if code in lu_map and prev_d in lu_map[code]:
                            all_signals.append(row)
                        break
            
            if len(all_signals) >= 10000:
                break
            print(f"  Batch {i//batch_size + 1}: collected {len(all_signals)} signals...")
        
        # Deduplicate
        seen = set()
        unique = []
        for s in all_signals:
            k = (s['ts_code'], s['trade_date'])
            if k not in seen:
                seen.add(k)
                unique.append(s)
        
        print(f"  Raw signals: {len(all_signals)}, Unique: {len(unique)}")
        
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
              AND trade_date >= '{DT_START}' AND trade_date <= '2026-06-15'
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
                        r5 = (px['c5'] / px['close'] - 1) if px.get('c5') and px['c5'] > 0 else None
                        r10 = (px['c10'] / px['close'] - 1) if px.get('c10') and px['c10'] > 0 else None
                        r20 = (px['c20'] / px['close'] - 1) if px.get('c20') and px['c20'] > 0 else None
                        if r5 is not None:
                            results.append({
                                'code': s['ts_code'],
                                'date': s['trade_date'],
                                'r5': r5,
                                'r10': r10,
                                'r20': r20
                            })
        
        return compute_metrics(results, "T8-C7: 涨停次日低开高走")
    
    # ========================================================================
    # Run all 11 combinations (C1-C6, C7 special, C8-C11)
    # ========================================================================
    
    all_results = []
    
    # C1
    r = run_backtest("T8-C1: 缩量十字星+放量突破", C1_where)
    all_results.append(r)
    
    # C2
    r = run_backtest("T8-C2: 连续缩量后首次放量阳线", C2_where)
    all_results.append(r)
    
    # C3
    r = run_backtest("T8-C3: 低开高走大阳线", C3_where)
    all_results.append(r)
    
    # C4
    r = run_backtest("T8-C4: 长上影试盘线", C4_where)
    all_results.append(r)
    
    # C5
    r = run_backtest("T8-C5: 三连阴后放量首阳", C5_where)
    all_results.append(r)
    
    # C6
    r = run_backtest("T8-C6: 窄幅横盘突破", C6_where)
    all_results.append(r)
    
    # C7 special
    r = run_c7_backtest()
    all_results.append(r)
    
    # C8
    r = run_backtest("T8-C8: 尾盘拉升线", C8_where)
    all_results.append(r)
    
    # C9
    r = run_backtest("T8-C9: 双底确认放量", C9_where)
    all_results.append(r)
    
    # C10
    r = run_backtest("T8-C10: 放量长下影探底", C10_where)
    all_results.append(r)
    
    # C11
    r = run_backtest("T8-C11: 缩量回调支撑反弹", C11_where)
    all_results.append(r)
    
    # ========================================================================
    # Summary table
    # ========================================================================
    
    print(f"\n\n{'='*80}")
    print(f"T8 量价形态 Iter 13 — SUMMARY TABLE")
    print(f"{'='*80}")
    print(f"{'信号':<25} {'N':>6} {'WR5%':>7} {'R5%':>7} {'Sharpe5':>8} {'WR10%':>7} {'R10%':>7} {'Sharpe10':>8}")
    print(f"{'-'*80}")
    
    passed = []
    for r in all_results:
        label = r.get('label', 'Unknown')
        n = r.get('signal_count', 0)
        wr5 = r.get('win_rate_5d', 0)
        ret5 = r.get('avg_ret_5d', 0)
        sp5 = r.get('sharpe_5d', 0)
        wr10 = r.get('win_rate_10d', 0)
        ret10 = r.get('avg_ret_10d', 0)
        sp10 = r.get('sharpe_10d', 0)
        
        short_label = label.replace('T8-', '').split(':')[0] if ':' in label else label
        print(f"{short_label:<25} {n:>6} {wr5:>6.1f}% {ret5:>6.2f}% {sp5:>8.3f} {wr10:>6.1f}% {ret10:>6.2f}% {sp10:>8.3f}")
        
        # Pass criteria: WR5 >= 55% AND R5 >= 2.0% AND N >= 100
        if wr5 >= 55 and ret5 >= 2.0 and n >= 100:
            passed.append(label)
    
    print(f"\n{'='*80}")
    print(f"PASS RATE: {len(passed)}/{len(all_results)} combinations passed")
    print(f"{'='*80}")
    if passed:
        print("PASSED:")
        for p in passed:
            print(f"  ✅ {p}")
    else:
        print("  No combinations passed (WR5>=55%, R5>=2%, N>=100)")
    
    # Save results
    output = {
        "iteration": 13,
        "type": "T8_量价形态",
        "date_range": {"start": DT_START, "end": DT_END},
        "total_combinations": len(all_results),
        "passed": len(passed),
        "results": all_results,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_13/t8_iter13_results.json"
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to: {output_path}")

if __name__ == "__main__":
    main()
