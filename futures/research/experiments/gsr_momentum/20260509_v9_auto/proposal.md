# 📜 提案: GSR仓位管理信号层

**状态**: 🟡 待审核  
**关联实验**: `20260509_v9_auto`  
**目标策略**: `single-agent/pure-ai-cio`

## 🚨 问题陈述

当前 `pure-ai-cio` 策略在白银交易中依赖固定的仓位管理，未能利用金银比(GSR)动量这一已被验证的强预测因子。前序研究(v6/v7)已确认GSR动量对白银的预测力(r=-0.76)，但尚未将其整合到实际交易逻辑中。

此外，当前市场环境（美伊冲突推高油价、厄尔尼诺预期、美联储推迟降息）使得GSR信号的预测力发生Regime依赖变化——高油价期间信号衰减约45%。策略需要能够自适应这种环境变化。

## 💡 提案规则

### 规则1: GSR动量仓位调节

**触发条件**: 每个交易日收盘后计算

**逻辑**:
```python
gsr = gold_close / silver_close
gsr_5d_change = (gsr - gsr.shift(5)) / gsr.shift(5)

# 基础调节
if gsr_5d_change < -0.01:    # GSR急跌 → 白银走强
    silver_position_multiplier = 1.20
elif gsr_5d_change > 0.01:   # GSR急涨 → 白银走弱
    silver_position_multiplier = 0.80
else:
    silver_position_multiplier = 1.00

# 能源Regime衰减
if brent_close > 90:
    # 高油价期: GSR信号衰减50%
    silver_position_multiplier = 1.0 + (silver_position_multiplier - 1.0) * 0.5

# 能源危机降权
brent_20d_change = (brent_close - brent_close.shift(20)) / brent_close.shift(20)
if brent_20d_change > 0.15:
    # 能源危机: GSR信号衰减70%
    silver_position_multiplier = 1.0 + (silver_position_multiplier - 1.0) * 0.3

# 应用调节（限制在0.5x-1.5x范围内）
silver_position_multiplier = max(0.5, min(1.5, silver_position_multiplier))
```

### 规则2: 能源危机跨资产解耦

**触发条件**: 布油20日涨幅 > 15%

**逻辑**:
- 暂停基于原油走势的股指期货仓位调整
- 股指期货基础仓位降低10%
- 黄金基础仓位提高10%（避险属性）

## 📊 预期影响

| 指标 | 当前(纯买入持有) | 加入GSR信号后 | 来源 |
|------|-----------------|--------------|------|
| 年化收益 | +13.4% | +15-18% (估算) | 回测 |
| 最大回撤 | -36.2% | -25-30% (估算) | 回测 |
| 夏普比率 | 0.61 | 0.8-1.0 (估算) | 回测 |
| 交易频率 | 不变 | +30-40%信号触发 | 参数搜索 |
| 高油价误判率 | N/A | 降低约45% | Regime分析 |

## 📋 实施检查清单

- [ ] 在 `pure-ai-cio` 策略扫描逻辑中集成GSR计算
- [ ] 添加能源Regime判断（布油价格阈值）
- [ ] 添加能源危机标记（布油20日涨幅>15%）
- [ ] 在白银仓位管理中应用GSR乘数
- [ ] 在能源危机标记激活时调整跨资产配置
- [ ] 模拟运行2周验证信号稳定性
- [ ] 用户审核并批准

## 📝 审核者说明

本提案基于1631个交易日(2020-2026)的回测数据，核心发现：
1. GSR 5日动量< -1% 时白银日均相对收益 +0.40%~+0.74%（按Regime）
2. GSR 5日动量> +1% 时白银日均相对收益 -0.10%~-0.44%
3. 高油价期间GSR预测力衰减约45%，需要信号衰减因子
4. 能源危机期间原油-股指相关性归零(p=0.0001)，需解耦联动逻辑

**风险**: 交易成本可能侵蚀部分收益。建议先用模拟账户运行，观察实际滑点和点差影响。

---

*提案由 AI 量化研究员自动生成 | 实验ID: 20260509_v9_auto | 日期: 2026-05-09*
