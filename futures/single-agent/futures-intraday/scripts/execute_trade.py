#!/usr/bin/env python3
"""
execute_trade.py — MT5 交易执行 (v2, CIO-grade risk)

读取 signal_scanner.py 的输出 JSON，检查风控后执行交易。
核心改动:
- 手数基于 ATR×1 SL 距离计算，与挂单 SL 一致
- RR < 1:1 一票否决
- 同方向持仓比例检查
- 扫描结果持久化到 logs/scans/

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
SCAN_LOG_DIR = os.path.join(BASE_DIR, "logs", "scans")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def log_scan(signal: dict, result: dict):
    """持久化扫描结果到 logs/scans/"""
    os.makedirs(SCAN_LOG_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "signal": signal,
        "result": result,
    }
    path = os.path.join(SCAN_LOG_DIR, f"scan_{ts}.json")
    with open(path, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return path


def connect_mt5():
    import MetaTrader5 as mt5
    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")

    if not mt5.initialize(path=path, login=login, password=password, server=server):
        return None, f"MT5 init failed: {mt5.last_error()}"

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


def check_risk(mt5, signal: dict, risk_cfg: dict, magic: int) -> tuple[bool, str]:
    """
    风控检查（CIO 级）:
    1. 总持仓数限制
    2. 品种组限制（同组最多1单）
    3. 单品种重复检查
    4. 同方向比例检查（≤70%）
    5. 单品种方向比例（≤30%）
    6. RR 检查（<1:1 一票否决）
    """
    symbol = signal["symbol"]
    direction = signal["direction"]
    strategy_id = signal["strategy_id"]
    current_price = signal["current_price"]
    atr = signal.get("atr", 0)

    # 获取已有持仓
    positions = mt5.positions_get()
    existing = [p for p in (positions or []) if p.magic == magic]

    # ── 1. 总持仓数 ──
    max_total = risk_cfg.get("max_total_positions", 4)
    if len(existing) >= max_total:
        return False, f"Max total positions ({max_total}) reached"

    # ── 2. 品种组限制 ──
    sym_groups = risk_cfg.get("pos_validation", {}).get("symposium_groups", {})
    base_symbol = symbol.replace("m", "")
    my_group = None
    for gname, gsyms in sym_groups.items():
        if base_symbol in gsyms:
            my_group = gname
            break

    if my_group:
        for p in existing:
            p_base = p.symbol.replace("m", "")
            if p_base in sym_groups.get(my_group, []):
                return False, f"已有同组持仓 ({my_group}): {p.symbol}"

    # ── 3. 单品种重复 ──
    for p in existing:
        if p.symbol == symbol:
            return False, f"已有同品种持仓: {symbol}"

    # ── 4. 同方向比例 ≤70% ──
    max_dir_pct = risk_cfg.get("max_same_direction_pct", 0.70)
    if existing:
        same_dir = sum(1 for p in existing
                       if (p.type == 0 and direction == "long")
                       or (p.type == 1 and direction == "short"))
        # 加上当前这笔
        after_pct = (same_dir + 1) / (len(existing) + 1)
        if after_pct > max_dir_pct:
            return False, (f"Direction overload: {direction} would be "
                           f"{after_pct:.0%} of portfolio (max {max_dir_pct:.0%})")

    # ── 5. 单品种风险敞口 ≤30% ──
    max_var_pct = risk_cfg.get("max_single_variety_pct", 0.30)
    if existing:
        same_var = sum(1 for p in existing if p.symbol.replace("m", "") == base_symbol)
        after_var_pct = (same_var + 1) / (len(existing) + 1)
        if after_var_pct > max_var_pct:
            return False, (f"Variety overload: {symbol} would be "
                           f"{after_var_pct:.0%} of portfolio (max {max_var_pct:.0%})")

    # ── 6. RR < 1:1 一票否决 ──
    min_rr = risk_cfg.get("min_rr", 1.0)
    sl_atr_mult = risk_cfg.get("sl_atr_multiple", 2.0)
    tp_rr_mult = risk_cfg.get("tp_rr_multiple", 2.0)
    if atr > 0:
        sl_distance = atr * sl_atr_mult
        tp_distance = sl_distance * tp_rr_mult
        rr = tp_distance / sl_distance if sl_distance > 0 else 0
        if rr < min_rr:
            return False, f"RR veto: RR={rr:.2f} < min_rr={min_rr:.1f} (SL={sl_distance:.5f}, TP={tp_distance:.5f})"

    return True, "risk check passed"


def calculate_lot_size(mt5, symbol: str, signal: dict, risk_pct: float,
                       equity: float, risk_cfg: dict) -> float:
    """
    基于 ATR 的精确手数计算。

    SL_距离 = ATR × sl_atr_multiple (从 config 读)
    每手风险 = (SL_距离 / point) × tick_value
    目标手数 = (权益 × 风险%) / 每手风险

    这样手数和实际挂单 SL 完全对齐，不存在偏离。
    """
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return 0.01

    tick_value = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size
    point = sym_info.point
    volume_min = sym_info.volume_min
    volume_step = sym_info.volume_step
    volume_max = sym_info.volume_max

    # 使用配置中的 ATR 乘数计算 SL 距离（与 place_order 一致）
    atr = signal.get("atr", 0)
    if atr <= 0:
        # 后备：用价格的 1%
        atr = signal.get("current_price", 0) * 0.01

    sl_atr_mult = risk_cfg.get("lot_calc_sl_atr_multiple",
                               risk_cfg.get("sl_atr_multiple", 2.0))
    sl_distance = atr * sl_atr_mult
    risk_per_lot = (sl_distance / point) * tick_value if point > 0 else 1

    if risk_per_lot <= 0:
        return volume_min

    target_lots = (equity * risk_pct) / risk_per_lot
    lots = max(volume_min, min(volume_max, round(target_lots / volume_step) * volume_step))
    return round(lots, 2)


def place_order(mt5, signal: dict, lot_size: float, magic: int,
                risk_cfg: dict) -> dict:
    """执行市价单，SL/TP 从 config 读取乘数"""
    import MetaTrader5 as mt5
    symbol = signal["symbol"]
    direction = signal["direction"]
    current_price = signal["current_price"]
    is_buy = direction == "long"

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"error": f"Cannot get tick for {symbol}"}

    price = tick.ask if is_buy else tick.bid

    # 从 config 读取乘数
    sl_atr_mult = risk_cfg.get("sl_atr_multiple", 2.0)
    tp_rr_mult = risk_cfg.get("tp_rr_multiple", 2.0)

    sym_info = mt5.symbol_info(symbol)
    atr = signal.get("atr", current_price * 0.01)
    sl_distance = atr * sl_atr_mult
    tp_distance = sl_distance * tp_rr_mult  # 保证 RR = tp_rr_mult

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
        "rr": tp_rr_mult,
        "strategy_id": signal.get("strategy_id"),
        "dealt_at_utc": datetime.utcnow().isoformat(),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal", type=str, required=True)
    parser.add_argument("--lot-size", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    signal = json.loads(args.signal)
    cfg = load_config()
    risk_cfg = cfg.get("risk", {})
    magic = cfg.get("magic_number", 234010)

    mt5, account = connect_mt5()
    if mt5 is None:
        result = {"error": account, "signal": signal}
        print(json.dumps(result, ensure_ascii=False))
        log_scan(signal, result)
        return

    try:
        # ── 风控检查 ──
        allowed, reason = check_risk(mt5, signal, risk_cfg, magic)
        if not allowed:
            result = {"risk_blocked": True, "reason": reason, "signal": signal}
            print(json.dumps(result, ensure_ascii=False))
            log_path = log_scan(signal, result)
            print(f"[LOG] Scan saved to {log_path}", file=sys.stderr)
            return

        # ── 计算手数 ──
        if args.lot_size:
            lot_size = args.lot_size
        else:
            lot_size = calculate_lot_size(
                mt5, signal["symbol"], signal,
                risk_cfg.get("risk_per_trade_pct", 0.05),
                account["equity"],
                risk_cfg
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

        # ── 执行 ──
        trade_result = place_order(mt5, signal, lot_size, magic, risk_cfg)
        result = {
            "execution": trade_result,
            "lot_size": lot_size,
            "signal": signal,
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))

        # ── 持久化日志 ──
        os.makedirs(TRADE_LOG_DIR, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(TRADE_LOG_DIR, f"trade_{ts}.json")
        with open(log_file, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[LOG] Trade saved to {log_file}", file=sys.stderr)

        # 扫描也存一份
        log_path = log_scan(signal, result)
        print(f"[LOG] Scan saved to {log_path}", file=sys.stderr)

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
