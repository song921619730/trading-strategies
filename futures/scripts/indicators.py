"""
indicators.py — 共享技术指标计算库

被 tick_engine.py（实时交易）和 precompute_indicators.py（研究回测）共用。
所有函数输入都是 bars（list of dict: time/open/high/low/close/volume）。
返回计算后的指标值，None 表示数据不足。

用法:
  from indicators import calc_rsi, calc_atr, calc_macd, ...
  bars = get_bars()
  rsi = calc_rsi(bars)          # RSI(14)
  rsi7 = calc_rsi(bars, 7)      # RSI(7)
  macd = calc_macd(bars)        # {"macd": ..., "signal": ..., "hist": ...}
"""

import math
import numpy as np
from typing import Optional, Union


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _closes(bars: list) -> list:
    return [b["close"] for b in bars]


def _highs(bars: list) -> list:
    return [b["high"] for b in bars]


def _lows(bars: list) -> list:
    return [b["low"] for b in bars]


def _volumes(bars: list) -> list:
    return [b.get("volume", b.get("tick_volume", 0)) for b in bars]


def _typical(bars: list) -> list:
    return [(b["high"] + b["low"] + b["close"]) / 3 for b in bars]


# ═══════════════════════════════════════════════════════════════
# 1. 动量指标
# ═══════════════════════════════════════════════════════════════

def calc_rsi(bars: list, period: int = 14) -> Optional[float]:
    """RSI: Relative Strength Index"""
    closes = _closes(bars)
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


def calc_stochastic(bars: list, k_period: int = 14, d_period: int = 3) -> dict:
    """Stochastic Oscillator: %K and %D"""
    if len(bars) < k_period + 1:
        return {"k": None, "d": None}
    recent = bars[-(k_period + 1):]
    high_k = max(b["high"] for b in recent)
    low_k = min(b["low"] for b in recent)
    if high_k == low_k:
        return {"k": 50.0, "d": 50.0}
    last = bars[-1]
    k = (last["close"] - low_k) / (high_k - low_k) * 100

    # %D = SMA of %K
    if len(bars) < k_period + d_period:
        return {"k": k, "d": None}
    k_values = []
    for i in range(d_period):
        sub_bars = bars[-(k_period + 1 + i):len(bars) - i]
        h = max(b["high"] for b in sub_bars)
        l = min(b["low"] for b in sub_bars)
        if h != l:
            k_values.append((sub_bars[-1]["close"] - l) / (h - l) * 100)
        else:
            k_values.append(50.0)
    d = sum(k_values) / len(k_values) if k_values else None
    return {"k": float(k), "d": float(d)}


def calc_williams_r(bars: list, period: int = 14) -> Optional[float]:
    """Williams %R"""
    if len(bars) < period:
        return None
    recent = bars[-period:]
    high_h = max(b["high"] for b in recent)
    low_l = min(b["low"] for b in recent)
    if high_h == low_l:
        return -50.0
    return (high_h - bars[-1]["close"]) / (high_h - low_l) * -100


def calc_cci(bars: list, period: int = 20) -> Optional[float]:
    """Commodity Channel Index"""
    if len(bars) < period:
        return None
    recent = bars[-period:]
    tp_vals = [(b["high"] + b["low"] + b["close"]) / 3 for b in recent]
    sma_tp = sum(tp_vals) / period
    mad = sum(abs(t - sma_tp) for t in tp_vals) / period
    if mad == 0:
        return 0.0
    return (tp_vals[-1] - sma_tp) / (0.015 * mad)


def calc_momentum(bars: list, period: int = 10) -> Optional[float]:
    """Momentum: close / close_n_periods_ago * 100"""
    closes = _closes(bars)
    if len(closes) <= period:
        return None
    return (closes[-1] / closes[-period - 1]) * 100


def calc_roc(bars: list, period: int = 10) -> Optional[float]:
    """Rate of Change %"""
    closes = _closes(bars)
    if len(closes) <= period or closes[-period - 1] == 0:
        return None
    return (closes[-1] - closes[-period - 1]) / closes[-period - 1] * 100


# ═══════════════════════════════════════════════════════════════
# 2. 趋势指标
# ═══════════════════════════════════════════════════════════════

def calc_ema(bars: list, period: int) -> Optional[float]:
    """Exponential Moving Average（最后一个值）"""
    closes = _closes(bars)
    if len(closes) < period:
        return closes[-1] if closes else None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def calc_sma(closes: list, period: int) -> Optional[float]:
    """Simple Moving Average"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calc_macd(bars: list, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD: line, signal, histogram"""
    closes = _closes(bars)
    if len(closes) < slow + signal:
        return {"macd": None, "signal": None, "hist": None}

    # EMA fast
    k_fast = 2 / (fast + 1)
    ema_f = sum(closes[:fast]) / fast
    for c in closes[fast:]:
        ema_f = c * k_fast + ema_f * (1 - k_fast)

    # EMA slow
    k_slow = 2 / (slow + 1)
    ema_s = sum(closes[:slow]) / slow
    for c in closes[slow:]:
        ema_s = c * k_slow + ema_s * (1 - k_slow)

    macd_line = ema_f - ema_s

    # Signal line: EMA of macd
    # We need a series of macd values for this
    macd_values = []
    for i in range(signal + 1):
        idx = len(closes) - signal - 1 + i
        if idx < slow:
            continue
        chunk = closes[:idx + 1]
        ef = sum(chunk[:fast]) / fast
        for c in chunk[fast:]:
            ef = c * k_fast + ef * (1 - k_fast)
        es = sum(chunk[:slow]) / slow
        for c in chunk[slow:]:
            es = c * k_slow + es * (1 - k_slow)
        macd_values.append(ef - es)

    if len(macd_values) >= signal:
        sig = sum(macd_values[-signal:]) / signal
        hist = macd_line - sig
    else:
        sig = macd_line
        hist = 0

    return {
        "macd": float(macd_line),
        "signal": float(sig),
        "hist": float(hist),
    }


def calc_adx(bars: list, period: int = 14) -> dict:
    """ADX + DI+ / DI-"""
    if len(bars) < period + 2:
        return {"adx": None, "di_plus": None, "di_minus": None}

    tr_values, plus_dm, minus_dm = [], [], []
    for i in range(1, min(period + 2, len(bars))):
        h, l, pc = bars[-i]["high"], bars[-i]["low"], bars[-i - 1]["close"]
        tr_values.append(max(h - l, abs(h - pc), abs(l - pc)))
        up_move = bars[-i]["high"] - bars[-i - 1]["high"]
        down_move = bars[-i - 1]["low"] - bars[-i]["low"]
        plus_dm.append(max(up_move, 0) if up_move > down_move else 0)
        minus_dm.append(max(down_move, 0) if down_move > up_move else 0)

    tr_sum = sum(tr_values[:period])
    plus_sum = sum(plus_dm[:period])
    minus_sum = sum(minus_dm[:period])

    if tr_sum == 0:
        return {"adx": 0, "di_plus": 0, "di_minus": 0}

    di_plus = (plus_sum / tr_sum) * 100 if tr_sum > 0 else 0
    di_minus = (minus_sum / tr_sum) * 100 if tr_sum > 0 else 0
    dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
    adx = dx  # simplified: single-period ADX ≈ DX for 1-period

    return {
        "adx": float(adx),
        "di_plus": float(di_plus),
        "di_minus": float(di_minus),
    }


def calc_aroon(bars: list, period: int = 14) -> dict:
    """Aroon Up/Down/Oscillator"""
    if len(bars) < period + 1:
        return {"up": None, "down": None, "osc": None}
    recent = bars[-(period + 1):]
    high_idx = max(range(len(recent)), key=lambda i: recent[i]["high"])
    low_idx = min(range(len(recent)), key=lambda i: recent[i]["low"])
    up = ((period - high_idx) / period) * 100
    down = ((period - low_idx) / period) * 100
    return {"up": float(up), "down": float(down), "osc": float(up - down)}


# ═══════════════════════════════════════════════════════════════
# 3. 波动率指标
# ═══════════════════════════════════════════════════════════════

def calc_atr(bars: list, period: int = 14) -> Optional[float]:
    """ATR: Average True Range"""
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[-i]["high"]
        l = bars[-i]["low"]
        pc = bars[-i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[:period]) / period


def calc_bollinger_bands(bars: list, period: int = 20, std_dev: float = 2.0) -> dict:
    """Bollinger Bands: upper, middle, lower, width, %B"""
    closes = _closes(bars)
    if len(closes) < period:
        return {"upper": None, "middle": None, "lower": None, "width": None, "b": None}
    sma = sum(closes[-period:]) / period
    variance = sum((c - sma) ** 2 for c in closes[-period:]) / period
    std = math.sqrt(variance)
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    width = (upper - lower) / sma * 100 if sma > 0 else 0
    b_pct = (closes[-1] - lower) / (upper - lower) * 100 if (upper - lower) > 0 else 50
    return {
        "upper": float(upper),
        "middle": float(sma),
        "lower": float(lower),
        "width": float(width),
        "b": float(b_pct),
    }


def calc_choppiness(bars: list, period: int = 14) -> Optional[float]:
    """Choppiness Index (0-100). Low = trending, High = choppy"""
    if len(bars) < period:
        return None
    recent = bars[-period:]
    high_h = max(b["high"] for b in recent)
    low_l = min(b["low"] for b in recent)
    tr_sum = 0
    for i in range(1, len(recent)):
        h = recent[-i]["high"]
        l = recent[-i]["low"]
        pc = recent[-i - 1]["close"]
        tr_sum += max(h - l, abs(h - pc), abs(l - pc))
    if tr_sum == 0 or (high_h - low_l) == 0:
        return 50.0
    ci = 100 * math.log10(tr_sum / (high_h - low_l)) / math.log10(period)
    return max(0, min(100, float(ci)))


# ═══════════════════════════════════════════════════════════════
# 4. 成交量指标
# ═══════════════════════════════════════════════════════════════

def calc_volume_ratio(bars: list, period: int = 5) -> Optional[float]:
    """当前成交量 / 过去 period 根的平均成交量"""
    volumes = _volumes(bars)
    if len(volumes) < period + 1:
        return None
    avg_vol = sum(volumes[-(period + 1):-1]) / period
    if avg_vol == 0:
        return 1.0
    return volumes[-1] / avg_vol


def calc_obv(bars: list) -> Optional[float]:
    """On-Balance Volume"""
    if len(bars) < 2:
        return None
    obv = 0
    for i in range(1, len(bars)):
        if bars[i]["close"] > bars[i - 1]["close"]:
            obv += bars[i].get("volume", bars[i].get("tick_volume", 0))
        elif bars[i]["close"] < bars[i - 1]["close"]:
            obv -= bars[i].get("volume", bars[i].get("tick_volume", 0))
    return float(obv)


def calc_mfi(bars: list, period: int = 14) -> Optional[float]:
    """Money Flow Index"""
    if len(bars) < period + 1:
        return None
    pos_flow, neg_flow = 0, 0
    for i in range(1, period + 1):
        tp = (bars[-i]["high"] + bars[-i]["low"] + bars[-i]["close"]) / 3
        vol = bars[-i].get("volume", bars[-i].get("tick_volume", 0))
        prev_tp = (bars[-i - 1]["high"] + bars[-i - 1]["low"] + bars[-i - 1]["close"]) / 3
        if tp > prev_tp:
            pos_flow += tp * vol
        elif tp < prev_tp:
            neg_flow += tp * vol
    if neg_flow == 0:
        return 100.0 if pos_flow > 0 else 50.0
    mfr = pos_flow / neg_flow
    return 100.0 - (100.0 / (1.0 + mfr))


# ═══════════════════════════════════════════════════════════════
# 5. 价格行为指标
# ═══════════════════════════════════════════════════════════════

def detected_consecutive_bears(bars: list) -> int:
    """连阴计数"""
    count = 0
    for bar in reversed(bars):
        if bar["close"] < bar["open"]:
            count += 1
        else:
            break
    return count


def detected_consecutive_bulls(bars: list) -> int:
    """连阳计数"""
    count = 0
    for bar in reversed(bars):
        if bar["close"] > bar["open"]:
            count += 1
        else:
            break
    return count


def detect_doji(bars: list, body_ratio: float = 0.1) -> bool:
    """Doji: 实体很小（开收盘接近）"""
    if not bars:
        return False
    b = bars[-1]
    body = abs(b["close"] - b["open"])
    range_v = b["high"] - b["low"]
    if range_v == 0:
        return False
    return body / range_v < body_ratio


def detect_hammer(bars: list, body_ratio: float = 0.3, wick_ratio: float = 2.0) -> bool:
    """Hammer: 下影线>=2倍实体，上影线短"""
    if len(bars) < 1:
        return False
    b = bars[-1]
    body = abs(b["close"] - b["open"])
    upper_wick = b["high"] - max(b["open"], b["close"])
    lower_wick = min(b["open"], b["close"]) - b["low"]
    if body == 0:
        return False
    return lower_wick >= body * wick_ratio and upper_wick <= body * 0.3


def detect_engulfing(bars: list) -> dict:
    """吞没形态: bull_engulfing, bear_engulfing"""
    if len(bars) < 2:
        return {"bull": False, "bear": False}
    curr, prev = bars[-1], bars[-2]
    bull = curr["close"] > curr["open"] and prev["close"] < prev["open"] \
           and curr["close"] > prev["open"] and curr["open"] < prev["close"]
    bear = curr["close"] < curr["open"] and prev["close"] > prev["open"] \
           and curr["close"] < prev["open"] and curr["open"] > prev["close"]
    return {"bull": bull, "bear": bear}


def detect_inside_bar(bars: list) -> bool:
    """Inside Bar: 当前 bar 在上一根范围内"""
    if len(bars) < 2:
        return False
    curr, prev = bars[-1], bars[-2]
    return curr["high"] <= prev["high"] and curr["low"] >= prev["low"]


def detect_pin_bar(bars: list, wick_ratio: float = 2.0) -> dict:
    """Pin Bar: 长影线，实体小"""
    if len(bars) < 1:
        return {"bull": False, "bear": False}
    b = bars[-1]
    body = abs(b["close"] - b["open"])
    upper = b["high"] - max(b["open"], b["close"])
    lower = min(b["open"], b["close"]) - b["low"]
    if body == 0:
        return {"bull": False, "bear": False}
    bull = lower >= upper * wick_ratio and lower >= body * wick_ratio
    bear = upper >= lower * wick_ratio and upper >= body * wick_ratio
    return {"bull": bull, "bear": bear}


# ═══════════════════════════════════════════════════════════════
# 6. 结构指标
# ═══════════════════════════════════════════════════════════════

def calc_highest_high(bars: list, period: int = 20) -> Optional[float]:
    """过去 period 根的最高价"""
    if len(bars) < period:
        return None
    return max(b["high"] for b in bars[-period:])


def calc_lowest_low(bars: list, period: int = 20) -> Optional[float]:
    """过去 period 根的最低价"""
    if len(bars) < period:
        return None
    return min(b["low"] for b in bars[-period:])


def calc_support_resistance(bars: list, period: int = 20) -> dict:
    """支撑位和阻力位"""
    if len(bars) < period:
        return {"support": None, "resistance": None}
    recent = bars[-period:]
    resistance = max(b["high"] for b in recent)
    support = min(b["low"] for b in recent)
    return {
        "support": float(support),
        "resistance": float(resistance),
        "near_support_pct": ((bars[-1]["close"] - support) / (resistance - support) * 100
                             if (resistance - support) > 0 else 50),
        "near_resistance_pct": ((resistance - bars[-1]["close"]) / (resistance - support) * 100
                                if (resistance - support) > 0 else 50),
    }


def calc_pivot_points(bars: list, period: int = 1) -> dict:
    """Pivot Points (日级别)"""
    if len(bars) < period * 24:  # 粗略估算
        return {"pivot": None, "r1": None, "s1": None, "r2": None, "s2": None}
    # 用最近 period 根 bar 的 high/low/close
    recent = bars[-period:]
    high = max(b["high"] for b in recent)
    low = min(b["low"] for b in recent)
    close = recent[-1]["close"]
    pivot = (high + low + close) / 3
    return {
        "pivot": float(pivot),
        "r1": float(2 * pivot - low),
        "s1": float(2 * pivot - high),
        "r2": float(pivot + (high - low)),
        "s2": float(pivot - (high - low)),
    }


# ═══════════════════════════════════════════════════════════════
# 7. Session / 时间
# ═══════════════════════════════════════════════════════════════

SESSION_MAP = {
    "asia":   (0, 8),
    "europe": (8, 13),
    "us":     (13, 22),
}
SESSION_ALIAS = {"london": "europe"}


def get_session(utc_hour: int) -> str:
    for name, (start, end) in SESSION_MAP.items():
        if start <= utc_hour < end:
            return name
    return "asia"


# ═══════════════════════════════════════════════════════════════
# 9. 高级指标（新增 46 个函数）
# ═══════════════════════════════════════════════════════════════

# ── 辅助函数 ──

def _ema_series(vals: list, period: int) -> list:
    """返回完整的 EMA 序列（从第 period 个元素开始）"""
    if len(vals) < period:
        return []
    k = 2 / (period + 1)
    ema = sum(vals[:period]) / period
    result = [ema]
    for v in vals[period:]:
        ema = v * k + ema * (1 - k)
        result.append(ema)
    return result


def _sma_values(vals: list, period: int) -> list:
    """返回完整的 SMA 序列"""
    if len(vals) < period:
        return []
    return [sum(vals[i - period:i]) / period for i in range(period, len(vals) + 1)]


def _true_range(bars: list, i: int) -> float:
    """计算第 i 根 bar 的 True Range（i>=1）"""
    h = bars[i]["high"]
    l = bars[i]["low"]
    pc = bars[i - 1]["close"]
    return max(h - l, abs(h - pc), abs(l - pc))


# ═══════════════════════════════════════════════════════════════
# 9A. 均线分散 / Guppy
# ═══════════════════════════════════════════════════════════════

def calc_guppy_short_spread(bars: list) -> Optional[float]:
    """Guppy 短期均线分散度: EMA(3,5,8,10,12,15) 的离散程度
    正值表示多头排列（短均线在上方），负值表示空头排列。
    """
    periods = [3, 5, 8, 10, 12, 15]
    emas = []
    for p in periods:
        v = calc_ema(bars, p)
        if v is None:
            return None
        emas.append(v)
    if emas[-1] == 0:
        return None
    return float((emas[0] - emas[-1]) / emas[-1] * 100)


def calc_guppy_long_spread(bars: list) -> Optional[float]:
    """Guppy 长期均线分散度: EMA(30,34,50,55,89,100,144,200) 的离散程度
    正值表示多头排列，负值表示空头排列。
    """
    periods = [30, 34, 50, 55, 89, 100, 144, 200]
    emas = []
    for p in periods:
        v = calc_ema(bars, p)
        if v is None:
            return None
        emas.append(v)
    if emas[-1] == 0:
        return None
    return float((emas[0] - emas[-1]) / emas[-1] * 100)


# ═══════════════════════════════════════════════════════════════
# 9B. TRIX / 三重指数平滑移动平均
# ═══════════════════════════════════════════════════════════════

def calc_trix(bars: list, period: int = 14) -> dict:
    """TRIX: Triple Exponential Moving Average Oscillator
    对收盘价做三次 EMA 平滑后计算变化率。
    返回: {"trix": float, "signal": float, "cross": int(-1/0/1)}
    """
    closes = _closes(bars)
    min_needed = period * 3 + 2
    if len(closes) < min_needed:
        return {"trix": None, "signal": None, "cross": 0}

    ema1 = _ema_series(closes, period)
    if len(ema1) < period:
        return {"trix": None, "signal": None, "cross": 0}
    ema2 = _ema_series(ema1, period)
    if len(ema2) < period:
        return {"trix": None, "signal": None, "cross": 0}
    ema3 = _ema_series(ema2, period)
    if len(ema3) < 2:
        return {"trix": None, "signal": None, "cross": 0}

    # TRIX = 三次 EMA 的百分比变化
    trix_vals = []
    for i in range(1, len(ema3)):
        prev = ema3[i - 1]
        trix_vals.append((ema3[i] - prev) / prev * 100 if prev != 0 else 0.0)

    trix_current = trix_vals[-1]

    # Signal = SMA of TRIX
    if len(trix_vals) >= period:
        signal_val = sum(trix_vals[-period:]) / period
    else:
        signal_val = trix_current

    # Cross direction
    cross = 0
    if len(trix_vals) >= period + 1:
        prev_trix = trix_vals[-2]
        prev_signal = sum(trix_vals[-(period + 1):-1]) / period
        if prev_trix <= prev_signal and trix_current > signal_val:
            cross = 1
        elif prev_trix >= prev_signal and trix_current < signal_val:
            cross = -1

    return {"trix": float(trix_current), "signal": float(signal_val), "cross": cross}


# ═══════════════════════════════════════════════════════════════
# 9C. Ultimate Oscillator / 终极振荡器
# ═══════════════════════════════════════════════════════════════

def calc_ultimate_oscillator(bars: list) -> Optional[float]:
    """Ultimate Oscillator (终极振荡器): 多周期权重组合 (7,14,28)
    BP = close - min(low, prev_close)
    TR = max(high, prev_close) - min(low, prev_close)
    返回: float (0-100)
    """
    if len(bars) < 29:
        return None

    def _uo(p: int) -> float:
        bp_sum = 0.0
        tr_sum = 0.0
        for i in range(1, min(p + 1, len(bars))):
            idx = len(bars) - i
            prev = bars[idx - 1]
            b = bars[idx]
            bp = b["close"] - min(b["low"], prev["close"])
            tr = max(b["high"], prev["close"]) - min(b["low"], prev["close"])
            bp_sum += bp
            tr_sum += tr
        return bp_sum / tr_sum if tr_sum != 0 else 0.5

    avg7 = _uo(7)
    avg14 = _uo(14)
    avg28 = _uo(28)

    uo = (avg7 * 4 + avg14 * 2 + avg28 * 1) / (4 + 2 + 1) * 100
    return float(uo)


# ═══════════════════════════════════════════════════════════════
# 9D. RVGI / 相对活力指数
# ═══════════════════════════════════════════════════════════════

def calc_rvgi(bars: list) -> dict:
    """RVGI: Relative Vigor Index (相对活力指数)
    RVG = (close - open) / (high - low) 的 SMA(10) 平滑
    Signal = SMA(4) of RVG
    返回: {"rvg": float, "signal": float}
    """
    if len(bars) < 14:
        return {"rvg": None, "signal": None}

    # 计算原始 RVG 值
    rvg_raw = []
    for b in bars:
        denom = b["high"] - b["low"]
        rvg_raw.append((b["close"] - b["open"]) / denom if denom != 0 else 0.0)

    # SMA(10)
    if len(rvg_raw) < 10:
        return {"rvg": None, "signal": None}
    rvg_line = [sum(rvg_raw[i - 10:i]) / 10 for i in range(10, len(rvg_raw) + 1)]

    rvg_current = rvg_line[-1]

    # Signal = SMA(4) of RVG line
    signal_val = sum(rvg_line[-4:]) / 4 if len(rvg_line) >= 4 else rvg_current

    return {"rvg": float(rvg_current), "signal": float(signal_val)}


# ═══════════════════════════════════════════════════════════════
# 9E. KST / Know Sure Thing
# ═══════════════════════════════════════════════════════════════

def calc_kst(bars: list) -> dict:
    """KST (Know Sure Thing): 综合多周期 ROC 的动量指标
    KST = RCMA(10,10) + RCMA(15,10)*2 + RCMA(20,10)*3 + RCMA(30,15)*4
    返回: {"kst": float, "signal": float}
    """
    closes = _closes(bars)
    if len(closes) < 46:  # 30 + 15 + 1
        return {"kst": None, "signal": None}

    def _rcma(vals, roc_p, sma_p):
        if len(vals) < roc_p + sma_p:
            return None
        roc_vals = []
        for i in range(roc_p, len(vals)):
            prev = vals[i - roc_p]
            roc_vals.append((vals[i] - prev) / prev * 100 if prev != 0 else 0.0)
        if len(roc_vals) < sma_p:
            return None
        return sum(roc_vals[-sma_p:]) / sma_p

    rcma1 = _rcma(closes, 10, 10)
    rcma2 = _rcma(closes, 15, 10)
    rcma3 = _rcma(closes, 20, 10)
    rcma4 = _rcma(closes, 30, 15)

    if any(v is None for v in [rcma1, rcma2, rcma3, rcma4]):
        return {"kst": None, "signal": None}

    kst_val = rcma1 * 1 + rcma2 * 2 + rcma3 * 3 + rcma4 * 4

    # 计算 KST 序列用于 Signal
    kst_series = []
    start = max(10 + 10, 15 + 10, 20 + 10, 30 + 15)
    for i in range(start, len(closes)):
        sub = closes[:i + 1]
        r1 = _rcma(sub, 10, 10) or 0
        r2 = _rcma(sub, 15, 10) or 0
        r3 = _rcma(sub, 20, 10) or 0
        r4 = _rcma(sub, 30, 15) or 0
        kst_series.append(r1 * 1 + r2 * 2 + r3 * 3 + r4 * 4)

    signal_val = sum(kst_series[-9:]) / 9 if len(kst_series) >= 9 else kst_val

    return {"kst": float(kst_val), "signal": float(signal_val)}


# ═══════════════════════════════════════════════════════════════
# 9F. Ichimoku / 一目均衡表
# ═══════════════════════════════════════════════════════════════

def calc_ichimoku(bars: list) -> dict:
    """Ichimoku Cloud (一目均衡表)
    返回: {"tenkan_sen": float, "kijun_sen": float, "senkou_a": float,
           "senkou_b": float, "chikou": float, "cloud_green": int,
           "above_cloud": int, "tk_cross": int}
    """
    if len(bars) < 53:
        return {"tenkan_sen": None, "kijun_sen": None,
                "senkou_a": None, "senkou_b": None, "chikou": None,
                "cloud_green": 0, "above_cloud": 0, "tk_cross": 0}

    # Tenkan-sen (转换线): (9日高 + 9日低) / 2
    tenkan = (max(b["high"] for b in bars[-9:]) + min(b["low"] for b in bars[-9:])) / 2

    # Kijun-sen (基准线): (26日高 + 26日低) / 2
    kijun = (max(b["high"] for b in bars[-26:]) + min(b["low"] for b in bars[-26:])) / 2

    # Senkou A (先行线A): (tenkan + kijun) / 2
    senkou_a = (tenkan + kijun) / 2

    # Senkou B (先行线B): (52日高 + 52日低) / 2
    senkou_b = (max(b["high"] for b in bars[-52:]) + min(b["low"] for b in bars[-52:])) / 2

    # Chikou (延迟线): 26根前的收盘价
    chikou = bars[-26]["close"] if len(bars) >= 26 else bars[-1]["close"]

    # 云层颜色: senkou_a > senkou_b = 绿色(多头)
    cloud_green = 1 if senkou_a > senkou_b else 0

    # 价格在云层上方/下方
    current_close = bars[-1]["close"]
    if current_close > max(senkou_a, senkou_b):
        above_cloud = 1
    elif current_close < min(senkou_a, senkou_b):
        above_cloud = -1
    else:
        above_cloud = 0

    # TK 交叉
    tk_cross = 0
    if len(bars) >= 27:
        prev_tenkan = (max(b["high"] for b in bars[-10:-1]) +
                       min(b["low"] for b in bars[-10:-1])) / 2
        prev_kijun = (max(b["high"] for b in bars[-27:-1]) +
                      min(b["low"] for b in bars[-27:-1])) / 2
        if prev_tenkan <= prev_kijun and tenkan > kijun:
            tk_cross = 1
        elif prev_tenkan >= prev_kijun and tenkan < kijun:
            tk_cross = -1

    return {
        "tenkan_sen": float(tenkan),
        "kijun_sen": float(kijun),
        "senkou_a": float(senkou_a),
        "senkou_b": float(senkou_b),
        "chikou": float(chikou),
        "cloud_green": cloud_green,
        "above_cloud": above_cloud,
        "tk_cross": tk_cross,
    }


# ═══════════════════════════════════════════════════════════════
# 9G. Parabolic SAR / 抛物线转向
# ═══════════════════════════════════════════════════════════════

def calc_psar(bars: list, accel: float = 0.02, max_accel: float = 0.2) -> dict:
    """Parabolic SAR (抛物线转向指标)
    返回: {"psar": float, "above_psar": int}
    """
    if len(bars) < 3:
        return {"psar": None, "above_psar": 0}

    # 初始方向判断
    if bars[1]["close"] > bars[0]["close"]:
        psar = bars[0]["low"]
        is_up = True
        ep = bars[0]["high"]
    else:
        psar = bars[0]["high"]
        is_up = False
        ep = bars[0]["low"]

    af = accel

    for i in range(1, len(bars)):
        prev_psar = psar
        prev_ep = ep

        if is_up:
            psar = prev_psar + af * (prev_ep - prev_psar)
            # PSAR 不能低于前两根的低点
            psar = min(psar, bars[i - 1]["low"])
            if i >= 2:
                psar = min(psar, bars[i - 2]["low"])
            # 反转检测
            if bars[i]["low"] < psar:
                is_up = False
                psar = prev_ep
                ep = bars[i]["low"]
                af = accel
            else:
                if bars[i]["high"] > ep:
                    ep = bars[i]["high"]
                    af = min(af + accel, max_accel)
        else:
            psar = prev_psar - af * (prev_psar - prev_ep)
            # PSAR 不能高于前两根的高点
            psar = max(psar, bars[i - 1]["high"])
            if i >= 2:
                psar = max(psar, bars[i - 2]["high"])
            # 反转检测
            if bars[i]["high"] > psar:
                is_up = True
                psar = prev_ep
                ep = bars[i]["high"]
                af = accel
            else:
                if bars[i]["low"] < ep:
                    ep = bars[i]["low"]
                    af = min(af + accel, max_accel)

    above_psar = 1 if bars[-1]["close"] > psar else 0
    return {"psar": float(psar), "above_psar": above_psar}


# ═══════════════════════════════════════════════════════════════
# 9H. Heikin Ashi / 平均足
# ═══════════════════════════════════════════════════════════════

def calc_heikin_ashi(bars: list) -> dict:
    """Heikin Ashi (平均足)
    返回: {"ha_open": float, "ha_close": float, "ha_high": float,
           "ha_low": float, "ha_bullish": int, "ha_trend_strength": float}
    """
    if len(bars) < 2:
        return {"ha_open": None, "ha_close": None, "ha_high": None,
                "ha_low": None, "ha_bullish": 0, "ha_trend_strength": 0.0}

    ha_opens = []
    ha_closes = []

    for i in range(len(bars)):
        b = bars[i]
        ha_close = (b["open"] + b["high"] + b["low"] + b["close"]) / 4

        if i == 0:
            ha_open = (b["open"] + b["close"]) / 2
        else:
            ha_open = (ha_opens[-1] + ha_closes[-1]) / 2

        ha_high = max(b["high"], ha_open, ha_close)
        ha_low = min(b["low"], ha_open, ha_close)

        ha_opens.append(ha_open)
        ha_closes.append(ha_close)

    curr_open = ha_opens[-1]
    curr_close = ha_closes[-1]

    # 重新计算最后 HA 的 high/low
    curr_high = max(bars[-1]["high"], curr_open, curr_close)
    curr_low = min(bars[-1]["low"], curr_open, curr_close)

    ha_bullish = 1 if curr_close > curr_open else 0

    body = abs(curr_close - curr_open)
    ha_range = curr_high - curr_low
    ha_trend_strength = body / ha_range if ha_range > 0 else 0.0

    return {
        "ha_open": float(curr_open),
        "ha_close": float(curr_close),
        "ha_high": float(curr_high),
        "ha_low": float(curr_low),
        "ha_bullish": ha_bullish,
        "ha_trend_strength": float(ha_trend_strength),
    }


# ═══════════════════════════════════════════════════════════════
# 9I. Keltner Channels / 肯特纳通道
# ═══════════════════════════════════════════════════════════════

def calc_keltner(bars: list, period: int = 20, mult: float = 1.5) -> dict:
    """Keltner Channels (肯特纳通道)
    Mid = EMA(period), Upper = Mid + mult * ATR(period), Lower = Mid - mult * ATR(period)
    返回: {"upper": float, "lower": float, "mid": float, "pos": float}
    """
    if len(bars) < period + 1:
        return {"upper": None, "lower": None, "mid": None, "pos": None}

    mid = calc_ema(bars, period)
    atr = calc_atr(bars, period)

    if mid is None or atr is None:
        return {"upper": None, "lower": None, "mid": None, "pos": None}

    upper = mid + mult * atr
    lower = mid - mult * atr
    close = bars[-1]["close"]
    pos = (close - lower) / (upper - lower) * 100 if upper != lower else 50.0

    return {"upper": float(upper), "lower": float(lower), "mid": float(mid), "pos": float(pos)}


# ═══════════════════════════════════════════════════════════════
# 9J. Donchian Channels / 唐奇安通道
# ═══════════════════════════════════════════════════════════════

def calc_donchian(bars: list, period: int = 20) -> dict:
    """Donchian Channels (唐奇安通道)
    返回: {"upper": float, "lower": float, "mid": float, "width_pct": float,
           "pos": float, "break_up": int, "break_down": int}
    """
    if len(bars) < period:
        return {"upper": None, "lower": None, "mid": None, "width_pct": None,
                "pos": None, "break_up": 0, "break_down": 0}

    upper = max(b["high"] for b in bars[-period:])
    lower = min(b["low"] for b in bars[-period:])
    mid = (upper + lower) / 2
    mid_safe = mid if mid > 0 else 1
    width_pct = (upper - lower) / mid_safe * 100
    close = bars[-1]["close"]
    pos = (close - lower) / (upper - lower) * 100 if upper != lower else 50.0

    # 突破检测
    break_up = 0
    break_down = 0
    if len(bars) >= period + 1:
        prev_upper = max(b["high"] for b in bars[-(period + 1):-1])
        prev_lower = min(b["low"] for b in bars[-(period + 1):-1])
        if close > prev_upper:
            break_up = 1
        if close < prev_lower:
            break_down = 1

    return {"upper": float(upper), "lower": float(lower), "mid": float(mid),
            "width_pct": float(width_pct), "pos": float(pos),
            "break_up": break_up, "break_down": break_down}


# ═══════════════════════════════════════════════════════════════
# 9K. Envelope / 包络线
# ═══════════════════════════════════════════════════════════════

def calc_envelope(bars: list, period: int = 20, pct: float = 2.0) -> dict:
    """Envelope (包络线): SMA ± SMA * pct/100
    返回: {"upper": float, "lower": float}
    """
    closes = _closes(bars)
    if len(closes) < period:
        return {"upper": None, "lower": None}

    sma = sum(closes[-period:]) / period
    offset = sma * pct / 100.0
    return {"upper": float(sma + offset), "lower": float(sma - offset)}


# ═══════════════════════════════════════════════════════════════
# 9L. VWAP / 成交量加权平均价
# ═══════════════════════════════════════════════════════════════

def calc_vwap(bars: list) -> Optional[float]:
    """VWAP: Volume Weighted Average Price (成交量加权平均价)
    用所有 bars 的典型价 * 成交量加权
    """
    if not bars:
        return None
    sum_pv = 0.0
    sum_v = 0.0
    for b in bars:
        vol = b.get("volume", b.get("tick_volume", 0))
        tp = (b["high"] + b["low"] + b["close"]) / 3.0
        sum_pv += tp * vol
        sum_v += vol
    return float(sum_pv / sum_v) if sum_v > 0 else None


# ═══════════════════════════════════════════════════════════════
# 9M. CMF / 蔡金资金流
# ═══════════════════════════════════════════════════════════════

def calc_cmf(bars: list, period: int = 20) -> Optional[float]:
    """CMF: Chaikin Money Flow (蔡金资金流)
    CMF = sum(MFV) / sum(volume)
    MFV = ((C-L)-(H-C))/(H-L) * V
    """
    if len(bars) < period:
        return None

    mfv_sum = 0.0
    vol_sum = 0.0
    for b in bars[-period:]:
        h, l, c = b["high"], b["low"], b["close"]
        vol = b.get("volume", b.get("tick_volume", 0))
        if h != l:
            mfv = ((c - l) - (h - c)) / (h - l) * vol
        else:
            mfv = 0.0
        mfv_sum += mfv
        vol_sum += vol

    return float(mfv_sum / vol_sum) if vol_sum > 0 else 0.0


# ═══════════════════════════════════════════════════════════════
# 9N. Force Index / 力指数
# ═══════════════════════════════════════════════════════════════

def calc_force_index(bars: list) -> Optional[float]:
    """Force Index (原始力指数): (close - prev_close) * volume"""
    if len(bars) < 2:
        return None
    vol = bars[-1].get("volume", bars[-1].get("tick_volume", 0))
    return float((bars[-1]["close"] - bars[-2]["close"]) * vol)


def calc_force_index_ema(bars: list) -> Optional[float]:
    """Force Index EMA(13): 力指数的13期指数移动平均"""
    if len(bars) < 15:
        return None

    # 计算 force index 序列
    fi_vals = []
    for i in range(1, len(bars)):
        vol = bars[i].get("volume", bars[i].get("tick_volume", 0))
        fi = (bars[i]["close"] - bars[i - 1]["close"]) * vol
        fi_vals.append(fi)

    # EMA(13)
    period = 13
    if len(fi_vals) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(fi_vals[:period]) / period
    for v in fi_vals[period:]:
        ema = v * k + ema * (1 - k)
    return float(ema)


# ═══════════════════════════════════════════════════════════════
# 9O. EOM / 简易波动指标
# ═══════════════════════════════════════════════════════════════

def calc_eom(bars: list) -> Optional[float]:
    """EOM: Ease of Movement (简易波动指标)
    EOM = ((H+L)/2 - (prev_H+prev_L)/2) / (volume / (H-L))
    """
    if len(bars) < 2:
        return None

    b = bars[-1]
    prev = bars[-2]
    mid = (b["high"] + b["low"]) / 2
    prev_mid = (prev["high"] + prev["low"]) / 2
    distance = mid - prev_mid
    ratio = b["high"] - b["low"]
    vol = b.get("volume", b.get("tick_volume", 0))

    if ratio == 0 or vol == 0:
        return 0.0
    return float(distance / (vol / ratio))


# ═══════════════════════════════════════════════════════════════
# 9P. NVI / 负量指标
# ═══════════════════════════════════════════════════════════════

def calc_nvi(bars: list, recent: int = 500) -> Optional[float]:
    """NVI: Negative Volume Index (负量指标)
    当成交量小于前一根时更新: NVI += (close - prev_close) / prev_close * NVI
    初始值 1000，只计算最近 recent 根 bar
    """
    if len(bars) < 2:
        return None

    start = max(0, len(bars) - recent)
    nvi = 1000.0
    for i in range(start + 1, len(bars)):
        vol = bars[i].get("volume", bars[i].get("tick_volume", 0))
        prev_vol = bars[i - 1].get("volume", bars[i - 1].get("tick_volume", 0))
        if vol < prev_vol:
            prev_close = bars[i - 1]["close"]
            if prev_close != 0:
                nvi *= (1 + (bars[i]["close"] - prev_close) / prev_close)
    return float(nvi)


# ═══════════════════════════════════════════════════════════════
# 9Q. PVI / 正量指标
# ═══════════════════════════════════════════════════════════════

def calc_pvi(bars: list, recent: int = 500) -> Optional[float]:
    """PVI: Positive Volume Index (正量指标)
    当成交量大于前一根时更新: PVI += (close - prev_close) / prev_close * PVI
    初始值 1000
    """
    if len(bars) < 2:
        return None

    start = max(0, len(bars) - recent)
    pvi = 1000.0
    for i in range(start + 1, len(bars)):
        vol = bars[i].get("volume", bars[i].get("tick_volume", 0))
        prev_vol = bars[i - 1].get("volume", bars[i - 1].get("tick_volume", 0))
        if vol > prev_vol:
            prev_close = bars[i - 1]["close"]
            if prev_close != 0:
                pvi *= (1 + (bars[i]["close"] - prev_close) / prev_close)
    return float(pvi)


# ═══════════════════════════════════════════════════════════════
# 9R. Klinger Oscillator / 克林格成交量振荡器
# ═══════════════════════════════════════════════════════════════

def calc_klinger(bars: list) -> dict:
    """Klinger Oscillator (克林格成交量振荡器)
    VF = volume * trend * (abs(close - prev_close) / (high - low)) * 100
    Klinger = EMA(34) of VF - EMA(55) of VF
    Signal = SMA(9) of Klinger
    返回: {"klinger": float, "signal": float}
    """
    if len(bars) < 56:
        return {"klinger": None, "signal": None}

    # 计算 Volume Force
    vf_vals = []
    for i in range(1, len(bars)):
        trend = 1 if bars[i]["close"] > bars[i - 1]["close"] else -1
        vol = bars[i].get("volume", bars[i].get("tick_volume", 0))
        dm = bars[i]["high"] - bars[i]["low"]
        if dm == 0:
            vf = 0.0
        else:
            vf = vol * trend * (abs(bars[i]["close"] - bars[i - 1]["close"]) / dm) * 100
        vf_vals.append(vf)

    if len(vf_vals) < 55:
        return {"klinger": None, "signal": None}

    # EMA(34) of VF
    k34 = 2 / 35.0
    ema34 = sum(vf_vals[:34]) / 34
    for v in vf_vals[34:]:
        ema34 = v * k34 + ema34 * (1 - k34)

    # EMA(55) of VF
    k55 = 2 / 56.0
    ema55 = sum(vf_vals[:55]) / 55
    for v in vf_vals[55:]:
        ema55 = v * k55 + ema55 * (1 - k55)

    klinger_val = ema34 - ema55

    # 计算 Klinger 序列用于 Signal (SMA 9)
    klinger_series = []
    for i in range(55, len(vf_vals)):
        sub = vf_vals[:i + 1]
        # 近似快速计算
        e34 = sum(sub[-34:]) / 34
        e55 = sum(sub[-55:]) / 55
        klinger_series.append(e34 - e55)

    signal_val = sum(klinger_series[-9:]) / 9 if len(klinger_series) >= 9 else klinger_val

    return {"klinger": float(klinger_val), "signal": float(signal_val)}


# ═══════════════════════════════════════════════════════════════
# 9S. AD Line / 累积/分配线
# ═══════════════════════════════════════════════════════════════

def calc_ad_line(bars: list) -> dict:
    """AD Line: Accumulation/Distribution Line (累积/分配线)
    MFV = ((C-L)-(H-C))/(H-L) * V
    AD = 累加 MFV
    返回: {"ad": float, "ma": float, "signal": int}
    """
    if len(bars) < 2:
        return {"ad": None, "ma": None, "signal": 0}

    ad = 0.0
    ad_values = []  # 用于计算 MA
    for i in range(len(bars)):
        b = bars[i]
        h, l, c = b["high"], b["low"], b["close"]
        vol = b.get("volume", b.get("tick_volume", 0))
        if h != l:
            mfv = ((c - l) - (h - c)) / (h - l) * vol
        else:
            mfv = 0.0
        ad += mfv
        ad_values.append(ad)

    current_ad = ad_values[-1]

    # MA of AD (20-period)
    if len(ad_values) >= 20:
        ad_ma = sum(ad_values[-20:]) / 20
    else:
        ad_ma = current_ad

    # Signal: AD above/below MA
    signal = 1 if current_ad > ad_ma else -1 if current_ad < ad_ma else 0

    return {"ad": float(current_ad), "ma": float(ad_ma), "signal": signal}


# ═══════════════════════════════════════════════════════════════
# 9T. VPT / 量价趋势
# ═══════════════════════════════════════════════════════════════

def calc_vpt(bars: list) -> Optional[float]:
    """VPT: Volume Price Trend (量价趋势)
    VPT = cumulative sum of volume * (close - prev_close) / prev_close
    """
    if len(bars) < 2:
        return None

    vpt = 0.0
    for i in range(1, len(bars)):
        pc = bars[i - 1]["close"]
        if pc == 0:
            continue
        vol = bars[i].get("volume", bars[i].get("tick_volume", 0))
        vpt += vol * (bars[i]["close"] - pc) / pc
    return float(vpt)


# ═══════════════════════════════════════════════════════════════
# 9U. Mass Index / 质量指数
# ═══════════════════════════════════════════════════════════════

def calc_mass_index(bars: list) -> Optional[float]:
    """Mass Index (质量指数): 测量价格反转
    EMA9 of (H-L) / EMA9 of EMA9 of (H-L), 25日求和
    """
    if len(bars) < 26:
        return None

    # 计算 (H-L) 值
    hl_vals = [b["high"] - b["low"] for b in bars]

    if len(hl_vals) < 9 + 25:
        return None

    # 9-day EMA of HL
    k9 = 2 / 10.0
    ema_vals = []
    ema = sum(hl_vals[:9]) / 9
    ema_vals.append(ema)
    for v in hl_vals[9:]:
        ema = v * k9 + ema * (1 - k9)
        ema_vals.append(ema)

    # 9-day EMA of ema_vals (double smooth)
    if len(ema_vals) < 9:
        return None
    dema_vals = []
    dema = sum(ema_vals[:9]) / 9
    dema_vals.append(dema)
    for v in ema_vals[9:]:
        dema = v * k9 + dema * (1 - k9)
        dema_vals.append(dema)

    # Ratio: ema_vals[i] / dema_vals[i]
    ratios = []
    for i in range(min(len(ema_vals), len(dema_vals))):
        if dema_vals[i] != 0:
            ratios.append(ema_vals[i] / dema_vals[i])
        else:
            ratios.append(1.0)

    # Mass Index = sum of last 25 ratios
    if len(ratios) < 25:
        return None

    mass = sum(ratios[-25:])
    return float(mass)


# ═══════════════════════════════════════════════════════════════
# 9V. DPO / 去趋势价格振荡器
# ═══════════════════════════════════════════════════════════════

def calc_dpo(bars: list, period: int = 20) -> Optional[float]:
    """DPO: Detrended Price Oscillator (去趋势价格振荡器)
    DPO = close - SMA(period/2+1) shifted back by period/2+1
    """
    closes = _closes(bars)
    shift = period // 2 + 1
    if len(closes) < period + shift:
        return None

    # SMA of period
    sma_vals = []
    for i in range(period, len(closes) + 1):
        sma_vals.append(sum(closes[i - period:i]) / period)

    # DPO = close - sma shifted
    idx = len(closes) - 1
    sma_idx = idx - period + 1 - shift  # sma_vals 中的索引
    if sma_idx < 0 or sma_idx >= len(sma_vals):
        return None

    return float(closes[-1] - sma_vals[sma_idx])


# ═══════════════════════════════════════════════════════════════
# 9W. Z-Score / Z分数
# ═══════════════════════════════════════════════════════════════

def calc_zscore(bars: list, period: int = 20) -> Optional[float]:
    """Z-Score: (当前收盘价 - 均值) / 标准差"""
    closes = _closes(bars)
    if len(closes) < period:
        return None

    recent = closes[-period:]
    mean = sum(recent) / period
    variance = sum((c - mean) ** 2 for c in recent) / period
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return float((closes[-1] - mean) / std)


# ═══════════════════════════════════════════════════════════════
# 9X. Volatility / 波动率
# ═══════════════════════════════════════════════════════════════

def calc_volatility(bars: list, period: int = 20) -> Optional[float]:
    """Volatility: 收益率的标准差（日收益率波动率）"""
    closes = _closes(bars)
    if len(closes) < period + 1:
        return None

    # 计算日收益率
    returns = []
    for i in range(1, period + 1):
        pc = closes[-i - 1]
        if pc != 0:
            returns.append((closes[-i] - pc) / pc)
        else:
            returns.append(0.0)

    mean_r = sum(returns) / period
    variance = sum((r - mean_r) ** 2 for r in returns) / period
    return float(math.sqrt(variance))


def calc_volatility_ratio(bars: list, short: int = 20, long: int = 100) -> Optional[float]:
    """Volatility Ratio: 短期波动率 / 长期波动率"""
    short_v = calc_volatility(bars, short)
    long_v = calc_volatility(bars, long)
    if short_v is None or long_v is None or long_v == 0:
        return None
    return float(short_v / long_v)


# ═══════════════════════════════════════════════════════════════
# 9Y. 统计指标: 偏度/峰度/上涨比例/自相关
# ═══════════════════════════════════════════════════════════════

def calc_return_skew(bars: list, period: int = 20) -> Optional[float]:
    """Return Skewness: 收益率的偏度（三阶矩）"""
    closes = _closes(bars)
    if len(closes) < period + 1:
        return None

    returns = []
    for i in range(1, period + 1):
        pc = closes[-i - 1]
        returns.append((closes[-i] - pc) / pc if pc != 0 else 0.0)

    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    if variance == 0:
        return 0.0
    std = math.sqrt(variance)
    m3 = sum((r - mean_r) ** 3 for r in returns) / n
    return float(m3 / (std ** 3))


def calc_return_kurt(bars: list, period: int = 20) -> Optional[float]:
    """Return Kurtosis: 收益率的峰度（四阶矩），超额峰度（-3）"""
    closes = _closes(bars)
    if len(closes) < period + 1:
        return None

    returns = []
    for i in range(1, period + 1):
        pc = closes[-i - 1]
        returns.append((closes[-i] - pc) / pc if pc != 0 else 0.0)

    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    if variance == 0:
        return -3.0  # 超额峰度基准
    std = math.sqrt(variance)
    m4 = sum((r - mean_r) ** 4 for r in returns) / n
    return float(m4 / (std ** 4) - 3.0)  # 超额峰度


def calc_up_ratio(bars: list, period: int = 20) -> Optional[float]:
    """Up Ratio: 上涨天数占比（阳线比例）"""
    if len(bars) < period:
        return None
    up_count = sum(1 for b in bars[-period:] if b["close"] > b["open"])
    return float(up_count / period)


def calc_autocorr(bars: list, period: int = 20, lag: int = 1) -> Optional[float]:
    """Autocorrelation: 收盘价的自相关系数（给定 lag）"""
    closes = _closes(bars)
    if len(closes) < period + lag + 1:
        return None

    vals = closes[-(period + lag):]
    x = vals[:-lag]  # 前部分
    y = vals[lag:]   # 后部分

    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    var_x = sum((v - mean_x) ** 2 for v in x)
    var_y = sum((v - mean_y) ** 2 for v in y)

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return 0.0
    return float(cov / denom)


# ═══════════════════════════════════════════════════════════════
# 9Z. K线形态 (Candlestick Patterns)
# ═══════════════════════════════════════════════════════════════

def detect_gravestone_doji(bars: list) -> dict:
    """墓碑十字星: 上影线长，无下影线，实体极小
    返回: {"grave": int}  1=是 0=否
    """
    if not bars:
        return {"grave": 0}
    b = bars[-1]
    body = abs(b["close"] - b["open"])
    upper = b["high"] - max(b["open"], b["close"])
    lower = min(b["open"], b["close"]) - b["low"]
    total = b["high"] - b["low"]
    if total == 0:
        return {"grave": 0}
    body_ratio = body / total
    is_grave = upper > lower * 3 and lower <= body and body_ratio < 0.15
    return {"grave": 1 if is_grave else 0}


def detect_dragonfly_doji(bars: list) -> dict:
    """蜻蜓十字星: 下影线长，无上影线，实体极小
    返回: {"dragon": int}  1=是 0=否
    """
    if not bars:
        return {"dragon": 0}
    b = bars[-1]
    body = abs(b["close"] - b["open"])
    upper = b["high"] - max(b["open"], b["close"])
    lower = min(b["open"], b["close"]) - b["low"]
    total = b["high"] - b["low"]
    if total == 0:
        return {"dragon": 0}
    body_ratio = body / total
    is_dragon = lower > upper * 3 and upper <= body and body_ratio < 0.15
    return {"dragon": 1 if is_dragon else 0}


def detect_long_legged_doji(bars: list) -> int:
    """长腿十字星: 上下影线都很长，实体极小
    返回: 1=是 0=否
    """
    if not bars:
        return 0
    b = bars[-1]
    body = abs(b["close"] - b["open"])
    upper = b["high"] - max(b["open"], b["close"])
    lower = min(b["open"], b["close"]) - b["low"]
    total = b["high"] - b["low"]
    if total == 0:
        return 0
    body_ratio = body / total
    # 上下影线都长，实体极小
    is_long = body_ratio < 0.1 and upper > body * 2 and lower > body * 2
    return 1 if is_long else 0


def detect_spinning_top(bars: list) -> int:
    """纺锤线: 实体小，上下影线等长
    返回: 1=是 0=否
    """
    if not bars:
        return 0
    b = bars[-1]
    body = abs(b["close"] - b["open"])
    upper = b["high"] - max(b["open"], b["close"])
    lower = min(b["open"], b["close"]) - b["low"]
    total = b["high"] - b["low"]
    if total == 0:
        return 0
    body_ratio = body / total
    is_spinning = 0.1 <= body_ratio <= 0.35 and abs(upper - lower) / total < 0.3
    return 1 if is_spinning else 0


def detect_hanging_man(bars: list) -> int:
    """吊人线: 下影线长，实体小，出现在上涨后
    返回: 1=是 0=否
    """
    if len(bars) < 3:
        return 0
    b = bars[-1]
    prev_bull = bars[-2]["close"] > bars[-2]["open"]
    body = abs(b["close"] - b["open"])
    lower = min(b["open"], b["close"]) - b["low"]
    upper = b["high"] - max(b["open"], b["close"])
    total = b["high"] - b["low"]
    if total == 0:
        return 0
    body_ratio = body / total
    is_hanging = prev_bull and body_ratio < 0.3 and lower >= body * 2 and upper <= body * 0.5
    return 1 if is_hanging else 0


def detect_shooting_star(bars: list) -> int:
    """射击之星: 上影线长，实体小，出现在上涨后
    返回: 1=是 0=否
    """
    if len(bars) < 3:
        return 0
    b = bars[-1]
    prev_bull = bars[-2]["close"] > bars[-2]["open"]
    body = abs(b["close"] - b["open"])
    upper = b["high"] - max(b["open"], b["close"])
    lower = min(b["open"], b["close"]) - b["low"]
    total = b["high"] - b["low"]
    if total == 0:
        return 0
    body_ratio = body / total
    is_star = prev_bull and body_ratio < 0.3 and upper >= body * 2 and lower <= body * 0.5
    return 1 if is_star else 0


def detect_harami(bars: list) -> dict:
    """孕育线 (Harami): 小实体被大实体包含
    返回: {"bull": int, "bear": int}
    """
    if len(bars) < 2:
        return {"bull": 0, "bear": 0}
    curr, prev = bars[-1], bars[-2]
    prev_body = abs(prev["close"] - prev["open"])
    curr_body = abs(curr["close"] - curr["open"])
    if prev_body == 0:
        return {"bull": 0, "bear": 0}

    # 前一根实体大，当前实体小，且当前实体完全在前一根实体内
    bull = (prev["close"] > prev["open"] and  # 前一根阳线
            curr_body < prev_body * 0.6 and
            curr["close"] < prev["close"] and curr["open"] > prev["open"])

    bear = (prev["close"] < prev["open"] and  # 前一根阴线
            curr_body < prev_body * 0.6 and
            curr["close"] > prev["close"] and curr["open"] < prev["open"])

    return {"bull": 1 if bull else 0, "bear": 1 if bear else 0}


def detect_outside_bar(bars: list) -> int:
    """Outside Bar (外部线/吞没线): 当前 bar 的高低点完全覆盖前一根
    与 engulfing 不同，这里只看高低点范围
    返回: 1=是 0=否
    """
    if len(bars) < 2:
        return 0
    curr, prev = bars[-1], bars[-2]
    return 1 if curr["high"] > prev["high"] and curr["low"] < prev["low"] else 0


def detect_marubozu(bars: list) -> dict:
    """光头光脚线 (Marubozu): 无影线或极短，实体大
    返回: {"bull": int, "bear": int}
    """
    if not bars:
        return {"bull": 0, "bear": 0}
    b = bars[-1]
    body = abs(b["close"] - b["open"])
    upper = b["high"] - max(b["open"], b["close"])
    lower = min(b["open"], b["close"]) - b["low"]
    total = b["high"] - b["low"]
    if total == 0:
        return {"bull": 0, "bear": 0}

    body_ratio = body / total
    shadow_ratio = (upper + lower) / total

    bull = body_ratio > 0.85 and shadow_ratio < 0.05 and b["close"] > b["open"]
    bear = body_ratio > 0.85 and shadow_ratio < 0.05 and b["close"] < b["open"]

    return {"bull": 1 if bull else 0, "bear": 1 if bear else 0}


def detect_piercing(bars: list) -> int:
    """刺透形态 (Piercing Line): 下降趋势中，阴线后阳线收盘>前阴线中点
    返回: 1=是 0=否
    """
    if len(bars) < 2:
        return 0
    curr, prev = bars[-1], bars[-2]
    # 前一根阴线，当前阳线
    if prev["close"] >= prev["open"] or curr["close"] <= curr["open"]:
        return 0
    prev_body = prev["open"] - prev["close"]  # 阴线实体长度
    midpoint = prev["close"] + prev_body / 2  # 阴线中点
    if curr["close"] > midpoint and curr["open"] < prev["close"]:
        return 1
    return 0


def detect_dark_cloud(bars: list) -> int:
    """乌云盖顶 (Dark Cloud Cover): 上升趋势中，阳线后阴线收盘<前阳线中点
    返回: 1=是 0=否
    """
    if len(bars) < 2:
        return 0
    curr, prev = bars[-1], bars[-2]
    # 前一根阳线，当前阴线
    if prev["close"] <= prev["open"] or curr["close"] >= curr["open"]:
        return 0
    prev_body = prev["close"] - prev["open"]  # 阳线实体长度
    midpoint = prev["open"] + prev_body / 2  # 阳线中点
    if curr["close"] < midpoint and curr["open"] > prev["close"]:
        return 1
    return 0


def detect_three_morning_star(bars: list) -> int:
    """晨星 (Morning Star): 长阴 + 小实体(星) + 长阳，底部反转
    返回: 1=是 0=否
    """
    if len(bars) < 3:
        return 0
    b1, b2, b3 = bars[-3], bars[-2], bars[-1]
    # b1: 长阴, b2: 小实体, b3: 长阳
    body1 = abs(b1["close"] - b1["open"])
    body2 = abs(b2["close"] - b2["open"])
    body3 = abs(b3["close"] - b3["open"])
    range1 = b1["high"] - b1["low"]
    if range1 == 0 or body1 == 0:
        return 0
    is_star = (b1["close"] < b1["open"] and  # 阴线
               body2 < body1 * 0.4 and  # 星线实体小
               b2["close"] < b1["close"] and  # 星线在阴线下方
               b3["close"] > b3["open"] and  # 阳线
               b3["close"] > (b1["open"] + b1["close"]) / 2)  # 阳线收在阴线中点上方
    return 1 if is_star else 0


def detect_three_evening_star(bars: list) -> int:
    """暮星 (Evening Star): 长阳 + 小实体(星) + 长阴，顶部反转
    返回: 1=是 0=否
    """
    if len(bars) < 3:
        return 0
    b1, b2, b3 = bars[-3], bars[-2], bars[-1]
    body1 = abs(b1["close"] - b1["open"])
    body2 = abs(b2["close"] - b2["open"])
    body3 = abs(b3["close"] - b3["open"])
    range1 = b1["high"] - b1["low"]
    if range1 == 0 or body1 == 0:
        return 0
    is_star = (b1["close"] > b1["open"] and  # 阳线
               body2 < body1 * 0.4 and  # 星线实体小
               b2["close"] > b1["close"] and  # 星线在阳线上方
               b3["close"] < b3["open"] and  # 阴线
               b3["close"] < (b1["open"] + b1["close"]) / 2)  # 阴线收在阳线中点下方
    return 1 if is_star else 0


# ═══════════════════════════════════════════════════════════════
# 9ZA. Market Regime / 市场状态检测
# ═══════════════════════════════════════════════════════════════

def calc_market_regime(bars: list) -> dict:
    """Market Regime (市场状态): 基于均线斜率和ADX判断
    返回: {"regime": str (bull/bear/sideways), "strength": int (0-100)}
    """
    if len(bars) < 50:
        return {"regime": "sideways", "strength": 0}

    closes = _closes(bars)

    # 计算 MA(20) 和 MA(50) 的斜率
    ma20 = calc_sma(closes, 20)
    ma50 = calc_sma(closes, 50)

    if ma20 is None or ma50 is None:
        return {"regime": "sideways", "strength": 0}

    # 更早的 MA 值用于计算斜率
    ma20_prev = calc_sma(closes[:-5], 20) if len(closes) > 25 else ma20
    ma50_prev = calc_sma(closes[:-5], 50) if len(closes) > 55 else ma50

    slope20 = (ma20 - (ma20_prev or ma20)) / (ma20_prev or ma20) * 100
    slope50 = (ma50 - (ma50_prev or ma50)) / (ma50_prev or ma50) * 100

    # 价格相对 MA 的位置
    price = closes[-1]
    above_ma20 = price > ma20
    above_ma50 = price > ma50

    # ADX 用于判断趋势强度
    adx_data = calc_adx(bars)
    adx_val = adx_data.get("adx", 0) or 0

    # 判断
    if above_ma20 and above_ma50 and slope20 > 0 and slope50 > 0:
        regime = "bull"
        strength = min(100, int(adx_val * 2 + 10))
    elif not above_ma20 and not above_ma50 and slope20 < 0 and slope50 < 0:
        regime = "bear"
        strength = min(100, int(adx_val * 2 + 10))
    else:
        regime = "sideways"
        strength = max(0, min(100, int(100 - adx_val * 2)))

    return {"regime": regime, "strength": int(strength)}


# ═══════════════════════════════════════════════════════════════
# 9ZB. Fibonacci Retracement / 斐波那契回调
# ═══════════════════════════════════════════════════════════════

def calc_fib_retracement(bars: list, period: int = 100) -> dict:
    """Fibonacci Retracement (斐波那契回调): 判断价格在回调位的位置
    返回: {"level_236": int, "level_382": int, "level_500": int,
           "level_618": int, "level_786": int}
    每个 level 返回 -1(低于该位), 0(接近), 1(高于该位)
    """
    if len(bars) < period:
        return {"level_236": 0, "level_382": 0, "level_500": 0, "level_618": 0, "level_786": 0}

    recent = bars[-period:]
    high = max(b["high"] for b in recent)
    low = min(b["low"] for b in recent)
    close = bars[-1]["close"]

    diff = high - low
    if diff == 0:
        return {"level_236": 0, "level_382": 0, "level_500": 0, "level_618": 0, "level_786": 0}

    levels = {
        "236": high - 0.236 * diff,
        "382": high - 0.382 * diff,
        "500": high - 0.5 * diff,
        "618": high - 0.618 * diff,
        "786": high - 0.786 * diff,
    }

    # 判断每个 level -1/0/1
    result = {}
    for name, level_val in levels.items():
        # level ±0.5% 范围视为"接近"
        band = diff * 0.01  # 1% of range
        if close > level_val + band:
            result[f"level_{name}"] = 1
        elif close < level_val - band:
            result[f"level_{name}"] = -1
        else:
            result[f"level_{name}"] = 0

    return result


# ═══════════════════════════════════════════════════════════════
# 8. 全量计算（研究级）
# ═══════════════════════════════════════════════════════════════

def compute_all_trading_indicators(bars: list) -> dict:
    """
    计算所有实时交易常用的指标（约 50+ 个值）。
    被 tick_engine.py 调用，在新 bar 形成时执行。

    参数:
      bars: list of dict [{time, open, high, low, close, volume}, ...]

    返回:
      dict: {indicator_name: value, ...}
    """
    if not bars:
        return {}
    ind = {}
    latest = bars[-1]
    closes = _closes(bars)
    current_close = latest["close"]
    utc_hour = int(latest.get("utc_hour", 0))
    if not utc_hour and "time" in latest:
        from datetime import timezone
        t = latest["time"]
        if isinstance(t, (int, float)):
            utc_hour = datetime.fromtimestamp(t, tz=timezone.utc).hour
        elif hasattr(t, "hour"):
            # pandas Timestamp / datetime 对象
            utc_hour = t.hour
        else:
            utc_hour = 0

    # ── 价格衍生 ──
    ind["price"] = current_close
    ind["high"] = latest["high"]
    ind["low"] = latest["low"]
    ind["open"] = latest["open"]
    ind["range"] = latest["high"] - latest["low"]
    ind["range_pct"] = (latest["high"] - latest["low"]) / latest["open"] * 100 if latest["open"] > 0 else 0
    body = abs(latest["close"] - latest["open"])
    ind["body"] = body
    ind["body_pct"] = body / (latest["high"] - latest["low"]) * 100 if (latest["high"] - latest["low"]) > 0 else 0

    # ── Session ──
    ind["session"] = get_session(utc_hour)
    ind["utc_hour"] = utc_hour

    # ── 动量 ──
    for p in [7, 14, 21, 50]:
        v = calc_rsi(bars, p)
        if v is not None:
            ind[f"rsi{p}"] = v
    ind["rsi_oversold"] = 1 if ind.get("rsi14") is not None and ind["rsi14"] < 30 else 0
    ind["rsi_overbought"] = 1 if ind.get("rsi14") is not None and ind["rsi14"] > 70 else 0

    # Stochastic
    stoch = calc_stochastic(bars)
    ind.update({f"stoch_k_{k}": v for k, v in stoch.items()})

    # Williams %R
    for p in [10, 14, 21]:
        v = calc_williams_r(bars, p)
        if v is not None:
            ind[f"williams_r_{p}"] = v

    # CCI
    for p in [10, 14, 20]:
        v = calc_cci(bars, p)
        if v is not None:
            ind[f"cci_{p}"] = v

    # Momentum / ROC
    for p in [5, 10, 20]:
        v = calc_momentum(bars, p)
        if v is not None:
            ind[f"mom_{p}"] = v
        v = calc_roc(bars, p)
        if v is not None:
            ind[f"roc_{p}"] = v

    # ── 趋势 ──
    # MA
    for p in [5, 10, 20, 30, 50, 100, 200]:
        v = calc_sma(closes, p)
        if v is not None:
            ind[f"ma{p}"] = v
            ind[f"ma{p}_slope"] = (closes[-1] - v) / v * 100

    # EMA
    for p in [5, 8, 12, 13, 20, 21, 26, 34, 50, 55, 89, 144, 200]:
        v = calc_ema(bars, p)
        if v is not None:
            ind[f"ema{p}"] = v

    # MA cross signals
    for pair in [(5, 20), (10, 30), (20, 50), (50, 200)]:
        ma1 = calc_sma(closes, pair[0])
        ma2 = calc_sma(closes, pair[1])
        if ma1 is not None and ma2 is not None:
            ind[f"ma{pair[0]}_above_ma{pair[1]}"] = 1 if ma1 > ma2 else 0

    # MACD
    macd = calc_macd(bars)
    ind.update({f"macd_{k}": v for k, v in macd.items()})
    if macd["macd"] is not None and macd["signal"] is not None:
        ind["macd_cross"] = 1 if macd["macd"] > macd["signal"] else -1 if macd["macd"] < macd["signal"] else 0

    # ADX
    adx = calc_adx(bars)
    ind.update({f"adx_{k}": v for k, v in adx.items()})
    if adx["adx"] is not None:
        ind["adx_trending"] = 1 if adx["adx"] > 25 else 0

    # Aroon
    aroon = calc_aroon(bars)
    ind.update({f"aroon_{k}": v for k, v in aroon.items()})
    if aroon["up"] is not None and aroon["down"] is not None:
        ind["aroon_uptrend"] = 1 if aroon["up"] > 70 and aroon["down"] < 30 else 0
        ind["aroon_downtrend"] = 1 if aroon["down"] > 70 and aroon["up"] < 30 else 0

    # Close vs MA
    for p in [20, 50, 100, 200]:
        ma_v = calc_sma(closes, p)
        if ma_v is not None and ma_v > 0:
            ind[f"close_vs_ma{p}"] = (current_close - ma_v) / ma_v * 100

    # ── 波动率 ──
    for p in [5, 7, 10, 14, 21, 50]:
        v = calc_atr(bars, p)
        if v is not None:
            ind[f"atr{p}"] = v
            if current_close > 0:
                ind[f"atr{p}_pct"] = v / current_close * 100

    # ATR percentile
    atr14 = ind.get("atr14")
    if atr14 is not None:
        # 用最近 50 根的 ATR 排百分位
        atr_series = []
        for i in range(min(50, len(bars) - 14)):
            sub = bars[-(i + 15):len(bars) - i]
            if len(sub) >= 15:
                atr_series.append(calc_atr(sub, 14) or 0)
        if atr_series:
            rank = sum(1 for a in atr_series if a < atr14) / len(atr_series)
            ind["atr14_percentile"] = rank
            ind["atr14_high"] = 1 if rank > 0.8 else 0
            ind["atr14_low"] = 1 if rank < 0.2 else 0

    # Bollinger Bands
    for p, std in [(20, 2), (20, 3), (50, 2), (10, 1.5)]:
        bb = calc_bollinger_bands(bars, p, std)
        if bb["upper"] is not None:
            sfx = f"{p}_{int(std)}"
            for k, v in bb.items():
                if v is not None:
                    ind[f"bb_{sfx}_{k}"] = v

    # Choppiness
    for p in [14, 30, 50]:
        v = calc_choppiness(bars, p)
        if v is not None:
            ind[f"chop_{p}"] = v
            ind[f"chop_{p}_trending"] = 1 if v < 30 else 0
            ind[f"chop_{p}_choppy"] = 1 if v > 60 else 0

    # ── 成交量 ──
    volume = latest.get("volume", latest.get("tick_volume", 0))
    ind["volume"] = volume
    for p in [5, 10, 20]:
        v = calc_volume_ratio(bars, p)
        if v is not None:
            ind[f"volume_ratio_{p}"] = v
            ind[f"volume_spike_{p}"] = 1 if v > 1.5 else 0

    # OBV
    obv = calc_obv(bars)
    if obv is not None:
        ind["obv"] = obv

    # MFI
    for p in [9, 14, 21]:
        v = calc_mfi(bars, p)
        if v is not None:
            ind[f"mfi_{p}"] = v

    # ── 价格行为 ──
    ind["consecutive_bear"] = detected_consecutive_bears(bars)
    ind["consecutive_bull"] = detected_consecutive_bulls(bars)

    # K线形态
    ind["doji"] = 1 if detect_doji(bars) else 0
    eng = detect_engulfing(bars)
    ind["bull_engulfing"] = 1 if eng["bull"] else 0
    ind["bear_engulfing"] = 1 if eng["bear"] else 0
    ind["inside_bar"] = 1 if detect_inside_bar(bars) else 0
    pin = detect_pin_bar(bars)
    ind["pin_bar_bull"] = 1 if pin["bull"] else 0
    ind["pin_bar_bear"] = 1 if pin["bear"] else 0
    ind["hammer"] = 1 if detect_hammer(bars) else 0

    # ── 结构 ──
    for p in [5, 10, 20, 50]:
        hh = calc_highest_high(bars, p)
        ll = calc_lowest_low(bars, p)
        if hh is not None:
            ind[f"hh_{p}"] = hh
            ind[f"hh_{p}_breakout"] = 1 if current_close > hh else 0
        if ll is not None:
            ind[f"ll_{p}"] = ll
            ind[f"ll_{p}_breakout"] = 1 if current_close < ll else 0

    # 支撑/阻力
    for p in [10, 20, 50]:
        sr = calc_support_resistance(bars, p)
        if sr["support"] is not None:
            ind[f"support_{p}"] = sr["support"]
            ind[f"resistance_{p}"] = sr["resistance"]
            ind[f"near_support_{p}"] = sr["near_support_pct"]
            ind[f"near_resistance_{p}"] = sr["near_resistance_pct"]

    # Pivot Points
    for p in [1]:
        pp = calc_pivot_points(bars, p)
        if pp["pivot"] is not None:
            for k, v in pp.items():
                ind[f"pp_{p}_{k}"] = v
            ind[f"pp_{p}_above_pivot"] = 1 if current_close > pp["pivot"] else 0

    # ── 新指标: Guppy MMA ──
    guppy_short = calc_guppy_short_spread(bars)
    if guppy_short is not None:
        ind["guppy_short_spread"] = guppy_short
    guppy_long = calc_guppy_long_spread(bars)
    if guppy_long is not None:
        ind["guppy_long_spread"] = guppy_long

    # ── 新指标: TRIX ──
    trix = calc_trix(bars)
    if trix and trix.get("trix") is not None:
        for k, v in trix.items():
            ind[f"trix_{k}"] = v

    # ── 新指标: Ultimate Oscillator ──
    uo = calc_ultimate_oscillator(bars)
    if uo is not None:
        ind["ultimate_osc"] = uo

    # ── 新指标: RVGI ──
    rvgi = calc_rvgi(bars)
    if rvgi and rvgi.get("rvg") is not None:
        ind.update({f"rvgi_{k}": v for k, v in rvgi.items()})

    # ── 新指标: KST ──
    kst = calc_kst(bars)
    if kst and kst.get("kst") is not None:
        ind.update({f"kst_{k}": v for k, v in kst.items()})

    # ── 新指标: Ichimoku ──
    ichimoku = calc_ichimoku(bars)
    if ichimoku and ichimoku.get("tenkan_sen") is not None:
        ind.update({f"ichi_{k}": v for k, v in ichimoku.items()})

    # ── 新指标: Parabolic SAR ──
    psar = calc_psar(bars)
    if psar and psar.get("psar") is not None:
        ind.update({f"psar_{k}": v for k, v in psar.items()})

    # ── 新指标: Heikin Ashi ──
    ha = calc_heikin_ashi(bars)
    if ha and ha.get("ha_close") is not None:
        for k, v in ha.items():
            ind[k] = v  # keys already have "ha_" prefix

    # ── 新指标: Keltner Channels ──
    for mult in [1.0, 1.5, 2.0]:
        kc = calc_keltner(bars, 20, mult)
        if kc and kc.get("upper") is not None:
            for k, v in kc.items():
                ind[f"kc_{mult}_{k}"] = v

    # ── 新指标: Donchian Channels ──
    for p in [10, 20, 50]:
        dc = calc_donchian(bars, p)
        if dc and dc.get("upper") is not None:
            for k, v in dc.items():
                ind[f"dc_{p}_{k}"] = v

    # ── 新指标: Envelopes ──
    for pct in [1, 2, 3, 5]:
        env = calc_envelope(bars, 20, pct)
        if env and env.get("upper") is not None:
            for k, v in env.items():
                ind[f"envelope_{pct}_{k}"] = v

    # ── 新指标: VWAP ──
    vwap = calc_vwap(bars)
    if vwap is not None:
        ind["vwap"] = vwap
        if current_close > 0:
            ind["vwap_pos"] = (current_close - vwap) / vwap * 100
            ind["above_vwap"] = 1 if current_close > vwap else 0

    # ── 新指标: CMF (多周期) ──
    for p in [10, 20, 50]:
        cmf = calc_cmf(bars, p)
        if cmf is not None:
            ind[f"cmf_{p}"] = cmf
    ind["cmf_bullish"] = 1 if ind.get("cmf_20") is not None and ind["cmf_20"] > 0 else 0

    # ── 新指标: Force Index ──
    fi = calc_force_index(bars)
    if fi is not None:
        ind["force_index"] = fi
    fie = calc_force_index_ema(bars)
    if fie is not None:
        ind["force_index_ema"] = fie
        ind["force_index_signal"] = 1 if fie > 0 else 0

    # ── 新指标: Ease of Movement ──
    eom = calc_eom(bars)
    if eom is not None:
        ind["eom"] = eom

    # ── 新指标: NVI / PVI ──
    nvi_v = calc_nvi(bars)
    pvi_v = calc_pvi(bars)
    if nvi_v is not None:
        ind["nvi"] = nvi_v
    if pvi_v is not None:
        ind["pvi"] = pvi_v

    # ── 新指标: Klinger ──
    klinger = calc_klinger(bars)
    if klinger and klinger.get("klinger") is not None:
        ind.update({f"klinger_{k}": v for k, v in klinger.items()})

    # ── 新指标: AD Line ──
    ad = calc_ad_line(bars)
    if ad and ad.get("ad") is not None:
        ind.update({f"ad_{k}": v for k, v in ad.items()})

    # ── 新指标: VPT ──
    vpt = calc_vpt(bars)
    if vpt is not None:
        ind["vpt"] = vpt

    # ── 新指标: Mass Index ──
    mi = calc_mass_index(bars)
    if mi is not None:
        ind["mass_index"] = mi

    # ── 新指标: DPO ──
    for p in [10, 20, 50]:
        dpo = calc_dpo(bars, p)
        if dpo is not None:
            ind[f"dpo_{p}"] = dpo

    # ── 新指标: Z-Score ──
    for p in [10, 20, 50, 100, 200]:
        z = calc_zscore(bars, p)
        if z is not None:
            ind[f"zscore_{p}"] = z
            ind[f"zscore_extreme_{p}"] = 1 if abs(z) > 2 else 0

    # ── 新指标: Volatility ──
    for p in [5, 10, 20, 50, 100]:
        v = calc_volatility(bars, p)
        if v is not None:
            ind[f"volatility_{p}"] = v
    vr = calc_volatility_ratio(bars)
    if vr is not None:
        ind["volatility_ratio_20_100"] = vr
        ind["high_volatility"] = 1 if vr > 1.5 else 0

    # ── 新指标: 统计 ──
    for p in [5, 10, 20, 50]:
        sk = calc_return_skew(bars, p)
        if sk is not None:
            ind[f"return_skew_{p}"] = sk
        ku = calc_return_kurt(bars, p)
        if ku is not None:
            ind[f"return_kurt_{p}"] = ku
    for p in [10, 20, 50]:
        ur = calc_up_ratio(bars, p)
        if ur is not None:
            ind[f"up_ratio_{p}"] = ur
    for lag in [1, 2, 3, 5]:
        ac = calc_autocorr(bars, 20, lag)
        if ac is not None:
            ind[f"autocorr_{lag}"] = ac

    # ── 新指标: 更多K线形态 ──
    ind["long_legged_doji"] = detect_long_legged_doji(bars)
    gd = detect_gravestone_doji(bars)
    ind["gravestone_doji"] = gd.get("grave", 0) if gd else 0
    dd = detect_dragonfly_doji(bars)
    ind["dragonfly_doji"] = dd.get("dragon", 0) if dd else 0
    ind["spinning_top"] = detect_spinning_top(bars)
    ind["hanging_man"] = detect_hanging_man(bars)
    ind["shooting_star"] = detect_shooting_star(bars)
    hr = detect_harami(bars)
    ind["bull_harami"] = hr.get("bull", 0) if hr else 0
    ind["bear_harami"] = hr.get("bear", 0) if hr else 0
    ind["outside_bar"] = detect_outside_bar(bars)
    mr = detect_marubozu(bars)
    ind["marubozu_bull"] = mr.get("bull", 0) if mr else 0
    ind["marubozu_bear"] = mr.get("bear", 0) if mr else 0
    ind["piercing"] = detect_piercing(bars)
    ind["dark_cloud"] = detect_dark_cloud(bars)
    ind["three_morning_star"] = detect_three_morning_star(bars)
    ind["three_evening_star"] = detect_three_evening_star(bars)

    # ── 新指标: 市场状态 ──
    regime = calc_market_regime(bars)
    if regime:
        ind["market_regime"] = regime.get("regime", "sideways")
        ind["regime_strength"] = regime.get("strength", 0)

    # ── 新指标: Fibonacci ──
    fib = calc_fib_retracement(bars)
    if fib:
        for k, v in fib.items():
            ind[f"fib_{k}"] = v

    return ind


# ═══════════════════════════════════════════════════════════════
# DataFrame 向量化包装器（研究用）
# ═══════════════════════════════════════════════════════════════

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    pd = None
    _HAS_PANDAS = False


def compute_from_series_for_row(row, df, i, max_window=250) -> dict:
    """Compute indicators for a single row using list-based compute_all_trading_indicators"""
    start = max(0, i - max_window + 1)
    bars_subset = df.iloc[start:i + 1].to_dict('records')
    return compute_all_trading_indicators(bars_subset)


def compute_all_trading_indicators_vectorized(df) -> "pd.DataFrame":
    """
    向量化版本 — 对 DataFrame 每行调用 compute_all_trading_indicators。
    用于研究/回测，保证与实时引擎 100% 一致。

    参数:
      df: pd.DataFrame (必须有 time/open/high/low/close/volume 列)

    返回:
      pd.DataFrame: 与 df 同索引，列 = 全部 ~320 个指标
    """
    records = df.to_dict('records')
    results = []
    total = len(records)
    for i in range(total):
        # 滑动窗口 250 bar（覆盖所有指标最大周期 200），非累计指标不受影响
        start = max(0, i - 249)
        window = records[start:i + 1]
        # 确保 window 中每行有 time 字段（Unix 秒）
        if window and 'time' not in window[-1] and hasattr(df, 'index'):
            ts = df.index[i]
            if hasattr(ts, 'timestamp'):
                window[-1]['time'] = int(ts.timestamp())
            elif isinstance(ts, (int, float)):
                # 处理 numpy int64（按 dytpe 分辨）
                dtype_str = str(df.index.dtype)
                val = int(ts)
                if 'ns' in dtype_str:
                    val = val // 10**9
                elif 'us' in dtype_str:
                    val = val // 10**6
                elif 'ms' in dtype_str:
                    val = val // 10**3
                window[-1]['time'] = val
        ind = compute_all_trading_indicators(window)
        results.append(ind)
    result_df = pd.DataFrame(results, index=df.index)
    return result_df


# 为了方便，datetime import 放在函数里以避免顶层依赖
from datetime import datetime, timezone
