#!/usr/bin/env python3
"""T6 板块轮动 Iter13 — 新维度探索
使用 ch_query.py 直连 ClickHouse（MCP query_sql 太慢导致115次超时）

新维度方向（避免历史重复）：
- C1: 行业相对强度（个股跑赢行业均值，板块内相对强势）
- C2: 行业资金分歧（net_amount_rate极低但close不跌 = 散户恐慌主力承接）
- C3: 板块量价背离（行业量增价跌 = 洗盘末期）
- C4: 行业动量加速（3D pct_change 加速上行 + 个股底部启动）
- C5: 行业恐慌后修复（行业连跌2日后企稳 + 个股深底放量）
"""
import json, hashlib, subprocess, sys, math, os
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START_DATE = '20200101'
END_DATE = '20260511'

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"  [SQL ERR] {r.stderr[:300]}", file=sys.stderr)
        return []
    try:
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else data.get("data", [])
    except:
        return []

def combo_hash(params):
    return hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:11]

def calc_sharpe(returns):
    if len(returns) < 10:
        return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0:
        return 0
    var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    std = math.sqrt(var)
    return mean_r / std * math.sqrt(252 / 5) if std > 0 else 0

def calc_p10(returns):
    if not returns:
        return 0
    s = sorted(returns)
    idx = max(0, int(len(s) * 0.1) - 1)
    return s[idx] * 100

# ============================================================
# Step 1: Load stock industry mapping (stock_basic)
# ============================================================
print("Loading stock industry mapping...")
rows = ch_query("SELECT ts_code, industry FROM tushare.tushare_stock_basic FINAL WHERE industry IS NOT NULL AND industry != ''")
stock_industry = {r["ts_code"]: r["industry"] for r in rows}
print(f"  Industry mapping: {len(stock_industry)} stocks")

# ============================================================
# Step 2: Load daily data with window functions
# ============================================================
print("Loading daily data (stock_daily + daily_basic join)...")
daily_sql = f"""
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.high, d.low, d.pre_close,
       db.volume_ratio, db.turnover_rate, db.pe, db.pb, db.circ_mv
FROM tushare.tushare_stock_daily d
LEFT JOIN tushare.tushare_daily_basic db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date
WHERE d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%'
  AND d.ts_code NOT LIKE '920%' AND d.ts_code NOT LIKE '%ST%'
  AND d.close IS NOT NULL AND d.amount > 0
  AND d.trade_date >= '{START_DATE}' AND d.trade_date <= '{END_DATE}'
ORDER BY d.ts_code, d.trade_date
"""
rows = ch_query(daily_sql)
print(f"  Daily rows: {len(rows)}")

# Build index structures
stock_data = {}  # code -> [(dt, close, pct_chg, high, low, vr, tr, pe, pb, circ_mv), ...]
idx_map = {}     # (code, dt) -> position
for r in rows:
    code = r["ts_code"]
    dt = str(r["trade_date"]).replace("-", "")
    if code not in stock_data:
        stock_data[code] = []
    pos = len(stock_data[code])
    stock_data[code].append((
        dt,
        r["close"],
        r.get("pct_chg", 0) or 0,
        r.get("high", 0) or 0,
        r.get("low", 0) or 0,
        r.get("volume_ratio", 0) or 0,
        r.get("turnover_rate", 0) or 0,
        r.get("pe", 0) or 0,
        r.get("pb", 0) or 0,
        r.get("circ_mv", 0) or 0,
    ))
    idx_map[(code, dt)] = pos

print(f"  Stocks: {len(stock_data)}, Total bars: {sum(len(v) for v in stock_data.values())}")

# ============================================================
# Step 3: Compute daily industry returns (PAST, no look-ahead)
# ============================================================
print("Computing daily industry returns (past, no look-ahead)...")
# For each (date, industry), compute avg pct_chg of constituent stocks
day_ind_rets = defaultdict(list)  # dt -> [(industry, avg_ret, count), ...]
ind_stocks = defaultdict(set)
for code, ind in stock_industry.items():
    if code in stock_data:
        ind_stocks[ind].add(code)

for dt_str in sorted(set(dt for bars in stock_data.values() for dt, *_ in bars)):
    for ind, stocks in ind_stocks.items():
        rets = []
        for code in stocks:
            bars = stock_data.get(code, [])
            for i, (d, close, pct, *_) in enumerate(bars):
                if d == dt_str:
                    rets.append(pct)
                    break
        if len(rets) >= 3:
            avg_r = sum(rets) / len(rets)
            day_ind_rets[dt_str].append((ind, avg_r, len(rets)))

print(f"  Days with industry data: {len(day_ind_rets)}")

# Pre-compute industry daily rankings
day_ind_rank = {}  # dt -> {industry: rank_1based}
for dt, inds in day_ind_rets.items():
    sorted_inds = sorted(inds, key=lambda x: -x[1])
    day_ind_rank[dt] = {ind: i + 1 for i, (ind, _, _) in enumerate(sorted_inds)}

# Pre-compute industry 3D cumulative return
ind_3d_ret = {}  # (dt, industry) -> 3D cumulative return
all_dates = sorted(set(dt for bars in stock_data.values() for dt, *_ in bars))
date_idx = {d: i for i, d in enumerate(all_dates)}

for ind, stocks in ind_stocks.items():
    for code in stocks:
        bars = stock_data.get(code, [])
        for i in range(3, len(bars)):
            dt = bars[i][0]
            ret3d = (bars[i][1] / bars[i - 3][1] - 1) * 100 if bars[i - 3][1] > 0 else 0
            key = (dt, ind)
            if key not in ind_3d_ret:
                ind_3d_ret[key] = []
            ind_3d_ret[key].append(ret3d)

# Average by (dt, ind)
ind_3d_avg = {}
for key, rets in ind_3d_ret.items():
    ind_3d_avg[key] = sum(rets) / len(rets)

print("Data loading complete. Running backtests...")

# ============================================================
# Step 4: Define and run combos
# ============================================================

def run_backtest(signals, name=""):
    """Calculate metrics for a list of (code, dt) signals."""
    rets_5d, rets_10d, rets_20d = [], [], []
    for code, dt in signals:
        pos = idx_map.get((code, dt))
        if pos is None:
            continue
        bars = stock_data.get(code, [])
        if pos + 5 < len(bars):
            rets_5d.append(bars[pos + 5][1] / bars[pos][1] - 1)
        if pos + 10 < len(bars):
            rets_10d.append(bars[pos + 10][1] / bars[pos][1] - 1)
        if pos + 20 < len(bars):
            rets_20d.append(bars[pos + 20][1] / bars[pos][1] - 1)

    def stats(rets):
        if not rets:
            return [0, 0, 0, 0, 0]
        n = len(rets)
        m = sum(rets) / n * 100
        w = sum(1 for r in rets if r > 0) / n * 100
        s = calc_sharpe(rets)
        p10 = calc_p10(rets)
        return [m, w, s, n, p10]

    r5 = stats(rets_5d)
    r10 = stats(rets_10d)
    r20 = stats(rets_20d)
    passed = r5[0] >= 3.0 and r5[1] >= 52.0 and len(signals) >= 200

    return {
        "name": name,
        "signals": len(signals),
        "win_rate_5d": round(r5[1], 2),
        "ret_5d": round(r5[0], 2),
        "sharpe_5d": round(r5[2], 3),
        "p10_5d": round(r5[4], 2),
        "ret_10d": round(r10[0], 2),
        "win_rate_10d": round(r10[1], 2),
        "ret_20d": round(r20[0], 2),
        "win_rate_20d": round(r20[1], 2),
        "pass_5d": passed,
    }

all_results = []
TOTAL_STOCKS = len(stock_data)

# ─── C1: 行业相对强度（个股跑赢行业 + 底部放量） ───
# 逻辑：行业内部相对强势股，在底部位置放量启动
print("\n" + "=" * 60)
print("C1: 行业相对强度+底部放量")
c1_signals = []
for code, bars in stock_data.items():
    ind = stock_industry.get(code, "")
    if not ind:
        continue
    for i in range(60, len(bars)):
        dt, close, pct, high, low, vr, tr, pe, pb, cm = bars[i]
        # 底20% (20日)
        low_20 = min(b[3] for b in bars[max(0, i - 19):i + 1])
        high_20 = max(b[2] for b in bars[max(0, i - 19):i + 1])
        if high_20 == low_20:
            continue
        pos_ratio = (close - low_20) / (high_20 - low_20)
        if pos_ratio > 0.20:
            continue
        # 放量
        if vr < 1.3:
            continue
        # 振幅≥5%
        amp = (high - low) / low if low > 0 else 0
        if amp < 0.05:
            continue
        # 跑赢行业（个股当日pct > 行业avg）
        if dt in day_ind_rets:
            ind_avg = None
            for ii, cc, cnt in day_ind_rets[dt]:
                if ii == ind:
                    ind_avg = cc
                    break
            if ind_avg is not None and pct > ind_avg:
                c1_signals.append((code, dt))

h = combo_hash({"type": "C1", "close_position": "底20%", "vr": ">=1.3", "amp": ">=5%", "relative_strength": "跑赢行业"})
print(f"  C1 signals: {len(c1_signals)}")
r = run_backtest(c1_signals, f"C1_行业相对强度+底部放量(hash={h})")
all_results.append(r)
print(f"  N={r['signals']} WR={r['win_rate_5d']}% R5={r['ret_5d']}% Sharpe={r['sharpe_5d']} {'✅' if r['pass_5d'] else '❌'}")

# ─── C2: 行业资金分歧（行业资金净流出但close不跌 = 主力承接） ───
# 使用 moneyflow_ind_dc 查行业资金流
print("\n" + "=" * 60)
print("C2: 行业资金分歧+恐慌深底")
# Load moneyflow_ind_dc (content_type='行业资金流')
mf_sql = f"""
SELECT trade_date, ts_code, name, pct_change, net_amount, net_amount_rate,
       buy_elg_amount, buy_lg_amount
FROM tushare.tushare_moneyflow_ind_dc FINAL
WHERE content_type = '行业资金流'
  AND trade_date >= '20200101' AND trade_date <= '{END_DATE}'
"""
mf_rows = ch_query(mf_sql)
print(f"  moneyflow_ind_dc rows: {len(mf_rows)}")

# Build industry net_flow by date
# Map ts_code in moneyflow_ind_dc to industry names
ind_flow_by_date = defaultdict(dict)  # dt -> {industry_name: net_amount_rate}
for r in mf_rows:
    dt = str(r["trade_date"]).replace("-", "")
    name = r.get("name", "")
    rate = r.get("net_amount_rate", 0) or 0
    if name:
        ind_flow_by_date[dt][name] = rate

c2_signals = []
for code, bars in stock_data.items():
    ind = stock_industry.get(code, "")
    if not ind:
        continue
    for i in range(60, len(bars)):
        dt, close, pct, high, low, vr, tr, pe, pb, cm = bars[i]
        # 恐慌
        if pct > -5:
            continue
        # 底20%
        low_20 = min(b[3] for b in bars[max(0, i - 19):i + 1])
        high_20 = max(b[2] for b in bars[max(0, i - 19):i + 1])
        if high_20 == low_20:
            continue
        pos_ratio = (close - low_20) / (high_20 - low_20)
        if pos_ratio > 0.20:
            continue
        # 振幅≥6%
        amp = (high - low) / low if low > 0 else 0
        if amp < 0.06:
            continue
        # 行业资金分歧：行业net_amount_rate < -2%（净流出）但个股在底部
        flow = ind_flow_by_date.get(dt, {}).get(ind, None)
        if flow is not None and flow < -2:
            c2_signals.append((code, dt))

h = combo_hash({"type": "C2", "pct": "<=-5", "close_pos": "底20%", "amp": ">=6%", "ind_flow": "<-2%"})
print(f"  C2 signals: {len(c2_signals)}")
r = run_backtest(c2_signals, f"C2_行业资金分歧+恐慌深底(hash={h})")
all_results.append(r)
print(f"  N={r['signals']} WR={r['win_rate_5d']}% R5={r['ret_5d']}% Sharpe={r['sharpe_5d']} {'✅' if r['pass_5d'] else '❌'}")

# ─── C3: 板块量价背离（行业量增价跌=洗盘 + 个股深底） ───
# 行业当日下跌但成交额放大（洗盘特征）+ 个股深底反转
print("\n" + "=" * 60)
print("C3: 板块量价背离+深底反转")
# Compute industry avg volume ratio (using daily_basic circ_mv as proxy)
# Industry volume expansion + price decline
ind_vol_price = {}  # (dt, ind) -> (avg_pct, count_down, count_up)
for dt, inds in day_ind_rets.items():
    for ind, avg_r, cnt in inds:
        if avg_r < -1:  # 行业下跌
            ind_vol_price[(dt, ind)] = avg_r

c3_signals = []
for code, bars in stock_data.items():
    ind = stock_industry.get(code, "")
    if not ind:
        continue
    for i in range(60, len(bars)):
        dt, close, pct, high, low, vr, tr, pe, pb, cm = bars[i]
        # 板块量价背离：行业下跌
        if (dt, ind) not in ind_vol_price:
            continue
        # 个股深底15%
        low_20 = min(b[3] for b in bars[max(0, i - 19):i + 1])
        high_20 = max(b[2] for b in bars[max(0, i - 19):i + 1])
        if high_20 == low_20:
            continue
        pos_ratio = (close - low_20) / (high_20 - low_20)
        if pos_ratio > 0.15:
            continue
        # 放量VR≥1.5
        if vr < 1.5:
            continue
        # 振幅≥6%
        amp = (high - low) / low if low > 0 else 0
        if amp < 0.06:
            continue
        # 微盘
        if cm > 300000:  # circ_mv in 万元, 30亿=300000万
            continue
        c3_signals.append((code, dt))

h = combo_hash({"type": "C3", "ind_pct": "<-1", "close_pos": "底15%", "vr": ">=1.5", "amp": ">=6%", "cm": "<=30亿"})
print(f"  C3 signals: {len(c3_signals)}")
r = run_backtest(c3_signals, f"C3_板块量价背离+深底微盘(hash={h})")
all_results.append(r)
print(f"  N={r['signals']} WR={r['win_rate_5d']}% R5={r['ret_5d']}% Sharpe={r['sharpe_5d']} {'✅' if r['pass_5d'] else '❌'}")

# ─── C4: 行业动量加速（行业3D涨幅加速 + 个股底部启动） ───
# 行业3D收益>0且加速上行（3D>前3D）+ 个股底部放量启动
print("\n" + "=" * 60)
print("C4: 行业动量加速+底部启动")
c4_signals = []
for code, bars in stock_data.items():
    ind = stock_industry.get(code, "")
    if not ind:
        continue
    for i in range(60, len(bars)):
        dt, close, pct, high, low, vr, tr, pe, pb, cm = bars[i]
        # 行业3D动量加速
        key = (dt, ind)
        ret3d = ind_3d_avg.get(key, None)
        if ret3d is None or ret3d < 0:
            continue
        # Check acceleration: 3D ret > prior 3D ret
        # Need date 3 days ago
        di = date_idx.get(dt, -1)
        if di < 6:
            continue
        dt_prior = all_dates[di - 3]
        key_prior = (dt_prior, ind)
        ret3d_prior = ind_3d_avg.get(key_prior, None)
        if ret3d_prior is None or ret3d <= ret3d_prior:
            continue
        # 个股底部40%
        low_20 = min(b[3] for b in bars[max(0, i - 19):i + 1])
        high_20 = max(b[2] for b in bars[max(0, i - 19):i + 1])
        if high_20 == low_20:
            continue
        pos_ratio = (close - low_20) / (high_20 - low_20)
        if pos_ratio > 0.40:
            continue
        # 涨幅≥2%（方向确认）
        if pct < 2:
            continue
        # 振幅≥5%
        amp = (high - low) / low if low > 0 else 0
        if amp < 0.05:
            continue
        # VR≥1.0
        if vr < 1.0:
            continue
        c4_signals.append((code, dt))

h = combo_hash({"type": "C4", "ind_3d": "加速>0", "close_pos": "底40%", "pct": ">=2", "amp": ">=5%", "vr": ">=1.0"})
print(f"  C4 signals: {len(c4_signals)}")
r = run_backtest(c4_signals, f"C4_行业动量加速+底部启动(hash={h})")
all_results.append(r)
print(f"  N={r['signals']} WR={r['win_rate_5d']}% R5={r['ret_5d']}% Sharpe={r['sharpe_5d']} {'✅' if r['pass_5d'] else '❌'}")

# ─── C5: 行业恐慌后修复（行业连跌2日后企稳 + 个股深底放量） ───
# 行业连续2日下跌后第3日企稳 + 个股深底+放量
print("\n" + "=" * 60)
print("C5: 行业恐慌后修复+深底放量")
# Pre-compute: industry 2 consecutive down days then stabilize
ind_2d_down_then_stable = set()  # (dt, ind)
for ind in ind_stocks:
    for di in range(5, len(all_dates)):
        dt = all_dates[di]
        dt_1 = all_dates[di - 1]
        dt_2 = all_dates[di - 2]
        r0 = None
        r1 = None
        r2 = None
        for ii, cc, cnt in day_ind_rets.get(dt, []):
            if ii == ind:
                r0 = cc
                break
        for ii, cc, cnt in day_ind_rets.get(dt_1, []):
            if ii == ind:
                r1 = cc
                break
        for ii, cc, cnt in day_ind_rets.get(dt_2, []):
            if ii == ind:
                r2 = cc
                break
        if r1 is not None and r2 is not None and r0 is not None:
            if r1 < -1 and r2 < -1 and r0 > -0.5:
                ind_2d_down_then_stable.add((dt, ind))

c5_signals = []
for code, bars in stock_data.items():
    ind = stock_industry.get(code, "")
    if not ind:
        continue
    for i in range(60, len(bars)):
        dt, close, pct, high, low, vr, tr, pe, pb, cm = bars[i]
        # 行业恐慌后修复
        if (dt, ind) not in ind_2d_down_then_stable:
            continue
        # 个股深底20%
        low_20 = min(b[3] for b in bars[max(0, i - 19):i + 1])
        high_20 = max(b[2] for b in bars[max(0, i - 19):i + 1])
        if high_20 == low_20:
            continue
        pos_ratio = (close - low_20) / (high_20 - low_20)
        if pos_ratio > 0.20:
            continue
        # 放量VR≥1.3
        if vr < 1.3:
            continue
        # 振幅≥5%
        amp = (high - low) / low if low > 0 else 0
        if amp < 0.05:
            continue
        # 中小盘
        if cm > 500000:
            continue
        c5_signals.append((code, dt))

h = combo_hash({"type": "C5", "ind_pattern": "连跌2日+企稳", "close_pos": "底20%", "vr": ">=1.3", "amp": ">=5%", "cm": "<=50亿"})
print(f"  C5 signals: {len(c5_signals)}")
r = run_backtest(c5_signals, f"C5_行业恐慌后修复+深底放量(hash={h})")
all_results.append(r)
print(f"  N={r['signals']} WR={r['win_rate_5d']}% R5={r['ret_5d']}% Sharpe={r['sharpe_5d']} {'✅' if r['pass_5d'] else '❌'}")

# ============================================================
# Summary
# ============================================================
print(f"\n{'=' * 80}")
print(f"{'COMBO':<45} {'N':>7} {'WR_5d':>7} {'R_5d':>7} {'P10':>7} {'R_10d':>7} {'R_20d':>7} {'Sharpe':>8} {'PASS':>5}")
print("-" * 100)
for r in all_results:
    ps = "✅" if r["pass_5d"] else "❌"
    print(f"{r['name'][:44]:<45} {r['signals']:>7} {r['win_rate_5d']:>6.1f}% {r['ret_5d']:>6.2f}% {r['p10_5d']:>6.2f}% {r['ret_10d']:>6.2f}% {r['ret_20d']:>6.2f}% {r['sharpe_5d']:>8.3f}  {ps:>3}")

# Write report
output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_13/analysis_T6_板块轮动.md"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

passed = [r for r in all_results if r["pass_5d"]]
best = max(all_results, key=lambda r: r["ret_5d"]) if all_results else None
best_wr = max(all_results, key=lambda r: r["win_rate_5d"]) if all_results else None

with open(output_path, "w") as f:
    f.write(f"# T6 板块轮动 — Iter 13 分析报告\n\n")
    f.write(f"- 基准交易日: 2026-05-11\n")
    f.write(f"- 回测区间: 2020-01-01 ~ 2026-05-11\n")
    f.write(f"- 数据源: ClickHouse 直连 (ch_query.py)\n")
    f.write(f"- 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"- 疲劳计数: 6（连续6轮未破全局R5=25.76%纪录）\n\n")

    f.write(f"## 新维度设计思路\n\n")
    f.write(f"避免历史重复（iter11 C4板块恐慌+筹码锁定已验证，iter10 C2行业尾部+个股恐慌已验证），\n")
    f.write(f"本轮探索5个新维度：\n\n")
    f.write(f"1. **C1 行业相对强度**: 个股跑赢行业均值 + 底部放量（板块内相对强势）\n")
    f.write(f"2. **C2 行业资金分歧**: 行业资金净流出(<-2%) + 个股恐慌深底（主力承接场景）\n")
    f.write(f"3. **C3 板块量价背离**: 行业下跌但量增（洗盘特征）+ 个股深底微盘放量\n")
    f.write(f"4. **C4 行业动量加速**: 行业3D收益加速上行 + 个股底部启动（趋势跟随型）\n")
    f.write(f"5. **C5 行业恐慌后修复**: 行业连跌2日后企稳 + 个股深底放量（均值回归型）\n\n")

    f.write(f"## 回测结果汇总\n\n")
    f.write(f"| # | 组合 | N | WR_5d | R_5d | P10 | R_10d | R_20d | Sharpe | 达标 |\n")
    f.write(f"|---|------|---|-------|------|-----|-------|-------|--------|------|\n")
    for i, r in enumerate(all_results, 1):
        ps = "✅" if r["pass_5d"] else "❌"
        f.write(f"| {i} | {r['name']} | {r['signals']} | {r['win_rate_5d']:.1f}% | {r['ret_5d']:.2f}% | {r['p10_5d']:.2f}% | {r['ret_10d']:.2f}% | {r['ret_20d']:.2f}% | {r['sharpe_5d']:.3f} | {ps} |\n")

    f.write(f"\n## 详细分析\n\n")
    for i, r in enumerate(all_results, 1):
        f.write(f"### {i}. {r['name']}\n\n")
        f.write(f"- **信号数**: {r['signals']}\n")
        f.write(f"- **WR_5d**: {r['win_rate_5d']}%\n")
        f.write(f"- **R_5d**: {r['ret_5d']}%\n")
        f.write(f"- **P10_5d**: {r['p10_5d']}%\n")
        f.write(f"- **R_10d**: {r['ret_10d']}%\n")
        f.write(f"- **R_20d**: {r['ret_20d']}%\n")
        f.write(f"- **Sharpe_5d**: {r['sharpe_5d']}\n")
        f.write(f"- **达标**: {'✅' if r['pass_5d'] else '❌'}\n\n")

    f.write(f"## 结论\n\n")
    if passed:
        f.write(f"✅ **{len(passed)}/{len(all_results)} 达标**\n\n")
        for p in passed:
            f.write(f"- **{p['name']}**: WR={p['win_rate_5d']}%, R5={p['ret_5d']}%, N={p['signals']}, Sharpe={p['sharpe_5d']}\n")
    else:
        f.write(f"❌ **全部未达标**\n\n")
        if best:
            f.write(f"最佳(R5): **{best['name']}** — R5={best['ret_5d']}%, WR={best['win_rate_5d']}%, N={best['signals']}\n")
        if best_wr:
            f.write(f"最佳(WR): **{best_wr['name']}** — WR={best_wr['win_rate_5d']}%, R5={best_wr['ret_5d']}%, N={best_wr['signals']}\n")

    f.write(f"\n---\n*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

print(f"\n✅ Report: {output_path}")
print(f"\nPassed: {len(passed)}/{len(all_results)}")
if passed:
    for p in passed:
        print(f"  ✅ {p['name']}: WR={p['win_rate_5d']}% R5={p['ret_5d']}% N={p['signals']}")
