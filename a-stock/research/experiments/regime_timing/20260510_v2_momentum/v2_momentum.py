"""
V2: 择时+动量策略 — 降低换手率, 加入交易成本
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

RESULTS_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/市场择时信号_(market_regime_timing)/20260510_v2_momentum/'

print("=" * 70)
print("V2: 择时+动量策略 — 降低换手率版")
print("=" * 70)

# 加载数据
t0 = time.time()
print("\n[1/3] 加载数据...")

sql = """
SELECT ts_code, trade_date, close, pct_chg
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20200101'
ORDER BY ts_code, trade_date
"""
df = ck_query(sql)
df['close'] = pd.to_numeric(df['close'], errors='coerce')
df['pct_chg'] = pd.to_numeric(df['pct_chg'], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

# 指数
sql_idx = """
SELECT trade_date, close
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000300.SH' AND trade_date >= '20190101'
ORDER BY trade_date
"""
df_idx = ck_query(sql_idx)
df_idx['close'] = pd.to_numeric(df_idx['close'], errors='coerce')
df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])
df_idx['ma200'] = df_idx['close'].rolling(200, min_periods=100).mean()
df_idx['bull'] = df_idx['close'] > df_idx['ma200']

# 合并择时信号
df = df.merge(df_idx[['trade_date','bull']], on='trade_date', how='left')

print(f"  数据: {len(df):,} 行, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 计算动量 (多窗口)
# ============================================================
t0 = time.time()
print("\n[2/3] 计算动量...")

for window in [5, 10, 20, 60]:
    df[f'mom_{window}'] = df.groupby('ts_code')['close'].transform(lambda x: x.pct_change(window))

# 交易日期列表
trade_dates = sorted(df['trade_date'].unique())
print(f"  交易日: {len(trade_dates)} 天, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 回测: 周度再平衡
# ============================================================
print("\n" + "=" * 70)
print("📊 周度再平衡回测")
print("=" * 70)

TRANSACTION_COST = 0.0015  # 单边0.15% (佣金+印花税+滑点)

strategies = {}

for mom_window in [5, 10, 20, 60]:
    for top_pct in [0.05, 0.10, 0.20, 0.30]:
        name = f'MOM{mom_window}_TOP{int(top_pct*100)}%'
        
        portfolio_value = 1.0
        holdings = []  # list of ts_code
        weekly_counter = 0
        returns = []
        
        for date in trade_dates:
            date_data = df[df['trade_date'] == date]
            if len(date_data) == 0:
                continue
            
            is_bull = date_data['bull'].iloc[0] if len(date_data) > 0 else False
            if pd.isna(is_bull):
                is_bull = False
            
            # 每周再平衡 (每5个交易日)
            weekly_counter += 1
            should_rebalance = (weekly_counter >= 5)
            
            if should_rebalance:
                weekly_counter = 0
                
                if is_bull:
                    # 牛市: 选动量前top_pct
                    valid = date_data[date_data[f'mom_{mom_window}'].notna()]
                    if len(valid) > 0:
                        valid = valid.sort_values(f'mom_{mom_window}', ascending=False)
                        n_stocks = max(1, int(len(valid) * top_pct))
                        new_holdings = set(valid.head(n_stocks)['ts_code'].values)
                        
                        # 计算换手成本
                        if holdings:
                            sold = set(holdings) - new_holdings
                            bought = new_holdings - set(holdings)
                            turnover = max(len(sold), len(bought)) / max(len(holdings), 1)
                            cost = turnover * TRANSACTION_COST * 2  # 买入+卖出
                            portfolio_value *= (1 - cost)
                        
                        holdings = list(new_holdings)
                    else:
                        holdings = []
                else:
                    # 熊市: 空仓
                    if holdings:
                        cost = TRANSACTION_COST  # 卖出成本
                        portfolio_value *= (1 - cost)
                    holdings = []
            
            # 计算当日组合收益
            if holdings:
                held = date_data[date_data['ts_code'].isin(holdings)]
                day_ret = held['pct_chg'].mean() / 100
                portfolio_value *= (1 + day_ret)
            
            returns.append({
                'trade_date': date,
                'value': portfolio_value,
                'n_holdings': len(holdings),
                'is_bull': is_bull,
            })
        
        df_ret = pd.DataFrame(returns)
        if len(df_ret) == 0:
            continue
        
        # 年化
        n_years = (df_ret['trade_date'].iloc[-1] - df_ret['trade_date'].iloc[0]).days / 365.25
        total_ret = df_ret['value'].iloc[-1] - 1
        ann_ret = (df_ret['value'].iloc[-1] ** (1/n_years) - 1) * 100
        
        # 最大回撤
        cummax = df_ret['value'].cummax()
        max_dd = ((df_ret['value'] - cummax) / cummax).min() * 100
        
        # 分年度
        df_ret['year'] = df_ret['trade_date'].dt.year
        by_year = {}
        for y in sorted(df_ret['year'].unique()):
            ysub = df_ret[df_ret['year'] == y]
            y_ret = (ysub['value'].iloc[-1] / ysub['value'].iloc[0] - 1) * 100
            by_year[int(y)] = round(y_ret, 2)
        
        strategies[name] = {
            'ann_ret': round(ann_ret, 2),
            'total_ret': round(total_ret * 100, 2),
            'max_dd': round(max_dd, 2),
            'avg_holdings': round(df_ret['n_holdings'].mean(), 0),
            'bull_pct': round(df_ret['is_bull'].mean() * 100, 1),
            'by_year': by_year,
        }

# 排序
sorted_strats = sorted(strategies.items(), key=lambda x: x[1]['ann_ret'], reverse=True)

print(f"\n{'策略':<25} {'年化收益':>10} {'总收益':>10} {'最大回撤':>10} {'平均持仓':>10}")
print("-" * 70)
for name, r in sorted_strats[:10]:
    print(f"{name:<25} {r['ann_ret']:>9.2f}% {r['total_ret']:>9.2f}% {r['max_dd']:>9.2f}% {r['avg_holdings']:>10.0f}")

# ============================================================
# 最佳策略详细
# ============================================================
best_name, best_r = sorted_strats[0]
print(f"\n🏆 最佳: {best_name}")
print(f"  年化: {best_r['ann_ret']}%")
print(f"  总收益: {best_r['total_ret']}%")
print(f"  最大回撤: {best_r['max_dd']}%")
print(f"  分年度:")
for y, ret in best_r['by_year'].items():
    print(f"    {y}: {ret}%")

# ============================================================
# 对比: 纯基准 vs 纯动量 vs 择时+动量
# ============================================================
print("\n" + "=" * 70)
print("📊 三策略对比")
print("=" * 70)

# 基准: 等权持有所有股票
ew_daily = df.groupby('trade_date')['pct_chg'].mean() / 100
ew_cum = (1 + ew_daily).cumprod()
ew_ann = (ew_cum.iloc[-1] ** (1/n_years) - 1) * 100

print(f"\n  等权基准: 年化 {ew_ann:.2f}%")
print(f"  最佳择时+动量: 年化 {best_r['ann_ret']}%")
print(f"  超额: {best_r['ann_ret'] - ew_ann:.2f}%")

# ============================================================
# 保存
# ============================================================
with open(RESULTS_DIR + 'summary.json', 'w') as f:
    json.dump({
        'strategies': dict(sorted_strats[:15]),
        'best': best_name,
        'benchmark_ann': round(ew_ann, 2),
    }, f, indent=2, ensure_ascii=False)

print("\n✅ V2 研究完成!")
