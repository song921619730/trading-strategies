#!/usr/bin/env python3
"""
Trade Gate filter for Triumvirate Magic 234004
Evaluates 5 filters for 14 symbols and outputs JSON
"""
import json, os
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)

# Our Magic's held symbols
TRIUMVIRATE_HELD = {"USOIL", "USDJPY"}  # From pnl_report

# Correlation groups
CORR_GROUPS = {
    "贵金属组": ["XAUUSD", "XAGUSD"],
    "美股指组": ["US30", "US500", "USTEC"],
    "欧系组": ["EURUSD", "GBPUSD"],
    "商品组": ["USOIL", "UKOIL"],
    "亚洲组": ["JP225", "HK50"],
}

# Our open positions with directions
OUR_POSITIONS = {
    "USOIL": {"dir": "BUY", "vol": 0.03, "pnl": -3.6},
    "USDJPY": {"dir": "BUY", "vol": 0.1, "pnl": 3.3},
}

# Load latest pre_analyze data
data_path = os.path.join(TRIUMVIRATE_DIR, "data", "pre_analyze_latest.json")
with open(data_path, 'r') as f:
    pre = json.load(f)

symbols_data = pre.get("symbols", {})
account = pre.get("account", {})
equity = account.get("equity", 2000)
positions = pre.get("open_positions", [])
meta = pre.get("meta", {})
session = meta.get("trading_session", "美盘 (US Session)")
timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M%S")

results = {}
for sym, data in sorted(symbols_data.items()):
    filters = {}
    
    # Filter 1: 有可用数据
    ind = data.get("indicators", {})
    tp = data.get("trade_params", {})
    atr = ind.get("atr_14", 0)
    price = tp.get("current_price", 0)
    has_data = atr > 0 and price > 0
    filters["filter1_data_available"] = has_data
    
    # Filter 2: 持仓表中该品种没有现有仓位 (Magic 234004 perspective)
    already_held = sym in TRIUMVIRATE_HELD
    filters["filter2_no_position"] = not already_held
    filters["_held_by_other_magic"] = data.get("already_held", False) and not already_held
    
    # Filter 3: 趋势方向可辨 - we'll do a quick check from H1/H4 candles
    # For now, we'll mark this as needing detailed analysis (True for all with data)
    h1_summary = data.get("h1_summary", {})
    d1_summary = data.get("d1_summary", {})
    has_candles = (h1_summary.get("candle_count", 0) >= 10 and 
                   d1_summary.get("candle_count", 0) >= 5)
    filters["filter3_trend_discernible"] = has_candles
    
    # Filter 4: H1 结构质量 - requires detailed AI analysis
    # Mark as "needs_analysis" for now
    filters["filter4_h1_quality"] = "needs_analysis"
    
    # Filter 5: 相关性风险
    corr = data.get("correlation", {})
    # Check buy and sell scenarios
    for direction in ["BUY", "SELL"]:
        dir_corr = corr.get(direction, {})
        can_open = dir_corr.get("can_open", True)
        reason = dir_corr.get("reason", "OK")
        
        # Calculate correlation risk manually
        group_risk_pct = 0
        my_group = None
        for gname, members in CORR_GROUPS.items():
            if sym in members:
                my_group = gname
                # Check if we have any positions in this group
                for held_sym in TRIUMVIRATE_HELD:
                    if held_sym in members:
                        pos = OUR_POSITIONS.get(held_sym, {})
                        if pos.get("dir") == direction:
                            # Estimate risk based on position size
                            group_risk_pct += 5  # rough estimate
                break
        
        filters[f"filter5_corr_risk_{direction}"] = {
            "can_open": can_open,
            "reason": reason,
            "group": my_group,
            "group_risk_pct": group_risk_pct
        }
    
    # Overall pass/fail for first pass
    all_filters_pass_basic = (
        filters["filter1_data_available"] and
        filters["filter2_no_position"] and
        filters["filter3_trend_discernible"]
    )
    
    results[sym] = {
        "filters": filters,
        "basic_pass": all_filters_pass_basic,
        "price": price,
        "atr": atr,
    }

# Output results
output = {
    "timestamp": timestamp,
    "trading_session": session,
    "triumvirate_held": list(TRIUMVIRATE_HELD),
    "account_equity": equity,
    "candidates": results
}

# Save to logs/scans/
log_dir = os.path.join(TRIUMVIRATE_DIR, "logs", "scans")
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, f"{timestamp}_tradegate.json")
with open(log_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"Trade Gate results saved to: {log_path}")
print()

# Summary
pass_count = sum(1 for r in results.values() if r["basic_pass"])
total = len(results)
print(f"Basic Pass (Filters 1-3): {pass_count}/{total}")
print(f"Need AI analysis (Filter 4 - H1 Quality):")
for sym, r in sorted(results.items()):
    if r["basic_pass"]:
        corr_info = r["filters"]["filter5_corr_risk_BUY"]
        print(f"  {sym}: price={r['price']}, atr={r['atr']:.2f}, group={corr_info['group']}, held_by_other={r['filters']['_held_by_other_magic']}")
    else:
        reasons = []
        if not r["filters"]["filter1_data_available"]: reasons.append("NO_DATA")
        if not r["filters"]["filter2_no_position"]: reasons.append("HELD")
        if not r["filters"]["filter3_trend_discernible"]: reasons.append("NO_TREND")
        print(f"  {sym}: ❌ {', '.join(reasons)}")

# Print the full JSON
print()
print(json.dumps(output, indent=2, ensure_ascii=False))
