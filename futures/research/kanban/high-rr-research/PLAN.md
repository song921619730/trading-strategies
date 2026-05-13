# 低胜率高盈亏比策略研究 — 实施蓝图

> 目录: `futures/research/kanban/high-rr-research/`
> Magic: 234012（独立系统）
> 引擎架构: 克隆 Scalping M1/M5 pipeline，替换核心评估逻辑

---

## 1. 核心理念

当前 Scalping 锁定 **RR=1.6 + WR>60%**，但低 WR 策略在 RR 足够高时同样赚钱：

```
Scalping:      WR=68%, RR=1.6  → EV=0.77
High-RR:       WR=35%, RR=5:1  → EV=0.75  ← 同样正向
```

目标形态：趋势延续、结构突破、假突破反向——这些形态触发的瞬间失败率很高（65%），但一旦成功，跑出 ATR×5~10 的大行情。

---

## 2. 架构

### 2.1 整体流程

```
研究 Cron (每15min)        交易系统
┌─────────────────┐       ┌──────────────────┐
│ 1. 读研究状态     │       │ Scanner (独立)    │
│ 2. 随机采样参数   │ ──→  │ Magic 234012     │
│ 3. 按形态回测     │       │ SL/TP 按形态配置  │
│ 4. 更新 findings  │       │ 注入新发现        │
│ 5. auto_inject   │       │ Execute          │
│ 6. 写日志/报告    │       │ BE管理（同Scalping)│
└─────────────────┘       └──────────────────┘
         ↑                        │
         └─────── scalping_strategies.json ──┘
                           (共用策略配置池)
```

### 2.2 关键区别 vs Scalping

| 维度 | Scalping (Magic 234011) | High-RR (Magic 234012) |
|:----|:---------------------:|:---------------------:|
| **SL/TP** | 固定 ATR×2.5/4.0 | **按形态配置，多组可选** |
| **评估指标** | WR 优先 | **总收益 / Sharpe / PF 优先** |
| **注入门槛** | WR>60% + n>100 | **Sharpe>1.5 + PF>2.0 + n>80** |
| **持仓时间** | 5-30 分钟 | 1-8 小时 |
| **分析框架** | M1/M5 直接扫 | **H1 定势 + M5 入场** |
| **形态类型** | RSI超卖/连阴均值回归 | 趋势回调/突破/假突破 |
| **启动方式** | Autopilot 每分钟 | **独立 Autopilot** |

### 2.3 形态配置（SL/TP 按形态定）

```
趋势回调衰竭:
  H1 趋势向上 + M5 回调至 MA/趋势线 + RSI 回归中性
  → SL = ATR×1.0, TP = ATR×5.0 (RR=5:1)
  → 预期 WR=40-50%, Sharpe 优先

结构突破:
  H1 关键 HL 突破 + M5 放量
  → SL = ATR×0.8, TP = ATR×8.0 (RR=10:1)  
  → 预期 WR=25-35%, PF 优先

假突破反向:
  H1 突破后快速收回 + M5 反转 K
  → SL = ATR×1.2, TP = ATR×6.0 (RR=5:1)
  → 预期 WR=30-40%, Sharpe 优先
```

---

## 3. 实施步骤

### Phase 1: 研究引擎（2-3天）

**Step 1: 数据准备**
- 克隆 Scalping 的 data/ 结构
- H1/M5/M15 parquet 数据（已有，复用或 symlink）
- 修改 metadata.json

**Step 2: 回测引擎**
- 基于 Scalping 的 scan_strategy 改造
- 核心改动: 支持 SL/TP 按形态配置（传入 strategy config 的 sl_multiple / tp_multiple）
- 评估指标: 记录 WR / avg_return / Sharpe / PF / max_drawdown
- 保存格式: 兼容现有 best_findings 但增加 pf / sharpe / rr 字段

**Step 3: 研究者脚本**
- 克隆 scalping-m1/scripts/orchestrator.py
- 替换采样逻辑：在 形态类型 × 品种 × timeframe × 参数 空间中随机搜索
- 替换评估逻辑：按 Sharpe / PF 排名，而非 WR
- 注入逻辑：auto_inject 门槛改为 Sharpe > 1.5 + PF > 2.0

### Phase 2: 交易系统（2天）

**Step 4: Scanner（独立）**
- 克隆 scalping_scanner.py → `high_rr_scanner.py`
- 核心改动：从 strategies.json 读取每个 strategy 的 sl_multiple / tp_multiple
- SL/TP 计算: `sl_distance = atr * sl_multiple`, `tp_distance = atr * tp_multiple`
- 扫描频率: 每 5 分钟（比 Scalping 慢，因为 H1 结构变化慢）

**Step 5: Execute（独立）**
- 克隆 scalping_execute.py → `high_rr_execute.py`
- Magic = 234012
- SL/TP 由 scanner 传入，execute 接单执行

**Step 6: Autopilot（独立）**
- 克隆 scalping_autopilot.py → `high_rr_autopilot.py`
- 复用 BE 管理逻辑
- 循环: 5 分钟

### Phase 3: 部署（0.5天）

- 配置文件初始化
- 研究 Cron 创建
- 回测 + 验证
- 启动 autopilot

---

## 4. 文件清单

### 研究引擎 (scripts/)
- `orchestrator.py` — 研究主循环（克隆 scalping 版，改评估逻辑）
- `high_rr_scanner.py` — 信号扫描（支持多组 SL/TP）
- `auto_inject_high_rr.py` — 注入到交易系统

### 交易系统 (single-agent/high-rr/)
- `scripts/high_rr_scanner.py` — 实盘扫描器
- `scripts/high_rr_execute.py` — 执行（Magic 234012）
- `scripts/high_rr_autopilot.py` — 自动循环

### 配置
- `config/high_rr_strategies.json` — 策略池
- `cron-prompts/research-round.md` — 研究 Cron Prompt
- `state/research_state.json` — 研究进度

### 文档
- `PLAN.md`（本文件）

---

## 5. 待讨论项

1. **第一批形态** — 趋势回调衰竭（最稳妥）还是结构突破（潜力最大）？
2. **Magic 号** — 234012 可以吗？
3. **研究频率** — 每 15 分钟和 Scalping 一样，还是 30 分钟？
4. **scanner 频率** — 5 分钟一次够吗？
5. **数据** — 需要拉 D1 数据做 H1 结构的辅助判断吗？
