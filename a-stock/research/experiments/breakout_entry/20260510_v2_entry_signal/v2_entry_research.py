"""
V2: 主升浪入场信号研究 - 均线粘合 + ATR低位 + 放量突破
ClickHouse获取原始数据 -> Python计算指标
"""
import requests
import pandas as pd
import numpy as np
import json
import time

CK_URL = 'http://172.24.224.1:8123/'
CK_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ck_query(sql, fmt='TabSeparatedWithNames'):
    r = requests.get(CK_URL, params={'query': sql + f' FORMAT {fmt}'}, auth=CK_AUTH, timeout=300)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    data = [line.split('\t') for line in lines[1:]]
    return pd.DataFrame(data, columns=cols)

RESULTS_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/主升浪潜伏与起爆点_(pre-main_uptrend_entry)/20260510_v2_entry_signal/'

print("=" * 70)
print("V2: 主升浪入场信号研究 — 均线粘合 + ATR低位 + 放量突破")
print("=" * 70)

# ============================================================
# Step 1: 获取全A股日线 + 基本面
# ============================================================
t0 = time.time()
print("\n[Step 1] 获取日线行情数据...")
sql1 = """
SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20190101'
ORDER BY ts_code, trade_date
"""
df_price = ck_query(sql1)
for c in ['open','high','low','close','vol','pct_chg']:
    df_price[c] = pd.to_numeric(df_price[c], errors='coerce')
df_price['trade_date'] = pd.to_datetime(df_price['trade_date'])
print(f"  行情数据: {len(df_price):,} 行, 耗时 {time.time()-t0:.1f}s")

t0 = time.time()
print("\n[Step 2] 获取基本面数据...")
sql2 = """
SELECT ts_code, trade_date, circ_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20190101'
ORDER BY ts_code, trade_date
"""
df_basic = ck_query(sql2)
df_basic['circ_mv'] = pd.to_numeric(df_basic['circ_mv'], errors='coerce')
df_basic['trade_date'] = pd.to_datetime(df_basic['trade_date'])
print(f"  基本面数据: {len(df_basic):,} 行, 耗时 {time.time()-t0:.1f}s")

# 合并
t0 = time.time()
print("\n[Step 3] 合并数据...")
df = df_price.merge(df_basic[['ts_code','trade_date','circ_mv']], on=['ts_code','trade_date'], how='left')
print(f"  合并后: {len(df):,} 行, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# Step 4: 向量化计算技术指标
# ============================================================
t0 = time.time()
print("\n[Step 4] 计算技术指标 (向量化)...")

df = df.sort_values(['ts_code','trade_date']).reset_index(drop=True)

# 均线
df['ma5'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(5, min_periods=5).mean())
df['ma10'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(10, min_periods=10).mean())
df['ma20'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['ma60'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(60, min_periods=60).mean())
print(f"  MA计算完成, 耗时 {time.time()-t0:.1f}s")

t0 = time.time()
# MA变异系数
ma_cols = ['ma5','ma10','ma20','ma60']
df['ma_mean'] = df[ma_cols].mean(axis=1)
df['ma_std'] = df[ma_cols].std(axis=1)
df['ma_cv'] = df['ma_std'] / df['ma_mean']
print(f"  MA_CV计算完成, 耗时 {time.time()-t0:.1f}s")

t0 = time.time()
# ATR(14)
df['prev_close'] = df.groupby('ts_code')['close'].shift(1)
df['tr1'] = df['high'] - df['low']
df['tr2'] = (df['high'] - df['prev_close']).abs()
df['tr3'] = (df['low'] - df['prev_close']).abs()
df['tr'] = df[['tr1','tr2','tr3']].max(axis=1)
df['atr14'] = df.groupby('ts_code')['tr'].transform(lambda x: x.rolling(14, min_periods=14).mean())
df['atr_pct'] = df['atr14'] / df['close']
print(f"  ATR计算完成, 耗时 {time.time()-t0:.1f}s")

t0 = time.time()
# ATR百分位: 用rolling rank加速
# 近似: (current - rolling_min) / (rolling_max - rolling_min)
df['atr_250min'] = df.groupby('ts_code')['atr_pct'].transform(lambda x: x.rolling(250, min_periods=60).min())
df['atr_250max'] = df.groupby('ts_code')['atr_pct'].transform(lambda x: x.rolling(250, min_periods=60).max())
df['atr_range'] = df['atr_250max'] - df['atr_250min']
df['atr_pctile'] = (df['atr_pct'] - df['atr_250min']) / df['atr_range'].replace(0, np.nan)
print(f"  ATR百分位计算完成, 耗时 {time.time()-t0:.1f}s")

t0 = time.time()
# 量比
df['vol_ma20'] = df.groupby('ts_code')['vol'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['vol_ratio'] = df['vol'] / df['vol_ma20']

# 20日最高价(不含当日)
df['high_20d'] = df.groupby('ts_code')['high'].transform(lambda x: x.rolling(20, min_periods=20).max().shift(1))

# 市值过滤
df['cap_ok'] = df['circ_mv'] > 300000  # 30亿

print(f"  量价指标计算完成, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# Step 5: 筛选信号
# ============================================================
t0 = time.time()
print("\n[Step 5] 筛选信号...")

signals = df[
    (df['ma60'].notna()) &
    (df['ma_cv'] < 0.02) &
    (df['atr_pctile'] < 0.2) &
    (df['vol_ratio'] > 2.0) &
    (df['close'] > df['high_20d']) &
    (df['cap_ok'] == True)
].copy()

print(f"  信号数: {len(signals):,}")
print(f"  涉及股票: {signals['ts_code'].nunique()}")
print(f"  时间范围: {signals['trade_date'].min()} ~ {signals['trade_date'].max()}")

if len(signals) < 50:
    print("  信号太少, 放宽条件...")
    signals = df[
        (df['ma60'].notna()) &
        (df['ma_cv'] < 0.03) &
        (df['atr_pctile'] < 0.3) &
        (df['vol_ratio'] > 1.5) &
        (df['close'] > df['high_20d']) &
        (df['cap_ok'] == True)
    ].copy()
    print(f"  放宽后: {len(signals):,}")

print(f"  耗时 {time.time()-t0:.1f}s")

# ============================================================
# Step 6: 获取沪深300指数
# ============================================================
t0 = time.time()
print("\n[Step 6] 获取沪深300指数...")
sql_idx = """
SELECT trade_date, close as idx_close
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000300.SH' AND trade_date >= '20190101'
ORDER BY trade_date
"""
df_idx = ck_query(sql_idx)
df_idx['idx_close'] = pd.to_numeric(df_idx['idx_close'], errors='coerce')
df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])
df_idx['idx_ma200'] = df_idx['idx_close'].rolling(200, min_periods=60).mean()
df_idx = df_idx[['trade_date','idx_close','idx_ma200']].dropna()
print(f"  指数数据: {len(df_idx):,} 行")

signals = signals.merge(df_idx, on='trade_date', how='left')
signals['bull_market'] = signals['idx_close'] > signals['idx_ma200']
print(f"  耗时 {time.time()-t0:.1f}s")

# ============================================================
# Step 7: 计算未来收益 (高效方法)
# ============================================================
t0 = time.time()
print("\n[Step 7] 计算未来收益...")

# 使用merge技巧: 对每个信号, merge同一股票的未来数据
# 但更高效的方法: 在df上按ts_code排序后, 用shift获取未来N日价格

# 为df添加未来收盘价
for n in [5, 10, 20]:
    df[f'close_fwd_{n}'] = df.groupby('ts_code')['close'].shift(-n)
    df[f'high_fwd_{n}'] = df.groupby('ts_code')['high'].transform(
        lambda x: x.rolling(n, min_periods=1).max().shift(-n)
    )

# 计算最高价(未来n日内)
for n in [5, 10, 20, 30]:
    # rolling max from current+1 to current+n
    df[f'high_next_{n}'] = df.groupby('ts_code')['high'].transform(
        lambda x: x.shift(-1).rolling(n, min_periods=1).max()
    )

# 从df中提取信号的收益
sig_idx = signals.index
signals['ret_5d'] = (df.loc[sig_idx, 'close_fwd_5'].values / signals['close'].values) - 1
signals['ret_10d'] = (df.loc[sig_idx, 'close_fwd_10'].values / signals['close'].values) - 1
signals['ret_20d'] = (df.loc[sig_idx, 'close_fwd_20'].values / signals['close'].values) - 1
signals['ret_max'] = (df.loc[sig_idx, 'high_next_20'].values / signals['close'].values) - 1

df_results = signals[['ts_code','trade_date','close','ma_cv','atr_pctile','vol_ratio',
                       'bull_market','ret_5d','ret_10d','ret_20d','ret_max']].copy()
df_results = df_results.dropna(subset=['ret_20d'])  # 确保有20日收益

print(f"  有效信号(含20日收益): {len(df_results):,}")
print(f"  耗时 {time.time()-t0:.1f}s")

# ============================================================
# Step 8: 统计分析
# ============================================================
print("\n" + "=" * 70)
print("📊 统计分析结果")
print("=" * 70)

for horizon in ['ret_5d', 'ret_10d', 'ret_20d']:
    data = df_results[horizon].dropna()
    if len(data) == 0:
        continue
    win_rate = (data > 0).mean()
    avg_ret = data.mean()
    median_ret = data.median()
    std_ret = data.std()
    max_ret = data.max()
    min_ret = data.min()
    avg_win = data[data > 0].mean()
    avg_loss = data[data < 0].mean()
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    
    print(f"\n--- {horizon} ({len(data)} 样本) ---")
    print(f"  平均收益: {avg_ret*100:.2f}%")
    print(f"  中位收益: {median_ret*100:.2f}%")
    print(f"  胜率: {win_rate*100:.1f}%")
    print(f"  标准差: {std_ret*100:.2f}%")
    print(f"  最大收益: {max_ret*100:.2f}%")
    print(f"  最小收益: {min_ret*100:.2f}%")
    print(f"  盈亏比: {pl_ratio:.2f}")

# ============================================================
# Step 9: 按市场环境分组
# ============================================================
print("\n" + "=" * 70)
print("📊 按市场环境分组 (牛/熊)")
print("=" * 70)

for regime, name in [(True, '🟢 牛市(CSI300>MA200)'), (False, '🔴 熊市(CSI300<MA200)')]:
    subset = df_results[df_results['bull_market'] == regime]
    print(f"\n--- {name} ({len(subset)} 样本) ---")
    for horizon in ['ret_5d', 'ret_10d', 'ret_20d']:
        data = subset[horizon].dropna()
        if len(data) == 0:
            continue
        print(f"  {horizon}: 均值={data.mean()*100:.2f}%, 中位={data.median()*100:.2f}%, 胜率={(data>0).mean()*100:.1f}%")

# ============================================================
# Step 10: 参数敏感性
# ============================================================
print("\n" + "=" * 70)
print("📊 参数敏感性测试")
print("=" * 70)

print("\n  MA_CV阈值:")
for cv_t in [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]:
    subset = df_results[df_results['ma_cv'] < cv_t]
    ret = subset['ret_20d'].dropna()
    if len(ret) < 5:
        continue
    print(f"    MA_CV<{cv_t}: n={len(ret)}, 均值={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%")

print("\n  ATR百分位阈值:")
for atr_t in [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]:
    subset = df_results[df_results['atr_pctile'] < atr_t]
    ret = subset['ret_20d'].dropna()
    if len(ret) < 5:
        continue
    print(f"    ATR<{atr_t}: n={len(ret)}, 均值={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%")

print("\n  量比阈值:")
for vr_t in [1.5, 2.0, 2.5, 3.0, 4.0]:
    subset = df_results[df_results['vol_ratio'] > vr_t]
    ret = subset['ret_20d'].dropna()
    if len(ret) < 5:
        continue
    print(f"    VR>{vr_t}: n={len(ret)}, 均值={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%")

# ============================================================
# Step 11: 分年度统计
# ============================================================
print("\n" + "=" * 70)
print("📊 分年度统计")
print("=" * 70)

df_results['year'] = df_results['trade_date'].dt.year
for year in sorted(df_results['year'].unique()):
    subset = df_results[df_results['year'] == year]
    ret = subset['ret_20d'].dropna()
    if len(ret) < 5:
        continue
    print(f"  {year}: n={len(ret)}, 均值={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%")

# ============================================================
# Step 12: 保存
# ============================================================
print("\n" + "=" * 70)
print("💾 保存结果")
print("=" * 70)

df_results.to_csv(RESULTS_DIR + 'results.csv', index=False)

ret20 = df_results['ret_20d'].dropna()
summary = {
    'total_signals': len(df_results),
    'ret_5d_mean': round(float(df_results['ret_5d'].mean()), 6) if len(df_results['ret_5d'].dropna()) > 0 else None,
    'ret_10d_mean': round(float(df_results['ret_10d'].mean()), 6) if len(df_results['ret_10d'].dropna()) > 0 else None,
    'ret_20d_mean': round(float(ret20.mean()), 6) if len(ret20) > 0 else None,
    'ret_20d_median': round(float(ret20.median()), 6) if len(ret20) > 0 else None,
    'ret_20d_winrate': round(float((ret20 > 0).mean()), 4) if len(ret20) > 0 else None,
    'sample_size': len(ret20),
}
with open(RESULTS_DIR + 'summary.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(f"  总信号数: {len(df_results):,}")
print(f"  20日平均收益: {ret20.mean()*100:.2f}%")
print(f"  20日中位收益: {ret20.median()*100:.2f}%")
print(f"  20日胜率: {(ret20>0).mean()*100:.1f}%")
print(f"  样本数: {len(ret20):,}")

print("\n✅ V2 研究完成!")
