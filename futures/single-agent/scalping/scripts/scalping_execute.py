#!/usr/bin/env python3
"""
scalping_execute.py — Scalping M1/M5 交易执行脚本 (Magic 234011)

职责: 执行 M1/M5 级别开仓/平仓/改单，SL/TP 基于 M5 ATR(14)
与 H1 策略（Magic 234010）完全隔离

用法:
  python scalping_execute.py open SYMBOL DIRECTION VOLUME SL TP [COMMENT]
  python scalping_execute.py close TICKET
  python scalping_execute.py modify TICKET [SL] [TP]
  python scalping_execute.py status
  python scalping_execute.py positions
"""
import MetaTrader5 as mt5
import sys
import os
import json
from datetime import datetime, timezone, timedelta

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MAGIC_NUMBER = 234011

CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCALPING_DIR = os.path.dirname(SCRIPT_DIR)

SYMBOLS = {
    "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD",
    "USTEC": "USTEC", "US30": "US30", "US500": "US500",
    "JP225": "JP225", "HK50": "HK50",
    "USOIL": "USOIL", "UKOIL": "UKOIL",
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY", "AUDUSD": "AUDUSD", "USDCHF": "USDCHF",
}

RISK_PER_TRADE_PCT = 0.05   # 单笔风险 5% 净值
SL_ATR_MULTIPLE = 2.5       # Scalping: SL = ATR × 2.5（放宽止损防噪音扫）
TP_ATR_MULTIPLE = 4.0       # Scalping: TP = ATR × 4.0（RR=1.6，给 spread 留缓冲）
CONFIG_PATH = os.path.join(SCALPING_DIR, "config", "scalping_strategies.json")


# ─── 日志 ───
def log_result(result: dict, action_type: str):
    log_dir = os.path.join(SCALPING_DIR, "logs", "executions")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M%S")

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


# ─── MT5 操作 ───
def connect():
    if not mt5.initialize(path=MT5_PATH):
        err = {"error": f"MT5 init failed: {mt5.last_error()}"}
        print(json.dumps(err))
        log_result(err, "init_failed")
        sys.exit(1)


def disconnect():
    mt5.shutdown()


# ─── 风控截断（Scalping 版，用 M5/M1 ATR 计算） ───
def _cap_volume_by_risk(symbol_code: str, price: float, sl: float,
                        direction: str, volume: float) -> tuple:
    """
    按 5% 净值风险上限截断手数。
    用 SL 距离计算，如果 SL 未提供则尝试获取 M5 ATR
    """
    try:
        acct = mt5.account_info()
        if not acct:
            return volume, volume, False
        equity = acct.equity
        if equity <= 0:
            return volume, volume, False

        sym = SYMBOLS.get(symbol_code)
        if not sym:
            return volume, volume, False
        sym_info = mt5.symbol_info(sym)
        if not sym_info:
            return volume, volume, False

        tick_value = sym_info.trade_tick_value
        point = sym_info.point
        vol_min = sym_info.volume_min
        vol_step = sym_info.volume_step
        vol_max = sym_info.volume_max

        if point <= 0 or tick_value <= 0:
            return volume, volume, False

        if sl and price > 0:
            sl_distance = abs(price - sl)
        else:
            # Scalping 后备: 用 M5 ATR × 1.0
            bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 20)
            if bars is None or len(bars) < 14:
                return volume, volume, False
            atr = sum(abs(b['high'] - b['low']) for b in bars[-14:]) / 14
            sl_distance = atr * SL_ATR_MULTIPLE

        if sl_distance <= 0:
            return volume, volume, False

        risk_per_lot = (sl_distance / point) * tick_value
        if risk_per_lot <= 0:
            return volume, volume, False

        max_lot_raw = (equity * RISK_PER_TRADE_PCT) / risk_per_lot
        max_lot = max(vol_min, min(vol_max,
                                   round(max_lot_raw / vol_step) * vol_step))

        capped = min(float(volume), round(max_lot, 2))
        was_capped = capped < float(volume)
        return round(capped, 2), float(volume), was_capped

    except Exception:
        return volume, volume, False


# ─── 开仓 ───
def open_order(symbol_code: str, direction: str, volume: float,
               sl: float = None, tp: float = None, comment: str = "SCALP_234011"):
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

    # 风控截断
    capped_vol, orig_vol, was_capped = _cap_volume_by_risk(
        symbol_code, price, sl, direction, volume
    )
    if was_capped:
        warn = (f"[RISK CAP] {symbol_code} {direction} vol={orig_vol}→{capped_vol} "
                f"(exceeds 5% risk limit)")
        print(warn, file=sys.stderr)
        log_result({"warning": warn, "original_volume": orig_vol,
                     "capped_volume": capped_vol}, "risk_cap")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": float(capped_vol),
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


# ─── 平仓 ───
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
        "comment": "SCALP_close",
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


# ─── 修改 SL/TP ───
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


# ─── 查询持仓 ───
def list_positions():
    positions = mt5.positions_get(group="*") or []
    my_positions = [p for p in positions if p.magic == MAGIC_NUMBER]
    result = {
        "action": "positions",
        "magic": MAGIC_NUMBER,
        "count": len(my_positions),
        "positions": [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "time": str(p.time),
            }
            for p in my_positions
        ],
    }
    return result


# ─── 主入口 ───
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
            comment = sys.argv[7] if len(sys.argv) > 7 else "SCALP_234011"
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
            positions = mt5.positions_get(group="*") or []
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
                        "profit": p.profit,
                        "sl": p.sl,
                        "tp": p.tp,
                    }
                    for p in my_positions
                ],
            }

        elif cmd == "positions":
            result = list_positions()

        else:
            result = {"error": f"Unknown command: {cmd}"}

        print(json.dumps(result, ensure_ascii=False, indent=2))

    finally:
        disconnect()


if __name__ == "__main__":
    main()
