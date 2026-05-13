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
from typing import Optional


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
        utc_hour = datetime.fromtimestamp(latest["time"], tz=timezone.utc).hour

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

    return ind


# 为了方便，datetime import 放在函数里以避免顶层依赖
from datetime import datetime, timezone
