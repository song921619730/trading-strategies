#!/usr/bin/env python3
"""
Mandatory Grid Search Engine for Research Experiments
Run this BEFORE declaring a topic exhausted.
"""
import requests
import pandas as pd
import numpy as np
from itertools import product
from io import StringIO
import json

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def run_grid_search():
    # 1. Define Factor Space (MUST cover all available DB columns)
    factor_space = {
        'ma_cv': [0.005, 0.01, 0.015, 0.02, 0.03],
        'atr_pct': [0.015, 0.02, 0.025, 0.03],
        'vol_ratio': [1.5, 2.0, 3.0, 5.0],
        'pct_chg_range': [(2, 5), (5, 7), (0, 3)],  # (min, max)
        'turnover_rate': [0.02, 0.05, 0.10, 0.20],   # 2%, 5%, 10%, 20%
        'market_cap_quartile': ['Q1', 'Q2', 'Q3'],    # Small, Mid, Large
    }
    
    # 2. Generate Combinations (Cartesian Product)
    keys = list(factor_space.keys())
    combos = list(product(*factor_space.values()))
    print(f"🔍 Generating {len(combos)} combinations...")
    
    results = []
    # 3. Run ClickHouse queries in batches
    for combo in combos[:100]: # Limit to 100 per run to avoid timeout
        params = dict(zip(keys, combo))
        # Build SQL dynamically...
        # (Simplified for template)
        metrics = {
            "params": {k: str(v) for k, v in params.items()},
            "n_signals": 0,
            "avg_ret_20d": 0.0,
            "win_rate": 0.0
        }
        results.append(metrics)
        
    # 4. Save & Sort
    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values("avg_ret_20d", ascending=False)
    df_res.to_json("grid_results.json", orient="records", indent=2)
    print("✅ grid_results.json saved. Top 5:")
    print(df_res.head())

if __name__ == "__main__":
    run_grid_search()
