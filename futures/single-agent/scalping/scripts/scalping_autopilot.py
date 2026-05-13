#!/usr/bin/env python3
"""
scalping_autopilot.py — Scalping M1/M5 全自动扫描+风控+执行守护进程

每分钟自循环（运行在 Windows Python 下，因为需要 MT5）：
  1. 连接 MT5
  2. 扫描 scalping_strategies.json 所有策略
  3. AI 级风控检查（持仓数/同组/同方向/RR/点差）
  4. 执行交易（调用 scalping_execute.py open）
  5. 写日志到 logs/
  6. 写 trigger 文件供 AI 汇报 Cron 读取
  7. 睡眠 60 秒

用法:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/scripts/scalping_autopilot.py
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/scripts/scalping_autopilot.py --once
"""
import json, os, sys, time, traceback
from datetime import datetime, timezone, timedelta

# ─── 路径（Windows 环境） ───
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "scalping_strategies.json")
SCAN_LOG_DIR = os.path.join(BASE, "logs", "signals")
TRIGGER_DIR = os.path.join(BASE, "logs", "triggers")

MAGIC = 234011
SLEEP_SEC = 60  # 每分钟一次
CST = timezone(timedelta(hours=8))

os.makedirs(SCAN_LOG_DIR, exist_ok=True)
os.makedirs(TRIGGER_DIR, exist_ok=True)

# 导入扫描函数（直接调用，不走 subprocess）
sys.path.insert(0, os.path.join(BASE, "scripts"))
from scalping_scanner import connect_mt5, scan_strategy, SESSION_MAP


def log_msg(msg: str, level: str = "INFO"):
    ts = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{level}] {ts} | {msg}", flush=True)


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_existing_positions(mt5) -> dict:
    """查询 Magic 234011 当前持仓"""
    positions = mt5.positions_get(group="*") or []
    my_positions = [p for p in positions if p.magic == MAGIC]
    return {
        "count": len(my_positions),
        "positions": [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "profit": p.profit,
                "sl": p.sl,
                "tp": p.tp,
            }
            for p in my_positions
        ],
        "held_symbols": {p.symbol for p in my_positions},
    }


def check_risk(signal: dict, positions: dict, risk_cfg: dict, mt5) -> tuple[bool, str]:
    """风控检查"""
    max_total = risk_cfg.get("max_total_positions", 6)
    max_per_group = risk_cfg.get("max_position_per_group", 1)
    max_same_pct = risk_cfg.get("max_same_direction_pct", 0.7)
    max_variety_pct = risk_cfg.get("max_single_variety_pct", 0.3)
    min_rr = risk_cfg.get("min_rr", 1.0)
    max_spread_pct = risk_cfg.get("max_spread_pct", 0.005)  # 0.5% 放宽
    groups = risk_cfg.get("pos_validation", {}).get("symposium_groups", {})

    symbol = signal.get("symbol", "")
    direction = signal.get("direction", "").upper()
    rr = signal.get("rr", 0)
    spread = signal.get("spread", 0)
    price = signal.get("current_price", 0)

    held = positions.get("positions", [])
    held_count = len(held)
    held_symbols = positions.get("held_symbols", set())

    same_dir_count = sum(1 for p in held if p["type"] == direction)
    same_sym_count = sum(1 for p in held if p["symbol"] == symbol)

    # 1. 总持仓
    if held_count >= max_total:
        return False, f"总持仓 {held_count} ≥ {max_total}"

    # 2. 重复品种
    if symbol in held_symbols:
        return False, f"已有 {symbol} 持仓"

    # 3. 同组限制
    symbol_group = None
    for group_name, members in groups.items():
        if symbol in members:
            symbol_group = group_name
            break
    if symbol_group:
        group_count = sum(1 for p in held if p["symbol"] in groups[symbol_group])
        if group_count >= max_per_group:
            return False, f"同组 {symbol_group} 已达上限"

    # 4. 同方向比例（仅当有持仓时检查）
    if held_count > 0:
        new_same_pct = (same_dir_count + 1) / (held_count + 1)
        if new_same_pct > max_same_pct:
            return False, f"同方向占比 {new_same_pct:.0%} > {max_same_pct:.0%}"

    # 5. 单品种方向比例（仅当有持仓时检查）
    if held_count > 0:
        new_variety_pct = (same_sym_count + 1) / (held_count + 1)
        if new_variety_pct > max_variety_pct:
            return False, f"单品种占比 {new_variety_pct:.0%} > {max_variety_pct:.0%}"

    # 6. RR
    if rr is not None and rr > 0 and rr < min_rr:
        return False, f"RR={rr} < {min_rr}"

    # 7. 点差
    if spread > 0 and price > 0:
        spread_pct = spread / price
        if spread_pct > max_spread_pct:
            return False, f"点差 {spread_pct*100:.4f}% > {max_spread_pct*100:.2f}%"

    # ── 8. spread 实时检查 ──
    try:
        import MetaTrader5 as mt5_module
        tick = mt5_module.symbol_info_tick(symbol)
        if tick and price > 0:
            real_spread_pct = (tick.ask - tick.bid) / price
            if real_spread_pct > max_spread_pct:
                return False, f"实时刻点差 {real_spread_pct*100:.4f}% > {max_spread_pct*100:.2f}%"
    except:
        pass

    return True, "OK"


def execute_trade(mt5, signal: dict, risk_cfg: dict) -> dict:
    """直接通过 MT5 API 执行交易"""
    import MetaTrader5 as mt5_module
    symbol = signal["symbol"]
    direction = signal["direction"]
    price = signal["current_price"]
    sl_price = signal.get("sl_price")
    tp_price = signal.get("tp_price")
    atr = signal.get("atr", 0)

    # 确定买卖方向
    if direction.upper() in ("LONG", "BUY"):
        order_type = mt5_module.ORDER_TYPE_BUY
        trade_comment = "SCALP_234011_L"
    else:
        order_type = mt5_module.ORDER_TYPE_SELL
        trade_comment = "SCALP_234011_S"

    # 选价
    tick = mt5_module.symbol_info_tick(symbol)
    if not tick:
        return {"error": f"No tick for {symbol}"}
    entry_price = tick.ask if order_type == mt5_module.ORDER_TYPE_BUY else tick.bid

    # ── 手数计算（5% 风险截断） ──
    acct = mt5_module.account_info()
    if not acct:
        return {"error": "No account info"}
    equity = acct.equity
    sym_info = mt5_module.symbol_info(symbol)
    if not sym_info:
        return {"error": f"No symbol info for {symbol}"}

    risk_pct = risk_cfg.get("risk_per_trade_pct", 0.05)
    point = sym_info.point
    tick_value = sym_info.trade_tick_value
    vol_min = sym_info.volume_min
    vol_step = sym_info.volume_step
    vol_max = sym_info.volume_max

    if point <= 0 or tick_value <= 0:
        return {"error": "Invalid point or tick_value"}

    # SL 距离决定手数
    sl_distance = abs(entry_price - sl_price) if sl_price else (atr * 1.0 if atr else 0)
    if sl_distance <= 0:
        return {"error": "SL distance is zero"}

    risk_per_lot = (sl_distance / point) * tick_value
    if risk_per_lot <= 0:
        return {"error": "Risk per lot is zero"}

    lot_raw = (equity * risk_pct) / risk_per_lot
    volume = max(vol_min, min(vol_max, round(lot_raw / vol_step) * vol_step))
    if volume < vol_min:
        return {"error": f"Volume {volume} below minimum {vol_min}"}

    # ── 检查同组最大手数（从已有持仓） ──
    # 已有同组持仓则减少手数

    # ── 发单 ──
    request = {
        "action": mt5_module.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": entry_price,
        "deviation": 20,
        "magic": MAGIC,
        "comment": trade_comment,
        "type_time": mt5_module.ORDER_TIME_GTC,
        "type_filling": mt5_module.ORDER_FILLING_FOK,
    }
    if sl_price:
        request["sl"] = round(sl_price, sym_info.digits)
    if tp_price:
        request["tp"] = round(tp_price, sym_info.digits)

    result = mt5_module.order_send(request)
    if result is None:
        err_info = mt5_module.last_error()
        return {"error": f"order_send returned None", "last_error": err_info}

    response = {
        "action": "open",
        "retcode": result.retcode,
        "order": result.order,
        "deal": result.deal,
        "volume": float(result.volume),
        "price": float(result.price),
        "symbol": symbol,
        "direction": direction,
        "sl": sl_price,
        "tp": tp_price,
        "comment": result.comment,
        "status": "SUCCESS" if result.retcode == 10009 else "FAILED",
    }
    if result.retcode != 10009:
        response["error_detail"] = f"Retcode {result.retcode}: {result.comment}"

    return response


def write_trigger(signal: dict, execute_result: dict):
    """写入 trigger 文件"""
    now = datetime.now(timezone.utc)
    trigger = {
        "timestamp_utc": now.isoformat(),
        "magic": MAGIC,
        "signal": signal,
        "result": execute_result,
        "read": False,
    }
    path = os.path.join(TRIGGER_DIR, f"trigger_{now.strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w") as f:
        json.dump(trigger, f, ensure_ascii=False, indent=2)
    return path


def run_once() -> dict:
    """单轮扫描+执行"""
    cfg = load_config()
    all_signals = cfg.get("signals", [])
    risk_cfg = cfg.get("risk", {})

    # 1. 连接 MT5
    mt5, account = connect_mt5()
    if mt5 is None:
        return {"error": f"MT5 connect failed: {account}"}

    try:
        # 2. 查询持仓
        positions = get_existing_positions(mt5)
        held_symbols = positions["held_symbols"]

        # 3. 获取 DXY 数据
        dxy_bars = None
        try:
            import numpy as np
            dxy_raw = mt5.copy_rates_from_pos("DXY", mt5.TIMEFRAME_H1, 0, 20)
            if dxy_raw is not None and len(dxy_raw) >= 6:
                dxy_bars = []
                for b in dxy_raw:
                    dxy_bars.append({
                        "time": b["time"] if isinstance(b, (dict, np.void)) else b.time,
                        "open": b["open"] if isinstance(b, (dict, np.void)) else b.open,
                        "high": b["high"] if isinstance(b, (dict, np.void)) else b.high,
                        "low": b["low"] if isinstance(b, (dict, np.void)) else b.low,
                        "close": b["close"] if isinstance(b, (dict, np.void)) else b.close,
                    })
        except:
            pass

        # 4. 扫描所有策略（跳过已有持仓品种）
        detected = []
        for strategy in all_signals:
            for sym in strategy.get("symbols", []):
                if sym in held_symbols:
                    continue  # 已有持仓不重复扫描
                try:
                    mt5.symbol_select(sym, True)
                    sigs = scan_strategy(mt5, sym, strategy, account)
                    detected.extend(sigs)
                except Exception as e:
                    log_msg(f"Scan {sym} error: {e}", "WARN")

        # 5. 风控 + 执行
        executed = []
        for sig in detected:
            allowed, reason = check_risk(sig, positions, risk_cfg, mt5)
            if not allowed:
                executed.append({"signal": sig, "status": "blocked", "reason": reason})
                continue

            result = execute_trade(mt5, sig, risk_cfg)
            status = "executed" if result.get("status") == "SUCCESS" else "failed"
            entry = {"signal": sig, "status": status, "result": result}
            executed.append(entry)

            # 写入 trigger
            trigger_path = write_trigger(sig, result)
            entry["trigger_path"] = trigger_path

            # 更新持仓缓存（同一轮不再重复开品种）
            held_symbols.add(sig.get("symbol", ""))
            positions["held_symbols"] = held_symbols

        # 6. 日志
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        summary = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "magic": MAGIC,
            "account_equity": account.get("equity", 0) if account else 0,
            "strategies_scanned": len(all_signals),
            "signals_found": len(detected),
            "signals_executed": sum(1 for e in executed if e["status"] == "executed"),
            "signals_blocked": sum(1 for e in executed if e["status"] == "blocked"),
            "held_positions": positions["count"],
            "held_symbols": list(held_symbols),
            "details": executed,
        }
        log_path = os.path.join(SCAN_LOG_DIR, f"autopilot_{ts}.json")
        with open(log_path, "w") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        return summary

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

    finally:
        try:
            mt5.shutdown()
        except:
            pass


def main():
    once_mode = "--once" in sys.argv
    import MetaTrader5 as mt5_module

    log_msg(f"🟢 Scalping Autopilot starting (Magic {MAGIC})")
    log_msg(f"    Config: {CONFIG_PATH}")
    log_msg(f"    MT5 version: {mt5_module.__version__}")
    log_msg(f"    Mode: {'ONCE' if once_mode else 'DAEMON (60s loop)'}")

    if once_mode:
        summary = run_once()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    while True:
        try:
            loop_start = time.time()
            summary = run_once()

            if summary.get("signals_executed", 0) > 0:
                log_msg(f"✅ 执行 {summary['signals_executed']} 笔 | "
                        f"信号 {summary['signals_found']} | "
                        f"拦截 {summary['signals_blocked']} | "
                        f"持仓 {summary['held_positions']}")
            elif summary.get("signals_found", 0) > 0:
                log_msg(f"📊 信号 {summary['signals_found']} 全部被风控拦截 | "
                        f"持仓 {summary['held_positions']}")
            elif summary.get("error"):
                log_msg(f"❌ {summary['error']}", "ERROR")

            elapsed = time.time() - loop_start
            sleep_time = max(1, SLEEP_SEC - int(elapsed))
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            log_msg("🔴 Scalping Autopilot stopped by user")
            break
        except Exception as e:
            log_msg(f"❌ Unhandled error: {e}\n{traceback.format_exc()}", "CRITICAL")
            time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()
