---
name: intraday-framework
version: 1.0.0
profile: Analyst
label: Intraday Hypothesis Testing & Interpretation Framework
description: >
  The core Analyst skill. Guides the AI to consume Researcher's structured data,
  formulate and test hypotheses via grid_engine, interpret aggregate statistics,
  manage the hypothesis queue, and converge on exhausted topics with a final report.
inputs:
  - state/research_state.json       # hypothesis queue, best_findings, fatigue counter
  - Researcher data summary table   # printed by data-mt5 workflow
  - grid_engine.py                  # run_grid(config) → aggregate stats
outputs:
  - updated research_state.json     # tested hypotheses, new hypotheses, findings
  - best_findings entries           # win_rate > 60% signals added to state
  - convergence decision            # fatigue counter → final report
dependencies:
  - skills/data-mt5.md              # Researcher profile — data loading & enrichment
  - scripts/grid_engine.py          # run_grid() — entry condition evaluation
  - scripts/data_loader.py          # compute_indicators() — column reference
  - state/research_state.json       # persistent queue & findings storage
---

# intraday-framework — Analyst: Hypothesis Testing & Interpretation

## Role

You are the **Analyst** profile. Your job is to **think like a quant researcher**:

1. **Consume** the structured data summary produced by the Researcher (the printed
   table showing symbols, row counts, date ranges, and available indicator columns).

2. **Formulate** precise, testable hypotheses about intraday patterns in futures
   markets — drawing from a systematic set of research dimensions.

3. **Test** those hypotheses by constructing `entry_condition` strings, calling
   `run_grid()` via the terminal, and collecting aggregate statistics.

4. **Interpret** the results: distinguish genuine signals from noise, decide
   whether to reverse direction, and identify parameter ranges that work.

5. **Generate** new hypotheses based on what you learned, and manage the hypothesis
   queue so no idea is left untested.

6. **Converge** — when a dimension is exhausted (fatigue accumulates), stop,
   generate a final report of best findings, and signal readiness for a new topic.

> **Golden rule:** Every hypothesis must be falsifiable. If you cannot construct
> an `entry_condition` string that captures the idea, the idea is not ready for
> testing. Refine it until it is.

---

## 1. Research Dimensions to Explore

Intraday pattern research is vast. To avoid wandering, you systematically explore
the following **dimensions**. Each dimension is a family of related hypotheses.
Within each dimension, you vary parameters (thresholds, windows, symbols) to
find the most robust signals.

### 1.1 Time Patterns

The futures market is not homogeneous across time. Certain hours, days, or
trading sessions exhibit predictable tendencies.

**Concrete hypotheses to test:**

| Hypothesis | `entry_condition` example | Notes |
|---|---|---|
| First hour of London open shows directional bias | `hour == 8 and dayofweek <= 4` | 08:00 UTC = London cash open |
| Tuesday/Friday mean-reversion after Monday | `dayofweek == 1 and pct_chg < -0.5 * atr14/close` | Monday was down → Tuesday reversal? |
| Asia session range breakout into Europe | `session == 'asia' and (high - low) / close < 0.3 * atr14/close` | Low-volatility Asia → breakout |
| Last hour of US session (20:00-21:00 UTC) | `hour == 20 and session == 'us'` | End-of-day positioning |
| Monday gap continuation/ fade | `dayofweek == 0 and abs(gap_pct) > 0.001` | Gap > 0.1% → direction? |

**How to iterate:**
- Start with session-level filters (`session == 'asia'`), then drill to specific
  hours (`hour == 3`).
- Cross with day of week to find day-specific asymmetries.
- Test both long and short directions for each time window.

### 1.2 Momentum

Momentum effects — trend continuation or exhaustion — are among the most
studied patterns. You test both **continuation** and **reversal** hypotheses.

**Concrete hypotheses:**

| Hypothesis | `entry_condition` example | Logic |
|---|---|---|
| Consecutive bullish candles → continuation | `consecutive_bull_count >= 3` | 3+ green candles → buy |
| Consecutive bearish candles → bounce | `consecutive_bear_count >= 4 and rsi14 < 30` | 4+ red candles + oversold → reversal long |
| Gap-and-go | `gap_pct > 0.002 and close > open` | Bullish gap + bullish open → continuation |
| Gap fade | `gap_pct > 0.003 and rsi14 > 70` | Large gap + overbought → fade short |
| Inside bar breakout | `high <= prev_high and low >= prev_low` | Inside bar → breakout next candle |

**How to iterate:**
- Vary the consecutive-count threshold (2, 3, 4, 5).
- Add RSI or ATR filters to see if the pattern strengthens in overbought/oversold
  or high/low volatility regimes.
- Test both continuation (trade with the momentum) and reversal (trade against
  extreme momentum) on the same condition.

### 1.3 Volatility

Volatility regimes dramatically affect the probability and magnitude of
directional moves. You use ATR percentile and Bollinger Band position to
define regimes.

**Concrete hypotheses:**

| Hypothesis | `entry_condition` example | Logic |
|---|---|---|
| Low volatility breakout | `atr14 < ma(atr14, 100)` | Volatility below 100-period MA → expansion expected |
| High volatility exhaustion | `atr14 > ma(atr14, 100) * 1.5` | Volatility spike → mean reversion |
| Bollinger Band touch — mean reversion | `close > bb_upper and rsi14 > 70` | Touch upper band + overbought → short |
| Bollinger Band squeeze | `(bb_upper - bb_lower) / ma20 < 0.05` | Narrow bands → breakout coming |
| ATR percentile (requires precomputation) | `atr14 / close > 0.01` | ATR > 1% of price → high vol regime |

**How to iterate:**
- Combine volatility with time: "low volatility during Asia session" is a
  narrower (and potentially stronger) filter than either alone.
- Test volatility-adaptive thresholds: use `atr14` to normalise price moves
  (e.g., `pct_chg > 0.5 * atr14 / close` for a "half-ATR" move).

### 1.4 Multi-Symbol / Cross-Asset

Futures interact. Correlations are time-varying, but certain lead-lag
relationships are structural (e.g., USDJPY → Nikkei, Gold → Silver).

**Concrete hypotheses:**

| Hypothesis | Approach | Grid config |
|---|---|---|
| EURUSD → USDJPY: EUR strength leads JPY weakness | Load both, test `entry_condition` on EURUSD, measure returns on USDJPY | `symbols: ["EURUSDm", "USDJPYm"]` |
| Gold → Silver: XAU moves lead XAG | Entry on XAU, returns on XAG | `symbols: ["XAUUSDm", "XAGUSDm"]` |
| US500 → US30: Index leader-follower | Entry on US500, returns on US30 | `symbols: ["US500m", "US30m"]` |
| Oil → CAD: USOIL moves affect USDCHF | Entry on USOIL, returns on USDCHF | `symbols: ["USOILm", "USDCHFm"]` |
| Same-direction confirmation | `close > ma20 and close > open` (same entry across correlated symbols) | Cross-symbol |

**How to iterate:**
- The grid engine runs the *same* `entry_condition` on *each* symbol independently
  and reports per-symbol results. Use this to compare: does a pattern work on
  XAUUSD but not XAGUSD? That is a finding.
- For true cross-symbol entry (enter symbol A based on symbol B's data), you
  need a custom script. For now, use the univariate approach: hypothesise that
  the pattern works on multiple symbols, and look for leader/follower via
  comparing win rates.

### 1.5 Daily (D1) Context

Intraday patterns do not exist in a vacuum. The daily trend, daily volatility,
and daily support/resistance levels provide context that can dramatically
change the reliability of intraday signals.

**Concrete hypotheses:**

| Hypothesis | `entry_condition` example | Logic |
|---|---|---|
| Above MA200 → buy dips | `close > ma200 and rsi14 < 40` | Bullish D1 trend, buy pullbacks |
| Below MA200 → sell rallies | `close < ma200 and rsi14 > 60` | Bearish D1 trend, sell strength |
| D1 trend + session confluence | `close > ma200 and session == 'europe' and hour == 8` | Bullish D1 + London open |
| D1 breakout day | `close > prev_high and hour > 1` | Price above previous day high → continuation |
| D1 range mean reversion | `close < prev_low and rsi14 < 25` | Price below previous day low → bounce |

**How to iterate:**
- The `ma200`, `ma50`, and `ma20` columns are computed from the intraday data
  and serve as proxies for D1 trend when enough bars are available (~200 hours
  ≈ 8 trading days).
- For true daily context (daily OHLC), use `resample_to_daily()` from
  `data_loader.py` to get daily bars, then merge back. The grid engine's
  `entry_condition` can reference daily-derived columns if you precompute them.
- Test combinations: D1 trend filter + time filter + momentum filter. Each
  additional filter reduces signal count but may improve win rate.

---

## 2. Hypothesis Testing Workflow

Each research round follows a strict workflow. Do not skip steps.

```
   ┌─────────────────────────────────────────────────────┐
   │  Step 1: Pick or generate 1 hypothesis              │
   │         ↓                                           │
   │  Step 2: Construct entry_condition string            │
   │         ↓                                           │
   │  Step 3: Call run_grid() via terminal               │
   │         ↓                                           │
   │  Step 4: Read & interpret results                   │
   │         ↓                                           │
   │  Step 5: Record in research_state.json              │
   │         ↓                                           │
   │  Step 6: Generate next hypothesis(es)               │
   │         ↓                                           │
   │  Step 7: Check convergence (fatigue)                │
   └─────────────────────────────────────────────────────┘
```

### Step 1 — Pick a Hypothesis from the Queue

Read `state/research_state.json`. The `hypothesis_queue` contains hypotheses
with a `status` field (`"pending"`, `"in_progress"`, or `"tested"`).

**Rules:**
- Always pick a `"pending"` hypothesis first (FIFO within same priority).
- If no pending hypotheses remain but there are `"tested"` ones, review them.
  Generate new hypotheses based on what was learned (see Section 6).
- If the queue is completely empty, generate at least 3 new hypotheses from the
  dimensions in Section 1 before proceeding.

### Step 2 — Construct the `entry_condition` String

Translate the natural-language hypothesis into a Python expression that
`pandas.DataFrame.eval()` can execute.

**Available columns** (from `compute_indicators()`):

```
open, high, low, close, tick_volume, spread, real_volume,
atr14, rsi14, ma20, ma50, ma200,
bb_upper, bb_lower,
pct_chg, gap_pct,
hour, dayofweek, session,
consecutive_bull_count, consecutive_bear_count
```

**Rules for constructing conditions:**
- Use only column names and operators that `eval()` supports: `+`, `-`, `*`,
  `/`, `>`, `<`, `>=`, `<=`, `==`, `!=`, `&`, `|`, `~`, `and`, `or`, `not`.
- Parentheses are supported and **strongly encouraged** for complex conditions.
- Do **not** use `if/else`, `lambda`, or function calls unless they are defined
  in the eval namespace (they are not by default).
- Boolean conditions: `session == 'asia'` works because `session` is a string
  column. `dayofweek == 1` works (Tuesday, since 0=Monday).

**Examples of good `entry_condition` strings:**

```python
# Simple: RSI oversold bounce
"rsi14 < 30"

# Compound: London open + pullback in uptrend
"session == 'europe' and hour == 8 and close > ma20 and rsi14 < 45"

# Momentum + volatility: 3 bearish candles + low ATR
"consecutive_bear_count >= 3 and atr14 / close < 0.008"

# Multi-condition with parentheses
"(close > bb_lower) and (rsi14 < 35) and (consecutive_bear_count >= 2)"
```

**Before proceeding, validate your condition mentally:**
1. Would it have generated trades? (If it's too narrow, `signal_count` will be 0.)
2. Is it unambiguous? (e.g., `rsi14 < 30 or rsi14 > 70` — which direction are
   we trading?)
3. Does the condition leak future information? (e.g., using the closing price
   of the same candle to decide to enter — acceptable for backtesting, but the
   entry is at the close of that candle.)

### Step 3 — Call `run_grid()` via Terminal

From the `scripts/` directory, run an interactive Python session or a script
that calls `run_grid()`.

**Standard invocation pattern:**

```python
cd /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/scripts

python3 << 'EOF'
from grid_engine import run_grid
from pprint import pprint

config = {
    "timeframe": "H1",
    "symbols": ["XAUUSDm", "EURUSDm", "USDJPYm", "GBPUSDm", "US500m"],
    "entry_condition": "rsi14 < 30 and close > ma20",
    "direction": "long",
    "hold_periods": [1, 3, 5, 10],
    "exit_at_close": True,
}

results = run_grid(config)
# Print results per symbol
meta = results.pop("_meta", {})
print(f"\nConfig: {meta.get('config', {}).get('entry_condition', '?')}")
print(f"Direction: {meta.get('config', {}).get('direction', '?')}")
print(f"Symbols with signals: {meta.get('symbols_with_signals', 0)} / {meta.get('total_symbols', 0)}")
print()
for sym, sym_res in sorted(results.items()):
    for hp in sorted(sym_res.keys(), key=int):
        s = sym_res[hp]
        cnt = s.get("signal_count", 0)
        if cnt == 0:
            continue
        wr = s.get("win_rate", 0) or 0
        avg = s.get("avg_return", 0) or 0
        sharpe = s.get("sharpe_ratio", 0) or 0
        dd = s.get("max_drawdown", 0) or 0
        print(f"  {sym:<12} hold={hp:>2}  n={cnt:>4}  wr={wr:>6.2%}  avg={avg:>+7.4f}  sharpe={sharpe:>6.2f}  dd={dd:>7.4f}")
EOF
```

**Important:** Always set `symbols` explicitly to the subset you care about.
Testing all 14 symbols on every run is fine, but if you are testing a
time-specific hypothesis (e.g., London open), you may only want FX symbols.

**Quick tip:** To avoid re-typing, save your runner scripts as
`scripts/analyst_run_001.py`, `scripts/analyst_run_002.py`, etc. But for
ad-hoc exploration, the heredoc pattern above is fastest.

### Step 4 — Read & Interpret Results

The `run_grid()` output gives you per-symbol, per-holding-period statistics.
Your job is to extract meaning from these numbers.

**For each (symbol, hold_period) pair, you get:**

| Field | Meaning |
|---|---|
| `signal_count` | Number of times the entry condition triggered |
| `avg_return` | Mean return per trade (decimal, e.g. 0.005 = 0.5%) |
| `win_rate` | Proportion of trades with positive return |
| `sharpe_ratio` | Annualised risk-adjusted return (roughly) |
| `max_drawdown` | Maximum peak-to-trough decline in equity curve |

**Interpretation rules** (apply strictly):

```
signal_count < 30  →  "too few samples" — mark as INCONCLUSIVE
                       (even if win_rate is high, it's not reliable)

win_rate > 55%     →  "promising" — note the parameters in research_state.json
                       under promising_findings. Consider further refinement.

win_rate > 60%     →  "strong signal" — add to best_findings in research_state.json.
                       This is a candidate for further validation or strategy inclusion.

win_rate < 50% AND
directional accuracy > 0  →  "reverse direction might work"
                       Example: if entry_condition="rsi14<30" with direction="long"
                       yields win_rate=42%, the same condition with direction="short"
                       might yield ~58%. Always note the reverse potential.

avg_return < 0.001  →  "economic significance low"
                       Even with high win rate, if average return per trade is
                       smaller than transaction costs, it's not tradeable.
```

**Context matters:**
- A win rate of 58% on EURUSDm with 200 signals is more meaningful than
  62% on HK50m with 35 signals. Sample size is your first check.
- Sharpe > 1.0 on the primary hold period is strong. Sharpe > 2.0 is rare
  and warrants immediate attention.
- Compare across symbols: if the pattern works on 5 of 5 FX symbols but not
  on indices or commodities, that is itself a finding.
- Compare across holding periods: a pattern that works on `hold=1` but
  reverses on `hold=5` suggests short-term momentum followed by mean reversion
  — a finding worth reporting.

---

## 3. Convergence Decision

Not every dimension yields usable signals. You must recognise when a research
thread is exhausted and move on.

**Fatigue mechanism:**

```
fatigue starts at 0.

Every round where NO new finding is made:
   if 3+ consecutive rounds without a finding → fatigue += 1

If fatigue >= 5 → mark this topic as EXHAUSTED
                   generate a final report
                   set research_state.json → status: "converged"
                   ready for new topic
```

**What counts as a "new finding":**
- A condition that achieves `win_rate > 55%` on at least one symbol with
  `signal_count >= 30`.
- A confirmed reverse-direction finding (`current_direction_win < 50%`
  and `reverse_win > 55%` in a subsequent test).
- A negative finding that is interesting: "Pattern X does NOT work on any
  symbol across hold periods 1-10" — this is still a finding if it was unclear
  before. Report it as "dimension tested, no signal found."
- A cross-symbol pattern: "Works on EURUSD/GBPUSD/USDJPY but not on XAUUSD."

**What does NOT count as a new finding:**
- Trivial variations: testing `rsi14 < 30` then `rsi14 < 29` then `rsi14 < 31`
  — unless the threshold dramatically changes win rate.
- Re-testing the same hypothesis on a different timeframe just to increase the
  count (M30 vs H1 is a valid check, but doing both in the same round is one
  finding, not two).
- Results with `signal_count < 30` (inconclusive by definition).

**When fatigue triggers:**
```
Round 1:  test hypothesis   → win_rate=48%, no finding
Round 2:  test hypothesis   → win_rate=52%, no finding
Round 3:  test hypothesis   → win_rate=44%, no finding
          → 3 consecutive rounds with no finding → fatigue += 1

Round 4:  test hypothesis   → win_rate=51%, no finding
          → still 3+ consecutive without a finding? yes (rounds 2,3,4 all no)
          → fatigue += 1

... fatigue accumulates until >= 5, then converge.
```

> **Note:** A finding resets the "consecutive rounds without finding" counter.
> Fatigue itself does not reset — it accumulates across the entire research
> session for this topic. If you have 2 fatigue points and make a finding,
> fatigue stays at 2 (but the consecutive counter resets to 0).

**Final report format (when converged):**

When `fatigue >= 5`, generate a structured summary:

```markdown
## Convergence Report — {topic}

### Summary
- **Total hypotheses tested:** {number}
- **Rounds executed:** {number}
- **Strongest signals found:** {count}

### Best Findings
| # | Hypothesis | Symbol | Hold | Win Rate | Avg Return | Sharpe |
|---|------------|--------|------|----------|------------|--------|
| 1 | {condition}| {sym}  | {hp} | {wr}     | {avg}      | {sharpe}|

### Dimensions Explored
- Time patterns: [summary of what was tested and results]
- Momentum: [summary]
- Volatility: [summary]
- Multi-symbol: [summary]
- D1 context: [summary]

### Exhausted Dimensions (no signal found)
- {dimension}: {tested conditions}

### Next Research Directions
- {suggestion 1}
- {suggestion 2}
```

---

## 4. Hypothesis Queue Management

The `hypothesis_queue` in `research_state.json` is the persistent backlog.
It is your responsibility to keep it healthy.

### After Testing a Hypothesis

Update its status and attach results:

```json
{
  "id": "init_001",
  "hypothesis": "开盘后第1根H1/M30的方向延续性",
  "status": "tested",
  "created_at": "2026-05-11",
  "tested_at": "2026-05-11",
  "priority": 1,
  "result": {
    "verdict": "promising",
    "best_params": {
      "timeframe": "H1",
      "symbols": ["XAUUSDm", "EURUSDm", "USDJPYm"],
      "direction": "long",
      "hold_period": 3,
      "win_rate": 0.57,
      "signal_count": 142
    },
    "summary": "First-hour continuation works on FX pairs with ~57% win rate (hold=3). Reversal pattern not confirmed."
  }
}
```

**Verdict options:** `"promising"` (55-60%), `"strong"` (>60%), `"inconclusive"`
(<30 signals), `"no_signal"` (0 signals across all symbols), `"reversal_possible"`
(win_rate < 50%).

### Generating New Hypotheses

After each test, generate follow-up hypotheses. Use these **generation patterns**:

| What happened | New hypothesis to generate |
|---|---|
| Entry condition worked on FX but not indices | "Does this pattern work on individual index symbols with adjusted thresholds?" |
| Win rate was good but signal count was low | "Relax one filter to increase frequency: lower the RSI threshold from 30 to 35." |
| Win rate was weak but reverse was untested | "Test the reverse direction with the same entry condition." |
| Pattern worked on H1 but M30 not tested | "Replicate on M30 timeframe." |
| Pattern worked at hold=5 but not hold=1 | "The pattern is medium-term, not scalping. Test longer holds (8, 13, 21)." |
| No pattern found at all in this dimension | "Mark dimension as exhausted. Move to next dimension." |

**Prioritisation rules for the queue:**
1. Untested hypotheses (`status: "pending"`) rank above everything else.
2. Among pending hypotheses, lower `priority` number = higher urgency.
3. After testing, if the result was `"promising"` or `"strong"`, generate 1-2
   refinement hypotheses and add them with `priority: 1` (high).
4. After a `"no_signal"` result, add variants with different parameter ranges
   at `priority: 2` (medium), then plan to move to the next dimension if
   those also fail.
5. If the queue grows beyond 15 items, cull: remove duplicates, merge similar
   ideas, and drop low-priority items that have been superseded.

### Recording Best Findings

When a hypothesis achieves `win_rate > 60%` with `signal_count >= 30`:

```json
{
  "id": "finding_001",
  "hypothesis": "RSI < 30 + close > MA20 on H1 for XAUUSD",
  "entry_condition": "rsi14 < 30 and close > ma20",
  "direction": "long",
  "timeframe": "H1",
  "symbols": ["XAUUSDm"],
  "best_hold": 5,
  "metrics": {
    "win_rate": 0.64,
    "avg_return": 0.0032,
    "sharpe_ratio": 1.84,
    "signal_count": 87,
    "max_drawdown": -0.042
  },
  "discovered_at": "2026-05-11",
  "status": "active"
}
```

Append this to `best_findings` in `research_state.json`.

---

## 5. Complete Round Script Template

Below is a complete script that ties everything together — run this from
`scripts/` as your standard round template. It loads state, runs one hypothesis,
updates the queue, and checks convergence.

```python
#!/usr/bin/env python3
"""analyst_round.py — Standard single-hypothesis round for the Analyst."""

import json
import sys
from pathlib import Path
from grid_engine import run_grid

# ------------------------------------------------------------------
# 1. Load research state
# ------------------------------------------------------------------
state_path = Path("../state/research_state.json")
state = json.loads(state_path.read_text())

queue = [h for h in state["hypothesis_queue"] if h["status"] == "pending"]
if not queue:
    print("No pending hypotheses. Generate new ones (see Section 6).")
    sys.exit(0)

# Pick the highest-priority pending hypothesis
hypothesis = sorted(queue, key=lambda h: (h["priority"], h.get("created_at", "")))[0]
hypothesis["status"] = "in_progress"

print(f"\n{'='*70}")
print(f"  Round {state['current_round'] + 1}")
print(f"  Hypothesis: {hypothesis['hypothesis']}")
print(f"  ID: {hypothesis['id']}")
print(f"{'='*70}\n")

# ------------------------------------------------------------------
# 2. Construct and run grid
# ------------------------------------------------------------------
# NOTE: You MUST replace the entry_condition, direction, and symbols
# below with those appropriate for the hypothesis you are testing.
config = {
    "timeframe": "H1",
    "symbols": None,  # None = all available symbols
    "entry_condition": "rsi14 < 30 and close > ma20",
    "direction": "long",
    "hold_periods": [1, 3, 5, 10],
    "exit_at_close": True,
}

results = run_grid(config)

# ------------------------------------------------------------------
# 3. Interpret results
# ------------------------------------------------------------------
meta = results.pop("_meta", {})
best_wr = 0.0
best_params = None

print(f"  Symbols with signals: {meta.get('symbols_with_signals', 0)}")
print(f"  {'Symbol':<12} {'Hold':>4} {'n':>5} {'WinRate':>8} {'AvgRet':>9} {'Sharpe':>7} {'MaxDD':>8}")
print(f"  {'-'*55}")

for sym in sorted(results.keys()):
    sym_res = results[sym]
    for hp in sorted(sym_res.keys(), key=int):
        s = sym_res[hp]
        cnt = s.get("signal_count", 0)
        if cnt == 0:
            continue
        wr = s.get("win_rate", 0) or 0
        avg = s.get("avg_return", 0) or 0
        sh = s.get("sharpe_ratio", 0) or 0
        dd = s.get("max_drawdown", 0) or 0
        print(f"  {sym:<12} {hp:>4} {cnt:>5} {wr:>7.2%} {avg:>+8.4f} {sh:>6.2f} {dd:>7.4f}")
        
        if wr > best_wr and cnt >= 30:
            best_wr = wr
            best_params = {"symbol": sym, "hold": hp, "win_rate": wr,
                           "avg_return": avg, "sharpe": sh, "count": cnt}

print(f"\n  Best result: wr={best_wr:.2%}" if best_params else "\n  No valid results.")

# ------------------------------------------------------------------
# 4. Apply interpretation rules
# ------------------------------------------------------------------
verdict = "inconclusive"
summary = ""
new_findings = []

if best_params:
    if best_wr > 0.60:
        verdict = "strong"
        summary = f"Strong signal: {best_params['symbol']} hold={best_params['hold']} wr={best_wr:.2%}"
        new_findings.append({
            "id": f"finding_{len(state['best_findings'])+1:03d}",
            "hypothesis": hypothesis["hypothesis"],
            "entry_condition": config["entry_condition"],
            "direction": config["direction"],
            "timeframe": config["timeframe"],
            "symbols": [best_params["symbol"]],
            "best_hold": best_params["hold"],
            "metrics": {
                "win_rate": best_wr,
                "avg_return": best_params["avg_return"],
                "sharpe_ratio": best_params["sharpe"],
                "signal_count": best_params["count"],
            },
            "discovered_at": "2026-05-11",
            "status": "active"
        })
    elif best_wr > 0.55:
        verdict = "promising"
        summary = f"Promising: {best_params['symbol']} hold={best_params['hold']} wr={best_wr:.2%} — refine further"

# Check if reverse direction might work
avg_win_rate_all = sum(
    s.get("win_rate", 0) or 0
    for sym_res in results.values()
    for s in sym_res.values()
    if s.get("signal_count", 0) > 0
)
signal_count_total = sum(
    s.get("signal_count", 0)
    for sym_res in results.values()
    for s in sym_res.values()
)
if signal_count_total > 0:
    overall_wr = avg_win_rate_all / max(1, len([1 for sym_res in results.values()
                                                  for s in sym_res.values()
                                                  if s.get("signal_count", 0) > 0]))
    if overall_wr < 0.50:
        print(f"  ⚠ Overall win rate {overall_wr:.2%} < 50%. Reverse direction may work.")

# ------------------------------------------------------------------
# 5. Record results in the hypothesis
# ------------------------------------------------------------------
hypothesis["status"] = "tested"
hypothesis["tested_at"] = "2026-05-11"
hypothesis["result"] = {
    "verdict": verdict,
    "best_params": best_params,
    "summary": summary,
}

# Add to tested_hypotheses
state["tested_hypotheses"].append(hypothesis)

# Remove from active queue
state["hypothesis_queue"] = [h for h in state["hypothesis_queue"]
                              if h["id"] != hypothesis["id"]]

# Append best findings
state["best_findings"].extend(new_findings)

# ------------------------------------------------------------------
# 6. Generate new hypotheses (if applicable)
# ------------------------------------------------------------------
if verdict in ("promising", "strong"):
    # Generate a refinement hypothesis
    new_h = {
        "id": f"auto_{len(state['hypothesis_queue'])+len(state['tested_hypotheses'])+1:03d}",
        "hypothesis": f"Refine: {hypothesis['hypothesis']} — tighten filters for higher win rate",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
    }
    state["hypothesis_queue"].append(new_h)
    print(f"  ➕ Generated refinement hypothesis: {new_h['hypothesis']}")

# ------------------------------------------------------------------
# 7. Convergence check
# ------------------------------------------------------------------
state["current_round"] += 1

# Check for 3+ consecutive rounds without a finding
if not new_findings:
    state["fatigue_count"] = state.get("fatigue_count", 0) + 1
else:
    # Reset consecutive counter but fatigue stays
    pass

if state.get("fatigue_count", 0) >= 5:
    print(f"\n  ⛔ Fatigue={state['fatigue_count']} >= 5. Marking topic as EXHAUSTED.")
    state["status"] = "converged"
    # Generate final report
    print(f"\n  Convergence Report")
    print(f"  ==================")
    print(f"  Total hypotheses tested: {len(state['tested_hypotheses'])}")
    print(f"  Best findings: {len(state['best_findings'])}")
    for f in state["best_findings"]:
        print(f"    - {f['hypothesis']} → wr={f['metrics']['win_rate']:.2%}")
    print(f"\n  Ready for new topic.")
elif state.get("fatigue_count", 0) > 0:
    print(f"\n  Fatigue: {state['fatigue_count']}/5 (consecutive rounds without finding)")

# ------------------------------------------------------------------
# 8. Save state
# ------------------------------------------------------------------
state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
print(f"\n  State saved to {state_path}")
print(f"  End of round {state['current_round']}")
```

---

## 6. Common Interpretation Pitfalls

### Pitfall 1: Survivorship / Look-Ahead Bias

The `entry_condition` is evaluated on the candle's close. If you enter at the
close, that is fine. But if your condition uses `high` or `low` of the current
candle (e.g., `high > bb_upper`), you are peeking into the future because you
would not know the high until the candle closed.

**Fix:** Only use `open`, or lag your `high`/`low` references using `shift()`.
The grid engine does not support `shift()` in `eval()` — so stick to
conditions that use only `close`, `open`, and indicators that are computed
from prior data (RSI, ATR, MAs, Bollinger Bands are all based on past closes).

### Pitfall 2: Multiple Comparisons

If you test 14 symbols × 4 hold periods = 56 combinations, expect ~3
combinations to show `win_rate > 60%` by random chance at the 95% confidence
level.

**Mitigation:**
- Demand at least 50 signals (not 30) before calling a multi-symbol result "strong."
- Require the pattern to hold across at least 2 symbols (for cross-symbol hypotheses).
- Re-test the best parameter on out-of-sample data (a later date range).

### Pitfall 3: Ignoring Transaction Costs

A `win_rate` of 55% with `avg_return = 0.0005` (5 basis points) is not
profitable after spreads, commissions, and slippage, especially on H1 where
you might trade several times a day.

**Rule of thumb:** For H1 trading, `avg_return` should be > 0.0015 (15 bps)
to be economically meaningful after costs. For M30, > 0.002 (20 bps) given
higher turnover.

### Pitfall 4: Overfitting to Time

A pattern that works only in 2022 but not in 2023-2025 is likely noise.
Check results across time: the grid engine runs on all available data, but
you can manually split your test by adding a date filter:

```python
# In your runner script, filter data before passing to grid_engine:
# (grid_engine currently does not support date filtering in entry_condition)
# Workaround: test two separate configs with pre-filtered data.
```

For now, be aware of this limitation. When reviewing results, mentally note
whether the pattern is likely regime-dependent.

---

## 7. Output — Handoff to Task Manager / Log

After each round, the Analyst communicates results in a structured log format
that the task manager or parent orchestrator can parse:

```
## Analyst Round Summary

**Round:** {n}
**Hypothesis:** {short description}
**Entry condition:** `{string}`
**Direction:** {long/short}
**Timeframe:** {H1/M30}
**Symbols tested:** {list}

**Best results:**
- {symbol}: hold={hp}, n={cnt}, wr={wr:.1%}, sharpe={sharpe:.2f}
- ...

**Verdict:** {promising/strong/inconclusive/no_signal}
**Finding added:** {yes/no}
**Fatigue:** {current}/5

**Next hypothesis queued:** {short description}

**Status:** {in_progress / completed / converged}
```

This log is written to the conversation or appended to a research journal file.
It is the primary way the human (or parent agent) tracks progress.

---

## 8. Research Dimensions — Reference Cheat Sheet

Use the following table to quickly choose your next hypothesis dimension:

| Dimension | Entry condition pattern | Typical params to vary |
|---|---|---|
| Time (hour) | `hour == X` | X ∈ {0..23}, combine with `dayofweek`, `session` |
| Time (session) | `session == 'asia'` | asia, europe, us; cross with hour |
| Time (day) | `dayofweek == N` | N ∈ {0..4}, cross with hour |
| Momentum (continuation) | `consecutive_bull_count >= N` | N ∈ {2,3,4,5}, add RSI filter |
| Momentum (reversal) | `consecutive_bear_count >= N and rsi14 < 30` | N ∈ {2,3,4}, vary RSI threshold |
| Momentum (gap) | `abs(gap_pct) > T` | T ∈ {0.001, 0.002, 0.003} |
| Volatility (low) | `atr14 / close < V` | V ∈ {0.005, 0.008, 0.01} |
| Volatility (high) | `atr14 / close > V` | V ∈ {0.012, 0.015, 0.02} |
| Volatility (BB) | `close > bb_upper and rsi14 > 70` | Vary RSI threshold, add `close > ma20` |
| Multi-symbol | Same condition across symbols | Compare FX vs indices vs commodities |
| D1 context | `close > ma200` | ma200, ma50; combine with session |
| D1 + momentum | `close > ma200 and consecutive_bear_count >= 3` | Add RSI, hour filters |

---

*End of intraday-framework.md — Analyst Skill Profile v1.0*
