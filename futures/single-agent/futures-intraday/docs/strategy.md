# Futures Intraday Algo — 策略说明书

## 数据来源
32 轮自动化研究（Round 1-32），基于 2021-01 ~ 2026-05 的 H1/M30 全量历史数据。

## 研究引擎
- 目录: `strategies/futures/research/kanban/futures-intraday/`
- 脚本: `grid_engine.py` → 多品种多时段回测
- 状态: `state/research_state.json`（65 条 findings）
- 状态: **converged**（疲劳度 5，研究空间已穷尽）

## 核心发现模式

### 模式 A: 美盘时段超卖反弹（最强信号）
```
条件: session='us' + RSI<40 + ATR>0.25%
方向: long
持有: 5-15 根 K 线
品种: EURUSD(67%), XAUUSD(66%), JP225(64%), US30(61%), AUDUSD(61%)
逻辑: 美盘时段高波动+超卖 → 短线空头回补/反转
```

### 模式 B: 连续阴线反转
```
条件: consecutive_bear_count >= 3
方向: long
持有: 8-10 根 K 线
品种: US500(55.7%), USDJPY(55.3%), US30(55.1%)
逻辑: 三连阴后均值回归
```

### 模式 C: 美盘方向性偏差
```
条件: session='us'
方向: long
持有: 10 根 K 线
品种: US500(55.6%), USTEC(55.7%)
逻辑: 美盘长期偏多
```

### 模式 D: 伦敦开盘反转
```
条件: hour=8 + RSI>50
方向: short
持有: 3
品种: EURUSD(55.8%)
逻辑: 伦敦开盘高RSI → 均值回归
