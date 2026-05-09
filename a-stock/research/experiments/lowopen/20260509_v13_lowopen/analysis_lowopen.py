#!/usr/bin/env python3
"""
低开高走模式识别 - 阶段1：基础统计与筛选因子

核心假设：
H1: 前日涨停/大涨的股票，次日低开高走的概率显著高于随机基线
H2: 前日缩量（放量）与次日低开高走存在系统性关联
H3: 特定行业/板块在低开高走模式中存在显著偏好

定义：
- 低开: open < pre_close AND open_pct_change < -1%
- 高走: close > open AND close_pct_change_intraday > 2%
- 强信号: 低开 >= -1%, 收盘涨幅 >= 2%, 且 close > pre_close
"""

import requests
import pandas as pd
import numpy as np
# scipy not available, use numpy/pandas built-in stats

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames'):
    """执行ClickHouse查询"""
    full_query = f"{query} FORMAT {fmt}"
    r = requests.get(CH_URL, params={'query': full_query}, auth=CH_AUTH, timeout=120)
    if r.status_code != 200:
        raise Exception(f"Query failed: {r.text}")
    return r.text

def parse_tab(text):
    """解析TabSeparatedWithNames格式为DataFrame"""
    lines = text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    rows = [line.split('\t') for line in lines[1:]]
    df = pd.DataFrame(rows, columns=cols)
    return df

def main():
    print("=" * 60)
    print("低开高走模式识别 - 阶段1分析")
    print("=" * 60)

    # ============================================================
    # 分析1: 全局低开高走频率统计
    # ============================================================
    print("\n【分析1】全局低开高走频率统计")
    
    query1 = """
    WITH base AS (
        SELECT 
            ts_code,
            trade_date,
            open,
            close,
            pre_close,
            pct_chg,
            vol,
            amount,
            -- 低开幅度 (开盘价相对前日收盘)
            (open - pre_close) / pre_close * 100 as open_gap_pct,
            -- 日内涨幅 (收盘相对开盘)
            (close - open) / open * 100 as intraday_pct,
            -- 是否低开
            if((open - pre_close) / pre_close * 100 < -1, 1, 0) as is_low_open,
            -- 是否高走 (日内涨幅>2%)
            if((close - open) / open * 100 > 2, 1, 0) as is_high_go,
            -- 是否强信号 (低开>=-1% 且 日内涨幅>=2% 且 收盘>前收)
            if((open - pre_close) / pre_close * 100 < -1 
               AND (close - open) / open * 100 > 2
               AND close > pre_close, 1, 0) as is_strong
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '20200101'
          AND trade_date <= '20260507'
          AND pre_close > 0
          AND open > 0
          AND close > 0
    )
    SELECT 
        count() as total,
        sum(is_low_open) as low_open_cnt,
        round(sum(is_low_open) / count() * 100, 2) as low_open_pct,
        sum(is_high_go) as high_go_cnt,
        round(sum(is_high_go) / count() * 100, 2) as high_go_pct,
        sum(is_strong) as strong_cnt,
        round(sum(is_strong) / count() * 100, 2) as strong_pct,
        -- 低开条件下的高走概率
        round(sum(is_low_open AND is_high_go) / sum(is_low_open) * 100, 2) as cond_high_go_given_low,
        -- 低开条件下的强信号概率
        round(sum(is_strong) / sum(is_low_open) * 100, 2) as cond_strong_given_low
    FROM base
    """
    print("执行查询 (可能需要10-30秒)...")
    text = ch_query(query1)
    df1 = parse_tab(text)
    print(df1.to_string(index=False))
    
    total = int(df1.iloc[0]['total'])
    low_open_pct = float(df1.iloc[0]['low_open_pct'])
    high_go_pct = float(df1.iloc[0]['high_go_pct'])
    strong_pct = float(df1.iloc[0]['strong_pct'])
    cond_high_go = float(df1.iloc[0]['cond_high_go_given_low'])
    cond_strong = float(df1.iloc[0]['cond_strong_given_low'])
    
    print(f"\n基准统计 (2020-2026, {total:,} 条日K线):")
    print(f"  低开率: {low_open_pct}%")
    print(f"  高走率: {high_go_pct}%")
    print(f"  强信号率: {strong_pct}%")
    print(f"  P(高走|低开): {cond_high_go}%")
    print(f"  P(强信号|低开): {cond_strong}%")

    # ============================================================
    # 分析2: 按前日涨跌幅分组统计
    # ============================================================
    print("\n【分析2】按前日涨跌幅分组统计低开高走概率")
    
    query2 = """
    WITH base AS (
        SELECT 
            ts_code,
            trade_date,
            open,
            close,
            pre_close,
            pct_chg as today_pct,
            vol,
            amount,
            (open - pre_close) / pre_close * 100 as open_gap_pct,
            (close - open) / open * 100 as intraday_pct,
            if((open - pre_close) / pre_close * 100 < -1, 1, 0) as is_low_open,
            if((close - open) / open * 100 > 2, 1, 0) as is_high_go,
            if((open - pre_close) / pre_close * 100 < -1 
               AND (close - open) / open * 100 > 2
               AND close > pre_close, 1, 0) as is_strong
        FROM (
            SELECT 
                ts_code,
                trade_date,
                open,
                close,
                pre_close,
                pct_chg,
                vol,
                amount,
                lagInFrame(pct_chg, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as prev_pct,
                lagInFrame(vol, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as prev_vol
            FROM tushare.tushare_stock_daily FINAL
            WHERE trade_date >= '20200101'
              AND trade_date <= '20260507'
              AND pre_close > 0 AND open > 0 AND close > 0
        )
        WHERE prev_pct IS NOT NULL
    )
    SELECT 
        prev_pct_group,
        count() as cnt,
        round(sum(is_low_open) / count() * 100, 2) as lo_pct,
        round(sum(is_low_open AND is_high_go) / max(sum(is_low_open),1) * 100, 2) as lo_hg_rate,
        round(sum(is_strong) / max(sum(is_low_open),1) * 100, 2) as strong_rate
    FROM (
        SELECT 
            *,
            multiIf(prev_pct >= 9.5, '涨停', prev_pct >= 5, '大涨5%+', prev_pct >= 2, '涨2-5%', prev_pct >= -2, '平盘±2%', prev_pct >= -5, '跌2-5%', prev_pct >= -9.5, '大跌5%+', '跌停') as prev_pct_group
        FROM base
    )
    GROUP BY prev_pct_group
    ORDER BY prev_pct_group
    """
    text2 = ch_query(query2)
    df2 = parse_tab(text2)
    print(df2.to_string(index=False))

    # ============================================================
    # 分析3: 按前日成交量变化分组
    # ============================================================
    print("\n【分析3】按前日成交量变化分组")
    
    query3 = """
    WITH base AS (
        SELECT 
            ts_code, trade_date, open, close, pre_close, vol,
            (open - pre_close) / pre_close * 100 as open_gap_pct,
            (close - open) / open * 100 as intraday_pct,
            if((open - pre_close) / pre_close * 100 < -1, 1, 0) as is_low_open,
            if((close - open) / open * 100 > 2, 1, 0) as is_high_go,
            if((open - pre_close) / pre_close * 100 < -1 AND (close - open) / open * 100 > 2 AND close > pre_close, 1, 0) as is_strong,
            lagInFrame(vol, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as prev_vol
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '20200101' AND trade_date <= '20260507'
          AND pre_close > 0 AND open > 0 AND close > 0 AND vol > 0
    )
    SELECT 
        vol_group, count() as cnt,
        round(sum(is_low_open) / count() * 100, 2) as lo_pct,
        round(sum(is_low_open AND is_high_go) / max(sum(is_low_open),1) * 100, 2) as lo_hg_rate,
        round(sum(is_strong) / max(sum(is_low_open),1) * 100, 2) as strong_rate
    FROM (
        SELECT *, 
            multiIf(prev_vol IS NOT NULL AND prev_vol > 0 AND vol/prev_vol >= 3, '放量3x+',
                    prev_vol IS NOT NULL AND prev_vol > 0 AND vol/prev_vol >= 2, '放量2-3x',
                    prev_vol IS NOT NULL AND prev_vol > 0 AND vol/prev_vol >= 1.5, '放量1.5-2x',
                    prev_vol IS NOT NULL AND prev_vol > 0 AND vol/prev_vol >= 0.8, '正常0.8-1.5x',
                    prev_vol IS NOT NULL AND prev_vol > 0 AND vol/prev_vol >= 0.5, '缩量0.5-0.8x',
                    '极度缩量<0.5x') as vol_group
        FROM base
    )
    GROUP BY vol_group ORDER BY vol_group
    """
    text3 = ch_query(query3)
    df3 = parse_tab(text3)
    print(df3.to_string(index=False))

    # ============================================================
    # 分析4: 获取实际样本数据用于进一步分析
    # ============================================================
    print("\n【分析4】获取样本数据 (采样) 用于深入分析...")
    
    # 采样获取带完整特征的样本 (每只股票随机取部分数据避免过大)
    query4 = """
    WITH base AS (
        SELECT 
            ts_code,
            trade_date,
            open,
            close,
            pre_close,
            pct_chg,
            vol,
            amount,
            (open - pre_close) / pre_close * 100 as open_gap_pct,
            (close - open) / open * 100 as intraday_pct,
            if((open - pre_close) / pre_close * 100 < -1, 1, 0) as is_low_open,
            if((close - open) / open * 100 > 2, 1, 0) as is_high_go,
            if((open - pre_close) / pre_close * 100 < -1 
               AND (close - open) / open * 100 > 2
               AND close > pre_close, 1, 0) as is_strong,
            lagInFrame(pct_chg, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as prev_pct,
            lagInFrame(vol, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as prev_vol,
            lagInFrame(turnover_rate, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as prev_turnover
        FROM (
            SELECT 
                s.ts_code,
                s.trade_date,
                s.open,
                s.close,
                s.pre_close,
                s.pct_chg,
                s.vol,
                s.amount,
                b.turnover_rate
            FROM tushare.tushare_stock_daily FINAL s
            LEFT JOIN tushare.tushare_daily_basic FINAL b 
                ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
            WHERE s.trade_date >= '20200101'
              AND s.trade_date <= '20260507'
              AND s.pre_close > 0 AND s.open > 0 AND s.close > 0
              AND s.vol > 0
        )
    )
    SELECT *
    FROM (
        SELECT 
            *,
            CASE WHEN prev_vol IS NOT NULL AND prev_vol > 0 THEN vol / prev_vol ELSE 1 END as vol_ratio,
            CASE 
                WHEN prev_pct >= 9.5 THEN 6
                WHEN prev_pct >= 5 THEN 5
                WHEN prev_pct >= 2 THEN 4
                WHEN prev_pct >= -2 THEN 3
                WHEN prev_pct >= -5 THEN 2
                WHEN prev_pct >= -9.5 THEN 1
                ELSE 0
            END as prev_pct_bin
        FROM base
        WHERE prev_pct IS NOT NULL
    )
    WHERE rand() % 10 = 0
    """
    text4 = ch_query(query4)
    df4 = parse_tab(text4)
    print(f"采样样本数: {len(df4)}")
    
    # 转换数值类型
    for col in ['open', 'close', 'pre_close', 'pct_chg', 'vol', 'amount', 
                'open_gap_pct', 'intraday_pct', 'is_low_open', 'is_high_go', 'is_strong',
                'prev_pct', 'prev_vol', 'vol_ratio', 'prev_turnover', 'prev_pct_bin']:
        if col in df4.columns:
            df4[col] = pd.to_numeric(df4[col], errors='coerce')
    
    # 分析: 前日涨跌幅 vs 次日低开高走概率
    print("\n--- 前日涨跌幅与低开高走的关系 ---")
    groups = df4.groupby('prev_pct_bin').agg(
        cnt=('is_low_open', 'count'),
        lo_count=('is_low_open', 'sum'),
        lo_pct=('is_low_open', 'mean'),
        lo_hg=('is_high_go', lambda x: (x * df4.loc[x.index, 'is_low_open']).sum() / max(df4.loc[x.index, 'is_low_open'].sum(), 1)),
    )
    print(groups)
    
    # 分析: 前日换手率 vs 低开高走
    print("\n--- 前日换手率分位与低开高走的关系 ---")
    df4['turnover_q'] = pd.qcut(df4['prev_turnover'].dropna(), q=5, labels=['Q1最低', 'Q2', 'Q3', 'Q4', 'Q5最高'], duplicates='drop')
    tr_groups = df4.groupby('turnover_q', observed=True).agg(
        cnt=('ts_code', 'count'),
        lo_rate=('is_low_open', 'mean'),
        lo_hg_rate=('is_high_go', lambda x: (x * df4.loc[x.index, 'is_low_open']).sum() / max(df4.loc[x.index, 'is_low_open'].sum(), 1)),
    )
    print(tr_groups)
    
    # ============================================================
    # 分析5: 按月份/市场环境分析季节性
    # ============================================================
    print("\n【分析5】按月份分析低开高走季节性")
    
    query5 = """
    WITH base AS (
        SELECT 
            toMonth(toDate(trade_date)) as month,
            toYear(toDate(trade_date)) as year,
            ts_code,
            trade_date,
            open, close, pre_close,
            if((open - pre_close) / pre_close * 100 < -1, 1, 0) as is_low_open,
            if((close - open) / open * 100 > 2, 1, 0) as is_high_go,
            if((open - pre_close) / pre_close * 100 < -1 
               AND (close - open) / open * 100 > 2
               AND close > pre_close, 1, 0) as is_strong
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '20200101'
          AND trade_date <= '20260507'
          AND pre_close > 0 AND open > 0 AND close > 0
    )
    SELECT 
        month,
        count() as total,
        round(sum(is_low_open) / count() * 100, 2) as lo_pct,
        round(sum(is_low_open AND is_high_go) / sum(is_low_open) * 100, 2) as lo_hg_rate,
        round(sum(is_strong) / sum(is_low_open) * 100, 2) as strong_rate
    FROM base
    GROUP BY month
    ORDER BY month
    """
    text5 = ch_query(query5)
    df5 = parse_tab(text5)
    print(df5.to_string(index=False))

    # ============================================================
    # 分析6: 按市场环境(牛/熊/震荡)分析
    # ============================================================
    print("\n【分析6】按市场环境分析 (用上证指数涨跌定义)")
    
    # 先获取上证指数数据来定义市场环境
    query_sh = """
    SELECT trade_date, open, close, pre_close, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE ts_code = '000001.SH'
      AND trade_date >= '20200101'
      AND trade_date <= '20260507'
      AND pre_close > 0
    ORDER BY trade_date
    """
    sh_text = ch_query(query_sh)
    sh_df = parse_tab(sh_text)
    for col in ['open', 'close', 'pre_close', 'pct_chg']:
        sh_df[col] = pd.to_numeric(sh_df[col], errors='coerce')
    
    # 用30日滚动收益定义市场环境
    sh_df['roll_30'] = sh_df['close'].pct_change(20)  # 约20个交易日
    sh_df['regime'] = pd.qcut(sh_df['roll_30'].dropna(), q=3, labels=['熊市', '震荡', '牛市'], duplicates='drop')
    sh_df['date'] = sh_df['trade_date']
    
    print(f"上证指数市场环境分布:")
    print(sh_df['regime'].value_counts().to_string())
    
    # 将市场环境映射到个股
    regime_map = dict(zip(sh_df['date'], sh_df['regime']))
    
    # 获取带市场环境的样本
    query6 = """
    SELECT 
        ts_code,
        trade_date,
        open, close, pre_close, vol, pct_chg,
        if((open - pre_close) / pre_close * 100 < -1, 1, 0) as is_low_open,
        if((close - open) / open * 100 > 2, 1, 0) as is_high_go,
        if((open - pre_close) / pre_close * 100 < -1 
           AND (close - open) / open * 100 > 2
           AND close > pre_close, 1, 0) as is_strong
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101'
      AND trade_date <= '20260507'
      AND pre_close > 0 AND open > 0 AND close > 0
      AND rand() % 20 = 0
    """
    text6 = ch_query(query6)
    df6 = parse_tab(text6)
    for col in ['open', 'close', 'pre_close', 'vol', 'pct_chg', 'is_low_open', 'is_high_go', 'is_strong']:
        df6[col] = pd.to_numeric(df6[col], errors='coerce')
    
    df6['regime'] = df6['trade_date'].map(regime_map)
    regime_stats = df6.groupby('regime', observed=True).agg(
        cnt=('ts_code', 'count'),
        lo_pct=('is_low_open', 'mean'),
        lo_hg_rate=('is_high_go', lambda x: (x * df6.loc[x.index, 'is_low_open']).sum() / max(df6.loc[x.index, 'is_low_open'].sum(), 1)),
        strong_rate=('is_strong', lambda x: (x * df6.loc[x.index, 'is_low_open']).sum() / max(df6.loc[x.index, 'is_low_open'].sum(), 1)),
    )
    print("\n市场环境 vs 低开高走:")
    print(regime_stats)

    # ============================================================
    # 分析7: 行业板块偏好 (用股票名称+代码推断)
    # ============================================================
    print("\n【分析7】行业板块偏好分析 (用stock_basic表)")
    
    # 获取股票所属行业
    query_ind = """
    SELECT ts_code, industry, name
    FROM tushare.tushare_stock_basic FINAL
    WHERE list_status = 'L'
    """
    ind_text = ch_query(query_ind)
    ind_df = parse_tab(ind_text)
    
    # 获取样本数据按行业分组
    query7 = """
    WITH base AS (
        SELECT 
            ts_code,
            trade_date,
            if((open - pre_close) / pre_close * 100 < -1, 1, 0) as is_low_open,
            if((close - open) / open * 100 > 2, 1, 0) as is_high_go,
            if((open - pre_close) / pre_close * 100 < -1 
               AND (close - open) / open * 100 > 2
               AND close > pre_close, 1, 0) as is_strong
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '20200101'
          AND trade_date <= '20260507'
          AND pre_close > 0 AND open > 0 AND close > 0
          AND rand() % 10 = 0
    )
    SELECT * FROM base
    """
    text7 = ch_query(query7)
    df7 = parse_tab(text7)
    for col in ['is_low_open', 'is_high_go', 'is_strong']:
        df7[col] = pd.to_numeric(df7[col], errors='coerce')
    
    # 合并行业信息
    df7 = df7.merge(ind_df[['ts_code', 'industry']], on='ts_code', how='left', suffixes=('', '_ind'))
    
    industry_stats = df7.groupby('industry').agg(
        cnt=('ts_code', 'count'),
        lo_pct=('is_low_open', 'mean'),
        lo_hg_rate=('is_high_go', lambda x: (x * df7.loc[x.index, 'is_low_open']).sum() / max(df7.loc[x.index, 'is_low_open'].sum(), 1)),
        strong_rate=('is_strong', lambda x: (x * df7.loc[x.index, 'is_low_open']).sum() / max(df7.loc[x.index, 'is_low_open'].sum(), 1)),
    ).query('cnt >= 500').sort_values('lo_hg_rate', ascending=False)
    
    print("\nTop 15 行业 (低开高走率最高):")
    print(industry_stats.head(15).to_string())
    print("\nBottom 10 行业 (低开高走率最低):")
    print(industry_stats.tail(10).to_string())

    # ============================================================
    # 保存结果
    # ============================================================
    df4.to_csv('sample_data.csv', index=False)
    print("\n✅ 分析完成, sample_data.csv 已保存")
    
    return {
        'global': df1,
        'by_prev_pct': df2,
        'by_volume': df3,
        'by_month': df5,
        'by_regime': regime_stats,
        'by_industry': industry_stats,
        'global_metrics': {
            'total': total,
            'low_open_pct': low_open_pct,
            'high_go_pct': high_go_pct,
            'strong_pct': strong_pct,
            'cond_high_go': cond_high_go,
            'cond_strong': cond_strong,
        }
    }

if __name__ == '__main__':
    results = main()
