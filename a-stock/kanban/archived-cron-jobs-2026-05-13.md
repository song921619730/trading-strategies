# Cron 定时任务归档 — 2026-05-13

> 归档原因：精简流水线，仅保留三个核心任务
> 保留：Tushare 全表每日同步 / 策略全表挖掘 Mining-All167 / A股短线盘前策略
> 归档时间：2026-05-13 19:12 UTC+8

---

## 归档任务（7 个，已暂停）

### 1. A股盘后短线初筛 `995d7d94-f38`

| 字段 | 值 |
|------|------|
| 调度 | `0 22 * * 1-5` (交易日 22:00 UTC+8) |
| workdir | `strategies/a-stock/kanban/a-stock-shortline` |
| skills | `kanban-orchestrator` |
| 模型 | `deepseek-v4-flash` (opencode) |

**Cron Prompt** (`cron-prompts/postclose-screen.md`):
```
# 盘后短线初筛 — Cron Prompt
> 执行时间：每个交易日 22:00 (UTC+8)，任务编号 T1-T7
你是 Orchestrator。执行 A 股盘后短线初筛流水线。T1-T7 任务，不得跳过。

## 步骤概要
T1 交易日历确认
T2 A股日线扫描（五大指数/涨停池/北向资金/概念板块/PE-PB中位数）
T3 MT5 全球行情 + global-futures 国际期货
T4 Tavily 新闻搜索（宏观/A股行业/中美贸易/重大公告）
T5 财经专家全市场扫描（依赖 T1-T4，assignee=analyst）
T6 主控初筛压缩到 12-20 只（依赖 T5，assignee=analyst）
T7 报告生成（依赖 T6，assignee=writer）

## 核心逻辑
短线六锚点：情绪周期/龙头梯队/量价结构/执行窗口/关键价位/待涨接盘识别
候选分层：待涨观察池/预备突破池/强确认跟踪池
```

---

### 2. A股盘后短线收敛 `a38dcc35-eab`

| 字段 | 值 |
|------|------|
| 调度 | `35 23 * * 1-5` (交易日 23:35 UTC+8) |
| workdir | `strategies/a-stock/kanban/a-stock-shortline` |
| skills | `kanban-orchestrator` |
| 模型 | `deepseek-v4-flash` (opencode) |

**Cron Prompt** (`cron-prompts/postclose-converge.md`):
```
# 盘后短线收敛 — Cron Prompt
> 执行时间：每个交易日 23:30 (UTC+8)，任务编号 T8-T14

T8 逐票价格校验（无 parent，自动读取最新初筛报告）
T9-T12 四专家并行专项加减分（财经/科技/期货/政治，依赖 T8）
T13 主控最终裁决收敛到 6-10 只（依赖 T9-T12）
T14 收敛报告生成（依赖 T13）

高位一致惩罚 + 待涨优先原则（待涨池 >= 50%）
风险口径统一：综合风险等级 = max(专家均值, 接盘风险)
月度技术扫描 + 次日执行卡
```

---

### 3. DLR 涨停雷达盘后初筛 `83f6ce2d7344`

| 字段 | 值 |
|------|------|
| 调度 | `28 0 * * 1-5` (交易日 00:28 UTC+8) |
| workdir | `strategies/a-stock/kanban/daily-limit-radar` |
| skills | `kanban-orchestrator`, `tushare-db-fast` |
| 模型 | `deepseek-v4-flash` (opencode) |

**Cron Prompt** (`cron-prompts/postclose-screen.md`):
```
# 盘后初筛 — Cron Prompt (DLR 涨停雷达)
> 执行时间：每个交易日 00:28 (UTC+8)，任务编号 T1-T7

T1 交易日历确认
T2 涨停池数据拉取（limit_list_d，含连板数/封单比）
T3 板块聚类分析（kpl_concept_cons JOIN limit_list_d）
T4 情绪指标拉取（涨跌停统计/连板梯队/昨日涨停溢价）
T5 财经扫描与风险初筛（assignee=analyst）
T6 主控初筛与 10 因子预评分（F1-F8 数值分 + F9/F10 标记）
T7 盘后初筛报告生成（assignee=writer）

10 因子评分体系：三层分层阈值（待涨≥34 / 预备突破30-33 / 强确认26-29）
```

---

### 4. DLR 涨停雷达盘后收敛 `27bc55b60b37`

| 字段 | 值 |
|------|------|
| 调度 | `45 0 * * 1-5` (交易日 00:45 UTC+8) |
| workdir | `strategies/a-stock/kanban/daily-limit-radar` |
| skills | `kanban-orchestrator`, `tushare-db-fast` |
| 模型 | `deepseek-v4-flash` (opencode) |

**Cron Prompt** (`cron-prompts/postclose-converge.md`):
```
# 盘后收敛 — Cron Prompt (DLR 涨停雷达)
> 执行时间：交易日 00:45 (UTC+8)，任务编号 T8-T14
前置依赖：盘后初筛流水线已完成

T8 候选股深度数据拉取（120日OHLCV/60日资金流/基本面/涨停历史）
T9 财经专家分析（F9催化评分 0-5）
T10 技术专家分析（F10技术共振评分 0-5，均线/MACD/量价）
T11 资金专家分析（F4资金重评）
T12 板块专家分析（F3板块重评）
T13 主控裁决与完整打分（汇总4专家，收敛到7只）
T14 盘后收敛报告生成
```

---

### 5. DLR 涨停雷达盘前确认 `ee63b0546f28`

| 字段 | 值 |
|------|------|
| 调度 | `30 8 * * 1-5` (交易日 08:30 UTC+8) |
| workdir | `strategies/a-stock/kanban/daily-limit-radar` |
| skills | `kanban-orchestrator`, `tushare-db-fast` |
| 模型 | `deepseek-v4-flash` (opencode) |

**Cron Prompt** (`cron-prompts/preopen-check.md`):
```
读取收敛报告 + 检查隔夜外盘 + 确认今日候选股执行条件 + 生成盘前确认报告
```

---

### 6. LowOpen 每日低吸 `c14c589450b0`

| 字段 | 值 |
|------|------|
| 调度 | `13 0 * * 1-5` (交易日 00:13 UTC+8) |
| workdir | `strategies/a-stock/kanban/lowopen-daily` |
| skills | `kanban-orchestrator` |
| 模型 | `deepseek-v4-flash` (opencode) |

**Cron Prompt** (`cron-prompts/orchestrator.md`):
```
# LowOpen 每日低吸 — Cron Prompt
> 执行时间：每个交易日 00:13 (UTC+8)，任务编号 T1-T4

T1 运行筛选脚本 screen_lowopen.py → candidates.json
T2 板块概念 + 新闻搜索（依赖 T1）
T3 低吸分析（close/open >= 1.05 + buy_lg_amount_rate >= 5 + net_amount > 0）
T4 报告生成（买入条件矩阵/入场/止损/目标）
```

---

### 7. 每日行情多空辩论 `bb378f1b3b93`

| 字段 | 值 |
|------|------|
| 调度 | `0 22 * * 1-5` (交易日 22:00 UTC+8) |
| workdir | `strategies/a-stock/kanban/market-discussion` |
| skills | `kanban-orchestrator` |
| 模型 | `deepseek-v4-flash` (opencode) |

**Cron Prompt** (嵌入在 cron job 定义中):
```
# 每日行情多空辩论 — Cron Prompt
> 执行时间：每个交易日 22:00 (UTC+8)
数据来源：Tushare DB (stock_daily, daily_basic, index_daily, moneyflow_hsgt)
Bull/Bear 分析师并行辩论 → 主持人总结 → 交易员计划
```

---

## 保留任务（3 个）

| # | 任务 | job_id | 调度 | 状态 |
|---|------|--------|------|------|
| 1 | Tushare 全表每日同步 | `96a00336da56` | `0 20 * * 1-5` | ✅ 运行 |
| 2 | 策略全表挖掘 Mining-All167 | `e331f9afa57d` | `every 120m` | ✅ 运行 |
| 3 | A股盘前确认 | `e9209dd4-eed` | `30 8 * * 1-5` | ✅ 运行 |

---

## 恢复指南

如需恢复某个归档任务，执行：
```
cronjob(action='resume', job_id='<job_id>')
```
所有原始 prompt 文件仍保留在各自 workdir 的 `cron-prompts/` 目录下。
