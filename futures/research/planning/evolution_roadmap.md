# 🔮 Research System Evolution Roadmap

**Created**: 2026-05-08  
**Last Updated**: 2026-05-08  
**Status**: Phase A Active

---

## 📋 Executive Summary

This document tracks the evolution of the **Autonomous Research Engine** — the system that discovers, validates, and proposes trading strategy improvements for both Futures and A-Stock markets.

The engine follows a **three-phase evolution path**, moving from a simple single-agent loop to a full parallel research Kanban pipeline. Each phase adds capability while maintaining backward compatibility with existing live trading systems.

### Core Design Philosophy
- **Research is separate from live trading** — all work happens in isolated `experiments/` directories
- **Human gate required** — AI produces proposals, user approves before any rule merges to live strategies
- **Evolution over revolution** — prove value at each phase before adding complexity

---

## 🗺️ Phase Roadmap

### Phase A: Single-Agent Loop (✅ Active)

**Architecture**: Orchestrator → Brief → Single AI Agent → Report/Proposal

```
[Cron Trigger]
    │
    ▼
[Orchestrator] (15s)
    ├── Auto-discover strategies from strategies/{market}/
    ├── Filter news (581 raw → 10 high-signal events)
    ├── Generate real-time market context (trade calendar, sessions)
    ├── Load knowledge base (prevent redundant research)
    ├── Generate briefs/YYYYMMDD_HHMM.md
    └── Initialize experiments/YYYYMMDD_vN_auto/
        ├── report.md (template)
        ├── proposal.md (template)
        ├── backtest.py (from templates/)
        └── status.json
    │
    ▼
[Single AI Agent] (researcher profile)
    ├── Read brief
    ├── Formulate hypothesis
    ├── Write & run Python scripts (MT5/Tushare/News)
    ├── Fill report.md
    ├── Draft proposal.md (if validated)
    └── Update status.json + knowledge_base.md
    │
    ▼
[Human Gate] (QQ/WeChat delivery)
    ├── User reviews proposal
    ├── User replies ✅ (merge) or ❌ (reject)
    └── If ✅: AI merges rule to live strategy skills/
```

**Current Capabilities**:
- ✅ Auto strategy discovery (no hardcoded paths)
- ✅ News dedup + scoring + clustering (581→10 events)
- ✅ Real-time market context (sessions, trade calendar, data freshness warnings)
- ✅ Experiment workspace auto-initialization (report/proposal/backtest templates)
- ✅ Knowledge base (prevents duplicate research)
- ✅ Tool catalog in brief (Python env, data sources, connection info)
- ✅ Cron scheduling (Futures: Sat 09:00, A-Stock: Sat 10:00)

**Known Limitations**:
- ❌ Single agent handles everything → context window crowding
- ❌ Serial execution → data fetching blocks backtesting
- ❌ No cross-validation → same AI does hypothesis, backtest, and report
- ❌ Failure tracking → if MT5 times out, entire run fails
- ❌ No parallel hypothesis testing → one research topic per run
- ❌ Fixed weekly schedule → no ad-hoc research triggers

**When to Move to Phase B**:
- AI consistently produces validated proposals (≥1 per month)
- Single agent starts losing context (forgetting early instructions)
- Need to test multiple hypotheses in one run
- Research runtime consistently exceeds 10 minutes

---

### Phase B: Lightweight Kanban (🟡 Planned — ~3 months)

**Architecture**: Orchestrator → Kanban (T1→T3→T5→T6) → Report/Proposal

```
[Cron Trigger / Manual]
    │
    ▼
[T1: Aggregator]
    ├── Run Orchestrator
    ├── Parse brief into structured research tasks
    └─→ Output: research_task.json
    │
    ▼
[T2: Data Fetcher] (parallel: T2a MT5 + T2b Tushare + T2c News)
    ├── Pull OHLCV from MT5 / Tushare ClickHouse
    ├── Pull event timeline from News Pipeline
    └─→ Output: data/ directory with CSV/JSON
    │
    ▼
[T3: Quant Analyst]
    ├── Read T1 task + T2 data
    ├── Formulate 1-2 hypotheses
    ├── Write Python backtest/stat scripts
    └─→ Output: hypothesis.md + backtest.py
    │
    ▼
[T4: Execution]
    ├── Run backtest.py with Windows Python 3.10
    ├── Run statistical tests (statsmodels)
    └─→ Output: results.json (WR, Sharpe, MaxDD, p-values)
    │
    ▼
[T5: Writer] (parallel: T5a Report + T5b Proposal)
    ├── T5a: Fill report.md with T4 results
    ├── T5b: Draft proposal.md if T4 results significant
    └─→ Output: report.md + proposal.md + updated knowledge_base.md
    │
    ▼
[T6: Quality Review] (independent profile or different model)
    ├── Check sample size adequacy
    ├── Check for overfitting
    ├── Verify not re-discovering known facts
    ├── Validate report format completeness
    └─→ Output: review.md (pass/fail with notes)
    │
    ▼
[Human Gate]
    └── Push report + proposal + review to user
```

**Key Improvements Over Phase A**:
| Feature | Phase A | Phase B |
|---------|---------|---------|
| Parallelism | Serial (1 agent) | T2 parallel data fetch, T5 parallel writing |
| Context | Full brief in one agent | Each node gets only what it needs |
| Quality control | Self-reviewed | Independent T6 reviewer node |
| Failure handling | Entire run fails | Retry individual T-nodes, skip if needed |
| Tracking | status.json only | kanban.db with full T-node audit trail |
| Cost | ~1 model call/run | ~6-8 model calls/run |

**New Components Needed**:
- `kanban/research-kanban.md` — T-node task definitions
- `kanban/scripts/` — T2 data fetcher scripts, T4 execution wrapper
- `profiles/review_agent` — Independent reviewer profile (optional: different model)
- `scripts/cron_to_kanban.py` — Bridge: converts Orchestrator brief into Kanban task queue

**Profile Requirements**:
- `researcher` (existing) — T3 Quant Analyst, T5 Writer
- `data_engineer` (new, lightweight) — T2 Data Fetcher
- `review_agent` (new) — T6 Quality Review

---

### Phase C: Full Research Kanban (🔵 Future — ~6 months)

**Architecture**: Full parallel pipeline with multi-hypothesis support, red-teaming, and ML integration

```
[Cron Trigger / Ad-hoc / Post-close auto]
    │
    ▼
[T1: Aggregator] (enhanced)
    ├── Run Orchestrator
    ├── Parse brief → identify 2-3 research angles
    ├── Cross-reference knowledge base
    └─→ Output: research_tasks.json (multi-topic)
    │
    ▼
[T2: Data Lake] (parallel across all data sources)
    ├── T2a: MT5 OHLCV (all symbols, multiple timeframes)
    ├── T2b: Tushare ClickHouse (167 tables, full history)
    ├── T2c: News Pipeline (event timelines, sentiment scoring)
    ├── T2d: Global Futures (commodity/index correlation data)
    ├── T2e: Trade Logs (live strategy performance analysis)
    └─→ Output: data_lake/ with structured datasets
    │
    ▼
[T3: Hypothesis Engine] (parallel: 2-3 analysts)
    ├── T3a: Technical pattern researcher
    ├── T3b: Macro/event researcher
    ├── T3c: Cross-asset correlation researcher
    └─→ Output: hypotheses/ directory (one per analyst)
    │
    ▼
[T4: Backtest Engine] (parallel per hypothesis)
    ├── Run each hypothesis through backtrader/MT5
    ├── Compute Sharpe, Sortino, MaxDD, WinRate, Calmar
    ├── Run walk-forward optimization
    └─→ Output: backtest_results/ (one per hypothesis)
    │
    ▼
[T5: Synthesis] (parallel: Report + Proposal + Risk Analysis)
    ├── T5a: Consolidate findings into master report
    ├── T5b: Draft proposals for all validated hypotheses
    ├── T5c: Risk analysis (correlation impact, regime dependency)
    └─→ Output: consolidated report + proposals + risk_analysis.md
    │
    ▼
[T6: Red Team] (adversarial review)
    ├── Stress test: "Under what conditions does this fail?"
    ├── Overfitting detection: does it work OOS?
    ├── Regime analysis: does it only work in one market regime?
    ├── Correlation check: does it conflict with existing rules?
    └─→ Output: vulnerability_report.md
    │
    ▼
[T7: Final Review] (human-facing)
    ├── Merge T5 + T6 into decision-ready package
    ├── Generate executive summary (1-page)
    ├── Push to user with ✅/❌/🔍 options
    └─→ Output: final_delivery.md
    │
    ▼
[Human Gate]
    └── User approves → AI merges to live strategy
```

**Phase C Capabilities**:
- Multi-hypothesis parallel research (2-3 topics per run)
- Full data lake construction (all sources, all timeframes)
- Walk-forward optimization and OOS validation
- Adversarial red-teaming (find strategy weaknesses before deployment)
- Regime-aware strategy validation (does it work in trending AND ranging?)
- Correlation impact analysis (new rule vs existing portfolio)
- Executive summary generation (1-page decision document)
- Ad-hoc research triggers (user says "研究一下这个" → immediate Kanban run)
- Post-close auto-trigger (data ready at 22:00 → research starts at 22:15)

**New Components Needed**:
- `kanban/scripts/red_team.py` — adversarial testing framework
- `kanban/scripts/walk_forward.py` — walk-forward optimization
- `kanban/scripts/correlation_check.py` — portfolio impact analysis
- `kanban/scripts/executive_summary.py` — 1-page report generator
- `profiles/red_team` — adversarial reviewer profile
- `profiles/macro_analyst` — macro/event research specialist
- Webhook integration for ad-hoc research triggers

---

## 📊 Decision Matrix: When to Move Phases

| Signal | Phase A → B | Phase B → C |
|--------|:-----------:|:-----------:|
| Proposals per month | ≥ 1 validated | ≥ 2 validated |
| Average research runtime | > 10 min | > 20 min |
| Context loss incidents | ≥ 2 per month | ≥ 3 per month |
| Failed runs (timeout/error) | ≥ 30% | ≥ 20% |
| User wants parallel topics | Yes | Yes |
| Budget for LLM calls | ~¥50/run OK | ~¥200/run OK |

**Move forward when ≥ 3 signals are met.**

---

## 📁 Current File Inventory (Phase A)

```
research/
├── scripts/
│   ├── orchestrator.py          # v2: Brief gen + workspace init
│   └── news_filter.py           # 9-source dedup + scoring
├── briefs/                      # Generated briefs (read-only)
├── experiments/                 # AI workspace folders
├── proposals/                   # Draft proposals pending review
├── templates/
│   ├── backtest_template.py     # Skeleton for AI to fill
│   └── research_prompt.md       # Legacy (replaced by Cron Prompt)
├── knowledge_base.md            # Accumulated validated findings
├── research_cron_prompt.md      # Phase A Cron instructions
├── INDEX.md                     # Experiment tracking
├── README.md                    # Research directory documentation
└── planning/                    # ← This folder
    └── evolution_roadmap.md     # This file
```

---

## 🎯 Next Immediate Actions (Phase A Completion)

- [ ] Run first full research cycle (Cron → Orchestrator → AI → Report → Proposal)
- [ ] Verify AI can produce a valid, testable proposal
- [ ] Test human gate workflow (user reviews → approves → AI merges)
- [ ] Document lessons learned from first few runs
- [ ] Update this roadmap based on real-world performance

---

## 📝 Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-05-08 | Initial roadmap created after system audit | AI + User |
