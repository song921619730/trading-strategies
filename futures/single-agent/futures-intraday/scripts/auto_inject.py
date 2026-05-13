#!/usr/bin/env python3
"""
auto_inject.py — 将研究发现的高质量信号自动注入到交易系统

核心逻辑：根据胜率、收益率、样本量判断是否注入，
参数（session/rsi/atr）只要能解析出来即可。

用法:
    python3 auto_inject.py              # 全自动执行
    python3 auto_inject.py --dry-run     # 只看不写
"""

import json
import os
import re
import sys
from datetime import datetime

RESEARCH_STATE = "/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/state/research_state.json"
STRATEGIES_CONFIG = "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/config/strategies.json"

# ── 注入门槛 ──
# 核心指标门槛
MIN_WIN_RATE = 0.68       # 胜率 > 68%（高胜率策略，可接受小样本）
MIN_SIGNAL_COUNT = 60     # 样本量 >= 60（用户指定最低门槛）
MIN_AVG_RETURN = 0.0002   # 平均收益 > 0.02%（正期望值）

# 已有策略ID集合（去重用）
EXISTING_IDS = set()


def load_existing_ids(cfg: dict) -> set:
    return {s["id"] for s in cfg.get("signals", [])}


def _parse_condition(cond: str, symbol: str, bf: dict) -> dict | None:
    """从 entry_condition 字符串中提取扫描器需要的参数。

    示例:
        "session == 'asia' and rsi14 < 40 and atr14/close > 0.0025"
        → {"session": "asia", "rsi14_max": 40, "atr_min_pct": 0.0025}

    如果解析不出 session/rsi/atr 中的任一实用字段，仍然返回
    部分结果——扫描器可以处理部分条件的策略。
    """
    params = {}

    # 1. Session
    session_match = re.search(r"session\s*==\s*'(\w+)'", cond)
    if session_match:
        sess = session_match.group(1)
        if sess != "us":  # 美盘已有，跳过
            params["session"] = sess
    else:
        sess = "any"

    # 2. RSI 上限
    rsi_match = re.search(r"rsi14\s*<\s*(\d+)", cond)
    if rsi_match:
        params["rsi14_max"] = int(rsi_match.group(1))

    # 3. RSI 下限（超卖做多的边界）
    rsi_gt_match = re.search(r"rsi14\s*>\s*(\d+)", cond)
    if rsi_gt_match:
        params["rsi14_min"] = int(rsi_gt_match.group(1))

    # 4. ATR 最小百分比
    atr_match = re.search(r"atr14\s*/\s*close\s*>\s*([\d.]+)", cond)
    if atr_match:
        params["atr_min_pct"] = float(atr_match.group(1))
    else:
        # 默认 ATR 阈值
        params["atr_min_pct"] = 0.0020

    # 5. Consecutive bears（连续阴线）
    bear_match = re.search(r"consecutive_bear_count\s*>=\s*(\d+)", cond)
    if bear_match:
        params["consecutive_bears_min"] = int(bear_match.group(1))

    # 6. DXY filter
    if "dxy" in cond.lower():
        params["dxy_filter"] = "down"

    return params


def _determine_group(symbol: str, session: str) -> str:
    if "XAU" in symbol or "XAG" in symbol:
        return f"metals_{session}" if session != "any" else "metals_any"
    if symbol in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]:
        return f"fx_{session}" if session != "any" else "fx_any"
    if symbol in ["US30", "US500", "USTEC", "JP225", "HK50"]:
        return f"indices_{session}" if session != "any" else "indices_any"
    if "OIL" in symbol:
        return f"energy_{session}" if session != "any" else "energy_any"
    return f"{session}_session" if session != "any" else "any_session"


def evaluate_signal(bf: dict, existing_ids: set) -> dict | None:
    """评估一个 Best Finding 是否值得注入交易系统。

    返回信号 dict（可注入）或 None（不符合条件）。
    """
    bf_id = bf.get("id", "")
    if bf_id in existing_ids:
        return None

    # ── 核心指标（可能在 metrics 嵌套层） ──
    metrics = bf.get("metrics", bf)
    symbol_list = bf.get("symbols", [])
    symbol = bf.get("symbol", symbol_list[0] if symbol_list else "")

    if not symbol:
        return None

    direction = bf.get("direction", "long")
    timeframe = bf.get("timeframe", "H1")
    win_rate = metrics.get("win_rate", 0) or 0
    signal_count = metrics.get("signal_count", 0) or 0
    avg_return = metrics.get("avg_return", 0) or 0
    sharpe = metrics.get("sharpe_ratio", 0) or 0
    hold_period = bf.get("best_hold", bf.get("hold_period", 5))

    # ── 门槛检查 ──
    if win_rate < MIN_WIN_RATE:
        return None
    if signal_count < MIN_SIGNAL_COUNT:
        return None
    if avg_return < MIN_AVG_RETURN:
        return None

    # ── 解析 entry_condition ──
    entry_condition = bf.get("entry_condition", "")
    if not entry_condition:
        return None

    params = _parse_condition(entry_condition, symbol, bf)

    # 跳过纯美盘信号（已有）
    if params.get("session") == "us":
        return None

    session = params.get("session", "any")

    # ── 构建 ID ──
    base_id = f"auto_{session}_{symbol.lower()}_{timeframe.lower()}_{direction[:1]}"
    new_id = base_id
    counter = 1
    while new_id in existing_ids:
        new_id = f"{base_id}_{counter}"
        counter += 1

    # 高胜率/高收益 → 高优先级（数字越小越优先）
    # 美盘信号 priority=1~8，自动注入的从 20 开始
    priority = 20
    if win_rate >= 0.65:
        priority = 10
    elif win_rate >= 0.60:
        priority = 15
    elif win_rate >= 0.55:
        priority = 20

    signal = {
        "id": new_id,
        "group": _determine_group(symbol, session),
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
        print(f"❌ 研究状态文件不存在: {RESEARCH_STATE}")
        return 1
    if not os.path.exists(STRATEGIES_CONFIG):
        print(f"❌ 策略配置不存在: {STRATEGIES_CONFIG}")
        return 1

    with open(RESEARCH_STATE) as f:
        research = json.load(f)
    with open(STRATEGIES_CONFIG) as f:
        cfg = json.load(f)

    existing_ids = load_existing_ids(cfg)

    # 已注入的 research finding 源ID（防止重复注入）
    injected_sources = set(cfg.get("_injected_sources", []))

    # 遍历所有 best_findings
    candidates = []
    for bf in research.get("best_findings", []):
        bf_id = bf.get("id", "")
        if bf_id in injected_sources:
            continue  # 这个发现已经注入过了
        sig = evaluate_signal(bf, existing_ids)
        if sig:
            candidates.append(sig)
            existing_ids.add(sig["id"])

    if not candidates:
        # 输出现状说明
        bf_list = research.get("best_findings", [])
        print(f"📊 best_findings 共 {len(bf_list)} 个")
        print(f"❌ 没有符合条件的信号 (门槛: WR≥{MIN_WIN_RATE*100:.0f}%, n≥{MIN_SIGNAL_COUNT}, avg_ret≥{MIN_AVG_RETURN})")
        for bf in bf_list:
            wr = bf.get("win_rate", 0) or 0
            n = bf.get("signal_count", 0) or 0
            avg = bf.get("avg_return", 0) or 0
            reason = []
            if wr < MIN_WIN_RATE:
                reason.append(f"WR={wr*100:.1f}%<{MIN_WIN_RATE*100:.0f}%")
            if n < MIN_SIGNAL_COUNT:
                reason.append(f"n={n}<{MIN_SIGNAL_COUNT}")
            if avg < MIN_AVG_RETURN:
                reason.append(f"avg={avg:.4f}<{MIN_AVG_RETURN}")
            ec = bf.get("entry_condition", "")[:40]
            print(f"   - {bf.get('id','?'):12s} WR={wr*100:5.1f}% n={n:>5} avg={avg:>+7.4f}  [{', '.join(reason)}]  {ec}")
        return 0

    print(f"📦 发现 {len(candidates)} 个符合条件的信号:")
    for sig in candidates:
        ec = sig["entry_conditions"]
        print(f"  ➕ {sig['id']}")
        print(f"     {sig['symbols'][0]} {sig['timeframe']} {sig['direction']} "
              f"WR={sig['win_rate']}% n={sig['signal_count']} "
              f"avg_ret={sig['avg_return']}% prio={sig['priority']}")
        print(f"     conditions: {ec}")

    if dry_run:
        print("\n🏁 Dry-run 模式，未写入。")
        return 0

    cfg["signals"].extend(candidates)
    cfg["_last_auto_inject"] = datetime.now().isoformat()
    cfg["_auto_inject_count"] = cfg.get("_auto_inject_count", 0) + len(candidates)
    # 记录已注入的源ID
    injected_sources = set(cfg.get("_injected_sources", []))
    for sig in candidates:
        src = sig.get("_source", "")
        if src:
            injected_sources.add(src)
    cfg["_injected_sources"] = sorted(injected_sources)

    with open(STRATEGIES_CONFIG, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已注入 {len(candidates)} 个新信号到 {STRATEGIES_CONFIG}")
    print(f"   当前总策略数: {len(cfg['signals'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
