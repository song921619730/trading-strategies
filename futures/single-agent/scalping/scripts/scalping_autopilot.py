#!/usr/bin/env python3
"""
scalping_autopilot.py — Scalping M1/M5 全自动扫描+风控+执行守护进程 (Tick Engine 版)

每 1.5 秒自循环:
  1. 从 TickReader 读取 tick + 指标（不复连 MT5）
  2. 扫描 scalping_strategies.json 所有策略（30ms 扫完）
  3. AI 级风控检查
  4. 执行交易（仅此步需 MT5 连接，复用保持）
  5. 写日志, trigger, BE 管理

用法:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe ^
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/scripts/scalping_autopilot.py
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe ^
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/scripts/scalping_autopilot.py --once
"""

import json, os, sys, time, traceback, random
from datetime import datetime, timezone, timedelta

# ─── 路径（Windows 环境） ───
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "scalping_strategies.json")
SCAN_LOG_DIR = os.path.join(BASE, "logs", "signals")
TRIGGER_DIR = os.path.join(BASE, "logs", "triggers")
LOG_FILE = os.path.join(BASE, "logs", "scalping_autopilot.log")

MAGIC = 234011
SLEEP_SEC = 0.5        # 秒级循环（0.5s 扫描频率）
LOOP_LOG_INTERVAL = 20 # 每 20 个循环打印一次状态（≈30s）
CST = timezone(timedelta(hours=8))
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB 轮转

# ─── 风控参数 ───
MAX_LOTS_PER_TRADE = 1.0      # 单笔最大手数硬上限
MAX_CONSECUTIVE_LOSS = 4      # 连续亏损熔断阈值
LB_COOLDOWN_MIN = 20          # 熔断冷却时间
DAILY_LOSS_LIMIT = 300.0      # 日亏损上限

os.makedirs(SCAN_LOG_DIR, exist_ok=True)
os.makedirs(TRIGGER_DIR, exist_ok=True)

# 导入共享库
_SHARED = os.path.join(os.path.dirname(os.path.dirname(BASE)), "scripts")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)
sys.path.insert(0, os.path.join(BASE, "scripts"))

from scalping_scanner import scan_strategy  # 新版：scan_strategy(symbol, config, reader, account)
from tick_reader import TickReader
from indicators import SESSION_MAP


def log_msg(msg: str, level: str = "INFO"):
    """双写：stdout + 持久化日志文件（自动轮转 10MB）"""
    ts = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{level}] {ts} | {msg}"
    print(line, flush=True)
    # 写文件
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            base, ext = os.path.splitext(LOG_FILE)
            os.rename(LOG_FILE, f"{base}_1{ext}")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ─── 熔断器 ───
CB_FILE = os.path.join(BASE, "logs", "circuit_breaker_scalp.json")


def _load_cb() -> dict:
    try:
        if os.path.exists(CB_FILE):
            with open(CB_FILE, "r") as f:
                data = json.load(f)
                today = datetime.now(CST).strftime("%Y-%m-%d")
                if data.get("date") != today:
                    data = {"date": today, "consecutive_losses": 0,
                            "daily_loss": 0.0, "daily_trades": 0,
                            "pause_until": None, "paused_today": False}
                return data
    except:
        pass
    today = datetime.now(CST).strftime("%Y-%m-%d")
    return {"date": today, "consecutive_losses": 0,
            "daily_loss": 0.0, "daily_trades": 0,
            "pause_until": None, "paused_today": False}


def _save_cb(data: dict):
    try:
        os.makedirs(os.path.dirname(CB_FILE), exist_ok=True)
        with open(CB_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass


def check_circuit_breaker() -> bool:
    """检查熔断器，返回是否允许交易"""
    cb = _load_cb()
    if cb.get("daily_loss", 0) <= -DAILY_LOSS_LIMIT and not cb.get("paused_today"):
        log_msg(f"⚠️ 日亏损已达 ${-cb['daily_loss']:.0f}，上限 ${DAILY_LOSS_LIMIT}，今日停止", "WARN")
        cb["pause_until"] = "EOD"
        cb["paused_today"] = True
        _save_cb(cb)
        return False
    pause_until = cb.get("pause_until")
    if pause_until and pause_until != "EOD":
        try:
            pause_dt = datetime.fromisoformat(pause_until)
            if datetime.now(CST) < pause_dt:
                return False
        except:
            pass
    if pause_until == "EOD":
        if datetime.now(CST).hour < 6:
            return False
    return True


def record_trade_result(profit: float):
    """记录交易结果，更新熔断器"""
    cb = _load_cb()
    cb["daily_trades"] = cb.get("daily_trades", 0) + 1
    cb["daily_loss"] = cb.get("daily_loss", 0) + profit
    if profit < 0:
        cb["consecutive_losses"] = cb.get("consecutive_losses", 0) + 1
        cl = cb["consecutive_losses"]
        if cl >= MAX_CONSECUTIVE_LOSS:
            now = datetime.now(CST)
            cooldown_end = now + timedelta(minutes=LB_COOLDOWN_MIN)
            cb["pause_until"] = cooldown_end.isoformat()
            log_msg(f"🔴 连续 {cl} 亏，熔断 {LB_COOLDOWN_MIN}min", "WARN")
    else:
        cb["consecutive_losses"] = 0
    _save_cb(cb)


def track_closed_positions(mt5, last_tickets: set) -> set:
    """检测持仓关闭 → 更新熔断器"""
    try:
        positions = mt5.positions_get(group="*") or []
        my_positions = [p for p in positions if p.magic == MAGIC]
        current_tickets = {p.ticket for p in my_positions}
        closed = last_tickets - current_tickets
        if closed:
            from_time = datetime.now(timezone.utc) - timedelta(minutes=5)
            history = mt5.history_deals_get(from_time, datetime.now(timezone.utc))
            if history:
                for d in history:
                    if d.position_id and d.ticket in closed:
                        if abs(d.profit) > 0.01:
                            record_trade_result(d.profit)
            return current_tickets
        return last_tickets
    except:
        return last_tickets


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
                "price_open": p.price_open,
            }
            for p in my_positions
        ],
        "held_symbols": {p.symbol for p in my_positions},
    }


def check_risk(signal: dict, positions: dict, risk_cfg: dict, mt5) -> tuple[bool, str]:
    """风控检查（与之前相同，略去具体实现以保持简洁）"""
    # 完整风控代码保持原样（569行的autopilot里已有的check_risk函数）
    import MetaTrader5 as mt5_module
    max_total = risk_cfg.get("max_total_positions", 6)
    max_per_group = risk_cfg.get("max_position_per_group", 1)
    max_same_pct = risk_cfg.get("max_same_direction_pct", 0.7)
    max_variety_pct = risk_cfg.get("max_single_variety_pct", 0.3)
    min_rr = risk_cfg.get("min_rr", 1.0)
    max_spread_pct = risk_cfg.get("max_spread_pct", 0.005)
    groups = risk_cfg.get("pos_validation", {}).get("symposium_groups", {})

    symbol = signal.get("symbol", "")
    direction = signal.get("direction", "").upper()
    rr = signal.get("rr", 0)
    price = signal.get("current_price", 0)

    held = positions.get("positions", [])
    held_count = len(held)
    held_symbols = positions.get("held_symbols", set())
    same_dir_count = sum(1 for p in held if p["type"] == direction)
    same_sym_count = sum(1 for p in held if p["symbol"] == symbol)

    if held_count >= max_total:
        return False, f"总持仓 {held_count} ≥ {max_total}"
    if symbol in held_symbols:
        return False, f"已有 {symbol} 持仓"
    symbol_group = None
    for group_name, members in groups.items():
        if symbol in members:
            symbol_group = group_name
            break
    if symbol_group:
        group_count = sum(1 for p in held if p["symbol"] in groups[symbol_group])
        if group_count >= max_per_group:
            return False, f"同组 {symbol_group} 已达上限"
    if held_count > 0:
        new_same_pct = (same_dir_count + 1) / (held_count + 1)
        if new_same_pct > max_same_pct:
            return False, f"同方向占比 {new_same_pct:.0%} > {max_same_pct:.0%}"
    if held_count > 0:
        new_variety_pct = (same_sym_count + 1) / (held_count + 1)
        if new_variety_pct > max_variety_pct:
            return False, f"单品种占比 {new_variety_pct:.0%} > {max_variety_pct:.0%}"
    if rr is not None and rr > 0 and rr < min_rr:
        return False, f"RR={rr} < {min_rr}"
    # 实时 spread 检查
    try:
        tick = mt5_module.symbol_info_tick(symbol)
        if tick and price > 0:
            real_spread_pct = (tick.ask - tick.bid) / price
            if real_spread_pct > max_spread_pct:
                return False, f"实时刻点差 {real_spread_pct*100:.4f}% > {max_spread_pct*100:.2f}%"
    except:
        pass
    return True, "OK"


def execute_trade(mt5, signal: dict, risk_cfg: dict) -> dict:
    """执行交易（直接调用 MT5 API）"""
    import MetaTrader5 as mt5_module
    symbol = signal["symbol"]
    direction = signal["direction"]
    price = signal["current_price"]
    sl_price = signal.get("sl_price")
    tp_price = signal.get("tp_price")
    max_spread_pct = risk_cfg.get("max_spread_pct", 0.005)

    sym_info = mt5_module.symbol_info(symbol)
    if not sym_info:
        return {"status": "FAILED", "error": f"Cannot get symbol info for {symbol}"}

    digits = sym_info.digits
    point = sym_info.point
    spread = (mt5_module.symbol_info_tick(symbol).ask -
              mt5_module.symbol_info_tick(symbol).bid) if mt5_module.symbol_info_tick(symbol) else 0

    # 点差检查
    if price > 0 and spread / price > max_spread_pct:
        return {"status": "BLOCKED", "error": f"Spread too high: {spread/price*100:.4f}%"}

    # 算手数
    sl = sl_price or price * 0.99
    sl_points = abs(price - sl) / point if point > 0 else 100
    risk_pct = risk_cfg.get("risk_per_trade_pct", 0.05)
    account_info = mt5_module.account_info()
    balance = account_info.balance if account_info else 1000
    tick_value = mt5_module.symbol_info(symbol).trade_tick_value or 1
    lot_step = sym_info.volume_step or 0.01
    max_lots = min(sym_info.volume_max or 100, MAX_LOTS_PER_TRADE)

    risk_amount = balance * risk_pct
    raw_lots = risk_amount / (sl_points * tick_value) if sl_points > 0 and tick_value > 0 else 0.01
    lots = max(sym_info.volume_min or 0.01, min(raw_lots, max_lots))
    lots = round(lots / lot_step) * lot_step

    order_type = mt5_module.ORDER_TYPE_BUY if direction in ("long", "buy", "BUY") else mt5_module.ORDER_TYPE_SELL
    request = {
        "action": mt5_module.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "price": mt5_module.symbol_info_tick(symbol).ask if order_type == mt5_module.ORDER_TYPE_BUY
                 else mt5_module.symbol_info_tick(symbol).bid,
        "sl": float(round(sl_price, digits)) if sl_price is not None else float(round(sl, digits)),
        "tp": float(round(tp_price, digits)) if tp_price is not None else 0.0,
        "deviation": 20,
        "magic": MAGIC,
        "comment": f"Auto {signal.get('strategy_id','scalping')}",
        "type_time": mt5_module.ORDER_TIME_GTC,
        "type_filling": mt5_module.ORDER_FILLING_IOC,
    }

    # 尝试不同的填充模式（不同品种/平台支持的填充模式不同）
    filling_modes = [
        mt5_module.ORDER_FILLING_IOC,
        mt5_module.ORDER_FILLING_FOK,
        mt5_module.ORDER_FILLING_RETURN,
    ]
    result = None
    for fm in filling_modes:
        request["type_filling"] = fm
        result = mt5_module.order_send(request)
        if result and result.retcode == 10009:
            break
        if result and result.retcode != 10030:
            # 非填充模式错误，直接返回
            break

    if result and result.retcode == 10009:
        return {"status": "SUCCESS", "ticket": result.order, "price": result.price,
                "lots": lots, "sl": sl_price, "tp": tp_price}
    return {"status": "FAILED", "error": f"Order failed: {result.retcode if result else 'No result'}"}


def manage_breakeven(mt5, positions: dict) -> list:
    """半程盈亏平衡管理"""
    import MetaTrader5 as mt5_module
    adjustments = []
    be_log_path = os.path.join(os.path.dirname(SCAN_LOG_DIR), "trades", "breakeven_log.json")
    os.makedirs(os.path.dirname(be_log_path), exist_ok=True)

    for p in positions.get("positions", []):
        symbol = p["symbol"]
        direction = p["type"]
        ticket = p["ticket"]
        open_price = p["price_open"]
        current_sl = p["sl"]
        tp = p["tp"]
        if not tp:
            continue

        sym_info = mt5_module.symbol_info(symbol)
        if not sym_info:
            continue

        current_price = (mt5_module.symbol_info_tick(symbol).bid
                         if direction == "BUY" else mt5_module.symbol_info_tick(symbol).ask)
        if not current_price:
            continue

        tp_distance = abs(tp - open_price)
        be_threshold = open_price + tp_distance * 0.5 if direction == "BUY" else open_price - tp_distance * 0.5
        be_sl = round(open_price, sym_info.digits)
        needs_be = (direction == "BUY" and current_price >= be_threshold
                    and (not current_sl or current_sl < be_sl)) or \
                   (direction == "SELL" and current_price <= be_threshold
                    and (not current_sl or current_sl > be_sl))
        if needs_be:
            result = mt5_module.order_send({
                "action": mt5_module.TRADE_ACTION_SLTP, "symbol": symbol,
                "position": ticket, "sl": float(be_sl), "tp": float(tp),
            })
            status = "SUCCESS" if result and result.retcode == 10009 else "FAILED"
            adjustments.append({
                "ticket": ticket, "symbol": symbol, "type": direction,
                "old_sl": current_sl, "new_sl": be_sl, "status": status,
            })
            if status == "SUCCESS":
                try:
                    with open(be_log_path, 'a') as f:
                        f.write(json.dumps({"ts": datetime.utcnow().isoformat(),
                                            "ticket": ticket, "symbol": symbol,
                                            "action": "BE"}) + "\n")
                except:
                    pass
    return adjustments


def write_trigger(signal: dict, result: dict) -> str:
    """写入 trigger 文件供 AI 汇报 Cron 读取"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:19]
    trigger_path = os.path.join(TRIGGER_DIR, f"trade_{ts}.json")
    trigger_data = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "type": "scalping_autopilot",
        "signal": signal,
        "trade_result": result,
    }
    with open(trigger_path, "w") as f:
        json.dump(trigger_data, f, ensure_ascii=False, indent=2)
    return trigger_path


def run_once(mt5, reader: TickReader, cfg: dict, prev_positions: dict | None = None) -> dict:
    """单次循环（扫描+风控+执行），复用 mt5 连接"""
    # 熔断检查
    if not check_circuit_breaker():
        return {"magic": MAGIC, "engine_alive": reader.is_alive(),
                "strategies_scanned": 0, "signals_found": 0,
                "signals_executed": 0, "signals_blocked": 0,
                "blocked_reasons": ["⛔ 熔断中"], "held_positions": 0,
                "held_symbols": []}

    all_signals = cfg.get("signals", [])
    risk_cfg = cfg.get("risk", {})

    # 1. 查询持仓（复用 mt5 连接）
    positions = get_existing_positions(mt5)
    held_symbols = positions["held_symbols"]

    # 2. 半程盈亏平衡管理
    be_adjustments = manage_breakeven(mt5, positions)
    for adj in be_adjustments:
        if adj["status"] == "SUCCESS":
            log_msg(f"🔒 BE {adj['symbol']} {adj['type']} ticket={adj['ticket']}", "INFO")
    if be_adjustments:
        positions = get_existing_positions(mt5)
        held_symbols = positions["held_symbols"]

    # 3. 扫描（用 TickReader，不复连 MT5）
    detected = []
    for strategy in all_signals:
        for sym in strategy.get("symbols", []):
            if sym in held_symbols:
                continue
            try:
                sigs = scan_strategy(sym, strategy, reader, {})
                detected.extend(sigs)
            except Exception as e:
                log_msg(f"Scan {sym} error: {e}", "WARN")

    # 4. 风控 + 执行
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
        trigger_path = write_trigger(sig, result)
        entry["trigger_path"] = trigger_path
        held_symbols.add(sig.get("symbol", ""))
        positions["held_symbols"] = held_symbols

    # 5. 日志
    blocked_reasons = list(set(
        e.get("reason", "") for e in executed if e["status"] == "blocked"
    ))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "magic": MAGIC,
        "engine_alive": reader.is_alive(),
        "strategies_scanned": len(all_signals),
        "signals_found": len(detected),
        "signals_executed": sum(1 for e in executed if e["status"] == "executed"),
        "signals_blocked": sum(1 for e in executed if e["status"] == "blocked"),
        "blocked_reasons": blocked_reasons,
        "held_positions": positions["count"],
        "held_symbols": list(held_symbols),
        "details": executed,
    }
    log_path = os.path.join(SCAN_LOG_DIR, f"autopilot_{ts}.json")
    with open(log_path, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main():
    once_mode = "--once" in sys.argv
    import MetaTrader5 as mt5_module

    log_msg(f"🟢 Scalping Autopilot (Tick Engine) starting (Magic {MAGIC})")
    log_msg(f"    Config: {CONFIG_PATH}")
    log_msg(f"    Loop: {SLEEP_SEC}s")
    log_msg(f"    Mode: {'ONCE' if once_mode else 'DAEMON'}")

    # 创建 TickReader
    reader = TickReader()

    # ── MT5 并发保护：等 Tick Engine 就绪 + 随机抖动 ──
    WAIT_MAX = 15  # 最多等 15 秒
    for attempt in range(WAIT_MAX):
        if reader.is_alive():
            break
        log_msg(f"⏳ 等待 Tick Engine 就绪... ({attempt+1}s)", "WARN")
        time.sleep(1)
    else:
        log_msg("⚠️  Tick Engine 未运行！Scanner 将使用降级模式（直连 MT5）", "WARN")

    # 随机抖动 3-8 秒，避免与 Tick Engine 的 MT5 并发访问 segfault
    jitter = random.uniform(3.0, 8.0)
    log_msg(f"🕒 MT5 连接前等待 {jitter:.1f}s (并发保护)")
    time.sleep(jitter)

    if once_mode:
        # 一次模式：连 MT5 → 跑一次 → 断开
        mt5, account = connect_old_mt5()
        if mt5 is None:
            log_msg(f"❌ MT5 connect failed", "ERROR")
            return
        try:
            cfg = load_config()
            summary = run_once(mt5, reader, cfg)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        finally:
            mt5_module.shutdown()
        return

    # DAEMON 模式：MT5 连接保持，循环 1.5s
    mt5 = None
    try:
        # 初始化 MT5（只做一次！不再每轮连了断）
        path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
        if not mt5_module.initialize(path=path):
            log_msg(f"❌ MT5 init failed: {mt5_module.last_error()}", "ERROR")
            return
        mt5 = mt5_module
        account_info = mt5.account_info()
        if account_info:
            log_msg(f"✅ MT5 connected: login={account_info.login}, balance={account_info.balance:.2f}")

        cfg = load_config()
        loop_count = 0
        known_tickets = set()

        while True:
            try:
                loop_start = time.time()
                loop_count += 1

                # 检测已关闭持仓 → 更新熔断器
                known_tickets = track_closed_positions(mt5, known_tickets)

                # 每隔 LOOP_LOG_INTERVAL 次重载配置（检查 auto-inject）
                if loop_count % LOOP_LOG_INTERVAL == 0:
                    old_len = len(cfg.get("signals", []))
                    cfg = load_config()
                    new_len = len(cfg.get("signals", []))
                    if new_len != old_len:
                        log_msg(f"🔄 Config reloaded: {old_len} → {new_len} strategies")

                summary = run_once(mt5, reader, cfg)

                if summary.get("signals_executed", 0) > 0:
                    log_msg(f"✅ 执行 {summary['signals_executed']} 笔 | "
                            f"信号 {summary['signals_found']} | "
                            f"拦截 {summary['signals_blocked']} | "
                            f"持仓 {summary['held_positions']}")
                elif summary.get("signals_found", 0) > 0 and loop_count % 5 == 0:
                    reasons = "; ".join(summary.get("blocked_reasons", []))
                    log_msg(f"📊 信号 {summary['signals_found']} 被拦截 | "
                            f"{reasons} | 持仓 {summary['held_positions']}")
                elif loop_count % LOOP_LOG_INTERVAL == 0:
                    log_msg(f"⏱️ 循环 #{loop_count} | 持仓 {summary.get('held_positions', 0)}")

                elapsed = time.time() - loop_start
                sleep_time = max(0.1, SLEEP_SEC - elapsed)
                time.sleep(sleep_time)

            except KeyboardInterrupt:
                log_msg("🔴 Autopilot stopped by user")
                break
            except Exception as e:
                log_msg(f"❌ Loop error: {e}", "ERROR")
                time.sleep(SLEEP_SEC * 2)

    finally:
        if mt5:
            try:
                mt5.shutdown()
                log_msg("👋 MT5 disconnected")
            except:
                pass


def connect_old_mt5():
    """兼容 --once 模式的 MT5 连接（每次跑完断）"""
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
    return mt5, {"name": term.name, "login": acct.login, "balance": acct.balance, "equity": acct.equity}


if __name__ == "__main__":
    main()
