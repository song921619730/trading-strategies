#!/usr/bin/env python3
"""
补充分析: 检验复合风险信号的统计显著性
- 使用更长周期的累计收益作为检验对象 (20日/60日窗口)
- 分析信号在不同子样本期间的表现
- 检验信号的"尾部风险"预测能力
"""

import sys
import os
import json
import numpy as np
import pandas as pd
from collections import defaultdict

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
PYTHON_PATH = r"C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe"

def fetch_mt5_data():
    """通过 Windows Python + MT5 获取数据"""
    script = r"""
import MetaTrader5 as mt5
import json, sys
from datetime import datetime

if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
    print(json.dumps({"error": "MT5 init failed"}))
    sys.exit(1)

symbols = {"XAUUSD":"XAUUSDm","USOIL":"USOILm","UKOIL":"UKOILm",
           "USTEC":"USTECm","US500":"US500m","US30":"US30m",
           "EURUSD":"EURUSDm","USDCHF":"USDCHFm"}

result = {}
for code, sym in symbols.items():
    mt5.symbol_select(sym, True)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5000)
    if rates is not None and len(rates) > 0:
        candles = []
        for r in rates:
            candles.append({
                "time": datetime.fromtimestamp(r["time"]).strftime("%Y-%m-%d"),
                "close": float(r["close"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "open": float(r["open"]),
            })
        result[code] = candles
mt5.shutdown()
print(json.dumps(result))
"""
    temp_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mt5_tmp2.py")
    with open(temp_script, 'w', encoding='utf-8') as f:
        f.write(script)
    try:
        import subprocess
        proc = subprocess.run([PYTHON_PATH, temp_script], capture_output=True, text=True, timeout=120)
        output = proc.stdout.strip()
        start = output.find('{')
        end = output.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(output[start:end])
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        if os.path.exists(temp_script):
            os.remove(temp_script)


def main():
    print("=" * 70)
    print("补充分析: 复合风险信号的深度统计检验")
    print("=" * 70)
    
    mt5_data = fetch_mt5_data()
    if mt5_data is None:
        print("❌ 数据获取失败")
        sys.exit(1)
    
    # 构建 DataFrame
    dfs = {}
    for code, candles in mt5_data.items():
        df = pd.DataFrame(candles)
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)
        df["return"] = df["close"].pct_change()
        df["ret_20d"] = df["close"].pct_change(20)
        df["ret_60d"] = df["close"].pct_change(60)
        df["tr"] = np.maximum(df["high"] - df["low"],
                              np.maximum(abs(df["high"] - df["close"].shift(1)),
                                        abs(df["low"] - df["close"].shift(1))))
        df["atr_14"] = df["tr"].rolling(14).mean()
        df["vol_60d"] = df["return"].rolling(60).std() * np.sqrt(252)
        dfs[code] = df
    
    return_df = pd.DataFrame({code: dfs[code]["return"] for code in dfs})
    
    # 计算 Regime
    ukoil = dfs["UKOIL"]
    usdchf = dfs["USDCHF"]
    
    high_oil = ukoil["close"] > 95.0
    usd_strength = usdchf["ret_20d"] > 0
    oil_vol = ukoil["vol_60d"]
    vol_threshold = oil_vol.quantile(0.60)
    high_vol = oil_vol > vol_threshold
    
    composite_hawkish = high_oil & usd_strength
    composite_strong = high_oil & usd_strength & high_vol
    
    regime_df = pd.DataFrame({
        "high_oil": high_oil, "usd_strength": usd_strength,
        "high_vol": high_vol,
        "composite_hawkish": composite_hawkish,
        "composite_strong": composite_strong,
    }, index=ukoil.index)
    
    results = {}
    
    # ============================================================
    # 分析 1: 20日累计收益检验
    # ============================================================
    print("\n[分析1] 20日累计收益检验 (降低噪音)")
    print("-" * 50)
    
    for regime_col in ["composite_hawkish", "composite_strong", "high_oil"]:
        aligned = regime_df[regime_col].reindex(return_df.index)
        
        for symbol in ["USTEC", "US500", "US30"]:
            rets_20d = return_df[symbol].rolling(20).sum()
            valid = pd.DataFrame({regime_col: aligned, "ret_20d": rets_20d}).dropna()
            # 预热期
            warmup = valid.index.min() + pd.Timedelta(days=365)
            valid = valid[valid.index >= warmup]
            
            in_r = valid[valid[regime_col] == True]["ret_20d"]
            out_r = valid[valid[regime_col] == False]["ret_20d"]
            
            if len(in_r) < 10 or len(out_r) < 10:
                continue
            
            # 使用 scipy t-test
            from scipy import stats
            t_stat, p_value = stats.ttest_ind(in_r, out_r, equal_var=False)
            
            n1, n2 = len(in_r), len(out_r)
            m1, m2 = in_r.mean(), out_r.mean()
            s1, s2 = in_r.std(), out_r.std()
            pooled_std = np.sqrt(((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2))
            cohens_d = (m1 - m2) / pooled_std if pooled_std > 0 else 0
            
            sig = "***" if p_value < 0.01 else ("**" if p_value < 0.05 else ("*" if p_value < 0.1 else "n.s."))
            
            print(f"  {regime_col} / {symbol}:")
            print(f"    Regime内20日收益均值: {m1*100:+.3f}% ({n1}个窗口)")
            print(f"    Regime外20日收益均值: {out_r.mean()*100:+.3f}% ({n2}个窗口)")
            print(f"    t={t_stat:.3f} p={p_value:.4f} {sig} | d={cohens_d:.3f}")
            
            results[f"20d_{regime_col}_{symbol}"] = {
                "mean_in": round(m1*100, 3), "mean_out": round(out_r.mean()*100, 3),
                "t": round(t_stat, 3), "p": round(p_value, 4), "d": round(cohens_d, 3),
                "n_in": n1, "n_out": n2,
            }
    
    # ============================================================
    # 分析 2: 尾部风险预测能力 (大幅下跌日)
    # ============================================================
    print("\n[分析2] 尾部风险预测能力 (日跌幅 > 2%)")
    print("-" * 50)
    
    for regime_col in ["composite_hawkish", "composite_strong", "high_oil"]:
        aligned = regime_df[regime_col].reindex(return_df.index)
        
        for symbol in ["USTEC", "US500", "US30"]:
            valid = pd.DataFrame({regime_col: aligned, symbol: return_df[symbol]}).dropna()
            warmup = valid.index.min() + pd.Timedelta(days=365)
            valid = valid[valid.index >= warmup]
            
            in_r = valid[valid[regime_col] == True][symbol]
            out_r = valid[valid[regime_col] == False][symbol]
            
            if len(in_r) < 10:
                continue
            
            # 大幅下跌日比例 (跌幅 > 2%)
            tail_in = (in_r < -0.02).sum() / len(in_r)
            tail_out = (out_r < -0.02).sum() / len(out_r)
            
            # 大幅上涨日比例 (涨幅 > 2%)
            big_up_in = (in_r > 0.02).sum() / len(in_r)
            big_up_out = (out_r > 0.02).sum() / len(out_r)
            
            # 卡方检验
            from scipy import stats
            contingency = np.array([
                [(in_r < -0.02).sum(), (in_r >= -0.02).sum()],
                [(out_r < -0.02).sum(), (out_r >= -0.02).sum()]
            ])
            chi2, chi_p, _, _ = stats.chi2_contingency(contingency)
            sig = "***" if chi_p < 0.01 else ("**" if chi_p < 0.05 else ("*" if chi_p < 0.1 else "n.s."))
            
            print(f"  {regime_col} / {symbol}:")
            print(f"    Regime内大跌日(>-2%): {tail_in*100:.1f}% ({(in_r < -0.02).sum()}/{len(in_r)})")
            print(f"    Regime外大跌日(>-2%): {tail_out*100:.1f}% ({(out_r < -0.02).sum()}/{len(out_r)})")
            print(f"    倍数: {tail_in/tail_out:.2f}x | 卡方 p={chi_p:.4f} {sig}")
            print(f"    Regime内大涨日(>+2%): {big_up_in*100:.1f}% | Regime外: {big_up_out*100:.1f}%")
            
            results[f"tail_{regime_col}_{symbol}"] = {
                "tail_in_pct": round(tail_in*100, 2), "tail_out_pct": round(tail_out*100, 2),
                "tail_ratio": round(tail_in/tail_out, 2) if tail_out > 0 else None,
                "chi2_p": round(chi_p, 4),
                "big_up_in_pct": round(big_up_in*100, 2), "big_up_out_pct": round(big_up_out*100, 2),
            }
    
    # ============================================================
    # 分析 3: 子样本期间分析 (2022俄乌 vs 2026美伊)
    # ============================================================
    print("\n[分析3] 子样本期间分解")
    print("-" * 50)
    
    periods = {
        "2022_俄乌": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
        "2024_平稳": (pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31")),
        "2025_冲突升级": (pd.Timestamp("2025-06-01"), pd.Timestamp("2026-05-08")),
    }
    
    for regime_col in ["composite_hawkish", "composite_strong"]:
        aligned = regime_df[regime_col].reindex(return_df.index)
        for symbol in ["USTEC", "US500"]:
            for pname, (start, end) in periods.items():
                mask = (return_df.index >= start) & (return_df.index <= end)
                valid = pd.DataFrame({
                    regime_col: aligned[mask],
                    symbol: return_df[symbol][mask]
                }).dropna()
                
                if len(valid) < 30:
                    continue
                
                in_r = valid[valid[regime_col] == True][symbol]
                out_r = valid[valid[regime_col] == False][symbol]
                
                if len(in_r) < 10 or len(out_r) < 10:
                    print(f"  {regime_col}/{symbol}/{pname}: 样本不足 (in={len(in_r)}, out={len(out_r)})")
                    continue
                
                from scipy import stats
                t_stat, p_value = stats.ttest_ind(in_r, out_r, equal_var=False)
                
                cum_in = (1 + in_r).cumprod()
                total_in = cum_in.iloc[-1] - 1
                
                cum_out = (1 + out_r).cumprod()
                total_out = cum_out.iloc[-1] - 1
                
                sig = "***" if p_value < 0.01 else ("**" if p_value < 0.05 else ("*" if p_value < 0.1 else "n.s."))
                
                print(f"  {regime_col}/{symbol}/{pname}:")
                print(f"    Regime内: 总收益 {total_in*100:+.2f}% ({len(in_r)}天)")
                print(f"    Regime外: 总收益 {total_out*100:+.2f}% ({len(out_r)}天)")
                print(f"    t={t_stat:.3f} p={p_value:.4f} {sig}")
    
    # ============================================================
    # 分析 4: 最优阈值搜索
    # ============================================================
    print("\n[分析4] 最优油价阈值搜索 (USTEC)")
    print("-" * 50)
    
    from scipy import stats
    
    best_p = 1.0
    best_threshold = 0
    best_results = {}
    
    for threshold in [70, 75, 80, 85, 90, 95, 100, 105, 110]:
        hi_oil = ukoil["close"] > threshold
        aligned = hi_oil.reindex(return_df.index)
        valid = pd.DataFrame({"regime": aligned, "ustec": return_df["USTEC"]}).dropna()
        warmup = valid.index.min() + pd.Timedelta(days=365)
        valid = valid[valid.index >= warmup]
        
        in_r = valid[valid["regime"] == True]["ustec"]
        out_r = valid[valid["regime"] == False]["ustec"]
        
        if len(in_r) < 20 or len(out_r) < 200:
            continue
        
        t_stat, p_value = stats.ttest_ind(in_r, out_r, equal_var=False)
        
        ann_in = ((1 + in_r).cumprod().iloc[-1]) ** (252/len(in_r)) - 1
        ann_out = ((1 + out_r).cumprod().iloc[-1]) ** (252/len(out_r)) - 1
        
        sig = "***" if p_value < 0.01 else ("**" if p_value < 0.05 else ("*" if p_value < 0.1 else "n.s."))
        
        print(f"  阈值 ${threshold}: Regime内年化 {ann_in*100:+.2f}% ({len(in_r)}天) vs 外 {ann_out*100:+.2f}% | p={p_value:.4f} {sig}")
        
        if p_value < best_p and len(in_r) >= 30:
            best_p = p_value
            best_threshold = threshold
            best_results = {
                "threshold": threshold, "p": p_value, "t": t_stat,
                "ann_in": ann_in, "ann_out": ann_out, "n_in": len(in_r)
            }
    
    print(f"\n  最优阈值: ${best_threshold} (p={best_results.get('p', 'N/A')})")
    
    # 保存结果
    result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "supplementary_results.json")
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n✅ 补充分析完成, 结果已保存至: {result_path}")
    
    return results


if __name__ == "__main__":
    main()
