#!/usr/bin/env python3
"""
scalping_scanner.py — M1/M5 信号扫描引擎

从 MT5 拉取 M1/M5 数据 → 计算 RSI/ATR/连阴 → 匹配 scalping_strategies.json → 输出信号

用法（在 WSL 中调用 Windows Python）:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/scripts/scalping_scanner.py

输出：JSON 格式的信号列表（stdout）
"""
import json
import os
import sys
import numpy as np
from datetime import datetime, timezone, timedelta

# ─── 路径 ───
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "scalping_strategies.json")
LOG_DIR = os.path.join(BASE, "logs", "signals")

# ─── MT5 连接 ───
def connect_mt5():
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


# ─── Session 映射 ───
SESSION_MAP = {
    "asia":  (0, 8),
    "europe":(8, 13),
    "us":    (13, 22),
}
SESSION_ALIAS = {"london": "europe", "europe": "europe"}

def get_session(utc_hour: int) -> str:
    for name, (start, end) in SESSION_MAP.items():
        if start <= utc_hour < end:
            return name
    return "asia"


# ─── 技术指标 ───
def calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calc_atr(bars: list[dict], period: int = 14) -> float | None:
    """计算 M1/M5 周期的 ATR(14)"""
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[-i]["high"]
        l = bars[-i]["low"]
        pc = bars[-i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sum(trs[:period]) / period


def detected_consecutive_bears(bars: list[dict]) -> int:
    count = 0
    for bar in reversed(bars):
        if bar["close"] < bar["open"]:
            count += 1
        else:
            break
    return count


# ─── TF 映射 ───
TF_MAP = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60}


def get_mt5_tf(mt5, tf_name: str):
    name = f"TIMEFRAME_{tf_name}"
    return getattr(mt5, name, None)


# ─── 扫描单个策略 ───
def scan_strategy(mt5, symbol: str, config: dict, account: dict) -> list:
    signals = []
    strategy_id = config["id"]
    direction = config["direction"]
    tf_name = config["timeframe"]
    cond = config.get("entry_conditions", {})
    best_hold = config.get("best_hold", 5)

    mt5_tf = get_mt5_tf(mt5, tf_name)
    if mt5_tf is None:
        return signals

    needed = 40 if "consecutive_bear" in cond else 30
    bars = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, needed)
    if bars is None or len(bars) < 20:
        return signals

    bars_list = []
    for b in bars:
        bars_list.append({
            "time": b["time"] if isinstance(b, (dict, np.void)) else b.time,
            "open": b["open"] if isinstance(b, (dict, np.void)) else b.open,
            "high": b["high"] if isinstance(b, (dict, np.void)) else b.high,
            "low": b["low"] if isinstance(b, (dict, np.void)) else b.low,
            "close": b["close"] if isinstance(b, (dict, np.void)) else b.close,
            "volume": b["tick_volume"] if isinstance(b, (dict, np.void)) else b.tick_volume,
        })

    latest = bars_list[-1]
    closes = [b["close"] for b in bars_list]
    current_price = latest["close"]
    current_utc_hour = datetime.fromtimestamp(latest["time"], tz=timezone.utc).hour

    # 计算指标
    rsi = calc_rsi(closes)
    atr = calc_atr(bars_list)
    session = get_session(current_utc_hour)
    consecutive_bears = detected_consecutive_bears(bars_list)

    # 逐条件检查
    matched = True
    match_reasons = []

    if "session" in cond and cond["session"]:
        required_session = SESSION_ALIAS.get(cond["session"], cond["session"])
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

    if matched:
        if not match_reasons:
            match_reasons.append("no_entry_conditions")
        # ── Scalping SL/TP 计算 ──
        # SL = ATR(M5/M1) × 2.5, TP = ATR(M5/M1) × 3.75 (RR=1.5)
        sl_distance = atr * 2.5 if atr else 0
        tp_distance = atr * 3.75 if atr else 0

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
            "utc_hour": int(current_utc_hour),
            "match_reasons": "; ".join(match_reasons),
            "sl_price": sl_price,
            "tp_price": tp_price,
            "sl_distance": float(round(sl_distance, 5)) if sl_distance > 0 else None,
            "tp_distance": float(round(tp_distance, 5)) if tp_distance > 0 else None,
            "rr": round(tp_distance / sl_distance, 2) if sl_distance > 0 and tp_distance > 0 else None,
            "detected_at_utc": datetime.utcnow().isoformat(),
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

    mt5, account = connect_mt5()
    if mt5 is None:
        result = {"error": account, "signals": [], "timestamp": datetime.utcnow().isoformat()}
        print(json.dumps(result, ensure_ascii=False))
        return

    try:
        ticks_start = datetime.now()
        detected = []
        for strategy in all_signals:
            for sym in strategy.get("symbols", []):
                try:
                    mt5.symbol_select(sym, True)
                    sigs = scan_strategy(mt5, sym, strategy, account)
                    detected.extend(sigs)
                except Exception:
                    pass  # silently skip symbol errors

        ticks_end = datetime.now()

        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "account": {
                "balance": account["balance"],
                "equity": account["equity"],
            },
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
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(LOG_DIR, f"scan_{ts}.json")
        with open(log_path, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[LOG] Saved to logs/signals/scan_{ts}.json", file=sys.stderr)

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
