"""
V3: 主升浪入场信号优化 — 严格参数 + 确认日入场 + 年度过滤
基于V2发现: 量比>4.0最优, MA_CV<0.01有帮助, 2025-2026严重衰减
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

RESULTS_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/主升浪潜伏与起爆点_(pre-main_uptrend_entry)/20260510_v3_optimized/'

print("=" * 70)
print("V3: 主升浪入场信号优化")
print("=" * 70)

# ============================================================
# 加载数据 (复用V2逻辑)
# ============================================================
t0 = time.time()
print("\n[1/3] 加载数据...")

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

sql2 = """
SELECT ts_code, trade_date, circ_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20190101'
ORDER BY ts_code, trade_date
"""
df_basic = ck_query(sql2)
df_basic['circ_mv'] = pd.to_numeric(df_basic['circ_mv'], errors='coerce')
df_basic['trade_date'] = pd.to_datetime(df_basic['trade_date'])

df = df_price.merge(df_basic[['ts_code','trade_date','circ_mv']], on=['ts_code','trade_date'], how='left')
df = df.sort_values(['ts_code','trade_date']).reset_index(drop=True)
print(f"  数据: {len(df):,} 行, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 计算指标
# ============================================================
t0 = time.time()
print("\n[2/3] 计算指标...")

df['ma5'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(5, min_periods=5).mean())
df['ma10'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(10, min_periods=10).mean())
df['ma20'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['ma60'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(60, min_periods=60).mean())

ma_cols = ['ma5','ma10','ma20','ma60']
df['ma_mean'] = df[ma_cols].mean(axis=1)
df['ma_std'] = df[ma_cols].std(axis=1)
df['ma_cv'] = df['ma_std'] / df['ma_mean']

df['prev_close'] = df.groupby('ts_code')['close'].shift(1)
df['tr'] = np.maximum(df['high']-df['low'], np.maximum((df['high']-df['prev_close']).abs(), (df['low']-df['prev_close']).abs()))
df['atr14'] = df.groupby('ts_code')['tr'].transform(lambda x: x.rolling(14, min_periods=14).mean())
df['atr_pct'] = df['atr14'] / df['close']
df['atr_250min'] = df.groupby('ts_code')['atr_pct'].transform(lambda x: x.rolling(250, min_periods=60).min())
df['atr_250max'] = df.groupby('ts_code')['atr_pct'].transform(lambda x: x.rolling(250, min_periods=60).max())
df['atr_pctile'] = (df['atr_pct'] - df['atr_250min']) / (df['atr_250max'] - df['atr_250min']).replace(0, np.nan)

df['vol_ma20'] = df.groupby('ts_code')['vol'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['vol_ratio'] = df['vol'] / df['vol_ma20']
df['high_20d'] = df.groupby('ts_code')['high'].transform(lambda x: x.rolling(20, min_periods=20).max().shift(1))
df['cap_ok'] = df['circ_mv'] > 300000

# 未来收益
for n in [5, 10, 20]:
    df[f'close_fwd_{n}'] = df.groupby('ts_code')['close'].shift(-n)
df['high_next_20'] = df.groupby('ts_code')['high'].transform(lambda x: x.shift(-1).rolling(20, min_periods=1).max())

# 沪深300
sql_idx = "SELECT trade_date, close as idx_close FROM tushare.tushare_index_daily FINAL WHERE ts_code='000300.SH' AND trade_date>='20190101' ORDER BY trade_date"
df_idx = ck_query(sql_idx)
df_idx['idx_close'] = pd.to_numeric(df_idx['idx_close'], errors='coerce')
df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])
df_idx['idx_ma200'] = df_idx['idx_close'].rolling(200, min_periods=60).mean()
df_idx = df_idx[['trade_date','idx_close','idx_ma200']].dropna()
df = df.merge(df_idx, on='trade_date', how='left')
df['bull_market'] = df['idx_close'] > df['idx_ma200']

df['year'] = df['trade_date'].dt.year

print(f"  指标计算完成, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 测试多种策略组合
# ============================================================
print("\n" + "=" * 70)
print("📊 多策略对比测试")
print("=" * 70)

strategies = {
    'S1_严格突破(基准)': {
        'filter': (df['ma60'].notna()) & (df['ma_cv']<0.01) & (df['atr_pctile']<0.2) & (df['vol_ratio']>3.0) & (df['close']>df['high_20d']) & (df['cap_ok']),
        'desc': 'MA_CV<0.01 + ATR<0.2 + VR>3.0 + 突破20日高'
    },
    'S2_极端量比': {
        'filter': (df['ma60'].notna()) & (df['ma_cv']<0.01) & (df['atr_pctile']<0.2) & (df['vol_ratio']>4.0) & (df['close']>df['high_20d']) & (df['cap_ok']),
        'desc': 'MA_CV<0.01 + ATR<0.2 + VR>4.0 + 突破20日高'
    },
    'S3_宽松ATR': {
        'filter': (df['ma60'].notna()) & (df['ma_cv']<0.01) & (df['atr_pctile']<0.3) & (df['vol_ratio']>3.0) & (df['close']>df['high_20d']) & (df['cap_ok']),
        'desc': 'MA_CV<0.01 + ATR<0.3 + VR>3.0 + 突破20日高'
    },
    'S4_突破+回踩MA20': {
        'filter': (df['ma60'].notna()) & (df['ma_cv']<0.015) & (df['vol_ratio']>2.5) & (df['close']>df['high_20d']) & (df['close']>df['ma20']) & (df['cap_ok']),
        'desc': 'MA_CV<0.015 + VR>2.5 + 突破 + 站在MA20上'
    },
    'S5_缩量回踩(反突破)': {
        'filter': (df['ma60'].notna()) & (df['ma_cv']<0.02) & (df['vol_ratio']<0.8) & (df['close']>df['ma20']) & (df['close']<df['ma5']) & (df['cap_ok']),
        'desc': 'MA_CV<0.02 + 缩量(VR<0.8) + 在MA20上 + 跌破MA5'
    },
}

all_results = {}

for name, strat in strategies.items():
    sig = df[strat['filter']].copy()
    sig = sig.dropna(subset=['close_fwd_20'])
    
    if len(sig) < 10:
        print(f"\n  {name}: 信号太少 ({len(sig)}), 跳过")
        continue
    
    ret20 = sig['close_fwd_20'] / sig['close'] - 1
    ret10 = sig['close_fwd_10'] / sig['close'] - 1
    ret5 = sig['close_fwd_5'] / sig['close'] - 1
    
    # 分年度
    by_year = {}
    for y in sorted(sig['year'].unique()):
        sub = sig[sig['year'] == y]
        r = sub['close_fwd_20'] / sub['close'] - 1
        by_year[int(y)] = {
            'n': len(r.dropna()),
            'mean': round(float(r.mean())*100, 2),
            'median': round(float(r.median())*100, 2),
            'winrate': round(float((r>0).mean())*100, 1),
        }
    
    # 分牛熊
    bull = sig[sig['bull_market']==True]
    bear = sig[sig['bull_market']==False]
    bull_ret = bull['close_fwd_20'] / bull['close'] - 1
    bear_ret = bear['close_fwd_20'] / bear['close'] - 1
    
    result = {
        'total': len(sig),
        'ret5_mean': round(float(ret5.mean())*100, 2),
        'ret5_median': round(float(ret5.median())*100, 2),
        'ret5_wr': round(float((ret5>0).mean())*100, 1),
        'ret10_mean': round(float(ret10.mean())*100, 2),
        'ret20_mean': round(float(ret20.mean())*100, 2),
        'ret20_median': round(float(ret20.median())*100, 2),
        'ret20_wr': round(float((ret20>0).mean())*100, 1),
        'bull_n': len(bull),
        'bull_wr': round(float((bull_ret>0).mean())*100, 1) if len(bull)>0 else None,
        'bear_n': len(bear),
        'bear_wr': round(float((bear_ret>0).mean())*100, 1) if len(bear)>0 else None,
        'by_year': by_year,
    }
    all_results[name] = result
    
    print(f"\n  ── {name} ──")
    print(f"  描述: {strat['desc']}")
    print(f"  样本: {result['total']:,}")
    print(f"  20日: 均值={result['ret20_mean']}%, 中位={result['ret20_median']}%, 胜率={result['ret20_wr']}%")
    print(f"  牛市({result['bull_n']}): 胜率={result['bull_wr']}% | 熊市({result['bear_n']}): 胜率={result['bear_wr']}%")
    for y, stats in by_year.items():
        print(f"    {y}: n={stats['n']}, 均值={stats['mean']}%, 胜率={stats['winrate']}%")

# ============================================================
# 额外测试: 2020-2024子集 (排除2025-2026)
# ============================================================
print("\n" + "=" * 70)
print("📊 2020-2024子集测试 (排除衰减期)")
print("=" * 70)

df_pre = df[df['year'] <= 2024].copy()

for name, strat in strategies.items():
    sig = df_pre[strat['filter']].copy()
    sig = sig.dropna(subset=['close_fwd_20'])
    
    if len(sig) < 10:
        continue
    
    ret20 = sig['close_fwd_20'] / sig['close'] - 1
    
    print(f"\n  {name}: n={len(sig)}, 20日均值={ret20.mean()*100:.2f}%, 中位={ret20.median()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# ============================================================
# 测试: 确认日入场 (T+1买入)
# ============================================================
print("\n" + "=" * 70)
print("📊 确认日入场测试 (T+1买入)")
print("=" * 70)

# 基础信号
base_sig = df[
    (df['ma60'].notna()) & (df['ma_cv']<0.01) & (df['atr_pctile']<0.2) & 
    (df['vol_ratio']>3.0) & (df['close']>df['high_20d']) & (df['cap_ok'])
].copy()

# T+1买入: 用T+1的开盘价买入
# 需要T+1的open价格
df['open_next'] = df.groupby('ts_code')['open'].shift(-1)
df['close_next'] = df.groupby('ts_code')['close'].shift(-1)

base_sig = base_sig.dropna(subset=['open_next', 'close_fwd_20'])
base_sig = base_sig[base_sig['year'] <= 2024]  # 只测2020-2024

# T+1开盘买入, 持有20日
base_sig['ret_t1_20d'] = base_sig['close_fwd_20'] / base_sig['open_next'] - 1

print(f"\n  T+1开盘买入 (2020-2024):")
print(f"  样本: {len(base_sig):,}")
print(f"  20日: 均值={base_sig['ret_t1_20d'].mean()*100:.2f}%, 中位={base_sig['ret_t1_20d'].median()*100:.2f}%, 胜率={(base_sig['ret_t1_20d']>0).mean()*100:.1f}%")

# ============================================================
# 保存结果
# ============================================================
print("\n" + "=" * 70)
print("💾 保存结果")
print("=" * 70)

summary = {
    'strategies': all_results,
    'v2_comparison': {
        'v2_baseline': {'n': 16251, 'ret20_mean': 22.61, 'ret20_median': -33.23, 'wr': 37.4},
    }
}
with open(RESULTS_DIR + 'summary.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

# 找出最佳策略
best = max(all_results.items(), key=lambda x: x[1]['ret20_wr'])
print(f"\n  🏆 最佳策略: {best[0]}")
print(f"  20日胜率: {best[1]['ret20_wr']}%")
print(f"  20日均值: {best[1]['ret20_mean']}%")
print(f"  20日中位: {best[1]['ret20_median']}%")
print(f"  样本: {best[1]['total']:,}")

print("\n✅ V3 研究完成!")
