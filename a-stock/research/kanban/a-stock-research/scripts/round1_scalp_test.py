#!/usr/bin/env python3
"""
Scalping Round 1 — M1/M5 超短线初始模式挖掘
品种: XAUUSD, XAGUSD, JP225, US500, US30
时间框架: M1, M5
"""

import json
import math
import sys
import subprocess
import os
from datetime import datetime, timedelta

WINDOWS_PYTHON = "/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe"

# ─── 通过 Windows Python / MT5 获取数据 ────────────────────────

def fetch_mt5(tf, lookback=5000):
    """Fetch MT5 data via Windows Python bridge. Returns {symbol: [klines]}"""
    code = f'''
import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import json
from datetime import datetime as _dt

if not mt5.initialize():
    print(json.dumps({{'error': f'MT5 init failed: {{mt5.last_error()}}'}}))
    sys.exit(0)

symbols = ['XAUUSD', 'XAGUSD', 'JP225', 'US500', 'US30']
tf_map = {{'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15}}
tf = tf_map.get('{tf}', mt5.TIMEFRAME_M5)

result = {{}}
for sym in symbols:
    rates = mt5.copy_rates_from_pos(sym, tf, 0, {lookback})
    if rates is None or len(rates) == 0:
        result[sym] = []
        continue
    klines = []
    for r in rates:
        klines.append({{
            'time': _dt.fromtimestamp(r[0]).strftime('%Y-%m-%d %H:%M:%S'),
            'open': float(r[1]),
            'high': float(r[2]),
            'low': float(r[3]),
            'close': float(r[4]),
            'volume': int(r[5]),
        }})
    result[sym] = klines

mt5.shutdown()
print(json.dumps(result))
'''
    # Windows Python 需要 Windows 路径格式
    # WSL 调用 Windows exe: exe 路径用 /mnt/c/, 参数用 Windows 格式
    win_path_win = "C:/Users/gj/tmp/mt5_round1.py"
    win_path_wsl = "/mnt/c/Users/gj/tmp/mt5_round1.py"
    os.makedirs("/mnt/c/Users/gj/tmp", exist_ok=True)
    with open(win_path_wsl, "w", encoding='utf-8') as f:
        f.write(code)

    r = subprocess.run(
        [WINDOWS_PYTHON, win_path_win, "--tf", tf, "--lookback", str(lookback)],
        capture_output=True, text=True, timeout=300
    )
    if r.returncode != 0:
        return {"error": f"Windows Python error: {r.stderr[:500]}"}
    idx = r.stdout.find('{')
    if idx >= 0:
        return json.loads(r.stdout[idx:])
    return {"error": f"No JSON: {r.stdout[:500]}"}


# ─── 技术指标 ──────────────────────────────────────────────────

def compute_rsi(series, period=14):
    """RSI 计算"""
    if len(series) < period + 1:
        return [None] * len(series)
    rsi = [None] * len(series)
    gains, losses = 0, 0
    for i in range(1, period + 1):
        diff = series[i] - series[i-1]
        gains += max(diff, 0)
        losses += max(-diff, 0)
    avg_gain = gains / period
    avg_loss = losses / period
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi[period] = 100 - 100 / (1 + rs)
    for i in range(period + 1, len(series)):
        diff = series[i] - series[i-1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi[i] = 100 - 100 / (1 + rs)
    return rsi


def compute_sma(series, period):
    if len(series) < period:
        return [None] * len(series)
    sma = [None] * len(series)
    for i in range(period - 1, len(series)):
        sma[i] = sum(series[i - period + 1:i + 1]) / period
    return sma


def compute_bb(series, period=20, std_dev=2):
    """Bollinger Bands: (middle, upper, lower)"""
    middle = compute_sma(series, period)
    bb_upper = [None] * len(series)
    bb_lower = [None] * len(series)
    for i in range(period - 1, len(series)):
        window = series[i - period + 1:i + 1]
        std = math.sqrt(sum((x - middle[i]) ** 2 for x in window) / period)
        bb_upper[i] = middle[i] + std_dev * std
        bb_lower[i] = middle[i] - std_dev * std
    return middle, bb_upper, bb_lower


def compute_atr(high, low, close, period=14):
    """ATR"""
    if len(close) < 2:
        return [None] * len(close)
    tr = [None]
    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        tr.append(max(hl, hc, lc))
    atr = [None] * len(tr)
    # first ATR = SMA of first 'period' TRs
    if len(tr) >= period + 1:
        atr[period] = sum(tr[1:period + 1]) / period
        for i in range(period + 1, len(tr)):
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr


# ─── 假设测试 ──────────────────────────────────────────────────

def wilson_ci(n, p, z=1.96):
    """Wilson 95% 置信区间"""
    if n == 0:
        return (0, 0)
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0, (c - m) / d), min(1, (c + m) / d))


def test_hypothesis(klines, entry_cond, direction="long", forward_bars=1):
    """
    通用假设测试框架
    entry_cond(klines, idx) → True/False 是否在该K线入场
    direction: "long" or "short"
    forward_bars: 持有几根K线后检查
    """
    signals = []
    results = []
    for i in range(len(klines)):
        if entry_cond(klines, i):
            signals.append(i)
            if i + forward_bars < len(klines):
                entry_price = klines[i]['close']
                exit_price = klines[i + forward_bars]['close']
                if direction == "long":
                    ret = (exit_price - entry_price) / entry_price
                else:
                    ret = (entry_price - exit_price) / entry_price
                results.append(ret)

    n = len(results)
    if n == 0:
        return {"signal_count": 0, "win_rate": 0, "avg_return": 0}

    wins = [r for r in results if r > 0]
    losses = [r for r in results if r < 0]
    win_rate = len(wins) / n
    avg_ret = sum(results) / n
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    ci_lower, ci_upper = wilson_ci(n, win_rate)

    # 连续复利累计
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in results:
        equity *= (1 + r)
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        "signal_count": n,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(win_rate * 100, 2),
        "avg_return": round(avg_ret * 100, 4),
        "avg_win": round(avg_win * 100, 4),
        "avg_loss": round(avg_loss * 100, 4),
        "profit_factor": round(profit_factor, 2),
        "ci_95_lower": round(ci_lower * 100, 2),
        "ci_95_upper": round(ci_upper * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "cumulative_return": round((equity - 1) * 100, 2),
    }


# ─── 入场条件函数 ──────────────────────────────────────────────

# 条件1: RSI < 30 (超卖) + 收阳
def cond_rsi_oversold_bullish(klines, idx):
    if 'rsi' not in klines[idx] or klines[idx]['rsi'] is None:
        return False
    return klines[idx]['rsi'] < 30 and klines[idx]['close'] > klines[idx]['open']

# 条件2: RSI > 70 (超买) + 收阴
def cond_rsi_overbought_bearish(klines, idx):
    if 'rsi' not in klines[idx] or klines[idx]['rsi'] is None:
        return False
    return klines[idx]['rsi'] > 70 and klines[idx]['close'] < klines[idx]['open']

# 条件3: 连续3根阴线 (M1)
def cond_three_bears(klines, idx):
    if idx < 2:
        return False
    return (klines[idx]['close'] < klines[idx]['open'] and
            klines[idx-1]['close'] < klines[idx-1]['open'] and
            klines[idx-2]['close'] < klines[idx-2]['open'])

# 条件4: 连续3根阳线 (M1)
def cond_three_bulls(klines, idx):
    if idx < 2:
        return False
    return (klines[idx]['close'] > klines[idx]['open'] and
            klines[idx-1]['close'] > klines[idx-1]['open'] and
            klines[idx-2]['close'] > klines[idx-2]['open'])

# 条件5: 价格触及布林下轨 + 收阳
def cond_bb_lower_bounce(klines, idx):
    if 'bb_lower' not in klines[idx] or klines[idx]['bb_lower'] is None:
        return False
    low = klines[idx]['low']
    bb_l = klines[idx]['bb_lower']
    # 价格触及或低于下轨
    if low <= bb_l and klines[idx]['close'] > klines[idx]['open']:
        return True
    return False

# 条件6: 价格触及布林上轨 + 收阴
def cond_bb_upper_reject(klines, idx):
    if 'bb_upper' not in klines[idx] or klines[idx]['bb_upper'] is None:
        return False
    high = klines[idx]['high']
    bb_u = klines[idx]['bb_upper']
    if high >= bb_u and klines[idx]['close'] < klines[idx]['open']:
        return True
    return False

# 条件7: 成交量突增(>2x 20期均值) + 反向K线
def cond_volume_spike_reversal(klines, idx):
    if 'volume_ma' not in klines[idx] or klines[idx]['volume_ma'] is None:
        return False
    if klines[idx]['volume_ma'] == 0:
        return False
    vol_ratio = klines[idx]['volume'] / klines[idx]['volume_ma']
    if vol_ratio > 2.0:
        # 前一根下跌，这一根上涨（做多反转）
        if idx > 0 and klines[idx-1]['close'] < klines[idx-1]['open'] and klines[idx]['close'] > klines[idx]['open']:
            return True
    return False

# 条件8: M5 MA5 > MA20 多头回调至MA20 (趋势延续)
def cond_trend_pullback(klines, idx):
    if ('sma5' not in klines[idx] or 'sma20' not in klines[idx] or
        klines[idx]['sma5'] is None or klines[idx]['sma20'] is None):
        return False
    # 多头排列: MA5 > MA20
    if klines[idx]['sma5'] > klines[idx]['sma20']:
        # 价格回到MA20附近 (在MA20的0.1%范围内或略低于)
        price = klines[idx]['close']
        ma20 = klines[idx]['sma20']
        if price >= ma20 * 0.998 and price <= ma20 * 1.002:
            return True
    return False


# ─── 主流程 ────────────────────────────────────────────────────

def analyze_symbol(sym, klines, tf_name):
    """对单个品种/时间框架运行所有假设测试"""
    closes = [k['close'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    volumes = [k['volume'] for k in klines]
    opens = [k['open'] for k in klines]

    n = len(klines)
    if n < 100:
        return {"error": f"Too few bars: {n}"}

    # 计算指标
    rsi = compute_rsi(closes, 14)
    sma5 = compute_sma(closes, 5)
    sma10 = compute_sma(closes, 10)
    sma20 = compute_sma(closes, 20)
    bb_mid, bb_upper, bb_lower = compute_bb(closes, 20, 2)
    atr = compute_atr(highs, lows, closes, 14)

    # 成交量MA
    vol_ma20 = compute_sma(volumes, 20)

    # 注入到 klines
    for i in range(n):
        klines[i]['rsi'] = rsi[i]
        klines[i]['sma5'] = sma5[i]
        klines[i]['sma10'] = sma10[i]
        klines[i]['sma20'] = sma20[i]
        klines[i]['bb_mid'] = bb_mid[i]
        klines[i]['bb_upper'] = bb_upper[i]
        klines[i]['bb_lower'] = bb_lower[i]
        klines[i]['atr'] = atr[i]
        klines[i]['volume_ma'] = vol_ma20[i]

    # 运行测试
    tests = {
        "RSI<30+收阳→1根做多": (cond_rsi_oversold_bullish, "long", 1),
        "RSI<30+收阳→3根做多": (cond_rsi_oversold_bullish, "long", 3),
        "RSI<30+收阳→5根做多": (cond_rsi_oversold_bullish, "long", 5),
        "RSI>70+收阴→1根做空": (cond_rsi_overbought_bearish, "short", 1),
        "RSI>70+收阴→3根做空": (cond_rsi_overbought_bearish, "short", 3),
        "RSI>70+收阴→5根做空": (cond_rsi_overbought_bearish, "short", 5),
        "连续3阴→1根做多": (cond_three_bears, "long", 1),
        "连续3阴→3根做多": (cond_three_bears, "long", 3),
        "连续3阳→1根做空": (cond_three_bulls, "short", 1),
        "连续3阳→3根做空": (cond_three_bulls, "short", 3),
        "布林下轨+收阳→1根做多": (cond_bb_lower_bounce, "long", 1),
        "布林下轨+收阳→3根做多": (cond_bb_lower_bounce, "long", 3),
        "布林下轨+收阳→5根做多": (cond_bb_lower_bounce, "long", 5),
        "布林上轨+收阴→1根做空": (cond_bb_upper_reject, "short", 1),
        "布林上轨+收阴→3根做空": (cond_bb_upper_reject, "short", 3),
        "放量反转→1根做多": (cond_volume_spike_reversal, "long", 1),
        "MA多头回调MA20→1根做多": (cond_trend_pullback, "long", 1),
        "MA多头回调MA20→3根做多": (cond_trend_pullback, "long", 3),
    }

    results = {}
    for label, (cond, direction, fb) in tests.items():
        r = test_hypothesis(klines, cond, direction, fb)
        results[label] = r
        if r["signal_count"] > 0:
            sys.stderr.write(f"  {sym} {tf_name} | {label:25s} | n={r['signal_count']:>5} WR={r['win_rate']:.2f}% avg={r['avg_return']:+.4f}%\n")

    return results


def main():
    print("=" * 80)
    print("  Scalping Round 1 — M1/M5 超短线初始模式挖掘")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    timeframes = ["M1", "M5"]
    all_results = {}

    for tf in timeframes:
        print(f"\n{'─'*80}")
        print(f"  [{tf}] 拉取数据中...")
        print(f"{'─'*80}")
        
        # Fetch 5000 bars per symbol per timeframe
        data = fetch_mt5(tf, lookback=5000)
        
        if "error" in data:
            print(f"  ERROR: {data['error']}")
            all_results[tf] = {"error": data['error']}
            continue

        symbols_present = [s for s in data if isinstance(data.get(s), list) and len(data[s]) > 100]
        print(f"  成功获取 {len(symbols_present)} 个品种数据")

        tf_results = {}
        for sym in symbols_present:
            klines = data[sym]
            print(f"\n  ── {sym} ({len(klines)} bars) ──")
            result = analyze_symbol(sym, klines, tf)
            tf_results[sym] = result

        all_results[tf] = tf_results

    # ─── 汇总分析 ──────────────────────────────────────────
    print(f"\n{'='*80}")
    print("  【累计分析】跨品种汇总")
    print(f"{'='*80}")

    # 按假设汇总
    hypothesis_aggregate = {}
    for tf, tf_results in all_results.items():
        if isinstance(tf_results, dict) and "error" not in tf_results:
            for sym, sym_results in tf_results.items():
                if isinstance(sym_results, dict) and "error" not in sym_results:
                    for label, stats in sym_results.items():
                        if stats["signal_count"] > 0:
                            key = f"{tf}/{label}"
                            if key not in hypothesis_aggregate:
                                hypothesis_aggregate[key] = {
                                    "tf": tf, "label": label,
                                    "total_signals": 0, "total_wins": 0,
                                    "weighted_wr": 0, "total_avg_ret": 0,
                                    "symbols": []
                                }
                            h = hypothesis_aggregate[key]
                            h["total_signals"] += stats["signal_count"]
                            h["total_wins"] += stats["win_count"]
                            h["total_avg_ret"] += stats["avg_return"] * stats["signal_count"]
                            h["symbols"].append(sym)

    # 按总信号数排序
    sorted_h = sorted(hypothesis_aggregate.values(), key=lambda x: x["total_signals"], reverse=True)

    print(f"\n{'标签':35s} {'TF':4s} {'信号':>6s} {'胜率':>7s} {'95%CI_low':>9s} {'平均收益':>9s}  {'品种'}")
    print(f"{'─'*35} {'─'*4} {'─'*6} {'─'*7} {'─'*9} {'─'*9}  {'─'*10}")
    for h in sorted_h:
        total = h["total_signals"]
        wins = h["total_wins"]
        wr = wins / total if total > 0 else 0
        ci_l, _ = wilson_ci(total, wr)
        avg_ret = h["total_avg_ret"] / total if total > 0 else 0
        symbols_str = ", ".join(set(h["symbols"]))
        print(f"{h['label']:35s} {h['tf']:4s} {total:>6d} {wr*100:>6.2f}% {ci_l*100:>8.2f}% {avg_ret:>+8.4f}%  {symbols_str}")

    # ─── 输出 JSON ─────────────────────────────────────────
    output = {
        "round": 1,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": all_results,
        "summary": {
            h["label"]: {
                "tf": h["tf"],
                "total_signals": h["total_signals"],
                "total_wins": h["total_wins"],
                "win_rate": round(wins / total * 100, 2) if (total := h["total_signals"]) > 0 else 0,
                "avg_return": round(h["total_avg_ret"] / h["total_signals"], 4) if h["total_signals"] > 0 else 0,
            }
            for h in sorted_h
        }
    }

    print(f"\n{'='*80}")
    print("  Round 1 完成")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


if __name__ == "__main__":
    result = main()
    # 保存到文件
    import os
    os.makedirs("reports", exist_ok=True)
    with open("reports/round_001.json", "w", encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nReports saved to reports/round_001.json")
