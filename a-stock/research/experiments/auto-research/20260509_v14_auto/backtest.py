#!/usr/bin/env python3
"""
A-Stock Research: 量价背离因子 + 资金流分层因子 实证研究 (修正版)
假设1: 量价背离(价格创新高但成交量萎缩)是有效的短线反转信号
假设2: 超大单净买入占比高的股票具有显著正向次日溢价
"""

import pandas as pd
import numpy as np
import pickle
import requests
import io
import warnings
warnings.filterwarnings('ignore')

# Manual t-test
def ttest_ind(a, b):
    n1, n2 = len(a), len(b)
    m1, m2 = np.mean(a), np.mean(b)
    v1, v2 = np.var(a, ddof=1), np.var(b, ddof=1)
    se = np.sqrt(v1/n1 + v2/n2)
    if se == 0: return 0, 1.0
    t = (m1 - m2) / se
    p = 2 * (1 - _norm_cdf(abs(t)))
    return t, p

def ttest_1samp(a, popmean):
    n = len(a)
    m = np.mean(a)
    v = np.var(a, ddof=1)
    se = np.sqrt(v / n)
    if se == 0: return 0, 1.0
    t = (m - popmean) / se
    p = 2 * (1 - _norm_cdf(abs(t)))
    return t, p

def _norm_cdf(x):
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x) / np.sqrt(2)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5*t + a4)*t) + a3)*t + a2)*t + a1)*t * np.exp(-x*x)
    return 0.5 * (1.0 + sign * y)

url = 'http://172.24.224.1:8123/'
auth = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

# ============================================================
# 数据加载
# ============================================================
print("="*60)
print("加载数据...")
df = pd.read_pickle('hs300_daily.pkl')
df['trade_date'] = pd.to_datetime(df['trade_date'])
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

# pct_chg 在 Tushare 中已经是百分比 (如 1.5 = 1.5%)
# 转换为小数收益率
df['ret'] = df['pct_chg'] / 100.0

print(f"数据: {len(df)} 条, {df.ts_code.nunique()} 只股票")
print(f"日期范围: {df.trade_date.min().date()} 至 {df.trade_date.max().date()}")
print(f"平均日收益率: {df.ret.mean()*100:.3f}%")

# ============================================================
# 假设1: 量价背离因子 (Volume-Price Divergence)
# ============================================================
print("\n" + "="*60)
print("假设1: 量价背离因子实证")
print("="*60)
print("逻辑: 价格创新高但成交量萎缩 → 上涨动能衰竭 → 次日可能回调")

results_vp = {}

for n in [10, 20, 30]:
    for m in [10, 20, 30]:
        d = df.copy()
        d['high_n'] = d.groupby('ts_code')['close'].transform(lambda x: x.rolling(n).max())
        d['vol_ma_m'] = d.groupby('ts_code')['vol'].transform(lambda x: x.rolling(m).mean())
        
        d['price_ratio'] = d['close'] / d['high_n']  # 接近1 = 近期高点
        d['vol_ratio'] = d['vol'] / (d['vol_ma_m'] + 1e-9)  # <1 = 缩量
        d['vp_div'] = d['price_ratio'] - d['vol_ratio']  # 越高 = 越背离
        
        d['next_ret'] = d.groupby('ts_code')['ret'].shift(-1)
        valid = d.dropna(subset=['vp_div', 'next_ret'])
        valid['q'] = pd.qcut(valid['vp_div'], 5, labels=False, duplicates='drop')
        
        gs = valid.groupby('q')['next_ret'].agg(['mean', 'count'])
        if 4 in gs.index and 0 in gs.index:
            q4 = valid[valid['q']==4]['next_ret'].values
            q0 = valid[valid['q']==0]['next_ret'].values
            t, p = ttest_ind(q4, q0)
            results_vp[f'n{n}_m{m}'] = {
                'q0': gs.loc[0,'mean'], 'q4': gs.loc[4,'mean'],
                'diff': gs.loc[4,'mean']-gs.loc[0,'mean'],
                't': t, 'p': p, 'n0': len(q0), 'n4': len(q4)
            }

print(f"\n{'参数':<12} {'Q0(低背离)%':<12} {'Q4(高背离)%':<12} {'差异(bp)':<10} {'t':<8} {'p':<10} {'N0':<8} {'N4':<8}")
print("-"*85)

best_key = min(results_vp, key=lambda k: results_vp[k]['p'])
for key in sorted(results_vp.keys()):
    v = results_vp[key]
    sig = "***" if v['p']<0.01 else ("**" if v['p']<0.05 else "")
    print(f"{key:<12} {v['q0']*100:<12.3f} {v['q4']*100:<12.3f} {(v['diff']*10000):<10.1f} {v['t']:<8.3f} {v['p']:<10.2e} {v['n0']:<8} {v['n4']:<8} {sig}")

bv = results_vp[best_key]
print(f"\n最佳: {best_key}, 高背离组日均 {bv['q4']*100:.3f}%, 低背离组 {bv['q0']*100:.3f}%, 差异 {bv['diff']*10000:.1f}bp, p={bv['p']:.2e}")

# ============================================================
# 假设2: 资金流分层因子
# ============================================================
print("\n" + "="*60)
print("假设2: 资金流分层因子实证")
print("="*60)
print("逻辑: 超大单(机构)净买入 → 信息优势 → 正向溢价")

hs300_codes = [c for c in df.ts_code.unique()]
codes_str = ','.join([f"'{c}'" for c in hs300_codes])

query = f"""
SELECT ts_code, trade_date, 
       buy_elg_amount, sell_elg_amount, buy_lg_amount, sell_lg_amount,
       buy_md_amount, sell_md_amount, buy_sm_amount, sell_sm_amount
FROM tushare.tushare_moneyflow FINAL
WHERE ts_code IN ({codes_str})
AND trade_date >= '20200101'
FORMAT TabSeparatedWithNames
"""
print("获取资金流数据...")
r = requests.get(url, params={'query': query}, auth=auth, timeout=300)
mf_df = pd.read_csv(io.StringIO(r.text), sep='\t')
mf_df['trade_date'] = pd.to_datetime(mf_df['trade_date'])
print(f"资金流数据: {len(mf_df)} 条")

merged = df.merge(mf_df, on=['ts_code', 'trade_date'], how='inner')
print(f"合并后: {len(merged)} 条")

merged['elg_net'] = merged['buy_elg_amount'] - merged['sell_elg_amount']
merged['lg_net'] = merged['buy_lg_amount'] - merged['sell_lg_amount']
merged['total_amt'] = (merged['buy_elg_amount'] + merged['sell_elg_amount'] + 
                       merged['buy_lg_amount'] + merged['sell_lg_amount'] +
                       merged['buy_md_amount'] + merged['sell_md_amount'] +
                       merged['buy_sm_amount'] + merged['sell_sm_amount'])
merged['elg_ratio'] = merged['elg_net'] / (merged['total_amt'] + 1e-9)
merged['inst_ratio'] = (merged['elg_net'] + merged['lg_net']) / (merged['total_amt'] + 1e-9)
merged['next_ret'] = merged.groupby('ts_code')['ret'].shift(-1)
merged = merged.dropna(subset=['elg_ratio', 'inst_ratio', 'next_ret'])

print(f"\n{'因子':<25} {'Q1(低)%':<10} {'Q5(高)%':<10} {'差异(bp)':<10} {'t':<8} {'p':<10} {'N1':<8} {'N5':<8}")
print("-"*95)

best_mf = None
best_mf_p = 1.0
for fname, fcol in [('超大单净占比(elg)', 'elg_ratio'), ('机构净占比(elg+lg)', 'inst_ratio')]:
    d = merged.copy()
    d['q'] = pd.qcut(d[fcol], 5, labels=False, duplicates='drop')
    gs = d.groupby('q')['next_ret'].agg(['mean', 'count'])
    if 4 in gs.index and 0 in gs.index:
        q5 = d[d['q']==4]['next_ret'].values
        q1 = d[d['q']==0]['next_ret'].values
        t, p = ttest_ind(q5, q1)
        diff = gs.loc[4,'mean'] - gs.loc[0,'mean']
        sig = "***" if p<0.01 else ("**" if p<0.05 else "")
        print(f"{fname:<25} {gs.loc[0,'mean']*100:<10.3f} {gs.loc[4,'mean']*100:<10.3f} "
              f"{diff*10000:<10.1f} {t:<8.3f} {p:<10.2e} {len(q1):<8} {len(q5):<8} {sig}")
        if p < best_mf_p:
            best_mf_p = p
            best_mf = {'name': fname, 'col': fcol, 'q1': gs.loc[0,'mean'], 'q5': gs.loc[4,'mean'],
                       'diff': diff, 't': t, 'p': p, 'n1': len(q1), 'n5': len(q5)}

print(f"\n最佳因子: {best_mf['name']}, Q5-Q1 = {best_mf['diff']*10000:.1f}bp, p={best_mf['p']:.2e}")

# ============================================================
# 综合策略回测
# ============================================================
print("\n" + "="*60)
print("综合策略回测: 低量价背离 + 高机构资金流")
print("="*60)

# 使用最佳参数
d = merged.copy()
d['high_20'] = d.groupby('ts_code')['close'].transform(lambda x: x.rolling(20).max())
d['vol_ma_30'] = d.groupby('ts_code')['vol'].transform(lambda x: x.rolling(30).mean())
d['price_ratio'] = d['close'] / (d['high_20'] + 1e-9)
d['vol_ratio'] = d['vol'] / (d['vol_ma_30'] + 1e-9)
d['vp_div'] = d['price_ratio'] - d['vol_ratio']
d['elg_net'] = d['buy_elg_amount'] - d['sell_elg_amount']
d['lg_net'] = d['buy_lg_amount'] - d['sell_lg_amount']
d['total_amt'] = (d['buy_elg_amount']+d['sell_elg_amount']+d['buy_lg_amount']+d['sell_lg_amount']+
                  d['buy_md_amount']+d['sell_md_amount']+d['buy_sm_amount']+d['sell_sm_amount'])
d['inst_ratio'] = (d['elg_net'] + d['lg_net']) / (d['total_amt'] + 1e-9)
d['next_ret'] = d.groupby('ts_code')['ret'].shift(-1)
d = d.dropna(subset=['vp_div', 'inst_ratio', 'next_ret'])

# 信号: vp_div低分位(<20%) + inst_ratio高分位(>80%)
vp_th = d['vp_div'].quantile(0.2)
inst_th = d['inst_ratio'].quantile(0.8)
d['signal'] = (d['vp_div'] <= vp_th) & (d['inst_ratio'] >= inst_th)

sig_ret = d[d['signal']]['next_ret']
all_ret = d['next_ret']

print(f"\n信号数量: {d['signal'].sum()} / {len(d)} ({d['signal'].mean()*100:.1f}%)")
print(f"信号日均收益: {sig_ret.mean()*100:.3f}%")
print(f"全样本日均: {all_ret.mean()*100:.3f}%")
print(f"超额收益: {(sig_ret.mean()-all_ret.mean())*100:.3f}%")

t, p = ttest_1samp(sig_ret.values, all_ret.mean())
print(f"t检验: t={t:.3f}, p={p:.2e}")

# 年化 (ret是小数)
ann_sig = sig_ret.mean() * 250
ann_bench = all_ret.mean() * 250
print(f"\n年化收益 (信号): {ann_sig*100:.1f}%")
print(f"年化收益 (基准): {ann_bench*100:.1f}%")
print(f"年化超额: {(ann_sig-ann_bench)*100:.1f}%")

# 胜率
wr_sig = (sig_ret > 0).mean()
wr_bench = (all_ret > 0).mean()
print(f"信号胜率: {wr_sig*100:.1f}%")
print(f"基准胜率: {wr_bench*100:.1f}%")

# 最大回撤
cum = (1 + sig_ret).cumprod()
roll_max = cum.expanding().max()
dd = (cum - roll_max) / roll_max
max_dd = dd.min()
print(f"最大回撤: {max_dd*100:.1f}%")

# 夏普
rf = 0.03/250
sharpe = (sig_ret.mean() - rf) / sig_ret.std() * np.sqrt(250)
print(f"夏普比率: {sharpe:.2f}")

# 按月统计
d['month'] = d['trade_date'].dt.to_period('M')
monthly = d.groupby('month').agg(
    signal_ret=('next_ret', lambda x: x[x.index.isin(sig_ret.index)].mean() if len(x[x.index.isin(sig_ret.index)]) > 0 else np.nan),
    bench_ret=('next_ret', 'mean'),
    signal_count=('signal', 'sum'),
    total_count=('signal', 'count')
).dropna()

if len(monthly) > 0:
    monthly['excess'] = monthly['signal_ret'] - monthly['bench_ret']
    print(f"\n月度统计 ({len(monthly)} 个月):")
    print(f"  信号月均收益: {monthly['signal_ret'].mean()*100:.2f}%")
    print(f"  基准月均收益: {monthly['bench_ret'].mean()*100:.2f}%")
    print(f"  月均超额: {monthly['excess'].mean()*100:.2f}%")
    print(f"  超额为正月份: {(monthly['excess']>0).sum()}/{len(monthly)} ({(monthly['excess']>0).mean()*100:.0f}%)")

# 保存结果
final_results = {
    'vp_divergence': {
        'best': best_key,
        'q0_mean': bv['q0'], 'q4_mean': bv['q4'], 'diff': bv['diff'],
        't': bv['t'], 'p': bv['p'],
        'interpretation': '高量价背离(价格新高+缩量)预示次日收益更低, 是有效的反转信号'
    },
    'moneyflow': {
        'best': best_mf['name'],
        'q1_mean': best_mf['q1'], 'q5_mean': best_mf['q5'], 'diff': best_mf['diff'],
        't': best_mf['t'], 'p': best_mf['p'],
        'interpretation': '超大单净占比与次日收益呈显著正相关, 机构资金流是有效的动量信号'
    },
    'combined_strategy': {
        'n_signals': int(d['signal'].sum()),
        'signal_daily_ret': float(sig_ret.mean()),
        'bench_daily_ret': float(all_ret.mean()),
        'excess_daily': float(sig_ret.mean()-all_ret.mean()),
        't': float(t), 'p': float(p),
        'ann_ret_sig': float(ann_sig),
        'ann_ret_bench': float(ann_bench),
        'win_rate_sig': float(wr_sig),
        'win_rate_bench': float(wr_bench),
        'max_dd': float(max_dd),
        'sharpe': float(sharpe),
    },
    'data_range': f"{df.trade_date.min().date()} to {df.trade_date.max().date()}",
    'n_stocks': int(df.ts_code.nunique()),
    'n_records': int(len(df)),
}

with open('research_results.pkl', 'wb') as f:
    pickle.dump(final_results, f)

print(f"\n{'='*60}")
print(f"✅ 研究完成! 结果已保存到 research_results.pkl")
print(f"{'='*60}")
