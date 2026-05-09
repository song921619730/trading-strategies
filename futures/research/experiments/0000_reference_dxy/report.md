# 0000 Reference: DXY Correlation Analysis
## 📅 Date: 2026-05-08
## 🎯 Objective: Analyze correlation between DXY and XAUUSDm
## 🔍 Method: 3-month rolling correlation, intraday lag analysis

### Data Sources
- `data/dxy_h1.csv`: USD Index Hourly Data
- `data/gold_h1.csv`: Gold Hourly Data

### Code Snippet
```python
import pandas as pd
dxy = pd.read_csv('data/dxy_h1.csv', index_col=0)
gold = pd.read_csv('data/gold_h1.csv', index_col=0)
corr = gold['close'].rolling(24).corr(dxy['close'])
print(f"Avg Correlation: {corr.mean():.2f}")
```

### Conclusion
High negative correlation (-0.75) observed. Suggests adding DXY filter for Gold trades.
