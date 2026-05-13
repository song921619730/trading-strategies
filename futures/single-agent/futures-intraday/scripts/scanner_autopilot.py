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

# 复用 scanner 和 executor 的子函数
from signal_scanner import connect_mt5 as scan_connect, scan_strategy
from execute_trade import check_risk, calculate_lot_size, place_order, load_config

LOG_DIR = os.path.join(BASE, "logs", "scans")
TRIGGER_DIR = os.path.join(BASE, "logs", "triggers")
TRADE_LOG_DIR = os.path.join(BASE, "logs", "trades")


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

        # 3. 扫描所有策略
        detected = []
        for strategy in all_signals:
            for sym in strategy.get("symbols", []):
                try:
                    sigs = scan_strategy(mt5, sym, strategy, account, dxy_bars)
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
