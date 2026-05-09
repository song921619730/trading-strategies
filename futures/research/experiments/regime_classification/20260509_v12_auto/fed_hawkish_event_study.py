# -*- coding: utf-8 -*-
"""
实验 v12: 美联储鹰派信号对14品种跨资产冲击研究
H1: 鹰派信号对跨资产影响存在显著分化 — 鹰派初期美元↑/黄金↓/股指↓，
    但当叠加地缘冲突时，黄金-美元正相关(避险溢价覆盖利率效应)
H2: "软滞胀"环境(高油价+不降息+就业尚可)下，贵金属+原油跑赢股指+外汇
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ========== 配置 ==========
SYMBOLS = [
    'XAUUSDm', 'XAGUSDm',           # 贵金属
    'EURUSDm', 'GBPUSDm', 'USDJPYm', 'AUDUSDm', 'USDCHFm',  # 外汇
    'USOILm', 'UKOILm',              # 原油
    'USTECm', 'US30m', 'US500m',    # 美股指数
    'JP225m', 'HK50m',              # 亚太股指
]

# 按相关性分组
GROUPS = {
    '贵金属': ['XAUUSDm', 'XAGUSDm'],
    'USD空头': ['EURUSDm', 'GBPUSDm', 'AUDUSDm'],
    'USD多头': ['USDJPYm', 'USDCHFm'],
    '原油': ['USOILm', 'UKOILm'],
    '美股指数': ['USTECm', 'US30m', 'US500m'],
    '亚太股指': ['JP225m', 'HK50m'],
}

# ========== 步骤1: 初始化MT5 ==========
print("=" * 60)
print("实验 v12: 美联储鹰派信号跨资产冲击研究")
print("=" * 60)

if not mt5.initialize():
    print(f"MT5初始化失败: {mt5.last_error()}")
    exit(1)
print("✅ MT5初始化成功")

# ========== 步骤2: 获取全部14品种D1历史数据 ==========
print("\n📥 获取历史K线数据...")
data_dict = {}
for sym in SYMBOLS:
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
    if rates is None or len(rates) == 0:
        print(f"  ⚠️ {sym}: 无数据")
        continue
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['return'] = df['close'].pct_change()
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    df['atr14'] = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    df = df.set_index('time')
    data_dict[sym] = df
    print(f"  ✅ {sym}: {len(df)} bars ({df.index.min().date()} ~ {df.index.max().date()})")

# ========== 步骤3: 构建美联储鹰派事件时间线 ==========
print("\n📰 构建美联储鹰派事件时间线...")

# 基于News Pipeline和公开信息构建事件日历
# 鹰派信号关键词: "加息", "不降息", "hawkish", "rate hike", "higher for longer"
# 数据源: News Pipeline API + 手动构建关键事件

import requests

# 从News Pipeline搜索美联储相关新闻
def search_fed_news(keywords, months=24):
    """从News Pipeline搜索美联储相关历史新闻"""
    events = []
    for kw in keywords:
        try:
            r = requests.get(
                f"http://127.0.0.1:8900/api/v1/news/query",
                params={'symbol': kw, 'limit': 200},
                timeout=10
            )
            if r.status_code == 200:
                items = r.json().get('items', [])
                for item in items:
                    pub = item.get('published_at', '') or item.get('created_at', '') or item.get('time', '')
                    if pub:
                        events.append({
                            'date': str(pub)[:10],
                            'title': item.get('title', ''),
                            'keyword': kw,
                            'source': item.get('source', ''),
                        })
        except:
            pass
    if not events:
        return pd.DataFrame(columns=['date', 'title', 'keyword', 'source'])
    return pd.DataFrame(events).drop_duplicates().sort_values('date')

# 搜索关键词
fed_keywords = ['美联储', '加息', '降息', 'FOMC', '鲍威尔', '利率']
news_df = search_fed_news(fed_keywords)
print(f"  搜索到 {len(news_df)} 条美联储相关新闻")

# 手动构建关键鹰派事件时间线 (基于Brief中的新闻 + 已知重大事件)
hawkish_events = [
    # 格式: (date, event_name, severity 1-3)
    # 2026年事件 (来自Brief)
    ('2026-05-09', '美银修正:2027年前不降息 + 古尔斯比加息选项上桌 + 非农超预期', 3),
    ('2026-05-09', '拉加德:权衡伊朗冲突对通胀影响', 2),
    # 2026年其他已知鹰派事件
    ('2026-05-08', '4月非农+11.5万超预期(预期5.5万)', 2),
    ('2026-05-07', '美联储FOMC维持利率不变+声明偏鹰', 2),
    ('2026-04-30', '美伊冲突升级+油价飙升', 2),
    ('2026-04-15', 'CPI超预期+核心通胀粘性', 2),
    ('2026-03-19', 'FOMC点阵图上移:2026年仅1次降息预期', 3),
    ('2026-03-10', '鲍威尔国会证词:不急于降息', 2),
    ('2026-02-27', 'PCE通胀超预期反弹', 2),
    ('2026-02-12', '1月CPI同比+3.0%超预期', 2),
    ('2026-01-29', 'FOMC维持利率不变+删除宽松偏向', 3),
    ('2025-12-18', 'FOMC降息25bp但点阵图显示2025年仅2次', 2),
    ('2025-11-07', '非农+22.7万超预期,降息预期降温', 2),
    ('2025-09-18', 'FOMC降息50bp但声明暗示暂停', 1),
    ('2025-07-31', 'FOMC降息25bp(年内首次)', 1),
    # 2025年鹰派事件
    ('2025-06-12', 'CPI反弹+FOMC不降息', 2),
    ('2025-05-01', 'FOMC维持利率,鲍威尔偏鹰', 2),
    ('2025-03-19', 'FOMC按兵不动+点阵图鹰派', 2),
    ('2025-01-29', 'FOMC暂停降息+通胀担忧', 2),
    # 2024年鹰派事件
    ('2024-12-18', 'FOMC降息但暗示2025年放缓', 1),
    ('2024-11-07', '降息25bp但声明偏鹰', 1),
    ('2024-09-18', 'FOMC大幅降息50bp', 1),
    ('2024-07-31', 'FOMC暗示9月降息', 1),
    ('2024-06-12', 'FOMC维持利率+点阵图上移', 2),
    ('2024-04-10', 'CPI超预期反弹,降息预期推迟', 2),
    ('2024-03-20', 'FOMC维持利率+鹰派点阵图', 3),
    ('2024-01-31', 'FOMC维持利率+排除3月降息', 2),
    # 2023年鹰派事件
    ('2023-12-13', 'FOMC暂停加息但暗示高位维持', 2),
    ('2023-11-01', 'FOMC暂停加息', 1),
    ('2023-09-20', 'FOMC维持利率+鹰派点阵图', 2),
    ('2023-07-26', 'FOMC加息25bp至5.25-5.50%', 3),
    ('2023-06-14', 'FOMC暂停加息但暗示还会加', 2),
    ('2023-05-03', 'FOMC加息25bp', 3),
    ('2023-03-22', 'FOMC加息25bp(银行危机期间)', 2),
    ('2023-02-01', 'FOMC加息25bp', 3),
    # 2022年鹰派事件
    ('2022-12-14', 'FOMC加息50bp+鹰派点阵图', 3),
    ('2022-11-02', 'FOMC加息75bp', 3),
    ('2022-09-21', 'FOMC加息75bp+鹰派点阵图', 3),
    ('2022-07-27', 'FOMC加息100bp', 3),
    ('2022-06-15', 'FOMC加息75bp(1994年来最大)', 3),
    ('2022-05-04', 'FOMC加息50bp(2000年来首次)', 3),
    ('2022-03-16', 'FOMC启动加息周期(+25bp)', 3),
]

hawkish_df = pd.DataFrame(hawkish_events, columns=['date', 'event', 'severity'])
hawkish_df['date'] = pd.to_datetime(hawkish_df['date'])
hawkish_df = hawkish_df.sort_values('date')
print(f"  构建了 {len(hawkish_df)} 个鹰派事件")
print(f"  时间范围: {hawkish_df['date'].min().date()} ~ {hawkish_df['date'].max().date()}")
print(f"  Severity分布: 1={sum(hawkish_df['severity']==1)}, 2={sum(hawkish_df['severity']==2)}, 3={sum(hawkish_df['severity']==3)}")

# ========== 步骤4: 事件研究 (Event Study) ==========
print("\n🔬 执行事件研究...")

def event_study(hawkish_df, data_dict, window_before=5, window_after=10):
    """
    事件研究: 计算鹰派事件前后各品种的累计收益
    """
    results = {}
    
    for sym in SYMBOLS:
        if sym not in data_dict:
            continue
        
        price_data = data_dict[sym]['return'].copy()
        
        event_returns = []
        for _, event in hawkish_df.iterrows():
            event_date = event['date']
            # 确保事件日期在数据范围内
            if event_date not in price_data.index:
                # 找最接近的日期
                available = price_data.index
                idx = available.searchsorted(event_date)
                if idx >= len(available):
                    continue
                event_date = available[idx]
            
            # 检查窗口是否在数据范围内
            all_dates = price_data.index
            try:
                event_idx = all_dates.get_loc(event_date)
            except KeyError:
                continue
                
            start_idx = max(0, event_idx - window_before)
            end_idx = min(len(all_dates) - 1, event_idx + window_after)
            
            if end_idx - start_idx < window_before + window_after:
                continue
            
            window_returns = price_data.iloc[start_idx:end_idx + 1].values
            cum_returns = np.cumprod(1 + window_returns) - 1
            
            event_returns.append({
                'date': event_date,
                'severity': event['severity'],
                'event': event['event'][:50],
                'window_returns': window_returns,
                'cum_returns': cum_returns,
                'pre_return': cum_returns[window_before - 1] if window_before <= len(cum_returns) else np.nan,
                'post_1d': window_returns[window_before] if window_before < len(window_returns) else np.nan,
                'post_3d': cum_returns[window_before + 2] - cum_returns[window_before - 1] if window_before + 2 < len(cum_returns) else np.nan,
                'post_5d': cum_returns[window_before + 4] - cum_returns[window_before - 1] if window_before + 4 < len(cum_returns) else np.nan,
                'post_10d': cum_returns[-1] - cum_returns[window_before - 1] if len(cum_returns) > window_before + 9 else np.nan,
            })
        
        results[sym] = pd.DataFrame(event_returns)
    
    return results

event_results = event_study(hawkish_df, data_dict, window_before=5, window_after=10)

# ========== 步骤5: 汇总分析 ==========
print("\n📊 汇总分析...")

# 按品种组汇总
group_results = {}
for group_name, syms in GROUPS.items():
    valid_syms = [s for s in syms if s in event_results and len(event_results[s]) > 0]
    if not valid_syms:
        continue
    
    # 合并所有事件的结果
    post_1d_list = []
    post_5d_list = []
    for sym in valid_syms:
        df = event_results[sym]
        if 'post_1d' in df.columns:
            post_1d_list.append(df['post_1d'].dropna())
        if 'post_5d' in df.columns:
            post_5d_list.append(df['post_5d'].dropna())
    
    if post_1d_list:
        all_post_1d = pd.concat(post_1d_list)
        all_post_5d = pd.concat(post_5d_list) if post_5d_list else pd.Series(dtype=float)
        
        from scipy import stats
        t_1d, p_1d = stats.ttest_1samp(all_post_1d.dropna(), 0)
        t_5d, p_5d = stats.ttest_1samp(all_post_5d.dropna(), 0) if len(all_post_5d) > 1 else (np.nan, np.nan)
        
        group_results[group_name] = {
            'n_events': len(all_post_1d),
            'post_1d_mean': all_post_1d.mean(),
            'post_1d_std': all_post_1d.std(),
            'post_1d_t': t_1d,
            'post_1d_p': p_1d,
            'post_5d_mean': all_post_5d.mean() if len(all_post_5d) > 0 else np.nan,
            'post_5d_std': all_post_5d.std() if len(all_post_5d) > 0 else np.nan,
            'post_5d_t': t_5d,
            'post_5d_p': p_5d,
            'hit_rate_1d': (all_post_1d > 0).mean(),
            'hit_rate_5d': (all_post_5d > 0).mean() if len(all_post_5d) > 0 else np.nan,
        }

print("\n📋 各组别鹰派事件后平均收益:")
print(f"{'品种组':<12} | {'N':>4} | {'1D收益%':>8} | {'p值':>8} | {'5D收益%':>8} | {'p值':>8} | {'1D胜率%':>8}")
print("-" * 80)
for group_name, stats_data in group_results.items():
    print(f"{group_name:<12} | {stats_data['n_events']:4.0f} | {stats_data['post_1d_mean']*100:>8.3f} | {stats_data['post_1d_p']:>8.4f} | {stats_data['post_5d_mean']*100:>8.3f} | {stats_data['post_5d_p']:>8.4f} | {stats_data['hit_rate_1d']*100:>8.1f}")

# ========== 步骤6: 按严重性分层分析 ==========
print("\n📋 按严重性分层 (按Severity分组):")

for severity in [1, 2, 3]:
    sev_events = hawkish_df[hawkish_df['severity'] == severity]
    print(f"\n  Severity {severity} ({len(sev_events)} events):")
    for sym in ['XAUUSDm', 'EURUSDm', 'USTECm', 'USOILm']:
        if sym not in event_results or len(event_results[sym]) == 0:
            continue
        # 匹配对应severity的事件
        sev_dates = set(sev_events['date'].dt.strftime('%Y-%m-%d'))
        sym_df = event_results[sym]
        if 'date' not in sym_df.columns:
            continue
        sym_df_dates = sym_df['date'].dt.strftime('%Y-%m-%d')
        matched = sym_df[sym_df_dates.isin(sev_dates)]
        if len(matched) > 2:
            mean_1d = matched['post_1d'].mean() * 100 if 'post_1d' in matched.columns else np.nan
            mean_5d = matched['post_5d'].mean() * 100 if 'post_5d' in matched.columns else np.nan
            p_1d = stats.ttest_1samp(matched['post_1d'].dropna(), 0)[1] if 'post_1d' in matched.columns else np.nan
            print(f"    {sym:<10}: 1D={mean_1d:>+7.3f}% (p={p_1d:.4f}), 5D={mean_5d:>+7.3f}%")

# ========== 步骤7: 构建"滞胀环境"识别 ==========
print("\n🔬 步骤7: 滞胀环境识别与品种表现...")

# 定义滞胀环境: 油价高位(20日MA > 80) + 鹰派事件密集期(30天内>=2个severity>=2事件)
# 简化: 使用高油价+鹰派事件窗口

# 获取油价数据
if 'UKOILm' in data_dict:
    oil = data_dict['UKOILm'].copy()
    oil['oil_ma20'] = oil['close'].rolling(20).mean()
    oil['high_oil'] = oil['oil_ma20'] > 80  # 布油20日均线>80视为高油价
    
    # 高油价天数
    high_oil_days = oil['high_oil'].sum()
    total_days = len(oil)
    print(f"  高油价期(布油MA20>80): {high_oil_days}/{total_days} 天 ({high_oil_days/total_days*100:.1f}%)")
    
    # 在高油价期内，各品种表现
    print(f"\n  高油价期内各品种年化收益:")
    print(f"  {'品种':<12} | {'年化收益%':>10} | {'夏普':>8} | {'最大回撤%':>10} | {'胜率%':>8}")
    print("  " + "-" * 65)
    
    for sym in SYMBOLS:
        if sym not in data_dict:
            continue
        sym_data = data_dict[sym].copy()
        
        # 对齐日期
        common_dates = oil.index.intersection(sym_data.index)
        if len(common_dates) < 30:
            continue
            
        oil_mask = oil.loc[common_dates, 'high_oil'].values
        sym_returns = sym_data.loc[common_dates, 'return'].values
        
        high_oil_returns = sym_returns[oil_mask]
        normal_returns = sym_returns[~oil_mask]
        
        if len(high_oil_returns) < 10:
            continue
        
        # 年化收益
        ann_return = (1 + high_oil_returns.mean()) ** 252 - 1
        sharpe = high_oil_returns.mean() / high_oil_returns.std() * np.sqrt(252) if high_oil_returns.std() > 0 else 0
        
        # 最大回撤
        cum = np.cumprod(1 + high_oil_returns)
        peak = np.maximum.accumulate(cum)
        max_dd = (cum / peak - 1).min()
        
        hit_rate = (high_oil_returns > 0).mean() * 100
        
        print(f"  {sym:<12} | {ann_return*100:>10.2f} | {sharpe:>8.2f} | {max_dd*100:>10.2f} | {hit_rate:>8.1f}")

# ========== 步骤8: 鹰派事件+高油价交叉分析 ==========
print("\n🔬 步骤8: 鹰派+高油价交叉分析...")

# 在鹰派事件窗口内(后5天)且高油价期间的表现
print(f"\n  鹰派事件后5天 × 高油价期 交叉矩阵:")
print(f"  {'品种':<12} | {'非高油价1D%':>12} | {'高油价1D%':>12} | {'差异p值':>10}")
print("  " + "-" * 60)

from scipy.stats import ttest_ind

for sym in SYMBOLS:
    if sym not in event_results or len(event_results[sym]) == 0:
        continue
    if sym not in data_dict:
        continue
        
    ev_df = event_results[sym].copy()
    if 'date' not in ev_df.columns or 'post_1d' not in ev_df.columns:
        continue
    
    # 获取油价状态
    oil_data = data_dict.get('UKOILm')
    if oil_data is None:
        continue
        
    normal_1d = []
    high_oil_1d = []
    
    for _, row in ev_df.iterrows():
        ev_date = row['date']
        post_1d = row.get('post_1d', np.nan)
        if np.isnan(post_1d):
            continue
        
        # 检查事件当天油价状态 - oil_data has DatetimeIndex
        mask = oil_data.index <= ev_date
        if mask.sum() == 0:
            continue
        last_oil = oil_data.loc[mask].iloc[-1]
        oil_status = last_oil.get('high_oil', False)
        
        if oil_status:
            high_oil_1d.append(post_1d)
        else:
            normal_1d.append(post_1d)
    
    if len(normal_1d) > 2 and len(high_oil_1d) > 2:
        norm_mean = np.mean(normal_1d) * 100
        high_mean = np.mean(high_oil_1d) * 100
        _, p_val = ttest_ind(normal_1d, high_oil_1d)
        print(f"  {sym:<12} | {norm_mean:>12.3f} | {high_mean:>12.3f} | {p_val:>10.4f}")

# ========== 步骤9: 保存结果 ==========
print("\n💾 保存中间结果...")
import json

# 保存汇总统计
summary = {
    'group_results': {},
    'high_oil_results': {},
}

for group_name, s in group_results.items():
    summary['group_results'][group_name] = {k: float(v) if not np.isnan(v) else None for k, v in s.items()}

# 保存到文件
with open('event_study_summary.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

print("✅ 中间结果已保存")
print("\n" + "=" * 60)
print("事件研究完成")
print("=" * 60)

mt5.shutdown()
print("✅ MT5已关闭")
