#!/usr/bin/env python3
"""
fetch_mt5_data.py — 通过 MT5 (Windows Python) 获取历史K线数据

用法:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
    "F:/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/scripts/fetch_mt5_data.py"
"""
import json
import os
import sys
from datetime import datetime, timezone

import MetaTrader5 as mt5

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data", "research")
os.makedirs(DATA_DIR, exist_ok=True)

# 要下载的品种和时间框架
SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDJPY",
           "USDCAD", "USDCHF", "NZDUSD", "US30", "US500", "USTEC",
           "JP225", "HK50", "UK100", "DE30", "USOIL", "UKOIL", "BTCUSD"]
TF_MAP = {"M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1}
TIMEFRAMES = ["M30", "H1"]
BARS_COUNT = 5000  # MT5最大约65000，取5000足够3年H1或1.5年M30

def main():
    print("=" * 60)
    print(f"MT5 历史数据下载器")
    print(f"启动时间: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    
    # 初始化MT5
    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    
    print(f"MT5路径: {path}")
    if not mt5.initialize(path=path, login=login, password=password, server=server):
        print(f"❌ MT5 初始化失败: {mt5.last_error()}")
        return
    
    account = mt5.account_info()
    if account:
        print(f"✅ 账户: {account.login} | 余额: {account.balance:.2f}")
    else:
        print(f"⚠️ 无法获取账户信息，但MT5可能已连接")
    
    total = 0
    for tf_name in TIMEFRAMES:
        mt5_tf = TF_MAP[tf_name]
        for symbol in SYMBOLS:
            csv_path = os.path.join(DATA_DIR, f"{symbol}_{tf_name}.csv")
            if os.path.exists(csv_path):
                size = os.path.getsize(csv_path)
                if size > 1000:
                    print(f"  ✅ {symbol} {tf_name} 已存在 ({size:,} bytes)")
                    continue
            
            print(f"  📥 {symbol} {tf_name}...", end=" ", flush=True)
            try:
                bars = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, BARS_COUNT)
                if bars is None or len(bars) < 100:
                    print(f"⚠️ 数据不足 ({len(bars) if bars else 0})")
                    continue
                
                # 转换为 CSV
                lines = ["time,open,high,low,close,volume"]
                for bar in bars:
                    t = datetime.fromtimestamp(bar['time'], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    lines.append(f"{t},{bar['open']:.5f},{bar['high']:.5f},{bar['low']:.5f},{bar['close']:.5f},{bar['tick_volume']}")
                
                with open(csv_path, "w") as f:
                    f.write("\n".join(lines))
                
                print(f"✓ {len(bars)} bars → {csv_path}")
                total += 1
            except Exception as e:
                print(f"❌ {e}")
    
    mt5.shutdown()
    print(f"\n✅ 完成！共下载 {total} 个品种×时间框架的数据文件")
    print(f"数据目录: {DATA_DIR}")

if __name__ == "__main__":
    main()
