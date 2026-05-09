# 🧪 Futures Research Cron Prompt

**Target**: `strategies/futures/research/`
**Profile**: `researcher`

## Step 1: Run Orchestrator

```bash
cd strategies/futures/research
python3 scripts/orchestrator.py
```

Wait for output like:
```
✅ Brief saved: briefs/20260508_HHMM.md
🧪 Experiment workspace: experiments/20260508_vN_auto/
```

## Step 2: Read the Brief

Open the **latest** `briefs/YYYYMMDD_HHMM.md`. It contains:
- 🕐 **Market Context**: Real-time trading session, trade calendar
- 📰 **Filtered News**: 10 high-signal events (deduped + scored)
- 🩺 **Strategy Diagnostics**: Recent scan summaries from active strategies
- 📚 **Known Facts**: Previously validated patterns (avoid redundancy)
- 🛠️ **Available Tools**: Tushare ClickHouse, MT5, News Pipeline, Global Futures

**Note the Experiment Workspace path** in the Brief header (e.g., `experiments/20260508_v10_auto/`).

## Step 3: Conduct Research

Work **exclusively** inside the experiment workspace folder. The folder already contains:
- `report.md` — Fill in your findings
- `proposal.md` — Draft if you find something actionable
- `backtest.py` — Backtest skeleton (uses Python 3.10 env)
- `README.md` — Experiment info
- `status.json` — Track progress

### Research Workflow
1. **Formulate Hypothesis**: Based on Brief data, what pattern/inefficiency could be exploited?
2. **Gather Data**: Use tools listed in Brief (MT5 for futures OHLCV, News Pipeline for event context, etc.)
3. **Test**: Write Python scripts to validate. Use `C:\Users\gj\AppData\Local\Programs\Python\Python310\python.exe` for Windows tools (MT5, backtrader).
4. **Document**: Fill in `report.md` with methodology, results, statistical significance.

## Step 4: Deliverables

### Must Complete
- [ ] `report.md` — Research findings with data, methodology, results
- [ ] `status.json` — Update `"status": "completed"`, set `"report_done": true`

### If Validated (Win Rate improvement, edge detected, etc.)
- [ ] `proposal.md` — Draft rule for user review
- [ ] Update `status.json` → `"proposal_done": true`
- [ ] Update `knowledge_base.md` — Add key finding (format: `- Date: Finding`)

### If No Edge Found
- [ ] Still complete `report.md` with negative result
- [ ] Update `status.json` → `"status": "no_edge_found"`

## ⚠️ Constraints

- 🚫 **NEVER** modify files outside your experiment folder
- 🚫 **NEVER** modify live strategy files (`../single-agent/`, `../kanban/`)
- 🚫 **NEVER** re-verify facts already in Knowledge Base
- 🚫 **NEVER** execute trades or change MT5 positions
- 🚫 **NEVER** pull all 600 raw news items — use the filtered summary in Brief

## 🔧 Tool Usage Rules

| Tool | When to Use | How |
|------|------------|-----|
| **MT5** | Futures OHLCV, positions, account | Windows Python 3.10 env |
| **Tushare CH** | Macro data, forex, futures history | HTTP API at 172.24.224.1:8123 |
| **News Pipeline** | Event context verification | `query?symbol=X` for specific events |
| **Global Futures** | Commodity/index history (Yahoo) | Local script, no API key needed |
| **Tavily** | Supplemental research | Hermes built-in, fallback only |

---
*Phase A: Human Gate required for any rule changes. AI produces proposals, user approves.*
