#!/usr/bin/env python3
"""auto_inject_high_rr.py — 将 High-RR 研究发现注入到交易系统配置

注入门槛: Sharpe > 1.5 + Profit Factor > 2.0 + n > 80
输出: high_rr_strategies.json
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE, "state", "research_state.json")
# 交易系统配置路径（独立于 Scalping）
STRATEGIES_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/high-rr/config"
if sys.platform == "win32":
    STRATEGIES_DIR = STRATEGIES_DIR.replace("/mnt/f/", "F:/")
OUTPUT_PATH = os.path.join(STRATEGIES_DIR, "high_rr_strategies.json")

# ─── 注入门槛（比研究阶段更严） ───
MIN_SHARPE = 1.5
MIN_PROFIT_FACTOR = 2.0
MIN_TRADES = 80
MAX_STRATEGIES = 30  # 最多保留 30 个

# 14 个 MT5 品种
SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']

# Session 映射
SESSION_ALIAS = {"asia": "asia", "europe": "europe", "us": "us"}


def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        print("⏭ No state file")
        return {"best_findings": []}
    with open(STATE_PATH) as f:
        return json.load(f)


def load_existing_config() -> dict:
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            return json.load(f)
    return {
        "magic_number": 234012,
        "group": "high_rr",
        "risk": {
            "max_total_positions": 4,
            "max_position_per_group": 1,
            "max_same_direction_pct": 0.6,
            "max_single_variety_pct": 0.3,
            "min_rr": 2.0,
            "max_spread_pct": 0.003,
            "risk_per_trade_pct": 0.05,
            "pos_validation": {
                "symposium_groups": {
                    "metals": ["XAUUSD", "XAGUSD"],
                    "indices": ["JP225", "US30", "US500", "USTEC", "HK50"],
                    "oil": ["USOIL", "UKOIL"],
                    "fx_majors": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
                }
            }
        },
        "signals": [],
    }


def finding_to_strategy(finding: dict, existing_ids: set) -> dict:
    desc = finding.get("description", "")
    params = finding.get("_params", {})

    # 解析 symbol
    symbol = ""
    for s in SYMBOLS:
        if desc.startswith(s):
            symbol = s
            break
    if not symbol:
        return None

    # 方向
    direction = finding.get("direction", params.get("direction", "long"))

    # ID 生成
    base_id = f"hrr_{symbol.lower()}_{params.get('pattern_type','?')[:4]}_{direction[:1]}"
    new_id = base_id
    counter = 1
    while new_id in existing_ids:
        counter += 1
        new_id = f"{base_id}_{counter}"
    if new_id in existing_ids:
        return None

    # 生成 entry_conditions
    cond = {}
    if params.get("h1_trend") and params["h1_trend"] != "any":
        cond["h1_trend"] = params["h1_trend"]
    if params.get("session") and params["session"] != "any":
        cond["session"] = params["session"]
    if params.get("rsi14_max"):
        cond["rsi14_max"] = params["rsi14_max"]
    if params.get("rsi14_min"):
        cond["rsi14_min"] = params["rsi14_min"]
    if params.get("consecutive_bear", 0) >= 2:
        cond["consecutive_bear"] = params["consecutive_bear"]
    if params.get("consecutive_bull", 0) >= 2:
        cond["consecutive_bull"] = params["consecutive_bull"]
    if params.get("pullback_to_ma50"):
        cond["pullback_to_ma50"] = True

    tf = finding.get("timeframe", params.get("timeframe_entry", "M5"))

    return {
        "id": new_id,
        "group": "high_rr",
        "symbols": [symbol],
        "timeframe": tf,
        "direction": direction,
        "entry_conditions": cond,
        "sl_multiple": params.get("sl_multiple", 1.0),
        "tp_multiple": params.get("tp_multiple", 5.0),
        "max_hold_bars": params.get("max_hold_bars", 48),
        "min_signals_for_entry": 1,
        "sharpe": finding.get("sharpe", 0),
        "profit_factor": finding.get("profit_factor", 0),
        "win_rate": finding.get("win_rate", 0),
        "signal_count": finding.get("n", 0),
        "avg_return_pct": finding.get("avg_return_pct", 0),
        "priority": 10 if finding.get("sharpe", 0) >= 3.0 else (20 if finding.get("sharpe", 0) >= 2.0 else 30),
        "_auto_injected": True,
        "_injected_at": datetime.now().isoformat(),
        "_source": finding.get("source", ""),
    }


def main():
    state = load_state()
    findings = state.get("best_findings", [])
    if not findings:
        print("⏭ No findings in state")
        return

    print(f"📊 Total findings: {len(findings)}")

    # 过滤
    qualified = [f for f in findings
                 if f.get("sharpe", 0) >= MIN_SHARPE
                 and f.get("profit_factor", 0) >= MIN_PROFIT_FACTOR
                 and f.get("n", 0) >= MIN_TRADES]

    if not qualified:
        print(f"⏭ No findings pass thresholds "
              f"(Sharpe>={MIN_SHARPE} PF>={MIN_PROFIT_FACTOR} n>={MIN_TRADES})")
        return

    print(f"✅ Qualified: {len(qualified)}")

    # 读取已有配置
    cfg = load_existing_config()
    existing_ids = {s["id"] for s in cfg["signals"]}
    new_strategies = []

    for f in qualified:
        # 按 Sharpe 降序，只取前 N 个不重复的
        strat = finding_to_strategy(f, existing_ids)
        if strat:
            new_strategies.append(strat)
            existing_ids.add(strat["id"])

    if not new_strategies:
        print("⏭ No new strategies to inject (all existing)")
        return

    # 排序 + Top MAX_STRATEGIES
    new_strategies.sort(key=lambda s: s.get("sharpe", 0), reverse=True)
    total = new_strategies[:MAX_STRATEGIES]

    # 合并：保留已有 + 新注入，按 sharpe 排序截断 MAX_STRATEGIES
    old_non_injected = [s for s in cfg["signals"] if not s.get("_auto_injected")]
    cfg["signals"] = old_non_injected + total
    cfg["signals"].sort(key=lambda s: s.get("priority", 99))

    # 确保目录存在
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    print(f"✅ 已注入 {len(total)} 个策略到 {OUTPUT_PATH}")
    for s in total:
        print(f"   {s['symbols'][0]:<8} {s['direction']:<6} "
              f"SL={s['sl_multiple']}x TP={s['tp_multiple']}x "
              f"S={s['sharpe']:.2f} PF={s['profit_factor']:.2f}")


if __name__ == "__main__":
    main()
