"""
Triumvirate — 交易执行脚本 (Magic 234004)

职责: 严格执行 AI 指令，不包含任何决策逻辑
日志: 每次操作记录到 logs/trades/ + stdout
"""
import MetaTrader5 as mt5
import sys
import os
import json
from datetime import datetime, timezone, timedelta

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MAGIC_NUMBER = 234004

CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)

SYMBOLS = {
    "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD",
    "USTEC": "USTEC", "US30": "US30", "US500": "US500",
    "JP225": "JP225", "HK50": "HK50",
    "USOIL": "USOIL", "UKOIL": "UKOIL",
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY", "AUDUSD": "AUDUSD", "USDCHF": "USDCHF",
}


def log_result(result: dict, action_type: str):
    """Write result to logs/trades/ with timestamp"""
    log_dir = os.path.join(TRIUMVIRATE_DIR, "logs", "trades")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M%S")

    # Determine filename based on action
    if action_type == "open":
        symbol = result.get("symbol", "unknown")
        direction = result.get("direction", "unknown")
        filename = f"{timestamp}_OPEN_{symbol}_{direction}.json"
    else:
        ticket = result.get("ticket", result.get("order", "unknown"))
        filename = f"{timestamp}_{action_type.upper()}_ticket{ticket}.json"

    filepath = os.path.join(log_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # Also append to running trade log
    running_log = os.path.join(log_dir, "trade_history.jsonl")
    entry = {
        "timestamp": datetime.now(CST).isoformat(),
        "action": action_type,
        "data": result,
    }
    try:
        with open(running_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def connect():
    if not mt5.initialize(path=MT5_PATH):
        err = {"error": f"MT5 init failed: {mt5.last_error()}"}
        print(json.dumps(err))
        log_result(err, "init_failed")
        sys.exit(1)


def disconnect():
    mt5.shutdown()


def open_order(symbol_code: str, direction: str, volume: float,
               sl: float = None, tp: float = None, comment: str = "TRIUMVIRATE_234004"):
    sym = SYMBOLS.get(symbol_code)
    if not sym:
        return {"error": f"Unknown symbol: {symbol_code}"}

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
        request["sl"] = round(sl, mt5.symbol_info(sym).digits)
    if tp:
        request["tp"] = round(tp, mt5.symbol_info(sym).digits)

    result = mt5.order_send(request)
    if result is None:
        return {"error": "order_send returned None", "last_error": mt5.last_error()}

    response = {
        "action": "open",
        "retcode": result.retcode,
        "order": result.order,
        "deal": result.deal,
        "volume": result.volume,
        "price": result.price,
        "bid": result.bid,
        "ask": result.ask,
        "spread": round(tick.ask - tick.bid, 5),
        "slippage": round(abs(result.price - price), 5),
        "comment": result.comment,
        "symbol": symbol_code,
        "direction": direction,
        "sl": sl,
        "tp": tp,
        "status": "SUCCESS" if result.retcode == 10009 else "FAILED",
    }
    if result.retcode != 10009:
        response["error_detail"] = f"Retcode {result.retcode}: {result.comment}"

    log_result(response, "open")
    return response


def close_position(ticket: int):
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        err = {"error": f"Position {ticket} not found"}
        log_result(err, "close")
        return err

    pos = positions[0]
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        err = {"error": f"No tick data for {pos.symbol}"}
        log_result(err, "close")
        return err

    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "TRIUM_close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    })

    if result is None:
        err = {"error": "order_send returned None"}
        log_result(err, "close")
        return err

    response = {
        "action": "close",
        "ticket": ticket,
        "retcode": result.retcode,
        "status": "SUCCESS" if result.retcode == 10009 else "FAILED",
        "volume": result.volume,
        "price": result.price,
        "profit": result.profit if hasattr(result, 'profit') else None,
    }
    log_result(response, "close")
    return response


def modify_position(ticket: int, sl: float = None, tp: float = None):
    if sl is None and tp is None:
        return {"error": "Must provide at least sl or tp"}

    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return {"error": f"Position {ticket} not found"}
    pos = positions[0]

    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": ticket,
        "sl": float(sl) if sl is not None else 0.0,
        "tp": float(tp) if tp is not None else 0.0,
    })

    if result is None:
        return {"error": "order_send returned None"}

    response = {
        "action": "modify",
        "ticket": ticket,
        "retcode": result.retcode,
        "status": "SUCCESS" if result.retcode == 10009 else "FAILED",
        "new_sl": sl,
        "new_tp": tp,
    }
    log_result(response, "modify")
    return response


def main():
    connect()
    try:
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
            comment = sys.argv[7] if len(sys.argv) > 7 else "TRIUMVIRATE_234004"
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

        elif cmd == "status":
            # 查询 Magic 234004 所有持仓
            positions = mt5.positions_get(group="*", ticket=0) or []
            my_positions = [p for p in positions if p.magic == MAGIC_NUMBER]
            result = {
                "action": "status",
                "count": len(my_positions),
                "positions": [
                    {
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                        "volume": p.volume,
                        "price": p.price_open,
                        "sl": p.sl,
                        "tp": p.tp,
                        "profit": p.profit,
                        "swap": p.swap,
                        "time": str(p.time),
                    }
                    for p in my_positions
                ]
            }
            log_result(result, "status")

        elif cmd == "history":
            # 查询最近平仓记录
            from_date = datetime.now(CST) - timedelta(days=7)
            deals = mt5.history_deals_get(from_date, datetime.now(CST))
            if deals:
                my_deals = [d for d in deals if d.magic == MAGIC_NUMBER]
                result = {
                    "action": "history",
                    "count": len(my_deals),
                    "deals": [
                        {
                            "deal": d.deal,
                            "order": d.order,
                            "symbol": d.symbol,
                            "type": "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL" if d.type == mt5.DEAL_TYPE_SELL else "UNKNOWN",
                            "volume": d.volume,
                            "price": d.price,
                            "profit": d.profit,
                            "commission": d.commission,
                            "swap": d.swap,
                            "time": str(d.time),
                        }
                        for d in my_deals
                    ]
                }
            else:
                result = {"action": "history", "count": 0, "deals": []}
            log_result(result, "history")

        else:
            result = {"error": f"Unknown command: {cmd}"}

        print(json.dumps(result, indent=2))

    finally:
        disconnect()


if __name__ == "__main__":
    main()
