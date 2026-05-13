#!/usr/bin/env python3
"""
signal_scanner.py — 信号扫描引擎

从 MT5 拉取 H1/M30 数据 → 计算 RSI/ATR/连阴 → 匹配 strategies.json → 输出信号

用法（在 WSL 中调用 Windows Python）：
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/scripts/signal_scanner.py

输出：JSON 格式的信号列表（stdout）
"""
import json
import os
import sys
import math
import numpy as np
from datetime import datetime, timezone, timedelta

# ─── 路径 ───
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "strategies.json")
LOG_DIR = os.path.join(BASE, "logs", "signals")

# ─── MT5 连接（Windows only） ───
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


# ─── 技术指标 ───
SESSION_MAP = {
    "asia":  (0, 8),    # 00:00-08:00 UTC
    "europe":(8, 13),   # 08:00-13:00 UTC（纯欧盘，美盘开盘前）
    "us":    (13, 22),  # 13:00-22:00 UTC（美盘+欧盘重叠期归美盘）
}

# 兼容旧名 "london" 和 "europe"
SESSION_ALIAS = {
    "london": "europe",
    "europe": "europe",
}

def get_session(utc_hour: int) -> str:
    for name, (start, end) in SESSION_MAP.items():
        if start <= utc_hour < end:
            return name
    return "asia"

def calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
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


# ─── 信号匹配 ───
def scan_strategy(mt5, symbol: str, config: dict, account: dict, dxy_data: list | None = None) -> list:
    """对单个品种扫描一个策略配置，返回匹配的信号列表"""
    signals = []
    strategy_id = config["id"]
    direction = config["direction"]
    tf_name = config["timeframe"]
    cond = config["entry_conditions"]
    
    # 时间框架映射
    TF_MAP = {"M30": 30, "H1": 60}
    mt5_tf = getattr(mt5, f"TIMEFRAME_{tf_name}", None)
    if mt5_tf is None:
        return signals
    
    # 获取数据（需要 extra bars 用于指标计算）
    needed = 40 if "consecutive_bear" in cond else 30
    bars = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, needed)
    if bars is None or len(bars) < 20:
        return signals
    
    # 转换（numpy void → dict，兼容新旧 MT5 API）
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
    
    # 取最新 K 线
    latest = bars_list[-1]
    closes = [b["close"] for b in bars_list]
    current_close = latest["close"]
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
        # 统一 session 名称：兼容 "europe"/"london"
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
        atr_pct = atr / current_close if current_close > 0 else 0
        if atr_pct < cond["atr_min_pct"]:
            matched = False
        else:
            match_reasons.append(f"ATR%={atr_pct*100:.3f}>{cond['atr_min_pct']*100:.2f}%")
    
    if "consecutive_bear" in cond:
        if consecutive_bears < cond["consecutive_bear"]:
            matched = False
        else:
            match_reasons.append(f"连阴={consecutive_bears}")
    
    if matched and match_reasons:
        signal = {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timeframe": tf_name,
            "direction": direction,
            "current_price": current_close,
            "rsi": float(round(rsi, 2)) if rsi else None,
            "atr": float(round(atr, 5)) if atr else None,
            "atr_pct": float(round(atr / current_close * 100, 3)) if atr and current_close > 0 else None,
            "session": session,
            "consecutive_bears": int(consecutive_bears),
            "utc_hour": int(current_utc_hour),
            "match_reasons": "; ".join(match_reasons),
            "detected_at_utc": datetime.utcnow().isoformat(),
        }
        
        # ── DXY 过滤 ──
        dxy_filter = cond.get("dxy_filter")
        if dxy_filter and dxy_data is not None:
            dxy_recent = dxy_data[-6:]  # 最近6根DXY K线看趋势
            if dxy_filter == "down":
                # DXY 下跌：最后一根 close < 倒数第2根 close
                dxy_down = dxy_recent[-1]["close"] < dxy_recent[-2]["close"]
                signal["dxy_check"] = {
                    "required": dxy_filter,
                    "passed": bool(dxy_down),
                    "current": float(dxy_recent[-1]["close"]),
                    "prev": float(dxy_recent[-2]["close"]),
                    "change_pct": round((dxy_recent[-1]["close"] - dxy_recent[-2]["close"]) / dxy_recent[-2]["close"] * 100, 3)
                }
                signal["match_reasons"] += f"; DXY{'↓' if dxy_down else '↑'}"
            elif dxy_filter == "up":
                dxy_up = dxy_recent[-1]["close"] > dxy_recent[-2]["close"]
                signal["dxy_check"] = {
                    "required": dxy_filter,
                    "passed": bool(dxy_up),
                    "current": float(dxy_recent[-1]["close"]),
                    "prev": float(dxy_recent[-2]["close"]),
                    "change_pct": round((dxy_recent[-1]["close"] - dxy_recent[-2]["close"]) / dxy_recent[-2]["close"] * 100, 3)
                }
                signal["match_reasons"] += f"; DXY{'↑' if dxy_up else '↓'}"
        
        signals.append(signal)
    
    return signals


def main():
    # 加载配置
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    
    all_signals = cfg.get("signals", [])
    risk_cfg = cfg.get("risk", {})
    magic = cfg.get("magic_number", 234010)
    
    # 连接 MT5
    mt5, account = connect_mt5()
    if mt5 is None:
        result = {"error": account, "signals": [], "timestamp": datetime.utcnow().isoformat()}
        print(json.dumps(result, ensure_ascii=False))
        return
    
    try:
        # ── 获取 DXY 数据（用于过滤） ──
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
        
        # 品种列表（去重）
        symbols_set = set()
        for s in all_signals:
            for sym in s.get("symbols", []):
                if not mt5.symbol_select(f"{sym}m", True):
                    symbols_set.add(sym)
                else:
                    symbols_set.add(sym)
        
        # 扫描所有策略
        detected = []
        for strategy in all_signals:
            for sym in strategy.get("symbols", []):
                try:
                    sigs = scan_strategy(mt5, sym, strategy, account, dxy_bars)
                    detected.extend(sigs)
                except Exception as e:
                    pass  # silently skip symbol errors
        
        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "account": {
                "balance": account["balance"],
                "equity": account["equity"],
            },
            "magic": magic,
            "signals": detected,
            "total_signals": len(detected),
            "risk_config": risk_cfg,
        }
        
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        # 保存到日志
        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        with open(os.path.join(LOG_DIR, f"scan_{ts}.json"), "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[LOG] Saved to logs/signals/scan_{ts}.json", file=sys.stderr)
        
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
