#!/usr/bin/env python3
"""
scanner_autopilot.py — 全自动扫描+风控+执行（每分钟自循环）

特点:
- 不依赖 AI/AI Cron，纯 Python 自运转
- 自带风控检查（同组/同方向/同品种/RR/DXY过滤）
- 有信号直接执行，日志写 logs/scans/
- 写入 trigger 标记文件，供 AI 汇报 Cron 读取

用法（Windows Python）:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/scripts/scanner_autopilot.py
"""
import json
import os
import sys
from datetime import datetime, timezone
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

# 复用 executor 的风控和下单函数
from execute_trade import check_risk, calculate_lot_size, place_order, load_config, connect_mt5 as scan_connect

# 复用 signal_scanner 的扫描引擎（支持新版 conditions 数组 + 跨TF）
try:
    from tick_reader import TickReader
    from signal_scanner import scan_strategy as scan_strategy_tick
    TICK_AVAILABLE = True
except ImportError:
    TICK_AVAILABLE = False

LOG_DIR = os.path.join(BASE, "logs", "scans")
TRIGGER_DIR = os.path.join(BASE, "logs", "triggers")
TRADE_LOG_DIR = os.path.join(BASE, "logs", "trades")


# ── 自包含扫描器（不依赖 signal_scanner，直接读 MT5） ──

_SESSION_MAP = {"asia": 0, "europe": 8, "us": 13}


def _get_session(hour: int) -> str:
    if hour < 8:  return "asia"
    if hour < 13: return "europe"
    return "us"


def _rsi(closes: list, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_g / avg_l))


def _atr(bars: list, period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[-i]["high"]
        l = bars[-i]["low"]
        pc = bars[-i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[:period]) / period


def scan_strategy_mt5(mt5, symbol: str, config: dict, dxy_bars: list | None) -> list:
    """扫描单品种策略（直接读 MT5 数据，不依赖 signal_scanner）"""
    signals = []
    strategy_id = config["id"]
    direction = config["direction"]
    tf_name = config["timeframe"]
    cond = config["entry_conditions"]

    # 映射 timeframe 到 MT5 常量
    TF_MAP = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
              "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1}
    mt5_tf = TF_MAP.get(tf_name)
    if not mt5_tf:
        return signals

    # 读 100 根 K 线
    raw = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 100)
    if raw is None or len(raw) < 30:
        return signals

    bars = []
    for b in raw:
        bars.append({"time": b["time"], "open": b["open"], "high": b["high"],
                      "low": b["low"], "close": b["close"],
                      "tick_volume": b.get("tick_volume", b.get("volume", 0))})

    closes = [b["close"] for b in bars]
    rsi = _rsi(closes)
    atr = _atr(bars)
    last_bar = bars[-1]
    current_price = last_bar["close"]
    utc_hour = last_bar["time"] // 3600 % 24 if isinstance(last_bar["time"], int) else 0
    session = _get_session(utc_hour)

    # 检查条件
    matched = True
    match_reasons = []

    if "session" in cond and cond["session"]:
        if cond["session"] != session:
            return signals
        match_reasons.append(f"session={session}")

    if "rsi14_max" in cond and rsi is not None:
        if rsi > cond["rsi14_max"]:
            return signals
        match_reasons.append(f"RSI={rsi:.1f}<{cond['rsi14_max']}")

    if "rsi14_min" in cond and rsi is not None:
        if rsi < cond["rsi14_min"]:
            return signals
        match_reasons.append(f"RSI={rsi:.1f}>{cond['rsi14_min']}")

    if "atr_min_pct" in cond and atr and current_price > 0:
        atr_pct = atr / current_price
        if atr_pct < cond["atr_min_pct"]:
            return signals
        match_reasons.append(f"ATR%={atr_pct*100:.3f}>{cond['atr_min_pct']*100:.2f}%")

    # DXY 过滤
    if dxy_bars and "dxy_filter" in cond:
        dxy_closes = [b["close"] for b in dxy_bars]
        dxy_rsi = _rsi(dxy_closes)
        dxy_last = dxy_closes[-1]
        dxy_ma20 = sum(dxy_closes[-20:]) / 20 if len(dxy_closes) >= 20 else dxy_last

        if cond["dxy_filter"] == "down":
            if not (dxy_last < dxy_ma20):
                return signals
            match_reasons.append(f"DXY↓({dxy_last:.3f}<MA20={dxy_ma20:.3f})")
        elif cond["dxy_filter"] == "up":
            if not (dxy_last > dxy_ma20):
                return signals
            match_reasons.append(f"DXY↑({dxy_last:.3f}>MA20={dxy_ma20:.3f})")

    # 通过所有条件 → 生成信号
    sl_distance = atr * 2.0 if atr else 0
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
        "direction": direction,
        "timeframe": tf_name,
        "entry_price": current_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "rr_ratio": round(tp_distance / sl_distance, 2) if sl_distance > 0 and tp_distance > 0 else 0,
        "rsi": round(rsi, 2) if rsi else None,
        "atr": round(atr, 5) if atr else None,
        "session": session,
        "match_reasons": ", ".join(match_reasons),
    }

    return [signal]


def write_trigger(signal: dict, result: dict):
    """写入 trigger 文件，供 AI Cron 读取"""
    os.makedirs(TRIGGER_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    trigger = {
        "timestamp_utc": now.isoformat(),
        "signal": signal,
        "result": result,
        "read": False,
    }
    path = os.path.join(TRIGGER_DIR, f"trigger_{now.strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w") as f:
        json.dump(trigger, f, ensure_ascii=False, indent=2)
    return path


def main():
    cfg = load_config()
    risk_cfg = cfg.get("risk", {})
    magic = cfg.get("magic_number", 234010)
    risk_pct = risk_cfg.get("risk_per_trade_pct", 0.05)
    all_signals = cfg.get("signals", [])

    # 1. 连接 MT5
    mt5, account = scan_connect()
    if mt5 is None:
        result = {"error": f"MT5 connect failed: {account}", "signals": []}
        print(json.dumps(result))
        return

    try:
        # 2. 获取 DXY 数据
        dxy_bars = None
        try:
            dxy_raw = mt5.copy_rates_from_pos("DXY", mt5.TIMEFRAME_H1, 0, 20)
            if dxy_raw is not None and len(dxy_raw) >= 6:
                dxy_bars = []
                for b in dxy_raw:
                    if isinstance(b, (dict, np.void)):
                        dxy_bars.append({"time": b["time"], "open": b["open"],
                                         "high": b["high"], "low": b["low"],
                                         "close": b["close"]})
                    else:
                        dxy_bars.append({"time": b.time, "open": b.open,
                                         "high": b.high, "low": b.low,
                                         "close": b.close})
        except:
            pass

        # 3. 扫描所有策略 — 优先使用 Tick Engine（支持新版条件格式）
        detected = []
        if TICK_AVAILABLE:
            try:
                reader = TickReader()
                if reader.is_alive():
                    dxy_indicators = reader.get_indicator("DXY", "H1")
                    for strategy in all_signals:
                        tf_name = strategy.get("timeframe", "M30")
                        for sym in strategy.get("symbols", []):
                            try:
                                sym_h1 = (reader.get_indicator(sym, "H1")
                                          if tf_name not in ("H1", "h1") else None)
                                sigs = scan_strategy_tick(
                                    sym, strategy, reader, dxy_indicators, sym_h1)
                                detected.extend(sigs)
                            except:
                                pass
            except Exception:
                pass  # fallback to MT5 direct scan

        if not detected:
            # 降级: 直连 MT5 扫描（仅支持旧版条件）
            for strategy in all_signals:
                for sym in strategy.get("symbols", []):
                    try:
                        sigs = scan_strategy_mt5(mt5, sym, strategy, dxy_bars)
                        detected.extend(sigs)
                    except:
                        pass

        scan_result = {
            "timestamp": datetime.utcnow().isoformat(),
            "account": {"balance": account["balance"], "equity": account["equity"]},
            "magic": magic,
            "signals": detected,
            "total_signals": len(detected),
        }

        # 4. 持久化日志（每次必写）
        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        scan_log_path = os.path.join(LOG_DIR, f"scan_{ts}.json")
        with open(scan_log_path, "w") as f:
            json.dump(scan_result, f, ensure_ascii=False, indent=2)

        # 5. 有信号 → DXY二次检查 + 风控 + 执行
        executed = []
        for sig in detected:
            # DXY 硬过滤（如果 required 但没通过，跳过）
            dxy_check = sig.get("dxy_check")
            if dxy_check and not dxy_check.get("passed", True):
                executed.append({"signal": sig, "status": "dxy_blocked",
                                 "reason": f"DXY filter: required={dxy_check['required']} but DXY moved opposite"})
                continue

            allowed, reason = check_risk(mt5, sig, risk_cfg, magic)
            if not allowed:
                executed.append({"signal": sig, "status": "risk_blocked", "reason": reason})
                continue

            # 计算手数
            lot_size = calculate_lot_size(mt5, sig["symbol"], sig, risk_pct, account["equity"], risk_cfg)

            # 执行
            trade_result = place_order(mt5, sig, lot_size, magic, risk_cfg)
            entry = {"signal": sig, "lot_size": lot_size, "result": trade_result, "status": "executed"}
            executed.append(entry)

            # 写入 trigger（AI 汇报用）
            trigger_path = write_trigger(sig, trade_result)
            entry["trigger_path"] = trigger_path

            # 写入 trade log
            os.makedirs(TRADE_LOG_DIR, exist_ok=True)
            trade_log_path = os.path.join(TRADE_LOG_DIR, f"trade_{ts}.json")
            with open(trade_log_path, "w") as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)

        # 6. 输出摘要
        output = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "equity": account.get("equity", 0),
            "scan_log": scan_log_path,
            "signals_found": len(detected),
            "signals_executed": sum(1 for e in executed if e["status"] == "executed"),
            "dxy_blocked": sum(1 for e in executed if e["status"] == "dxy_blocked"),
            "risk_blocked": sum(1 for e in executed if e["status"] == "risk_blocked"),
            "details": executed,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
