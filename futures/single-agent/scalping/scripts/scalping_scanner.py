#!/usr/bin/env python3
"""
scalping_scanner.py — M1/M5 信号扫描引擎（Tick Engine 版）

从 Tick Engine 的共享数据读取 tick + 指标 → 匹配 scalping_strategies.json → 输出信号

不再直接连接 MT5（由 Tick Engine 统一管理）。
如果 Tick Engine 不在运行，自动降级到 tick_reader 的 fallback 模式。

用法（任意 Python 环境，无需 MT5 库）:
  python3 scalping_scanner.py

输出：JSON 格式的信号列表（stdout）
"""

import json
import os
import sys
from datetime import datetime, timezone

def utcnow():
    return datetime.now(timezone.utc)

# ─── 路径 ───
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "scalping_strategies.json")
LOG_DIR = os.path.join(BASE, "logs", "signals")

# 添加共享库路径
_SHARED_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(BASE)), "scripts")
if _SHARED_SCRIPTS not in sys.path:
    sys.path.insert(0, _SHARED_SCRIPTS)

from tick_reader import TickReader
from indicators import get_session, SESSION_ALIAS

# ─── Session 别名（兼容旧配置） ───
SESSION_ALIAS_MAP = SESSION_ALIAS  # {"london": "europe"}

# ─── 扫描单个策略 ───
def scan_strategy(symbol: str, config: dict, reader: TickReader, account: dict) -> list:
    signals = []
    strategy_id = config["id"]
    direction = config["direction"]
    tf_name = config["timeframe"]
    cond = config.get("entry_conditions", {})
    best_hold = config.get("best_hold", 5)

    # 从共享数据读取指标（Tick Engine 已算好）
    ind = reader.get_indicator(symbol, tf_name)
    if not ind:
        return signals

    # 从共享数据读取当前 tick
    tick = reader.get_tick(symbol)
    if not tick:
        return signals

    # 提取值
    current_price = ind.get("price", tick.get("bid", tick.get("ask", 0)))
    rsi = ind.get("rsi14")
    atr = ind.get("atr14")
    session = ind.get("session", reader.get_session())
    consecutive_bears = ind.get("consecutive_bear", 0)
    current_utc_hour = ind.get("utc_hour", 0)
    spread = tick.get("spread", 0)

    # 逐条件检查
    matched = True
    match_reasons = []

    if "session" in cond and cond["session"]:
        required_session = SESSION_ALIAS_MAP.get(cond["session"], cond["session"])
        if required_session != session:
            matched = False
        else:
            match_reasons.append(f"session={session}")

    if "rsi14_max" in cond:
        if rsi is None or rsi > cond["rsi14_max"]:
            matched = False
        else:
            match_reasons.append(f"RSI={rsi:.1f}<{cond['rsi14_max']}")

    if "rsi14_min" in cond:
        if rsi is None or rsi < cond["rsi14_min"]:
            matched = False
        else:
            match_reasons.append(f"RSI={rsi:.1f}>{cond['rsi14_min']}")

    if "atr_min_pct" in cond and atr:
        atr_pct = atr / current_price if current_price > 0 else 0
        if atr_pct < cond["atr_min_pct"]:
            matched = False
        else:
            match_reasons.append(f"ATR%={atr_pct*100:.3f}>{cond['atr_min_pct']*100:.2f}%")

    if "consecutive_bear" in cond:
        if consecutive_bears < cond["consecutive_bear"]:
            matched = False
        else:
            match_reasons.append(f"连阴={consecutive_bears}")

    # Hour 窗口
    if "hour_start" in cond:
        if current_utc_hour < cond["hour_start"] or current_utc_hour >= cond.get("hour_end", 24):
            matched = False
        else:
            match_reasons.append(f"hour=[{cond['hour_start']}-{cond.get('hour_end',24)})")
    elif "hour_end" in cond:
        if current_utc_hour >= cond["hour_end"]:
            matched = False
        else:
            match_reasons.append(f"hour<{cond['hour_end']}")

    if matched and match_reasons:
        # ── Scalping SL/TP 计算 ──
        sl_distance = atr * 2.5 if atr else 0
        tp_distance = atr * 4.0 if atr else 0

        if direction in ("long", "buy", "BUY"):
            sl_price = round(current_price - sl_distance, 5) if sl_distance > 0 else None
            tp_price = round(current_price + tp_distance, 5) if tp_distance > 0 else None
        else:
            sl_price = round(current_price + sl_distance, 5) if sl_distance > 0 else None
            tp_price = round(current_price - tp_distance, 5) if tp_distance > 0 else None

        signal = {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timeframe": tf_name,
            "direction": direction,
            "best_hold": best_hold,
            "current_price": current_price,
            "rsi": float(round(rsi, 2)) if rsi else None,
            "atr": float(round(atr, 5)) if atr else None,
            "atr_pct": float(round(atr / current_price * 100, 3)) if atr and current_price > 0 else None,
            "session": session,
            "consecutive_bears": int(consecutive_bears),
            "spread": spread,
            "utc_hour": int(current_utc_hour),
            "match_reasons": "; ".join(match_reasons),
            "sl_price": sl_price,
            "tp_price": tp_price,
            "sl_distance": float(round(sl_distance, 5)) if sl_distance > 0 else None,
            "tp_distance": float(round(tp_distance, 5)) if tp_distance > 0 else None,
            "rr": round(tp_distance / sl_distance, 2) if sl_distance > 0 and tp_distance > 0 else None,
            "detected_at_utc": utcnow().isoformat(),
            "data_source": "tick_engine",
        }
        signals.append(signal)

    return signals


# ─── 主函数 ───
def main():
    if not os.path.exists(CONFIG_PATH):
        result = {"error": f"Config not found: {CONFIG_PATH}", "signals": []}
        print(json.dumps(result, ensure_ascii=False))
        return

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    all_signals = cfg.get("signals", [])
    risk_cfg = cfg.get("risk", {})
    magic = cfg.get("magic_number", 234011)

    reader = TickReader()

    # 检查 Tick Engine 是否在运行
    engine_alive = reader.is_alive()
    account = {"balance": None, "equity": None}
    if engine_alive:
        hb = reader._read("_heartbeat.json")
        if hb:
            account["balance"] = hb.get("balance", "N/A")
            account["equity"] = hb.get("equity", "N/A")

    ticks_start = datetime.now()
    detected = []
    for strategy in all_signals:
        for sym in strategy.get("symbols", []):
            try:
                sigs = scan_strategy(sym, strategy, reader, account)
                detected.extend(sigs)
            except Exception:
                pass  # silently skip symbol errors

    ticks_end = datetime.now()

    result = {
        "timestamp": utcnow().isoformat(),
        "account": account,
        "data_source": "tick_engine" if engine_alive else "unknown",
        "engine_alive": engine_alive,
        "magic": magic,
        "scan_duration_ms": int((ticks_end - ticks_start).total_seconds() * 1000),
        "signals": detected,
        "total_signals": len(detected),
        "strategies_scanned": len(all_signals),
        "risk_config": risk_cfg,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 保存日志
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, f"scan_{ts}.json")
    with open(log_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[LOG] Saved to logs/signals/scan_{ts}.json", file=sys.stderr)


if __name__ == "__main__":
    main()
