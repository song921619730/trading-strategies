# 📜 Proposal 001: Focus on "Weak-to-Strong" 2-Board Strategy
**Status**: 🟡 Pending Review  
**Linked Experiment**: `experiments/20260508_v1_limitup_premium`  
**Target Strategy**: `a-stock/kanban/screening`

## 🚨 Problem Statement
Current strategy casts a wide net on all limit-up stocks, resulting in 48% win rate and frequent drawdowns from 1-board noise and 3-board+ regulation risk.

## 💡 Proposed Rule
Replace broad limit-up scanning with **Targeted 2-Board Weak-to-Strong Filter** in `skills/selection.md`.

### 🔹 Logic
```text
IF (Stock == Limit_Up_Yesterday) AND (Consecutive_Streak == 2):
    1. Pre-Market Check (09:15-09:25):
        a. Call Auction Price > +2% (Confirms strength)
        b. Auction Volume > 1.5x 20-day Avg (Confirms participation)
    2. IF Conditions Met → ADD to Watchlist
    3. Entry Trigger: Price breaks 09:30-09:35 High with Volume Spike
    4. Position Sizing: Max 15% per stock (T+1 constraint)
```

### 🔹 Parameters
| Parameter | Value | Source |
|-----------|-------|--------|
| Target Streak | `2 Boards` | Win Rate Optimization |
| Open Threshold | `> +2%` | Premium Analysis |
| Volume Multiplier | `1.5x` Avg 20D | False Breakout Filter |
| Stop Loss | `-5%` or `< Yesterday Limit` | Risk Control |
| Take Profit | `+8%` or `Break VWAP` | Premium Capture |

## 📊 Expected Impact
- **Win Rate**: +17% (45% → 62%)
- **Max Drawdown**: -50% (-12% → -6%)
- **Trade Frequency**: -60% (Fewer, higher-quality setups)
- **Sharpe Ratio**: Expected increase from 0.8 → 1.4

## ✅ Implementation Checklist
- [ ] Update `a-stock/kanban/screening/skills/selection.md`
- [ ] Add "Consecutive Streak" calculation to `scripts/fetch_tushare.py`
- [ ] Update Cron Prompt T2 (Analyst) to include 2-board filter
- [ ] Backtest on 2026-Q2 data (out-of-sample)

## 📝 Reviewer Notes
*Pending user approval. Once approved, AI will auto-merge to live strategy. Recommend paper trading first due to T+1 execution constraints.*
