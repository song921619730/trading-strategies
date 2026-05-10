"""
V1: 缩量回调买入策略 — 多信号对比
核心逻辑: 强势股缩量回调至支撑位时买入
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

RESULTS_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/缩量回调买入_(pullback_on_shrinking_volume)/20260510_v1_pullback/'

print("=" * 70)
print("V1: 缩量回调买入策略 — 多信号对比")
print("=" * 70)

# ============================================================
# 加载数据
# ============================================================
t0 = time.time()
print("\n[1/4] 加载数据...")

sql1 = """
SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20190101'
ORDER BY ts_code, trade_date
"""
df = ck_query(sql1)
for c in ['open','high','low','close','vol','pct_chg']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

sql2 = """
SELECT ts_code, trade_date, circ_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20190101'
ORDER BY ts_code, trade_date
"""
df_b = ck_query(sql2)
df_b['circ_mv'] = pd.to_numeric(df_b['circ_mv'], errors='coerce')
df_b['trade_date'] = pd.to_datetime(df_b['trade_date'])

df = df.merge(df_b[['ts_code','trade_date','circ_mv']], on=['ts_code','trade_date'], how='left')
df = df.sort_values(['ts_code','trade_date']).reset_index(drop=True)
print(f"  数据: {len(df):,} 行, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 计算指标
# ============================================================
t0 = time.time()
print("\n[2/4] 计算指标...")

df['ma5'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(5, min_periods=5).mean())
df['ma10'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(10, min_periods=10).mean())
df['ma20'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['ma60'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(60, min_periods=60).mean())

# MA20趋势 (上/下)
df['ma20_slope'] = df.groupby('ts_code')['ma20'].transform(lambda x: x.diff(5))
df['ma20_uptrend'] = df['ma20_slope'] > 0

# 量比
df['vol_ma20'] = df.groupby('ts_code')['vol'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['vol_ratio'] = df['vol'] / df['vol_ma20']

# 连续缩量天数
df['vol_shrink'] = df['vol_ratio'] < 0.8
df['consec_shrink'] = df.groupby('ts_code')['vol_shrink'].transform(
    lambda x: x.astype(int).rolling(5, min_periods=1).sum()
)

# 回调深度: 距离MA20的百分比
df['pullback_pct'] = (df['close'] - df['ma20']) / df['ma20']

# 距离MA10的百分比
df['pullback_ma10_pct'] = (df['close'] - df['ma10']) / df['ma10']

# 振幅
df['amplitude'] = (df['high'] - df['low']) / df['close']

# 下影线比率
df['lower_shadow'] = (df['close'] - df['low']) / df['close']
df['upper_shadow'] = (df['high'] - df['close']) / df['close']
df['body'] = abs(df['close'] - df['open']) / df['close']

# 未来收益
for n in [5, 10, 20]:
    df[f'close_fwd_{n}'] = df.groupby('ts_code')['close'].shift(-n)

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
df['cap_ok'] = df['circ_mv'] > 300000

print(f"  指标计算完成, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 定义并测试策略
# ============================================================
print("\n" + "=" * 70)
print("📊 策略对比测试")
print("=" * 70)

strategies = {
    'S1_趋势缩量回踩MA20': {
        'filter': (df['ma60'].notna()) & (df['close'] > df['ma60']) & (df['ma20'] > df['ma60']) &
                  (df['vol_ratio'] < 0.8) & (df['pullback_pct'] > -0.03) & (df['pullback_pct'] < 0.03) &
                  (df['cap_ok']),
        'desc': '股价>MA60 + MA20>MA60 + 量比<0.8 + 回踩MA20±3%'
    },
    'S2_缩量回踩MA10': {
        'filter': (df['ma60'].notna()) & (df['close'] > df['ma60']) & (df['ma20'] > df['ma60']) &
                  (df['vol_ratio'] < 0.7) & (df['pullback_ma10_pct'] > -0.02) & (df['pullback_ma10_pct'] < 0.02) &
                  (df['cap_ok']),
        'desc': '股价>MA60 + MA20>MA60 + 量比<0.7 + 回踩MA10±2%'
    },
    'S3_连续缩量3日+': {
        'filter': (df['ma60'].notna()) & (df['close'] > df['ma60']) & (df['ma20'] > df['ma60']) &
                  (df['consec_shrink'] >= 3) & (df['pullback_pct'] < 0.05) & (df['pullback_pct'] > -0.05) &
                  (df['cap_ok']),
        'desc': '股价>MA60 + MA20>MA60 + 连续3日缩量 + 距MA20±5%'
    },
    'S4_缩量十字星': {
        'filter': (df['ma60'].notna()) & (df['close'] > df['ma60']) & (df['ma20'] > df['ma60']) &
                  (df['vol_ratio'] < 0.8) & (df['amplitude'] < 0.02) & (df['cap_ok']),
        'desc': '股价>MA60 + MA20>MA60 + 量比<0.8 + 振幅<2%'
    },
    'S5_缩量长下影': {
        'filter': (df['ma60'].notna()) & (df['close'] > df['ma60']) & (df['ma20'] > df['ma60']) &
                  (df['vol_ratio'] < 0.8) & (df['lower_shadow'] > df['body'] * 2) & (df['body'] < 0.015) &
                  (df['cap_ok']),
        'desc': '股价>MA60 + MA20>MA60 + 量比<0.8 + 长下影+小实体'
    },
    'S6_宽松回调': {
        'filter': (df['ma60'].notna()) & (df['close'] > df['ma60']) & (df['ma20_uptrend']) &
                  (df['vol_ratio'] < 0.9) & (df['pullback_pct'] > -0.05) & (df['pullback_pct'] < 0.05) &
                  (df['cap_ok']),
        'desc': '股价>MA60 + MA20上行 + 量比<0.9 + 距MA20±5%'
    },
    'S7_缩量企稳(次日确认)': {
        'filter': (df['ma60'].notna()) & (df['close'] > df['ma60']) & (df['ma20'] > df['ma60']) &
                  (df['vol_ratio'] < 0.7) & (df['pullback_pct'] < 0.02) & (df['pullback_pct'] > -0.04) &
                  (df['pct_chg'] > -1.0) & (df['cap_ok']),
        'desc': '股价>MA60 + MA20>MA60 + 量比<0.7 + 回踩MA20附近 + 当日跌幅<1%'
    },
}

all_results = {}

for name, strat in strategies.items():
    mask = strat['filter']
    sig = df[mask].copy()
    sig = sig.dropna(subset=['close_fwd_20'])
    
    if len(sig) < 20:
        print(f"\n  {name}: 信号太少 ({len(sig)}), 跳过")
        continue
    
    ret20 = sig['close_fwd_20'] / sig['close'] - 1
    ret10 = sig['close_fwd_10'] / sig['close'] - 1
    ret5 = sig['close_fwd_5'] / sig['close'] - 1
    
    # 盈亏比
    avg_win = ret20[ret20 > 0].mean()
    avg_loss = ret20[ret20 < 0].mean()
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    # 分年度
    by_year = {}
    for y in sorted(sig['year'].unique()):
        sub = sig[sig['year'] == y]
        r = sub['close_fwd_20'] / sub['close'] - 1
        by_year[int(y)] = {
            'n': len(r.dropna()),
            'mean': round(float(r.mean())*100, 2),
            'median': round(float(r.median())*100, 2),
            'wr': round(float((r>0).mean())*100, 1),
        }
    
    # 分牛熊
    bull = sig[sig['bull_market']==True]
    bear = sig[sig['bull_market']==False]
    bull_ret = bull['close_fwd_20'] / bull['close'] - 1
    bear_ret = bear['close_fwd_20'] / bear['close'] - 1
    
    result = {
        'total': len(sig),
        'ret5_wr': round(float((ret5>0).mean())*100, 1),
        'ret10_wr': round(float((ret10>0).mean())*100, 1),
        'ret20_mean': round(float(ret20.mean())*100, 2),
        'ret20_median': round(float(ret20.median())*100, 2),
        'ret20_wr': round(float((ret20>0).mean())*100, 1),
        'pl_ratio': round(pl_ratio, 2),
        'bull_n': len(bull),
        'bull_wr': round(float((bull_ret>0).mean())*100, 1) if len(bull)>0 else None,
        'bear_n': len(bear),
        'bear_wr': round(float((bear_ret>0).mean())*100, 1) if len(bear)>0 else None,
        'by_year': by_year,
    }
    all_results[name] = result
    
    print(f"\n  ── {name} ──")
    print(f"  {strat['desc']}")
    print(f"  样本: {result['total']:,}")
    print(f"  20日: 均值={result['ret20_mean']}%, 中位={result['ret20_median']}%, 胜率={result['ret20_wr']}%")
    print(f"  盈亏比: {result['pl_ratio']}")
    print(f"  🟢牛市({result['bull_n']}): {result['bull_wr']}% | 🔴熊市({result['bear_n']}): {result['bear_wr']}%")
    for y, stats in by_year.items():
        bar = "🟢" if stats['wr'] >= 50 else "🔴"
        print(f"    {bar}{y}: n={stats['n']}, 均值={stats['mean']}%, 胜率={stats['wr']}%")

# ============================================================
# 找出最佳策略
# ============================================================
print("\n" + "=" * 70)
print("🏆 策略排名 (按20日胜率)")
print("=" * 70)

sorted_strats = sorted(all_results.items(), key=lambda x: x[1]['ret20_wr'], reverse=True)
for i, (name, result) in enumerate(sorted_strats, 1):
    print(f"  {i}. {name}: 胜率={result['ret20_wr']}%, 均值={result['ret20_mean']}%, n={result['total']:,}")

# ============================================================
# 额外: 最佳策略分年度详细
# ============================================================
best_name, best_result = sorted_strats[0]
print(f"\n🏆 最佳策略 '{best_name}' 分年度:")
for y, stats in best_result['by_year'].items():
    bar = "🟢" if stats['wr'] >= 50 else "🔴"
    print(f"  {bar} {y}: n={stats['n']}, 均值={stats['mean']}%, 中位={stats['median']}%, 胜率={stats['wr']}%")

# ============================================================
# 保存
# ============================================================
print("\n" + "=" * 70)
print("💾 保存结果")
print("=" * 70)

with open(RESULTS_DIR + 'summary.json', 'w') as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print(f"  最佳策略: {best_name}")
print(f"  胜率: {best_result['ret20_wr']}%")
print(f"  均值: {best_result['ret20_mean']}%")

print("\n✅ V1 研究完成!")
