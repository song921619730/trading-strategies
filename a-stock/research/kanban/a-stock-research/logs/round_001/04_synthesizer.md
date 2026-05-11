# Round 001 — Synthesizer Log

## 收集到的 Analyst 产出
- TechnicalAnalyst: ✅ hold=1 显著有效（WR 70.33%, CI [65.24%, 74.95%]）
- EventAnalyst: ⚠️ 怀疑信号中混入了涨停溢价

## 评级

| ID | 等级 | 分析师 | 假设简述 |
|----|------|--------|---------|
| init_001_hold1 | B | TechnicalAnalyst | 跳空高开>2%+放量1.5x+RSI>50, hold=1 |

**说明**: CI下限65.24%虽然远超53%（S级门槛），但：
- 只有 TechnicalAnalyst 确认
- 信号量337偏小
- EventAnalyst 发现可能混入涨停溢价 → 需要进一步拆分验证
- 先评为B级，待第二轮拆分验证后升级

## 下轮建议
1. 拆分init_001: 单纯gap_up>2%+放量 (不加RSI) → 对比RSI的边际贡献
2. 排除前日涨停查看纯缺口溢价
3. 换方向: 低开高走模式（补上用户指定主题）

## 当前需要覆盖
- TechnicalAnalyst: round=1
- EventAnalyst: round=1
- MoneyFlowAnalyst, FundamentalAnalyst, SentimentAnalyst, MacroAnalyst: 0次覆盖
