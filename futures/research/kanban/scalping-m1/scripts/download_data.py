#!/usr/bin/env python3
"""download_data.py — 从 MT5 下载 M1/M5 数据并保存为 parquet

用法（Windows Python）:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
    F:/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts/download_data.py
"""
import json
import os
import sys
from datetime import datetime, timezone

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
           "XAUUSD", "XAGUSD",
           "US30", "US500", "USTEC", "JP225", "HK50",
           "USOIL", "UKOIL"]

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
}

# MT5 copy_rates_from_pos 单次最多约 200K 条
# 用分批下载拼接来获取1年数据
BARS_PER_CALL = 50000
TOTAL_BARS = {
    "M1": 500000,   # ~1年
    "M5": 100000,   # ~1年
}


def download():
    mt5.initialize()

    for tf_name, tf_const in TIMEFRAMES.items():
        data_dir = os.path.join(BASE, "data", tf_name)
        os.makedirs(data_dir, exist_ok=True)

        total_needed = TOTAL_BARS[tf_name]
        print(f"\n{'='*50}")
        print(f"📥 下载 {tf_name} 数据（分批 {BARS_PER_CALL}）")
        print(f"{'='*50}")

        for sym in SYMBOLS:
            print(f"  {sym:10s} ", end="", flush=True)
            try:
                # 分批下载，用 DataFrame 拼接
                all_dfs = []
                offset = 0
                while True:
                    batch = mt5.copy_rates_from_pos(sym, tf_const, offset, BARS_PER_CALL)
                    if batch is None or len(batch) == 0:
                        if offset == 0:
                            print(f"❌ MT5返回空: {mt5.last_error()}")
                        else:
                            print(f"!耗尽({offset})", end="", flush=True)
                        break
                    print(".", end="", flush=True)
                    # 直接用 dtype.names 访问列
                    df = pd.DataFrame({name: batch[name] for name in batch.dtype.names})
                    all_dfs.append(df)
                    offset += len(batch)
                    if len(batch) < BARS_PER_CALL:
                        break

                if not all_dfs:
                    print("❌ 无数据")
                    continue

                df = pd.concat(all_dfs, ignore_index=True)
                # 取最新的 total_needed 条
                if len(df) > total_needed:
                    df = df.tail(total_needed)
                df["time"] = pd.to_datetime(df["time"], unit="s")
                df = df.set_index("time")
                df = df[["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]]
                df = df.sort_index()

                fp = os.path.join(data_dir, f"{sym}.parquet")
                df.to_parquet(fp)

                print(f" ✅ {len(df):>6} rows  [{df.index[0].strftime('%Y-%m-%d %H:%M')} → {df.index[-1].strftime('%Y-%m-%d %H:%M')}]")
            except Exception as e:
                import traceback
                print(f" ❌ {e}")

    mt5.shutdown()
    print(f"\n✅ 全部下载完成")


if __name__ == "__main__":
    download()
