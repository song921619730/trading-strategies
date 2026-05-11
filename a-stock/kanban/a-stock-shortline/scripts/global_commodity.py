#!/usr/bin/env python3
"""Get overnight index data from global-futures for additional context."""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/skills/global-futures/scripts')
from global_futures import GlobalFutures
gf = GlobalFutures()
# Get gold and crude oil as they affect market sentiment
for symbol in ['Gold', 'CrudeOil', 'Copper']:
    try:
        hist = gf.get_history(symbol, '5d')
        if hist is not None and len(hist) > 0:
            print(f"\n=== {symbol} (last 5 days) ===")
            print(hist.tail(5).to_string())
        else:
            print(f"\n{symbol}: No data")
    except Exception as e:
        print(f"\n{symbol}: Error: {e}")
