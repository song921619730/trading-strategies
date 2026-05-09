#!/usr/bin/env python3
"""
实验 20260509_v7_auto: 宏观复合风险预警信号回测

假设 H1: 高油价 + 鹰派宏观环境（美元走强+波动率放大）的复合信号，
        对股指期货下行的预测能力显著强于单一油价信号。

假设 H2: 黄金在高油价+鹰派Fed复合环境中表现出独特的对冲属性，
        其相对收益（黄金-股指）在该 regime 下显著为正。

数据源: MT5 D1 历史数据
Python: Windows Python 3.12
"""

import sys
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# MT5 数据获取模块
# ============================================================

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
PYTHON_PATH = r"C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe"

SYMBOLS_MT5 = {
    "XAUUSD": "XAUUSDm",
    "USOIL": "USOILm",
    "UKOIL": "UKOILm",
    "USTEC": "USTECm",
    "US500": "US500m",
    "US30": "US30m",
    "EURUSD": "EURUSDm",
    "USDCHF": "USDCHFm",
}

def fetch_mt5_data():
    """通过 Windows Python + MT5 获取所有品种 D1 历史数据"""
    script = r"""
import MetaTrader5 as mt5
import json
import sys
from datetime import datetime

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

symbols = {
    "XAUUSD": "XAUUSDm", "USOIL": "USOILm", "UKOIL": "UKOILm",
    "USTEC": "USTECm", "US500": "US500m", "US30": "US30m",
    "EURUSD": "EURUSDm", "USDCHF": "USDCHFm",
}

if not mt5.initialize(path=MT5_PATH):
    print(json.dumps({"error": f"MT5 init failed: {mt5.last_error()}"}))
    sys.exit(1)

result = {}
for code, sym in symbols.items():
    mt5.symbol_select(sym, True)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5000)
    if rates is not None and len(rates) > 0:
        candles = []
        for r in rates:
            candles.append({
                "time": datetime.fromtimestamp(r["time"]).strftime("%Y-%m-%d"),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r["tick_volume"]),
            })
        result[code] = {
            "symbol": sym,
            "count": len(candles),
            "first_date": candles[0]["time"],
            "last_date": candles[-1]["time"],
            "data": candles,
        }
    else:
        result[code] = {"error": "No data", "symbol": sym}

mt5.shutdown()
print(json.dumps(result, ensure_ascii=False))
"""
    # Write temp script and execute
    temp_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mt5_fetch_tmp.py")
    with open(temp_script, 'w', encoding='utf-8') as f:
        f.write(script)
    
    try:
        import subprocess
        proc = subprocess.run(
            [PYTHON_PATH, temp_script],
            capture_output=True, text=True, timeout=120,
            creationflags=0x08000000 if os.name == 'nt' else 0
        )
        # Try to find JSON in output
        output = proc.stdout.strip()
        # Find JSON object
        start = output.find('{')
        end = output.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(output[start:end])
            return data
        else:
            print(f"MT5 fetch stdout: {output[:500]}")
            print(f"MT5 fetch stderr: {proc.stderr[:500]}")
            return None
    except Exception as e:
        print(f"MT5 fetch error: {e}")
        return None
    finally:
        if os.path.exists(temp_script):
            os.remove(temp_script)


# ============================================================
# 信号计算模块
# ============================================================

def build_dataframe(mt5_data):
    """将 MT5 数据合并为对齐的 DataFrame"""
    if mt5_data is None:
        return None
    
    dfs = {}
    for code, info in mt5_data.items():
        if "data" not in info:
            continue
        df = pd.DataFrame(info["data"])
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)
        df["return"] = df["close"].pct_change()
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        # ATR 14
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df["close"].shift(1)),
                abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr_14"] = df["tr"].rolling(14).mean()
        # 20日收益率
        df["ret_20d"] = df["close"].pct_change(20)
        # 60日波动率
        df["vol_60d"] = df["return"].rolling(60).std() * np.sqrt(252)
        dfs[code] = df
    
    # 合并所有品种的收盘价
    close_df = pd.DataFrame({code: dfs[code]["close"] for code in dfs})
    return_df = pd.DataFrame({code: dfs[code]["return"] for code in dfs})
    
    return dfs, close_df, return_df


def compute_macro_regime(dfs, close_df, return_df):
    """
    计算宏观复合风险预警信号
    
    Regime 定义:
    1. 高油价: UKOIL > 95美元 (布油)
    2. 鹰派美元: DXY代理 = USDCHF 相对强度 (USDCHF上涨 = 美元走强)
    3. 波动率放大: 跨品种平均波动率 > 历史60分位
    4. 风险预警: 原油20日涨幅 > 15%
    
    复合信号 = 高油价 AND (美元走强 OR 波动率放大)
    """
    if "UKOIL" not in dfs or "USDCHF" not in dfs:
        return None, None
    
    ukoil = dfs["UKOIL"]
    usdchf = dfs["USDCHF"]
    
    # 1. 高油价 regime
    high_oil = ukoil["close"] > 95.0
    
    # 2. 美元走强代理: USDCHF 20日收益率 > 0
    usd_strength = usdchf["ret_20d"] > 0
    
    # 3. 波动率放大: UKOIL 60日波动率 > 历史60分位
    oil_vol = ukoil["vol_60d"]
    vol_threshold = oil_vol.quantile(0.60)
    high_vol = oil_vol > vol_threshold
    
    # 4. 原油20日涨幅 > 15% (原有风险预警)
    oil_surge = ukoil["ret_20d"] > 0.15
    
    # 复合信号A: 高油价 + 美元走强
    composite_hawkish = high_oil & usd_strength
    
    # 复合信号B: 高油价 + 波动率放大
    composite_volatile = high_oil & high_vol
    
    # 复合信号C (最强): 高油价 + 美元走强 + 波动率放大
    composite_strong = high_oil & usd_strength & high_vol
    
    regime_df = pd.DataFrame({
        "high_oil": high_oil,
        "usd_strength": usd_strength,
        "high_vol": high_vol,
        "oil_surge": oil_surge,
        "composite_hawkish": composite_hawkish,
        "composite_volatile": composite_volatile,
        "composite_strong": composite_strong,
    }, index=ukoil.index)
    
    return regime_df, {
        "vol_threshold": vol_threshold,
    }


# ============================================================
# 回测引擎
# ============================================================

def regime_backtest(return_df, regime_df, symbol, regime_col, min_days=30):
    """
    计算特定 regime 下某品种的统计表现
    
    返回: regime 期间 vs 非 regime 期间的对比统计
    """
    if symbol not in return_df.columns:
        return None
    
    # 对齐 regime 和 return 的索引
    aligned_regime = regime_df[regime_col].reindex(return_df.index)
    valid = pd.DataFrame({regime_col: aligned_regime, symbol: return_df[symbol]}).dropna()
    valid = valid[valid.index >= valid.index.min() + pd.Timedelta(days=365)]  # 去掉首年预热
    
    in_regime = valid[valid[regime_col] == True]
    out_regime = valid[valid[regime_col] == False]
    
    if len(in_regime) < min_days or len(out_regime) < min_days:
        return None
    
    results = {}
    for label, subset in [("in_regime", in_regime), ("out_regime", out_regime), ("all", valid)]:
        rets = subset[symbol].dropna()
        if len(rets) == 0:
            continue
        cumulative = (1 + rets).cumprod()
        total_return = cumulative.iloc[-1] - 1
        
        # 年化
        years = len(rets) / 252
        ann_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
        
        # 夏普 (假设无风险利率 2%)
        excess = rets - 0.02/252
        sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0
        
        # 最大回撤
        cum_max = cumulative.cummax()
        drawdown = (cumulative - cum_max) / cum_max
        max_dd = drawdown.min()
        
        # 胜率 (日度)
        win_rate = (rets > 0).sum() / len(rets)
        
        # 波动率
        ann_vol = rets.std() * np.sqrt(252)
        
        # 卡玛比率
        calmar = ann_return / abs(max_dd) if max_dd != 0 else 0
        
        results[label] = {
            "days": len(rets),
            "total_return": round(total_return * 100, 2),
            "ann_return": round(ann_return * 100, 2),
            "sharpe": round(sharpe, 3),
            "max_dd": round(max_dd * 100, 2),
            "win_rate": round(win_rate * 100, 2),
            "ann_vol": round(ann_vol * 100, 2),
            "calmar": round(calmar, 3),
        }
    
    return results


def gold_hedge_test(return_df, regime_df, symbol, regime_col, min_days=30):
    """
    测试黄金在高油价+鹰派环境下的对冲效果
    
    比较: 纯股指期货 vs 60%股指+40%黄金 组合
    """
    needed = [c for c in ["USTEC", "XAUUSD"] if c in return_df.columns]
    if len(needed) < 2:
        return None
    
    aligned_regime = regime_df[regime_col].reindex(return_df.index)
    valid = pd.DataFrame({
        regime_col: aligned_regime,
        "USTEC": return_df["USTEC"],
        "XAUUSD": return_df["XAUUSD"]
    }).dropna()
    valid = valid[valid.index >= valid.index.min() + pd.Timedelta(days=365)]
    
    in_regime = valid[valid[regime_col] == True]
    out_regime = valid[valid[regime_col] == False]
    
    results = {}
    for label, subset in [("in_regime", in_regime), ("out_regime", out_regime)]:
        if len(subset) < min_days:
            continue
        
        ustec_ret = subset["USTEC"]
        gold_ret = subset["XAUUSD"]
        
        # 纯USTEC
        cum_ustec = (1 + ustec_ret).cumprod()
        ustec_total = cum_ustec.iloc[-1] - 1
        
        # 60/40 组合
        port_ret = 0.6 * ustec_ret + 0.4 * gold_ret
        cum_port = (1 + port_ret).cumprod()
        port_total = cum_port.iloc[-1] - 1
        
        # 对冲效果 = 组合收益 - 纯股指收益
        hedge_effect = port_total - ustec_total
        
        # 最大回撤对比
        dd_ustec = ((cum_ustec - cum_ustec.cummax()) / cum_ustec.cummax()).min()
        dd_port = ((cum_port - cum_port.cummax()) / cum_port.cummax()).min()
        
        results[label] = {
            "days": len(subset),
            "ustec_return": round(ustec_total * 100, 2),
            "portfolio_return": round(port_total * 100, 2),
            "hedge_effect_pct": round(hedge_effect * 100, 2),
            "ustec_max_dd": round(dd_ustec * 100, 2),
            "port_max_dd": round(dd_port * 100, 2),
            "dd_reduction": round((dd_port - dd_ustec) * 100, 2),
        }
    
    return results


def statistical_test(return_df, regime_df, symbol, regime_col):
    """
    t检验: regime 期间 vs 非 regime 期间的日均收益差异
    """
    from scipy import stats
    
    # 对齐索引
    aligned_regime = regime_df[regime_col].reindex(return_df.index)
    valid = pd.DataFrame({regime_col: aligned_regime, symbol: return_df[symbol]}).dropna()
    valid = valid[valid.index >= valid.index.min() + pd.Timedelta(days=365)]
    
    in_r = valid[valid[regime_col] == True][symbol].dropna()
    out_r = valid[valid[regime_col] == False][symbol].dropna()
    
    if len(in_r) < 30 or len(out_r) < 30:
        return None
    
    # Welch's t-test
    t_stat, p_value = stats.ttest_ind(in_r, out_r, equal_var=False)
    
    # Cohen's d (效应量)
    n1, n2 = len(in_r), len(out_r)
    m1, m2 = in_r.mean(), out_r.mean()
    s1, s2 = in_r.std(), out_r.std()
    pooled_std = np.sqrt(((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2))
    cohens_d = (m1 - m2) / pooled_std if pooled_std > 0 else 0
    
    return {
        "t_stat": round(t_stat, 4),
        "p_value": round(p_value, 6),
        "cohens_d": round(cohens_d, 4),
        "mean_in_regime": round(in_r.mean() * 100, 4),
        "mean_out_regime": round(out_r.mean() * 100, 4),
        "diff_daily_bps": round((in_r.mean() - out_r.mean()) * 10000, 2),
        "n_in": len(in_r),
        "n_out": len(out_r),
    }


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 70)
    print("实验 20260509_v7_auto: 宏观复合风险预警信号回测")
    print("=" * 70)
    
    # 1. 获取数据
    print("\n[1] 获取 MT5 历史数据...")
    mt5_data = fetch_mt5_data()
    
    if mt5_data is None:
        print("❌ MT5 数据获取失败，回测终止")
        sys.exit(1)
    
    # 打印数据范围
    print("\n数据范围:")
    for code, info in mt5_data.items():
        if "first_date" in info:
            print(f"  {code}: {info['first_date']} → {info['last_date']} ({info['count']} 天)")
    
    # 2. 构建 DataFrame
    print("\n[2] 构建数据帧...")
    result = build_dataframe(mt5_data)
    if result is None:
        print("❌ 数据帧构建失败")
        sys.exit(1)
    
    dfs, close_df, return_df = result
    print(f"  可用品种: {list(dfs.keys())}")
    print(f"  日期范围: {close_df.index.min()} → {close_df.index.max()}")
    print(f"  总交易日: {len(close_df)}")
    
    # 3. 计算宏观 Regime
    print("\n[3] 计算宏观风险 Regime...")
    regime_df, regime_params = compute_macro_regime(dfs, close_df, return_df)
    if regime_df is None:
        print("❌ Regime 计算失败")
        sys.exit(1)
    
    vol_thresh = regime_params["vol_threshold"]
    print(f"  波动率阈值 (60分位): {vol_thresh:.4f}")
    
    for col in ["high_oil", "usd_strength", "high_vol", "oil_surge",
                 "composite_hawkish", "composite_volatile", "composite_strong"]:
        count = regime_df[col].sum()
        pct = count / len(regime_df) * 100
        print(f"  {col}: {count} 天 ({pct:.1f}%)")
    
    # 4. 回测 - H1: 复合信号对股指的预测力
    print("\n[4] 回测 H1: 复合风险信号对股指期货的预测能力")
    print("-" * 50)
    
    all_results = {}
    
    for regime_col in ["composite_hawkish", "composite_volatile", "composite_strong", "high_oil", "oil_surge"]:
        print(f"\n  === {regime_col} ===")
        for symbol in ["USTEC", "US500", "US30"]:
            bt = regime_backtest(return_df, regime_df, symbol, regime_col)
            if bt is None:
                print(f"    {symbol}: 样本不足")
                continue
            
            all_results[f"{regime_col}_{symbol}"] = bt
            
            # 打印关键对比
            if "in_regime" in bt and "out_regime" in bt:
                ir = bt["in_regime"]
                or_ = bt["out_regime"]
                print(f"    {symbol}:")
                print(f"      Regime内: 年化 {ir['ann_return']}% | 夏普 {ir['sharpe']} | 回撤 {ir['max_dd']}% | {ir['days']}天")
                print(f"      Regime外: 年化 {or_['ann_return']}% | 夏普 {or_['sharpe']} | 回撤 {or_['max_dd']}% | {or_['days']}天")
                print(f"      差异: 年化 {ir['ann_return'] - or_['ann_return']:+.2f}% | 夏普 {ir['sharpe'] - or_['sharpe']:+.3f}")
            
            # 统计检验
            st = statistical_test(return_df, regime_df, symbol, regime_col)
            if st:
                sig = "***" if st["p_value"] < 0.01 else ("**" if st["p_value"] < 0.05 else ("*" if st["p_value"] < 0.1 else "n.s."))
                print(f"      t={st['t_stat']:.3f} p={st['p_value']:.4f} {sig} | Cohen's d={st['cohens_d']:.3f} | 日均差异={st['diff_daily_bps']:+.2f}bps")
    
    # 5. 回测 - H2: 黄金对冲效果
    print("\n[5] 回测 H2: 黄金在复合风险环境下的对冲效果")
    print("-" * 50)
    
    for regime_col in ["composite_strong", "composite_hawkish", "high_oil"]:
        hedge = gold_hedge_test(return_df, regime_df, "USTEC", regime_col)
        if hedge is None:
            print(f"  {regime_col}: 数据不足")
            continue
        
        all_results[f"hedge_{regime_col}"] = hedge
        print(f"  === {regime_col} ===")
        for label, res in hedge.items():
            print(f"    {label}: USTEC {res['ustec_return']}% | 60/40组合 {res['portfolio_return']}% | 对冲效果 {res['hedge_effect_pct']:+.2f}%")
            print(f"           USTEC回撤 {res['ustec_max_dd']}% | 组合回撤 {res['port_max_dd']}% | 回撤减少 {res['dd_reduction']:+.2f}% | {res['days']}天")
    
    # 6. 汇总输出
    print("\n" + "=" * 70)
    print("📊 汇总结果")
    print("=" * 70)
    
    # 保存结果到 JSON
    result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_results.json")
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存至: {result_path}")
    
    # 打印关键发现
    print("\n🔑 关键发现:")
    
    # 找出最显著的信号
    best_diff = -999
    best_regime = ""
    best_symbol = ""
    for key, bt in all_results.items():
        if key.startswith("hedge_"):
            continue
        if "in_regime" in bt and "out_regime" in bt:
            diff = bt["in_regime"]["ann_return"] - bt["out_regime"]["ann_return"]
            if diff < best_diff:  # 负差异越大越好（预警信号）
                best_diff = diff
                parts = key.rsplit("_", 1)
                best_regime = parts[0]
                best_symbol = parts[1]
    
    if best_regime:
        print(f"  最强预警信号: {best_regime} → {best_symbol}")
        bt = all_results[f"{best_regime}_{best_symbol}"]
        print(f"    Regime内年化: {bt['in_regime']['ann_return']}% vs Regime外: {bt['out_regime']['ann_return']}%")
        print(f"    差异: {best_diff:+.2f}%")
    
    print("\n✅ 回测完成")
    return all_results


if __name__ == "__main__":
    main()
