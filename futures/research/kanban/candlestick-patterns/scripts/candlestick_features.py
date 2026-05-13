"""
candlestick_features.py — Candlestick Pattern Detection for Grid Engine

Adds candlestick pattern columns to any OHLCV DataFrame so they can be
referenced in grid_engine entry_condition strings.

Available columns (all bool):
  doji                 — Open ≈ Close (body < 5% of range)
  inside_bar           — High <= prev_high AND Low >= prev_low
  engulfing_bull       — Bullish engulfing: prev_red_candle, current_green_candle covers prev range
  engulfing_bear       — Bearish engulfing: prev_green_candle, current_red_candle covers prev range
  hammer               — Small body in upper half, long lower wick (>= 2x body)
  shooting_star        — Small body in lower half, long upper wick (>= 2x body)
  pin_bar              — Long wick (>= 2x body) on either side; small body
  marubozu_bull        — Full-bodied green: open == low, close == high (within tol)
  marubozu_bear        — Full-bodied red: open == high, close == low (within tol)
  tweezer_top          — Two consecutive candles with same high
  tweezer_bottom       — Two consecutive candles with same low
  harami_bull          — Large red then small green inside prev range
  harami_bear          — Large green then small red inside prev range
  three_white_soldiers — 3 consecutive green with higher highs and higher closes
  three_black_crows    — 3 consecutive red with lower lows and lower closes
  morning_star         — Large red → small doji → large green
  evening_star         — Large green → small doji → large red

Usage:
    from candlestick_features import add_candlestick_features
    df = add_candlestick_features(df)
    # Now entry_condition can use: "doji and rsi14 < 40"
"""

import pandas as pd
import numpy as np


def _body_size(open_, close):
    """Absolute body size."""
    return abs(close - open_)


def _full_range(high, low):
    """Full candle range."""
    return high - low


def _upper_wick(high, open_, close):
    """Upper wick length."""
    return high - np.maximum(open_, close)


def _lower_wick(low, open_, close):
    """Lower wick length."""
    return np.minimum(open_, close) - low


def add_candlestick_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add candlestick pattern columns to the DataFrame.

    Operates on a copy. Requires columns: open, high, low, close.
    All added columns are boolean (True = pattern detected).
    """
    df = df.copy()
    o, h, l_, c = df["open"], df["high"], df["low"], df["close"]

    body = _body_size(o, c)
    body_avg = body.rolling(14, min_periods=1).mean().fillna(body)
    full_rng = _full_range(h, l_)
    full_rng_avg = full_rng.rolling(14, min_periods=1).mean().fillna(full_rng)
    upper = _upper_wick(h, o, c)
    lower = _lower_wick(l_, o, c)
    wick_max = np.maximum(upper, lower)
    wick_min = np.minimum(upper, lower)

    # Small body tolerance: body < 5% of full range (or body < 0.1 * avg body)
    small_body = (body < 0.05 * full_rng) | (body < 0.1 * body_avg)

    # --- 1. Doji ---
    df["doji"] = small_body

    # --- 2. Inside Bar ---
    prev_h = h.shift(1)
    prev_l = l_.shift(1)
    df["inside_bar"] = (h <= prev_h) & (l_ >= prev_l) & prev_h.notna()

    # --- 3. Engulfing ---
    prev_o = o.shift(1)
    prev_c = c.shift(1)
    red_prev = prev_c < prev_o
    green_curr = c > o
    green_prev = prev_c > prev_o
    red_curr = c < o

    df["engulfing_bull"] = red_prev & green_curr & (h >= prev_h) & (l_ <= prev_l)
    df["engulfing_bear"] = green_prev & red_curr & (h >= prev_h) & (l_ <= prev_l)

    # --- 4. Hammer ---
    # Small body in upper half of range, lower wick >= 2x body
    body_pos = (o + c) / 2  # midpoint of body
    range_mid = (h + l_) / 2
    body_upper_half = body_pos > range_mid
    long_lower_wick = lower >= 2 * body
    df["hammer"] = small_body & body_upper_half & long_lower_wick

    # --- 5. Shooting Star ---
    # Small body in lower half of range, upper wick >= 2x body
    body_lower_half = body_pos < range_mid
    long_upper_wick = upper >= 2 * body
    df["shooting_star"] = small_body & body_lower_half & long_upper_wick

    # --- 6. Pin Bar ---
    # Long wick >= 2x body on one side, small body
    long_wick_any = wick_max >= 2 * body
    short_opposite_wick = wick_min <= 0.3 * wick_max  # the other wick is short
    df["pin_bar"] = small_body & long_wick_any & short_opposite_wick

    # --- 7. Marubozu ---
    tol = 0.0001  # relative tolerance for open=low / close=high
    df["marubozu_bull"] = (c > o) & (abs(o - l_) / (h - l_ + 1e-10) < tol) & \
                          (abs(c - h) / (h - l_ + 1e-10) < tol)
    df["marubozu_bear"] = (c < o) & (abs(o - h) / (h - l_ + 1e-10) < tol) & \
                          (abs(c - l_) / (h - l_ + 1e-10) < tol)

    # --- 8. Tweezer Top / Bottom ---
    same_high = abs(h - prev_h) / (h + 1e-10) < 0.0005
    same_low = abs(l_ - prev_l) / (l_ + 1e-10) < 0.0005
    df["tweezer_top"] = same_high & (c.shift(1) < o.shift(1)) & (c > o)
    df["tweezer_bottom"] = same_low & (c.shift(1) > o.shift(1)) & (c < o)

    # --- 9. Harami ---
    # Bullish harami: large red then small green entirely inside prev range
    large_prev = _body_size(prev_o, prev_c) > 1.5 * body_avg.shift(1)
    df["harami_bull"] = red_prev & (c > o) & \
                        (h <= prev_h) & (l_ >= prev_l) & large_prev & \
                        (_body_size(o, c) < 0.5 * _body_size(prev_o, prev_c))
    df["harami_bear"] = green_prev & (c < o) & \
                        (h <= prev_h) & (l_ >= prev_l) & large_prev & \
                        (_body_size(o, c) < 0.5 * _body_size(prev_o, prev_c))

    # --- 10. Three White Soldiers / Three Black Crows ---
    g1 = c.shift(2) > o.shift(2)  # 3 bars ago green
    g2 = c.shift(1) > o.shift(1)  # 2 bars ago green
    g3 = c > o                     # current green
    higher_high2 = c.shift(1) > c.shift(2)
    higher_high3 = c > c.shift(1)
    close_in_upper2 = c.shift(1) > (o.shift(1) + c.shift(1)) / 2
    close_in_upper3 = c > (o + c) / 2
    df["three_white_soldiers"] = g1 & g2 & g3 & higher_high2 & higher_high3 & \
                                 close_in_upper2 & close_in_upper3

    r1 = c.shift(2) < o.shift(2)
    r2 = c.shift(1) < o.shift(1)
    r3 = c < o
    lower_low2 = c.shift(1) < c.shift(2)
    lower_low3 = c < c.shift(1)
    close_in_lower2 = c.shift(1) < (o.shift(1) + c.shift(1)) / 2
    close_in_lower3 = c < (o + c) / 2
    df["three_black_crows"] = r1 & r2 & r3 & lower_low2 & lower_low3 & \
                              close_in_lower2 & close_in_lower3

    # --- 11. Morning Star / Evening Star ---
    # Morning star: red candle(2 bars ago) → small body(1 bar ago) → green(current)
    # Requires the star candle to be small relative to the first candle
    prev2_o = o.shift(2)
    prev2_c = c.shift(2)
    prev2_body = _body_size(prev2_o, prev2_c)
    ms_cond = (c.shift(2) < o.shift(2)) & small_body.shift(1) & (c > o) & \
              (_body_size(o, c) < 0.5 * prev2_body) & (prev2_body > body_avg.shift(2))
    df["morning_star"] = ms_cond

    # Evening star: green candle(2 bars ago) → small body(1 bar ago) → red(current)
    es_cond = (c.shift(2) > o.shift(2)) & small_body.shift(1) & (c < o) & \
              (_body_size(o, c) < 0.5 * prev2_body) & (prev2_body > body_avg.shift(2))
    df["evening_star"] = es_cond

    # --- 12. Composite: Any reversal signal ---
    df["bull_reversal"] = df["hammer"] | df["engulfing_bull"] | \
                          df["morning_star"] | df["harami_bull"] | \
                          df["tweezer_bottom"] | df["pin_bar"]
    df["bear_reversal"] = df["shooting_star"] | df["engulfing_bear"] | \
                          df["evening_star"] | df["harami_bear"] | \
                          df["tweezer_top"]

    # --- 13. Trend continuation ---
    df["bull_continuation"] = df["marubozu_bull"] | df["three_white_soldiers"]
    df["bear_continuation"] = df["marubozu_bear"] | df["three_black_crows"]

    return df


def list_available_patterns() -> list:
    """Return a list of all candlestick pattern column names."""
    return [
        "doji", "inside_bar",
        "engulfing_bull", "engulfing_bear",
        "hammer", "shooting_star", "pin_bar",
        "marubozu_bull", "marubozu_bear",
        "tweezer_top", "tweezer_bottom",
        "harami_bull", "harami_bear",
        "three_white_soldiers", "three_black_crows",
        "morning_star", "evening_star",
        "bull_reversal", "bear_reversal",
        "bull_continuation", "bear_continuation",
    ]


def pattern_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Print a summary of how often each pattern appears in the data."""
    pattern_cols = [c for c in list_available_patterns() if c in df.columns]
    counts = df[pattern_cols].sum()
    pcts = (counts / len(df) * 100).round(3)
    summary = pd.DataFrame({"count": counts, "pct": pcts})
    summary = summary.sort_values("count", ascending=False)
    summary = summary[summary["count"] > 0]
    return summary
