#!/usr/bin/env python3
"""
Round 77 — H1/M30 K线形态深度研究（高效版）
时间框架: H1 / M30 | 品种: 全部14个MT5品种
"""
import sys, os, json, time, gc
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(SCRIPT_DIR)  # scripts/.. = scalping-m1/
DATA_DIR = os.path.join(BASE, 'data')
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']

H1_HOLDS = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50]
M30_HOLDS = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50, 60, 80]

# ── 轻量级 indicator 计算 ──
def fast_indicators(df):
    """只计算需要的指标：rsi14, rsi7, rsi9, 连续阴阳线, session"""
    df = df.copy()
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values
    
    # RSI14
    delta = np.diff(closes)
    gains = np.where(delta > 0, delta, 0).astype(float)
    losses = np.where(delta < 0, -delta, 0).astype(float)
    
    rsi14 = np.full(len(closes), np.nan)
    rsi7 = np.full(len(closes), np.nan)
    rsi9 = np.full(len(closes), np.nan)
    
    for period, arr in [(14, rsi14), (7, rsi7), (9, rsi9)]:
        avg_gain = np.full(len(closes), np.nan)
        avg_loss = np.full(len(closes), np.nan)
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])
        for j in range(period+1, len(closes)):
            avg_gain[j] = (avg_gain[j-1] * (period-1) + gains[j-1]) / period
            avg_loss[j] = (avg_loss[j-1] * (period-1) + losses[j-1]) / period
        rs = avg_gain / np.maximum(avg_loss, 1e-10)
        arr[:] = 100 - (100 / (1 + rs))
    
    df['rsi14'] = rsi14
    df['rsi7'] = rsi7
    df['rsi9'] = rsi9
    
    # Session
    hour = df.index.hour
    df['session'] = 'asia'
    df.loc[(hour >= 8) & (hour < 16), 'session'] = 'europe'
    df.loc[(hour >= 16), 'session'] = 'us'
    df['hour'] = hour
    df['dow'] = df.index.dayofweek
    
    # 连续阴阳线
    bear = (closes < opens).astype(int)
    bull = (closes > opens).astype(int)
    df['consecutive_bear'] = 0
    df['consecutive_bull'] = 0
    cb = 0
    for i in range(len(df)):
        if bear[i]:
            cb += 1
        else:
            cb = 0
        df.iloc[i, df.columns.get_loc('consecutive_bear')] = cb
    
    cb = 0
    for i in range(len(df)):
        if bull[i]:
            cb += 1
        else:
            cb = 0
        df.iloc[i, df.columns.get_loc('consecutive_bull')] = cb
    
    return df


# ═══════════════════════════════════════════════
# 加载数据（带缓存）
# ═══════════════════════════════════════════════
_CACHE = {}
def get_data(sym, tf):
    key = (sym, tf)
    if key not in _CACHE:
        t0 = time.time()
        data_dir = os.path.join(DATA_DIR, tf)
        fp = os.path.join(data_dir, f'{sym}.parquet')
        if not os.path.exists(fp):
            print(f"  ⚠ {sym} {tf}: 文件不存在")
            _CACHE[key] = None
            return None
        df = pd.read_parquet(fp)
        df = fast_indicators(df)
        _CACHE[key] = df
        print(f"  ✅ {sym} {tf}: {len(df)} rows ({time.time()-t0:.1f}s)")
    return _CACHE[key]


def test_condition(df, cond, label, hold_list, min_sig=3, direction='long'):
    if cond.sum() == 0:
        return None
    entries = df[cond]
    n_signals = len(entries)
    best = None
    ppy = 6000 if 'H1' in label else 12000
    
    for hold in hold_list:
        rets = []
        for idx in entries.index:
            pos = df.index.get_loc(idx)
            if isinstance(pos, slice):
                pos = pos.start
            exit_pos = pos + hold
            if exit_pos >= len(df):
                continue
            entry_p = df.iloc[pos]['close']
            exit_p = df.iloc[exit_pos]['close']
            if direction == 'long':
                r = (exit_p - entry_p) / entry_p
            else:
                r = (entry_p - exit_p) / entry_p
            rets.append(r)
        
        if len(rets) < min_sig:
            continue
        rets = np.array(rets)
        wr = float((rets > 0).mean())
        avg_ret = float(rets.mean())
        std = float(rets.std()) if rets.std() > 1e-10 else 1e-10
        sharpe = avg_ret / std * np.sqrt(ppy / hold) if avg_ret != 0 and std > 1e-10 else 0
        
        if best is None or wr > best['wr']:
            best = {
                'label': label, 'symbol': label.split(' ')[0],
                'timeframe': 'H1' if 'H1' in label else 'M30',
                'hold': hold, 'wr': wr, 'n': len(rets), 'n_signals': n_signals,
                'avg_ret': avg_ret, 'sharpe': sharpe
            }
    return best


def scan_all(df, sym, tf, hold_list):
    """扫描所有模式"""
    results = []
    
    for sess in ['asia', 'europe', 'us']:
        sm = df['session'] == sess
        
        # RSI14
        for v in [18, 20, 22, 25, 28]:
            cond = sm & (df['rsi14'] < v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} RSI14<{v}", hold_list)
            if r: results.append(r)
        
        # RSI14 + CB
        for cb in [2, 3, 4]:
            for v in [20, 25, 28]:
                cond = sm & (df['rsi14'] < v) & (df['consecutive_bear'] >= cb)
                r = test_condition(df, cond, f"{sym} {tf} {sess} CB>={cb}+RSI14<{v}", hold_list)
                if r: results.append(r)
        
        # 纯CB
        for cb in [3, 4, 5, 6]:
            cond = sm & (df['consecutive_bear'] >= cb)
            r = test_condition(df, cond, f"{sym} {tf} {sess} CB>={cb}", hold_list)
            if r: results.append(r)
        
        # RSI7
        for v in [15, 20, 25]:
            cond = sm & (df['rsi7'] < v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} RSI7<{v}", hold_list)
            if r: results.append(r)
        
        # RSI9
        for v in [15, 20, 25]:
            cond = sm & (df['rsi9'] < v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} RSI9<{v}", hold_list)
            if r: results.append(r)
        
        # 做空 RSI超买
        for v in [75, 78, 80]:
            cond = sm & (df['rsi14'] > v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} RSI14>{v} 做空", hold_list, direction='short')
            if r: results.append(r)
        
        # 做空 CBull+RSI
        for cb in [3, 4]:
            cond = sm & (df['consecutive_bull'] >= cb) & (df['rsi14'] > 70)
            r = test_condition(df, cond, f"{sym} {tf} {sess} CBull>={cb}+RSI14>70 做空", hold_list, direction='short')
            if r: results.append(r)
    
    # EU开盘
    eu = df['session'] == 'europe'
    cond = eu & (df['hour'].isin([8, 9]))
    r = test_condition(df, cond, f"{sym} {tf} EU开盘8-9UTC", hold_list)
    if r: results.append(r)
    for v in [22, 25, 30]:
        cond = eu & (df['hour'].isin([8, 9])) & (df['rsi14'] < v)
        r = test_condition(df, cond, f"{sym} {tf} EU开盘8-9+RSI14<{v}", hold_list)
        if r: results.append(r)
    
    # ASIA低点
    as_m = df['session'] == 'asia'
    for h in [0, 1, 2]:
        cond = as_m & (df['hour'] == h) & (df['rsi14'] < 25)
        r = test_condition(df, cond, f"{sym} {tf} ASIA{h}点RSI14<25", hold_list)
        if r: results.append(r)
    
    # Session过渡
    cond = (df['hour'] >= 6) & (df['hour'] <= 10) & (df['rsi14'] < 25)
    r = test_condition(df, cond, f"{sym} {tf} 亚→欧过渡RSI14<25", hold_list)
    if r: results.append(r)
    
    cond = (df['hour'] >= 14) & (df['hour'] <= 17) & (df['rsi14'] < 25)
    r = test_condition(df, cond, f"{sym} {tf} 欧→美过渡RSI14<25", hold_list)
    if r: results.append(r)
    
    return results


def print_table(rows, title=None):
    """打印格式化的结果表格"""
    if not rows:
        print("  (无结果)")
        return
    if title:
        print(f"\n  {title}")
    print(f"  {'#':<4} {'品种':<10} {'Session':<8} {'模式':<48} {'Hold':<5} {'WR':<7} {'n':<5} {'Sharpe':<7}")
    print(f"  {'─'*4} {'─'*10} {'─'*8} {'─'*48} {'─'*5} {'─'*7} {'─'*5} {'─'*7}")
    for i, r in enumerate(rows):
        parts = r['label'].split(' ')
        sess = parts[2] if len(parts) > 2 else ''
        cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
        print(f"  {i+1:<4} {r['symbol']:<10} {sess:<8} {cond[:46]:<48} {r['hold']:<5} {r['wr']*100:<6.1f}% {r['n']:<5} {r['sharpe']:<7.2f}")


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
def main():
    print("=" * 120)
    print(f"ROUND 77 — H1/M30 K线形态深度研究 — {NOW}")
    print(f"品种: {', '.join(SYMBOLS)}")
    print(f"时间框架: H1 / M30 | 轻量高效版")
    print("=" * 120)
    
    t_start = time.time()
    all_results = []
    
    for tf in ['H1', 'M30']:
        hold_list = H1_HOLDS if tf == 'H1' else M30_HOLDS
        print(f"\n{'─'*80}")
        print(f"📊 {tf} 扫描开始")
        print(f"{'─'*80}")
        
        tf_t0 = time.time()
        tf_results = []
        
        for sym in SYMBOLS:
            df = get_data(sym, tf)
            if df is None:
                continue
            sym_results = scan_all(df, sym, tf, hold_list)
            tf_results.extend(sym_results)
            if sym_results:
                best = max(sym_results, key=lambda r: r['wr'])
                print(f"    {sym}: {len(sym_results)}候选, 最佳WR={best['wr']*100:.1f}% n={best['n']}")
        
        all_results.extend(tf_results)
        print(f"\n  ⏱ {tf}完成: {len(tf_results)}候选, 耗时{time.time()-tf_t0:.0f}s")
    
    # ── 分析师 ──
    print(f"\n{'='*80}")
    print(f"📊 分析师 — 筛选")
    print(f"{'='*80}")
    
    df_r = pd.DataFrame(all_results)
    df_r['wr_pct'] = df_r['wr'] * 100
    
    # 精英: n>=20, WR>=80%
    h1_elite = df_r[(df_r['timeframe'] == 'H1') & (df_r['n'] >= 20) & (df_r['wr_pct'] >= 80)].sort_values('wr_pct', ascending=False) if len(df_r) > 0 else pd.DataFrame()
    m30_elite = df_r[(df_r['timeframe'] == 'M30') & (df_r['n'] >= 20) & (df_r['wr_pct'] >= 80)].sort_values('wr_pct', ascending=False) if len(df_r) > 0 else pd.DataFrame()
    
    # 强信号: n>=15, WR>=75%
    h1_strong = df_r[(df_r['timeframe'] == 'H1') & (df_r['n'] >= 15) & (df_r['wr_pct'] >= 75)].sort_values('wr_pct', ascending=False) if len(df_r) > 0 else pd.DataFrame()
    m30_strong = df_r[(df_r['timeframe'] == 'M30') & (df_r['n'] >= 15) & (df_r['wr_pct'] >= 75)].sort_values('wr_pct', ascending=False) if len(df_r) > 0 else pd.DataFrame()
    
    print(f"\n  H1: {len(df_r[df_r['timeframe']=='H1'])}候选 → 精英{len(h1_elite)} + 强{len(h1_strong)}")
    print(f"  M30: {len(df_r[df_r['timeframe']=='M30'])}候选 → 精英{len(m30_elite)} + 强{len(m30_strong)}")
    
    # 打印精英
    if len(h1_elite) > 0:
        print_table(h1_elite.head(30).to_dict('records'), title="🏆 H1 精英 (WR≥80% n≥20)")
    if len(m30_elite) > 0:
        print_table(m30_elite.head(30).to_dict('records'), title="🏆 M30 精英 (WR≥80% n≥20)")
    if len(h1_strong) > 0:
        print_table(h1_strong.head(30).to_dict('records'), title="💪 H1 强信号 (WR≥75% n≥15)")
    if len(m30_strong) > 0:
        print_table(m30_strong.head(30).to_dict('records'), title="💪 M30 强信号 (WR≥75% n≥15)")
    
    # 品种最佳
    sym_best = {}
    for _, r in df_r.iterrows():
        sym = r['symbol']
        if r['n'] < 10 or r['wr_pct'] < 65:
            continue
        if sym not in sym_best or r['wr_pct'] > sym_best[sym]['wr_pct']:
            sym_best[sym] = r
    
    print(f"\n{'─'*80}")
    print(f"📋 按品种最佳 (WR≥65% n≥10)")
    print(f"{'─'*80}")
    print(f"  {'品种':<10} {'TF':<5} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8} {'模式'}")
    for sym in SYMBOLS:
        if sym in sym_best:
            r = sym_best[sym]
            print(f"  {sym:<10} {r['timeframe']:<5} {r['wr_pct']:<7.1f}% {int(r['n']):<6} {r['hold']:<6} {r['sharpe']:<8.2f} {r['label'][:55]}")
        else:
            print(f"  {sym:<10} {'—':<5} {'—':<8} {'—':<6} {'—':<6} {'—':<8} 无合格信号")
    
    # 模式统计
    print(f"\n{'─'*80}")
    print(f"📊 模式类型有效性统计")
    print(f"{'─'*80}")
    
    categories = [
        ('RSI14超卖做多', lambda r: 'RSI14<' in r['label'] and '做空' not in r['label']),
        ('CB+RSI做多', lambda r: 'CB>=' in r['label'] and 'RSI' in r['label'] and '做空' not in r['label']),
        ('纯CB反弹做多', lambda r: 'CB>=' in r['label'] and 'RSI' not in r['label'] and '做空' not in r['label']),
        ('RSI7超卖做多', lambda r: 'RSI7<' in r['label']),
        ('RSI9超卖做多', lambda r: 'RSI9<' in r['label']),
        ('做空(超买)', lambda r: '做空' in r['label']),
        ('EU开盘做多', lambda r: 'EU开盘' in r['label']),
        ('ASIA低点做多', lambda r: 'ASIA' in r['label'] and '点' in r['label']),
        ('Session过渡', lambda r: '过渡' in r['label']),
    ]
    
    print(f"  {'模式类型':<20} {'强信号':<8} {'精英':<8} {'候选':<8} {'结论'}")
    print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*8} {'─'*10}")
    for cat_name, cat_func in categories:
        candidates = [r for r in all_results if cat_func(r)]
        s = len([r for r in candidates if r['n'] >= 15 and r['wr'] >= 0.75])
        e = len([r for r in candidates if r['n'] >= 20 and r['wr'] >= 0.80])
        c = len(candidates)
        conclusion = "✅推荐" if e >= 3 else ("⚠️观察" if s >= 3 else ("❌弱" if c > 0 else "—"))
        print(f"  {cat_name:<20} {s:<8} {e:<8} {c:<8} {conclusion}")
    
    # ── 生成报告 ──
    print(f"\n{'─'*80}")
    print(f"📝 生成报告")
    print(f"{'─'*80}")
    
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    lines = []
    lines.append("# Round 77 — H1/M30 K线形态深度研究报告")
    lines.append("")
    lines.append(f"**生成时间**: {now_str}")
    lines.append(f"**品种**: 全部14个MT5期货外汇品种")
    lines.append(f"**时间框架**: H1（主）/ M30（辅）")
    lines.append(f"**研究重点**: 超卖反弹、连续阴线(CB)、Session过渡、多指标组合")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    lines.append("## 1. 执行摘要")
    lines.append("")
    lines.append(f"- 📡 H1: {len(df_r[df_r['timeframe']=='H1'])}个候选模式 → 精英{len(h1_elite)}个(WR≥80% n≥20) + 强信号{len(h1_strong)}个(WR≥75% n≥15)")
    lines.append(f"- 📡 M30: {len(df_r[df_r['timeframe']=='M30'])}个候选模式 → 精英{len(m30_elite)}个 + 强信号{len(m30_strong)}个")
    lines.append(f"- ✅ 有信号的品种: {len(sym_best)}/{len(SYMBOLS)}")
    lines.append("")
    
    # Top elite combined
    all_elite = sorted([r for r in all_results if r['n'] >= 20 and r['wr'] >= 0.80], key=lambda x: -x['wr'])
    if all_elite:
        lines.append("**🏆 Top 10 最强信号:**")
        lines.append("")
        for i, r in enumerate(all_elite[:10]):
            lines.append(f"  {i+1}. {r['label'][:65]} | WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']} Sharpe={r['sharpe']:.2f}")
        lines.append("")
    
    # H1 精英
    if len(h1_elite) > 0:
        lines.append("## 2. H1 精英信号 (WR≥80% n≥20)")
        lines.append("")
        lines.append("| # | 品种 | Session | 模式 | Hold | WR | n | Sharpe |")
        lines.append("|---|:----:|:-------:|:-----|:----:|:--:|:-:|:------:|")
        for i, (_, r) in enumerate(h1_elite.head(25).iterrows()):
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            lines.append(f"| {i+1} | {r['symbol']} | {sess} | {cond[:50]} | {int(r['hold'])} | {r['wr_pct']:.1f}% | {int(r['n'])} | {r['sharpe']:.2f} |")
        lines.append("")
    
    if len(h1_strong) > 0:
        lines.append("## 3. H1 强信号 (WR≥75% n≥15)")
        lines.append("")
        lines.append("| # | 品种 | Session | 模式 | Hold | WR | n | Sharpe |")
        lines.append("|---|:----:|:-------:|:-----|:----:|:--:|:-:|:------:|")
        for i, (_, r) in enumerate(h1_strong.head(30).iterrows()):
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            lines.append(f"| {i+1} | {r['symbol']} | {sess} | {cond[:50]} | {int(r['hold'])} | {r['wr_pct']:.1f}% | {int(r['n'])} | {r['sharpe']:.2f} |")
        lines.append("")
    
    if len(m30_elite) > 0:
        lines.append("## 4. M30 精英信号 (WR≥80% n≥20)")
        lines.append("")
        lines.append("| # | 品种 | Session | 模式 | Hold | WR | n | Sharpe |")
        lines.append("|---|:----:|:-------:|:-----|:----:|:--:|:-:|:------:|")
        for i, (_, r) in enumerate(m30_elite.head(25).iterrows()):
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            lines.append(f"| {i+1} | {r['symbol']} | {sess} | {cond[:50]} | {int(r['hold'])} | {r['wr_pct']:.1f}% | {int(r['n'])} | {r['sharpe']:.2f} |")
        lines.append("")
    
    if len(m30_strong) > 0:
        lines.append("## 5. M30 强信号 (WR≥75% n≥15)")
        lines.append("")
        lines.append("| # | 品种 | Session | 模式 | Hold | WR | n | Sharpe |")
        lines.append("|---|:----:|:-------:|:-----|:----:|:--:|:-:|:------:|")
        for i, (_, r) in enumerate(m30_strong.head(30).iterrows()):
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            lines.append(f"| {i+1} | {r['symbol']} | {sess} | {cond[:50]} | {int(r['hold'])} | {r['wr_pct']:.1f}% | {int(r['n'])} | {r['sharpe']:.2f} |")
        lines.append("")
    
    # 品种最佳
    lines.append("## 6. 按品种最佳信号")
    lines.append("")
    lines.append("| 品种 | TF | 最佳模式 | WR | n | Hold | Sharpe |")
    lines.append("|:----|:--:|:---------|:--:|:-:|:----:|:------:|")
    for sym in SYMBOLS:
        if sym in sym_best:
            r = sym_best[sym]
            lines.append(f"| {sym} | {r['timeframe']} | {r['label'][:50]} | {r['wr_pct']:.1f}% | {int(r['n'])} | {r['hold']} | {r['sharpe']:.2f} |")
        else:
            lines.append(f"| {sym} | — | 无合格信号 | — | — | — | — |")
    lines.append("")
    
    # Session分析
    lines.append("## 7. Session分布分析")
    lines.append("")
    for sess in ['europe', 'us', 'asia']:
        sess_elite = [r for r in all_elite if sess in r['label'].lower()]
        lines.append(f"- **{sess.upper()}盘**: {len(sess_elite)}个精英信号")
        if sess_elite:
            for r in sess_elite[:5]:
                lines.append(f"  - {r['label'][:55]} | WR={r['wr']*100:.1f}% n={r['n']}")
        lines.append("")
    
    # 假设验证
    lines.append("## 8. 假设验证")
    lines.append("")
    
    h1_eu_s = len([r for r in all_results if r['timeframe']=='H1' and 'europe' in r['label'] and r['n']>=15 and r['wr']>=0.75])
    m30_eu_s = len([r for r in all_results if r['timeframe']=='M30' and 'europe' in r['label'] and r['n']>=15 and r['wr']>=0.75])
    short_s = len([r for r in all_results if '做空' in r['label'] and r['n']>=15 and r['wr']>=0.70])
    fx_s = len([r for r in all_results if r['symbol'] in ['EURUSD','GBPUSD','AUDUSD'] and r['n']>=15 and r['wr']>=0.75])
    
    lines.append("| 假设ID | 描述 | 结果 |")
    lines.append("|--------|------|:----:|")
    lines.append(f"| H77-001 | H1欧盘RSI超卖做多在4+品种上有效(WR≥75%) | {'✅ confirmed' if h1_eu_s >= 4 else '⚠️ partial'} ({h1_eu_s}) |")
    lines.append(f"| H77-002 | M30欧盘信号多于美盘 | {'✅ confirmed' if m30_eu_s > len([r for r in all_results if r['timeframe']=='M30' and 'us' in r['label'] and r['n']>=15 and r['wr']>=0.75]) else '⚠️ mixed'} |")
    lines.append(f"| H77-003 | 做空信号整体弱于做多 | {'✅ confirmed' if short_s < 3 else '⚠️ partial'} ({short_s}) |")
    lines.append(f"| H77-004 | 至少10品种有合格信号 | {'✅ confirmed' if len(sym_best) >= 10 else '⚠️ partial'} ({len(sym_best)}品种) |")
    lines.append(f"| H77-005 | EURUSD/GBPUSD/AUDUSD货币对M30优于H1 | {'✅ confirmed' if len([r for r in all_results if r['timeframe']=='M30' and r['symbol'] in ['EURUSD','GBPUSD','AUDUSD'] and r['wr']>=0.75 and r['n']>=15]) > len([r for r in all_results if r['timeframe']=='H1' and r['symbol'] in ['EURUSD','GBPUSD','AUDUSD'] and r['wr']>=0.75 and r['n']>=15]) else '⚠️ mixed'} |")
    lines.append(f"| H77-006 | 连续阴线CB+RSI组合优于纯RSI超卖 | {'✅ confirmed' if len([r for r in all_results if 'CB>=' in r['label'] and 'RSI' in r['label'] and r['n']>=15 and r['wr']>=0.75]) > len([r for r in all_results if 'RSI14<' in r['label'] and 'CB' not in r['label'] and '做空' not in r['label'] and r['n']>=15 and r['wr']>=0.75]) else '⚠️ comparable'} |")
    lines.append("")
    
    # 推荐排名
    lines.append("## 9. 策略推荐排名")
    lines.append("")
    ranked = sorted(sym_best.items(), key=lambda x: -x[1]['wr'])
    lines.append("| 排名 | 品种 | WR | n | Hold | Sharpe | TF | 模式 |")
    lines.append("|:----:|:----:|:--:|:-:|:----:|:------:|:--:|:-----|")
    for i, (sym, r) in enumerate(ranked):
        lines.append(f"| {i+1} | {sym} | {r['wr']*100:.1f}% | {r['n']} | {r['hold']} | {r['sharpe']:.2f} | {r['timeframe']} | {r['label'][:45]} |")
    lines.append("")
    
    lines.append("## 10. 下一轮建议")
    lines.append("")
    lines.append("基于Round 77发现:")
    lines.append("")
    lines.append("- **P1** 对精英信号做bootstrap置信区间验证(2000次迭代)")
    lines.append("- **P1** 跨品种协同 — 联动品种同时超卖的叠加效果(GBP+AUD, EUR+GBP)")
    lines.append("- **P2** H1欧盘信号hold精细优化(+ATR动态止损)")
    lines.append("- **P2** M30 squeeze play扩展 — ATR收缩→扩张机制")
    lines.append("- **P3** 做空信号深化 — 超买+CBull组合在美盘的short squeeze")
    lines.append("- **P3** 亚盘指数(JP225/HK50/US500)独立策略优化")
    lines.append("")
    
    lines.append("---")
    lines.append(f"*报告由 Candlestick Pattern Researcher 于 {now_str} 自动生成*")
    lines.append(f"*研究范围: 期货外汇14品种 | H1/M30时间框架 | 严禁A股*")
    
    report = '\n'.join(lines)
    
    # 保存
    report_dir = os.path.join(BASE, 'reports')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, 'round77_h1m30_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    elapsed = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"✅ Round 77 完成! 耗时{elapsed:.0f}s")
    print(f"   H1精英{len(h1_elite)} M30精英{len(m30_elite)} | 报告: {report_path}")
    print(f"{'='*80}")
    
    # 输出报告用于交付
    print("\n" + report)

main()
