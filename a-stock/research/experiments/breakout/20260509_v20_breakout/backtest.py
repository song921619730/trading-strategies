#!/usr/bin/env python3
"""
主升浪潜伏与起爆点 — 均线粘合 + ATR低位 + 放量突破 策略回测
Hypothesis: "均线粘合 + ATR 低位 + 放量突破" 组合在 20 日内跑赢指数 15% 以上

策略: 用 ClickHouse 计算因子筛选信号, 在 pandas 中计算前向收益。
"""

import requests
import pandas as pd
import numpy as np
from io import StringIO

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames'):
    q = query.strip().rstrip(';') + f' FORMAT {fmt}'
    r = requests.get(CH_URL, params={'query': q}, auth=CH_AUTH, timeout=300)
    if r.status_code != 200:
        raise Exception(f"CH Error {r.status_code}: {r.text[:500]}")
    text = r.text
    if not text.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(text), sep='\t', low_memory=False)

print("=" * 60)
print("主升浪潜伏与起爆点 — 策略回测")
print("=" * 60)

# ============================================================
# 第一步: ClickHouse 计算因子, 输出信号候选(不含前向收益)
# ============================================================
print("\n[1/6] ClickHouse 计算因子并筛选信号候选...")

# 关键: 用 neighbor() 替代 lead(), 输出更多上下文供 pandas 计算前向收益
signal_sql = """
WITH 
stock_with_ma AS (
    SELECT 
        ts_code,
        trade_date,
        close,
        high,
        low,
        vol,
        pct_chg,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as ma5,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma10,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ma20,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as ma60,
        avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as vol_ma20,
        high - low as tr,
        count() OVER (PARTITION BY ts_code) as total_days
    FROM tushare.tushare_stock_daily FINAL
),
stock_with_atr AS (
    SELECT *,
        avg(tr) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as atr14,
        (ma5 + ma10 + ma20 + ma60) / 4.0 as ma_mean_4,
        sqrt(
            (power(ma5 - (ma5+ma10+ma20+ma60)/4.0, 2) +
             power(ma10 - (ma5+ma10+ma20+ma60)/4.0, 2) +
             power(ma20 - (ma5+ma10+ma20+ma60)/4.0, 2) +
             power(ma60 - (ma5+ma10+ma20+ma60)/4.0, 2)) / 4.0
        ) as ma_std_4
    FROM stock_with_ma
    WHERE total_days >= 60
),
stock_with_cv AS (
    SELECT *,
        if(ma_mean_4 > 0, ma_std_4 / ma_mean_4, NULL) as ma_cv
    FROM stock_with_atr
),
stock_with_cv10 AS (
    SELECT *,
        avg(ma_cv) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma_cv_10d
    FROM stock_with_cv
    WHERE ma_cv IS NOT NULL AND isFinite(ma_cv)
),
stock_with_basic AS (
    SELECT 
        s.ts_code,
        s.trade_date,
        s.close,
        s.vol,
        s.pct_chg,
        s.ma5, s.ma10, s.ma20, s.ma60,
        s.vol_ma20,
        s.atr14,
        s.ma_cv_10d,
        if(s.vol_ma20 > 0, s.vol / s.vol_ma20, 0) as vol_ratio,
        if(s.close > 0, s.atr14 / s.close, 0) as atr_pct,
        b.pe_ttm,
        b.total_mv
    FROM stock_with_cv10 s
    LEFT JOIN tushare.tushare_daily_basic b FINAL 
        ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
)
-- 筛选: 只要满足因子条件的候选, 不限制前向收益
SELECT 
    ts_code,
    trade_date,
    round(close, 2) as close,
    round(vol_ratio, 2) as vol_ratio,
    round(pct_chg, 2) as pct_chg,
    round(ma_cv_10d, 5) as ma_cv_10d,
    round(atr_pct, 5) as atr_pct,
    round(pe_ttm, 2) as pe_ttm,
    round(total_mv / 1e8, 2) as total_mv_yi
FROM stock_with_basic
WHERE 
    pe_ttm > 0
    AND total_mv >= 300000
    AND ma_cv_10d < 0.02
    AND atr_pct < 0.025
    AND vol_ratio > 1.5
    AND pct_chg > 2
    AND close > ma60
ORDER BY trade_date, ts_code
"""

print("  执行查询 (可能需要60-120秒)...")
df_signals = ch_query(signal_sql)
print(f"  信号候选数: {len(df_signals):,}")

if len(df_signals) == 0:
    print("  条件过严, 尝试放宽到 ma_cv<0.03, atr<0.035...")
    loose = signal_sql.replace("ma_cv_10d < 0.02", "ma_cv_10d < 0.03").replace("atr_pct < 0.025", "atr_pct < 0.035")
    df_signals = ch_query(loose)
    print(f"  放宽后信号数: {len(df_signals):,}")

if len(df_signals) == 0:
    print("\n  ⚠️ 无任何信号, 回测终止。")
    exit(0)

# ============================================================
# 第二步: 加载全市场日线计算前向收益
# ============================================================
print("\n[2/6] 加载日线数据计算前向收益...")

# 只加载信号涉及的股票和日期范围
sig_dates = pd.to_datetime(df_signals['trade_date'])
min_date = sig_dates.min().strftime('%Y-%m-%d')
max_date = sig_dates.max().strftime('%Y-%m-%d')
sig_codes = df_signals['ts_code'].unique()
code_list = "', '".join(sig_codes)

daily_sql = f"""
SELECT ts_code, trade_date, close, high, low
FROM tushare.tushare_stock_daily FINAL
WHERE ts_code IN ('{code_list}')
  AND trade_date >= '{min_date}'
  AND trade_date <= '{max_date}'
ORDER BY ts_code, trade_date
"""
print(f"  查询范围: {min_date} ~ {max_date}, {len(sig_codes)} 只股票...")
df_daily = ch_query(daily_sql)
df_daily['trade_date'] = pd.to_datetime(df_daily['trade_date'])
df_daily['close'] = pd.to_numeric(df_daily['close'], errors='coerce')
df_daily['high'] = pd.to_numeric(df_daily['high'], errors='coerce')
df_daily['low'] = pd.to_numeric(df_daily['low'], errors='coerce')
print(f"  下载 {len(df_daily):,} 条")

# 计算前向收益
for period in [5, 10, 20]:
    df_daily[f'fwd_ret_{period}d'] = df_daily.groupby('ts_code')['close'].shift(-period) / df_daily['close'] - 1
    df_daily[f'fwd_{period}d_high'] = df_daily.groupby('ts_code')['high'].shift(-1).rolling(period).max().reset_index(0, drop=True)
    df_daily[f'fwd_{period}d_low'] = df_daily.groupby('ts_code')['low'].shift(-1).rolling(period).min().reset_index(0, drop=True)

# 将前向收益合并到信号
df_signals['trade_date'] = pd.to_datetime(df_signals['trade_date'])
for col in ['close', 'vol_ratio', 'pct_chg', 'ma_cv_10d', 'atr_pct', 'pe_ttm', 'total_mv_yi']:
    df_signals[col] = pd.to_numeric(df_signals[col], errors='coerce')

for period in [5, 10, 20]:
    df_signals = df_signals.merge(
        df_daily[['ts_code', 'trade_date', f'fwd_ret_{period}d', f'fwd_{period}d_high', f'fwd_{period}d_low']],
        on=['ts_code', 'trade_date'],
        how='left'
    )

# ============================================================
# 第三步: 统计信号收益
# ============================================================
print("\n[3/6] 信号收益统计...")

for period in [5, 10, 20]:
    col = f'fwd_ret_{period}d'
    ret = df_signals[col].dropna()
    if len(ret) > 0:
        print(f"\n  T+{period}日:")
        print(f"    样本数: {len(ret):,}")
        print(f"    平均收益: {ret.mean()*100:.3f}%")
        print(f"    中位收益: {ret.median()*100:.3f}%")
        print(f"    胜率: {(ret > 0).mean()*100:.1f}%")
        print(f"    最大收益: {ret.max()*100:.2f}%")
        print(f"    最大亏损: {ret.min()*100:.2f}%")
        pos_mean = ret[ret > 0].mean() if (ret > 0).any() else 0
        neg_mean = abs(ret[ret < 0].mean()) if (ret < 0).any() else 0.001
        print(f"    盈亏比: {pos_mean/neg_mean:.2f}")

# 分年度
df_signals['year'] = df_signals['trade_date'].dt.year
print(f"\n  {'='*55}")
print(f"  分年度统计 (T+20日)")
print(f"  {'='*55}")
for year in sorted(df_signals['year'].unique()):
    subset = df_signals[df_signals['year'] == year]
    ret = subset['fwd_ret_20d'].dropna()
    if len(ret) > 0:
        hi = subset['fwd_20d_high'].dropna().mean()
        lo = subset['fwd_20d_low'].dropna().mean()
        print(f"  {year}: n={len(ret):,}, 收益={ret.mean()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%, 期间最高={hi*100:.2f}%, 期间最低={lo*100:.2f}%")

# ============================================================
# 第四步: 沪深300 基准 + 超额
# ============================================================
print("\n[4/6] 沪深300基准 + 超额收益...")

idx_sql = """
SELECT trade_date, close,
    avg(close) OVER (ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as ma60
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000300.SH'
ORDER BY trade_date
"""
df_idx = ch_query(idx_sql)
df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])
df_idx['close'] = pd.to_numeric(df_idx['close'], errors='coerce')
df_idx['ma60'] = pd.to_numeric(df_idx['ma60'], errors='coerce')
df_idx = df_idx.set_index('trade_date')
print(f"  指数数据: {len(df_idx)} 天")

idx_dates_all = df_idx.index.tolist()
idx_close = df_idx['close'].to_dict()
idx_ma60 = df_idx['ma60'].to_dict()

def idx_fwd(date, fwd):
    future = [d for d in idx_dates_all if d >= date]
    if len(future) < fwd + 1:
        return np.nan
    end = future[min(fwd, len(future)-1)]
    s = idx_close.get(date, 0)
    e = idx_close.get(end, 0)
    return e/s - 1 if s > 0 else np.nan

for period in [5, 10, 20]:
    df_signals[f'idx_ret_{period}d'] = df_signals['trade_date'].apply(lambda d: idx_fwd(d, period))
    df_signals[f'alpha_{period}d'] = df_signals[f'fwd_ret_{period}d'] - df_signals[f'idx_ret_{period}d']

print(f"\n  超额收益统计 (vs 沪深300):")
for period in [5, 10, 20]:
    alpha = df_signals[f'alpha_{period}d'].dropna()
    if len(alpha) > 0:
        print(f"  T+{period}日平均超额: {alpha.mean()*100:.3f}% (中位: {alpha.median()*100:.3f}%)")

# 市场环境
df_signals['env'] = df_signals['trade_date'].map(
    lambda d: '牛市' if idx_close.get(d, 0) > idx_ma60.get(d, 0) and idx_ma60.get(d, 0) > 0 
              else ('熊市' if idx_ma60.get(d, 0) > 0 else '未知')
)

print(f"\n  {'='*55}")
print(f"  市场环境分组 (T+20日)")
print(f"  {'='*55}")
for env in ['牛市', '熊市', '未知']:
    sub = df_signals[df_signals['env'] == env]
    ret = sub['fwd_ret_20d'].dropna()
    alpha = sub['alpha_20d'].dropna()
    if len(ret) > 10:
        print(f"  {env}: n={len(ret):,}, 收益={ret.mean()*100:.2f}%, 超额={alpha.mean()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%")

# ============================================================
# 第五步: 参数敏感性
# ============================================================
print(f"\n  {'='*55}")
print(f"  参数敏感性 (ClickHouse端, T+20日)")
print(f"  {'='*55}")

param_tests = [
    ("ma_cv<0.010, atr<0.015", 0.010, 0.015),
    ("ma_cv<0.015, atr<0.020", 0.015, 0.020),
    ("ma_cv<0.020, atr<0.025 (基准)", 0.020, 0.025),
    ("ma_cv<0.025, atr<0.030", 0.025, 0.030),
    ("ma_cv<0.030, atr<0.035", 0.030, 0.035),
]

base_cte = """
WITH 
stock_with_ma AS (
    SELECT ts_code, trade_date, close, high, low, vol, pct_chg,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as ma5,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma10,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ma20,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as ma60,
        avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as vol_ma20,
        high - low as tr,
        count() OVER (PARTITION BY ts_code) as total_days
    FROM tushare.tushare_stock_daily FINAL
),
stock_with_atr AS (
    SELECT *,
        avg(tr) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as atr14,
        (ma5+ma10+ma20+ma60)/4.0 as ma_mean_4,
        sqrt((power(ma5-(ma5+ma10+ma20+ma60)/4.0,2)+power(ma10-(ma5+ma10+ma20+ma60)/4.0,2)+power(ma20-(ma5+ma10+ma20+ma60)/4.0,2)+power(ma60-(ma5+ma10+ma20+ma60)/4.0,2))/4.0) as ma_std_4
    FROM stock_with_ma WHERE total_days >= 60
),
stock_with_cv AS (
    SELECT *, if(ma_mean_4>0, ma_std_4/ma_mean_4, NULL) as ma_cv FROM stock_with_atr
),
stock_with_cv10 AS (
    SELECT *,
        avg(ma_cv) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma_cv_10d
    FROM stock_with_cv WHERE ma_cv IS NOT NULL AND isFinite(ma_cv)
),
stock_with_all AS (
    SELECT s.ts_code, s.trade_date, s.close, s.vol, s.pct_chg, s.vol_ma20, s.atr14, s.ma_cv_10d,
        if(s.vol_ma20>0, s.vol/s.vol_ma20, 0) as vol_ratio,
        if(s.close>0, s.atr14/s.close, 0) as atr_pct,
        b.pe_ttm, b.total_mv
    FROM stock_with_cv10 s
    LEFT JOIN tushare.tushare_daily_basic b FINAL ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
)
"""

for label, ma_t, atr_t in param_tests:
    sql = f"""{base_cte}
    SELECT 
        count() as n,
        avg(if(neighbor(close, 20) > 0 AND close > 0, neighbor(close, 20) / close - 1, NULL)) as avg_ret
    FROM stock_with_all
    WHERE pe_ttm > 0 AND total_mv >= 300000
        AND ma_cv_10d < {ma_t} AND atr_pct < {atr_t}
        AND vol_ratio > 1.5 AND pct_chg > 2 AND close > ma60
    """
    try:
        res = ch_query(sql)
        n = int(res['n'].iloc[0])
        ret = float(res['avg_ret'].iloc[0]) if not pd.isna(res['avg_ret'].iloc[0]) else 0
        print(f"  {label}: n={n:,}, 收益={ret*100:.2f}%")
    except Exception as e:
        print(f"  {label}: 跳过 ({str(e)[:80]})")

# ============================================================
# 保存
# ============================================================
df_signals.to_csv('signals_full.csv', index=False)
print(f"\n  信号数据已保存: signals_full.csv ({len(df_signals):,} 条)")
print("\n  回测完成！")
