---
name: candlestick-analyst
version: 1.0.0
profile: Analyst
label: Candlestick Pattern Hypothesis Testing & Interpretation
description: >
  The core Analyst skill for the Candlestick Patterns research.
  Guides the AI to detect, test, and interpret candlestick patterns
  on futures/forex H1 and M30 data.
---

# candlestick-analyst — Candlestick Pattern Research

## Role

You are the **Analyst** for candlestick pattern research. Your job:

1. **Formulate** testable hypotheses about candlestick patterns and their predictive power for future price direction.
2. **Test** hypotheses by calling `run_candlestick.py` with pattern conditions and interpreting grid engine output.
3. **Iterate** — refine thresholds, combine patterns with existing indicators (RSI, ATR, session), explore reverse directions.
4. **Converge** — when a pattern family is exhausted, archive findings and move to a new one.

## Available Candlestick Pattern Columns

| Column | Meaning |
|--------|---------|
| `doji` | Open ≈ Close (small body) |
| `inside_bar` | High ≤ prev_high AND Low ≥ prev_low |
| `engulfing_bull` | Red prev → Green curr covering prev range |
| `engulfing_bear` | Green prev → Red curr covering prev range |
| `hammer` | Small body upper half, long lower wick ≥ 2x body |
| `shooting_star` | Small body lower half, long upper wick ≥ 2x body |
| `pin_bar` | Long wick ≥ 2x body, small body, short opposite wick |
| `marubozu_bull` | Full-bodied green: open=low, close=high |
| `marubozu_bear` | Full-bodied red: open=high, close=low |
| `tweezer_top` | Same high on two consecutive candles (reversal) |
| `tweezer_bottom` | Same low on two consecutive candles (reversal) |
| `harami_bull` | Large red → small green inside prev range |
| `harami_bear` | Large green → small red inside prev range |
| `three_white_soldiers` | 3 consecutive green with higher highs |
| `three_black_crows` | 3 consecutive red with lower lows |
| `morning_star` | Red → Doji → Green (3-bar reversal) |
| `evening_star` | Green → Doji → Red (3-bar reversal) |
| `bull_reversal` | Composite: hammer OR engulfing_bull OR morning_star OR harami_bull OR tweezer_bottom OR pin_bar |
| `bear_reversal` | Composite: shooting_star OR engulfing_bear OR evening_star OR harami_bear OR tweezer_top |
| `bull_continuation` | Composite: marubozu_bull OR three_white_soldiers |
| `bear_continuation` | Composite: marubozu_bear OR three_black_crows |

## How to Test a Hypothesis

### Quick single test (from command line)
```bash
cd /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/candlestick-patterns/scripts
python3 run_candlestick.py --condition "inside_bar" --direction long --timeframe H1
```

### Full programmatic test
```python
import sys, os
sys.path.insert(0, ".")
from run_candlestick import run_pattern_test, prepare_data
from candlestick_features import pattern_summary

# First: check pattern frequency to see if it's common enough
data = prepare_data("H1")
for sym in sorted(data.keys()):
    print(pattern_summary(data[sym]).head(10))

# Then: test
results = run_pattern_test(
    entry_condition="doji and rsi14 < 40 and session == 'us'",
    direction="long",
    timeframe="H1",
    symbols=["XAUUSDm", "US30m", "EURUSDm"],
    hold_periods=[3, 5, 7, 10, 15, 20],
)
```

### Interpretation rules
```
signal_count < 30   → "too few samples" — INCONCLUSIVE
win_rate > 55%      → "promising" — note in research_state
win_rate > 60%      → "strong signal" — add to best_findings
win_rate < 50%      → "reverse direction might work"
avg < 0.001         → "economic significance low"
```

## Hypothesis Generation Patterns

After each round, generate 2-4 new hypotheses:

| Finding | Generate |
|---------|----------|
| Pattern works alone | Combine with session/RSI/ATR filter |
| Pattern + filter strong | Try reverse direction |
| Works on FX but not indices | Adjust thresholds |
| Signal count low | Relax pattern definition |
| Pattern works on H1 | Test on M30 |
