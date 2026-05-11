#!/usr/bin/env python3
"""
scanner_autopilot.py — 全自动扫描+风控+执行（每分钟自循环）

特点:
- 不依赖 AI/AI Cron，纯 Python 自运转
- 自带风控检查（同组/同方向/同品种/RR）
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

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

# 复用 scanner 和 executor
from signal_scanner import connect_mt5 as scan_connect, run_scan
from execute_trade import check_risk, calculate_lot_size, place_order, load_config, log_scan

LOG_DIR = os.path.join(BASE, "logs", "scans")
TRIGGER_DIR = os.path.join(BASE, "logs", "triggers")

def write_trigger(signal: dict, result: dict):
    """写入 trigger 文件，供 AI Cron 读取"""
    os.makedirs(TRIGGER_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    trigger = {
        "timestamp_utc": now.isoformat(),
        "signal": signal,
        "result": result,
        "read": False,  # AI 读取后标记为 True
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

    # 1. 连接 MT5
    mt5, account = scan_connect()
    if mt5 is None:
        result = {"error": f"MT5 connect failed: {account}", "signals": []}
        print(json.dumps(result))
        return

    try:
        # 2. 运行扫描
        scan_result = run_scan(mt5, cfg)
        signals = scan_result.get("signals", [])

        # 3. 持久化日志（每次必写）
        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        scan_log_path = os.path.join(LOG_DIR, f"scan_{ts}.json")
        with open(scan_log_path, "w") as f:
            json.dump(scan_result, f, ensure_ascii=False, indent=2)

        # 4. 有信号 → 风控 + 执行
        executed = []
        for sig in signals:
            allowed, reason = check_risk(mt5, sig, risk_cfg, magic)
            if not allowed:
                executed.append({"signal": sig, "status": "blocked", "reason": reason})
                continue

            # 计算手数
            lot_size = calculate_lot_size(mt5, sig["symbol"], sig, risk_pct, account["equity"], risk_cfg)

            # 执行
            trade_result = place_order(mt5, sig, lot_size, magic, risk_cfg)
            result_entry = {"signal": sig, "lot_size": lot_size, "result": trade_result, "status": "executed"}
            executed.append(result_entry)

            # 写入 trigger
            trigger_path = write_trigger(sig, trade_result)
            result_entry["trigger_path"] = trigger_path

            # 写入 trade log
            os.makedirs(os.path.join(BASE, "logs", "trades"), exist_ok=True)
            trade_log_path = os.path.join(BASE, "logs", "trades", f"trade_{ts}.json")
            with open(trade_log_path, "w") as f:
                json.dump(result_entry, f, ensure_ascii=False, indent=2)

        # 5. 输出摘要（stdout）
        output = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "equity": account.get("equity", 0),
            "scan_log": scan_log_path,
            "signals_found": len(signals),
            "signals_executed": sum(1 for e in executed if e["status"] == "executed"),
            "signal_blocked": sum(1 for e in executed if e["status"] == "blocked"),
            "details": executed,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
