#!/usr/bin/env python3
"""
低开高走模式识别 - 阶段1：基础统计与筛选因子
使用简化SQL避免ClickHouse兼容性问题
"""

import requests
import pandas as pd
import numpy as np
import json

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames', timeout=120):
    full_query = f"{query} FORMAT {fmt}"
    r = requests.get(CH_URL, params={'query': full_query}, auth=CH_AUTH, timeout=timeout)
    if r.status_code != 200:
        raise Exception(f"Query failed: {r.text[:500]}")
    return r.text

def parse_tab(text):
    lines = text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    rows = [line.split('\t') for line in lines[1:]]
    df = pd.DataFrame(rows, columns=cols)
    return df

def num_cols(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

results = {}

# ============================================================
# 分析1: 全局统计
# ============================================================
print("【分析1】全局低开高走频率统计...")
q1 = """
SELECT 
    count() as total,
    round(sum(lo) / count() * 100, 2) as lo_pct,
    round(sum(hg) / count() * 100, 2) as hg_pct,
    round(sum(strong) / count() * 100, 2) as strong_pct,
    round(sum(lo AND hg) / greatest(sum(lo),1) * 100, 2) as cond_hg_given_lo,
    round(sum(strong) / greatest(sum(lo),1) * 100, 2) as cond_strong_given_lo
FROM (
    SELECT 
        if((open - pre_close) / pre_close * 100 < -1, 1, 0) as lo,
        if((close - open) / open * 100 > 2, 1, 0) as hg,
        if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2 AND close > pre_close, 1, 0) as strong
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260507'
      AND pre_close > 0 AND open > 0 AND close > 0
)
"""
df1 = parse_tab(ch_query(q1))
num_cols(df1, ['total','lo_pct','hg_pct','strong_pct','cond_hg_given_lo','cond_strong_given_lo'])
print(df1.to_string(index=False))
results['global'] = df1.iloc[0].to_dict()

# ============================================================
# 分析2: 按前日涨跌幅分组
# ============================================================
print("\n【分析2】按前日涨跌幅分组...")
q2 = """
WITH d AS (
    SELECT 
        ts_code, trade_date, open, close, pre_close, pct_chg,
        lagInFrame(pct_chg, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as pp
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260507'
      AND pre_close > 0 AND open > 0 AND close > 0
)
SELECT 
    g, cnt,
    round(lo / cnt * 100, 2) as lo_pct,
    round(lo_hg / greatest(lo,1) * 100, 2) as lo_hg_rate,
    round(strong / greatest(lo,1) * 100, 2) as strong_rate
FROM (
    SELECT 
        multiIf(pp >= 9.5, '涨停', pp >= 5, '大涨5%+', pp >= 2, '涨2-5%', pp >= -2, '平盘±2%', pp >= -5, '跌2-5%', pp >= -9.5, '大跌5%+', '跌停') as g,
        count() as cnt,
        sum(if((open - pre_close) / pre_close * 100 < -1, 1, 0)) as lo,
        sum(if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2, 1, 0)) as lo_hg,
        sum(if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2 AND close > pre_close, 1, 0)) as strong
    FROM d WHERE pp IS NOT NULL
    GROUP BY g
)
ORDER BY g
"""
df2 = parse_tab(ch_query(q2))
print(df2.to_string(index=False))
results['by_prev_pct'] = df2.to_dict('records')

# ============================================================
# 分析3: 按前日成交量变化分组
# ============================================================
print("\n【分析3】按前日成交量变化分组...")
q3 = """
WITH d AS (
    SELECT 
        ts_code, trade_date, open, close, pre_close, vol,
        lagInFrame(vol, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as pv
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260507'
      AND pre_close > 0 AND open > 0 AND close > 0 AND vol > 0
)
SELECT 
    g, cnt,
    round(lo / cnt * 100, 2) as lo_pct,
    round(lo_hg / greatest(lo,1) * 100, 2) as lo_hg_rate,
    round(strong / greatest(lo,1) * 100, 2) as strong_rate
FROM (
    SELECT 
        multiIf(pv > 0 AND vol/pv >= 3, '放量3x+', pv > 0 AND vol/pv >= 2, '放量2-3x', pv > 0 AND vol/pv >= 1.5, '放量1.5-2x', pv > 0 AND vol/pv >= 0.8, '正常0.8-1.5x', pv > 0 AND vol/pv >= 0.5, '缩量0.5-0.8x', '极度缩量<0.5x') as g,
        count() as cnt,
        sum(if((open - pre_close) / pre_close * 100 < -1, 1, 0)) as lo,
        sum(if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2, 1, 0)) as lo_hg,
        sum(if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2 AND close > pre_close, 1, 0)) as strong
    FROM d
    GROUP BY g
)
ORDER BY g
"""
df3 = parse_tab(ch_query(q3))
print(df3.to_string(index=False))
results['by_volume'] = df3.to_dict('records')

# ============================================================
# 分析4: 按换手率分组
# ============================================================
print("\n【分析4】按前日换手率分组...")
q4 = """
SELECT 
    g, cnt,
    round(lo / cnt * 100, 2) as lo_pct,
    round(lo_hg / greatest(lo,1) * 100, 2) as lo_hg_rate,
    round(strong / greatest(lo,1) * 100, 2) as strong_rate
FROM (
    SELECT 
        multiIf(ptr >= 15, '极高>15%', ptr >= 10, '高10-15%', ptr >= 5, '中5-10%', ptr >= 2, '低2-5%', ptr > 0, '极低<2%', '未知') as g,
        count() as cnt,
        sum(if((open - pre_close) / pre_close * 100 < -1, 1, 0)) as lo,
        sum(if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2, 1, 0)) as lo_hg,
        sum(if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2 AND close > pre_close, 1, 0)) as strong
    FROM (
        SELECT 
            tushare_stock_daily.open, tushare_stock_daily.close, tushare_stock_daily.pre_close,
            lagInFrame(tushare_daily_basic.turnover_rate, 1) OVER (PARTITION BY tushare_stock_daily.ts_code ORDER BY tushare_stock_daily.trade_date) as ptr
        FROM tushare.tushare_stock_daily FINAL
        INNER JOIN tushare.tushare_daily_basic FINAL ON tushare_stock_daily.ts_code = tushare_daily_basic.ts_code AND tushare_stock_daily.trade_date = tushare_daily_basic.trade_date
        WHERE tushare_stock_daily.trade_date >= '20200101' AND tushare_stock_daily.trade_date <= '20260507'
          AND tushare_stock_daily.pre_close > 0 AND tushare_stock_daily.open > 0 AND tushare_stock_daily.close > 0
    ) WHERE ptr IS NOT NULL AND ptr > 0
    GROUP BY g
)
ORDER BY g
"""
df4 = parse_tab(ch_query(q4))
print(df4.to_string(index=False))
results['by_turnover'] = df4.to_dict('records')

# ============================================================
# 分析5: 按月份分析季节性
# ============================================================
print("\n【分析5】按月分析...")
q5 = """
SELECT 
    toMonth(toDate(trade_date)) as month,
    count() as cnt,
    round(sum(lo) / cnt * 100, 2) as lo_pct,
    round(sum(lo AND hg) / greatest(sum(lo),1) * 100, 2) as lo_hg_rate,
    round(sum(strong) / greatest(sum(lo),1) * 100, 2) as strong_rate
FROM (
    SELECT trade_date,
        if((open - pre_close) / pre_close * 100 < -1, 1, 0) as lo,
        if((close - open) / open * 100 > 2, 1, 0) as hg,
        if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2 AND close > pre_close, 1, 0) as strong
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260507'
      AND pre_close > 0 AND open > 0 AND close > 0
)
GROUP BY month ORDER BY month
"""
df5 = parse_tab(ch_query(q5))
print(df5.to_string(index=False))
results['by_month'] = df5.to_dict('records')

# ============================================================
# 分析6: 按市场环境 (用上证指数30日涨跌定义)
# ============================================================
print("\n【分析6】按市场环境分析...")
# 先获取上证指数 (用 index_daily 表)
sh_q = """
SELECT trade_date, close, pct_chg
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000001.SH' AND trade_date >= '20200101' AND trade_date <= '20260507'
  AND close > 0
ORDER BY trade_date
"""
sh_df = parse_tab(ch_query(sh_q))
print(f"上证指数数据行数: {len(sh_df)}")
if len(sh_df) == 0:
    # 尝试其他指数
    sh_q2 = """
    SELECT trade_date, close, pct_chg
    FROM tushare.tushare_index_daily FINAL
    WHERE ts_code IN ('000300.SH', '000001.SZ') AND trade_date >= '20200101' AND trade_date <= '20260507'
      AND close > 0
    ORDER BY trade_date
    """
    sh_df = parse_tab(ch_query(sh_q2))
    print(f"尝试沪深300数据行数: {len(sh_df)}")

sh_df = num_cols(sh_df, ['close', 'pct_chg'])
sh_df['close'] = pd.to_numeric(sh_df['close'])
sh_df['roll20'] = sh_df['close'].pct_change(20)
sh_df['regime'] = pd.qcut(sh_df['roll20'].dropna(), q=3, labels=['熊市','震荡','牛市'], duplicates='drop')
regime_map = dict(zip(sh_df['trade_date'], sh_df['regime']))

# 抽样个股数据并映射市场环境
q6 = """
SELECT ts_code, trade_date, open, close, pre_close, pct_chg
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20200101' AND trade_date <= '20260507'
  AND pre_close > 0 AND open > 0 AND close > 0
  AND rand() % 30 = 0
"""
df6 = num_cols(parse_tab(ch_query(q6)), ['open','close','pre_close','pct_chg'])
df6['lo'] = ((df6['open'] - df6['pre_close']) / df6['pre_close'] * 100 < -1).astype(int)
df6['hg'] = ((df6['close'] - df6['open']) / df6['open'] * 100 > 2).astype(int)
df6['strong'] = ((df6['open'] - df6['pre_close']) / df6['pre_close'] * 100 < -1).astype(int) & \
                ((df6['close'] - df6['open']) / df6['open'] * 100 > 2).astype(int) & \
                (df6['close'] > df6['pre_close']).astype(int)
df6['regime'] = df6['trade_date'].map(regime_map)
df6 = df6.dropna(subset=['regime'])

regime_stats = df6.groupby('regime').agg(
    cnt=('ts_code','count'),
    lo_pct=('lo','mean'),
    lo_hg_rate=('hg', lambda x: (x * df6.loc[x.index,'lo']).sum() / max(df6.loc[x.index,'lo'].sum(),1)),
    strong_rate=('strong', lambda x: (x * df6.loc[x.index,'lo']).sum() / max(df6.loc[x.index,'lo'].sum(),1)),
)
print(regime_stats)
results['by_regime'] = regime_stats.to_dict()

# ============================================================
# 分析7: 行业板块偏好
# ============================================================
print("\n【分析7】行业板块分析...")
# 获取行业信息
ind_q = "SELECT ts_code, industry, name FROM tushare.tushare_stock_basic FINAL WHERE industry != '' AND industry IS NOT NULL"
ind_df = parse_tab(ch_query(ind_q))

# 抽样数据
q7 = """
SELECT ts_code, trade_date, open, close, pre_close
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20200101' AND trade_date <= '20260507'
  AND pre_close > 0 AND open > 0 AND close > 0
  AND rand() % 15 = 0
"""
df7 = num_cols(parse_tab(ch_query(q7)), ['open','close','pre_close'])
df7['lo'] = ((df7['open'] - df7['pre_close']) / df7['pre_close'] * 100 < -1).astype(int)
df7['hg'] = ((df7['close'] - df7['open']) / df7['open'] * 100 > 2).astype(int)
df7['strong'] = ((df7['open'] - df7['pre_close']) / df7['pre_close'] * 100 < -1).astype(int) & \
                ((df7['close'] - df7['open']) / df7['open'] * 100 > 2).astype(int) & \
                (df7['close'] > df7['pre_close']).astype(int)
df7 = df7.merge(ind_df, on='ts_code', how='left')
df7 = df7.dropna(subset=['industry'])

# 按行业统计 (要求至少500个样本)
ind_stats = df7.groupby('industry').agg(
    cnt=('ts_code','count'),
    lo_pct=('lo','mean'),
    lo_hg_rate=('hg', lambda x: (x * df7.loc[x.index,'lo']).sum() / max(df7.loc[x.index,'lo'].sum(),1)),
    strong_rate=('strong', lambda x: (x * df7.loc[x.index,'lo']).sum() / max(df7.loc[x.index,'lo'].sum(),1)),
).query('cnt >= 500').sort_values('lo_hg_rate', ascending=False)

print("\nTop 15 行业 (低开高走率最高):")
print(ind_stats.head(15).to_string())
print("\nBottom 10 行业 (低开高走率最低):")
print(ind_stats.tail(10).to_string())
results['by_industry_top'] = ind_stats.head(15).to_dict()
results['by_industry_bottom'] = ind_stats.tail(10).to_dict()

# ============================================================
# 分析8: 连板股 vs 非连板股
# ============================================================
print("\n【分析8】涨停股 vs 非涨停股...")
q8 = """
WITH d AS (
    SELECT 
        ts_code, trade_date, open, close, pre_close, pct_chg,
        lagInFrame(pct_chg, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as pp
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260507'
      AND pre_close > 0 AND open > 0 AND close > 0
)
SELECT 
    g, cnt,
    round(lo / cnt * 100, 2) as lo_pct,
    round(lo_hg / greatest(lo,1) * 100, 2) as lo_hg_rate,
    round(strong / greatest(lo,1) * 100, 2) as strong_rate
FROM (
    SELECT 
        if(pp >= 9.5, '前日涨停', if(pp >= 5, '前日大涨5%+', '前日普通')) as g,
        count() as cnt,
        sum(if((open - pre_close) / pre_close * 100 < -1, 1, 0)) as lo,
        sum(if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2, 1, 0)) as lo_hg,
        sum(if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2 AND close > pre_close, 1, 0)) as strong
    FROM d WHERE pp IS NOT NULL
    GROUP BY g
)
ORDER BY g
"""
df8 = parse_tab(ch_query(q8))
print(df8.to_string(index=False))
results['by_limitup'] = df8.to_dict('records')

# ============================================================
# 分析9: 低开后的次日收益分布 (事件研究)
# ============================================================
print("\n【分析9】强信号次日收益分析...")
q9 = """
WITH d AS (
    SELECT 
        ts_code, trade_date, open, close, pre_close, pct_chg,
        lagInFrame(pct_chg, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as next_pct
    FROM (
        SELECT 
            ts_code, trade_date, open, close, pre_close, pct_chg
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '20200101' AND trade_date <= '20260507'
          AND pre_close > 0 AND open > 0 AND close > 0
    )
),
signals AS (
    SELECT 
        ts_code, trade_date, next_pct,
        if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2 AND close > pre_close, 1, 0) as is_strong,
        if((open - pre_close) / pre_close * 100 < -1, 1, 0) as is_lo
    FROM d WHERE next_pct IS NOT NULL
)
SELECT 
    '强信号' as type, avg(next_pct) as avg_next_pct, count() as cnt,
    round(sum(if(next_pct > 0, 1, 0)) / count() * 100, 2) as win_pct
FROM signals WHERE is_strong = 1
UNION ALL
SELECT 
    '仅低开' as type, avg(next_pct) as avg_next_pct, count() as cnt,
    round(sum(if(next_pct > 0, 1, 0)) / count() * 100, 2) as win_pct
FROM signals WHERE is_lo = 1 AND is_strong = 0
UNION ALL
SELECT 
    '全市场' as type, avg(next_pct) as avg_next_pct, count() as cnt,
    round(sum(if(next_pct > 0, 1, 0)) / count() * 100, 2) as win_pct
FROM signals
"""
df9 = parse_tab(ch_query(q9))
num_cols(df9, ['avg_next_pct','cnt','win_pct'])
print(df9.to_string(index=False))
results['next_day_return'] = df9.to_dict('records')

# ============================================================
# 保存结果
# ============================================================
with open('analysis_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print("\n✅ 分析完成, analysis_results.json 已保存")
