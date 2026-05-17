#!/usr/bin/env python3
"""
Round 77 — H1/M30 K线形态深度研究 v2
时间框架: H1（主）/ M30（辅）
品种: 全部14个MT5品种

采用更高效的批量扫描模式，复用已验证的基础架构。
"""
import sys, os, json, time, gc
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']

# Session定义 (UTC)
SESSION_MAP = {'asia': (0, 8), 'europe': (8, 16), 'us': (16, 24)}

H1_HOLDS = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50]
M30_HOLDS = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50, 60, 80]

_CACHE = {}

def get_data(symbol, timeframe):
    """带缓存的加载+计算"""
    key = (symbol, timeframe)
    if key not in _CACHE:
        t0 = time.time()
        data = load_data(timeframe=timeframe, symbols=[symbol])
        if symbol in data:
            df = compute_indicators(data[symbol])
            # 添加session特征
            hour = df.index.hour
            df['session'] = 'asia'
            df.loc[(hour >= 8) & (hour < 16), 'session'] = 'europe'
            df.loc[(hour >= 16), 'session'] = 'us'
            df['hour'] = hour
            df['dow'] = df.index.dayofweek
            _CACHE[key] = df
            print(f"  ✅ {symbol} {timeframe}: {len(df)} rows [{df.index[0].strftime('%m-%d')} → {df.index[-1].strftime('%m-%d %H:%M')}] ({time.time()-t0:.1f}s)")
        else:
            _CACHE[key] = None
    return _CACHE[key]

def test_condition(df, cond, label, hold_list, min_sig=3, direction='long'):
    """通用条件测试器"""
    if cond.sum() == 0:
        return None
    n = int(cond.sum())
    entries = df[cond]
    best = None
    
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
        # Use 6000 for H1, 12000 for M30
        ppy = 6000 if 'H1' in label else 12000
        sharpe = avg_ret / std * np.sqrt(ppy / hold) if avg_ret != 0 and std > 1e-10 else 0
        
        if best is None or wr > best['wr']:
            best = {
                'label': label,
                'symbol': label.split(' ')[0],
                'timeframe': 'H1' if 'H1' in label else 'M30',
                'hold': hold, 'wr': wr, 'n': len(rets), 'n_signals': n,
                'avg_ret': avg_ret, 'sharpe': sharpe
            }
    
    return best

def scan_symbol_tf(df, sym, tf, hold_list):
    """扫描单个品种+时间框架的所有模式"""
    results = []
    
    for sess in ['asia', 'europe', 'us']:
        sess_mask = df['session'] == sess
        
        # === RSI14 超卖做多 ===
        for rsi_v in [18, 20, 22, 25, 28]:
            cond = sess_mask & (df['rsi14'] < rsi_v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} RSI14<{rsi_v}", hold_list, direction='long')
            if r: results.append(r)
        
        # === RSI14 + CB ===
        for cb in [2, 3, 4]:
            for rsi_v in [20, 25, 28]:
                cond = sess_mask & (df['rsi14'] < rsi_v) & (df['consecutive_bear'] >= cb)
                r = test_condition(df, cond, f"{sym} {tf} {sess} CB>={cb}+RSI14<{rsi_v}", hold_list, direction='long')
                if r: results.append(r)
        
        # === 纯CB ===
        for cb in [3, 4, 5, 6]:
            cond = sess_mask & (df['consecutive_bear'] >= cb)
            r = test_condition(df, cond, f"{sym} {tf} {sess} CB>={cb}", hold_list, direction='long')
            if r: results.append(r)
        
        # === RSI7超卖 ===
        for rsi_v in [15, 20, 25]:
            cond = sess_mask & (df['rsi7'] < rsi_v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} RSI7<{rsi_v}", hold_list, direction='long')
            if r: results.append(r)
        
        # === RSI9超卖 ===
        for rsi_v in [15, 20, 25]:
            cond = sess_mask & (df['rsi9'] < rsi_v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} RSI9<{rsi_v}", hold_list, direction='long')
            if r: results.append(r)
        
        # === Stochastic ===
        cond = sess_mask & (df['stoch_k_14'] < 20)
        r = test_condition(df, cond, f"{sym} {tf} {sess} Stoch<20", hold_list, direction='long')
        if r: results.append(r)
        
        # === Williams %R ===
        cond = sess_mask & (df['williams_r_14'] < -85)
        r = test_condition(df, cond, f"{sym} {tf} {sess} Williams%R<-85", hold_list, direction='long')
        if r: results.append(r)
        
        # === CCI ===
        cond = sess_mask & (df['cci_14'] < -100)
        r = test_condition(df, cond, f"{sym} {tf} {sess} CCI<-100", hold_list, direction='long')
        if r: results.append(r)
        
        # === MACD cross + RSI ===
        for rsi_v in [25, 30]:
            cond = sess_mask & (df['macd_cross'] == 1) & (df['rsi14'] < rsi_v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} MACDcross+RSI14<{rsi_v}", hold_list, direction='long')
            if r: results.append(r)
        
        # === BB touch + RSI ===
        cond = sess_mask & (df['close'] <= df['bb_20_2.0_lower']) & (df['rsi14'] < 30)
        r = test_condition(df, cond, f"{sym} {tf} {sess} BBtouch+RSI14<30", hold_list, direction='long')
        if r: results.append(r)
        
        # === 做空: RSI超买 ===
        for rsi_v in [75, 78, 80]:
            cond = sess_mask & (df['rsi14'] > rsi_v)
            r = test_condition(df, cond, f"{sym} {tf} {sess} RSI14>{rsi_v} 做空", hold_list, direction='short')
            if r: results.append(r)
        
        # === 做空: CBull + RSI超买 ===
        for cb in [3, 4]:
            cond = sess_mask & (df['consecutive_bull'] >= cb) & (df['rsi14'] > 70)
            r = test_condition(df, cond, f"{sym} {tf} {sess} CBull>={cb}+RSI14>70 做空", hold_list, direction='short')
            if r: results.append(r)
    
    # === EU开盘8-9 UTC ===
    eu_mask = df['session'] == 'europe'
    cond = eu_mask & (df['hour'].isin([8, 9]))
    r = test_condition(df, cond, f"{sym} {tf} EU开盘8-9UTC", hold_list, direction='long')
    if r: results.append(r)
    
    for rsi_v in [22, 25, 30]:
        cond = eu_mask & (df['hour'].isin([8, 9])) & (df['rsi14'] < rsi_v)
        r = test_condition(df, cond, f"{sym} {tf} EU开盘8-9+RSI14<{rsi_v}", hold_list, direction='long')
        if r: results.append(r)
    
    # === ASIA低点 ===
    asia_mask = df['session'] == 'asia'
    for h in [0, 1, 2]:
        cond = asia_mask & (df['hour'] == h) & (df['rsi14'] < 25)
        r = test_condition(df, cond, f"{sym} {tf} ASIA{h}:00+RSI14<25", hold_list, direction='long')
        if r: results.append(r)
    
    # === Session 过渡 ===
    cond = (df['hour'] >= 6) & (df['hour'] <= 10) & (df['rsi14'] < 25)
    r = test_condition(df, cond, f"{sym} {tf} ASIA→EU过渡 RSI14<25", hold_list, direction='long')
    if r: results.append(r)
    
    cond = (df['hour'] >= 14) & (df['hour'] <= 17) & (df['rsi14'] < 25)
    r = test_condition(df, cond, f"{sym} {tf} EU→US过渡 RSI14<25", hold_list, direction='long')
    if r: results.append(r)
    
    return results


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════
def main():
    print("=" * 120)
    print(f"ROUND 77 — H1/M30 K线形态深度研究 — {NOW}")
    print(f"品种: {', '.join(SYMBOLS)}")
    print(f"时间框架: H1 / M30")
    print("=" * 120)
    print(f"⚠️ 范围: 期货外汇 | 严禁A股")
    print(f"{'=' * 120}")
    
    t_start = time.time()
    all_results = []
    
    for timeframe in ['H1', 'M30']:
        hold_list = H1_HOLDS if timeframe == 'H1' else M30_HOLDS
        print(f"\n{'─'*80}")
        print(f"📊 {timeframe} 扫描")
        print(f"{'─'*80}")
        
        tf_t0 = time.time()
        tf_results = []
        
        for sym in SYMBOLS:
            df = get_data(sym, timeframe)
            if df is None:
                continue
            sym_results = scan_symbol_tf(df, sym, timeframe, hold_list)
            tf_results.extend(sym_results)
            if sym_results:
                best = max(sym_results, key=lambda r: r['wr'])
                print(f"  {sym}: {len(sym_results)} candidates, best WR={best['wr']*100:.1f}% n={best['n']}")
        
        all_results.extend(tf_results)
        print(f"\n  ⏱ {timeframe} 耗时: {time.time()-tf_t0:.0f}s | 候选: {len(tf_results)}")
    
    # ── 分析师 ──
    print(f"\n{'='*80}")
    print(f"📊 分析师阶段 — 筛选排序")
    print(f"{'='*80}")
    
    df_all = pd.DataFrame(all_results)
    df_all['wr_pct'] = df_all['wr'] * 100
    
    h1_df = df_all[df_all['timeframe'] == 'H1'].copy() if len(df_all) > 0 else pd.DataFrame()
    m30_df = df_all[df_all['timeframe'] == 'M30'].copy() if len(df_all) > 0 else pd.DataFrame()
    
    # 精英信号 (n>=20, WR>=80%)
    h1_elite = h1_df[(h1_df['n'] >= 20) & (h1_df['wr_pct'] >= 80)].sort_values('wr_pct', ascending=False) if len(h1_df) > 0 else pd.DataFrame()
    m30_elite = m30_df[(m30_df['n'] >= 20) & (m30_df['wr_pct'] >= 80)].sort_values('wr_pct', ascending=False) if len(m30_df) > 0 else pd.DataFrame()
    
    # 强信号 (n>=15, WR>=75%)
    h1_strong = h1_df[(h1_df['n'] >= 15) & (h1_df['wr_pct'] >= 75)].sort_values('wr_pct', ascending=False) if len(h1_df) > 0 else pd.DataFrame()
    m30_strong = m30_df[(m30_df['n'] >= 15) & (m30_df['wr_pct'] >= 75)].sort_values('wr_pct', ascending=False) if len(m30_df) > 0 else pd.DataFrame()
    
    print(f"\nH1: 总{len(h1_df)}候选 → {len(h1_elite)}精英 + {len(h1_strong)}强信号")
    print(f"M30: 总{len(m30_df)}候选 → {len(m30_elite)}精英 + {len(m30_strong)}强信号")
    
    # ── 输出结果表格 ──
    if len(h1_elite) > 0:
        print(f"\n{'─'*80}")
        print(f"🏆 H1 精英信号 (WR≥80% n≥20)")
        print(f"{'─'*80}")
        print(f"{'#':<4} {'品种':<10} {'Session':<8} {'模式':<50} {'Hold':<6} {'WR':<8} {'n':<6} {'Sharpe':<8}")
        print(f"{'─'*4} {'─'*10} {'─'*8} {'─'*50} {'─'*6} {'─'*8} {'─'*6} {'─'*8}")
        for i, (_, r) in enumerate(h1_elite.head(30).iterrows()):
            # Extract session from label
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            print(f"{i+1:<4} {r['symbol']:<10} {sess:<8} {cond[:48]:<50} {int(r['hold']):<6} {r['wr_pct']:<7.1f}% {int(r['n']):<6} {r['sharpe']:<8.2f}")
    
    if len(m30_elite) > 0:
        print(f"\n{'─'*80}")
        print(f"🏆 M30 精英信号 (WR≥80% n≥20)")
        print(f"{'─'*80}")
        print(f"{'#':<4} {'品种':<10} {'Session':<8} {'模式':<50} {'Hold':<6} {'WR':<8} {'n':<6} {'Sharpe':<8}")
        print(f"{'─'*4} {'─'*10} {'─'*8} {'─'*50} {'─'*6} {'─'*8} {'─'*6} {'─'*8}")
        for i, (_, r) in enumerate(m30_elite.head(30).iterrows()):
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            print(f"{i+1:<4} {r['symbol']:<10} {sess:<8} {cond[:48]:<50} {int(r['hold']):<6} {r['wr_pct']:<7.1f}% {int(r['n']):<6} {r['sharpe']:<8.2f}")
    
    if len(h1_strong) > 0:
        print(f"\n{'─'*80}")
        print(f"💪 H1 强信号 (WR≥75% n≥15, 含精英)")
        print(f"{'─'*80}")
        print(f"{'#':<4} {'品种':<10} {'Session':<8} {'模式':<50} {'Hold':<6} {'WR':<8} {'n':<6} {'Sharpe':<8}")
        print(f"{'─'*4} {'─'*10} {'─'*8} {'─'*50} {'─'*6} {'─'*8} {'─'*6} {'─'*8}")
        for i, (_, r) in enumerate(h1_strong.head(40).iterrows()):
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            print(f"{i+1:<4} {r['symbol']:<10} {sess:<8} {cond[:48]:<50} {int(r['hold']):<6} {r['wr_pct']:<7.1f}% {int(r['n']):<6} {r['sharpe']:<8.2f}")
    
    if len(m30_strong) > 0:
        print(f"\n{'─'*80}")
        print(f"💪 M30 强信号 (WR≥75% n≥15, 含精英)")
        print(f"{'─'*80}")
        print(f"{'#':<4} {'品种':<10} {'Session':<8} {'模式':<50} {'Hold':<6} {'WR':<8} {'n':<6} {'Sharpe':<8}")
        print(f"{'─'*4} {'─'*10} {'─'*8} {'─'*50} {'─'*6} {'─'*8} {'─'*6} {'─'*8}")
        for i, (_, r) in enumerate(m30_strong.head(40).iterrows()):
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            print(f"{i+1:<4} {r['symbol']:<10} {sess:<8} {cond[:48]:<50} {int(r['hold']):<6} {r['wr_pct']:<7.1f}% {int(r['n']):<6} {r['sharpe']:<8.2f}")
    
    # ── 按品种最佳 ──
    print(f"\n{'─'*80}")
    print(f"📋 按品种最佳信号")
    print(f"{'─'*80}")
    
    sym_best = {}
    for _, r in df_all.iterrows():
        sym = r['symbol']
        if r['n'] < 10 or r['wr_pct'] < 65:
            continue
        if sym not in sym_best or r['wr_pct'] > sym_best[sym]['wr_pct']:
            sym_best[sym] = r
    
    print(f"{'品种':<10} {'TF':<5} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8} {'模式'}")
    print(f"{'─'*10} {'─'*5} {'─'*8} {'─'*6} {'─'*6} {'─'*8} {'─'*50}")
    for sym in SYMBOLS:
        if sym in sym_best:
            r = sym_best[sym]
            print(f"{sym:<10} {r['timeframe']:<5} {r['wr_pct']:<7.1f}% {int(r['n']):<6} {int(r['hold']):<6} {r['sharpe']:<8.2f} {r['label'][:55]}")
        else:
            print(f"{sym:<10} {'—':<5} {'—':<8} {'—':<6} {'—':<6} {'—':<8} 无合格信号")
    
    # ── 模式类型统计 ──
    print(f"\n{'─'*80}")
    print(f"📊 模式类型统计")
    print(f"{'─'*80}")
    
    def count_by_type(keyword, direction='long'):
        if direction == 'long':
            return len([r for r in all_results if keyword in r['label'] and '做空' not in r['label'] and r['n'] >= 15 and r['wr'] >= 0.75])
        else:
            return len([r for r in all_results if keyword in r['label'] and '做空' in r['label'] and r['n'] >= 15 and r['wr'] >= 0.70])
    
    categories = [
        ('RSI14超卖', 'RSI14<'),
        ('CB+RSI', 'CB>='),
        ('纯CB反弹', 'CB>='),  # will exclude rsi ones
        ('Stoch超卖', 'Stoch<'),
        ('Williams%R超卖', 'Williams'),
        ('CCI超卖', 'CCI<'),
        ('MACD交叉', 'MACDcross'),
        ('布林带', 'BBtouch'),
        ('做空', 'RSI14>'),
        ('开盘模式', '开盘'),
        ('Session过渡', '过渡'),
    ]
    
    print(f"{'模式类型':<20} {'强信号(≥75%)':<15} {'候选数':<10}")
    print(f"{'─'*20} {'─'*15} {'─'*10}")
    for cat_name, keyword in categories:
        if cat_name == '做空':
            cnt = count_by_type(keyword, 'short')
        elif cat_name == '纯CB反弹':
            cnt = len([r for r in all_results if ('CB>=' in r['label'] or 'cb>=' in r['label'].lower()) and 'RSI' not in r['label'] and '做空' not in r['label'] and r['n'] >= 15 and r['wr'] >= 0.75])
        else:
            cnt = count_by_type(keyword, 'long')
        total = len([r for r in all_results if keyword in r['label']])
        status = "✅" if cnt >= 3 else ("⚠️" if cnt >= 1 else "❌")
        print(f"{cat_name:<20} {cnt:<15} {total:<10} {status}")
    
    # ── 生成报告 ──
    print(f"\n{'─'*80}")
    print(f"📝 保存报告")
    print(f"{'─'*80}")
    
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    lines = []
    lines.append("# Round 77 — H1/M30 K线形态深度研究报告")
    lines.append("")
    lines.append(f"**生成时间**: {now_str}")
    lines.append(f"**品种**: 全部14个MT5期货外汇品种")
    lines.append(f"**时间框架**: H1（主）/ M30（辅）")
    lines.append(f"**研究重点**: 超卖反弹、连续阴线、Session过渡、多指标组合确认")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    lines.append("## 1. 执行摘要")
    lines.append("")
    lines.append(f"- 📡 H1: {len(h1_df)}个候选 → {len(h1_elite)}个精英(WR≥80% n≥20) + {len(h1_strong)}个强信号(WR≥75% n≥15)")
    lines.append(f"- 📡 M30: {len(m30_df)}个候选 → {len(m30_elite)}个精英 + {len(m30_strong)}个强信号")
    lines.append("")
    
    # Top 5
    all_elite = pd.concat([h1_elite, m30_elite]).sort_values('wr_pct', ascending=False) if len(h1_elite) > 0 or len(m30_elite) > 0 else pd.DataFrame()
    if len(all_elite) > 0:
        lines.append("**Top 5 最强信号:**")
        lines.append("")
        for i, (_, r) in enumerate(all_elite.head(5).iterrows()):
            lines.append(f"{i+1}. {r['label'][:65]} | WR={r['wr_pct']:.1f}% n={int(r['n'])} Hold={int(r['hold'])} Sharpe={r['sharpe']:.2f}")
        lines.append("")
    
    # H1详细
    lines.append("## 2. H1 时间框架分析")
    lines.append("")
    if len(h1_elite) > 0:
        lines.append("### 2.1 精英信号 (WR≥80% n≥20)")
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
        lines.append("### 2.2 强信号 (WR≥75% n≥15)")
        lines.append("")
        lines.append("| # | 品种 | Session | 模式 | Hold | WR | n | Sharpe |")
        lines.append("|---|:----:|:-------:|:-----|:----:|:--:|:-:|:------:|")
        for i, (_, r) in enumerate(h1_strong.head(30).iterrows()):
            parts = r['label'].split(' ')
            sess = parts[2] if len(parts) > 2 else ''
            cond = ' '.join(parts[3:]) if len(parts) > 3 else r['label'][:45]
            lines.append(f"| {i+1} | {r['symbol']} | {sess} | {cond[:50]} | {int(r['hold'])} | {r['wr_pct']:.1f}% | {int(r['n'])} | {r['sharpe']:.2f} |")
        lines.append("")
    
    # M30详细
    lines.append("## 3. M30 时间框架分析")
    lines.append("")
    if len(m30_elite) > 0:
        lines.append("### 3.1 精英信号 (WR≥80% n≥20)")
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
        lines.append("### 3.2 强信号 (WR≥75% n≥15)")
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
    lines.append("## 4. 按品种最佳信号")
    lines.append("")
    lines.append("| 品种 | TF | 最佳模式 | WR | n | Hold | Sharpe |")
    lines.append("|:----|:--:|:---------|:--:|:-:|:----:|:------:|")
    for sym in SYMBOLS:
        if sym in sym_best:
            r = sym_best[sym]
            lines.append(f"| {sym} | {r['timeframe']} | {r['label'][:50]} | {r['wr_pct']:.1f}% | {int(r['n'])} | {int(r['hold'])} | {r['sharpe']:.2f} |")
        else:
            lines.append(f"| {sym} | — | 无合格信号 | — | — | — | — |")
    lines.append("")
    
    # 模式类型结论
    lines.append("## 5. 模式类型结论")
    lines.append("")
    lines.append("| 模式类型 | 强信号数 | 结论 |")
    lines.append("|----------|:--------:|:----:|")
    for cat_name, keyword in categories:
        if cat_name == '做空':
            cnt = count_by_type(keyword, 'short')
        elif cat_name == '纯CB反弹':
            cnt = len([r for r in all_results if ('CB>=' in r['label'] or 'cb>=' in r['label'].lower()) and 'RSI' not in r['label'] and '做空' not in r['label'] and r['n'] >= 15 and r['wr'] >= 0.75])
        else:
            cnt = count_by_type(keyword, 'long')
        conclusion = "✅ 推荐" if cnt >= 3 else ("⚠️ 观察" if cnt >= 1 else "❌ 弱")
        lines.append(f"| {cat_name} | {cnt} | {conclusion} |")
    lines.append("")
    
    # 假设验证
    lines.append("## 6. 假设验证")
    lines.append("")
    
    # 统计各类别
    h1_eu_strong = len([r for r in all_results if r['timeframe'] == 'H1' and 'europe' in r['label'] and r['n'] >= 15 and r['wr'] >= 0.75])
    m30_eu_strong = len([r for r in all_results if r['timeframe'] == 'M30' and 'europe' in r['label'] and r['n'] >= 15 and r['wr'] >= 0.75])
    h1_us_strong = len([r for r in all_results if r['timeframe'] == 'H1' and 'us' in r['label'] and r['n'] >= 15 and r['wr'] >= 0.75])
    m30_us_strong = len([r for r in all_results if r['timeframe'] == 'M30' and 'us' in r['label'] and r['n'] >= 15 and r['wr'] >= 0.75])
    short_strong = len([r for r in all_results if '做空' in r['label'] and r['n'] >= 15 and r['wr'] >= 0.70])
    long_strong = len([r for r in all_results if '做多' in r['label'] or ('做空' not in r['label'] and r['n'] >= 15 and r['wr'] >= 0.75)])
    
    lines.append("| 假设ID | 描述 | 结果 |")
    lines.append("|--------|------|:----:|")
    lines.append(f"| H77-001 | H1欧盘RSI超卖具有统计显著性(≥75%强信号≥5个) | {'✅ confirmed' if h1_eu_strong >= 5 else '⚠️ partial'} (H1 EU强信号: {h1_eu_strong}) |")
    lines.append(f"| H77-002 | M30欧盘信号多于美盘信号 | {'✅ confirmed' if m30_eu_strong > m30_us_strong else '⚠️ equal'} (EU:{m30_eu_strong} US:{m30_us_strong}) |")
    lines.append(f"| H77-003 | 做空信号显著弱于做多信号 | {'✅ confirmed' if short_strong < long_strong / 3 else '⚠️ partial'} (做空强:{short_strong} 做多强:{long_strong}) |")
    lines.append(f"| H77-004 | CB+RSI组合优于纯RSI超卖 | {'✅ confirmed' if count_by_type('CB>=') > count_by_type('RSI14<') else '⚠️ comparable'} |")
    lines.append(f"| H77-005 | 至少8个品种有合格信号(WR≥65% n≥10) | {'✅ confirmed' if len(sym_best) >= 8 else '⚠️ partial'} ({len(sym_best)}品种) |")
    lines.append(f"| H77-006 | EURUSD/GBPUSD/AUDUSD等货币对在M30表现优于H1 | {'✅ confirmed' if len([r for r in all_results if r['timeframe']=='M30' and r['symbol'] in ['EURUSD','GBPUSD','AUDUSD'] and r['wr']>=0.75 and r['n']>=15]) > len([r for r in all_results if r['timeframe']=='H1' and r['symbol'] in ['EURUSD','GBPUSD','AUDUSD'] and r['wr']>=0.75 and r['n']>=15]) else '⚠️ mixed'} |")
    lines.append("")
    
    # 下一轮
    lines.append("## 7. 下一轮建议")
    lines.append("")
    lines.append("基于Round 77发现，建议:")
    lines.append("")
    lines.append("- **P1** 对精英信号做bootstrap置信区间验证(2000次迭代)")
    lines.append("- **P1** 跨品种协同验证 — 联动品种同时超卖的叠加效果(如GBP+AUD)")
    lines.append("- **P2** H1欧盘信号做hold精细优化(+ATR动态止损)")
    lines.append("- **P2** M30 squeeze play扩展 — ATR收缩/扩张机制")
    lines.append("- **P3** 做空信号深化 — 超买+CBull组合在特定时段的表现")
    lines.append("- **P3** 亚盘指数(JP225/HK50/US500)独立策略优化")
    lines.append("")
    
    lines.append("---")
    lines.append(f"*报告由 Candlestick Pattern Researcher 于 {now_str} 自动生成*")
    lines.append(f"*研究范围: 期货外汇14品种 | H1/M30时间框架 | 禁止A股*")
    
    report = '\n'.join(lines)
    
    # 保存
    report_dir = os.path.join(BASE, 'reports')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f'round77_h1m30_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 报告已保存: {report_path}")
    print(f"📊 总候选: {len(all_results)} | 总耗时: {time.time()-t_start:.0f}s")
    
    # Print summary for delivery
    print("\n" + report)

main()
