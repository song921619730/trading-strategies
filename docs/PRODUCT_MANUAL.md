# 期货量化交易系统 — 产品文档

> **一句话**: MT5 拉数据 → 引擎算 320 个指标 → AI 挖掘因子 → 自动注入策略配置 → Autopilot 扫信号下单

---

## 第一章：这个系统能干什么

### 1.1 核心能力

| 能力 | 说明 |
|------|------|
| **全天候自动交易** | 5 个交易引擎同时跑，覆盖 M1~H1 五个时间框架 |
| **AI 辅助策略发现** | Agent 自动跑因子挖掘，合格信号自动注入交易系统 |
| **无需手动写代码** | 新增策略只改 JSON，注入脚本自动处理格式转换 |
| **崩溃自愈** | 每个组件在 tmux 里跑，挂了自动重启，systemd 保证开机自启 |
| **研究→实盘闭环** | 研究产出的信号 → 自动注入配置 → 下一分钟就开始实盘扫描 |

### 1.2 交易什么

**19 个品种**，覆盖外汇、贵金属、指数、能源、商品：

```
外汇:   EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, USDCAD, NZZDUSD
贵金属: XAUUSD, XAGUSD
指数:   US30, US500, USTEC, JP225, HK50
能源:   USOIL, UKOIL
商品:   XNGUSD(天然气), XCUUSD(铜)
美元:   DXY(仅作为过滤信号)
```

### 1.3 交易风格

| 策略族 | Magic | 时间框架 | 风格 | 存活信号 |
|--------|-------|---------|------|---------|
| **Intraday** | 234010 | M30/H1 + M5/M15 | 趋势反转波段 + 低胜率高盈亏比 | 74 |
| **Scalping** | 234011 | M1/M5 | 超短线高胜率剥头皮 | 54 |
| **PA Scalping** | 234013 | M1/M5 | 价格行为形态 | — |
| **合计** | | | | **128 个信号** |

---

## 第二章：数据怎么来的

### 2.1 实时行情（Tick Engine）

系统里**唯一**连 MT5 的组件，其他模块都不准直接连 MT5。

```bash
# 它每秒钟干这些事：
1. 读 19 个品种的 tick（bid/ask/spread）
2. 检测有没有新 K 线形成
3. 如果有新 K 线 → 拉取 OHLCV 数据 → 计算 320 个指标
4. 把结果写到共享文件 data/tick/ 下面
5. 更新心跳时间戳
```

**配置文件** `config/tick_engine.json`:
```json
{
  "symbols": ["XAUUSD","EURUSD","US500", ...19个],
  "timeframes": ["M1","M5","M15","M30","H1"],
  "loop_interval_sec": 1.0
}
```

### 2.2 共享数据层

Tick Engine 写好文件后，所有 Scanner 和 Autopilot 通过 `tick_reader.py` 读取，**不再连 MT5**。

```
data/tick/
├── ticks.json               # 19品种最新 bid/ask
├── indicators_M1.json       # M1 全部指标
├── indicators_M5.json
├── indicators_M15.json
├── indicators_M30.json
├── indicators_H1.json       # H1 全部指标
├── bar_signals.json         # 新 K 线事件通知
└── heartbeat.json           # 引擎心跳
```

每个指标文件的结构：
```json
{
  "indicators": {
    "XAUUSD": {
      "price": 4693.1,
      "rsi14": 46.79,
      "atr14": 17.81,
      "consecutive_bear": 3,
      "session": "europe",
      "close_vs_ma50": -0.036,
      ... // 共 320 个字段
    },
    "EURUSD": { ... },
    ...
  },
  "_updated_at": "2026-05-14T12:01:54Z",
  "_cycle": 10863
}
```

### 2.3 回测/研究数据

研究用的历史数据存 **Parquet** 格式，和实时数据同源（都从 `indicators.py` 算指标）。

```
research/kanban/{研究线}/data/
├── H1/
│   ├── XAUUSD.parquet
│   ├── EURUSD.parquet
│   └── ...
└── M5/
    ├── XAUUSD.parquet
    └── ...
```

---

## 第三章：指标怎么算

### 3.1 indicators.py — 唯一指标库

所有指标只在一个地方实现：`scripts/indicators.py`（84 个函数，320 个指标）。

研究回调和实时交易**调用同一份代码**，保证值完全一致。

| 类别 | 指标举例 |
|------|---------|
| **趋势** | EMA(5/8/12/13/20/21/26/34/50/55/89/144/200), SMA(5/10/20/30/50/100), Ichimoku, Guppy, PSAR |
| **动量** | RSI(7/14/21/50), MACD, Stochastic, CCI, Williams %R, ROC, TRIX |
| **波动率** | ATR(5/7/10/14/21/50), Bollinger Bands(3组), Keltner(3组), Donchian(3组) |
| **成交量** | OBV, MFI, CMF, Volume Ratio, Volume Spike, EoM, Force Index |
| **价格行为** | Doji, Hammer, Engulfing, Harami, Pin Bar, Inside Bar, Marubozu, 3-line patterns |
| **结构** | HH/LL Breakout, Support/Resistance, Pivot Points, Fibonacci |
| **综合** | Z-Score (5档), Market Regime, Heikin Ashi, VWAP, Choppiness Index |

### 3.2 研究用的批量计算

```bash
# 给某个数据集算全部指标，存入 Parquet
python3 scripts/batch_precompute.py --data-dir research/kanban/scalping-m1/data
```

### 3.3 一致性验证

```
实时 tick_engine → indicators.py  → ATR14=XAUUSD=17.81
研究 batch_precompute → indicators.py → ATR14=XAUUSD=17.81  ✅
```

---

## 第四章：因子怎么挖（研究流水线）

### 4.1 研究引擎

核心脚本 `scripts/discovery_engine.py`，扫数据集的所有列，自动发现交易信号。

```bash
# 用法
python3 scripts/discovery_engine.py --data-dir research/kanban/high-rr-research/data
```

### 4.2 四种研究线并行

| 研究线 | 挖什么 | 当前进度 |
|--------|--------|---------|
| **scalping-m1** | M1/M5 超短线，高胜率（WR>70%），RSI 极值入场 | Round 40+ |
| **futures-intraday** | M30/H1 波段，RSI 超卖反弹 + DXY 过滤 | Round 32+ |
| **high-rr-research** | M5/M15/H1 低胜率高盈亏比（Sharpe>30,PF>2） | Round 12, 100 发现池 |
| **candlestick-patterns** | H1/D1 K 线形态 | Round 19 |

### 4.3 一次研究的完整流程

```
Step 1: AI Agent 接收 Cron 触发
  ↓
Step 2: 运行 discovery_engine.py
  ↓
Step 3: Agent 分析输出 → 过滤合格发现 → 输出报告
  ↓
Step 4: 写入 research_state.json（最佳发现池）
  ↓
Step 5: 下一轮 → auto_inject 自动注入到交易系统
```

**产出格式**（research_state.json 的 best_findings）：
```json
{
  "id": "hrr_001_XAGUSD_trend_pullback_s",
  "symbol": "XAGUSD",
  "timeframe": "M15",
  "direction": "short",
  "win_rate": 46.7,        // 低胜率
  "sharpe": 85.57,          // 高 Sharpe
  "profit_factor": 2.67,    // 高盈亏比
  "n": 30,                  // 样本量
  "_params": {
    "pattern_type": "trend_pullback",
    "session": "us",
    "sl_multiple": 1.2,
    "tp_multiple": 5.0,
    "rsi14_max": 50,
    "rsi14_min": 70,
    "pullback_to_ma50": true,
    "h1_trend": "down"
  }
}
```

---

## 第五章：策略怎么注入

### 5.1 条件引擎（condition_utils.py）

研究发现产出的条件 → 转成 Scanner 能执行的形式。

**三套格式自动兼容**:

```
旧版简单格式:
  {"rsi14_max": 40, "session": "us", "atr_min_pct": 0.0025}

新版通用格式（conditions 数组）:
  {"conditions": [
    {"i": "rsi14", "op": "<", "v": 40},
    {"i": "consecutive_bear", "op": ">=", "v": 3}
  ]}

特殊处理器（跨品种/跨TF）:
  _dxy_filter          → 读 DXY H1 判断美元方向
  _near_ma50           → 检查价格离 MA50 < 0.1%
  _h1_close_vs_ma50    → 跨TF检查 H1 趋势方向
```

### 5.2 注入脚本

| 脚本 | 读什么 | 写到哪里 | 门槛 |
|------|--------|---------|------|
| `auto_inject.py` | intraday research_state | intraday strategies.json | WR>68%, n≥60 |
| `auto_inject_highrr.py` | high-rr research_state | intraday strategies.json | Sharpe≥30, PF≥1.8, n≥30 |

**注入流程**:
```
读取 research_state.json
  → 遍历 best_findings
  → 检查门槛（WR/Sharpe/PF/n）
  → 去重（已有 ID + 已注入源）
  → _params_to_conditions() 转成 entry_conditions
  → 追加到 strategies.json 的 signals[]
  → 记录 _injected_sources 防重复
  → 下一分钟 autopilot 自动开始扫描该信号
```

### 5.3 策略配置格式（strategies.json）

```json
{
  "description": "Futures Intraday Algo — 策略配置参数",
  "magic_number": 234010,
  "risk": {
    "risk_per_trade_pct": 0.05,
    "max_portfolio_risk": 0.2,
    "max_positions": 4,
    "max_per_group": 1,
    "min_rr": 1.0
  },
  "signals": [
    {
      "id": "tier1_eur_us_h1_oversold",
      "group": "fx_dxy_filtered",
      "symbols": ["EURUSD"],
      "timeframe": "H1",
      "direction": "long",
      "entry_conditions": {
        "session": "us",
        "rsi14_max": 40,
        "atr_min_pct": 0.0025,
        "dxy_filter": "down"
      },
      "priority": 1,
      "win_rate": 89.7
    },
    {
      "id": "hrr_trend_xagusd_m15_s",
      "group": "hrr_metals_pullback",
      "symbols": ["XAGUSD"],
      "timeframe": "M15",
      "direction": "short",
      "entry_conditions": {
        "session": "us",
        "sl_multiple": 1.2,
        "tp_multiple": 5.0,
        "conditions": [
          {"i": "rsi14", "op": "<", "v": 50},
          {"i": "rsi14", "op": ">", "v": 70},
          {"i": "consecutive_bear", "op": ">=", "v": 2},
          {"i": "consecutive_bull", "op": ">=", "v": 3},
          {"i": "_near_ma50", "op": "==", "v": 1},
          {"i": "_h1_close_vs_ma50", "op": "<", "v": 0}
        ]
      },
      "_auto_injected": true,
      "sharpe": 85.57,
      "profit_factor": 2.67
    }
  ]
}
```

---

## 第六章：实盘怎么交易

### 6.1 三个 Autopilot 同时跑

每个在 tmux 里独立运行，互不干扰：

```
tmux: futures-daemon-tick-engine    → tick_engine.py          (1s/次)
tmux: futures-daemon-scalping-ap    → scalping_autopilot.py   (15s/次)
tmux: futures-daemon-intraday-ap    → intraday_autopilot.py   (15s/次)
```

### 6.2 Autopilot 一次循环

```python
while True:
    # 1. 读策略配置
    cfg = read_json("config/strategies.json")

    # 2. 通过 TickReader 读共享数据（不连 MT5）
    reader = TickReader()
    dxy = reader.get_indicator("DXY", "H1")

    # 3. 遍历所有策略，扫描信号
    for strategy in cfg["signals"]:
        ind = reader.get_indicator(symbol, timeframe)
        h1_ind = reader.get_indicator(symbol, "H1")  # 跨TF
        matched = evaluate_entry_conditions(
            strategy["entry_conditions"], ind, dxy, h1_ind
        )
        if matched:
            signals.append(signal)

    # 4. 风控检查
    for sig in signals:
        check_risk(sig, positions, risk_cfg)

    # 5. 执行交易（带 SL/TP）
    place_order(sig, lot_size, magic)

    # 6. 写日志
    save_scan_log(detected)
    sleep(15)
```

### 6.3 风控规则（check_risk）

执行交易前必须通过全部检查：

| # | 检查项 | 规则 |
|---|--------|------|
| 1 | RR 比率 | TP/SL ≥ 1.0 |
| 2 | 同品种 | 已有持仓 → 跳过 |
| 3 | 同组 | 同品种组已有持仓 → 跳过 |
| 4 | 最大持仓 | Intraday ≤ 4, Scalping ≤ 6 |
| 5 | 同方向占比 | ≤ 70%（仅 Intraday） |
| 6 | 单品种敞口 | ≤ 30%（仅 Intraday） |

### 6.4 SL/TP 规则

```
默认: SL = ATR × 2.0,  TP = ATR × 4.0  (RR=2.0)
可配置: entry_conditions 里写 sl_multiple/tp_multiple 覆盖

High-RR 信号示例:
  trend_pullback: SL=ATR×1.2, TP=ATR×5.0  (RR=4.2)
  structure_breakout: SL=ATR×0.5, TP=ATR×10.0  (RR=20.0)
```

### 6.5 日志体系

每次扫描和交易都存档，供 AI 复盘：

```
logs/
├── signals/          ← 信号扫描记录(scan_20260514_*.json)
├── scans/            ← scanner_autopilot 扫描记录
├── trades/           ← 交易执行记录(trade_20260514_*.json)
├── triggers/         ← trigger 文件（Cron 报告用）
├── intraday_autopilot.log  ← 循环日志
└── scanner_debug.log       ← 调试日志
```

---

## 第七章：怎么部署和运维

### 7.1 启动全部

```bash
cd F:/AIcoding_space/Hermes/strategies/futures

# 一键启动所有
./auto_launch_all.sh start

# 检查状态
./auto_launch_all.sh status

# 停掉所有
./auto_launch_all.sh stop

# 附加到某个 tmux 看实时输出
tmux attach -t futures-daemon-intraday-ap
```

### 7.2 新增策略只改两个文件

```bash
# 1. 注册到 daemon
vim daemon/daemon.json
#   → 加一行: "my-new-ap": {"script": "single-agent/.../autopilot.py"}

# 2. 写策略配置
vim single-agent/my-new-ap/config/strategies.json

# 3. 重启生效
./auto_launch_all.sh stop
./auto_launch_all.sh start
```

### 7.3 运行环境

| 组件 | 运行位置 |
|------|---------|
| Tick Engine | **Windows**（需要 MT5 Python API） |
| Autopilot | **Windows**（下单需要连 MT5） |
| AI Agent / 研究 | **WSL**（Hermes Agent） |
| 数据存储 | `F:/` 共享盘，两边都能读写 |

### 7.4 监控要点

```
1. Tick Engine 是否活着？
   → cat data/tick/heartbeat.json | jq ._updated_at

2. Autopilot 循环计数？
   → tail -1 logs/intraday_autopilot.log
   → 看到 "循环#23xxx | 持仓 0" 就正常

3. 有没有信号？
   → tail -20 logs/scanner_debug.log
   → 找 "signals_found"

4. 持仓状态？
   → 登录 MT5 看，或跑 check_positions.py
```

---

## 第八章：一次完整的研→交闭环

用 High-RR 注入的完整流程举例：

```
时间线                             发生了什么
────────────────────────────────────────────────────────
Day 1  13:00 UTC   AI Cron 触发研究轮次
                   → discovery_engine.py 扫描 H1/M5 数据集
                   → 发现 XAGUSD M15 trend_pullback short
                   → Sharpe=85.57, PF=2.67, n=30
                   → 写入 research_state.json

Day 1  13:05 UTC   AI Agent 分析结果 → 输出报告
                   → 报告存入 reports/research_round_5.md

Day 1  13:10 UTC   auto_inject_highrr.py 执行
                   → 读 research_state.json
                   → Sharpe 85.57 ≥ 30 ✅ → 转换参数
                   → 追加到 strategies.json

Day 1  13:11 UTC   Intraday Autopilot 重启 → 读到新配置
                   → XAGUSD M15 信号进入扫描队列

Day X  US 时段     市场条件满足 XAGUSD M15 条件:
                   session=us ✅
                   rsi<50 ✅ rsi>70 ✅
                   price near MA50 ✅
                   H1 downtrend ✅
                   → 信号触发 → 风控通过 → 下单执行

Day X+1            Autopilot 检查持仓 → TP 或 SL 触发 → 平仓
                   → 交易日志存档 → AI 复盘引用
```

---

## 附录

### A. 常用命令速查

```bash
# 手动跑一次信号扫描（验证信号）
python3 signal_scanner.py

# 手动跑一次交易循环
python3 intraday_autopilot.py --once

# 注入最新研究发现
python3 auto_inject_highrr.py --dry-run  # 先预览
python3 auto_inject_highrr.py             # 再执行

# 检查账户
python3 execute_trade.py --check

# 查看持仓
python3 -c "
import MetaTrader5 as mt5
mt5.initialize()
for p in mt5.positions_get():
    print(p.symbol, p.type_str(), p.volume, p.profit)
mt5.shutdown()
"
```

### B. 关键文件索引

| 文件 | 作用 | 约多少行 |
|------|------|---------|
| `scripts/tick_engine.py` | 数据引擎 | 438 |
| `scripts/indicators.py` | 320 指标库 | 2,332 |
| `scripts/tick_reader.py` | 共享数据读取 | 193 |
| `scripts/condition_utils.py` | 条件解析引擎 | 317 |
| `scripts/discovery_engine.py` | 因子发现引擎 | 413 |
| `scripts/batch_precompute.py` | 批量预计算 | 517 |
| `scripts/tick_engine.py` | 数据引擎 | 438 |
| `intraday/scripts/signal_scanner.py` | 信号扫描 | 163 |
| `intraday/scripts/intraday_autopilot.py` | 主执行循环 | 295 |
| `intraday/scripts/scanner_autopilot.py` | Cron 版扫描 | 307 |
| `intraday/scripts/execute_trade.py` | 下单执行 | ~340 |
| `intraday/scripts/auto_inject_highrr.py` | High-RR 注入 | ~280 |

### C. 符号对照

| 符号 | 含义 |
|------|------|
| 234010 | Intraday 自动交易 |
| 234011 | Scalping 自动交易 |
| 234013 | Scalping PA 自动交易 |
| 234004 | Triumvirate 三AI共识 |
| 234012 | High-RR 独立扫描（研究中） |
