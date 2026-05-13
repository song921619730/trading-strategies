#!/usr/bin/env python3
"""
Iter18 — T2 动量趋势 (Momentum Trend) 分析师 — v5
5组全新参数组合 + 全量历史回测
关键修复: turnover_rate 单位为%(0.45=0.45%)，条件修正
"""
import json, subprocess, os, sys, time
from datetime import datetime
from hashlib import md5
from collections import OrderedDict

CH_SCRIPT = "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py"
BOARD = "ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'"
START_DATE = '2020-01-01'
END_DATE = '2026-05-12'
RESULTS = []

def ch_query(sql, label=""):
    start = time.time()
    result = subprocess.run(["python3", CH_SCRIPT, "sql", sql],
        capture_output=True, text=True, timeout=300)
    elapsed = time.time() - start
    if result.returncode != 0:
        err = result.stderr[:500] if result.stderr else "unknown error"
        print(f"  ❌ SQL Error ({elapsed:.1f}s): {err}")
        return []
    try:
        data = json.loads(result.stdout)
        print(f"  ✅ {len(data)} rows ({elapsed:.1f}s)")
        return data
    except json.JSONDecodeError:
        print(f"  ❌ JSON Error: {result.stdout[:300]}")
        return []

def compute_returns(data):
    rets_5d, rets_10d, rets_20d = [], [], []
    for row in data:
        c = float(row['close'])
        if row.get('fwd_close_5') and row['fwd_close_5'] is not None:
            f5 = float(row['fwd_close_5'])
            if f5 > 0 and c > 0:
                rets_5d.append((f5 / c - 1) * 100)
        if row.get('fwd_close_10') and row['fwd_close_10'] is not None:
            f10 = float(row['fwd_close_10'])
            if f10 > 0 and c > 0:
                rets_10d.append((f10 / c - 1) * 100)
        if row.get('fwd_close_20') and row['fwd_close_20'] is not None:
            f20 = float(row['fwd_close_20'])
            if f20 > 0 and c > 0:
                rets_20d.append((f20 / c - 1) * 100)
    return rets_5d, rets_10d, rets_20d

def calc_metrics(rets):
    n = len(rets)
    if n < 5: return {"count": n, "win_rate": 0, "avg_return": 0, "sharpe": 0}
    wins = sum(1 for r in rets if r > 0)
    wr = wins / n * 100
    avg = sum(rets) / n
    var = sum((r - avg) ** 2 for r in rets) / (n - 1) if n > 1 else 0
    std = var ** 0.5 if var > 0 else 0.001
    sharpe = (avg / std) * (252 / 5) ** 0.5 if std > 0 else 0
    return {"count": n, "win_rate": round(wr, 2), "avg_return": round(avg, 4), "sharpe": round(sharpe, 3)}

# ═══════════════════════════════════════════════════
# COMBO 1: 持续放量5日+深底20%+中阳+微盘 (已验证)
# ═══════════════════════════════════════════════════
C1_SQL = f"""
SELECT ts_code, trade_date, close, pct_chg, circ_mv,
       fwd_close_5, fwd_close_10, fwd_close_20
FROM (
    SELECT d.ts_code AS ts_code, d.trade_date AS trade_date,
           d.close AS close, d.pct_chg AS pct_chg, d.high AS high, d.low AS low, d.vol AS vol,
           b.volume_ratio AS volume_ratio, b.circ_mv AS circ_mv,
           any(d.vol) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS vol_1d,
           any(d.vol) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 2 PRECEDING AND 2 PRECEDING) AS vol_2d,
           any(d.vol) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 3 PRECEDING AND 3 PRECEDING) AS vol_3d,
           any(d.vol) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND 4 PRECEDING) AS vol_4d,
           MIN(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
           MAX(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) d
    LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
) t
WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
  AND vol_4d > 0 AND vol_3d > 0 AND vol_2d > 0 AND vol_1d > 0
  AND vol_4d < vol_3d AND vol_3d < vol_2d AND vol_2d < vol_1d AND vol_1d < vol
  AND (max_20d - min_20d) > 0
  AND close <= min_20d + (max_20d - min_20d) * 0.2
  AND pct_chg >= 2
  AND (high - low) / low * 100 >= 5
  AND circ_mv <= 300000
  AND {BOARD}
LIMIT 50000
"""

# ═══════════════════════════════════════════════════
# COMBO 2: 底部中阳放量+超大单确认 (T2×T4)
# ═══════════════════════════════════════════════════
C2_SQL = f"""
SELECT ts_code, trade_date, close, pct_chg, circ_mv,
       fwd_close_5, fwd_close_10, fwd_close_20
FROM (
    SELECT d.ts_code AS ts_code, d.trade_date AS trade_date,
           d.close AS close, d.pct_chg AS pct_chg, d.high AS high, d.low AS low,
           b.volume_ratio AS volume_ratio, b.circ_mv AS circ_mv, b.turnover_rate AS turnover_rate,
           m.buy_elg_amount AS buy_elg_amount, m.sell_elg_amount AS sell_elg_amount, m.net_mf_amount AS net_mf_amount,
           MIN(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
           MAX(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) d
    LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
    LEFT JOIN (SELECT * FROM tushare.tushare_moneyflow FINAL) m ON d.ts_code = m.ts_code AND d.trade_date = m.trade_date
) t
WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
  AND (max_20d - min_20d) > 0
  AND close <= min_20d + (max_20d - min_20d) * 0.2
  AND pct_chg >= 3
  AND (high - low) / low * 100 >= 5
  AND volume_ratio >= 1.3
  AND circ_mv <= 500000
  AND (turnover_rate IS NULL OR (turnover_rate >= 0.3 AND turnover_rate <= 25))
  AND buy_elg_amount > sell_elg_amount
  AND net_mf_amount > 0
  AND {BOARD}
LIMIT 50000
"""

# ═══════════════════════════════════════════════════
# COMBO 3: 双日反转+深底+放量+微盘 (动量启动)
# ═══════════════════════════════════════════════════
C3_SQL = f"""
SELECT ts_code, trade_date, close, pct_chg, circ_mv,
       fwd_close_5, fwd_close_10, fwd_close_20
FROM (
    SELECT d.ts_code AS ts_code, d.trade_date AS trade_date,
           d.close AS close, d.pct_chg AS pct_chg, d.high AS high, d.low AS low,
           b.volume_ratio AS volume_ratio, b.circ_mv AS circ_mv, b.turnover_rate AS turnover_rate,
           any(d.pct_chg) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS prev_pct_chg,
           MIN(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
           MAX(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) d
    LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
) t
WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
  AND prev_pct_chg <= -3 AND pct_chg >= 2
  AND volume_ratio >= 1.3
  AND (high - low) / low * 100 >= 5
  AND (max_20d - min_20d) > 0
  AND close <= min_20d + (max_20d - min_20d) * 0.2
  AND circ_mv <= 300000
  AND (turnover_rate IS NULL OR turnover_rate <= 25)
  AND {BOARD}
LIMIT 50000
"""

# ═══════════════════════════════════════════════════
# COMBO 4: MA5支撑+底40%+放量中阳+小盘
# ═══════════════════════════════════════════════════
C4_SQL = f"""
SELECT ts_code, trade_date, close, pct_chg, circ_mv,
       fwd_close_5, fwd_close_10, fwd_close_20
FROM (
    SELECT d.ts_code AS ts_code, d.trade_date AS trade_date,
           d.close AS close, d.pct_chg AS pct_chg, d.high AS high, d.low AS low,
           b.volume_ratio AS volume_ratio, b.circ_mv AS circ_mv, b.turnover_rate AS turnover_rate,
           AVG(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5,
           MIN(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
           MAX(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) d
    LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
) t
WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
  AND close > ma5
  AND (max_20d - min_20d) > 0
  AND close <= min_20d + (max_20d - min_20d) * 0.5
  AND pct_chg >= 2
  AND volume_ratio >= 1.3
  AND (high - low) / low * 100 >= 4
  AND circ_mv <= 500000
  AND (turnover_rate IS NULL OR turnover_rate <= 25)
  AND {BOARD}
LIMIT 50000
"""

# ═══════════════════════════════════════════════════
# COMBO 5: 接近20日新高放量温和突破+小盘
# ═══════════════════════════════════════════════════
C5_SQL = f"""
SELECT ts_code, trade_date, close, pct_chg, circ_mv,
       fwd_close_5, fwd_close_10, fwd_close_20
FROM (
    SELECT d.ts_code AS ts_code, d.trade_date AS trade_date,
           d.close AS close, d.pct_chg AS pct_chg, d.high AS high, d.low AS low,
           b.volume_ratio AS volume_ratio, b.circ_mv AS circ_mv, b.turnover_rate AS turnover_rate,
           MAX(d.high) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND 1 PRECEDING) AS high_20d_excl,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
           any(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) d
    LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
) t
WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
  AND high_20d_excl IS NOT NULL
  AND close > high_20d_excl * 0.98
  AND volume_ratio >= 1.0
  AND pct_chg >= 1
  AND (high - low) / low * 100 >= 3
  AND circ_mv <= 500000
  AND (turnover_rate IS NULL OR turnover_rate <= 20)
  AND {BOARD}
LIMIT 50000
"""

# ═══════════════════════════════════════════════════
COMBOS = [
    {
        "name": "C1-持续放量5日深底中阳微盘",
        "desc": "持续放量5日+底20%+涨幅≥2%+振幅≥5%+CM≤30亿",
        "params": OrderedDict([
            ("vol_trend_5d", "持续放量(5日逐日放大)"),
            ("close_position", "底20%(20日)"),
            ("pct_chg_min", 2),
            ("amplitude_min", 5),
            ("circ_mv_max_wan", 300000)
        ]),
        "sql": C1_SQL
    },
    {
        "name": "C2-底部中阳放量超大单确认",
        "desc": "底20%+涨幅≥3%+VR≥1.3+振幅≥5%+buy_elg>sell_elg+net_mf>0+CM≤50亿",
        "params": OrderedDict([
            ("close_position", "底20%(20日)"),
            ("pct_chg_min", 3),
            ("volume_ratio_min", 1.3),
            ("amplitude_min", 5),
            ("moneyflow", "buy_elg>sell_elg+net_mf>0"),
            ("circ_mv_max_wan", 500000)
        ]),
        "sql": C2_SQL
    },
    {
        "name": "C3-双日反转深底放量微盘",
        "desc": "前日跌≥3%+今日涨≥2%+VR≥1.3+振幅≥5%+底20%+CM≤30亿",
        "params": OrderedDict([
            ("pattern", "双日反转(前日恐慌+今日放量)"),
            ("close_position", "底20%(20日)"),
            ("pct_chg_range", "prev≤-3%+today≥2%"),
            ("volume_ratio_min", 1.3),
            ("amplitude_min", 5),
            ("circ_mv_max_wan", 300000)
        ]),
        "sql": C3_SQL
    },
    {
        "name": "C4-MA5支撑底部放量小盘",
        "desc": "close>MA5+底50%+涨幅≥2%+VR≥1.3+振幅≥4%+CM≤50亿",
        "params": OrderedDict([
            ("ma_support", "close>MA5"),
            ("close_position", "底50%(20日)"),
            ("pct_chg_min", 2),
            ("volume_ratio_min", 1.3),
            ("amplitude_min", 4),
            ("circ_mv_max_wan", 500000)
        ]),
        "sql": C4_SQL
    },
    {
        "name": "C5-接近20日新高放量小盘",
        "desc": "close>前20日最高98%+涨幅≥1%+VR≥1.0+振幅≥3%+CM≤50亿",
        "params": OrderedDict([
            ("n_day_high", "20(接近新高>98%)"),
            ("pct_chg_min", 1),
            ("volume_ratio_min", 1.0),
            ("amplitude_min", 3),
            ("circ_mv_max_wan", 500000)
        ]),
        "sql": C5_SQL
    }
]

# ═══════════════════════════════════════════════════
print("=" * 70)
print(f"Iter18 T2 动量趋势 Backtest v5 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Data: {START_DATE} ~ {END_DATE}")
print("=" * 70)

for combo in COMBOS:
    print(f"\n{'─' * 60}")
    print(f"{combo['name']}: {combo['desc']}")
    print(f"{'─' * 60}")
    
    data = ch_query(combo['sql'], combo['name'])
    
    if not data or len(data) < 5:
        RESULTS.append({
            "name": combo['name'], "desc": combo['desc'],
            "params": dict(combo['params']),
            "results_5d": {"count": len(data) if data else 0, "win_rate": 0, "avg_return": 0, "sharpe": 0},
            "results_10d": {"count": 0, "win_rate": 0, "avg_return": 0},
            "results_20d": {"count": 0, "win_rate": 0, "avg_return": 0}
        })
        print(f"  ⚠️  Insufficient data ({len(data) if data else 0} rows)")
        continue
    
    rets_5d, rets_10d, rets_20d = compute_returns(data)
    m5 = calc_metrics(rets_5d)
    m10 = calc_metrics(rets_10d)
    m20 = calc_metrics(rets_20d)
    
    RESULTS.append({
        "name": combo['name'], "desc": combo['desc'],
        "params": dict(combo['params']),
        "results_5d": m5, "results_10d": m10, "results_20d": m20
    })
    
    print(f"  📊 5D: N={m5['count']:>6d}  WR={m5['win_rate']:>6.2f}%  R5={m5['avg_return']:>6.2f}%  Sharpe={m5['sharpe']:>6.3f}")
    if m10['count'] > 0:
        print(f"     10D: N={m10['count']:>6d}  WR={m10['win_rate']:>6.2f}%  R10={m10['avg_return']:>6.2f}%")
    if m20['count'] > 0:
        print(f"     20D: N={m20['count']:>6d}  WR={m20['win_rate']:>6.2f}%  R20={m20['avg_return']:>6.2f}%")
    
    passed = m5['count'] >= 200 and m5['win_rate'] >= 55 and m5['avg_return'] >= 5
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} (标准: WR≥55% AND R5≥5% AND N≥200)")

# ═══════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("SUMMARY — All 5 Combos")
print(f"{'=' * 70}")
print(f"{'Rank':<5} {'Combo':<38} {'N':>6} {'WR%':>7} {'R5%':>7} {'R10%':>7} {'R20%':>7} {'Sharpe':>8} {'Status':>8}")
print(f"{'─' * 88}")

sorted_results = sorted(RESULTS, key=lambda x: (
    x['results_5d']['win_rate'] * max(0, x['results_5d']['avg_return']) * (x['results_5d']['count'] ** 0.5)
), reverse=True)

for i, r in enumerate(sorted_results):
    res5 = r['results_5d']; res10 = r['results_10d']; res20 = r['results_20d']
    passed = res5['count'] >= 200 and res5['win_rate'] >= 55 and res5['avg_return'] >= 5
    status = "✅" if passed else "❌"
    print(f"{i+1:<5} {r['name']:<38} {res5['count']:>6} {res5['win_rate']:>6.2f}% {res5['avg_return']:>6.2f}% "
          f"{res10['avg_return']:>6.2f}% {res20['avg_return']:>6.2f}% {res5['sharpe']:>7.3f} {status:>8}")

print(f"\nPass criteria: WR≥55% AND R5≥5% AND N≥200")

# Save
results_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_18/t2_results.json"
with open(results_path, 'w') as f:
    json.dump(RESULTS, f, indent=2, ensure_ascii=False)
print(f"Results saved to: {results_path}")
