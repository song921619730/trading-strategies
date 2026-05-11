# 统一参数空间 — 全量 167 表维度

> 所有分析师共享同一个参数空间。流派只是切入视角，不限制数据范围或参数选择。每轮每个分析师从以下空间随机采 3-8 个维度做组合测试。

## 数据来源

167 张 Tushare 表，核心 8 个域：

| 域 | 代表表 |
|---|---|
| 日线行情 | stock_daily, stock_weekly, stock_monthly, adj_factor, daily_basic, bak_daily |
| 资金流向 | moneyflow, moneyflow_hsgt, hsgt_top10, ggt_top10, moneyflow_ind_dc |
| 龙虎榜/大宗 | top_list, top_inst, block_trade, dc_hot, dc_daily |
| 融资融券 | margin, margin_detail, margin_secs |
| 财报/估值 | income, balancesheet, cashflow, fina_indicator, forecast, express, fina_audit |
| 股东/筹码 | top10_holders, stk_holdernumber, stk_holdertrade, pledge_stat, cyq_chips |
| 概念/板块 | kpl_concept_cons, kpl_list, ths_daily, ths_index, ths_member, limit_list_d, sw_daily |
| 宏观/期货/跨市场 | fut_daily, cn_pmi, cn_cpi, cn_m, cn_gdp, shibor, fx_daily, index_global, cn_ppi |

## 参数空间（全部可选）

```python
param_space_all = {
    # ══ 价格行为 ══
    'n_day_high':       [5, 10, 20, 60, 120],        # N日新高
    'n_day_low':        [5, 10, 20, 60, 120],         # N日新低
    'pct_chg_1d_min':   [-10, -7, -5, -3, -2, 0, 2, 3, 5],   # 当日涨幅下限
    'pct_chg_1d_max':   [3, 5, 7, 10, None],                   # 当日涨幅上限
    'close_position':   ['底20%', '底40%', '中位', '顶40%', '顶20%'],
    'amplitude_min':    [0, 3, 5, 7, 10],             # 日振幅
    'gap_direction':    ['向上跳空', '向下跳空', '无缺口'],

    # ══ 量能 ══
    'volume_ratio_min': [0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0],
    'volume_ratio_max': [1.5, 2.0, 3.0, 5.0, 10.0, None],
    'turnover_rate_min': [0.003, 0.005, 0.01, 0.02, 0.05, 0.10],
    'turnover_rate_max': [0.10, 0.20, 0.30, None],
    'vol_trend_5d':     ['持续放量', '持续缩量', '忽大忽小'],
    'amount_min':       [1e8, 5e8, 1e9],              # 最小成交额

    # ══ 均线系统 ══
    'ma_arrangement':   ['多头排列', '空头排列', '粘合(差<3%)', '金叉', '死叉', '无所谓'],
    'ma_support':       ['MA5', 'MA10', 'MA20', 'MA60', 'MA120', '无支撑要求'],
    'ma_resistance':    ['MA5', 'MA10', 'MA20', 'MA60', '无压力要求'],
    'atr_pct_20d':      [0.005, 0.01, 0.015, 0.02, 0.03, 0.05],

    # ══ 资金流 ══
    'net_mf_min':       [-100_000_000, -50_000_000, -10_000_000, 0, 5_000_000, 20_000_000],
    'buy_lg_ratio_min': [0.05, 0.08, 0.10, 0.15, 0.20],
    'sell_lg_ratio_max': [0.20, 0.15, 0.10, 0.08, 0.05],
    'buy_elg_ratio_min': [0.02, 0.03, 0.05, 0.08, 0.10],
    'sell_elg_ratio_max': [0.10, 0.05, 0.03, 0.02],
    'north_net_inflow': ['净流入>0', '净流出<0', '无所谓'],
    'margin_balance_chg_5d': ['增加>5%', '增加>10%', '减少>5%', '无所谓'],
    'sm_vol_ratio':     ['散户大量卖出', '散户大量买入', '无所谓'],  # small sell/buy ratio

    # ══ 估值/基本面 ══
    'pe_max':           [10, 15, 30, 50, 100, 200, None],
    'pe_min':           [0, 5, 10, 20, None],
    'pb_max':           [1, 2, 3, 5, 10, None],
    'pb_min':           [0, 0.5, 1, None],
    'market_cap_bucket': ['小盘(<30亿)', '中小盘(30-100亿)', '中大盘(100-500亿)', '大盘(>500亿)'],
    'circ_mv_min':      [1e9, 5e9, 10e9, 50e9, 100e9],
    'roe_min':          [0, 0.05, 0.10, 0.15, 0.20],
    'roe_max':          [0.30, 0.50, None],
    'gross_margin_min': [0, 0.10, 0.20, 0.30, 0.50],
    'net_profit_margin_min': [0, 0.05, 0.10, 0.20],
    'eps_yoy_growth':   ['>0', '>10%', '>30%', '无所谓'],
    'revenue_yoy_growth': ['>0', '>10%', '>30%', '无所谓'],
    'forecast_type':    ['预增', '预减', '预亏', '无所谓'],
    'dividend_yield_min': [0, 0.01, 0.02, 0.03, 0.05],
    'fina_audit_result': ['标准无保留', '无所谓'],

    # ══ 股东/筹码 ══
    'holder_num_chg_3q': ['减少>5%', '减少>10%', '增加>5%', '无所谓'],  # 户数变化=筹码集中度
    'top10_holder_pct_min': [0.2, 0.3, 0.5, 0.7],
    'pledge_ratio_max':  [0.2, 0.3, 0.5, None],      # 质押比例
    'holder_trade_3m':  ['高管增持', '高管减持', '无所谓'],
    'cyq_concentration': ['高度集中(>70%)', '集中(50-70%)', '分散(<50%)', '无所谓'],

    # ══ 板块/概念 ══
    'industry_hot_rank': ['前3', '前5', '前10', '不限制'],    # 按涨停数排名
    'concept_count_min': [0, 1, 2, 3, 5],
    'concept_count_max': [1, 2, 3, 5, 10, None],
    'limit_up_sector_count_5d': [0, 3, 5, 10, 20],   # 板块5日内涨停家数
    'ths_index_trend':  ['上升', '下降', '横盘'],
    'sw_sector_return_5d': ['前20%', '前10%', '无所谓'],

    # ══ 涨停/跌停 ══
    'limit_times_min':  [0, 1, 2, 3],
    'limit_times_max':  [1, 3, 5, 10, None],
    'fc_ratio_min':     [0, 0.10, 0.20, 0.30, 0.50],  # 封板率
    'is_limit_up_today': [True, False],
    'was_limit_down_recent': [True, False, '无所谓'],
    'limit_step_count': [0, 1, 2, 3],                  # 涨停阶梯数

    # ══ 跨市场/宏观 ══
    'futures_corr_20d':  ['>0.3', '>0.5', '<-0.3', '<-0.5', '无所谓'],
    'macro_regime':      ['PMI>50', 'PMI<50', 'CPI上行', 'CPI下行', '无所谓'],
    'shibor_trend_10d':  ['上行', '下行', '平稳'],
    'm2_growth':         ['加速', '减速', '无所谓'],
    'usd_index_trend':   ['强势', '弱势', '无所谓'],
    'index_global_trend': ['上涨', '下跌', '无所谓'],

    # ══ 可转债 ══
    'cb_premium_rate':   ['低溢价(<10%)', '中溢价(10-30%)', '高溢价(>30%)', '无所谓'],
    'cb_turnover_min':   [0.10, 0.20, 0.50],

    # ══ 持有期/退出规则 ══
    'hold_days':         [1, 2, 3, 5, 10, 20],
    'profit_target':     [0.03, 0.05, 0.08, 0.10, 0.15],
    'stop_loss':         [-0.01, -0.02, -0.03, -0.05, -0.08],

    # ══ 时间/市场环境过滤 ══
    'month_filter':      ['全年', '仅1-4月财报季', '仅Q1', '仅Q4', '避开6-8月'],
    'index_trend_20d':   ['沪深300上涨', '沪深300下跌', '无所谓'],
    'market_regime':     ['牛市', '熊市', '震荡', '无所谓'],

    # ══ 基本面排除 ══
    'exclude_st':         True,   # 排除 ST
    'exclude_bse':        True,   # 排除北交所
    'exclude_chuang':     True,   # 排除创业板
    'exclude_kechuang':   True,   # 排除科创板
    'exclude_new_days':   [0, 30, 60, 120],  # 排除上市不足N天的新股
}
```

## 使用规则

1. **每轮每个 analyst 随机采 3-8 个维度**，从每个维度中随机选一个值
2. **去重**：对比 `state.json` 中的 `recent_combos`，跳过最近 50 轮已测试的组合
3. **主板过滤**：默认 `exclude_st/exclude_bse/exclude_chuang/exclude_kechuang=True`
4. **数据日期**：必须先查询 `max(trade_date)` 确认最新数据日期，然后用全量历史数据回测
5. **回测指标**：胜率(WR)、5日/10日/20日平均收益、信号数量、夏普比率
6. **成功标准**：WR ≥ 55% AND 5D 收益 ≥ 5% AND 信号数 ≥ 200
