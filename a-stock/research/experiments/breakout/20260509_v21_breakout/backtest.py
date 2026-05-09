#!/usr/bin/env python3
"""
V21: 主升浪潜伏与起爆点 — 进阶测试
=====================================
在 v20 基础上新增:
1. 黄金坑/洗盘信号 (突破前5-15日内是否有急跌洗盘)
2. 止损回测 (-8%硬止损)
3. 市场环境过滤组合分析 (牛市/熊市 + 洗盘/无洗盘)
4. 深度黄金坑测试

数据源: Tushare ClickHouse
"""

import requests
import pandas as pd
import numpy as np
from io import StringIO
import json

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')


def ch_query(query, fmt='TabSeparatedWithNames', timeout=300):
    q = query.strip().rstrip(';') + f' FORMAT {fmt}'
    r = requests.get(CH_URL, params={'query': q}, auth=CH_AUTH, timeout=timeout)
    if r.status_code != 200:
        raise Exception(f"CH Error {r.status_code}: {r.text[:500]}")
    text = r.text
    if not text.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(text), sep='\t', low_memory=False)


print("=" * 60)
print("V21: 主升浪潜伏与起爆点 — 进阶测试")
print("=" * 60)

# ============================================================
# 第一步: ClickHouse 计算因子 + 新增洗盘信号
# ============================================================
print("\n[1/7] ClickHouse 计算因子 (含洗盘/黄金坑信号)...")

signal_sql = """
WITH 
stock_base AS (
    SELECT 
        ts_code,
        trade_date,
        close,
        high,
        low,
        vol,
        pct_chg,
        count() OVER (PARTITION BY ts_code) as total_days
    FROM tushare.tushare_stock_daily FINAL
),
stock_with_ma AS (
    SELECT *,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as ma5,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma10,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ma20,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as ma60,
        avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as vol_ma20
    FROM stock_base
    WHERE total_days >= 60
),
stock_with_tr AS (
    SELECT *,
        greatest(high - low, abs(high - lagInFrame(close, 1) OVER w), abs(low - lagInFrame(close, 1) OVER w)) as tr
    FROM stock_with_ma
    WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
),
stock_with_atr AS (
    SELECT *,
        avg(tr) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as atr14
    FROM stock_with_tr
),
stock_with_cv AS (
    SELECT *,
        (ma5 + ma10 + ma20 + ma60) / 4.0 as ma_mean,
        sqrt(
            (power(ma5 - (ma5+ma10+ma20+ma60)/4.0, 2) +
             power(ma10 - (ma5+ma10+ma20+ma60)/4.0, 2) +
             power(ma20 - (ma5+ma10+ma20+ma60)/4.0, 2) +
             power(ma60 - (ma5+ma10+ma20+ma60)/4.0, 2)) / 4.0
        ) as ma_std
    FROM stock_with_atr
),
stock_cv_ratio AS (
    SELECT *,
        if(ma_mean > 0, ma_std / ma_mean, NULL) as ma_cv
    FROM stock_with_cv
    WHERE ma_std IS NOT NULL AND isFinite(ma_std)
),
stock_cv10 AS (
    SELECT *,
        avg(ma_cv) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma_cv_10d
    FROM stock_cv_ratio
    WHERE ma_cv IS NOT NULL AND isFinite(ma_cv)
),
-- 黄金坑/洗盘信号
stock_washout AS (
    SELECT *,
        -- 过去15日内最大单日跌幅
        min(pct_chg) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 14 PRECEDING AND CURRENT ROW) as min_pct_15d,
        -- 过去15日内最低价
        min(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 14 PRECEDING AND CURRENT ROW) as low_15d,
        -- 过去10日内最大单日跌幅
        min(pct_chg) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as min_pct_10d,
        -- 过去5日内最低价
        min(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as low_5d
    FROM stock_cv10
),
stock_with_basic AS (
    SELECT 
        s.ts_code,
        s.trade_date,
        s.close,
        s.high,
        s.low,
        s.vol,
        s.pct_chg,
        s.ma5, s.ma10, s.ma20, s.ma60,
        s.vol_ma20,
        s.atr14,
        s.ma_cv_10d,
        if(s.vol_ma20 > 0, s.vol / s.vol_ma20, 0) as vol_ratio,
        if(s.close > 0, s.atr14 / s.close, 0) as atr_pct,
        b.pe_ttm,
        b.total_mv,
        -- 洗盘信号
        s.min_pct_15d,
        s.min_pct_10d,
        s.low_15d,
        s.low_5d,
        -- 洗盘标记: 过去15日内有单日跌幅<-4%
        if(s.min_pct_15d < -4, 1, 0) as wash_out_15d,
        -- 深度洗盘: 过去15日内有单日跌幅<-6%
        if(s.min_pct_15d < -6, 1, 0) as deep_wash_15d,
        -- 黄金坑深度: 15日最低价相对当前价的跌幅
        if(s.close > 0, (s.low_15d - s.close) / s.close, 0) as pit_depth
    FROM stock_washout s
    LEFT JOIN tushare.tushare_daily_basic b FINAL 
        ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
)
-- 基础信号筛选
SELECT 
    ts_code,
    trade_date,
    round(close, 2) as close,
    round(high, 2) as high,
    round(low, 2) as low,
    round(vol_ratio, 2) as vol_ratio,
    round(pct_chg, 2) as pct_chg,
    round(ma_cv_10d, 5) as ma_cv_10d,
    round(atr_pct, 5) as atr_pct,
    round(pe_ttm, 2) as pe_ttm,
    round(total_mv / 1e8, 2) as total_mv_yi,
    min_pct_15d,
    min_pct_10d,
    wash_out_15d,
    deep_wash_15d,
    round(pit_depth, 4) as pit_depth
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
df_signals = ch_query(signal_sql, timeout=300)
print(f"  信号候选数: {len(df_signals):,}")

if len(df_signals) == 0:
    print("  条件过严, 放宽到 ma_cv<0.03, atr<0.035...")
    loose = signal_sql.replace("ma_cv_10d < 0.02", "ma_cv_10d < 0.03").replace("atr_pct < 0.025", "atr_pct < 0.035")
    df_signals = ch_query(loose, timeout=300)
    print(f"  放宽后信号数: {len(df_signals):,}")

if len(df_signals) == 0:
    print("  无任何信号, 回测终止。")
    exit(0)

# ============================================================
# 第二步: 加载日线数据计算前向收益 + 止损
# ============================================================
print("\n[2/7] 加载日线数据计算前向收益...")

sig_dates = pd.to_datetime(df_signals['trade_date'])
min_date = sig_dates.min().strftime('%Y%m%d')
max_date = sig_dates.max().strftime('%Y%m%d')
sig_codes = df_signals['ts_code'].unique()

# 分批查询避免 IN 子句过长
batch_size = 500
all_daily = []
for i in range(0, len(sig_codes), batch_size):
    batch_codes = sig_codes[i:i+batch_size]
    code_list = "', '".join(batch_codes)
    daily_sql = f"""
    SELECT ts_code, trade_date, close, high, low, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE ts_code IN ('{code_list}')
      AND trade_date >= '{min_date}'
      AND trade_date <= '{max_date}'
    ORDER BY ts_code, trade_date
    """
    batch_df = ch_query(daily_sql, timeout=180)
    all_daily.append(batch_df)
    print(f"  批次 {i//batch_size + 1}: {len(batch_df):,} 条")

df_daily = pd.concat(all_daily, ignore_index=True)
df_daily['trade_date'] = pd.to_datetime(df_daily['trade_date'])
df_daily['close'] = pd.to_numeric(df_daily['close'], errors='coerce')
df_daily['high'] = pd.to_numeric(df_daily['high'], errors='coerce')
df_daily['low'] = pd.to_numeric(df_daily['low'], errors='coerce')
df_daily['pct_chg'] = pd.to_numeric(df_daily['pct_chg'], errors='coerce')
print(f"  总计 {len(df_daily):,} 条")

# 计算前向收益 (固定持有期)
for period in [5, 10, 20]:
    df_daily[f'fwd_ret_{period}d'] = df_daily.groupby('ts_code')['close'].shift(-period) / df_daily['close'] - 1

# 计算持有期内最低价 (用于止损模拟)
for period in [5, 10, 20]:
    df_daily[f'fwd_{period}d_low'] = (
        df_daily.groupby('ts_code')['low']
        .transform(lambda x: x.shift(-1).rolling(period).min())
    )

# ============================================================
# 第三步: 合并信号与前向收益
# ============================================================
print("\n[3/7] 合并信号与前向收益...")

df_signals['trade_date'] = pd.to_datetime(df_signals['trade_date'])
for col in ['close', 'vol_ratio', 'pct_chg', 'ma_cv_10d', 'atr_pct', 'pe_ttm', 'total_mv_yi']:
    df_signals[col] = pd.to_numeric(df_signals[col], errors='coerce')

df_signals['wash_out_15d'] = pd.to_numeric(df_signals['wash_out_15d'], errors='coerce').fillna(0).astype(int)
df_signals['deep_wash_15d'] = pd.to_numeric(df_signals['deep_wash_15d'], errors='coerce').fillna(0).astype(int)
df_signals['min_pct_15d'] = pd.to_numeric(df_signals['min_pct_15d'], errors='coerce')
df_signals['min_pct_10d'] = pd.to_numeric(df_signals['min_pct_10d'], errors='coerce')
df_signals['pit_depth'] = pd.to_numeric(df_signals['pit_depth'], errors='coerce')

for period in [5, 10, 20]:
    df_signals = df_signals.merge(
        df_daily[['ts_code', 'trade_date', f'fwd_ret_{period}d', f'fwd_{period}d_low']],
        on=['ts_code', 'trade_date'],
        how='left'
    )

print(f"  合并后: {len(df_signals):,} 个信号")

# ============================================================
# 第四步: 加载沪深300指数计算超额收益
# ============================================================
print("\n[4/7] 加载沪深300指数计算超额收益...")

index_sql = """
SELECT trade_date, close
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000300.SH'
ORDER BY trade_date
"""
idx_df = ch_query(index_sql)
idx_df['trade_date'] = pd.to_datetime(idx_df['trade_date'])
idx_df['close'] = pd.to_numeric(idx_df['close'], errors='coerce')
idx_df['ma60'] = idx_df['close'].rolling(60).mean()
idx_df['bull_market'] = (idx_df['close'] > idx_df['ma60']).astype(int)
print(f"  指数数据: {len(idx_df)} 条")

# 映射日期到指数收益
idx_dict = dict(zip(idx_df['trade_date'], idx_df['close']))
idx_bull = dict(zip(idx_df['trade_date'], idx_df['bull_market']))
idx_dates_sorted = idx_df['trade_date'].values
idx_prices = idx_df['close'].values

from datetime import timedelta

def get_idx_return(sig_date_str, holding_days):
    """计算信号日后N个交易日的指数收益率"""
    sig_dt = pd.to_datetime(sig_date_str)
    # 找到在排序数组中的位置
    pos = np.searchsorted(idx_dates_sorted, sig_dt)
    if pos >= len(idx_dates_sorted) or idx_dates_sorted[pos] != sig_dt:
        return np.nan
    end_pos = pos + holding_days
    if end_pos >= len(idx_dates_sorted):
        return np.nan
    entry_price = idx_prices[pos]
    exit_price = idx_prices[end_pos]
    return (exit_price - entry_price) / entry_price

# ============================================================
# 第五步: 计算止损收益
# ============================================================
print("\n[5/7] 计算止损收益...")

# 对于每个信号, 检查持有期内最低价是否触及-8%止损
for period in [5, 10, 20]:
    low_col = f'fwd_{period}d_low'
    ret_col = f'fwd_ret_{period}d'

    # 止损价 = 入场价 * 0.92
    df_signals[f'stop_triggered_{period}d'] = (
        df_signals[low_col] <= df_signals['close'] * 0.92
    )

    # 如果触发止损, 假设在止损价卖出 (用最低价近似)
    # 更精确: 止损收益 = max(-8%, 实际最低价对应的收益)
    df_signals[f'ret_stop_{period}d'] = np.where(
        df_signals[f'stop_triggered_{period}d'],
        (df_signals[low_col] / df_signals['close'] - 1).clip(lower=-0.08),  # 止损最多亏8%
        df_signals[ret_col]
    )

# ============================================================
# 第六步: 计算超额收益 + 市场环境分组
# ============================================================
print("\n[6/7] 计算超额收益...")

# 添加市场环境
df_signals['sig_date_only'] = df_signals['trade_date'].dt.strftime('%Y%m%d').astype(str)
df_signals['bull_market'] = df_signals['sig_date_only'].map(
    lambda x: idx_bull.get(pd.to_datetime(x), 0) if pd.notna(x) else 0
)

# 计算超额收益
for period in [5, 10, 20]:
    ret_col = f'fwd_ret_{period}d'
    df_signals[f'idx_ret_{period}d'] = df_signals['trade_date'].apply(
        lambda x: get_idx_return(x, period)
    )
    df_signals[f'excess_{period}d'] = df_signals[ret_col] - df_signals[f'idx_ret_{period}d']

print(f"  超额收益计算完成")

# ============================================================
# 第七步: 统计分析
# ============================================================
print("\n[7/7] 统计分析...")

# 定义变体
variants = {
    'v1_base': ('基础信号', pd.Series([True]*len(df_signals), index=df_signals.index)),
    'v2_washout': ('+ 洗盘过滤', df_signals['wash_out_15d'] == 1),
    'v3_no_washout': ('无洗盘纯突破', df_signals['wash_out_15d'] == 0),
    'v4_deep_pit': ('深度洗盘(>6%)', df_signals['deep_wash_15d'] == 1),
    'v5_bull_only': ('仅牛市', df_signals['bull_market'] == 1),
    'v6_bear_only': ('仅熊市', df_signals['bull_market'] == 0),
    'v7_gp_bull': ('洗盘 + 牛市', (df_signals['wash_out_15d'] == 1) & (df_signals['bull_market'] == 1)),
    'v8_nw_bull': ('无洗盘 + 牛市', (df_signals['wash_out_15d'] == 0) & (df_signals['bull_market'] == 1)),
}

# 年度分析
df_signals['year'] = df_signals['trade_date'].dt.year

print("\n" + "=" * 80)
print("📊 V21 回测结果")
print("=" * 80)

# 汇总表
print("\n--- 各变体 T+20日 对比 (固定持有) ---")
print(f"{'变体':<20} {'样本':>8} {'均收益':>8} {'中位':>8} {'胜率':>8} {'年化超额':>10} {'偏度':>7}")
print("-" * 80)

summary = {}
for vkey, (vname, mask) in variants.items():
    sub = df_signals[mask]
    if len(sub) < 30:
        continue

    ret = sub['fwd_ret_20d'].dropna()
    excess = sub['excess_20d'].dropna()
    if len(ret) < 10:
        continue

    annualized_excess = excess.mean() * (252 / 20)
    skew = ret.skew()

    row = {
        'variant': vkey,
        'name': vname,
        'count': len(sub),
        'avg_ret_5d': sub['fwd_ret_5d'].dropna().mean(),
        'avg_ret_10d': sub['fwd_ret_10d'].dropna().mean(),
        'avg_ret_20d': ret.mean(),
        'median_ret_20d': ret.median(),
        'win_rate_20d': (ret > 0).mean(),
        'excess_20d': excess.mean(),
        'annualized_excess': annualized_excess,
        'skew_20d': skew,
    }

    # 止损分析
    stopped = sub[sub[f'stop_triggered_20d'] == True]
    row['stop_rate'] = len(stopped) / len(sub)
    row['avg_ret_stop'] = sub['ret_stop_20d'].dropna().mean()

    # 牛市/熊市
    bull = sub[sub['bull_market'] == 1]
    bear = sub[sub['bull_market'] == 0]
    if len(bull) > 10:
        row['bull_avg_20d'] = bull['fwd_ret_20d'].dropna().mean()
        row['bull_wr_20d'] = (bull['fwd_ret_20d'] > 0).mean()
        row['bull_excess'] = bull['excess_20d'].dropna().mean()
    if len(bear) > 10:
        row['bear_avg_20d'] = bear['fwd_ret_20d'].dropna().mean()
        row['bear_wr_20d'] = (bear['fwd_ret_20d'] > 0).mean()
        row['bear_excess'] = bear['excess_20d'].dropna().mean()

    # 洗盘深度分桶
    row['pit_avg_20d'] = sub['fwd_ret_20d'].dropna().mean()

    summary[vkey] = row

    print(f"{vname:<20} {len(sub):>8,} "
          f"{ret.mean()*100:>7.2f}% "
          f"{ret.median()*100:>7.2f}% "
          f"{(ret > 0).mean()*100:>7.1f}% "
          f"{annualized_excess*100:>9.2f}% "
          f"{skew:>6.2f}")

# 止损对比
print("\n--- 止损分析 (T+20日, -8%硬止损) ---")
print(f"{'变体':<20} {'止损触发率':>10} {'止损后均收益':>12} {'vs无止损':>10}")
print("-" * 60)
for vkey, row in summary.items():
    vs_no_stop = row['avg_ret_stop'] - row['avg_ret_20d']
    print(f"{row['name']:<20} {row['stop_rate']*100:>9.1f}% "
          f"{row['avg_ret_stop']*100:>11.2f}% "
          f"{vs_no_stop*100:>+9.2f}%")

# 牛市 vs 熊市
print("\n--- 市场环境对比 (T+20日) ---")
print(f"{'变体':<20} {'牛市样本':>8} {'牛市均收益':>10} {'牛市胜率':>8} {'熊市样本':>8} {'熊市均收益':>10} {'熊市胜率':>8}")
print("-" * 90)
for vkey, row in summary.items():
    bull_n = row.get('bull_avg_20d', None)
    bear_n = row.get('bear_avg_20d', None)
    bull_cnt = int((df_signals[variants[vkey][1]]['bull_market'] == 1).sum()) if vkey in variants else 0
    bear_cnt = int((df_signals[variants[vkey][1]]['bull_market'] == 0).sum()) if vkey in variants else 0
    print(f"{row['name']:<20} "
          f"{bull_cnt:>8,} "
          f"{row.get('bull_avg_20d', 0)*100:>9.2f}% "
          f"{row.get('bull_wr_20d', 0)*100:>7.1f}% "
          f"{bear_cnt:>8,} "
          f"{row.get('bear_avg_20d', 0)*100:>9.2f}% "
          f"{row.get('bear_wr_20d', 0)*100:>7.1f}%")

# 年度分布
print("\n--- 分年度表现 (基础信号 T+20日) ---")
base_mask = variants['v1_base'][1]
for year in sorted(df_signals[base_mask]['year'].unique()):
    yr = df_signals[base_mask][df_signals[base_mask]['year'] == year]
    ret_yr = yr['fwd_ret_20d'].dropna()
    wash_yr = yr[yr['wash_out_15d'] == 1]
    nowash_yr = yr[yr['wash_out_15d'] == 0]
    wash_ret = wash_yr['fwd_ret_20d'].dropna().mean() if len(wash_yr) > 5 else 0
    nowash_ret = nowash_yr['fwd_ret_20d'].dropna().mean() if len(nowash_yr) > 5 else 0
    wash_wr = (wash_yr['fwd_ret_20d'] > 0).mean() * 100 if len(wash_yr) > 5 else 0
    nowash_wr = (nowash_yr['fwd_ret_20d'] > 0).mean() * 100 if len(nowash_yr) > 5 else 0
    print(f"  {year}: {len(yr):>5,} 信号, "
          f"均收益 {ret_yr.mean()*100:+.2f}%, "
          f"胜率 {(ret_yr>0).mean()*100:.1f}%, "
          f"洗盘{wash_ret*100:+.2f}%({wash_wr:.0f}%), "
          f"无洗盘{nowash_ret*100:+.2f}%({nowash_wr:.0f}%)")

# ============================================================
# 关键假设检验
# ============================================================
print("\n" + "=" * 60)
print("🔬 假设检验")
print("=" * 60)

# 假设1: 洗盘信号提升胜率
wash_ret = df_signals[df_signals['wash_out_15d']==1]['fwd_ret_20d'].dropna()
nowash_ret = df_signals[df_signals['wash_out_15d']==0]['fwd_ret_20d'].dropna()

if len(wash_ret) > 100 and len(nowash_ret) > 100:
    from scipy import stats
    t_stat, p_value = stats.ttest_ind(wash_ret, nowash_ret)
    wash_wr = (wash_ret > 0).mean()
    nowash_wr = (nowash_ret > 0).mean()
    print(f"\n假设1: 洗盘信号提升胜率")
    print(f"  洗盘组: {len(wash_ret)} 信号, 均收益 {wash_ret.mean()*100:+.2f}%, 胜率 {wash_wr*100:.1f}%")
    print(f"  无洗盘组: {len(nowash_ret)} 信号, 均收益 {nowash_ret.mean()*100:+.2f}%, 胜率 {nowash_wr*100:.1f}%")
    print(f"  差值: {(wash_ret.mean()-nowash_ret.mean())*100:+.2f}%, t={t_stat:.3f}, p={p_value:.4f}")
    print(f"  {'✅ 显著' if p_value < 0.05 else '❌ 不显著'} (p{'<' if p_value < 0.05 else '>='}0.05)")

# 假设2: 止损改善风险调整后收益
base = df_signals[base_mask]
stop_ret = base['ret_stop_20d'].dropna()
orig_ret = base['fwd_ret_20d'].dropna()
print(f"\n假设2: -8%止损改善尾部风险")
print(f"  无止损: 均值 {orig_ret.mean()*100:+.2f}%, 5分位 {orig_ret.quantile(0.05)*100:+.2f}%, 最大亏损 {orig_ret.min()*100:+.2f}%")
print(f"  有止损: 均值 {stop_ret.mean()*100:+.2f}%, 5分位 {stop_ret.quantile(0.05)*100:+.2f}%, 最大亏损 {stop_ret.min()*100:+.2f}%")

# 假设3: 牛市+洗盘 最佳组合
gp_bull = df_signals[(df_signals['wash_out_15d']==1) & (df_signals['bull_market']==1)]
nw_bull = df_signals[(df_signals['wash_out_15d']==0) & (df_signals['bull_market']==1)]
if len(gp_bull) > 100 and len(nw_bull) > 100:
    print(f"\n假设3: 牛市+洗盘 = 最佳组合")
    gp_ret = gp_bull['fwd_ret_20d'].dropna()
    nw_ret = nw_bull['fwd_ret_20d'].dropna()
    print(f"  牛市+洗盘: {len(gp_bull)} 信号, 均收益 {gp_ret.mean()*100:+.2f}%, 胜率 {(gp_ret>0).mean()*100:.1f}%")
    print(f"  牛市+无洗盘: {len(nw_bull)} 信号, 均收益 {nw_ret.mean()*100:+.2f}%, 胜率 {(nw_ret>0).mean()*100:.1f}%")
    t2, p2 = stats.ttest_ind(gp_ret, nw_ret)
    print(f"  差值: {(gp_ret.mean()-nw_ret.mean())*100:+.2f}%, p={p2:.4f}")
    print(f"  {'✅ 洗盘在牛市中更有价值' if p2 < 0.05 else '⚠️ 洗盘在牛市中差异不显著'}")

# ============================================================
# 保存结果
# ============================================================
print("\n✅ 保存结果...")

# 保存为 CSV
df_signals.to_csv('signals_v21.csv', index=False)

# 保存 JSON 摘要
json_summary = {}
for vkey, row in summary.items():
    json_summary[vkey] = {k: (round(v, 6) if isinstance(v, float) else v)
                          for k, v in row.items() if isinstance(v, (int, float, str))}

# 添加假设检验结果
json_summary['hypothesis_tests'] = {
    'washout_vs_nowashout': {
        'wash_count': len(wash_ret),
        'wash_avg': round(wash_ret.mean(), 6),
        'wash_wr': round((wash_ret > 0).mean(), 4),
        'nowash_count': len(nowash_ret),
        'nowash_avg': round(nowash_ret.mean(), 6),
        'nowash_wr': round((nowash_ret > 0).mean(), 4),
        'p_value': round(float(p_value), 6) if len(wash_ret) > 100 else None,
    },
    'stop_loss': {
        'no_stop_mean': round(orig_ret.mean(), 6),
        'no_stop_p5': round(orig_ret.quantile(0.05), 6),
        'no_stop_min': round(orig_ret.min(), 6),
        'stop_mean': round(stop_ret.mean(), 6),
        'stop_p5': round(stop_ret.quantile(0.05), 6),
        'stop_min': round(stop_ret.min(), 6),
    }
}

with open('summary_v21.json', 'w', encoding='utf-8') as f:
    json.dump(json_summary, f, ensure_ascii=False, indent=2, default=str)

print(f"  signals_v21.csv: {len(df_signals):,} 行")
print(f"  summary_v21.json: {len(summary)} 个变体")
print("\n✅ V21 回测完成!")
