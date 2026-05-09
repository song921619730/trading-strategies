# Proposal 0000: Focus on "Weak-to-Strong" 2-Board Strategy
## 📌 Status: Reference (Example)
## 🔗 Linked Experiment: `experiments/0000_reference_sentiment`

### 🚨 Problem
Current strategy buys random limit-up stocks, leading to low consistency.

### 💡 Proposed Rule
Add strict filter in `a-stock/kanban/screening/skills/selection.md`:
- Only target stocks with **2 consecutive limit-ups** (2 连板).
- Filter: Next day must open > 2% (confirming strength).
- Logic: Market consensus is strongest at 2nd board.

### 📊 Expected Impact
- Increase Win Rate from 45% to 60%+.
- Reduce noise from 1-board "lucky" stocks.

### ✅ Implementation Plan
Update `a-stock/kanban/screening/skills/selection.md` to include "Consecutive Limit-Up" check.
