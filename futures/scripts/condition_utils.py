#!/usr/bin/env python3
"""
condition_utils.py — 通用条件解析+求值引擎

支持 320+ 指标的条件匹配，供 auto_inject 和 scanner 共用。

指标数据源: Tick Engine 写入的 data/tick/indicators_{TF}.json
  每个品种的 indicator dict 已包含全部 319 个字段。

条件格式（新版 — 通用数组）:
  {"conditions": [
    {"i": "rsi14", "op": "<", "v": 25},
    {"i": "atr14_pct", "op": ">", "v": 0.35},
    {"i": "above_vwap", "op": "==", "v": 1},
    {"i": "stoch_k_14", "op": ">", "v": 80},
    {"i": "cci_14", "op": ">", "v": 100},
    {"i": "session", "op": "==", "v": "us"},
  ]}

旧版兼容: 自动检测旧字段格式 (session/rsi14_max/rsi14_min/atr_min_pct/consecutive_bear)
"""
import re
from typing import Any

# ── 支持的运算符 ──
OPERATORS = {
    "<": lambda a, b: a is not None and a < b,
    "<=": lambda a, b: a is not None and a <= b,
    ">": lambda a, b: a is not None and a > b,
    ">=": lambda a, b: a is not None and a >= b,
    "==": lambda a, b: a is not None and a == b,
    "!=": lambda a, b: a is not None and a != b,
}
_re_prd = re.compile(r'_(\d+)$')


# ── 字段名归一化：研究侧名 → Tick Engine 实盘名 ──
# 研究用 batch_precompute.py 命名，实盘用 indicators.py 命名，部分不一致
FIELD_NAME_MAP = {
    "stoch_k": "stoch_k_k",
    "stoch_d": "stoch_k_d",
    "adx": "adx_adx",
    "plus_di": "adx_di_plus",
    "minus_di": "adx_di_minus",
    "klinger": "klinger_klinger",
    "consecutive_bear_count": "consecutive_bear",
    # 研究文本短名映射
    "rsi": "rsi14",
    "cb": "consecutive_bull",
}


def normalize_field(name: str) -> str:
    """将任意指标名映射到 Tick Engine 实际字段名"""
    if name in FIELD_NAME_MAP:
        return FIELD_NAME_MAP[name]
    base = _re_prd.sub('', name)
    if base != name and base in FIELD_NAME_MAP:
        return FIELD_NAME_MAP[base]
    import re
    name = re.sub(r'_(\d+)\.0', r'_\1', name)  # bb_20_2.0 → bb_20_2
    name = name.replace('.', '_')  # fallback: other dots
    return name


def parse_condition_text(text: str) -> list[dict]:
    """将自然语言条件文本解析为通用条件格式

    支持任意指标名 + 运算符 + 值的组合。
    示例:
      "rsi14 < 25 and atr14/close > 0.003 and session == 'us' and above_vwap == 1"
      → [{"i":"rsi14","op":"<","v":25}, {"i":"atr14_pct","op":">","v":0.003},
           {"i":"session","op":"==","v":"us"}, {"i":"above_vwap","op":"==","v":1}]
    """
    conditions = []

    if not text:
        return conditions

    # 1. 拆分成单条件片段 (按 and 或 + 分割)
    parts = re.split(r'\s+and\s+', text.lower().strip())
    if len(parts) <= 1 and '+' in text:
        parts = text.lower().strip().split('+')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        cond = _parse_single_condition(part)
        if cond:
            conditions.append(cond)

    return conditions


def _parse_single_condition(part: str) -> dict | None:
    """解析单个条件表达式，返回 {"i": ..., "op": ..., "v": ...}"""

    # 处理 session == 'xxx'
    m = re.match(r"session\s*==?\s*'(\w+)'", part)
    if m:
        return {"i": "session", "op": "==", "v": m.group(1)}

    # 处理 atr14/close > val → atr14_pct
    m = re.match(r'atr(\d+)\s*/\s*close\s*([<>=!]+)\s*([\d.]+)', part)
    if m:
        period = m.group(1)
        op = m.group(2)
        val = float(m.group(3))
        if op not in OPERATORS:
            return None
        return {"i": f"atr{period}_pct", "op": op, "v": val * 100}

    # 处理 indicator operator value (通用模式)
    # 匹配: 字母_数字 或 纯字母 → 运算符 → 值
    m = re.match(r'([a-zA-Z_][\w]*)\s*([<>=!]+)\s*([\d.]+)', part)
    if m:
        indicator = m.group(1)
        op = m.group(2)
        raw_val = m.group(3)
        val = float(raw_val) if '.' in raw_val else int(raw_val)
        if op not in OPERATORS:
            return None
        return {"i": indicator, "op": op, "v": val}

    # 处理 session 别名（中文）
    cn_map = {"美盘": "us", "欧盘": "europe", "亚盘": "asia",
              "美中": "us", "欧洲": "europe", "亚洲": "asia"}
    for cn, en in cn_map.items():
        if cn in part:
            return {"i": "session", "op": "==", "v": en}

    return None


# ══════════════════════════════════════════════════════
# 旧版格式兼容 — 将旧 entry_conditions dict 转为 conditions array
# ══════════════════════════════════════════════════════

_OLD_TO_CONDITIONS = [
    # (old_key, indicator, operator, value_fn)
    # 这些不需要 value_fn，直接取 old value
]


def old_format_to_conditions(entry_conditions: dict) -> list[dict]:
    """将旧版 entry_conditions dict 转为新版 conditions 数组"""
    conditions = []

    if "session" in entry_conditions and entry_conditions["session"]:
        conditions.append({"i": "session", "op": "==", "v": entry_conditions["session"]})
    if "rsi14_max" in entry_conditions:
        conditions.append({"i": "rsi14", "op": "<", "v": entry_conditions["rsi14_max"]})
    if "rsi14_min" in entry_conditions:
        conditions.append({"i": "rsi14", "op": ">", "v": entry_conditions["rsi14_min"]})
    if "atr_min_pct" in entry_conditions:
        conditions.append({"i": "atr14_pct", "op": ">", "v": entry_conditions["atr_min_pct"] * 100})
    if "consecutive_bear" in entry_conditions:
        conditions.append({"i": "consecutive_bear", "op": ">=", "v": entry_conditions["consecutive_bear"]})
    if "consecutive_bull" in entry_conditions:
        conditions.append({"i": "consecutive_bull", "op": ">=", "v": entry_conditions["consecutive_bull"]})
    if "pullback_to_ma50" in entry_conditions:
        conditions.append({"i": "_near_ma50", "op": "==", "v": int(entry_conditions["pullback_to_ma50"])})
    if "hour_start" in entry_conditions:
        conditions.append({"i": "utc_hour", "op": ">=", "v": entry_conditions["hour_start"]})
    if "hour_end" in entry_conditions:
        conditions.append({"i": "utc_hour", "op": "<", "v": entry_conditions["hour_end"]})
    if "dxy_filter" in entry_conditions:
        # DXY 过滤是特殊逻辑，保持原样
        conditions.append({"i": "_dxy_filter", "op": "==", "v": entry_conditions["dxy_filter"]})

    return conditions


def has_old_format(entry_conditions: dict) -> bool:
    """检查 entry_conditions 是否使用旧版字段格式"""
    old_keys = {"rsi14_max", "rsi14_min", "atr_min_pct",
                "consecutive_bear", "consecutive_bull", "pullback_to_ma50",
                "hour_start", "hour_end", "dxy_filter"}
    return bool(old_keys & set(entry_conditions.keys()))


# ══════════════════════════════════════════════════════
# 求值引擎
# ══════════════════════════════════════════════════════

def evaluate_conditions(conditions: list[dict],
                        indicators: dict,
                        dxy_indicators: dict | None = None,
                        h1_indicators: dict | None = None) -> tuple[bool, list[str]]:
    """评估条件列表，返回 (是否匹配, 匹配原因列表)

    indicators: 品种在当前 TF 的全部指标 dict (319 字段)
    dxy_indicators: DXY H1 指标 dict（可选，用于 _dxy_filter）
    """
    matched = True
    reasons = []

    for cond in conditions:
        indicator = cond["i"]
        op = cond["op"]
        target = cond["v"]

        # 特殊处理: _dxy_filter
        if indicator == "_dxy_filter":
            if dxy_indicators is None:
                matched = False
                continue
            dxy_close = dxy_indicators.get("price")
            dxy_ma20 = dxy_indicators.get("ma20")
            if target == "down":
                ok = dxy_close is not None and dxy_ma20 is not None and dxy_close < dxy_ma20
            elif target == "up":
                ok = dxy_close is not None and dxy_ma20 is not None and dxy_close > dxy_ma20
            else:
                ok = True
            if ok:
                reasons.append(f"DXY{target}(close={dxy_close}ma20={dxy_ma20})")
            else:
                matched = False
            continue

        # 特殊处理: _near_ma50 — 价格是否在 MA50 附近 0.1% 以内
        if indicator == "_near_ma50":
            close_vs_ma50 = indicators.get("close_vs_ma50")
            if close_vs_ma50 is None:
                matched = False
                continue
            is_near = abs(close_vs_ma50) < 0.1
            ok = (target == 1 and is_near) or (target == 0 and not is_near)
            if ok:
                reasons.append(f"near_ma50={is_near}(close_vs_ma50={close_vs_ma50:.4f}%)")
            else:
                matched = False
            continue

        # 跨TF: _h1_ 前缀 → 读 H1 指标
        if indicator.startswith("_h1_"):
            h1_field = indicator[4:]  # 去掉 "_h1_" 前缀
            if h1_indicators is None:
                matched = False
                continue
            h1_actual = h1_indicators.get(h1_field)
            if h1_actual is None:
                matched = False
                continue
            op_fn = OPERATORS.get(op)
            if op_fn is None:
                matched = False
                continue
            result = op_fn(h1_actual, target)
            if result:
                reasons.append(f"H1.{h1_field}={h1_actual:.4f}{op}{target}")
            else:
                matched = False
            continue

        # 查找指标值（自动归一化字段名）
        norm_name = normalize_field(indicator)
        actual = indicators.get(norm_name)
        if actual is None and norm_name != indicator:
            actual = indicators.get(indicator)  # fallback 原名字
        if actual is None:
            # 指标不存在或未就绪
            matched = False
            continue

        # 执行运算
        op_fn = OPERATORS.get(op)
        if op_fn is None:
            matched = False
            continue

        result = op_fn(actual, target)
        if result:
            if isinstance(actual, float):
                reasons.append(f"{indicator}={actual:.2f}{op}{target}")
            else:
                reasons.append(f"{indicator}={actual}{op}{target}")
        else:
            matched = False

    return matched, reasons


def evaluate_entry_conditions(entry_conditions: dict,
                               indicators: dict,
                               dxy_indicators: dict | None = None,
                               h1_indicators: dict | None = None) -> tuple[bool, list[str]]:
    """统一入口: 兼容新旧格式，评估 entry_conditions

    新版: {"conditions": [{"i":..., "op":..., "v":...}, ...], "session": "us"}
    旧版: {"session": "us", "rsi14_max": 25, "atr_min_pct": 0.003, ...}
    """
    # 新版优先
    if "conditions" in entry_conditions and entry_conditions["conditions"]:
        conds = entry_conditions["conditions"]
        # 额外的 session 检查
        session = indicators.get("session")
        if "session" in entry_conditions and entry_conditions["session"]:
            if session != entry_conditions["session"]:
                return False, [f"session={session} != {entry_conditions['session']}"]
        return evaluate_conditions(conds, indicators, dxy_indicators, h1_indicators)

    # 旧版兼容
    if has_old_format(entry_conditions):
        conds = old_format_to_conditions(entry_conditions)
        return evaluate_conditions(conds, indicators, dxy_indicators, h1_indicators)

    # 纯 session 检查
    if "session" in entry_conditions and entry_conditions["session"]:
        session = indicators.get("session")
        if session != entry_conditions["session"]:
            return False, [f"session={session} != {entry_conditions['session']}"]
        return True, [f"session={session}"]

    return True, ["no_conditions"]
