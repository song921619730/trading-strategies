# 📜 Proposal: Volatility Release Filter

**Status**: 🟡 Draft
**Linked Experiment**: `experiments/20260508_v3_auto`
**Target Strategy**: `futures/single-agent/pure-ai-cio` (Trade Gate)

## 🚨 Problem Statement

The Pure AI CIO Trade Gate currently filters out setups when volatility is "extremely low" (e.g., < 70% daily average).
Research shows this blocks 10/12 symbols and misses the "Volatility Release" phase, which has a **37.1% probability** of a significant directional move (vs 20.6% normal).

## 💡 Proposed Rule Modification

**Modify Trade Gate Logic:**

Instead of a hard block:
```python
# OLD
if atr_ratio < 0.7:
    return BLOCK (Reason: Low Volatility)
```

Use a state-aware approach:
```python
# NEW
if atr_ratio < 0.7:
    # Check if we are in a RELEASE phase (crossing up from compression)
    if prev_atr_ratio < 0.7 and current_atr_ratio > 0.7:
        return ALLOW_PRIORITY (Reason: Volatility Release)
    else:
        return ALLOW_CONDITIONAL (Reason: Compression - look for Breakout only)
```

**Entry Criteria Adjustment**:
During Compression/Release:
*   Allow Breakout entries (Price > 4H High / Price < 4H Low).
*   Reject Mean Reversion entries (fading the move).

## 📊 Expected Impact

| Metric | Current (Blocked) | Proposed (Active) | Source |
|--------|-------------------|-------------------|--------|
| Opportunities | 0 during compression | High probability release setups | Backtest |
| Win Rate (Release) | N/A | ~37% (Big moves) | Experiment |
| Missed Trends | High | Low | Logic |

## 📋 Implementation Checklist

- [ ] Update `active_cron_prompt.md` (Trade Gate section)
- [ ] Update `scripts/pre_analyze.py` to calculate `atr_ratio`
- [ ] Backtest on 2026 Q1 data (OOS)
- [ ] User review
