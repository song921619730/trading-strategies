#!/usr/bin/env python3
"""
auto_inject_highrr.py — 将 High-RR 研究成果注入 intraday (234010) 策略配置

读取 research_state.json 的 best_findings，
将 pattern_type + _params 转为 entry_conditions 注入 strategies.json。

用法:
    python3 auto_inject_highrr.py              # 全自动执行
    python3 auto_inject_highrr.py --dry-run     # 只看不写
"""
import json
import os
import sys
import re
from datetime import datetime, timezone

# ── 路径 ──
HIGH_RR_STATE = "/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/high-rr-research/state/research_state.json"
STRATEGIES_CONFIG = "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/futures-intraday/config/strategies.json"
if sys.platform == "win32":
    HIGH_RR_STATE = HIGH_RR_STATE.replace("/mnt/f/", "F:/")
    STRATEGIES_CONFIG = STRATEGIES_CONFIG.replace("/mnt/f/", "F:/")

INJECT_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "logs", "auto_inject_highrr.log")

# ── 注入门槛（低胜率高盈亏比专用） ──
MIN_SHARPE = 30        # Sharpe >= 30
MIN_PROFIT_FACTOR = 1.8  # PF >= 1.8
MIN_N = 30             # 最小样本量
MAX_INJECT_PER_RUN = 15  # 单次最多注入数量

# 按 Sharpe 保留的上限
TOP_N = 20

# 需要排除的品种（如 DXY 不可交易或不想交易）
EXCLUDE_SYMBOLS = {}  # 空 = 全部注入


def _params_to_conditions(params: dict) -> dict:
    """将 high-rr _params 转为 entry_conditions 字典

    Params 示例:
    {
        "pattern_type": "trend_pullback",
        "timeframe_entry": "M15",
        "h1_trend": "down",
        "session": "us",
        "sl_multiple": 1.2,
        "tp_multiple": 5.0,
        "rsi14_max": 50,
        "rsi14_min": 70,
        "consecutive_bear": 2,
        "consecutive_bull": 3,
        "pullback_to_ma50": true,
        "direction": "short"
    }

    返回:
    {
        "session": "us",
        "sl_multiple": 1.2,
        "tp_multiple": 5.0,
        "conditions": [
            {"i": "rsi14", "op": "<", "v": 50},
            {"i": "rsi14", "op": ">", "v": 70},
            {"i": "consecutive_bear", "op": ">=", "v": 2},
            {"i": "consecutive_bull", "op": ">=", "v": 3},
            {"i": "_near_ma50", "op": "==", "v": 1},
            {"i": "_h1_close_vs_ma50", "op": "<", "v": 0},
        ]
    }
    """
    conditions = []
    entry_ec = {}

    # session — 放在外层，同时加条件（方便 scanner 做 session 快速过滤）
    session = params.get("session", "any")
    if session and session != "any":
        entry_ec["session"] = session
        conditions.append({"i": "session", "op": "==", "v": session})

    # RSI — 根据方向选择正确的入口条件
    # 研究引擎的 rsi14_max/min 是先后阶段条件（先超买再回落），不是同时条件
    # LONG: rsi14_max 是入场条件（RSI 超卖），SHORT: rsi14_min 是入场条件（RSI 超买）
    rsi_max = params.get("rsi14_max")
    rsi_min = params.get("rsi14_min")
    rsi_dir = params.get("direction", "long")
    if rsi_dir in ("long", "buy", "BUY") and rsi_max is not None:
        conditions.append({"i": "rsi14", "op": "<", "v": rsi_max})
    elif rsi_dir in ("short", "sell", "SELL") and rsi_min is not None:
        conditions.append({"i": "rsi14", "op": ">", "v": rsi_min})

    # Consecutive bars
    cb_bear = params.get("consecutive_bear", 0)
    cb_bull = params.get("consecutive_bull", 0)
    if cb_bear and cb_bear > 0:
        conditions.append({"i": "consecutive_bear", "op": ">=", "v": cb_bear})
    if cb_bull and cb_bull > 0:
        conditions.append({"i": "consecutive_bull", "op": ">=", "v": cb_bull})

    # Pullback to MA50 — 用 _near_ma50 特殊处理器
    if params.get("pullback_to_ma50"):
        conditions.append({"i": "_near_ma50", "op": "==", "v": 1})

    # H1 trend — 跨TF，用 _h1_ 前缀读取 H1 指标
    h1_trend = params.get("h1_trend", "")
    if h1_trend == "up":
        conditions.append({"i": "_h1_close_vs_ma50", "op": ">", "v": 0})
    elif h1_trend == "down":
        conditions.append({"i": "_h1_close_vs_ma50", "op": "<", "v": 0})

    # SL/TP multiple — 放 entry_conditions 顶层，scanner 会读取
    sl_mult = params.get("sl_multiple")
    tp_mult = params.get("tp_multiple")
    if sl_mult is not None:
        entry_ec["sl_multiple"] = sl_mult
    if tp_mult is not None:
        entry_ec["tp_multiple"] = tp_mult

    entry_ec["conditions"] = conditions
    return entry_ec


def _determine_group(symbol: str, session: str, pattern_type: str) -> str:
    """确定信号分组"""
    base = "highrr"
    type_map = {"trend_pullback": "pullback", "fakeout_reversal": "fakeout",
                "structure_breakout": "breakout"}
    ptype = type_map.get(pattern_type, pattern_type)

    if "XAU" in symbol or "XAG" in symbol:
        return f"hrr_metals_{ptype}"
    if symbol in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD"):
        return f"hrr_fx_{ptype}"
    if symbol in ("US30", "US500", "USTEC", "JP225", "HK50"):
        return f"hrr_indices_{ptype}"
    if "OIL" in symbol:
        return f"hrr_energy_{ptype}"
    if symbol == "DXY":
        return f"hrr_dxy_{ptype}"
    if "XNG" in symbol or "XCU" in symbol:
        return f"hrr_commodity_{ptype}"
    return f"hrr_other_{ptype}"


def evaluate_finding(finding: dict, existing_ids: set,
                     injected_sources: set) -> dict | None:
    """评估一个 High-RR best_finding 是否可注入"""
    f_id = finding.get("id", "")
    if f_id in injected_sources:
        return None

    # 从 ID 提取品种 (格式: hrr_NNN_SYMBOL_...)
    symbol = finding.get("symbol", "")
    if not symbol:
        id_match = re.search(r'hrr_\d+_([A-Z0-9]+)', f_id)
        if id_match:
            symbol = id_match.group(1)
    # fallback: 从 description 提取
    if not symbol:
        desc = finding.get("description", "")
        desc_match = re.match(r'([A-Z]+)\s', desc)
        if desc_match:
            symbol = desc_match.group(1)
    if not symbol:
        return None
    if symbol in EXCLUDE_SYMBOLS:
        return None

    direction = finding.get("direction", "long")
    tf = finding.get("timeframe", "M15")
    params = finding.get("_params", {})
    pattern_type = params.get("pattern_type", "unknown")

    # 门槛检查
    sharpe = finding.get("sharpe", 0) or 0
    pf = finding.get("profit_factor", 0) or 0
    n = finding.get("n", 0) or 0
    wr = finding.get("win_rate", 0) or 0
    avg_ret = finding.get("avg_return_pct", 0) or 0

    if sharpe < MIN_SHARPE:
        return None
    if pf < MIN_PROFIT_FACTOR:
        return None
    if n < MIN_N:
        return None

    # 生成 ID
    base_id = f"hrr_{pattern_type[:5]}_{symbol.lower()}_{tf.lower()}_{direction[:1]}"
    new_id = base_id
    counter = 1
    while new_id in existing_ids:
        counter += 1
        new_id = f"{base_id}_{counter}"

    session = params.get("session", "any")

    # 转换条件
    entry_conditions = _params_to_conditions(params)

    # 优先级：Sharpe 越高越优先
    if sharpe >= 70:
        priority = 5
    elif sharpe >= 50:
        priority = 10
    elif sharpe >= 30:
        priority = 15
    else:
        priority = 20

    signal = {
        "id": new_id,
        "group": _determine_group(symbol, session, pattern_type),
        "symbols": [symbol],
        "timeframe": tf,
        "direction": direction,
        "entry_conditions": entry_conditions,
        "best_hold": finding.get("best_hold", 48),
        "min_signals_for_entry": 1,
        "win_rate": round(wr, 1),
        "signal_count": n,
        "sharpe": round(sharpe, 2),
        "profit_factor": round(pf, 2),
        "avg_return_pct": round(avg_ret, 4),
        "max_dd_pct": round(finding.get("max_dd_pct", 0), 2),
        "priority": priority,
        "_auto_injected": True,
        "_injected_at": datetime.now(timezone.utc).isoformat(),
        "_source": f_id,
        "_pattern_type": pattern_type,
    }
    return signal


def main():
    dry_run = "--dry-run" in sys.argv

    if not os.path.exists(HIGH_RR_STATE):
        print(f"❌ High-RR 状态文件不存在: {HIGH_RR_STATE}")
        return 1
    if not os.path.exists(STRATEGIES_CONFIG):
        print(f"❌ 策略配置不存在: {STRATEGIES_CONFIG}")
        return 1

    with open(HIGH_RR_STATE) as f:
        research = json.load(f)
    with open(STRATEGIES_CONFIG) as f:
        cfg = json.load(f)

    existing_ids = {s["id"] for s in cfg.get("signals", [])}
    injected_sources = set(cfg.get("_injected_sources", []))

    candidates = []
    for bf in research.get("best_findings", []):
        sig = evaluate_finding(bf, existing_ids, injected_sources)
        if sig:
            candidates.append(sig)
            existing_ids.add(sig["id"])

    # 按 Sharpe 排序，取 Top N
    candidates.sort(key=lambda s: s.get("sharpe", 0), reverse=True)
    if len(candidates) > MAX_INJECT_PER_RUN:
        print(f"⚠️  {len(candidates)} 个符合条件，限制注入前 {MAX_INJECT_PER_RUN} 个")
        candidates = candidates[:MAX_INJECT_PER_RUN]

    if not candidates:
        print(f"📊 best_findings 共 {len(research.get('best_findings', []))} 个")
        print(f"❌ 没有符合条件的信号 "
              f"(门槛: Sharpe≥{MIN_SHARPE}, PF≥{MIN_PROFIT_FACTOR}, n≥{MIN_N})")
        # 打印前 10 个排名的详情
        for bf in research.get("best_findings", [])[:10]:
            sharpe = bf.get("sharpe", 0) or 0
            pf = bf.get("profit_factor", 0) or 0
            n = bf.get("n", 0) or 0
            reason = []
            if sharpe < MIN_SHARPE:
                reason.append(f"S={sharpe:.1f}<{MIN_SHARPE}")
            if pf < MIN_PROFIT_FACTOR:
                reason.append(f"PF={pf:.2f}<{MIN_PROFIT_FACTOR}")
            if n < MIN_N:
                reason.append(f"n={n}<{MIN_N}")
            desc = bf.get("description", "")[:50]
            print(f"   ✗ {bf.get('id','?'):30s} S={sharpe:6.1f} PF={pf:.2f} n={n:>4}  [{', '.join(reason)}]")
        return 0

    print(f"📦 发现 {len(candidates)} 个符合条件的 High-RR 信号:")
    for sig in candidates:
        ec = sig["entry_conditions"]
        conds_str = "; ".join(f"{c['i']}{c['op']}{c['v']}" for c in ec.get("conditions", []))
        print(f"  ➕ {sig['id']}")
        print(f"     {sig['symbols'][0]} {sig['timeframe']} {sig['direction']} "
              f"S={sig['sharpe']} PF={sig['profit_factor']} WR={sig['win_rate']}% n={sig['signal_count']}")
        print(f"     pattern={sig['_pattern_type']} sl_mult={ec.get('sl_multiple','2.0')} tp_mult={ec.get('tp_multiple','4.0')}")
        print(f"     conditions: {conds_str}")

    if dry_run:
        print("\n🏁 Dry-run 模式，未写入。")
        return 0

    # ── 写入 ──
    cfg["signals"].extend(candidates)
    cfg["_last_auto_inject_highrr"] = datetime.now(timezone.utc).isoformat()
    cfg["_auto_inject_highrr_count"] = cfg.get("_auto_inject_highrr_count", 0) + len(candidates)

    injected_sources = set(cfg.get("_injected_sources", []))
    for sig in candidates:
        src = sig.get("_source", "")
        if src:
            injected_sources.add(src)
    cfg["_injected_sources"] = sorted(injected_sources)

    with open(STRATEGIES_CONFIG, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已注入 {len(candidates)} 个 High-RR 信号到 {STRATEGIES_CONFIG}")
    print(f"   当前总策略数: {len(cfg['signals'])}")

    # 写日志
    try:
        os.makedirs(os.path.dirname(INJECT_LOG), exist_ok=True)
        with open(INJECT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] "
                    f"High-RR 注入 {len(candidates)} 个策略\n")
            for sig in candidates:
                f.write(f"  + {sig['id']}: {sig['symbols'][0]} {sig['timeframe']} "
                        f"{sig['direction']} S={sig['sharpe']} PF={sig['profit_factor']}\n")
            f.write(f"  总策略数: {len(cfg['signals'])}\n\n")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
