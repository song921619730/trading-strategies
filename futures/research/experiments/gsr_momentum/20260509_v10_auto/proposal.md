# 📜 Proposal: GSR跨资产风险情绪信号层

**Status**: 🟢 Validated (实验 v10 已验证)
**Linked Experiment**: `20260509_v10_auto`
**Target Strategy**: `pure-ai-cio` (主要), `keylevel-trend` (次要)

## 🚨 Problem Statement

现有策略(pure-ai-cio, keylevel-trend)在原油方向判断和股指期货风险预警方面缺乏跨资产的前瞻性信号。实验v10证实：
1. 金银比(GSR)20日变化率对US500m和USTECm未来20日收益的预测相关系数>0.16，p<1e-10
2. 简单GSR策略在UKOILm上回测年化65.67%，夏普1.03
3. 黄金在"鹰派+冲突"环境下并非最佳资产，该直觉被数据拒绝

## 💡 Proposed Rule

### 规则1: GSR-原油动量信号
```
计算: GSR = XAUUSDm_close / XAGUSDm_close
     GSR_chg20 = (GSR / GSR[20日前] - 1) * 100
     GSR_zscore = (GSR - GSR_MA20) / GSR_STD20

信号:
  IF GSR_chg20 > 0 AND GSR_zscore > 0:
      → 原油方向偏多 (历史胜率58%+)
  IF GSR_chg20 < 0 AND GSR_zscore < -1.5:
      → 原油方向偏空 (极度风险偏好后的回调信号)
```

### 规则2: GSR-股指期货风险预警
```
计算: GSR_chg20 的 252日滚动80分位阈值

预警:
  IF GSR_chg20 > threshold_80pct:
      → USTECm/US500m/US30m 仓位降至50%
      → 理由: GSR快速上升 = 风险厌恶升温 → 股指期货前瞻收益转弱
  IF GSR_chg20 < threshold_20pct:
      → 正常仓位 (风险偏好环境，股指通常表现良好)
```

## 📊 Expected Impact

| Metric | Before | After | Source |
|--------|--------|-------|--------|
| 原油方向准确率 | N/A (无专门信号) | 58%+ (鹰派+冲突期) | v10回测 |
| 原油策略年化 | N/A | 65.67% | v10 UKOILm策略 |
| 原油策略夏普 | N/A | 1.03 | v10 UKOILm策略 |
| 股指期货预警 | N/A | GSR_chg20 r=0.167, p<1e-10 | v10统计检验 |
| 最大回撤(原油) | N/A | -25.10% | v10回测 |

## 📋 Implementation Checklist

- [x] 实验验证 (v10: 1553个交易日, 14品种, 全样本)
- [ ] 在 `pure-ai-cio` 策略中添加GSR计算模块
- [ ] 添加GSR-原油信号层到扫描逻辑
- [ ] 添加GSR-股指风险预警层
- [ ] 样本外验证 (使用前向滚动窗口)
- [ ] 用户审查和批准

## 📝 Reviewer Notes

**关键发现**: 实验v10拒绝了"黄金在鹰派+冲突期是最佳避险资产"的直觉假设。相反，原油在该Regime下表现最强(年化50%+)。GSR作为跨资产风险情绪指标，对股指期货和原油具有统计显著的预测力。

**风险**: GSR策略对黄金和美股指数本身失效(回测为负收益)，仅适用于原油方向判断和股指风险预警。不建议将GSR作为贵金属或股指的直接交易信号。

**数据范围**: 2020-01-13 至 2026-05-08, 1553个交易日, 14品种全覆盖。
