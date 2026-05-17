#!/usr/bin/env python3
"""
Round 32 — H1/M30 K线形态综合研究
首次全面使用 H1 和 M30 时间框架数据
目标: 发现 H1/M30 时间框架下的高胜率 K 线组合形态

品种范围: 期货外汇 (严禁A股)
时间框架: H1, M30
数据范围: 2026-01 ~ 2026-05 (约3.5月)
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def add_session(df):
    df = df.copy()
    df['session'] = 'asia'
    df.loc[(df.index.hour >= 8) & (df.index.hour < 13), 'session'] = 'europe'
    df.loc[(df.index.hour >= 13) & (df.index.hour < 22), 'session'] = 'us'
    bear = (df['close'] < df['open']).astype(int)
    df['consecutive_bear'] = bear.groupby((bear == 0).cumsum()).cumsum()
    bull = (df['close'] > df['open']).astype(int)
    df['consecutive_bull'] = bull.groupby((bull == 0).cumsum()).cumsum()
    return df

def get_stats(df, mask, hold):
    entries = df[mask]
    hits, total, count = 0, 0.0, 0
    for idx, row in entries.iterrows():
        pos = df.index.get_loc(idx)
        if pos + hold < len(df):
            pnl = (df.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            total += pnl
            count += 1
            if pnl > 0: hits += 1
    return count, hits/count*100 if count else 0, total/count if count else 0

def test_pattern(df, cond, label, hold_list, min_sig=5):
    entries = df[cond].copy()
    n = len(entries)
    print(f"  {label:<50} n={n:<5}", end="")
    if n < min_sig:
        print(f" 跳过(<{min_sig})")
        return None
    best = {'hold': 0, 'wr': 0, 'avg': 0}
    for hold in hold_list:
        cnt, wr, avg = get_stats(df, cond, hold)
        if cnt >= 3 and wr > best['wr']:
            best = {'hold': hold, 'wr': wr, 'avg': avg, 'n': cnt}
    if best['wr'] >= 60:
        print(f" hold={best['hold']:3d} WR={best['wr']:.1f}% n={best['n']} avg={best['avg']:.3f}% ✅")
    else:
        print(f" hold={best['hold']:3d} WR={best['wr']:.1f}% n={best['n']} avg={best['avg']:.3f}%")
    return best

# ═══════════════════════════════════════════════════════════════
# PATTERN DETECTION FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def detect_doji(df, body_pct=0.1):
    """十字星: 实体小于总范围的 body_pct"""
    body = abs(df['close'] - df['open'])
    total = df['high'] - df['low']
    return (body / total.replace(0, np.nan)) < body_pct

def detect_inside_bar(df):
    """Inside Bar: 当前最高<前高 且 当前最低>前低"""
    return (df['high'] < df['high'].shift(1)) & (df['low'] > df['low'].shift(1))

def detect_engulfing_bull(df):
    """看涨吞没: 前阴后阳 且 阳包阴"""
    prev_bear = df['close'].shift(1) < df['open'].shift(1)
    curr_bull = df['close'] > df['open']
    engulf = (df['close'] > df['open'].shift(1)) & (df['open'] < df['close'].shift(1))
    return prev_bear & curr_bull & engulf

def detect_engulfing_bear(df):
    """看跌吞没: 前阳后阴 且 阴包阳"""
    prev_bull = df['close'].shift(1) > df['open'].shift(1)
    curr_bear = df['close'] < df['open']
    engulf = (df['open'] > df['close'].shift(1)) & (df['close'] < df['open'].shift(1))
    return prev_bull & curr_bear & engulf

def detect_tweezer_top(df, tol=0.001):
    """钳子顶: 连续两个K线最高价近似相等"""
    return (abs(df['high'] - df['high'].shift(1)) / df['high'].shift(1) < tol) & \
           (df['close'].shift(1) > df['open'].shift(1)) & \
           (df['close'] < df['open'])

def detect_tweezer_bottom(df, tol=0.001):
    """钳子底: 连续两个K线最低价近似相等"""
    return (abs(df['low'] - df['low'].shift(1)) / df['low'].shift(1) < tol) & \
           (df['close'].shift(1) < df['open'].shift(1)) & \
           (df['close'] > df['open'])

def detect_evening_star(df):
    """黄昏星: 大阳→小实体→大阴"""
    big_bull = (df['close'] - df['open']) > (df['high'] - df['low']) * 0.6
    small_body = abs(df['close'] - df['open']) / (df['high'] - df['low']).replace(0, np.nan) < 0.3
    big_bear = (df['open'] - df['close']) > (df['high'] - df['low']) * 0.6
    return big_bull.shift(2) & small_body.shift(1) & big_bear

def detect_morning_star(df):
    """晨星: 大阴→小实体→大阳"""
    big_bear = (df['open'] - df['close']) > (df['high'] - df['low']) * 0.6
    small_body = abs(df['close'] - df['open']) / (df['high'] - df['low']).replace(0, np.nan) < 0.3
    big_bull = (df['close'] - df['open']) > (df['high'] - df['low']) * 0.6
    return big_bear.shift(2) & small_body.shift(1) & big_bull

def detect_three_black_crows(df):
    """三只乌鸦: 连续三根大阴线"""
    bear1 = (df['close'].shift(2) < df['open'].shift(2)) & ((df['open'].shift(2) - df['close'].shift(2)) > 0)
    bear2 = (df['close'].shift(1) < df['open'].shift(1)) & ((df['open'].shift(1) - df['close'].shift(1)) > 0)
    bear3 = (df['close'] < df['open']) & ((df['open'] - df['close']) > 0)
    return bear1 & bear2 & bear3

def detect_three_white_soldiers(df):
    """三白兵: 连续三根大阳线"""
    bull1 = (df['close'].shift(2) > df['open'].shift(2)) & ((df['close'].shift(2) - df['open'].shift(2)) > 0)
    bull2 = (df['close'].shift(1) > df['open'].shift(1)) & ((df['close'].shift(1) - df['open'].shift(1)) > 0)
    bull3 = (df['close'] > df['open']) & ((df['close'] - df['open']) > 0)
    return bull1 & bull2 & bull3

def detect_hammer(df, body_pct=0.3, lower_wig_pct=0.6):
    """锤子线: 下影线很长, 实体在上部"""
    body = abs(df['close'] - df['open'])
    total = df['high'] - df['low']
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    return (body / total.replace(0, np.nan) < body_pct) & \
           (lower_shadow / total.replace(0, np.nan) > lower_wig_pct) & \
           (upper_shadow / total.replace(0, np.nan) < 0.1)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 110)
print("ROUND 32 — H1/M30 K线形态综合研究")
print(f"日期: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"品种: 期货外汇 (14个品种)")
print(f"时间框架: H1 / M30")
print(f"数据范围: ~2026-01 至 2026-05 (约3.5个月)")
print("=" * 110)

# ── Load H1 and M30 data ──
results = {}

for tf in ["H1", "M30"]:
    print(f"\n{'='*110}")
    print(f"📊 {tf} 时间框架")
    print(f"{'='*110}")
    
    all_data = {}
    for sym in ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
                "US30", "US500", "USTEC", "JP225", "HK50", "UKOIL", "USOIL"]:
        raw = load_data(tf, symbols=[sym])
        if raw:
            df = compute_indicators(raw[sym])
            df = add_session(df)
            all_data[sym] = df
            print(f"  {sym:8s}: {len(df):>5} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
                  f"Close={df['close'].iloc[-1]:.1f}  RSI={df['rsi14'].iloc[-1]:.1f}")
        else:
            print(f"  ⚠️  {sym}: 数据不可用")

    if not all_data:
        print(f"  ⚠️  {tf} 无可用数据，跳过")
        continue

    results[tf] = all_data

    # ── Pattern frequency analysis ──
    print(f"\n--- 形态频率分布 ({tf}) ---")
    pattern_funcs = {
        'doji': detect_doji,
        'inside_bar': detect_inside_bar,
        'engulfing_bull': detect_engulfing_bull,
        'engulfing_bear': detect_engulfing_bear,
        'tweezer_top': detect_tweezer_top,
        'tweezer_bottom': detect_tweezer_bottom,
        'evening_star': detect_evening_star,
        'morning_star': detect_morning_star,
        'three_black_crows': detect_three_black_crows,
        'three_white_soldiers': detect_three_white_soldiers,
        'hammer': detect_hammer,
    }
    
    freq_table = {}
    for sym, df in all_data.items():
        for pname, pfunc in pattern_funcs.items():
            count = pfunc(df).sum()
            freq_table.setdefault(pname, {})[sym] = count / max(1, len(df)) * 100
    
    print(f"  {'形态':<22} {'均频率%':<10} {'最高品种':<12} {'最高%':<10} {'最低品种':<12} {'最低%':<10}")
    print(f"  {'-'*22} {'-'*10} {'-'*12} {'-'*10} {'-'*12} {'-'*10}")
    for pname in sorted(freq_table.keys()):
        vals = freq_table[pname]
        avg = np.mean(list(vals.values()))
        best_sym = max(vals, key=vals.get)
        best_val = vals[best_sym]
        worst_sym = min(vals, key=vals.get)
        worst_val = vals[worst_sym]
        print(f"  {pname:<22} {avg:.2f}%{'':>6} {best_sym:<12} {best_val:.2f}%{'':>4} {worst_sym:<12} {worst_val:.2f}%")

    # ── Session breakdown ──
    print(f"\n--- 交易时段分析 ({tf}) ---")
    session_stats = {}
    for sym, df in all_data.items():
        for sess in ['asia', 'europe', 'us']:
            sess_df = df[df['session'] == sess]
            session_stats.setdefault(sess, {})[sym] = len(sess_df)
    for sess in ['asia', 'europe', 'us']:
        counts = list(session_stats.get(sess, {}).values())
        if counts:
            print(f"  {sess:8s}: avg={np.mean(counts):.0f} min={min(counts)} max={max(counts)}")

    # ── Pattern + RSI + Session testing ──
    print(f"\n--- 形态+RSI+Session 综合测试 ({tf}) ---")
    
    hold_short = list(range(1, 25, 1))   # short-term H1/M30 holds
    hold_medium = list(range(25, 121, 5))  # medium-term
    
    best_findings = []
    
    for sym, df in all_data.items():
        # ── Doji + RSI extreme ──
        doji = detect_doji(df)
        for rsi_thresh, direction, label_suffix in [(75, 'short', 'RSI>75'), (25, 'long', 'RSI<25')]:
            if direction == 'short':
                cond = doji & (df['rsi14'] > rsi_thresh)
                hold_range = hold_short + hold_medium
            else:
                cond = doji & (df['rsi14'] < rsi_thresh)
                hold_range = hold_short + hold_medium
            res = test_pattern(df, cond, f"Doji+{label_suffix} {sym}", hold_range, min_sig=3)
            if res and res['wr'] >= 60:
                best_findings.append((f"Doji+{label_suffix} {sym} {tf}", res['wr'], res['n'], res['hold'], res['avg']))

        # ── Doji + RSI extreme + Session ──
        for rsi_thresh, direction, label_suffix in [(75, 'short', 'RSI>75'), (25, 'long', 'RSI<25')]:
            for sess in ['us', 'europe']:
                sess_mask = df['session'] == sess
                if direction == 'short':
                    cond = doji & sess_mask & (df['rsi14'] > rsi_thresh)
                else:
                    cond = doji & sess_mask & (df['rsi14'] < rsi_thresh)
                res = test_pattern(df, cond, f"Doji+{label_suffix}+{sess} {sym}", hold_range, min_sig=3)
                if res and res['wr'] >= 65:
                    best_findings.append((f"Doji+{label_suffix}+{sess} {sym} {tf}", res['wr'], res['n'], res['hold'], res['avg']))

        # ── Inside Bar + RSI ──
        inside = detect_inside_bar(df)
        for rsi_thresh, direction in [(75, 'short'), (25, 'long')]:
            if direction == 'short':
                cond = inside & (df['rsi14'] > rsi_thresh)
            else:
                cond = inside & (df['rsi14'] < rsi_thresh)
            res = test_pattern(df, cond, f"InsideBar+RSI>{rsi_thresh if direction=='short' else '<'+str(rsi_thresh)} {sym}", hold_range, min_sig=3)
            if res and res['wr'] >= 60:
                best_findings.append((f"InsideBar+RSI{'<' if direction=='long' else '>'}{rsi_thresh} {sym} {tf}", res['wr'], res['n'], res['hold'], res['avg']))

        # ── Engulfing + RSI ──
        engulf_bull = detect_engulfing_bull(df)
        engulf_bear = detect_engulfing_bear(df)
        for cond, direction, name in [
            (engulf_bull & (df['rsi14'] < 30), 'long', 'EngulfingBull+RSI<30'),
            (engulf_bear & (df['rsi14'] > 70), 'short', 'EngulfingBear+RSI>70'),
        ]:
            res = test_pattern(df, cond, f"{name} {sym}", hold_range, min_sig=3)
            if res and res['wr'] >= 60:
                best_findings.append((f"{name} {sym} {tf}", res['wr'], res['n'], res['hold'], res['avg']))

        # ── Tweezer Top/Bottom + RSI ──
        tt = detect_tweezer_top(df)
        tb = detect_tweezer_bottom(df)
        for cond, direction, name in [
            (tt & (df['rsi14'] > 70), 'short', 'TweezerTop+RSI>70'),
            (tb & (df['rsi14'] < 30), 'long', 'TweezerBottom+RSI<30'),
        ]:
            res = test_pattern(df, cond, f"{name} {sym}", hold_range, min_sig=3)
            if res and res['wr'] >= 60:
                best_findings.append((f"{name} {sym} {tf}", res['wr'], res['n'], res['hold'], res['avg']))

        # ── Evening/Morning Star ──
        es = detect_evening_star(df)
        ms = detect_morning_star(df)
        for cond, name in [
            (es, 'EveningStar'),
            (ms, 'MorningStar'),
        ]:
            res = test_pattern(df, cond, f"{name} {sym}", hold_range, min_sig=3)
            if res and res['wr'] >= 60:
                best_findings.append((f"{name} {sym} {tf}", res['wr'], res['n'], res['hold'], res['avg']))

        # ── Three Black Crows / Three White Soldiers ──
        tbc = detect_three_black_crows(df)
        tws = detect_three_white_soldiers(df)
        for cond, name in [
            (tbc, 'ThreeBlackCrows'),
            (tws, 'ThreeWhiteSoldiers'),
        ]:
            res = test_pattern(df, cond, f"{name} {sym}", hold_range, min_sig=3)
            if res and res['wr'] >= 60:
                best_findings.append((f"{name} {sym} {tf}", res['wr'], res['n'], res['hold'], res['avg']))

        # ── Hammer + RSI ──
        hammer = detect_hammer(df)
        for cond, name in [
            (hammer & (df['rsi14'] < 30), 'Hammer+RSI<30 (long)'),
            (hammer & (df['rsi14'] > 70), 'Hammer+RSI>70 (short)'),
        ]:
            res = test_pattern(df, cond, f"{name} {sym}", hold_range, min_sig=3)
            if res and res['wr'] >= 60:
                best_findings.append((f"{name} {sym} {tf}", res['wr'], res['n'], res['hold'], res['avg']))

        # ── Consecutive bear + RSI extreme (oversold bounce) ──
        for cb_thresh in [3, 4, 5]:
            for rsi_thresh in [20, 25, 30]:
                cond = (df['consecutive_bear'] >= cb_thresh) & (df['rsi14'] < rsi_thresh)
                res = test_pattern(df, cond, f"CB>={cb_thresh}+RSI<{rsi_thresh} {sym} long", hold_medium, min_sig=3)
                if res and res['wr'] >= 65:
                    best_findings.append((f"CB>={cb_thresh}+RSI<{rsi_thresh} {sym} long {tf}", res['wr'], res['n'], res['hold'], res['avg']))
        
        for cb_thresh in [3, 4, 5]:
            for rsi_thresh in [70, 75, 80]:
                cond = (df['consecutive_bull'] >= cb_thresh) & (df['rsi14'] > rsi_thresh)
                res = test_pattern(df, cond, f"CBull>={cb_thresh}+RSI>{rsi_thresh} {sym} short", hold_medium, min_sig=3)
                if res and res['wr'] >= 65:
                    best_findings.append((f"CBull>={cb_thresh}+RSI>{rsi_thresh} {sym} short {tf}", res['wr'], res['n'], res['hold'], res['avg']))

    # ── Best findings ranking ──
    print(f"\n--- 🏆 {tf} 最佳发现排名 (WR≥60%, n≥3) ---")
    if best_findings:
        best_findings.sort(key=lambda x: x[1], reverse=True)
        print(f"  {'排名':<5} {'策略':<55} {'WR':<8} {'n':<6} {'Hold':<8} {'avg%':<10}")
        print(f"  {'-'*5} {'-'*55} {'-'*8} {'-'*6} {'-'*8} {'-'*10}")
        for i, (name, wr, n, hold, avg) in enumerate(best_findings, 1):
            print(f"  {i:<5} {name:<55} {wr:.1f}%{'':>3} {n:<6} {hold:<8} {avg:.3f}%")
        
        # Saved to report data
        results[f'{tf}_best'] = best_findings
    else:
        print(f"  (无符合条件的发现)")
        results[f'{tf}_best'] = []

# ═══════════════════════════════════════════════════════════════
# CROSS-TIMEFRAME COMPARISON
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*110}")
print("📊 H1 vs M30 跨时间框架对比")
print(f"{'='*110}")

h1_best = results.get('H1_best', [])
m30_best = results.get('M30_best', [])

# Find overlapping patterns
h1_names = set(r[0] for r in h1_best)
m30_names = set(r[0] for r in m30_best)
overlap = h1_names & m30_names
print(f"\n  H1有效策略数: {len(h1_best)}")
print(f"  M30有效策略数: {len(m30_best)}")
print(f"  跨框架重叠数: {len(overlap)}")

# ═══════════════════════════════════════════════════════════════
# FREQUENCY STATISTICS SUMMARY
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*110}")
print("📊 全品种形态频率统计汇总")
print(f"{'='*110}")

for tf in ["H1", "M30"]:
    print(f"\n--- {tf} 形态频率 (全品种平均) ---")
    if tf not in results:
        continue
    all_data = results[tf]
    
    pattern_funcs = {
        'inside_bar': detect_inside_bar,
        'doji': detect_doji,
        'engulfing_bull': detect_engulfing_bull,
        'engulfing_bear': detect_engulfing_bear,
        'tweezer_top': detect_tweezer_top,
        'tweezer_bottom': detect_tweezer_bottom,
        'evening_star': detect_evening_star,
        'morning_star': detect_morning_star,
        'three_black_crows': detect_three_black_crows,
        'three_white_soldiers': detect_three_white_soldiers,
        'hammer': detect_hammer,
    }
    
    print(f"  {'形态':<22} {'平均频率%':<12} {'范围%':<20}")
    print(f"  {'-'*22} {'-'*12} {'-'*20}")
    
    for pname, pfunc in sorted(pattern_funcs.items()):
        freqs = []
        for sym, df in all_data.items():
            total = max(1, len(df))
            freqs.append(pfunc(df).sum() / total * 100)
        if freqs:
            print(f"  {pname:<22} {np.mean(freqs):.2f}%{'':>8} {min(freqs):.2f}% ~ {max(freqs):.2f}%")

# ═══════════════════════════════════════════════════════════════
# SESSION DISTRIBUTION
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*110}")
print("📊 交易时段分布")
print(f"{'='*110}")

for tf in ["H1", "M30"]:
    if tf not in results:
        continue
    all_data = results[tf]
    print(f"\n--- {tf} ---")
    print(f"  {'品种':<10} {'亚洲':<10} {'欧洲':<10} {'美国':<10} {'总计':<10}")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for sym in sorted(all_data.keys()):
        df = all_data[sym]
        asia = (df['session'] == 'asia').sum()
        europe = (df['session'] == 'europe').sum()
        us = (df['session'] == 'us').sum()
        print(f"  {sym:<10} {asia:<10} {europe:<10} {us:<10} {len(df):<10}")

print(f"\n{'='*110}")
print("ROUND 32 COMPLETE")
print(f"Completed at: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Next: 分析结果并生成报告")
print("=" * 110)
