#!/usr/bin/env python3
"""discovery_engine.py — 共享全指标扫描发现引擎 (v2)

独立于具体研究目录，通过 --data-dir 指向任意数据目录运行。
用法:
  python3 discovery_engine.py --data-dir ../research/kanban/scalping-m1/data
  python3 discovery_engine.py --data-dir ../research/kanban/high-rr-research/data
  python3 discovery_engine.py --data-dir ../research/kanban/futures-intraday/data
"""
import sys, os, json, logging, time, re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("discovery")

# ── 共享库 ──
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from batch_precompute import compute_all_fast as _calc_all
from mt5_symbols import MT5_SYMBOLS_19

# ── 排除字段 ──
EXCLUDE_COLS = {
    "open", "high", "low", "close", "volume", "time",
    "spread", "tick_volume", "real_volume", "body", "range",
    "upper_shadow", "lower_shadow",
    "ma3", "ma5", "ma8", "ma10", "ma13",
    "ma20", "ma21", "ma30", "ma34", "ma50",
    "ma55", "ma89", "ma100", "ma144", "ma200",
    "bb_20_2_mid", "bb_20_2_upper", "bb_20_2_lower",
}

SESSIONS = ["asia", "europe", "us"]
SUPPORTED_TFS = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]


# ================================================================
# 1. 列类型检测
# ================================================================
def categorize_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    cats = {"bool": [], "int": [], "pct": [], "raw": []}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in EXCLUDE_COLS:
            continue
        if any(excl in col_lower for excl in ["time", "date", "index"]):
            continue
        dtype = df[col].dtype
        series = df[col].dropna()
        if series.empty:
            continue
        unique_vals = series.unique()
        if dtype == bool or (dtype in (int, float) and set(unique_vals) <= {0, 1}):
            cats["bool"].append(col)
        elif dtype in (int, np.int64):
            cats["int"].append(col)
        elif "pct" in col_lower or "ratio" in col_lower:
            cats["pct"].append(col)
        else:
            cats["raw"].append(col)
    return cats


# ================================================================
# 2. 数据加载
# ================================================================
def load_raw_data(data_dir: str, timeframe: str,
                  symbols: Optional[List[str]] = None,
                  max_rows: int = 20000) -> Dict[str, pd.DataFrame]:
    """从 data_dir/{tf}/{symbol}.parquet 加载原始 OHLCV 数据"""
    tf_dir = Path(data_dir) / timeframe
    if not tf_dir.exists():
        log.warning("目录不存在: %s", tf_dir)
        return {}

    if symbols is None:
        symbols = sorted(p.stem for p in tf_dir.glob("*.parquet")
                         if p.stem != "indicators")
        # 只保留标准品种
        symbols = [s for s in symbols if s in MT5_SYMBOLS_19]

    result = {}
    for sym in symbols:
        f = tf_dir / f"{sym}.parquet"
        if not f.exists():
            log.warning("文件缺失: %s", f)
            continue
        try:
            df = pd.read_parquet(f)
            if df.empty:
                continue
            # 确保 datetime index
            if not isinstance(df.index, pd.DatetimeIndex):
                if "time" in df.columns:
                    df["time"] = pd.to_datetime(df["time"])
                    df = df.set_index("time")
                else:
                    continue
            df = df.sort_index()
            # 只保留 OHLCV 基础列
            keep = [c for c in ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
                    if c in df.columns]
            if not all(c in df.columns for c in ["open", "high", "low", "close"]):
                continue
            df = df[keep]
            # 采样加速
            if len(df) > max_rows:
                df = df.iloc[-max_rows:].copy()
            result[sym] = df
            log.info("  %s %s: %d rows [%s → %s]", sym, timeframe, len(df),
                     df.index[0].strftime("%Y-%m-%d"), df.index[-1].strftime("%Y-%m-%d"))
        except Exception as e:
            log.warning("  %s 读取失败: %s", sym, e)
    return result


# ================================================================
# 3. 候选条件生成（双向，全列覆盖）
# ================================================================
def generate_conditions(df: pd.DataFrame, symbol: str) -> List[Dict]:
    cats = categorize_columns(df)
    candidates = []

    # 2a. Bool 列
    for col in cats["bool"]:
        if df[col].sum() < 10:
            continue
        for session in SESSIONS:
            for direction in ["long", "short"]:
                candidates.append({
                    "condition": f"{col} == 1 and session == '{session}'",
                    "symbol": symbol, "direction": direction,
                    "type": f"bool_{col}_{direction}", "source_col": col,
                })

    # 2b. RSI — 双向，全门槛
    for col in cats["raw"] + cats["pct"]:
        if "rsi" not in col.lower():
            continue
        series = df[col].dropna()
        for threshold in [5, 10, 15, 18, 20, 25, 30]:
            if series.min() > threshold:
                continue
            for session in SESSIONS:
                candidates.append({
                    "condition": f"{col} < {threshold} and session == '{session}'",
                    "symbol": symbol, "direction": "long",
                    "type": f"rsi_oversold_{col}", "source_col": col,
                })
        for threshold in [70, 75, 80, 85]:
            if series.max() < threshold:
                continue
            for session in SESSIONS:
                candidates.append({
                    "condition": f"{col} > {threshold} and session == '{session}'",
                    "symbol": symbol, "direction": "short",
                    "type": f"rsi_overbought_{col}", "source_col": col,
                })

    # 2c. 数值列 — 双向，全列
    for col in cats["raw"] + cats["pct"]:
        if "rsi" in col.lower() or "slope" in col.lower() or "trend" in col.lower():
            continue
        series = df[col].dropna()
        if series.nunique() < 5:
            continue
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        for session in SESSIONS:
            candidates.append({
                "condition": f"{col} < {round(q1, 4)} and session == '{session}'",
                "symbol": symbol, "direction": "long",
                "type": f"low_{col}", "source_col": col,
            })
            candidates.append({
                "condition": f"{col} > {round(q3, 4)} and session == '{session}'",
                "symbol": symbol, "direction": "short",
                "type": f"high_{col}", "source_col": col,
            })

    # 2d. 斜率 — 双向，全列
    for col in cats["pct"] + cats["raw"]:
        if "slope" not in col.lower() and "trend" not in col.lower():
            continue
        for session in SESSIONS:
            candidates.append({
                "condition": f"{col} > 0 and session == '{session}'",
                "symbol": symbol, "direction": "long",
                "type": f"slope_{col}", "source_col": col,
            })
            candidates.append({
                "condition": f"{col} < 0 and session == '{session}'",
                "symbol": symbol, "direction": "short",
                "type": f"slope_{col}_neg", "source_col": col,
            })

    # 2e. Weekday — 双向
    for col in cats["bool"]:
        if not any(day in col.lower() for day in ["monday", "tuesday", "wednesday",
                                                    "thursday", "friday", "weekend"]):
            continue
        if df[col].sum() < 10:
            continue
        for session in SESSIONS:
            for direction in ["long", "short"]:
                candidates.append({
                    "condition": f"{col} == 1 and session == '{session}'",
                    "symbol": symbol, "direction": direction,
                    "type": f"weekday_{col}_{direction}", "source_col": col,
                })

    # 2f. Consecutive — 全门槛 + 双向
    for col in cats["int"]:
        if "consecutive" not in col.lower():
            continue
        if "bear" not in col.lower() and "bull" not in col.lower():
            continue
        series = df[col].dropna()
        for thresh in [2, 3, 4, 5]:
            if series.max() < thresh:
                continue
            for session in SESSIONS:
                for direction in ["long", "short"]:
                    candidates.append({
                        "condition": f"{col} >= {thresh} and session == '{session}'",
                        "symbol": symbol, "direction": direction,
                        "type": f"cb_{col}_{direction}", "source_col": col,
                    })
    return candidates


# ================================================================
# 4. 批量回测
# ================================================================
def batch_test(df: pd.DataFrame, candidates: List[Dict],
               hold_periods: List[int] = None) -> List[Dict]:
    if hold_periods is None:
        hold_periods = [3, 5, 10, 20, 30]

    results = []
    for cand in candidates:
        condition = cand["condition"]
        direction = cand["direction"]
        symbol = cand["symbol"]
        try:
            mask = df.eval(condition)
            entry_count = mask.sum()
            if entry_count < 20:
                continue
            entry_indices = np.where(mask.values)[0]
            entry_prices = df["close"].values[entry_indices]
            closes = df["close"].values
            n = len(closes)
            for hold in hold_periods:
                exit_positions = entry_indices + hold
                valid = exit_positions < n
                if valid.sum() < 20:
                    continue
                entry = entry_prices[valid]
                exit_ = closes[exit_positions[valid]]
                if direction == "long":
                    returns = (exit_ - entry) / entry
                else:
                    returns = (entry - exit_) / entry
                n_trades = len(returns)
                if n_trades < 20:
                    continue
                win_rate = float((returns > 0).mean())
                avg_return = float(returns.mean())
                std = float(returns.std()) if returns.std() > 0 else 1e-10
                sharpe = float(avg_return / std)
                results.append({
                    "condition": condition, "symbol": symbol,
                    "direction": direction, "hold": hold,
                    "type": cand.get("type", "?"),
                    "n": int(n_trades),
                    "win_rate": round(win_rate * 100, 1),
                    "avg_return": round(avg_return * 100, 3),
                    "sharpe": round(sharpe, 2),
                })
        except Exception as e:
            log.debug("跳过 %s: %s", condition, e)
    return results


# ================================================================
# 5. 汇总输出
# ================================================================
def findings_to_best_known(results: List[Dict], top_n: int = 20) -> Dict[str, str]:
    valid = [r for r in results if r["n"] >= 30]
    if not valid:
        return {}
    valid.sort(key=lambda r: (r["sharpe"] * np.log10(r["n"] + 1)), reverse=True)
    best_known = {}
    for i, r in enumerate(valid[:top_n]):
        cond = r["condition"]
        sym = r["symbol"]
        tf = "M5"
        dir_cn = "做多" if r["direction"] == "long" else "做空"
        sid = f"auto_{sym}_M5_{r['direction']}_{i}"
        desc = f"{sym} M5 {dir_cn}: {cond} WR={r['win_rate']}% n={r['n']} hold={r['hold']} avg_ret={r['avg_return']}% Sharpe={r['sharpe']}"
        best_known[sid] = desc
    return best_known


# ================================================================
# 6. 主流程
# ================================================================
def run_discovery(data_dir: str, timeframe: str = "M5",
                  symbols: Optional[List[str]] = None,
                  dry_run: bool = False, top_n: int = 20) -> Dict:
    log.info("🚀 全指标发现: %s %s (data=%s)", timeframe,
             symbols or "all19", data_dir)
    start = time.time()
    all_results = []

    raw_data = load_raw_data(data_dir, timeframe, symbols)
    for sym, raw in raw_data.items():
        log.info("📊 计算 %s %s 指标...", sym, timeframe)
        t0 = time.time()
        df = _calc_all(raw, timeframe)
        if df is None or df.empty:
            continue
        log.info("  ✅ %d 行 × %d 列 (%ds)", len(df), len(df.columns), time.time() - t0)

        candidates = generate_conditions(df, sym)
        log.info("  🎯 %d 候选条件(双向)", len(candidates))

        if dry_run:
            for c in candidates[:5]:
                log.info("    %s | %s | %s", c["type"], c["direction"], c["condition"])
            continue

        t1 = time.time()
        sym_results = batch_test(df, candidates)
        all_results.extend(sym_results)
        log.info("  🏆 %d 合格发现 (%ds)", len(sym_results), time.time() - t1)

    if dry_run:
        return {"status": "dry_run", "total_candidates": sum(
            len(generate_conditions(_calc_all(raw_data[s], timeframe), s))
            for s in raw_data) if raw_data else 0}

    log.info("=" * 60)
    log.info("📈 总结果: %d 个", len(all_results))

    if all_results:
        all_results.sort(key=lambda r: (r["sharpe"] * np.log10(max(r["n"], 1) + 1)), reverse=True)
        log.info("\n🏆 TOP 15:")
        for r in all_results[:15]:
            log.info("  %s %s %s WR=%.1f%% n=%d Sharpe=%.2f",
                     r["symbol"], r["direction"], r["condition"],
                     r["win_rate"], r["n"], r["sharpe"])

    return {
        "status": "completed",
        "timeframe": timeframe,
        "symbols": list(raw_data.keys()),
        "total_findings": len(all_results),
        "duration_s": round(time.time() - start, 1),
        "top_findings": all_results[:top_n],
        "best_known": findings_to_best_known(all_results, top_n),
    }


# ================================================================
# 7. CLI
# ================================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="共享全指标发现引擎 v2")
    parser.add_argument("--data-dir", required=True,
                        help="数据目录 (含 {TF}/{symbol}.parquet)")
    parser.add_argument("--tf", default="M5",
                        help=f"时间框架 ({','.join(SUPPORTED_TFS)})")
    parser.add_argument("--symbols", default=None,
                        help="品种(逗号分隔,默认全部19)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成候选不跑回测")
    parser.add_argument("--top", type=int, default=20,
                        help="输出前N个")
    parser.add_argument("--save", default=None,
                        help="结果保存路径 (默认打印到 stdout)")
    args = parser.parse_args()

    if args.symbols:
        syms = args.symbols.split(",")
    else:
        syms = None

    result = run_discovery(
        data_dir=args.data_dir,
        timeframe=args.tf,
        symbols=syms,
        dry_run=args.dry_run,
        top_n=args.top,
    )

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.save:
        os.makedirs(os.path.dirname(args.save) or ".", exist_ok=True)
        with open(args.save, "w") as f:
            f.write(output)
        log.info("✅ 结果已保存到 %s", args.save)
    else:
        print(output)
