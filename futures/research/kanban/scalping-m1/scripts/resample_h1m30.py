#!/usr/bin/env python3
"""从M5 parquet数据重采样生成H1和M30数据"""
import sys, os
from pathlib import Path
import pandas as pd
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M5_DIR = os.path.join(BASE, "data", "M5")
H1_DIR = os.path.join(BASE, "data", "H1")
M30_DIR = os.path.join(BASE, "data", "M30")
os.makedirs(H1_DIR, exist_ok=True)
os.makedirs(M30_DIR, exist_ok=True)

SYMBOLS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCHF",
           "XAUUSD","XAGUSD",
           "US30","US500","USTEC","JP225","HK50",
           "USOIL","UKOIL"]

olhcv_cols = ["open","high","low","close","tick_volume","spread","real_volume"]

for sym in SYMBOLS:
    m5_path = os.path.join(M5_DIR, f"{sym}.parquet")
    if not os.path.exists(m5_path):
        print(f"  ⚠ {sym}: 无M5数据")
        continue
    
    df = pd.read_parquet(m5_path)
    print(f"  {sym:10s} M5: {len(df):>6} rows  [{df.index[0]} → {df.index[-1]}]", end="")
    
    # H1 resampling
    ohlc_dict = {
        "open": "first", "high": "max", "low": "min", "close": "last",
        "tick_volume": "sum", "spread": "mean", "real_volume": "sum"
    }
    h1 = df.resample("1h", closed="right", label="right").agg(ohlc_dict).dropna()
    h1_path = os.path.join(H1_DIR, f"{sym}.parquet")
    h1.to_parquet(h1_path)
    print(f" | H1: {len(h1):>5} rows  [{h1.index[0]} → {h1.index[-1]}]", end="")
    
    # M30 resampling
    m30 = df.resample("30min", closed="right", label="right").agg(ohlc_dict).dropna()
    m30_path = os.path.join(M30_DIR, f"{sym}.parquet")
    m30.to_parquet(m30_path)
    print(f" | M30: {len(m30):>5} rows  [{m30.index[0]} → {m30.index[-1]}]")

print("\n✅ H1/M30重采样完成")
