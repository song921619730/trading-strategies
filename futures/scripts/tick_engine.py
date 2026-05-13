#!/usr/bin/env python3
"""
tick_engine.py — 统一 Tick Engine 守护进程

核心功能:
  1. 唯一连接 MT5，避免多个 Scanner 重复连接
  2. 每 1.5s 读取所有品种 tick（bid/ask/spread）
  3. 检测新 bar 形成 → 拉取 bars → 重新计算指标
  4. 写入共享 JSON 文件（Scanner 读取，不再连 MT5）

安全设计:
  - Windows Python 运行（需要 MT5 库）
  - 共享文件每次原子写入（先写 tmp 再 rename，避免读半截）
  - heartbeat 机制：Scanner 检测到 engine 超时就自动 fallback

用法:
  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe ^
    F:/AIcoding_space/Hermes/strategies/futures/scripts/tick_engine.py

停止: Ctrl+C 或杀掉进程
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ─── 路径 ───
BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "config" / "tick_engine.json"
SHARED_DIR = BASE / "data" / "tick"
SHARED_DIR.mkdir(parents=True, exist_ok=True)

# ─── 加载配置 ───
with open(CONFIG_PATH) as f:
    CFG = json.load(f)

SYMBOLS = CFG["symbols"]
TIMEFRAMES = CFG["timeframes"]
LOOP_INTERVAL = CFG["loop_interval_sec"]
INDICATOR_BARS = CFG["indicator_bars"]
HEARTBEAT_MAX_AGE = CFG["heartbeat_max_age_sec"]

# ─── Session 映射 ───
SESSION_MAP = {
    "asia":   (0, 8),
    "europe": (8, 13),
    "us":     (13, 22),
}


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[TickEngine] {ts} | {msg}", flush=True)


def atomic_write(path: Path, data: dict):
    """先写 tmp 再 rename，避免 Scanner 读到半截文件"""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    # Windows rename 要求先删目标
    if path.exists():
        os.remove(path)
    os.rename(tmp, path)


# ─── 技术指标（和 Scanner 保持一致） ───
def calc_rsi(closes: list, period: int = 14):
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
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def calc_atr(bars: list, period: int = 14):
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[-i]["high"]
        l = bars[-i]["low"]
        pc = bars[-i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[:period]) / period


def detected_consecutive_bears(bars: list) -> int:
    count = 0
    for bar in reversed(bars):
        if bar["close"] < bar["open"]:
            count += 1
        else:
            break
    return count


def detected_consecutive_bulls(bars: list) -> int:
    count = 0
    for bar in reversed(bars):
        if bar["close"] > bar["open"]:
            count += 1
        else:
            break
    return count


def get_session(utc_hour: int) -> str:
    for name, (start, end) in SESSION_MAP.items():
        if start <= utc_hour < end:
            return name
    return "asia"


def calc_ema(closes: list, period: int) -> float:
    """简单 EMA，用于 scalping 判断趋势"""
    if len(closes) < period:
        return closes[-1] if closes else 0
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def calc_ma(closes: list, period: int) -> float:
    if len(closes) < period:
        return sum(closes) / len(closes) if closes else 0
    return sum(closes[-period:]) / period


# ─── 内部状态 ───
class TickEngineState:
    def __init__(self):
        self.mt5 = None
        self.ticks: dict = {}           # {symbol: tick}
        self.bar_cache: dict = {}        # {symbol_TF: bars_list}
        self.last_bar_time: dict = {}    # {symbol_TF: last_timestamp}
        self.indicators: dict = {}       # {symbol_TF: {indicator_name: value}}
        self.bar_signals: dict = {}      # {symbol_TF: bar_info}
        self.cycle_count = 0
        self.errors = 0
        self.start_time = datetime.now(timezone.utc)


def init_mt5(state: TickEngineState):
    import MetaTrader5 as mt5
    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")

    if not mt5.initialize(path=path, login=login, password=password, server=server):
        log(f"❌ MT5 init failed: {mt5.last_error()}")
        return False

    term = mt5.terminal_info()
    acct = mt5.account_info()
    if not term or not acct:
        log("❌ Cannot get terminal/account info")
        mt5.shutdown()
        return False

    # 验证各品种可选
    for sym in SYMBOLS:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        if info:
            log(f"  ✅ {sym}: spread={info.spread}, digits={info.digits}")
        else:
            log(f"  ⚠️ {sym}: symbol_info failed")

    state.mt5 = mt5
    log(f"✅ MT5 connected: {term.name}, login={acct.login}, balance={acct.balance:.2f}")
    return True


def get_mt5_tf(mt5, tf_name: str):
    name = f"TIMEFRAME_{tf_name}"
    return getattr(mt5, name, None)


def bars_to_list(bars) -> list:
    """MT5 bars (numpy void) → list of dict"""
    result = []
    for b in bars:
        result.append({
            "time": int(b["time"]) if isinstance(b, (dict,)) else int(b.time),
            "open": float(b["open"]) if isinstance(b, (dict,)) else float(b.open),
            "high": float(b["high"]) if isinstance(b, (dict,)) else float(b.high),
            "low": float(b["low"]) if isinstance(b, (dict,)) else float(b.low),
            "close": float(b["close"]) if isinstance(b, (dict,)) else float(b.close),
            "volume": int(b["tick_volume"]) if isinstance(b, (dict,)) else int(b.tick_volume),
        })
    return result


def update_indicators(state: TickEngineState, symbol: str, tf: str):
    """对指定品种+TF 重新计算所有指标"""
    key = f"{symbol}_{tf}"
    bars = state.bar_cache.get(key)
    if not bars or len(bars) < 20:
        return

    closes = [b["close"] for b in bars]
    latest = bars[-1]
    utc_hour = datetime.fromtimestamp(latest["time"], tz=timezone.utc).hour

    ind = {
        "rsi14": calc_rsi(closes),
        "atr14": calc_atr(bars),
        "consecutive_bear": detected_consecutive_bears(bars),
        "consecutive_bull": detected_consecutive_bulls(bars),
        "session": get_session(utc_hour),
        "ema12": calc_ema(closes, 12),
        "ema26": calc_ema(closes, 26),
        "ma20": calc_ma(closes, 20),
        "ma50": calc_ma(closes, 50),
        "utc_hour": utc_hour,
        "bar_time": latest["time"],
        "bar_open": latest["open"],
        "bar_high": latest["high"],
        "bar_low": latest["low"],
        "bar_close": latest["close"],
        "bar_volume": latest["volume"],
    }

    # ATR as % of close
    if ind["atr14"] and latest["close"] > 0:
        ind["atr14_pct"] = ind["atr14"] / latest["close"] * 100
    else:
        ind["atr14_pct"] = None

    state.indicators[key] = ind


def update_bars_and_indicators(state: TickEngineState, symbol: str, tf: str):
    """拉取 bars 并更新指标"""
    mt5 = state.mt5
    mt5_tf = get_mt5_tf(mt5, tf)
    if mt5_tf is None:
        return

    bars = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, INDICATOR_BARS)
    if bars is None or len(bars) < 20:
        return

    bars_list = bars_to_list(bars)
    key = f"{symbol}_{tf}"
    state.bar_cache[key] = bars_list
    state.last_bar_time[key] = bars_list[-1]["time"]

    update_indicators(state, symbol, tf)


def check_new_bars(state: TickEngineState):
    """检测是否有新 bar 形成，有则更新 bars+indicators"""
    mt5 = state.mt5
    new_signals = {}

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            key = f"{symbol}_{tf}"
            mt5_tf = get_mt5_tf(mt5, tf)
            if mt5_tf is None:
                continue

            # 只读最新一根 bar 的时间，检查是否变化
            bar = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 1)
            if bar is None or len(bar) == 0:
                continue

            bar_time = int(bar[0]["time"]) if isinstance(bar[0], (dict,)) else int(bar[0].time)

            last_time = state.last_bar_time.get(key)
            if last_time is None or bar_time > last_time:
                # 新 bar 形成
                update_bars_and_indicators(state, symbol, tf)
                new_signals[key] = {
                    "time": bar_time,
                    "symbol": symbol,
                    "timeframe": tf,
                    "detected_at": time.time(),
                }
                log(f"📊 New {tf} bar: {symbol} @ {bar_time}")

    if new_signals:
        state.bar_signals.update(new_signals)


def update_ticks(state: TickEngineState):
    """读取所有品种的当前 tick"""
    mt5 = state.mt5
    ticks = {}

    for symbol in SYMBOLS:
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                tick_data = {
                    "bid": float(tick.bid),
                    "ask": float(tick.ask),
                    "spread": int(tick.spread),
                    "time": int(tick.time),
                    "last": float(tick.last) if hasattr(tick, 'last') else None,
                    "volume": int(tick.volume) if hasattr(tick, 'volume') else 0,
                }
                ticks[symbol] = tick_data
        except Exception:
            pass

    state.ticks = ticks
    return ticks


def write_shared_state(state: TickEngineState):
    """写入所有共享 JSON 文件（原子写入）"""
    now = datetime.now(timezone.utc)
    ts = now.isoformat()

    # 1. 当前 Tick
    tick_data = {
        "ticks": state.ticks,
        "_updated_at": ts,
        "_cycle": state.cycle_count,
    }
    atomic_write(SHARED_DIR / "ticks.json", tick_data)

    # 2. Bar 信号（新 bar 通知）
    if state.bar_signals:
        bar_signal_data = {
            "signals": state.bar_signals,
            "_updated_at": ts,
        }
        atomic_write(SHARED_DIR / "bar_signals.json", bar_signal_data)

    # 3. 各时间框架的指标
    for tf in TIMEFRAMES:
        tf_indicators = {}
        for symbol in SYMBOLS:
            key = f"{symbol}_{tf}"
            if key in state.indicators:
                tf_indicators[symbol] = state.indicators[key]
        if tf_indicators:
            data = {
                "indicators": tf_indicators,
                "_updated_at": ts,
                "_cycle": state.cycle_count,
            }
            atomic_write(SHARED_DIR / f"indicators_{tf}.json", data)

    # 4. Heartbeat
    heartbeat = {
        "status": "running",
        "started_at": state.start_time.isoformat(),
        "updated_at": ts,
        "cycle": state.cycle_count,
        "errors": state.errors,
        "symbols_connected": len(state.ticks),
        "symbols": list(state.ticks.keys()),
        "timeframes": TIMEFRAMES,
    }
    atomic_write(SHARED_DIR / "_heartbeat.json", heartbeat)


def print_status(state: TickEngineState):
    """每 10 周期打印一次状态摘要"""
    if state.cycle_count % 10 != 0:
        return
    uptime = (datetime.now(timezone.utc) - state.start_time).total_seconds()
    log(f"[{state.cycle_count}] ticks={len(state.ticks)}/{len(SYMBOLS)} "
        f"indicators={len(state.indicators)} errors={state.errors} "
        f"uptime={uptime:.0f}s")


def main_loop(state: TickEngineState):
    """主循环：每 LOOP_INTERVAL 秒执行一次"""
    log(f"🚀 Tick Engine started (interval={LOOP_INTERVAL}s, symbols={len(SYMBOLS)}, tf={TIMEFRAMES})")
    log(f"   Shared dir: {SHARED_DIR}")

    # 首次：全量拉取所有 TF 的 bars + indicators
    log("📥 Initial data load...")
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            update_bars_and_indicators(state, symbol, tf)
    log(f"✅ Initial load done: {len(state.indicators)} indicator sets")

    # 写初始状态
    update_ticks(state)
    write_shared_state(state)
    print_status(state)

    # 主循环
    while True:
        try:
            state.cycle_count += 1

            # Step 1: Tick 更新（每次循环都做）
            update_ticks(state)

            # Step 2: Bar 检测（检查是否有新 bar 形成）
            check_new_bars(state)

            # Step 3: 写入共享状态
            write_shared_state(state)

            # 状态打印
            print_status(state)

            time.sleep(LOOP_INTERVAL)

        except KeyboardInterrupt:
            log("🛑 Shutdown requested")
            break
        except Exception:
            state.errors += 1
            log(f"❌ Error in main loop: {traceback.format_exc()}")
            time.sleep(LOOP_INTERVAL * 2)

    # 清理
    if state.mt5:
        state.mt5.shutdown()
        log("👋 MT5 disconnected")
    # 写最终状态
    atomic_write(SHARED_DIR / "_heartbeat.json", {
        "status": "stopped",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cycle": state.cycle_count,
        "errors": state.errors,
    })
    log("👋 Tick Engine stopped")


def main():
    log("=" * 60)
    log("Tick Engine 统一数据层 v1")
    log("=" * 60)

    state = TickEngineState()

    if not init_mt5(state):
        log("❌ Failed to initialize MT5. Exiting.")
        sys.exit(1)

    try:
        main_loop(state)
    finally:
        if state.mt5:
            state.mt5.shutdown()


if __name__ == "__main__":
    main()
