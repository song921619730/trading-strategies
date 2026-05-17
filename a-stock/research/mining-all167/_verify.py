#!/usr/bin/env python3
import json
d = json.load(open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/state/state.json'))
print('current_iteration:', d['current_iteration'])
print('fatigue_count:', d['fatigue_count'])
print('history entries:', len(d['history']))
print('recent_combos:', len(d['recent_combos']))
h = d['history'][1]
print()
print('Latest history entry:')
for k in ['iteration','ret_5d','win_5d','signal_count','sharpe_5d','analyst']:
    print(f'  {k}: {h[k]}')
print('  note (first 200 chars):', h['note'][:200])
print()
print('Global records still:')
print(f'  WR={d["best_metrics"]["win_rate_5d"]}%, R5={d["best_metrics"]["ret_5d"]}%, Sharpe={d["best_metrics"]["sharpe_5d"]}')
