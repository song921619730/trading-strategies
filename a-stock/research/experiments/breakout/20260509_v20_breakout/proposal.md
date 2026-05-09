# 📜 Proposal: 主升浪潜伏信号 — 均线粘合+ATR收缩+放量突破

**Status**: 🟢 Validated (实证支持)  
**Linked Experiment**: `20260509_v20_breakout`  
**Target Strategy**: `a-stock-shortline` (作为选股增强因子)

## 🚨 Problem Statement

当前短线筛选规则缺乏对"蓄势突破"形态的识别能力。大量突破前的整理末期股票未被有效捕捉，导致错过主升浪起爆点。

## 💡 Proposed Rule

### 规则定义：主升浪潜伏信号 (Breakout潜伏因子)

```python
def breakout_latent_signal(stock_data):
    """
    主升浪潜伏与起爆点信号
    返回: 信号强度 (0-100分)
    """
    score = 0
    
    # 1. 均线粘合度 (MA CV10) — 权重 40%
    ma_cv = compute_ma_cv_10d(stock_data)  # MA5/10/20/60 变异系数，10日平滑
    if ma_cv < 0.01:
        score += 40  # 极度粘合
    elif ma_cv < 0.02:
        score += 30  # 高度粘合
    elif ma_cv < 0.03:
        score += 15  # 中度粘合
    
    # 2. ATR 波动率收缩 — 权重 30%
    atr_pct = compute_atr14_pct(stock_data)  # ATR(14)/收盘价
    if atr_pct < 0.015:
        score += 30  # 极度收缩
    elif atr_pct < 0.025:
        score += 20  # 显著收缩
    elif atr_pct < 0.035:
        score += 10  # 轻度收缩
    
    # 3. 放量突破确认 — 权重 30%
    vol_ratio = compute_vol_ratio(stock_data)  # 当日量 / 20日均量
    pct_chg = stock_data['pct_chg']
    close = stock_data['close']
    ma60 = compute_ma(stock_data['close'], 60)
    
    if vol_ratio > 2.0 and pct_chg > 3 and close > ma60:
        score += 30  # 强突破
    elif vol_ratio > 1.5 and pct_chg > 2 and close > ma60:
        score += 20  # 标准突破
    elif vol_ratio > 1.2 and close > ma60:
        score += 10  # 弱突破
    
    return score
```

### 使用方式

1. **选股过滤**: 得分 ≥ 50 分的股票纳入候选池
2. **排序增强**: 在候选池内按得分降序排列，优先选择高分股票
3. **环境过滤**: 仅当沪深300指数收盘价 > MA60 时启用此因子

## 📊 Expected Impact

| Metric | Before | After | Source |
|--------|--------|-------|--------|
| Alpha (年化) | - | +16.5% | 回测 (2020-2026) |
| Win Rate | - | 47.7% (T+20) | 回测 |
| 盈亏比 | - | 1.66 | 回测 |
| 牛市超额 | - | +1.50%/次 | 回测 |
| 熊市超额 | - | +0.86%/次 | 回测 |
| 信号频率 | - | ~4,000次/年 | 回测 |

## 📋 Implementation Checklist

- [ ] 在 `a-stock-shortline` 筛选规则中新增 breakout_latent 因子
- [ ] 实现 MA_CV_10d 计算函数 (MA5/10/20/60 变异系数)
- [ ] 实现 ATR(14)/Close 计算函数
- [ ] 加入沪深300 MA60 环境过滤开关
- [ ] 回测验证整合后的策略表现
- [ ] 设置止损规则 (建议 -8% 或 ATR×3)
- [ ] 用户 review 和审批

## 📝 Reviewer Notes

### 风险提示
1. **高度右偏分布**: 策略中位收益为负 (-0.4%)，大部分信号小亏，靠少数大赢获利。**必须配合止损**。
2. **2022年熊市失效**: 收益 -2.38%，胜率仅 29.1%。**必须加入市场环境过滤**。
3. **信号偏多**: 年均 4,000 次信号，需要配合仓位管理和分批建仓。

### 优势
1. **样本量大**: 25,871 个信号，覆盖 6+ 年全市场，统计可靠性高
2. **逻辑清晰**: 均线粘合 → 波动率收缩 → 放量突破，符合经典技术分析理论
3. **超额稳定**: 年化超额 16.5%，牛熊均有正超额

### 建议
- 作为 **辅助因子** 而非独立策略使用
- 与已有的量价背离因子、机构资金流因子 **组合使用**
- 优先考虑 **板块共振** (如当前新闻显示半导体、新能源有催化剂)
