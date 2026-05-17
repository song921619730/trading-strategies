#!/usr/bin/env python3
"""inject_discoveries.py — 将 discovery_engine 的发现注入到 scalping_strategies.json

从 discovery_result.json 读取 top_findings，过滤后转换为通用 conditions 数组格式。
"""
import json, os, sys, re
from datetime import datetime

# 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# discovery results
STATE_DIR = os.path.join(SCRIPT_DIR, "..", "state")
# scalping 配置
SCALPING_CFG = "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/config/scalping_strategies.json"

# 共享脚本
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))), "scripts"))
# Also add the futures scripts dir
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(SCALPING_CFG)), "..", "scripts"))

from condition_utils import parse_condition_text

# ── 注入门槛 ──
MIN_WR = 68.0     # 胜率 ≥ 68%
MIN_N = 30        # 样本量 ≥ 30
MIN_AVG_RET = 0.01  # 平均收益 ≥ 0.01%

# 共享品种表
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "scripts"))
from mt5_symbols import MT5_SYMBOLS_19
SYMBOLS = MT5_SYMBOLS_19

def extract_symbol(desc: str) -> str:
    """从描述中提取品种"""
    for s in SYMBOLS:
        if desc.startswith(s):
            return s
    # 从 condition 文本中提取
    for s in SYMBOLS:
        if s in desc:
            return s
    return ""

def extract_timeframe(desc: str) -> str:
    m = re.search(r'\b(M[15]|M15|M30|H[14])\b', desc)
    return m.group(1) if m else "M5"

def extract_direction(desc: str) -> str:
    return "short" if "做空" in desc else "long"

def parse_condition_from_desc(desc: str) -> str:
    """从描述文本 'XAUUSD M5 做多: rsi9 < 5 and session == 'europe' WR=86.2%...'
    提取条件部分 'rsi9 < 5 and session == 'europe''
    """
    # 去掉前缀 "SYMBOL TF DIR: "
    no_prefix = re.sub(r'^[\w]+\s+M\d+\s+做[多空]+:\s*', '', desc)
    # 去掉后缀 " WR=... n=... hold=... avg_ret=... Sharpe=..."
    cond = re.sub(r'\s+WR=[\d.]+%.*', '', no_prefix)
    return cond.strip()

def main():
    dry_run = "--dry-run" in sys.argv

    # 读取 discovery 结果
    result_path = os.path.join(STATE_DIR, "discovery_result.json")
    if not os.path.exists(result_path):
        print(f"❌ 未找到: {result_path}")
        return 1
    with open(result_path) as f:
        result = json.load(f)

    # 读取 scalping 配置
    with open(SCALPING_CFG) as f:
        cfg = json.load(f)

    existing_ids = {s["id"] for s in cfg.get("signals", [])}
    injected_sources = set(cfg.get("_injected_sources", []))

    # 获取 findings
    best_known = result.get("best_known", {})
    top_findings = result.get("top_findings", result.get("findings_summary", {}).get("top", []))

    candidates = []

    # ── 从 best_known 注入 ──
    for bk_id, desc in best_known.items():
        if bk_id in injected_sources:
            continue

        condition_text = parse_condition_from_desc(desc)
        symbol = extract_symbol(desc)
        timeframe = extract_timeframe(desc)
        direction = extract_direction(desc)

        # 提取指标
        wr_m = re.search(r'WR=([\d.]+)%', desc)
        n_m = re.search(r'\bn=(\d+)', desc)
        hold_m = re.search(r'hold=(\d+)', desc)
        avg_m = re.search(r'avg_ret[^=]*=([-\d.]+)%', desc)
        sharpe_m = re.search(r'Sharpe=([-\d.]+)', desc)

        if not wr_m or not n_m:
            continue
        win_rate = float(wr_m.group(1))
        n = int(n_m.group(1))

        if win_rate < MIN_WR or n < MIN_N:
            continue

        # 解析条件
        conditions = parse_condition_text(condition_text)
        if not conditions:
            continue

        hold = int(hold_m.group(1)) if hold_m else 5
        avg_ret = float(avg_m.group(1)) if avg_m else MIN_AVG_RET

        # 生成 ID
        base_id = f"disc_{symbol.lower()}_{timeframe.lower()}_{direction[0]}_{len(candidates)}"
        uniq_id = base_id
        c = 1
        while uniq_id in existing_ids:
            c += 1
            uniq_id = f"{base_id}_{c}"

        sig = {
            "id": uniq_id,
            "group": "scalping_m1m5",
            "symbols": [symbol],
            "timeframe": timeframe,
            "direction": direction,
            "entry_conditions": {
                "conditions": conditions,
                "session": next((c["v"] for c in conditions if c["i"] == "session"), None),
            },
            "best_hold": hold,
            "min_signals_for_entry": 1,
            "win_rate": win_rate,
            "signal_count": n,
            "avg_return": round(avg_ret, 4),
            "sharpe": float(sharpe_m.group(1)) if sharpe_m else 0.0,
            "priority": 10 if win_rate >= 75 else 20,
            "_auto_injected": True,
            "_injected_at": datetime.now().isoformat(),
            "_source": bk_id,
        }
        candidates.append(sig)
        existing_ids.add(uniq_id)

    # ── 从 top_findings 注入（如果 best_known 没有全覆盖） ──
    for tf in top_findings:
        cond_text = tf.get("condition", "")
        if not cond_text:
            continue
        # 生成一个唯一 key
        symbol = tf.get("symbol", "")
        if not symbol:
            symbol = extract_symbol(cond_text)
        if not symbol:
            continue  # 跳过无法确定品种的条目

        tf_key = f"auto_{symbol}_{cond_text[:30]}"
        if tf_key in injected_sources:
            continue

        direction = tf.get("direction", "long")
        n = tf.get("n", 0)
        win_rate = tf.get("win_rate", 0)
        avg_ret = tf.get("avg_return", 0)

        if win_rate < MIN_WR or n < MIN_N or avg_ret < MIN_AVG_RET:
            continue

        conditions = parse_condition_text(cond_text)
        if not conditions:
            continue

        base_id = f"disc_{symbol.lower()}_m5_{direction[0]}_{len(candidates)}"
        uniq_id = base_id
        c = 1
        while uniq_id in existing_ids:
            c += 1
            uniq_id = f"{base_id}_{c}"

        sig = {
            "id": uniq_id,
            "group": "scalping_m1m5",
            "symbols": [symbol],
            "timeframe": "M5",
            "direction": direction,
            "entry_conditions": {
                "conditions": conditions,
                "session": next((c["v"] for c in conditions if c["i"] == "session"), None),
            },
            "best_hold": tf.get("hold", 5),
            "min_signals_for_entry": 1,
            "win_rate": win_rate,
            "signal_count": n,
            "avg_return": round(avg_ret, 4),
            "sharpe": tf.get("sharpe", 0.0),
            "priority": 10 if win_rate >= 75 else 20,
            "_auto_injected": True,
            "_injected_at": datetime.now().isoformat(),
            "_source": tf_key,
        }
        candidates.append(sig)
        existing_ids.add(uniq_id)
        injected_sources.add(tf_key)

    if not candidates:
        print(f"✅ 无新合格发现 (WR≥{MIN_WR}%, n≥{MIN_N}, avg≥{MIN_AVG_RET}%)")
        return 0

    print(f"📦 发现 {len(candidates)} 个合格信号:")
    for sig in candidates:
        cond_str = "; ".join(f"{c['i']}{c['op']}{c['v']}" for c in sig["entry_conditions"]["conditions"])
        print(f"  ➕ {sig['id']}: {sig['symbols'][0]} {sig['timeframe']} {sig['direction']} "
              f"WR={sig['win_rate']}% n={sig['signal_count']} | {cond_str}")

    if dry_run:
        return 0

    # ── 注入 ──
    cfg["signals"].extend(candidates)
    cfg["_last_auto_inject"] = datetime.now().isoformat()
    cfg["_auto_inject_count"] = cfg.get("_auto_inject_count", 0) + len(candidates)
    injected_sources.update(s.get("_source", "") for s in candidates if s.get("_source"))
    cfg["_injected_sources"] = sorted(set(cfg.get("_injected_sources", [])) | injected_sources)

    with open(SCALPING_CFG, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已注入 {len(candidates)} 个新信号到 {SCALPING_CFG}")
    print(f"   当前总策略: {len(cfg['signals'])}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
