#!/usr/bin/env python3
"""
scalping_scanner.py — M1/M5 信号扫描引擎（Tick Engine 版，全指标支持）

从 Tick Engine 的共享数据读取 tick + 319 指标 → 匹配 scalping_strategies.json → 输出信号

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
from condition_utils import evaluate_entry_conditions, has_old_format

# ─── 扫描单个策略 ───
def scan_strategy(symbol: str, config: dict, reader: TickReader, account: dict) -> list:
    signals = []
    strategy_id = config["id"]
    direction = config["direction"]
    tf_name = config["timeframe"]
    cond = config.get("entry_conditions", {})
    best_hold = config.get("best_hold", 5)

    # 从共享数据读取指标（全部 319 个字段）
    ind = reader.get_indicator(symbol, tf_name)
    if not ind:
        return signals

    # 从共享数据读取当前 tick
    tick = reader.get_tick(symbol)
    if not tick:
        return signals

    current_price = ind.get("price", tick.get("bid", tick.get("ask", 0)))
    atr = ind.get("atr14")
    spread = tick.get("spread", 0)

    # ── 通用条件求值（兼容新旧格式） ──
    matched, match_reasons = evaluate_entry_conditions(cond, ind)

    if matched and match_reasons:
        # ── Scalping SL/TP 计算 ──
        sl_distance = atr * 2.5 if atr else 0
        tp_distance = atr * 4.0 if atr else 0

        # ATR 不可用时不发信号（无 SL/TP 无法开仓）
        if not atr:
            return signals

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
            "rsi": ind.get("rsi14"),
            "atr": round(atr, 5) if atr else None,
            "atr_pct": round(atr / current_price * 100, 3) if atr and current_price > 0 else None,
            "session": ind.get("session"),
            "spread": spread,
            "match_reasons": "; ".join(match_reasons),
            "sl_price": sl_price,
            "tp_price": tp_price,
            "sl_distance": round(sl_distance, 5) if sl_distance > 0 else None,
            "tp_distance": round(tp_distance, 5) if tp_distance > 0 else None,
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
