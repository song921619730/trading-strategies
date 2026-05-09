# 📜 Proposal: Cross-Asset Volatility Resonance Alert

**Status**: 🟡 Draft  
**Linked Experiment**: `20260508_v4_auto`  
**Target Strategy**: Pure AI CIO (`single-agent/pure-ai-cio`)

## 🚨 Problem Statement

Pure AI CIO 的 Trade Gate 在当前全市场低波动环境下频繁拦截交易（连续 3 次扫描零机会）。虽然"低波动拦截"在大多数情况下是正确的（避免噪音交易），但它也**错失了最可能爆发的时刻**。

研究表明：当 3+ 品种同时进入低波动压缩时，随后的 5 日波动比正常大 **80-118%**。能源品种（原油/布油）更是高达 **190-253%**。

## 💡 Proposed Rule

**不改变现有 Trade Gate 的拦截逻辑**，而是增加一个 **"共振警报"层**：

### 新规则：Sync Compression Alert (SCA)

```
IF 3+ commodities are simultaneously in low-vol compression:
    → Flag as "HIGH POTENTIAL BREAKOUT WINDOW"
    → Override: Allow trades with relaxed structural requirements
    → Alert: Notify user of rare regime condition
    → Size: Reduce position size (higher uncertainty)
    → Note: Still requires SL/TP
```

### 具体实现建议

1. **pre_analyze.py 增强**:
   - 在现有单品种 ATR 计算基础上，增加跨品种同步计数
   - 计算 `sync_count = sum(1 for asset in assets if asset.compression_ratio < 0.7)`
   - 如果 `sync_count >= 3`，标记为共振窗口

2. **Trade Gate 调整**:
   - 原有 5 条硬过滤保持不变
   - 新增例外条款: "若 sync_count >= 3，允许 H1 结构不完全符合第二段时开仓"
   - 降低手数上限（共振窗口不确定性更高）

3. **AI Prompt 更新**:
   - 在扫描 Prompt 中注入同步计数信息
   - 引导 AI 将此视为"高置信度突破窗口"，而非"无机会"

## 📊 Expected Impact

| Metric | Before | After | Source |
|--------|--------|-------|--------|
| Trades during sync | 0 | 1-2 per sync window | Backtest |
| Avg move captured | Missed (0%) | Partial (50-70%) | Estimate |
| False positives | N/A | Low (15 sync days in 2.5y) | Backtest |
| Win rate | N/A | Unknown | Needs live testing |

## 📋 Implementation Checklist

- [ ] Update `scripts/pre_analyze.py` to calculate sync_count
- [ ] Add sync_count to scan output/brief
- [ ] Update Pure AI CIO prompt with SCA rules
- [ ] Test on historical sync windows (backtest)
- [ ] User review and approval

## 📝 Reviewer Notes

- **Risk**: This increases trade frequency during a regime that occurs ~15 days per 2.5 years. The opportunity cost of *not* acting is high (missing 129% enhanced moves).
- **Conservative approach**: Don't remove the hard filters — just add an exception path when the cross-asset signal is strong.
- **Energy focus**: Oil (USOIL/UKOIL) shows the strongest amplification. Consider oil-specific sync detection as a leading indicator.
