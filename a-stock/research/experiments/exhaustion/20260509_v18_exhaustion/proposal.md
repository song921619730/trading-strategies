# 📜 Proposal: 空方衰竭信号作为入场时机优化器

**Status**: 🟡 待验证 (组合因子)  
**Linked Experiment**: `20260509_v18_exhaustion`  
**Target Strategy**: `a-stock-shortline` (增强)

## 🚨 Problem Statement

"空方力量衰竭"（连续缩量+放量收阳/MACD底背离）作为**独立买入信号**胜率不足50%，不满足短线策略的胜率要求。但实验发现：
- H1信号均值+0.16%/日显著异于0 (p<0.001, 27,489样本)
- H2信号均值+0.29%/日为所有假设中最高 (11,513样本)
- 超额收益来自右尾分布，适合做"入场时机优化"

## 💡 Proposed Rule

**不在选股阶段使用衰竭信号**，而是在**已有正向选股模型的候选池中**：

1. 对已选出的候选股票，等待衰竭信号出现后再入场
2. 信号定义: 前3日连续缩量 + 今日放量收阳(vol_ratio > 1.5, pct_chg > 0)
3. 配合v14验证的机构资金流因子(inst_ratio > 80分位)叠加使用
4. 持有期建议: 3-5日，动态止损-3%

## 📊 Expected Impact

| Metric | Before | After | Source |
|--------|--------|-------|--------|
| Win Rate | 基线 | +2~3% (预估) | 需组合回测 |
| Entry Timing | 任意 | 衰竭确认后 | H1/H2 |
| Max Drawdown | 基线 | 降低 (预估) | 更好的入场点 |
| Trade Frequency | 基线 | 减少20-30% | 信号过滤 |

## 📋 Implementation Checklist

- [ ] 组合因子回测: H1信号 + 机构资金流因子(v14)
- [ ] 市场环境过滤测试 (牛市/震荡市/熊市)
- [ ] 动态退出机制优化 (非固定持有期)
- [ ] 回测 on out-of-sample data
- [ ] User review and approval

## 📝 Reviewer Notes

本实验表明衰竭信号**不独立有效**，但作为辅助工具可能有价值。需进一步验证与v14资金流因子的组合效果后再决定是否合并入策略。
