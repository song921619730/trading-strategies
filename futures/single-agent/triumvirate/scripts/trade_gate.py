"""Triumvirate — Trade Gate Filtering (Step 3)"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)

def main():
    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")

    # Find latest pre_analyze
    scans_dir = os.path.join(TRIUMVIRATE_DIR, "logs", "scans")
    pre_files = [f for f in os.listdir(scans_dir) if f.endswith("_pre_analyze.json")]
    if not pre_files:
        print(json.dumps({"error": "No pre_analyze files found"}))
        sys.exit(1)
    latest_pre = sorted(pre_files)[-1]
    
    with open(os.path.join(scans_dir, latest_pre)) as f:
        data = json.load(f)

    symbols = data['symbols']
    positions = data.get('open_positions', [])
    held_symbols = [p.get('symbol', '') for p in positions]

    tradegate = {
        "timestamp": ts,
        "source_pre_analyze": latest_pre,
        "meta": {
            "account_equity": data['account']['equity'],
            "balance": data['account']['balance'],
            "total_positions": len(positions),
            "held_symbols": held_symbols,
            "magic": "234004"
        },
        "candidates": {},
        "summary": {
            "total_symbols": len(symbols),
            "auto_passed": [],
            "auto_failed": [],
            "needs_round1": []
        }
    }

    for sym, info in symbols.items():
        result = {
            "symbol": sym,
            "price": info.get('trade_params', {}).get('current_price', 0),
            "atr": info.get('indicators', {}).get('atr_14', 0),
            "checks": {},
            "auto_pass": True,
            "fail_reasons": []
        }
        
        # Check 1: Data availability
        has_atr = info.get('indicators', {}).get('atr_14', 0) > 0
        has_price = info.get('trade_params', {}).get('current_price', 0) > 0
        has_h1 = len(info.get('h1_candles', [])) > 0
        has_d1 = len(info.get('d1_candles', [])) > 0
        data_ok = all([has_atr, has_price, has_h1, has_d1])
        result['checks']['data_available'] = data_ok
        if not data_ok:
            result['auto_pass'] = False
            result['fail_reasons'].append("数据不足")
        
        # Check 2: No existing position
        no_pos = sym not in held_symbols
        result['checks']['no_existing_position'] = no_pos
        if not no_pos:
            result['auto_pass'] = False
            result['fail_reasons'].append("已有持仓")
        
        # Check 5: Correlation risk
        corr_buy = info.get('correlation', {}).get('BUY', {}).get('can_open', True)
        corr_sell = info.get('correlation', {}).get('SELL', {}).get('can_open', True)
        corr_ok = corr_buy and corr_sell
        result['checks']['correlation_ok'] = corr_ok
        if not corr_ok:
            result['auto_pass'] = False
            result['fail_reasons'].append("相关性风险超限")
        
        # Checks 3 & 4: Need Round 1 analysis
        result['checks']['trend_direction'] = "NEEDS_ROUND1"
        result['checks']['h1_structure'] = "NEEDS_ROUND1"
        
        tradegate['candidates'][sym] = result
        
        if not result['auto_pass']:
            tradegate['summary']['auto_failed'].append({"symbol": sym, "reasons": result['fail_reasons']})
        else:
            tradegate['summary']['needs_round1'].append(sym)

    # Write log
    os.makedirs(os.path.join(TRIUMVIRATE_DIR, "logs", "scans"), exist_ok=True)
    tg_path = os.path.join(TRIUMVIRATE_DIR, "logs", "scans", f"{ts}_tradegate.json")
    with open(tg_path, 'w', encoding='utf-8') as f:
        json.dump(tradegate, f, indent=2, ensure_ascii=False)

    print(json.dumps(tradegate, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
