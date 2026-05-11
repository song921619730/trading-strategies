# Futures Intraday Algo — 信号量化交易策略

> 基于 32 轮自动化研究发现的强信号（WR 55-67%），在 MT5 上自动执行。

## Top 信号概览

| Tier | 品种 | 条件 | TF | WR | n |
|------|------|------|-----|-----|---|
| ⭐ | EURUSD | ATR>0.25% + RSI<40 + 美盘时段 做多 | H1 | 67.4% | 193 |
| ⭐ | XAUUSD | 美盘时段 + RSI<40 + ATR>0.35% 做多 | M30 | 65.8% | 664 |
| ⭐ | JP225 | 美盘时段 + RSI<40 + ATR>0.25% 做多 | M30 | 63.8% | 583 |
| ⭐ | XAUUSD | 美盘时段 + RSI<40 + ATR>0.25% 做多 | H1 | 62.5% | 1,530 |
| ⭐ | US30 | 美盘时段 + RSI<40 + ATR>0.25% 做多 | H1 | 61.1% | 517 |
| ⭐ | AUDUSD | 美盘时段 + RSI<40 + ATR>0.25% 做多 | H1 | 60.6% | 94 |
| ⭐ | HK50 | 美盘时段 + RSI<40 + ATR>0.25% 做多 | M30 | 60.5% | 223 |
| A | EURUSD | 美盘时段 + RSI<50 + ATR>0.20% 做多 | M30 | 59.3% | 329 |

## 架构

```
scripts/signal_scanner.py   # 信号扫描引擎（核心）
scripts/execute_trade.py    # MT5 执行
config/strategies.json      # 策略配置参数
config/cron_prompt.md       # Cron Job Prompt
```

## 运行方式

每 15-30 分钟通过 Cron Job 自动执行：
1. 连接 MT5，拉取 14 个品种的 H1/M30 数据
2. 计算 RSI、ATR 等技术指标
3. 匹配 strategies.json 中的条件
4. 有信号 → 检查风控（已有持仓、相关品种限制、手数计算）
5. 执行交易
