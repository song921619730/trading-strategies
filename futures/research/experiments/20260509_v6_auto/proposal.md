# 📜 Proposal: 能源风险预警层 (Energy Risk Warning Layer)

**Status**: 🟡 Draft  
**Linked Experiment**: `20260509_v6_auto`  
**Target Strategy**: `single-agent/pure-ai-cio`

## 🚨 Problem Statement

当前 `pure-ai-cio` 策略在交易股指期货（USTECm/US500m/US30m）时，缺乏对宏观能源价格冲击的风险感知。

2026年4-5月美伊冲突期间，霍尔木兹海峡封锁导致布油突破$101。回测数据显示，当布油>$100时：
- USTEC年化收益从+25.00%骤降至-5.26%
- US500年化收益从+18.36%降至-2.52%
- 原油-股指60日滚动相关跌至-0.74（6年极端值）

虽然单一事件统计显著性不足（t=-0.62, p>0.1），但方向一致且与经济学逻辑吻合——能源成本冲击压缩企业利润，尤其打击科技成长股。

## 💡 Proposed Rule

在 `pure-ai-cio` 的预分析阶段（`pre_analyze.py`）添加能源风险检查层：

```python
# 能源风险预警信号
def check_energy_risk(oil_brent_close, oil_20d_return):
    """
    评估当前能源价格对股指期货的潜在风险
    
    返回: dict
      - risk_level: "HIGH" | "MEDIUM" | "LOW"
      - reason: str
      - position_adjustment: float (仓位调整系数, 0.0-1.0)
    """
    if oil_brent_close > 100 and oil_20d_return > 0.15:
        return {
            "risk_level": "HIGH",
            "reason": f"布油${oil_brent_close:.0f} (> $100) + 20日涨幅{oil_20d_return*100:.1f}%",
            "position_adjustment": 0.6  # 减仓40%
        }
    elif oil_brent_close > 100:
        return {
            "risk_level": "MEDIUM",
            "reason": f"布油${oil_brent_close:.0f} (> $100)",
            "position_adjustment": 0.8  # 减仓20%
        }
    else:
        return {
            "risk_level": "LOW",
            "reason": "正常",
            "position_adjustment": 1.0
        }
```

**触发条件**:
1. `HIGH`: 布油>$100 **且** 20日涨幅>15% → 风险敞口减至60%
2. `MEDIUM`: 布油>$100（仅价格条件） → 风险敞口减至80%
3. `LOW`: 正常 → 不变

**影响范围**: 仅对股指期货品种（USTECm, US500m, US30m）生效，不影响黄金、外汇、原油品种。

**与现有规则的关系**:
- 作为现有 Trade Gate 的**补充层**，不替代任何现有规则
- 在 Trade Gate 之后、最终下单之前执行
- 仅调整仓位大小，不改变入场/出场逻辑

## 📊 Expected Impact

| Metric | Before | After | Source |
|--------|--------|-------|--------|
| Win Rate | 不变 | 不变 | 不改变入场逻辑 |
| Max Drawdown (USTEC) | -30.49% | ~-28.6% | 回测 |
| Max Drawdown (US500) | -27.04% | ~-27.0% | 回测 |
| Sharpe Ratio | 0.920 | 0.920 | 回测（基本不变） |
| Trade Frequency | 不变 | 不变 | 不改变信号生成 |
| 触发频率 | N/A | ~5.6% | 历史统计 |

## 📋 Implementation Checklist

- [ ] 在 `pre_analyze.py` 中添加 UKOILm 数据获取（已有）
- [ ] 计算 UKOILm 20日滚动收益率
- [ ] 实现 `check_energy_risk()` 函数
- [ ] 将结果输出到 `pre_analyze_latest.json`
- [ ] 在 `active_cron_prompt.md` 中添加能源风险解读指引
- [ ] 回测验证（样本外数据）
- [ ] 用户审查和批准

## 📝 Reviewer Notes

**研究背景**: 本次实验测试了两个假设：
1. ❌ 原油-黄金领先-滞后关系 → **不成立**，相关性极弱(0.08-0.10)，无领先关系
2. ⚠️ 能源冲击对股指影响 → **部分成立**，方向正确但统计显著性不足

**保守性说明**: 本提案采取保守姿态——仅作为仓位调整参考，不改变任何入场/出场逻辑。触发频率仅5.6%，属于"低频极端事件过滤器"。

**风险提示**: 
- 2026年美伊冲突期间，虽然油价高企，但股指期货仍在上涨（USTEC +22.93%）。减仓可能错失部分收益。
- 回测样本中高油价期仅123天，统计显著性不足（p>0.1）。
- 建议先在模拟账户观察1-2个月后再考虑实盘应用。

*Pending user approval.*
