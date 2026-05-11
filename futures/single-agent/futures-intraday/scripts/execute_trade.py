#!/usr/bin/env python3
"""
execute_trade.py — MT5 交易执行

读取 signal_scanner.py 的输出 JSON，检查风控后执行交易。

用法:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/scripts/execute_trade.py \\
    --signal '{"signal_json"...}'
"""
import json
import os
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "strategies.json")
TRADE_LOG_DIR = os.path.join(BASE_DIR, "logs", "trades")

# ─── MT5 连接 ───
def connect_mt5():
    import MetaTrader5 as mt5
    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    
    if not mt5.initialize(path=path, login=login, password=password, server=server):
        return None, f"MT5 init failed: {mt5.last_error()}"
    
    # 检查自动交易
    term = mt5.terminal_info()
    acct = mt5.account_info()
    if not term or not acct:
        mt5.shutdown()
        return None, "Cannot get terminal/account info"
    if not term.trade_allowed:
        mt5.shutdown()
        return None, "Trading disabled in terminal"
    if not acct.trade_expert:
        mt5.shutdown()
        return None, "Expert trading disabled on this account"
    
    return mt5, {"balance": acct.balance, "equity": acct.equity, "login": acct.login}


# ─── 风控检查 ───
def check_risk(mt5, signal: dict, risk_cfg: dict, magic: int) -> tuple[bool, str]:
    """返回 (allowed, reason)"""
    symbol = signal["symbol"]
    direction = signal["direction"]
    strategy_id = signal["strategy_id"]
    
    # 获取已有持仓
    positions = mt5.positions_get()
    existing = [p for p in (positions or []) if p.magic == magic]
    
    # 总持仓数限制
    max_total = risk_cfg.get("max_total_positions", 4)
    if len(existing) >= max_total:
        return False, f"Max total positions ({max_total}) reached"
    
    # 品种组限制
    sym_groups = risk_cfg.get("pos_validation", {}).get("symposium_groups", {})
    base_symbol = symbol.replace("m", "")
    my_group = None
    for gname, gsyms in sym_groups.items():
        if base_symbol in gsyms:
            my_group = gname
            break
    
    if my_group:
        for p in existing:
            for gname, gsyms in sym_groups.items():
                if my_group == gname:
                    continue  # 同一组，下面的逻辑会处理
            p_base = p.symbol.replace("m", "")
            if p_base in sym_groups.get(my_group, []):
                return False, f"已有同组持仓 ({my_group}): {p.symbol}"
    
    # 单品种重复检查
    for p in existing:
        if p.symbol == symbol:
            return False, f"已有同品种持仓: {symbol}"
    
    return True, "risk check passed"


def calculate_lot_size(mt5, symbol: str, current_price: float, risk_pct: float, equity: float) -> float:
    """根据风险百分比计算手数"""
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return sym_info.volume_min if hasattr(sym_info, 'volume_min') else 0.01
    
    # 使用交易品种规格计算
    tick_value = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size
    point = sym_info.point
    volume_min = sym_info.volume_min
    volume_step = sym_info.volume_step
    volume_max = sym_info.volume_max
    
    # 假设 SL = ATR (默认 3 倍 tick_size 保守值，实际由 AI 确定)
    # 这里用固定 0.5% 作为 SL 距离雏形
    sl_distance = current_price * 0.005  # 0.5% SL
    risk_per_lot = (sl_distance / point) * tick_value
    target_lots = (equity * risk_pct) / risk_per_lot if risk_per_lot > 0 else volume_min
    
    # 归一化到 volume_step
    lots = max(volume_min, min(volume_max, round(target_lots / volume_step) * volume_step))
    return round(lots, 2)


def place_order(mt5, signal: dict, lot_size: float, magic: int) -> dict:
    """执行市价单"""
    import MetaTrader5 as mt5
    symbol = signal["symbol"]
    direction = signal["direction"]
    current_price = signal["current_price"]
    is_buy = direction == "long"
    
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"error": f"Cannot get tick for {symbol}"}
    
    price = tick.ask if is_buy else tick.bid
    
    # 计算 SL/TP
    sym_info = mt5.symbol_info(symbol)
    atr = signal.get("atr", current_price * 0.005)
    sl_distance = atr * 2  # 2 × ATR
    tp_distance = sl_distance * 2  # RR=2
    
    sl = price - sl_distance if is_buy else price + sl_distance
    tp = price + tp_distance if is_buy else price - tp_distance
    
    # 标准化价格
    digits = sym_info.digits if sym_info else 5
    sl = round(sl, digits)
    tp = round(tp, digits)
    price = round(price, digits)
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": magic,
        "comment": f"algo-v1-{signal.get('strategy_id','')[:6]}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    
    result = mt5.order_send(request)
    if result.retcode != 10009:
        return {
            "error": f"Order failed: {result.retcode} - {result.comment}",
            "request": {k: str(v) for k, v in request.items()}
        }
    
    return {
        "success": True,
        "ticket": result.order,
        "symbol": symbol,
        "direction": direction,
        "volume": lot_size,
        "price": price,
        "sl": sl,
        "tp": tp,
        "strategy_id": signal.get("strategy_id"),
        "dealt_at_utc": datetime.utcnow().isoformat(),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal", type=str, required=True, help="Signal JSON string")
    parser.add_argument("--lot-size", type=float, default=None, help="Override lot size")
    parser.add_argument("--dry-run", action="store_true", help="Print what would do")
    args = parser.parse_args()
    
    # 解析信号
    signal = json.loads(args.signal)
    
    # 加载配置
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    risk_cfg = cfg.get("risk", {})
    magic = cfg.get("magic_number", 234010)
    
    # 连接 MT5
    mt5, account = connect_mt5()
    if mt5 is None:
        result = {"error": account, "signal": signal}
        print(json.dumps(result, ensure_ascii=False))
        return
    
    try:
        # 风控检查
        allowed, reason = check_risk(mt5, signal, risk_cfg, magic)
        if not allowed:
            result = {"risk_blocked": True, "reason": reason, "signal": signal}
            print(json.dumps(result, ensure_ascii=False))
            return
        
        # 计算手数
        if args.lot_size:
            lot_size = args.lot_size
        else:
            lot_size = calculate_lot_size(
                mt5, signal["symbol"], signal["current_price"],
                risk_cfg.get("risk_per_trade_pct", 0.02),
                account["equity"]
            )
        
        if args.dry_run:
            result = {
                "dry_run": True,
                "signal": signal,
                "lot_size": lot_size,
                "equity": account["equity"],
                "risk_check": reason,
            }
            print(json.dumps(result, ensure_ascii=False))
            return
        
        # 执行
        trade_result = place_order(mt5, signal, lot_size, magic)
        result = {
            "execution": trade_result,
            "lot_size": lot_size,
            "signal": signal,
        }
        
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        # 保存日志
        os.makedirs(TRADE_LOG_DIR, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(TRADE_LOG_DIR, f"trade_{ts}.json")
        with open(log_file, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[LOG] Saved to {log_file}", file=sys.stderr)
        
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
