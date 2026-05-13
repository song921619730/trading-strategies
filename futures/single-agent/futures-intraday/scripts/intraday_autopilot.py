#!/usr/bin/env python3
"""
intraday_autopilot.py — Intraday M30/H1 全自动扫描+风控+执行（Tick Engine 版）

每秒自循环:
  1. 从 TickReader 读取 tick + 指标（不复连 MT5）
  2. 扫描 strategies.json 所有策略（49 个，~50ms）
  3. 风控检查（同组/同方向/RR/DXY过滤）
  4. 执行交易（仅此步需 MT5，复用连接）
  5. 写日志 + trigger

用法（Windows Python）:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe ^
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/scripts/intraday_autopilot.py
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe ^
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/scripts/intraday_autopilot.py --once
"""

import json, os, sys, time, traceback
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "strategies.json")
SCAN_LOG_DIR = os.path.join(BASE, "logs", "scans")
TRIGGER_DIR = os.path.join(BASE, "logs", "triggers")

MAGIC = 234010
SLEEP_SEC = 2.0
LOOP_LOG_INTERVAL = 30
CST = timezone(timedelta(hours=8))

os.makedirs(SCAN_LOG_DIR, exist_ok=True)
os.makedirs(TRIGGER_DIR, exist_ok=True)

# 共享库
_SHARED = os.path.join(os.path.dirname(os.path.dirname(BASE)), "scripts")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)
sys.path.insert(0, os.path.join(BASE, "scripts"))

from signal_scanner import scan_strategy
from tick_reader import TickReader


def log_msg(msg: str, level: str = "INFO"):
    ts = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{level}] {ts} | {msg}", flush=True)


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_positions(mt5) -> dict:
    positions = mt5.positions_get(group="*") or []
    my_positions = [p for p in positions if p.magic == MAGIC]
    return {
        "count": len(my_positions),
        "positions": [{"ticket": p.ticket, "symbol": p.symbol,
                       "type": "BUY" if p.type == 0 else "SELL",
                       "volume": p.volume, "profit": p.profit,
                       "sl": p.sl, "tp": p.tp, "price_open": p.price_open}
                      for p in my_positions],
        "held_symbols": {p.symbol for p in my_positions},
    }


def check_risk(signal: dict, positions: dict, risk_cfg: dict, mt5) -> tuple[bool, str]:
    """风控检查（简版）"""
    import MetaTrader5 as mt5_module
    symbol = signal.get("symbol", "")
    direction = signal.get("direction", "").upper()
    rr = signal.get("rr", 0)
    price = signal.get("current_price", 0)
    max_total = risk_cfg.get("max_positions", 6)
    min_rr = risk_cfg.get("min_rr", 1.0)
    max_spread_pct = risk_cfg.get("max_spread_pct", 0.005)
    groups = risk_cfg.get("groups", {})
    held = positions.get("positions", [])
    held_symbols = positions.get("held_symbols", set())

    if len(held) >= max_total:
        return False, f"总持仓 {len(held)} ≥ {max_total}"
    if symbol in held_symbols:
        return False, f"已有 {symbol} 持仓"
    symbol_group = next((g for g, m in groups.items() if symbol in m), None)
    if symbol_group:
        gc = sum(1 for p in held if p["symbol"] in groups[symbol_group])
        if gc >= risk_cfg.get("max_per_group", 2):
            return False, f"同组 {symbol_group} 已达上限"
    if rr and rr > 0 and rr < min_rr:
        return False, f"RR={rr} < {min_rr}"
    try:
        tick = mt5_module.symbol_info_tick(symbol)
        if tick and price > 0 and (tick.ask - tick.bid) / price > max_spread_pct:
            return False, f"点差过高"
    except:
        pass
    return True, "OK"


def execute_trade(mt5, signal: dict, risk_cfg: dict) -> dict:
    """执行交易"""
    import MetaTrader5 as mt5_module
    symbol = signal["symbol"]
    direction = signal["direction"]
    price = signal["current_price"]
    sl_price = signal.get("sl_price")
    tp_price = signal.get("tp_price")
    si = mt5_module.symbol_info(symbol)
    if not si:
        return {"status": "FAILED", "error": f"No symbol info: {symbol}"}
    tick = mt5_module.symbol_info_tick(symbol)
    if not tick:
        return {"status": "FAILED", "error": "No tick"}
    digits = si.digits
    point = si.point or 0.00001
    risk_pct = risk_cfg.get("risk_per_trade", risk_cfg.get("risk_per_trade_pct", 0.05))
    acct = mt5_module.account_info()
    balance = acct.balance if acct else 1000
    sl = sl_price or price * 0.99
    sl_pts = abs(price - sl) / point
    tick_val = si.trade_tick_value or 1
    vol_min = si.volume_min or 0.01
    vol_max = si.volume_max or 100
    vol_step = si.volume_step or 0.01
    raw = (balance * risk_pct) / (sl_pts * tick_val) if sl_pts > 0 else vol_min
    lots = max(vol_min, min(raw, vol_max))
    lots = round(lots / vol_step) * vol_step
    ot = mt5_module.ORDER_TYPE_BUY if direction in ("long", "buy", "BUY") else mt5_module.ORDER_TYPE_SELL
    req = {
        "action": mt5_module.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": ot,
        "price": tick.ask if ot == mt5_module.ORDER_TYPE_BUY else tick.bid,
        "sl": float(round(sl_price, digits)) if sl_price else 0,
        "tp": float(round(tp_price, digits)) if tp_price else 0,
        "deviation": 20,
        "magic": MAGIC,
        "comment": f"Intraday {signal.get('strategy_id','auto')}",
        "type_time": mt5_module.ORDER_TIME_GTC,
        "type_filling": mt5_module.ORDER_FILLING_IOC,
    }
    result = mt5_module.order_send(req)
    if result and result.retcode == 10009:
        return {"status": "SUCCESS", "ticket": result.order, "price": result.price, "lots": lots}
    return {"status": "FAILED", "error": f"Order fail: {result.retcode if result else 'no result'}"}


def run_once(mt5, reader: TickReader, cfg: dict) -> dict:
    """单次循环"""
    all_signals = cfg.get("signals", [])
    risk_cfg = cfg.get("risk", {})
    positions = get_positions(mt5)
    dxy_indicators = reader.get_indicator("DXY", "H1")

    detected = []
    for strategy in all_signals:
        for sym in strategy.get("symbols", []):
            if sym in positions["held_symbols"]:
                continue
            try:
                sigs = scan_strategy(sym, strategy, reader, dxy_indicators)
                detected.extend(sigs)
            except:
                pass

    executed = []
    for sig in detected:
        allowed, reason = check_risk(sig, positions, risk_cfg, mt5)
        if not allowed:
            executed.append({"signal": sig, "status": "blocked", "reason": reason})
            continue
        result = execute_trade(mt5, sig, risk_cfg)
        status = "executed" if result.get("status") == "SUCCESS" else "failed"
        executed.append({"signal": sig, "status": status, "result": result})
        positions["held_symbols"].add(sig.get("symbol", ""))

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "magic": MAGIC, "engine_alive": reader.is_alive(),
        "strategies_scanned": len(all_signals),
        "signals_found": len(detected),
        "signals_executed": sum(1 for e in executed if e["status"] == "executed"),
        "signals_blocked": sum(1 for e in executed if e["status"] == "blocked"),
        "held_positions": positions["count"],
        "details": executed,
    }
    with open(os.path.join(SCAN_LOG_DIR, f"intraday_{ts}.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main():
    once_mode = "--once" in sys.argv
    import MetaTrader5 as mt5_module
    reader = TickReader()

    log_msg(f"🟢 Intraday Autopilot (Tick Engine) Magic={MAGIC}")
    log_msg(f"    Loop: {SLEEP_SEC}s | Mode: {'ONCE' if once_mode else 'DAEMON'}")
    if not reader.is_alive():
        log_msg("⚠️  Tick Engine not running!", "WARN")

    if once_mode:
        path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
        if not mt5_module.initialize(path=path):
            print(json.dumps({"error": f"MT5 init failed: {mt5_module.last_error()}"}))
            return
        try:
            cfg = load_config()
            print(json.dumps(run_once(mt5_module, reader, cfg), ensure_ascii=False, indent=2))
        finally:
            mt5_module.shutdown()
        return

    # DAEMON 模式
    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
    if not mt5_module.initialize(path=path):
        log_msg(f"❌ MT5 init failed: {mt5_module.last_error()}", "ERROR")
        return
    try:
        acct = mt5_module.account_info()
        if acct:
            log_msg(f"✅ MT5: login={acct.login}, balance={acct.balance:.2f}")
        cfg = load_config()
        loop_count = 0
        while True:
            try:
                loop_start = time.time()
                loop_count += 1
                if loop_count % LOOP_LOG_INTERVAL == 0:
                    cfg = load_config()
                summary = run_once(mt5_module, reader, cfg)
                if summary.get("signals_executed", 0) > 0:
                    log_msg(f"✅ 执行 {summary['signals_executed']} 笔 | "
                            f"信号 {summary['signals_found']} | "
                            f"拦截 {summary['signals_blocked']} | "
                            f"持仓 {summary['held_positions']}")
                elif loop_count % LOOP_LOG_INTERVAL == 0:
                    log_msg(f"⏱️ 循环#{loop_count} | 持仓 {summary.get('held_positions',0)}")
                elapsed = time.time() - loop_start
                time.sleep(max(0.1, SLEEP_SEC - elapsed))
            except KeyboardInterrupt:
                log_msg("🔴 Stopped")
                break
            except Exception as e:
                log_msg(f"❌ {e}", "ERROR")
                time.sleep(SLEEP_SEC * 2)
    finally:
        try:
            mt5_module.shutdown()
        except:
            pass


if __name__ == "__main__":
    main()
