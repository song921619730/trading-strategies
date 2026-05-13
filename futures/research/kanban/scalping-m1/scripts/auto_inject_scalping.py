#!/usr/bin/env python3
"""auto_inject_scalping.py — 将 M1/M5 研究发现自动注入到 strategies.json

与 futures-intraday 的 auto_inject.py 相同逻辑，
但为 M1/M5 信号降低 avg_return 门槛（短线收益天然小）。

用法:
    python3 auto_inject_scalping.py
    python3 auto_inject_scalping.py --dry-run
"""
import json, os, re, sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_STATE = os.path.join(BASE, "state", "research_state.json")
STRATEGIES_CONFIG = "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/config/strategies.json"

# ── Scalping 注入门槛（比 M30/H1 宽松） ──
MIN_WIN_RATE = 0.57       # 胜率 >= 57%
MIN_SIGNAL_COUNT = 100    # 样本量 >= 100（短线信号多）
MIN_AVG_RETURN = 0.0001   # 平均收益 > 0.01%（短线收益低）


def load_existing_ids(cfg):
    return {s["id"] for s in cfg.get("signals", [])}


def evaluate_signal(bf, existing_ids, injected_sources):
    bf_id = bf.get("id", "")
    if bf_id in injected_sources:
        return None

    symbol = bf.get("symbol", "")
    if not symbol:
        return None

    metrics = bf.get("metrics", bf)
    direction = bf.get("direction", "long")
    timeframe = bf.get("timeframe", "M5")
    win_rate = metrics.get("win_rate", 0) or 0
    signal_count = metrics.get("signal_count", 0) or 0
    avg_return = metrics.get("avg_return", 0) or 0
    sharpe = metrics.get("sharpe_ratio", 0) or 0
    hold_period = bf.get("best_hold", bf.get("hold_period", 5))

    # 门槛
    if win_rate < MIN_WIN_RATE:
        return None
    if signal_count < MIN_SIGNAL_COUNT:
        return None
    if avg_return < MIN_AVG_RETURN:
        return None

    entry_condition = bf.get("entry_condition", "")
    if not entry_condition:
        return None

    # 解析参数
    params = {}
    session_match = re.search(r"session\s*==\s*'(\w+)'", entry_condition)
    if session_match:
        sess = session_match.group(1)
        params["session"] = sess
    rsi_max = re.search(r"rsi14\s*<\s*(\d+)", entry_condition)
    if rsi_max:
        params["rsi14_max"] = int(rsi_max.group(1))
    rsi_min = re.search(r"rsi14\s*>\s*(\d+)", entry_condition)
    if rsi_min:
        params["rsi14_min"] = int(rsi_min.group(1))
    atr_match = re.search(r"atr14_pct\s*>\s*([\d.]+)", entry_condition)
    if atr_match:
        params["atr_min_pct"] = float(atr_match.group(1)) / 100
    bear_match = re.search(r"consecutive_bear\s*>=\s*(\d+)", entry_condition)
    if bear_match:
        params["consecutive_bear"] = int(bear_match.group(1))

    session = params.get("session", "any")

    # ID 生成
    base_id = f"scalp_{session}_{symbol.lower()}_{timeframe.lower()}_{direction[:1]}"
    new_id = base_id
    counter = 1
    while new_id in existing_ids:
        counter += 1
        new_id = f"{base_id}_{counter}"
    if new_id in existing_ids:
        return None

    priority = 30
    if win_rate >= 0.65:
        priority = 20
    elif win_rate >= 0.60:
        priority = 25

    signal = {
        "id": new_id,
        "group": "scalping_m1m5",
        "symbols": [symbol],
        "timeframe": timeframe,
        "direction": direction,
        "entry_conditions": params,
        "best_hold": hold_period,
        "min_signals_for_entry": 1,
        "win_rate": round(win_rate * 100, 1),
        "signal_count": signal_count,
        "avg_return": round(avg_return * 100, 4),
        "priority": priority,
        "_auto_injected": True,
        "_injected_at": datetime.now().isoformat(),
        "_source": bf_id,
    }
    return signal


def main():
    dry_run = "--dry-run" in sys.argv

    if not os.path.exists(RESEARCH_STATE):
        print(f"❌ 研究状态不存在: {RESEARCH_STATE}")
        return 1

    with open(RESEARCH_STATE) as f:
        research = json.load(f)
    with open(STRATEGIES_CONFIG) as f:
        cfg = json.load(f)

    existing_ids = load_existing_ids(cfg)
    injected_sources = set(cfg.get("_injected_sources", []))

    candidates = []
    for bf in research.get("best_findings", []):
        sig = evaluate_signal(bf, existing_ids, injected_sources)
        if sig:
            candidates.append(sig)
            existing_ids.add(sig["id"])
            injected_sources.add(bf.get("id", ""))

    if not candidates:
        print(f"📊 best_findings: {len(research.get('best_findings',[]))} 个")
        print(f"❌ 无符合条件的信号 (WR≥{MIN_WIN_RATE*100:.0f}% n≥{MIN_SIGNAL_COUNT} avg≥{MIN_AVG_RETURN})")
        return 0

    print(f"📦 发现 {len(candidates)} 个信号:")
    for sig in candidates:
        print(f"  ➕ {sig['id']}: {sig['symbols'][0]} {sig['timeframe']} {sig['direction']} "
              f"WR={sig['win_rate']}% n={sig['signal_count']}")

    if dry_run:
        return 0

    cfg["signals"].extend(candidates)
    cfg["_last_auto_inject"] = datetime.now().isoformat()
    cfg["_auto_inject_count"] = cfg.get("_auto_inject_count", 0) + len(candidates)
    cfg["_injected_sources"] = sorted(set(cfg.get("_injected_sources", [])) |
                                      {s.get("_source", "") for s in candidates if s.get("_source")})

    with open(STRATEGIES_CONFIG, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已注入 {len(candidates)} 个新信号")
    print(f"   当前总策略: {len(cfg['signals'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
