# 🧪 A-Stock Research Cron Prompt

**Target**: `strategies/a-stock/research/`
**Profile**: `researcher`

## Step 1: Run Orchestrator

```bash
cd strategies/a-stock/research
python3 scripts/orchestrator.py
```

Wait for output like:
```
✅ Brief saved: briefs/20260508_HHMM.md
🧪 Experiment workspace: experiments/20260508_vN_auto/
```

## Step 2: Read the Brief

Open the **latest** `briefs/YYYYMMDD_HHMM.md`. It contains:
- 🕐 **Market Context**: Trading day status, next trading day, Tushare data timing
- 📰 **Filtered News**: 10 high-signal events (deduped + scored from 9 sources)
- 🩺 **Strategy Diagnostics**: Recent Kanban scan summaries
- 📚 **Known Facts**: Previously validated patterns (avoid redundancy)
- 🛠️ **Available Tools**: Tushare ClickHouse (167 tables), News Pipeline, Global Futures, MT5

**Note the Experiment Workspace path** in the Brief header (e.g., `experiments/20260508_v11_auto/`).

## Step 3: Conduct Research

Work **exclusively** inside the experiment workspace folder. The folder already contains:
- `report.md` — Fill in your findings
- `proposal.md` — Draft if you find something actionable
- `backtest.py` — Backtest skeleton (uses Python 3.10 env)
- `README.md` — Experiment info
- `status.json` — Track progress

### Research Workflow
1. **Formulate Hypothesis**: Based on Brief data, what A-stock pattern could be exploited? (limit-up patterns, sector rotation, volume-price divergence, etc.)
2. **Gather Data**: Use Tushare ClickHouse for OHLCV, financials, limit-up lists, moneyflow. Use News Pipeline for event context.
3. **Test**: Write Python scripts to validate.
   - WSL: `python3` for data analysis (pandas, numpy, scipy)
   - Windows Python 3.10: For MT5 cross-market correlation if needed
4. **Document**: Fill in `report.md` with methodology, results, statistical significance.

## Step 4: Deliverables

### Must Complete
- [ ] `report.md` — Research findings with data, methodology, results
- [ ] `status.json` — Update `"status": "completed"`, set `"report_done": true`

### If Validated (edge detected, statistical significance)
- [ ] `proposal.md` — Draft rule for user review
- [ ] Update `status.json` → `"proposal_done": true`
- [ ] Update `knowledge_base.md` — Add key finding (format: `- Date: Finding`)

### If No Edge Found
- [ ] Still complete `report.md` with negative result
- [ ] Update `status.json` → `"status": "no_edge_found"`

## ⚠️ Constraints

- 🚫 **NEVER** modify files outside your experiment folder
- 🚫 **NEVER** modify live Kanban files (`../kanban/`)
- 🚫 **NEVER** re-verify facts already in Knowledge Base
- 🚫 **Tushare data is T-1**: Daily data updates by 22:00 UTC+8. If current time < 22:00, use yesterday's data.
- 🚫 **NO minute-level data**: Only daily/weekly/monthly granularity available

## 🔧 Tool Usage Rules

| Tool | When to Use | How |
|------|------------|-----|
| **Tushare CH** | A-stock OHLCV, financials, limit-up, moneyflow | HTTP API, 167 tables, FINAL keyword required |
| **News Pipeline** | Event context for sector/stock moves | `query?symbol=板块名` |
| **Global Futures** | Global market sentiment (oil, gold, indices) | Local script |
| **MT5** | Cross-market correlation (A-stock vs global) | Windows Python 3.10 env |
| **Tavily** | Supplemental research | Hermes built-in, fallback only |

## 📋 Tushare ClickHouse Key Tables

| Category | Table | Key Fields |
|----------|-------|------------|
| Daily OHLCV | `tushare_stock_daily FINAL` | ts_code, trade_date, open, high, low, close, vol, pct_chg |
| Valuation | `tushare_daily_basic FINAL` | ts_code, trade_date, pe, pb, total_mv, circ_mv, turnover_rate |
| Limit-Up | `tushare_limit_list_d FINAL` | trade_date, ts_code, name, limit_times, fc_ratio |
| Moneyflow | `tushare_moneyflow FINAL` | ts_code, trade_date, buy/sell by order size |
| THS Index | `tushare_ths_daily FINAL` | ths_index daily OHLCV |
| Index Daily | `tushare_index_daily FINAL` | Market index OHLCV |

**Always use `FINAL`** with ClickHouse queries (ReplacingMergeTree dedup).
**Date format**: `YYYYMMDD` string (e.g., `'20260508'`).
**Stock code format**: `000001.SZ` (SZSE), `600000.SH` (SSE), `832000.BJ` (BSE).

---
*Phase A: Human Gate required for any rule changes. AI produces proposals, user approves.*
