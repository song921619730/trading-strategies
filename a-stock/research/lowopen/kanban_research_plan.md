# A 股 Kanban 研究流水线设计方案 (Kanban Research Pipeline Design)

**版本**: v1.1 (已修正)  
**状态**: 待实施  
**最后更新**: 2026-05-10  
**目标市场**: A 股 (A-Stock)

---

## 1. 核心设计理念 (Core Philosophy)

本流水线旨在通过 **Kanban 多智能体协作** 实现全自动、深度的策略挖掘。

### 1.1 核心目标
*   **渐进式数据探索 (Progressive Data Exploration)**: 拒绝"盲人摸象"，强制系统从量价基础逐层解锁至资金、财务、宏观，确保 Tushare 167 张表的价值被榨干。
*   **状态驱动迭代 (State-Driven Iteration)**: 引入"状态机"记忆，防止重复劳动。AI 根据历史战绩进化参数，直到达到"收益饱和点 (Saturation Point)"。
*   **多维收益矩阵 (Multi-Dimensional Metrics)**: 不仅看总收益，必须输出 1/5/10/20 日收益率、胜率、最大回撤，精准定位策略生命周期。
*   **全量日志审计 (Audit & Logging)**: 所有操作（数据源、新闻、参数、结论）必须结构化记录，确保可复现、可回溯。

---

## 2. 目录结构规划 (Directory Structure)

研究系统位于 `strategies/a-stock/research/lowopen/` 下（以策略名 "Low Open High Go" 命名）。

```text
strategies/a-stock/research/lowopen/
├── state/                       # 【核心】状态记忆目录
│   └── lowopen_state.json       # "低开高走" 主题进度
├── skills/
│   ├── kanban_rules.md          # 全局规范
│   └── audit_checklist.md       # 审计清单
├── scripts/
│   ├── orchestrator.py          # 任务分发器 (Orchestrator)
│   ├── data_loader.py           # 动态数据加载与合并 (Dynamic JOIN)
│   └── grid_engine.py           # 回测引擎 (AI 只填配置，引擎跑循环)
├── cron_prompts/                # T1-T4 任务 Prompt 模板
└── logs/                        # 每次迭代的日志 (实验护照)
```

---

## 3. 核心机制设计

### 3.1 状态机 (State Machine)
每个研究主题拥有独立的 `state.json`，作为迭代基准。

**示例结构 (`state/lowopen_state.json`):**
```json
{
  "topic": "Low Open High Go (低开高走)",
  "base_rule": "Intraday_Gain >= 5% AND Next_Day_Close >= Current_Close",
  "current_iteration": 0,
  "best_metrics": {
    "best_5d_return": null,
    "best_10d_return": null,
    "max_drawdown": null
  },
  "data_exploration": {
    "tested_layers": ["L1_PriceVol"],
    "current_layer": "L1_PriceVol",
    "fatigue_count": 0 
  },
  "history": [] 
}
```

### 3.2 数据分层策略 (Tiered Data Strategy)

系统强制 AI 按层级解锁数据，禁止跳跃。每一层都对应 Tushare 的核心业务维度。**下表列出各层级的主要火力覆盖，完整 167 张表分类见 3.3 节。**

| 层级 | 业务维度 | 关键数据表 (Tushare 核心表) | 覆盖内容示例 (Implementation Detail) |
| :--- | :--- | :--- | :--- |
| **L1** | **量价基础** | `daily`, `daily_basic`, `adj_factor`, `weekly`, `monthly`, `stk_factor`, `daily_info` | **基础行情**：开高低收、成交量、换手率、PE/PB/PS、复权因子。<br>**长周期**：周线/月线数据（用于判断大周期趋势）。 |
| **L2** | **资金情绪** | `moneyflow`, `moneyflow_dc`, `limit_list`, `dragon_tiger`, `margin`, `pledge_stat`, `top_inst`, `top_list` | **资金流向**：大/中/小单净流入、主力追踪、同花顺资金流。<br>**市场情绪**：涨跌停统计、龙虎榜买卖、融资融券余额。<br>**机构动向**：机构专用席位交易数据、质押统计。 |
| **L3** | **财务估值** | `fina_indicator`, `balancesheet`, `income`, `cashflow`, `forecast`, `dividend`, `top10_holders`, `stk_holdernumber` | **财务指标**：ROE、毛利率、营收增长率、现金流。<br>**审计/预告**：审计意见类型、业绩预告快报。<br>**股东结构**：分红送股记录、十大股东持仓变动、股东户数增减。 |
| **L4** | **宏观与特色** | `moneyflow_hsgt`, `concept_detail`, `index_daily`, `cyq_perf`, `stk_premarket`, `us_tycr`, `hk_hold` | **板块/概念**：所属概念板块、板块资金流向、指数行情。<br>**特殊行情**：早盘集合竞价数据、筹码分布。<br>**外盘/宏观**：美债收益率、沪深港通资金流向、美股/大宗商品映射。 |

**疲劳检测规则 (Fatigue Check)**:
若连续 2 次迭代 (Iteration) 收益提升 < 0.3%，且 `tested_layers` 未包含新层：
1. 触发 `fatigue_count += 1`。
2. 当 `fatigue_count >= 3` 时，判定主题"已榨干"，归档并切换下一主题。

### 3.3 Tushare 全量表分类速查 (167 Tables Mapping)

实施时请根据需求从以下分类中调用。**所有表名在 ClickHouse 中通常以 `tushare_` 为前缀。**

| 分类 | 核心表名 (Key Tables) | 覆盖内容 (Coverage) |
| :--- | :--- | :--- |
| **行情数据** | `daily`, `weekly`, `monthly`, `adj_factor`, `stk_factor`, `daily_info`, `bkt_daily` | 核心 K 线、复权因子、每日行情统计、百股行情 |
| **财务数据** | `balancesheet`, `income`, `cashflow`, `fina_indicator`, `fina_mainbz`, `fina_audit`, `forecast`, `express`, `report_rc` | 资产负债表、利润表、现金流、财务指标、主营构成、审计意见、业绩预告/快报 |
| **参考数据** | `stock_basic`, `trade_cal`, `namechange`, `hs_const`, `new_share`, `share_float`, `top10_holders`, `top10_floatholders`, `stk_holdernumber`, `stk_holdertrade`, `dividend` | 股票列表、交易日历、改名、沪深港通、新股、限售解禁、十大股东/流通股东、股东人数/增减持、分红送股 |
| **资金流向** | `moneyflow`, `moneyflow_dc`, `moneyflow_ths`, `moneyflow_cnt`, `moneyflow_ind`, `moneyflow_hsgt`, `ggt_daily`, `ggt_top10`, `hk_hold` | 个股资金流、大盘资金流、同花顺/概念/行业资金流、沪深港通资金、港股通每日/十大/持仓 |
| **特色数据** | `limit_list`, `limit_step`, `dragon_tiger`, `top_list`, `top_inst`, `pledge_stat`, `pledge_detail`, `repurchase`, `concept`, `concept_detail`, `stk_premarket`, `cyq_perf`, `stk_nineturn` | 涨跌停统计/阶梯、龙虎榜/明细/机构、质押统计/明细、回购、概念板块、早盘竞价、筹码分布、九转序列 |
| **指数数据** | `index_daily`, `index_weight`, `index_dailybasic`, `index_classify`, `index_member`, `index_global`, `sz_daily_info` | 指数行情、权重、估值、分类、成分股、全球指数、深证行情 |
| **宏观经济** | `shibor`, `shibor_quote`, `shibor_lpr`, `cpi`, `ppi`, `gdp`, `m`, `us_tycr`, `eco_cal` | 利率、CPI/PPI、GDP、货币供应量、美债收益率、经济日历 |
| **新闻舆情** | `news_api`, `tavily_search`, `rss_feeds` | 宏观经济新闻、行业政策、个股公告、外媒映射 (结合 Tavily 55-key 轮询) |
| **基金/债券** | `fund_daily`, `fund_nav`, `fund_share`, `fund_portfolio`, `cb_basic`, `cb_price_chg`, `cb_share`, `cb_issue` | 基金行情、净值、份额、持仓、可转债行情/发行/转股 |

### 3.4 迭代工作流 (T1-T4 Loop)

每次 Cron 触发，执行以下闭环：

1.  **T1: 假设与组合设计 (Analyst)**
    *   读取 `state.json` 和 Brief。
    *   根据当前数据层级，设计 **3-5 个参数组合** (如：市值阈值、换手率)。
    *   输出 `hypothesis.json`。
2.  **T2: 网格搜索执行 (Researcher)**
    *   将假设填入 `grid_config.json`。
    *   调用 `grid_engine.py` (Python 3.12)。
    *   脚本自动执行 Data JOIN + 循环回测 + 输出多维指标。
3.  **T3: 审计与归因 (Risk Manager)**
    *   对比历史最优指标。
    *   分析新闻关联度 (例：收益提升是否因为隔夜新闻)。
    *   输出 `audit_report.md`。
4.  **T4: 归档与状态更新 (Writer)**
    *   生成 `experiment_log.md` (实验护照)。
    *   更新 `state.json` (刷新最优解、疲劳度)。
    *   决策：继续循环 (Continue) 还是 归档 (Archive)。

---

## 4. 专项研究定义：低开高走 (Low Open High Go)

### 4.1 选股条件 (Base Filter)
所有实验必须基于此核心逻辑，不可修改：
*   **日内涨幅**: `(Close - Open) / Open >= 0.05` (涨幅 >= 5%)
*   **次日表现**: `Next_Close >= Close` (次日收盘价 >= 当日收盘价)
    *   *解释*：确保 T+1 日产生正收益（绝对盈亏），而非仅仅 K 线收红（避免低开收阳仍亏损的情况）。

### 4.2 评估指标 (Metrics)
引擎自动计算以下矩阵：
*   **收益率**: `1D` (隔日), `5D` (周度), `10D` (半月), `20D` (月度)。
*   **胜率 (Win Rate)**: 各周期的盈利概率。
*   **最大回撤 (Max Drawdown)**: 持仓期内的最大跌幅（基于策略组合净值曲线）。
*   **样本量 (Sample Size)**: 必须 > 500 次信号以保证统计显著性。

### 4.3 日志标准 (Log Passport)
每次实验生成的 `log.md` 必须包含：
1.  **数据范围**: 例如 `2020-01-01 至 2026-05-10` (全量)。
2.  **数据源**: 明确列出的 Tushare 表名。
3.  **结合新闻**: 用于过滤或归因的新闻关键词。
4.  **结果矩阵**: Top 3 组合的收益/回撤对比。

---

## 4.4 成功标准 (Alpha Definition)

疲劳检测定义了"何时放弃"，但我们需要明确定义**"何时赢" (Success Criteria)**。当策略满足以下**全部**条件时，视为发现 Alpha：

1.  **收益门槛**：
    *   `5D 年化收益` > **15%**
    *   `10D 年化收益` > **10%**
2.  **稳定性**：
    *   `胜率 (Win Rate)` > **52%**
    *   `最大回撤 (Max Drawdown)` < **10%**
3.  **统计显著性**：
    *   `样本量 (Sample Size)` > **100** (L2/L3 层) 或 > **500** (L1 层)
    *   `夏普比率 (Sharpe)` > **1.0**

**✅ 触发部署动作**：
*   自动生成 `proposal.md` (包含最优参数、回测曲线、风控建议)。
*   更新 `state.json` 标记 `status: verified`。
*   通知 Hermes 主系统进入"影子模式 (Shadow Mode)"验证。

---

## 5. 实施步骤 (Next Steps)

### 5.1 回测引擎技术规范 (Grid Engine Specs)

`scripts/grid_engine.py` 是系统的核心，必须实现以下四大功能：

1.  **动态 JOIN 解析**：
    *   读取 `grid_config.json` 中的 `data_layers`。
    *   自动构建 ClickHouse SQL：`SELECT * FROM tushare_daily d JOIN tushare_daily_basic b ON d.ts_code=b.ts_code ...`
    *   处理不同频率数据的对齐（如日线 vs 周线）。

2.  **PIT 安全逻辑 (Point-in-Time)**：
    *   **严禁未来函数**：所有用于决策的指标（如财务数据、换手率）必须 `shift(1)`，确保使用的是 T-1 日已知的数据。
    *   **财务数据对齐**：使用 `report_date` 映射到 `trade_date`，确保财报发布前不可见。

3.  **向量化多周期计算**：
    *   不使用 Python `for` 循环遍历股票。
    *   使用 Pandas `groupby` + `rolling` 或 `shift` 一次性计算 1/5/10/20 日收益矩阵。
    *   计算组合净值曲线 (Portfolio Equity Curve) 以获取真实的最大回撤。

4.  **结果输出**：
    *   输出 `results.csv`：包含每一笔交易信号的详细信息（买入日、卖出日、各周期收益、持仓期间最大回撤）。
    *   输出 `summary.json`：包含该组参数的聚合指标（总收益、胜率、夏普等）。

---

## 6. 附件清单

*   `state/lowopen_state.json`: 初始状态文件。
*   `grid_config_template.json`: AI 填写的标准配置模板。
*   `tushare_cheat_sheet.md`: 字段名防错速查表。
