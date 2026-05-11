"""
Cron Health Check - verifies MT5 connectivity and data freshness.
Outputs: health_status.json
"""
import MetaTrader5 as mt5
import json, os
from datetime import datetime, timezone, timedelta

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
CST = timezone(timedelta(hours=8))

def main():
    status = {"timestamp": datetime.now(CST).isoformat(), "mt5_connected": False, "data_fresh": False, "errors": []}
    
    # Check MT5
    if not mt5.initialize(path=MT5_PATH):
        status["errors"].append("MT5 initialization failed")
        print(json.dumps(status))
        return
    
    status["mt5_connected"] = True
    
    # Check account
    acct = mt5.account_info()
    if not acct:
        status["errors"].append("Cannot get account info")
    else:
        status["account"] = {
            "balance": round(acct.balance, 2),
            "equity": round(acct.equity, 2),
            "positions": len(mt5.positions_get() or [])
        }
        status["data_fresh"] = True
    
    # Check data freshness
    pa_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "pre_analyze_latest.json")
    if os.path.exists(pa_path):
        import time
        age_min = (time.time() - os.path.getmtime(pa_path)) / 60
        status["pre_analyze_age_minutes"] = round(age_min, 1)
        if age_min > 5:
            status["errors"].append(f"pre_analyze.json is {age_min:.0f} minutes old — STALE DATA!")
    
    mt5.shutdown()
    print(json.dumps(status, indent=2))

if __name__ == "__main__":
    main()
