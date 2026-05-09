# 🧠 Knowledge Base (Futures Research)

*Accumulated wisdom from past experiments. Orchestrator loads this to prevent redundant research.*

## 📅 Archive

## 2026-05-08: Volatility Compression Release (Gold)
- **Finding**: XAUUSDm ATR compression (<70% of 20-bar median) precedes higher volatility. "Release" bars have 37.1% chance of big move (vs 20.6% baseline).
- **Metric**: 1 year H1 data. Compression freq 5.2%. Release big move rate +80% relative to baseline.
- **Status**: Proposal drafted. Suggests modifying Pure AI CIO Trade Gate from "Hard Block" to "Release Priority".

## 2026-05-08: Cross-Asset Volatility Resonance
- **Finding**: When 3+ commodities simultaneously enter low-vol compression, subsequent 5-day moves are 80-118% stronger than baseline. Oil (USOIL/UKOIL) amplifies most at 190-253%.
- **Metric**: 648 aligned trading days (7 symbols, ~2.5 years). 15 sync days, 3 release events. Release enhancement: +129.6%.
- **Status**: Proposal drafted. Suggests adding "Sync Compression Alert" layer to Pure AI CIO without removing existing Trade Gate filters.
- **Distinction from prior work**: Previous research studied single-asset Gold compression. This studies multi-asset synchronization effect.

## 2026-05-09: Geopolitical Regime Impact on Gold Volatility
- **Finding (H1)**: Gold volatility compression releases are NOT more explosive during geopolitical escalation. Big move rate is 100% across ALL regimes (normal, escalation, de-escalation). Escalation releases actually showed 19% smaller max moves (1.10% vs 1.36%).
- **Finding (H2)**: Gold-stock correlation shifts are event-type dependent, not regime-uniform. Delta (esc - normal) = -0.083, below significance threshold. War events (RU-Ukraine -0.647) show strong negative correlation; liquidity crises (pandemic +0.497) show positive correlation.
- **Metric**: 818 trading days (2020-01 to 2023-06), 5 symbols. 12 compression releases (9 normal, 2 escalation, 1 de-escalation). 6 geopolitical events.
- **Status**: No strategy modification recommended. Compression signal is self-contained and regime-independent.
- **Distinction from prior work**: Previous research studied compression in isolation. This tests whether geopolitical context amplifies or modifies the compression signal.
- **Limitation**: Equity data only through mid-2023; recent events (2024-2026) not tested.

## 2026-05-09: 原油-黄金跨资产领先-滞后关系 (Oil-Gold Lead-Lag)
- **Finding (H1)**: 原油与黄金之间**不存在任何有意义的领先-滞后关系**。全样本相关系数仅0.08-0.10，最佳交叉相关出现在lag=0（同期）。冲突期与正常期相关性完全一致(0.0824 vs 0.0839)。
- **Finding (H2)**: 原油动量信号用于黄金交易的策略**完全不可用**——所有回测参数均大幅跑输买入持有黄金（最差-45.03% vs +190.17%基准）。
- **Finding (H3)**: 2022年俄乌战争期间黄金-WTI相关飙升至0.40（两者同为避险），但2026年美伊冲突期间为-0.18（反向运动），说明跨资产关系高度依赖冲突类型。
- **Metric**: 1631个交易日(2020-01至2026-05), 3品种(XAUUSD/USOIL/UKOIL), 7个冲突事件窗口(373天)。
- **Status**: ❌ 不建议将原油信号纳入黄金交易决策。

## 2026-05-09: 宏观复合风险预警信号 (Macro Composite Risk Signal)
- **Finding (H1)**: "高油价(UKOIL>$95) + 美元走强(USDCHF 20日收益>0)"复合信号对股指期货负收益预测**高度显著**——USTEC 20日窗口 t=-5.70, p<0.001, Cohen's d=-0.778。US500 t=-6.09, p<0.001, d=-0.938。US30 t=-6.03, p<0.001, d=-0.925。
- **Finding (H2)**: 尾部风险预警极其显著——Regime内US500大跌日(>2%)频率是正常期的6.81倍，US30为11.14倍，USTEC为3.45倍(卡方p<0.001)。
- **Finding (H3)**: 单一高油价信号完全不显著(p=0.255)，必须加入美元走强条件才产生统计显著性。印证跨资产关系高度依赖冲突类型。
- **Metric**: 1632个交易日(UKOIL 2020-01至2026-05), 94天复合鹰派Regime(5.8%), 三大股指期货。
- **Status**: ✅ 验证通过。建议为pure-ai-cio添加复合宏观风险预警层(影子模式→启用)。
- **Distinction from prior work**: 前次研究(能源价格冲击)仅用布油>$100单一条件，统计不显著(t=-0.62, p>0.1)。本次加入美元走强条件后提升至p<0.001。

## 2026-05-09: 黄金-白银分化模型 (Gold-Silver Divergence)
- **Finding (H1)**: 复合鹰派 Regime (高油价+美元走强) 下，白银年化收益**落后黄金 63.85%** (vs 正常期 +8.06%)，t=-2.193, p=0.0301。20日窗口检验 p<0.001。单一油价信号不显著 (p=0.4582)。
- **Finding (H2)**: GSR 20日变化与白银未来20日相对收益的相关系数 **r=-0.7566** (p<0.001)，R²=0.5725。五分位分组单调梯度极差 12.06%，t=27.745。GSR动量策略夏普 1.786 (含5bp成本)。
- **Finding (H3)**: 2025年白银跑赢黄金 +36.1% (全年无鹰派信号)，表明鹰派解除后白银均值回归动力强劲。2022年鹰派期白银反而 +6.9%，印证跨资产关系依赖冲突类型。
- **Metric**: 1267个交易日(2019-07至2026-05), XAUUSDm/XAGUSDm/UKOILm/USDCHFm, 94天复合鹰派Regime。
- **Status**: ✅ 验证通过。建议为pure-ai-cio添加GSR动量配对信号层。提案已起草。
- **Distinction from prior work**: 前序研究(v6/v7)聚焦能源价格冲击对股指期货的影响。本研究首次将复合宏观信号应用于贵金属跨品种分析，并发现GSR动量本身是极强的预测因子(r=-0.76)。

## 2026-05-09: 能源价格冲击对股指期货的非对称影响
- **Finding (H1)**: 布油>$100时，三大股指期货年化收益全部转负（USTEC -5.26% vs +25.00%正常, US500 -2.52% vs +18.36%, US30 -4.15% vs +13.53%）。方向一致但统计不显著(t=-0.62, p>0.1, 样本123天)。
- **Finding (H2)**: 2026年美伊冲突期间，原油-股指60日滚动相关跌至极端负值（USTEC -0.68, US500 -0.74），为6年数据最低。但同期股指仍在上涨（USTEC +22.93%）。
- **Finding (H3)**: 风险预警信号（原油20日涨幅>15%减仓至50%）触发频率5.6%，USTEC最大回撤减少1.92个百分点(-30.49%→-28.57%)，夏普基本不变。
- **Metric**: 1611个交易日(2020-02至2026-05), 6品种, 123天高油价期。
- **Status**: ⚠️ 部分成立。建议作为辅助性风险参考层添加到pure-ai-cio策略，提案已起草（能源风险预警层）。仅影响股指期货，不改变黄金/外汇/原油交易逻辑。
