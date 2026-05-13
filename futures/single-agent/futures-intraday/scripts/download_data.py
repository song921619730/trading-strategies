#!/usr/bin/env python3
"""下载研究数据到 CSV 文件"""
import json
import os
import time
import sys
import yfinance as yf
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data", "research")
os.makedirs(DATA_DIR, exist_ok=True)

# 品种映射
SYMBOL_MAP = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "US30": "^DJI",
    "US500": "^GSPC",
    "USTEC": "^IXIC",
    "JP225": "^N225",
    "HK50": "^HSI",
    "USOIL": "CL=F",
    "UKOIL": "BZ=F",
    "BTCUSD": "BTC-USD",
    "DXY": "DX-Y.NYB",
}

symbols_to_download = ["XAUUSD", "EURUSD", "US30", "JP225", "GBPUSD", "AUDUSD", "USDJPY", "US500", "HK50", "USOIL", "DXY"]

for sym in symbols_to_download:
    yf_sym = SYMBOL_MAP[sym]
    csv_path = os.path.join(DATA_DIR, f"{sym}_D1.csv")
    
    if os.path.exists(csv_path):
        print(f"✅ {sym} ({yf_sym}) 已缓存")
        continue
    
    print(f"📥 下载 {sym} ({yf_sym})...", end=" ", flush=True)
    try:
        df = yf.download(yf_sym, period="5y", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            print(f"⚠️ 无数据")
        else:
            df.to_csv(csv_path)
            print(f"✓ {len(df)} 行")
    except Exception as e:
        print(f"❌ {e}")
    
    # 延迟以避免速率限制
    print("  ⏳ 等待 3 秒...")
    time.sleep(3)

print(f"\n下载完成！数据保存在 {DATA_DIR}")
