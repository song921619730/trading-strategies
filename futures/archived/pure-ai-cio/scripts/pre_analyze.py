"""
Pure AI CIO Strategy - Pre-Analysis Engine
Magic Number: 234003

Purpose: Fetches market data from MT5, calculates ATR, lot sizes,
and includes meta time context for CIO strategy decisions.

Usage: python pre_analyze.py
"""
import MetaTrader5 as mt5
import sys
import json
import os
from datetime import datetime, timezone, timedelta

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

SYMBOLS = {
    "XAUUSD": "XAUUSDm",
    "XAGUSD": "XAGUSDm",
    "USTEC": "USTECm",
    "US30": "US30m",
    "US500": "US500m",
    "JP225": "JP225m",
    "HK50": "HK50m",
    "USOIL": "USOILm",
    "UKOIL": "UKOILm",
    "EURUSD": "EURUSDm",
    "GBPUSD": "GBPUSDm",
    "USDJPY": "USDJPYm",
    "AUDUSD": "AUDUSDm",
    "USDCHF": "USDCHFm",
}

CORRELATION_GROUPS = [
    ["EURUSD", "GBPUSD", "AUDUSD"],
    ["USDJPY", "USDCHF"],
    ["USOIL", "UKOIL"],
    ["USTEC", "US500", "US30"],
]

ATR_SL_MULTIPLIER = 1.5
ATR_TP_MULTIPLIER = 3.0

CST = timezone(timedelta(hours=8))


def connect():
    if not mt5.initialize(path=MT5_PATH):
        print(json.dumps({"error": f"MT5 init failed: {mt5.last_error()}"}))
        sys.exit(1)


def disconnect():
    mt5.shutdown()


def calculate_atr(candles, period=14):
    if len(candles) < period + 1:
        return 0.0
    trs = []
    trs.append(candles[0]["high"] - candles[0]["low"])
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period


def calculate_sr(candles, lookback=14):
    if len(candles) < 2:
        return 0.0, 0.0
    subset = candles[-lookback:] if len(candles) >= lookback else candles
    highs = [c["high"] for c in subset]
    lows = [c["low"] for c in subset]
    return min(lows), max(highs)


def get_ohlcv(symbol_code: str, timeframe: str = "H1", count: int = 50):
    sym = SYMBOLS.get(symbol_code)
    if not sym:
        return {"error": f"Unknown symbol: {symbol_code}"}
    tf_map = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
        "MN": mt5.TIMEFRAME_MN1,
    }
    tf = tf_map.get(timeframe)
    if not tf:
        return {"error": f"Unknown timeframe: {timeframe}"}
    mt5.symbol_select(sym, True)
    rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
    if rates is None or len(rates) == 0:
        return {"error": f"No data for {symbol_code}"}
    candles = []
    for r in rates:
        candles.append({
            "time": datetime.fromtimestamp(r["time"]).strftime("%Y-%m-%d %H:%M"),
            "open": round(r["open"], 5),
            "high": round(r["high"], 5),
            "low": round(r["low"], 5),
            "close": round(r["close"], 5),
            "tick_volume": int(r["tick_volume"]),
        })
    return candles


def get_d1_candle(symbol_code: str):
    """Get the latest D1 candle for session status check."""
    candles = get_ohlcv(symbol_code, "D1", 3)
    if isinstance(candles, list) and len(candles) > 0:
        return candles[-1]
    return None


def calculate_lot_size(symbol_code: str, atr: float, equity: float, risk_pct: float = 0.05):
    sym = SYMBOLS.get(symbol_code)
    if not sym or atr <= 0:
        return None
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if not info or not tick:
        return None

    digits = info.digits
    tick_size = info.trade_tick_size if info.trade_tick_size > 0 else info.point
    tick_value = info.trade_tick_value
    current_price = tick.ask
    if tick_value == 0 or tick_value is None:
        tick_value = info.trade_contract_size * info.point

    sl_distance = atr * ATR_SL_MULTIPLIER
    tp_distance = atr * ATR_TP_MULTIPLIER
    risk_amount = equity * risk_pct
    sl_ticks = sl_distance / tick_size if tick_size > 0 else 1
    risk_per_lot = sl_ticks * tick_value

    if risk_per_lot <= 0:
        lot = info.volume_min
    else:
        lot = risk_amount / risk_per_lot

    lot = round(lot / info.volume_step) * info.volume_step
    lot = max(info.volume_min, min(info.volume_max, lot))
    lot = round(lot, 2)

    SYMBOL_CATEGORY = {
        "EURUSD": "forex", "GBPUSD": "forex", "USDJPY": "forex",
        "AUDUSD": "forex", "USDCHF": "forex",
        "XAUUSD": "metal", "XAGUSD": "metal",
        "USOIL": "oil", "UKOIL": "oil",
        "USTEC": "index", "US30": "index", "US500": "index",
        "JP225": "index", "HK50": "index",
    }
    CATEGORY_MAX_LOT = {
        "forex": 0.50, "metal": 0.10, "oil": 0.20, "index": 2.00,
    }
    category = SYMBOL_CATEGORY.get(symbol_code, "forex")
    max_cat_lot = CATEGORY_MAX_LOT.get(category, 5.0)
    lot = min(lot, max_cat_lot)

    rr = round(ATR_TP_MULTIPLIER / ATR_SL_MULTIPLIER, 1)

    sl_buy = round(current_price - sl_distance, digits)
    tp_buy = round(current_price + tp_distance, digits)
    sl_sell = round(current_price + sl_distance, digits)
    tp_sell = round(current_price - tp_distance, digits)

    return {
        "recommended_lot": lot,
        "current_price": round(current_price, digits),
        "atr": round(atr, digits),
        "sl_distance": round(sl_distance, digits),
        "tp_distance": round(tp_distance, digits),
        "risk_usd": round(risk_amount, 2),
        "buy_scenario": {"sl": sl_buy, "tp": tp_buy, "rr": rr},
        "sell_scenario": {"sl": sl_sell, "tp": tp_sell, "rr": rr},
    }


def check_correlation(symbol_code: str, direction: str, open_positions: list) -> dict:
    held_symbols = [p["symbol"] for p in open_positions]
    held_directions = {p["symbol"]: p["type"] for p in open_positions}
    for group in CORRELATION_GROUPS:
        if symbol_code in group:
            held_in_group = []
            group_directions = []
            for s in group:
                if s in held_symbols:
                    direction = held_directions[s]
                    held_in_group.append(f"{s}({direction})")
                    group_directions.append(direction)
            if group_directions:
                existing_dir = group_directions[0]
                if existing_dir != direction:
                    return {"can_open": False, "reason": f"Correlation direction conflict: {', '.join(held_in_group)}", "held_in_group": held_in_group}
            if len(held_in_group) >= 2:
                return {"can_open": False, "reason": f"Max 2 positions in group: {', '.join(held_in_group)}", "held_in_group": held_in_group}
            break
    return {"can_open": True, "reason": "OK", "held_in_group": []}


def get_trading_session(cst_now):
    """Determine current trading session based on CST time."""
    hour = cst_now.hour
    if 0 <= hour < 7:
        return "悉尼/东京盘 (低流动性)"
    elif 7 <= hour < 12:
        return "亚盘 (Asian Session)"
    elif 12 <= hour < 15:
        return "欧盘早盘 (European Open)"
    elif 15 <= hour < 20:
        return "美盘 (US Session)"
    elif 20 <= hour < 23:
        return "美盘尾盘/亚盘夜盘"
    else:
        return "悉尼/东京盘 (低流动性)"


def main():
    connect()
    try:
        # Meta: Time context
        cst_now = datetime.now(CST)
        day_names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
        day_of_week = day_names[cst_now.weekday() + 1] if cst_now.weekday() < 5 else ("周六" if cst_now.weekday() == 5 else "周日")
        
        # D1 candle status check (use XAUUSD as reference)
        d1_ref = get_d1_candle("XAUUSD")
        d1_status = "新蜡烛形成中"
        if d1_ref:
            d1_time = datetime.strptime(d1_ref["time"], "%Y-%m-%d %H:%M")
            d1_time_cst = d1_time.replace(tzinfo=CST)
            hours_elapsed = (cst_now - d1_time_cst).total_seconds() / 3600
            if hours_elapsed < 2:
                d1_status = f"新蜡烛形成中 (仅{hours_elapsed:.1f}H)"
            elif hours_elapsed < 12:
                d1_status = f"实体形成中 ({hours_elapsed:.1f}H)"
            else:
                d1_status = f"实体已成熟 ({hours_elapsed:.1f}H)"

        meta = {
            "current_time_cst": cst_now.strftime("%Y-%m-%d %H:%M:%S"),
            "day_of_week": day_of_week,
            "trading_session": get_trading_session(cst_now),
            "d1_session": d1_status,
            "magic_number": 234003,
            "phase": "B",
        }

        # Account info
        acct = mt5.account_info()
        if not acct:
            print(json.dumps({"error": "No account info"}))
            return

        equity = round(acct.equity, 2)
        balance = round(acct.balance, 2)
        risk_per_trade = round(equity * 0.05, 2)
        account_type = "模拟" if "trial" in acct.server.lower() else "实盘"

        # Open positions with SL management
        positions = mt5.positions_get()
        open_positions = []
        if positions:
            for pos in positions:
                sym_clean = pos.symbol.replace("m", "") if pos.symbol.endswith("m") else pos.symbol
                atr = 0.0
                h1 = get_ohlcv(sym_clean, "H1", 50)
                if isinstance(h1, list) and len(h1) > 14:
                    atr = calculate_atr(h1, 14)

                current_sl = pos.sl if pos.sl > 0 else 0.0
                current_tp = pos.tp if pos.tp > 0 else 0.0
                entry = pos.price_open
                current_price = pos.price_current
                p_type = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"

                suggested_sl = current_sl
                sl_reason = ""
                profit_progress = 0.0

                if atr > 0:
                    if p_type == "BUY":
                        profit_dist = current_price - entry
                        tp_dist = current_tp - entry if current_tp > entry else (atr * 3.0)
                    else:
                        profit_dist = entry - current_price
                        tp_dist = entry - current_tp if current_tp > 0 else (atr * 3.0)
                    profit_progress = profit_dist / tp_dist if tp_dist > 0 else 0

                    if p_type == "BUY":
                        trail_sl = current_price - (atr * 1.5)
                        if abs(current_price - trail_sl) < atr * 1.0:
                            trail_sl = current_price - (atr * 1.0)
                        if profit_progress >= 0.50:
                            breakeven_sl = entry + (atr * 0.1)
                            suggested_sl = max(breakeven_sl, trail_sl)
                            if suggested_sl > current_sl:
                                sl_reason = f"Breakeven ({profit_progress*100:.0f}%): BE={breakeven_sl:.2f}, Trail={trail_sl:.2f}"
                        elif trail_sl > current_sl:
                            suggested_sl = trail_sl
                            sl_reason = f"Trailing ({profit_progress*100:.0f}%)"
                    else:
                        trail_sl = current_price + (atr * 1.5)
                        if abs(current_price - trail_sl) < atr * 1.0:
                            trail_sl = current_price + (atr * 1.0)
                        if profit_progress >= 0.50:
                            breakeven_sl = entry - (atr * 0.1)
                            suggested_sl = min(breakeven_sl, trail_sl)
                            if suggested_sl < current_sl or current_sl == 0:
                                sl_reason = f"Breakeven ({profit_progress*100:.0f}%): BE={breakeven_sl:.2f}, Trail={trail_sl:.2f}"
                        elif trail_sl < current_sl or current_sl == 0:
                            suggested_sl = trail_sl
                            sl_reason = f"Trailing ({profit_progress*100:.0f}%)"

                if suggested_sl != 0:
                    sym_info = mt5.symbol_info(pos.symbol)
                    if sym_info:
                        suggested_sl = round(suggested_sl, sym_info.digits)

                open_positions.append({
                    "ticket": pos.ticket,
                    "symbol": sym_clean,
                    "type": p_type,
                    "volume": pos.volume,
                    "open_price": round(entry, 5),
                    "sl": round(current_sl, 5) if current_sl > 0 else None,
                    "tp": round(current_tp, 5) if current_tp > 0 else None,
                    "current_price": round(current_price, 5),
                    "profit": round(pos.profit, 2),
                    "sl_management": {
                        "atr_14": round(atr, 5),
                        "suggested_sl": suggested_sl,
                        "action": "MODIFY" if (suggested_sl != current_sl and suggested_sl > 0) else "HOLD",
                        "reason": sl_reason,
                        "profit_progress": round(profit_progress, 3) if atr > 0 else 0,
                    }
                })

        # Symbol analysis
        analysis = {}
        FOREX_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"}

        for code in SYMBOLS:
            if code in FOREX_SYMBOLS:
                atr_candles = get_ohlcv(code, "H4", 50)
                sr_candles = get_ohlcv(code, "H1", 50)
            else:
                atr_candles = get_ohlcv(code, "H1", 50)
                sr_candles = atr_candles

            atr_14 = 0.0
            sr_support = 0.0
            sr_resistance = 0.0
            if isinstance(atr_candles, list):
                atr_14 = round(calculate_atr(atr_candles, 14), 5)
            if isinstance(sr_candles, list):
                sr_support, sr_resistance = calculate_sr(sr_candles, 14)
                sr_support = round(sr_support, 5)
                sr_resistance = round(sr_resistance, 5)

            min_sl_distance = {
                "EURUSD": 0.0030, "GBPUSD": 0.0030, "USDJPY": 0.30,
                "AUDUSD": 0.0025, "USDCHF": 0.0025,
                "XAUUSD": 15.0, "XAGUSD": 0.50,
                "USOIL": 1.50, "UKOIL": 1.50,
            }
            min_sl = min_sl_distance.get(code, 0)
            if atr_14 * 1.5 < min_sl:
                atr_14 = max(atr_14, min_sl / 1.5)

            trade_params = calculate_lot_size(code, atr_14, equity)
            already_held = any(p["symbol"] == code for p in open_positions)
            corr_buy = check_correlation(code, "BUY", open_positions)
            corr_sell = check_correlation(code, "SELL", open_positions)

            # Get H1 and D1 candle summary for CIO strategy
            h1_candles = get_ohlcv(code, "H1", 20)
            d1_candles = get_ohlcv(code, "D1", 10)

            analysis[code] = {
                "already_held": already_held,
                "correlation": {"BUY": corr_buy, "SELL": corr_sell},
                "indicators": {
                    "atr_14": atr_14,
                    "support_14": sr_support,
                    "resistance_14": sr_resistance,
                },
                "trade_params": trade_params,
                "h1_summary": {
                    "candle_count": len(h1_candles) if isinstance(h1_candles, list) else 0,
                    "latest_close": h1_candles[-1]["close"] if isinstance(h1_candles, list) and len(h1_candles) > 0 else None,
                    "latest_time": h1_candles[-1]["time"] if isinstance(h1_candles, list) and len(h1_candles) > 0 else None,
                },
                "d1_summary": {
                    "candle_count": len(d1_candles) if isinstance(d1_candles, list) else 0,
                    "latest_close": d1_candles[-1]["close"] if isinstance(d1_candles, list) and len(d1_candles) > 0 else None,
                    "latest_time": d1_candles[-1]["time"] if isinstance(d1_candles, list) and len(d1_candles) > 0 else None,
                },
            }

        output = {
            "meta": meta,
            "account": {
                "equity": equity,
                "balance": balance,
                "risk_per_trade": risk_per_trade,
                "risk_pct": 0.05,
                "account_type": account_type,
            },
            "open_positions": open_positions,
            "symbols": analysis,
            "rules": {
                "atr_sl_multiplier": ATR_SL_MULTIPLIER,
                "atr_tp_multiplier": ATR_TP_MULTIPLIER,
                "target_rr": round(ATR_TP_MULTIPLIER / ATR_SL_MULTIPLIER, 1),
                "min_rr": 1.0,
            },
        }

        # Save
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(data_dir, exist_ok=True)
        output_path = os.path.join(data_dir, "pre_analyze_latest.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(json.dumps(output, indent=2))

    finally:
        disconnect()


if __name__ == "__main__":
    main()
