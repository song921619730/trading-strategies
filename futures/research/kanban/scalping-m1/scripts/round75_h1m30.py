#!/usr/bin/env python3
"""
Round 75 — H1/M30 欧盘/亚盘模式研究

时间框架: H1（主）/ M30（辅）
品种: 全部14个MT5品种
焦点: 欧盘/亚盘时段RSI超卖反弹 + 连续阴阳线(CBull)组合
"""
import sys, os, json, time
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_data, compute_indicators, list_available_symbols

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 14 MT5品种
SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']

# Session定义 (UTC)
# 亚盘: 0:00-7:59, 欧盘: 8:00-15:59, 美盘: 16:00-23:59
SESSION_MAP = {
    'asia': (0, 8),
    'europe': (8, 16),
    'us': (16, 24)
}

def add_session_features(df):
    """添加session和连续阴阳线特征"""
    df = df.copy()
    hour = df.index.hour
    df['session'] = 'asia'
    df.loc[(hour >= 8) & (hour < 16), 'session'] = 'europe'
    df.loc[(hour >= 16), 'session'] = 'us'
    
    # 连续阳线 (consecutive_bull)
    bull = (df['close'] > df['open']).astype(int)
    df['consecutive_bull'] = bull.groupby((bull == 0).cumsum()).cumsum()
    
    # 连续阴线 (consecutive_bear)
    bear = (df['close'] < df['open']).astype(int)
    df['consecutive_bear'] = bear.groupby((bear == 0).cumsum()).cumsum()
    
    df['hour'] = hour
    df['dow'] = df.index.dayofweek
    return df

def test_condition(df, cond, label, hold_list, min_sig=3, direction='long'):
    """通用条件测试器"""
    if cond.sum() == 0:
        return None
    n = int(cond.sum())
    entries = df[cond]
    best = {'hold': 0, 'wr': 0.0, 'avg_ret': 0.0, 'n': 0, 'sharpe': 0.0, 'max_dd': 0.0}
    
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
        sharpe = avg_ret / std * np.sqrt(len(rets) / hold) if avg_ret != 0 else 0
        
        if wr > best['wr']:
            best = {'hold': hold, 'wr': wr, 'avg_ret': avg_ret, 'n': len(rets),
                    'sharpe': sharpe, 'max_dd': float(rets.min())}
    
    if best['n'] >= min_sig:
        best['label'] = label
        best['n_signals'] = n  # 原始信号数
        return best
    return None

def run_grid_scan(df, symbol, timeframe):
    """对单个品种运行H1/M30网格扫描"""
    results = []
    sessions = ['asia', 'europe', 'us']
    
    # ========== 1. RSI超卖做多 ==========
    rsi_thresholds = {
        'rsi14<20': 20, 'rsi14<25': 25, 'rsi14<30': 30, 'rsi14<35': 35,
        'rsi9<20': 20, 'rsi9<25': 25, 'rsi9<30': 30, 'rsi9<35': 35,
        'rsi7<20': 20, 'rsi7<25': 25, 'rsi7<30': 30, 'rsi7<35': 35,
    }
    hold_list = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50, 60]
    
    for sess in sessions:
        sess_mask = df['session'] == sess
        
        # 纯RSI超卖
        for rsi_col, thresh in rsi_thresholds.items():
            if rsi_col not in df.columns:
                continue
            cond = sess_mask & (df[rsi_col] < thresh)
            r = test_condition(df, cond, f"{symbol} {timeframe} {sess} {rsi_col}<{thresh} 做多",
                              hold_list, direction='long')
            if r:
                results.append(r)
        
        # RSI超卖 + 连续阴线
        for cb in [1, 2, 3, 4, 5]:
            for rsi_col, thresh in rsi_thresholds.items():
                if rsi_col not in df.columns:
                    continue
                if thresh > 30:
                    continue  # 跳过太宽松的条件
                cond = sess_mask & (df[rsi_col] < thresh) & (df['consecutive_bear'] >= cb)
                r = test_condition(df, cond, f"{symbol} {timeframe} {sess} CB>={cb} {rsi_col}<{thresh} 做多", 
                                  hold_list, direction='long')
                if r:
                    results.append(r)
        
        # 连续阴线纯形态 (不做RSI过滤)
        for cb in [2, 3, 4, 5, 6]:
            cond = sess_mask & (df['consecutive_bear'] >= cb)
            r = test_condition(df, cond, f"{symbol} {timeframe} {sess} CB>={cb} 做多",
                              hold_list, direction='long')
            if r:
                results.append(r)
    
    # ========== EU特有: 欧盘开盘模式 ==========
    eu_mask = df['session'] == 'europe'
    for h in [8, 9]:
        cond = (df['hour'] == h)
        r = test_condition(df, cond, f"{symbol} {timeframe} EU开盘{h}:00 做多", hold_list, direction='long')
        if r:
            results.append(r)
    
    # EU开盘 + RSI超卖
    for rsi_col in ['rsi14<25', 'rsi14<30', 'rsi9<25', 'rsi9<30']:
        if rsi_col not in df.columns:
            continue
        cond = eu_mask & (df['hour'].isin([8, 9])) & (df[rsi_col] < int(rsi_col.split('<')[1]))
        r = test_condition(df, cond, f"{symbol} {timeframe} EU开盘8-9 + {rsi_col} 做多", hold_list, direction='long')
        if r:
            results.append(r)
    
    # ========== ASIA特有: 亚盘低点反弹 ==========
    asia_mask = df['session'] == 'asia'
    for h in [0, 1, 2]:
        for rsi_col in ['rsi14<25', 'rsi14<30']:
            if rsi_col not in df.columns:
                continue
            cond = asia_mask & (df['hour'] == h) & (df[rsi_col] < int(rsi_col.split('<')[1]))
            r = test_condition(df, cond, f"{symbol} {timeframe} ASIA{h}:00 + {rsi_col} 做多", hold_list, direction='long')
            if r:
                results.append(r)
    
    # ========== 做空测试 (对称) ==========
    rsi_overbought = {'rsi14>70': 70, 'rsi14>75': 75, 'rsi14>80': 80, 'rsi9>70': 70, 'rsi9>75': 75}
    for sess in sessions:
        sess_mask = df['session'] == sess
        for rsi_col, thresh in rsi_overbought.items():
            if rsi_col not in df.columns:
                continue
            cond = sess_mask & (df[rsi_col] > thresh)
            r = test_condition(df, cond, f"{symbol} {timeframe} {sess} {rsi_col} 做空", 
                              hold_list, direction='short')
            if r:
                results.append(r)
        
        for cb in [2, 3, 4]:
            cond = sess_mask & (df['consecutive_bull'] >= cb)
            r = test_condition(df, cond, f"{symbol} {timeframe} {sess} CBull>={cb} 做空", 
                              hold_list, direction='short')
            if r:
                results.append(r)
    
    return results

def rank_results(results, min_n=5, wr_threshold=60):
    """筛选并排序结果"""
    df = pd.DataFrame(results)
    if len(df) == 0:
        return df
    df['wr_pct'] = df['wr'] * 100
    df = df[df['n'] >= min_n].copy()
    df = df[df['wr_pct'] >= wr_threshold].copy()
    if len(df) > 0:
        df = df.sort_values('wr_pct', ascending=False)
    return df

# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
print("=" * 120)
print(f"ROUND 75 — H1/M30 欧盘/亚盘模式研究 — {NOW}")
print(f"数据: 14 MT5品种, H1(主)/M30(辅)")
print("=" * 120)

all_results = {}

for timeframe in ['H1', 'M30']:
    print(f"\n{'#'*100}")
    print(f"## {timeframe} 框架分析")
    print(f"{'#'*100}")
    
    data = load_data(timeframe=timeframe, symbols=SYMBOLS)
    tf_results = []
    
    for sym in SYMBOLS:
        if sym not in data:
            print(f"  ⚠ {sym}: 无数据")
            continue
        
        df = data[sym]
        df = compute_indicators(df)
        df = add_session_features(df)
        
        print(f"\n  📊 {sym} {timeframe}: {len(df)} rows [{df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d %H:%M')}]")
        
        # Session breakdown
        for sess in ['asia', 'europe', 'us']:
            cnt = (df['session'] == sess).sum()
            print(f"     {sess}: {cnt} candles ({cnt/len(df)*100:.1f}%)")
        
        r = run_grid_scan(df, sym, timeframe)
        tf_results.extend(r)
        print(f"     → 发现 {len(r)} 个候选模式")
    
    ranked = rank_results(tf_results, min_n=5, wr_threshold=60)
    all_results[timeframe] = ranked
    
    print(f"\n┌{'─'*90}┐")
    print(f"│ {timeframe} 最佳模式 (WR≥60%, n≥5)")
    print(f"└{'─'*90}┘")
    if len(ranked) > 0:
        top20 = ranked.head(40)
        print(f"{'排名':<4} {'品种':<10} {'Session':<8} {'条件':<55} {'Hold':<6} {'WR':<8} {'n':<6} {'AvgRet':<10} {'Sharpe':<8}")
        print(f"{'─'*4} {'─'*10} {'─'*8} {'─'*55} {'─'*6} {'─'*8} {'─'*6} {'─'*10} {'─'*8}")
        for i, (_, row) in enumerate(top20.iterrows()):
            label = row.get('label', '')
            # 简化显示
            parts = label.split(' ')
            sym_name = parts[0] if len(parts) > 0 else ''
            cond_short = ' '.join(parts[2:]) if len(parts) > 2 else label
            print(f"{i+1:<4} {sym_name:<10} {parts[2] if len(parts)>2 else '':<8} {cond_short:<55} {int(row['hold']):<6} {row['wr_pct']:<7.1f}% {int(row['n']):<6} {row['avg_ret']*100:<9.3f}% {row['sharpe']:<8.2f}")
    else:
        print("  (无符合条件的模式)")
    
    # 按品种汇总
    print(f"\n┌{'─'*90}┐")
    print(f"│ {timeframe} 按品种最佳模式")
    print(f"└{'─'*90}┘")
    for sym in SYMBOLS:
        sym_data = ranked[ranked['label'].str.startswith(sym, na=False)] if len(ranked) > 0 else pd.DataFrame()
        if len(sym_data) > 0:
            best = sym_data.iloc[0]
            print(f"  {sym:<10} | WR={best['wr_pct']:.1f}% | n={int(best['n'])} | Hold={int(best['hold'])} | {best.get('label','')[:60]}")
        else:
            n_results = len([r for r in tf_results if r.get('label','').startswith(sym)])
            print(f"  {sym:<10} | 无合格模式 (WR<60%或n<5) [共{n_results}个候选]")

# ============ H1 vs M30 跨周期一致性 ============
print(f"\n{'#'*100}")
print(f"## H1 vs M30 跨周期一致性检查")
print(f"{'#'*100}")

for sym in SYMBOLS:
    h1_best = None
    m30_best = None
    if 'H1' in all_results and len(all_results['H1']) > 0:
        h1_matches = all_results['H1'][all_results['H1']['label'].str.startswith(sym, na=False)]
        if len(h1_matches) > 0:
            h1_best = h1_matches.iloc[0]
    if 'M30' in all_results and len(all_results['M30']) > 0:
        m30_matches = all_results['M30'][all_results['M30']['label'].str.startswith(sym, na=False)]
        if len(m30_matches) > 0:
            m30_best = m30_matches.iloc[0]
    
    if h1_best is not None and m30_best is not None:
        print(f"  {sym:<10} | H1: WR={h1_best['wr_pct']:.1f}% n={int(h1_best['n'])} M30: WR={m30_best['wr_pct']:.1f}% n={int(m30_best['n'])} {'✅ 一致' if abs(h1_best['wr_pct'] - m30_best['wr_pct']) < 10 else '⚠️ 差异较大'}")
    elif h1_best is not None:
        print(f"  {sym:<10} | H1: WR={h1_best['wr_pct']:.1f}% n={int(h1_best['n'])}  M30: 无合格模式")
    elif m30_best is not None:
        print(f"  {sym:<10} | H1: 无合格模式  M30: WR={m30_best['wr_pct']:.1f}% n={int(m30_best['n'])}")
    else:
        print(f"  {sym:<10} | 双框架均无合格模式")

# ============ 欧盘专题 ============
print(f"\n{'#'*100}")
print(f"## 欧盘(EU)专题深度分析")
print(f"{'#'*100}")
for timeframe in ['H1', 'M30']:
    if timeframe not in all_results:
        continue
    ranked = all_results[timeframe]
    eu_results = ranked[ranked['label'].str.contains('europe', case=False, na=False)]
    if len(eu_results) > 0:
        print(f"\n  --- {timeframe} 欧盘最佳 ---")
        for i, (_, row) in enumerate(eu_results.head(15).iterrows()):
            print(f"  {i+1}. {row['label'][:80]} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])} AvgRet={row['avg_ret']*100:.3f}%")

print(f"\n{'#'*100}")
print(f"## 亚盘(ASIA)专题深度分析")
print(f"{'#'*100}")
for timeframe in ['H1', 'M30']:
    if timeframe not in all_results:
        continue
    ranked = all_results[timeframe]
    asia_results = ranked[ranked['label'].str.contains('asia', case=False, na=False)]
    if len(asia_results) > 0:
        print(f"\n  --- {timeframe} 亚盘最佳 ---")
        for i, (_, row) in enumerate(asia_results.head(15).iterrows()):
            print(f"  {i+1}. {row['label'][:80]} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])} AvgRet={row['avg_ret']*100:.3f}%")

# ============ 保存结果 ============
output = {
    'timestamp': NOW,
    'round': 75,
    'focus': 'H1/M30 欧盘/亚盘模式研究',
    'symbols': SYMBOLS,
    'summary': {}
}
for tf in ['H1', 'M30']:
    if tf in all_results:
        ranked = all_results[tf]
        output['summary'][tf] = {
            'total_candidates': len(all_results.get(tf, pd.DataFrame())),
            'qualified_patterns': len(ranked),
            'best_by_symbol': {}
        }
        for sym in SYMBOLS:
            sym_data = ranked[ranked['label'].str.startswith(sym, na=False)] if len(ranked) > 0 else pd.DataFrame()
            if len(sym_data) > 0:
                best = sym_data.iloc[0]
                output['summary'][tf]['best_by_symbol'][sym] = {
                    'wr_pct': round(float(best['wr_pct']), 1),
                    'n': int(best['n']),
                    'hold': int(best['hold']),
                    'label': str(best.get('label', '')),
                    'sharpe': round(float(best['sharpe']), 2),
                    'avg_ret_pct': round(float(best['avg_ret'] * 100), 3)
                }

# 保存到文件
report_dir = os.path.join(BASE, 'reports')
os.makedirs(report_dir, exist_ok=True)
report_path = os.path.join(report_dir, 'round75_h1m30_report.txt')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(f"Round 75 — H1/M30 欧盘/亚盘模式研究报告\n")
    f.write(f"生成时间: {NOW}\n")
    f.write(f"{'='*100}\n\n")
    
    for tf in ['H1', 'M30']:
        if tf in all_results:
            ranked = all_results[tf]
            f.write(f"## {tf} 最佳模式 (WR≥60%, n≥5)\n\n")
            if len(ranked) > 0:
                for i, (_, row) in enumerate(ranked.head(50).iterrows()):
                    f.write(f"{i+1}. {row['label']} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])} AvgRet={row['avg_ret']*100:.3f}% Sharpe={row['sharpe']:.2f}\n")
            else:
                f.write("  (无合格模式)\n")
            f.write("\n")
    
    f.write(f"\n## 原始数据\n")
    for tf in ['H1', 'M30']:
        if tf in all_results:
            ranked = all_results[tf]
            f.write(f"\n### {tf} (共{len(ranked)}个合格)\n")
            if len(ranked) > 0:
                f.write(ranked.to_csv(sep='|'))

print(f"\n✅ 报告保存到: {report_path}")
print(f"📊 H1合格模式: {len(all_results.get('H1', pd.DataFrame()))}")
print(f"📊 M30合格模式: {len(all_results.get('M30', pd.DataFrame()))}")
