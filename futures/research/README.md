# 🧪 Futures Strategy Research & Discovery

期货市场的 **自主策略挖掘、回测验证与历史复盘** 系统。与实盘交易流水线 (`single-agent/`, `kanban/`) **严格隔离**，确保研究不干扰实时交易。

## 📡 最新状态

| 项目 | 状态 |
|------|------|
| 架构版本 | Phase A (单 Agent Orchestrator) |
| 数据源优先级 | ⭐ MT5 (主) > Yahoo Finance (备用) |
| 回测环境 | Windows Python 3.12 |
| 最近实验 | `20260508_v4_auto` — 跨品种波动率共振 |
| 最近发现 | 3+ 品种同步压缩 → 突破波幅 +129.6% |
| Cron 调度 | 每周六 09:00 (UTC+8) |

## 🎯 核心目标

- **前向探索**: AI 自主分析原始数据 (OHLCV/宏观/新闻)，挖掘未预设的统计规律
- **后向复盘**: 定期读取实盘日志 (`../single-agent/*/logs/scans/`)，从历史盈亏中总结优化规则
- **策略进化**: 将验证有效的规律转化为 `proposals/`，经用户确认后合并至实盘

## 📂 目录结构

```
research/
├── scripts/
│   ├── orchestrator.py      # 核心引擎: 发现策略 → 聚合日志 → 过滤新闻 → 生成 Brief
│   └── news_filter.py       # 新闻去重+评分 (9 数据源 → Top 10 高信噪事件)
├── briefs/                   # AI Research Brief (每次运行自动生成)
├── experiments/              # 实验实例 (每次独立隔离环境)
│   ├── 0000_reference_dxy/  # 参考实验: DXY 领先黄金 2 小时
│   ├── 20260508_v3_auto/    # ✅ 黄金波动率压缩释放 (+80% 波幅)
│   └── 20260508_v4_auto/    # ✅ 跨品种波动率共振 (+129.6% 波幅)
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
| ⭐ 主 | **MT5** (MetaTrader 5) | 期货/外汇行情 + 历史 K 线 | Exness 模拟账户，品种后缀 `m`，D1/H1/M15 数据 |
| 备 | **Yahoo Finance** (global-futures skill) | 外盘商品/指数历史 | 有限速风险，批量请求需 `time.sleep(3)` |
| 备 | **Tushare ClickHouse** | 期货合约/宏观数据 | `172.24.224.1:8123`，主要用于 A 股，期货为辅 |

### 辅助工具

| 工具 | 用途 |
|------|------|
| **News Pipeline** (`http://127.0.0.1:8900`) | 9 数据源财经新闻，经 `news_filter.py` 过滤后输出 Top 10 高信噪事件 |
| **Tavily MCP** | 补充搜索，News Pipeline 未覆盖时备用 |

### 回测环境

| 项目 | 配置 |
|------|------|
| **Python** | `C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe` |
| **已安装库** | pandas, numpy, scipy, matplotlib, mplfinance, yfinance, MetaTrader5, backtrader, ta, statsmodels |
| **MT5 路径** | `C:\Program Files\MetaTrader 5\terminal64.exe` |
| **运行注意** | WSL 下需使用 Windows 格式路径 (`F:\...`)，不能用 `/mnt/f/...` |

## 🔄 研究工作流 (Workflow)

```
Cron 触发 (周六 09:00)
    ↓
Orchestrator 启动
    ├── 1. 自动发现 strategies/ 下所有活跃策略 (扫描 logs/scans/)
    ├── 2. 聚合最近扫描日志，提取盲区与性能聚类
    ├── 3. 拉取 News Pipeline 6h 窗口新闻，去重评分
    ├── 4. 加载 knowledge_base.md (防重复研究)
    ├── 5. 生成 briefs/YYYYMMDD_HHMM.md
    └── 6. 初始化 experiments/YYYYMMDD_vN_auto/ 工作区
    ↓
AI Researcher 读取 Brief
    ├── 1. 分析策略诊断与市场上下文
    ├── 2. 提出 1-2 个假设 (避开已知事实)
    ├── 3. 编写回测脚本 (MT5 / Yahoo / ClickHouse)
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

### `20260508_v4_auto` — 跨品种波动率共振 ✅
- **假设**: 多品种同时进入低波动压缩时，随后突破比单品种更强
- **方法**: MT5 7 品种 2.5 年日线数据，构建同步指数
- **发现**: 3+ 品种同步压缩 → 5 日波幅 +129.6%；原油/布油放大 190-253%
- **提案**: 增加 "Sync Compression Alert" 层，不改变现有 Trade Gate

### `20260508_v3_auto` — 黄金波动率压缩释放 ✅
- **假设**: ATR 压缩后释放瞬间波动更大
- **方法**: MT5 黄金 1 年 H1 数据
- **发现**: Release 瞬间大波动概率 37.1% vs 基线 20.6% (+80%)
- **提案**: Trade Gate 从"硬性拦截"改为"寻找突破"

### `20260508_v1_dxy_lead_lag` — DXY 领先黄金 ✅
- **发现**: DXY 变动领先黄金约 2 小时
- **提案**: 增加 DXY 异动过滤

## ⚠️ 核心规则

1. **隔离原则**: 严禁直接修改实盘文件 (`../single-agent/`, `../kanban/`)。所有变更通过 `proposals/` 流转
2. **数据边界**: 中间数据/日志/临时脚本必须限制在 `experiments/{id}/` 内
3. **命名规范**: 实验目录 `YYYYMMDD_v{N}_{topic}`
4. **数据源**: 期货优先用 MT5，A 股优先用 Tushare ClickHouse
5. **知识沉淀**: 每次实验必须更新 `knowledge_base.md`，防止 AI 重复研究

## 🚀 演进路线

| 阶段 | 条件 | 说明 |
|------|------|------|
| **Phase A** (当前) | 单 Agent Orchestrator | 轻量、低成本，验证闭环 |
| **Phase B** | 上下文拥挤或需并行 | 引入 Kanban (Researcher/Analyst/Backtester) |
| **Phase C** | 多市场/多策略并行 | 全并行 Research Kanban + 自动合并验证 |

详见 `planning/evolution_roadmap.md`
