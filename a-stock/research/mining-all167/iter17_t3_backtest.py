#!/usr/bin/env python3
"""
Iter17 T3 Reversal Low-Absorption Backtest
Tests 5 parameter combos against full historical data.
"""
import json, sys, hashlib, math, os
from datetime import datetime
sys.path.insert(0, '/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts')
from ch_query import _ch_query as ch_query

BASE_DATE = 20260512  # max trade_date
HISTORICAL_START = 20200101  # 5+ years of data

def board_filter():
    """Main board filter excluding STAR, ChiNext, BSE, ST"""
    return "AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'"

def run_backtest(combo_name, params):
    """Run full historical backtest for a given parameter combo"""
    
    conditions = []
    
    # ===== MAP PARAMS TO SQL CONDITIONS =====
    
    # pct_chg_min (跌幅/涨幅下限)
    if 'pct_chg_min' in params:
        v = params['pct_chg_min']
        conditions.append(f"s.pct_chg <= {v}")
    
    # pct_chg_max (涨幅上限)
    if 'pct_chg_max' in params:
        v = params['pct_chg_max']
        conditions.append(f"s.pct_chg <= {v}")
    
    # amplitude_min
    if 'amplitude_min' in params:
        v = params['amplitude_min']
        conditions.append(f"s.amplitude >= {v}")
    
    # volume_ratio_min (from daily_basic)
    if 'volume_ratio_min' in params:
        v = params['volume_ratio_min']
        conditions.append(f"b.volume_ratio >= {v}")
    
    # turnover_rate constraints (from daily_basic)
    if 'turnover_min' in params:
        v = params['turnover_min']
        conditions.append(f"b.turnover_rate >= {v}")
    if 'turnover_max' in params:
        v = params['turnover_max']
        conditions.append(f"b.turnover_rate <= {v}")
    
    # circ_mv constraints (from daily_basic, unit: 万元)
    if 'circ_mv_max' in params:
        v = params['circ_mv_max'] / 10000  # convert yuan to 万元
        conditions.append(f"b.circ_mv <= {v}")
    
    # PE / PB (from daily_basic)
    if 'pe_max' in params and params['pe_max'] is not None:
        conditions.append(f"b.pe <= {params['pe_max']}")
    if 'pb_max' in params and params['pb_max'] is not None:
        conditions.append(f"b.pb <= {params['pb_max']}")
    
    # close_position (底20%, 底40% etc.) - computed in the window CTE
    pos_condition = None
    if 'close_position' in params:
        pos = params['close_position']
        if pos == '底20%':
            pos_condition = "close <= low_20d + 0.2 * (high_20d - low_20d)"
        elif pos == '底40%':
            pos_condition = "close <= low_20d + 0.4 * (high_20d - low_20d)"
        elif pos == '中位':
            pos_condition = "close >= low_20d + 0.4 * (high_20d - low_20d) AND close <= low_20d + 0.6 * (high_20d - low_20d)"
    
    # n_day_low (N日新低)
    low_condition = None
    if 'n_day_low' in params:
        n = params['n_day_low']
        if n == 10:
            low_condition = "s.low = low_10d"
        elif n == 20:
            low_condition = "s.low = low_20d"
    
    # sm_bearish (散户买卖, from moneyflow)
    mf_conditions = []
    if 'sm_bearish' in params:
        v = params['sm_bearish']
        if v == 'sell_sm>buy_sm':
            mf_conditions.append("m.sell_sm_amount > m.buy_sm_amount")
        elif v == 'buy_sm>sell_sm':
            mf_conditions.append("m.buy_sm_amount > m.sell_sm_amount")
    
    # net_mf_required
    if 'net_mf_required' in params:
        v = params['net_mf_required']
        if v == '负':
            mf_conditions.append("m.net_mf_amount < 0")
    
    # Build the query
    select_cols = ["s.ts_code", "s.trade_date", "s.close", "s.pct_chg", "s.amplitude"]
    window_cols = []
    
    # Position window
    window_cols.append("""
        MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as low_20d,
        MAX(s.high) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as high_20d
    """)
    
    # 10-day low window
    window_cols.append("""
        MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as low_10d
    """)
    
    # Future returns - use leadInFrame for correct frame specification
    window_cols.append("""
        leadInFrame(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) as close_5d,
        leadInFrame(s.close, 10) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) as close_10d,
        leadInFrame(s.close, 20) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) as close_20d
    """)
    
    window_sql = ",\n        ".join(window_cols)
    
    # Main query - FINAL requires subquery wrapper
    sql = f"""
    WITH daily AS (
        SELECT * FROM (
            SELECT 
                ts_code, trade_date, close, pct_chg, amplitude, low, high,
                {window_sql}
            FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
            WHERE trade_date >= {HISTORICAL_START}
        ) AS sd
        WHERE 1=1
    )
    SELECT 
        d.ts_code, d.trade_date, d.close, d.pct_chg, d.amplitude,
        d.close_5d, d.close_10d, d.close_20d,
        b.volume_ratio, b.turnover_rate, b.pe, b.pb, b.circ_mv
    FROM daily d
    LEFT JOIN (
        SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
    ) b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
    WHERE 1=1
        AND d.trade_date >= {HISTORICAL_START}
        AND d.trade_date <= {BASE_DATE}
        AND d.close_5d IS NOT NULL
        {f' AND {pos_condition}' if pos_condition else ''}
        {f' AND {low_condition}' if low_condition else ''}
        {' AND ' + ' AND '.join(conditions) if conditions else ''}
        {board_filter()}
    ORDER BY d.trade_date, d.ts_code
    """
    
    # For combos with moneyflow conditions, we need a different approach
    if mf_conditions:
        # Use two-step approach: first get candidates, then filter by moneyflow
        mf_sql = f"""
        WITH daily AS (
            SELECT * FROM (
                SELECT 
                    ts_code, trade_date, close, pct_chg, amplitude, low, high,
                    {window_sql}
                FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
                WHERE trade_date >= {HISTORICAL_START}
            ) AS sd
            WHERE 1=1
        )
        SELECT 
            d.ts_code, d.trade_date, d.close, d.pct_chg, d.amplitude,
            d.close_5d, d.close_10d, d.close_20d,
            b.volume_ratio, b.turnover_rate, b.pe, b.pb, b.circ_mv
        FROM daily d
        LEFT JOIN (
            SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv
            FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
        ) b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
        WHERE 1=1
            AND d.trade_date >= {HISTORICAL_START}
            AND d.trade_date <= {BASE_DATE}
            AND d.close_5d IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM (
                    SELECT ts_code, trade_date, buy_sm_amount, sell_sm_amount, net_mf_amount
                    FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) AS mf
                ) m
                WHERE m.ts_code = d.ts_code AND m.trade_date = d.trade_date
                {' AND ' + ' AND '.join(mf_conditions) if mf_conditions else ''}
            )
            {f' AND {pos_condition}' if pos_condition else ''}
            {f' AND {low_condition}' if low_condition else ''}
            {' AND ' + ' AND '.join(conditions) if conditions else ''}
            {board_filter()}
        ORDER BY d.trade_date, d.ts_code
        """
        sql = mf_sql
    
    print(f"[{combo_name}] Running SQL query...")
    try:
        rows = ch_query(sql)
    except Exception as e:
        return {
            'combo': combo_name,
            'params': params,
            'error': str(e),
            'signals': 0,
            'win_rate_5d': 0,
            'avg_ret_5d': 0,
            'avg_ret_10d': 0,
            'avg_ret_20d': 0,
            'sharpe_5d': 0,
        }
    
    if not rows:
        return {
            'combo': combo_name,
            'params': params,
            'signals': 0,
            'win_rate_5d': 0,
            'avg_ret_5d': 0,
            'avg_ret_10d': 0,
            'avg_ret_20d': 0,
            'sharpe_5d': 0,
        }
    
    n = len(rows)
    
    # Calculate returns
    ret_5d_list = []
    ret_10d_list = []
    ret_20d_list = []
    
    for r in rows:
        close = r.get('close')
        c5 = r.get('close_5d')
        c10 = r.get('close_10d')
        c20 = r.get('close_20d')
        
        if close and close > 0 and c5 and c5 > 0:
            ret_5d_list.append((c5 / close) - 1)
        if close and close > 0 and c10 and c10 > 0:
            ret_10d_list.append((c10 / close) - 1)
        if close and close > 0 and c20 and c20 > 0:
            ret_20d_list.append((c20 / close) - 1)
    
    if not ret_5d_list:
        return {
            'combo': combo_name,
            'params': params,
            'signals': 0,
            'win_rate_5d': 0,
            'avg_ret_5d': 0,
            'avg_ret_10d': 0,
            'avg_ret_20d': 0,
            'sharpe_5d': 0,
        }
    
    avg_ret_5d = sum(ret_5d_list) / len(ret_5d_list)
    avg_ret_10d = sum(ret_10d_list) / len(ret_10d_list) if ret_10d_list else 0
    avg_ret_20d = sum(ret_20d_list) / len(ret_20d_list) if ret_20d_list else 0
    
    win_5d = sum(1 for r in ret_5d_list if r > 0) / len(ret_5d_list)
    
    # Sharpe ratio: mean / std * sqrt(252/5) for 5-day returns
    if len(ret_5d_list) > 1:
        mean_ret = sum(ret_5d_list) / len(ret_5d_list)
        variance = sum((r - mean_ret) ** 2 for r in ret_5d_list) / (len(ret_5d_list) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0001
        sharpe = (mean_ret / std) * math.sqrt(252 / 5)
    else:
        sharpe = 0
    
    # P10 (worst 10% return)
    sorted_ret = sorted(ret_5d_list)
    p10_idx = max(0, int(len(sorted_ret) * 0.1) - 1)
    p10 = sorted_ret[p10_idx] if p10_idx < len(sorted_ret) else 0
    
    return {
        'combo': combo_name,
        'params': params,
        'signals': len(rows),
        'win_rate_5d': round(win_5d * 100, 2),
        'avg_ret_5d': round(avg_ret_5d * 100, 2),
        'avg_ret_10d': round(avg_ret_10d * 100, 2),
        'avg_ret_20d': round(avg_ret_20d * 100, 2),
        'sharpe_5d': round(sharpe, 3),
        'p10_5d': round(p10 * 100, 2),
    }


# ===== DEFINE 5 COMBOS =====

combos = [
    {
        'name': 'C1:恐慌深底筹码集中',
        'params': {
            'pct_chg_min': -7,
            'close_position': '底20%',
            'amplitude_min': 6,
            'volume_ratio_min': 1.3,
            'circ_mv_max': 3000000000,  # 30亿 in yuan
            'pe_max': 20,
            'turnover_max': 0.10,
        }
    },
    {
        'name': 'C2:连续恐慌放量微盘',
        'params': {
            'n_day_low': 20,
            'pct_chg_min': -5,
            'amplitude_min': 7,
            'volume_ratio_min': 1.2,
            'circ_mv_max': 3000000000,  # 30亿
        }
    },
    {
        'name': 'C3:恐慌散户逆势大振幅',
        'params': {
            'pct_chg_min': -7,
            'amplitude_min': 8,
            'volume_ratio_min': 1.0,
            'sm_bearish': 'buy_sm>sell_sm',
            'circ_mv_max': 5000000000,  # 50亿
            'turnover_min': 0.005,
            'turnover_max': 0.05,
        }
    },
    {
        'name': 'C4:双日恐慌深价值微盘',
        'params': {
            'n_day_low': 10,
            'pct_chg_min': -5,
            'amplitude_min': 5,
            'volume_ratio_min': 1.0,
            'pe_max': 15,
            'pb_max': 2,
            'circ_mv_max': 3000000000,  # 30亿
        }
    },
    {
        'name': 'C5:恐慌筹码锁定价值',
        'params': {
            'close_position': '底40%',
            'pct_chg_min': -5,
            'amplitude_min': 5,
            'volume_ratio_min': 1.3,
            'turnover_min': 0.003,
            'turnover_max': 0.03,
            'pe_max': 30,
            'circ_mv_max': 10000000000,  # 100亿
        }
    },
]

# ===== RUN ALL COMBOS =====
results = []
for combo in combos:
    print(f"\n{'='*60}")
    print(f"Running: {combo['name']}")
    print(f"{'='*60}")
    result = run_backtest(combo['name'], combo['params'])
    results.append(result)
    
    print(f"  Signals: {result.get('signals', 'ERROR')}")
    if 'error' in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  WinRate_5d: {result['win_rate_5d']}%")
        print(f"  AvgRet_5d: {result['avg_ret_5d']}%")
        print(f"  AvgRet_10d: {result['avg_ret_10d']}%")
        print(f"  AvgRet_20d: {result['avg_ret_20d']}%")
        print(f"  Sharpe_5d: {result['sharpe_5d']}")
        print(f"  P10_5d: {result['p10_5d']}%")

# ===== SUMMARY =====
print(f"\n{'='*60}")
print(f"ITER17 T3 RESULTS SUMMARY")
print(f"{'='*60}")

pass_count = 0
for r in results:
    if 'error' in r:
        print(f"  ❌ {r['combo']}: ERROR - {r['error']}")
        continue
    
    s = r['signals']
    wr = r['win_rate_5d']
    r5 = r['avg_ret_5d']
    
    passed = s >= 200 and wr >= 52 and r5 >= 3.0
    if passed:
        pass_count += 1
        print(f"  ✅ {r['combo']}: N={s} WR={wr}% R5={r5}%")
    else:
        fail_reasons = []
        if s < 200: fail_reasons.append(f"N={s}<200")
        if wr < 52: fail_reasons.append(f"WR={wr}%<52%")
        if r5 < 3.0: fail_reasons.append(f"R5={r5}%<3%")
        print(f"  ❌ {r['combo']}: N={s} WR={wr}% R5={r5}% — {'; '.join(fail_reasons)}")

print(f"\nPass rate: {pass_count}/5")

# Save results to JSON for the report
with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/iter17_t3_results.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\nResults saved to iter17_t3_results.json")
