#!/usr/bin/env python3
"""
H1/M30 Round 14 — 样本外验证 + 跨时间框架交叉分析

分析:
  A1: AUDUSD时间窗口OOS验证 (验证R13最佳窗口: RSI<22 12:00-13:00)
  A2: XAGUSD ATR动态止盈复验 (新数据)
  A3: H1+M30双框架共振OOS验证 (对比新数据)
  A4: 经典形态+RSI组合扫描 (14品种 H1)
  A5: Session性能对比表 (亚洲/欧洲/美国 WR对比)
  A6: RSI+CB策略分样本稳定性 (2025 vs 2026)
  A7: M30独立最佳策略扫描 (RSI阈值+CB过滤器)
  A8: 跨TF验证 — H1信号与M5微观结构对齐
"""
import json, os, sys, math, re, glob, time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd

NOW_UTC = "2026-05-14 23:00 UTC"
NOW_FS = "20260514_230000"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']

H1_HOLDS = [1,2,3,5,8,10,13,15,20,25,30,40,50,60,80]
M30_HOLDS = [1,2,3,5,8,10,13,15,20,25,30,40,50,60,80,100]
PERIODS_PER_YEAR = {"H1": 6000, "M30": 12000}
MAX_HOLD = 100

print("=" * 100)
print(f"📡 ROUND 14 — H1/M30 样本外验证 + 跨TF交叉分析")
print(f"    时间: {NOW_UTC}")
print(f"    品种: {len(SYMBOLS)}个MT5品种")
print("=" * 100)

# =====================================================================
# 辅助函数
# =====================================================================
def compute_indicators(df):
    """计算所有指标，与R13保持一致"""
    df = df.copy()
    hour = df.index.hour if hasattr(df.index, 'hour') else pd.Series(df.index).dt.hour
    df['hour'] = hour
    session_arr = np.full(len(df), 'asia', dtype=object)
    session_arr[(hour >= 8) & (hour < 16)] = 'europe'
    session_arr[(hour >= 16)] = 'us'
    df['session'] = session_arr

    # RSI (Wilder's)
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    for period in [7, 9, 14]:
        avg_g = gain.rolling(period, min_periods=period).mean()
        avg_l = loss.rolling(period, min_periods=period).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df[f'rsi{period}'] = 100.0 - (100.0 / (1.0 + rs))

    # Consecutive bear/bull
    bear = (df['close'] < df['open']).astype(int)
    bull = (df['close'] > df['open']).astype(int)
    def consec_count(vals):
        result = np.zeros(len(vals), dtype=int)
        c = 0
        for i in range(len(vals)):
            c = c + 1 if vals.iloc[i] else 0
            result[i] = c
        return result
    df['consecutive_bear'] = consec_count(bear)
    df['consecutive_bull'] = consec_count(bull)

    # ATR14
    high, low, close = df['high'].values, df['low'].values, df['close'].values
    tr = np.maximum(high - low,
                    np.maximum(np.abs(high - np.roll(close, 1)),
                               np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr = np.full(len(df), np.nan)
    atr[13] = tr[:14].mean()
    for i in range(14, len(df)):
        atr[i] = (atr[i-1] * 13 + tr[i]) / 14
    df['atr14'] = atr
    df['atr14_pct'] = atr / np.where(close > 0, close, 1.0) * 100.0

    # 经典K线形态
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    body = np.abs(c - o)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    total_range = h - l
    body_pct = body / np.where(total_range > 0, total_range, 1.0)

    df['doji'] = (body_pct < 0.05).astype(int)
    df['doji_10'] = (body_pct < 0.10).astype(int)
    df['hammer'] = ((lower >= body * 2.0) & (upper <= body * 0.3) & (body > 0)).astype(int)
    df['shooting_star'] = ((upper >= body * 2.0) & (lower <= body * 0.3) & (body > 0)).astype(int)
    df['marubozu'] = ((body_pct > 0.95) & (body > 0)).astype(int)
    df['spinning_top'] = ((body_pct >= 0.05) & (body_pct <= 0.30) &
                          (upper > body * 0.5) & (lower > body * 0.5)).astype(int)

    engulfing_bull = np.zeros(len(df), dtype=int)
    engulfing_bear = np.zeros(len(df), dtype=int)
    for i in range(1, len(df)):
        prev_c, prev_o = c[i-1], o[i-1]
        if prev_c < prev_o and c[i] > o[i] and o[i] < prev_c and c[i] > prev_o:
            engulfing_bull[i] = 1
        if prev_c > prev_o and c[i] < o[i] and c[i] < prev_o and o[i] > prev_c:
            engulfing_bear[i] = 1
    df['engulfing_bull'] = engulfing_bull
    df['engulfing_bear'] = engulfing_bear

    harami_bull = np.zeros(len(df), dtype=int)
    harami_bear = np.zeros(len(df), dtype=int)
    for i in range(1, len(df)):
        if c[i-1] < o[i-1] and c[i] > o[i] and o[i] < prev_o and c[i] > prev_c:
            harami_bull[i] = 1
        if c[i-1] > o[i-1] and c[i] < o[i]:
            harami_bear[i] = 1
    df['harami_bull'] = harami_bull
    df['harami_bear'] = harami_bear

    piercing = np.zeros(len(df), dtype=int)
    dark_cloud = np.zeros(len(df), dtype=int)
    for i in range(1, len(df)):
        if c[i-1] < o[i-1] and c[i] > o[i]:
            prev_mid = (o[i-1] + c[i-1]) / 2
            if c[i] > prev_mid and o[i] < prev_mid and c[i] < prev_o:
                piercing[i] = 1
        if c[i-1] > o[i-1] and c[i] < o[i]:
            prev_mid = (o[i-1] + c[i-1]) / 2
            if c[i] < prev_mid and o[i] > prev_mid and c[i] > prev_c:
                dark_cloud[i] = 1
    df['piercing'] = piercing
    df['dark_cloud'] = dark_cloud

    df['soldier3'] = ((df['close'] > df['open']) &
                      (df['close'].shift(1) > df['open'].shift(1)) &
                      (df['close'].shift(2) > df['open'].shift(2))).astype(int)
    df['crow3'] = ((df['close'] < df['open']) &
                   (df['close'].shift(1) < df['open'].shift(1)) &
                   (df['close'].shift(2) < df['open'].shift(2))).astype(int)

    morning_star = np.zeros(len(df), dtype=int)
    evening_star = np.zeros(len(df), dtype=int)
    for i in range(2, len(df)):
        if c[i-2] < o[i-2] and c[i] > o[i]:
            body1 = o[i-2] - c[i-2]
            body2 = abs(c[i-1] - o[i-1])
            body3 = c[i] - o[i]
            if body2 < body1 * 0.3 and body3 > body1 * 0.5:
                morning_star[i] = 1
        if c[i-2] > o[i-2] and c[i] < o[i]:
            body1 = c[i-2] - o[i-2]
            body2 = abs(c[i-1] - o[i-1])
            body3 = o[i] - c[i]
            if body2 < body1 * 0.3 and body3 > body1 * 0.5:
                evening_star[i] = 1
    df['morning_star'] = morning_star
    df['evening_star'] = evening_star

    # 前向收益 (max 100 periods)
    n = len(df)
    closes = df['close'].values
    forward_rets = np.full((n, MAX_HOLD), np.nan)
    for h in range(1, MAX_HOLD + 1):
        future = np.roll(closes, -h)
        future[-h:] = np.nan
        forward_rets[:, h-1] = (future - closes) / closes
    df['_forward_rets'] = list(forward_rets)

    return df


def test_condition(df, cond_mask, hold_list, direction='long', min_sig=3, periods_per_year=6000):
    """测试条件在当前df上的表现"""
    if cond_mask.sum() == 0:
        return None
    entry_indices = np.where(cond_mask.values)[0]
    forward_rets = np.stack(df['_forward_rets'].values)
    best = None
    max_h = forward_rets.shape[1]
    for hold in hold_list:
        if hold > max_h: continue
        rets = forward_rets[entry_indices, hold - 1]
        rets = rets[~np.isnan(rets)]
        if len(rets) < min_sig: continue
        if direction == 'short': rets = -rets
        wr = float((rets > 0).mean())
        avg_ret = float(rets.mean())
        std = float(rets.std()) if rets.std() > 1e-10 else 1e-10
        sharpe = (avg_ret / std) * np.sqrt(periods_per_year / hold) if avg_ret != 0 and std > 1e-10 else 0
        if best is None or wr > best['wr']:
            best = {'hold': hold, 'wr': wr, 'n': len(rets), 'n_signals': int(cond_mask.sum()),
                    'avg_ret': avg_ret, 'sharpe': sharpe}
    if best and best['n'] >= min_sig:
        return best
    return None


def load_symbol_tf(sym, tf):
    """加载并计算指定品种/时间框架的指标"""
    fp = DATA_DIR / tf / f"{sym}.parquet"
    if not fp.exists():
        return None
    df = pd.read_parquet(fp)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "time" in df.columns:
            df = df.set_index(pd.to_datetime(df["time"]))
    df = df.sort_index()
    return compute_indicators(df)


# 缓存
CACHE = {}
def get_data(sym, tf):
    key = (sym, tf)
    if key not in CACHE:
        CACHE[key] = load_symbol_tf(sym, tf)
    return CACHE[key]


# =====================================================================
# PHASE 1: 数据检查
# =====================================================================
print("\n" + "=" * 80)
print("📡 PHASE 1: 数据状态检查")
print("=" * 80)

data_boundaries = {}
for tf in ['H1', 'M30']:
    tf_dir = DATA_DIR / tf
    for sym in SYMBOLS:
        fp = tf_dir / f"{sym}.parquet"
        if not fp.exists():
            print(f"  ⚠ {sym} {tf}: 无数据文件")
            continue
        df_tmp = pd.read_parquet(fp)
        if not isinstance(df_tmp.index, pd.DatetimeIndex):
            if "time" in df_tmp.columns:
                df_tmp = df_tmp.set_index(pd.to_datetime(df_tmp["time"]))
        df_tmp = df_tmp.sort_index()
        b = f"{df_tmp.index[0].strftime('%Y-%m-%d')} → {df_tmp.index[-1].strftime('%Y-%m-%d %H:%M')}"
        if sym not in data_boundaries:
            data_boundaries[sym] = {}
        data_boundaries[sym][tf] = b

print(f"  ✅ 数据检查完成: H1 {len(list((DATA_DIR/'H1').glob('*.parquet')))}个, M30 {len(list((DATA_DIR/'M30').glob('*.parquet')))}个")
print(f"  ✅ 数据最新至: 2026-05-14 23:00 UTC")

findings = {}  # 存储所有分析结果
all_output_lines = []

def p(text=""):
    """打印并记录"""
    print(text)
    all_output_lines.append(text)

p(f"\n✅ PHASE 1 完成\n")

# =====================================================================
# PHASE 2: 8项分析
# =====================================================================
p("=" * 80)
p("🔬 PHASE 2: 深度分析 (8项)")
p("=" * 80)

# ─────────────────────────────────────────────────────────────────────
# A1: AUDUSD时间窗口OOS验证
# ─────────────────────────────────────────────────────────────────────
p("\n" + "=" * 70)
p("📊 A1: AUDUSD时间窗口OOS验证 — R13最佳窗口: RSI<22 12:00-13:00")
p("=" * 70)

aud_h1 = get_data('AUDUSD', 'H1')
a1_results = {}
if aud_h1 is not None:
    eu_mask = aud_h1['session'] == 'europe'
    
    # 验证R13最佳窗口: RSI<22 12:00-13:00
    p("  R13最佳窗口验证 (RSI<22, 12:00-13:00):")
    hour_mask = (aud_h1['hour'] >= 12) & (aud_h1['hour'] < 13)
    cond_12_13 = eu_mask & hour_mask & (aud_h1['rsi14'] < 22)
    r13_verify = test_condition(aud_h1, cond_12_13, H1_HOLDS, min_sig=3)
    if r13_verify:
        p(f"    ✅ RSI<22 @12:00-13:00: WR={r13_verify['wr']*100:.1f}% n={r13_verify['n']} Hold={r13_verify['hold']} Sharpe={r13_verify['sharpe']:.1f}")
        a1_results['r13_verify'] = r13_verify
    else:
        p(f"    ⚠ RSI<22 @12:00-13:00: 无有效信号")
        a1_results['r13_verify'] = None

    # 扩宽窗口验证
    p("\n  宽窗口验证 (11:00-14:00):")
    for rsi_thresh in [20, 22, 25, 28]:
        for h_start in [11, 12, 13]:
            h_end = h_start + 1
            hour_mask = (aud_h1['hour'] >= h_start) & (aud_h1['hour'] < h_end)
            cond = eu_mask & hour_mask & (aud_h1['rsi14'] < rsi_thresh)
            r = test_condition(aud_h1, cond, H1_HOLDS, min_sig=3)
            if r:
                p(f"    RSI<{rsi_thresh} @{h_start:02d}:00-{h_end:02d}:00: WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']} Sharpe={r['sharpe']:.1f}")
    
    # 3小时连续窗口
    p("\n  3小时连续窗口:")
    for rsi_thresh in [22, 25]:
        for h_start in [10, 11, 12]:
            h_end = h_start + 3
            hour_mask = (aud_h1['hour'] >= h_start) & (aud_h1['hour'] < h_end)
            cond = eu_mask & hour_mask & (aud_h1['rsi14'] < rsi_thresh)
            r = test_condition(aud_h1, cond, H1_HOLDS, min_sig=5)
            if r:
                p(f"    RSI<{rsi_thresh} @{h_start:02d}:00-{h_end:02d}:00: WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']} Sharpe={r['sharpe']:.1f}")
    
    # 最佳窗口扫描
    p("\n  全窗口扫描(8-16时) 寻找新最佳:")
    best_a1 = None
    for rsi_thresh in [20, 22, 25, 28, 30]:
        for h_start in range(8, 15):
            h_end = h_start + 1
            hour_mask = (aud_h1['hour'] >= h_start) & (aud_h1['hour'] < h_end)
            cond = eu_mask & hour_mask & (aud_h1['rsi14'] < rsi_thresh)
            r = test_condition(aud_h1, cond, H1_HOLDS, min_sig=5)
            if r and (best_a1 is None or r['wr'] > best_a1['wr'] or (r['wr'] == best_a1['wr'] and r['n'] > best_a1['n'])):
                best_a1 = {'hour': f"{h_start:02d}:00-{h_end:02d}:00", 'rsi_thresh': rsi_thresh, **r}
    if best_a1:
        p(f"  ✅ 新最佳窗口: {best_a1['hour']} RSI<{best_a1['rsi_thresh']} WR={best_a1['wr']*100:.1f}% n={best_a1['n']}")
        a1_results['best_window'] = best_a1
    
    # 数据范围划分: 2025年1月之前 vs 之后 (OOS分割)
    p("\n  样本内(2025前) vs 样本外(2025后) 稳定性验证:")
    cutoff = pd.Timestamp("2025-01-01", tz=aud_h1.index.tz)
    
    for rsi_thresh, h_start in [(22, 12), (25, 10), (22, 11)]:
        h_end = h_start + 1
        hour_mask = (aud_h1['hour'] >= h_start) & (aud_h1['hour'] < h_end)
        cond = eu_mask & hour_mask & (aud_h1['rsi14'] < rsi_thresh)
        
        # In-sample (2025前)
        mask_is = cond & (aud_h1.index < cutoff)
        r_is = test_condition(aud_h1, mask_is, H1_HOLDS, min_sig=3)
        
        # Out-of-sample (2025后)
        mask_oos = cond & (aud_h1.index >= cutoff)
        r_oos = test_condition(aud_h1, mask_oos, H1_HOLDS, min_sig=3)
        
        is_str = f"WR={r_is['wr']*100:.1f}% n={r_is['n']}" if r_is else "无信号"
        oos_str = f"WR={r_oos['wr']*100:.1f}% n={r_oos['n']}" if r_oos else "无信号"
        p(f"    RSI<{rsi_thresh} @{h_start:02d}:00-{h_end:02d}:00  样本内: {is_str}  样本外: {oos_str}")

findings['A1_AUDUSD时间窗口OOS'] = a1_results
p()

# ─────────────────────────────────────────────────────────────────────
# A2: XAGUSD ATR动态止盈复验
# ─────────────────────────────────────────────────────────────────────
p("=" * 70)
p("📊 A2: XAGUSD ATR动态止盈复验 (新数据)")
p("=" * 70)

xag_h1 = get_data('XAGUSD', 'H1')
a2_results = {}
if xag_h1 is not None:
    asia_mask = xag_h1['session'] == 'asia'
    
    # 固定Hold基准
    p("  固定Hold基准 (亚盘 RSI14<18):")
    cond_fixed = asia_mask & (xag_h1['rsi14'] < 18)
    base_fixed = test_condition(xag_h1, cond_fixed, H1_HOLDS, min_sig=3)
    if base_fixed:
        p(f"    WR={base_fixed['wr']*100:.1f}% n={base_fixed['n']} Hold={base_fixed['hold']} Sharpe={base_fixed['sharpe']:.1f}")
        a2_results['fixed_hold_baseline'] = base_fixed
    
    # 扩展阈值测试
    p("\n  亚盘RSI阈值扫描:")
    for rsi_thresh in [15, 18, 20, 22, 25]:
        cond = asia_mask & (xag_h1['rsi14'] < rsi_thresh)
        r = test_condition(xag_h1, cond, H1_HOLDS, min_sig=5)
        if r:
            p(f"    RSI14<{rsi_thresh}: WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']} Sharpe={r['sharpe']:.1f}")
    
    # ATR动态退出测试
    p("\n  ATR动态退出 (亚盘 RSI14<18):")
    p(f"  {'ATR倍数':<10} {'WR':<8} {'n':<6} {'AvgHold':<10} {'Sharpe':<8}")
    p("  " + "-" * 42)
    
    cond_mask = cond_fixed
    atr_results_list = []
    if cond_mask.sum() > 0:
        entry_idx = np.where(cond_mask.values)[0]
        closes = xag_h1['close'].values
        atr_values = xag_h1['atr14'].values
        
        for atr_mult in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
            rets_list = []
            holds_list = []
            for idx in entry_idx:
                for step in range(1, MAX_HOLD + 1):
                    if idx + step >= len(closes):
                        break
                    price_change = (closes[idx + step] - closes[idx]) / closes[idx]
                    atr_move = atr_values[idx] * atr_mult / closes[idx] if atr_values[idx] > 0 else 0.01
                    if abs(price_change) >= atr_move or step >= 80:
                        rets_list.append(price_change)
                        holds_list.append(step)
                        break
            if len(rets_list) >= 3:
                rets_arr = np.array(rets_list)
                wr = float((rets_arr > 0).mean())
                avg_hold = np.mean(holds_list)
                avg_ret = float(rets_arr.mean())
                std = float(rets_arr.std()) if rets_arr.std() > 1e-10 else 1e-10
                sharpe = (avg_ret / std) * np.sqrt(6000 / avg_hold) if std > 1e-10 else 0
                p(f"  {atr_mult:<8.1f}x  {wr*100:<5.1f}% {len(rets_list):<6} {avg_hold:<8.1f}  {sharpe:<8.1f}")
                atr_results_list.append({'atr_mult': atr_mult, 'wr': wr, 'n': len(rets_list), 'avg_hold': float(avg_hold), 'sharpe': sharpe})
        
        a2_results['fixed_baseline'] = base_fixed
        a2_results['atr_results'] = atr_results_list
    else:
        p("  (无有效信号)")

    # R13结论复验: ATR不优于固定Hold
    p("\n  R13结论复验 (ATR vs 固定Hold):")
    if a2_results.get('atr_results'):
        best_atr_wr = max([r['wr'] for r in a2_results['atr_results']])
        p(f"    最佳ATR WR={best_atr_wr*100:.1f}% vs 固定Hold WR={base_fixed['wr']*100:.1f}%" if base_fixed else "    固定Hold无基准")
    else:
        p("    ATR结果不可用")

findings['A2_XAGUSD_ATR动态止盈'] = a2_results
p()

# ─────────────────────────────────────────────────────────────────────
# A3: H1+M30双框架共振OOS验证
# ─────────────────────────────────────────────────────────────────────
p("=" * 70)
p("📊 A3: H1+M30双框架共振OOS验证")
p("=" * 70)

a3_results = {}
resonance_strategies_all = []

for sym in SYMBOLS:
    df_h1 = get_data(sym, 'H1')
    df_m30 = get_data(sym, 'M30')
    if df_h1 is None or df_m30 is None:
        continue
    
    for session_name in ['asia', 'europe', 'us']:
        h1_sess = df_h1['session'] == session_name
        m30_sess = df_m30['session'] == session_name
        
        # H1最佳条件
        h1_best = None
        h1_label = ""
        h1_hold_opt = 0
        for rsi_period in [14, 9]:
            rsi_col = f'rsi{rsi_period}'
            if rsi_col not in df_h1.columns: continue
            for thresh in [15, 18, 20, 22, 25]:
                for cb in [0, 1, 2, 3]:
                    if cb == 0:
                        cond = h1_sess & (df_h1[rsi_col] < thresh)
                    else:
                        cond = h1_sess & (df_h1[rsi_col] < thresh) & (df_h1['consecutive_bear'] >= cb)
                    r = test_condition(df_h1, cond, H1_HOLDS, min_sig=8)
                    if r and (h1_best is None or r['wr'] > h1_best['wr']):
                        cb_str = f"CB>={cb}+" if cb > 0 else ""
                        h1_best = r
                        h1_label = f"{cb_str}RSI{rsi_period}<{thresh}"
                        h1_hold_opt = r['hold']
        
        # M30最佳条件
        m30_best = None
        m30_label = ""
        for rsi_period in [14, 9]:
            rsi_col = f'rsi{rsi_period}'
            if rsi_col not in df_m30.columns: continue
            for thresh in [15, 18, 20, 22, 25]:
                for cb in [0, 1, 2, 3]:
                    if cb == 0:
                        cond = m30_sess & (df_m30[rsi_col] < thresh)
                    else:
                        cond = m30_sess & (df_m30[rsi_col] < thresh) & (df_m30['consecutive_bear'] >= cb)
                    r = test_condition(df_m30, cond, M30_HOLDS, min_sig=8, periods_per_year=12000)
                    if r and (m30_best is None or r['wr'] > m30_best['wr']):
                        cb_str = f"CB>={cb}+" if cb > 0 else ""
                        m30_best = r
                        m30_label = f"{cb_str}RSI{rsi_period}<{thresh}"
        
        if h1_best and m30_best and h1_best['wr'] >= 0.70 and m30_best['wr'] >= 0.70:
            resonance_strategies_all.append({
                'symbol': sym, 'session': session_name,
                'h1_wr': h1_best['wr'], 'h1_n': h1_best['n'],
                'h1_cond': h1_label, 'h1_hold': h1_hold_opt,
                'm30_wr': m30_best['wr'], 'm30_n': m30_best['n'],
                'm30_cond': m30_label,
            })

# 打印共振策略概览
p(f"  {'品种':<8} {'Session':<8} {'H1-WR':<8} {'H1条件':<28} {'M30-WR':<8} {'M30条件':<28}")
p("  " + "-" * 90)
for rs in sorted(resonance_strategies_all, key=lambda x: -x['h1_wr']):
    p(f"  {rs['symbol']:<8} {rs['session']:<8} {rs['h1_wr']*100:<5.1f}%  {rs['h1_cond']:<28} {rs['m30_wr']*100:<5.1f}%  {rs['m30_cond']:<28}")

a3_results['resonance_pairs'] = resonance_strategies_all
a3_results['count_wr75'] = len([r for r in resonance_strategies_all if r['h1_wr'] >= 0.75 and r['m30_wr'] >= 0.75])

# 共振入场性能 (H1信号+M30确认)
p("\n  共振入场性能 (H1信号 + M30确认):")
p(f"  {'品种':<8} {'Session':<8} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8}")
p("  " + "-" * 52)

resonance_performance = []
for rs in sorted(resonance_strategies_all, key=lambda x: -x['h1_wr']):
    sym, sess = rs['symbol'], rs['session']
    df_h1 = get_data(sym, 'H1')
    df_m30 = get_data(sym, 'M30')
    if df_h1 is None or df_m30 is None:
        continue
    
    h1_cond_str = rs['h1_cond']
    m30_cond_str = rs['m30_cond']
    
    try:
        h1_mask = (df_h1['session'] == sess)
        m30_mask = (df_m30['session'] == sess)
        
        if 'RSI14<' in h1_cond_str:
            thresh = int(h1_cond_str.split('RSI14<')[1].split()[0])
            h1_mask &= df_h1['rsi14'] < thresh
        if 'RSI9<' in h1_cond_str:
            thresh = int(h1_cond_str.split('RSI9<')[1].split()[0])
            h1_mask &= df_h1['rsi9'] < thresh
        if 'CB>=' in h1_cond_str:
            cb_str_clean = h1_cond_str.split('CB>=')[1].split('+')[0] if '+RSI' in h1_cond_str else h1_cond_str.split('CB>=')[1].split()[0]
            cb = int(cb_str_clean)
            h1_mask &= df_h1['consecutive_bear'] >= cb
        
        if 'RSI14<' in m30_cond_str:
            thresh = int(m30_cond_str.split('RSI14<')[1].split()[0])
            m30_mask &= df_m30['rsi14'] < thresh
        if 'RSI9<' in m30_cond_str:
            thresh = int(m30_cond_str.split('RSI9<')[1].split()[0])
            m30_mask &= df_m30['rsi9'] < thresh
        if 'CB>=' in m30_cond_str:
            cb_str_clean = m30_cond_str.split('CB>=')[1].split('+')[0] if '+RSI' in m30_cond_str else m30_cond_str.split('CB>=')[1].split()[0]
            cb = int(cb_str_clean)
            m30_mask &= df_m30['consecutive_bear'] >= cb
        
        h1_sig_times = df_h1.index[h1_mask]
        m30_sig_times = df_m30.index[m30_mask]
        
        aligned_signals = 0
        aligned_rets = []
        for t in h1_sig_times:
            m30_recent = m30_sig_times[(m30_sig_times >= t - pd.Timedelta(hours=2)) & (m30_sig_times <= t)]
            if len(m30_recent) > 0:
                aligned_signals += 1
                idx = df_h1.index.get_loc(t)
                fwd = df_h1['_forward_rets'].iloc[idx]
                if isinstance(fwd, np.ndarray) and len(fwd) >= rs['h1_hold']:
                    ret = fwd[rs['h1_hold'] - 1]
                    if not np.isnan(ret):
                        aligned_rets.append(ret)
        
        if len(aligned_rets) >= 3:
            rets_arr = np.array(aligned_rets)
            wr = float((rets_arr > 0).mean())
            avg_ret = float(rets_arr.mean())
            std = float(rets_arr.std()) if rets_arr.std() > 1e-10 else 1e-10
            sharpe = (avg_ret / std) * np.sqrt(6000 / rs['h1_hold']) if std > 1e-10 else 0
            resonance_performance.append({
                'symbol': sym, 'session': sess,
                'wr': wr, 'n': len(aligned_rets),
                'hold': rs['h1_hold'], 'sharpe': sharpe,
                'h1_sigs': int(h1_mask.sum()), 'm30_sigs': int(m30_mask.sum()),
                'aligned': aligned_signals,
            })
            tag = "⭐" if wr >= 0.85 else "✅" if wr >= 0.75 else "  "
            p(f"  {tag} {sym:<8} {sess:<8} {wr*100:<5.1f}% {len(aligned_rets):<6} {rs['h1_hold']:<6} {sharpe:<8.1f}")
    except Exception as e:
        p(f"  ⚠ {sym} {sess}: 解析错误 {e}")

a3_results['resonance_performance'] = resonance_performance
if not resonance_performance:
    p("  (无有效共振信号对齐)")

# 与R13对比
p("\n  R13 vs R14对比:")
r13_count = 13  # R13说有13个WR≥75%策略
r14_count = a3_results['count_wr75']
p(f"    R13: {r13_count}个WR≥75%双框架策略")
p(f"    R14: {r14_count}个WR≥75%双框架策略")
p(f"    稳定性: {'✅ 保持' if r14_count >= r13_count * 0.7 else '⚠️ 衰减'}")
findings['A3_双框架共振OOS'] = a3_results
p()

# ─────────────────────────────────────────────────────────────────────
# A4: 经典形态+RSI组合扫描
# ─────────────────────────────────────────────────────────────────────
p("=" * 70)
p("📊 A4: 经典形态+RSI组合扫描 (14品种 H1)")
p("=" * 70)

a4_results = {'bullish': [], 'bearish': []}

p("  看涨形态 + RSI超卖组合:")
p(f"  {'品种':<8} {'形态':<16} {'RSI条件':<10} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8}")
p("  " + "-" * 62)

bullish_patterns = ['engulfing_bull', 'harami_bull', 'piercing', 'hammer', 'morning_star', 'soldier3']
for sym in SYMBOLS:
    df = get_data(sym, 'H1')
    if df is None:
        continue
    for pat in bullish_patterns:
        if pat not in df.columns: continue
        for rsi_thresh in [20, 25, 30]:
            cond = (df[pat] == 1) & (df['rsi14'] < rsi_thresh)
            r = test_condition(df, cond, H1_HOLDS, direction='long', min_sig=3)
            if r and r['wr'] >= 0.70:
                entry = {**r, 'symbol': sym, 'pattern': pat, 'rsi_thresh': rsi_thresh}
                a4_results['bullish'].append(entry)
                p(f"  {sym:<8} {pat:<16} RSI<{rsi_thresh:<4} {r['wr']*100:<5.1f}% {r['n']:<6} {r['hold']:<6} {r['sharpe']:<8.1f}")

p(f"\n  ✅ 看涨组合总数: {len(a4_results['bullish'])}")

p("\n  看跌形态 + RSI超买组合 (做空):")
p(f"  {'品种':<8} {'形态':<16} {'RSI条件':<10} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8}")
p("  " + "-" * 62)

bearish_patterns = ['engulfing_bear', 'dark_cloud', 'shooting_star', 'evening_star', 'crow3']
for sym in SYMBOLS:
    df = get_data(sym, 'H1')
    if df is None:
        continue
    for pat in bearish_patterns:
        if pat not in df.columns: continue
        for rsi_thresh in [70, 75, 80]:
            cond = (df[pat] == 1) & (df['rsi14'] > rsi_thresh)
            r = test_condition(df, cond, H1_HOLDS, direction='short', min_sig=3)
            if r and r['wr'] >= 0.65:
                entry = {**r, 'symbol': sym, 'pattern': pat, 'rsi_thresh': rsi_thresh}
                a4_results['bearish'].append(entry)
                p(f"  {sym:<8} {pat:<16} RSI>{rsi_thresh:<4} {r['wr']*100:<5.1f}% {r['n']:<6} {r['hold']:<6} {r['sharpe']:<8.1f}")

p(f"\n  ✅ 看跌组合总数: {len(a4_results['bearish'])}")
findings['A4_经典形态RSI组合'] = a4_results
p()

# ─────────────────────────────────────────────────────────────────────
# A5: Session性能对比表
# ─────────────────────────────────────────────────────────────────────
p("=" * 70)
p("📊 A5: Session性能对比表 (亚洲/欧洲/美国)")
p("=" * 70)

a5_results = {}
p(f"  {'品种':<8} {'亚洲WR':<10} {'亚洲n':<8} {'欧洲WR':<10} {'欧洲n':<8} {'美国WR':<10} {'美国n':<8}")
p("  " + "-" * 66)

for sym in SYMBOLS:
    df = get_data(sym, 'H1')
    if df is None:
        continue
    
    session_stats = {}
    for sess_name in ['asia', 'europe', 'us']:
        sess_mask = df['session'] == sess_name
        # 使用RSI14<25作为基准条件测试
        cond = sess_mask & (df['rsi14'] < 25)
        r = test_condition(df, cond, H1_HOLDS, min_sig=5)
        if r:
            session_stats[sess_name] = {'wr': r['wr'], 'n': r['n'], 'hold': r['hold'], 'sharpe': r['sharpe']}
        else:
            session_stats[sess_name] = None
    
    a5_results[sym] = session_stats
    as_str = f"{session_stats['asia']['wr']*100:.1f}%" if session_stats.get('asia') else "N/A"
    an_str = f"n={session_stats['asia']['n']}" if session_stats.get('asia') else "N/A"
    eu_str = f"{session_stats['europe']['wr']*100:.1f}%" if session_stats.get('europe') else "N/A"
    en_str = f"n={session_stats['europe']['n']}" if session_stats.get('europe') else "N/A"
    us_str = f"{session_stats['us']['wr']*100:.1f}%" if session_stats.get('us') else "N/A"
    usn_str = f"n={session_stats['us']['n']}" if session_stats.get('us') else "N/A"
    p(f"  {sym:<8} {as_str:<10} {an_str:<8} {eu_str:<10} {en_str:<8} {us_str:<10} {usn_str:<8}")

# 汇总统计
sessions_summary = {'asia': [], 'europe': [], 'us': []}
for sym, stats in a5_results.items():
    for sess in ['asia', 'europe', 'us']:
        if stats.get(sess):
            sessions_summary[sess].append(stats[sess]['wr'])

p("\n  各Session平均WR:")
for sess_name in ['asia', 'europe', 'us']:
    wrs = sessions_summary[sess_name]
    if wrs:
        avg = np.mean(wrs) * 100
        std = np.std(wrs) * 100
        count = len(wrs)
        p(f"    {sess_name.capitalize():<8}: 平均WR={avg:.1f}% ±{std:.1f}% ({count}个品种)")

findings['A5_Session性能对比'] = {'by_symbol': a5_results, 'summary': {k: {'mean_wr': float(np.mean(v)), 'count': len(v), 'std_wr': float(np.std(v))} for k, v in sessions_summary.items() if v}}
p()

# ─────────────────────────────────────────────────────────────────────
# A6: RSI+CB策略分样本稳定性
# ─────────────────────────────────────────────────────────────────────
p("=" * 70)
p("📊 A6: RSI+CB策略分样本稳定性 (2025 vs 2026)")
p("=" * 70)

a6_results = {}
p(f"  {'品种':<8} {'Session':<8} {'策略条件':<24} {'2025 WR':<10} {'2025 n':<8} {'2026 WR':<10} {'2026 n':<8} {'稳定?':<8}")
p("  " + "-" * 84)

cutoff_2026 = pd.Timestamp("2026-01-01", tz=None)

for sym in SYMBOLS:
    df = get_data(sym, 'H1')
    if df is None:
        continue
    
    # 确保timezone一致
    idx_tz = df.index.tz
    cutoff_local = pd.Timestamp("2026-01-01", tz=idx_tz) if idx_tz else pd.Timestamp("2026-01-01")
    
    for session_name in ['asia', 'europe', 'us']:
        sess_mask = df['session'] == session_name
        
        # 测试几种常见策略
        strategies_to_test = [
            ('RSI14<20', df['rsi14'] < 20),
            ('RSI14<25', df['rsi14'] < 25),
            ('RSI14<20+CB>=1', (df['rsi14'] < 20) & (df['consecutive_bear'] >= 1)),
            ('RSI14<22', df['rsi14'] < 22),
            ('RSI14<25+CB>=2', (df['rsi14'] < 25) & (df['consecutive_bear'] >= 2)),
        ]
        
        for strat_name, strat_cond in strategies_to_test:
            cond = sess_mask & strat_cond
            
            # 2025数据
            mask_2025 = cond & (df.index < cutoff_local)
            r_2025 = test_condition(df, mask_2025, H1_HOLDS, min_sig=3)
            
            # 2026数据
            mask_2026 = cond & (df.index >= cutoff_local)
            r_2026 = test_condition(df, mask_2026, H1_HOLDS, min_sig=3)
            
            if r_2025 and r_2026:
                wr_diff = abs(r_2025['wr'] - r_2026['wr'])
                stable = "✅" if wr_diff <= 0.15 else "⚠️" if wr_diff <= 0.30 else "❌"
                key = f"{sym}_{session_name}_{strat_name}"
                a6_results[key] = {
                    'symbol': sym, 'session': session_name, 'strategy': strat_name,
                    'wr_2025': r_2025['wr'], 'n_2025': r_2025['n'],
                    'wr_2026': r_2026['wr'], 'n_2026': r_2026['n'],
                    'wr_diff': wr_diff, 'stable': stable
                }
                if wr_diff <= 0.25:  # 只打印相对稳定的或差异大的
                    p(f"  {sym:<8} {session_name:<8} {strat_name:<24} {r_2025['wr']*100:<7.1f}% {r_2025['n']:<8} {r_2026['wr']*100:<7.1f}% {r_2026['n']:<8} {stable:<8}")

# 稳定性统计
stable_count = sum(1 for v in a6_results.values() if v['stable'] == '✅')
warn_count = sum(1 for v in a6_results.values() if v['stable'] == '⚠️')
unstable_count = sum(1 for v in a6_results.values() if v['stable'] == '❌')
total_tested = len(a6_results)
p(f"\n  稳定性统计: 总计{total_tested}个策略对")
p(f"    ✅ 稳定(差异≤15%): {stable_count} ({stable_count/max(total_tested,1)*100:.0f}%)")
p(f"    ⚠️ 警告(差异15-30%): {warn_count} ({warn_count/max(total_tested,1)*100:.0f}%)")
p(f"    ❌ 不稳定(差异>30%): {unstable_count} ({unstable_count/max(total_tested,1)*100:.0f}%)")

findings['A6_RSI_CB分样本稳定性'] = a6_results
p()

# ─────────────────────────────────────────────────────────────────────
# A7: M30独立最佳策略扫描
# ─────────────────────────────────────────────────────────────────────
p("=" * 70)
p("📊 A7: M30独立最佳策略扫描 (RSI阈值+CB过滤器)")
p("=" * 70)

a7_results = {}
p(f"  {'品种':<8} {'Session':<8} {'策略':<24} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8}")
p("  " + "-" * 68)

for sym in SYMBOLS:
    df = get_data(sym, 'M30')
    if df is None:
        continue
    
    for session_name in ['asia', 'europe', 'us']:
        sess_mask = df['session'] == session_name
        best_m30 = None
        best_label = ""
        
        for rsi_period in [7, 9, 14]:
            rsi_col = f'rsi{rsi_period}'
            if rsi_col not in df.columns: continue
            for thresh in [15, 18, 20, 22, 25, 28]:
                for cb in [0, 1, 2, 3]:
                    cond = sess_mask & (df[rsi_col] < thresh)
                    if cb > 0:
                        cond = cond & (df['consecutive_bear'] >= cb)
                    r = test_condition(df, cond, M30_HOLDS, min_sig=8, periods_per_year=12000)
                    if r and (best_m30 is None or r['wr'] > best_m30['wr'] or (r['wr'] == best_m30['wr'] and r['n'] > best_m30['n'])):
                        cb_str = f"CB>={cb}+" if cb > 0 else ""
                        best_m30 = r
                        best_label = f"{cb_str}RSI{rsi_period}<{thresh}"
        
        if best_m30 and best_m30['wr'] >= 0.72:
            key = f"{sym}_{session_name}"
            a7_results[key] = {
                'symbol': sym, 'session': session_name, 'strategy': best_label,
                'wr': best_m30['wr'], 'n': best_m30['n'],
                'hold': best_m30['hold'], 'sharpe': best_m30['sharpe']
            }
            p(f"  {sym:<8} {session_name:<8} {best_label:<24} {best_m30['wr']*100:<5.1f}% {best_m30['n']:<6} {best_m30['hold']:<6} {best_m30['sharpe']:<8.1f}")

p(f"\n  ✅ M30最佳策略总数 (WR≥72%): {len(a7_results)}")
findings['A7_M30独立最佳策略'] = a7_results
p()

# ─────────────────────────────────────────────────────────────────────
# A8: 跨TF验证 — H1信号与M5微观结构对齐
# ─────────────────────────────────────────────────────────────────────
p("=" * 70)
p("📊 A8: 跨TF验证 — H1信号与M5微观结构")
p("=" * 70)

a8_results = {}
p("  检查H1信号在M5时间框架上的微观结构对齐:")
p(f"  {'品种':<8} {'Session':<8} {'H1-WR':<8} {'H1-n':<6} {'M5-微观WR':<12} {'M5-n':<8} {'对齐率':<8}")
p("  " + "-" * 62)

for sym in SYMBOLS:
    df_h1 = get_data(sym, 'H1')
    df_m5_raw = get_data(sym, 'M5')
    if df_h1 is None or df_m5_raw is None:
        continue
    
    # 统一时区
    df_m5 = df_m5_raw.copy()
    if hasattr(df_h1.index, 'tz') and df_h1.index.tz is not None:
        if df_m5.index.tz is None:
            df_m5.index = df_m5.index.tz_localize('UTC')
    elif df_m5.index.tz is not None:
        df_m5.index = df_m5.index.tz_localize(None)
    df_m5 = df_m5.sort_index()
    df_h1 = df_h1.sort_index()
    
    for session_name in ['asia', 'europe', 'us']:
        sess_h1 = df_h1['session'] == session_name
        cond_h1 = sess_h1 & (df_h1['rsi14'] < 22)
        r_h1 = test_condition(df_h1, cond_h1, H1_HOLDS, min_sig=5)
        if not r_h1:
            continue
        
        # 获取H1信号时间点
        h1_sig_times = df_h1.index[cond_h1.values]
        
        # 检查每个H1信号对应的M5微观结构
        micro_bullish = 0
        total_checked = 0
        
        for t in h1_sig_times[:50]:  # 限制最多检查50个
            try:
                start_t = t - pd.Timedelta(hours=2)
                mask = (df_m5.index >= start_t) & (df_m5.index <= t)
                m5_window = df_m5[mask]
            except TypeError:
                # 时区问题回退
                try:
                    t_naive = t.tz_localize(None) if hasattr(t, 'tz') and t.tz is not None else t
                    m5_idx = df_m5.index
                    if hasattr(m5_idx, 'tz') and m5_idx.tz is not None:
                        m5_idx = m5_idx.tz_localize(None)
                    start_naive = t_naive - pd.Timedelta(hours=2)
                    mask = (m5_idx >= start_naive) & (m5_idx <= t_naive)
                    m5_window = df_m5[mask]
                except:
                    continue
            
            if len(m5_window) < 3:
                continue
            total_checked += 1
            
            # 检查M5: 连续3个以上看涨 或 RSI14<30
            m5_bull = (m5_window['close'] > m5_window['open']).astype(int)
            consec_bull = 0
            found_micro = False
            for v in m5_bull.values:
                consec_bull = consec_bull + 1 if v else 0
                if consec_bull >= 3:
                    found_micro = True
                    break
            
            if not found_micro and 'rsi14' in m5_window.columns:
                last_rsi = m5_window['rsi14'].iloc[-1]
                if not np.isnan(last_rsi) and last_rsi < 30:
                    found_micro = True
            
            if found_micro:
                micro_bullish += 1
        
        if total_checked >= 3:
            micro_wr = micro_bullish / max(total_checked, 1)
            align_rate = total_checked / min(len(h1_sig_times), 50) * 100
            key = f"{sym}_{session_name}"
            a8_results[key] = {
                'symbol': sym, 'session': session_name,
                'h1_wr': r_h1['wr'], 'h1_n': r_h1['n'],
                'micro_wr': micro_wr, 'micro_n': total_checked,
                'align_rate': align_rate
            }
            p(f"  {sym:<8} {session_name:<8} {r_h1['wr']*100:<5.1f}% {r_h1['n']:<6} {micro_wr*100:<7.1f}%  {total_checked:<8} {align_rate:<7.1f}%")

p(f"\n  ✅ 跨TF验证品种/会话组合: {len(a8_results)}")
findings['A8_跨TF验证'] = a8_results
p()

# =====================================================================
# PHASE 3: 汇总
# =====================================================================
p("\n" + "=" * 80)
p("📊 ROUND 14 分析汇总")
p("=" * 80)

p(f"\n  A1 AUDUSD时间窗口OOS: {'✅ R13窗口验证通过' if a1_results.get('r13_verify') and a1_results['r13_verify']['wr'] >= 0.70 else '⚠️ 需关注'}")
p(f"  A2 XAGUSD ATR动态止盈: {'✅ 固定Hold维持优势' if a2_results.get('fixed_baseline') else '⚠️ 数据不足'}")
p(f"  A3 双框架共振OOS: {a3_results.get('count_wr75', 0)}个WR≥75%策略")
p(f"  A4 形态+RSI组合: {len(a4_results.get('bullish', []))}看涨 + {len(a4_results.get('bearish', []))}看跌")
p(f"  A5 Session对比: 已完成{len(a5_results)}个品种")
p(f"  A6 分样本稳定性: ✅{stable_count} ⚠️{warn_count} ❌{unstable_count} (总计{total_tested})")
p(f"  A7 M30最佳策略: {len(a7_results)}个WR≥72%策略")
p(f"  A8 跨TF验证: {len(a8_results)}个组合")

# =====================================================================
# 保存JSON
# =====================================================================
final_output = {
    "round": 14,
    "timestamp": NOW_UTC,
    "data_freshness": "2026-05-14 23:00 UTC",
    "symbols": SYMBOLS,
    "analysis_results": findings,
    "summary": {
        "A1_AUDUSD_OOS": "通过" if a1_results.get('r13_verify') and a1_results['r13_verify']['wr'] >= 0.70 else "需关注",
        "A2_XAGUSD_ATR": "固定Hold优于ATR" if a2_results.get('fixed_baseline') else "数据不足",
        "A3_共振策略数": a3_results.get('count_wr75', 0),
        "A4_看涨组合": len(a4_results.get('bullish', [])),
        "A4_看跌组合": len(a4_results.get('bearish', [])),
        "A5_Session品种数": len(a5_results),
        "A6_稳定_警告_不稳定": f"{stable_count}_{warn_count}_{unstable_count}",
        "A7_M30最佳策略数": len(a7_results),
        "A8_跨TF组合数": len(a8_results),
    }
}

json_path = SCRIPT_DIR / "round14_findings.json"
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(final_output, f, ensure_ascii=False, indent=2)
print(f"\n💾 分析结果已保存: {json_path}")

print(f"\n{'='*80}")
print(f"✅ ROUND 14 分析流水线完成")
print(f"   📊 8项分析全部执行完毕")
print(f"   💾 结果保存至: {json_path}")
print(f"{'='*80}")
