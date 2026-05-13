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


def _parse_cond_text(text: str) -> dict:
    """从自然语言条件字符串中提取 entry_conditions 参数

    支持格式：
      - session='us'/session='europe'/session='asia' 或 美盘/欧盘/亚盘
      - rsi14<25 或 RSI<20
      - rsi14>50 或 RSI>70
      - atr14_pct>0.3 或 atr>0.4
      - consecutive_bear>=3 或 CB>=2
      - hour>=16 and hour<19 或 (16-19)
    """
    params = {}
    # Session: 英文格式
    sm = re.search(r"session\s*={1,2}\s*'(\w+)'", text)
    if sm: params["session"] = sm.group(1)
    # Session: 中文格式
    cn_map = {"美盘": "us", "欧盘": "europe", "亚盘": "asia",
              "美中": "us", "US中": "us", "欧洲": "europe", "亚洲": "asia"}
    for cn, en in cn_map.items():
        if cn in text and "session" not in params:
            params["session"] = en
            break

    # RSI < threshold (long)
    rm = re.search(r'(?:rsi14|RSI)\s*<\s*(\d+)', text)
    if rm: params["rsi14_max"] = int(rm.group(1))
    # RSI > threshold (short)
    rm2 = re.search(r'(?:rsi14|RSI)\s*>\s*(\d+)', text)
    if rm2: params["rsi14_min"] = int(rm2.group(1))

    # ATR
    am = re.search(r'(?:atr14_pct|atr)\s*>\s*([\d.]+)', text)
    if am:
        val = float(am.group(1))
        # 判断是百分比还是小数: >0.3 可能是 0.3% 或 0.003
        # 看上下文：atr14_pct>0.3 是 0.3%, atr>0.004 是 0.004
        if 'atr14_pct' in text:
            params["atr_min_pct"] = val / 100
        else:
            if val > 1:  # 可能是 0.3% 格式
                params["atr_min_pct"] = val / 100
            else:
                params["atr_min_pct"] = val

    # 连续阴线/阳线
    bm = re.search(r'(?:consecutive_bear|CB)\s*>\s*(\d+)', text)
    if bm: params["consecutive_bear"] = int(bm.group(1))
    bm2 = re.search(r'(?:consecutive_bear|CB)\s*>=\s*(\d+)', text)
    if bm2 and "consecutive_bear" not in params:
        params["consecutive_bear"] = int(bm2.group(1))

    # Hour 范围: hour>=16 and hour<19
    h_range = re.search(r'hour\s*>=\s*(\d+)\s+and\s+hour\s*<\s*(\d+)', text)
    if h_range:
        params["hour_start"] = int(h_range.group(1))
        params["hour_end"] = int(h_range.group(2))
    # Hour 范围: (16-19) 或 16-19
    h_paren = re.search(r'\((\d+)\s*-\s*(\d+)\)', text)
    if h_paren and "hour_start" not in params:
        params["hour_start"] = int(h_paren.group(1))
        params["hour_end"] = int(h_paren.group(2))
    h_dash = re.search(r'(?<!\d)(\d{2})\s*-\s*(\d{2})(?!\d)', text)
    if h_dash and "hour_start" not in params:
        # 排除年份、百分比
        v1, v2 = int(h_dash.group(1)), int(h_dash.group(2))
        if 0 <= v1 <= 23 and 0 <= v2 <= 23:
            params["hour_start"] = v1
            params["hour_end"] = v2

    # 单 hour 条件
    hm = re.search(r'hour\s*(>=|<=|>|<|==)\s*(\d+)', text)
    if hm and "hour_start" not in params:
        params[f'hour_{hm.group(1)}'] = int(hm.group(2))

    return params


def parse_entry_params(cond_str: str, fallback_str: str = "") -> dict:
    """从条件字符串解析 entry_conditions 参数，支持双段合并

    先用 cond_str 解析，再用 fallback_str 补充（合并非空值），
    确保条件对 RSI/ATR/session/连阴 的提取优先于纯小时窗口。
    """
    params = _parse_cond_text(cond_str)
    if fallback_str:
        fb_params = _parse_cond_text(fallback_str)
        # 合并：fallback 的非 hour 条件优先补充
        for k, v in fb_params.items():
            if k not in params or k.startswith("hour_"):
                params[k] = v
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

    # 解析 entry_condition（双段解析：前半段条件+后半段回测结果）
    desc_parts = desc.split("—")
    desc_first = desc_parts[0].strip() if desc_parts else ""       # 前半段（可能含条件）
    desc_second = desc_parts[-1].strip() if len(desc_parts) > 1 else ""  # 后半段
    params = parse_entry_params(desc_second, desc_first)
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
