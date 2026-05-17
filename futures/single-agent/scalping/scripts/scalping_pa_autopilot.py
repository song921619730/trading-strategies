#!/usr/bin/env python3
"""
scalping_pa_autopilot.py - Price Action M1/M5 全自动交易 (Magic 234013)

每 0.5 秒自循环:
  1. 从 TickReader 读取 tick + 指标
  2. 将 K 线数据喂入 PriceActionEngine（纯价格行为分析）
  3. 引擎分析趋势/动量/衰竭/结构突破/影线压力
  4. 得分超阈值则下单（风控/手数/SL/TP 复用现有逻辑）
  5. 写日志, trigger, BE 管理

和 scalping_autopilot.py (Magic 234011) 并行运行，独立 Magic/日志/持仓。

用法:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe ^
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/scripts/scalping_pa_autopilot.py
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe ^
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/scripts/scalping_pa_autopilot.py --once
"""

import json, os, sys, time, traceback, random
from datetime import datetime, timezone, timedelta

# ─── 路径（Windows 环境） ───
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIGGER_DIR = os.path.join(BASE, "logs", "triggers_pa")
LOG_FILE = os.path.join(BASE, "logs", "scalping_pa_autopilot.log")

MAGIC = 234013
SLEEP_SEC = 0.5         # 秒级循环（0.5s 扫描频率）
LOOP_LOG_INTERVAL = 20  # 每 20 个循环打印一次状态
CST = timezone(timedelta(hours=8))
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB 轮转

# ─── 风控参数 ───
MAX_SIGNALS_PER_CYCLE = 2     # 每周期最多执行信号数（排序后取top）
MIN_SCORE = 6                 # 信号分数最小值
MIN_CONFIDENCE = 0.4          # 信号置信度最小值
MAX_LOTS_PER_TRADE = 1.0      # 单笔最大手数硬上限
MAX_POSITION_RISK_PCT = 0.03  # 单笔最大风险 3% 净值（原 5%）
MAX_TOTAL_RISK_PCT = 0.08     # 所有持仓总风险不超过 8%
MAX_CONSECUTIVE_LOSS = 3      # 连续亏损熔断阈值
LB_COOLDOWN_MIN = 30          # 熔断冷却时间（分钟）
DAILY_LOSS_LIMIT = 200.0      # 日亏损上限（美元）

os.makedirs(TRIGGER_DIR, exist_ok=True)

# 导入共享库
_SHARED = os.path.join(os.path.dirname(os.path.dirname(BASE)), "scripts")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)
sys.path.insert(0, os.path.join(BASE, "scripts"))

from tick_reader import TickReader
from price_action_engine import PriceActionEngine, get_engine


def log_msg(msg: str, level: str = "INFO"):
    """双写：stdout + 持久化日志文件（自动轮转 10MB）"""
    ts = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{level}] {ts} | {msg}"
    print(line, flush=True)
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            base, ext = os.path.splitext(LOG_FILE)
            os.rename(LOG_FILE, f"{base}_1{ext}")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_existing_positions(mt5) -> dict:
    """查询 Magic 234013 当前持仓"""
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
        "total_volume": sum(p.volume for p in my_positions),
        "total_profit": sum(p.profit for p in my_positions),
    }


# ─── 熔断器 ───
CB_FILE = os.path.join(BASE, "logs", "circuit_breaker_pa.json")


def _load_cb() -> dict:
    """读取熔断器状态"""
    try:
        if os.path.exists(CB_FILE):
            with open(CB_FILE, "r") as f:
                data = json.load(f)
                # 跨日重置
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
    """保存熔断器状态"""
    try:
        os.makedirs(os.path.dirname(CB_FILE), exist_ok=True)
        with open(CB_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass


def check_circuit_breaker() -> bool:
    """检查熔断器，返回是否允许交易"""
    cb = _load_cb()
    # 日亏损上限
    if cb.get("daily_loss", 0) <= -DAILY_LOSS_LIMIT and not cb.get("paused_today"):
        log_msg(f"⚠️ 日亏损已达 ${-cb['daily_loss']:.0f}，超过上限 ${DAILY_LOSS_LIMIT}，今日停止交易", "WARN")
        cb["pause_until"] = "EOD"
        cb["paused_today"] = True
        _save_cb(cb)
        return False
    # 冷却中
    pause_until = cb.get("pause_until")
    if pause_until and pause_until != "EOD":
        try:
            pause_dt = datetime.fromisoformat(pause_until)
            if datetime.now(CST) < pause_dt:
                remaining = (pause_dt - datetime.now(CST)).seconds // 60
                log_msg(f"⏸️ 熔断中，剩余 {remaining} 分钟", "WARN")
                # 每五分钟才打一次日志避免刷屏
                if remaining % 5 == 0:
                    pass
                return False
        except:
            pass
    if pause_until == "EOD":
        today = datetime.now(CST).strftime("%Y-%m-%d")
        tomorrow = (datetime.now(CST) + timedelta(days=1)).strftime("%Y-%m-%d")
        cb["date"] = today
        if cb.get("date") != today:
            cb["pause_until"] = None
            cb["paused_today"] = False
            _save_cb(cb)
            return True
        if datetime.now(CST).hour < 6:
            return False  # 凌晨不开
        cb["date"] = tomorrow
        cb["pause_until"] = None
        cb["paused_today"] = False
        _save_cb(cb)
        return True
    return True


def record_trade_result(profit: float):
    """记录交易结果并更新熔断器"""
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
            log_msg(f"🔴 连续 {cl} 笔亏损，熔断 {LB_COOLDOWN_MIN} 分钟至 {cooldown_end.strftime('%H:%M')}", "WARN")
    else:
        cb["consecutive_losses"] = 0  # 赢则重置
    _save_cb(cb)


def check_risk(signal: dict, positions: dict, risk_cfg: dict, mt5) -> tuple:
    """风控检查（精简版，硬编码参数）"""
    import MetaTrader5 as mt5_module
    max_total = 6
    max_per_group = 1
    max_same_pct = 0.7
    max_spread_pct = 0.005
    groups = {
        "贵金属": ["XAUUSD", "XAGUSD"],
        "原油": ["USOIL", "UKOIL", "XNGUSD"],
        "美指": ["US30", "US500", "USTEC"],
        "日经": ["JP225"],
        "恒指": ["HK50"],
        "外汇": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD"],
        "铜": ["XCUUSD"],
        "美元指数": ["DXY"],
    }
    symbol = signal.get("symbol", "")
    direction = signal.get("direction", "").upper()
    held = positions.get("positions", [])
    held_count = len(held)
    held_symbols = positions.get("held_symbols", set())
    same_dir_count = sum(1 for p in held if p["type"] == direction)
    same_sym_count = sum(1 for p in held if p["symbol"] == symbol)
    if held_count >= max_total:
        return False, f"总持仓 {held_count} >= {max_total}"
    if symbol in held_symbols:
        return False, f"已有 {symbol} 持仓"
    symbol_group = None
    for gname, members in groups.items():
        if symbol in members:
            symbol_group = gname
            break
    if symbol_group:
        group_count = sum(1 for p in held if p["symbol"] in groups[symbol_group])
        if group_count >= max_per_group:
            return False, f"同组 {symbol_group} 已达上限"
    if held_count > 0:
        new_same_pct = (same_dir_count + 1) / (held_count + 1)
        if new_same_pct > max_same_pct:
            return False, f"同方向占比 {new_same_pct:.0%} > {max_same_pct:.0%}"
    # 总风险检查（已有持仓 + 新开的总风险不超 8%）
    current_total_risk = positions.get("total_volume", 0) * 100  # 估算
    if signal.get("lots_estimate", 0.01) > 0:
        new_volume = signal.get("lots_estimate", 0.01)
        est_risk_pct = new_volume / 100.0  # 粗略估算
        import MetaTrader5 as mt5_module
        acct = mt5_module.account_info()
        if acct and acct.balance > 0:
            total_risk_pct = (current_total_risk / 100.0 + est_risk_pct)
            if total_risk_pct > MAX_TOTAL_RISK_PCT * 100:
                return False, f"总风险 {total_risk_pct:.0f}% > {MAX_TOTAL_RISK_PCT*100:.0f}%"
    try:
        tick = mt5_module.symbol_info_tick(symbol)
        if tick and signal.get("current_price", 0) > 0:
            spread_pct = (tick.ask - tick.bid) / signal["current_price"]
            if spread_pct > max_spread_pct:
                return False, f"点差 {spread_pct*100:.4f}% > {max_spread_pct*100:.2f}%"
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
    sym_info = mt5_module.symbol_info(symbol)
    if not sym_info:
        return {"status": "FAILED", "error": f"Cannot get symbol info for {symbol}"}
    digits = sym_info.digits
    point = sym_info.point
    # 算手数（风险 3% 净值，硬上限 1 手）
    sl = sl_price or price * 0.99
    sl_points = abs(price - sl) / point if point > 0 else 100
    risk_pct = MAX_POSITION_RISK_PCT  # 3%
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
        "comment": f"PA {signal.get('signal_type','auto')}",
        "type_time": mt5_module.ORDER_TIME_GTC,
        "type_filling": mt5_module.ORDER_FILLING_IOC,
    }
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
            break
    if result and result.retcode == 10009:
        return {"status": "SUCCESS", "ticket": result.order, "price": result.price,
                "lots": lots, "sl": sl_price, "tp": tp_price}
    return {"status": "FAILED", "error": f"Order failed: {result.retcode if result else 'No result'}"}


def manage_breakeven(mt5, positions: dict) -> list:
    """半程盈亏平衡管理"""
    import MetaTrader5 as mt5_module
    adjustments = []
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
    return adjustments


def write_trigger(signal: dict, result: dict) -> str:
    """写入 trigger 文件"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:19]
    trigger_path = os.path.join(TRIGGER_DIR, f"trade_{ts}.json")
    trigger_data = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "type": "price_action",
        "signal": signal,
        "trade_result": result,
    }
    with open(trigger_path, "w") as f:
        json.dump(trigger_data, f, ensure_ascii=False, indent=2)
    return trigger_path


def calc_rolling_sharpe(closes: list[float], period: int = 20) -> float:
    """滚动夏普：最近 period 个 close 收益率的均值/标准差，判断价格是否有序运动"""
    if len(closes) < period:
        return 0.0
    prices = closes[-period:]
    returns = []
    for i in range(1, len(prices)):
        prev = prices[i-1]
        if prev == 0:
            continue
        returns.append((prices[i] - prev) / prev)
    if not returns:
        return 0.0
    avg = sum(returns) / len(returns)
    var = sum((r - avg)**2 for r in returns) / len(returns)
    std = var ** 0.5
    if std == 0:
        return 0.0
    return avg / std  # 不年化，纯方向性参考


def track_closed_positions(mt5, last_tickets: set) -> set:
    """检测持仓关闭 → 更新熔断器"""
    try:
        positions = get_existing_positions(mt5)
        current_tickets = {p["ticket"] for p in positions["positions"]}
        closed = last_tickets - current_tickets
        if closed:
            # 查最近5分钟历史确认盈亏
            from_time = datetime.now(timezone.utc) - timedelta(minutes=5)
            history = mt5.history_deals_get(from_time, datetime.now(timezone.utc))
            if history:
                processed = set()
                for d in history:
                    if d.position_id in processed:
                        continue
                    if d.position_id and (d.ticket in closed or d.position_id in [p.get("ticket") for p in last_tickets]):
                        if abs(d.profit) > 0.01:
                            record_trade_result(d.profit)
                            processed.add(d.position_id)
            return current_tickets
        return last_tickets
    except:
        return last_tickets


def run_once(mt5, reader: TickReader, symbols: list[str], engine: PriceActionEngine) -> dict:
    """单次循环：喂数据 → 分析 → 风控 → 执行"""
    # ── 0. 熔断检查 ──
    if not check_circuit_breaker():
        return {"magic": MAGIC, "engine_alive": reader.is_alive(),
                "symbols_scanned": 0, "signals_found": 0,
                "signals_executed": 0, "signals_blocked": 0,
                "blocked_reasons": ["⛔ 熔断中"], "held_positions": 0,
                "held_symbols": []}

    risk_cfg = {}
    positions = get_existing_positions(mt5)
    held_symbols = positions["held_symbols"]

    # 1. 半程盈亏平衡管理
    be_adjustments = manage_breakeven(mt5, positions)
    for adj in be_adjustments:
        if adj["status"] == "SUCCESS":
            log_msg(f" BE {adj['symbol']} {adj['type']} ticket={adj['ticket']}")
    if be_adjustments:
        positions = get_existing_positions(mt5)
        held_symbols = positions["held_symbols"]

    # 2. 价格行为分析（带质量过滤）
    detected = []
    # 只分析 M5（M1 噪音太大）
    timeframes = ["M5"]

    for sym in symbols:
        if sym in held_symbols:
            continue
        for tf in timeframes:
            try:
                ind = reader.get_indicator(sym, tf)
                if not ind or not ind.get("bar_close"):
                    continue
                # 喂数据给引擎
                engine.feed(sym, tf, ind)
                # 分析
                signal = engine.analyze(sym, tf)
                if signal is None:
                    continue

                # === 信号质量过滤 ===
                abs_score = abs(signal["score"])
                confidence = signal.get("confidence", 0)
                candle_count = signal.get("candle_count", 0)
                signal_type = signal.get("signal_type", "mixed")
                
                # 分数不够
                if abs_score < MIN_SCORE:
                    continue
                # 置信度不够
                if confidence < MIN_CONFIDENCE:
                    continue
                # K线不够
                if candle_count < engine.MIN_CANDLES:
                    continue
                # 纯 mixed 类型（没有明确倾向）过滤
                if signal_type == "mixed" and abs_score < 8:
                    continue
                # 滚动夏普 < 0.15 跳过（价格无序震荡无方向）
                closes = [c["close"] for c in engine.get_candles(sym, tf, 20)]
                if calc_rolling_sharpe(closes) < 0.15:
                    continue

                # 构造交易信号
                atr = ind.get("atr14", 0) or 0
                current_price = ind.get("price") or ind.get("bar_close", 0)
                if not current_price:
                    continue
                # ATR 不可用时不发信号
                if not atr:
                    continue

                sl_distance = atr * 2.5 if atr else 0
                tp_distance = atr * 4.0 if atr else 0

                if signal["direction"] in ("long", "buy", "BUY"):
                    sl_price = round(current_price - sl_distance, 5) if sl_distance > 0 else None
                    tp_price = round(current_price + tp_distance, 5) if tp_distance > 0 else None
                else:
                    sl_price = round(current_price + sl_distance, 5) if sl_distance > 0 else None
                    tp_price = round(current_price - tp_distance, 5) if tp_distance > 0 else None

                trade_signal = {
                    "symbol": sym,
                    "timeframe": tf,
                    "direction": signal["direction"],
                    "current_price": current_price,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "atr": atr,
                    "score": signal["score"],
                    "confidence": signal["confidence"],
                    "signal_type": signal["signal_type"],
                    "reasons": signal["reasons"],
                    "candle_count": signal["candle_count"],
                    "data_source": "price_action_engine",
                }
                detected.append(trade_signal)
            except Exception as e:
                log_msg(f"Analyze {sym} {tf} error: {e}", "WARN")
                traceback.print_exc()

    # 3. 按信号强度排序，只取 TOP N
    detected.sort(key=lambda s: abs(s["score"]), reverse=True)
    detected = detected[:MAX_SIGNALS_PER_CYCLE]

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

        if status == "executed":
            trigger_path = write_trigger(sig, result)
            entry["trigger_path"] = trigger_path
            held_symbols.add(sig.get("symbol", ""))
            positions["held_symbols"] = held_symbols

    # 5. 日志汇总
    blocked_reasons = list(set(
        e.get("reason", "") for e in executed if e["status"] == "blocked"
    ))
    executed_count = sum(1 for e in executed if e["status"] == "executed")
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "magic": MAGIC,
        "engine_alive": reader.is_alive(),
        "symbols_scanned": len(symbols),
        "signals_found": len(detected),
        "signals_executed": executed_count,
        "signals_blocked": sum(1 for e in executed if e["status"] == "blocked"),
        "blocked_reasons": blocked_reasons,
        "held_positions": positions["count"],
        "held_symbols": list(held_symbols),
        "details": executed,
    }
    return summary


def main():
    once_mode = "--once" in sys.argv
    import MetaTrader5 as mt5_module

    log_msg(f" [PA] Price Action Autopilot starting (Magic {MAGIC})")
    log_msg(f"    Loop: {SLEEP_SEC}s")
    log_msg(f"    Mode: {'ONCE' if once_mode else 'DAEMON'}")

    reader = TickReader()
    engine = get_engine(max_candles=20)

    SYMBOLS = ["XAUUSD","XAGUSD","USTEC","US30","US500","JP225","HK50",
               "USOIL","UKOIL","EURUSD","GBPUSD","USDJPY","AUDUSD","USDCHF",
               "USDCAD","NZDUSD","XNGUSD","XCUUSD","DXY"]

    # MT5 并发保护
    WAIT_MAX = 15
    for attempt in range(WAIT_MAX):
        if reader.is_alive():
            break
        log_msg(f" [PA] 等待 Tick Engine 就绪... ({attempt+1}s)", "WARN")
        time.sleep(1)
    else:
        log_msg(" [PA] Tick Engine 未运行！降级模式", "WARN")

    jitter = random.uniform(3.0, 8.0)
    log_msg(f" [PA] MT5 连接前等待 {jitter:.1f}s (并发保护)")
    time.sleep(jitter)

    if once_mode:
        path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
        if not mt5_module.initialize(path=path):
            log_msg(f" [PA] MT5 init failed: {mt5_module.last_error()}", "ERROR")
            return
        try:
            summary = run_once(mt5_module, reader, SYMBOLS, engine)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        finally:
            mt5_module.shutdown()
        return

    # DAEMON 模式
    mt5 = None
    try:
        path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
        if not mt5_module.initialize(path=path):
            log_msg(f" [PA] MT5 init failed: {mt5_module.last_error()}", "ERROR")
            return
        mt5 = mt5_module
        acct = mt5.account_info()
        if acct:
            log_msg(f" [PA] MT5 connected: login={acct.login}, balance={acct.balance:.2f}")

        loop_count = 0
        known_tickets = set()
        while True:
            try:
                loop_start = time.time()
                loop_count += 1

                # 检测已关闭持仓 → 更新熔断器
                known_tickets = track_closed_positions(mt5, known_tickets)

                summary = run_once(mt5, reader, SYMBOLS, engine)

                if summary.get("signals_executed", 0) > 0:
                    log_msg(f"[PA] 执行 {summary['signals_executed']} 笔 | "
                            f"信号 {summary['signals_found']} | "
                            f"拦截 {summary['signals_blocked']} | "
                            f"持仓 {summary['held_positions']}")
                elif summary.get("signals_found", 0) > 0 and loop_count % 5 == 0:
                    reasons = "; ".join(summary.get("blocked_reasons", []))
                    log_msg(f"[PA] 信号 {summary['signals_found']} 被拦截 | "
                            f"{reasons} | 持仓 {summary['held_positions']}")
                elif loop_count % LOOP_LOG_INTERVAL == 0:
                    log_msg(f"[PA] 循环 #{loop_count} | 持仓 {summary.get('held_positions', 0)}")

                elapsed = time.time() - loop_start
                time.sleep(max(0.1, SLEEP_SEC - elapsed))

            except KeyboardInterrupt:
                log_msg("[PA] Autopilot stopped by user")
                break
            except Exception as e:
                log_msg(f"[PA] Loop error: {e}", "ERROR")
                traceback.print_exc()
                time.sleep(SLEEP_SEC * 2)
    finally:
        if mt5:
            try:
                mt5.shutdown()
                log_msg("[PA] MT5 disconnected")
            except:
                pass


if __name__ == "__main__":
    main()
