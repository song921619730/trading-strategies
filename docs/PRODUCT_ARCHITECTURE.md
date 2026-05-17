# 量化期货交易系统 — 产品架构文档

> **版本**: v4.0 | **最后更新**: 2026-05-14
> **定位**: 从数据拉取 → 因子挖掘 → 策略注入 → 实盘交易的全自动闭环

---

## 目录

1. [系统概览](#1-系统概览)
2. [数据层](#2-数据层)
3. [指标工厂](#3-指标工厂)
4. [因子挖掘 → 研究流水线](#4-因子挖掘--研究流水线)
5. [策略注入引擎](#5-策略注入引擎)
6. [实盘交易执行](#6-实盘交易执行)
7. [部署与运维](#7-部署与运维)
8. [风险控制体系](#8-风险控制体系)
9. [研发到实盘的桥梁](#9-研发到实盘的桥梁)
10. [目录结构](#10-目录结构)

---

## 1. 系统概览

### 1.1 核心设计理念

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Agent (决策大脑)                        │
│  Hermes Agent + Kanban Multi-Agent + 研究 Cron               │
└──────────┬──────────────┬──────────────┬────────────────────┘
           │              │              │
     ┌─────▼─────┐  ┌────▼────┐  ┌─────▼─────┐
     │  研究流水线 │  │ 配置注入  │  │  结果分析   │
     │  discovery │  │ auto_   │  │  report/   │
     │  _engine   │  │ inject  │  │  feedback  │
     └─────┬─────┘  └────┬────┘  └─────┬─────┘
           │              │              │
           └──────────────┼──────────────┘
                          │
              ┌───────────▼───────────┐
              │   strategies.json     │
              │   (信号配置注册表)      │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │   策略执行层 (Autopilot) │
              │   tmux + systemd      │
              │   风险控制/下单/持仓    │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │   Tick Engine         │
              │   (唯一 MT5 连接)      │
              │   1s 循环 ✦ 19品种 × 5TF │
              └───────────────────────┘
```

### 1.2 三大分层

| 层 | 职责 | 关键技术 |
|----|------|---------|
| **研究中台** | 数据采集、指标计算、因子挖掘、回测验证 | Python + Pandas + Parquet |
| **策略注入** | AI 研究产出 → 结构化配置文件 | `condition_utils.py` + `auto_inject*.py` |
| **交易执行** | 实时信号扫描、风控、下单、持仓管理 | Tick Engine + Autopilot + tmux |

### 1.3 核心原则

- **单一数据源**：Tick Engine 是**唯一**连接 MT5 的组件，其他模块只读共享数据
- **研究-实盘指标同源**：`indicators.py` 被研究（batch_precompute）和实盘（tick_engine）共用，320 个指标 100% 一致
- **配置驱动**：新增策略不写代码，只改 JSON 配置
- **自愈运行**：tmux + systemd + while-true 循环，崩溃自动重启

---

## 2. 数据层

### 2.1 数据源

| 市场 | 主源 | 备用 | 存储 |
|------|------|------|------|
| 国际期货/外汇 | **MT5** (Exness Demo) | Yahoo Finance | Parquet + JSON |
| A 股 | **Tushare ClickHouse** (172.24.224.1:8123) | — | ClickHouse 表 |

### 2.2 MT5 实时数据流

```
MT5 Terminal
    │
    ▼
tick_engine.py  ←── config/tick_engine.json
    │                   ├── symbols: 19品种
    │                   ├── timeframes: M1/M5/M15/M30/H1
    │                   └── loop_interval: 1.0s
    │
    ├──→ data/tick/ticks.json          (最新 bid/ask/spread)
    ├──→ data/tick/indicators_{TF}.json (320 个指标/品种)
    ├──→ data/tick/bar_signals.json    (新 bar 事件)
    └──→ data/tick/heartbeat.json      (存活心跳)
```

**Tick Engine 工作流**：
1. 每 1s 循环 → 读取所有品种 tick
2. 检测新 bar → 拉取 bars 数据
3. 调用 `indicators.py` 计算全量 320 指标
4. 原子写入共享 JSON（tmp → rename）
5. 写入 heartbeat

### 2.3 A 股数据流

```
Tushare Pro API
    │
    ▼
tushare-daily-sync (Cron 每日 22:00)
    │
    ▼
ClickHouse 172.24.224.1:8123
    │
    ├── 日线/周线/月线 (无分钟级)
    ├── 167 张表全量同步
    └── 交易日检测 + 手工补跑
```

### 2.4 共享数据层 (data/tick/)

所有 Scanner/Autopilot 通过 `tick_reader.py` 读取共享数据，**不复连 MT5**。

```
tick_reader.py 提供:
  - get_tick(symbol)         → {bid, ask, spread, time}
  - get_indicator(sym, tf)   → {rsi14, atr14, macd, ...} (320字段)
  - get_bar_signal(sym, tf)  → 新 bar 事件
  - is_alive()               → Tick Engine 心跳检测
```

---

## 3. 指标工厂

### 3.1 indicators.py — 核心指标库

**定位**: 研究侧 + 实盘侧共享的唯一指标计算入口。

- **84 个函数 / 320 个指标**
- 覆盖: 趋势、动量、波动率、成交量、价格行为、形态、结构
- 输入: `list[dict]` (OHLCV bars)，输出: 标量值

| 类别 | 指标数 | 代表性指标 |
|------|--------|-----------|
| 趋势 | ~60 | EMA12-200, SMA, ADX, Ichimoku, Guppy, PSAR |
| 动量 | ~50 | RSI(7/14/21/50), MACD, Stochastic, CCI, Williams%R |
| 波动率 | ~30 | ATR(5/7/10/14/21/50), Bollinger, Keltner, Donchian |
| 成交量 | ~25 | OBV, MFI, CMF, Volume Ratio, Volume Spike |
| 价格行为 | ~40 | Doji, Hammer, Engulfing, Harami, Pin Bar, Inside Bar |
| 结构 | ~20 | HH/LL Breakout, Support/Resistance, Pivot Points |
| 综合 | ~95 | Z-Score, Market Regime, Envelopes, Heikin Ashi |

### 3.2 batch_precompute.py — 批量预计算

用于研究场景，Pandas 向量化计算全部指标并存入 Parquet。

```
输入: data/{TF}/{symbol}.parquet (OHLCV 原始数据)
           │
           ▼
    batch_precompute.py
           │
           ▼
输出: data/{TF}/{symbol}.parquet (含全部 320 指标列)
```

**核心方法**: `compute_all_trading_indicators_vectorized(df)` 包装器。

### 3.3 一致性保障

实时 tick_engine 调用 indicators.py → 研究 batch_precompute 调用 indicators.py

```
实时指标[ATR14=XAUUSD=17.81] === 研究回测指标[ATR14=XAUUSD=17.81]
```

---

## 4. 因子挖掘 → 研究流水线

### 4.1 discovery_engine.py — 共享发现引擎

独立于具体研究目录，通过 `--data-dir` 指向任意数据集运行。

**流程**:
1. 加载 Parquet 数据（含 320 指标）
2. 分类列类型（bool/int/pct/raw）
3. 对每列执行信号发现（评估交易规则）
4. 输出：`best_findings` 按 Sharpe/PF 排序

**支持的研究项目**:

| 研究线 | Timeframes | 策略类型 | 当前轮次 |
|--------|-----------|---------|---------|
| scalping-m1 | M1/M5 | 高胜率超短线 | Round 40+ |
| futures-intraday | M30/H1 | 趋势反转波段 | Round 32+ |
| high-rr-research | M5/M15/H1 | 低胜率高盈亏比 | Round 12 |
| candlestick-patterns | H1/D1 | K 线形态 | Round 19 |

### 4.2 Kanban 多智能体研究流水线

每次研究 Cron 运行一个完整的 Agent 工作流:

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Researcher  │───→│   Analyst    │───→│  Risk Manager│
│  (拉数据)     │    │  (因子扫描)   │    │  (回测评估)   │
└──────────────┘    └──────────────┘    └──────────────┘
                            │
                     ┌──────▼──────┐
                     │ research_   │
                     │ state.json  │
                     │ (最佳发现池) │
                     └─────────────┘
```

**研究产出的核心字段**:
```json
{
  "id": "hrr_001_XAGUSD_trend_pullback_s",
  "symbol": "XAGUSD",
  "timeframe": "M15",
  "direction": "short",
  "win_rate": 46.7,
  "n": 30,
  "sharpe": 85.57,
  "profit_factor": 2.67,
  "_params": {
    "pattern_type": "trend_pullback",
    "session": "us",
    "sl_multiple": 1.2,
    "tp_multiple": 5.0,
    "rsi14_max": 50,
    "rsi14_min": 70,
    "consecutive_bear": 2,
    "consecutive_bull": 3,
    "pullback_to_ma50": true,
    "h1_trend": "down"
  }
}
```

### 4.3 研究数据存放

```
research/kanban/{研究线}/
├── data/                        # Parquet 数据集
│   ├── M5/{symbol}.parquet
│   ├── M15/{symbol}.parquet
│   └── H1/{symbol}.parquet
├── state/research_state.json    # 最佳发现池
├── reports/                     # 每轮报告
├── cron-prompts/                # Cron prompt 模板
└── scripts/                     # 研究脚本
```

---

## 5. 策略注入引擎

### 5.1 condition_utils.py — 条件解析引擎

将研究发现的条件表达式 → Scanner 可执行的规则。

**三套格式兼容**:

| 格式 | 示例 | 适用场景 |
|------|------|---------|
| 旧版 dict | `{"rsi14_max": 40, "session": "us"}` | 原始 intraday 信号 |
| 新版 conditions 数组 | `[{"i":"rsi14","op":"<","v":40}]` | Scalping 注入 |
| 特殊处理器 | `_dxy_filter`, `_near_ma50`, `_h1_*` | 跨品种/跨TF/综合条件 |

**支持的运算符**: `<`, `<=`, `>`, `>=`, `==`, `!=`

**特殊处理器**:

| 处理器 | 功能 |
|--------|------|
| `_dxy_filter` | 实时读取 DXY H1 指标，检查 DXY 方向 |
| `_near_ma50` | 检查 close_vs_ma50 绝对值 < 0.1%（价格在 MA50 附近） |
| `_h1_close_vs_ma50` | 跨 TF 读取 H1 的 close_vs_ma50，判断大趋势方向 |

### 5.2 auto_inject 注入体系

```python
# 核心注入脚本
auto_inject.py            # Scalping → Intraday 注入
auto_inject_highrr.py     # High-RR 研究发现 → Intraday 注入
```

**注入流程**:
1. 读取 `research_state.json` 的 `best_findings`
2. 按门槛过滤（WR/Sharpe/PF/n）
3. 调用 `_params_to_conditions()` 转为 `entry_conditions`
4. 去重检查（已有 ID + 已注入源）
5. 追加到 `strategies.json` 的 `signals[]`
6. 标记 `_injected_sources` 防止重复

**当前信号总量**:
- Intraday (234010): 74 信号（12 原始 + 47 Scalping 注入 + 15 High-RR 注入）
- Scalping (234011): 54 信号
- **合计: 128 信号**

### 5.3 信号配置格式

```json
{
  "id": "hrr_trend_xagusd_m15_s",
  "group": "hrr_metals_pullback",
  "symbols": ["XAGUSD"],
  "timeframe": "M15",
  "direction": "short",
  "entry_conditions": {
    "session": "us",
    "sl_multiple": 1.2,      ← 覆盖默认 2.0
    "tp_multiple": 5.0,       ← 覆盖默认 4.0
    "conditions": [
      {"i": "rsi14", "op": "<", "v": 50},
      {"i": "rsi14", "op": ">", "v": 70},
      {"i": "consecutive_bear", "op": ">=", "v": 2},
      {"i": "consecutive_bull", "op": ">=", "v": 3},
      {"i": "_near_ma50", "op": "==", "v": 1},
      {"i": "_h1_close_vs_ma50", "op": "<", "v": 0}
    ]
  },
  "best_hold": 48,
  "win_rate": 46.7,
  "signal_count": 30,
  "sharpe": 85.57,
  "profit_factor": 2.67,
  "priority": 5,
  "_auto_injected": true,
  "_source": "hrr_001_XAGUSD_trend_pullback_s",
  "_pattern_type": "trend_pullback"
}
```

---

## 6. 实盘交易执行

### 6.1 多引擎架构

| Magic | 引擎 | Timeframe | 策略风格 | 信号来源 |
|-------|------|-----------|---------|---------|
| 234010 | **Intraday AP** | M30/H1/M15/M5 | 趋势反转波段 | intraday 研究发现 + Scalping/High-RR 注入 |
| 234011 | **Scalping AP** | M1/M5 | 高胜率超短线 | scalping-m1 研究发现 |
| 234013 | **Scalping PA** | M1/M5 | 价格行为 | price_action_engine |
| — | **KeyLevel AP** | 60s 周期 | 关键位趋势 | AI Cron 决策（非全自动） |
| 234004 | **Triumvirate** | H1/D1 | 三AI投票共识 | AI Agent 分析 |

### 6.2 Autopilot 运行循环

每个 Autopilot 在 tmux 中运行无限循环:

```
while true:
    1. 读取 strategies.json   ← 配置驱动
    2. 连接 TickReader         ← 读取共享数据（不复连 MT5）
    3. 扫描所有策略:
       - 读取品种指标 (320 字段)
       - 评估 entry_conditions
       - 支持跨 TF (_h1_ 条件: 自动读 H1 指标)
    4. 风控检查:
       - RR ≥ 1:1
       - 同品种/同组不重复
       - 最大持仓数
       - 同方向占比
       - DXY 过滤
    5. 下单执行:
       - SL/TP 从 config 读取（支持自定义倍数）
       - 动态仓位（单笔风险 % 净值）
    6. 写日志 + trigger 文件   ← 供 AI 复盘
    7. sleep 15s
```

### 6.3 扫描器实现

两个扫描器同源，均使用 `signal_scanner.py` + `condition_utils.py`:

| 扫描器 | 运行方式 | 数据源 | 用途 |
|--------|---------|--------|------|
| `signal_scanner.py` | 被 autopilot import | TickReader | 主扫描引擎 |
| `scanner_autopilot.py` | Cron 每分钟一次 | TickReader (优先) / MT5 (降级) | 独立扫描 + 执行 |

**降级机制**: 当 Tick Engine 心跳超时 → 自动直连 MT5 扫描（仅支持旧版条件格式）。

### 6.4 风险控制体系

| 规则 | Intraday | Scalping |
|------|----------|---------|
| 单笔风险 | 5% 净值 | 0.05% 净值 |
| 最大持仓 | 4 | 6 |
| 同品种 | max 1 | max 1 |
| 同组 | max 1 | max 1 |
| SL/TP | 可配置倍数 | 2.5x ATR / 3.75x ATR |
| 最小 RR | 1:1 | 1:1 |
| 同方向占比 | ≤ 70% | — |
| 单品种占比 | ≤ 30% | — |

---

## 7. 部署与运维

### 7.1 进程拓扑

```
systemd: futures-daemon.service
    │
    └── tmux: futures-daemon-tick-engine
    │       └── tick_engine.py (1s 循环)
    │
    ├── tmux: futures-daemon-scalping-ap
    │       └── scalping_autopilot.py (15s 循环)
    │
    ├── tmux: futures-daemon-intraday-ap
    │       └── intraday_autopilot.py (15s 循环)
    │
    ├── tmux: futures-daemon-keylevel-ap
    │       └── keylevel_ap.py (60s 周期)
    │
    └── system crontab:
            * * * * * → scan_every_minute.sh → scanner_autopilot.py
```

### 7.2 配置驱动启动

所有策略定义在 `daemon/daemon.json`:

```json
{
  "python": "/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe",
  "base": "F:/AIcoding_space/Hermes/strategies/futures",
  "strategies": {
    "tick-engine":    {"script": "scripts/tick_engine.py", "restart_delay": 5},
    "scalping-ap":    {"script": "single-agent/scalping/scripts/scalping_autopilot.py", "restart_delay": 15},
    "intraday-ap":    {"script": "single-agent/futures-intraday/scripts/intraday_autopilot.py", "restart_delay": 15},
    "keylevel-ap":    {"script": "single-agent/keylevel-trend/scripts/keylevel_ap.py", "restart_delay": 10},
    "scalping-pa":    {"script": "single-agent/scalping/scripts/scalping_pa_autopilot.py", "restart_delay": 15}
  }
}
```

**管理命令**:
```bash
./auto_launch_all.sh start    # 启动所有策略
./auto_launch_all.sh stop     # 停止所有策略
./auto_launch_all.sh status   # 查看状态
./auto_launch_all.sh attach   # 附加到 tmux 会话
```

### 7.3 自愈机制

- 每个组件在 **tmux** 中由 bash `while true` 包裹
- 崩溃后自动重启（默认 15s 延迟）
- **systemd** 保证开机自启 / 全局崩溃恢复
- Tick Engine 写入 heartbeat → Scanner 检测到超时自动降级

### 7.4 监控与报警

- `futures-daemon.service` systemd 服务状态
- Tick Engine heartbeat（10s 超时检测）
- Scanner 日志循环写入 `logs/scanner_debug.log`
- Autopilot 循环计数（当前 ~23580 循环）

---

## 8. 风险控制体系

### 8.1 硬性规则

1. **所有开仓/挂单必须带 SL/TP**
2. **盈亏比 ≥ 1:1**（SL 参考 ATR 且 ≥ 1 倍 ATR）
3. **动态仓位**（单笔风险 = 5% 净值）
4. **禁止重复持仓**（同品种/同组）
5. **DXY 过滤**（外汇/贵金属做多信号需 DXY↓ 验证）

### 8.2 风控检查链

```
扫描到信号 → check_risk():
  1. RR ≥ min_rr (1.0)
  2. 同品种已有持仓？→ veto
  3. 同组已有持仓？→ veto
  4. 最大持仓数超限？→ veto
  5. 同方向占比超限？→ veto
  6. 单品种敞口超限？→ veto
  通过 → calculate_lot_size() → place_order()
```

### 8.3 账户隔离

| 交易风格 | Magic | 账户 |
|---------|-------|------|
| Scalping | 234011 | Exness Demo 277656924 |
| Intraday | 234010 | 同上（共享资金池） |
| KeyLevel | — | 同上 |

---

## 9. 研发到实盘的桥梁

```
研究产出                    配置注入                     实盘执行
─────────                  ────────                   ────────
research_state.json  ──→   auto_inject.py  ──→        strategies.json
(best_findings)             │                          │
  ├─ symbol                 │  1. 门槛过滤              │  被 Autopilot
  ├─ timeframe              │  2. 参数转换              │  每分钟读取
  ├─ direction              │  3. 去重检查              │
  ├─ entry_conditions       │  4. 追加到 config         │  → 评估条件
  └─ _params (pattern)      └──→ 写入 JSON             │  → 风控检查
                                                       │  → 执行交易
                                                       ▼
                                                    MT5 实盘
```

**一句话流程**: AI Agent 研究 → `research_state.json` → `auto_inject*.py` → `strategies.json` → Autopilot 每分钟扫描执行。

---

## 10. 目录结构

```
strategies/
├── README.md
├── docs/
│   └── PRODUCT_ARCHITECTURE.md       ← 本文档
│
├── futures/                          ← 期货交易系统
│   ├── config/
│   │   └── tick_engine.json          ← Tick Engine 配置
│   ├── daemon/
│   │   └── daemon.json               ← 策略注册表
│   ├── data/tick/                    ← 共享数据层 (JSON)
│   ├── scripts/
│   │   ├── tick_engine.py            ← 数据引擎 (唯一连 MT5)
│   │   ├── tick_reader.py            ← 共享数据读取层
│   │   ├── indicators.py             ← 320 指标计算库
│   │   ├── condition_utils.py        ← 条件解析引擎
│   │   ├── discovery_engine.py       ← 因子发现引擎
│   │   ├── batch_precompute.py       ← 批量预计算
│   │   └── price_action_engine.py    ← 价格行为引擎
│   │
│   ├── single-agent/
│   │   ├── futures-intraday/         ← Intraday AP (M30/H1)
│   │   │   ├── config/strategies.json  ← 主策略配置
│   │   │   ├── scripts/
│   │   │   │   ├── intraday_autopilot.py      ← 循环执行
│   │   │   │   ├── signal_scanner.py          ← 信号扫描
│   │   │   │   ├── scanner_autopilot.py       ← Cron 扫描器
│   │   │   │   ├── auto_inject.py             ← Scalping 注入
│   │   │   │   ├── auto_inject_highrr.py      ← High-RR 注入
│   │   │   │   └── execute_trade.py            ← 下单执行
│   │   │   ├── logs/
│   │   │   └── data/research/
│   │   │
│   │   ├── scalping/                 ← Scalping AP (M1/M5)
│   │   │   ├── config/scalping_strategies.json
│   │   │   └── scripts/
│   │   │
│   │   ├── keylevel-trend/           ← KeyLevel 趋势
│   │   ├── triumvirate/              ← 三AI投票共识
│   │   └── pure-ai-cio/              ← AI 自主决策
│   │
│   ├── research/kanban/              ← 研究流水线
│   │   ├── scalping-m1/
│   │   ├── futures-intraday/
│   │   ├── high-rr-research/
│   │   └── candlestick-patterns/
│   │
│   └── reports/                      ← 运行报告存档
│
└── a-stock/                          ← A 股系统
    └── (Tushare ClickHouse 驱动)
```
