#!/usr/bin/env python3
"""
grid_engine.py — Scalping M1/M5 Pattern Mining Engine
======================================================
职责: 在 M1/M5 时间框架下挖掘高胜率K线形态和微观结构模式。
输出: 形态统计 + 预测能力分析 + 信号质量评分

核心假设: M1/M5 的超短线波动更多受局部供需失衡驱动，
传统H1形态需要重新校准阈值，并引入微观结构特征。
"""
import json, os, sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

CST = timezone(timedelta(hours=8))

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(PROJECT_DIR, "data", "m1m5_latest.json")
REPORT_DIR = os.path.join(PROJECT_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# ─────────────────────────────────────────────────
# TARGET: M1/M5 超短线高胜率模式
# ─────────────────────────────────────────────────

SCALPING_PATTERNS_M1 = {
    # --- 微观结构形态 (Micro-structure) ---
    "micro_bull_engulf": {
        "name": "微看涨吞没",
        "n_candles": 2,
        "desc": "M1级别: 小阴线后紧接大阳线(体长>=2倍阴线)",
    },
    "micro_bear_engulf": {
        "name": "微看跌吞没",
        "n_candles": 2,
        "desc": "M1级别: 小阳线后紧接大阴线(体长>=2倍阳线)",
    },
    "micro_doji_reversal": {
        "name": "十字星反转",
        "n_candles": 2,
        "desc": "M1级别: 趋势中十字星后反向大线",
    },
    "micro_two_legged_pullback": {
        "name": "两段式回调",
        "n_candles": 3,
        "desc": "M5级别: 急跌后小反弹再急跌(空头陷阱)",
    },
    "micro_breakout_retest": {
        "name": "突破回测",
        "n_candles": 3,
        "desc": "M5级别: 关键位突破后回测再加速",
    },
    "micro_volume_climax": {
        "name": "天量高潮",
        "n_candles": 1,
        "desc": "M1/M5: tick_volume突增>=近期均值200%后的反转",
    },
    "micro_staircase_bull": {
        "name": "阶梯上涨",
        "n_candles": 5,
        "desc": "M5级别: 连续阶梯式抬高低点+高点的持续形态",
    },
    "micro_staircase_bear": {
        "name": "阶梯下跌",
        "n_candles": 5,
        "desc": "M5级别: 连续阶梯式降低高点+低点的持续形态",
    },
    "micro_pinbar_bull": {
        "name": "锤头线(微)",
        "n_candles": 1,
        "desc": "M1/M5: 长下影线>=实体2倍, 实体位于上端",
    },
    "micro_pinbar_bear": {
        "name": "射击之星(微)",
        "n_candles": 1,
        "desc": "M1/M5: 长上影线>=实体2倍, 实体位于下端",
    },
    "micro_narrow_range_7": {
        "name": "窄幅7连",
        "n_candles": 7,
        "desc": "M1: 连续7根K线振幅持续缩小, 突破前兆",
    },
    "micro_absorption": {
        "name": "吸收形态",
        "n_candles": 3,
        "desc": "M5: 大实体后跟随多个小实体(吸收动能)",
    },
}


# ─────────────────────────────────────────────────
# PATTERN DETECTORS (M1/M5 specific thresholds)
# ─────────────────────────────────────────────────

def detect_micro_engulfing(candles, i, direction="bull"):
    """检测微级别吞没形态 (M1/M5)"""
    if i < 1:
        return False
    c1, c2 = candles[i-1], candles[i]
    o1, c1c = c1['open'], c1['close']
    o2, c2c = c2['open'], c2['close']
    body1 = abs(c1c - o1)
    body2 = abs(c2c - o2)
    if body1 <= 0 or body2 <= 0:
        return False
    if direction == "bull":
        # 小阴线 + 大阳线完全吞没
        if c1c < o1 and c2c > o2 and c2c > o1 and o2 < c1c and body2 >= body1 * 1.5:
            return True
    else:
        # 小阳线 + 大阴线完全吞没
        if c1c > o1 and c2c < o2 and c2c < o1 and o2 > c1c and body2 >= body1 * 1.5:
            return True
    return False


def detect_doji_reversal(candles, i):
    """十字星反转: 趋势中的doji后反向K线"""
    if i < 1:
        return False
    c1, c2 = candles[i-1], candles[i]
    o1, h1, l1, c1c = c1['open'], c1['high'], c1['low'], c1['close']
    o2, h2, l2, c2c = c2['open'], c2['high'], c2['low'], c2['close']
    body1 = abs(c1c - o1)
    body2 = abs(c2c - o2)
    rng1 = h1 - l1
    rng2 = h2 - l2
    if rng1 <= 0 or rng2 <= 0:
        return False
    # is c1 a doji?
    is_doji = body1 <= rng1 * 0.15
    if not is_doji:
        return False
    # does c2 reverse?
    # c1 had a direction bias before doji
    prev = candles[i-2] if i >= 2 else None
    if prev is None:
        return False
    trend_up = prev['close'] > prev['open']
    trend_down = prev['close'] < prev['open']
    if trend_up and c2c < o2 and c2c < c1c:
        return "bear_reversal"  # doji after uptrend → bear candle
    if trend_down and c2c > o2 and c2c > c1c:
        return "bull_reversal"
    return False


def detect_staircase(candles, i, direction="bull", lookback=5):
    """检测阶梯形态 (M5)"""
    if i < lookback - 1:
        return False
    segment = candles[i-lookback+1:i+1]
    if len(segment) < lookback:
        return False
    if direction == "bull":
        lows = [c['low'] for c in segment]
        highs = [c['high'] for c in segment]
        if all(lows[j] <= lows[j+1] for j in range(len(lows)-1)):
            if all(highs[j] <= highs[j+1] for j in range(len(highs)-1)):
                return True
    else:
        lows = [c['low'] for c in segment]
        highs = [c['high'] for c in segment]
        if all(lows[j] >= lows[j+1] for j in range(len(lows)-1)):
            if all(highs[j] >= highs[j+1] for j in range(len(highs)-1)):
                return True
    return False


def detect_pinbar(candles, i, direction="bull"):
    """长影线形态 (M1/M5), 影线>=实体2倍"""
    if i < 0:
        return False
    c = candles[i]
    o, h, l, cl = c['open'], c['high'], c['low'], c['close']
    rng = h - l
    body = abs(cl - o)
    if rng <= 0 or body <= 0:
        return False
    if direction == "bull":
        lower_shadow = min(o, cl) - l
        if lower_shadow >= body * 2 and lower_shadow >= rng * 0.6:
            return True
    else:
        upper_shadow = h - max(o, cl)
        if upper_shadow >= body * 2 and upper_shadow >= rng * 0.6:
            return True
    return False


def detect_narrow_range_7(candles, i):
    """窄幅7连: 连续7根振幅收缩"""
    if i < 6:
        return False
    ranges = []
    for j in range(i-6, i+1):
        c = candles[j]
        rng = c['high'] - c['low']
        if rng <= 0:
            return False
        ranges.append(rng)
    # Check if ranges are progressively narrowing
    avg_first3 = sum(ranges[:3]) / 3
    avg_last3 = sum(ranges[-3:]) / 3
    if avg_last3 <= avg_first3 * 0.6 and avg_first3 > 0:
        return True
    return False


def detect_absorption(candles, i):
    """吸收形态: 大实体+多个小实体"""
    if i < 3:
        return False
    c_main = candles[i-3]
    c_follow = candles[i-2:i+1]
    main_body = abs(c_main['close'] - c_main['open'])
    if main_body <= 0:
        return False
    # Following candles should have smaller bodies
    avg_follow_body = sum(abs(c['close'] - c['open']) for c in c_follow) / len(c_follow)
    if avg_follow_body <= main_body * 0.4:
        return True
    return False


def detect_volume_climax(candles, i, lookback=20):
    """天量高潮: tick_volume突增后的反转"""
    if i < lookback:
        return False
    vol_now = candles[i]['tick_volume']
    prev_vols = [candles[j]['tick_volume'] for j in range(i-lookback, i)]
    avg_vol = sum(prev_vols) / len(prev_vols)
    if avg_vol <= 0:
        return False
    if vol_now >= avg_vol * 2.0:
        return True
    return False


# ─────────────────────────────────────────────────
# GRID ENGINE: 在M1/M5数据网格中扫描所有模式
# ─────────────────────────────────────────────────

class GridEngine:
    """在给定品种和时间框架的数据网格中扫描所有预定义模式"""
    
    def __init__(self, data):
        self.data = data  # from fetch_m1m5_data.py output
        self.all_results = {}
    
    def scan_symbol(self, sym, tf):
        """扫描单个品种单个时间框架"""
        candles = self.data['data'][sym]['candles'].get(tf, [])
        if isinstance(candles, dict) or len(candles) < 20:
            return None
        
        patterns_found = []
        
        # Single candle patterns
        for i in range(len(candles)):
            # Pinbars
            if detect_pinbar(candles, i, "bull"):
                patterns_found.append({
                    "pattern": "micro_pinbar_bull",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
            if detect_pinbar(candles, i, "bear"):
                patterns_found.append({
                    "pattern": "micro_pinbar_bear",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
            # Volume climax
            if detect_volume_climax(candles, i):
                patterns_found.append({
                    "pattern": "micro_volume_climax",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
        
        # Multi-candle patterns
        for i in range(1, len(candles)):
            # Engulfing
            if detect_micro_engulfing(candles, i, "bull"):
                patterns_found.append({
                    "pattern": "micro_bull_engulf",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
            if detect_micro_engulfing(candles, i, "bear"):
                patterns_found.append({
                    "pattern": "micro_bear_engulf",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
            # Doji reversal
            dr = detect_doji_reversal(candles, i)
            if dr:
                patterns_found.append({
                    "pattern": f"micro_doji_{dr}",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
        
        for i in range(4, len(candles)):
            # Staircase
            if detect_staircase(candles, i, "bull"):
                patterns_found.append({
                    "pattern": "micro_staircase_bull",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
            if detect_staircase(candles, i, "bear"):
                patterns_found.append({
                    "pattern": "micro_staircase_bear",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
        
        for i in range(3, len(candles)):
            # Absorption
            if detect_absorption(candles, i):
                patterns_found.append({
                    "pattern": "micro_absorption",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
        
        for i in range(6, len(candles)):
            # Narrow range 7
            if detect_narrow_range_7(candles, i):
                patterns_found.append({
                    "pattern": "micro_narrow_range_7",
                    "time": candles[i]['time'],
                    "index": i,
                    "price": candles[i]['close'],
                })
        
        return patterns_found
    
    def evaluate_predictions(self, candles, patterns, lookahead=5):
        """评估形态出现后的价格预测能力 (M1/M5版本)"""
        results = []
        for p in patterns:
            idx = p['index']
            if idx + lookahead >= len(candles):
                continue
            
            entry_price = candles[idx]['close']
            
            # 1, 2, 3, 5, 10 candles ahead
            eval_points = {}
            for n in [1, 2, 3, 5, 10]:
                if idx + n >= len(candles):
                    continue
                fc = candles[idx + n]['close']
                chg = (fc - entry_price) / entry_price * 100
                
                # Max favorable move
                if chg > 0:
                    max_high = max(c['high'] for c in candles[idx:idx+n+1])
                    max_fav = (max_high - entry_price) / entry_price * 100
                    max_unfav = min(((c['low'] - entry_price) / entry_price * 100) for c in candles[idx:idx+n+1])
                else:
                    max_low = min(c['low'] for c in candles[idx:idx+n+1])
                    max_fav = (entry_price - max_low) / entry_price * 100  # positive for short
                    max_unfav = max(((c['high'] - entry_price) / entry_price * 100) for c in candles[idx:idx+n+1])
                
                eval_points[f'n{n}'] = {
                    'change_pct': round(chg, 4),
                    'direction': 1 if chg > 0 else (-1 if chg < 0 else 0),
                    'max_favorable_pct': round(max_fav, 4),
                    'max_unfavorable_pct': round(max_unfav, 4),
                }
            
            p['eval'] = eval_points
            results.append(p)
        
        return results
    
    def aggregate_stats(self, all_analyzed):
        """汇总所有形态的统计结果"""
        stats = defaultdict(lambda: {
            'count': 0, 'up_1': 0, 'down_1': 0,
            'chg_n1': [], 'chg_n3': [], 'chg_n5': [], 'chg_n10': [],
            'max_fav_n5': [], 'max_unfav_n5': [],
            'symbols': defaultdict(int),
        })
        
        for sym, tf_data in all_analyzed.items():
            for tf, patterns in tf_data.items():
                for p in patterns:
                    pname = p['pattern']
                    s = stats[pname]
                    s['count'] += 1
                    s['symbols'][sym] += 1
                    
                    ev = p.get('eval', {})
                    for n_key in ['n1', 'n3', 'n5', 'n10']:
                        if n_key in ev:
                            s[f'chg_{n_key}'].append(ev[n_key]['change_pct'])
                            if ev[n_key]['direction'] > 0:
                                s[f'up_{n_key[1:]}'] = s.get(f'up_{n_key[1:]}', 0) + 1
                            elif ev[n_key]['direction'] < 0:
                                s[f'down_{n_key[1:]}'] = s.get(f'down_{n_key[1:]}', 0) + 1
                    
                    if 'n5' in ev:
                        s['max_fav_n5'].append(ev['n5']['max_favorable_pct'])
                        s['max_unfav_n5'].append(ev['n5']['max_unfavorable_pct'])
        
        # Compute aggregates
        result = {}
        for pname, s in stats.items():
            if s['count'] == 0:
                continue
            
            row = {
                'count': s['count'],
                'symbols': dict(s['symbols']),
            }
            
            for n in [1, 3, 5, 10]:
                ck = f'chg_n{n}'
                uk = f'up_{n}'
                dk = f'down_{n}'
                vals = s[ck]
                if vals:
                    up = s.get(uk, 0)
                    dn = s.get(dk, 0)
                    row[f'bullish_rate_n{n}_pct'] = round(up / len(vals) * 100, 1)
                    row[f'bearish_rate_n{n}_pct'] = round(dn / len(vals) * 100, 1)
                    row[f'avg_chg_n{n}_pct'] = round(sum(vals) / len(vals), 4)
                    row[f'pos_winrate_n{n}_pct'] = round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1)
                else:
                    row[f'bullish_rate_n{n}_pct'] = None
                    row[f'bearish_rate_n{n}_pct'] = None
                    row[f'avg_chg_n{n}_pct'] = None
            
            if s['max_fav_n5']:
                row['avg_max_fav_n5_pct'] = round(sum(s['max_fav_n5']) / len(s['max_fav_n5']), 4)
                row['avg_max_unfav_n5_pct'] = round(sum(s['max_unfav_n5']) / len(s['max_unfav_n5']), 4)
            
            # Sharpe-like score = avg_chg / std(chg)
            for n in [1, 3, 5]:
                vals = s[f'chg_n{n}']
                if len(vals) >= 5 and sum(vals) != 0:
                    mean = sum(vals) / len(vals)
                    if mean > 0:
                        variance = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
                        std = variance ** 0.5
                        row[f'sharpe_n{n}'] = round(mean / std, 3) if std > 0 else 0
                    else:
                        row[f'sharpe_n{n}'] = None
                else:
                    row[f'sharpe_n{n}'] = None
            
            result[pname] = row
        
        return result
    
    def run(self):
        """运行完整扫描"""
        symbols = list(self.data.get('data', {}).keys())
        timeframes = ['M1', 'M5']
        
        raw_findings = {}
        all_analyzed = {}
        
        for sym in symbols:
            sym_data = {}
            for tf in timeframes:
                patterns = self.scan_symbol(sym, tf)
                if patterns is None:
                    continue
                candles = self.data['data'][sym]['candles'].get(tf, [])
                analyzed = self.evaluate_predictions(candles, patterns)
                sym_data[tf] = analyzed
            all_analyzed[sym] = sym_data
        
        # Aggregate across all symbols
        aggregated = self.aggregate_stats(all_analyzed)
        
        return {
            'aggregated': aggregated,
            'per_symbol': all_analyzed,
            'meta': {
                'timestamp': datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
                'symbols_analyzed': symbols,
                'timeframes': timeframes,
                'total_patterns_found': sum(
                    sum(len(v) for v in sd.values() if isinstance(v, list))
                    for sd in all_analyzed.values()
                ),
            }
        }


# ─────────────────────────────────────────────────
# REPORT GENERATOR
# ─────────────────────────────────────────────────

PATTERN_CN = {
    'micro_bull_engulf': '微看涨吞没',
    'micro_bear_engulf': '微看跌吞没',
    'micro_doji_bull_reversal': '十字星看涨反转',
    'micro_doji_bear_reversal': '十字星看跌反转',
    'micro_two_legged_pullback': '两段式回调',
    'micro_breakout_retest': '突破回测',
    'micro_volume_climax': '天量高潮反转',
    'micro_staircase_bull': '阶梯上涨',
    'micro_staircase_bear': '阶梯下跌',
    'micro_pinbar_bull': '锤头线(微)',
    'micro_pinbar_bear': '射击之星(微)',
    'micro_narrow_range_7': '窄幅7连',
    'micro_absorption': '吸收形态',
}

def generate_report(grid_result, timestamp):
    """生成中文Markdown报告"""
    agg = grid_result['aggregated']
    meta = grid_result['meta']
    per_sym = grid_result['per_symbol']
    
    lines = []
    lines.append("# ⚡ Scalping M1/M5 超短线模式挖掘报告")
    lines.append(f"## Reze Grid Engine | {timestamp} CST")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Overview
    lines.append("## 一、研究概述")
    lines.append("")
    lines.append("| 项目 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| **扫描时间** | {meta['timestamp']} CST |")
    lines.append(f"| **时间框架** | M1 / M5 |")
    lines.append(f"| **分析品种** | {', '.join(meta['symbols_analyzed'])} |")
    lines.append(f"| **识别模式总数** | {meta['total_patterns_found']} |")
    lines.append(f"| **数据源** | MT5 实时数据 |")
    lines.append(f"| **研究性质** | 探索性/非实盘建议 |")
    lines.append("")
    
    # Per-symbol summary
    lines.append("---")
    lines.append("## 二、分品种模式分布")
    lines.append("")
    
    for sym in meta['symbols_analyzed']:
        if sym not in per_sym:
            continue
        sym_total = sum(len(v) for v in per_sym[sym].values() if isinstance(v, list))
        lines.append(f"### {sym} ({sym_total} 次)")
        lines.append("")
        for tf in meta['timeframes']:
            if tf not in per_sym[sym]:
                continue
            pats = per_sym[sym][tf]
            if not isinstance(pats, list) or len(pats) == 0:
                continue
            
            tf_counts = defaultdict(int)
            for p in pats:
                tf_counts[p['pattern']] += 1
            
            lines.append(f"**{tf}** — {len(pats)} 次识别:")
            for pname, cnt in sorted(tf_counts.items(), key=lambda x: -x[1]):
                cn = PATTERN_CN.get(pname, pname)
                lines.append(f"  - {cn}: {cnt}次")
            lines.append("")
    
    # Top patterns
    lines.append("---")
    lines.append("## 三、⭐ 高胜率模式排名 (全品种汇总)")
    lines.append("")
    lines.append(f"> 统计方法：形态出现后N根K线收盘方向。看涨率≥65%或看跌率≥65%标为 **高置信度**。")
    lines.append("")
    
    # Sort by n1 win rate
    ranked = []
    for pname, stats in agg.items():
        if stats['count'] < 2:
            continue
        n1_bull = stats.get('bullish_rate_n1_pct') or 0
        n1_bear = stats.get('bearish_rate_n1_pct') or 0
        n3_bull = stats.get('bullish_rate_n3_pct') or 0
        n3_bear = stats.get('bearish_rate_n3_pct') or 0
        n5_bull = stats.get('bullish_rate_n5_pct') or 0
        n5_bear = stats.get('bearish_rate_n5_pct') or 0
        
        # Determine direction bias
        if n1_bull >= 65 and n3_bull >= 55:
            direction = "📈 看涨"
            score = n1_bull * 0.4 + n3_bull * 0.3 + n5_bull * 0.3
        elif n1_bear >= 65 and n3_bear >= 55:
            direction = "📉 看跌"
            score = n1_bear * 0.4 + n3_bear * 0.3 + n5_bear * 0.3
        elif n1_bull >= 55:
            direction = "偏涨"
            score = n1_bull * 0.3 + n3_bull * 0.4 + n5_bull * 0.3
        elif n1_bear >= 55:
            direction = "偏跌"
            score = n1_bear * 0.3 + n3_bear * 0.4 + n5_bear * 0.3
        else:
            direction = "震荡"
            score = 0
        
        avg_chg_n3 = stats.get('avg_chg_n3_pct') or 0
        sharpe_n3 = stats.get('sharpe_n3') or 0
        
        ranked.append((pname, direction, score, stats['count'], 
                       n1_bull, n1_bear,
                       avg_chg_n3, sharpe_n3))
    
    ranked.sort(key=lambda x: -x[2])
    
    # Print top patterns table
    lines.append("### 3.1 Top 信号排名 (按置信度评分)")
    lines.append("")
    header = "| 排名 | 形态 | 方向 | 评分 | 出现次数 | N1看涨率 | N1看跌率 | N3均值% | Sharp(N3) |"
    sep = "|" + "|".join(["---"] * 10) + "|"
    lines.append(header)
    lines.append(sep)
    
    for rank, (pname, direction, score, cnt, n1b, n1be, chg3, sh3) in enumerate(ranked, 1):
        cn = PATTERN_CN.get(pname, pname)
        score_str = f"{score:.1f}"
        n1b_str = f"{n1b:.1f}%" if n1b else "-"
        n1be_str = f"{n1be:.1f}%" if n1be else "-"
        chg3_str = f"{chg3:+.4f}%" if chg3 else "-"
        sh3_str = f"{sh3:.3f}" if sh3 else "-"
        lines.append(f"| {rank} | {cn} | {direction} | {score_str} | {cnt} | {n1b_str} | {n1be_str} | {chg3_str} | {sh3_str} |")
    
    lines.append("")
    
    # Detailed stats table
    lines.append("### 3.2 完整形态统计表")
    lines.append("")
    header2 = "| 形态 | 次数 | N1涨率% | N1均值% | N3涨率% | N3均值% | N5涨率% | N5均值% | N10均值% | MaxFav5% | Sharpe3 |"
    sep2 = "|" + "|".join(["---"] * 12) + "|"
    lines.append(header2)
    lines.append(sep2)
    
    for pname, st in sorted(agg.items(), key=lambda x: -x[1]['count']):
        if st['count'] < 2:
            continue
        cn = PATTERN_CN.get(pname, pname)
        c = st['count']
        n1b = st.get('bullish_rate_n1_pct', '-')
        n1c = st.get('avg_chg_n1_pct', '-')
        n3b = st.get('bullish_rate_n3_pct', '-')
        n3c = st.get('avg_chg_n3_pct', '-')
        n5b = st.get('bullish_rate_n5_pct', '-')
        n5c = st.get('avg_chg_n5_pct', '-')
        n10c = st.get('avg_chg_n10_pct', '-')
        mf5 = st.get('avg_max_fav_n5_pct', '-')
        sh3 = st.get('sharpe_n3', '-')
        
        n1b_s = f"{n1b:.1f}" if isinstance(n1b, (int, float)) else "-"
        n3b_s = f"{n3b:.1f}" if isinstance(n3b, (int, float)) else "-"
        n5b_s = f"{n5b:.1f}" if isinstance(n5b, (int, float)) else "-"
        
        fmt_val = lambda v: f"{v:+.4f}" if isinstance(v, (int, float)) else "-"
        
        lines.append(f"| {cn} | {c} | {n1b_s}% | {fmt_val(n1c)} | {n3b_s}% | {fmt_val(n3c)} | {n5b_s}% | {fmt_val(n5c)} | {fmt_val(n10c)} | {fmt_val(mf5)} | {sh3 if sh3 else '-'} |")
    
    lines.append("")
    
    # Key findings
    lines.append("---")
    lines.append("## 四、🔍 关键发现")
    lines.append("")
    
    # Extract top bullish/bearish patterns
    findings = []
    for pname, st in sorted(agg.items(), key=lambda x: -x[1]['count']):
        if st['count'] < 3:
            continue
        n1b = st.get('bullish_rate_n1_pct', 0) or 0
        n1be = st.get('bearish_rate_n1_pct', 0) or 0
        n3b = st.get('bullish_rate_n3_pct', 0) or 0
        n3c = st.get('avg_chg_n3_pct', 0) or 0
        n5c = st.get('avg_chg_n5_pct', 0) or 0
        
        cn = PATTERN_CN.get(pname, pname)
        
        if n1b >= 65:
            findings.append(f"**{cn}** — M1/M5 看涨信号 (N1涨率 {n1b:.1f}%), N3平均 +{n3c:.4f}% (N5: {n5c:+.4f}%), 样本 {st['count']}次")
        elif n1be >= 65:
            findings.append(f"**{cn}** — M1/M5 看跌信号 (N1跌率 {n1be:.1f}%), N3平均 {n3c:+.4f}% (N5: {n5c:+.4f}%), 样本 {st['count']}次")
        elif n1b >= 58:
            findings.append(f"**{cn}** — M1/M5 偏涨信号 (N1涨率 {n1b:.1f}%), N3平均 {n3c:+.4f}%, 样本 {st['count']}次")
    
    if findings:
        for f in findings:
            lines.append(f"- {f}")
    else:
        lines.append("- 当前样本未发现高置信度模式，可能需要更多数据或更细粒度的形态定义。")
    
    lines.append("")
    
    # Hypotheses for next round
    lines.append("---")
    lines.append("## 五、研究假说与下一轮方向")
    lines.append("")
    
    # Generate hypotheses based on results
    hypotheses = [
        "M1吞没形态的阈值需要根据ATR动态调整 (固定1.5倍实体比可能过于严格)",
        "分时段(亚/欧/美盘)的M1/M5模式胜率可能存在显著差异",
        "结合tick_volume的微观形态比纯价格形态更具预测能力",
    ]
    
    if agg:
        try:
            top_pattern = max(agg.items(), key=lambda x: x[1]['count'])
            hypotheses.append(f"**{PATTERN_CN.get(top_pattern[0], top_pattern[0])}**出现{top_pattern[1]['count']}次，值得深入优化参数阈值")
        except:
            pass
    
    for h in hypotheses:
        lines.append(f"- {h}")
    
    lines.append("")
    
    # Summary score
    lines.append("## 总体评估")
    lines.append("")
    
    total = meta['total_patterns_found']
    total_confident = len([p for p, st in agg.items() if st['count'] >= 3 and 
                          ((st.get('bullish_rate_n1_pct', 0) or 0) >= 65 or 
                           (st.get('bearish_rate_n1_pct', 0) or 0) >= 65)])
    
    lines.append(f"- 共识别 {total} 次形态，覆盖 {len(agg)} 种模式")
    lines.append(f"- 高置信度模式数: {total_confident}")
    if total > 0:
        lines.append(f"- 建议下一轮扩大样本范围 (更多历史数据) 以验证模式稳定性")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*报告由 Reze Grid Engine 自动生成 | 仅供研究参考，不构成交易建议*")
    
    return "\n".join(lines)


def main():
    # Load data
    with open(DATA_PATH, 'r') as f:
        data = json.load(f)
    
    # Run grid engine
    engine = GridEngine(data)
    result = engine.run()
    
    # Generate report
    timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    report_md = generate_report(result, datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"))
    
    # Save report
    report_path = os.path.join(REPORT_DIR, f"{timestamp}_M1M5_超短线模式挖掘报告.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_md)
    
    # Save research data
    data_path = os.path.join(REPORT_DIR, f"research_data_{timestamp}.json")
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 报告已保存: {report_path}")
    print(f"✅ 数据已保存: {data_path}")
    print()
    print(report_md)
    
    return result


if __name__ == "__main__":
    main()
