#!/usr/bin/env python3
"""
Iter17 T3 Reversal Low-Absorption Backtest
Tests 5 parameter combos against full historical data (2020-01-01 to 2026-05-12)
*/
import json, sys, math
sys.path.insert(0, '/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts')
from ch_query import _ch_query as ch_query

HOST = "172.24.224.1"
HTTP_PORT = "8123"
USER = "ai_reader"
PASSWORD = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
DATABASE = "tushare"

# Date range for historical backtest
START_DATE = "2020-01-01"
END_DATE = "2026-05-12"
HIST_DAYS = 20  # days back for window computations (lead frame needs this many future days available)

BOARD_FILTER = "AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'"

def ch_query_direct(sql):
    """Execute SQL against ClickHouse HTTP interface."""
    import urllib.request, urllib.parse
    params = {
        "user": USER,
        "password": PASSWORD,
        "database": DATABASE,
        "query": sql,
        "default_format": "JSONEachRow",
    }
    url = f"http://{HOST}:{HTTP_PORT}/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read().decode("utf-8")
        if not body.strip():
            return []
        return [json.loads(line) for line in body.strip().split("\n") if line.strip()]

def run_backtest(combo_name, params):
    """Run full historical backtest for a parameter combo."""
    print(f"\n{'='*60}")
    print(f"[{combo_name}] Starting backtest...")
    print(f"{'='*60}")
    
    conditions = []
    joins = []
    tbl_alias = "s"
    
    # ===== Build conditions =====
    
    # pct_chg (daily return limit)
    if 'pct_chg_min' in params:
        conditions.append(f"s.pct_chg <= {params['pct_chg_min']}")
    if 'pct_chg_max' in params:
        conditions.append(f"s.pct_chg <= {params['pct_chg_max']}")
    
    # amplitude = (high - low) / pre_close * 100
    if 'amplitude_min' in params:
        amp = params['amplitude_min']
        conditions.append(f"((s.high - s.low) / NULLIF(s.pre_close, 0) * 100) >= {amp}")
    
    # volume_ratio from daily_basic
    if 'volume_ratio_min' in params:
        conditions.append(f"b.volume_ratio >= {params['volume_ratio_min']}")
    
    # turnover_rate from daily_basic
    if 'turnover_min' in params:
        conditions.append(f"b.turnover_rate >= {params['turnover_min']}")
    if 'turnover_max' in params:
        conditions.append(f"b.turnover_rate <= {params['turnover_max']}")
    
    # circ_mv from daily_basic (unit: 万元)
    if 'circ_mv_max' in params:
        cm = params['circ_mv_max'] / 10000  # convert yuan to 万元
        conditions.append(f"b.circ_mv <= {cm}")
    
    # PE / PB from daily_basic
    if 'pe_max' in params and params['pe_max'] is not None:
        conditions.append(f"b.pe <= {params['pe_max']}")
    if 'pb_max' in params and params['pb_max'] is not None:
        conditions.append(f"b.pb <= {params['pb_max']}")
    
    # close_position (requires window function subquery)
    pos_filter = ""
    if 'close_position' in params:
        pos = params['close_position']
        if pos == '底20%':
            pos_filter = "AND w.close_pos <= 0.2"
    elif 'n_day_low' in params:
        n = params['n_day_low']
        pos_filter = f"AND w.low_{n}d = 1"
    
    # ===== Build main query with window functions =====
    
    # Select columns for signals
    select_cols = """
        w.ts_code, w.trade_date, w.close,
        w.pct_chg, w.close_5d, w.close_10d, w.close_20d
    """.strip()
    
    from_clause = f"""
    FROM (
        SELECT
            s.ts_code, s.trade_date, s.close, s.pct_chg,
            -- Close position in 20-day range (0=bottom, 1=top)
            (s.close - low_20d) / NULLIF(high_20d - low_20d, 0) AS close_pos,
            -- N-day low flag
            CASE WHEN low_10d_chk = 1 THEN 1 ELSE 0 END AS low_10d,
            CASE WHEN low_20d_chk = 1 THEN 1 ELSE 0 END AS low_20d,
            -- Future close prices (use subquery approach via numbered CTE)
            s.close as close_signal,
            -- We'll compute future returns via array approach or separate query
            s.close_5d, s.close_10d, s.close_20d
        FROM (
            SELECT 
                sd.*,
                -- 20-day range
                MIN(sd.low) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
                MAX(sd.high) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
                -- 10-day new low check
                CASE WHEN sd.low = MIN(sd.low) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) THEN 1 ELSE 0 END AS low_10d_chk,
                -- 20-day new low check
                CASE WHEN sd.low = MIN(sd.low) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) THEN 1 ELSE 0 END AS low_20d_chk
            FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) sd
            WHERE sd.trade_date >= '{START_DATE}'
              AND sd.trade_date <= '{END_DATE}'
        ) s
    ) w
    """.strip()
    
    # Need to join with daily_basic for VR, TR, PE, PB, circ_mv
    has_basic = any(k in params for k in ['volume_ratio_min', 'turnover_min', 'turnover_max', 'circ_mv_max', 'pe_max', 'pb_max'])
    
    # Need to join with moneyflow for sm_bearish conditions
    has_mf = 'sm_bearish' in params or 'net_mf_required' in params
    
    # Check if we need future returns - we need close_5d, close_10d, close_20d
    # This is the tricky part. Let's use a CTE approach.
    
    # Fully window-based approach with leadInFrame
    # ClickHouse supports leadInFrame with explicit ROWS frame
    
    win_sql = f"""
    WITH signals AS (
        SELECT
            s.ts_code, s.trade_date, s.close, s.pct_chg,
            -- future returns using leadInFrame
            leadInFrame(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_5d,
            leadInFrame(s.close, 10) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_10d,
            leadInFrame(s.close, 20) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS close_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
        WHERE s.trade_date >= '{START_DATE}'
          AND s.trade_date <= '{END_DATE}'
    ),
    pos AS (
        SELECT
            s.ts_code, s.trade_date, s.close, s.pct_chg,
            -- 20-day range position
            (s.close - MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)) 
            / NULLIF(MAX(s.high) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) 
                     - MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0) AS close_pos,
            -- 10/20 day new low
            CASE WHEN s.low = MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) THEN 1 ELSE 0 END AS is_low_10d,
            CASE WHEN s.low = MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) THEN 1 ELSE 0 END AS is_low_20d,
            -- amplitude
            (s.high - s.low) / NULLIF(s.pre_close, 0) * 100 AS amp,
            sig.close_5d, sig.close_10d, sig.close_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
        INNER JOIN signals sig ON s.ts_code = sig.ts_code AND s.trade_date = sig.trade_date
    )
    SELECT 
        pos.ts_code, pos.trade_date, pos.close, pos.pct_chg, pos.amp,
        pos.close_5d, pos.close_10d, pos.close_20d
    FROM pos
    WHERE 1=1
        AND pos.close_5d IS NOT NULL
        {pos_filter}
    """
    
    # Add conditions for price/amplitude
    if conditions:
        win_sql += "\n        AND " + "\n        AND ".join(conditions)
    
    # Add moneyflow conditions via EXISTS
    if has_mf:
        mf_conds = []
        if 'sm_bearish' in params:
            v = params['sm_bearish']
            if v == 'sell_sm>buy_sm':
                mf_conds.append("mf.sell_sm_amount > mf.buy_sm_amount")
            elif v == 'buy_sm>sell_sm':
                mf_conds.append("mf.buy_sm_amount > mf.sell_sm_amount")
        if 'net_mf_required' in params:
            v = params['net_mf_required']
            if v == '负':
                mf_conds.append("mf.net_mf_amount < 0")
        
        mf_filter = " AND ".join(mf_conds) if mf_conds else "1=1"
        win_sql += f"""
        AND EXISTS (
            SELECT 1 FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) mf
            WHERE mf.ts_code = pos.ts_code AND mf.trade_date = pos.trade_date
              AND {mf_filter}
        )
        """
    
    # Join with daily_basic if needed
    if has_basic:
        win_sql = win_sql.replace("FROM pos", """
        FROM pos
        LEFT JOIN (
            SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv, dv_ratio
            FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) db
        ) b ON pos.ts_code = b.ts_code AND pos.trade_date = b.trade_date
        """)
        
        basic_conds = []
        if 'volume_ratio_min' in params:
            basic_conds.append(f"b.volume_ratio >= {params['volume_ratio_min']}")
        if 'turnover_min' in params:
            basic_conds.append(f"b.turnover_rate >= {params['turnover_min']}")
        if 'turnover_max' in params:
            basic_conds.append(f"b.turnover_rate <= {params['turnover_max']}")
        if 'circ_mv_max' in params:
            cm = params['circ_mv_max'] / 10000
            basic_conds.append(f"b.circ_mv <= {cm}")
        if 'pe_max' in params and params['pe_max'] is not None:
            basic_conds.append(f"b.pe <= {params['pe_max']}")
        if 'pb_max' in params and params['pb_max'] is not None:
            basic_conds.append(f"b.pb <= {params['pb_max']}")
        
        if basic_conds:
            win_sql += "\n        AND " + "\n        AND ".join(basic_conds)
    
    # Add board filter
    win_sql += f"\n        {BOARD_FILTER}"
    
    win_sql += "\n    ORDER BY pos.trade_date, pos.ts_code"
    
    # ===== Execute query =====
    print(f"  SQL length: {len(win_sql)} chars")
    try:
        rows = ch_query_direct(win_sql)
    except Exception as e:
        print(f"  SQL ERROR: {e}")
        # Print a snippet of the query for debugging
        print(f"  Query (first 500): {win_sql[:500]}")
        return {
            'combo': combo_name,
            'params': params,
            'error': str(e),
            'sql_first500': win_sql[:500],
            'signals': 0, 'win_rate_5d': 0, 'avg_ret_5d': 0,
            'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
        }
    
    if not rows:
        print(f"  [WARN] Zero signals returned!")
        return {
            'combo': combo_name,
            'params': params,
            'signals': 0, 'win_rate_5d': 0, 'avg_ret_5d': 0,
            'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
        }
    
    n = len(rows)
    print(f"  Signals: {n}")
    
    # ===== Compute returns in Python =====
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
        print(f"  [WARN] No valid return calculations!")
        return {
            'combo': combo_name, 'params': params,
            'signals': n, 'win_rate_5d': 0, 'avg_ret_5d': 0,
            'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
        }
    
    avg_ret_5d = sum(ret_5d_list) / len(ret_5d_list) * 100
    avg_ret_10d = sum(ret_10d_list) / len(ret_10d_list) * 100 if ret_10d_list else 0
    avg_ret_20d = sum(ret_20d_list) / len(ret_20d_list) * 100 if ret_20d_list else 0
    
    win_5d = sum(1 for r in ret_5d_list if r > 0) / len(ret_5d_list) * 100
    
    # Sharpe ratio
    if len(ret_5d_list) > 1:
        mean_ret = sum(ret_5d_list) / len(ret_5d_list)
        variance = sum((r - mean_ret) ** 2 for r in ret_5d_list) / (len(ret_5d_list) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0001
        sharpe = (mean_ret / std) * math.sqrt(252 / 5)
    else:
        sharpe = 0
    
    # P10 (worst 10%)
    sorted_ret = sorted(ret_5d_list)
    p10_idx = max(0, int(len(sorted_ret) * 0.1) - 1)
    p10 = sorted_ret[p10_idx] * 100 if p10_idx < len(sorted_ret) else 0
    
    print(f"  WinRate_5d: {win_5d:.2f}%")
    print(f"  AvgRet_5d: {avg_ret_5d:.2f}%")
    print(f"  AvgRet_10d: {avg_ret_10d:.2f}%")
    print(f"  AvgRet_20d: {avg_ret_20d:.2f}%")
    print(f"  Sharpe_5d: {sharpe:.3f}")
    print(f"  P10_5d: {p10:.2f}%")
    
    return {
        'combo': combo_name,
        'params': params,
        'signals': n,
        'win_rate_5d': round(win_5d, 2),
        'avg_ret_5d': round(avg_ret_5d, 2),
        'avg_ret_10d': round(avg_ret_10d, 2),
        'avg_ret_20d': round(avg_ret_20d, 2),
        'sharpe_5d': round(sharpe, 3),
        'p10_5d': round(p10, 2),
    }


# ===== 5 COMBOS =====
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

# ===== RUN ALL =====
results = []
for combo in combos:
    result = run_backtest(combo['name'], combo['params'])
    results.append(result)

# ===== SUMMARY =====
print(f"\n{'='*60}")
print(f"ITER17 T3 RESULTS SUMMARY")
print(f"{'='*60}")

pass_count = 0
best = None
for r in results:
    if 'error' in r and r['signals'] == 0:
        print(f"  ❌ {r['combo']}: ERROR - {r.get('error', 'Unknown')}")
        continue
    
    s = r['signals']
    wr = r['win_rate_5d']
    r5 = r['avg_ret_5d']
    
    passed = s >= 200 and wr >= 52 and r5 >= 3.0
    if passed:
        pass_count += 1
        best = r if best is None or (r5 > best['avg_ret_5d']) else best
        print(f"  ✅ {r['combo']}: N={s} WR={wr}% R5={r5}% R10={r['avg_ret_10d']}% R20={r['avg_ret_20d']}% Sharpe={r['sharpe_5d']}")
    else:
        fail_reasons = []
        if s < 200: fail_reasons.append(f"N={s}<200")
        if wr < 52: fail_reasons.append(f"WR={wr}%<52%")
        if r5 < 3.0: fail_reasons.append(f"R5={r5}%<3%")
        print(f"  {'⚠️' if s >= 50 else '❌'} {r['combo']}: N={s} WR={wr}% R5={r5}% — {'; '.join(fail_reasons)}")

print(f"\nPass rate: {pass_count}/5")

# Save results
output = {
    'timestamp': '2026-05-13 05:30 UTC+8',
    'iteration': 17,
    'analyst': 'T3_Reversal_Low_Absorption',
    'results': results,
    'pass_count': pass_count,
    'best': best,
}
with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/iter17_t3_results.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\nResults saved to iter17_t3_results.json")

# Save the SQL for best combo for the log
if best:
    print(f"\n🏆 BEST COMBO: {best['combo']}")
    print(f"  N={best['signals']} WR={best['win_rate_5d']}% R5={best['avg_ret_5d']}% R10={best['avg_ret_10d']}% R20={best['avg_ret_20d']}% Sharpe={best['sharpe_5d']}")
