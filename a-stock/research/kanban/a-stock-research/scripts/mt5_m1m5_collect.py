#!/usr/bin/env python3
"""MT5 M1/M5 data collector — WSL calls Windows Python to get scalping data."""
import subprocess
import json
import sys
import os
from datetime import datetime, timedelta

WINDOWS_PYTHON = r"C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe"
MT5_SCRIPT = r"C:\Users\gj\tmp\mt5_fetch_m1m5.py"

MT5_CODE = r'''
import sys
sys.stdout.reconfigure(encoding='utf-8')
import struct
import time as _time
try:
    import MetaTrader5 as mt5
    mt5_ok = True
except ImportError:
    mt5_ok = False

if not mt5_ok:
    print("MT5_NOT_AVAILABLE")
    sys.exit(0)

if not mt5.initialize():
    print(f"MT5_INIT_FAILED: {mt5.last_error()}")
    sys.exit(0)

import json as _json
from datetime import datetime as _dt

symbols = ['XAUUSD', 'XAGUSD', 'JP225', 'US500', 'US30']
timeframes = {
    'M1': mt5.TIMEFRAME_M1,
    'M5': mt5.TIMEFRAME_M5,
    'M15': mt5.TIMEFRAME_M15,
    'M30': mt5.TIMEFRAME_M30,
    'H1': mt5.TIMEFRAME_H1,
    'H4': mt5.TIMEFRAME_H4,
    'D1': mt5.TIMEFRAME_D1,
}

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--lookback", type=int, default=720)
parser.add_argument("--tf", type=str, default="M5")
args, _ = parser.parse_known_args()

tf = timeframes.get(args.tf, mt5.TIMEFRAME_M5)
lookback = args.lookback

result = {}
for sym in symbols:
    rates = mt5.copy_rates_from_pos(sym, tf, 0, lookback)
    if rates is None or len(rates) == 0:
        result[sym] = []
        continue
    klines = []
    for r in rates:
        klines.append({
            "time": _dt.fromtimestamp(r[0]).strftime("%Y-%m-%d %H:%M:%S"),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": int(r[5]),
            "spread": int(r[6]),
            "real_volume": int(r[7])
        })
    result[sym] = klines

print(_json.dumps(result))
mt5.shutdown()
'''

def fetch_mt5_data(timeframe="M5", lookback=720):
    """Fetch MT5 data via Windows Python bridge."""
    # Write temp script
    import tempfile
    script_path = os.path.join(tempfile.gettempdir(), "mt5_fetch_m1m5.py")
    with open(script_path, "w", encoding='utf-8') as f:
        f.write(MT5_CODE)
    
    # Run via Windows Python
    wsl_path = script_path.replace("\\", "/")
    # Find the Windows path equivalent
    # /tmp/mt5_fetch_m1m5.py → C:\Users\gj\...  nope, /tmp is WSL only
    # We need to write to a Windows-accessible location
    win_path = f"C:/Users/gj/tmp/mt5_fetch_m1m5.py"
    os.makedirs("/mnt/c/Users/gj/tmp", exist_ok=True)
    with open("/mnt/c/Users/gj/tmp/mt5_fetch_m1m5.py", "w", encoding='utf-8') as f:
        f.write(MT5_CODE)
    
    cmd = [
        WINDOWS_PYTHON,
        win_path,
        "--tf", timeframe,
        "--lookback", str(lookback)
    ]
    
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        if r.returncode != 0:
            return {"error": f"Windows Python error: {r.stderr[:500]}"}
        
        # Parse output
        idx = r.stdout.find('{')
        if idx >= 0:
            data = json.loads(r.stdout[idx:])
            return data
        else:
            return {"error": f"No JSON in output: {r.stdout[:500]}"}
    except subprocess.TimeoutExpired:
        return {"error": "MT5 fetch timeout"}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tf", default="M5", help="Timeframe: M1, M5, M15, M30, H1")
    parser.add_argument("--lookback", type=int, default=720, help="Number of bars")
    args = parser.parse_args()
    
    data = fetch_mt5_data(args.tf, args.lookback)
    print(json.dumps(data, ensure_ascii=False, indent=2))
