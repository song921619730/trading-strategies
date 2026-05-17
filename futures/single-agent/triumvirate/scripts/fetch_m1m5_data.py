#!/usr/bin/env python3
"""
Fetch M1/M5 candle data from MT5 for scalping research.
Saves structured data for grid_engine.py consumption.
"""
import MetaTrader5 as mt5
import sys, os, json
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

SYMBOLS_MAP = {
    "XAUUSD": "XAUUSD",
    "XAGUSD": "XAGUSD",
    "JP225": "JP225",
    "US500": "US500",
    "US30": "US30",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
}

CANDLE_COUNT = {
    "M1": 240,    # 4 hours of M1
    "M5": 120,    # 10 hours of M5
    "M15": 60,
    "M30": 50,
    "H1": 50,
}

def connect():
    if not mt5.initialize(path=MT5_PATH):
        return {"error": f"MT5 init failed: {mt5.last_error()}"}
    return None

def fetch_timeframe(symbol, timeframe_str):
    tf_code = TF_MAP.get(timeframe_str)
    if tf_code is None:
        return {"error": f"Unknown timeframe: {timeframe_str}"}
    
    count = CANDLE_COUNT.get(timeframe_str, 100)
    bars = mt5.copy_rates_from_pos(symbol, tf_code, 0, count)
    if bars is None:
        return {"error": f"No data for {symbol} {timeframe_str}: {mt5.last_error()}"}
    
    candles = []
    for b in bars:
        t = datetime.fromtimestamp(b['time'], tz=timezone.utc).astimezone(CST)
        candles.append({
            "time": t.strftime("%Y-%m-%d %H:%M"),
            "open": round(b['open'], 5),
            "high": round(b['high'], 5),
            "low": round(b['low'], 5),
            "close": round(b['close'], 5),
            "tick_volume": b['tick_volume'],
            "spread": b['spread'],
            "real_volume": b['real_volume'],
        })
    return candles

def main():
    err = connect()
    if err:
        print(json.dumps(err))
        sys.exit(1)
    
    timeframes = ["M1", "M5"]
    result = {
        "meta": {
            "fetch_time_cst": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
            "source": "MT5",
            "symbols": list(SYMBOLS_MAP.keys()),
            "timeframes": timeframes,
        },
        "data": {},
    }
    
    for sym_code, sym_mt5 in SYMBOLS_MAP.items():
        mt5.symbol_select(sym_mt5, True)
        tick = mt5.symbol_info_tick(sym_mt5)
        result["data"][sym_code] = {
            "current_price": tick.ask if tick else None,
            "current_bid": tick.bid if tick else None,
            "current_ask": tick.ask if tick else None,
            "candles": {},
        }
        for tf in timeframes:
            candles = fetch_timeframe(sym_code, tf)
            result["data"][sym_code]["candles"][tf] = candles
            if isinstance(candles, list):
                result["data"][sym_code]["candles"][f"{tf}_count"] = len(candles)
    
    mt5.shutdown()
    
    # Save to data/
    data_path = os.path.join(PROJECT_DIR, "data", "m1m5_latest.json")
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    # Also save timestamped
    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(PROJECT_DIR, "logs", "scans")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{ts}_m1m5_data.json")
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
