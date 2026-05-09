# 📊 Futures Research Index

| ID | Topic | Date | Status | Conclusion/Output |
|----|-------|------|--------|-------------------|
| `0000_reference_dxy` | DXY Lead-Lag for Gold | 2026-05-08 | ✅ Validated | DXY 领先黄金 ~2h。提案: 增加 DXY 异动过滤。 |
| `20260508_v3_auto` | 黄金波动率压缩释放 | 2026-05-08 | ✅ Validated | Release 瞬间大波动概率 37.1% vs 基线 20.6% (+80%)。提案: Trade Gate "硬性拦截"改为"寻找突破"。 |
| `20260508_v4_auto` | 跨品种波动率共振 | 2026-05-08 | ✅ Validated | 3+ 品种同步压缩 → 5 日波幅 +129.6%；原油/布油放大 190-253%。提案: 增加 "Sync Compression Alert" 层。 |

## 📈 发现汇总

| # | 发现 | 支持数据 | 实战价值 |
|---|------|----------|----------|
| 1 | **DXY 领先黄金 2h** | 1 年 H1 数据，Granger 因果检验 | 过滤: DXY 异动时暂缓黄金开仓 |
| 2 | **ATR 压缩释放** | 黄金 1 年 H1，Release 概率 +80% | Trade Gate 低波动时不拦截，改寻找突破 |
| 3 | **跨品种共振** | 7 品种 2.5 年日线，3+ sync 波幅 +129.6% | 多品种同步时标记"高置信突破窗口" |

## 🔗 文件索引

- `experiments/0000_reference_dxy/report.md` — DXY 领先黄金研究报告
- `experiments/20260508_v3_auto/report.md` — 黄金波动率压缩报告
- `experiments/20260508_v4_auto/report.md` — 跨品种共振报告
- `proposals/proposal_001_dxy_filter.md` — DXY 过滤提案
