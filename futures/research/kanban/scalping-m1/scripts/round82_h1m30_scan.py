#!/usr/bin/env python3
"""
Round 82 — H1/M30 欧盘/亚盘模式研究 (自包含版)
时间框架: H1（主）/ M30（辅）
品种: 全部14个MT5品种
焦点: 欧盘/亚盘/美盘超卖反弹 + 连续阴线(CB) + RSI多周期组合

研究假设:
  H1R8-001: H1欧盘RSI超卖反弹 — 延续USTEC RSI<28 WR=100%等核心策略
  H1R8-002: H1/M30连续阴线形态 — CB>=3/4/5 反转做多
  H1R8-003: 亚盘大周期持有 — hold=40/80/160 趋势延续
  H1R8-004: 美盘做空 — 连续阳线+RSI超买回调
  H1R8-005: 多时间框架协同 — H1+M30条件共振
  H1R8-006: 波动率filter改进 — ATR条件过滤
"""
import sys, os, json, time, gc
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# ─── Paths ───
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
STATE_DIR = PROJECT_DIR / "state"
REPORT_DIR = SCRIPT_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)
HOME_REPORT_DIR = Path.home() / "reports"
HOME_REPORT_DIR.mkdir(exist_ok=True)

NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
NOW_FS = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

# 14个MT5品种
SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']

# Session定义 (UTC): 亚盘0-8, 欧盘8-16, 美盘16-24
SESSIONS = {'asia': (0, 8), 'europe': (8, 16), 'us': (16, 24)}

H1_HOLDS = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50, 60, 80]
M30_HOLDS = [1, 2, 3, 5, 8, 10, 13, 15, 20, 25, 30, 40, 50, 60, 80, 100]
PERIODS_PER_YEAR = {"H1": 6000, "M30": 12000}

# ─── Indicator computation (self-contained) ───
def compute_indicators(df):
    """Compute essential indicators for H1/M30 analysis."""
    df = df.copy()
    
    # Session
    hour = df.index.hour if hasattr(df.index, 'hour') else pd.Series(df.index).dt.hour
    df['hour'] = hour
    df['session'] = 'asia'
    df.loc[(hour >= 8) & (hour < 16), 'session'] = 'europe'
    df.loc[(hour >= 16), 'session'] = 'us'
    df['dow'] = df.index.dayofweek
    
    # RSI14
    if 'rsi14' not in df.columns:
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_g = gain.rolling(14, min_periods=14).mean()
        avg_l = loss.rolling(14, min_periods=14).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df['rsi14'] = 100.0 - (100.0 / (1.0 + rs))
    
    # RSI9
    if 'rsi9' not in df.columns:
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_g = gain.rolling(9, min_periods=9).mean()
        avg_l = loss.rolling(9, min_periods=9).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df['rsi9'] = 100.0 - (100.0 / (1.0 + rs))
    
    # RSI7
    if 'rsi7' not in df.columns:
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_g = gain.rolling(7, min_periods=7).mean()
        avg_l = loss.rolling(7, min_periods=7).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df['rsi7'] = 100.0 - (100.0 / (1.0 + rs))
    
    # Consecutive bear candles
    bear = (df['close'] < df['open']).astype(int)
    bull = (df['close'] > df['open']).astype(int)
    
    def count_consecutive(series):
        result = series.copy() * 0
        count = 0
        for i in range(len(series)):
            if series.iloc[i] == 1:
                count += 1
            else:
                count = 0
            result.iloc[i] = count
        return result
    
    df['consecutive_bear'] = count_consecutive(bear)
    df['consecutive_bull'] = count_consecutive(bull)
    
    # ATR14
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    df['atr14'] = atr14
    df['atr14_pct'] = atr14 / close.replace(0, np.nan) * 100
    
    # EMA filters
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    
    # Price relative to EMA
    df['above_ema20'] = (df['close'] > df['ema20']).astype(int)
    df['above_ema50'] = (df['close'] > df['ema50']).astype(int)
    df['above_ema200'] = (df['close'] > df['ema200']).astype(int)
    
    return df


def load_data(timeframe, symbols=None):
    """Load parquet data."""
    tf_dir = DATA_DIR / timeframe
    if not tf_dir.exists():
        print(f"  ⚠ No data directory for {timeframe}")
        return {}
    
    if symbols is None:
        symbols = [p.stem for p in tf_dir.glob("*.parquet")]
    
    result = {}
    for sym in symbols:
        fp = tf_dir / f"{sym}.parquet"
        if not fp.exists():
            continue
        try:
            df = pd.read_parquet(fp)
            if not isinstance(df.index, pd.DatetimeIndex):
                if "time" in df.columns:
                    df = df.set_index(pd.to_datetime(df["time"]))
            df = df.sort_index()
            result[sym] = df
        except Exception as e:
            print(f"  ⚠ Failed to load {sym}: {e}")
    return result


# ─── Cached data loader ───
_CACHE = {}

def get_data(symbol, timeframe):
    key = (symbol, timeframe)
    if key not in _CACHE:
        t0 = time.time()
        data = load_data(timeframe, symbols=[symbol])
        if symbol in data:
            df = data[symbol]
            df = compute_indicators(df)
            _CACHE[key] = df
            print(f"  ✅ {symbol} {timeframe}: {len(df)} rows [{df.index[0].strftime('%m-%d')} → {df.index[-1].strftime('%m-%d %H:%M')}] ({time.time()-t0:.1f}s)")
        else:
            _CACHE[key] = None
    return _CACHE[key]


# ─── Test a single condition ───
def test_condition(df, cond, label, hold_list, min_sig=3, direction='long', timeframe='H1'):
    """Test entry condition and return best result."""
    if cond.sum() == 0:
        return None
    n_signals = int(cond.sum())
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
        rets_arr = np.array(rets)
        wr = float((rets_arr > 0).mean())
        avg_ret = float(rets_arr.mean())
        std = float(rets_arr.std()) if rets_arr.std() > 1e-10 else 1e-10
        periods_year = PERIODS_PER_YEAR.get(timeframe, 6000)
        sharpe = (avg_ret / std) * np.sqrt(periods_year / hold) if avg_ret != 0 else 0
        
        cum = np.cumprod(1 + rets_arr)
        peak = np.maximum.accumulate(cum)
        dd = (peak - cum) / peak
        max_dd = float(dd.max()) if len(dd) > 0 else 0.0
        
        if best is None or wr > best['wr']:
            best = {
                'label': label, 'timeframe': timeframe,
                'hold': hold, 'wr': wr, 'n': len(rets_arr), 'n_signals': n_signals,
                'avg_ret': avg_ret, 'sharpe': sharpe, 'max_dd': max_dd
            }
    
    if best and best['n'] >= min_sig:
        return best
    return None


# ══════════════════════════════════════════════
# MAIN SCANNER
# ══════════════════════════════════════════════

def scan_symbol(symbol, timeframe, df):
    """Run all pattern scans for one symbol on one timeframe."""
    results = []
    hold_list = H1_HOLDS if timeframe == 'H1' else M30_HOLDS
    
    for sess_name, sess_mask_fn in [('asia', df['session'] == 'asia'), 
                                      ('europe', df['session'] == 'europe'),
                                      ('us', df['session'] == 'us')]:
        
        # ── RSI超卖做多 ──
        rsi_entries = [
            ('rsi14', [15, 18, 20, 22, 25, 28, 30]),
            ('rsi9', [15, 18, 20, 25, 30]),
            ('rsi7', [15, 18, 20, 25, 30]),
        ]
        for rsi_col, thresh_list in rsi_entries:
            if rsi_col not in df.columns:
                continue
            for thresh in thresh_list:
                cond = sess_mask_fn & (df[rsi_col] < thresh)
                r = test_condition(df, cond, 
                    f"{symbol} {timeframe} {sess_name} {rsi_col}<{thresh} 做多",
                    hold_list, timeframe=timeframe)
                if r: results.append(r)
        
        # ── RSI超卖 + CB组合 ──
        for cb in [1, 2, 3, 4, 5]:
            for rsi_col, thresh_list in [('rsi14', [18, 20, 25, 28]),
                                          ('rsi9', [18, 20, 25]),
                                          ('rsi7', [18, 20, 25])]:
                if rsi_col not in df.columns:
                    continue
                for thresh in thresh_list:
                    cond = sess_mask_fn & (df[rsi_col] < thresh) & (df['consecutive_bear'] >= cb)
                    r = test_condition(df, cond,
                        f"{symbol} {timeframe} {sess_name} CB>={cb}+{rsi_col}<{thresh} 做多",
                        hold_list, timeframe=timeframe)
                    if r: results.append(r)
        
        # ── 纯CB形态做多 ──
        for cb in [2, 3, 4, 5, 6, 7]:
            cond = sess_mask_fn & (df['consecutive_bear'] >= cb)
            r = test_condition(df, cond,
                f"{symbol} {timeframe} {sess_name} CB>={cb} 做多",
                hold_list, timeframe=timeframe)
            if r: results.append(r)
        
        # ── 做空（连续阳线+RSI超买） ──
        for cb in [2, 3, 4, 5]:
            for rsi_col, thresh_list in [('rsi14', [70, 75, 80]),
                                          ('rsi9', [70, 75, 80])]:
                if rsi_col not in df.columns:
                    continue
                for thresh in thresh_list:
                    cond = sess_mask_fn & (df[rsi_col] > thresh) & (df['consecutive_bull'] >= cb)
                    r = test_condition(df, cond,
                        f"{symbol} {timeframe} {sess_name} CB>={cb}+{rsi_col}>{thresh} 做空",
                        hold_list, direction='short', timeframe=timeframe)
                    if r: results.append(r)
    
    # ── 欧盘特有: 开盘模式 ──
    eu_mask = df['session'] == 'europe'
    for h in [8, 9]:
        cond = eu_mask & (df['hour'] == h)
        r = test_condition(df, cond,
            f"{symbol} {timeframe} EU开盘{h}:00 做多",
            hold_list, timeframe=timeframe)
        if r: results.append(r)
    
    # EU开盘 + RSI超卖
    for rsi_col in ['rsi14<20', 'rsi14<25', 'rsi9<20', 'rsi9<25']:
        if rsi_col.split('<')[0] not in df.columns:
            continue
        rsi_name, thresh_str = rsi_col.split('<')
        thresh = int(thresh_str)
        cond = eu_mask & (df['hour'].isin([8, 9])) & (df[rsi_name] < thresh)
        r = test_condition(df, cond,
            f"{symbol} {timeframe} EU开盘8-9+{rsi_col} 做多",
            hold_list, timeframe=timeframe)
        if r: results.append(r)
    
    return results


def filter_results(results, min_wr=0.65, min_n=8):
    """Filter and sort results."""
    filtered = [r for r in results if r['wr'] >= min_wr and r['n'] >= min_n]
    filtered.sort(key=lambda x: (-x['wr'], -x['sharpe'], -x['n']))
    return filtered


# ══════════════════════════════════════════════
# EXECUTION
# ══════════════════════════════════════════════

def main():
    print("=" * 120)
    print(f"ROUND 82 — H1/M30 K线形态模式研究 — {NOW}")
    print(f"品种: {len(SYMBOLS)}个MT5期货外汇品种")
    print(f"时间框架: H1（主）/ M30（辅）")
    print(f"数据源: Parquet (重采样自M5)")
    print("=" * 120)
    
    all_results = {'H1': {}, 'M30': {}}
    
    for timeframe in ['H1', 'M30']:
        print(f"\n{'─'*120}")
        print(f"📊 SCANNING: {timeframe} — 全部{len(SYMBOLS)}个品种")
        print(f"{'─'*120}")
        
        tf_results = []
        for sym in SYMBOLS:
            df = get_data(sym, timeframe)
            if df is None or df.empty:
                print(f"  ⚠ No data for {sym} {timeframe}")
                continue
            
            t0 = time.time()
            sym_results = scan_symbol(sym, timeframe, df)
            elapsed = time.time() - t0
            print(f"  📈 {sym} {timeframe}: {len(sym_results)} conditions tested ({elapsed:.1f}s)")
            
            # Filter best results
            good = filter_results(sym_results, min_wr=0.70, min_n=10)
            tf_results.extend(sym_results)
            
            if good:
                print(f"     Top findings (WR>=70%, n>=10):")
                for r in good[:5]:
                    print(f"       ⭐ {r['label']}: WR={r['wr']*100:.1f}% n={r['n']} hold={r['hold']} Sharpe={r['sharpe']:.1f}")
        
        all_results[timeframe] = tf_results
        print(f"\n  📊 {timeframe} 总结果: {len(tf_results)} 个条件, 其中合格(WR>=70%, n>=10): {len(filter_results(tf_results))} 个")
    
    # ─── Analysis & Synthesis ───
    print(f"\n{'='*120}")
    print(f"📋 分析综合报告")
    print(f"{'='*120}")
    
    for timeframe in ['H1', 'M30']:
        results = all_results[timeframe]
        good = filter_results(results, min_wr=0.75, min_n=10)
        excellent = filter_results(results, min_wr=0.85, min_n=10)
        elite = filter_results(results, min_wr=0.90, min_n=15)
        
        print(f"\n{'─'*60}")
        print(f"📊 {timeframe} 分析汇总")
        print(f"{'─'*60}")
        print(f"  总测试条件数: {len(results)}")
        print(f"  合格 (WR>=75%, n>=10): {len(good)}")
        print(f"  优秀 (WR>=85%, n>=10): {len(excellent)}")
        print(f"  精英 (WR>=90%, n>=15): {len(elite)}")
        
        # Top 30 by WR
        sorted_results = sorted(good, key=lambda x: (-x['wr'], -x['n'], -x['sharpe']))
        
        print(f"\n  🏆 {timeframe} Top 30 (按WR排序, WR>=75%, n>=10):")
        print(f"  {'#':<4} {'品种':<10} {'策略':<40} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8}")
        print(f"  {'-'*4} {'-'*10} {'-'*40} {'-'*8} {'-'*6} {'-'*6} {'-'*8}")
        for i, r in enumerate(sorted_results[:30]):
            label_short = r['label']
            print(f"  {i+1:<4} {label_short:<80} {r['wr']*100:<7.1f}% {r['n']:<6} {r['hold']:<6} {r['sharpe']:<8.1f}")
        
        # Per-symbol best
        print(f"\n  📈 {timeframe} 各品种最佳策略:")
        best_per_sym = {}
        for r in sorted_results:
            sym = r['label'].split(' ')[0]
            if sym not in best_per_sym or r['wr'] > best_per_sym[sym]['wr']:
                best_per_sym[sym] = r
        
        for sym in SYMBOLS:
            if sym in best_per_sym:
                r = best_per_sym[sym]
                print(f"    {sym:<10}: {r['label']:<55} WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']} Sharpe={r['sharpe']:.1f}")
        
        # Session analysis
        print(f"\n  ⏰ {timeframe} Session分布 (WR>=75%):")
        sess_counts = defaultdict(int)
        for r in good:
            for sess in ['asia', 'europe', 'us']:
                if sess in r['label'].lower():
                    sess_counts[sess] += 1
                    break
        for sess in ['asia', 'europe', 'us']:
            print(f"    {sess:<8}: {sess_counts.get(sess, 0)} 个合格条件")
        
        # RSI threshold analysis
        print(f"\n  📐 {timeframe} RSI阈值偏好:")
        threshold_stats = defaultdict(lambda: {'count': 0, 'total_wr': 0.0})
        for r in good:
            label = r['label']
            for rsi_type in ['rsi14', 'rsi9', 'rsi7']:
                if rsi_type in label:
                    # Extract threshold
                    import re
                    m = re.search(rf'{rsi_type}<(\d+)', label)
                    if m:
                        th = int(m.group(1))
                        key = f"{rsi_type}<{th}"
                        threshold_stats[key]['count'] += 1
                        threshold_stats[key]['total_wr'] += r['wr']
        
        for key in sorted(threshold_stats.keys()):
            stats = threshold_stats[key]
            avg_wr = stats['total_wr'] / stats['count'] if stats['count'] > 0 else 0
            print(f"    {key:<12}: {stats['count']:>3} conditions, avg WR={avg_wr*100:.1f}%")
        
        # Direction analysis
        long_count = sum(1 for r in good if '做多' in r['label'])
        short_count = sum(1 for r in good if '做空' in r['label'])
        print(f"\n  📌 {timeframe} 方向分布:")
        print(f"    做多: {long_count} | 做空: {short_count}")
    
    # ─── Cross-Timeframe Analysis ───
    print(f"\n{'─'*120}")
    print(f"📊 跨时间框架分析 (H1 vs M30 协同)")
    print(f"{'─'*120}")
    
    h1_good = filter_results(all_results['H1'], min_wr=0.75, min_n=10)
    m30_good = filter_results(all_results['M30'], min_wr=0.75, min_n=10)
    
    # Find symbols with good results on both timeframes
    h1_syms = set(r['label'].split(' ')[0] for r in h1_good)
    m30_syms = set(r['label'].split(' ')[0] for r in m30_good)
    both_syms = h1_syms & m30_syms
    
    print(f"  H1 有合格信号的品种: {len(h1_syms)}: {', '.join(sorted(h1_syms))}")
    print(f"  M30有合格信号的品种: {len(m30_syms)}: {', '.join(sorted(m30_syms))}")
    print(f"  双TF都有信号的品种: {len(both_syms)}: {', '.join(sorted(both_syms))}")
    
    # ─── Save Report ───
    report = {
        "round": 82,
        "timestamp": NOW,
        "timeframes": ["H1", "M30"],
        "symbols": SYMBOLS,
        "summary": {
            "H1": {
                "total": len(all_results['H1']),
                "good": len(filter_results(all_results['H1'], min_wr=0.75, min_n=10)),
                "excellent": len(filter_results(all_results['H1'], min_wr=0.85, min_n=10)),
                "elite": len(filter_results(all_results['H1'], min_wr=0.90, min_n=15)),
            },
            "M30": {
                "total": len(all_results['M30']),
                "good": len(filter_results(all_results['M30'], min_wr=0.75, min_n=10)),
                "excellent": len(filter_results(all_results['M30'], min_wr=0.85, min_n=10)),
                "elite": len(filter_results(all_results['M30'], min_wr=0.90, min_n=15)),
            }
        },
        "top_findings_H1": [r for r in sorted(good, key=lambda x: (-x['wr'], -x['n'], -x['sharpe']))[:50]],
        "top_findings_M30": [r for r in sorted(m30_good, key=lambda x: (-x['wr'], -x['n'], -x['sharpe']))[:50]],
    }
    
    # Save JSON report
    json_path = REPORT_DIR / f"round82_h1m30_report_{NOW_FS}.json"
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  💾 JSON报告已保存: {json_path}")
    
    # Save MD report
    md_path = HOME_REPORT_DIR / f"round82_h1m30_report_{NOW_FS}.md"
    with open(md_path, 'w') as f:
        f.write(generate_markdown(report))
    print(f"  💾 Markdown报告已保存: {md_path}")
    
    print(f"\n{'='*120}")
    print("✅ R82 H1/M30 研究完成")
    print(f"{'='*120}")
    
    return report


def generate_markdown(report):
    """Generate markdown report from findings."""
    lines = []
    lines.append(f"# Round 82 — H1/M30 K线形态研究轮次")
    lines.append(f"")
    lines.append(f"**生成时间**: {report['timestamp']}")
    lines.append(f"**品种**: {len(report['symbols'])}个MT5期货外汇品种")
    lines.append(f"**时间框架**: H1（主）/ M30（辅）")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 1. 执行摘要")
    lines.append(f"")
    for tf in ['H1', 'M30']:
        s = report['summary'][tf]
        lines.append(f"- **{tf}**: 共测试 {s['total']} 个条件，合格(WR≥75%) {s['good']} 个，优秀(WR≥85%) {s['excellent']} 个，精英(WR≥90%) {s['elite']} 个")
    lines.append(f"")
    lines.append(f"## 2. H1顶级发现排行榜")
    lines.append(f"")
    lines.append(f"| 排名 | 品种 | 策略 | WR | n | Hold | Sharpe |")
    lines.append(f"|:---:|:----:|:-----|:-:|:-:|:----:|:------:|")
    for i, r in enumerate(report['top_findings_H1'][:30]):
        label = r['label']
        lines.append(f"| {i+1} | | {label} | {r['wr']*100:.1f}% | {r['n']} | {r['hold']} | {r['sharpe']:.1f} |")
    lines.append(f"")
    lines.append(f"## 3. M30顶级发现排行榜")
    lines.append(f"")
    lines.append(f"| 排名 | 品种 | 策略 | WR | n | Hold | Sharpe |")
    lines.append(f"|:---:|:----:|:-----|:-:|:-:|:----:|:------:|")
    for i, r in enumerate(report['top_findings_M30'][:30]):
        label = r['label']
        lines.append(f"| {i+1} | | {label} | {r['wr']*100:.1f}% | {r['n']} | {r['hold']} | {r['sharpe']:.1f} |")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"*报告由Reze Orchestrator自动生成*")
    
    return '\n'.join(lines)


if __name__ == '__main__':
    report_data = main()
