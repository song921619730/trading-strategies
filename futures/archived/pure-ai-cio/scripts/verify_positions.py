"""
Position Verification Script - Pure AI CIO
Verifies AI-reported positions against actual MT5 positions.
Outputs: position_check.json
"""
import MetaTrader5 as mt5
import json
import os
from datetime import datetime, timezone, timedelta

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MAGIC_NUMBER = 234003
CST = timezone(timedelta(hours=8))

def main():
    if not mt5.initialize(path=MT5_PATH):
        print(json.dumps({"error": "MT5 init failed"}))
        return

    try:
        # Get all positions
        positions = mt5.positions_get()
        actual_positions = []

        if positions:
            for pos in positions:
                # Filter by magic number if possible
                actual_positions.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                    "volume": pos.volume,
                    "open_price": round(pos.price_open, 5),
                    "sl": round(pos.sl, 5) if pos.sl > 0 else None,
                    "tp": round(pos.tp, 5) if pos.tp > 0 else None,
                    "current_price": round(pos.price_current, 5),
                    "profit": round(pos.profit, 2),
                    "magic": pos.magic,
                    "comment": pos.comment,
                })

        # Account info
        acct = mt5.account_info()
        account = {
            "balance": round(acct.balance, 2) if acct else 0,
            "equity": round(acct.equity, 2) if acct else 0,
            "margin": round(acct.margin, 2) if acct else 0,
            "position_count": len(actual_positions),
        }

        output = {
            "timestamp": datetime.now(CST).isoformat(),
            "account": account,
            "actual_positions": actual_positions,
        }

        # Save
        output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "position_check.json")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(json.dumps(output, indent=2))
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
