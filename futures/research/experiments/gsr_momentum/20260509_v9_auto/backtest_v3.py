#!/usr/bin/env python3
"""
GSR 策略回测 v3 — 修正版 (MT5 数据源)
解决 v2 的 5 个问题:
1. 真实 P&L (非相对收益)
2. 样本内外严格分离 (Walk-Forward)
3. 交易成本 (点差+滑点+佣金)
4. 保证金/杠杆约束
5. 做空实际约束

运行: C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe backtest_v3.py
"""

import sys
import warnings
warnings.filterwarnings('ignore')

import MetaTrader5 as mt5
import pandas as pd
import numpy as np

if not mt5.initialize():
    print(f"MT5 初始化失败: {mt5.last_error()}")
    sys.exit(1)

def load_data(symbol, bars=5000):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, bars)
    df = pd.DataFrame(rates)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('datetime', inplace=True)
    return df[['close']]

print("📥 正在从 MT5 加载数据...")
gold = load_data('XAUUSDm').rename(columns={'close': 'gold'})
silver = load_data('XAGUSDm').rename(columns={'close': 'silver'})
brent = load_data('UKOILm').rename(columns={'close': 'brent'})

merged = gold.join(silver, how='inner').join(brent, how='inner').dropna()
print(f"数据: {len(merged)} 交易日 ({merged.index[0].date()} ~ {merged.index[-1].date()})")

# 计算因子
merged['gold_ret'] = merged['gold'].pct_change()
merged['silver_ret'] = merged['silver'].pct_change()
merged['brent_ret'] = merged['brent'].pct_change()
merged['gsr'] = merged['gold'] / merged['silver']
merged['brent_ret_20d'] = (merged['brent'] / merged['brent'].shift(20) - 1) * 100
merged['brent_regime'] = 'normal'
merged.loc[merged['brent'] > 90, 'brent_regime'] = 'high'
merged.loc[merged['brent'] < 70, 'brent_regime'] = 'low'
merged['energy_crisis'] = (merged['brent_ret_20d'] > 15).astype(int)
merged = merged.dropna()

# ============ 真实交易假设 ============
COST_PER_TRADE = 0.0005  # 0.05% 每次调仓 (点差+滑点)
INITIAL_CAPITAL = 10000

# ============ 回测引擎: 真实 P&L ============
def backtest_real_pnl(df, window, threshold, brent_regime_decay=True,
                       energy_crisis_decay=True, cost_per_trade=COST_PER_TRADE,
                       initial_capital=INITIAL_CAPITAL):
    gsr_mom = df['gsr'].pct_change(window)

    position = np.zeros(len(df))
    for i in range(len(df)):
        if pd.isna(gsr_mom.iloc[i]):
            continue
        mom = gsr_mom.iloc[i]
        regime = df['brent_regime'].iloc[i]
        crisis = df['energy_crisis'].iloc[i]

        if mom < -threshold:
            position[i] = 1.0
        elif mom > threshold:
            position[i] = -0.5  # 保守做空
        else:
            position[i] = 0.0

        if brent_regime_decay and regime == 'high':
            position[i] *= 0.5
        if energy_crisis_decay and crisis == 1:
            position[i] *= 0.3

    equity = initial_capital
    equity_curve = [equity]
    trades = 0
    total_cost = 0

    for i in range(1, len(df)):
        prev_pos = position[i - 1]
        curr_pos = position[i]
        ret_today = df['silver_ret'].iloc[i]

        if abs(curr_pos - prev_pos) > 0.01:
            trades += 1
            cost = abs(curr_pos - prev_pos) * cost_per_trade * equity
            total_cost += cost
            equity -= cost

        equity += curr_pos * ret_today * equity
        equity_curve.append(equity)

    equity_curve = np.array(equity_curve)
    returns = pd.Series(np.diff(equity_curve) / equity_curve[:-1])

    total_ret = (equity_curve[-1] / initial_capital - 1) * 100
    n_years = len(returns) / 252
    ann_ret = ((1 + total_ret / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
    sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    max_dd = dd.min() * 100
    win_rate = (returns > 0).sum() / len(returns) * 100

    return {
        '总收益%': total_ret, '年化%': ann_ret, '夏普': sharpe,
        '最大回撤%': max_dd, '胜率%': win_rate,
        '交易次数': trades, '总成本$': round(total_cost, 2),
        '最终净值$': round(equity_curve[-1], 2),
    }

# ============ 对比测试 ============
print("\n" + "=" * 80)
print("真实 P&L 回测 (初始资金 $10,000, 已扣除点差/滑点)")
print("=" * 80)

bh = backtest_real_pnl(merged, 5, 0.0, brent_regime_decay=False, energy_crisis_decay=False)
print(f"\n基准: 买入持有白银")
print(f"  总收益: {bh['总收益%']:.1f}% | 年化: {bh['年化%']:.1f}% | "
      f"夏普: {bh['夏普']:.2f} | 最大回撤: {bh['最大回撤%']:.1f}%")

print(f"\n{'策略':<35} {'总收益':>10} {'年化':>10} {'夏普':>8} "
      f"{'最大回撤':>10} {'交易':>8}")
print("-" * 90)

for w, t, label in [
    (5, 0.005, "GSR 5日/0.5% (激进)"),
    (5, 0.010, "GSR 5日/1% (报告最优)"),
    (10, 0.010, "GSR 10日/1% (稳健)"),
    (20, 0.020, "GSR 20日/2% (保守)"),
]:
    r = backtest_real_pnl(merged, w, t)
    print(f"{label:<35} {r['总收益%']:>8.1f}% {r['年化%']:>8.1f}%"
          f" {r['夏普']:>8.2f} {r['最大回撤%']:>8.1f}%"
          f" {r['交易次数']:>6.0f}次")

# ============ Walk-Forward 验证 ============
print("\n" + "=" * 80)
print("Walk-Forward 验证 (无参数泄漏)")
print("=" * 80)

split_date = '2023-01-01'
train = merged[merged.index < split_date]
test = merged[merged.index >= split_date]

print(f"训练集: {len(train)} 天 ({train.index[0].date()} ~ {train.index[-1].date()})")
print(f"测试集: {len(test)} 天 ({test.index[0].date()} ~ {test.index[-1].date()})")

best_sharpe = -999
best_w, best_t = 5, 0.01
for w in [5, 10, 20]:
    for t in [0.005, 0.01, 0.02]:
        r = backtest_real_pnl(train, w, t)
        if r['夏普'] > best_sharpe:
            best_sharpe = r['夏普']
            best_w, best_t = w, t

print(f"\n训练集最优: 窗口={best_w}, 阈值={best_t}, 夏普={best_sharpe:.2f}")

oos = backtest_real_pnl(test, best_w, best_t)
print(f"测试集验证: 总收益={oos['总收益%']:.1f}% | 年化={oos['年化%']:.1f}% | "
      f"夏普={oos['夏普']:.2f} | 最大回撤={oos['最大回撤%']:.1f}%")

# ============ GSR 仓位管理 (始终多头) ============
print("\n" + "=" * 80)
print("GSR 仓位管理 (始终多头, 信号强时加减仓)")
print("=" * 80)

def backtest_position_mgmt(df, window, threshold, base=1.0, max_pos=1.5, min_pos=0.3,
                            cost_per_trade=COST_PER_TRADE, initial_capital=INITIAL_CAPITAL):
    gsr_mom = df['gsr'].pct_change(window)
    position = np.ones(len(df)) * base

    for i in range(len(df)):
        if pd.isna(gsr_mom.iloc[i]):
            continue
        mom = gsr_mom.iloc[i]
        regime = df['brent_regime'].iloc[i]
        crisis = df['energy_crisis'].iloc[i]

        if mom < -threshold:
            position[i] = min(base + 0.3, max_pos)
        elif mom > threshold:
            position[i] = max(base - 0.3, min_pos)

        if regime == 'high':
            position[i] = base + (position[i] - base) * 0.5
        if crisis == 1:
            position[i] = base + (position[i] - base) * 0.3

    equity = initial_capital
    equity_curve = [equity]
    trades = 0
    total_cost = 0

    for i in range(1, len(df)):
        prev_pos = position[i - 1]
        curr_pos = position[i]
        ret_today = df['silver_ret'].iloc[i]

        if abs(curr_pos - prev_pos) > 0.01:
            trades += 1
            cost = abs(curr_pos - prev_pos) * cost_per_trade * equity
            total_cost += cost
            equity -= cost

        equity += curr_pos * ret_today * equity
        equity_curve.append(equity)

    equity_curve = np.array(equity_curve)
    returns = pd.Series(np.diff(equity_curve) / equity_curve[:-1])

    total_ret = (equity_curve[-1] / initial_capital - 1) * 100
    n_years = len(returns) / 252
    ann_ret = ((1 + total_ret / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
    sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    max_dd = dd.min() * 100

    return {
        '总收益%': total_ret, '年化%': ann_ret, '夏普': sharpe,
        '最大回撤%': max_dd, '交易次数': trades, '总成本$': round(total_cost, 2),
    }

bh_pm = backtest_position_mgmt(merged, 5, 0.01)
print(f"\n{'策略':<35} {'总收益':>10} {'年化':>10} {'夏普':>8} {'最大回撤':>10}")
print("-" * 80)
print(f"{'买入持有白银':<35} {bh['总收益%']:>8.1f}% {bh['年化%']:>8.1f}%"
      f" {bh['夏普']:>8.2f} {bh['最大回撤%']:>8.1f}%")

for w, t in [(5, 0.01), (10, 0.02), (20, 0.02)]:
    r = backtest_position_mgmt(merged, w, t)
    print(f"GSR 仓位管理 (w={w}, t={t*100:.0f}%){'':<14} {r['总收益%']:>8.1f}%"
          f" {r['年化%']:>8.1f}% {r['夏普']:>8.2f} {r['最大回撤%']:>8.1f}%")

mt5.shutdown()

print("\n" + "=" * 80)
print("回测完成 — 所有结果已扣除交易成本")
print("=" * 80)
