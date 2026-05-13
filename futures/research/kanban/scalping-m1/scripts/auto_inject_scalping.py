#!/usr/bin/env python3
"""auto_inject_scalping.py — 将 M1/M5 研究发现自动注入到 scalping_strategies.json

⚠️ Scalping 研究状态格式与 H1 不同：
   - win_rate 存储为百分比（72.8 = 72.8%）
   - n 存储信号数
   - avg_return_pct 存储为百分比（0.952 = 0.952%）
   - 没有 symbol 字段 → 从 description 解析
   - 没有 entry_condition 字段 → 从 description 解析
   - 没有 metrics 子对象

用法:
    python3 auto_inject_scalping.py
    python3 auto_inject_scalping.py --dry-run
"""
import json, os, re, sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_STATE = os.path.join(BASE, "state", "research_state.json")
_RAW_CONFIG = "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/config/scalping_strategies.json"
if sys.platform == "win32":
    _RAW_CONFIG = _RAW_CONFIG.replace("/mnt/f/", "F:/")
STRATEGIES_CONFIG = _RAW_CONFIG

# ── 注入门槛 ──
MIN_WIN_RATE_PCT = 68.0    # 胜率 > 68%（存储为百分比）
MIN_SIGNAL_COUNT = 60      # 样本量 >= 60
MIN_AVG_RETURN_PCT = 0.01  # 平均收益 > 0.01%（存储为百分比）

# 14 个 MT5 品种
SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']


def parse_entry_params(cond_str: str) -> dict:
    """从条件字符串解析 entry_conditions 参数"""
    params = {}
    sm = re.search(r"session\s*={1,2}\s*'(\w+)'", cond_str)
    if sm: params["session"] = sm.group(1)
    rm = re.search(r'rsi14\s*<\s*(\d+)', cond_str)
    if rm: params["rsi14_max"] = int(rm.group(1))
    rm2 = re.search(r'rsi14\s*>\s*(\d+)', cond_str)
    if rm2: params["rsi14_min"] = int(rm2.group(1))
    am = re.search(r'atr14_pct\s*>\s*([\d.]+)', cond_str)
    if am: params["atr_min_pct"] = float(am.group(1)) / 100
    bm = re.search(r'consecutive_bear\s*>=\s*(\d+)', cond_str)
    if bm: params["consecutive_bear"] = int(bm.group(1))
    hm = re.findall(r'hour\s*(>=|<=|>|<|==)\s*(\d+)', cond_str)
    for op, val in hm:
        params[f'hour_{op}'] = int(val)
    # hour range: hour >= 8 and hour < 13
    hrange = re.search(r'hour\s*>=\s*(\d+)\s+and\s+hour\s*<\s*(\d+)', cond_str)
    if hrange:
        params["hour_start"] = int(hrange.group(1))
        params["hour_end"] = int(hrange.group(2))
    return params


def evaluate_signal(bf, existing_ids, injected_sources):
    bf_id = bf.get("id", "")
    if bf_id in injected_sources:
        return None

    desc = bf.get("description", "")
    # 解析 symbol
    symbol = ""
    for s in SYMBOLS:
        if desc.startswith(s):
            symbol = s
            break
    if not symbol:
        return None

    # 指标
    win_rate = float(bf.get("win_rate", 0) or 0)      # 百分比格式
    signal_count = int(bf.get("n", 0) or 0)            # n 字段
    avg_return = float(bf.get("avg_return_pct", 0) or 0)  # 百分比格式
    sharpe = float(bf.get("sharpe", 0) or 0)           # sharp 字段名
    hold_period = int(bf.get("best_hold", 5) or 5)
    timeframe = bf.get("timeframe", "M5")
    direction = bf.get("direction", "long")

    # 门槛（百分比 vs 百分比比较）
    if win_rate < MIN_WIN_RATE_PCT:
        return None
    if signal_count < MIN_SIGNAL_COUNT:
        return None
    if avg_return < MIN_AVG_RETURN_PCT:
        return None

    # 解析 entry_condition
    cond = desc.split("—")[-1].strip() if "—" in desc else ""
    if not cond:
        return None

    params = parse_entry_params(cond)
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

    # 优先级
    priority = 30
    if win_rate >= 75:
        priority = 10
    elif win_rate >= 70:
        priority = 20

    signal = {
        "id": new_id,
        "group": "scalping_m1m5",
        "symbols": [symbol],
        "timeframe": timeframe,
        "direction": direction,
        "entry_conditions": params,
        "best_hold": hold_period,
        "min_signals_for_entry": 1,
        "win_rate": round(win_rate, 1),
        "signal_count": signal_count,
        "avg_return": round(avg_return, 4),
        "sharpe": round(sharpe, 2),
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

    existing_ids = {s["id"] for s in cfg.get("signals", [])}
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
        print(f"❌ 无符合条件的信号 (WR≥{MIN_WIN_RATE_PCT:.0f}% n≥{MIN_SIGNAL_COUNT} avg≥{MIN_AVG_RETURN_PCT}%)")
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
