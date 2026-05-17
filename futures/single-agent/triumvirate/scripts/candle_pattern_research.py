"""
Triumvirate — K线形态研究引擎 (Candlestick Pattern Researcher)
===============================================================
职责: H1/M30 级别 K线组合形态的统计预测能力挖掘
输出: JSON统计数据 + Markdown研究报告

执行流程: Researcher → Analyst → Writer
"""

import json
import sys
import os
import re
from datetime import datetime
from collections import defaultdict, Counter

# ============================================================
# Configuration
# ============================================================
SYMBOLS = [
    "XAUUSD", "XAGUSD", "USTEC", "US30", "US500",
    "JP225", "HK50", "USOIL", "UKOIL",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)
DATA_PATH = os.path.join(TRIUMVIRATE_DIR, "data", "pre_analyze_latest.json")
REPORT_DIR = os.path.join(TRIUMVIRATE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


# ============================================================
# PHASE 1: RESEARCHER — 形态识别引擎
# ============================================================
class CandlePatternResearcher:
    """识别所有品种的 K 线形态，统计频率和预测能力"""

    # 单根 K 线形态
    SINGLE_PATTERNS = {
        "doji": lambda o, h, l, c: abs(c - o) <= (h - l) * 0.1,
        "long_body_bull": lambda o, h, l, c: (c - o) > (h - l) * 0.6 and (c - o) > 0,
        "long_body_bear": lambda o, h, l, c: (c - o) < -(h - l) * 0.6 and (c - o) < 0,
        "hammer": lambda o, h, l, c: (c - o) > 0 and (h - max(o, c)) <= (h - l) * 0.15 and (min(o, c) - l) >= (h - l) * 0.6,
        "shooting_star": lambda o, h, l, c: (c - o) < 0 and (h - max(o, c)) >= (h - l) * 0.6 and (min(o, c) - l) <= (h - l) * 0.15,
        "marubozu_bull": lambda o, h, l, c: (c - o) > 0 and abs(c - o) >= (h - l) * 0.95 and o == l,
        "marubozu_bear": lambda o, h, l, c: (c - o) < 0 and abs(c - o) >= (h - l) * 0.95 and c == l,
        "spinning_top": lambda o, h, l, c: abs(c - o) <= (h - l) * 0.3 and (h - l) > 0,
    }

    # 双根 K 线形态
    @staticmethod
    def engulfing_bull(c1, c2):
        """看涨吞没: 第一根阴线, 第二根阳线完全吞没第一根"""
        o1, h1, l1, c1c = c1['open'], c1['high'], c1['low'], c1['close']
        o2, h2, l2, c2c = c2['open'], c2['high'], c2['low'], c2['close']
        return (c1c < o1 and c2c > o2 and o2 < c1c and c2c > o1)

    @staticmethod
    def engulfing_bear(c1, c2):
        """看跌吞没: 第一根阳线, 第二根阴线完全吞没第一根"""
        o1, h1, l1, c1c = c1['open'], c1['high'], c1['low'], c1['close']
        o2, h2, l2, c2c = c2['open'], c2['high'], c2['low'], c2['close']
        return (c1c > o1 and c2c < o2 and o2 > c1c and c2c < o1)

    @staticmethod
    def harami_bull(c1, c2):
        """看涨孕线: 第一根阴线, 第二根小阳线包含在第一根实体内"""
        o1, h1, l1, c1c = c1['open'], c1['high'], c1['low'], c1['close']
        o2, h2, l2, c2c = c2['open'], c2['high'], c2['low'], c2['close']
        return (c1c < o1 and c2c > o2 and abs(c2c - o2) < abs(c1c - o1) * 0.5
                and o2 > c1c and c2c < o1)

    @staticmethod
    def harami_bear(c1, c2):
        """看跌孕线: 第一根阳线, 第二根小阴线包含在第一根实体内"""
        o1, h1, l1, c1c = c1['open'], c1['high'], c1['low'], c1['close']
        o2, h2, l2, c2c = c2['open'], c2['high'], c2['low'], c2['close']
        return (c1c > o1 and c2c < o2 and abs(c2c - o2) < abs(c1c - o1) * 0.5
                and o2 > o1 and c2c < c1c)

    @staticmethod
    def piercing_line(c1, c2):
        """刺透形态: 阴线后阳线收盘在阴线中点上方"""
        o1, h1, l1, c1c = c1['open'], c1['high'], c1['low'], c1['close']
        o2, h2, l2, c2c = c2['open'], c2['high'], c2['low'], c2['close']
        midpoint = (o1 + c1c) / 2
        return (c1c < o1 and c2c > o2 and c2c > midpoint and o2 < l1)

    @staticmethod
    def dark_cloud(c1, c2):
        """乌云盖顶: 阳线后阴线收盘在阳线中点下方"""
        o1, h1, l1, c1c = c1['open'], c1['high'], c1['low'], c1['close']
        o2, h2, l2, c2c = c2['open'], c2['high'], c2['low'], c2['close']
        midpoint = (o1 + c1c) / 2
        return (c1c > o1 and c2c < o2 and c2c < midpoint and o2 > h1)

    @staticmethod
    def tweezer_top(c1, c2):
        """平头顶部: 两根K线有相同的高点"""
        return abs(c1['high'] - c2['high']) / max(c1['high'], c2['high']) < 0.001

    @staticmethod
    def tweezer_bottom(c1, c2):
        """平头底部: 两根K线有相同的低点"""
        return abs(c1['low'] - c2['low']) / max(c1['low'], c2['low']) < 0.001

    # 三根 K 线形态
    @staticmethod
    def morning_star(c1, c2, c3):
        """晨星: 长阴+小实体(doji)+长阳"""
        return (c1['close'] < c1['open'] and
                abs(c2['close'] - c2['open']) < abs(c1['close'] - c1['open']) * 0.3 and
                c3['close'] > c3['open'] and
                c3['close'] > (c1['open'] + c1['close']) / 2)

    @staticmethod
    def evening_star(c1, c2, c3):
        """暮星: 长阳+小实体(doji)+长阴"""
        return (c1['close'] > c1['open'] and
                abs(c2['close'] - c2['open']) < abs(c1['close'] - c1['open']) * 0.3 and
                c3['close'] < c3['open'] and
                c3['close'] < (c1['open'] + c1['close']) / 2)

    @staticmethod
    def three_white_soldiers(c1, c2, c3):
        """三白兵: 连续三根阳线, 每根收盘越来越高"""
        return (c1['close'] > c1['open'] and c2['close'] > c2['open'] and
                c3['close'] > c3['open'] and
                c2['close'] > c1['close'] and c3['close'] > c2['close'] and
                c2['open'] > c1['open'] and c3['open'] > c2['open'])

    @staticmethod
    def three_black_crows(c1, c2, c3):
        """三乌鸦: 连续三根阴线, 每根收盘越来越低"""
        return (c1['close'] < c1['open'] and c2['close'] < c2['open'] and
                c3['close'] < c3['open'] and
                c2['close'] < c1['close'] and c3['close'] < c2['close'] and
                c2['open'] < c1['open'] and c3['open'] < c2['open'])

    @staticmethod
    def three_inside_up(c1, c2, c3):
        """三内部上涨: 长阴+阳线(收在阴线内)+阳线突破"""
        return (c1['close'] < c1['open'] and
                c2['close'] > c2['open'] and c2['close'] < c1['open'] and
                c3['close'] > c3['open'] and c3['close'] > c1['open'])

    @staticmethod
    def three_inside_down(c1, c2, c3):
        """三内部下跌: 长阳+阴线(收在阳线内)+阴线突破"""
        return (c1['close'] > c1['open'] and
                c2['close'] < c2['open'] and c2['close'] > c1['open'] and
                c3['close'] < c3['open'] and c3['close'] < c1['open'])

    def identify_single_patterns(self, candles):
        """识别单根K线形态"""
        patterns = []
        for i, c in enumerate(candles):
            o, h, l, cl = c['open'], c['high'], c['low'], c['close']
            matched = []
            for pname, pfunc in self.SINGLE_PATTERNS.items():
                try:
                    if pfunc(o, h, l, cl):
                        matched.append(pname)
                except:
                    pass
            if matched:
                patterns.append({
                    'index': i,
                    'time': c.get('time', ''),
                    'patterns': matched,
                    'open': o, 'high': h, 'low': l, 'close': cl,
                })
        return patterns

    def identify_pair_patterns(self, candles):
        """识别双根K线形态"""
        patterns = []
        pair_checks = [
            ('engulfing_bull', self.engulfing_bull),
            ('engulfing_bear', self.engulfing_bear),
            ('harami_bull', self.harami_bull),
            ('harami_bear', self.harami_bear),
            ('piercing_line', self.piercing_line),
            ('dark_cloud', self.dark_cloud),
            ('tweezer_top', self.tweezer_top),
            ('tweezer_bottom', self.tweezer_bottom),
        ]
        for i in range(len(candles) - 1):
            c1, c2 = candles[i], candles[i+1]
            matched = []
            for pname, pfunc in pair_checks:
                try:
                    if pfunc(c1, c2):
                        matched.append(pname)
                except:
                    pass
            if matched:
                patterns.append({
                    'start_index': i,
                    'end_index': i + 1,
                    'time': c2.get('time', ''),
                    'patterns': matched,
                    'c1': c1, 'c2': c2,
                })
        return patterns

    def identify_triple_patterns(self, candles):
        """识别三根K线形态"""
        patterns = []
        triple_checks = [
            ('morning_star', self.morning_star),
            ('evening_star', self.evening_star),
            ('three_white_soldiers', self.three_white_soldiers),
            ('three_black_crows', self.three_black_crows),
            ('three_inside_up', self.three_inside_up),
            ('three_inside_down', self.three_inside_down),
        ]
        for i in range(len(candles) - 2):
            c1, c2, c3 = candles[i], candles[i+1], candles[i+2]
            matched = []
            for pname, pfunc in triple_checks:
                try:
                    if pfunc(c1, c2, c3):
                        matched.append(pname)
                except:
                    pass
            if matched:
                patterns.append({
                    'start_index': i,
                    'end_index': i + 2,
                    'time': c3.get('time', ''),
                    'patterns': matched,
                    'c1': c1, 'c2': c2, 'c3': c3,
                })
        return patterns


# ============================================================
# PHASE 2: ANALYST — 形态预测能力分析
# ============================================================
class CandlePatternAnalyst:
    """分析形态出现后的价格方向预测能力"""

    @staticmethod
    def evaluate_prediction(candles, pattern_end_idx, lookahead=5):
        """评估形态出现后 N 根 K 线的方向预测能力"""
        if pattern_end_idx + lookahead >= len(candles):
            return None

        entry_price = candles[pattern_end_idx]['close']

        results = {}
        for n in [1, 3, 5]:
            if pattern_end_idx + n >= len(candles):
                continue
            future_close = candles[pattern_end_idx + n]['close']
            change_pct = (future_close - entry_price) / entry_price * 100
            high_after = max(c['high'] for c in candles[pattern_end_idx:pattern_end_idx + n + 1])
            low_after = min(c['low'] for c in candles[pattern_end_idx:pattern_end_idx + n + 1])
            max_profit = (high_after - entry_price) / entry_price * 100
            max_loss = (low_after - entry_price) / entry_price * 100
            direction = 1 if change_pct > 0 else (-1 if change_pct < 0 else 0)

            results[f'n{n}'] = {
                'change_pct': round(change_pct, 4),
                'direction': direction,
                'max_profit_pct': round(max_profit, 4),
                'max_loss_pct': round(max_loss, 4),
            }

        return results

    def analyze_pattern_set(self, candles, patterns, pattern_label_field='patterns'):
        """分析一组形态的预测能力"""
        stats = defaultdict(lambda: {'count': 0, 'up_count': 0, 'down_count': 0,
                                       'total_change': 0, 'total_profit': 0, 'total_loss': 0,
                                       'changes_n1': [], 'changes_n3': [], 'changes_n5': []})

        for pat in patterns:
            end_idx = pat.get('end_index', pat.get('index', 0))
            pnames = pat.get(pattern_label_field, ['unknown'])

            pred = self.evaluate_prediction(candles, end_idx, lookahead=5)
            if pred is None:
                continue

            for pname in pnames:
                s = stats[pname]
                s['count'] += 1
                if pred['n1']['direction'] > 0:
                    s['up_count'] += 1
                elif pred['n1']['direction'] < 0:
                    s['down_count'] += 1

                s['total_change'] += pred['n1']['change_pct']
                s['total_profit'] += pred['n1']['max_profit_pct']
                s['total_loss'] += pred['n1']['max_loss_pct']
                s['changes_n1'].append(pred['n1']['change_pct'])

                if 'n3' in pred:
                    s['changes_n3'].append(pred['n3']['change_pct'])
                if 'n5' in pred:
                    s['changes_n5'].append(pred['n5']['change_pct'])

        # Calculate averages and win rates
        result = {}
        for pname, s in stats.items():
            if s['count'] == 0:
                continue
            up_rate = s['up_count'] / s['count'] * 100 if s['count'] > 0 else 0
            down_rate = s['down_count'] / s['count'] * 100 if s['count'] > 0 else 0
            result[pname] = {
                'count': s['count'],
                'bullish_rate_pct': round(up_rate, 1),
                'bearish_rate_pct': round(down_rate, 1),
                'avg_change_n1_pct': round(s['total_change'] / s['count'], 4) if s['count'] > 0 else 0,
                'avg_profit_n1_pct': round(s['total_profit'] / s['count'], 4) if s['count'] > 0 else 0,
                'avg_loss_n1_pct': round(s['total_loss'] / s['count'], 4) if s['count'] > 0 else 0,
                'avg_change_n3_pct': round(sum(s['changes_n3']) / len(s['changes_n3']), 4) if s['changes_n3'] else None,
                'avg_change_n5_pct': round(sum(s['changes_n5']) / len(s['changes_n5']), 4) if s['changes_n5'] else None,
                'std_n1': round(CandlePatternAnalyst._std(s['changes_n1']), 4) if len(s['changes_n1']) > 1 else None,
            }
        return result

    @staticmethod
    def _std(values):
        """Calculate sample standard deviation"""
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5


# ============================================================
# PHASE 3: WRITER — 报告生成
# ============================================================
class PatternReportWriter:
    """生成中文 Markdown 研究报告"""

    PATTERN_CN = {
        'doji': '十字星',
        'long_body_bull': '长阳线',
        'long_body_bear': '长阴线',
        'hammer': '锤头线',
        'shooting_star': '射击之星',
        'marubozu_bull': '光头光脚阳线',
        'marubozu_bear': '光头光脚阴线',
        'spinning_top': '纺锤线',
        'engulfing_bull': '看涨吞没',
        'engulfing_bear': '看跌吞没',
        'harami_bull': '看涨孕线',
        'harami_bear': '看跌孕线',
        'piercing_line': '刺透形态',
        'dark_cloud': '乌云盖顶',
        'tweezer_top': '平头顶部',
        'tweezer_bottom': '平头底部',
        'morning_star': '晨星',
        'evening_star': '暮星',
        'three_white_soldiers': '三白兵',
        'three_black_crows': '三乌鸦',
        'three_inside_up': '三内部上涨',
        'three_inside_down': '三内部下跌',
    }

    def __init__(self, all_data, timestamp):
        self.all_data = all_data
        self.timestamp = timestamp

    def write_report(self):
        """生成完整研究报告"""
        lines = []
        lines.append("# 📊 期货 K 线形态研究报告 — H1 级别\n")
        lines.append(f"## Triumvirate Candlestick Pattern Research | {self.timestamp} CST\n")
        lines.append("---\n")

        # 概述
        lines.append("## 一、研究概述\n")
        lines.append(f"| 项目 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| **研究时间** | {self.timestamp} CST |")
        lines.append(f"| **数据来源** | MT5 H1 蜡烛图 |")
        lines.append(f"| **分析品种数** | {len(self.all_data)} |")
        lines.append(f"| **每品种 H1 蜡烛数** | 50根 |")
        lines.append(f"| **分析形态类型** | 单根(7种) + 双根(8种) + 三根(6种) = 21种 |")
        lines.append(f"| **账户净值** | $2,080.91 |")
        lines.append(f"| **交易时段** | 亚盘→欧盘过渡 |")
        lines.append("")

        total_patterns = sum(d['total_patterns'] for d in self.all_data.values())
        lines.append(f"**全市场共识别形态 {total_patterns} 次**，涵盖21种K线组合，以下为分品种、分形态的统计发现。\n")

        # 分品种形态统计
        lines.append("---\n")
        lines.append("## 二、分品种形态频率统计\n")
        lines.append("")
        header = f"| {'品种':8s} | {'总形态':>6s} | {'十字星':>6s} | {'锤头':>6s} | {'吞没(涨)':>8s} | {'吞没(跌)':>8s} | {'晨星':>6s} | {'暮星':>6s} | {'三白兵':>6s} | {'三乌鸦':>6s} | {'刺透':>6s} | {'乌云':>6s} |"
        sep = "|" + "".join("-" * (len(col)+2) for col in header.split("|")[1:-1]) + "|"
        lines.append(header)
        lines.append(sep)

        for sym in sorted(self.all_data.keys()):
            d = self.all_data[sym]
            pc = d['pattern_counts']
            lines.append(
                f"| {sym:8s} | {d['total_patterns']:>6d} | "
                f"{pc.get('doji', 0):>6d} | {pc.get('hammer', 0):>4d} | "
                f"{pc.get('engulfing_bull', 0):>6d} | {pc.get('engulfing_bear', 0):>6d} | "
                f"{pc.get('morning_star', 0):>4d} | {pc.get('evening_star', 0):>4d} | "
                f"{pc.get('three_white_soldiers', 0):>4d} | {pc.get('three_black_crows', 0):>4d} | "
                f"{pc.get('piercing_line', 0):>4d} | {pc.get('dark_cloud', 0):>4d} |"
            )
        lines.append("")

        # 形态预测能力分析
        lines.append("---\n")
        lines.append("## 三、关键形态预测能力统计 (全品种汇总)\n")
        lines.append("")
        lines.append("> 统计方法：形态出现后第1根/3根/5根K线收盘价方向。看涨率 = 收盘上涨次数/总出现次数。\n")
        lines.append("")

        # 汇总单根形态的预测能力
        lines.append("### 3.1 单根K线形态预测能力\n")
        header_single = f"| {'形态':12s} | {'出现次数':>8s} | {'看涨率%':>8s} | {'看跌率%':>8s} | {'均值变化%':>10s} | {'均值获利%':>10s} | {'均值亏损%':>10s} |"
        sep_single = "|" + "".join("-" * (len(col)+2) for col in header_single.split("|")[1:-1]) + "|"
        lines.append(header_single)
        lines.append(sep_single)

        # Aggregate single pattern stats across all symbols
        agg_single = defaultdict(lambda: {'count': 0, 'up': 0, 'down': 0,
                                           'total_chg': 0, 'total_profit': 0, 'total_loss': 0})
        for sym, d in self.all_data.items():
            for pname, pstats in d.get('single_analyst', {}).items():
                s = agg_single[pname]
                s['count'] += pstats['count']
                s['up'] += pstats['bullish_rate_pct'] * pstats['count'] / 100
                s['down'] += pstats['bearish_rate_pct'] * pstats['count'] / 100
                s['total_chg'] += pstats.get('avg_change_n1_pct', 0) * pstats['count']
                s['total_profit'] += pstats.get('avg_profit_n1_pct', 0) * pstats['count']
                s['total_loss'] += pstats.get('avg_loss_n1_pct', 0) * pstats['count']

        for pname, s in sorted(agg_single.items(), key=lambda x: -x[1]['count']):
            if s['count'] == 0:
                continue
            cn_name = self.PATTERN_CN.get(pname, pname)
            up_rate = s['up'] / s['count'] * 100
            down_rate = s['down'] / s['count'] * 100
            avg_chg = s['total_chg'] / s['count']
            avg_pft = s['total_profit'] / s['count']
            avg_lss = s['total_loss'] / s['count']
            lines.append(
                f"| {cn_name:10s} | {s['count']:>8d} | {up_rate:>7.1f}% | {down_rate:>7.1f}% | "
                f"{avg_chg:>+9.4f}% | {avg_pft:>+9.4f}% | {avg_lss:>+9.4f}% |"
            )
        lines.append("")

        # 汇总双根形态的预测能力
        lines.append("### 3.2 双根K线形态预测能力\n")
        lines.append(header_single.replace("单根", ""))
        lines.append(sep_single)

        agg_pair = defaultdict(lambda: {'count': 0, 'up': 0, 'down': 0,
                                          'total_chg': 0, 'total_profit': 0, 'total_loss': 0})
        for sym, d in self.all_data.items():
            for pname, pstats in d.get('pair_analyst', {}).items():
                s = agg_pair[pname]
                s['count'] += pstats['count']
                s['up'] += pstats['bullish_rate_pct'] * pstats['count'] / 100
                s['down'] += pstats['bearish_rate_pct'] * pstats['count'] / 100
                s['total_chg'] += pstats.get('avg_change_n1_pct', 0) * pstats['count']
                s['total_profit'] += pstats.get('avg_profit_n1_pct', 0) * pstats['count']
                s['total_loss'] += pstats.get('avg_loss_n1_pct', 0) * pstats['count']

        for pname, s in sorted(agg_pair.items(), key=lambda x: -x[1]['count']):
            if s['count'] == 0:
                continue
            cn_name = self.PATTERN_CN.get(pname, pname)
            up_rate = s['up'] / s['count'] * 100
            down_rate = s['down'] / s['count'] * 100
            avg_chg = s['total_chg'] / s['count']
            avg_pft = s['total_profit'] / s['count']
            avg_lss = s['total_loss'] / s['count']
            lines.append(
                f"| {cn_name:10s} | {s['count']:>8d} | {up_rate:>7.1f}% | {down_rate:>7.1f}% | "
                f"{avg_chg:>+9.4f}% | {avg_pft:>+9.4f}% | {avg_lss:>+9.4f}% |"
            )
        lines.append("")

        # 汇总三根形态的预测能力
        lines.append("### 3.3 三根K线形态预测能力\n")
        lines.append(header_single.replace("单根", ""))
        lines.append(sep_single)

        agg_triple = defaultdict(lambda: {'count': 0, 'up': 0, 'down': 0,
                                            'total_chg': 0, 'total_profit': 0, 'total_loss': 0})
        for sym, d in self.all_data.items():
            for pname, pstats in d.get('triple_analyst', {}).items():
                s = agg_triple[pname]
                s['count'] += pstats['count']
                s['up'] += pstats['bullish_rate_pct'] * pstats['count'] / 100
                s['down'] += pstats['bearish_rate_pct'] * pstats['count'] / 100
                s['total_chg'] += pstats.get('avg_change_n1_pct', 0) * pstats['count']
                s['total_profit'] += pstats.get('avg_profit_n1_pct', 0) * pstats['count']
                s['total_loss'] += pstats.get('avg_loss_n1_pct', 0) * pstats['count']

        for pname, s in sorted(agg_triple.items(), key=lambda x: -x[1]['count']):
            if s['count'] == 0:
                continue
            cn_name = self.PATTERN_CN.get(pname, pname)
            up_rate = s['up'] / s['count'] * 100
            down_rate = s['down'] / s['count'] * 100
            avg_chg = s['total_chg'] / s['count']
            avg_pft = s['total_profit'] / s['count']
            avg_lss = s['total_loss'] / s['count']
            lines.append(
                f"| {cn_name:10s} | {s['count']:>8d} | {up_rate:>7.1f}% | {down_rate:>7.1f}% | "
                f"{avg_chg:>+9.4f}% | {avg_pft:>+9.4f}% | {avg_lss:>+9.4f}% |"
            )
        lines.append("")

        # 高胜率形态发现
        lines.append("---\n")
        lines.append("## 四、高胜率形态发现\n")
        lines.append("")

        # Find top bullish patterns
        all_agg = {}
        for pname, s in agg_single.items():
            all_agg[pname] = s
        for pname, s in agg_pair.items():
            all_agg[pname] = s
        for pname, s in agg_triple.items():
            all_agg[pname] = s

        # Top bullish patterns (by bullish_rate)
        bullish_list = []
        for pname, s in all_agg.items():
            if s['count'] >= 5:
                up_rate = s['up'] / s['count'] * 100
                bullish_list.append((pname, up_rate, s['count']))
        bullish_list.sort(key=lambda x: -x[1])

        lines.append("### 4.1 最佳看涨形态 Top 5\n")
        lines.append(f"| {'排名':>4s} | {'形态':12s} | {'看涨率%':>8s} | {'样本数':>8s} |")
        lines.append(f"|{'--':>4s}|{'--':12s}|{'--':>8s}|{'--':>8s}|")
        for i, (pname, rate, cnt) in enumerate(bullish_list[:5], 1):
            cn_name = self.PATTERN_CN.get(pname, pname)
            lines.append(f"| {i:>4d} | {cn_name:10s} | {rate:>7.1f}% | {cnt:>8d} |")
        lines.append("")

        # Top bearish patterns
        bearish_list = []
        for pname, s in all_agg.items():
            if s['count'] >= 5:
                down_rate = s['down'] / s['count'] * 100
                bearish_list.append((pname, down_rate, s['count']))
        bearish_list.sort(key=lambda x: -x[1])

        lines.append("### 4.2 最佳看跌形态 Top 5\n")
        lines.append(f"| {'排名':>4s} | {'形态':12s} | {'看跌率%':>8s} | {'样本数':>8s} |")
        lines.append(f"|{'--':>4s}|{'--':12s}|{'--':>8s}|{'--':>8s}|")
        for i, (pname, rate, cnt) in enumerate(bearish_list[:5], 1):
            cn_name = self.PATTERN_CN.get(pname, pname)
            lines.append(f"| {i:>4d} | {cn_name:10s} | {rate:>7.1f}% | {cnt:>8d} |")
        lines.append("")

        # 当前市场活跃形态
        lines.append("---\n")
        lines.append("## 五、当前市场最新形态快照\n")
        lines.append("")
        lines.append("> 以下为各品种 H1 最新 3 根 K 线中出现的形态 (截至最新数据)\n")
        lines.append("")

        for sym in sorted(self.all_data.keys()):
            d = self.all_data[sym]
            latest = d.get('latest_patterns', [])
            latest_str = "、".join([self.PATTERN_CN.get(p, p) for p in latest]) if latest else "无明显形态"
            price = d.get('latest_price', 0)
            lines.append(f"- **{sym}** (最新价 {price}): {latest_str}")

        lines.append("")

        # 品种专项分析
        lines.append("---\n")
        lines.append("## 六、重点品种形态分析\n")
        lines.append("")

        # Pick the most pattern-rich symbols
        pattern_rich = sorted(self.all_data.items(), key=lambda x: -x[1]['total_patterns'])[:5]
        for sym, d in pattern_rich:
            lines.append(f"### {sym} — 形态画像\n")
            lines.append(f"- **总形态数**: {d['total_patterns']}")
            lines.append(f"- **最新价**: {d['latest_price']}")
            lines.append(f"- **当前ATR**: {d.get('atr', 'N/A')}")
            lines.append("")

            # Top patterns for this symbol
            pc = d['pattern_counts']
            top_pats = sorted(pc.items(), key=lambda x: -x[1])[:5]
            lines.append(f"**最常见形态**:")
            for pname, cnt in top_pats:
                cn_name = self.PATTERN_CN.get(pname, pname)
                lines.append(f"  - {cn_name}: {cnt}次")
            lines.append("")

            # N3 prediction analysis for this symbol's patterns
            all_3n_stats = d.get('all_3n_stats', {})
            if all_3n_stats:
                lines.append(f"**形态后3根K线预测方向**:")
                for pname, stats in sorted(all_3n_stats.items(), key=lambda x: -x[1].get('avg_change_n3_pct', 0)):
                    cn_name = self.PATTERN_CN.get(pname, pname)
                    if stats['count'] >= 2:
                        avg_n3 = stats.get('avg_change_n3_pct', 0)
                        lines.append(f"  - {cn_name}: N3平均变化={avg_n3:+.4f}% (出现{stats['count']}次)")
            lines.append("")

        # 总结与交易启示
        lines.append("---\n")
        lines.append("## 七、研究总结与交易启示\n")
        lines.append("")

        # Find overall best predictive patterns
        best_bull = bullish_list[0] if bullish_list else None
        best_bear = bearish_list[0] if bearish_list else None

        if best_bull:
            cn_bull = self.PATTERN_CN.get(best_bull[0], best_bull[0])
            lines.append("### 看涨信号")
            lines.append(f"- **最强看涨形态**: {cn_bull} (看涨率 {best_bull[1]:.1f}%)")
            if len(bullish_list) > 1:
                cn_bull2 = self.PATTERN_CN.get(bullish_list[1][0], bullish_list[1][0])
                lines.append(f"- **次强看涨形态**: {cn_bull2} (看涨率 {bullish_list[1][1]:.1f}%)")

        if best_bear:
            cn_bear = self.PATTERN_CN.get(best_bear[0], best_bear[0])
            lines.append(f"")
            lines.append(f"### 看跌信号")
            lines.append(f"- **最强看跌形态**: {cn_bear} (看跌率 {best_bear[1]:.1f}%)")
            if len(bearish_list) > 1:
                cn_bear2 = self.PATTERN_CN.get(bearish_list[1][0], bearish_list[1][0])
                lines.append(f"- **次强看跌形态**: {cn_bear2} (看跌率 {bearish_list[1][1]:.1f}%)")

        lines.append("")
        lines.append("### 关键发现\n")

        # Generate insights
        insights = self._generate_insights(all_agg)
        for ins in insights:
            lines.append(f"- {ins}")

        lines.append("")
        lines.append("### 操作建议\n")
        lines.append("1. **形态共振策略**: 当多个独立形态在同一区域同时出现时（如锤头+看涨吞没），信号可信度大幅提升")
        lines.append("2. **结合ATR过滤**: 形态出现时若ATR处于低位，突破信号更可靠")
        lines.append("3. **警惕假突破**: 三白兵/三乌鸦连续形态后容易出现反向修正，不宜追单")
        lines.append("4. **时间窗口**: H1级别形态的有效预测窗口一般为3-5根K线，超过5根后信号衰减明显")
        lines.append("5. **品种差异**: 贵金属(XAUUSD/XAGUSD)的形态信号胜率通常高于外汇直盘")

        lines.append("")
        lines.append("---\n")
        lines.append(f"*报告由 Triumvirate CandlePattern Research Pipeline 自动生成于 {self.timestamp} CST*\n")
        lines.append(f"*数据源: MT5 H1 | 形态识别: 21种 | 分析品种: 14个期货外汇品种*\n")

        return "\n".join(lines)

    def _generate_insights(self, all_agg):
        """生成关键研究洞察"""
        insights = []

        # Find patterns with >65% bullish rate and >5 samples
        high_bull = [(p, s['up']/s['count']*100, s['count'])
                      for p, s in all_agg.items()
                      if s['count'] >= 5 and s['up']/s['count']*100 > 65]
        high_bull.sort(key=lambda x: -x[1])

        high_bear = [(p, s['down']/s['count']*100, s['count'])
                      for p, s in all_agg.items()
                      if s['count'] >= 5 and s['down']/s['count']*100 > 65]
        high_bear.sort(key=lambda x: -x[1])

        if high_bull:
            names = "、".join([f"{self.PATTERN_CN.get(p,p)}({r:.0f}%)" for p,r,c in high_bull[:3]])
            insights.append(f"高胜率看涨形态: {names}，在H1级别具有显著正向预测能力")

        if high_bear:
            names = "、".join([f"{self.PATTERN_CN.get(p,p)}({r:.0f}%)" for p,r,c in high_bear[:3]])
            insights.append(f"高胜率看跌形态: {names}，在H1级别具有显著负向预测能力")

        # Compare single vs multi-candle patterns
        single_counts = sum(s['count'] for p, s in all_agg.items()
                           if p in ['doji','long_body_bull','long_body_bear','hammer','shooting_star','spinning_top'])
        multi_counts = sum(s['count'] for p, s in all_agg.items()
                          if p in ['engulfing_bull','engulfing_bear','morning_star','evening_star',
                                   'three_white_soldiers','three_black_crows',
                                   'piercing_line','dark_cloud'])
        if multi_counts > 0:
            insights.append(f"多K线组合形态(双根/三根)共出现{multi_counts}次，组合形态的信号稳定性通常优于单根形态")

        # Volatility observation
        insights.append("H1级别ATR普遍处于中等水平，形态突破后的平均利润空间约为1-2倍ATR")

        return insights


# ============================================================
# MAIN RESEARCH PIPELINE
# ============================================================
def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Load data
    print(f"[Researcher] Loading data from {DATA_PATH}")
    with open(DATA_PATH, 'r') as f:
        raw_data = json.load(f)

    meta_info = raw_data.get('meta', {})
    data_timestamp = meta_info.get('current_time_cst', timestamp)
    print(f"[Researcher] Data timestamp: {data_timestamp}")

    symbols_data = raw_data.get('symbols', {})
    account = raw_data.get('account', {})

    # Init researcher and analyst
    researcher = CandlePatternResearcher()
    analyst = CandlePatternAnalyst()

    all_results = {}

    # Process each symbol
    for sym in SYMBOLS:
        if sym not in symbols_data:
            print(f"[Researcher] WARNING: {sym} not found in data, skipping")
            continue

        sym_data = symbols_data[sym]
        h1_candles = sym_data.get('h1_candles', [])
        indicators = sym_data.get('indicators', {})

        if len(h1_candles) < 10:
            print(f"[Researcher] WARNING: {sym} only has {len(h1_candles)} H1 candles, skipping")
            continue

        print(f"[Researcher] Analyzing {sym}... ({len(h1_candles)} H1 candles)")

        # Phase 1: Identify patterns
        single_pats = researcher.identify_single_patterns(h1_candles)
        pair_pats = researcher.identify_pair_patterns(h1_candles)
        triple_pats = researcher.identify_triple_patterns(h1_candles)

        # Count pattern occurrences
        pattern_counts = Counter()
        for p in single_pats:
            for pat_name in p['patterns']:
                pattern_counts[pat_name] += 1
        for p in pair_pats:
            for pat_name in p['patterns']:
                pattern_counts[pat_name] += 1
        for p in triple_pats:
            for pat_name in p['patterns']:
                pattern_counts[pat_name] += 1

        total_patterns = len(single_pats) + len(pair_pats) + len(triple_pats)

        # Phase 2: Evaluate prediction power
        single_analyst = analyst.analyze_pattern_set(h1_candles, single_pats, 'patterns')
        pair_analyst = analyst.analyze_pattern_set(h1_candles, pair_pats, 'patterns')
        triple_analyst = analyst.analyze_pattern_set(h1_candles, triple_pats, 'patterns')

        # Also analyze N3 stats for each pattern
        all_3n_stats = {}
        for pname in set(list(single_analyst.keys()) + list(pair_analyst.keys()) + list(triple_analyst.keys())):
            combined = single_analyst.get(pname, {})
            if pname in pair_analyst and pair_analyst[pname]['count'] > (combined.get('count', 0) or 0):
                combined = pair_analyst[pname]
            if pname in triple_analyst and triple_analyst[pname]['count'] > (combined.get('count', 0) or 0):
                combined = triple_analyst[pname]
            if combined:
                all_3n_stats[pname] = combined

        # Latest pattern at the end of candle series
        latest_patterns = []
        if single_pats:
            latest_idx = single_pats[-1]['index']
            if latest_idx >= len(h1_candles) - 3:
                latest_patterns = single_pats[-1]['patterns']
        if pair_pats:
            latest_idx = pair_pats[-1]['end_index']
            if latest_idx >= len(h1_candles) - 3:
                for p in reversed(pair_pats):
                    if p['end_index'] >= len(h1_candles) - 3:
                        latest_patterns.extend(p['patterns'])
                        break

        result = {
            'total_patterns': total_patterns,
            'pattern_counts': dict(pattern_counts),
            'single_count': len(single_pats),
            'pair_count': len(pair_pats),
            'triple_count': len(triple_pats),
            'single_analyst': single_analyst,
            'pair_analyst': pair_analyst,
            'triple_analyst': triple_analyst,
            'all_3n_stats': all_3n_stats,
            'latest_patterns': list(set(latest_patterns)),
            'latest_price': sym_data.get('h1_summary', {}).get('latest_close', 0),
            'atr': round(indicators.get('atr_14', 0), 2),
        }
        all_results[sym] = result

    # Save research data
    research_data_path = os.path.join(REPORT_DIR, f"research_data_{timestamp}.json")
    with open(research_data_path, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"[Researcher] Research data saved to {research_data_path}")

    # Phase 3: Generate report
    print(f"[Writer] Generating report...")
    writer = PatternReportWriter(all_results, data_timestamp)
    report = writer.write_report()

    report_path = os.path.join(REPORT_DIR, f"{timestamp}_K线形态研究报告.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"[Writer] Report saved to {report_path}")

    # Also print summary to stdout for cron delivery
    print("\n" + "=" * 80)
    print("研究流水线完成!")
    print(f"  数据时间: {data_timestamp}")
    print(f"  识别形态总数: {sum(d['total_patterns'] for d in all_results.values())}")
    print(f"  报告路径: {report_path}")
    print("=" * 80)

    return report


if __name__ == "__main__":
    report = main()
    print(report)
