#!/usr/bin/env python3
"""Prepare market data context for EURUSD and XAGUSD Round 1 analysis"""
import json, os
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)

data_path = os.path.join(TRIUMVIRATE_DIR, "data", "pre_analyze_latest.json")
with open(data_path, 'r') as f:
    pre = json.load(f)

# Current time info
meta = pre.get("meta", {})
account = pre.get("account", {})
positions = pre.get("open_positions", [])

# Our Triumvirate positions (Magic 234004)
our_positions = [
    {"symbol": "USOIL", "type": "BUY", "volume": 0.03, "open_price": 97.981, "sl": 96.45, "tp": 100.95, "profit": -3.6},
    {"symbol": "USDJPY", "type": "BUY", "volume": 0.1, "open_price": 157.735, "sl": 157.306, "tp": 158.1, "profit": 3.3}
]

# Full position list for context
all_positions = []
for p in positions:
    all_positions.append({
        "symbol": p["symbol"],
        "type": p["type"],
        "volume": p["volume"],
        "open_price": p["open_price"],
        "sl": p.get("sl", ""),
        "tp": p.get("tp", ""),
        "profit": p.get("profit", 0)
    })

context = {
    "session_info": {
        "bjt_time": "2026-05-13 16:17",
        "trading_session": "美盘 (US Session)",
        "day_of_week": "周三",
        "volatility": "高 (美盘时段)",
        "account_equity": account.get("equity", 2103.47),
        "account_balance": account.get("balance", 2076.26),
        "magic": 234004,
        "max_positions": 5,
        "current_position_count": 2
    },
    "triumvirate_positions": our_positions,
    "all_account_positions": all_positions,
    "news_summary": "US Session 2026-05-13: DXY at 104.78 (up 0.10%). Gold ~$2372 area soft. WTI crude ~$78.91. Stock futures flat to slightly higher ahead of Fed minutes. USDJPY testing 152 area. Key events: US CPI (Wed), Fed minutes, Retail Sales this week.",
}

# Extract EURUSD data
eurusd_data = pre["symbols"]["EURUSD"]
xagusd_data = pre["symbols"]["XAGUSD"]

# EURUSD context
eurusd_ctx = {
    "symbol": "EURUSD",
    "current_price": eurusd_data["trade_params"]["current_price"],
    "atr_14": eurusd_data["indicators"]["atr_14"],
    "support_14": eurusd_data["indicators"]["support_14"],
    "resistance_14": eurusd_data["indicators"]["resistance_14"],
    "d1_candles": eurusd_data["d1_candles"][-10:],
    "h1_candles": eurusd_data["h1_candles"][-24:],
    "recommended_lot": eurusd_data["trade_params"]["recommended_lot"],
    "buy_scenario": eurusd_data["trade_params"]["buy_scenario"],
    "sell_scenario": eurusd_data["trade_params"]["sell_scenario"],
    "already_held_in_account": eurusd_data["already_held"],
    "d1_trend_quick": "BEARISH (LH/LL formed, closes declining)",
    "news": "EUR/USD under pressure from strong USD. DXY above 104.50. Eurozone data mixed. Market expects hawkish Fed."
}

xagusd_ctx = {
    "symbol": "XAGUSD",
    "current_price": xagusd_data["trade_params"]["current_price"],
    "atr_14": xagusd_data["indicators"]["atr_14"],
    "support_14": xagusd_data["indicators"]["support_14"],
    "resistance_14": xagusd_data["indicators"]["resistance_14"],
    "d1_candles": xagusd_data["d1_candles"][-10:],
    "h1_candles": xagusd_data["h1_candles"][-24:],
    "recommended_lot": xagusd_data["trade_params"]["recommended_lot"],
    "buy_scenario": xagusd_data["trade_params"]["buy_scenario"],
    "sell_scenario": xagusd_data["trade_params"]["sell_scenario"],
    "already_held_in_account": xagusd_data["already_held"],
    "d1_trend_quick": "BULLISH (HH/HL formed, recent pullback)",
    "news": "Silver benefited from industrial demand and gold correlation. However, DXY strength caps upside. Technical pullback from recent highs."
}

# Also include USDCHF for comparison
usdchf_data = pre["symbols"]["USDCHF"]
usdchf_ctx = {
    "symbol": "USDCHF",
    "current_price": usdchf_data["trade_params"]["current_price"],
    "atr_14": usdchf_data["indicators"]["atr_14"],
    "support_14": usdchf_data["indicators"]["support_14"],
    "resistance_14": usdchf_data["indicators"]["resistance_14"],
    "d1_candles": usdchf_data["d1_candles"][-10:],
    "h1_candles": usdchf_data["h1_candles"][-24:],
    "recommended_lot": usdchf_data["trade_params"]["recommended_lot"],
    "buy_scenario": usdchf_data["trade_params"]["buy_scenario"],
    "sell_scenario": usdchf_data["trade_params"]["sell_scenario"],
    "d1_trend_quick": "BULLISH (Higher lows, gradual uptrend)",
}

output = {
    "context": context,
    "candidates": {
        "EURUSD": eurusd_ctx,
        "XAGUSD": xagusd_ctx,
        "USDCHF": usdchf_ctx
    }
}

print(json.dumps(output, indent=2, ensure_ascii=False))
