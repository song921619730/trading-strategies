#!/usr/bin/env python3
"""resume_m5.py — Resume M5 precompute for the 5 missing Yahoo Finance symbols."""
import sys, logging
from pathlib import Path
import pandas as pd, numpy as np

_SCRIPTS = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from indicators import compute_all_trading_indicators_vectorized

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("resume-m5")

DATA = Path(__file__).resolve().parent.parent / "data" / "M5"
MISSING = ['DXY','NZDUSD','USDCAD','XCUUSD','XNGUSD']

def compute_rsi(series, period):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

for i, sym in enumerate(MISSING):
    src = DATA / f"{sym}.parquet"
    out = DATA / f"{sym}_enhanced.parquet"
    if out.exists():
        log.info("[%d/5] SKIP %s (already exists)", i+1, sym)
        continue
    if not src.exists():
        log.warning("[%d/5] Missing raw: %s", i+1, sym)
        continue

    log.info("[%d/5] Loading %s...", i+1, sym)
    df = pd.read_parquet(src)
    if df.empty:
        log.warning("Empty: %s", sym)
        continue
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
    df = df.sort_index()

    if "volume" not in df.columns and "tick_volume" in df.columns:
        df["volume"] = df["tick_volume"]
    elif "volume" not in df.columns:
        df["volume"] = 0

    ts = df.index.asi8.copy()
    dt = str(df.index.dtype)
    if "ns" in dt: ts //= 10**9
    elif "us" in dt: ts //= 10**6
    elif "ms" in dt: ts //= 10**3
    df["time"] = ts

    # A. Core
    try:
        core_df = compute_all_trading_indicators_vectorized(df)
        dupes = [c for c in core_df.columns if c in df.columns]
        core_df = core_df.drop(columns=dupes)
        df = pd.concat([df, core_df], axis=1)
    except Exception as e:
        log.warning("Core failed for %s: %s", sym, e)

    closes = df["close"].values
    # Returns
    for p in [1,2,3,5,10,20]:
        df[f"return_{p}"] = df["close"].pct_change(p) * 100

    # Gaps
    df["gap_pct"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1).replace(0, np.nan) * 100
    df["gap_up"] = (df["gap_pct"] > 0.5).astype(int)
    df["gap_down"] = (df["gap_pct"] < -0.5).astype(int)

    # Shadows
    df["upper_shadow"] = df["high"] - df[["open","close"]].max(axis=1)
    df["lower_shadow"] = df[["open","close"]].min(axis=1) - df["low"]
    wick_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["wick_ratio"] = (df["upper_shadow"] + df["lower_shadow"]) / wick_range

    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift(1)).abs()
    lc = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    for ap in [7,14,21,30,50]:
        df[f"atr_{ap}"] = tr.rolling(ap).mean()
        af = df[f"atr_{ap}"].replace(0, np.nan)
        df[f"atr_pct_{ap}"] = af / df["close"] * 100
        df[f"atr_sma_ratio_{ap}"] = af / af.rolling(ap).mean().replace(0, np.nan)

    # Bollinger
    for bp in [20,50]:
        sma = df["close"].rolling(bp).mean()
        std = df["close"].rolling(bp).std()
        df[f"bb_upper_{bp}"] = sma + 2 * std
        df[f"bb_lower_{bp}"] = sma - 2 * std
        df[f"bb_width_{bp}"] = (df[f"bb_upper_{bp}"] - df[f"bb_lower_{bp}"]) / sma.replace(0, np.nan) * 100
        df[f"bb_position_{bp}"] = (df["close"] - sma) / (2 * std).replace(0, np.nan)

    # MA
    for mp in [5,10,20,50,100,200]:
        df[f"sma_{mp}"] = df["close"].rolling(mp).mean()
        df[f"ema_{mp}"] = df["close"].ewm(span=mp, adjust=False).mean()
        ma = df[f"sma_{mp}"]
        df[f"dist_sma_{mp}"] = (df["close"] - ma) / ma.replace(0, np.nan) * 100
        df[f"above_sma_{mp}"] = (df["close"] > ma).astype(int)

    # RSI / Momentum
    for mom_p in [5,10,14,20,30,50]:
        df[f"rsi_{mom_p}"] = compute_rsi(df["close"], mom_p)
        df[f"mom_{mom_p}"] = df["close"] - df["close"].shift(mom_p)
        df[f"mom_pct_{mom_p}"] = df["close"].pct_change(mom_p) * 100

    # MACD
    for f,s,sig in [(12,26,9),(8,21,5),(20,50,10)]:
        ef = df["close"].ewm(span=f, adjust=False).mean()
        es = df["close"].ewm(span=s, adjust=False).mean()
        macd = ef - es
        signal = macd.ewm(span=sig, adjust=False).mean()
        df[f"macd_{f}_{s}_{sig}"] = macd
        df[f"macd_signal_{f}_{s}_{sig}"] = signal
        df[f"macd_hist_{f}_{s}_{sig}"] = macd - signal

    # Volume
    df["volume_ma_5"] = df["volume"].rolling(5).mean()
    df["volume_ma_10"] = df["volume"].rolling(10).mean()
    df["volume_ma_20"] = df["volume"].rolling(20).mean()
    vma = df["volume_ma_20"].replace(0, np.nan)
    df["volume_ratio_20"] = df["volume"] / vma
    for p in [5,10,20]:
        df[f"volume_above_ma{p}"] = (df["volume"] > df[f"volume_ma_{p}"]).astype(int)

    # OBV
    obv = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()
    df["obv"] = obv
    for obv_p in [14,30]:
        df[f"obv_sma_{obv_p}"] = obv.rolling(obv_p).mean()
        df[f"obv_roc_{obv_p}"] = obv.pct_change(obv_p) * 100

    # Parabolic SAR
    def psar(df_, accel=0.02, max_accel=0.2):
        high, low, close = df_["high"].values, df_["low"].values, df_["close"].values
        n = len(close)
        sar = np.empty(n)
        sar.fill(np.nan)
        ep = np.empty(n)
        ep.fill(np.nan)
        af = np.empty(n)
        af.fill(np.nan)
        trend = np.empty(n, dtype=int)
        if n < 2: return sar
        trend[0] = 1 if close[0] > close[1] else -1
        if trend[0] == 1:
            sar[0] = low.min()
            ep[0] = high[0]
        else:
            sar[0] = high.max()
            ep[0] = low[0]
        af[0] = accel
        for i in range(1, n):
            prev_trend = trend[i-1]
            if prev_trend == 1:
                sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
                sar[i] = min(sar[i], low[i-1], low[i-2] if i>=2 else low[i-1])
                if low[i] < sar[i]:
                    trend[i] = -1
                    sar[i] = ep[i-1]
                    ep[i] = low[i]
                    af[i] = accel
                else:
                    trend[i] = 1
                    if high[i] > ep[i-1]:
                        ep[i] = high[i]
                        af[i] = min(af[i-1] + accel, max_accel)
                    else:
                        ep[i] = ep[i-1]
                        af[i] = af[i-1]
            else:
                sar[i] = sar[i-1] - af[i-1] * (sar[i-1] - ep[i-1])
                sar[i] = max(sar[i], high[i-1], high[i-2] if i>=2 else high[i-1])
                if high[i] > sar[i]:
                    trend[i] = 1
                    sar[i] = ep[i-1]
                    ep[i] = high[i]
                    af[i] = accel
                else:
                    trend[i] = -1
                    if low[i] < ep[i-1]:
                        ep[i] = low[i]
                        af[i] = min(af[i-1] + accel, max_accel)
                    else:
                        ep[i] = ep[i-1]
                        af[i] = af[i-1]
        return sar
    df["psar"] = psar(df)

    # ADX
    for adx_p in [7,14,21]:
        high, low, close = df["high"].values, df["low"].values, df["close"].values
        n = len(high)
        up_move = np.diff(high, prepend=high[0])
        down_move = np.diff(low, prepend=low[0]) * -1
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0).astype(float)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0).astype(float)
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = 0
        atr = pd.Series(tr).rolling(adx_p).mean().values
        atr_safe = np.where(atr == 0, np.nan, atr)
        plus_di = 100 * pd.Series(plus_dm).rolling(adx_p).mean().values / atr_safe
        minus_di = 100 * pd.Series(minus_dm).rolling(adx_p).mean().values / atr_safe
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        dx = np.where(np.isnan(dx), 0, dx)
        adx_vals = pd.Series(dx).rolling(adx_p).mean().values
        df[f"adx_{adx_p}"] = adx_vals
        df[f"plus_di_{adx_p}"] = plus_di
        df[f"minus_di_{adx_p}"] = minus_di

    # Pivot Points
    for pp_p in [1,5,10]:
        if len(df) < pp_p + 1: continue
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

    df.to_parquet(out)
    rows, cols = df.shape
    log.info("  ✅ Saved %s %dx%d", sym, rows, cols)

log.info("=" * 50)
log.info("M5 resume complete: %d symbols processed", len(MISSING))
