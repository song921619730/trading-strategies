# Triumvirate Architecture — 三 AI 共识设计文档

## 设计目标

将交易决策从"单人判断"升级为"三人共识"，消除 Pure AI CIO 的认知偏差问题。

## 核心架构

### 三层隔离

```
数据层   → pre_analyze.py (MT5数据)
分析层   → analyst / risk_manager / president (三个独立 Worker)
执行层   → execute_trade.py (MT5下单)
```

### 认知安全机制

1. **隔离** — 三人各管一摊，互不干涉核心职能
2. **质疑** — 第二轮交叉评审，强制要求回应他人观点
3. **否决** — 量化理由的反对不可绕过

## 与 Pure AI CIO 的关系

| 维度 | CIO | Triumvirate |
|------|-----|-------------|
| 数据 | pre_analyze.py | 复用，wrapper 套壳 |
| 执行 | execute_trade.py | 独立版本 (Magic 234004) |
| 新闻 | fetch_news.py | 独立版本 |
| 决策 | 单人 AI | 三人共识 |
| Magic | 234003 | 234004 |

## 失败模式分析

**CIO 已知失败的交易**，在 Triumvirate 下的结局：

| CIO 亏损交易 | 亏损 | 如果三 AI 会怎样？ |
|-------------|------|-------------------|
| XAUUSD SELL #1753985994 | -$11.06 | President 会 VETO（D1 上涨趋势做空）|
| US30 SELL #1753986580 | -$1.36 | President 会 VETO（D1 上涨趋势做空）|
| XAGUSD BUY #1754685771 | -$43.35 | Analyst 评分会低于 5（回调 53%）|
| JP225 BUY #1756812809 | (待关闭) | RiskManager 会拦截（RR 1:0.9）|
| US500 BUY #1755081322 | +$0.96 | SL 异常会被 RiskManager 拦截 |
