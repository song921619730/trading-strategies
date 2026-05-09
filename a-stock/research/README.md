# 🧪 A-Stock Strategy Research & Discovery

A 股市场的 **自主策略挖掘、回测验证与历史复盘** 系统。与实盘交易流水线 (`kanban/`, `single-agent/`) **严格隔离**。

## 📡 最新状态

| 项目 | 状态 |
|------|------|
| 架构版本 | Phase A (单 Agent Orchestrator) |
| 数据源优先级 | ⭐ Tushare ClickHouse (主, 仅日线+) |
| 回测环境 | Windows Python 3.12 |
| Cron 调度 | 每周六 10:00 (UTC+8) |

## 🎯 核心目标

- **前向探索**: AI 自主分析原始数据 (日线/资金流/涨停/板块)，挖掘未预设的统计规律
- **后向复盘**: 定期读取实盘日志 (`../kanban/screening/logs/`)，从历史选股记录中总结优化规则
- **策略进化**: 将验证有效的规律转化为 `proposals/`，经用户确认后合并至实盘

## 📂 目录结构

```
research/
├── scripts/
│   ├── orchestrator.py      # 核心引擎: 发现策略 → 聚合日志 → 过滤新闻 → 生成 Brief
│   └── news_filter.py       # 新闻去重+评分 (9 数据源 → Top 10 高信噪事件)
├── briefs/                   # AI Research Brief (每次运行自动生成)
├── experiments/              # 实验实例 (每次独立隔离环境)
│   ├── 0000_reference_sentiment/  # 参考实验: 情绪溢价研究
│   └── 20260508_v11_auto/        # 最新实验工作区
├── proposals/                # 策略提案 (待用户审核)
├── templates/                # 回测脚本骨架、报告模板
├── knowledge_base.md         # 已验证发现 (防重复研究)
├── planning/
│   └── evolution_roadmap.md  # Phase A→B→C 升级路线
├── INDEX.md                  # 实验总索引
└── README.md                 # 本文件
```

## 🛠️ 数据源与工具

### 数据源优先级

| 优先级 | 数据源 | 用途 | 说明 |
|--------|--------|------|------|
| ⭐ 主 | **Tushare ClickHouse** | A 股全量数据 | `172.24.224.1:8123`，5729 只股票，2019-2026，仅日线/周线/月线 |
| 备 | **Global Futures** (Yahoo) | 跨市场关联 (油价/黄金/美元指数) | A 股情绪参考 |
| 备 | **MT5** | 全球期货/外汇 (跨资产相关性) | Exness 账户，XAUUSDm/USOILm 等 |

### A 股数据表速查

| 类别 | 主要表 | 说明 |
|------|--------|------|
| 日线行情 | `tushare_stock_daily` | OHLCV, 涨跌幅, 复权需配合 `adj_factor` |
| 基本面 | `daily_basic` | PE/PB/市值/换手率 |
| 资金流向 | `moneyflow` | 小/中/大/超大单, `moneyflow_hsgt` 北向资金 |
| 涨停/龙虎榜 | `limit_list_d`, `top_list` | 涨停统计, 龙虎榜明细 |
| 概念/板块 | `concept_detail`, `ths_index` | 概念成分股, 同花顺指数 |
| 财报 | `income`, `balancesheet`, `fina_indicator` | 利润表/资产负债表/财务指标 |

> 📖 完整 167 张表结构见 `tushare-db-fast` Skill

### 辅助工具

| 工具 | 用途 |
|------|------|
| **News Pipeline** (`http://127.0.0.1:8900`) | 9 数据源财经新闻，经 `news_filter.py` 过滤后输出 Top 10 高信噪事件 |
| **Tavily MCP** | 补充搜索 |

### 回测环境

| 项目 | 配置 |
|------|------|
| **Python** | `C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe` |
| **已安装库** | pandas, numpy, scipy, matplotlib, mplfinance, yfinance, MetaTrader5, backtrader, ta, statsmodels |
| **ClickHouse** | `http://172.24.224.1:8123/` (User: `ai_reader`) |
| **查询注意** | 必须加 `FINAL` (ReplacingMergeTree 去重)，用 `FORMAT TabSeparatedWithNames` |
| **运行注意** | WSL 下需使用 Windows 格式路径 (`F:\...`)，不能用 `/mnt/f/...` |

## 🔄 研究工作流 (Workflow)

```
Cron 触发 (周六 10:00)
    ↓
Orchestrator 启动
    ├── 1. 自动发现 A 股策略目录 (扫描 logs/)
    ├── 2. 聚合最近选股/交易日志，提取盲区
    ├── 3. 拉取 News Pipeline 24h 窗口新闻 (A 股/宏观/政治)
    ├── 4. 加载 knowledge_base.md (防重复研究)
    ├── 5. 生成 briefs/YYYYMMDD_HHMM.md
    └── 6. 初始化 experiments/YYYYMMDD_vN_auto/ 工作区
    ↓
AI Researcher 读取 Brief
    ├── 1. 分析选股盲区与市场上下文
    ├── 2. 提出 1-2 个假设 (避开已知事实)
    ├── 3. 编写 SQL + Python 分析脚本 (Tushare CH)
    ├── 4. 执行回测，统计检验
    ├── 5. 输出 report.md (结论 + 数据支撑)
    └── 6. 输出 proposal.md (如发现有实战价值)
    ↓
产出归档
    ├── 更新 experiments/*/status.json → "completed"
    ├── 更新 knowledge_base.md (归档发现)
    └── 等待用户审核 proposal
```

## 📊 已完成的实验

### `20260508_v11_auto` — 进行中 🔄
- 最新实验工作区，待 AI 自主研究

### `20260508_v1_limitup_premium` — 涨停溢价研究 ✅
- **发现**: 2 板弱转强最优 (62% 胜率)
- **提案**: 聚焦 2 板弱转强形态

## ⚠️ 核心规则

1. **隔离原则**: 严禁直接修改实盘文件 (`../kanban/`, `../single-agent/`)。所有变更通过 `proposals/` 流转
2. **数据边界**: 中间数据/日志/临时脚本必须限制在 `experiments/{id}/` 内
3. **命名规范**: 实验目录 `YYYYMMDD_v{N}_{topic}`
4. **数据源**: A 股优先用 Tushare ClickHouse，**无分钟级数据**
5. **知识沉淀**: 每次实验必须更新 `knowledge_base.md`，防止 AI 重复研究
6. **Tushare 数据延迟**: 每日 22:00 前补齐当日数据，研究以昨日及更早数据为准

## 🚀 演进路线

| 阶段 | 条件 | 说明 |
|------|------|------|
| **Phase A** (当前) | 单 Agent Orchestrator | 轻量、低成本，验证闭环 |
| **Phase B** | 上下文拥挤或需并行 | 引入 Kanban (Researcher/Analyst/Backtester) |
| **Phase C** | 多市场/多策略并行 | 全并行 Research Kanban + 自动合并验证 |

详见 `planning/evolution_roadmap.md`
