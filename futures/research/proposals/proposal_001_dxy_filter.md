# 📜 Proposal 001: DXY Lead Filter for Gold Trades
**Status**: 🟡 Pending Review  
**Linked Experiment**: `experiments/20260508_v1_dxy_lead_lag`  
**Target Strategy**: `futures/kanban/macro`

## 🚨 Problem Statement
Backtest analysis reveals 18% of Gold long entries fail due to unexpected USD strength surges during US session. AI currently lacks macro-context filtering.

## 💡 Proposed Rule
Add **Mandatory Macro Check** in `skills/risk-rules.md` → Section: `Macro Filters`.

### 🔹 Logic
```text
IF (Asset == XAUUSD) AND (Direction == BUY):
    1. Fetch DXY H1 Return (last 2 bars)
    2. IF DXY_Return > +0.25%:
        a. Check Volatility Regime (ATR_H1 > 1.5 * Median_ATR_20)
        b. IF Regime == HIGH_VOL → REJECT Trade (Reason: DXY Surge Risk)
        c. IF Regime == LOW_VOL → ALLOW (Correlation weak)
    3. ELSE → ALLOW (Standard analysis applies)
```

### 🔹 Parameters
| Parameter | Value | Source |
|-----------|-------|--------|
| DXY Return Threshold | `+0.25%` (2H) | CCF Optimization |
| Volatility Multiplier | `1.5x` Median ATR | Regime Filter Test |
| Block Duration | `2 Hours` | Lead-Lag Detection |

## 📊 Expected Impact
- **Win Rate**: +9% (52% → 61%)
- **Max Drawdown**: -12% (avoid USD spike drawdowns)
- **Trade Frequency**: -8% (filter out low-probability setups)

## ✅ Implementation Checklist
- [ ] Update `futures/kanban/macro/skills/risk-rules.md`
- [ ] Add DXY data fetch to `scripts/pre_analyze.py`
- [ ] Update Cron Prompt T6 (Risk Manager) to include DXY check
- [ ] Backtest on 2026-Q2 data (out-of-sample)

## 📝 Reviewer Notes
*Pending user approval. Once approved, AI will auto-merge to live strategy.*
