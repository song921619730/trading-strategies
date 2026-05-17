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

# 通用条件解析引擎 — 支持 320+ 指标
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))), "scripts"))
from condition_utils import parse_condition_text

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_STATE = os.path.join(BASE, "state", "research_state.json")
_RAW_CONFIG = "/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/config/scalping_strategies.json"
if sys.platform == "win32":
    _RAW_CONFIG = _RAW_CONFIG.replace("/mnt/f/", "F:/")
STRATEGIES_CONFIG = _RAW_CONFIG

# ── 注入日志文件 ──
INJECT_LOG = os.path.join(BASE, "logs", "auto_inject_scalping.log")
INJECT_LOG_MAX = 10 * 1024 * 1024
MIN_WIN_RATE_PCT = 68.0    # 胜率 > 68%（存储为百分比）
MIN_SIGNAL_COUNT = 60      # 样本量 >= 60
MIN_AVG_RETURN_PCT = 0.01  # 平均收益 > 0.01%（存储为百分比）

# 19 个 MT5 品种
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(BASE)), "scripts"))
from mt5_symbols import MT5_SYMBOLS_19
SYMBOLS = MT5_SYMBOLS_19


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

    # 生成通用 conditions 数组（支持 320+ 指标）
    conditions = parse_condition_text(desc)

    # 零条件策略不注入（无过滤 = 永动机）
    if not conditions:
        return None

    signal = {
        "id": new_id,
        "group": "scalping_m1m5",
        "symbols": [symbol],
        "timeframe": timeframe,
        "direction": direction,
        "entry_conditions": {
            "session": session if session != "any" else None,
            "conditions": conditions,
        },
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


def _parse_best_known(best_known: dict, existing_ids: set, injected_sources: set) -> list:
    """从 research_state.json 的 best_known 文本描述中解析结构化信号

    best_known 条目格式示例:
      "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=85.7% n=63 hold=55 ..."
    """
    candidates = []
    for key, desc in best_known.items():
        # 跳过已注入或明显不合格的记录
        if key in injected_sources:
            continue

        # 从 key 或 desc 提取 symbol
        symbol = ""
        for s in SYMBOLS:
            if s in desc or key.startswith(s):
                symbol = s
                break
        if not symbol:
            continue

        # 提取 timeframe (M1/M5/M15/M30/H1/H4)
        tf_match = re.search(r'\b(M[15]|M15|M30|H[14])\b', desc)
        if not tf_match:
            # 也检查 key 中的 TF
            tf_match = re.search(r'_(M[15]|M15|M30|H[14])_', key)
        if not tf_match:
            continue
        timeframe = tf_match.group(1)

        # 提取方向: 做多=long, 做空=short
        direction = "long" if "做多" in desc else ("short" if "做空" in desc else "long")

        # 提取 WR, n, hold
        wr_match = re.search(r'WR=(\d+\.?\d*)%', desc)
        n_match = re.search(r'\bn=(\d+)', desc)
        hold_match = re.search(r'hold=(\d+)', desc)
        avg_match = re.search(r'avg_ret[urn]*=([-\d.]+)%', desc)

        if not wr_match or not n_match:
            continue
        win_rate = float(wr_match.group(1))
        signal_count = int(n_match.group(1))

        # 过滤门槛
        if win_rate < MIN_WIN_RATE_PCT:
            continue
        if signal_count < MIN_SIGNAL_COUNT:
            continue
        avg_return = float(avg_match.group(1)) if avg_match else MIN_AVG_RETURN_PCT
        if avg_return < MIN_AVG_RETURN_PCT:
            continue

        # 解析 entry_conditions
        cond = _parse_best_known_conditions(desc, key)

        # ── 质量过滤 ──

        # 1. 跳过已停止跟踪的策略
        stop_keywords = ["停止跟踪", "stopped tracking", "已停止跟踪",
                         "不推荐", "撤销推荐", "已撤销",
                         "归档冻结", "冻结归档", "❌", "停止监控",
                         "正式撤销", "已停止"]
        if any(kw in desc for kw in stop_keywords):
            continue

        # 2. 必须至少有一个实际交易条件（session 不算，还需要 RSI/CB/ATR 之一）
        real_conditions = [k for k in cond if k in (
            "rsi14_max", "rsi14_min", "consecutive_bear",
            "atr_min_pct", "hour_start", "hour_end", "dxy_filter",
        )]
        if not real_conditions:
            continue

        # 3. 跳过做空（做空分支已正式关闭）
        if "做空" in desc:
            continue

        # ID: best_known 的 key
        bf_id = key if key else f"bk_{len(candidates)}"
        if bf_id in injected_sources:
            continue

        sig_id = f"auto_{symbol.lower()}_{timeframe.lower()}_{direction[0]}_{len(candidates)}"

        hold_period = int(hold_match.group(1)) if hold_match else 5

        sig = {
            "id": sig_id,
            "group": "scalping_m1m5",
            "symbols": [symbol],
            "timeframe": timeframe,
            "direction": direction,
            "entry_conditions": cond,
            "best_hold": hold_period,
            "min_signals_for_entry": 1,
            "win_rate": win_rate,
            "signal_count": signal_count,
            "avg_return": avg_return,
            "sharpe": 0,
            "priority": 10,
            "_auto_injected": True,
            "_injected_at": datetime.now().isoformat(),
            "_source": bf_id,
        }
        candidates.append(sig)
        injected_sources.add(bf_id)

    return candidates


def _parse_best_known_conditions(desc: str, key: str) -> dict:
    """从 best_known 文本描述中提取 entry_conditions"""
    cond = {}

    # Session: 用分隔符匹配避免 XAUUSD 中的 US 误匹配
    # 优先从描述文本中提取中文关键词
    if "亚盘" in desc:
        cond["session"] = "asia"
    elif "欧盘" in desc:
        cond["session"] = "europe"
    elif "美盘" in desc:
        cond["session"] = "us"
    else:
        # 从 key 的分隔符段提取: _ASIA_ / _EU_ / _US_
        key_parts = set(key.upper().split("_"))
        if "ASIA" in key_parts:
            cond["session"] = "asia"
        elif "EU" in key_parts or "EUROPE" in key_parts:
            cond["session"] = "europe"
        elif "US" in key_parts:
            cond["session"] = "us"

    # RSI < threshold
    rsi_max = re.search(r'RSI<(\d+)', desc)
    if rsi_max:
        cond["rsi14_max"] = int(rsi_max.group(1))
    # RSI > threshold
    rsi_min = re.search(r'RSI>(\d+)', desc)
    if rsi_min:
        cond["rsi14_min"] = int(rsi_min.group(1))

    # CB >= threshold
    cb = re.search(r'CB>\s*=\s*(\d+)', desc)
    if cb:
        cond["consecutive_bear"] = int(cb.group(1))

    # ATR
    atr = re.search(r'ATR>\s*([\d.]+)%?', desc)
    if atr:
        cond["atr_min_pct"] = float(atr.group(1))

    # hour 范围
    hour = re.search(r'(\d{1,2})-(\d{1,2})', desc)
    if hour:
        cond["hour_start"] = int(hour.group(1))
        cond["hour_end"] = int(hour.group(2))

    return cond


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

    # 先尝试旧格式 best_findings
    for bf in research.get("best_findings", []):
        sig = evaluate_signal(bf, existing_ids, injected_sources)
        if sig:
            candidates.append(sig)
            existing_ids.add(sig["id"])
            injected_sources.add(bf.get("id", ""))

    # 旧格式无候选时，从 best_known 文本描述中解析
    if not candidates:
        candidates = _parse_best_known(research.get("best_known", {}),
                                       existing_ids, injected_sources)

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
    # 写注入日志
    try:
        os.makedirs(os.path.dirname(INJECT_LOG), exist_ok=True)
        if os.path.exists(INJECT_LOG) and os.path.getsize(INJECT_LOG) > INJECT_LOG_MAX:
            os.rename(INJECT_LOG, INJECT_LOG + ".1")
        with open(INJECT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] 注入 {len(candidates)} 个策略\n")
            for sig in candidates:
                f.write(f"  + {sig['id']}: {sig['symbols'][0]} {sig['timeframe']} "
                        f"{sig['direction']} WR={sig['win_rate']}% n={sig['signal_count']}\n")
            f.write(f"  总策略数: {len(cfg['signals'])}\n\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
