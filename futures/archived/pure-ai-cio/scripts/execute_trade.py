"""
Pure AI CIO Strategy - Trade Executor
Magic Number: 234003

Purpose: Execute trades as instructed by AI. No decision-making here.
"""
import MetaTrader5 as mt5
import sys
import json
from datetime import datetime

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MAGIC_NUMBER = 234003

SYMBOLS = {
    "XAUUSD": "XAUUSDm", "XAGUSD": "XAGUSDm",
    "USTEC": "USTECm", "US30": "US30m", "US500": "US500m",
    "JP225": "JP225m", "HK50": "HK50m",
    "USOIL": "USOILm", "UKOIL": "UKOILm",
    "EURUSD": "EURUSDm", "GBPUSD": "GBPUSDm",
    "USDJPY": "USDJPYm", "AUDUSD": "AUDUSDm", "USDCHF": "USDCHFm",
}


def connect():
    if not mt5.initialize(path=MT5_PATH):
        print(json.dumps({"error": f"MT5 init failed: {mt5.last_error()}"}))
        sys.exit(1)


def disconnect():
    mt5.shutdown()


def get_mt5_symbol(symbol_code: str):
    sym = SYMBOLS.get(symbol_code)
    if not sym:
        return None, f"Unknown symbol: {symbol_code}"
    return sym, None


def round_price(price: float, symbol_code: str) -> float:
    sym, _ = get_mt5_symbol(symbol_code)
    if sym:
        info = mt5.symbol_info(sym)
        if info:
            return round(price, info.digits)
    return round(price, 5)


def open_order(symbol_code: str, direction: str, volume: float,
               sl: float = None, tp: float = None, comment: str = "CIO_234003"):
    sym, err = get_mt5_symbol(symbol_code)
    if err:
        return {"error": err}

    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if not tick:
        return {"error": f"No tick data for {symbol_code}"}

    if direction.upper() in ["BUY", "LONG"]:
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY
    elif direction.upper() in ["SELL", "SHORT"]:
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        return {"error": f"Invalid direction: {direction}"}

    price = round_price(price, symbol_code)
    if sl:
        sl = round_price(sl, symbol_code)
    if tp:
        tp = round_price(tp, symbol_code)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": float(volume),
        "type": order_type,
        "price": price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    if sl:
        request["sl"] = sl
    if tp:
        request["tp"] = tp

    result = mt5.order_send(request)
    if result is None:
        return {"error": "order_send returned None", "last_error": mt5.last_error()}

    # Calculate slippage
    actual_price = result.price
    requested_price = price
    slippage_points = abs(actual_price - requested_price)
    spread = tick.ask - tick.bid

    response = {
        "action": "open",
        "retcode": result.retcode,
        "order": result.order,
        "deal": result.deal,
        "volume": result.volume,
        "price": actual_price,
        "bid": result.bid,
        "ask": result.ask,
        "spread": round(spread, 5),
        "slippage": round(slippage_points, 5),
        "comment": result.comment,
        "request_id": result.request_id,
        "symbol": symbol_code,
        "direction": direction,
        "sl": sl,
        "tp": tp,
    }

    if result.retcode != 10009:
        response["status"] = "FAILED"
        response["error_detail"] = f"Retcode {result.retcode}: {result.comment}"
    else:
        response["status"] = "SUCCESS"

    return response


def close_position(ticket: int):
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return {"error": f"Position {ticket} not found"}

    pos = positions[0]
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        return {"error": f"No tick data for {pos.symbol}"}

    if pos.type == mt5.POSITION_TYPE_BUY:
        close_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        close_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "CIO_Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    })

    if result is None:
        return {"error": "order_send returned None"}

    return {
        "action": "close",
        "ticket": ticket,
        "retcode": result.retcode,
        "status": "SUCCESS" if result.retcode == 10009 else "FAILED",
        "comment": result.comment,
        "volume": result.volume,
        "price": result.price,
    }


def modify_position(ticket: int, sl: float = None, tp: float = None):
    if sl is None and tp is None:
        return {"error": "Must provide at least sl or tp"}

    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return {"error": f"Position {ticket} not found"}
    pos = positions[0]

    final_sl = sl if sl is not None else pos.sl
    final_tp = tp if tp is not None else pos.tp
    if final_sl == 0.0:
        final_sl = 0
    if final_tp == 0.0:
        final_tp = 0

    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": ticket,
        "sl": float(final_sl) if final_sl else 0.0,
        "tp": float(final_tp) if final_tp else 0.0,
    })

    if result is None:
        return {"error": "order_send returned None"}

    return {
        "action": "modify",
        "ticket": ticket,
        "retcode": result.retcode,
        "status": "SUCCESS" if result.retcode == 10009 else "FAILED",
        "comment": result.comment,
        "new_sl": sl,
        "new_tp": tp,
    }


def main():
    connect()
    try:
        acct = mt5.account_info()
        if not acct:
            print(json.dumps({"error": "No account info"}))
            return

        if len(sys.argv) < 2:
            print(json.dumps({"error": "No action specified"}))
            return

        cmd = sys.argv[1].lower()

        if cmd == "open":
            if len(sys.argv) < 5:
                print(json.dumps({"error": "Usage: open SYMBOL DIRECTION VOLUME [SL] [TP] [COMMENT]"}))
                return
            symbol = sys.argv[2]
            direction = sys.argv[3]
            volume = float(sys.argv[4])
            sl = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] != "None" else None
            tp = float(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] != "None" else None
            comment = sys.argv[7] if len(sys.argv) > 7 else "CIO_234003"
            result = open_order(symbol, direction, volume, sl, tp, comment)

        elif cmd == "close":
            if len(sys.argv) < 3:
                print(json.dumps({"error": "Usage: close TICKET"}))
                return
            ticket = int(sys.argv[2])
            result = close_position(ticket)

        elif cmd == "modify":
            if len(sys.argv) < 3:
                print(json.dumps({"error": "Usage: modify TICKET [SL] [TP]"}))
                return
            ticket = int(sys.argv[2])
            sl = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != "None" else None
            tp = float(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] != "None" else None
            result = modify_position(ticket, sl, tp)

        else:
            result = {"error": f"Unknown command: {cmd}"}

        print(json.dumps(result, indent=2))

    finally:
        disconnect()


if __name__ == "__main__":
    main()
