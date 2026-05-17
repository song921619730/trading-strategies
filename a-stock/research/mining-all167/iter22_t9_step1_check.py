#!/usr/bin/env python3
"""T9 Step 1: Check DB connectivity and latest trade date"""
import sys; sys.path.insert(0, '.')
from ch_helper import ch_query

# Check latest trade date
data = ch_query("SELECT max(trade_date) AS max_date FROM tushare.tushare_stock_daily FINAL WHERE trade_date < 20260513")
print('Latest trade date:', data)

# Check count
data2 = ch_query("SELECT count() AS cnt FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= 20260501")
print('Rows >= 20260501:', data2)

# Check state recent_combos
import json
try:
    with open('state/state.json') as f:
        state = json.load(f)
        recent = state.get('recent_combos', [])
        print(f'\nRecent combos in state.json: {len(recent)}')
        for c in recent[:5]:
            print(f'  {c[:80]}...' if len(c) > 80 else f'  {c}')
except:
    print('\nNo state.json found')
