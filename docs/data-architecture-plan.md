# 期货数据架构方案书

> **目标**: 构建统一、高效、可扩展的期货数据基础设施，支持多策略并行研究
> **原则**: Parquet 存算一体 + DuckDB 即席查询，零额外运维成本
> **状态**: 草案 v2 — 含完整运行环境说明（供 AI 执行者参考）

---

## 0. 运行环境全景（AI 执行者必读）

> ⚠️ 本节包含执行本方案所需的全部交易环境上下文。
> **在执行任何操作之前，先通读本节，避免因环境不熟导致错误。**

---

### 0.1 项目结构

```
Repository: 单一 Git 仓库
  Path: /mnt/f/AIcoding_space/Hermes/strategies/
  Remote: git@github.com:song921619730/trading-strategies.git (SSH)
  Git: WSL 内直接 git push（HTTPS 可通，SSH 已配置）

  市场分区:
    futures/  → 期货（14 MT5 品种）
    a-stock/  → A 股（日线+，Tushare ClickHouse）

  目录约定:
    research/kanban/{strategy-name}/   ← 研究项目
      data/         ← K 线 + 预计算 parquet
      scripts/      ← 研究引擎脚本
      state/        ← research_state.json（迭代状态）
      reports/      ← 每轮研究报告（时间戳命名）
      cron-prompts/ ← Cron Job 提示模板
      skills/       ← 智能体 Profile 配置
      logs/         ← 日志

    single-agent/{strategy-name}/      ← 交易系统
    scripts/        ← 市场级通用脚本
    data/           ← 中央数据目录（本方案目标）
    docs/           ← 文档
```

---

### 0.2 MT5 交易环境

| 参数 | 值 |
|:----|:----|
| **经纪商** | Exness Demo |
| **连接方式** | WSL → Windows Python 312 (WSL 调用 Windows 解释器) |
| **Windows Python** | `C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe` |
| **MT5 初始化** | `mt5.initialize(path=r'C:\Program Files\MetaTrader 5\terminal64.exe')` |
| **品种命名** | **不带 `m` 后缀**（XAUUSD ✅, XAUUSDm ❌） |
| **可用品种(14)** | XAUUSD, XAGUSD, USTEC, US30, US500, JP225, HK50, USOIL, UKOIL, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF |
| **账户余额** | ~$2,083.16 (Demo) |
| **交易时段** | 亚盘 UTC 0-8, 欧盘 UTC 8-13, 美盘 UTC 13-22 |
| **Magic 号分配** | 234003 ❌(废弃 Pure AI CIO), 234004 (Triumvirate), 234011 (Scalping), 234012 (High-RR) |
| **脚本中 MT5 路径** | 用 `F:/` 而非 `/mnt/f/`（Windows Python 理解 F:\ 格式） |

**Windows Python 调用示例**（从 WSL 执行 MT5 操作时必用此格式）：
```bash
# 正确 ✅
/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \
  F:/AIcoding_space/Hermes/strategies/futures/scripts/some_mt5_script.py

# 错误 ❌（WSL Python 没有 MT5 库）
python3 F:/AIcoding_space/Hermes/strategies/futures/scripts/some_mt5_script.py
```

**⚠️ 关键约束**：
- WSL 的 Linux Python（python3）不能连接 MT5（无 MetaTrader5 库）
- 所有涉及 MT5 的操作（数据拉取、下单、查询持仓）必须用 Windows Python
- 纯数据处理（读 parquet、回测、分析）可用 WSL Python3，速度更快

---

### 0.3 运行中的系统

| 系统 | 类型 | 周期 | 说明 |
|:----|:----|:----|:------|
| **Scalping Autopilot** | systemd user service | 每 60 秒 | Magic 234011，SL=ATR(M5)×2.5，TP=ATR×3.75(RR=1.5)，最大 6 笔持仓 |
| **Triumvirate 三AI共识** | Hermes Cron | 每 15 分钟 | Magic 234004，3 AI 投票(analyst+risk_manager+president)，3:0 才执行 |
| **High-RR 研究** | Hermes Cron | 每 2 小时 | ID: `scalping-highrr-research`，低胜率高盈亏比策略挖掘 |
| **Scalping M1 研究** | Hermes Cron | 每 15 分钟 | RSI 阈值梯度扫描 |
| **Candlestick 形态研究** | Hermes Cron | 每小时 | K 线形态 + 指标交叉验证 |
| **Futures Intraday 研究** | Hermes Cron | 每小时 | H1/M30 日内动量 |
| **A 股研究** | Hermes Cron | 每小时(工作日) | Kanban 状态驱动 |
| **Scalping Status Report** | Hermes Cron | 每 15 分钟 | 账户/持仓状况推送 |
| **Tushare 日线同步** | Hermes Cron | 每日 22:00 | A 股数据补齐 |

**所有研究 Cron Job 当前状态**：部分暂停（`lowopen-research`, `futures-intraday-research`, `Futures Intraday Algo`, `candlestick-patterns-research`, `futures-research`, `a-stock-research`），原因未知。

---

### 0.4 数据管道

```
MT5 (主数据源)
  │  Windows Python 拉取
  ▼
Raw parquet (OHLC only)
  │  precompute_indicators.py 计算 460+ 指标
  ▼
Enhanced parquet (467 cols × 14 symbols × H1/M5)
  │  研究引擎读取 / DuckDB 查询
  ▼
策略发现 → auto_inject → trading system
```

| 数据维度 | 说明 |
|:---------|:-----|
| **期货数据量** | 14 品种 × 2 时间框架(H1/M5) × 467 列 = ~800MB |
| **H1 数据范围** | 2026-01-28 ~ 2026-05-12（~1670 行/品种） |
| **M5 数据范围** | 同上（~100,158 行/品种） |
| **A 股数据** | Tushare ClickHouse `172.24.224.1:8123`，日线+，仅日线/周线/月线（无分钟级） |
| **研究用数据** | 仅限 parquet，不回 MT5 频繁拉取 |
| **预计算性能** | 467 列全量计算 14 品种 M5 耗时约 8 分钟（单线程） |

**⚠️ 注意**：
- 预计算脚本使用逐列 `df[col] = ...` 方式插入列，会触发 pandas `PerformanceWarning: DataFrame is highly fragmented` —— **这是无害的**，不影响数据正确性
- 如要消除警告，可用 `pd.concat([df, new_cols], axis=1)` 方式重构
- 文件系统路径用 `/mnt/f/`（WSL 视角），但给 Windows Python 传路径时用 `F:/`

---

### 0.5 风控纪律（不可违反）

以下规则在所有交易系统中强制执行：

| # | 规则 | 说明 |
|:-:|:----|:------|
| 1 | **SL/TP 必须带** | 所有开仓/挂单必须同时设置止损和止盈 |
| 2 | **RR ≥ 1:1** | 禁止盈亏比小于 1:1 的交易 |
| 3 | **SL ≥ 1× ATR(14)** | 止损距离不得小于 1 倍 ATR14 |
| 4 | **动态仓位** | 单笔风险 ≤ 5% 净值，手数 = (净值 × 5%) / (SL 点数 × 合约价值) |
| 5 | **禁止重复持仓** | 同一品种同一方向只能有 1 笔持仓 |
| 6 | **相关性检查** | 高度相关品种（如 USOIL/UKOIL, EURUSD/GBPUSD）不宜同时持有 |

**研究系统**：
- 注入门槛（auto_inject）：Sharpe > 1.5 + PF > 2.0 + n > 80（High-RR）
- Scalping 注入门槛：WR > 60% + n > 100
- 回测报告必须声明：前视偏差、参数泄漏、成本未计入、保证金未计入

---

### 0.6 重要操作约束

| 类别 | 约束 |
|:----|:-----|
| **文件搜索** | ❌ 不要用 `find /`（超时）。用 `find /mnt/f/AIcoding_space/` 或已知路径 |
| **文件操作** | 读文件用 `read_file` 工具，不用 cat。写文件用 `write_file`，不用 echo heredoc |
| **Git 提交** | `cd /mnt/f/AIcoding_space/Hermes/strategies && git add -A && git commit -m "msg" && git push` |
| **Cron Job** | 研究 Cron deliver=local（存文件不推送），交易相关 Cron deliver=origin |
| **报告语言** | 所有 Cron 报告、推送消息必须用中文 |
| **报告存档** | 每次研究轮次报告必须存文件（`reports/` 目录，时间戳命名） |
| **高频查询** | 不要每 15 分钟扫描全部 14 品种做全量回测。研究引擎用 state 驱动增量迭代 |
| **symlink** | Git 不追踪 parquet 文件。symlink 可以被追踪，但 `.gitignore` 要排除 parquet 实际路径 |
| **一致性检查** | 每次修改参数、地址、规则后，搜索所有相关文件同步更新（代码、配置、文档、Cron Prompt、jobs.json） |
| **A 股研究** | A 股不能做空，发现做空逻辑的策略直接否决 |
| **账户余额查询** | MT5 连接后调用 `mt5.account_info()` 获取，不要硬编码余额 |
| **品种覆盖** | 期货研究必须覆盖全部 14 品种，A 股必须全市场扫描 |

---

### 0.7 策略注入机制

策略从研究到交易的完整链路：

```
研究引擎 → research_state.json → auto_inject.py → strategies.json → scanner → execute

步骤说明:
1. 研究引擎每轮迭代生成 findings（策略参数 + 回测指标）
2. research_state.json 记录 best_findings（按 Sharpe/PF 排名）
3. auto_inject.py 读取 best_findings，过滤（Sharpe>1.5, PF>2.0, n>80）
4. 通过的策略写入 {strategy_name}_strategies.json
5. scanner 每分钟/5分钟读取 strategies.json，匹配当前行情
6. 信号触发 → execute_trade.py 下单（Magic 号隔离）

文件:
  strategies.json 格式：
  {
    "XAUUSD": [
      {
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "entry_condition": "rsi14 < 40 and session == 'us'",
        "direction": "long",
        "sl_multiple": 1.0,
        "tp_multiple": 5.0,
        "sharpe": 1.8,
        "pf": 2.3,
        "win_rate": 0.35,
        ...
      }
    ]
  }

注意:
- 每个策略系统有独立的 strategies.json（scalping_strategies.json, high_rr_strategies.json）
- Magic 号隔离：scanner 只扫描自己的 Magic 号策略
- 自动注入只发生在研究引擎确认策略有效之后
```

---

## 1. 现状与痛点

### 1.1 当前状况

```
strategies/futures/
├── research/kanban/
│   ├── futures-intraday/       ← 各有自己的 H1/M30 parquet
│   ├── scalping-m1/            ← 各有自己的 H1/M5/M30/M1 parquet
│   ├── candlestick-patterns/    ← 各有自己的 H1/M30 parquet
│   └── high-rr-research/       ← 各有自己的 H1/M5 parquet (含 467 列增强版)
```

### 1.2 核心问题

| # | 问题 | 后果 |
|:-:|:----|:-----|
| 1 | **数据冗余** — 每个研究项目的 `data/` 目录各自存一份 parquet | 占用 F 盘 ~15GB 重复数据，每个品种的 H1 数据在 4 个项目里各有副本 |
| 2 | **版本漂移** — high-rr 有 467 列增强版，其他项目只有原始 OHLC | scalping 研究用的是原始 K 线，错过增强指标；K线形态研究只用 OHLC 算形态，无法用预计算指标交叉验证 |
| 3 | **新策略启动成本高** — 每增一个研究项目，先拷一遍数据，再写一遍指标计算 | 每次 `cp -r` 几 GB 数据，加新指标要改 4 个脚本 |
| 4 | **无法跨品种/跨策略查询** — "找出所有 H1 上 RSI<30 且 ADX>25 的时刻" 需要写 Python 脚本 | 探索性分析阻力大 |

---

## 2. 架构方案

### 2.1 总体设计

```
┌──────────────────────────────────────────────────────────────┐
│                   Central Data Hub                            │
│         strategies/futures/data/                             │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  raw/    ← MT5 原始 tick/分钟数据 (不动)              │     │
│  │  parquet/ ← 统一预计算增强 parquet (467列)           │     │
│  │    H1/ 14_symbols × 467_cols                         │     │
│  │    M5/ 14_symbols × 467_cols                         │     │
│  │    M15/ (可选)                                       │     │
│  │  cache/  ← DuckDB 持久化查询缓存                     │     │
│  │  scripts/  ← 数据更新/预计算脚本                      │     │
│  └─────────────────────────────────────────────────────┘     │
│                         │                                      │
│          ┌──────────────┼──────────────┐                      │
│          ▼              ▼              ▼                        │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                  │
│  │high-rr     │ │scalping-m1 │ │futures-    │  ...更多策略     │
│  │(symlink→)  │ │(symlink→)  │ │intraday    │                  │
│  └────────────┘ └────────────┘ └────────────┘                  │
│                         │                                      │
│          ┌──────────────┘                                      │
│          ▼                                                      │
│  ┌──────────────────────────────────────────┐                  │
│  │         DuckDB 查询层 (零迁移)              │                  │
│  │  python duck_query.py "SELECT ..."         │                  │
│  │  → 直接读取 parquet，SQL 跨品种/跨 TF 查询   │                  │
│  └──────────────────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 核心决策

#### 为什么用 Parquet + DuckDB，不用 ClickHouse/InfluxDB？

| 方案 | 优势 | 劣势 | 结论 |
|:----|:----|:-----|:----:|
| **Parquet (现状)** | 列式存储，读特定列极快；零运维；pandas 原生支持 | 不能 SQL 查询；每个项目独立副本 | ✅ **存储主力** |
| + **DuckDB** | 零迁移直接读 parquet；完整 SQL；嵌入式无服务 | 不适合高并发写入；无权限管理 | ✅ **查询层** |
| ClickHouse (已有) | 适合 A 股 Tushare 的大宽表；分布式查询 | 期货数据量太小，杀鸡用牛刀；需数据导入管道 | ❌ 留给 A 股 |
| SQLite | 简单嵌入式 | 列存性能差，不适合 467 列宽表 | ❌ 不合适 |
| MongoDB | 灵活 schema | 分析性能差，不支持列存 | ❌ 不合适 |

**结论**: Parquet 存 + DuckDB 查 = 最佳组合。

#### 为什么用 Symlink 而非拷贝？

```bash
# 每个研究项目创建软链接，而非拷贝
ln -s ../../../data/parquet/H1  research/kanban/high-rr-research/data/H1
```

- 一改全改：补充增强指标 → 只跑一次 precompute 脚本 → 所有项目立即可用
- 零存储浪费：14品种 × 2TF × 467列 = ~800MB（而不是 4×800MB = 3.2GB）
- 无版本漂移：所有研究项目始终读取同一份数据

---

## 3. 目录结构设计

```
strategies/futures/
├── data/                              ← 中央数据目录（新）
│   ├── parquet/                       ← 统一预计算增强 parquet
│   │   ├── H1/                        ← 14品种 × 467列
│   │   ├── M5/                        ← 14品种 × 467列
│   │   ├── M15/                        ← (按需)
│   │   └── metadata.json              ← 列说明、版本号、最后更新日期
│   ├── raw/                           ← MT5 原始数据（不动）
│   ├── cache/                         ← DuckDB 持久化视图/缓存
│   ├── scripts/                       ← 中央数据维护脚本
│   │   ├── precompute_indicators.py   ← 全量预计算（单源）
│   │   ├── sync_from_mt5.py           ← MT5 → parquet 同步
│   │   ├── duck_query.py              ← DuckDB 查询工具
│   │   └── update_daily.py            ← 每日增量更新
│   └── README.md                      ← 数据目录说明
│
├── research/kanban/
│   ├── high-rr-research/
│   │   └── data → ../../../data/parquet/   ← symlink
│   ├── scalping-m1/
│   │   └── data → ../../../data/parquet/   ← symlink
│   ├── futures-intraday/
│   │   └── data → ../../../data/parquet/   ← symlink
│   └── candlestick-patterns/
│       └── data → ../../../data/parquet/   ← symlink
│
└── docs/
    └── data-architecture-plan.md       ← 本文件
```

---

## 4. DuckDB 查询层

### 4.1 工具设计

```bash
# 基本语法
python duck_query.py "SELECT ... [ FROM 'pattern.parquet' ]"

# 示例
python duck_query.py "
    SELECT symbol, COUNT(*) as n, AVG(rsi14) as avg_rsi
    FROM 'H1/*_enhanced.parquet'
    WHERE adx_14 > 25 AND chop_14 < 30
    GROUP BY symbol ORDER BY n DESC
"
```

### 4.2 典型查询场景

| 场景 | SQL | 用途 |
|:----|:----|:-----|
| 强趋势品种扫描 | `WHERE adx_14>25 AND chop_14<30` | 找趋势行情标的 |
| 超卖反弹机会 | `WHERE rsi14<30 AND return_5>0` | 均值回归入场 |
| 大波动日 | `WHERE atr_percentile_14>0.8` | 筛选活跃品种 |
| 阻力位附近 | `WHERE near_resistance_20=1 AND rsi14>70` | 找潜在反转 |
| K线形态+指标 | `WHERE doji=1 AND volume_ratio_5>1.5` | 形态验证 |
| 跨TF验证 | JOIN H1 和 M5 判断方向一致性 | 多周期分析 |

### 4.3 进阶：缓存高频查询

对于跨研究项目频繁使用的中间结果（如每日更新的品种排名），可存为 DuckDB 持久化视图：

```python
# cache 层思想
views = {
    "strong_trend": "SELECT * FROM 'H1/*_enhanced.parquet' WHERE adx_14>25 AND chop_14<30",
    "oversold": "SELECT * FROM 'H1/*_enhanced.parquet' WHERE rsi14<30",
}
```

---

## 5. 指标目录与发现系统 ⭐

### 5.1 问题：460 个指标藏在 parquet 里，研究引擎看不见

```
现状：
                        ┌─────────────────┐
  460个指标躺在        │ research_engine  │
  parquet 文件里       │   required_cols  │ ← 硬编码了 7 个列名
                        │   = ["rsi14",    │    剩下 453 个指标
                        │      "atr14",    │    根本不知道存在
                        │      "hh_20"...] │
                        └─────────────────┘

                        ┌─────────────────┐
                        │ candlestick     │
                        │   engine        │ ← 人写字符串条件，要先知道列名
                        │   "doji and     │
                        │    rsi14 < 40"  │
                        └─────────────────┘
```

### 5.2 方案：自动生成指标目录 + 发现函数

预计算脚本跑完后，自动生成一个 `column_registry.json` 文件，记录每个指标的元信息：

```json
{
  "version": "1.0",
  "generated_at": "2026-05-13T18:30:00",
  "indicators": {
    "rsi14": {
      "category": "momentum",
      "subcategory": "rsi",
      "description": "RSI 14-period",
      "type": "float",
      "range": [0, 100],
      "parameters": {"period": 14}
    },
    "adx_14": {
      "category": "trend",
      "subcategory": "adx",
      "description": "ADX 14-period",
      "type": "float",
      "range": [0, 100]
    },
    "doji": {
      "category": "pattern",
      "subcategory": "single_candle",
      "description": "Doji candlestick pattern",
      "type": "bool"
    },
    "bb_20_2_width": {
      "category": "volatility",
      "subcategory": "bollinger",
      "description": "Bollinger Band width (20,2)",
      "type": "float"
    },
    "volume_ratio_5": {
      "category": "volume",
      "subcategory": "ratio",
      "description": "Volume ratio vs 5-period MA",
      "type": "float"
    },
    "guppy_short_spread": {
      "category": "trend",
      "subcategory": "guppy",
      "description": "Guppy MMA short-term MA spread",
      "type": "float"
    },
    "session": {
      "category": "time",
      "subcategory": "session",
      "description": "Trading session (asia/europe/us)",
      "type": "categorical",
      "values": ["asia", "europe", "us"]
    }
  }
}
```

### 5.3 发现函数 API

提供两个核心函数，让研究引擎和 AI 能自动探索可用指标：

```python
# 1. 按类别列出指标
list_indicators(category="momentum")
# → ["rsi5", "rsi7", "rsi14", "rsi21", "rsi50",
#     "macd", "macd_signal", "macd_hist",
#     "mom_5", "mom_10", "mom_14", "mom_20", "mom_50",
#     "kst", "kst_signal", "ultimate_osc", ...]

# 2. 按多条件筛选
list_indicators(category="volatility", type="bool")
# → ["high_volatility", "atr7_high", "atr7_low",
#     "atr14_high", "atr14_low", "atr21_high", ...]

# 3. 获取完整目录字典
get_indicator_registry()
# → {col_name: {category, description, type, ...}, ...}

# 4. 检查特定列是否存在
indicator_exists("hurst_exponent_20")
# → True

# 5. 获取全部类别列表
get_categories()
# → ["trend", "momentum", "volatility", "volume",
#     "pattern", "structure", "time", "statistical"]
```

### 5.4 在预计算脚本中自动生成

将 `column_registry.json` 的生成集成到 `precompute_indicators.py`：

```python
def generate_column_registry(df: pd.DataFrame) -> dict:
    """自动从 DataFrame 列名推断指标目录"""
    registry = {"version": "1.0", "generated_at": datetime.now().isoformat(), "indicators": {}}
    for col in df.columns:
        registry["indicators"][col] = classify_column(col)
    return registry
```

`classify_column()` 根据列名前缀自动分类（`rsi*` → momentum, `adx*` → trend, `bb_*` → volatility, `ma*` → trend 等）。

### 5.5 研究引擎集成方式

```python
# 研究引擎启动时自动加载指标目录
from indicator_registry import list_indicators

# 全空间搜索：遍历所有动量指标
momentum_cols = list_indicators(category="momentum", type="float")
for col in momentum_cols:
    # 用每个指标的不同阈值做回测
    for threshold in [20, 25, 30, 35]:
        result = run_backtest(entry=f"{col} < {threshold}")
        
# AI 写策略时先查目录
available = list_indicators()
# 输出: "可用 460 个指标，分布在 8 个类别：趋势 85个、动量 42个、…"
```

### 5.6 与 DuckDB 整合

通过 SQL 直接查询指标目录：

```bash
python duck_query.py "SELECT * FROM read_json_auto('column_registry.json')
WHERE category='momentum' AND type='float'"
```

或在 DuckDB 中 JOIN 指标目录和数据：

```sql
-- 找出所有动量指标中当前处于极端值的品种
WITH momentum_cols AS (
    SELECT key as col_name
    FROM read_json_auto('column_registry.json')
    WHERE category='momentum'
)
SELECT * FROM 'H1/*_enhanced.parquet'
WHERE rsi14 < 30 OR rsi7 < 25
```
---

## 6. 查询场景与应用

### 6.1 典型查询场景

| 场景 | SQL | 用途 |
|:----|:----|:-----|
| 强趋势品种扫描 | `WHERE adx_14>25 AND chop_14<30` | 找趋势行情标的 |
| 超卖反弹机会 | `WHERE rsi14<30 AND return_5>0` | 均值回归入场 |
| 大波动日 | `WHERE atr_percentile_14>0.8` | 筛选活跃品种 |
| 阻力位附近 | `WHERE near_resistance_20=1 AND rsi14>70` | 找潜在反转 |
| K线形态+指标 | `WHERE doji=1 AND volume_ratio_5>1.5` | 形态验证 |
| 跨TF验证 | JOIN H1 和 M5 判断方向一致性 | 多周期分析 |
| **指标探索** | `SELECT * FROM read_json_auto('column_registry.json') WHERE category='momentum'` | 查某类有哪些指标 |

### 6.2 进阶：缓存高频查询

对于跨研究项目频繁使用的中间结果（如每日更新的品种排名），可存为 DuckDB 持久化视图：

```python
views = {
    "strong_trend": "SELECT * FROM 'H1/*_enhanced.parquet' WHERE adx_14>25 AND chop_14<30",
    "oversold": "SELECT * FROM 'H1/*_enhanced.parquet' WHERE rsi14<30",
}
```

### 6.3 AI 写策略时的标准流程

当 AI 研究者启动一个新策略研究时，应该按以下顺序操作：

```python
from indicator_registry import list_indicators, indicator_exists

# 1. 查看全部可用指标
available = list_indicators()       # → 460 个指标，8 个类别

# 2. 只看动量类
momentum = list_indicators(category="momentum")  # → 42 个指标

# 3. 只看布尔型的（形态、状态标志）
flags = list_indicators(type="bool")  # → 30+ 个指标

# 4. 确认列名写法
indicator_exists("rsi14")            # → True
indicator_exists("nvi")              # → True

# 5. 用选定的列写策略条件
strategy = {
    "entry_condition": "rsi14 < 27 and nvi < nvi_ma and doji == 1",
    "direction": "long",
    "sl_multiple": 1.0,
    "tp_multiple": 5.0,
}
```

这样就不会遗漏可用指标，也不会写错列名。

---

## 7. 实施计划

> ⚠️ **AI 执行者注意**：以下每个 Phase 的每步都附有执行备注。
> 执行前请对照 Section 0 的运行环境全景，确认路径、工具、约束。

---

### Phase 1: 中央化（~2 小时）

**目标**：把分散在各研究项目下的 parquet 文件集中到 `strategies/futures/data/parquet/`，各项目用 symlink 引用。

- [ ] **Step 1: 创建中央目录**
  ```bash
  mkdir -p /mnt/f/AIcoding_space/Hermes/strategies/futures/data/parquet/{H1,M5}
  ```
  > ⚠️ 路径用 `/mnt/f/`（WSL 视角），不是 `F:/`

- [ ] **Step 2: 迁移增强 parquet 文件**
  ```bash
  # 源: high-rr-research/data/{H1,M5}/*_enhanced.parquet
  # 目标: futures/data/parquet/{H1,M5}/
  cp /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/high-rr-research/data/H1/*_enhanced.parquet \
     /mnt/f/AIcoding_space/Hermes/strategies/futures/data/parquet/H1/
  cp /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/high-rr-research/data/M5/*_enhanced.parquet \
     /mnt/f/AIcoding_space/Hermes/strategies/futures/data/parquet/M5/
  ```
  > ⚠️ 用 `cp` 而不是 `mv`，保留源文件作为备份，确认没问题后删源。
  > ⚠️ `cp` 大文件时注意文件系统可用空间（F: 盘当前 49% 使用，3.7T/1.8T 已用）。

- [ ] **Step 3: 各研究项目创建 symlink**
  ```bash
  cd /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/high-rr-research
  rm -rf data   # 删掉旧的 data 目录（先确认里面有 _enhanced 备份）
  ln -s ../../../data/parquet data
  
  # 对其他项目同理：
  # research/kanban/scalping-m1/data
  # research/kanban/futures-intraday/data
  # research/kanban/candlestick-patterns/data
  ```
  > ⚠️ `rm -rf data` 前先确认 data 内容已迁移。可以先 `ls data/H1/*_enhanced.parquet | wc -l` 看有没有增强文件
  > ⚠️ symlink 路径是**相对路径**，从研究项目目录到中央目录。`ln -s ../../../data/parquet data`
  > ⚠️ symlink 本身可以被 Git 追踪，在 Git 提交时确认 `.gitignore` 排除了实际 parquet 文件

- [ ] **Step 4: 更新 data_loader.py 路径**
  > 每个研究项目的 data_loader.py 里有 `DATA_DIR` 变量指向 `../data`。
  > symlink 后路径不变（因为 symlink 就是 `data → ../../../data/parquet`），
  > 但如果 data_loader.py 用了绝对路径或额外子目录名，需要修改。
  ```bash
  # 验证各项目 data_loader 是否能正常加载
  cd /mnt/f/AIcoding_space/Hermes/strategies
  python3 -c "
  import sys
  sys.path.insert(0, 'futures/research/kanban/high-rr-research/scripts')
  from data_loader import load_data
  d = load_data('H1', symbols=['XAUUSD'])
  print('XAUUSD H1:', d['XAUUSD'].shape)
  "
  ```
  > ✅ 预期输出 `XAUUSD H1: (1673, 467)`（或类似行数）

- [ ] **Step 5: 添加 .gitignore 规则**
  ```
  # 在 strategies/.gitignore 中添加：
  futures/data/parquet/*.parquet
  ```
  > ⚠️ 不排除的话，`git add` 会尝试追踪 800MB 的 parquet 文件

- [ ] **Step 6: 清理旧数据（确认无误后）**
  ```bash
  # 确认中央目录文件完整后，删除每个研究项目旧 data 下的 _enhanced.parquet
  # 保留原始 {symbol}.parquet（不含 _enhanced 后缀）以防兼容性问题
  ```

---

### Phase 2: DuckDB 查询工具（~1 小时）

**目标**：编写一个 CLI 工具，能直接用 SQL 查询 parquet 文件。

- [ ] **Step 1: 安装 DuckDB**
  ```bash
  pip install duckdb
  ```
  > ⚠️ 安装到 WSL Python3（用于数据分析），不是 Windows Python

- [ ] **Step 2: 编写 `scripts/duck_query.py`**
  ```python
  # 路径: /mnt/f/AIcoding_space/Hermes/strategies/futures/scripts/duck_query.py
  # 功能:
  #   1. 接受 SQL 查询字符串或文件
  #   2. 自动将 'H1/*.parquet' 解析为中央目录路径
  #   3. 支持 glob pattern（多文件查询）
  #   4. 输出格式: table (默认) / csv / json
  ```
  > ⚠️ 全局变量 `PARQUET_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/futures/data/parquet"`
  > ⚠️ DuckDB SQL 语法：`SELECT * FROM read_parquet('H1/*_enhanced.parquet') WHERE rsi14 < 30`
  > ⚠️ DuckDB 的 glob 路径相对于当前工作目录，所以 duck_query.py 内部要拼接绝对路径

- [ ] **Step 3: 添加快捷参数**
  ```bash
  python duck_query.py --scan oversold       # 预定义查询: rsi14 < 30
  python duck_query.py --scan strong_trend   # 预定义查询: adx_14 > 25 and chop_14 < 30
  python duck_query.py --top-symbols         # 各品种最新数据行
  python duck_query.py --categories          # 列出所有指标类别
  ```
  > 预定义查询放在脚本内的 `PRESETS` 字典中

- [ ] **Step 4: 验证**
  ```bash
  python duck_query.py "SELECT symbol, COUNT(*) FROM 'H1/*_enhanced.parquet' WHERE rsi14 < 30 GROUP BY symbol"
  ```
  > ✅ 预期输出：所有 14 品种各约 100-300 行（取决于市场状态）

---

### Phase 3: 统一预计算脚本 + 指标目录（~3 小时）

**目标**：将 high-rr 的 precompute_indicators.py 搬到中央目录，改为支持增量更新，自动生成 column_registry.json。

- [ ] **Step 1: 搬迁脚本**
  ```bash
  cp /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/high-rr-research/scripts/precompute_indicators.py \
     /mnt/f/AIcoding_space/Hermes/strategies/futures/scripts/
  ```
  > ⚠️ 搬迁后更新脚本内部的 BASE/DATA_DIR 路径
  > ⚠️ 各研究项目在过渡期可能还会引用旧路径，搬迁后保留一份副本或创建 symlink

- [ ] **Step 2: 改为增量更新**
  - 方案：比较 `column_registry.json` 版本号，只算新增列/新增行
  - 新增行：拉取 MT5 最新数据，只补最后 N 行的指标
  - 新增列：在现有 parquet 文件上 add column（parquet 支持列追加）
  - 全量重算：当 schema 变更较大时（新增指标类别），跑一次完整重算

  ```python
  def update_indicators(tf: str, symbols: list, mode: str = "incremental"):
      if mode == "full":
          return process_timeframe(tf, symbols)  # 全量
      # incremental: 读已有 parquet，只算最后 N 行
      for sym in symbols:
          df = pd.read_parquet(f"{PARQUET_DIR}/{tf}/{sym}_enhanced.parquet")
          new_rows = fetch_new_mt5_data(sym, tf, df.index[-1])
          if len(new_rows) > 0:
              new_indicators = compute_all_indicators(new_rows, tf)
              updated = pd.concat([df, new_indicators])
              updated.to_parquet(f"{PARQUET_DIR}/{tf}/{sym}_enhanced.parquet")
  ```
  > ⚠️ fetch_new_mt5_data 必须用 **Windows Python** 执行（MT5 库只在 Windows 上）
  > ⚠️ 增量更新的关键：数据对齐。新行必须和旧行有相同的列

- [ ] **Step 3: 实现指标目录生成**
  - 编写 `classify_column(col_name: str) -> dict` 函数，根据列名前缀自动分类
  - 在 `process_timeframe()` 末尾调用 `generate_column_registry(df)`
  - 输出的 JSON 文件放在 `strategies/futures/data/column_registry.json`

  ```python
  def classify_column(col: str) -> dict:
      """根据列名前缀自动推断类别、类型、描述"""
      prefixes = {
          "rsi":      ("momentum",   "RSI",      float),
          "adx":      ("trend",      "ADX",      float),
          "atr":      ("volatility", "ATR",      float),
          "bb_":      ("volatility", "Bollinger Band", float),
          "ma":       ("trend",      "Moving Average", float),
          "ema":      ("trend",      "EMA",      float),
          "doji":     ("pattern",    "Doji",     bool),
          "hammer":   ("pattern",    "Hammer",   bool),
          "volume_":  ("volume",     "Volume",   float),
          "obv":      ("volume",     "OBV",      float),
          "mfi":      ("volume",     "MFI",      float),
          "stoch":    ("momentum",   "Stochastic", float),
          "macd":     ("momentum",   "MACD",     float),
          "williams": ("momentum",   "Williams %R", float),
          "cci":      ("momentum",   "CCI",      float),
          "dc_":      ("volatility", "Donchian", float),
          "kc_":      ("volatility", "Keltner",  float),
          "envelope": ("volatility", "Envelope", float),
          "fib_":     ("structure",  "Fibonacci", int),
          "pp_":      ("structure",  "Pivot Point", float),
          "hh_":      ("structure",  "Higher High", int),
          "ll_":      ("structure",  "Lower Low", int),
          "support":  ("structure",  "Support",  float),
          "resistance":("structure", "Resistance", float),
          "guppy":    ("trend",      "Guppy MMA", float),
          "ha_":      ("trend",      "Heikin Ashi", float),
          "psar":     ("trend",      "Parabolic SAR", float),
          "ichimoku": ("trend",      "Ichimoku", float),
          "kijun":    ("trend",      "Ichimoku Kijun", float),
          "tenkan":   ("trend",      "Ichimoku Tenkan", float),
          "senkou":   ("trend",      "Ichimoku Senkou", float),
          "chikou":   ("trend",      "Ichimoku Chikou", float),
          "cloud":    ("trend",      "Ichimoku Cloud", int),
          "aroon":    ("trend",      "Aroon",    float),
          "chop":     ("volatility", "Choppiness", float),
          "kst":      ("momentum",   "KST",      float),
          "trix":     ("momentum",   "TRIX",     float),
          "rvg":      ("momentum",   "RVGI",     float),
          "ultimate": ("momentum",   "Ultimate Osc", float),
          "mom":      ("momentum",   "Momentum", float),
          "roc":      ("momentum",   "ROC",      float),
          "dpo":      ("momentum",   "DPO",      float),
          "mass":     ("volatility", "Mass Index", float),
          "volatility":("volatility", "Volatility", float),
          "volume":   ("volume",     "Volume",   float),
          "cmf":      ("volume",     "CMF",      float),
          "force":    ("volume",     "Force Index", float),
          "eom":      ("volume",     "Ease of Movement", float),
          "vpt":      ("volume",     "VPT",      float),
          "klinger":  ("volume",     "Klinger Osc", float),
          "nvi":      ("volume",     "NVI",      float),
          "pvi":      ("volume",     "PVI",      float),
          "vwap":     ("volume",     "VWAP",     float),
          "zscore":   ("statistical", "Z-Score", float),
          "autocorr": ("statistical", "Autocorrelation", float),
          "skew":     ("statistical", "Skewness", float),
          "kurtosis": ("statistical", "Kurtosis", float),
          "hurst":    ("statistical", "Hurst Exponent", float),
          "entropy":  ("statistical", "Entropy",  float),
          "return":   ("price_action", "Return", float),
          "gap":      ("price_action", "Gap",    float),
          "session":  ("time",       "Session", str),
          "day_of_week":("time",     "Day of Week", int),
          "is_":      ("time",       "Time Flag", int),
          "market_regime":("market", "Market Regime", str),
          "regime":   ("market",     "Regime",   float),
          "trending": ("market",     "Trending", int),
          "consecutive":("price_action", "Consecutive", int),
      }
      ...
  ```

- [ ] **Step 4: 编写 `scripts/indicator_registry.py`**
  > 单独的文件，不依赖 precompute 脚本，只读 column_registry.json
  ```python
  def list_indicators(category=None, subcategory=None, type=None) -> list
  def get_indicator_registry() -> dict
  def indicator_exists(col_name: str) -> bool
  def get_categories() -> list
  def search_indicators(keyword: str) -> list
  def get_indicators_by_type(data_type: str) -> list
  ```
  > ⚠️ 这个文件会被多个研究引擎 import，要轻量、无副作用
  > ⚠️ 加载 registry 时用 `@functools.lru_cache` 缓存，避免每次调用都读 JSON

- [ ] **Step 5: 验证**
  ```bash
  python3 -c "
  from indicator_registry import list_indicators, get_categories
  print('Categories:', get_categories())
  print('Momentum cols:', list_indicators(category='momentum'))
  print('Bool cols:', list_indicators(type='bool'))
  "
  ```

- [ ] **Step 6: 创建每日更新 Cron**
  > 每日收盘后（UTC 22:00）执行增量更新，补齐当日数据 + 重算指标
  ```bash
  hermes cron create \
    --name "futures-daily-update" \
    --schedule "0 22 * * 1-5" \
    --prompt "执行 futures/scripts/update_daily.py，增量更新 MT5 数据并重算全量指标，然后生成新的 column_registry.json" \
    --skills futures-daily-update \
    --deliver local
  ```

---

### Phase 4: 各研究引擎适配（~1 小时）

**目标**：让各研究项目使用中央 parquet 和 indicator_registry.py。

- [ ] **high-rr research_engine.py**
  > **当前做法**：硬编码 `required_cols = ["rsi14", "atr14", "hh_20", "ll_20", ...]`
  > **改为**：
  ```python
  from indicator_registry import list_indicators, indicator_exists
  # 不再检查硬编码列表，而是动态获取
  all_float = list_indicators(type="float")
  # 策略的 entry_condition 用 eval 执行，列存在性由 indicator_registry 保证
  ```
  > ⚠️ 注意：`indicator_exists("rsi14")` 会去查 column_registry.json，不要漏 import
  > ⚠️ 如果研究引擎要用 `df.eval()` 执行条件字符串，确保 eval 不会执行恶意代码

- [ ] **scalping-m1 data_loader**
  > **当前做法**：读自己的 `data/M5/{symbol}.parquet`（只有 OHLC）
  > **改为**：读中央目录的 `data/M5/{symbol}_enhanced.parquet`
  > ⚠️ 列名变化：原来只读 `close`, `high`, `low`, `open`, `volume`，现在有 467 列。代码中如果用了 `.columns` 做判断，需要适配

- [ ] **futures-intraday data_loader**
  > 同上，改 symlink 或 DATA_DIR 路径

- [ ] **candlestick-patterns data_loader**
  > ⚠️ 注意：这个项目之前自己算 K 线形态特征（`candlestick_features.py`）。
  > 中央 parquet 已经预计算了形态列（`doji`, `hammer`, `engulfing` 等），
  > 可以把 candlestick_features.py 的逻辑改为只读已有列，不再重复计算。
  > 但要确认中央 parquet 的形态列命名和 candlestick 项目一致。

---

### Phase 5: 验证与收尾（~1 小时）

- [ ] 每个研究项目跑一轮研究循环，确认数据加载正常
- [ ] 对比中央化前后的回测结果（确保指标值一致）
- [ ] Git 提交：`git add -A && git commit -m "feat: centralize parquet data + indicator registry" && git push`
- [ ] 更新各研究 Cron 的 prompt（如果 prompt 里硬编码了数据路径）
- [ ] 写一个 README.md 文件在 `futures/data/` 目录下，说明中央数据目录结构和用法

---

## 8. 列命名规范

### 8.1 原则

- 小写 + 下划线，层级用下划线分隔
- 格式：`{类别}_{参数}_{修饰}`

### 8.2 命名示例

| 类别 | 规范 | 示例 |
|:----|:----|:-----|
| RSI | `rsi{period}` | `rsi14`, `rsi7` |
| ATR | `atr{period}` | `atr14`, `atr14_pct` |
| 布林带 | `bb_{period}_{std}_{field}` | `bb_20_2_upper`, `bb_20_2_width` |
| Keltner | `kc_{period}_{deviations}_{field}` | `kc_20_2_upper`, `kc_20_2_pos` |
| 均线 | `ma{period}` | `ma20`, `ma20_slope` |
| 形态 | `{pattern_name}` | `doji`, `hammer`, `engulfing` |
| 持仓量 | `oi_{suffix}` | `oi_total`, `oi_change_pct` |

### 8.3 约定

- 布尔指标用 `0/1`（如 `doji=1`）
- 多空方向用 `bull_`/`bear_` 前缀
- 列名尽量与 TA-Lib 参数顺序一致

---

## 9. 风险与应对

| 风险 | 影响 | 应对方案 |
|:----|:----|:--------|
| 中央 parquet 写入冲突 | 多研究同时读，但预计算单线程写 | parquet 读不影响写；脚本加锁 |
| symlink 被 Git 追踪 | Git 仓库变大或链接失效 | `.gitignore` 加 `data/parquet/*.parquet`；只追踪 symlink 本身 |
| 研究引擎需要不同时间框架 | 中央只存 H1/M5 | 研究可 symlink 后再在本地建子集；也可以目录里加 M15/M30 子目录 |
| 新增指标需重新生成全部数据 | 一次更新全部品种，10-15 分钟 | Phase 3 做增量更新，只补新行/新列 |
| **研究引擎用不到全部指标** | 460 个指标只用了 7 个 | Phase 3 的指标目录 + list_indicators() 让研究引擎能主动探索全空间 |

---

## 10. 待讨论

1. **数据目录位置**: `strategies/futures/data/` vs `strategies/data/`（是否要放 A 股共享）
2. **DuckDB 查询工具**: 做成 CLI 还是要写 Python 脚本？
3. **指标目录生成方式**: 从 precompute_indicators.py 自动生成，还是单独维护一个手动写的 catalog？
4. **指标分类粒度**: 8 个大类够细吗？还是需要二级分类（如 momentum/rsi, momentum/macd）？
5. **列名兼容性**: 现有研究引擎用了 `rsi14` 这种不含下划线的名字，新命名规范是否需要强行统一？
6. **A 股数据**: A 股的日线/周线要不要也做同样的 DuckDB 查询层？（A 股在 ClickHouse 里）

---

## 11. Pillar B: 实时数据共享层（Tick Engine）

> **目标**：所有实时交易系统共享同一数据源，避免重复连接 MT5 + 重复算指标
> **核心**：一个轻量守护进程 + N 个只读 Scanner
> **状态**：代码已实现（`scripts/tick_engine.py` + `scripts/tick_reader.py`）

---

### 11.1 现状问题

当前每个 Scanner 各自连接 MT5、拉 bar、算指标：

```
Scalping Scanner       Intraday Scanner
  ├ 连接 MT5               ├ 连接 MT5
  ├ 拉 M1 40 bars          ├ 拉 H1 40 bars
  ├ 算 RSI14/ATR           ├ 算 RSI14/ATR
  ├ 算 consecutive_bear    ├ 算 consecutive_bear
  └ 评估条件               └ 评估条件
       ↑ 重复连接       ↑ 重复拉数据    ↑ 重复算
```

**问题**：
1. **重复连接**：2+ 进程各连一次 MT5，每次 0.3-0.5s
2. **重复拉 bar**：相同的品种、相同的 TF，各拉各的
3. **重复算指标**：calc_rsi() / calc_atr() / detected_consecutive_bears() 在三处代码里一模一样
4. **无法秒级检测**：每个 scanner 是独立循环，60s 周期，无法快速响应价格变化

---

### 11.2 架构设计

```
┌──────────────────────────────────────────────────────────────┐
│  Tick Engine (tick_engine.py)                                │
│  运行在 Windows Python（唯一需要 MT5 的进程）                  │
│                                                              │
│  主循环 (每 1.5s):                                           │
│  1. mt5.symbol_info_tick(14品种)   ← 0.2s                    │
│  2. 检测新 bar 形成（M1/M5/H1）                               │
│  3. 新 bar → 拉 bars → 重算指标                               │
│  4. 写入共享 JSON 文件（原子写入）                              │
│                                                              │
│  输出: data/tick/                                             │
│  ├ ticks.json              ← 14 品种最新 bid/ask/spread       │
│  ├ indicators_M1.json      ← 各品种 M1 最新 RSI/ATR/连阴     │
│  ├ indicators_M5.json      ← 各品种 M5 最新指标               │
│  ├ indicators_H1.json      ← 各品种 H1 最新指标               │
│  ├ bar_signals.json        ← 新 bar 通知（谁+哪个TF）         │
│  └ _heartbeat.json         ← 运行状态（Scanner 据此判断是否活着）│
└────────────────────────┬─────────────────────────────────────┘
                         │
            ┌────────────┼─────────────┐
            ▼            ▼             ▼
    ┌────────────┐ ┌────────────┐ ┌────────────┐
    │ Scalping   │ │ Intraday   │ │ 未来策略    │
    │ Scanner    │ │ Scanner    │ │ Scanner     │
    │            │ │            │ │             │
    │ 不再连MT5   │ │ 不再连MT5   │ │ 直接读      │
    │ 读 ticks   │ │ 读 ticks   │ │ ticks.json  │
    │ + indicators│ │ + indicators│ │ + indicators│
    │ 只 eval    │ │ 只 eval    │ │ 只 eval     │
    │ execute 除外│ │ execute 除外│ │             │
    └────────────┘ └────────────┘ └────────────┘
```

**关键设计**：
- **只有一个进程连 MT5**，其他 Scanner 完全不需要 MT5 库
- **指标只在 bar 关闭时重算**，不浪费 CPU
- **Tick 数据每 1.5s 更新**，Scanner 实现秒级检测只需读 JSON
- **原子写入**：先写 `.tmp` 再 `rename`，避免 Scanner 读到半截文件
- **Heartbeat 机制**：Scanner 检测到 Engine 停止 → 自动 fallback 直连 MT5
- **价格级入场**：策略可加 `tick_entry` 条件（如 `tick.ask > threshold`），Scanner 的 1.5s 循环直接处理

---

### 11.3 文件说明

| 文件 | 功能 |
|:----|:-----|
| `scripts/tick_engine.py` | Tick Engine 守护进程（Windows Python 运行） |
| `scripts/tick_reader.py` | 共享数据读取层（Scanner 用，自动 fallback） |
| `scripts/start_tick_engine.bat` | Windows 启动脚本 |
| `config/tick_engine.json` | 配置（品种列表、TF、循环间隔） |
| `data/tick/` | 共享输出目录 |

---

### 11.4 tick_reader.py API

```python
from tick_reader import TickReader

reader = TickReader()

# 引擎健康检查
if not reader.is_alive():
    fallback_to_direct_mt5()  # 自动降级

# 读取 tick
eur_tick = reader.get_tick("EURUSD")
# → {"bid": 1.0845, "ask": 1.0847, "spread": 2, "time": 1747153800}

# 读取指标（不用自己算 RSI/ATR）
ind = reader.get_indicator("XAUUSD", "M5")
# → {"rsi14": 45.2, "atr14": 12.5, "consecutive_bear": 2,
#     "session": "europe", "bar_close": 2345.6, ...}

# 检查新 bar
signal = reader.get_bar_signal("EURUSD", "M1")
# → {"time": 1747153800, "symbol": "EURUSD", "timeframe": "M1"}

# 当前时段
session = reader.get_session()  # "europe"
```

---

### 11.5 Scanner 改造方案

#### Scalping Scanner 改动

```
当前:
  def scan_strategy(mt5, symbol, config):
      bars = mt5.copy_rates_from_pos(...)    ← 拉数据
      rsi = calc_rsi(closes)                 ← 算指标
      atr = calc_atr(bars)                   
      session = get_session(...)             
      # ... 检查条件
      
改为:
  def scan_strategy(symbol, config, reader):
      ind = reader.get_indicator(symbol, config["timeframe"])  ← 直接读
      if not ind:
          return []
      tick = reader.get_tick(symbol)
      # ... 检查条件（用 ind 的 rsi14/atr14/consecutive_bear/session 替代现场计算）
```

**核心变化**：
- 不再 import MetaTrader5
- 不再调用 `mt5.copy_rates_from_pos()`
- 不再调用 `calc_rsi()` / `calc_atr()` / `detected_consecutive_bears()`
- 不再调用 `get_session()`
- **纯只读 + 纯 eval**，循环周期可以从 60s 降到 1-2s

#### Intraday Scanner 改动

同上。额外注意：Signal Scanner 还有 DXY 过滤逻辑，这个需要保留但改为从 Tick Engine 读取。

---

### 11.6 文件清单

```
strategies/futures/
├── config/
│   └── tick_engine.json          ← 配置（已创建）
├── scripts/
│   ├── tick_engine.py            ← 守护进程（已创建，14017 bytes）
│   ├── tick_reader.py            ← 读取层（已创建，6019 bytes）
│   └── start_tick_engine.bat     ← 启动脚本（已创建）
└── data/
    └── tick/                      ← 共享输出目录（已创建）
```

---

### 11.7 实施步骤

#### Phase B1: 部署 Tick Engine（~1 小时）

- [ ] Windows 上双击 `start_tick_engine.bat` 启动
- [ ] 确认 `data/tick/` 下生成 ticks.json / _heartbeat.json / indicators_M5.json
- [ ] 确认 heartbeat.status == "running"
- [ ] 配置 systemd task / Windows Task Scheduler 实现开机自启

#### Phase B2: 改造 Scalping Scanner ✅ 已完成

- [x] scalping_scanner.py → 删掉 calc_rsi / calc_atr / detected_consecutive_bears / get_session
- [x] scan_strategy() 改为 `def scan_strategy(symbol, config, reader):`
- [x] 用 `ind = reader.get_indicator(symbol, tf)` 替代现场算指标
- [x] 用 `tick = reader.get_tick(symbol)` 替代 current_price
- [x] 41 策略扫描耗时: ~3s → 30ms
- [ ] scalping_autopilot.py → 主循环改为 1-2s（不再是 60s），纯读 tick_reader
- [ ] 保留 execute_trade() 的 MT5 调用（只有下单需要 MT5）

#### Phase B3: 改造 Intraday Scanner（~1 小时）

- [ ] signal_scanner.py → 同上改造
- [ ] scanner_autopilot.py → 适配

#### Phase B4: 验证与收尾（~1 小时）

- [ ] 停掉 Tick Engine → Scanner 自动 fallback 直连 MT5（验证降级）
- [ ] 启动 Tick Engine → Scanner 自动恢复共享读取
- [ ] 对比改造前后信号输出一致性
- [ ] Git 提交

---

### 11.8 风险与应对

| 风险 | 应对 |
|:----|:-----|
| Tick Engine 进程挂了 | Scanner 的 is_alive() 检测到超时 → 自动 fallback 直连 MT5 |
| 共享文件读写冲突 | 原子写入（tmp + rename）+ Scanner 读时加异常处理 |
| 1.5s 循环压垮 MT5 | 只读 tick（极轻量），bar 只在新 bar 时才拉。实测 14 品种 tick 约 0.2s |
| Windows 重启后 Engine 没自启 | Task Scheduler 配置开机启动 |
| Scanner 改造期间旧代码还能跑 | 改造前复制一份原脚本备份，新的用不同文件名测试 |
