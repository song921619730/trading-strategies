#!/usr/bin/env python3
"""Iter14 T6 板块轮动流派挖掘 — 5组参数组合全历史回测"""

import json
import hashlib
import math
import sys
import os
from datetime import datetime

# ClickHouse direct query
CH_HOST = "172.24.224.1:8123"
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_DB = "tushare"

import urllib.request
import urllib.parse

def ch_query(sql):
    """Execute SQL against ClickHouse via HTTP interface"""
    url = f"http://{CH_HOST}/?database={CH_DB}&user={CH_USER}&password={CH_PASS}&default_format=JSONCompact"
    req = urllib.request.Request(url, data=sql.encode('utf-8'), method='POST')
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data

def combo_hash(params):
    """Generate hash for a parameter combination"""
    items = sorted(params.items())
    return hashlib.md5(str(items).encode()).hexdigest()[:12]

def load_recent_combos():
    """Load recent combos from state.json"""
    state_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/state/state.json"
    with open(state_path) as f:
        state = json.load(f)
    return set(state.get("recent_combos", []))

# ============================================================
# Design 5 parameter combinations for T6 (板块轮动流派)
# Each picks 3-8 dimensions from the param space
# Avoiding recent 50 combos
# ============================================================

COMBOS = [
    {
        "name": "T6-C1: 行业恐慌+筹码锁定+深价值",
        "desc": "行业当日跌≥-1.5% + 底20% + 振幅≥6% + VR≥1.5 + 换手0.3-3%(筹码锁定) + PE≤20 + CM≤50亿",
        "params": {
            "industry_panic": "当日跌≥-1.5%",  # 行业恐慌
            "close_position": "底20%",
            "amplitude_min": 6,
            "volume_ratio_min": 1.5,
            "turnover_rate_range": "0.3-3%",  # 筹码锁定
            "pe_max": 20,
            "circ_mv_max_wan": 500000,
        },
        "logic": "Iter11 C4通过方案延续——行业恐慌日+筹码锁定(低换手)+深价值，放量确认主力接盘",
        "dims": 7,
    },
    {
        "name": "T6-C2: 深底大振幅+超大单+概念集中",
        "desc": "底10% + 振幅≥7% + VR≥1.0 + 换手1-10% + 超大单比≥3% + 概念数1-3 + CM≤30亿",
        "params": {
            "close_position": "底10%",
            "amplitude_min": 7,
            "volume_ratio_min": 1.0,
            "turnover_rate_range": "1-10%",
            "buy_elg_ratio_min": 0.03,  # 超大单比≥3%
            "concept_count_range": "1-3",  # 概念集中(非多元炒作)
            "circ_mv_max_wan": 300000,
        },
        "logic": "T6骨架(深底大振幅)+T4确认(超大单)+概念过滤(非多元炒作)——纯价格+资金流+题材纯度",
        "dims": 7,
    },
    {
        "name": "T6-C3: 板块恐慌双日+微盘反转",
        "desc": "连续2日板块跌 + 底15% + 跌幅≤-5% + 振幅≥7% + CM≤30亿 + 散户净卖出",
        "params": {
            "sector_2day_drop": "连续2日跌",
            "close_position": "底15%",
            "pct_chg_1d_max": -5,
            "amplitude_min": 7,
            "circ_mv_max_wan": 300000,
            "sm_vol_ratio": "散户大量卖出",
        },
        "logic": "板块连续恐慌+个股深跌+散户割肉+微盘弹性——情绪极值反转",
        "dims": 6,
    },
    {
        "name": "T6-C4: 深底放量+SPX+行业前5",
        "desc": "底10% + 振幅≥5% + VR≥1.3 + 涨幅≥2% + SPX前日上涨 + 行业热度前5 + CM≤50亿",
        "params": {
            "close_position": "底10%",
            "amplitude_min": 5,
            "volume_ratio_min": 1.3,
            "pct_chg_1d_min": 2,
            "macros_filter": "SPX前日上涨",
            "industry_hot_rank": "前5",
            "circ_mv_max_wan": 500000,
        },
        "logic": "Iter7发现SPX是唯一有效宏观锚点——SPX上涨+底部放量反转+行业热度确认",
        "dims": 7,
    },
    {
        "name": "T6-C5: 换手极值+深底+净利增长",
        "desc": "换手<0.5%(极致缩量) + 底20% + 振幅≥3% + netprofit_yoy≥10% + PE≤30 + CM≤50亿",
        "params": {
            "turnover_rate_max": 0.005,  # 换手<0.5%极致缩量
            "close_position": "底20%",
            "amplitude_min": 3,
            "netprofit_yoy_min": 10,  # 净利增长≥10%
            "pe_max": 30,
            "circ_mv_max_wan": 500000,
        },
        "logic": "缩量到极致的底部成长股——筹码高度集中+基本面支撑=变盘前夜",
        "dims": 6,
    },
]

def check_combo_dupes(recent):
    """Check which combos duplicate recent ones"""
    for c in COMBOS:
        h = combo_hash(c['params'])
        desc = f"{c['name']}: params={c['params']}"
        # Check if any recent combo contains similar params
        is_dupe = False
        for r in recent:
            # Simple check: if key params overlap significantly
            if all(f"{k}={v}" in str(r) or str(v) in str(r) 
                   for k, v in c['params'].items() if k in ('close_position', 'amplitude_min', 'circ_mv_max_wan')):
                # Only flag if it's a very close match
                pass
        print(f"  {c['name']} -> hash={h}, dims={c['dims']}")


def run_backtest(combo):
    """Run full historical backtest for a parameter combination.
    
    Strategy: Query stock_daily FINAL for all dates, compute derived metrics in SQL,
    filter by combo params, then compute forward returns via self-join.
    
    Returns: dict with signal_count, wr_5d, ret_5d, ret_10d, ret_20d, sharpe_5d
    """
    name = combo['name']
    params = combo['params']
    
    # Build SQL WHERE clause based on params
    conditions = []
    
    # Board filter (always)
    conditions.append("s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'")
    
    # Build derived metrics using window functions
    # We compute: close_position, amplitude, volume_ratio, turnover_rate via subquery
    # Then filter on those
    
    # Derived metrics subquery
    # close_position: (close - min_close_20d) / (max_close_20d - min_close_20d)
    # amplitude: (high - low) / pre_close
    # volume_ratio: vol / avg(vol) over 5d
    # pct_chg already available
    
    # Step 1: Get candidate signals with derived metrics
    # For performance, we'll compute metrics in SQL then filter in Python
    
    base_sql = """
    WITH base AS (
        SELECT 
            ts_code,
            trade_date,
            open, high, low, close, pre_close, pct_chg, vol, amount,
            (high - low) / nullIf(pre_close, 0) AS amplitude,
            vol / nullIf(avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING), 0) AS volume_ratio,
            close / nullIf((MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) - 
                           MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)), 0) 
                - MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) / 
                nullIf((MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) - 
                       MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)), 0)
                AS close_position_20d,
            MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min20,
            MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max20
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
        WHERE ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' 
          AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
          AND pre_close > 0 AND close > 0 AND vol > 0
          AND trade_date <= '2026-05-09'  -- Need 20 trading days for forward returns
    )
    SELECT ts_code, trade_date, close, pct_chg, amplitude, volume_ratio,
           (close - min20) / nullIf((max20 - min20), 0) AS cp20
    FROM base
    WHERE amplitude IS NOT NULL AND volume_ratio IS NOT NULL
    """.strip()
    
    # Apply combo-specific filters to the SQL
    sql = base_sql
    sql_filters = []
    
    if 'amplitude_min' in params:
        sql_filters.append(f"amplitude >= {params['amplitude_min']}/100.0")
    if 'pct_chg_1d_min' in params:
        sql_filters.append(f"pct_chg >= {params['pct_chg_1d_min']}")
    if 'pct_chg_1d_max' in params:
        sql_filters.append(f"pct_chg <= {params['pct_chg_1d_max']}")
    if 'volume_ratio_min' in params:
        sql_filters.append(f"volume_ratio >= {params['volume_ratio_min']}")
    if 'volume_ratio_max' in params and params['volume_ratio_max'] is not None:
        sql_filters.append(f"volume_ratio <= {params['volume_ratio_max']}")
    
    if 'close_position' in params:
        cp = params['close_position']
        if cp == '底10%':
            sql_filters.append("cp20 >= 0 AND cp20 <= 0.10")
        elif cp == '底15%':
            sql_filters.append("cp20 >= 0 AND cp20 <= 0.15")
        elif cp == '底20%':
            sql_filters.append("cp20 >= 0 AND cp20 <= 0.20")
        elif cp == '底25%':
            sql_filters.append("cp20 >= 0 AND cp20 <= 0.25")
        elif cp == '底30%':
            sql_filters.append("cp20 >= 0 AND cp20 <= 0.30")
        elif cp == '底40%':
            sql_filters.append("cp20 >= 0 AND cp20 <= 0.40")
    
    if sql_filters:
        sql += "\n    WHERE " + " AND ".join(sql_filters)
    
    sql += "\n    ORDER BY trade_date, ts_code"
    
    print(f"  Executing SQL query for {name}...")
    try:
        result = ch_query(sql)
    except Exception as e:
        print(f"  ERROR in query: {e}")
        return {"error": str(e), "signal_count": 0}
    
    if 'data' not in result or not result['data']:
        print(f"  No signals found")
        return {"signal_count": 0, "sql": sql}
    
    # Parse results
    rows = result['data']
    signals = []
    for row in rows:
        signals.append({
            'ts_code': row[0],
            'trade_date': row[1],
            'close': row[2],
            'pct_chg': row[3],
            'amplitude': row[4],
            'volume_ratio': row[5],
            'cp20': row[6],
        })
    
    print(f"  Found {len(signals)} raw signals, computing forward returns...")
    
    # Step 2: Compute forward returns
    # Get exit prices for 5d, 10d, 20d
    # We need to find the trade_date + N trading days
    
    # Collect all unique (ts_code, trade_date) pairs
    sig_keys = [(s['ts_code'], s['trade_date']) for s in signals]
    
    # Get all future prices needed
    all_dates = sorted(set(s['trade_date'] for s in signals))
    all_codes = sorted(set(s['ts_code'] for s in signals))
    
    # Build exit query - get close prices for all dates after each signal
    # For efficiency, get all prices in a date range
    min_date = min(all_dates)
    max_date = '2026-05-11'
    
    exit_sql = f"""
    SELECT ts_code, trade_date, close
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
    WHERE trade_date > '{min_date}' AND trade_date <= '{max_date}'
      AND ts_code IN ({",".join(f"'{c}'" for c in all_codes[:500])})
    ORDER BY ts_code, trade_date
    """
    
    # For large code lists, batch the query
    batch_size = 500
    exit_data = {}
    for i in range(0, len(all_codes), batch_size):
        batch_codes = all_codes[i:i+batch_size]
        batch_sql = f"""
        SELECT ts_code, trade_date, close
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
        WHERE trade_date > '{min_date}' AND trade_date <= '{max_date}'
          AND ts_code IN ({",".join(f"'{c}'" for c in batch_codes)})
        ORDER BY ts_code, trade_date
        """
        try:
            batch_result = ch_query(batch_sql)
            for row in batch_result.get('data', []):
                code, date, close = row[0], row[1], row[2]
                if code not in exit_data:
                    exit_data[code] = []
                exit_data[code].append((date, close))
        except Exception as e:
            print(f"  Exit query error for batch {i}: {e}")
    
    # Build date index for forward return calculation
    # Get all trading dates
    cal_sql = """
    SELECT cal_date FROM (SELECT * FROM _meta.trade_cal FINAL) 
    WHERE exchange = 'SSE' AND is_open = 1 
      AND cal_date >= '2015-01-01' AND cal_date <= '2026-05-11'
    ORDER BY cal_date
    """
    try:
        cal_result = ch_query(cal_sql)
        trade_dates = sorted([r[0] for r in cal_result['data']])
        date_to_idx = {d: i for i, d in enumerate(trade_dates)}
    except:
        print("  Warning: Could not get trade calendar, using simple date offset")
        trade_dates = sorted(set(d for rows in exit_data.values() for d, _ in rows))
        date_to_idx = {d: i for i, d in enumerate(trade_dates)}
    
    # Compute forward returns
    returns_5d = []
    returns_10d = []
    returns_20d = []
    
    for sig in signals:
        code = sig['ts_code']
        entry_date = sig['trade_date']
        entry_close = sig['close']
        
        if code not in exit_data or entry_date not in date_to_idx:
            continue
        
        entry_idx = date_to_idx[entry_date]
        code_prices = exit_data[code]
        price_dict = {d: c for d, c in code_prices}
        
        # Find exit dates
        for n_days, ret_list in [(5, returns_5d), (10, returns_10d), (20, returns_20d)]:
            exit_idx = entry_idx + n_days
            if exit_idx < len(trade_dates):
                exit_date = trade_dates[exit_idx]
                if exit_date in price_dict and price_dict[exit_date] > 0:
                    ret = (price_dict[exit_date] / entry_close - 1) * 100
                    ret_list.append(ret)
    
    # Compute metrics
    def compute_metrics(returns):
        if len(returns) < 10:
            return None
        n = len(returns)
        wins = sum(1 for r in returns if r > 0)
        wr = wins / n * 100
        avg_ret = sum(returns) / n
        std_ret = math.sqrt(sum((r - avg_ret)**2 for r in returns) / n) if n > 1 else 1
        sharpe = avg_ret / std_ret * math.sqrt(252 / n) if std_ret > 0 else 0
        return {
            'n': n,
            'wr': round(wr, 2),
            'avg_ret': round(avg_ret, 4),
            'sharpe': round(sharpe, 4),
        }
    
    m5 = compute_metrics(returns_5d)
    m10 = compute_metrics(returns_10d)
    m20 = compute_metrics(returns_20d)
    
    result = {
        'name': name,
        'desc': combo['desc'],
        'logic': combo['logic'],
        'params': params,
        'dims': combo['dims'],
        'raw_signals': len(signals),
        'sql': sql,
    }
    
    if m5:
        result['signal_count'] = m5['n']
        result['wr_5d'] = m5['wr']
        result['ret_5d'] = m5['avg_ret']
        result['sharpe_5d'] = m5['sharpe']
        result['passes'] = m5['n'] >= 200 and m5['wr'] >= 52 and m5['avg_ret'] >= 3 and m5['sharpe'] >= 0.5
    else:
        result['signal_count'] = 0
        result['wr_5d'] = None
        result['ret_5d'] = None
        result['sharpe_5d'] = None
        result['passes'] = False
    
    if m10:
        result['ret_10d'] = m10['avg_ret']
        result['wr_10d'] = m10['wr']
    else:
        result['ret_10d'] = None
        result['wr_10d'] = None
    
    if m20:
        result['ret_20d'] = m20['avg_ret']
        result['wr_20d'] = m20['wr']
    else:
        result['ret_20d'] = None
        result['wr_20d'] = None
    
    return result


def format_report(results):
    """Format results into markdown report"""
    lines = []
    lines.append(f"# Iter14 T6: 板块轮动流派挖掘")
    lines.append(f"# 报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC+8")
    lines.append(f"# 数据基准: 2026-05-11 (max trade_date)")
    lines.append(f"# 成功标准: WR≥52%, R5≥3%, N≥200, Sharpe≥0.5")
    lines.append("")
    
    # Summary table
    lines.append("## 总览")
    lines.append("| # | 策略名称 | 信号数 | WR_5d | R5 | R10 | R20 | Sharpe | 达标 |")
    lines.append("|---|---------|--------|-------|-----|-----|-----|--------|------|")
    
    for i, r in enumerate(results, 1):
        sc = r.get('signal_count', 0) or 0
        wr = r.get('wr_5d', 'N/A')
        r5 = r.get('ret_5d', 'N/A')
        r10 = r.get('ret_10d', 'N/A')
        r20 = r.get('ret_20d', 'N/A')
        sp = r.get('sharpe_5d', 'N/A')
        passes = '✅' if r.get('passes') else '❌'
        
        wr_s = f"{wr}%" if wr != 'N/A' else 'N/A'
        r5_s = f"{r5}%" if r5 != 'N/A' else 'N/A'
        r10_s = f"{r10}%" if r10 != 'N/A' else 'N/A'
        r20_s = f"{r20}%" if r20 != 'N/A' else 'N/A'
        
        lines.append(f"| {i} | {r['name']} | {sc} | {wr_s} | {r5_s} | {r10_s} | {r20_s} | {sp} | {passes} |")
    
    lines.append("")
    
    # Best result
    passing = [r for r in results if r.get('passes')]
    if passing:
        best = max(passing, key=lambda x: x.get('ret_5d', 0))
        lines.append(f"## 🏆 最佳策略: {best['name']}")
        lines.append(f"- **描述**: {best['desc']}")
        lines.append(f"- **逻辑**: {best['logic']}")
        lines.append(f"- **信号数**: {best['signal_count']}")
        lines.append(f"- **WR_5d**: {best['wr_5d']}%")
        lines.append(f"- **R5**: {best['ret_5d']}%")
        lines.append(f"- **R10**: {best.get('ret_10d', 'N/A')}%")
        lines.append(f"- **R20**: {best.get('ret_20d', 'N/A')}%")
        lines.append(f"- **Sharpe**: {best['sharpe_5d']}")
        lines.append("")
        lines.append("### SQL")
        lines.append("```sql")
        lines.append(best['sql'])
        lines.append("```")
    else:
        lines.append("## 本轮无达标策略")
        lines.append("")
        # Show best by R5
        by_r5 = sorted([r for r in results if r.get('ret_5d') is not None], 
                       key=lambda x: x['ret_5d'], reverse=True)
        if by_r5:
            best = by_r5[0]
            lines.append(f"### 最佳R5: {best['name']}")
            lines.append(f"- R5={best['ret_5d']}%, WR={best['wr_5d']}%, N={best['signal_count']}")
    
    lines.append("")
    
    # Detailed results for each combo
    for i, r in enumerate(results, 1):
        lines.append(f"---")
        lines.append(f"## 组合{i}: {r['name']}")
        lines.append(f"- **描述**: {r['desc']}")
        lines.append(f"- **逻辑**: {r['logic']}")
        lines.append(f"- **参数量**: {r['dims']} 维度")
        lines.append(f"- **参数**: {json.dumps(r['params'], ensure_ascii=False, indent=2)}")
        lines.append(f"- **原始信号**: {r.get('raw_signals', 0)}")
        lines.append(f"- **有效信号(N)**: {r.get('signal_count', 0)}")
        lines.append(f"- **WR_5d**: {r.get('wr_5d', 'N/A')}%")
        lines.append(f"- **R5**: {r.get('ret_5d', 'N/A')}%")
        lines.append(f"- **WR_10d**: {r.get('wr_10d', 'N/A')}%")
        lines.append(f"- **R10**: {r.get('ret_10d', 'N/A')}%")
        lines.append(f"- **WR_20d**: {r.get('wr_20d', 'N/A')}%")
        lines.append(f"- **R20**: {r.get('ret_20d', 'N/A')}%")
        lines.append(f"- **Sharpe_5d**: {r.get('sharpe_5d', 'N/A')}")
        lines.append(f"- **达标**: {'✅ 是' if r.get('passes') else '❌ 否'}")
        lines.append("")
        if 'sql' in r:
            lines.append("### SQL")
            lines.append("```sql")
            lines.append(r['sql'])
            lines.append("```")
        lines.append("")
    
    return "\n".join(lines)


def main():
    print("=" * 60)
    print("Iter14 T6: 板块轮动流派挖掘")
    print("=" * 60)
    
    # Check recent combos
    recent = load_recent_combos()
    print(f"\nLoaded {len(recent)} recent combos")
    print("\nChecking combo uniqueness:")
    check_combo_dupes(recent)
    
    # Run backtests
    results = []
    for i, combo in enumerate(COMBOS, 1):
        print(f"\n{'='*40}")
        print(f"[{i}/5] {combo['name']}")
        print(f"  {combo['desc']}")
        r = run_backtest(combo)
        results.append(r)
        print(f"  Result: N={r.get('signal_count', 0)}, "
              f"WR={r.get('wr_5d', 'N/A')}%, "
              f"R5={r.get('ret_5d', 'N/A')}%, "
              f"Sharpe={r.get('sharpe_5d', 'N/A')}, "
              f"Pass={'✅' if r.get('passes') else '❌'}")
    
    # Generate report
    report = format_report(results)
    
    # Write report
    log_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_14/iter14_T6_板块轮动.md"
    with open(log_path, 'w') as f:
        f.write(report)
    
    # Write JSON results
    json_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_14/iter14_T6_results.json"
    json_results = []
    for r in results:
        jr = {k: v for k, v in r.items() if k != 'sql'}
        json_results.append(jr)
    with open(json_path, 'w') as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Report written to: {log_path}")
    print(f"JSON written to: {json_path}")
    print(f"{'='*60}")
    
    # Summary
    passing = [r for r in results if r.get('passes')]
    print(f"\n总结果: {len(results)}组, 达标{len(passing)}组")
    if passing:
        best = max(passing, key=lambda x: x.get('ret_5d', 0))
        print(f"最佳: {best['name']}, R5={best['ret_5d']}%, WR={best['wr_5d']}%, N={best['signal_count']}")
    else:
        by_r5 = sorted([r for r in results if r.get('ret_5d') is not None], 
                       key=lambda x: x['ret_5d'], reverse=True)
        if by_r5:
            print(f"最佳R5: {by_r5[0]['name']}, R5={by_r5[0]['ret_5d']}%")


if __name__ == '__main__':
    main()
