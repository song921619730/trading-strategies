#!/usr/bin/env python3
"""
signal_scanner.py — M30/H1 信号扫描引擎（Tick Engine 版，全指标支持）

从 Tick Engine 共享数据读取 tick + 319 指标 → 匹配 strategies.json → 输出信号
不复连 MT5。DXY 过滤也从共享数据读取。

用法（任意 Python）:
  python3 signal_scanner.py

输出：JSON 格式的信号列表（stdout）
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

# ─── 路径 ───
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "strategies.json")
LOG_DIR = os.path.join(BASE, "logs", "signals")

# 添加共享库路径
_SHARED_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(BASE)), "scripts")
if _SHARED_SCRIPTS not in sys.path:
    sys.path.insert(0, _SHARED_SCRIPTS)

from tick_reader import TickReader
from condition_utils import evaluate_entry_conditions, has_old_format


def utcnow():
    return datetime.now(timezone.utc)


def scan_strategy(symbol: str, config: dict, reader: TickReader,
                  dxy_indicators: dict | None = None,
                  h1_indicators: dict | None = None) -> list:
    """扫描单个策略（从 TickReader 读指标，不复连 MT5）"""
    signals = []
    strategy_id = config["id"]
    direction = config["direction"]
    tf_name = config["timeframe"]

    # ── 读取共享指标（全部 319 个字段） ──
    ind = reader.get_indicator(symbol, tf_name)
    if not ind:
        return signals

    # 从共享数据读取当前 tick
    tick = reader.get_tick(symbol)
    if not tick:
        return signals

    current_price = ind.get("price", tick.get("bid", tick.get("ask", 0)))
    atr = ind.get("atr14")
    entry_conditions = config.get("entry_conditions", {})

    # ── 通用条件求值（兼容新旧格式，支持 319 个指标 + 跨TF） ──
    matched, match_reasons = evaluate_entry_conditions(
        entry_conditions, ind, dxy_indicators, h1_indicators,
    )

    if matched and match_reasons:
        # SL/TP 计算 — 优先使用策略配置的倍数，否则默认 2.0/4.0
        ec = entry_conditions
        sl_mult = ec.get("sl_multiple", 2.0) if isinstance(ec, dict) else 2.0
        tp_mult = ec.get("tp_multiple", 4.0) if isinstance(ec, dict) else 4.0
        sl_distance = atr * sl_mult if atr else 0
        tp_distance = atr * tp_mult if atr else 0

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
            "current_price": current_price,
            "rsi": ind.get("rsi14"),
            "atr": round(atr, 5) if atr else None,
            "atr_pct": round(atr / current_price * 100, 3) if atr and current_price > 0 else None,
            "session": ind.get("session"),
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


def main():
    if not os.path.exists(CONFIG_PATH):
        result = {"error": f"Config not found: {CONFIG_PATH}", "signals": []}
        print(json.dumps(result, ensure_ascii=False))
        return

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    all_signals = cfg.get("signals", [])
    risk_cfg = cfg.get("risk", {})
    magic = cfg.get("magic_number", 234010)

    reader = TickReader()
    engine_alive = reader.is_alive()

    # 从共享数据读取 DXY 指标（不复连 MT5）
    dxy_indicators = reader.get_indicator("DXY", "H1") if engine_alive else None

    ticks_start = datetime.now()
    detected = []
    for strategy in all_signals:
        tf_name = strategy.get("timeframe", "M30")
        for sym in strategy.get("symbols", []):
            try:
                # 跨TF: 读取该品种 H1 指标（用于 _h1_* 条件）
                sym_h1 = (reader.get_indicator(sym, "H1")
                          if engine_alive and tf_name not in ("H1", "h1") else None)
                sigs = scan_strategy(sym, strategy, reader, dxy_indicators, sym_h1)
                detected.extend(sigs)
            except Exception:
                pass

    ticks_end = datetime.now()

    result = {
        "timestamp": utcnow().isoformat(),
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
