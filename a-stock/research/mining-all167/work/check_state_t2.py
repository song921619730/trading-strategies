#!/usr/bin/env python3
import json
with open('state/state.json') as f:
    data = json.load(f)
combos = data.get('recent_combos', [])
print(f'Total recent combos: {len(combos)}')
print('Last 10:', combos[-10:] if len(combos) >= 10 else combos)
