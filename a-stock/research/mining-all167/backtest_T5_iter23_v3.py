#!/usr/bin/env python3
"""
T5 基本面估值流派 — Iter23 v3: 5新组合
聚焦: 60日深底破净高息微盘、极端价值SPX抄底、成长+深价值、营收增长+破净、极致参数
"""
import json, hashlib, math, subprocess, sys, os
from datetime import datetime

CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"
START_DATE = "2023-06-01"
END_DATE = "2026-05-12"
SIGNAL_END = "2026-05-06"

def ch_query(sql, fmt="JSON", timeout=180):
    with open('/tmp/ch_q_t5v3.sql', 'w') as f:
        f.write(sql.rstrip().rstrip(";") + (f"\nFORMAT {fmt}" if fmt else ""))
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time={timeout}&database={CH_DB}",
           "--data-binary", "@/tmp/ch_q_t5v3.sql"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        return json.loads(r.stdout)
    except Exception as e:
        print(f"  CH ERR: {e}", flush=True)
        return {"data": []}

def compute_stats(results):
    n = len(results)
    if n == 0:
        return {"signal_count": 0, "wr_5d": 0, "wr_10d": 0, "wr_20d": 0,
                "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
    def avg(lst): return sum(lst)/len(lst) if lst else 0
    def std(lst):
        if len(lst) < 2: return 0
        m = avg(lst)
        return math.sqrt(sum((x-m)**2 for x in lst)/len(lst))
    stats = {"signal_count": n}
    for k in ["ret_5d", "ret_10d", "ret_20d"]:
        vals = [r[k] for r in results if r[k] is not None]
        stats[f"wr_{k.replace('ret_','')}"] = round(sum(1 for v in vals if v>0)/len(vals)*100, 2) if vals else 0
        stats[k] = round(avg(vals)*100, 4) if vals else 0
    ret5_vals = [r["ret_5d"] for r in results if r["ret_5d"] is not None]
    if len(ret5_vals) > 1:
        sd = std(ret5_vals)
        stats["sharpe_5d"] = round((avg(ret5_vals)/sd)*math.sqrt(252/5), 4) if sd>0 else 0
    return stats

print("=== T5 Iter23 v3: Data Loading ===", flush=True)
t0 = datetime.now()

r = ch_query("SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL")
print(f"max(trade_date): {r.get('data',[{}])[0].get('max(trade_date)','?')}", flush=True)

# === Phase 1: Candidates with 60日 position ===
print(f"\nPhase 1: Candidates (60d position + basic filters)...", flush=True)
sql = f"""
SELECT ts_code, trade_date, close, pct_chg, high, low, vol, amount,
    round((high / low - 1) * 100, 2) AS amplitude,
    round((close - min_low_20d) / NULLIF(max_high_20d - min_low_20d, 0.001) * 100, 2) AS pos_20d,
    round((close - min_low_60d) / NULLIF(max_high_60d - min_low_60d, 0.001) * 100, 2) AS pos_60d,
    round(vol / NULLIF(avg_vol_20d, 0.001), 2) AS vol_ratio
FROM (
    SELECT ts_code, trade_date, close, high, low, vol, amount, pct_chg,
        MIN(low) OVER w20 AS min_low_20d,
        MAX(high) OVER w20 AS max_high_20d,
        MIN(low) OVER w60 AS min_low_60d,
        MAX(high) OVER w60 AS max_high_60d,
        AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol_20d
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START_DATE}' AND trade_date <= '{SIGNAL_END}'
      AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
      AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    WINDOW w20 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
           w60 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
)
ORDER BY ts_code, trade_date
"""
r = ch_query(sql, timeout=600)
data = r.get('data', [])
print(f"  Candidates: {len(data)} rows", flush=True)
candidates = {(row['ts_code'], str(row['trade_date'])[:10]): row for row in data}
ts_codes = set(row['ts_code'] for row in data)
print(f"  Stocks: {len(ts_codes)}", flush=True)

# === Phase 2: Daily Basic ===
print(f"\nPhase 2: daily_basic...", flush=True)
code_list = list(ts_codes)
batch_size = 500
db_data = {}
for i in range(0, len(code_list), batch_size):
    batch = code_list[i:i+batch_size]
    codes_str = ",".join(f"'{c}'" for c in batch)
    r = ch_query(f"""
    SELECT ts_code, trade_date, pe, pb, dv_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '{START_DATE}' AND trade_date <= '{SIGNAL_END}'
      AND ts_code IN ({codes_str})
    ORDER BY ts_code, trade_date
    """, timeout=300)
    for row in r.get('data', []):
        db_data[(row['ts_code'], str(row['trade_date'])[:10])] = row
    if i % (batch_size*5) == 0 or i+batch_size >= len(code_list):
        print(f"  Batch {i//batch_size}/{(len(code_list)-1)//batch_size}: total={len(db_data)}", flush=True)
print(f"  Daily basic: {len(db_data)} rows", flush=True)

# === Phase 3: SPX ===
print(f"\nPhase 3: SPX...", flush=True)
r = ch_query(f"""SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL
WHERE ts_code='SPX' AND trade_date >= '{START_DATE}' ORDER BY trade_date""")
spx_sorted = sorted(r.get('data', []), key=lambda x: x['trade_date'])
spx_prev_up = {}
for i, row in enumerate(spx_sorted):
    dt = str(row['trade_date'])[:10]
    if i > 0:
        prev_chg = spx_sorted[i-1].get('pct_chg', 0) or 0
        spx_prev_up[dt] = prev_chg > 0
    else:
        spx_prev_up[dt] = False
print(f"  SPX rows: {len(spx_sorted)}", flush=True)

# === Phase 4: Forward prices ===
print(f"\nPhase 4: forward prices...", flush=True)
all_prices = {}
for i in range(0, len(code_list), batch_size):
    batch = code_list[i:i+batch_size]
    codes_str = ",".join(f"'{c}'" for c in batch)
    r = ch_query(f"""
    SELECT ts_code, trade_date, close
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
      AND ts_code IN ({codes_str})
    ORDER BY ts_code, trade_date
    """, timeout=300)
    for row in r.get('data', []):
        all_prices[(row['ts_code'], str(row['trade_date'])[:10])] = row['close']
print(f"  Prices: {len(all_prices)} rows", flush=True)

# === Phase 5: fina_indicator ===
print(f"\nPhase 5: fina_indicator...", flush=True)
fina_data = {}
for i in range(0, len(code_list), 1000):
    batch = code_list[i:i+1000]
    codes_str = ",".join(f"'{c}'" for c in batch)
    r = ch_query(f"""
    SELECT ts_code, end_date, netprofit_yoy, tr_yoy, roe
    FROM tushare.tushare_fina_indicator FINAL
    WHERE ts_code IN ({codes_str})
    ORDER BY ts_code, end_date DESC
    """, timeout=300)
    for row in r.get('data', []):
        code = row['ts_code']
        if code not in fina_data:
            fina_data[code] = {
                'netprofit_yoy': row.get('netprofit_yoy'),
                'tr_yoy': row.get('tr_yoy'),
                'roe': row.get('roe'),
            }
print(f"  Fina: {len(fina_data)} stocks", flush=True)

elapsed_data = datetime.now() - t0
print(f"\nData loading: {elapsed_data}", flush=True)
print(f"Summary: {len(candidates)} cand, {len(db_data)} db, {len(fina_data)} fina, {len(all_prices)} prices", flush=True)

# ===================== 5 NEW COMBOS =====================

def compute_forward_returns(signals, all_prices):
    results = []
    for s in signals:
        code = s['ts_code']
        entry_date = s['trade_date']
        stock_dates = sorted([d for (c,d),v in all_prices.items() if c==code and d>=entry_date])
        if entry_date not in stock_dates: continue
        idx = stock_dates.index(entry_date)
        rets = {'ts_code': code, 'trade_date': entry_date, 'entry_close': s.get('close')}
        for offset, key in [(5,'ret_5d'),(10,'ret_10d'),(20,'ret_20d')]:
            if idx+offset < len(stock_dates):
                fd = stock_dates[idx+offset]
                fc = all_prices.get((code, fd))
                if fc and s.get('close') and s['close'] > 0:
                    rets[key] = (fc - s['close']) / s['close']
                else:
                    rets[key] = None
            else:
                rets[key] = None
        results.append(rets)
    return results

combos = [
    {
        'id': 'C6',
        'name': 'C6-60日深底破净高息微盘SPX: PB≤1+dv≥2%+CM≤30亿+60日底15%+VR≥1.2+振幅≥6%+SPX前日涨',
        'desc': '60日深底(15%) + 破净(PB≤1) + 高股息(dv≥2%) + 极致微盘(CM≤30亿) + SPX宏观过滤',
    },
    {
        'id': 'C7',
        'name': 'C7-极端价值SPX抄底: PE≤10+PB≤1+dv≥3%+CM≤50亿+底20%+SPX前日涨+pct≤-3%',
        'desc': '极端深价值(PE≤10+PB≤1+dv≥3%) + SPX + 微跌抄底(pct≤-3%)',
    },
    {
        'id': 'C8',
        'name': 'C8-成长破净高息: netprofit_yoy≥10%+PB≤1+dv≥2%+CM30-200亿+底20%+VR≥1.0',
        'desc': '净利润增长≥10% + 破净(PB≤1) + 高股息(dv≥2%) + 中大盘(30-200亿) — 成长+价值独立策略',
    },
    {
        'id': 'C9',
        'name': 'C9-营收增长破净: tr_yoy≥10%+PE≤15+PB≤1+CM≤50亿+底30%+振幅≥5%',
        'desc': '营收增长(tr_yoy≥10%) + 深价值(PE≤15+PB≤1) + 微盘 — 替代netprofit_yoy测试',
    },
    {
        'id': 'C10',
        'name': 'C10-极致破净高息SPX深底: PB≤1+dv≥3%+60日底10%+VR≥1.3+CM≤30亿+SPX前日涨',
        'desc': '极致: 最苛刻股息(dv≥3%) + 最深60日底10% + 最小微盘(CM≤30亿) + SPX + 强放量(VR≥1.3)',
    },
]

results = []

for combo in combos:
    cid = combo['id']
    cname = combo['name']
    print(f"\n{'='*60}", flush=True)
    print(f"Combo {cid}: {cname}", flush=True)
    print(f"{'='*60}", flush=True)

    signals = []
    skipped = {'pos':0, 'amp':0, 'vr':0, 'db':0, 'fina':0, 'pct':0, 'spx':0}

    for (code, date), row in candidates.items():
        k = (code, date)
        db_row = db_data.get(k, {})
        fina = fina_data.get(code, {})

        pos_20d = row.get('pos_20d', 999) or 999
        pos_60d = row.get('pos_60d', 999) or 999
        amp = row.get('amplitude', 0) or 0
        vr = row.get('vol_ratio', 0) or 0
        pct = row.get('pct_chg', 0) or 0

        pe = db_row.get('pe')
        pb = db_row.get('pb')
        dv = db_row.get('dv_ratio')
        cm = db_row.get('circ_mv')
        ny = fina.get('netprofit_yoy')
        ty = fina.get('tr_yoy')

        # SPX check
        spx_ok = True
        if cid in ['C6', 'C7', 'C10']:
            if date not in spx_prev_up or not spx_prev_up[date]:
                skipped['spx'] += 1
                spx_ok = False
        if not spx_ok:
            continue

        if cid == 'C6':
            # PB≤1 + dv≥2% + CM≤30亿 + 60日底15% + VR≥1.2 + 振幅≥6% + SPX
            if pos_60d > 15: skipped['pos'] += 1; continue
            if vr < 1.2: skipped['vr'] += 1; continue
            if amp < 6: skipped['amp'] += 1; continue
            if not pb or pb <= 0 or pb > 1: skipped['db'] += 1; continue
            if not dv or dv < 2: skipped['db'] += 1; continue
            if not cm or cm > 300000: skipped['db'] += 1; continue

        elif cid == 'C7':
            # PE≤10 + PB≤1 + dv≥3% + CM≤50亿 + 底20% + SPX + pct≤-3%
            if pct > -3: skipped['pct'] += 1; continue
            if pos_20d > 20: skipped['pos'] += 1; continue
            if not pe or pe <= 0 or pe > 10: skipped['db'] += 1; continue
            if not pb or pb <= 0 or pb > 1: skipped['db'] += 1; continue
            if not dv or dv < 3: skipped['db'] += 1; continue
            if not cm or cm > 500000: skipped['db'] += 1; continue

        elif cid == 'C8':
            # netprofit_yoy≥10% + PB≤1 + dv≥2% + CM30-200亿 + 底20% + VR≥1.0
            if pos_20d > 20: skipped['pos'] += 1; continue
            if vr < 1.0: skipped['vr'] += 1; continue
            if not pb or pb <= 0 or pb > 1: skipped['db'] += 1; continue
            if not dv or dv < 2: skipped['db'] += 1; continue
            if not cm or cm < 300000 or cm > 2000000: skipped['db'] += 1; continue
            if not ny or ny < 10: skipped['fina'] += 1; continue

        elif cid == 'C9':
            # tr_yoy≥10% + PE≤15 + PB≤1 + CM≤50亿 + 底30% + 振幅≥5%
            if pos_20d > 30: skipped['pos'] += 1; continue
            if amp < 5: skipped['amp'] += 1; continue
            if not pe or pe <= 0 or pe > 15: skipped['db'] += 1; continue
            if not pb or pb <= 0 or pb > 1: skipped['db'] += 1; continue
            if not cm or cm > 500000: skipped['db'] += 1; continue
            if not ty or ty < 10: skipped['fina'] += 1; continue

        elif cid == 'C10':
            # PB≤1 + dv≥3% + 60日底10% + VR≥1.3 + CM≤30亿 + SPX
            if pos_60d > 10: skipped['pos'] += 1; continue
            if vr < 1.3: skipped['vr'] += 1; continue
            if not pb or pb <= 0 or pb > 1: skipped['db'] += 1; continue
            if not dv or dv < 3: skipped['db'] += 1; continue
            if not cm or cm > 300000: skipped['db'] += 1; continue

        signals.append({
            'ts_code': code, 'trade_date': date, 'close': row['close'],
            'amplitude': amp, 'pos_20d': pos_20d, 'pos_60d': pos_60d,
            'vol_ratio': vr, 'pct_chg': pct,
            'circ_mv': cm, 'pe': pe, 'pb': pb, 'dv_ratio': dv,
            'netprofit_yoy': ny, 'tr_yoy': ty,
        })

    print(f"  Signals: {len(signals)}", flush=True)
    print(f"  Skipped: {json.dumps(skipped)}", flush=True)

    if len(signals) == 0:
        r = {'combo_id': cid, 'name': cname, 'signal_count': 0, 'n_5d': 0,
             'win_rate_5d': 0, 'ret_5d': 0, 'ret_10d': 0, 'ret_20d': 0,
             'sharpe_5d': 0, 'status': '❌ 零信号'}
        results.append(r)
        print(f"  Status: ❌ 零信号", flush=True)
        continue

    forward_results = compute_forward_returns(signals, all_prices)
    stats = compute_stats(forward_results)
    n_5d = sum(1 for r in forward_results if r.get('ret_5d') is not None)

    wr_5d = stats['wr_5d']
    ret_5d = stats['ret_5d']
    passed = wr_5d >= 52 and ret_5d >= 3 and n_5d >= 200
    excellent = wr_5d >= 58 and ret_5d >= 7 and n_5d >= 1000

    r = {
        'combo_id': cid,
        'name': cname,
        'signal_count': stats['signal_count'],
        'n_5d': n_5d,
        'win_rate_5d': round(wr_5d, 2),
        'ret_5d': round(ret_5d, 2),
        'ret_10d': round(stats['ret_10d'], 2),
        'ret_20d': round(stats['ret_20d'], 2),
        'sharpe_5d': round(stats['sharpe_5d'], 3),
        'status': ('🏆 优秀' if excellent else '✅' if passed else ('⚠️ 不足' if n_5d >= 200 else '❌ 信号不足'))
    }
    results.append(r)
    print(f"  N={stats['signal_count']}, N5d={n_5d}, WR5d={wr_5d:.1f}%, "
          f"R5={ret_5d:.2f}%, R10={stats['ret_10d']:.2f}%, "
          f"R20={stats['ret_20d']:.2f}%, Sharpe={stats['sharpe_5d']:.3f}, "
          f"Status={r['status']}", flush=True)

# ===== REPORT =====
elapsed = datetime.now() - t0
print(f"\n{'='*90}", flush=True)
print(f"📊 T5 基本面估值流派 — Iter23 v3 汇总 (用时{elapsed})", flush=True)
print(f"{'='*90}", flush=True)
print(f"{'ID':<4} {'信号量':>8} {'N5d':>6} {'WR5d':>8} {'R5%':>9} {'R10%':>9} {'R20%':>9} {'Sharpe':>10} {'状态':<8}", flush=True)
print(f"{'-'*75}", flush=True)
for r in results:
    print(f"{r['combo_id']:<4} {r['signal_count']:>8} {r['n_5d']:>6} "
          f"{r['win_rate_5d']:>7.1f}% {r['ret_5d']:>8.2f}% "
          f"{r['ret_10d']:>8.2f}% {r['ret_20d']:>8.2f}% "
          f"{r['sharpe_5d']:>9.3f}  {r['status']:<8}", flush=True)

passed = [r for r in results if r['status'] in ['✅', '🏆 优秀']]
if passed:
    best = max(passed, key=lambda x: x['ret_5d'])
    print(f"\n🏆 最佳通过: {best['name']}", flush=True)
    print(f"   R5={best['ret_5d']}%, WR={best['win_rate_5d']}%, N={best['signal_count']}, Sharpe={best['sharpe_5d']}", flush=True)

# Save combined with v2 results
output_dir = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_23'
os.makedirs(output_dir, exist_ok=True)

final_output = {
    'analyst': 'T5',
    'iteration': 23,
    'version': 'v3',
    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'start_date': START_DATE,
    'data_info': {
        'candidates': len(candidates), 'db_data': len(db_data),
        'prices': len(all_prices), 'fina_stocks': len(fina_data)
    },
    'combos': results,
}
with open(f'{output_dir}/t5_iter23_v3_results.json', 'w') as f:
    json.dump(final_output, f, ensure_ascii=False, indent=2)
print(f"\n✅ Saved to {output_dir}/t5_iter23_v3_results.json", flush=True)
print("DONE", flush=True)
