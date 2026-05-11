# DLR 涨停雷达 — 每日涨停选股策略

> 策略名称：Daily Limit Radar (DLR)
> 市场：A 股
> 方法：涨停池 + 10 因子评分 + 三层分层收敛
> 数据源：Tushare DB (ClickHouse, 167 张表) + MT5 + global-futures

## 策略逻辑

基于原版 `limit_line_radar.py` 改造，100% 保留原版选股逻辑：

1. **情绪周期四阶段**：启动 → 发酵 → 高潮 → 退潮
2. **10 因子打分**：涨停强度/连板高度/板块效应/资金流向/换手率匹配/市值弹性/位置评估/成交量配合/预期差催化/技术共振（0-5 分制，满分 50 分）
3. **三层分层收敛**：待涨观察池（≥34）/ 预备突破池（30-33）/ 强确认跟踪池（26-29）
4. **待涨优先原则**：最终候选中待涨池 ≥ 50%
5. **风险硬淘汰**：7 项硬淘汰条件 + 4 级风险扣分

## 目录结构

```
daily-limit-radar/
├── cron-prompts/           # Cron 任务提示词（3 个阶段）
│   ├── postclose-screen.md # 盘后初筛 T1-T7（22:30）
│   ├── postclose-converge.md # 盘后收敛 T8-T14（23:00）
│   └── preopen-check.md    # 盘前确认 T15-T17（08:30）
├── skills/                 # 业务规则
│   ├── researcher-soul.md  # 通用数据研究员
│   ├── analyst-soul.md     # 通用分析师
│   ├── writer-soul.md      # 通用报告撰写人
│   ├── reze-soul.md        # 通用主控
│   ├── scoring-engine.md   # DLR 10 因子打分体系
│   ├── risk-rules.md       # DLR 风险过滤规则
│   └── README.md           # 技能使用说明
├── templates/              # SQL 模板（query_sql 专用工具不支持时使用）
│   ├── limit_pool.sql      # 涨停池查询
│   ├── industry_cluster.sql # 板块聚类
│   ├── kline_scan.sql      # K 线扫描
│   ├── factor_data.sql     # 因子数据预计算
│   └── moneyflow.sql       # 资金流向
├── scripts/                # 数据脚本（MT5/ global-futures）
│   ├── mt5_overnight.py    # MT5 全球行情获取
│   └── global_futures.py   # yfinance 国际期货（已共享）
├── logs/                   # 每次运行日志
└── reports/                # 最终报告
```

## 数据源与工具

| 数据源 | 工具/方式 | 用途 |
|--------|----------|------|
| **Tushare DB MCP** | `query_sql` / `trade_calendar` / `get_ohlcv` / `get_moneyflow` / `get_financials` | A 股日线/资金/财报（优先使用专用工具） |
| **Tushare DB Skill** | `tushare-db-fast` | 167 张表结构、SQL 常用查询模板 |
| **MT5** | Windows Python inline -c | 全球行情（美股/黄金/原油/汇率/恒指/日经） |
| **global-futures** | `/mnt/f/AIcoding_space/skills/global-futures/scripts/global_futures.py` | 国际期货（大宗商品/利率） |
| **Tavily** | `tavily_search` | 新闻/政策搜索 |

### 数据窗口

| 数据类型 | 窗口 | 用途 |
|---------|------|------|
| **日线 OHLCV** | 120 日（半年） | F7 位置评估 / F10 技术共振 |
| **估值 PE/PB** | 120 日（半年） | F6 市值弹性趋势 |
| **资金流向** | 60 日（约 3 个月） | F4 资金流向趋势 |
| **涨停历史** | 60 日（约 3 个月） | F1 涨停强度 / F2 连板高度 |
| **板块趋势** | 60 日（约 3 个月） | F3 板块效应 |
| **北向资金** | 30 日 | 市场情绪参考 |

## 流水线

### Phase 1: 盘后初筛（22:30，7 任务）
```
T1 researcher → 交易日历确认
T2 researcher → 涨停池数据拉取          (并发)
T3 researcher → 板块聚类分析            (并发)
T4 researcher → 情绪指标拉取            (并发)
T5 analyst → 财经扫描与风险初筛         (等 T2/3/4)
T6 analyst → 主控初筛与 10 因子预评分    (等 T5)
T7 writer → 盘后初筛报告                (等 T6)
```

### Phase 2: 盘后收敛（23:00，7 任务）
```
T8 researcher → 候选股价格确认
T9 analyst → 财经专家 F9 评分           (并发，等 T8)
T10 analyst → 技术专家 F10 评分         (并发，等 T8)
T11 analyst → 资金专家 F4 重评          (并发，等 T8)
T12 analyst → 板块专家 F3 重评          (并发，等 T8)
T13 analyst → 主控裁决与完整打分         (等 T9-12)
T14 writer → 盘后收敛报告               (等 T13)
```

### Phase 3: 盘前确认（08:30，3 任务）
```
T15 researcher → 隔夜外盘与盘前数据
T16 analyst → 分层调整与执行建议         (等 T15)
T17 writer → 盘前确认报告               (等 T16)
```

## Cron Job 配置

```python
# 盘后初筛（周一至周五 22:30）
cronjob(action="create",
    name="DLR 盘后初筛",
    schedule="30 22 * * 1-5",
    workdir="/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/daily-limit-radar",
    prompt="./cron-prompts/postclose-screen.md",
    skills=["kanban-orchestrator", "tushare-db-fast"],
    enabled_toolsets=["terminal", "file", "web", "delegation"],
    deliver="qqbot:83715B86A7F1936F401F0784AEAF3D",
)

# 盘后收敛（周一至周五 23:00）
cronjob(action="create",
    name="DLR 盘后收敛",
    schedule="0 23 * * 1-5",
    workdir="/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/daily-limit-radar",
    prompt="./cron-prompts/postclose-converge.md",
    skills=["kanban-orchestrator", "tushare-db-fast"],
    enabled_toolsets=["terminal", "file", "web", "delegation"],
    deliver="qqbot:83715B86A7F1936F401F0784AEAF3D",
)

# 盘前确认（周一至周五 08:30）
cronjob(action="create",
    name="DLR 盘前确认",
    schedule="30 8 * * 1-5",
    workdir="/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/daily-limit-radar",
    prompt="./cron-prompts/preopen-check.md",
    skills=["kanban-orchestrator", "tushare-db-fast"],
    enabled_toolsets=["terminal", "file", "web", "delegation"],
    deliver="qqbot:83715B86A7F1936F401F0784AEAF3D",
)
```

## Profile 分工

| Profile | 模型 | 本次用途 |
|---------|------|---------|
| `reze` | qwen3.6-plus | Orchestrator（创建任务图） |
| `researcher` | deepseek-v4-flash | 纯数据查询 |
| `analyst` | deepseek-v4-pro | 4 专家分析 + 主控裁决 |
| `writer` | deepseek-v4-flash | 报告格式化 |
| `risk_manager` | deepseek-v4-pro | 风险过滤 |
| `trader` | deepseek-v4-pro | 执行决策（可选） |

## 日志规范

- 初筛阶段：`screen-{YYYYMMDD}-{01-07}-{步骤名}.md`
- 收敛阶段：`converge-{YYYYMMDD}-{08-14}-{步骤名}.md`
- 盘前阶段：`preopen-{YYYYMMDD}-{15-17}-{步骤名}.md`
- 报告同时保存到 `reports/` 和 `logs/`
