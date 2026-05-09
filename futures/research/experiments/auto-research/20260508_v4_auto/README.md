# Experiment: 20260508_v4_auto - Cross-Asset Volatility Resonance

**Brief**: `20260508_1954.md`
**Status**: ✅ Completed

## Hypothesis
When multiple futures simultaneously enter low-volatility regimes, the subsequent breakout is stronger and faster than single-asset compression.

## Results
- **Validated**: 3+ sync compression → 80-118% stronger breakouts
- **Oil amplification**: USOIL/UKOIL show 190-253% enhancement during sync
- **Release events**: Rare (~3 in 2.5 years) but 129.6% stronger than baseline

## Files
- `report.md` - Full research findings with statistical analysis
- `proposal.md` - Sync Compression Alert (SCA) rule for Pure AI CIO
- `backtest.py` - MT5-based cross-asset volatility analysis script

## How to Run
```bash
C:/Users/gj/AppData/Local/Programs/Python/Python312/python.exe backtest.py
```

## Key Data
- 7 symbols: XAUUSDm, XAGUSDm, USOILm, UKOILm, XCUUSDm, XNGUSDm, US30m
- 648 aligned trading days (2023-10 to 2026-05)
- 15 sync days, 3 release events
