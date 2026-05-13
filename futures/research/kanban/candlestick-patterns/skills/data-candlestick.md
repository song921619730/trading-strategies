---
name: data-candlestick
version: 1.0.0
profile: Researcher
label: Data Loader & Candlestick Feature Computation
description: >
  Loads H1 and M30 parquet data from the shared data directory (symlinked
  from futures-intraday), computes standard indicators, then adds candlestick
  pattern detection columns.
---

# data-candlestick — Researcher: Data Loading

## Data Location

Data is symlinked from `futures-intraday/data/`:
```
candlestick-patterns/
├── data/
│   └── futures-intraday/ -> ../../futures-intraday/data/
│       ├── H1/*.parquet
│       └── M30/*.parquet
└── scripts/
```

## Quick Data Load

```python
cd /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/candlestick-patterns/scripts
python3 << 'EOF'
from data_loader import load_data, compute_indicators, list_available_symbols
from candlestick_features import add_candlestick_features, pattern_summary

# Load H1 all symbols
data = load_data("H1")
print(f"Loaded {len(data)} symbols for H1")

# Check a sample symbol
sym = "XAUUSDm"
df = compute_indicators(data[sym])
df = add_candlestick_features(df)
print(f"\n{sym} rows: {len(df)}, cols: {list(df.columns)}")

# Pattern frequency
print(pattern_summary(df))
EOF
```

## Typical Researcher Output

When the Round starts, the Researcher:
1. Loads H1 and M30 data
2. Computes standard indicators and candlestick features
3. Prints a pattern frequency summary (which patterns are common, which are rare)
4. Hands off to the Analyst with the printed summary
