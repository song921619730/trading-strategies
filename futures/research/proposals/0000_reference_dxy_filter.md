# Proposal 0000: DXY Filter for Gold Trades
## 📌 Status: Reference (Example)
## 🔗 Linked Experiment: `experiments/0000_reference_dxy`

### 🚨 Problem
Gold trades frequently fail when USD Index (DXY) surges unexpectedly during US session.

### 💡 Proposed Rule
Add mandatory check in `skills/risk-rules.md`:
- If DXY H1 trend is strongly UP (slope > threshold), **FORBID** Gold Buy entries.
- Logic: Capital flow from commodities to cash.

### 📊 Expected Impact
- Reduce false breakouts by ~20%.
- Improve Win Rate on Gold longs.

### ✅ Implementation Plan
Update `futures/kanban/macro/skills/risk-rules.md` section "Macro Filters".
