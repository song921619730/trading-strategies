#!/usr/bin/env python3
"""
run_candlestick.py — K线形态研究回测引擎（v2 使用MT5本地数据）

检测K线形态 + 自定义入场条件，测试对未来价格走势的预测能力。
支持多品种、多时间框架、多持有期。

用法:
    from run_candlestick import run_pattern_test
    results = run_pattern_test(
        entry_condition="rsi14 < 40 and session == 'us' and doji == True",
        direction="long",
        timeframe="H1",
        symbols=["XAUUSD", "EURUSD", "US30", "JP225"],
        hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
    )
"""

import json
import os
import re
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")

# ─── 数据路径 ───
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data", "research")

_DATA_CACHE: dict[str, pd.DataFrame] = {}


def _fetch_data(
    symbol: str,
    timeframe: str = "H1",
) -> pd.DataFrame:
    """从本地CSV文件获取数据"""
    cache_key = f"{symbol}_{timeframe}"
    
    if cache_key in _DATA_CACHE:
        return _DATA_CACHE[cache_key].copy()
    
    csv_path = os.path.join(DATA_DIR, f"{symbol}_{timeframe}.csv")
    if not os.path.exists(csv_path):
        print(f"  [WARN] 数据文件不存在: {csv_path}")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(csv_path, parse_dates=["time"])
        df.set_index("time", inplace=True)
        df.index.name = "time"
        
        # 统一列名
        df.columns = [c.strip().lower() for c in df.columns]
        
        # 排序
        df.sort_index(inplace=True)
        
        # 去重
        df = df[~df.index.duplicated(keep="last")]
        
        _DATA_CACHE[cache_key] = df.copy()
        return df
    except Exception as e:
        print(f"  [WARN] 读取 {csv_path} 失败: {e}")
        return pd.DataFrame()


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算技术指标和形态特征"""
    if df.empty or len(df) < 50:
        return df
    
    d = df.copy()
    
    # RSI(14)
    delta = d["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    d["rsi14"] = 100 - (100 / (1 + rs))
    
    # ATR(14)
    high_low = d["high"] - d["low"]
    high_close = (d["high"] - d["close"].shift()).abs()
    low_close = (d["low"] - d["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()
    
    # ATR%
    d["atr14_pct"] = d["atr14"] / d["close"] * 100
    
    # MA
    d["ma20"] = d["close"].rolling(20).mean()
    d["ma50"] = d["close"].rolling(50).mean()
    d["ma200"] = d["close"].rolling(200).mean()
    
    # Bollinger Bands
    d["bb_mid"] = d["close"].rolling(20).mean()
    bb_std = d["close"].rolling(20).std()
    d["bb_upper"] = d["bb_mid"] + 2 * bb_std
    d["bb_lower"] = d["bb_mid"] - 2 * bb_std
    
    # 涨跌幅
    d["pct_chg"] = d["close"].pct_change() * 100
    
    # 跳空缺口
    d["gap_pct"] = (d["open"] - d["close"].shift(1)) / d["close"].shift(1) * 100
    
    # 时间特征
    d["hour"] = d.index.hour
    d["dayofweek"] = d.index.dayofweek
    
    # 交易时段 (UTC)
    def get_session(h):
        if 0 <= h < 8:
            return "asia"
        elif 8 <= h < 16:
            return "london"
        elif 13 <= h < 22:
            return "us"
        else:
            return "asia" if h < 13 else "london"
    
    d["session"] = d["hour"].apply(get_session)
    
    # 连续涨跌计数
    d["consecutive_bull_count"] = 0
    d["consecutive_bear_count"] = 0
    bull_streak = 0
    bear_streak = 0
    for i in range(len(d)):
        if i == 0:
            continue
        if d.iloc[i]["close"] > d.iloc[i - 1]["close"]:
            bull_streak += 1
            bear_streak = 0
        elif d.iloc[i]["close"] < d.iloc[i - 1]["close"]:
            bear_streak += 1
            bull_streak = 0
        else:
            bull_streak = 0
            bear_streak = 0
        d.iloc[i, d.columns.get_loc("consecutive_bull_count")] = bull_streak
        d.iloc[i, d.columns.get_loc("consecutive_bear_count")] = bear_streak
    
    return d


def _detect_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """检测K线形态"""
    if df.empty or len(df) < 5:
        return df
    
    d = df.copy()
    
    # 实体和影线
    d["body"] = abs(d["close"] - d["open"])
    d["upper_shadow"] = d["high"] - d[["open", "close"]].max(axis=1)
    d["lower_shadow"] = d[["open", "close"]].min(axis=1) - d["low"]
    d["body_pct"] = d["body"] / (d["high"] - d["low"]).replace(0, 1e-10)
    d["is_bull"] = d["close"] > d["open"]
    d["is_bear"] = d["close"] < d["open"]
    d["range"] = d["high"] - d["low"]
    d["avg_range"] = d["range"].rolling(20).mean()
    
    # ─── 单条形态 ───
    # doji: 实体非常小
    d["doji"] = (d["body"] <= d["range"] * 0.1) & (d["range"] > 0)
    
    # hammer: 下影线 ≥ 实体的2倍，上影线短
    d["hammer"] = (d["lower_shadow"] >= d["body"] * 2) & (d["upper_shadow"] <= d["body"] * 0.5) & (d["body"] > 0)
    # shooting_star: 上影线 ≥ 实体的2倍，下影线短
    d["shooting_star"] = (d["upper_shadow"] >= d["body"] * 2) & (d["lower_shadow"] <= d["body"] * 0.5) & (d["body"] > 0)
    # pin_bar: 长影线
    d["pin_bar"] = ((d["upper_shadow"] >= d["body"] * 2) | (d["lower_shadow"] >= d["body"] * 2)) & (d["body"] > 0)
    
    # marubozu: 光头光脚
    d["marubozu_bull"] = (d["is_bull"]) & (d["upper_shadow"] <= d["body"] * 0.05) & (d["lower_shadow"] <= d["body"] * 0.05) & (d["body"] > 0)
    d["marubozu_bear"] = (d["is_bear"]) & (d["upper_shadow"] <= d["body"] * 0.05) & (d["lower_shadow"] <= d["body"] * 0.05) & (d["body"] > 0)
    
    # inside_bar
    d["inside_bar"] = (d["high"] <= d["high"].shift(1)) & (d["low"] >= d["low"].shift(1)) & (d["range"] > 0)
    
    # ─── 双条形态 ───
    # engulfing_bull: 阳线包住前一根阴线
    prev_bear = d["is_bear"].shift(1) == True
    d["engulfing_bull"] = (d["is_bull"]) & (d["open"] <= d["close"].shift(1)) & (d["close"] >= d["open"].shift(1)) & prev_bear
    # engulfing_bear: 阴线包住前一根阳线
    prev_bull = d["is_bull"].shift(1) == True
    d["engulfing_bear"] = (d["is_bear"]) & (d["open"] >= d["close"].shift(1)) & (d["close"] <= d["open"].shift(1)) & prev_bull
    
    # tweezers
    d["tweezer_top"] = (abs(d["high"] - d["high"].shift(1)) / d["range"].replace(0, 1e-10) < 0.05) & (d["range"] > 0)
    d["tweezer_bottom"] = (abs(d["low"] - d["low"].shift(1)) / d["range"].replace(0, 1e-10) < 0.05) & (d["range"] > 0)
    
    # harami
    d["harami_bull"] = (d["is_bull"]) & (d["high"] <= d["high"].shift(1)) & (d["low"] >= d["low"].shift(1)) & (d["body"] < d["body"].shift(1) * 0.5) & (d["is_bull"].shift(1) == False)
    d["harami_bear"] = (d["is_bear"]) & (d["high"] <= d["high"].shift(1)) & (d["low"] >= d["low"].shift(1)) & (d["body"] < d["body"].shift(1) * 0.5) & (d["is_bull"].shift(1) == True)
    
    # ─── 三条形态 ───
    # three_white_soldiers
    d["three_white_soldiers"] = (
        d["is_bull"] & d["is_bull"].shift(1) & d["is_bull"].shift(2)
        & (d["close"] > d["close"].shift(1))
        & (d["close"].shift(1) > d["close"].shift(2))
        & (d["open"] > d["open"].shift(1))
        & (d["open"].shift(1) > d["open"].shift(2))
    )
    
    # three_black_crows
    d["three_black_crows"] = (
        d["is_bear"] & d["is_bear"].shift(1) & d["is_bear"].shift(2)
        & (d["close"] < d["close"].shift(1))
        & (d["close"].shift(1) < d["close"].shift(2))
        & (d["open"] < d["open"].shift(1))
        & (d["open"].shift(1) < d["open"].shift(2))
    )
    
    # morning_star
    d["morning_star"] = (
        d["is_bear"].shift(1) & d["is_bull"]
        & (d["body"].shift(1) > d["avg_range"].shift(1) * 0.5)
        & (d["body"] > d["avg_range"] * 0.5)
        & (d["close"] > (d["high"].shift(1) + d["low"].shift(1)) / 2)
    )
    
    # evening_star
    d["evening_star"] = (
        d["is_bull"].shift(1) & d["is_bear"]
        & (d["body"].shift(1) > d["avg_range"].shift(1) * 0.5)
        & (d["body"] > d["avg_range"] * 0.5)
        & (d["close"] < (d["high"].shift(1) + d["low"].shift(1)) / 2)
    )
    
    # ─── 综合形态 ───
    d["bull_reversal"] = d["hammer"] | d["morning_star"] | (d["engulfing_bull"] & d["tweezer_bottom"].shift(1))
    d["bear_reversal"] = d["shooting_star"] | d["evening_star"] | (d["engulfing_bear"] & d["tweezer_top"].shift(1))
    d["bull_continuation"] = d["three_white_soldiers"] | (d["marubozu_bull"] & d["is_bull"].shift(1))
    d["bear_continuation"] = d["three_black_crows"] | (d["marubozu_bear"] & d["is_bear"].shift(1))
    
    return d


def _eval_condition_vectorized(df: pd.DataFrame, condition_str: str) -> pd.Series:
    """向量化评估条件"""
    if not condition_str or condition_str.strip() == "":
        return pd.Series(True, index=df.index)
    
    result = pd.Series(True, index=df.index)
    conditions = re.split(r'\s+and\s+', condition_str.strip())
    is_or = " or " in condition_str.lower()
    
    if is_or:
        # 简单处理or的情况 - 用逐行eval
        return pd.Series([_eval_single(df, i, condition_str) for i in range(len(df))], index=df.index)
    
    for cond in conditions:
        cond = cond.strip()
        try:
            sub = _eval_single_cond(df, cond)
            if sub is not None:
                result = result & sub
        except:
            pass
    
    return result


def _eval_single_cond(df: pd.DataFrame, cond: str) -> pd.Series:
    """评估单个条件"""
    # 模式: column operator value
    # rsi14 < 40
    m = re.match(r'(\w+)\s*(<=|>=|!=|==|<|>)\s*([0-9.]+)', cond)
    if m:
        col, op, val_str = m.group(1), m.group(2), m.group(3)
        if col not in df.columns:
            return None
        try:
            if '.' in val_str:
                val = float(val_str)
            else:
                val = int(val_str)
        except:
            val = float(val_str)
        
        if df[col].dtype in (np.float64, np.int64, float, int):
            if op == '<': return df[col] < val
            elif op == '>': return df[col] > val
            elif op == '<=': return df[col] <= val
            elif op == '>=': return df[col] >= val
            elif op == '==': return df[col] == val
            elif op == '!=': return df[col] != val
        return None
    
    # 模式: session == 'us'
    m = re.match(r"(\w+)\s*==\s*'(\w+)'", cond)
    if m:
        col, val = m.group(1), m.group(2)
        if col in df.columns:
            return df[col] == val
    
    # 模式: doji == True 或 doji
    m = re.match(r'(\w+)\s*==\s*True', cond)
    if m:
        col = m.group(1)
        if col in df.columns:
            return df[col] == True
    
    m = re.match(r'(\w+)\s*==\s*False', cond)
    if m:
        col = m.group(1)
        if col in df.columns:
            return df[col] == False
    
    # 纯形态名
    if cond in df.columns and df[cond].dtype == bool:
        return df[cond] == True
    
    return None


def _eval_single(df: pd.DataFrame, idx: int, condition_str: str) -> bool:
    """逐行评估条件"""
    row = df.iloc[idx]
    local_vars = {}
    
    for col in df.columns:
        val = row[col]
        if isinstance(val, (np.integer,)):
            local_vars[col] = int(val)
        elif isinstance(val, (np.floating,)):
            local_vars[col] = float(val)
        elif isinstance(val, (np.bool_, bool)):
            local_vars[col] = bool(val)
        elif isinstance(val, str):
            local_vars[col] = val
        elif pd.isna(val):
            return False
        else:
            local_vars[col] = val
    
    try:
        result = eval(condition_str, {"__builtins__": {}}, local_vars)
        return bool(result)
    except:
        return False


def _calculate_future_returns(df: pd.DataFrame, idx: int, hold: int, direction: str) -> float:
    """计算持有后的收益率"""
    if idx + hold >= len(df):
        return np.nan
    
    entry_price = float(df.iloc[idx]["close"])
    exit_price = float(df.iloc[idx + hold]["close"])
    
    if direction == "long":
        ret = (exit_price - entry_price) / entry_price
    else:
        ret = (entry_price - exit_price) / entry_price
    
    return ret * 100


def _calculate_metrics(returns: list[float], threshold: float = 0.0) -> dict:
    """计算统计指标"""
    if len(returns) < 5:
        return {"n": len(returns), "win_rate": 0, "avg_return": 0, "sharpe": 0}
    
    arr = np.array(returns)
    wins = arr > threshold
    win_rate = float(wins.mean()) * 100
    avg_return = float(arr.mean())
    std_return = float(arr.std()) if float(arr.std()) > 0 else 0.001
    sharpe = avg_return / std_return if std_return > 0 else 0
    
    return {
        "n": int(len(arr)),
        "win_rate": round(win_rate, 1),
        "avg_return": round(avg_return, 3),
        "std_return": round(std_return, 3),
        "sharpe": round(sharpe, 2),
        "max_return": round(float(arr.max()), 3),
        "min_return": round(float(arr.min()), 3),
    }


def run_pattern_test(
    entry_condition: str = "",
    direction: str = "long",
    timeframe: str = "H1",
    symbols: list[str] = None,
    hold_periods: list[int] = None,
    verbose: bool = True,
) -> dict:
    """运行K线形态回测"""
    if symbols is None:
        symbols = ["XAUUSD", "EURUSD", "US30", "JP225", "GBPUSD", "AUDUSD"]
    if hold_periods is None:
        hold_periods = [1, 2, 3, 5, 7, 10, 15, 20]
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"📊 K线形态回测")
        print(f"   条件: {entry_condition or '无'}")
        print(f"   方向: {direction}")
        print(f"   时间框架: {timeframe}")
        print(f"   品种: {', '.join(symbols)}")
        print(f"   持有期: {hold_periods}")
        print(f"{'='*70}")
    
    all_results = {}
    best_overall = {"symbol": "", "hold": 0, "win_rate": 0, "n": 0}
    
    for symbol in symbols:
        if verbose:
            print(f"\n🔍 测试 {symbol}...")
        
        df = _fetch_data(symbol, timeframe)
        if df.empty:
            if verbose:
                print(f"  ⚠️  无数据，跳过")
            all_results[symbol] = {"error": "无数据"}
            continue
        
        df = _compute_indicators(df)
        df = _detect_candlestick_patterns(df)
        df = df.dropna()
        
        if len(df) < 50:
            if verbose:
                print(f"  ⚠️  数据不足 ({len(df)} 行)")
            all_results[symbol] = {"error": "数据不足"}
            continue
        
        if verbose:
            print(f"   数据点: {len(df)} 行")
        
        # 评估入场条件
        if entry_condition and entry_condition.strip():
            signal_mask = _eval_condition_vectorized(df, entry_condition)
            entry_indices = np.where(signal_mask)[0]
        else:
            entry_indices = np.arange(len(df))
        
        if verbose:
            print(f"   信号点: {len(entry_indices)}")
        
        symbol_results = {"signal_count": len(entry_indices), "hold_periods": {}}
        
        for hold in hold_periods:
            returns = []
            for idx in entry_indices:
                ret = _calculate_future_returns(df, idx, hold, direction)
                if not np.isnan(ret):
                    returns.append(ret)
            
            metrics = _calculate_metrics(returns)
            symbol_results["hold_periods"][hold] = metrics
            
            if metrics["n"] >= 10:
                if verbose:
                    print(f"   持有 {hold:2d}期: WR={metrics['win_rate']:5.1f}%  n={metrics['n']:4d}  Avg={metrics['avg_return']:+.3f}%  Sharpe={metrics['sharpe']:.2f}")
                
                if metrics["win_rate"] > best_overall["win_rate"] and metrics["n"] >= 15:
                    best_overall = {
                        "symbol": symbol,
                        "hold": hold,
                        "win_rate": metrics["win_rate"],
                        "n": metrics["n"],
                        "sharpe": metrics["sharpe"],
                        "avg_return": metrics["avg_return"],
                    }
            else:
                if verbose:
                    print(f"   持有 {hold:2d}期: WR={metrics['win_rate']:5.1f}%  n={metrics['n']:4d} ⚠️")
        
        all_results[symbol] = symbol_results
    
    summary = {
        "entry_condition": entry_condition,
        "direction": direction,
        "timeframe": timeframe,
        "symbols_tested": symbols,
        "hold_periods": hold_periods,
        "best_overall": best_overall,
        "details": all_results,
        "total_signals": sum(
            v.get("signal_count", 0) for v in all_results.values()
            if isinstance(v, dict) and "error" not in v
        ),
    }
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"📈 最佳结果: {best_overall['symbol']} | 持{best_overall['hold']}期 | WR={best_overall['win_rate']:.1f}% | n={best_overall['n']}")
        print(f"{'='*70}\n")
    
    return summary


def run_pattern_test_enhanced(
    entry_condition: str = "",
    direction: str = "long",
    timeframe: str = "H1",
    symbols: list[str] = None,
    hold_periods: list[int] = None,
    verbose: bool = True,
    min_pattern_count: int = 5,
) -> dict:
    """增强版回测：分别测试每种K线形态的表现"""
    if symbols is None:
        symbols = ["XAUUSD", "EURUSD", "US30", "JP225", "GBPUSD", "AUDUSD"]
    if hold_periods is None:
        hold_periods = [1, 2, 3, 5, 7, 10, 15, 20]
    
    pattern_names = [
        "doji", "inside_bar", "engulfing_bull", "engulfing_bear",
        "hammer", "shooting_star", "pin_bar",
        "marubozu_bull", "marubozu_bear",
        "tweezer_top", "tweezer_bottom",
        "harami_bull", "harami_bear",
        "three_white_soldiers", "three_black_crows",
        "morning_star", "evening_star",
        "bull_reversal", "bear_reversal",
        "bull_continuation", "bear_continuation",
    ]
    
    print(f"\n{'='*70}")
    print(f"🔬 增强K线形态分析")
    print(f"   基础条件: {entry_condition or '无'}")
    print(f"   方向: {direction}")
    print(f"   时间框架: {timeframe}")
    print(f"{'='*70}")
    
    all_pattern_results = {}
    
    for symbol in symbols:
        print(f"\n🔍 测试 {symbol}...")
        df = _fetch_data(symbol, timeframe)
        if df.empty:
            print(f"  ⚠️  跳过（无数据）")
            continue
        
        df = _compute_indicators(df)
        df = _detect_candlestick_patterns(df)
        df = df.dropna()
        
        if len(df) < 50:
            continue
        
        if entry_condition and entry_condition.strip():
            base_mask = _eval_condition_vectorized(df, entry_condition)
        else:
            base_mask = pd.Series(True, index=df.index)
        
        for pname in pattern_names:
            if pname not in df.columns:
                continue
            
            combined = base_mask & (df[pname] == True)
            entry_indices = np.where(combined)[0]
            
            if len(entry_indices) < min_pattern_count:
                continue
            
            if pname not in all_pattern_results:
                all_pattern_results[pname] = {}
            
            symbol_pattern_results = {}
            for hold in hold_periods:
                returns = []
                for idx in entry_indices:
                    ret = _calculate_future_returns(df, idx, hold, direction)
                    if not np.isnan(ret):
                        returns.append(ret)
                metrics = _calculate_metrics(returns)
                symbol_pattern_results[hold] = metrics
            
            all_pattern_results[pname][symbol] = {
                "count": len(entry_indices),
                "hold_results": symbol_pattern_results,
            }
    
    # 汇总最佳形态
    print(f"\n{'='*70}")
    print(f"📊 形态表现汇总（所有品种综合）")
    print(f"{'='*70}")
    
    pattern_summary = {}
    for pname, pdata in all_pattern_results.items():
        best_wr = 0
        best_hold = 0
        best_symbol = ""
        total_n = 0
        total_wins = 0
        
        for sym, sdata in pdata.items():
            for hold, metrics in sdata["hold_results"].items():
                if metrics["n"] >= 15 and metrics["win_rate"] > best_wr:
                    best_wr = metrics["win_rate"]
                    best_hold = hold
                    best_symbol = sym
                total_n += metrics["n"]
                total_wins += metrics["n"] * metrics["win_rate"] / 100
        
        avg_wr = (total_wins / total_n * 100) if total_n > 0 else 0
        
        pattern_summary[pname] = {
            "best_wr": round(best_wr, 1),
            "best_hold": best_hold,
            "best_symbol": best_symbol,
            "total_n": total_n,
            "avg_wr": round(avg_wr, 1),
        }
        
        if total_n >= 30:
            marker = "⭐" if best_wr > 60 else "  "
            print(f"  {marker} {pname:25s} WR={best_wr:5.1f}% (avg={avg_wr:.1f}%)  n={total_n:4d}  best={best_symbol}@{best_hold}")
    
    return {
        "entry_condition": entry_condition,
        "direction": direction,
        "timeframe": timeframe,
        "pattern_summary": pattern_summary,
        "details": all_pattern_results,
    }


if __name__ == "__main__":
    import sys
    
    # 测试 H1: 美盘 + RSI<40 + doji
    results_h1_doji = run_pattern_test(
        entry_condition="rsi14 < 40 and session == 'us' and doji == True",
        direction="long",
        timeframe="H1",
        symbols=["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "US30", "JP225"],
        hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
        verbose=True,
    )
    
    out_dir = os.path.join(BASE, "logs", "research")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(out_dir, f"research_{ts}.json"), "w") as f:
        json.dump(results_h1_doji, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已保存到 logs/research/research_{ts}.json")
