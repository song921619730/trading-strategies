#!/usr/bin/env python3
"""
price_action_engine.py — 纯 K 线价格行为分析引擎

不使用任何技术指标（RSI/MACD/布林带等），只看原始 OHLCV。
输入: bar_open, bar_high, bar_low, bar_close, volume, bar_time
输出: {"direction": "long"/"short", "score": int, "reasons": [str], "signal_type": str}

用法:
    engine = PriceActionEngine()
    engine.feed(symbol, timeframe, indicator_dict)  # 每 tick 调用
    signal = engine.analyze(symbol, timeframe)       # 返回信号或 None
"""

from collections import deque
import threading
from typing import Optional


class PriceActionEngine:
    """纯价格行为分析引擎，维护每个品种/TF 的滚动 K 线缓冲"""

    # 每根 K 线需要的最小信息
    CANDLE_FIELDS = ["open", "high", "low", "close", "volume", "time"]

    def __init__(self, max_candles: int = 20):
        self.max_candles = max_candles
        self._history: dict[str, deque] = {}       # {symbol_tf: deque of candle dicts}
        self._last_bar_time: dict[str, int] = {}    # {symbol_tf: bar_time}
        self._lock = threading.Lock()
        self.MIN_CANDLES = 8      # 最少需要几根K线才能分析
        self.SCORE_THRESHOLD = 6  # 分数绝对值 ≥ 此值才出信号（防止噪音）

    # ── 公共方法 ──

    def feed(self, symbol: str, timeframe: str, ind: dict) -> None:
        """喂入最新 tick 的指标数据，自动检测新 K 线并记录"""
        key = f"{symbol}_{timeframe}"

        # 检查是否有新 K 线数据
        bar_time = ind.get("bar_time") or ind.get("timestamp")
        bar_open = ind.get("bar_open") or ind.get("open")
        bar_high = ind.get("bar_high") or ind.get("high")
        bar_low = ind.get("bar_low") or ind.get("low")
        bar_close = ind.get("bar_close") or ind.get("close")
        volume = ind.get("volume") or ind.get("bar_volume", 0)
        price = ind.get("price", bar_close or 0)

        # 无数据跳过
        if not all([bar_open, bar_high, bar_low, bar_close]):
            return

        # 没有 bar_time 则用 price 作为 fallback（只记录不重复）
        if not bar_time:
            return

        with self._lock:
            last_time = self._last_bar_time.get(key)
            if bar_time == last_time:
                # 同一根 K 线，更新 high/low/close（实时更新）
                self._update_current_candle(key, bar_high, bar_low, bar_close, volume, price)
                return

            # 新 K 线
            candle = {
                "open": bar_open,
                "high": bar_high,
                "low": bar_low,
                "close": bar_close,
                "volume": volume,
                "time": bar_time,
            }

            if key not in self._history:
                self._history[key] = deque(maxlen=self.max_candles)

            self._history[key].append(candle)
            self._last_bar_time[key] = bar_time

    def get_candles(self, symbol: str, timeframe: str, n: int = 10) -> list[dict]:
        """获取最近 N 根完整 K 线"""
        key = f"{symbol}_{timeframe}"
        with self._lock:
            hist = list(self._history.get(key, []))
        return hist[-n:] if len(hist) >= n else []

    def analyze(self, symbol: str, timeframe: str) -> Optional[dict]:
        """
        分析价格行为，返回信号或 None

        返回格式:
        {
            "direction": "long" | "short",
            "score": int,
            "reasons": [str],
            "signal_type": "reversal" | "momentum" | "breakout" | "exhaustion",
        }
        """
        candles = self.get_candles(symbol, timeframe, self.MIN_CANDLES)
        if len(candles) < self.MIN_CANDLES:
            return None

        score = 0
        reasons = []
        signal_types = set()

        # ── 检测项 ──

        # 1. 趋势方向（高点和低点排列）
        trend_score, trend_reason, sig_type = self._detect_trend(candles)
        score += trend_score
        if trend_reason:
            reasons.append(trend_reason)
            signal_types.add(sig_type)

        # 2. K 线实体趋势（实体变大/变小）
        body_score, body_reason, sig_type = self._detect_body_momentum(candles)
        score += body_score
        if body_reason:
            reasons.append(body_reason)
            signal_types.add(sig_type)

        # 3. 影线压力分析（上影线/下影线）
        wick_score, wick_reason, sig_type = self._detect_wick_pressure(candles)
        score += wick_score
        if wick_reason:
            reasons.append(wick_reason)
            signal_types.add(sig_type)

        # 4. 动能衰竭（大实体→小实体→十字星）
        exhaustion_score, exhaustion_reason, sig_type = self._detect_exhaustion(candles)
        score += exhaustion_score
        if exhaustion_reason:
            reasons.append(exhaustion_reason)
            signal_types.add(sig_type)

        # 5. 结构突破（突破最近高低点）
        break_score, break_reason, sig_type = self._detect_structure_break(candles)
        score += break_score
        if break_reason:
            reasons.append(break_reason)
            signal_types.add(sig_type)

        # 6. 动量对比（最近 vs 之前）
        momentum_score, momentum_reason, sig_type = self._detect_momentum_shift(candles)
        score += momentum_score
        if momentum_reason:
            reasons.append(momentum_reason)
            signal_types.add(sig_type)

        # ── 评估 ──

        abs_score = abs(score)
        if abs_score < self.SCORE_THRESHOLD:
            return None

        direction = "long" if score > 0 else "short"

        # 取最相关的信号类型
        signal_type = "mixed"
        if len(signal_types) == 1:
            signal_type = signal_types.pop()
        elif signal_types:
            # 多个类型时取最高分的那个
            signal_type = signal_types.pop()

        # 置信度 = 分数 / 最大可能分数
        confidence = min(abs_score / 12.0, 1.0)

        return {
            "direction": direction,
            "score": score,
            "confidence": round(confidence, 2),
            "reasons": reasons[:3],  # 只保留前3个最重要的
            "signal_type": signal_type,
            "candle_count": len(candles),
        }

    # ── 内部检测方法 ──

    def _body_size(self, candle: dict) -> float:
        """K 线实体大小（绝对值）"""
        return abs(candle["close"] - candle["open"])

    def _upper_wick(self, candle: dict) -> float:
        """上影线长度"""
        return candle["high"] - max(candle["open"], candle["close"])

    def _lower_wick(self, candle: dict) -> float:
        """下影线长度"""
        return min(candle["open"], candle["close"]) - candle["low"]

    def _total_range(self, candle: dict) -> float:
        """K 线总振幅"""
        return candle["high"] - candle["low"]

    def _is_bull(self, candle: dict) -> bool:
        return candle["close"] > candle["open"]

    def _is_bear(self, candle: dict) -> bool:
        return candle["close"] < candle["open"]

    def _is_doji(self, candle: dict, threshold: float = 0.1) -> bool:
        """十字星：实体占总振幅比例小于阈值"""
        tr = self._total_range(candle)
        if tr == 0:
            return True
        return self._body_size(candle) / tr < threshold

    def _update_current_candle(self, key: str, high: float, low: float,
                                close: float, volume: float, price: float) -> None:
        """更新当前未收盘 K 线的实时数据"""
        if key not in self._history or not self._history[key]:
            return
        last = self._history[key][-1]
        last["high"] = max(last["high"], high)
        last["low"] = min(last["low"], low)
        last["close"] = close
        last["volume"] = max(last["volume"], volume)

    def _detect_trend(self, candles: list[dict]) -> tuple:
        """
        趋势方向判断：比较最近 N 根的高低点排列
        - 更高的高点 + 更高的低点 → 上涨趋势
        - 更低的高点 + 更低的低点 → 下跌趋势
        """
        if len(candles) < 3:
            return 0, None, None

        recent = candles[-3:]
        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]
        bodies = [self._body_size(c) for c in recent]

        highs_up = highs[2] > highs[1] > highs[0]
        highs_down = highs[2] < highs[1] < highs[0]
        lows_up = lows[2] > lows[1] > lows[0]
        lows_down = lows[2] < lows[1] < lows[0]

        score = 0
        if highs_up and lows_up:
            score = 2
            return score, f"趋势上涨(高点上移+低点上移)", "momentum"
        elif highs_down and lows_down:
            score = -2
            return score, f"趋势下跌(高点下移+低点下移)", "momentum"

        # 部分趋势：只有高点或低点在移动
        avg_body = sum(bodies) / len(bodies)
        last_body = bodies[-1]

        if highs_up and last_body > avg_body * 1.2:
            score = 1
            return score, f"偏多(高点上移+阳线放大)", "momentum"
        elif highs_down and last_body > avg_body * 1.2:
            score = -1
            return score, f"偏空(高点下移+阴线放大)", "momentum"

        return 0, None, None

    def _detect_body_momentum(self, candles: list[dict]) -> tuple:
        """
        K 线实体动量：比较最近 vs 之前的实体大小
        - 实体持续变大 → 动能增强
        - 实体持续变小 → 动能减弱
        """
        if len(candles) < 6:
            return 0, None, None

        recent = candles[-3:]
        prev = candles[-6:-3]

        recent_bodies = [self._body_size(c) for c in recent]
        prev_bodies = [self._body_size(c) for c in prev]

        recent_avg = sum(recent_bodies) / len(recent_bodies)
        prev_avg = sum(prev_bodies) / len(prev_bodies)

        # 判断方向（最近 K 线的颜色决定方向）
        bulls = sum(1 for c in recent if self._is_bull(c))
        bears = sum(1 for c in recent if self._is_bear(c))

        if bulls >= 2 and recent_avg > prev_avg * 1.3 and prev_avg > 0:
            score = 2 + max(0, int(recent_avg / prev_avg) - 1)
            return score, f"多方动能增强(实体{recent_avg/prev_avg:.1f}x)", "momentum"
        elif bears >= 2 and recent_avg > prev_avg * 1.3 and prev_avg > 0:
            score = -2 - max(0, int(recent_avg / prev_avg) - 1)
            return score, f"空方动能增强(实体{recent_avg/prev_avg:.1f}x)", "momentum"
        elif bulls >= 2 and prev_avg > 0 and recent_avg < prev_avg * 0.6:
            score = -1
            return score, f"多方动能减弱(实体{recent_avg/prev_avg:.1f}x)", "exhaustion"
        elif bears >= 2 and prev_avg > 0 and recent_avg < prev_avg * 0.6:
            score = 1
            return score, f"空方动能减弱(实体{recent_avg/prev_avg:.1f}x)", "exhaustion"

        return 0, None, None

    def _detect_wick_pressure(self, candles: list[dict]) -> tuple:
        """
        影线压力分析：
        - 连续上影线 → 上方卖压
        - 连续下影线 → 下方买盘支撑
        """
        if len(candles) < 3:
            return 0, None, None

        recent = candles[-3:]
        long_upper = 0
        long_lower = 0
        total_upper = 0
        total_lower = 0

        for c in recent:
            tr = self._total_range(c)
            if tr == 0:
                continue
            uw = self._upper_wick(c)
            lw = self._lower_wick(c)
            total_upper += uw
            total_lower += lw
            if uw / tr > 0.5:
                long_upper += 1
            if lw / tr > 0.5:
                long_lower += 1

        avg_upper = total_upper / len(recent)
        avg_lower = total_lower / len(recent)

        score = 0
        if long_upper >= 2 and avg_upper > avg_lower * 1.5:
            score = -2
            return score, f"卖压(连续{long_upper}根上影线)", "reversal"
        elif long_lower >= 2 and avg_lower > avg_upper * 1.5:
            score = 2
            return score, f"买盘支撑(连续{long_lower}根下影线)", "reversal"

        # 单根极端影线
        last = recent[-1]
        last_tr = self._total_range(last)
        if last_tr > 0:
            if self._upper_wick(last) / last_tr > 0.6 and self._is_bull(last):
                score = -1
                return score, f"冲高回落(上影线占比{self._upper_wick(last)/last_tr:.0%})", "reversal"
            if self._lower_wick(last) / last_tr > 0.6 and self._is_bear(last):
                score = 1
                return score, f"探底回升(下影线占比{self._lower_wick(last)/last_tr:.0%})", "reversal"

        return 0, None, None

    def _detect_exhaustion(self, candles: list[dict]) -> tuple:
        """
        动能衰竭检测：
        - 大阳/大阴 → 小阳/小阴 → 十字星  = 趋势耗尽
        """
        if len(candles) < 4:
            return 0, None, None

        recent = candles[-4:]
        bodies = [self._body_size(c) for c in recent]
        avg_body = sum(bodies) / len(bodies)

        # 检测：实体递减趋势
        body_decreasing = all(bodies[i] >= bodies[i+1] for i in range(len(bodies)-1))
        if not body_decreasing:
            return 0, None, None

        # 最后是十字星或者极小实体
        last_is_doji = self._is_doji(recent[-1]) or bodies[-1] < avg_body * 0.3

        if not last_is_doji:
            return 0, None, None

        # 方向取决于前期的方向
        first_bulls = sum(1 for c in recent[:2] if self._is_bull(c))
        first_bears = sum(1 for c in recent[:2] if self._is_bear(c))

        if first_bulls >= 2:
            score = -3
            return score, f"上涨衰竭(实体递减→十字星)", "exhaustion"
        elif first_bears >= 2:
            score = 3
            return score, f"下跌衰竭(实体递减→十字星)", "exhaustion"

        return 0, None, None

    def _detect_structure_break(self, candles: list[dict]) -> tuple:
        """
        结构突破检测：
        - 突破最近 N 根的高点
        - 跌破最近 N 根的低点
        - 假突破（突破后马上回来）
        """
        if len(candles) < 5:
            return 0, None, None

        recent_5 = candles[-5:]
        last = recent_5[-1]
        prev_4 = recent_5[:-1]

        range_high = max(c["high"] for c in prev_4)
        range_low = min(c["low"] for c in prev_4)
        range_body = range_high - range_low

        if range_body == 0:
            return 0, None, None

        score = 0

        # 真突破：突破前高且站稳（收盘在区间上方）
        if last["high"] > range_high and last["close"] > range_high:
            score = 2
            return score, f"突破前高({last['high']}>{range_high})", "breakout"

        # 真跌破：跌破前低且收盘在区间下方
        elif last["low"] < range_low and last["close"] < range_low:
            score = -2
            return score, f"跌破前低({last['low']}<{range_low})", "breakout"

        # 假突破：突破但收盘回来
        if last["high"] > range_high and last["close"] < range_high:
            score = -1
            return score, f"假突破(突破{range_high}后回落)", "reversal"
        elif last["low"] < range_low and last["close"] > range_low:
            score = 1
            return score, f"假跌破(跌破{range_low}后收回)", "reversal"

        return 0, None, None

    def _detect_momentum_shift(self, candles: list[dict]) -> tuple:
        """
        动量对比：最近 vs 之前区间的变化
        - 对比方向突变
        """
        if len(candles) < 8:
            return 0, None, None

        recent_3 = candles[-3:]
        prev_3 = candles[-6:-3]

        recent_bulls = sum(1 for c in recent_3 if self._is_bull(c))
        prev_bulls = sum(1 for c in prev_3 if self._is_bull(c))
        recent_bears = sum(1 for c in recent_3 if self._is_bear(c))
        prev_bears = sum(1 for c in prev_3 if self._is_bear(c))

        score = 0

        # 空转多
        if prev_bears >= 2 and recent_bulls >= 2:
            score = 2
            return score, f"空转多(前{prev_bears}阴→后{recent_bulls}阳)", "reversal"

        # 多转空
        if prev_bulls >= 2 and recent_bears >= 2:
            score = -2
            return score, f"多转空(前{prev_bulls}阳→后{recent_bears}阴)", "reversal"

        return 0, None, None


# ── 单例工厂 ──
_engine: Optional[PriceActionEngine] = None
_engine_lock = threading.Lock()


def get_engine(max_candles: int = 20) -> PriceActionEngine:
    """获取全局单例"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = PriceActionEngine(max_candles)
    return _engine


def analyze(symbol: str, timeframe: str) -> Optional[dict]:
    """快捷调用：分析单个品种当前信号"""
    return get_engine().analyze(symbol, timeframe)


def feed(symbol: str, timeframe: str, ind: dict) -> None:
    """快捷调用：喂数据"""
    get_engine().feed(symbol, timeframe, ind)
