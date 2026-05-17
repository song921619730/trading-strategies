#!/usr/bin/env python3
"""
batch_precompute.py — 批量全量指标预计算（快路径）

策略: Pandas 向量化计算所有指标（O(N) 快）
        最后一行调 indicators.py 的 compute_all_trading_indicators 保证一致性

用法:
  python3 scripts/batch_precompute.py
"""
import logging, sys, warnings, os
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("batch-precompute")

BASE = Path(__file__).resolve().parent.parent  # futures/
_SCRIPTS = BASE / "scripts"

SYMBOLS = ["XAUUSD","XAGUSD","EURUSD","GBPUSD","USDJPY",
           "AUDUSD","USDCHF","USOIL","UKOIL","USTEC",
           "US30","US500","JP225","HK50",
           "DXY","USDCAD","NZDUSD","XNGUSD","XCUUSD"]

TIMEFRAMES = {"M5": None}  # NOTE: H1 skipped for speed, re-enable if full rerun needed


def process_dataset(data_dir: Path):
    """对一个数据集目录做批量预计算"""
    for tf_name in TIMEFRAMES:
        src_dir = data_dir / tf_name
        if not src_dir.exists():
            log.warning("目录不存在: %s", src_dir)
            continue

        for idx, sym in enumerate(SYMBOLS):
            src = src_dir / f"{sym}.parquet"
            dst = src_dir / f"{sym}_enhanced.parquet"
            if not src.exists():
                log.warning("[%d/%d] ❌ 缺失: %s", idx+1, len(SYMBOLS), src)
                continue

            log.info("[%d/%d] Processing %s %s...", idx+1, len(SYMBOLS), sym, tf_name)
            try:
                df = pd.read_parquet(src)
                if df.empty:
                    log.warning("  空数据: %s", src)
                    continue

                df = compute_all_fast(df, tf_name)

                df.to_parquet(dst, index=True)
                log.info("  ✅ %s  saved: %s rows × %s cols",
                         sym, len(df), len(df.columns))
            except Exception as e:
                log.error("  ❌ %s error: %s", sym, e)
                import traceback
                traceback.print_exc()

        log.info("✅ %s done (%d symbols)", tf_name, len(SYMBOLS))


def compute_all_fast(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """快速计算全部指标（Pandas向量化 + 末行一致性验证）"""
    df = df.copy()

    # ── 列名标准化 ──
    if 'tick_volume' in df.columns and 'volume' not in df.columns:
        df['volume'] = df['tick_volume']
    if 'volume' not in df.columns:
        df['volume'] = 0

    # ── 收集原始 bar 数据（最后调 indicators.py 用） ──
    bars_records = df.to_dict('records')

    # ════════════════════════════════════════════════════
    # 全部指标 - Pandas 向量化快速计算
    # ════════════════════════════════════════════════════

    closes = df['close']
    highs = df['high']
    lows = df['low']
    opens = df['open']
    vols = df['volume']
    n = len(df)

    # ── 价格衍生 ──
    df['body'] = abs(closes - opens)
    df['range'] = highs - lows
    df['range_pct'] = (highs - lows) / opens.replace(0, np.nan) * 100
    body_pct = df['body'] / df['range'].replace(0, np.nan) * 100
    df['body_pct'] = body_pct
    df['upper_shadow'] = highs - df[['open', 'close']].max(axis=1)
    df['lower_shadow'] = df[['open', 'close']].min(axis=1) - lows
    df['wick_ratio'] = (df['upper_shadow'] + df['lower_shadow']) / df['range'].replace(0, np.nan)
    df['return_1'] = closes.pct_change(1) * 100
    for p in [5, 10, 20]:
        df[f'return_{p}'] = closes.pct_change(p) * 100
    df['gap_pct'] = (opens - closes.shift(1)) / closes.shift(1).replace(0, np.nan) * 100
    df['gap_up'] = (df['gap_pct'] > 0.5).astype(int)
    df['gap_down'] = (df['gap_pct'] < -0.5).astype(int)

    # ── RSI (多周期) ──
    for period in [5, 7, 9, 10, 14, 21, 25, 50]:
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_g = gain.rolling(period, min_periods=period).mean()
        avg_l = loss.rolling(period, min_periods=period).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df[f'rsi{period}'] = 100.0 - (100.0 / (1.0 + rs))
    df['rsi_oversold'] = (df['rsi14'] < 30).astype(int)
    df['rsi_overbought'] = (df['rsi14'] > 70).astype(int)
    df['rsi_divergence'] = ((closes.diff(5) > 0) & (df['rsi14'].diff(5) < -2)).astype(int)

    # ── SMA/MA ──
    for period in [3, 5, 8, 10, 13, 20, 21, 30, 34, 50, 55, 89, 100, 144, 200]:
        ma_v = closes.rolling(period).mean()
        df[f'ma{period}'] = ma_v
        df[f'ma{period}_slope'] = ma_v.diff(5) / ma_v.shift(5).replace(0, np.nan) * 100

    # 价格 vs MA
    for period in [20, 50, 100, 200]:
        df[f'close_vs_ma{period}'] = (closes - df[f'ma{period}']) / df[f'ma{period}'].replace(0, np.nan) * 100

    # MA 交叉
    for pair in [(5, 20), (10, 30), (20, 50), (50, 200)]:
        fn, sn = f'ma{pair[0]}', f'ma{pair[1]}'
        df[f'ma{pair[0]}_above_ma{pair[1]}'] = (df[fn] > df[sn]).astype(int)

    # Guppy MMA
    short_mas = [df[f'ma{p}'] for p in [3, 5, 8, 10, 13, 20]]
    long_mas = [df[f'ma{p}'] for p in [30, 34, 50, 55, 89, 100, 144, 200]]
    short_concat = pd.concat(short_mas, axis=1)
    long_concat = pd.concat(long_mas, axis=1)
    df['guppy_short_spread'] = short_concat.max(axis=1) - short_concat.min(axis=1)
    df['guppy_long_spread'] = long_concat.max(axis=1) - long_concat.min(axis=1)
    df['guppy_short_spread_pct'] = df['guppy_short_spread'] / closes.replace(0, np.nan) * 100
    df['guppy_long_spread_pct'] = df['guppy_long_spread'] / closes.replace(0, np.nan) * 100

    # ── EMA ──
    for period in [5, 8, 10, 12, 13, 20, 21, 26, 34, 50, 55, 89, 144, 200]:
        df[f'ema{period}'] = closes.ewm(span=period).mean()
    df['ema5_above_ema13'] = (df['ema5'] > df['ema13']).astype(int)
    df['ema12_above_ema26'] = (df['ema12'] > df['ema26']).astype(int)

    # ── MACD ──
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    df['macd_cross'] = ((df['macd'] > df['macd_signal']).astype(int).diff() > 0).astype(int)
    df['macd_zero_cross'] = ((df['macd'] > 0).astype(int).diff() > 0).astype(int)

    # ── Stochastic ──
    for stoch_p in [5, 8, 14, 21]:
        l_s = lows.rolling(stoch_p).min()
        h_s = highs.rolling(stoch_p).max()
        df[f'stoch_k_{stoch_p}'] = (closes - l_s) / (h_s - l_s).replace(0, np.nan) * 100
        df[f'stoch_d_{stoch_p}'] = df[f'stoch_k_{stoch_p}'].rolling(3).mean()
    df['stoch_k_14_oversold'] = (df['stoch_k_14'] < 20).astype(int)
    df['stoch_k_14_overbought'] = (df['stoch_k_14'] > 80).astype(int)

    # ── Williams %R ──
    for wr_p in [10, 14, 21]:
        l_w = lows.rolling(wr_p).min()
        h_w = highs.rolling(wr_p).max()
        df[f'williams_r_{wr_p}'] = (h_w - closes) / (h_w - l_w).replace(0, np.nan) * -100
    df['williams_oversold'] = (df['williams_r_14'] < -80).astype(int)
    df['williams_overbought'] = (df['williams_r_14'] > -20).astype(int)

    # ── CCI ──
    for cci_p in [10, 14, 20, 50]:
        tp_c = (highs + lows + closes) / 3
        sma_c = tp_c.rolling(cci_p).mean()
        mad_c = tp_c.rolling(cci_p).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
        df[f'cci_{cci_p}'] = (tp_c - sma_c) / (0.015 * mad_c.replace(0, np.nan))

    # ── ATR ──
    tr = pd.concat([
        highs - lows,
        (highs - closes.shift()).abs(),
        (lows - closes.shift()).abs(),
    ], axis=1).max(axis=1)
    for period in [5, 7, 10, 14, 21, 50]:
        atr_v = tr.rolling(period, min_periods=period).mean()
        df[f'atr{period}'] = atr_v
        df[f'atr{period}_pct'] = atr_v / closes.replace(0, np.nan) * 100
    df['atr14_ratio_ema'] = df['atr14'] / df['atr14'].ewm(span=50).mean().replace(0, np.nan)
    for period in [7, 14]:
        ap = f'atr{period}_pct'
        if ap in df.columns:
            df[f'atr{period}_percentile'] = df[ap].rolling(100).rank(pct=True)
            df[f'atr{period}_high'] = (df[f'atr{period}_percentile'] > 0.8).astype(int)
            df[f'atr{period}_low'] = (df[f'atr{period}_percentile'] < 0.2).astype(int)

    # ── Bollinger ──
    for bb_p in [10, 20, 50]:
        for bb_std in [1.5, 2.0, 2.5]:
            mid_b = closes.rolling(bb_p).mean()
            std_b = closes.rolling(bb_p).std()
            sfx = f'{bb_p}_{bb_std}'
            df[f'bb_{sfx}_upper'] = mid_b + bb_std * std_b
            df[f'bb_{sfx}_lower'] = mid_b - bb_std * std_b
            df[f'bb_{sfx}_width'] = (df[f'bb_{sfx}_upper'] - df[f'bb_{sfx}_lower']) / mid_b.replace(0, np.nan) * 100
            df[f'bb_{sfx}_pos'] = (closes - df[f'bb_{sfx}_lower']) / (df[f'bb_{sfx}_upper'] - df[f'bb_{sfx}_lower']).replace(0, np.nan) * 100
        df[f'bb_{bb_p}_touch_up'] = (highs >= df[f'bb_{bb_p}_2.0_upper']).astype(int)
        df[f'bb_{bb_p}_touch_down'] = (lows <= df[f'bb_{bb_p}_2.0_lower']).astype(int)

    # ── Keltner Channels ──
    for kc_mult in [1.0, 1.5, 2.0]:
        df[f'kc_{kc_mult}_upper'] = df['ema20'] + kc_mult * df['atr14']
        df[f'kc_{kc_mult}_lower'] = df['ema20'] - kc_mult * df['atr14']
        df[f'kc_{kc_mult}_mid'] = df['ema20']
        diff_kc = df[f'kc_{kc_mult}_upper'] - df[f'kc_{kc_mult}_lower']
        df[f'kc_{kc_mult}_pos'] = (closes - df[f'kc_{kc_mult}_lower']) / diff_kc.replace(0, np.nan) * 100

    # ── Donchian ──
    for dc_p in [10, 20, 50]:
        hi = highs.rolling(dc_p).max()
        lo = lows.rolling(dc_p).min()
        df[f'dc_{dc_p}_upper'] = hi
        df[f'dc_{dc_p}_lower'] = lo
        df[f'dc_{dc_p}_mid'] = (hi + lo) / 2
        df[f'dc_{dc_p}_width_pct'] = (hi - lo) / df[f'dc_{dc_p}_mid'].replace(0, np.nan) * 100
        df[f'dc_{dc_p}_pos'] = (closes - lo) / (hi - lo).replace(0, np.nan) * 100
        df[f'dc_{dc_p}_break_up'] = (highs > hi.shift()).astype(int)
        df[f'dc_{dc_p}_break_down'] = (lows < lo.shift()).astype(int)

    # ── Envelopes ──
    for env_pct in [1, 2, 3, 5]:
        env_ma = df['ma20']
        df[f'envelope_{env_pct}_upper'] = env_ma * (1 + env_pct / 100)
        df[f'envelope_{env_pct}_lower'] = env_ma * (1 - env_pct / 100)

    # ── ADX ──
    for adx_p in [7, 14, 21, 50]:
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = ((up_move > down_move) & (up_move > 0)).astype(int) * up_move
        minus_dm = ((down_move > up_move) & (down_move > 0)).astype(int) * down_move
        tr_p = tr.rolling(adx_p).sum()
        pdi = 100 * plus_dm.rolling(adx_p).sum() / tr_p.replace(0, np.nan)
        mdi = 100 * minus_dm.rolling(adx_p).sum() / tr_p.replace(0, np.nan)
        dx_v = abs(pdi - mdi) / (pdi + mdi).replace(0, np.nan) * 100
        df[f'adx_{adx_p}'] = dx_v.rolling(adx_p).mean()
        df[f'plus_di_{adx_p}'] = pdi
        df[f'minus_di_{adx_p}'] = mdi
        df[f'adx_di_cross_{adx_p}'] = (pdi > mdi).astype(int).diff().clip(0, 1)
    df['trend_strength'] = pd.cut(df['adx_14'], bins=[0, 20, 25, 40, 100],
                                  labels=['weak', 'mild', 'moderate', 'strong']).astype(str)

    # ── Aroon ──
    for ar_p in [10, 14, 25, 50]:
        ar_len = ar_p + 1
        if n < ar_len: continue
        def _a_up(x):
            return (ar_p - np.argmax(x)) / ar_p * 100 if len(x) == ar_len else np.nan
        def _a_down(x):
            return (ar_p - np.argmin(x)) / ar_p * 100 if len(x) == ar_len else np.nan
        df[f'aroon_up_{ar_p}'] = highs.rolling(ar_len).apply(_a_up, raw=True)
        df[f'aroon_down_{ar_p}'] = lows.rolling(ar_len).apply(_a_down, raw=True)
        df[f'aroon_osc_{ar_p}'] = df[f'aroon_up_{ar_p}'] - df[f'aroon_down_{ar_p}']
    df['aroon_strong_trend'] = (df['aroon_osc_14'].abs() > 50).astype(int)

    # ── Choppiness ──
    for chop_p in [10, 14, 30, 50]:
        hi_ch = highs.rolling(chop_p).max()
        lo_ch = lows.rolling(chop_p).min()
        tr_sum = tr.rolling(chop_p).sum()
        df[f'chop_{chop_p}'] = (np.log(tr_sum / (hi_ch - lo_ch).replace(0, np.nan)) / np.log(chop_p)) * 100
    df['choppy'] = (df['chop_14'] > 61.8).astype(int)
    df['trending'] = (df['chop_14'] < 38.2).astype(int)

    # ── Volume ──
    if vols.sum() > 0:
        for vp in [5, 10, 20, 50]:
            df[f'volume_ma{vp}'] = vols.rolling(vp).mean()
            df[f'volume_ratio_{vp}'] = vols / df[f'volume_ma{vp}'].replace(0, np.nan)
            df[f'volume_spike_{vp}'] = (df[f'volume_ratio_{vp}'] > 1.5).astype(int)
        df['volume_squeeze'] = (df['volume_ratio_20'] < 0.5).astype(int)

        # OBV
        obv_dir = ((closes > closes.shift()).astype(int) * 2 - 1).replace(0, 1)
        df['obv'] = (obv_dir * vols).cumsum()
        df['obv_ma'] = df['obv'].rolling(20).mean()
        df['obv_signal'] = (df['obv'] > df['obv_ma']).astype(int)
        df['obv_cross'] = ((df['obv'] > df['obv_ma']).astype(int).diff() > 0).astype(int)

        # MFI
        tp_mfi = (highs + lows + closes) / 3
        for mfi_p in [9, 14, 21]:
            pos_mf = (tp_mfi * vols).where(tp_mfi > tp_mfi.shift(), 0).rolling(mfi_p).sum()
            neg_mf = (tp_mfi * vols).where(tp_mfi < tp_mfi.shift(), 0).rolling(mfi_p).sum()
            df[f'mfi_{mfi_p}'] = 100 - 100 / (1 + pos_mf / neg_mf.replace(0, np.nan))

        # VWAP
        typical = (highs + lows + closes) / 3
        df['vwap'] = (typical * vols).cumsum() / vols.cumsum().replace(0, np.nan)
        df['vwap_pos'] = (closes - df['vwap']) / df['vwap'].replace(0, np.nan) * 100
        df['above_vwap'] = (closes > df['vwap']).astype(int)

        # CMF
        for cmf_p in [10, 20, 50]:
            mfm_c = ((closes - lows) - (highs - closes)) / (highs - lows).replace(0, np.nan)
            mfv_c = mfm_c * vols
            df[f'cmf_{cmf_p}'] = mfv_c.rolling(cmf_p).sum() / vols.rolling(cmf_p).sum().replace(0, np.nan)
        df['cmf_bullish'] = (df['cmf_20'] > 0).astype(int)

        # Force Index
        df['force_index'] = (closes - closes.shift()) * vols
        df['force_index_ema'] = df['force_index'].ewm(span=13).mean()
        df['force_index_signal'] = (df['force_index_ema'] > 0).astype(int)

        # Ease of Movement
        mid_pt = (highs + lows) / 2
        distance = mid_pt - mid_pt.shift()
        box_ratio = vols / (highs - lows).replace(0, np.nan)
        df['eom'] = distance / box_ratio.replace(0, np.nan)
        df['eom_ma'] = df['eom'].rolling(14).mean()

        # NVI/PVI (用 robust 方式避免 NaN)
        nvi_vals = [1000.0]; pvi_vals = [1000.0]
        vol_ma_50 = df['volume_ma50'].values if 'volume_ma50' in df.columns else np.full(n, vols.rolling(20).mean().iloc[-1] if n > 0 else 1000)
        vol_ma_20 = df['volume_ma20'].values if 'volume_ma20' in df.columns else vols.rolling(5).mean().values
        for i in range(1, len(df)):
            ret = df['return_1'].iloc[i] if pd.notna(df['return_1'].iloc[i]) else 0
            if vols.iloc[i] < (vol_ma_50[i] if i < len(vol_ma_50) else vol_ma_20[i]):
                nvi_vals.append(nvi_vals[-1] * (1 + ret / 100))
                pvi_vals.append(pvi_vals[-1])
            else:
                pvi_vals.append(pvi_vals[-1] * (1 + ret / 100))
                nvi_vals.append(nvi_vals[-1])
        df['nvi'] = nvi_vals[:len(df)]
        df['pvi'] = pvi_vals[:len(df)]

        # Klinger
        trend_kl = (highs + lows + closes).diff()
        dm_kl = highs - lows
        dm_kl_cm = dm_kl.where(trend_kl >= 0, -dm_kl)
        vf_kl = vols * dm_kl_cm
        df['klinger'] = vf_kl.ewm(span=34).mean() - vf_kl.ewm(span=55).mean()
        df['klinger_signal'] = df['klinger'].ewm(span=13).mean()

        # AD Line
        clv = ((closes - lows) - (highs - closes)) / (highs - lows).replace(0, np.nan)
        df['ad_line'] = (clv * vols).cumsum()
        df['ad_ma'] = df['ad_line'].rolling(20).mean()
        df['ad_signal'] = (df['ad_line'] > df['ad_ma']).astype(int)

        # VPT
        vpt = df['return_1'] * (vols / vols.shift().replace(0, 1))
        df['vpt'] = vpt.cumsum()

    # ── Momentum / ROC ──
    for mom_p in [5, 10, 14, 20, 21, 50]:
        df[f'mom_{mom_p}'] = closes - closes.shift(mom_p)
    for roc_p in [1, 2, 3, 5, 10, 20, 50, 100]:
        df[f'roc_{roc_p}'] = closes.pct_change(roc_p) * 100

    # ── Volatility ──
    for vol_p in [5, 10, 20, 50, 100]:
        df[f'volatility_{vol_p}'] = df['return_1'].rolling(vol_p).std()
    df['volatility_ratio_20_100'] = df['volatility_20'] / df['volatility_100'].replace(0, np.nan)
    df['high_volatility'] = (df['volatility_ratio_20_100'] > 1.5).astype(int)

    # ── Mass Index ──
    hi_lo = highs - lows
    hi_lo_ema = hi_lo.ewm(span=9).mean()
    hi_lo_double = hi_lo_ema.ewm(span=9).mean()
    df['mass_index'] = (hi_lo / hi_lo_double.replace(0, np.nan)).rolling(25).sum()

    # ── DPO ──
    for dpo_p in [10, 20, 50]:
        ma_dpo = closes.rolling(dpo_p).mean()
        df[f'dpo_{dpo_p}'] = closes.shift(dpo_p // 2 + 1) - ma_dpo

    # ── Z-Score ──
    for z_p in [10, 20, 50, 100, 200]:
        mean_z = closes.rolling(z_p).mean()
        std_z = closes.rolling(z_p).std()
        df[f'zscore_{z_p}'] = (closes - mean_z) / std_z.replace(0, np.nan)
        df[f'zscore_extreme_{z_p}'] = (df[f'zscore_{z_p}'].abs() > 2).astype(int)

    # ── 统计矩 ──
    for sk_p in [5, 10, 20, 50]:
        df[f'return_skew_{sk_p}'] = df['return_1'].rolling(sk_p).skew()
        df[f'return_kurt_{sk_p}'] = df['return_1'].rolling(sk_p).kurt()
    for up_p in [10, 20, 50]:
        df[f'up_ratio_{up_p}'] = ((closes > closes.shift()).rolling(up_p).mean())
    for lag in [1, 2, 3, 5]:
        df[f'autocorr_{lag}'] = df['return_1'].rolling(20).apply(
            lambda x: x.autocorr(lag=lag), raw=False)

    # ── HH/LL/结构 / 支压 ──
    for lb in [5, 10, 20, 50, 100]:
        df[f'hh_{lb}'] = highs.rolling(lb).max()
        df[f'll_{lb}'] = lows.rolling(lb).min()
        df[f'hh_{lb}_breakout'] = (highs > df[f'hh_{lb}'].shift()).astype(int)
        df[f'll_{lb}_breakout'] = (lows < df[f'll_{lb}'].shift()).astype(int)
    for sr_p in [10, 20, 50]:
        df[f'resistance_{sr_p}'] = df[f'hh_{sr_p}']
        df[f'support_{sr_p}'] = df[f'll_{sr_p}']
        sr_diff = df[f'resistance_{sr_p}'] - df[f'support_{sr_p}']
        df[f'near_support_{sr_p}'] = (closes - df[f'support_{sr_p}']) / sr_diff.replace(0, 1) * 100
        df[f'near_resistance_{sr_p}'] = 100 - df[f'near_support_{sr_p}']

    # ── K线形态 ──
    body_size = df['body']
    total_range = df['range']
    avg_body = body_size.rolling(20).mean()
    avg_range = total_range.rolling(20).mean()
    df['doji'] = (body_size <= total_range * 0.1).astype(int)
    df['long_legged_doji'] = ((body_size <= total_range * 0.1) & (total_range > avg_range * 1.5)).astype(int)
    df['dragonfly_doji'] = ((body_size <= total_range * 0.1) & (df['lower_shadow'] > total_range * 0.6) & (df['upper_shadow'] < total_range * 0.1)).astype(int)
    df['gravestone_doji'] = ((body_size <= total_range * 0.1) & (df['upper_shadow'] > total_range * 0.6) & (df['lower_shadow'] < total_range * 0.1)).astype(int)
    df['spinning_top'] = ((body_size < total_range * 0.3) & (df['upper_shadow'] > body_size) & (df['lower_shadow'] > body_size) & (body_size > 0)).astype(int)
    df['hammer'] = ((df['lower_shadow'] > body_size * 2) & (df['upper_shadow'] < body_size * 0.5) & (body_size > 0) & (closes <= opens)).astype(int)
    df['hanging_man'] = ((df['lower_shadow'] > body_size * 2) & (df['upper_shadow'] < body_size * 0.5) & (body_size > 0) & (closes > opens)).astype(int)
    df['shooting_star'] = ((df['upper_shadow'] > body_size * 2) & (df['lower_shadow'] < body_size * 0.5) & (body_size > 0)).astype(int)
    df['pin_bar'] = (((df['upper_shadow'] > total_range * 0.6) | (df['lower_shadow'] > total_range * 0.6)) & (body_size < total_range * 0.4)).astype(int)
    df['bull_engulfing'] = ((closes > opens) & (opens < closes.shift()) & (closes > opens.shift()) & (body_size > body_size.shift() * 0.5)).astype(int)
    df['bear_engulfing'] = ((closes < opens) & (closes < opens.shift()) & (opens > closes.shift()) & (body_size > body_size.shift() * 0.5)).astype(int)
    df['inside_bar'] = ((highs <= highs.shift()) & (lows >= lows.shift())).astype(int)
    df['outside_bar'] = ((highs > highs.shift()) & (lows < lows.shift())).astype(int)
    df['bull_harami'] = ((closes > opens) & (opens > closes.shift()) & (closes < opens.shift()) & (body_size < body_size.shift() * 0.5)).astype(int)
    df['bear_harami'] = ((closes < opens) & (opens < closes.shift()) & (closes > opens.shift()) & (body_size < body_size.shift() * 0.5)).astype(int)
    df['marubozu_bull'] = ((closes > opens) & (df['upper_shadow'] < body_size * 0.05) & (df['lower_shadow'] < body_size * 0.05)).astype(int)
    df['marubozu_bear'] = ((closes < opens) & (df['upper_shadow'] < body_size * 0.05) & (df['lower_shadow'] < body_size * 0.05)).astype(int)
    df['piercing'] = ((closes > opens) & (opens < lows.shift()) & (closes > (opens.shift() + closes.shift()) / 2)).astype(int)
    df['dark_cloud'] = ((closes < opens) & (highs > highs.shift()) & (closes < (opens.shift() + closes.shift()) / 2)).astype(int)
    df['three_morning_star'] = (((closes.shift(2) < opens.shift(2)) & (body_size.shift(2) > avg_body.shift(2) * 1.2) & (body_size.shift(1) < avg_body.shift(1) * 0.6) & (closes > opens) & (body_size > avg_body * 1.2))).astype(int)
    df['three_evening_star'] = (((closes.shift(2) > opens.shift(2)) & (body_size.shift(2) > avg_body.shift(2) * 1.2) & (body_size.shift(1) < avg_body.shift(1) * 0.6) & (closes < opens) & (body_size > avg_body * 1.2))).astype(int)

    # ── Pivot Points ──
    for pp_p in [1, 5, 10]:
        if n < pp_p + 1: continue
        pp_high = highs.rolling(pp_p, min_periods=pp_p).max().shift(pp_p)
        pp_low = lows.rolling(pp_p, min_periods=pp_p).min().shift(pp_p)
        pp_close = closes.rolling(pp_p, min_periods=pp_p).mean().shift(pp_p)
        pp_pivot = (pp_high + pp_low + pp_close) / 3
        df[f'pp_{pp_p}_pivot'] = pp_pivot
        df[f'pp_{pp_p}_r1'] = 2 * pp_pivot - pp_low
        df[f'pp_{pp_p}_s1'] = 2 * pp_pivot - pp_high
        df[f'pp_{pp_p}_r2'] = pp_pivot + (pp_high - pp_low)
        df[f'pp_{pp_p}_s2'] = pp_pivot - (pp_high - pp_low)
        df[f'pp_{pp_p}_above_pivot'] = (closes > pp_pivot).astype(int)

    # ── Fibonacci ──
    for fib_p in [50, 100]:
        hi_f = highs.rolling(fib_p).max()
        lo_f = lows.rolling(fib_p).min()
        rng_f = hi_f - lo_f
        for level in [0.236, 0.382, 0.500, 0.618, 0.786]:
            retrace = hi_f - rng_f * level
            pct_s = int(level * 1000)
            df[f'fib_{pct_s}_{fib_p}'] = (abs(closes - retrace) / rng_f.replace(0, np.nan) * 100 < 5).astype(int)

    # ── 市场状态 ──
    conditions = [
        (df['ma20'] > df['ma50']) & (df['ma50'] > df['ma200']),
        (df['ma20'] < df['ma50']) & (df['ma50'] < df['ma200']),
    ]
    df['market_regime'] = np.select(conditions, ['bull', 'bear'], default='sideways')
    regime_strength = df.get('adx_14', pd.Series(0, index=df.index))
    df['regime_strength'] = np.where(df['market_regime'] == 'sideways', 0,
                                     np.where(regime_strength > 25, 2, 1))

    # ── 时间特征 ──
    if isinstance(df.index, pd.DatetimeIndex):
        df['hour'] = df.index.hour
        df['minute'] = df.index.minute
        df['day_of_week'] = df.index.dayofweek
        df['is_monday'] = (df['day_of_week'] == 0).astype(int)
        df['is_friday'] = (df['day_of_week'] == 4).astype(int)
        df['is_month_start'] = (df.index.day < 5).astype(int)
        df['is_month_end'] = (df.index.day > 25).astype(int)
        def _session(h):
            if 0 <= h < 8: return "asia"
            elif 8 <= h < 13: return "europe"
            return "us"
        df['session'] = df.index.hour.map(_session)

    # ════════════════════════════════════════════════════
    # 最后一行用 indicators.py 保证一致性
    # ════════════════════════════════════════════════════
    try:
        import importlib
        spec = importlib.util.spec_from_file_location("indicators_mod",
            str(_SCRIPTS / "indicators.py"))
        ind_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ind_mod)
        core_last = ind_mod.compute_all_trading_indicators(bars_records)
        if core_last:
            for k, v in core_last.items():
                df.loc[df.index[-1], k] = v
    except Exception as e:
        log.warning("  ⚠️ 末行一致性覆盖失败: %s", e)

    return df


if __name__ == '__main__':
    log.info("=" * 60)
    log.info("批量全量指标预计算（Pandas 向量化快速路径）")
    log.info("=" * 60)

    for data_rel in ["research/kanban/high-rr-research/data"]:
        data_dir = BASE / data_rel
        if not data_dir.exists():
            log.warning("目录不存在: %s", data_dir)
            continue
        process_dataset(data_dir)

    log.info("✅ 全部完成")
