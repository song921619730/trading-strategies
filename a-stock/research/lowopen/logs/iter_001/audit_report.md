# Iteration 001: L1 Refinement - Audit Report

**Generated**: 2026-05-11T00:06 UTC+8
**Data Range**: 2024-01-01 to 2026-05-08
**Data Layers**: L1 (daily + daily_basic)
**Stocks**: 5,599

## Summary

Tested 144 refined parameter combinations. Results confirm L1 parameters have limited discriminatory power.

### Key Results

**Best (pe_max=20, turnover=1.0, vol_ratio=1.0)**:
- 5D Return: 5.83% | WR: 64.67% | Sharpe: 3.03 | Signals: 23,018

**Previous Best (pe_max=30, turnover=5.0)**:
- 5D Return: 5.76% | WR: 61.18% | Sharpe: 2.75 | Signals: 17,643

### Critical Finding: L1 Saturation

ALL parameter combinations produce nearly identical 5D returns (5.58% - 5.83%). The base rule itself (5% intraday gain + next_close >= close) is the dominant factor. L1 filters mainly affect signal count, not return quality.

| Filter Range | Signal Count Range | 5D Return Range |
|-------------|-------------------|-----------------|
| All combos | 6,576 - 23,589 | 5.58% - 5.83% |
| vol_ratio=1.0 | 18,311 - 23,589 | 5.73% - 5.83% |
| vol_ratio=1.5 | 6,576 - 9,224 | 5.58% - 5.72% |

**Implication**: Volume ratio > 1.0 reduces signal count by 60% but only drops return by 0.1%. Not worth the trade-off.

### Improvements Over Iteration 000

| Metric | Iter 000 | Iter 001 | Change |
|--------|----------|----------|--------|
| Best 5D Return | 5.76% | 5.83% | +0.07% |
| Win Rate | 61.18% | 64.67% | +3.49% |
| Sharpe | 2.75 | 3.03 | +0.28 |
| Signal Count | 17,643 | 23,018 | +5,375 |

Marginal improvement (+0.07%) — below the 0.3% fatigue threshold.

## Fatigue Assessment

- Fatigue count: 0 → 1 (improvement < 0.3%)
- 2nd consecutive failure needed to increment again

## Next Steps

**Option A**: Try more creative L1 parameters (e.g., pct_chg range, vol filters, combined conditions)
**Option B**: **Unlock L2** (moneyflow data) — more promising for discrimination
**Option C**: Test the current best params with a walk-forward split to validate robustness

**Recommendation**: **Option B**. L1 is saturated for this base rule. Money flow data (buy_sm_vol, sell_lg_vol, net_mf_vol) can tell us whether the intraday surge is retail-driven or institution-driven, which should differentiate future performance.
