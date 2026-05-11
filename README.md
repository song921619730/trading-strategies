# Hermes Trading Strategies Repository

本仓库包含所有交易策略的核心代码、Prompt 模板与业务逻辑。架构设计遵循 **"市场分区、架构分层、逻辑解耦"** 的原则，旨在实现策略的即插即用与高效扩展。

---

## 📂 目录结构 (Directory Structure)

策略按 **资产类别 (Market)** 和 **执行架构 (Architecture)** 两级分类。

```text
strategies/
│
├── 📈 futures/                                (期货/外汇/商品类)
│   ├── 📂 single-agent/                       (👉 轻量级：单智能体/单 Cron 自主决策)
│   │   ├── pure-ai-cio/                       (Magic 234003, AI 自主交易)
│   │   └── keylevel-trend/                    (关键位趋势跟踪)
│   │
│   ├── 📂 kanban/                             (👉 重量级：多智能体协作流水线)
│   │   └── macro/                             (宏观定调 + 专家会诊 + 风控决策)
│   │
│   ├── 📂 experimental/                       (实验性策略，验证中)
│   │   └── macro-risk-layer/                  (宏观风险预警：能源+外汇联动保护股指期货)
│   │
│   └── 📂 research/                           (期货研究引擎)
│       ├── briefs/                            (研究任务卡)
│       ├── experiments/                       (实验代码与回测结果)
│       ├── kanban/                            (多智能体研究管线)
│       ├── proposals/                         (提案：待审核)
│       ├── reports/                           (研究报告)
│       └── single-agent/                      (单节点研究管线)
│
├── 🇨🇳 a-stock/                                (A 股类)
│   ├── 📂 kanban/                             (👉 多智能体流水线)
│   │   ├── a-stock-shortline/                 (A股短线策略)
│   │   └── daily-limit-radar/                 (每日涨停雷达)
│   │
│   └── 📂 research/                           (A股研究引擎)
│       ├── USER_TOPIC.md                      (选题库：用户指定 + AI自主发掘)
│       ├── briefs/                            (研究任务卡)
│       ├── experiments/                       (实验代码与回测结果)
│       ├── kanban/                            (多智能体研究管线)
│       ├── proposals/                         (提案：待审核)
│       ├── reports/                           (研究报告)
│       └── single-agent/                      (单节点研究管线)
│
├── 📋 kanban-template/                        (Kanban 策略通用模板)
│   └── task-creation-rules.md                 (任务创建规则：架构/数据源/路径/Soul/Cron)
│
├── validate_proposal.py                       (通用验证脚本：回测审计 + 提案审核)
└── research_schedule.json                     (Cron 调度配置)
```

---

## 🧩 核心架构设计 (Architecture Design)

### 1. 架构模式分类

我们在根目录下使用两种目录来区分策略的复杂程度：

| 架构类型 | 目录名 | 特点 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **Single-Agent** | `single-agent/` | **轻量、直接**。<br>单个 Cron 触发 -> 单个 Agent 执行数据获取、分析、交易。 | 趋势跟踪、简单形态突破、已固化的成熟策略。 |
| **Kanban** | `kanban/` | **重、协作、多步骤**。<br>单个 Cron 触发 -> Orchestrator 分发任务 -> 多个 Profile 协作 (T1->T2->T3)。 | 宏观定调、多因子选股、需要强风控交叉验证的复杂策略。 |

---

## 👷 Profile 与 Skills 协同机制

这是本系统的核心设计。我们将 **"执行者 (Profile)"** 与 **"业务知识 (Skill)"** 彻底解耦。

### 1. Profile (工人) - 全局共享
*   **位置**: `~/.hermes/profiles/` (如 `researcher`, `analyst`, `risk_manager`, `trader`)
*   **职责**: 提供通用能力（联网、读文件、写代码、连接 MT5）。
*   **特点**: **策略无关**。`analyst` 这个 Profile 既不懂期货也不懂股票，它只懂如何"分析数据"。
*   **维护**: 全局统一配置模型、超时、API Key。升级一次，所有策略生效。

### 2. Skills (上岗证) - 策略专属
*   **位置**: `strategies/{market}/{architecture}/{strategy_name}/skills/`
*   **职责**: 提供特定市场的业务规则。
    *   *示例*: `risk-rules.md` (期货版) 会写"白银 1 手=5000 盎司，单笔风险 5%"。
    *   *示例*: `risk-rules.md` (A 股版) 会写"单票仓位 20%，禁止追涨停"。
*   **挂载方式**: 在 Cron Prompt 中指定加载哪个 Skill，Profile 就会根据该 Skill 的逻辑进行工作。

> **💡 类比**:
> *   **Profile** 是**大厨**（有通用技能：切菜、炒菜）。
> *   **Skill** 是**菜谱**（特定知识：川菜要放花椒，粤菜要清淡）。
> *   你不需要为每种菜系雇一个新厨师，只需要给同一个厨师不同的菜谱即可。

---

## 逻辑角色矩阵 (Logical Role Matrix)

在 Hermes 系统中，我们采用 **“物理 Profile (工人) + 逻辑 Role (岗位)”** 的设计。不需要为每个功能创建新的 Profile，而是通过 Skill 挂载，让同一个工人扮演不同的角色。

| 逻辑角色 (Logical Role) | 物理 Profile | 职责描述 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **宏观定调师** (Macro Strategist) | `researcher` | 判断市场情绪 (Risk On/Off)、宏观周期。 | 期货/外汇 (受宏观驱动大) |
| **数据侦察兵** (Data Scout) | `researcher` | 获取行情数据、清洗、计算指标。 | 所有策略 (T1 节点) |
| **形态分析师** (Pattern Analyst) | `analyst` | 寻找符合策略的技术形态 (如 H1 回调)。 | 所有策略 (T2-T5 节点) |
| **风控官** (Risk Officer) | `risk_manager` | 计算动态仓位、检查相关性、拦截高风险交易。 | 所有策略 (T6 节点) |
| **合规官** (Compliance Officer) | `risk_manager` | 检查交易时段、流动性、重大新闻回避。 | 期货 (夜盘/交割月) / A 股 (T+1) |
| **CIO / 交易员** (CIO / Trader) | `trader` | 最终决策、生成交易计划、执行。 | 所有策略 (T7 节点) |
| **报告员** (Reporter) | `writer` | *(可选)* 生成复盘报告、日报、周报。 | 需要详细文字输出的策略 |

> **💡 优势**: 新增角色只需写 Skill，无需重启服务或配置新 Profile。

## 策略内部标准结构 (Standard Template)

每个策略目录内部应包含以下标准文件：

| 目录/文件 | 作用 | 示例内容 |
| :--- | :--- | :--- |
| `cron-prompts/` | **大脑 (调度)** | 定义任务图 (T1->T2...) 和运行时间。Kanban 策略必备。 |
| `skills/` | **灵魂 (逻辑)** | 业务规则：风控公式、板块分析、合约规格。 |
| `scripts/` | **手脚 (执行)** | 数据源 (`pre_analyze.py`)、执行器 (`execute.py`)。 |
| `logs/` | **运行记录** | 按日期存储的扫描日志、中间状态。 |
| `reports/` | **决策产出** | 每日生成的交易计划或选股报告。 |
| `PLAN.md` | **设计文档** | 策略逻辑、参数说明、复盘记录。 |

---

## 🚀 如何新增一个策略？

### Single-Agent 策略

假设你要新增一个 **"加密货币趋势策略"** (单节点模式)：

1.  **创建目录**:
    在对应市场目录下新建文件夹，如 `futures/single-agent/trend-following/`。
2.  **编写 Skills**:
    创建 `skills/risk-rules.md`，写入专属风控规则。
3.  **编写 Script**:
    创建 `scripts/pre_analyze.py` 数据查询脚本。
4.  **注册 Cron Job**:
    添加 Cron 任务，设置 `workdir` 指向新目录。

### Kanban 策略

1.  **复制模板**:
    将 `kanban-template/task-creation-rules.md` 复制到 `新策略/rules/task-creation-rules.md`。
2.  **替换占位符**:
    按实际策略替换所有 `{{占位符}}`（数据源、路径、任务依赖链、Profile 分配等）。
3.  **创建 Cron Job**:
    按模板中的调度配置注册 Cron，Orchestrator 统一使用 flash 模型。

**优势**: 新策略完全独立，不依赖其他策略的文件，也不会被其他策略的更新误伤。

---

## 📋 维护与注意事项

1. **单一 Git 仓库**: 整个 `strategies/` 是单一 Git 仓库，不存在嵌套子仓库。所有策略共享同一套 Git 历史。
2. **路径规范**:
    *   脚本和 Prompt 中 **严禁使用硬编码路径**（如 `F:\...`）。
    *   Cron 系统会自动注入 `workdir`，优先使用绝对路径。Worker 的 scratch workspace 是独立的，相对路径不可靠。
3. **Kanban DB 同步**:
    所有 Worker Profile 的 `kanban.db` 已软链接到 Orchestrator Profile，确保多智能体任务状态同步。
4. **Kanban 新策略**:
    新建 Kanban 策略时，复制 `kanban-template/task-creation-rules.md` 到 `新策略/rules/`，替换所有 `{{占位符}}`。该模板基于 2026-05-10 实战经验编写，包含已知陷阱清单。
