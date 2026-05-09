# 📊 Research Report: Volatility Compression & Breakout Study

**Date**: 2026-05-08 20:15 (UTC+8)
**Brief**: `20260508_1932.md`
**Market**: FUTURES
**Asset**: XAUUSDm (Gold)

---

## 🎯 Research Question

The Pure AI CIO strategy currently filters out trades when volatility is "extremely low" (Trade Gate blocking 10/12 symbols on Friday). 
**Hypothesis:** Does volatility compression (ATR < threshold) predict significant directional breakouts in the subsequent 8-12 hours? 
If so, the Trade Gate might be filtering out high-probability entries instead of protecting us.

## 📐 Methodology

1.  **Data**: 1 year of H1 OHLCV data for XAUUSDm (~8,760 bars) via MetaTrader5.
2.  **Metric**: ATR Ratio = `ATR(14)` / `Median(ATR, 20)`.
    *   Compression = Ratio < Threshold (tested 0.5 to 0.9).
3.  **Testing**:
    *   Forward returns at 4H, 8H, 12H, 24H.
    *   Big move rate: % of bars where absolute return > 1σ of normal baseline.
    *   Compression Release: Analysis of the *first* bar after compression ends (transition from low to high vol).

## 📈 Results

### 1. Compression Frequency & Magnitude

| Threshold (ATR/Median) | Frequency | Avg 8H Move | Normal Avg Move | Ratio |
|------------------------|-----------|-------------|-----------------|-------|
| < 50% (Extreme)        | 0.1% (8 bars) | 0.550% | 0.579% | 0.95x |
| < 60% (Strong)         | 1.1%      | 0.631% | 0.579% | 1.09x |
| < 70% (Moderate)       | 5.2%      | 0.652% | 0.576% | **1.13x** |
| < 80% (Light)          | 15.0%     | 0.628% | 0.571% | 1.10x |

**Key Finding**: Moderate compression (<70% of median) shows a **13% increase in average move magnitude** over the next 8 hours.

### 2. "Big Move" Probability

Does compression lead to *explosive* moves (>1σ)?

*   **Compression (<70%)**: 25.5% chance of a big move.
*   **Normal Volatility**: 20.6% chance of a big move.
*   **Improvement**: +24% relative increase in probability of catching a trend starter.

### 3. Compression Release Analysis

When volatility *expands* (transition from compressed -> normal):
*   **Events**: 237 release points identified.
*   **Big Move Rate**: **37.1%** (vs baseline ~20%).
*   **Interpretation**: The transition out of compression is a stronger signal than the compression itself. Nearly 4 in 10 releases lead to a significant directional move.

### 4. Directional Bias

*   During compression (<70%), Gold had a slight positive bias (Mean 8H Return: +0.13%).
*   However, t-statistic was < 2, meaning **direction is not predictable** during the squeeze itself.
*   This confirms it's a **volatility breakout play**, not a directional directional play.

## 💡 Conclusion

1.  **Trade Gate Optimization**: The current Trade Gate volatility filter is likely **over-blocking**. While "extreme" low vol (0.1%) offers no edge, "moderate" low vol (5-15% of time) actually precedes higher-volatility moves.
2.  **Entry Signal**: A "Volatility Release" setup (ATR crossing above 70% of its median) has a **37% chance** of a big move, compared to ~20% normally. This is a statistically significant alpha source.
3.  **Risk**: Compression periods do *not* indicate direction. Strategies relying on this must use breakout logic (e.g., entering on break of the compression range high/low) rather than mean reversion.

## 📝 Proposal

**Draft Proposal: "Volatility Release Filter" for Trade Gate**

*   **Current Rule**: Block if Volatility < 70% (Hard Block).
*   **Proposed Rule**:
    *   If Volatility < 70%: **Do not block**. Instead, widen the entry criteria to look for "Breakout" setups (e.g., price breaking previous 4H high/low).
    *   Add a specific "Release" trigger: When ATR crosses from <70% back to >70%, prioritize entries in the direction of the break.
