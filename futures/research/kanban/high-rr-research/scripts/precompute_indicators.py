#!/usr/bin/env python3
"""precompute_indicators.py — 预计算全量技术指标（通用，不限策略）

覆盖全球主流技术分析指标，按类别组织。
产出: data/{H1,M5}/{symbol}_enhanced.parquet

每加新指标只需重新跑一次本脚本。
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# 使用 indicators.py 的向量化包装器（保证与实时引擎 100% 一致）
import sys
_SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from indicators import compute_all_trading_indicators_vectorized

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("precompute")

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"

SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF',
           'DXY','USDCAD','NZDUSD','XNGUSD','XCUUSD']

TIMEFRAMES = ["H1", "M5"]


def compute_all_indicators(df: pd.DataFrame, tf: str = "M5", n: int = 0, total: int = 0) -> pd.DataFrame:
    """在 DataFrame 上计算全部技术指标（与 indicators.py 同源保证一致性）

    核心指标 (320个): 委托 compute_all_trading_indicators_vectorized 计算
    研究增强 (~100+): 在此基础上添加更多周期扩展、统计特征、时间特征等
    """
    # ── 确保必要列存在 ──
    for col in ['open', 'high', 'low', 'close']:
        if col not in df.columns:
            log.warning("Missing column: %s", col)
            return df
    if 'volume' not in df.columns and 'tick_volume' in df.columns:
        df['volume'] = df['tick_volume']
    elif 'volume' not in df.columns:
        df['volume'] = 0

    # 确保 time 列存在（向量化方法需要，转 Unix 秒）
    if 'time' not in df.columns:
        ts = df.index.asi8
        dtype_str = str(df.index.dtype)
        if 'ns' in dtype_str:
            ts = ts // 10**9
        elif 'us' in dtype_str:
            ts = ts // 10**6
        elif 'ms' in dtype_str:
            ts = ts // 10**3
        # else: already seconds
        df['time'] = ts

    # ═══════════════════════════════════════════
    # A. 核心指标 compute_all_trading_indicators (与实时引擎 100% 一致)
    # ═══════════════════════════════════════════
    try:
        core_df = compute_all_trading_indicators_vectorized(df)
        # 去掉 core_df 中与 df 重复的列（如 time, volume）
        dupes = [c for c in core_df.columns if c in df.columns]
        core_df = core_df.drop(columns=dupes)
        # 用 concat 替代逐列插入，避免 PerformanceWarning
        df = pd.concat([df, core_df], axis=1)
    except Exception as e:
        log.warning("Core indicator computation failed: %s", str(e))

    # ═══════════════════════════════════════════
    # B. 研究增强指标 (Pandas 向量化，更多周期性扩展)
    # ═══════════════════════════════════════════

    closes = df['close'].values

    # 收益率 (更多周期)
    for p in [1, 2, 3, 5, 10, 20]:
        df[f'return_{p}'] = df['close'].pct_change(p) * 100

    # 缺口检测
    df['gap_pct'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1).replace(0, np.nan) * 100
    df['gap_up'] = (df['gap_pct'] > 0.5).astype(int)
    df['gap_down'] = (df['gap_pct'] < -0.5).astype(int)

    # K线实体/影线衍生
    df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
    wick_range = (df['high'] - df['low']).replace(0, np.nan)
    df['wick_ratio'] = (df['upper_shadow'] + df['lower_shadow']) / wick_range

    # MA 斜率对齐 (补充 indicators.py 未覆盖的额外周期)
    for p in [3, 8, 13, 21, 34, 55, 89, 144]:
        ma_v = df['close'].rolling(p).mean()
        df[f'ma{p}'] = ma_v
        df[f'ma{p}_slope'] = ma_v.diff(5) / ma_v.shift(5).replace(0, np.nan) * 100

    # EMA 对齐指标
    for p in [10]:
        df[f'ema{p}'] = df['close'].ewm(span=p).mean()
    df['ema5_above_ema13'] = (df['ema5'] > df['ema13']).astype(int) if 'ema5' in df.columns and 'ema13' in df.columns else 0
    df['ema12_above_ema26'] = (df['ema12'] > df['ema26']).astype(int) if 'ema12' in df.columns and 'ema26' in df.columns else 0
    for fast, slow in [(5, 13), (12, 26)]:
        fn, sn = f'ema{fast}', f'ema{slow}'
        if fn in df.columns and sn in df.columns:
            df[f'ema_cross_{fast}_{slow}'] = (df[fn] > df[sn]).astype(int).diff().clip(0, 1)

    # MA 交叉事件 (基于 indicators.py 已有 ma 列)
    for pair in [(5, 20), (10, 30), (20, 50)]:
        fn, sn = f'ma{pair[0]}', f'ma{pair[1]}'
        if fn in df.columns and sn in df.columns:
            df[f'ma_cross_{pair[0]}_{pair[1]}'] = (df[fn] > df[sn]).astype(int).diff().clip(0, 1)

    # Guppy 百分比扩展
    if 'guppy_short_spread' in df.columns and 'guppy_long_spread' in df.columns:
        df['guppy_short_spread_pct'] = df['guppy_short_spread'] / df['close'].replace(0, np.nan) * 100
        df['guppy_long_spread_pct'] = df['guppy_long_spread'] / df['close'].replace(0, np.nan) * 100

    # MACD 额外 (raw signal + zero cross)
    if 'macd_hist' in df.columns:
        df['macd'] = df.get('ema12', df['close']) - df.get('ema26', df['close'].rolling(26).mean())
        df['macd_zero_cross'] = (df['macd'] > 0).astype(int).diff().clip(0, 1)

    # RSI 多周期额外
    for p in [5, 9, 10, 25]:
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_g = gain.rolling(p, min_periods=p).mean()
        avg_l = loss.rolling(p, min_periods=p).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df[f'rsi{p}'] = 100.0 - (100.0 / (1.0 + rs))
    # RSI 背离
    if 'rsi14' in df.columns:
        df['rsi_divergence'] = ((df['close'].diff(5) > 0) & (df['rsi14'].diff(5) < -2)).astype(int)

    # Stochastic 多周期
    for stoch_p in [5, 8, 14, 21]:
        low_s = df['low'].rolling(stoch_p).min()
        high_s = df['high'].rolling(stoch_p).max()
        df[f'stoch_k_{stoch_p}'] = (df['close'] - low_s) / (high_s - low_s).replace(0, np.nan) * 100
        df[f'stoch_d_{stoch_p}'] = df[f'stoch_k_{stoch_p}'].rolling(3).mean()
    if 'stoch_k_14' in df.columns:
        df['stoch_k_14_oversold'] = (df['stoch_k_14'] < 20).astype(int)
        df['stoch_k_14_overbought'] = (df['stoch_k_14'] > 80).astype(int)

    # Williams 额外信号
    if 'williams_r_14' in df.columns:
        df['williams_oversold'] = (df['williams_r_14'] < -80).astype(int)
        df['williams_overbought'] = (df['williams_r_14'] > -20).astype(int)

    # CCI 多周期
    for cci_p in [50]:
        tp_c = (df['high'] + df['low'] + df['close']) / 3
        sma_c = tp_c.rolling(cci_p).mean()
        mad_c = tp_c.rolling(cci_p).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
        df[f'cci_{cci_p}'] = (tp_c - sma_c) / (0.015 * mad_c.replace(0, np.nan))

    # ATR 额外 (跳过 percentile/high/low，core_df 已有)
    if 'atr14' in df.columns:
        df['atr14_ratio_ema'] = df['atr14'] / df['atr14'].ewm(span=50).mean().replace(0, np.nan)
    # ATR7 percentile 是研究增强（core_df 无 atr7_pct 列的 percentile）

    # Bollinger Band 多配置 (研究版 3×3 = 9 组配置)
    for bb_p in [10, 20, 50]:
        for bb_std in [1.5, 2.0, 2.5]:
            mid_p = df['close'].rolling(bb_p).mean()
            std_p = df['close'].rolling(bb_p).std()
            sfx = f'{bb_p}_{bb_std}'
            df[f'bb_{sfx}_upper'] = mid_p + bb_std * std_p
            df[f'bb_{sfx}_lower'] = mid_p - bb_std * std_p
            df[f'bb_{sfx}_width'] = (df[f'bb_{sfx}_upper'] - df[f'bb_{sfx}_lower']) / mid_p.replace(0, np.nan) * 100
            df[f'bb_{sfx}_pos'] = (df['close'] - df[f'bb_{sfx}_lower']) / (df[f'bb_{sfx}_upper'] - df[f'bb_{sfx}_lower']).replace(0, np.nan) * 100
        df[f'bb_{bb_p}_touch_up'] = (df['high'] >= df[f'bb_{bb_p}_2.0_upper']).astype(int)
        df[f'bb_{bb_p}_touch_down'] = (df['low'] <= df[f'bb_{bb_p}_2.0_lower']).astype(int)

    # ADX 多周期
    for adx_p in [7, 14, 21, 50]:
        high = df['high']; low = df['low']
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = ((up_move > down_move) & (up_move > 0)).astype(int) * up_move
        minus_dm = ((down_move > up_move) & (down_move > 0)).astype(int) * down_move
        tr_p = pd.concat([high - low, (high - df['close'].shift()).abs(), (low - df['close'].shift()).abs()], axis=1).max(axis=1)
        tr_sm = tr_p.rolling(adx_p).sum()
        pdi = 100 * plus_dm.rolling(adx_p).sum() / tr_sm.replace(0, np.nan)
        mdi = 100 * minus_dm.rolling(adx_p).sum() / tr_sm.replace(0, np.nan)
        dx_v = abs(pdi - mdi) / (pdi + mdi).replace(0, np.nan) * 100
        df[f'adx_{adx_p}'] = dx_v.rolling(adx_p).mean()
        df[f'plus_di_{adx_p}'] = pdi
        df[f'minus_di_{adx_p}'] = mdi
        df[f'adx_di_cross_{adx_p}'] = (pdi > mdi).astype(int).diff().clip(0, 1)
    if 'adx_14' in df.columns:
        df['trend_strength'] = pd.cut(df['adx_14'], bins=[0, 20, 25, 40, 100],
                                      labels=['weak', 'mild', 'moderate', 'strong']).astype(str)

    # Aroon 多周期
    for ar_p in [10, 14, 25, 50]:
        ar_len = ar_p + 1
        if len(df) < ar_len:
            continue
        # Rolling apply variant for aroon
        def _aroon_up_f(x):
            if len(x) != ar_len: return np.nan
            return (ar_p - np.argmax(x)) / ar_p * 100
        def _aroon_down_f(x):
            if len(x) != ar_len: return np.nan
            return (ar_p - np.argmin(x)) / ar_p * 100
        df[f'aroon_up_{ar_p}'] = df['high'].rolling(ar_len).apply(_aroon_up_f, raw=True)
        df[f'aroon_down_{ar_p}'] = df['low'].rolling(ar_len).apply(_aroon_down_f, raw=True)
        df[f'aroon_osc_{ar_p}'] = df[f'aroon_up_{ar_p}'] - df[f'aroon_down_{ar_p}']
    if 'aroon_osc_14' in df.columns:
        df['aroon_strong_trend'] = (df['aroon_osc_14'].abs() > 50).astype(int)

    # TRIX 多周期
    for trix_p in [9, 14, 21]:
        ema1 = df['close'].ewm(span=trix_p).mean()
        ema2 = ema1.ewm(span=trix_p).mean()
        ema3 = ema2.ewm(span=trix_p).mean()
        df[f'trix_{trix_p}'] = ema3.pct_change() * 100
        df[f'trix_{trix_p}_signal'] = df[f'trix_{trix_p}'].ewm(span=9).mean()
        df[f'trix_{trix_p}_cross'] = (df[f'trix_{trix_p}'] > df[f'trix_{trix_p}_signal']).astype(int).diff().clip(0, 1)

    # Choppiness 额外周期
    # 先计算 True Range（被多个指标共用）
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs(),
    ], axis=1).max(axis=1)
    for chop_p in [10]:
        hi_ch = df['high'].rolling(chop_p).max()
        lo_ch = df['low'].rolling(chop_p).min()
        df[f'chop_{chop_p}'] = (np.log(tr.rolling(chop_p).sum() / (hi_ch - lo_ch).replace(0, np.nan)) / np.log(chop_p)) * 100
    if 'chop_14' in df.columns:
        df['choppy'] = (df['chop_14'] > 61.8).astype(int)
        df['trending'] = (df['chop_14'] < 38.2).astype(int)

    # Ichimoku (研究版用独立列名)
    if 'ichi_tenkan_sen' in df.columns:
        df['tenkan_sen'] = df['ichi_tenkan_sen']
        df['kijun_sen'] = df['ichi_kijun_sen']
        df['senkou_span_a'] = df['ichi_senkou_a']
        df['senkou_span_b'] = df['ichi_senkou_b']
        df['chikou_span'] = df['ichi_chikou']
        df['tk_cross'] = df['ichi_tk_cross']
        df['cloud_color_green'] = df['ichi_cloud_green']
        df['price_above_cloud'] = df['ichi_above_cloud']
        if 'kijun_sen' in df.columns and df['kijun_sen'].notna().any():
            df['close_vs_kijun'] = (df['close'] - df['kijun_sen']) / df['kijun_sen'].replace(0, np.nan) * 100

    # PSAR 别名
    if 'psar_psar' in df.columns:
        df['psar'] = df['psar_psar']
        df['above_psar'] = df['psar_above_psar']

    # 成交量增强
    if 'volume' in df.columns:
        vol = df['volume']
        for vp in [50]:
            df[f'volume_ma{vp}'] = vol.rolling(vp).mean()
            df[f'volume_ratio_{vp}'] = vol / df[f'volume_ma{vp}'].replace(0, np.nan)
        if 'volume_ratio_20' in df.columns:
            df['volume_squeeze'] = (df['volume_ratio_20'] < 0.5).astype(int)
        # Parabolic SAR 研究别名
        if 'psar_above_psar' in df.columns:
            df['above_psar'] = df['psar_above_psar']

    # 动量多周期 (补充 indicators.py 已有的)
    for mom_p in [14, 21, 50]:
        df[f'mom_{mom_p}'] = df['close'] - df['close'].shift(mom_p)
    for roc_p in [50, 100]:
        df[f'roc_{roc_p}'] = df['close'].pct_change(roc_p) * 100

    # HΗ/LL 额外周期
    for lookback in [100]:
        df[f'hh_{lookback}'] = df['high'].rolling(lookback).max()
        df[f'll_{lookback}'] = df['low'].rolling(lookback).min()
        df[f'hh_{lookback}_breakout'] = (df['high'] > df[f'hh_{lookback}'].shift()).astype(int)
        df[f'll_{lookback}_breakout'] = (df['low'] < df[f'll_{lookback}'].shift()).astype(int)

    # Pivot Points 多周期
    for pp_p in [5, 10]:
        if len(df) < pp_p + 1:
            continue
        pp_high = df['high'].rolling(pp_p, min_periods=pp_p).max().shift(pp_p)
        pp_low = df['low'].rolling(pp_p, min_periods=pp_p).min().shift(pp_p)
        pp_close = df['close'].rolling(pp_p, min_periods=pp_p).mean().shift(pp_p)
        pp_pivot = (pp_high + pp_low + pp_close) / 3
        df[f'pp_{pp_p}_pivot'] = pp_pivot
        df[f'pp_{pp_p}_r1'] = 2 * pp_pivot - pp_low
        df[f'pp_{pp_p}_s1'] = 2 * pp_pivot - pp_high
        df[f'pp_{pp_p}_r2'] = pp_pivot + (pp_high - pp_low)
        df[f'pp_{pp_p}_s2'] = pp_pivot - (pp_high - pp_low)
        df[f'pp_{pp_p}_above_pivot'] = (df['close'] > pp_pivot).astype(int)

    # K线形态增强
    body_size = abs(df['close'] - df['open'])
    total_range = df['high'] - df['low']
    avg_body = body_size.rolling(20).mean()
    avg_range = total_range.rolling(20).mean()
    upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
    lower_wick = df[['open', 'close']].min(axis=1) - df['low']

    df['pin_bar'] = (((upper_wick > total_range * 0.6) | (lower_wick > total_range * 0.6)) & (body_size < total_range * 0.4)).astype(int)
    df['rising_three'] = ((df['close'] > df['open']) & (body_size > avg_body * 1.2) &
                          (df['close'].shift(3) > df['open'].shift(3)) &
                          (body_size.shift(2) < avg_body.shift(2) * 0.5) &
                          (body_size.shift(1) < avg_body.shift(1) * 0.5)).astype(int)
    df['falling_three'] = ((df['close'] < df['open']) & (body_size > avg_body * 1.2) &
                           (df['close'].shift(3) < df['open'].shift(3)) &
                           (body_size.shift(2) < avg_body.shift(2) * 0.5) &
                           (body_size.shift(1) < avg_body.shift(1) * 0.5)).astype(int)

    # 斐波那契 (双周期)
    for fib_p in [50, 100]:
        hi_f = df['high'].rolling(fib_p).max()
        lo_f = df['low'].rolling(fib_p).min()
        rng = hi_f - lo_f
        for level in [0.236, 0.382, 0.500, 0.618, 0.786]:
            retrace = hi_f - rng * level
            pct = int(level * 1000)
            df[f'fib_{pct}_{fib_p}'] = (abs(df['close'] - retrace) / rng.replace(0, np.nan) * 100 < 5).astype(int)

    # 时间特征
    if isinstance(df.index, pd.DatetimeIndex):
        df['hour'] = df.index.hour
        df['minute'] = df.index.minute
        df['day_of_week'] = df.index.dayofweek
        df['is_monday'] = (df['day_of_week'] == 0).astype(int)
        df['is_friday'] = (df['day_of_week'] == 4).astype(int)
        df['is_month_start'] = (df.index.day < 5).astype(int)
        df['is_month_end'] = (df.index.day > 25).astype(int)

    return df
    # ═══════════════════════════════════════════
    df["body"] = abs(df["close"] - df["open"])
    df["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]
    df["wick_ratio"] = (df["upper_shadow"] + df["lower_shadow"]) / (df["high"] - df["low"]).replace(0, np.nan)
    df["range_pct"] = (df["high"] - df["low"]) / df["open"] * 100
    df["return_1"] = df["close"].pct_change(1) * 100
    df["return_5"] = df["close"].pct_change(5) * 100
    df["return_10"] = df["close"].pct_change(10) * 100
    df["return_20"] = df["close"].pct_change(20) * 100
    df["gap_pct"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1) * 100
    df["gap_up"] = (df["gap_pct"] > 0.5).astype(int)
    df["gap_down"] = (df["gap_pct"] < -0.5).astype(int)

    # ═══════════════════════════════════════════
    # 2. 移动平均线
    # ═══════════════════════════════════════════
    for period in [3, 5, 8, 10, 13, 20, 21, 30, 34, 50, 55, 89, 100, 144, 200]:
        df[f"ma{period}"] = df["close"].rolling(period).mean()
        df[f"ma{period}_slope"] = df[f"ma{period}"].diff(5) / df[f"ma{period}"].shift(5) * 100
    # 价格相对 MA
    for period in [20, 50, 100, 200]:
        df[f"close_vs_ma{period}"] = (df["close"] - df[f"ma{period}"]) / df[f"ma{period}"].replace(0, np.nan) * 100
    # MA 交叉
    df["ma5_above_ma20"] = (df["ma5"] > df["ma20"]).astype(int)
    df["ma10_above_ma30"] = (df["ma10"] > df["ma30"]).astype(int)
    df["ma20_above_ma50"] = (df["ma20"] > df["ma50"]).astype(int)
    df["ma50_above_ma200"] = (df["ma50"] > df["ma200"]).astype(int)
    df["ma_cross_5_20"] = (df["ma5"] > df["ma20"]).astype(int).diff().clip(0, 1)
    df["ma_cross_10_30"] = (df["ma10"] > df["ma30"]).astype(int).diff().clip(0, 1)
    df["ma_cross_20_50"] = (df["ma20"] > df["ma50"]).astype(int).diff().clip(0, 1)
    # Guppy MMA: 多组MA的分散度衡量趋势强度
    short_mas = [df[f"ma{p}"] for p in [3, 5, 8, 10, 13, 20]]
    long_mas = [df[f"ma{p}"] for p in [30, 34, 50, 55, 89, 100, 144, 200]]
    df["guppy_short_spread"] = pd.concat(short_mas, axis=1).max(axis=1) - pd.concat(short_mas, axis=1).min(axis=1)
    df["guppy_long_spread"] = pd.concat(long_mas, axis=1).max(axis=1) - pd.concat(long_mas, axis=1).min(axis=1)
    df["guppy_short_spread_pct"] = df["guppy_short_spread"] / df["close"] * 100
    df["guppy_long_spread_pct"] = df["guppy_long_spread"] / df["close"] * 100

    # ═══════════════════════════════════════════
    # 3. EMA / MACD
    # ═══════════════════════════════════════════
    for period in [5, 8, 10, 12, 13, 20, 21, 26, 34, 50, 55, 89, 144, 200]:
        df[f"ema{period}"] = df["close"].ewm(span=period).mean()
    df["ema5_above_ema13"] = (df["ema5"] > df["ema13"]).astype(int)
    df["ema12_above_ema26"] = (df["ema12"] > df["ema26"]).astype(int)
    df["ema_cross_12_26"] = (df["ema12"] > df["ema26"]).astype(int).diff().clip(0, 1)
    df["ema_cross_5_13"] = (df["ema5"] > df["ema13"]).astype(int).diff().clip(0, 1)
    # MACD 标准 + Trix
    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    df["macd_cross"] = (df["macd"] > df["macd_signal"]).astype(int).diff().clip(0, 1)
    df["macd_zero_cross"] = (df["macd"] > 0).astype(int).diff().clip(0, 1)

    # ═══════════════════════════════════════════
    # 4. RSI (多周期)
    # ═══════════════════════════════════════════
    for period in [5, 7, 9, 10, 14, 21, 25, 50]:
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(period, min_periods=period).mean()
        avg_loss = loss.rolling(period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df[f"rsi{period}"] = 100.0 - (100.0 / (1.0 + rs))
    df["rsi_oversold"] = (df["rsi14"] < 30).astype(int)
    df["rsi_overbought"] = (df["rsi14"] > 70).astype(int)
    df["rsi_divergence"] = ((df["close"].diff(5) > 0) & (df["rsi14"].diff(5) < -2)).astype(int)

    # ═══════════════════════════════════════════
    # 5. 随机指标
    # ═══════════════════════════════════════════
    for stoch_p in [5, 8, 14, 21]:
        low_s = df["low"].rolling(stoch_p).min()
        high_s = df["high"].rolling(stoch_p).max()
        df[f"stoch_k_{stoch_p}"] = (df["close"] - low_s) / (high_s - low_s).replace(0, np.nan) * 100
        df[f"stoch_d_{stoch_p}"] = df[f"stoch_k_{stoch_p}"].rolling(3).mean()
    df["stoch_k_14_oversold"] = (df["stoch_k_14"] < 20).astype(int)
    df["stoch_k_14_overbought"] = (df["stoch_k_14"] > 80).astype(int)

    # ═══════════════════════════════════════════
    # 6. Williams %R
    # ═══════════════════════════════════════════
    for wr_p in [10, 14, 21]:
        low_wr = df["low"].rolling(wr_p).min()
        high_wr = df["high"].rolling(wr_p).max()
        df[f"williams_r_{wr_p}"] = (high_wr - df["close"]) / (high_wr - low_wr).replace(0, np.nan) * -100
    df["williams_oversold"] = (df["williams_r_14"] < -80).astype(int)
    df["williams_overbought"] = (df["williams_r_14"] > -20).astype(int)

    # ═══════════════════════════════════════════
    # 7. CCI
    # ═══════════════════════════════════════════
    for cci_p in [10, 14, 20, 50]:
        tp_c = (df["high"] + df["low"] + df["close"]) / 3
        sma_c = tp_c.rolling(cci_p).mean()
        mad_c = tp_c.rolling(cci_p).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
        df[f"cci_{cci_p}"] = (tp_c - sma_c) / (0.015 * mad_c.replace(0, np.nan))

    # ═══════════════════════════════════════════
    # 8. ATR (多周期)
    # ═══════════════════════════════════════════
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    for period in [5, 7, 10, 14, 21, 50]:
        atr_v = tr.rolling(period, min_periods=period).mean()
        df[f"atr{period}"] = atr_v
        df[f"atr{period}_pct"] = atr_v / df["close"] * 100
    # 比值
    df["atr14_ratio_ema"] = df["atr14"] / df["atr14"].ewm(span=50).mean()
    for period in [7, 14]:
        df[f"atr{period}_percentile"] = df[f"atr{period}_pct"].rolling(100).rank(pct=True)
        df[f"atr{period}_high"] = (df[f"atr{period}_percentile"] > 0.8).astype(int)
        df[f"atr{period}_low"] = (df[f"atr{period}_percentile"] < 0.2).astype(int)

    # ═══════════════════════════════════════════
    # 9. 布林带 (20,2)
    # ═══════════════════════════════════════════
    for bb_p in [10, 20, 50]:
        for bb_std in [1.5, 2.0, 2.5]:
            mid_p = df["close"].rolling(bb_p).mean()
            std_p = df["close"].rolling(bb_p).std()
            sfx = f"{bb_p}_{bb_std}"
            df[f"bb_{sfx}_upper"] = mid_p + bb_std * std_p
            df[f"bb_{sfx}_lower"] = mid_p - bb_std * std_p
            df[f"bb_{sfx}_width"] = (df[f"bb_{sfx}_upper"] - df[f"bb_{sfx}_lower"]) / mid_p.replace(0, np.nan) * 100
            df[f"bb_{sfx}_pos"] = (df["close"] - df[f"bb_{sfx}_lower"]) / (df[f"bb_{sfx}_upper"] - df[f"bb_{sfx}_lower"]).replace(0, np.nan) * 100
        df[f"bb_{bb_p}_touch_up"] = (df["high"] >= df[f"bb_{bb_p}_2.0_upper"]).astype(int)
        df[f"bb_{bb_p}_touch_down"] = (df["low"] <= df[f"bb_{bb_p}_2.0_lower"]).astype(int)

    # ═══════════════════════════════════════════
    # 10. 通道 / 包络线
    # ═══════════════════════════════════════════
    # Keltner Channels
    kc_mid = df["ema20"]
    kc_atr = df["atr14"]
    for kc_mult in [1.0, 1.5, 2.0]:
        df[f"kc_{kc_mult}_upper"] = kc_mid + kc_mult * kc_atr
        df[f"kc_{kc_mult}_lower"] = kc_mid - kc_mult * kc_atr
        df[f"kc_{kc_mult}_pos"] = (df["close"] - df[f"kc_{kc_mult}_lower"]) / (df[f"kc_{kc_mult}_upper"] - df[f"kc_{kc_mult}_lower"]).replace(0, np.nan) * 100
    # Envelopes (MA ± %)
    for env_pct in [1, 2, 3, 5]:
        env_ma = df["ma20"]
        df[f"envelope_{env_pct}_upper"] = env_ma * (1 + env_pct / 100)
        df[f"envelope_{env_pct}_lower"] = env_ma * (1 - env_pct / 100)
    # Donchian Channels
    for dc_p in [10, 20, 50]:
        hi = df["high"].rolling(dc_p).max()
        lo = df["low"].rolling(dc_p).min()
        df[f"dc_{dc_p}_upper"] = hi
        df[f"dc_{dc_p}_lower"] = lo
        df[f"dc_{dc_p}_mid"] = (hi + lo) / 2
        df[f"dc_{dc_p}_width"] = (hi - lo) / df[f"dc_{dc_p}_mid"].replace(0, np.nan) * 100
        df[f"dc_{dc_p}_pos"] = (df["close"] - lo) / (hi - lo).replace(0, np.nan) * 100
        df[f"dc_{dc_p}_break_up"] = (df["high"] > hi.shift()).astype(int)
        df[f"dc_{dc_p}_break_down"] = (df["low"] < lo.shift()).astype(int)

    # ═══════════════════════════════════════════
    # 11. ADX / 趋势强度
    # ═══════════════════════════════════════════
    for adx_p in [7, 14, 21, 50]:
        high = df["high"]; low = df["low"]; close = df["close"]
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = ((up_move > down_move) & (up_move > 0)).astype(int) * up_move
        minus_dm = ((down_move > up_move) & (down_move > 0)).astype(int) * down_move
        tr_p = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        tr_sm = tr_p.rolling(adx_p).sum()
        pdi = 100 * plus_dm.rolling(adx_p).sum() / tr_sm.replace(0, np.nan)
        mdi = 100 * minus_dm.rolling(adx_p).sum() / tr_sm.replace(0, np.nan)
        dx_v = abs(pdi - mdi) / (pdi + mdi).replace(0, np.nan) * 100
        df[f"adx_{adx_p}"] = dx_v.rolling(adx_p).mean()
        df[f"plus_di_{adx_p}"] = pdi
        df[f"minus_di_{adx_p}"] = mdi
        df[f"adx_di_cross_{adx_p}"] = (pdi > mdi).astype(int).diff().clip(0, 1)
    df["trend_strength"] = pd.cut(df["adx_14"], bins=[0, 20, 25, 40, 100],
                                  labels=["weak", "mild", "moderate", "strong"]).astype(str)

    # ═══════════════════════════════════════════
    # 12. Aroon
    # ═══════════════════════════════════════════
    for ar_p in [10, 14, 25, 50]:
        hu = df["high"].rolling(ar_p + 1).apply(
            lambda x: (ar_p - np.argmax(x)) / ar_p * 100 if len(x) == ar_p + 1 else np.nan, raw=True)
        hd = df["low"].rolling(ar_p + 1).apply(
            lambda x: (ar_p - np.argmin(x)) / ar_p * 100 if len(x) == ar_p + 1 else np.nan, raw=True)
        df[f"aroon_up_{ar_p}"] = hu
        df[f"aroon_down_{ar_p}"] = hd
        df[f"aroon_osc_{ar_p}"] = hu - hd
    df["aroon_strong_trend"] = (df["aroon_osc_14"].abs() > 50).astype(int)

    # ═══════════════════════════════════════════
    # 13. 摆荡指标
    # ═══════════════════════════════════════════

    # TRIX (Triple Exponential Average)
    for trix_p in [9, 14, 21]:
        ema1 = df["close"].ewm(span=trix_p).mean()
        ema2 = ema1.ewm(span=trix_p).mean()
        ema3 = ema2.ewm(span=trix_p).mean()
        df[f"trix_{trix_p}"] = ema3.pct_change() * 100
        df[f"trix_{trix_p}_signal"] = df[f"trix_{trix_p}"].ewm(span=9).mean()
        df[f"trix_{trix_p}_cross"] = (df[f"trix_{trix_p}"] > df[f"trix_{trix_p}_signal"]).astype(int).diff().clip(0, 1)

    # Ultimate Oscillator
    for uo_p1, uo_p2, uo_p3 in [(7, 14, 28)]:
        bp = df["close"] - pd.concat([df["low"], df["close"].shift()], axis=1).min(axis=1)
        tr_u = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        avg7 = bp.rolling(uo_p1).sum() / tr_u.rolling(uo_p1).sum().replace(0, np.nan)
        avg14 = bp.rolling(uo_p2).sum() / tr_u.rolling(uo_p2).sum().replace(0, np.nan)
        avg28 = bp.rolling(uo_p3).sum() / tr_u.rolling(uo_p3).sum().replace(0, np.nan)
        df[f"ultimate_osc"] = (4 * avg7 + 2 * avg14 + 1 * avg28) / 7 * 100

    # Relative Vigor Index (RVGI)
    rvgi_open = df["open"].shift()
    rvgi_numer = df["close"] - rvgi_open
    rvgi_denom = df["high"] - df["low"]
    rvgi = rvgi_numer.rolling(10).sum() / rvgi_denom.rolling(10).sum().replace(0, np.nan)
    df["rvg_index"] = rvgi
    df["rvg_signal"] = rvgi.ewm(span=4).mean()

    # KST (Know Sure Thing)
    roc_10 = df["close"].pct_change(10) * 100
    roc_15 = df["close"].pct_change(15) * 100
    roc_20 = df["close"].pct_change(20) * 100
    roc_30 = df["close"].pct_change(30) * 100
    df["kst"] = roc_10.rolling(10).sum() + 2 * roc_15.rolling(10).sum() + 3 * roc_20.rolling(10).sum() + 4 * roc_30.rolling(15).sum()
    df["kst_signal"] = df["kst"].ewm(span=9).mean()

    # ═══════════════════════════════════════════
    # 14. Ichimoku Cloud
    # ═══════════════════════════════════════════
    tenkan_period = 9
    kijun_period = 26
    senkou_b_period = 52
    displacement = 26
    df["tenkan_sen"] = (df["high"].rolling(tenkan_period).max() + df["low"].rolling(tenkan_period).min()) / 2
    df["kijun_sen"] = (df["high"].rolling(kijun_period).max() + df["low"].rolling(kijun_period).min()) / 2
    df["senkou_span_a"] = ((df["tenkan_sen"] + df["kijun_sen"]) / 2).shift(displacement)
    df["senkou_span_b"] = ((df["high"].rolling(senkou_b_period).max() + df["low"].rolling(senkou_b_period).min()) / 2).shift(displacement)
    df["chikou_span"] = df["close"].shift(-displacement)
    df["price_above_cloud"] = ((df["close"] > df["senkou_span_a"]) & (df["close"] > df["senkou_span_b"])).astype(int)
    df["cloud_color_green"] = (df["senkou_span_a"] > df["senkou_span_b"]).astype(int)
    df["tk_cross"] = ((df["tenkan_sen"] > df["kijun_sen"]) & (df["tenkan_sen"].shift() <= df["kijun_sen"].shift())).astype(int)
    df["close_vs_kijun"] = (df["close"] - df["kijun_sen"]) / df["kijun_sen"].replace(0, np.nan) * 100

    # ═══════════════════════════════════════════
    # 15. Parabolic SAR
    # ═══════════════════════════════════════════
    def _calc_psar(high, low, close, accel=0.02, max_accel=0.2):
        out = close.copy().astype(float)
        bull = True
        af = accel
        ep = low[0]
        sar = high[0]
        for i in range(1, len(close)):
            if bull:
                sar = sar + af * (float(ep) - sar)
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + accel, max_accel)
                if low[i] < sar:
                    bull = False
                    sar = ep; af = accel; ep = low[i]
            else:
                sar = sar + af * (float(ep) - sar)
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + accel, max_accel)
                if high[i] > sar:
                    bull = True
                    sar = ep; af = accel; ep = high[i]
            out[i] = sar
        return out
    try:
        psar_v = _calc_psar(df["high"].values, df["low"].values, df["close"].values)
        df["psar"] = psar_v
        df["above_psar"] = (df["close"] > df["psar"]).astype(int)
    except Exception:
        df["psar"] = np.nan
        df["above_psar"] = 0

    # ═══════════════════════════════════════════
    # 16. Heikin Ashi
    # ═══════════════════════════════════════════
    df["ha_close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ho = [df["open"].iloc[0]]
    for i in range(1, len(df)):
        ho.append((ho[i - 1] + df["ha_close"].iloc[i - 1]) / 2)
    df["ha_open"] = ho
    df["ha_high"] = df[["high", "ha_open", "ha_close"]].max(axis=1)
    df["ha_low"] = df[["low", "ha_open", "ha_close"]].min(axis=1)
    df["ha_bullish"] = (df["ha_close"] > df["ha_open"]).astype(int)
    ha_range_v = df["ha_high"] - df["ha_low"]
    df["ha_trend_strength"] = abs(df["ha_close"] - df["ha_open"]) / ha_range_v.replace(0, 1)

    # ═══════════════════════════════════════════
    # 17. Choppiness Index
    # ═══════════════════════════════════════════
    for chop_p in [10, 14, 30, 50]:
        hi_ch = df["high"].rolling(chop_p).max()
        lo_ch = df["low"].rolling(chop_p).min()
        tr_sum = tr.rolling(chop_p).sum()
        df[f"chop_{chop_p}"] = (np.log(tr_sum / (hi_ch - lo_ch).replace(0, np.nan)) / np.log(chop_p)) * 100
    df["choppy"] = (df["chop_14"] > 61.8).astype(int)
    df["trending"] = (df["chop_14"] < 38.2).astype(int)

    # ═══════════════════════════════════════════
    # 18. 成交量指标
    # ═══════════════════════════════════════════
    if "tick_volume" in df.columns:
        vol = df["tick_volume"]
        for vp in [5, 10, 20, 50]:
            df[f"volume_ma{vp}"] = vol.rolling(vp).mean()
            df[f"volume_ratio_{vp}"] = vol / df[f"volume_ma{vp}"].replace(0, np.nan)
        df["volume_spike"] = (df["volume_ratio_20"] > 1.5).astype(int)
        df["volume_squeeze"] = (df["volume_ratio_20"] < 0.5).astype(int)
        # OBV
        obv = (df["close"] > df["close"].shift()).astype(int) * 2 - 1
        obv = obv.replace(0, 0) * vol
        df["obv"] = obv.cumsum()
        df["obv_ma"] = df["obv"].rolling(20).mean()
        df["obv_signal"] = (df["obv"] > df["obv_ma"]).astype(int)
        df["obv_cross"] = (df["obv"] > df["obv_ma"]).astype(int).diff().clip(0, 1)
        # MFI
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        money_flow = typical_price * vol
        for mfi_p in [9, 14, 21]:
            pos_mf = money_flow.where(typical_price > typical_price.shift(), 0).rolling(mfi_p).sum()
            neg_mf = money_flow.where(typical_price < typical_price.shift(), 0).rolling(mfi_p).sum()
            df[f"mfi_{mfi_p}"] = 100 - 100 / (1 + pos_mf / neg_mf.replace(0, np.nan))
        df["mfi_overbought"] = (df["mfi_14"] > 80).astype(int)
        df["mfi_oversold"] = (df["mfi_14"] < 20).astype(int)
        # CMF
        for cmf_p in [10, 20, 50]:
            mfm_c = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"]).replace(0, np.nan)
            mfv_c = mfm_c * vol
            df[f"cmf_{cmf_p}"] = mfv_c.rolling(cmf_p).sum() / vol.rolling(cmf_p).sum().replace(0, np.nan)
        df["cmf_bullish"] = (df["cmf_20"] > 0).astype(int)
        # Force Index
        df["force_index"] = (df["close"] - df["close"].shift()) * vol
        df["force_index_ema"] = df["force_index"].ewm(span=13).mean()
        df["force_index_signal"] = (df["force_index_ema"] > 0).astype(int)
        # Ease of Movement
        mid_pt = (df["high"] + df["low"]) / 2
        distance = mid_pt - mid_pt.shift()
        box_ratio = vol / (df["high"] - df["low"]).replace(0, np.nan)
        df["eom"] = distance / box_ratio.replace(0, np.nan)
        df["eom_ma"] = df["eom"].rolling(14).mean()
        # VWAP
        typical = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap_daily"] = (typical * vol).cumsum() / vol.cumsum().replace(0, np.nan)
        df["vwap_pos"] = (df["close"] - df["vwap_daily"]) / df["vwap_daily"].replace(0, np.nan) * 100
        df["above_vwap"] = (df["close"] > df["vwap_daily"]).astype(int)
        # Accumulation Distribution Line
        clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"]).replace(0, np.nan)
        df["ad_line"] = (clv * vol).cumsum()
        df["ad_ma"] = df["ad_line"].rolling(20).mean()
        df["ad_signal"] = (df["ad_line"] > df["ad_ma"]).astype(int)
        # Volume Price Trend
        vpt = df["return_1"] * (vol / vol.shift().replace(0, np.nan))
        df["vpt"] = vpt.cumsum()
        df["vpt_ma"] = df["vpt"].rolling(20).mean()
        # Negative / Positive Volume Index
        nvi_val = [1000]
        pvi_val = [1000]
        for i in range(1, len(df)):
            ret = df["return_1"].iloc[i]
            if pd.isna(ret): ret = 0
            if vol.iloc[i] < df["volume_ma_50"].iloc[i] if "volume_ma_50" in df.columns else vol.iloc[i] < vol.iloc[i-1]:
                nvi_val.append(nvi_val[-1] * (1 + ret / 100))
                pvi_val.append(pvi_val[-1])
            else:
                pvi_val.append(pvi_val[-1] * (1 + ret / 100))
                nvi_val.append(nvi_val[-1])
        df["nvi"] = nvi_val[-len(df):] if len(nvi_val) >= len(df) else nvi_val
        df["pvi"] = pvi_val[-len(df):] if len(pvi_val) >= len(df) else pvi_val
        # Klinger Oscillator
        high_kl = df["high"]; low_kl = df["low"]; close_kl = df["close"]
        trend_kl = (high_kl + low_kl + close_kl).diff()
        dm_kl = high_kl - low_kl
        dm_kl_cm = dm_kl.where(trend_kl >= 0, -dm_kl)
        vf_kl = vol * dm_kl_cm
        df["klinger"] = vf_kl.ewm(span=34).mean() - vf_kl.ewm(span=55).mean()
        df["klinger_signal"] = df["klinger"].ewm(span=13).mean()

    # ═══════════════════════════════════════════
    # 19. ROC / 动量
    # ═══════════════════════════════════════════
    for roc_p in [1, 2, 3, 5, 10, 20, 50, 100]:
        df[f"roc_{roc_p}"] = df["close"].pct_change(roc_p) * 100
    # 动量
    for mom_p in [5, 10, 14, 21, 50]:
        df[f"mom_{mom_p}"] = df["close"] - df["close"].shift(mom_p)

    # ═══════════════════════════════════════════
    # 20. 波动率
    # ═══════════════════════════════════════════
    for vol_p in [5, 10, 20, 50, 100]:
        df[f"volatility_{vol_p}"] = df["return_1"].rolling(vol_p).std()
    df["volatility_ratio_20_100"] = df["volatility_20"] / df["volatility_100"].replace(0, np.nan)
    df["high_volatility"] = (df["volatility_ratio_20_100"] > 1.5).astype(int)
    # Mass Index (high-low range expansion)
    hi_lo = df["high"] - df["low"]
    hi_lo_ema = hi_lo.ewm(span=9).mean()
    hi_lo_double = hi_lo_ema.ewm(span=9).mean()
    df["mass_index"] = (hi_lo / hi_lo_double.replace(0, np.nan)).rolling(25).sum()
    # Detrended Price Oscillator
    for dpo_p in [10, 20, 50]:
        ma_dpo = df["close"].rolling(dpo_p).mean()
        df[f"dpo_{dpo_p}"] = df["close"].shift(dpo_p // 2 + 1) - ma_dpo

    # ═══════════════════════════════════════════
    # 21. Z-Score / 统计
    # ═══════════════════════════════════════════
    for z_p in [10, 20, 50, 100, 200]:
        mean_z = df["close"].rolling(z_p).mean()
        std_z = df["close"].rolling(z_p).std()
        df[f"zscore_{z_p}"] = (df["close"] - mean_z) / std_z.replace(0, np.nan)
        df[f"zscore_extreme_{z_p}"] = (df[f"zscore_{z_p}"].abs() > 2).astype(int)
    # 统计矩
    for sk_p in [5, 10, 20, 50]:
        df[f"return_skew_{sk_p}"] = df["return_1"].rolling(sk_p).skew()
        df[f"return_kurt_{sk_p}"] = df["return_1"].rolling(sk_p).kurt()
    df["up_ratio_10"] = (df["close"] > df["close"].shift()).rolling(10).mean()
    df["up_ratio_20"] = (df["close"] > df["close"].shift()).rolling(20).mean()
    df["up_ratio_50"] = (df["close"] > df["close"].shift()).rolling(50).mean()
    # 序列相关性
    for lag_p in [1, 2, 3, 5]:
        df[f"autocorr_{lag_p}"] = df["return_1"].rolling(20).apply(
            lambda x: x.autocorr(lag=lag_p), raw=False)

    # ═══════════════════════════════════════════
    # 22. 经典 K 线形态
    # ═══════════════════════════════════════════
    body_size = abs(df["close"] - df["open"])
    total_range = df["high"] - df["low"]
    avg_body = body_size.rolling(20).mean()
    avg_range = total_range.rolling(20).mean()
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

    # Doji
    df["doji"] = (body_size <= total_range * 0.1).astype(int)
    df["long_legged_doji"] = ((body_size <= total_range * 0.1) & (total_range > avg_range * 1.5)).astype(int)
    df["dragonfly_doji"] = ((body_size <= total_range * 0.1) & (lower_wick > total_range * 0.6) & (upper_wick < total_range * 0.1)).astype(int)
    df["gravestone_doji"] = ((body_size <= total_range * 0.1) & (upper_wick > total_range * 0.6) & (lower_wick < total_range * 0.1)).astype(int)
    # Spinning Top
    df["spinning_top"] = ((body_size < total_range * 0.3) & (upper_wick > body_size) & (lower_wick > body_size) & (body_size > 0)).astype(int)
    # Hammer / Hanging Man / Shooting Star / Pin Bar
    df["hammer"] = ((lower_wick > body_size * 2) & (upper_wick < body_size * 0.5) & (body_size > 0)).astype(int)
    df["hanging_man"] = ((lower_wick > body_size * 2) & (upper_wick < body_size * 0.5) & (body_size > 0) & (df["close"] > df["open"])).astype(int)
    df["shooting_star"] = ((upper_wick > body_size * 2) & (lower_wick < body_size * 0.5) & (body_size > 0)).astype(int)
    df["pin_bar"] = (((upper_wick > total_range * 0.6) | (lower_wick > total_range * 0.6)) & (body_size < total_range * 0.4)).astype(int)
    # Engulfing
    df["bull_engulfing"] = ((df["close"] > df["open"]) & (df["open"] < df["close"].shift()) & (df["close"] > df["open"].shift()) & (body_size > body_size.shift() * 0.5)).astype(int)
    df["bear_engulfing"] = ((df["close"] < df["open"]) & (df["close"] < df["open"].shift()) & (df["open"] > df["close"].shift()) & (body_size > body_size.shift() * 0.5)).astype(int)
    # Harami
    df["bull_harami"] = ((df["close"] > df["open"]) & (df["open"] > df["close"].shift()) & (df["close"] < df["open"].shift()) & (body_size < body_size.shift() * 0.5)).astype(int)
    df["bear_harami"] = ((df["close"] < df["open"]) & (df["open"] < df["close"].shift()) & (df["close"] > df["open"].shift()) & (body_size < body_size.shift() * 0.5)).astype(int)
    # Inside / Outside Bar
    df["inside_bar"] = ((df["high"] <= df["high"].shift()) & (df["low"] >= df["low"].shift())).astype(int)
    df["outside_bar"] = ((df["high"] > df["high"].shift()) & (df["low"] < df["low"].shift())).astype(int)
    # Marubozu
    df["marubozu_bull"] = ((df["close"] > df["open"]) & (upper_wick < body_size * 0.05) & (lower_wick < body_size * 0.05)).astype(int)
    df["marubozu_bear"] = ((df["close"] < df["open"]) & (upper_wick < body_size * 0.05) & (lower_wick < body_size * 0.05)).astype(int)
    # Piercing / Dark Cloud
    df["piercing"] = ((df["close"] > df["open"]) & (df["open"] < df["low"].shift()) & (df["close"] > (df["open"].shift() + df["close"].shift()) / 2)).astype(int)
    df["dark_cloud"] = ((df["close"] < df["open"]) & (df["high"] > df["high"].shift()) & (df["close"] < (df["open"].shift() + df["close"].shift()) / 2)).astype(int)
    # Three Methods (rising/falling)
    df["rising_three"] = ((df["close"] > df["open"]) & (body_size > avg_body * 1.2) & (df["close"].shift(3) > df["open"].shift(3)) & (body_size.shift(2) < avg_body.shift(2) * 0.5) & (body_size.shift(1) < avg_body.shift(1) * 0.5)).astype(int)
    df["falling_three"] = ((df["close"] < df["open"]) & (body_size > avg_body * 1.2) & (df["close"].shift(3) < df["open"].shift(3)) & (body_size.shift(2) < avg_body.shift(2) * 0.5) & (body_size.shift(1) < avg_body.shift(1) * 0.5)).astype(int)
    # Morning / Evening Star (3-bar)
    first_bear_star = (df["close"] < df["open"]) & (body_size > avg_body * 1.2)
    first_bull_star = (df["close"] > df["open"]) & (body_size > avg_body * 1.2)
    mid_small = body_size < avg_body * 0.6
    df["three_morning_star"] = (first_bear_star.shift(2) & mid_small.shift(1) & (df["close"] > df["open"]) & (body_size > avg_body * 1.2)).astype(int)
    df["three_evening_star"] = (first_bull_star.shift(2) & mid_small.shift(1) & (df["close"] < df["open"]) & (body_size > avg_body * 1.2)).astype(int)

    # ═══════════════════════════════════════════
    # 23. 结构指标
    # ═══════════════════════════════════════════
    for lookback in [5, 10, 20, 50, 100]:
        df[f"hh_{lookback}"] = df["high"].rolling(lookback).max()
        df[f"ll_{lookback}"] = df["low"].rolling(lookback).min()
        df[f"hh_{lookback}_breakout"] = (df["high"] > df[f"hh_{lookback}"].shift()).astype(int)
        df[f"ll_{lookback}_breakout"] = (df["low"] < df[f"ll_{lookback}"].shift()).astype(int)
    # 连阴/连阳
    for col_name, compare in [("consecutive_bear", "close < open"),
                               ("consecutive_bull", "close > open")]:
        cond = df["close"] < df["open"] if "bear" in col_name else df["close"] > df["open"]
        df[col_name] = cond.astype(int).groupby((~cond).cumsum()).cumsum()
    # 支撑阻力
    for sr_p in [10, 20, 50]:
        df[f"support_{sr_p}"] = df[f"ll_{sr_p}"].rolling(5).min()
        df[f"resistance_{sr_p}"] = df[f"hh_{sr_p}"].rolling(5).max()
        diff_sr = df[f"resistance_{sr_p}"] - df[f"support_{sr_p}"]
        df[f"near_support_{sr_p}"] = (df["close"] - df[f"support_{sr_p}"]) / diff_sr.replace(0, 1) * 100
        df[f"near_resistance_{sr_p}"] = 100 - df[f"near_support_{sr_p}"]

    # ═══════════════════════════════════════════
    # 24. 斐波那契水平（接近检测）
    # ═══════════════════════════════════════════
    for fib_p in [50, 100]:
        hi_f = df["high"].rolling(fib_p).max()
        lo_f = df["low"].rolling(fib_p).min()
        rng = hi_f - lo_f
        for level in [0.236, 0.382, 0.500, 0.618, 0.786]:
            retrace = hi_f - rng * level
            df[f"fib_{int(level*1000)}_{fib_p}"] = (abs(df["close"] - retrace) / rng.replace(0, np.nan) * 100 < 5).astype(int)

    # ═══════════════════════════════════════════
    # 25. 时间特征
    # ═══════════════════════════════════════════
    df["hour"] = df.index.hour
    df["minute"] = df.index.minute
    df["day_of_week"] = df.index.dayofweek
    df["is_monday"] = (df["day_of_week"] == 0).astype(int)
    df["is_friday"] = (df["day_of_week"] == 4).astype(int)
    df["is_month_start"] = (df.index.day < 5).astype(int)
    df["is_month_end"] = (df.index.day > 25).astype(int)

    def _session(h: int) -> str:
        if 0 <= h < 8: return "asia"
        elif 8 <= h < 13: return "europe"
        return "us"
    df["session"] = df.index.hour.map(_session)

    # ═══════════════════════════════════════════
    # 26. 市场状态
    # ═══════════════════════════════════════════
    conditions = [
        (df["ma20"] > df["ma50"]) & (df["ma50"] > df["ma200"]),
        (df["ma20"] < df["ma50"]) & (df["ma50"] < df["ma200"]),
    ]
    choices = ["bull", "bear"]
    df["market_regime"] = np.select(conditions, choices, default="sideways")
    df["regime_strength"] = np.where(df["market_regime"] == "sideways", 0,
                                     np.where((df["adx_14"] > 25), 2, 1))

    # ═══════════════════════════════════════════
    # 27. 枢轴点 (Pivot Points)
    # ═══════════════════════════════════════════
    for pp_p in [1, 5, 10]:  # 每日/每5日/每10日
        if len(df) < pp_p + 1:
            continue
        # 简化的 pivot: 前 period 根 bar 的 HL/2
        pp_high = df["high"].rolling(pp_p, min_periods=pp_p).max().shift(pp_p)
        pp_low = df["low"].rolling(pp_p, min_periods=pp_p).min().shift(pp_p)
        pp_close = df["close"].rolling(pp_p, min_periods=pp_p).mean().shift(pp_p)
        pp_pivot = (pp_high + pp_low + pp_close) / 3
        df[f"pp_{pp_p}_pivot"] = pp_pivot
        df[f"pp_{pp_p}_r1"] = 2 * pp_pivot - pp_low
        df[f"pp_{pp_p}_s1"] = 2 * pp_pivot - pp_high
        df[f"pp_{pp_p}_r2"] = pp_pivot + (pp_high - pp_low)
        df[f"pp_{pp_p}_s2"] = pp_pivot - (pp_high - pp_low)
        df[f"pp_{pp_p}_above_pivot"] = (df["close"] > pp_pivot).astype(int)

    return df


def process_timeframe(tf: str):
    src_dir = DATA_DIR / tf
    out_dir = DATA_DIR / tf
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, sym in enumerate(SYMBOLS):
        src_path = src_dir / f"{sym}.parquet"
        out_path = out_dir / f"{sym}_enhanced.parquet"

        if not src_path.exists():
            log.warning("Missing: %s", src_path)
            continue

        log.info("[%d/%d] Processing %s %s...", idx + 1, len(SYMBOLS), sym, tf)
        df = pd.read_parquet(src_path)
        if df.empty:
            log.warning("Empty: %s", src_path)
            continue

        if not isinstance(df.index, pd.DatetimeIndex):
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
            else:
                log.warning("No time index: %s", src_path)
                continue

        df = df.sort_index()
        df = compute_all_indicators(df, tf, idx, len(SYMBOLS))
        df.to_parquet(out_path)
        rows, cols = df.shape
        log.info("  ✅ Saved: %s %dx%d", sym, rows, cols)

    log.info("✅ %s done (%d symbols)", tf, len(SYMBOLS))


def main():
    log.info("=" * 60)
    log.info("预计算全部技术指标（全量版）")
    log.info("=" * 60)
    for tf in TIMEFRAMES:
        process_timeframe(tf)
    log.info("=" * 60)
    log.info("全部完成")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
