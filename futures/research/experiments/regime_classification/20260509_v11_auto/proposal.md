# 📜 Proposal: Regime-Aware Position Sizing (RAPS) 感知仓位管理层

**Status**: 🟡 Draft  
**Linked Experiment**: `20260509_v11_auto`  
**Target Strategy**: `pure-ai-cio`

## 🚨 Problem Statement

当前 `pure-ai-cio` 策略基于纯技术信号（H1第二段结构）生成交易，但缺乏对市场整体宏观状态（Regime）的感知。实验 v11 证明：
- **同一品种在不同 Regime 下表现天差地别**：US500m 在 RISK_ON 年化 +62.40%，在 NORMAL 年化 -32.39%
- **NORMAL Regime 占 18.7% 时间**，且几乎所有品种同时亏损
- **RISK_OFF Regime 占 15.8% 时间**，股指暴跌但黄金暴涨 92.73%

不识别 Regime 就等于"蒙眼交易"——信号质量再好，也可能在错误的大环境下做多错误的品种。

## 💡 Proposed Rule

### 核心逻辑

每个扫描周期（每 10 分钟），在生成交易信号 **之前** 先判断当前 Regime：

```python
def detect_regime(us500_r20, xau_r20, ukoil_price):
    if ukoil_price >= 100 and us500_r20 < 0 and xau_r20 > 0:
        return "STAGFLATION"
    elif us500_r20 > 0 and ukoil_price < 100:
        return "RISK_ON"
    elif xau_r20 > 0 and us500_r20 < 0:
        return "RISK_OFF"
    else:
        return "NORMAL"
```

### Regime 对应的仓位调整

| Regime | 股指期货仓位 | 贵金属仓位 | 原油仓位 | 外汇仓位 | 说明 |
|--------|-------------|-----------|---------|---------|------|
| RISK_ON | **100%**（正常） | 50% | 50% | 正常 | 主做多股指 |
| RISK_OFF | **0%**（禁止开新多） | **100%**（允许） | 0% | 谨慎 | 切换至黄金 |
| NORMAL | **0%**（禁止开新仓） | 0% | 0% | 50% | 现金为主 |
| STAGFLATION | **0%** | **100%**（黄金+原油） | 50% | 0% | 金油组合 |

### 实施细则

1. **20日收益率计算**: 使用 D1 收盘价，每日更新一次
2. **Regime 切换延迟**: 新 Regime 确认后，次日再执行仓位调整（避免前视偏差）
3. **现有持仓处理**:
   - 从 RISK_ON 切换至 RISK_OFF：平仓所有股指多单，可开黄金多单
   - 从 RISK_ON 切换至 NORMAL：平仓所有品种，仅保留已有盈利持仓（放宽止损）
   - 从 NORMAL 切换至 RISK_ON：恢复正常交易
4. **信号叠加**: Regime 层不替代技术信号，而是作为 **信号过滤器**（Gate）。只有 Regime 允许的方向，技术信号才生效。

## 📊 Expected Impact

基于回测结果（2020-01-14 至 2026-05-08）：

| Metric | Before (B&H US500) | After (Regime Filtered) | Source |
|--------|-------------------|------------------------|--------|
| Annual Return | 16.08% | **53.63%** | Backtest v11 |
| Sharpe Ratio | 0.82 | **3.73** | Backtest v11 |
| Max Drawdown | -27.04% | **-12.58%** | Backtest v11 |
| Trade Frequency | 100% days | **81.3%** invested days | Backtest v11 |

**⚠️ 注意**: 以上为理想化回测，未计入交易成本/滑点。实际效果预计打 5-7 折。

## ⚠️ Risk Considerations

1. **滞后性**: 20日 Regime 判断天然滞后，Regime 切换初期会有信号延迟
2. **假信号**: RISK_OFF 可能只是短期回调而非趋势反转（平均仅 4 天）
3. **布油阈值**: $100 为事后搜索，需考虑 ±$5 的敏感性
4. **STAGFLATION 样本不足**: 仅 18 天，该 Regime 规则需谨慎对待

## 📋 Implementation Checklist

- [ ] 在 `pure-ai-cio` 扫描流程中前置 Regime 检测模块
- [ ] 更新 `skills/risk-rules.md` 添加 Regime-aware 规则
- [ ] 回测加入 1 日延迟执行假设 + 手续费/滑点
- [ ] 对布油阈值做敏感性分析（$90/$95/$100/$105）
- [ ] 用户 review 和 approval

## 📝 Reviewer Notes

*本提案基于实验 v11 的回测结果。核心洞察是：NORMAL Regime（占 18.7% 时间）几乎对所有品种都是"死亡区"，现金管理即可大幅改善风险收益比。RISK_OFF 期黄金的完美对冲表现（92.73% 年化）进一步增强了 Regime 过滤的价值。*

*建议先以影子模式运行 2-4 周，验证 Regime 判断的实时准确率后再正式上线。*
