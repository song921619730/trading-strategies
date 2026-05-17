#!/usr/bin/env python3
"""
Round 68 Runner — 快速版，跳过 Aroon 等慢速指标
直接使用 batch_precompute 的核心计算但不包括 Aroon
"""
import sys, os, json, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# ── 路径 ──
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"

# ── 注册 futures/scripts 到 sys.path ──
_FUTURES_SCRIPTS = str(HERE.parent.parent.parent.parent / "scripts")
if _FUTURES_SCRIPTS not in sys.path:
    sys.path.insert(0, _FUTURES_SCRIPTS)

from indicators import compute_all_trading_indicators

PERIODS_PER_YEAR = {"M1": 360000, "M5": 72000, "M30": 12000, "H1": 6000}

NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def load_data(timeframe="M5", symbols=None, max_rows=None):
    """加载数据（支持 max_rows 截断）"""
    tf_dir = DATA_DIR / timeframe
    if not tf_dir.exists():
        print(f"  ⚠ 目录不存在: {tf_dir}")
        return {}
    if symbols is None:
        symbols = sorted([p.stem for p in tf_dir.glob("*.parquet") if not p.stem.endswith("_enhanced")])
    result = {}
    for sym in symbols:
        fp = tf_dir / f"{sym}.parquet"
        if not fp.exists():
            continue
        try:
            df = pd.read_parquet(fp)
            if df.empty:
                continue
            if not isinstance(df.index, pd.DatetimeIndex):
                if "time" in df.columns:
                    df["time"] = pd.to_datetime(df["time"])
                    df = df.set_index("time")
            df = df.sort_index()
            if max_rows and len(df) > max_rows:
                df = df.iloc[-max_rows:]
            required = ["open", "high", "low", "close"]
            if not all(c in df.columns for c in required):
                continue
            result[sym] = df
            print(f"  ✅ 加载 {sym} {timeframe}: {len(df)} 行 [{df.index[0]} → {df.index[-1]}]")
        except Exception as e:
            print(f"  ⚠ 加载失败 {sym}: {e}")
    return result


def compute_indicators_fast(df):
    """快速计算指标（跳过 Aroon 等慢步骤）"""
    df = df.copy()
    if 'tick_volume' in df.columns and 'volume' not in df.columns:
        df['volume'] = df['tick_volume']
    if 'volume' not in df.columns:
        df['volume'] = 0

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
    for period in [20, 50, 100, 200]:
        df[f'close_vs_ma{period}'] = (closes - df[f'ma{period}']) / df[f'ma{period}'].replace(0, np.nan) * 100
    for pair in [(5, 20), (10, 30), (20, 50), (50, 200)]:
        fn, sn = f'ma{pair[0]}', f'ma{pair[1]}'
        df[f'ma{pair[0]}_above_ma{pair[1]}'] = (df[fn] > df[sn]).astype(int)
    short_mas = [df[f'ma{p}'] for p in [3, 5, 8, 10, 13, 20]]
    long_mas = [df[f'ma{p}'] for p in [30, 34, 50, 55, 89, 100, 144, 200]]
    df['guppy_short_spread'] = pd.concat(short_mas, axis=1).max(axis=1) - pd.concat(short_mas, axis=1).min(axis=1)
    df['guppy_long_spread'] = pd.concat(long_mas, axis=1).max(axis=1) - pd.concat(long_mas, axis=1).min(axis=1)
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

    # ── 跳过 Aroon（太慢）──
    # for ar_p in ... 跳过

    # ── Choppiness ──
    for chop_p in [10, 14, 30, 50]:
        hi_ch = highs.rolling(chop_p).max()
        lo_ch = lows.rolling(chop_p).min()
        tr_sum = tr.rolling(chop_p).sum()
        df[f'chop_{chop_p}'] = (np.log(tr_sum / (hi_ch - lo_ch).replace(0, np.nan)) / np.log(chop_p)) * 100
    df['choppy'] = (df['chop_14'] > 61.8).astype(int)

    # ── Volume ──
    for vp in [5, 10, 20]:
        vs = vols.rolling(vp).sum()
        df[f'volume_sma_{vp}'] = vs / vp
        df[f'volume_ratio_{vp}'] = vols / (vs / vp).replace(0, np.nan)
    df['volume_spike'] = (df['volume_ratio_5'] > 2.0).astype(int)
    df['volume_drop'] = (df['volume_ratio_5'] < 0.5).astype(int)

    # ── Consecutive bars ──
    df['consecutive_bear'] = (closes.diff() < 0).astype(int).groupby(
        (closes.diff() >= 0).astype(int).cumsum()).cumsum() + 1
    df['consecutive_bull'] = (closes.diff() > 0).astype(int).groupby(
        (closes.diff() <= 0).astype(int).cumsum()).cumsum() + 1

    # ── Session labels (基于小时) ──
    hour = df.index.hour
    df['session'] = 'closed'
    df.loc[(hour >= 0) & (hour < 9), 'session'] = 'asia'
    df.loc[(hour >= 9) & (hour < 15), 'session'] = 'europe'
    df.loc[(hour >= 15) & (hour < 24), 'session'] = 'us'

    return df


def run_grid(config):
    """简化版 grid_engine"""
    tf = config["timeframe"]
    symbols = config["symbols"]
    entry_condition = config.get("entry_condition", "")
    direction = config.get("direction", "long")
    hold_periods = config.get("hold_periods", [1, 3, 5, 10])
    max_rows = config.get("max_rows", None)
    
    periods_per_year = PERIODS_PER_YEAR.get(tf, 72000)
    if not entry_condition:
        return {}
    
    data = load_data(timeframe=tf, symbols=symbols, max_rows=max_rows)
    results = {}
    for sym, raw_df in data.items():
        print(f"    ⟳ 计算 {sym} {tf} 指标...")
        t0 = time.time()
        df = compute_indicators_fast(raw_df)
        t1 = time.time()
        print(f"    ✅ 指标完成: {df.shape[1]} 列 ({t1-t0:.1f}s)")
        
        try:
            mask = df.eval(entry_condition)
        except Exception as e:
            print(f"    ⚠ 条件评估失败: {e}")
            continue
        
        entry_prices = df.loc[mask, "close"].values
        entry_indices = df.index[mask]
        
        if len(entry_prices) < 5:
            print(f"    ℹ️  仅 {len(entry_prices)} 个信号，跳过")
            continue
        
        sym_results = []
        for hold in hold_periods:
            returns = []
            for i in range(len(entry_indices)):
                entry_idx = entry_indices[i]
                entry_price = entry_prices[i]
                raw_pos = df.index.get_loc(entry_idx)
                pos = raw_pos.start if isinstance(raw_pos, slice) else int(raw_pos)
                exit_pos = pos + hold
                if exit_pos >= len(df):
                    continue
                exit_price = df.iloc[exit_pos]["close"]
                if direction == "long":
                    ret = (exit_price - entry_price) / entry_price
                else:
                    ret = (entry_price - exit_price) / entry_price
                returns.append(ret)
            
            returns_arr = np.array(returns, dtype=float)
            stats = _compute_stats(returns_arr, hold, periods_per_year)
            stats["hold_period"] = hold
            sym_results.append(stats)
        
        if sym_results:
            results[sym] = sym_results
            best = max(sym_results, key=lambda r: r["win_rate"])
            print(f"    🏆 {sym}: best hold={best['hold_period']} WR={best['win_rate']*100:.1f}% n={best['n']} Sharpe={best['sharpe_ratio']:.2f}")
    
    return results


def _compute_stats(returns, hold_period, periods_per_year):
    n = len(returns)
    if n < 5:
        return {"n": n, "win_rate": 0.0, "avg_return": 0.0, "sharpe_ratio": 0.0, "max_drawdown": 0.0}
    win_rate = float((returns > 0).mean())
    avg_return = float(returns.mean())
    std = float(returns.std()) if returns.std() > 0 else 1e-10
    sharpe = (avg_return / std) * np.sqrt(periods_per_year / hold_period)
    cum = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cum)
    dd = (peak - cum) / peak
    max_dd = float(dd.max())
    return {"n": n, "win_rate": win_rate, "avg_return": avg_return, "sharpe_ratio": sharpe, "max_drawdown": max_dd}


# ════════════════════════════════════════════════════════════
# 以下直接复制自 round68_test.py
# ════════════════════════════════════════════════════════════

def print_best_table(name_results_map, prev_refs=None, min_n=3):
    header = f"| {'Strategy':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} | {'Ref':<20} |"
    sep = f"|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->9}|{':':->20}|"
    print(header)
    print(sep)
    for name in sorted(name_results_map.keys()):
        results = name_results_map[name]
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n:
                wr = f"{best['win_rate']*100:.1f}%"
                ar = f"{best['avg_return']*100:.3f}%"
                prev = prev_refs.get(name, "") if prev_refs else ""
                print(f"| {name:<35} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} | {prev:<20} |")


def collect_best(name_results_map, min_n=10, min_wr=0.70):
    findings = []
    for name, results in name_results_map.items():
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n and best["win_rate"] >= min_wr:
                findings.append((name, sym, best))
    return sorted(findings, key=lambda x: -x[2]["win_rate"])


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 直接执行 round68_test.py 内容
    exec(open("round68_test.py").read().replace(
        "from grid_engine import run_grid", 
        "# from grid_engine import run_grid  # using local run_grid"
    ).replace(
        "from data_loader import load_data, compute_indicators, list_available_symbols",
        "# from data_loader import ... # using local versions"
    ).replace(
        "import pandas as pd", "import pandas as pd  # already imported"
    ).replace(
        "import numpy as np", "import numpy as np  # already imported"
    ))
